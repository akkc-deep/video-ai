"""Formal legacy entry points wait indefinitely, with finite HTTP requests."""
import json
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('module_name', ['_source_clip_generation', '_upscale_generation', 'start_image_checks'])
def test_formal_legacy_http_outlives_old_deadline_and_keeps_request_bound(monkeypatch, module_name):
    import importlib
    from video_ai.adapters.common import HttpClient
    from video_ai.runtime.execution_limits import production_execution
    module = importlib.import_module('video_ai.runtime.'+module_name)
    clock = [0.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    calls = []
    def request(self, *args, **kwargs):
        calls.append(kwargs['timeout'])
        clock[0] += 100000
        return SimpleNamespace(evidence_path=__import__('pathlib').Path('http.body'))
    monkeypatch.setattr(HttpClient, 'request', request)
    @production_execution
    def operation():
        client_type = getattr(module, 'DeadlineHttp', None) or module._DeadlineHttp
        client = client_type('http://127.0.0.1:8188', .25, None)
        if module_name != '_upscale_generation':
            client.set_deadline(1)
        else:
            client.set_deadlines(1, 1)
            client.paths = []
            client.unit_id = 'shot_0001:frame_000001'
        clock[0] = 100000
        client.request('GET', '/queue')
        client.request('GET', '/queue')
        assert client.remaining() is None
    operation()
    assert calls == [.25, .25]


def test_public_pipeline_resume_scopes_even_historical_runs(monkeypatch):
    from contextlib import contextmanager
    from pathlib import Path
    from video_ai import pipeline
    from video_ai.runtime.execution_limits import unlimited_execution
    @contextmanager
    def exclusive(run):
        yield object()
    monkeypatch.setattr(pipeline, '_run_path', lambda run: run)
    monkeypatch.setattr(pipeline, 'exclusive', exclusive)
    monkeypatch.setattr(pipeline, '_invocation', lambda *a, **kw: (unlimited_execution(), None))
    assert pipeline.resume_pipeline(None, run_dir=Path('historical')) is True
    assert unlimited_execution() is False


def test_new_upscale_policy_is_unlimited_and_legacy_policy_stays_readable():
    from video_ai.runtime._upscale_resume import policy, check_policy
    config = SimpleNamespace(timeouts={'upscale_frame': 1, 'comfy_request': .25})
    value = policy(config)
    assert value.get('time_limits') == 'unlimited_v1'
    assert value['frame_timeout_seconds'] is None
    assert value['media_command_timeout_seconds'] is None
    legacy = dict(total_timeout_seconds=None, frame_timeout_seconds=1,
        media_command_timeout_seconds=300, request_timeout_seconds=.25)
    frozen = json.dumps(legacy)
    check_policy(legacy)
    assert json.dumps(legacy) == frozen


def test_public_upscale_receipt_replays_outside_scope_after_old_frame_budget(runtime_run, monkeypatch):
    from upscale_helpers import setup, review
    from video_ai.runtime.execution_limits import unlimited_execution
    # Every real command and durable checkpoint exceeds this obsolete phase limit.
    f = setup(runtime_run, monkeypatch, frame_timeout=.000001)
    result = f.uc.prepare_upscaled_clips(f.config, run_dir=f.run)
    assert result.status == 'review_required'
    assert not unlimited_execution()
    draft = json.loads(result.draft_path.read_text(encoding='utf-8'))
    assert draft['execution_policy']['time_limits'] == 'unlimited_v1'
    context = f.uc.inputs(f.config, f.run)
    f.uc.validate(f.config, f.run, draft, context, f.store.snapshot())
    assert len(f.requests) == 2
    path, _ = review(f.run)
    assert f.uc.finalize_upscaled_clips(f.config, run_dir=f.run, review_path=path).passed
    assert f.uc.load_committed_upscaled_clips(f.run)['execution_policy']['time_limits'] == 'unlimited_v1'


def test_source_receipt_replays_outside_scope_after_old_attempt_budget(runtime_run, monkeypatch):
    from source_clip_helpers import setup, user_acceptance
    from video_ai.runtime.execution_limits import unlimited_execution
    f = setup(runtime_run, monkeypatch, wan_timeout=.000001)
    result = f.sc.prepare_source_clips(f.config, run_dir=f.run)
    assert result.status == 'review_required'
    assert not unlimited_execution()
    draft = json.loads(result.draft_path.read_text(encoding='utf-8'))
    assert all(clip['attempts'][0]['execution_policy'] ==
        {'time_limits': 'unlimited_v1', 'timeout_seconds': None} for clip in draft['clips'])
    path, _ = user_acceptance(f.run)
    assert f.sc.finalize_source_clips(f.config, run_dir=f.run, review_path=path).passed
    assert len(f.sc.load_committed_source_clips(f.run)['clips']) == 7


@pytest.mark.parametrize('legacy', [False, True])
def test_pipeline_options_read_current_and_frozen_legacy_without_rewrite(runtime_run, legacy):
    from video_ai import pipeline
    from video_ai.runtime.manifest import now, hash_file, thaw
    run, _, _ = runtime_run
    script = run/'script.txt'
    script.write_text('test', encoding='utf-8')
    policy = dict(gpu_management='disabled', total_timeout_seconds=None,
        media_command_timeout_seconds=300 if legacy else None)
    if not legacy:policy['time_limits'] = 'unlimited_v1'
    path = run/'logs/pipeline/pipeline-options.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(schema_version=1, run_id=run.name, created_at=now(),
        input_identities=dict(script=thaw(hash_file(script))), unit_review_identity=None,
        image_inputs_identity=None, settings_identity=None, output_path=None,
        cpu_planner=False, execution_policy=policy)), encoding='utf-8')
    before = hash_file(path)
    options, ids = pipeline._options(run)
    assert options['script'] == script
    assert ids['options'].sha256 == before.sha256
    assert hash_file(path).sha256 == before.sha256


