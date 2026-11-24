import hashlib
import json
from uuid import uuid4

import pytest


@pytest.fixture
def tmp_path(isolated_test_runtime):
    path = isolated_test_runtime/'work'/('20261122-030000-'+uuid4().hex[:12])
    path.mkdir(parents=True)
    return path


def authorized_run(tmp_path):
    folder = tmp_path/'production'
    folder.mkdir()
    options = folder/'options.json'
    options.write_text('{"saved":true}', encoding='utf-8')
    value = dict(schema_version=1, run_id=tmp_path.name,
        options_sha256=hashlib.sha256(options.read_bytes()).hexdigest(),
        authorized_by='user', user_request='那不用审核了，继续合成视频吧',
        authorized_at='2026-11-22T03:00:00+00:00',
        scopes=['clip_playback', 'final_playback'])
    path = folder/'review-waiver.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    return path, value


def clip_record():
    return dict(clip=dict(clip_id='scene_0001_clip_0001'), request=dict(request_id='original'),
                accepted=None, rejected=None)


def test_waiver_is_opt_in_and_does_not_fabricate_viewing(tmp_path):
    from video_ai.runtime.scene_review_waiver import apply_clip_waiver
    record = clip_record()
    assert apply_clip_waiver(tmp_path, record) == record
    path, _ = authorized_run(tmp_path)
    result = apply_clip_waiver(tmp_path, record)
    assert result['accepted']['admission'] == 'user_review_waiver'
    assert result['accepted']['visual_review'] == 'unverified'
    assert result['accepted']['authorization']['path'] == str(path)
    assert 'verdict' not in result['accepted'] and 'observation' not in result['accepted']
    assert record['accepted'] is None
    assert not list((tmp_path/'production').glob('scene-clips/**/observation-accepted.json'))


@pytest.mark.parametrize('status', ['accepted', 'rejected'])
def test_actual_review_results_are_preserved(tmp_path, status):
    from video_ai.runtime.scene_review_waiver import apply_clip_waiver
    authorized_run(tmp_path)
    record = clip_record()
    record[status] = dict(actual_review=True)
    assert apply_clip_waiver(tmp_path, record) == record


@pytest.mark.parametrize('field,value', [('run_id', 'another-run'), ('options_sha256', '0'*64),
    ('authorized_by', 'agent'), ('scopes', ['final_playback'])])
def test_invalid_or_insufficient_authorization_does_not_release_clips(tmp_path, field, value):
    from video_ai.runtime.scene_review_waiver import apply_clip_waiver
    path, authorization = authorized_run(tmp_path)
    authorization[field] = value
    path.write_text(json.dumps(authorization), encoding='utf-8')
    with pytest.raises(ValueError):
        apply_clip_waiver(tmp_path, clip_record())


def test_absent_clip_still_requires_generation(tmp_path):
    from video_ai.runtime.scene_review_waiver import apply_clip_waiver
    authorized_run(tmp_path)
    assert apply_clip_waiver(tmp_path, None) is None


def test_final_waiver_binds_candidate_without_claiming_audiovisual_review(tmp_path):
    from video_ai.runtime.scene_review_waiver import final_waiver_acceptance
    candidate = dict(candidate=dict(path='final.mp4', bytes=100, sha256='0'*64))
    assert final_waiver_acceptance(tmp_path, candidate) is None
    authorized_run(tmp_path)
    result = final_waiver_acceptance(tmp_path, candidate)
    assert result['admission'] == 'user_review_waiver'
    assert result['visual_review'] == result['audio_review'] == 'unverified'
    assert result['scope'] == 'final_playback'
    assert 'verdict' not in result and 'full_film_watched' not in result


def test_delivery_waiver_preserves_truthful_quality_status(tmp_path):
    from types import SimpleNamespace
    from video_ai.runtime.scene_delivery_files import _expected_receipt
    context = dict(store=SimpleNamespace(run_dir=tmp_path), timeline=SimpleNamespace(total_frames=32),
                   scene_clips={}, image_acceptance={})
    tx = dict(transaction_id='1'*32, receipt=None, operations=dict(
        movie=dict(output={}), subtitle=dict(output={})))
    candidate = dict(technical_checks=dict(frame_count=True))
    ordinary = _expected_receipt(context, candidate, dict(actual_observation=True), tx)
    assert ordinary['actual_final_video_consistency'] == 'passed'
    waived = _expected_receipt(context, candidate, dict(admission='user_review_waiver'), tx)
    assert waived['actual_final_video_consistency'] == 'unverified_user_waived'
    assert waived['full_narration'] == waived['subtitles'] == 'unverified_user_waived'


