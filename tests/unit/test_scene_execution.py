"""Pure whole-scene budgets preserve the complete original native timeline."""
from copy import deepcopy
from dataclasses import dataclass

import pytest

from video_ai.planning.production_visual_plan import plan_scene_clips


@dataclass
class Timeline:
    total_frames: int

    def as_dict(self):
        return {'total_frames': self.total_frames}


def fixture(*lengths):
    scenes = []
    cursor = 0
    for index, frames in enumerate(lengths, 1):
        scenes.append(dict(scene_id=f'scene_{index:04d}', start_frame=cursor, end_frame=cursor+frames))
        cursor += frames
    plan = dict(scenes=scenes, total_frames=cursor, settings={'max_clip_seconds': 6})
    plan['clips'] = plan_scene_clips(plan, max_clip_seconds=6)
    return plan, Timeline(cursor)


def test_whole_320_retains_every_native_frame_and_requests_321():
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    plan, timeline = fixture(320)
    before = deepcopy(plan)
    clips = derive_scene_execution_clips(plan, timeline, mode='whole_scene_v1')
    assert clips == [dict(clip_id='scene_0001_clip_0001', scene_id='scene_0001', ordinal=1,
        parent_clip_id=None, input_kind='selected_scene_image', start_frame=0, end_frame=320,
        retained_frames=320, generated_frames=321, discard_head_frames=0, trim_tail_frames=1,
        retained_source_start=0, retained_source_end=320)]
    assert plan == before


def test_whole_three_scenes_retain_complete_463_frame_timeline():
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    plan, timeline = fixture(219, 110, 134)
    clips = derive_scene_execution_clips(plan, timeline, mode='whole_scene_v1')
    assert [(c['start_frame'], c['end_frame'], c['generated_frames']) for c in clips] == [
        (0, 219, 221), (219, 329, 113), (329, 463, 137)]
    assert sum(c['retained_frames'] for c in clips) == 463
    assert all(c['parent_clip_id'] is None and c['retained_source_start'] == 0 for c in clips)


def test_whole_rejects_321_retained_frames():
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    plan, timeline = fixture(321)
    with pytest.raises(ValueError, match='320'):
        derive_scene_execution_clips(plan, timeline, mode='whole_scene_v1')


@pytest.mark.parametrize('frames,generated', [(1, 1), (93, 93), (94, 97), (96, 97),
    (110, 113), (134, 137), (219, 221), (320, 321)])
def test_whole_boundaries_keep_exact_prefix_and_discard_only_tail(frames, generated):
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    from video_ai.planning.scene_clip_continuation import scene_clip_frame_mapping
    plan, timeline = fixture(frames)
    clip, = derive_scene_execution_clips(plan, timeline, mode='whole_scene_v1')
    assert clip['generated_frames'] == generated
    mapping = scene_clip_frame_mapping(clip, actual_generated_frames=generated)
    assert mapping['retained_to_generated'] == list(range(frames))
    assert mapping['generated_to_retained'] == list(range(frames)) + [None]*(generated-frames)
    assert mapping['output_to_generated'] == [dict(output_frame=i, generated_frame=i) for i in range(frames)]


@pytest.mark.parametrize('fault', ['gap', 'overlap', 'order', 'missing_tail', 'empty',
    'duplicate_id', 'invalid_id', 'bool_start', 'float_end', 'bool_total', 'timeline_mismatch'])
def test_whole_refuses_noninteger_or_incomplete_scene_coverage(fault):
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    plan, timeline = fixture(110, 134)
    if fault == 'gap': plan['scenes'][1]['start_frame'] += 1
    elif fault == 'overlap': plan['scenes'][1]['start_frame'] -= 1
    elif fault == 'order': plan['scenes'].reverse()
    elif fault == 'missing_tail': plan['scenes'].pop()
    elif fault == 'empty': plan['scenes'] = []
    elif fault == 'duplicate_id': plan['scenes'][1]['scene_id'] = 'scene_0001'
    elif fault == 'invalid_id': plan['scenes'][0]['scene_id'] = 'scene_0000'
    elif fault == 'bool_start': plan['scenes'][0]['start_frame'] = False
    elif fault == 'float_end': plan['scenes'][0]['end_frame'] = 110.0
    elif fault == 'bool_total': plan['total_frames'] = True
    else: timeline.total_frames += 1
    with pytest.raises(ValueError):
        derive_scene_execution_clips(plan, timeline, mode='whole_scene_v1')


