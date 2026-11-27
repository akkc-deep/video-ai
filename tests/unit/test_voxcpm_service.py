"""Real task storage and HTTP; only GPU inference is replaced with controlled audio."""
import json
from pathlib import Path
import threading
import time
import wave

import pytest

from video_ai.voxcpm.contracts import ApiError, freeze_request
from video_ai.voxcpm.store import JobStore
from video_ai.voxcpm.service import JobService

BINDING = dict(voice_id='existing-reference', reference_sha256='a'*64,
               model_revision='model-1', source_revision='source-1')
BODY = dict(request_id='sample_1', text='我们收到了来自远方的消息。')


@pytest.fixture
def store(tmp_path):
    root = tmp_path/'runtime'
    state = root/'scratch/tts-test'
    with JobStore(state, root) as value:
        yield value


def frozen(**changes):
    return freeze_request(dict(BODY, **changes), BINDING)


def wav(path, frames=480):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\x01\x00' * frames)


def wait_for(call, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = call()
        if predicate(value):
            return value
        time.sleep(.01)
    raise AssertionError(f'condition not reached: {value}')


def test_concurrent_duplicate_persists_one_identity_and_conflicts(store):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: store.submit(frozen()), range(8)))
    assert sum(created for task, created in results) == 1
    assert all(task['status'] == 'queued' for task, created in results)
    with pytest.raises(ApiError) as error:
        store.submit(frozen(seed=9))
    assert error.value.status == 409


@pytest.mark.parametrize('changes', [dict(request_id='../bad'), dict(text=' '),
    dict(text='字'*251), dict(cfg_value=float('nan')), dict(seed=True),
    dict(inference_timesteps=0), dict(voice_id='missing'), dict(output_path='C:/other.wav'),
    dict(emotion_intensity=1.1)])
def test_invalid_request_cannot_choose_paths_or_invalid_parameters(changes):
    with pytest.raises(ApiError) as error:
        frozen(**changes)
    assert error.value.status == 400


def test_queued_and_running_cancellation_are_distinct(store):
    store.submit(frozen())
    assert store.cancel('sample_1')['status'] == 'cancelled'
    assert store.claim(BINDING) is None
    store.submit(frozen(request_id='running'))
    assert store.claim(BINDING)['status'] == 'running'
    assert store.cancel('running')['status'] == 'cancel_requested'
    temp = store.temporary('running')
    wav(temp)
    result = store.finish('running', temp, dict(generation_time_ms=10))
    assert result['status'] == 'cancelled'
    assert not store.output_path('running').exists()


def test_completion_survives_restart_without_rerun(store):
    store.submit(frozen())
    store.claim(BINDING)
    wav(store.temporary('sample_1'))
    result = store.finish('sample_1', store.temporary('sample_1'), dict(generation_time_ms=10))
    assert result['result']['sample_count'] == 480
    assert result['result']['duration_ms'] == 10
    store.recover()
    assert store.get('sample_1')['result'] == result['result']
    assert store.submit(frozen())[1] is False
    assert store.claim(BINDING) is None


def test_recovery_preserves_queued_and_fails_uncommitted_running(store):
    store.submit(frozen())
    store.claim(BINDING)
    store.submit(frozen(request_id='waiting'))
    store.recover()
    assert store.get('sample_1')['status'] == 'failed'
    assert 'interrupted' in store.get('sample_1')['error']
    assert store.get('waiting')['status'] == 'queued'


def test_published_receipt_recovers_without_claiming_new_generation(store):
    from video_ai.runtime.storage_files import write_record
    task, _ = store.submit(frozen())
    store.claim(BINDING)
    path = store.output_path('sample_1')
    wav(path)
    write_record(path.with_suffix('.json'), dict(fingerprint=task['fingerprint'], result=dict(
        audio_path=path.relative_to(store.directory).as_posix(), sample_rate=48000,
        sample_count=480, channels=1, sample_width=2, duration_ms=10, generation_time_ms=10)))
    store.recover()
    assert store.get('sample_1')['status'] == 'completed'
    assert store.claim(BINDING) is None


def test_changed_frozen_binding_fails_queued_instead_of_generating_new_voice(store):
    store.submit(frozen())
    assert store.claim(dict(BINDING, reference_sha256='b'*64)) is None
    assert store.get('sample_1')['status'] == 'failed'
    assert 'input_changed' in store.get('sample_1')['error']


