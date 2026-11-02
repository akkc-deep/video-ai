"""Admission overlays must guard existing public paths without redoing media work."""
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_continuity_review_is_run_only_and_rejects_conflicting_actions(monkeypatch):
    import video_ai.production as production
    monkeypatch.setattr(production, 'create_run', lambda *a, **k: pytest.fail('allocated a run'))
    monkeypatch.setattr(production, 'RunLock', lambda *a, **k: pytest.fail('locked a run'))
    for kwargs in ({'text': '原文。'}, {'text': '原文。', 'clip_observation': 'clip.json'}):
        result = production.make_video(continuity_review='review.json', **kwargs)
        assert result.status == 'blocked' and result.run_dir is None


def test_cli_forwards_continuity_review_without_advancing(monkeypatch):
    import video_ai.production as production
    from video_ai.cli import main
    captured = []
    def consume(*args, **kwargs):
        captured.append(kwargs)
        return SimpleNamespace(status='awaiting_continuity_review', run_dir=None,
                               error=None, exit_code=3, to_dict=lambda: {})
    monkeypatch.setattr(production, 'make_video', consume)
    assert main(['make-video', '--run-dir', 'D:/VideoSi/projects/video-ai/runs/example',
                 '--continuity-review', 'review.json']) == 3
    assert captured[0]['continuity_review'] == 'review.json'


@pytest.mark.parametrize('other', ['--clip-observation', '--image-selection', '--final-observation', '--retry-email', '--revision', '--publish'])
def test_cli_continuity_review_is_mutually_exclusive(monkeypatch, other):
    import video_ai.production as production
    from video_ai.cli import main
    monkeypatch.setattr(production, 'make_video', lambda *a, **k: pytest.fail('conflicting action dispatched'))
    suffix = [other] if other == '--publish' else [other, 'another.json']
    assert main(['make-video', '--run-dir', 'D:/VideoSi/projects/video-ai/runs/example',
                 '--continuity-review', 'review.json', *suffix]) == 2


def test_public_source_acceptance_adds_current_overlay_after_base(monkeypatch):
    from video_ai.runtime import scene_clip_records as clips
    from video_ai.runtime import scene_continuity_records as continuity
    calls = []
    original = {'schema_version': 2, 'clips': []}
    monkeypatch.setattr(clips, '_require_scene_clip_base_acceptance',
                        lambda *a: calls.append('historical') or original)
    def pending(*a, **k):
        calls.append('current')
        raise continuity.SceneContinuityPending('current epoch awaits review')
    monkeypatch.setattr(continuity, 'require_scene_continuity_acceptance', pending)
    with pytest.raises(continuity.SceneContinuityPending):
        clips.require_scene_clip_acceptance(object(), [], object())
    assert calls == ['historical', 'current']


def test_completed_prefix_validates_history_before_current_wait(monkeypatch, runtime_run):
    from video_ai.runtime import production_scene_pipeline as pipeline
    from video_ai.runtime import scene_completed as completed
    from video_ai.runtime import scene_continuity_records as continuity
    run = runtime_run[0]; (run / 'production/scene-composition').mkdir(parents=True)
    frozen = SimpleNamespace(options={'script_path': str(run / 'production/script.txt')})
    calls = []
    monkeypatch.setattr(completed, 'validate_scene_completed_prefix', lambda *a:
                        calls.append('historical') or {'composition': {'status': 'ready'}})
    def pending(*a, **k):
        calls.append('current')
        raise continuity.SceneContinuityPending('current epoch awaits review')
    monkeypatch.setattr(continuity, 'require_scene_continuity_acceptance', pending)
    result = pipeline._preflight_later(frozen, [], object())
    assert calls == ['historical', 'current']
    assert result.status == 'awaiting_continuity_review'
    assert result.active_stage == 'source_clips'