def test_whole_is_independent_of_semantic_max_clip_seconds():
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    plan, timeline = fixture(219)
    plan['settings']['max_clip_seconds'] = 7
    plan['clips'] = plan_scene_clips(plan, max_clip_seconds=7)
    clip, = derive_scene_execution_clips(plan, timeline, mode='whole_scene_v1')
    assert (clip['retained_frames'], clip['generated_frames']) == (219, 221)


@pytest.mark.parametrize('frames', [1, 93, 94, 96, 110, 134, 219, 320])
def test_segmented_exactly_preserves_committed_original_budgets(frames):
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    plan, timeline = fixture(frames)
    before = deepcopy(plan)
    actual = derive_scene_execution_clips(plan, timeline, mode='segmented_v1')
    assert actual == plan['clips']
    actual[0]['start_frame'] = 7
    assert plan == before


@pytest.mark.parametrize('fault', ['changed_budget', 'over_96'])
def test_segmented_never_replans_or_relaxes_original_limit(fault):
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    plan, timeline = fixture(219)
    if fault == 'changed_budget': plan['clips'][1]['retained_source_start'] = 0
    else:
        plan['settings']['max_clip_seconds'] = 7
        plan['clips'] = plan_scene_clips(plan, max_clip_seconds=7)
    with pytest.raises(ValueError):
        derive_scene_execution_clips(plan, timeline, mode='segmented_v1')


@pytest.mark.parametrize('mode', [None, True, '', 'whole', 'whole_scene_v2', 'segmented'])
def test_unknown_execution_modes_are_rejected(mode):
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    plan, timeline = fixture(93)
    with pytest.raises(ValueError): derive_scene_execution_clips(plan, timeline, mode=mode)


def expected_identity(mode='whole_scene_v1'):
    return dict(run_id='run_123', mode=mode, rendering_identity_sha256='a'*64,
        admission=dict(path='D:/VideoSi/run/production/scene-rendering/whole-scene-evidence.json',
                       bytes=1024, sha256='b'*64) if mode == 'whole_scene_v1' else None)


@pytest.mark.parametrize('mode', ['whole_scene_v1', 'segmented_v1'])
def test_budget_binds_original_plan_full_timeline_and_frozen_identity(mode):
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.planning.scene_execution import build_scene_execution_budget, validate_scene_execution_budget
    plan, timeline = fixture(219, 110, 134)
    identity = expected_identity(mode)
    before = deepcopy((plan, timeline.as_dict(), identity))
    budget = build_scene_execution_budget(plan, timeline, **identity)
    assert set(budget) == set('schema_version algorithm production_strategy run_id mode scene_plan_sha256 '
        'timeline_sha256 rendering_identity_sha256 admission clips'.split())
    assert (budget['schema_version'], budget['algorithm'], budget['production_strategy']) == (
        1, 'scene_execution_v1', 'paragraph_jimeng_v1')
    assert budget['scene_plan_sha256'] == canonical_digest(plan)
    assert budget['timeline_sha256'] == canonical_digest(timeline.as_dict())
    assert {k: budget[k] for k in identity} == identity
    assert validate_scene_execution_budget(budget, plan, timeline, expected=identity) == budget
    validated = validate_scene_execution_budget(budget, plan, timeline, expected=identity)
    validated['clips'][0]['start_frame'] = 8
    assert budget['clips'][0]['start_frame'] == 0
    assert (plan, timeline.as_dict(), identity) == before


@pytest.mark.parametrize('field,value', [('schema_version', True), ('schema_version', 2),
    ('algorithm', 'unknown'), ('production_strategy', 'legacy'), ('run_id', 'different'),
    ('mode', 'segmented_v1'), ('scene_plan_sha256', 'c'*64), ('timeline_sha256', 'c'*64),
    ('rendering_identity_sha256', 'c'*64), ('admission', None), ('clips', []), ('extra', 1)])