def test_trusted_waived_revision_captures_current_node_without_recursive_history(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from video_ai.runtime.scene_review_waiver import capture_waived_origin
    from video_ai.runtime.resume_materials import trust_existing_materials
    from video_ai.runtime import _scene_revision_origins as origins
    authorized_run(tmp_path)
    frozen = SimpleNamespace(options=dict(script_path=str(tmp_path/'production/script.txt')),
                             config=SimpleNamespace(raw={}))
    original = dict(scene_id='scene_0001', candidates=[])
    monkeypatch.setattr(origins, 'require_origin_node', lambda *args: original)
    monkeypatch.setattr(origins, 'media_for_node', lambda *args: [])
    assert capture_waived_origin(frozen, 'image', 'scene_0001') is None
    with trust_existing_materials(tmp_path):
        captured = capture_waived_origin(frozen, 'image', 'scene_0001')
        assert captured['value'] == original
        assert captured['snapshot']['inventories'] == []
        assert {row['path'] for row in captured['snapshot']['files']} == {
            str(tmp_path/'production/options.json'), str(tmp_path/'production/review-waiver.json')}
        (tmp_path/'production/review-waiver.json').write_text('{}', encoding='utf-8')
        with pytest.raises(ValueError):
            captured['guard'].verify_captured_bytes()


def test_resume_of_waived_candidate_is_ready_for_delivery(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from video_ai.runtime import production_scene_pipeline as pipeline
    from video_ai.runtime import scene_completed
    authorized_run(tmp_path)
    composition = tmp_path/'production/scene-composition'
    composition.mkdir()
    for name in ('final-observation-template.json', 'candidate.mp4'):
        (composition/name).write_bytes(b'existing artifact')
    upscale = tmp_path/'production/scene-upscale'
    upscale.mkdir()
    (upscale/'complete.json').write_bytes(b'existing artifact')
    frozen = SimpleNamespace(options=dict(script_path=str(tmp_path/'production/script.txt')))
    progress = dict(composition=dict(status='ready'), upscale=dict(record=str(upscale/'complete.json')),
                    final_review=dict(status='waived', error=None))
    monkeypatch.setattr(scene_completed, 'validate_scene_completed_prefix', lambda *args: progress)
    monkeypatch.setattr(scene_completed, 'load_validated_prefix_details', lambda *args:
        dict(candidate=dict(candidate=dict(path=str(composition/'candidate.mp4')))))
    monkeypatch.setattr(pipeline, '_continuity_wait', lambda *args: None)
    assert pipeline._preflight_later(frozen, {}, None).status == 'final_review_ready'


def test_waived_clip_import_reuses_saved_record_without_rebuilding_scene_context(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from video_ai.runtime.scene_review_waiver import capture_waived_origin
    from video_ai.runtime.resume_materials import trust_existing_materials
    from video_ai.runtime import resume_materials
    from video_ai.runtime import _scene_revision_origins as origins
    authorized_run(tmp_path)
    artifacts = []
    for name in ('generated.mp4', 'source.mp4', 'last.png'):
        path = tmp_path/name
        path.write_bytes(b'completed media')
        artifacts.append(dict(path=str(path), bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    clip = dict(clip_id='scene_0001_clip_0001', generated=artifacts[0], source=artifacts[1])
    record = dict(clip=clip, accepted=dict(admission='user_review_waiver'), rejected=None,
                  last_frame=dict(image=artifacts[2]))
    monkeypatch.setattr(resume_materials, 'saved_clip', lambda *args: record)
    monkeypatch.setattr(origins, 'require_origin_node', lambda *args: pytest.fail('rebuilt scene context'))
    frozen = SimpleNamespace(options=dict(script_path=str(tmp_path/'production/script.txt')),
                             config=SimpleNamespace(raw={}))
    with trust_existing_materials(tmp_path):
        captured = capture_waived_origin(frozen, 'clip', clip['clip_id'])
        assert captured['value'] == clip
        assert [artifact for _, artifact in captured['media']] == artifacts


def test_saved_waiver_binding_is_compatible_with_revision_artifact_batch(tmp_path):
    from video_ai.runtime.resume_materials import trust_existing_materials, remember
    from video_ai.runtime.scene_revision_records import revision_artifact_batch, verify_artifact
    path, _ = authorized_run(tmp_path)
    artifact = dict(path=str(path), bytes=path.stat().st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    with trust_existing_materials(tmp_path):
        remember(artifact)
        with revision_artifact_batch():
            assert verify_artifact(artifact, root=tmp_path) == path


def test_waived_trusted_media_keeps_ownership_without_reauditing_sources_per_write(tmp_path):
    from types import SimpleNamespace
    from video_ai.runtime.resume_materials import trust_existing_materials
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_state import RunLock
    authorized_run(tmp_path)
    frozen = SimpleNamespace(options={}, config=SimpleNamespace(raw={}))
    with trust_existing_materials(tmp_path):
        with RunLock(tmp_path) as lock:
            store = SceneMediaStore(frozen, tmp_path, lock=lock)
            assert not store.recheck_inputs
            store.verify_captured_bytes = lambda: pytest.fail('repeated complete source audit')
            store.verify_global()
            store.assert_write()
        with pytest.raises(ValueError):
            store.verify_global()


def test_media_can_consume_declared_saved_origin_evidence_without_rebasing_history(tmp_path):
    from types import SimpleNamespace
    from video_ai.runtime.resume_materials import trust_existing_materials, remember
    from video_ai.runtime.scene_media_records import SceneMediaStore
    authorized_run(tmp_path)
    origin = tmp_path.parent/('20261121-030000-'+uuid4().hex[:12])
    origin.mkdir()
    path = origin/'original-command.json'
    path.write_bytes(b'original evidence')
    artifact = dict(path=str(path), bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    frozen = SimpleNamespace(options={}, config=SimpleNamespace(raw={}))
    with trust_existing_materials(tmp_path):
        remember(artifact)
        store = SceneMediaStore(frozen, tmp_path)
        assert store.artifact(path) == artifact
        assert store.validate_artifact(artifact) == path
        with pytest.raises(ValueError):
            store.validate_artifact(dict(artifact, sha256='0'*64))
        unknown = origin/'not-declared.json'
        unknown.write_bytes(b'not admitted')
        with pytest.raises(ValueError):
            store.artifact(unknown)


def completed_upscale_context(run):
    from types import SimpleNamespace
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime._scene_upscale_records import complete_value, mapping
    frozen = SimpleNamespace(options={}, config=SimpleNamespace(raw={}))
    cid = 'scene_0001_clip_0001'
    store = SceneMediaStore(frozen, run, clip_ids=(cid,))
    store.root.mkdir(parents=True, exist_ok=True)
    rows, frames = [], []
    for index in range(2):
        row = dict(frame_id=cid+f':frame_{index+1:06d}', clip_id=cid,
                   retained_frame_index=index, output_frame_index=index, source={})
        path = store.frame_dir(row['frame_id'])/'output.png'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'already checked output; do not decode again')
        rows.append(row)
        frames.append(dict(frame_id=row['frame_id'], mapping=mapping(row),
            output=dict(path=str(path), bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())))
    context = dict(store=store, rows=rows, inputs=dict(frozen_inputs='original'),
                   scene_clips=dict(clips=[dict(clip_id=cid)]), timeline=SimpleNamespace(as_dict=lambda:dict(total_frames=2)))
    value = complete_value(context, frames)
    (store.root/'inputs.json').write_text(json.dumps(context['inputs']), encoding='utf-8')
    (store.root/'complete.json').write_text(json.dumps(value), encoding='utf-8')
    return context, value


def test_completed_waived_upscale_does_not_replay_http_or_decode_images(tmp_path, monkeypatch):
    from video_ai.runtime.resume_materials import trust_existing_materials
    from video_ai.runtime import _scene_upscale_records as records
    from video_ai.runtime.scene_review_waiver import trusted_upscale_complete
    authorized_run(tmp_path)
    context, value = completed_upscale_context(tmp_path)
    monkeypatch.setattr(records, 'validate_upscale_frames', lambda *a, **kw: pytest.fail('replayed completed frame requests'))
    assert trusted_upscale_complete(context) is None
    with trust_existing_materials(tmp_path):
        context['store']._trusted_waived_inputs = True
        assert records.require_upscale_record(context) == value


@pytest.mark.parametrize('damage', ['header', 'mapping', 'missing_output'])
def test_completed_upscale_still_requires_current_mapping_and_outputs(tmp_path, damage):
    from video_ai.runtime.resume_materials import trust_existing_materials
    from video_ai.runtime.scene_review_waiver import trusted_upscale_complete
    authorized_run(tmp_path)
    context, value = completed_upscale_context(tmp_path)
    if damage == 'header': value['inputs_sha256'] = '0'*64
    elif damage == 'mapping': value['frames'][0]['mapping']['output_frame_index'] = 1
    else: __import__('pathlib').Path(value['frames'][0]['output']['path']).unlink()
    (context['store'].root/'complete.json').write_text(json.dumps(value), encoding='utf-8')
    with trust_existing_materials(tmp_path), pytest.raises((ValueError, FileNotFoundError)):
        context['store']._trusted_waived_inputs = True
        trusted_upscale_complete(context)


def test_trusted_waived_snapshot_uses_committed_readers_instead_of_raw_history_walk(tmp_path):
    from types import SimpleNamespace
    from video_ai.runtime.resume_materials import trust_existing_materials
    from video_ai.runtime.scene_media_records import SceneMediaStore
    authorized_run(tmp_path)
    frozen = SimpleNamespace(options={}, config=SimpleNamespace(raw={}))
    with trust_existing_materials(tmp_path):
        store = SceneMediaStore(frozen, tmp_path)
        snapshot = store.snapshot_json(files=('old-request-history.json',), directories=('old-http-history',))
        assert snapshot == dict(directories={}, artifacts={}, bodies={}, capture_paths=frozenset())
