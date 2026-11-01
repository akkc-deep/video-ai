"""Explicit modes and whole-scene text stay separate from historical contracts."""
from copy import deepcopy
from pathlib import Path

import pytest

from video_ai.planning.production_scenes import canonical_digest


def rendering(mode):
    value = dict(mode=mode, prompt_policy='visual_v2', prompt_contract='reviewed.json')
    if mode == 'whole_scene_v1':
        value['whole_scene_evidence'] = 'D:/VideoSi/cache/video-ai/logs/vco05-20261027-native321/final-assessment.json'
    return value


@pytest.mark.parametrize('mode', ['segmented_v1', 'whole_scene_v1'])
def test_explicit_rendering_exact_modes(mode):
    from video_ai.planning.scene_video_prompts import parse_scene_rendering
    value = rendering(mode)
    assert parse_scene_rendering(value) == value


@pytest.mark.parametrize('path', ['relative.json', 'C:/VideoSi/final-assessment.json',
    'D:/VideoSi/../outside.json', 'D:/VideoSi/x/*.json', '//host/share/final-assessment.json'])
def test_whole_evidence_requires_exact_local_runtime_path(path):
    from video_ai.planning.scene_video_prompts import parse_scene_rendering
    value = rendering('whole_scene_v1'); value['whole_scene_evidence'] = path
    with pytest.raises(ValueError): parse_scene_rendering(value)


@pytest.mark.parametrize('fault', ['unknown', 'null', 'extra', 'missing', 'segmented_evidence'])
def test_explicit_rendering_rejects_partial_or_mixed_configuration(fault):
    from video_ai.planning.scene_video_prompts import parse_scene_rendering
    value = rendering('whole_scene_v1')
    if fault == 'unknown': value['mode'] = 'whole_scene_v2'
    elif fault == 'null': value['mode'] = None
    elif fault == 'extra': value['extra'] = 1
    elif fault == 'missing': del value['whole_scene_evidence']
    else: value['mode'] = 'segmented_v1'
    with pytest.raises(ValueError): parse_scene_rendering(value)


@pytest.mark.parametrize('policy', [None, {}, {'schema_version': 1, 'policy': 'other'}])
def test_whole_configuration_requires_current_continuity_policy(policy):
    from video_ai.config import load_config
    from video_ai.runtime.manifest import thaw
    from unit.test_jimeng_config import image_settings
    base = load_config(Path(__file__).resolve().parents[2]/'config/production.example.json')
    raw = thaw(base.raw)
    raw.update(production_strategy='paragraph_jimeng_v1', image_generation=image_settings(),
               scene_rendering=rendering('whole_scene_v1'))
    if policy is not None: raw['scene_continuity'] = policy
    with pytest.raises(ValueError): load_config(base.config_file, raw=raw)


def test_valid_whole_config_and_quality_envelope_rejection():
    from video_ai.config import load_config
    from video_ai.runtime.manifest import thaw
    from unit.test_jimeng_config import image_settings
    base = load_config(Path(__file__).resolve().parents[2]/'config/production.example.json')
    raw = thaw(base.raw)
    raw.update(production_strategy='paragraph_jimeng_v1', image_generation=image_settings(),
        scene_rendering=rendering('whole_scene_v1'), scene_continuity=dict(schema_version=1, policy='advisory_v1'))
    raw['media']['profile'] = 'fast'
    assert load_config(base.config_file, raw=raw).raw['scene_rendering']['mode'] == 'whole_scene_v1'
    raw['media']['profile'] = 'quality'
    with pytest.raises(ValueError): load_config(base.config_file, raw=raw)


@pytest.mark.parametrize('media', [None, [], 'fast'])
def test_whole_malformed_media_has_configuration_error(media):
    from video_ai.config import load_config, ConfigError
    from video_ai.runtime.manifest import thaw
    from unit.test_jimeng_config import image_settings
    base=load_config(Path(__file__).resolve().parents[2]/'config/production.example.json')
    raw=thaw(base.raw)
    raw.update(production_strategy='paragraph_jimeng_v1',image_generation=image_settings(),
        scene_rendering=rendering('whole_scene_v1'),scene_continuity=dict(schema_version=1,policy='advisory_v1'),media=media)
    with pytest.raises(ConfigError): load_config(base.config_file,raw=raw)