def test_validator_rejects_each_budget_identity_or_schema_drift(field, value):
    from video_ai.planning.scene_execution import build_scene_execution_budget, validate_scene_execution_budget
    plan, timeline = fixture(320)
    identity = expected_identity()
    budget = build_scene_execution_budget(plan, timeline, **identity)
    budget[field] = value
    with pytest.raises(ValueError): validate_scene_execution_budget(budget, plan, timeline, expected=identity)


@pytest.mark.parametrize('field,value', [('retained_frames', 319), ('generated_frames', 325),
    ('discard_head_frames', 1), ('retained_source_start', 1), ('parent_clip_id', 'scene_0000_clip_0001'),
    ('start_frame', False), ('ordinal', True), ('trim_tail_frames', 1.0), ('extra', 1)])
def test_validator_rejects_forged_whole_budget_even_with_valid_identity(field, value):
    from video_ai.planning.scene_execution import build_scene_execution_budget, validate_scene_execution_budget
    plan, timeline = fixture(320)
    identity = expected_identity()
    budget = build_scene_execution_budget(plan, timeline, **identity)
    budget['clips'][0][field] = value
    with pytest.raises(ValueError): validate_scene_execution_budget(budget, plan, timeline, expected=identity)


@pytest.mark.parametrize('field,value', [('run_id', ''), ('run_id', True),
    ('rendering_identity_sha256', 'A'*64), ('admission', None),
    ('admission', {'path': 'relative.json', 'bytes': 1, 'sha256': 'b'*64}),
    ('admission', {'path': 'D:/VideoSi/a.json', 'bytes': True, 'sha256': 'b'*64}),
    ('admission', {'path': 'D:/VideoSi/a.json', 'bytes': 0, 'sha256': 'b'*64}),
    ('admission', {'path': 'D:/VideoSi/a.json', 'bytes': 1, 'sha256': 'invalid'})])
def test_builder_requires_complete_frozen_execution_identity(field, value):
    from video_ai.planning.scene_execution import build_scene_execution_budget
    plan, timeline = fixture(320)
    identity = expected_identity()
    identity[field] = value
    with pytest.raises(ValueError): build_scene_execution_budget(plan, timeline, **identity)


def test_explicit_segmented_rejects_whole_admission():
    from video_ai.planning.scene_execution import build_scene_execution_budget
    plan, timeline = fixture(93)
    identity = expected_identity()
    identity['mode'] = 'segmented_v1'
    with pytest.raises(ValueError): build_scene_execution_budget(plan, timeline, **identity)


def test_mapping_consumer_validates_whole_budget_and_covers_463_frames_once():
    from video_ai.planning.scene_execution import build_scene_execution_budget
    from video_ai.planning.scene_clip_continuation import scene_clip_frame_mapping, validate_scene_clip_frame_mappings
    plan, timeline = fixture(219, 110, 134)
    execution = build_scene_execution_budget(plan, timeline, **expected_identity())
    mappings = [scene_clip_frame_mapping(c, actual_generated_frames=c['generated_frames']) for c in execution['clips']]
    validate_scene_clip_frame_mappings(plan, timeline, mappings, execution=execution)
    assert [r['output_frame'] for m in mappings for r in m['output_to_generated']] == list(range(463))
    assert [m['retained_to_generated'] for m in mappings] == [list(range(219)), list(range(110)), list(range(134))]
    execution['clips'][1]['start_frame'] = 218
    with pytest.raises(ValueError): validate_scene_clip_frame_mappings(plan, timeline, mappings, execution=execution)


def test_validator_hashes_complete_timeline_and_original_semantic_plan():
    from video_ai.planning.scene_execution import build_scene_execution_budget, validate_scene_execution_budget
    plan, timeline = fixture(219)
    identity = expected_identity()
    budget = build_scene_execution_budget(plan, timeline, **identity)
    timeline.as_dict = lambda: {'total_frames': 219, 'original_text': 'changed'}
    with pytest.raises(ValueError): validate_scene_execution_budget(budget, plan, timeline, expected=identity)
    timeline.as_dict = lambda: {'total_frames': 219}
    plan['scenes'][0]['motion_prompt'] = 'changed'
    with pytest.raises(ValueError): validate_scene_execution_budget(budget, plan, timeline, expected=identity)
