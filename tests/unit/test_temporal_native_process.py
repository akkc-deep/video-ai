"""Native jobs own their Popen object; existing intent never gains a second sample."""
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from unit.test_temporal_scene_records import request_fixture, put

GIB = 1024**3
HEALTHY = dict(physical=9*GIB, commit=11*GIB, gpu=19*GIB, disk=64*GIB)


@pytest.fixture
def job(runtime_run, tmp_path, monkeypatch):
    import video_ai.runtime.temporal_native_process as native
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.resources import GpuLease
    from video_ai.runtime import resources
    from video_ai.runtime.temporal_scene_records import expected_temporal_request, temporal_workflow
    context, row, input_record, parent = request_fixture(runtime_run)
    store = context['store']; store.frozen.config = runtime_run[1]
    store.paths = replace(runtime_run[2], cache_root=tmp_path/'native-cache')
    request = expected_temporal_request(context, row, input_record, parent)
    workflow = temporal_workflow(context, row)
    folder = store.clip_dir(row['budget']['clip_id'])
    put(folder/'input.json', input_record); put(folder/'request.json', request); put(folder/'workflow.json', workflow)
    monkeypatch.setattr(native, 'process_started_at', lambda pid: 'fixture_start')
    monkeypatch.setattr(resources, 'gpu_guard', lambda *a, **k: dict(status='verified', external_pids=[]))
    data = {'resources': {}}
    manifest = SimpleNamespace(run_dir=store.run_dir, update=lambda callback: callback(data))
    logger = SimpleNamespace(event=lambda *a, **k: None)
    with RunLock(store.run_dir) as lock:
        store.lock = lock
        lease = GpuLease(store.paths, manifest, logger).acquire('source_clips', 'fixture_only')
        store.gpu_lease = lease
        try: yield native, store, request, workflow, folder
        finally: lease.release()


class FakeProcess:
    pid = 777777
    def __init__(self, finish=None, forever=False):
        self.returncode = None; self.finish = finish; self.forever = forever
        self.polls = 0; self.waits = []; self.terminated = False
    def poll(self):
        if self.returncode is not None: return self.returncode
        self.polls += 1
        if not self.forever and self.polls >= 2:
            if self.finish is not None: self.finish()
            self.returncode = 0
        return self.returncode
    def wait(self, timeout=None):
        self.waits.append(timeout)
        return self.returncode
    def terminate(self): self.terminated = True; self.returncode = 15
    def kill(self): self.terminate()


def completed_outputs(folder, request):
    from video_ai.planning.production_scenes import canonical_digest
    digest = canonical_digest(request)
    put(folder/'intent.json', dict(request_sha256=digest))
    put(folder/'sample-complete.json', dict(request_sha256=digest, native_diffusion_completed=True))
    put(folder/'native-result.json', dict(request_sha256=digest))


def test_fresh_worker_wait_has_no_total_timeout_and_replay_never_spawns(job):
    native, store, request, workflow, folder = job
    calls = []
    process = FakeProcess(lambda: completed_outputs(folder, request))
    def factory(args, **kwargs): calls.append((args, kwargs)); return process
    result = native.recover_or_start_native_window(store, request, workflow, worker_factory=factory,
        resource_sampler=lambda: dict(HEALTHY), sleeper=lambda seconds: None)
    assert result['status'] == 'completed' and len(calls) == 1
    assert None in process.waits and not process.terminated
    assert calls[0][1]['env']['PYTORCH_ALLOC_CONF'] == 'backend:cudaMallocAsync'
    assert '--operation' in calls[0][0] and 'one-window' in calls[0][0]
    start = json.loads((folder/'window-start.json').read_bytes())
    assert start['time_limit_seconds'] is None and start['max_gpu_allocated_bytes'] is None
    before = (folder/'window-start.json').read_bytes()
    assert native.recover_or_start_native_window(store, request, workflow, worker_factory=factory)['status'] == 'completed'
    assert len(calls) == 1 and (folder/'window-start.json').read_bytes() == before


def test_existing_unknown_intent_never_starts_a_worker(job):
    native, store, request, workflow, folder = job
    from video_ai.planning.production_scenes import canonical_digest
    put(folder/'intent.json', dict(request_sha256=canonical_digest(request)))
    def forbidden(*a, **k): raise AssertionError('unknown cannot start worker')
    result = native.recover_or_start_native_window(store, request, workflow, worker_factory=forbidden)
    assert result['status'] == 'unknown'


