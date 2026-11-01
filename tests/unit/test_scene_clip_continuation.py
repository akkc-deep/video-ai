from copy import deepcopy
from types import SimpleNamespace

import json
import pytest

from video_ai.planning import production_visual_plan


def test_200_frame_retained_native_mapping():
    from video_ai.planning.scene_clip_continuation import (
        scene_clip_frame_mapping, validate_scene_clip_frame_mappings)

    plan = {'scenes': [{'scene_id': 'scene_0001', 'start_frame': 0, 'end_frame': 200}],
            'total_frames': 200}
    plan['clips'] = production_visual_plan.plan_scene_clips(plan, max_clip_seconds=6)
    before = deepcopy(plan)
    clips = plan['clips']
    assert [c['retained_frames'] for c in clips] == [93, 92, 15]
    assert [c['generated_frames'] for c in clips] == [93, 93, 17]
    assert [c['retained_source_start'] for c in clips] == [0, 1, 1]
    assert [c['retained_source_end'] - 1 for c in clips] == [92, 92, 15]
    mappings = [scene_clip_frame_mapping(c, actual_generated_frames=c['generated_frames'])
                for c in clips]
    assert mappings[1]['generated_to_retained'][0] is None
    assert mappings[2]['generated_to_retained'][0] is None
    assert mappings[2]['generated_to_retained'][-1] is None
    assert mappings[2]['retained_to_generated'] == list(range(1, 16))
    assert [r['output_frame'] for m in mappings for r in m['output_to_generated']] == list(range(200))
    validate_scene_clip_frame_mappings(plan, SimpleNamespace(total_frames=200), mappings)
    assert plan == before


def _plan(frames):
    plan = dict(scenes=[dict(scene_id='scene_0001', start_frame=0, end_frame=frames)], total_frames=frames)
    plan['clips'] = production_visual_plan.plan_scene_clips(plan, max_clip_seconds=6)
    return plan


@pytest.mark.parametrize('frames', [1, 93, 94, 185, 200])
def test_boundary_frames_are_covered_once_and_generated_discards_are_explicit(frames):
    from video_ai.planning.scene_clip_continuation import scene_clip_frame_mapping, validate_scene_clip_frame_mappings
    plan = _plan(frames)
    mappings = [scene_clip_frame_mapping(c, actual_generated_frames=c['generated_frames']) for c in plan['clips']]
    validate_scene_clip_frame_mappings(plan, SimpleNamespace(total_frames=frames), mappings)
    assert [p['output_frame'] for m in mappings for p in m['output_to_generated']] == list(range(frames))
    for mapping in mappings:
        assert [j for j, value in enumerate(mapping['generated_to_retained']) if value is not None] == mapping['retained_to_generated']


@pytest.mark.parametrize('actual', [True, 93.0, 92, 94, 0])
def test_generated_count_must_match_exact_budget(actual):
    from video_ai.planning.scene_clip_continuation import scene_clip_frame_mapping
    with pytest.raises(ValueError): scene_clip_frame_mapping(_plan(93)['clips'][0], actual_generated_frames=actual)


@pytest.mark.parametrize('field,value', [('native_fps', True), ('output_fps', 16.0),
    ('generated_frames', 94), ('retained_frames', 92), ('start_frame', 1), ('end_frame', 199),
    ('clip_id', 'shot_0001'), ('scene_id', 'scene_0002'), ('retained_to_generated', list(range(1,94))),
    ('generated_to_retained', [True]+list(range(1,93))), ('extra', 'forbidden')])
def test_global_validator_rebuilds_all_mapping_fields(field, value):
    from video_ai.planning.scene_clip_continuation import scene_clip_frame_mapping, validate_scene_clip_frame_mappings
    plan = _plan(93)
    mapping = scene_clip_frame_mapping(plan['clips'][0], actual_generated_frames=93)
    mapping[field] = value
    with pytest.raises(ValueError): validate_scene_clip_frame_mappings(plan, SimpleNamespace(total_frames=93), [mapping])


@pytest.mark.parametrize('field,value', [('start_frame', True), ('ordinal', 2), ('parent_clip_id', 'scene_0002_clip_0001'),
    ('retained_source_start', 1), ('retained_source_end', 92), ('trim_tail_frames', 1), ('extra', 1)])
def test_clip_budget_rejects_forged_native_retention(field, value):
    from video_ai.planning.scene_clip_continuation import scene_clip_frame_mapping
    clip = _plan(93)['clips'][0]; clip[field] = value
    with pytest.raises(ValueError): scene_clip_frame_mapping(clip, actual_generated_frames=93)