def test_state_directory_cannot_escape_runtime_or_overlap_second_owner(store, tmp_path):
    with pytest.raises(ValueError):
        JobStore(tmp_path/'outside', tmp_path/'runtime')
    with pytest.raises(ValueError):
        JobStore(store.directory, store.runtime_root)


class ControlledBackend:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.generated = []

    def generate(self, request, temporary):
        self.generated.append(request['request_id'])
        self.entered.set()
        assert self.release.wait(5)
        if request['text'] == 'fail':
            raise RuntimeError('inference failed')
        wav(temporary)
        return dict(generation_time_ms=10)


def test_running_cancel_waits_for_actual_inference_end_and_model_is_reused(store):
    backend = ControlledBackend()
    service = JobService(store, BINDING, lambda: backend)
    service.start()
    try:
        service.submit(BODY)
        assert backend.entered.wait(5)
        assert service.cancel('sample_1')['status'] == 'cancel_requested'
        assert store.get('sample_1')['status'] == 'cancel_requested'
        service.submit(dict(BODY, request_id='second'))
        backend.release.set()
        wait_for(lambda: store.get('second'), lambda t: t['status'] == 'completed')
        assert store.get('sample_1')['status'] == 'cancelled'
        assert backend.generated == ['sample_1', 'second']
    finally:
        backend.release.set()
        service.close()


def test_inference_error_is_durable_and_duplicate_does_not_retry(store):
    backend = ControlledBackend()
    backend.release.set()
    service = JobService(store, BINDING, lambda: backend)
    service.start()
    try:
        service.submit(dict(BODY, text='fail'))
        failed = wait_for(lambda: store.get('sample_1'), lambda t: t['status'] == 'failed')
        assert 'inference failed' in failed['error']
        assert service.submit(dict(BODY, text='fail'))[0]['status'] == 'failed'
        assert backend.generated == ['sample_1']
    finally:
        service.close()


@pytest.fixture
def api(store):
    from video_ai.voxcpm.server import make_server
    backend = ControlledBackend()
    backend.release.set()
    service = JobService(store, BINDING, lambda: backend, session_id='test-session')
    service.start()
    wait_for(service.health, lambda h: h['status'] == 'ready')
    server = make_server(service, '127.0.0.1', 0, 'owner-secret')
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', service, backend
    server.shutdown()
    thread.join(5)
    server.server_close()
    service.close()


def http(url, path, body=None, *, raw=None, token=None):
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['X-Vox-Stop-Token'] = token
    data = raw if raw is not None else json.dumps(body).encode() if body is not None else None
    request = Request(url+path, data=data, headers=headers)
    try:
        response = urlopen(request, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        data = response.read()
        if response.headers.get_content_type() == 'application/json':
            data = json.loads(data)
        return response.status, data


def test_real_http_routes_idempotency_audio_and_no_path_control(api):
    url, service, backend = api
    assert http(url, '/health')[1]['session_id'] == 'test-session'
    assert http(url, '/voices')[1]['voices'][0]['voice_id'] == 'existing-reference'
    assert http(url, '/tts/generate', BODY)[0] == 202
    result = wait_for(lambda: http(url, '/tts/tasks/sample_1')[1], lambda t: t['status'] == 'completed')
    assert result['result']['sample_count'] == 480
    assert http(url, '/tts/generate', BODY)[0] == 200
    assert http(url, '/tts/generate', dict(BODY, text='different'))[0] == 409
    status, audio = http(url, '/tts/tasks/sample_1/audio')
    assert status == 200 and audio[:4] == b'RIFF' and len(audio) == 1004
    assert backend.generated == ['sample_1']
    assert http(url, '/tts/generate', dict(BODY, output_path='outside'))[0] == 400
    assert http(url, '/tts/tasks/missing')[0] == 404
    assert http(url, '/tts/generate', raw=b'{"seed":NaN}')[0] == 400
    assert http(url, '/tts/generate', raw=b'\xff')[0] == 400
    assert http(url, '/shutdown', {}, token='wrong')[0] == 403


def test_remote_binding_is_rejected_before_listening(store):
    from video_ai.voxcpm.server import make_server
    service = JobService(store, BINDING, lambda: ControlledBackend())
    with pytest.raises(ValueError):
        make_server(service, '0.0.0.0', 0, 'token')


def test_owner_controller_refuses_occupied_port_without_taking_ownership(api):
    from video_ai.voxcpm.process import VoxServiceProcess
    from video_ai.runtime.services import ServiceConflictError
    url, service, backend = api
    port = int(url.rsplit(':', 1)[1])
    controller = VoxServiceProcess(Path('E:/VideoAI'), service.store.directory, port=port)
    with pytest.raises(ServiceConflictError):
        controller.start(timeout=1)
    controller.stop()
    assert http(url, '/health')[0] == 200


def test_invalid_completion_receipt_fails_only_interrupted_task(store):
    from video_ai.runtime.storage_files import write_record
    task, _ = store.submit(frozen())
    store.claim(BINDING)
    path = store.output_path('sample_1')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'not a WAV')
    write_record(path.with_suffix('.json'), dict(fingerprint=task['fingerprint'], result={}))
    store.recover()
    assert store.get('sample_1')['status'] == 'failed'