def test_committed_sample_starts_decode_only_without_replacing_original_intent(job):
    native, store, request, workflow, folder = job
    from video_ai.planning.production_scenes import canonical_digest
    digest = canonical_digest(request)
    put(folder/'intent.json', dict(request_sha256=digest))
    put(folder/'sample-complete.json', dict(request_sha256=digest, native_diffusion_completed=True))
    original = (folder/'intent.json').read_bytes()
    calls = []
    def finish(): put(folder/'native-result.json', dict(request_sha256=digest))
    def factory(args, **kwargs): calls.append(args); return FakeProcess(finish)
    result = native.recover_or_start_native_window(store, request, workflow, worker_factory=factory,
        resource_sampler=lambda: dict(HEALTHY), sleeper=lambda seconds: None)
    assert result['status'] == 'completed' and len(calls) == 1
    assert 'decode-only' in calls[0] and 'one-window' not in calls[0]
    assert (folder/'intent.json').read_bytes() == original


def test_resource_stop_keeps_exact_trigger_sample_and_only_terminates_owned_object(job):
    native, store, request, workflow, folder = job
    samples = iter([dict(HEALTHY), dict(HEALTHY, commit=3*GIB)])
    process = FakeProcess(forever=True)
    result = native.recover_or_start_native_window(store, request, workflow, worker_factory=lambda *a, **k: process,
        resource_sampler=lambda: next(samples), sleeper=lambda seconds: None)
    assert result['status'] == 'failed' and process.terminated
    terminal = json.loads((folder/'process-terminal.json').read_bytes())
    assert terminal['stop_reason'] == 'commit_reserve'
    assert terminal['stop_snapshot']['commit'] == 3*GIB
    assert terminal['stop_thresholds']['commit'] == 4*GIB


def test_pid_reuse_does_not_spawn_or_kill_a_foreign_process(job, monkeypatch):
    native, store, request, workflow, folder = job
    from video_ai.planning.production_scenes import canonical_digest
    put(folder/'intent.json', dict(request_sha256=canonical_digest(request)))
    put(folder/'owner.json', dict(request_sha256=canonical_digest(request), workflow_sha256=canonical_digest(workflow),
        pid=12345, process_started_at='old_start', token='a'*32, operation='one-window'))
    monkeypatch.setattr(native, 'process_started_at', lambda pid: 'different_start')
    def forbidden(*a, **k): raise AssertionError('PID reuse cannot start a worker')
    assert native.recover_or_start_native_window(store, request, workflow, worker_factory=forbidden)['status'] == 'unknown'


def test_sampler_requires_actual_held_run_lock_and_gpu_lease(job):
    native, store, request, workflow, folder = job
    from video_ai.runtime.production_state import ProductionRefused
    store.gpu_lease = None
    def forbidden(*a, **k): raise AssertionError('unowned GPU cannot start worker')
    with pytest.raises(ProductionRefused):
        native.recover_or_start_native_window(store, request, workflow, worker_factory=forbidden,
            resource_sampler=lambda: dict(HEALTHY))


def test_missing_new_cache_prepares_separately_before_any_video_intent(job,monkeypatch):
    native,store,request,workflow,folder=job
    from video_ai.runtime import temporal_native_worker as worker
    prepared=[];calls=[]
    def resolver(value):
        if not prepared:raise worker.MissingNativeTextCache('fixture_only new prompt')
        return dict(cache={'fixture_only':True},binding={'fixture_only':True})
    monkeypatch.setattr(worker,'existing_native_text_context',resolver)
    def factory(command,**kwargs):
        calls.append(command)
        return FakeProcess(lambda:prepared.append(True))
    value=native.recover_or_prepare_native_cache(store,request,workflow,worker_factory=factory,
        resource_sampler=lambda:dict(HEALTHY),sleeper=lambda seconds:None)
    assert value['status']=='prepared' and len(calls)==1 and 'prepare-cache' in calls[0]
    assert not (folder/'intent.json').exists() and not (folder/'launch-intent.json').exists()
    assert native.recover_or_prepare_native_cache(store,request,workflow,worker_factory=factory)['status']=='prepared'
    assert len(calls)==1


def test_unknown_cache_prepare_never_launches_another_encoder(job,monkeypatch):
    native,store,request,workflow,folder=job
    from video_ai.runtime import temporal_native_worker as worker
    def missing(value):raise worker.MissingNativeTextCache('fixture_only new prompt')
    monkeypatch.setattr(worker,'existing_native_text_context',missing)
    cache_folder=store.path('text-context')/request['text_cache_key']
    put(cache_folder/'launch-intent.json',dict(fixture_only='unknown encoder'))
    def forbidden(*a,**k):raise AssertionError('unknown encoder cannot launch again')
    result=native.recover_or_prepare_native_cache(store,request,workflow,worker_factory=forbidden)
    assert result['status']=='unknown' and not (folder/'intent.json').exists()