def test_direct_media_context_cannot_bypass_current_guard(monkeypatch):
    from video_ai.runtime import scene_media_records as media
    from video_ai.runtime import scene_continuity_records as continuity
    calls = []
    context = {'store': SimpleNamespace(recheck_inputs=True, verify_captured_bytes=lambda: None)}
    monkeypatch.setattr(media, '_scene_media_base_context', lambda *a, **k:
                        calls.append('historical') or context)
    def pending(*a, **k):
        calls.append('current')
        raise continuity.SceneContinuityPending('current epoch awaits review')
    monkeypatch.setattr(continuity, 'capture_scene_continuity_guard', lambda *a, **k: pending)
    with pytest.raises(continuity.SceneContinuityPending):
        media.scene_media_context(object(), [], object())
    assert calls == ['historical', 'current']


def test_media_write_guard_rechecks_current_epoch_before_write(monkeypatch):
    from threading import get_ident
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime import scene_continuity_records as continuity
    store = object.__new__(SceneMediaStore)
    store.caller_thread = get_ident()
    store.frozen = SimpleNamespace(config=SimpleNamespace(raw={
        'scene_rendering': {'mode': 'segmented_v1'}}))
    store._media_check_coverage = None
    store.assert_owned = lambda: None
    def pending():
        raise continuity.SceneContinuityPending('epoch changed before writer')
    store.continuity_check = pending
    with pytest.raises(continuity.SceneContinuityPending):
        store.assert_write()


def test_source_finish_preserves_original_complete_while_current_epoch_waits(monkeypatch, runtime_run):
    from video_ai.runtime import production_scene_clips as clips
    from video_ai.runtime import scene_continuity_records as continuity
    run = runtime_run[0]
    target = run / 'production/scene-clips/complete.json'
    target.parent.mkdir(parents=True)
    original = b'{"schema_version":2,"fixture_only":"historical aggregate"}'
    target.write_bytes(original)
    writes = []
    store = SimpleNamespace(run_dir=run, verify_global=lambda: None,
                            write=lambda path, value: writes.append((path, value)) or target)
    scene = dict(scene_id='scene_0001', status='ready', completed_clip_ids=['scene_0001_clip_0001'],
                 accepted_clip_ids=['scene_0001_clip_0001'], waiting_clip_id=None, error=None)
    context = dict(store=store, frozen=object(), units=[], timeline=object(), rows=[])
    monkeypatch.setattr(clips, 'collect_progress', lambda *a: ({'scenes': [scene]}, {}))
    monkeypatch.setattr(clips, 'complete_value', lambda *a: {'schema_version': 2})
    monkeypatch.setattr(continuity, 'load_continuity_policy', lambda *a: {'policy': 'advisory_v1'})
    def pending(*a, **k):
        raise continuity.SceneContinuityPending('reassessed media awaits analysis')
    monkeypatch.setattr(continuity, 'require_scene_continuity_acceptance', pending)
    result = clips._finish(context)
    assert result.status == 'awaiting_continuity_review' and result.source_clips is None
    assert target.read_bytes() == original
    assert writes == [('complete.json', {'schema_version': 2})]


def test_missing_source_aggregate_wait_does_not_call_original_model_writer(monkeypatch, runtime_run):
    from video_ai.runtime import production_scene_pipeline as pipeline
    from video_ai.runtime import production_scene_clips as clips
    from video_ai.runtime import scene_clip_records as records
    from video_ai.runtime import scene_continuity_records as continuity
    run = runtime_run[0]; (run / 'production/scene-upscale').mkdir(parents=True)
    frozen = SimpleNamespace(options={'script_path': str(run / 'production/script.txt')})
    calls = []
    monkeypatch.setattr(records, 'scene_context', lambda *a, **k: {})
    monkeypatch.setattr(records, 'collect_progress', lambda *a: calls.append('historical') or ({}, {}))
    monkeypatch.setattr(records, 'complete_value', lambda *a: {'schema_version': 2})
    monkeypatch.setattr(clips, 'produce_scene_clips', lambda *a, **k: pytest.fail('called model writer'))
    def pending(*a, **k):
        calls.append('current')
        raise continuity.SceneContinuityPending('new epoch awaits responses')
    monkeypatch.setattr(continuity, 'require_scene_continuity_acceptance', pending)
    result = pipeline._restore_missing_aggregates(frozen, [], object(), paths=None,
                                                 logger=None, lock=None, deps=object())
    assert result.status == 'awaiting_continuity_review'
    assert calls == ['historical', 'current']
    assert not (run / 'production/scene-clips/complete.json').exists()


