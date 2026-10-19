"""Observation admission uses actual identities and explicit complete playback."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace

import pytest

from video_ai.planning.production_scenes import canonical_digest
from video_ai.runtime.production_state import ProductionRefused
from video_ai.runtime.scene_clip_observations import (
    build_observation_template, validate_scene_clip_observation,
)


CHECKS = ('subject_identity appearance_structure color_clothing environment_space '
          'time_lighting style motion_process end_frame_stability input_alignment parent_join').split()
NOW = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)


@pytest.fixture
def observation_context(runtime_run):
    run, _, _ = runtime_run
    folder = run/'production/scene-clips'
    folder.mkdir(parents=True)
    inputs = dict(visual_bible_sha256='a'*64)
    (folder/'inputs.json').write_text(json.dumps(inputs), encoding='utf-8')
    def artifact(name):
        path = folder/name
        raw = ('authentic test bytes '+name).encode()
        path.write_bytes(raw)
        return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    selected = dict(scene_id='scene_0001', candidate_id='candidate_0001', **artifact('original.png'))
    request = dict(inputs_sha256=canonical_digest(inputs), scene_id='scene_0001', clip_id='scene_0001_clip_0001',
        selected_image=selected, comparison_images=[dict(kind='scene_group', id='group_0001',
        scene_id='scene_0001', candidate_id='candidate_0001', image=artifact('baseline.png'))], parent=None)
    clip = dict(schema_version=2, production_strategy='paragraph_jimeng_v1', run_id=run.name,
        scene_id=request['scene_id'], clip_id=request['clip_id'], request_sha256=canonical_digest(request),
        generated=artifact('generated.mp4'), source=artifact('source.mp4'), created_at='2026-10-19T10:00:00+00:00')
    mapping = dict(retained_frames=93)
    last_frame = dict(image=artifact('frame_000093.png'))
    frozen = SimpleNamespace(options=dict(script_path=str(run/'inputs/script.txt'), run_id=run.name))
    return frozen, clip, request, mapping, last_frame


def authored(template):
    value = deepcopy(template)
    value.update(review_method='human_video', reviewer='fixture playback reviewer',
        viewed_at='2026-10-19T11:00:00+00:00', start_observation='Start compared to selected original and baselines.',
        process_observation='Continuous middle playback inspected.', end_observation='End compared to exact native PNG.',
        quality_observation='Full source inspected for temporal and image quality.',
        continuity_observation='Original to motion and end compared against fixed baselines.', reason='Full range inspected.')
    value['checks'] = {key: ('passed' if status is not None else None) for key, status in value['checks'].items()}
    value['verdict'] = 'passed'
    return value


def expected_context(context, parent=None):
    template = build_observation_template(*context, parent)
    return dict(template=template, created_at=context[1]['created_at'])


def test_template_never_invents_review_and_binds_exact_media(observation_context):
    frozen, clip, request, _, last_frame = observation_context
    before = deepcopy((clip, request, last_frame))
    template = expected_context(observation_context)['template']
    assert template['clip_sha256'] == canonical_digest(clip)
    assert template['last_frame'] == last_frame['image']
    assert template['visual_bible_sha256'] == 'a'*64
    assert template['playback'] == dict(clip_source_frames=[0, 93], parent_source_frames=None)
    assert template['checks'] == {key: (None if key == 'parent_join' else 'unverified') for key in CHECKS}
    assert all(template[key] is None for key in ('review_method', 'reviewer', 'viewed_at'))
    assert all(template[key] == '' for key in ('start_observation', 'process_observation', 'end_observation',
        'quality_observation', 'continuity_observation', 'reason'))
    assert template['verdict'] == 'unverified' and template['issues'] == []
    assert (clip, request, last_frame) == before


def test_full_authored_leaf_observation_is_accepted_without_mutation(observation_context):
    expected = expected_context(observation_context)
    value = authored(expected['template'])
    assert validate_scene_clip_observation(value, expected, now=NOW) == value
    with pytest.raises(ProductionRefused):
        validate_scene_clip_observation(expected['template'], expected, now=NOW)


@pytest.mark.parametrize('path,replacement', [
    (('schema_version',), True), (('scope',), 'old_shot_pair'), (('clip_sha256',), 'b'*64),
    (('generated', 'sha256'), 'b'*64), (('selected_image', 'path'), 'other.png'),
    (('playback', 'clip_source_frames'), [0, 92]), (('playback', 'clip_source_frames'), [[0, 1], [92, 93]]),
    (('playback', 'clip_source_frames'), [False, 93]), (('playback', 'parent_source_frames'), [0, 93]),
    (('review_method',), 'screenshots'), (('reviewer',), '  '),
    (('viewed_at',), '2026-10-19T09:59:59+00:00'), (('viewed_at',), '2026-10-19T12:00:01+00:00'),
    (('viewed_at',), '2026-10-19T11:00:00'), (('process_observation',), ''), (('reason',), ' '),
    (('checks', 'parent_join'), 'passed'), (('checks', 'subject_identity'), 'unverified'),
    (('checks', 'motion_process'), 'failed'), (('checks', 'style'), True), (('verdict',), 'accepted'),
    (('issues',), [dict(check='style', frames=[0, 1], description='flicker')]),
])
def test_rejects_identity_playback_review_and_verdict_forgery(observation_context, path, replacement):
    expected = expected_context(observation_context)
    value = authored(expected['template'])
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    with pytest.raises(ProductionRefused):
        validate_scene_clip_observation(value, expected, now=NOW)


@pytest.mark.parametrize('change', ['extra', 'missing', 'extra_check', 'extra_playback'])
def test_rejects_nonexact_fields(observation_context, change):
    expected = expected_context(observation_context)
    value = authored(expected['template'])
    if change == 'extra': value['screenshots'] = []
    if change == 'missing': del value['quality_observation']
    if change == 'extra_check': value['checks']['entity_id'] = 'passed'
    if change == 'extra_playback': value['playback']['screenshots'] = []
    with pytest.raises(ProductionRefused):
        validate_scene_clip_observation(value, expected, now=NOW)


@pytest.mark.parametrize('verdict,status', [('failed', 'failed'), ('unverified', 'unverified')])
def test_retains_explicit_failed_and_unverified_reviews(observation_context, verdict, status):
    expected = expected_context(observation_context)
    value = authored(expected['template'])
    value['checks']['motion_process'] = status
    value['verdict'] = verdict
    value['issues'] = [dict(check='motion_process', frames=[4, 90], description='Middle motion needs review.')]
    assert validate_scene_clip_observation(value, expected, now=NOW) == value


@pytest.mark.parametrize('issue', [
    dict(check='parent_join', frames=[0, 1], description='not applicable'),
    dict(check='style', frames=[0, 94], description='outside'),
    dict(check='style', frames=[1, 1], description='empty'),
    dict(check='style', frames=[True, 2], description='bool'),
    dict(check='style', frames=[0, 1], description=' '),
    dict(check='style', frames=[0, 1], description='bad', extra=True),
])
def test_rejects_invalid_issue_ranges_or_checks(observation_context, issue):
    expected = expected_context(observation_context)
    value = authored(expected['template'])
    value['checks']['style'] = 'failed'
    value.update(verdict='failed', issues=[issue])
    with pytest.raises(ProductionRefused):
        validate_scene_clip_observation(value, expected, now=NOW)


def test_child_requires_exact_parent_playback_and_join(observation_context):
    from pathlib import Path
    frozen, clip, request, mapping, last_frame = deepcopy(observation_context)
    parent = dict(clip=deepcopy(clip), mapping=dict(retained_frames=93), last_frame=deepcopy(last_frame), accepted={})
    parent_path = Path(clip['source']['path']).with_name('parent-source.mp4')
    parent_raw = b'authentic independent parent source'
    parent_path.write_bytes(parent_raw)
    parent['clip']['source'] = dict(path=str(parent_path), bytes=len(parent_raw), sha256=hashlib.sha256(parent_raw).hexdigest())
    request['parent'] = dict(clip_id=clip['clip_id'], clip_sha256=canonical_digest(parent['clip']),
        generated=parent['clip']['generated'], source=parent['clip']['source'], last_frame_sha256=canonical_digest(last_frame),
        last_frame=last_frame['image'], observation_acceptance_sha256=canonical_digest(parent['accepted']))
    request['clip_id'] = clip['clip_id'] = 'scene_0001_clip_0002'
    clip['request_sha256'] = canonical_digest(request)
    mapping['retained_frames'] = 15
    expected = expected_context((frozen, clip, request, mapping, last_frame), parent)
    assert expected['template']['playback'] == dict(clip_source_frames=[0, 15], parent_source_frames=[0, 93])
    value = authored(expected['template'])
    assert validate_scene_clip_observation(value, expected, now=NOW) == value
    parent_source = parent['clip']['source']
    old_source = Path(parent_source['path']).read_bytes()
    Path(parent_source['path']).write_bytes(b'changed parent source')
    with pytest.raises(ProductionRefused):
        validate_scene_clip_observation(value, expected, now=NOW)
    Path(parent_source['path']).write_bytes(old_source)
    value['checks']['parent_join'] = None
    with pytest.raises(ProductionRefused): validate_scene_clip_observation(value, expected, now=NOW)
    request['parent']['clip_sha256'] = 'b'*64
    clip['request_sha256'] = canonical_digest(request)
    with pytest.raises(ProductionRefused):
        expected_context((frozen, clip, request, mapping, last_frame), parent)


def test_template_refuses_changed_inputs_digest(observation_context):
    context = deepcopy(observation_context)
    context[2]['inputs_sha256'] = 'b'*64
    with pytest.raises(ProductionRefused): build_observation_template(*context, None)


@pytest.mark.parametrize('field', ['generated', 'source', 'last_frame', 'selected_image', 'comparison_images'])
def test_admission_rehashes_each_bound_media_even_same_size(observation_context, field):
    from pathlib import Path
    expected = expected_context(observation_context)
    value = authored(expected['template'])
    artifact = value[field]
    if field == 'comparison_images': artifact = artifact[0]['image']
    path = Path(artifact['path'])
    raw = path.read_bytes()
    path.write_bytes(bytes([raw[0] ^ 1])+raw[1:])
    with pytest.raises(ProductionRefused):
        validate_scene_clip_observation(value, expected, now=NOW)


@pytest.mark.parametrize('verdict,status,issues', [
    ('failed', 'failed', []), ('failed', 'passed', [dict(check='style', frames=[0, 1], description='flicker')]),
    ('unverified', 'passed', []), ('unverified', 'failed', [dict(check='style', frames=[0, 1], description='flicker')]),
])
def test_verdict_cannot_hide_failure_or_invent_uncertainty(observation_context, verdict, status, issues):
    expected = expected_context(observation_context)
    value = authored(expected['template'])
    value['checks']['style'] = status
    value.update(verdict=verdict, issues=issues)
    with pytest.raises(ProductionRefused):
        validate_scene_clip_observation(value, expected, now=NOW)
