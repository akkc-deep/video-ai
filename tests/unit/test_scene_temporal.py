"""Native temporal budgets preserve every requested frame and reject protocol drift."""
from copy import deepcopy

import pytest

from unit.test_scene_execution import fixture


@pytest.mark.parametrize('frames,retained', [
    (1, [1]), (13, [13]), (80, [80]), (93, [93]), (94, [93, 1]),
    (173, [93, 80]), (174, [93, 80, 1]), (253, [93, 80, 80]),
    (254, [93, 80, 80, 1]), (320, [93, 80, 80, 67]),
    (321, [93, 80, 80, 68]), (333, [93, 80, 80, 80]),
    (334, [93, 80, 80, 80, 1]), (10001, [93]+[80]*123+[68]),
])
def test_temporal_covers_full_timeline_once_with_only_terminal_trim(frames, retained):
    from video_ai.planning.scene_temporal import derive_temporal_clips, temporal_frame_mapping
    plan, timeline = fixture(frames)
    original = deepcopy(plan)
    clips = derive_temporal_clips(plan, timeline)
    assert [row['retained_frames'] for row in clips] == retained
    assert all(row['generated_frames'] == 93 for row in clips)
    assert [row['discard_head_frames'] for row in clips] == [0]+[13]*(len(clips)-1)
    assert [row['input_kind'] for row in clips] == ['selected_scene_image']+['parent_native_tail_13']*(len(clips)-1)
    assert all(row['trim_tail_frames'] == 0 for row in clips[:-1])
    mappings = [temporal_frame_mapping(row, actual_generated_frames=93) for row in clips]
    assert [item['output_frame'] for mapping in mappings for item in mapping['output_to_generated']] == list(range(frames))
    assert all(mapping['native_fps'] == mapping['output_fps'] == 16 for mapping in mappings)
    for row, mapping in zip(clips, mappings):
        a, b = row['retained_source_start'], row['retained_source_end']
        assert mapping['retained_to_generated'] == list(range(a, b))
        assert sum(value is not None for value in mapping['generated_to_retained']) == row['retained_frames']
    assert plan == original


def test_temporal_320_has_exact_four_window_source_ranges():
    from video_ai.planning.scene_temporal import derive_temporal_clips
    plan, timeline = fixture(320)
    clips = derive_temporal_clips(plan, timeline)
    assert [(row['start_frame'], row['end_frame'], row['retained_source_start'], row['retained_source_end']) for row in clips] == [
        (0, 93, 0, 93), (93, 173, 13, 93), (173, 253, 13, 93), (253, 320, 13, 80)]
    assert [row['parent_clip_id'] for row in clips] == [None, 'scene_0001_clip_0001', 'scene_0001_clip_0002', 'scene_0001_clip_0003']


def test_temporal_resets_history_at_scene_boundary_without_changing_semantic_plan():
    from video_ai.planning.scene_temporal import derive_temporal_clips
    plan, timeline = fixture(94, 174)
    clips = derive_temporal_clips(plan, timeline)
    assert [(row['scene_id'], row['ordinal'], row['start_frame'], row['end_frame'], row['discard_head_frames']) for row in clips] == [
        ('scene_0001', 1, 0, 93, 0), ('scene_0001', 2, 93, 94, 13),
        ('scene_0002', 1, 94, 187, 0), ('scene_0002', 2, 187, 267, 13), ('scene_0002', 3, 267, 268, 13)]
    assert clips[2]['parent_clip_id'] is None


@pytest.mark.parametrize('field,value', [
    ('protocol', 'unknown'), ('generated_frames', 94), ('discard_head_frames', 1),
    ('input_kind', 'parent_retained_last_frame'), ('retained_source_start', 0),
    ('retained_source_end', 92), ('ordinal', True), ('start_frame', 93.0),
    ('end_frame', False), ('trim_tail_frames', -1), ('extra', 1),
])
def test_temporal_clip_drift_cannot_produce_a_mapping(field, value):
    from video_ai.planning.scene_temporal import derive_temporal_clips, validate_temporal_clip
    plan, timeline = fixture(173)
    row = derive_temporal_clips(plan, timeline)[1]
    row[field] = value
    with pytest.raises(ValueError):
        validate_temporal_clip(row)