def test_confirmed_issue_is_blocked_instead_of_pending(monkeypatch):
    from video_ai.runtime import scene_continuity_records as continuity
    from video_ai.runtime.production_state import ProductionRefused
    progress = dict(policy={'policy': 'advisory_v1'}, clips=[dict(
        clip_id='scene_0001_clip_0001', state='blocked', reasons=['confirmed_issue'])])
    monkeypatch.setattr(continuity, 'load_scene_continuity_progress', lambda *a: progress)
    monkeypatch.setattr(continuity, 'load_continuity_policy', lambda *a: progress['policy'])
    with pytest.raises(ProductionRefused) as caught:
        continuity.require_scene_continuity_acceptance(object(), [], object())
    assert not isinstance(caught.value, continuity.SceneContinuityPending)


@pytest.mark.parametrize('durable_intent', [False, True])
def test_parent_guard_rechecks_new_submit_but_preserves_durable_get_recovery(monkeypatch, runtime_run, durable_intent):
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from video_ai.runtime import scene_continuity_records as continuity
    run = runtime_run[0]
    parent, child = 'scene_0001_clip_0001', 'scene_0001_clip_0002'
    request = {'clip_id': child, 'parent': {'clip_id': parent}}
    graph = {'fixture_only': 'No real network operation'}
    store = object.__new__(SceneClipStore)
    store.frozen = SimpleNamespace(options={'model_stamps': {}})
    store.root = run / 'production/scene-clips'
    store.clip_dir = lambda cid: store.root / cid
    store.continuity_context = ([], object())
    store.guard_paths = {}
    store.revision_context = None
    store.verify_global = lambda: None
    store.artifact = lambda path: {'path': str(path), 'bytes': 1, 'sha256': 'a' * 64}
    store.validate_artifact = lambda *a: None
    def read(path):
        return {'request.json': request, 'graph.json': graph,
                'intent.json': {'existing': True} if durable_intent else None}.get(Path(path).name)
    store.read = read
    def pending(*a, **k):
        assert k == {'clip_id': parent}
        raise continuity.SceneContinuityPending('parent was reassessed before submit')
    monkeypatch.setattr(continuity, 'require_scene_continuity_acceptance', pending)
    guard = store.capture_guard(request, graph)
    if durable_intent:
        guard()  # Existing original intent may poll, and the transaction never re-POSTs it.
    else:
        with pytest.raises(continuity.SceneContinuityPending):
            guard()


def test_parent_scoped_admission_includes_earlier_retained_scene_prefix(monkeypatch):
    from video_ai.runtime import scene_continuity_records as continuity
    from video_ai.runtime import scene_clip_records as clips
    from video_ai.runtime.production_state import ProductionRefused
    first, second = 'scene_0001_clip_0001', 'scene_0001_clip_0002'
    rows = [dict(budget=dict(clip_id=cid, scene_id='scene_0001', parent_clip_id=parent))
            for cid, parent in ((first, None), (second, first))]
    progress = dict(policy={'policy': 'advisory_v1'}, clips=[
        dict(clip_id=first, state='blocked', reasons=['confirmed_issue']),
        dict(clip_id=second, state='ready_for_next_stage', reasons=[])])
    monkeypatch.setattr(continuity, 'load_scene_continuity_progress', lambda *a: progress)
    monkeypatch.setattr(continuity, 'load_continuity_policy', lambda *a: progress['policy'])
    monkeypatch.setattr(clips, 'scene_context', lambda *a, **k: {'rows': rows})
    with pytest.raises(ProductionRefused):
        continuity.require_scene_continuity_acceptance(object(), [], object(), clip_id=second)