def test_interrupted_imported_upscale_prefix_replays_unlimited_without_post(runtime_run, monkeypatch):
    """A child must persist policy before a complete clip/draft can exist."""
    from datetime import datetime, timedelta
    from upscale_helpers import setup, write
    from unit.test_pipeline_revision_resume import source_copy, route_output
    from video_ai.adapters.common import AdapterError, FailureKind
    from video_ai.runtime.manifest import ManifestStore
    from video_ai.runtime.pipeline_import import derive_partial_stage
    from video_ai.runtime.pipeline_stages import prepare
    from video_ai.runtime._upscale_resume import reconstruct
    from video_ai.runtime.execution_limits import unlimited_execution
    f = setup(runtime_run, monkeypatch, frames=3, frame_timeout=.000001)
    native = f.ug.ComfyClient.validate_template
    def stop_second(client, template):
        if client.http.unit_id.endswith('000002'):
            raise AdapterError(FailureKind.ambiguous, 'TEST ONLY before second POST')
        return native(client, template)
    monkeypatch.setattr(f.ug.ComfyClient, 'validate_template', stop_second)
    assert f.uc.prepare_upscaled_clips(f.config, run_dir=f.run).status == 'failed'
    monkeypatch.setattr(f.ug.ComfyClient, 'validate_template', native)
    child = derive_partial_stage(f.config, parent_run_dir=f.run, stage='upscale')
    source_copy(f, child)
    route_output(f, child)
    f.process.stopped = False
    def stop_third(client, template):
        if client.http.unit_id.endswith('000003'):
            raise AdapterError(FailureKind.ambiguous, 'TEST ONLY before third POST')
        return native(client, template)
    monkeypatch.setattr(f.ug.ComfyClient, 'validate_template', stop_third)
    child_store = ManifestStore.open(child)
    assert prepare('upscale', f.config, child, options={}, reviews={}, store=child_store).status == 'failed'
    assert len(f.requests) == 2
    # Represent a completed extraction lasting longer than the historical 300s
    # cap without sleeping or changing frame, graph, or submission identities.
    extraction = next((child/'logs/upscale').glob('extract-*.json'))
    data = json.loads(extraction.read_text(encoding='utf-8'))
    data['command']['started_at'] = (datetime.fromisoformat(data['command']['finished_at'])
        - timedelta(seconds=301)).isoformat()
    write(extraction, data)
    before = (child/'manifest.json').read_bytes()
    snapshot = child_store.snapshot()
    assert not unlimited_execution()
    retained, _, _ = reconstruct(f.config, child, snapshot, f.uc.inputs(f.config, child), _pipeline=True)
    assert len(retained['partial']['shot_0001']['frames']) == 2
    assert 'upscale_execution_policy' in snapshot['workflows']
    assert len(f.requests) == 2 and (child/'manifest.json').read_bytes() == before


@pytest.mark.parametrize('operation', ['prepare_start_images', 'resume_start_images', 'finalize_start_images'])
def test_public_start_images_wait_without_budget_and_reset_scope(monkeypatch, operation):
    from pathlib import Path
    from video_ai.runtime import start_image_checks as images
    from video_ai.runtime.execution_limits import execution_deadline, execution_remaining, unlimited_execution
    class ReachedImageWork(Exception):
        pass
    def work(*args, **kwargs):
        assert execution_remaining(execution_deadline(1, 0), 100000) is None
        raise ReachedImageWork
    monkeypatch.setattr(images, '_run_path', work)
    kwargs = dict(run_dir=Path('historical'))
    if operation == 'resume_start_images':kwargs['reuse_context'] = None
    if operation == 'finalize_start_images':kwargs['review_path'] = Path('review.json')
    with pytest.raises(ReachedImageWork):
        getattr(images, operation)(None, **kwargs)
    assert not unlimited_execution()