@pytest.mark.parametrize('fault', ['bool_total', 'float_end', 'gap', 'overlap', 'empty', 'duplicate', 'missing_tail', 'negative'])
def test_temporal_rejects_invalid_or_incomplete_timeline(fault):
    from video_ai.planning.scene_temporal import derive_temporal_clips
    plan, timeline = fixture(93, 80)
    if fault == 'bool_total': plan['total_frames'] = True
    elif fault == 'float_end': plan['scenes'][0]['end_frame'] = 93.0
    elif fault == 'gap': plan['scenes'][1]['start_frame'] = 94
    elif fault == 'overlap': plan['scenes'][1]['start_frame'] = 92
    elif fault == 'empty': plan['scenes'] = []
    elif fault == 'duplicate': plan['scenes'][1]['scene_id'] = 'scene_0001'
    elif fault == 'missing_tail': plan['scenes'].pop()
    else: plan['scenes'][0]['start_frame'] = -1
    with pytest.raises(ValueError): derive_temporal_clips(plan, timeline)


def test_temporal_execution_uses_new_schema_and_legacy_mapping_consumer():
    from video_ai.planning.scene_execution import build_scene_execution_budget, validate_scene_execution_budget
    from video_ai.planning.scene_clip_continuation import scene_clip_frame_mapping, validate_scene_clip_frame_mappings
    plan, timeline = fixture(334)
    identity = dict(run_id='native_run', mode='temporal_extension_v1', rendering_identity_sha256='a'*64,
                    admission=dict(path='D:/VideoSi/native/evidence.json', bytes=100, sha256='b'*64))
    execution = build_scene_execution_budget(plan, timeline, **identity)
    assert (execution['schema_version'], execution['algorithm']) == (2, 'scene_execution_v2')
    assert [row['retained_frames'] for row in execution['clips']] == [93, 80, 80, 80, 1]
    assert validate_scene_execution_budget(execution, plan, timeline, expected=identity) == execution
    mappings = [scene_clip_frame_mapping(row, actual_generated_frames=93) for row in execution['clips']]
    validate_scene_clip_frame_mappings(plan, timeline, mappings, execution=execution)
    assert mappings[-1]['output_to_generated'] == [dict(output_frame=333, generated_frame=13)]
    with pytest.raises(ValueError): scene_clip_frame_mapping(execution['clips'][0], actual_generated_frames=94)


def test_native_rendering_has_exact_evidence_field_and_config_envelope():
    from pathlib import Path
    from video_ai.config import load_config, ConfigError
    from video_ai.runtime.manifest import thaw
    from video_ai.planning.scene_video_prompts import parse_scene_rendering
    from unit.test_jimeng_config import image_settings
    settings = dict(mode='temporal_extension_v1', prompt_policy='visual_v2', prompt_contract='reviewed.json',
                    temporal_evidence='D:/VideoSi/native/evidence.json')
    assert parse_scene_rendering(settings) == settings
    base = load_config(Path(__file__).resolve().parents[2]/'config/production.example.json')
    raw = thaw(base.raw)
    raw.update(production_strategy='paragraph_jimeng_v1', image_generation=image_settings(),
               scene_rendering=settings, scene_continuity=dict(schema_version=1, policy='advisory_v1'))
    raw['media']['profile'] = 'fast'
    assert load_config(base.config_file, raw=raw).raw['scene_rendering']['mode'] == 'temporal_extension_v1'
    raw['media']['profile'] = 'quality'
    with pytest.raises(ConfigError): load_config(base.config_file, raw=raw)
    raw['media']['profile'] = 'fast'
    del raw['scene_continuity']
    with pytest.raises(ConfigError): load_config(base.config_file, raw=raw)
    for path in ('relative.json', 'C:/VideoSi/evidence.json', 'D:/VideoSi/../escape.json', 'D:/VideoSi/a/*.json'):
        invalid = dict(settings, temporal_evidence=path)
        with pytest.raises(ValueError): parse_scene_rendering(invalid)