def test_review_cannot_borrow_receipt_for_different_original_video_bytes(monkeypatch, runtime_run):
    import hashlib
    import json
    from uuid import uuid4
    from video_ai.runtime import scene_continuity_records as continuity
    from video_ai.runtime._scene_continuity_io import Reader, artifact
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.planning.production_scenes import canonical_digest
    run = runtime_run[0]; aid = str(uuid4()); cid = 'scene_0001_clip_0001'
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
        return artifact(path)
    root = run / 'production/scene-continuity'
    assessment_path = root / 'jobs' / aid / 'assessment.json'
    assessment = {'assessment_id': aid, 'clip_id': cid}
    save(assessment_path, assessment)
    video = {'verdict': 'passed', 'reviewer': 'fixture_only'}
    original = run / 'original-video-observation.json'
    original_id = save(original, video)
    alternate = run / 'same-json-different-author-bytes.json'
    alternate.write_text(json.dumps(video, indent=4), encoding='utf-8')
    assert original.read_bytes() != alternate.read_bytes()
    folder = run / 'production/scene-clips' / cid
    save(folder / 'observation-accepted.json', dict(schema_version=2, run_id=run.name, clip_id=cid,
        clip_sha256='a' * 64, request_sha256='b' * 64, observation=original_id,
        observation_sha256=canonical_digest(video), accepted_at='2020-01-02T00:00:00+00:00'))
    review = dict(assessment_id=aid, video_observation=artifact(alternate), reviewed_at='2020-01-01T00:00:00+00:00')
    raw = json.dumps(review).encode()
    raw_path = root / 'reviews' / (hashlib.sha256(raw).hexdigest() + '.json')
    raw_path.parent.mkdir(parents=True); raw_path.write_bytes(raw)
    save(root / 'reviews' / aid / 'receipt.json', dict(schema_version=1, run_id=run.name,
        assessment_id=aid, assessment=artifact(assessment_path), review=artifact(raw_path),
        video_receipt=artifact(folder / 'observation-accepted.json'), state='ready_for_next_stage',
        created_at='2020-01-02T00:00:00+00:00'))
    record = {'clip': {'source': {'path': str(folder / 'source.mp4')}}}
    monkeypatch.setattr(continuity, '_review_expected', lambda *a: {})
    monkeypatch.setattr(continuity, 'validate_continuity_review', lambda *a, **k: review)
    monkeypatch.setattr(continuity, '_review_state', lambda *a: 'ready_for_next_stage')
    with pytest.raises(ProductionRefused):
        continuity._reviews({'store': SimpleNamespace(run_dir=run)}, {cid: record},
                            assessment, assessment_path, Reader())


def test_prefix_playback_rejects_fabricated_historical_assessment_stub(runtime_run):
    import json
    from uuid import uuid4
    from datetime import datetime, timezone
    from video_ai.runtime import scene_continuity_records as continuity
    from video_ai.runtime._scene_continuity_io import Reader, artifact
    from video_ai.runtime.production_state import ProductionRefused
    run = runtime_run[0]; aid = str(uuid4()); binding = {'clips': []}
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
        return artifact(path)
    for i in range(3):
        clip = run / ('clip-record-' + str(i) + '.json')
        binding['clips'].append(dict(clip_id=f'scene_0001_clip_{i + 1:04d}',
            source={'path': str(run / f'source-{i}.mp4'), 'bytes': 1, 'sha256': str(i) * 64},
            clip_record=save(clip, {'created_at': '2020-01-01T00:00:00+00:00'}),
            source_frames=[0, 4], output_frames=[i * 4, (i + 1) * 4]))
    fabricated = save(run / 'fabricated-assessment.json', {'assessment_id': aid, 'binding': binding})
    prefix = dict(schema_version=1, run_id=run.name, assessment_id=aid, assessment=fabricated,
        review_method='agent_video', reviewer='fixture_only', viewed_at='2020-01-02T00:00:00+00:00',
        playback=[{k: r[k] for k in ('clip_id', 'source', 'source_frames', 'output_frames')} for r in binding['clips']],
        start_observation='synthetic', process_observation='synthetic', end_observation='synthetic',
        quality_observation='synthetic', checks={k: 'passed' for k in
            ('subject_identity', 'color_lighting', 'motion_process', 'camera_path', 'cumulative_color')},
        verdict='passed', issues=[])
    prefix_id = save(run / 'prefix.json', prefix)
    with pytest.raises(ProductionRefused):
        continuity._prefix(prefix_id, {'run': run, 'binding': binding}, {'verdict': 'passed'},
                           'fixture_only', datetime.now(timezone.utc), Reader())