@pytest.mark.parametrize('timeouts', [{'wan':7201},{'service_start':301}])
def test_whole_timeouts_cannot_expand_admitted_envelope(timeouts):
    from video_ai.config import load_config,ConfigError
    from video_ai.runtime.manifest import thaw
    from unit.test_jimeng_config import image_settings
    base=load_config(Path(__file__).resolve().parents[2]/'config/production.example.json')
    raw=thaw(base.raw)
    raw.update(production_strategy='paragraph_jimeng_v1',image_generation=image_settings(),
        scene_rendering=rendering('whole_scene_v1'),scene_continuity=dict(schema_version=1,policy='advisory_v1'),timeouts=timeouts)
    raw['media']['profile']='fast'
    with pytest.raises(ConfigError):load_config(base.config_file,raw=raw)


def whole_contract():
    from unit.test_scene_video_prompts import fixture, reviewed
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    f, b, p, t, w, c = fixture()
    clips = derive_scene_execution_clips(p, t, mode='whole_scene_v1')
    c['schema_version'] = 2
    c['binding'].update(rendering_mode='whole_scene_v1', execution_clips_sha256=canonical_digest(clips))
    c['clips'] = [dict(clip_id=clip['clip_id'], motion='Continue from selected scene image pose',
        camera='Smooth continuous tracking', lighting='Maintain current lighting', changes=[]) for clip in clips]
    return f, b, p, t, w, reviewed(c), clips


def test_whole_prompt_binds_pure_execution_without_future_budget_sha():
    from video_ai.planning.scene_video_prompts import validate_scene_video_prompt_contract
    f, b, p, t, w, c, clips = whole_contract()
    before = deepcopy((p, c))
    assert validate_scene_video_prompt_contract(c, bible=b, plan=p, wan_inputs=w, script=f.script) == c
    assert len(c['clips']) == len(p['scenes']) < len(p['clips'])
    assert (p, c) == before


@pytest.mark.parametrize('fault', ['digest', 'order', 'missing', 'schema1', 'mode', 'future_sha'])
def test_whole_prompt_rejects_foreign_or_partial_budget(fault):
    from video_ai.planning.scene_video_prompts import validate_scene_video_prompt_contract
    from unit.test_scene_video_prompts import reviewed
    f, b, p, t, w, c, clips = whole_contract()
    if fault == 'digest': c['binding']['execution_clips_sha256'] = 'f'*64
    elif fault == 'order': c['clips'].reverse()
    elif fault == 'missing': c['clips'].pop()
    elif fault == 'schema1': c['schema_version'] = 1
    elif fault == 'mode': c['binding']['rendering_mode'] = 'segmented_v1'
    else: c['binding']['execution_budget_sha256'] = 'e'*64
    reviewed(c)
    with pytest.raises(ValueError):
        validate_scene_video_prompt_contract(c, bible=b, plan=p, wan_inputs=w, script=f.script)


@pytest.mark.parametrize('mode', ['segmented_v1', 'whole_scene_v1'])
def test_explicit_identity_is_schema3_and_does_not_change_common_planning(mode):
    from video_ai.planning.scene_revision import identity_from_options, validate_rendering_identity
    from unit.test_scene_revision import revision_fixture
    options = revision_fixture()[0]['source_options']
    before = identity_from_options(options)
    options['config_snapshot']['raw']['scene_rendering'] = rendering(mode)
    options['config_snapshot']['raw']['scene_continuity'] = dict(schema_version=1, policy='advisory_v1')
    inputs = options['execution_policy']['input_identities']
    inputs['scene_video_prompts'] = dict(sha256='1'*64)
    if mode == 'whole_scene_v1': inputs['whole_scene_evidence'] = dict(sha256='2'*64)
    identity = identity_from_options(options)
    validate_rendering_identity(identity)
    assert identity['schema_version'] == 3
    assert identity['rendering'] == dict(mode=mode, prompt_policy='visual_v2',
        prompt_contract_sha256='1'*64, whole_scene_evidence_sha256='2'*64 if mode == 'whole_scene_v1' else None,
        execution_algorithm='scene_execution_v1')
    assert identity['planning_sha256'] == before['planning_sha256']