def test_closed_service_never_accepts_more_work_and_load_failure_is_explicit(store):
    def broken():
        raise RuntimeError('missing local model')
    service = JobService(store, BINDING, broken)
    service.start()
    wait_for(service.health, lambda h: h['status'] == 'failed')
    assert 'missing local model' in service.health()['error']
    with pytest.raises(ApiError) as error:
        service.submit(BODY)
    assert error.value.status == 503
    service.close()


def test_lost_worker_marks_service_failed_and_rejects_submissions(store, monkeypatch):
    import sqlite3
    def unavailable(binding):
        raise sqlite3.OperationalError('database is locked')
    monkeypatch.setattr(store, 'claim', unavailable)
    service = JobService(store, BINDING, lambda: ControlledBackend())
    service.start()
    try:
        health = wait_for(service.health, lambda h: h['status'] == 'failed')
        assert 'database is locked' in health['error']
        with pytest.raises(ApiError) as error:
            service.submit(BODY)
        assert error.value.status == 503
    finally:
        service.close()


@pytest.mark.parametrize('name', ['partial', 'tasks.sqlite3', 'service.lock'])
def test_redirected_actual_files_cannot_write_outside_state(tmp_path, name):
    root = tmp_path/'runtime'
    state = root/'scratch/tts'
    state.mkdir(parents=True)
    outside = tmp_path/'outside.txt'
    outside.write_bytes(b'preserve')
    def link(path):
        try:
            path.symlink_to(outside)
        except OSError as error:
            pytest.skip(f'file symlinks unavailable: {error}')
    if name == 'partial':
        with JobStore(state, root) as current:
            path = current.output_path('sample_1').with_suffix('.partial.wav')
            path.parent.mkdir(parents=True)
            link(path)
            with pytest.raises(ValueError):
                current.temporary('sample_1')
    else:
        link(state/name)
        with pytest.raises(ValueError):
            JobStore(state, root)
    assert outside.read_bytes() == b'preserve'


def test_free_port_does_not_require_tcp_refusal_and_failed_launch_closes_log(tmp_path, monkeypatch):
    import socket
    from video_ai.voxcpm.process import VoxServiceProcess
    root = tmp_path/'runtime'
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    def delayed_refusal(*args, **kwargs):
        raise TimeoutError('Windows TCP refusal did not arrive within .5s')
    monkeypatch.setattr(socket, 'create_connection', delayed_refusal)
    owner = VoxServiceProcess(root, root/'scratch/state', port=port)
    with pytest.raises(FileNotFoundError):
        owner.start(timeout=1)  # Missing dedicated interpreter; no GPU can start.
    for path in owner.directory.glob('service-*.log'):
        path.unlink()  # Windows refuses unlink of an accidentally leaked open log handle.


def test_launcher_rejects_model_directory_before_writing_logs(tmp_path):
    from video_ai.voxcpm.process import VoxServiceProcess
    root = tmp_path/'runtime'
    target = root/'shared/models/forbidden'
    with pytest.raises(ValueError):
        VoxServiceProcess(root, target)
    assert not target.exists()