def request_fixture():
    from video_ai.planning.visual_consistency import derive_reference_graph
    profile = SimpleNamespace(name='fast', width=768, height=432, native_fps=16)
    frozen = SimpleNamespace(config=SimpleNamespace(media=SimpleNamespace(profile=profile, fps=16, transition='cut')))
    narration = [SimpleNamespace(unit_id=uid, text_start=a, text_end=a+len(text), text=text,
                      start_sample=start, end_sample=end) for uid,a,text,start,end in (
        ('unit_0001', 0, '原文第一句。', 1000, 8000),
        ('unit_0002', 7, '第二句完整文字。', 10000, 500000),
        ('unit_0003', 16, '末句不能截断。', 505000, 610001))]
    timeline = SimpleNamespace(total_frames=205, total_samples=613001, clips=narration)
    bible = dict(global_style={'style': '完整共享风格'},
        entities=[dict(entity_id='entity_0001', description='甲'), dict(entity_id='entity_0002', description='乙')],
        appearance_variants=[dict(variant_id='variant_0001', entity_id='entity_0001', description='白衣'),
                             dict(variant_id='variant_0002', entity_id='entity_0002', description='蓝衣')],
        scene_groups=[dict(group_id='group_0001', description='完整环境')])
    scenes = []
    for index, (start, end, ids, variants, members) in enumerate([
            (0, 1, ['entity_0001'], ['variant_0001'], ['unit_0001']),
            (1, 201, ['entity_0001', 'entity_0002'], ['variant_0001', 'variant_0002'], ['unit_0002']),
            (201, 205, ['entity_0002'], ['variant_0002'], ['unit_0003'])], 1):
        scene = dict(scene_id=f'scene_{index:04d}', start_frame=start, end_frame=end, entity_ids=ids,
            variant_ids=variants, scene_group_id='group_0001', unit_ids=members,
            motion_prompt=f'原样动作 {index}', bindings=[])
        for clip in narration:
            a, b = max(start*3000, clip.start_sample), min(end*3000, timeline.total_samples, clip.end_sample)
            if a < b: scene['bindings'].append(dict(unit_id=clip.unit_id, text_start=clip.text_start,
                text_end=clip.text_end, text=clip.text, semantic_member=clip.unit_id in members,
                start_sample=a, end_sample=b))
        scenes.append(scene)
    baselines, bindings, dependencies, batches = derive_reference_graph(scenes, bible)
    bible['baselines'] = baselines
    for scene, refs, deps in zip(scenes, bindings, dependencies): scene.update(reference_bindings=refs, dependencies=deps)
    plan = dict(scenes=scenes, total_frames=205, total_samples=613001, settings={'max_clip_seconds': 6}, batches=batches)
    plan['clips'] = production_visual_plan.plan_scene_clips(plan, max_clip_seconds=6)
    wan = dict(scenes=[dict(scene_id=s['scene_id'], candidate_id=f'candidate_{i:04d}',
        path=f'D:/VideoSi/run/original_{i}.png', bytes=300+i, sha256=str(i)*64)
        for i,s in enumerate(scenes, 1)])
    return frozen, bible, plan, timeline, wan