def test_temporal_schema3_prompt_binds_full_native_clip_coverage():
    from unit.test_scene_video_prompts import fixture as prompt_fixture, reviewed
    from video_ai.planning.scene_temporal import derive_temporal_clips
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.planning.scene_video_prompts import validate_scene_video_prompt_contract
    frozen, bible, plan, timeline, images, contract = prompt_fixture()
    clips = derive_temporal_clips(plan, timeline)
    contract['schema_version'] = 3
    contract['binding'].update(rendering_mode='temporal_extension_v1', execution_clips_sha256=canonical_digest(clips))
    contract['clips'] = [dict(clip_id=row['clip_id'], motion='Continue current motion', camera='Steady tracking',
                              lighting='Maintain current lighting', changes=[]) for row in clips]
    reviewed(contract)
    assert validate_scene_video_prompt_contract(contract, bible=bible, plan=plan, wan_inputs=images, script=frozen.script) == contract
    contract['binding']['rendering_mode'] = 'whole_scene_v1'
    reviewed(contract)
    with pytest.raises(ValueError):
        validate_scene_video_prompt_contract(contract, bible=bible, plan=plan, wan_inputs=images, script=frozen.script)


def test_native_plan_uses_reviewed_visual_text_and_preserves_original_narration():
    from unit.test_scene_video_prompts import fixture as prompt_fixture, reviewed
    from video_ai.planning.scene_temporal import derive_temporal_clips, build_scene_temporal_plan
    from video_ai.planning.scene_execution import build_scene_execution_budget
    from video_ai.planning.production_scenes import canonical_digest
    frozen, bible, plan, timeline, images, contract = prompt_fixture()
    clips = derive_temporal_clips(plan, timeline)
    contract['schema_version'] = 3
    contract['binding'].update(rendering_mode='temporal_extension_v1', execution_clips_sha256=canonical_digest(clips))
    contract['clips'] = [dict(clip_id=row['clip_id'], motion='Continue current motion', camera='Steady tracking',
                              lighting='Maintain current lighting', changes=[]) for row in clips]
    reviewed(contract)
    frozen.config.raw['scene_rendering'].update(mode='temporal_extension_v1', temporal_evidence='D:/VideoSi/native/evidence.json')
    timeline.as_dict = lambda: dict(total_frames=205, total_samples=613001)
    execution = build_scene_execution_budget(plan, timeline, run_id='native_run', mode='temporal_extension_v1',
        rendering_identity_sha256='a'*64, admission=dict(path='D:/VideoSi/native/evidence.json', bytes=100, sha256='b'*64))
    original = deepcopy((bible, plan, images, contract))
    rows = build_scene_temporal_plan(frozen, bible, plan, timeline, images,
                                    prompt_contract=contract, execution=execution)
    assert [row['budget']['retained_frames'] for row in rows] == [1, 93, 80, 27, 4]
    assert [(row['parameters']['width'], row['parameters']['height'], row['parameters']['fps'],
             row['parameters']['steps'], row['parameters']['cfg'], row['parameters']['length']) for row in rows] == [(768, 432, 16, 50, 4.0, 93)]*5
    assert all('Continue current motion' in row['parameters']['positive'] for row in rows)
    assert all(word not in row['parameters']['positive'] for row in rows
               for word in ('VISUAL_BIBLE_JSON', 'AUDIT_ONLY', 'source_facts', 'text_start', 'unit_id'))
    assert all(row['comparison_images'] for row in rows)
    assert [(item['start_sample'], item['end_sample']) for row in rows for item in row['narration_bindings']
            if item['unit_id'] == 'unit_0003'] == [(505000, 522000), (522000, 603000), (603000, 610001)]
    assert (bible, plan, images, contract) == original