def test_inherited_binding_reads_metadata_from_proved_origin(monkeypatch, runtime_run):
    import json
    from video_ai.runtime import scene_continuity_records as continuity
    from video_ai.runtime import scene_revision_records as revisions
    from video_ai.runtime import _scene_revision_origins as origins
    from video_ai.runtime import production_inputs as inputs
    from video_ai.runtime._scene_continuity_io import artifact
    run = runtime_run[0]; cid = 'scene_0001_clip_0001'
    origin_folder = run / 'proved-origin' / cid
    origin_folder.mkdir(parents=True)
    for name in ('clip.json', 'request.json', 'mapping.json', 'last-frame.json'):
        (origin_folder / name).write_text(json.dumps({'fixture_only': name}), encoding='utf-8')
    copied = run / 'production/scene-revision/media' / cid
    copied.mkdir(parents=True)
    for name in ('source.mp4', 'generated.mp4'):
        (copied / name).write_bytes(b'fixture only; never decode')
        (origin_folder / name).write_bytes(b'fixture only; never decode')
    original_record = dict(clip={'source': artifact(origin_folder / 'source.mp4'),
                                 'generated': artifact(origin_folder / 'generated.mp4')},
                           request={'selected_image': {}, 'comparison_images': []})
    copied_record = dict(original_record, clip={'source': artifact(copied / 'source.mp4'),
                                               'generated': artifact(copied / 'generated.mp4')})
    proof = {'imports': {'clip:' + cid: ({'origin_artifact': artifact(origin_folder / 'clip.json')}, {})},
             'source_run': run / 'proved-origin'}
    frozen = SimpleNamespace(options={'scene_revision': {}}, config=SimpleNamespace(raw={}))
    monkeypatch.setattr(revisions, 'require_scene_revision', lambda *a: proof)
    monkeypatch.setattr(inputs, 'load_frozen_inputs', lambda *a: object())
    monkeypatch.setattr(origins, 'source_clip_record', lambda *a: original_record)
    context = dict(store=SimpleNamespace(run_dir=run, revision_context=proof), frozen=frozen,
                   rows=[{'budget': dict(scene_id='scene_0001', clip_id=cid, retained_frames=4,
                                         start_frame=0, end_frame=4)}],
                   inputs={'visual_bible_sha256': 'a' * 64})
    binding = continuity._binding(context, {cid: copied_record}, cid)
    assert binding['clips'][0]['clip_record'] == artifact(origin_folder / 'clip.json')
    assert binding['clips'][0]['source'] == copied_record['clip']['source']


def test_direct_publish_checks_current_diagnostics_even_for_completed_transaction(monkeypatch):
    from video_ai.runtime import scene_delivery_files as delivery
    from video_ai.runtime import scene_continuity_records as continuity
    def blocked(*args,**kwargs):raise continuity.SceneContinuityPending('current epoch needs review')
    monkeypatch.setattr(continuity,'require_scene_continuity_acceptance',blocked)
    context=dict(frozen=object(),units={},timeline=None,store=SimpleNamespace(root=None))
    with pytest.raises(continuity.SceneContinuityPending):
        delivery.publish(context,{}, {},object(),lambda:None)