def test_shared_prompt_parameters_baselines_and_original_narration_with_nonzero_long_scene():
    from video_ai.planning.scene_clip_continuation import build_scene_wan_plan, scene_clip_frame_mapping, validate_scene_clip_frame_mappings
    frozen, bible, plan, timeline, wan = request_fixture()
    before = deepcopy((bible, plan, wan, vars(timeline)))
    result = build_scene_wan_plan(frozen, bible, plan, timeline, wan)
    assert len(result) == 5
    assert all(set(row) == {'budget', 'parameters', 'narration_bindings', 'comparison_images'} for row in result)
    assert [r['budget'] for r in result] == plan['clips']
    long = result[1:4]
    assert [(r['budget']['start_frame'],r['budget']['end_frame']) for r in long] == [(1,94),(94,186),(186,201)]
    assert len({r['parameters']['positive'] for r in long}) == 1
    context = json.loads(long[0]['parameters']['positive'].split('\nVISUAL_BIBLE_JSON\n')[1])
    assert context == {key: bible[key] for key in ('global_style','entities','appearance_variants','scene_groups')}
    tail_context = json.loads(result[-1]['parameters']['positive'].split('\nVISUAL_BIBLE_JSON\n')[1])
    assert tail_context['entities'] == [bible['entities'][1]]
    assert len(long[0]['comparison_images']) == 5
    assert [r['scene_id'] for r in long[0]['comparison_images']] == ['scene_0001','scene_0002','scene_0001','scene_0002','scene_0001']
    assert all(set(c) == {'kind','id','scene_id','candidate_id','image'} for r in result for c in r['comparison_images'])
    assert all(set(c['image']) == {'path','bytes','sha256'} for r in result for c in r['comparison_images'])
    assert [r['parameters']['seed_high'] for r in result] == list(range(264244520398999,264244520399004))
    assert [r['parameters']['length'] for r in long] == [93,93,17]
    p = long[0]['parameters']
    assert set(p) == set('positive negative seed_high seed_low width height length fps batch steps cfg sampler scheduler split_step shift_high shift_low lora_enabled'.split())
    assert (p['width'],p['height'],p['fps'],p['steps'],p['cfg'],p['lora_enabled']) == (768,432,16,40,3.5,False)
    for narration in timeline.clips:
        bindings = [b for row in result for b in row['narration_bindings'] if b['unit_id']==narration.unit_id]
        assert all(b['text'] == narration.text for b in bindings)
        assert bindings[0]['start_sample'] == narration.start_sample and bindings[-1]['end_sample'] == narration.end_sample
        assert all(a['end_sample'] == b['start_sample'] for a,b in zip(bindings,bindings[1:]))
    assert any(not b['semantic_member'] for row in result for b in row['narration_bindings'])
    mappings = [scene_clip_frame_mapping(c, actual_generated_frames=c['generated_frames']) for c in plan['clips']]
    validate_scene_clip_frame_mappings(plan, timeline, mappings)
    assert (bible, plan, wan, vars(timeline)) == before


@pytest.mark.parametrize('fault', ['budget', 'text', 'samples', 'omitted_baseline', 'image_order', 'profile', 'bool_frames'])
def test_request_plan_refuses_changed_budget_text_samples_baselines_or_profile(fault):
    from video_ai.planning.scene_clip_continuation import build_scene_wan_plan
    frozen, bible, plan, timeline, wan = request_fixture()
    if fault == 'budget': plan['clips'][2]['parent_clip_id'] = None
    elif fault == 'text': plan['scenes'][1]['bindings'][0]['text'] = '摘要'
    elif fault == 'samples': plan['scenes'][1]['bindings'][0]['start_sample'] += 1
    elif fault == 'omitted_baseline': bible['baselines'].pop()
    elif fault == 'image_order': wan['scenes'].reverse()
    elif fault == 'profile': frozen.config.media.profile.width = 720
    else: plan['clips'][0]['generated_frames'] = True
    with pytest.raises(ValueError): build_scene_wan_plan(frozen, bible, plan, timeline, wan)


def test_wan_stage_rejects_committed_over_six_second_clip_without_replanning():
    from video_ai.planning.scene_clip_continuation import build_scene_wan_plan
    frozen,bible,plan,timeline,wan=request_fixture()
    plan['settings']['max_clip_seconds']=7
    plan['clips']=production_visual_plan.plan_scene_clips(plan,max_clip_seconds=7)
    assert max(c['generated_frames'] for c in plan['clips'])==109
    before=deepcopy(plan)
    with pytest.raises(ValueError,match='six|6|96'):
        build_scene_wan_plan(frozen,bible,plan,timeline,wan)
    assert plan==before


def _whole_execution(plan, timeline):
    from video_ai.planning.scene_execution import build_scene_execution_budget
    timeline.as_dict = lambda: dict(total_frames=timeline.total_frames, total_samples=timeline.total_samples,
                                    clips=[dict(vars(c)) for c in timeline.clips])
    return build_scene_execution_budget(plan, timeline, run_id='run_123', mode='whole_scene_v1',
        rendering_identity_sha256='a'*64,
        admission=dict(path='D:/VideoSi/run/evidence.json', bytes=100, sha256='b'*64))


def _whole_request_fixture():
    from unit.test_whole_scene_contracts import whole_contract, rendering
    frozen, bible, plan, timeline, wan, contract, _ = whole_contract()
    frozen.config.raw['scene_rendering'] = rendering('whole_scene_v1')
    return frozen, bible, plan, timeline, wan, contract