def whole_snapshot():
    from types import SimpleNamespace
    from video_ai.planning.scene_execution import derive_scene_execution_clips
    from video_ai.planning.scene_revision import identity_from_options
    from unit.test_scene_revision import revision_fixture
    snapshot, request, _ = revision_fixture('reconfigure')
    options = snapshot['source_options']
    options['config_snapshot']['raw']['scene_rendering'] = rendering('whole_scene_v1')
    options['execution_policy']['input_identities'].update(
        scene_video_prompts=dict(sha256='1'*64), whole_scene_evidence=dict(sha256='2'*64))
    identity = identity_from_options(options)
    clips = derive_scene_execution_clips(snapshot['scene_plan'], SimpleNamespace(total_frames=52), mode='whole_scene_v1')
    snapshot['scene_execution'] = dict(schema_version=1, algorithm='scene_execution_v1',
        production_strategy='paragraph_jimeng_v1', run_id=options['run_id'], mode='whole_scene_v1',
        scene_plan_sha256=canonical_digest(snapshot['scene_plan']), timeline_sha256='9'*64,
        rendering_identity_sha256=canonical_digest(identity),
        admission=dict(path='D:/VideoSi/frozen/whole-scene-evidence.json', bytes=20, sha256='2'*64), clips=clips)
    snapshot['clip_nodes'] = [dict(clip_id=c['clip_id'], record={'clip_id': c['clip_id']},
        acceptance={'verdict': 'passed'}, status='accepted') for c in clips]
    snapshot['upscale_nodes'] = [dict(frame_id=c['clip_id']+f':frame_{i+1:06d}', record={}, status='ready')
        for c in clips for i in range(c['retained_frames'])]
    request.update(scene_ids=[], clip_ids=[], choices=[], config_path='D:/VideoSi/new/config.json')
    target = deepcopy(identity)
    target['config_sha256'] = 'f'*64
    target['rendering'].update(mode='segmented_v1', whole_scene_evidence_sha256=None)
    return snapshot, request, target


def test_mode_change_invalidates_source_whole_nodes_with_same_clip_names():
    from video_ai.planning.scene_revision import plan_scene_revision
    snapshot, request, target = whole_snapshot()
    result = plan_scene_revision(snapshot, request, target)
    ids = [c['clip_id'] for c in snapshot['scene_execution']['clips']]
    assert result['dirty']['clips'] == result['dirty']['clip_reviews'] == ids
    assert len(result['dirty']['upscale']) == 52
    assert result['dirty']['images'] == result['dirty']['choices'] == []
    assert result['reusable']['common'] == result['reusable']['plan'] == ['all']


@pytest.mark.parametrize('fault', ['missing', 'budget', 'mode', 'plan_sha', 'identity_sha'])
def test_revision_cannot_substitute_semantic_or_target_budget_for_source(fault):
    from video_ai.planning.scene_revision import plan_scene_revision
    snapshot, request, target = whole_snapshot()
    if fault == 'missing': del snapshot['scene_execution']
    elif fault == 'budget': snapshot['scene_execution']['clips'] = snapshot['scene_plan']['clips']
    elif fault == 'mode': snapshot['scene_execution']['mode'] = 'segmented_v1'
    elif fault == 'plan_sha': snapshot['scene_execution']['scene_plan_sha256'] = '3'*64
    else: snapshot['scene_execution']['rendering_identity_sha256'] = '4'*64
    with pytest.raises(ValueError): plan_scene_revision(snapshot, request, target)


def test_schema3_media_index_keeps_all_native_whole_frames_once():
    from video_ai.planning.scene_media import plan_scene_upscale
    from video_ai.planning.scene_clip_continuation import scene_clip_frame_mapping
    snapshot, _, _ = whole_snapshot()
    budgets = snapshot['scene_execution']['clips']
    value = dict(schema_version=3, total_frames=52,
        execution_budget=dict(path='D:/VideoSi/run/execution-budget.json', bytes=100, sha256='a'*64),
        clips=[dict(clip_id=c['clip_id'], scene_id=c['scene_id'], budget=c,
            frame_mapping=scene_clip_frame_mapping(c, actual_generated_frames=c['generated_frames']),
            source=dict(path='D:/VideoSi/run/'+c['clip_id']+'.mp4', bytes=40, sha256='b'*64)) for c in budgets])
    rows = plan_scene_upscale(value)
    assert len(rows) == 52
    assert [r['output_frame_index'] for r in rows] == list(range(52))
    assert all(r['generated_frame_index'] == r['retained_frame_index'] for r in rows)
    value['schema_version'] = 2
    with pytest.raises(ValueError): plan_scene_upscale(value)