@pytest.mark.parametrize('operation', ['derive_completed_stages', 'derive_run', 'derive_reconciled_run'])
def test_public_child_derivation_waits_without_budget_and_resets_scope(monkeypatch, operation):
    from pathlib import Path
    from video_ai.runtime import pipeline_import, _pipeline_saved_import
    from video_ai.runtime.execution_limits import execution_deadline, execution_remaining, unlimited_execution
    class ReachedChildWork(Exception):
        pass
    def work(*args, **kwargs):
        assert execution_remaining(execution_deadline(1, 0), 100000) is None
        raise ReachedChildWork
    module = _pipeline_saved_import if operation == 'derive_reconciled_run' else pipeline_import
    monkeypatch.setattr(module, '_derive_completed_stages' if operation == 'derive_completed_stages' else '_run_path', work)
    kwargs = dict(parent_run_dir=Path('historical'))
    if operation == 'derive_completed_stages':kwargs.update(stages=(), reason='test')
    else:kwargs['plan'] = SimpleNamespace(reused=())
    if operation == 'derive_reconciled_run':kwargs['reconciliations'] = ()
    with pytest.raises(ReachedChildWork):
        getattr(module, operation)(None, **kwargs)
    assert not unlimited_execution()


def test_first_public_resume_of_real_finite_policy_preserves_old_receipts(runtime_run, monkeypatch):
    """TEST ONLY simulate a >300s new inspection; historical bytes stay frozen."""
    from datetime import datetime, timedelta
    from pathlib import Path
    from upscale_helpers import setup, review, write
    from video_ai.adapters.common import AdapterError, FailureKind
    from video_ai.runtime import _upscale_resume
    from video_ai.runtime.execution_limits import unlimited_execution
    f = setup(runtime_run, monkeypatch)
    native_validate = f.ug.ComfyClient.validate_template
    current_policy = _upscale_resume.policy
    def stop_tail(client, template):
        if client.http.unit_id.endswith('000002'):
            raise AdapterError(FailureKind.ambiguous, 'TEST ONLY old unsubmitted tail')
        return native_validate(client, template)
    # Reproduce the historical pipeline writer and actual finite frame/media
    # execution. The restored public API must upgrade only subsequent work.
    with monkeypatch.context() as historical:
        historical.setattr(_upscale_resume, 'policy',
            lambda config, *, legacy=False: current_policy(config, legacy=True))
        historical.setattr(f.ug.ComfyClient, 'validate_template', stop_tail)
        assert f.uc.prepare_upscaled_clips.__wrapped__(f.config, run_dir=f.run,
            execution_policy='pipeline').status == 'failed'
    before = f.store.snapshot()
    old_policy = before['workflows']['upscale_execution_policy']
    old_policy_path = Path(old_policy['path'])
    old_policy_bytes = old_policy_path.read_bytes()
    assert json.loads(old_policy_bytes)['media_command_timeout_seconds'] == 300
    old_frame_path = f.run/'logs/upscale/frame-shot_0001-000001.json'
    old_frame_bytes = old_frame_path.read_bytes()
    assert 'execution_policy' not in json.loads(old_frame_bytes)
    posts_before = len(f.requests)
    encode = f.ug.encode_video_frames
    simulated = []
    def long_new_inspection(*args, **kwargs):
        info, logs = encode(*args, **kwargs)
        for path in logs:
            if path.suffix != '.json' or not path.name.startswith('media-'):
                continue
            data = json.loads(path.read_text(encoding='utf-8'))
            if Path(data['info']['identity']['path']).parent.name != 'upscaled-frames':
                continue
            # This new encoding-copy inspection is outside the historical
            # frame interval. Simulate elapsed wall time without a real wait.
            command = data['commands'][0]
            command['finished_at'] = (datetime.fromisoformat(command['started_at'])
                + timedelta(seconds=301)).isoformat()
            write(path, data)
            simulated.append(path)
        return info, logs
    monkeypatch.setattr(f.ug, 'encode_video_frames', long_new_inspection)
    f.process.stopped = False
    result = f.uc.resume_upscaled_clips(f.config, run_dir=f.run)
    assert result.status == 'review_required' and simulated
    assert len(f.requests) == posts_before + 1
    assert f.store.snapshot()['workflows']['upscale_execution_policy'] == old_policy
    assert old_policy_path.read_bytes() == old_policy_bytes
    assert old_frame_path.read_bytes() == old_frame_bytes
    assert f.store.snapshot()['units']['frame']['shot_0001:frame_000001'] == before['units']['frame']['shot_0001:frame_000001']
    assert not unlimited_execution()
    path, _ = review(f.run)
    assert f.uc.finalize_upscaled_clips(f.config, run_dir=f.run, review_path=path).passed
    assert not unlimited_execution()
    report = f.uc.load_committed_upscaled_clips(f.run)
    assert report['execution_policy']['time_limits'] == 'unlimited_v1'
    assert len(f.requests) == posts_before + 1
    assert old_frame_path.read_bytes() == old_frame_bytes and old_policy_path.read_bytes() == old_policy_bytes