def test_whole_requests_keep_original_first_semantic_clip_seed_and_complete_narration():
    from video_ai.planning.scene_clip_continuation import build_scene_wan_plan
    frozen, bible, plan, timeline, wan, contract = _whole_request_fixture()
    execution = _whole_execution(plan, timeline)
    before = deepcopy((bible, plan, wan, execution))
    result = build_scene_wan_plan(frozen, bible, plan, timeline, wan, execution=execution, prompt_contract=contract)
    assert len(result) == 3
    assert [r['budget']['retained_frames'] for r in result] == [1, 200, 4]
    assert [r['parameters']['length'] for r in result] == [1, 201, 5]
    assert [r['parameters']['seed_high'] for r in result] == [264244520398999, 264244520399000, 264244520399003]
    assert all(r['parameters']['seed_low'] == 0 for r in result)
    assert all(r['budget']['parent_clip_id'] is None for r in result)
    assert [r['narration_bindings'] for r in result] == [s['bindings'] for s in plan['scenes']]
    assert all('Continue from selected scene image pose' in r['parameters']['positive'] for r in result)
    assert all('原样动作' not in r['parameters']['positive'] and 'AUDIT_ONLY' not in r['parameters']['positive'] for r in result)
    assert (bible, plan, wan, execution) == before


@pytest.mark.parametrize('fault', ['quality', 'budget', 'timeline', 'semantic_clip', 'text'])
def test_whole_requests_reject_profile_budget_or_original_narration_drift(fault):
    from video_ai.planning.scene_clip_continuation import build_scene_wan_plan
    frozen, bible, plan, timeline, wan, contract = _whole_request_fixture()
    execution = _whole_execution(plan, timeline)
    if fault == 'quality':
        frozen.config.media.profile.name = 'quality'
        frozen.config.media.profile.width, frozen.config.media.profile.height = 1280, 720
    elif fault == 'budget': execution['clips'][1]['generated_frames'] += 4
    elif fault == 'timeline': timeline.total_samples += 1
    elif fault == 'semantic_clip': plan['clips'][2]['parent_clip_id'] = None
    else: plan['scenes'][1]['bindings'][0]['text'] = '摘要'
    with pytest.raises(ValueError):
        build_scene_wan_plan(frozen, bible, plan, timeline, wan, execution=execution, prompt_contract=contract)


def test_explicit_segmented_execution_preserves_original_requests_and_mappings():
    from video_ai.planning.scene_clip_continuation import build_scene_wan_plan, scene_clip_frame_mapping, validate_scene_clip_frame_mappings
    from video_ai.planning.scene_execution import build_scene_execution_budget
    from unit.test_scene_video_prompts import fixture
    frozen, bible, plan, timeline, wan, contract = fixture()
    _whole_execution(plan, timeline)
    execution = build_scene_execution_budget(plan, timeline, run_id='run_123', mode='segmented_v1',
        rendering_identity_sha256='a'*64, admission=None)
    original = build_scene_wan_plan(frozen, bible, plan, timeline, wan, prompt_contract=contract)
    frozen.config.raw['scene_rendering']['mode'] = 'segmented_v1'
    assert build_scene_wan_plan(frozen, bible, plan, timeline, wan, execution=execution, prompt_contract=contract) == original
    mappings = [scene_clip_frame_mapping(c, actual_generated_frames=c['generated_frames']) for c in plan['clips']]
    validate_scene_clip_frame_mappings(plan, timeline, mappings, execution=execution)


@pytest.mark.parametrize('fault', ['legacy_execution', 'old_visual_execution', 'mode_mismatch',
    'missing_execution_whole', 'missing_execution_segmented'])
def test_requests_refuse_missing_or_mixed_explicit_execution_modes(fault):
    from video_ai.planning.scene_clip_continuation import build_scene_wan_plan
    from unit.test_scene_video_prompts import fixture
    if fault in ('old_visual_execution', 'missing_execution_segmented'):
        frozen, bible, plan, timeline, wan, contract = fixture()
    else:
        frozen, bible, plan, timeline, wan, contract = _whole_request_fixture()
    execution = _whole_execution(plan, timeline)
    if fault == 'legacy_execution':
        frozen.config.raw = {}
        contract = None
    elif fault == 'mode_mismatch':
        frozen.config.raw['scene_rendering'].pop('whole_scene_evidence')
        frozen.config.raw['scene_rendering']['mode'] = 'segmented_v1'
    elif fault == 'missing_execution_whole': execution = None
    elif fault == 'missing_execution_segmented':
        frozen.config.raw['scene_rendering']['mode'] = 'segmented_v1'
        execution = None
    with pytest.raises(ValueError):
        build_scene_wan_plan(frozen, bible, plan, timeline, wan, prompt_contract=contract, execution=execution)
