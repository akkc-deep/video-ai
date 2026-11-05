"""Actual signed submit bodies and durable reference transaction recovery."""
from copy import deepcopy
from pathlib import Path

import pytest

from reference_helpers import reference_setup, generate_reference


@pytest.fixture
def setup(runtime_run, tmp_path, monkeypatch):
    return reference_setup(runtime_run, tmp_path, monkeypatch)


def test_actual_submit_contains_fixed_baseline_and_shared_prompt(setup):
    from video_ai.runtime.reference_image_records import verify_reference_provenance
    s = setup; manifest = generate_reference(s)
    assert len(s['state']['submits']) == s['frozen'].config.image_generation.candidates_per_scene
    for payload in s['state']['submits']:
        assert len(payload['image_urls']) == 1
        assert s['references'][0]['sha256']+'.original?' in payload['image_urls'][0]
        assert payload['prompt'].startswith(s['scene']['image_prompt']+'\nVISUAL_BIBLE_JSON\n')
    provenance = verify_reference_provenance(s['frozen'], s['scene'], s['bible'], s['plan'])
    assert provenance['references'] == s['references']
    before = deepcopy(s['state']); presigns = s['storage'].presigns
    assert generate_reference(s) == manifest
    assert s['state'] == before and s['storage'].presigns == presigns
    records = '\n'.join(p.read_text(encoding='utf-8') for p in s['run'].rglob('*.json'))
    assert all(secret not in records for secret in ('signature=private', 'fixture-ak', 'fixture-sk', 'Authorization'))


def test_submit_unknown_never_creates_second_paid_request(setup):
    s = setup; s['state']['failure'] = 'submit'
    with pytest.raises(TimeoutError): generate_reference(s)
    s['state']['failure'] = None
    with pytest.raises(ValueError, match='submit_unknown'): generate_reference(s)
    assert len(s['state']['submits']) == 1
    assert s['storage'].presigns == 1


@pytest.mark.parametrize('failure', ['query', 'download'])
def test_original_task_resumes_without_refreshing_url_or_resubmitting(setup, failure):
    s = setup; s['state']['failure'] = failure
    with pytest.raises(TimeoutError): generate_reference(s)
    first_task = s['state']['queries'][0]
    presigns = s['storage'].presigns
    s['state']['failure'] = None
    generate_reference(s)
    assert s['state']['queries'][1] == first_task
    assert s['storage'].presigns == presigns  # both accepted IDs survive; neither needs new input URLs
    assert len(s['state']['submits']) == 2


@pytest.mark.parametrize('change', ['source', 'receipt', 'uses', 'count', 'bytes', 'prompt', 'ttl'])
def test_invalid_local_reference_preconditions_make_zero_submissions(setup, change):
    s = setup
    if change == 'source':
        Path(s['accepted'][0]['selections'][0]['path']).write_bytes(b'changed original')
    elif change == 'receipt':
        path = s['run']/'production/reference-storage'/s['references'][0]['sha256']/'object.json'
        path.unlink()
    elif change == 'uses': s['references'][0]['uses'].pop()
    elif change == 'count': s['references'] *= 2
    elif change == 'bytes': s['references'][0]['bytes'] += 1
    elif change == 'prompt': s['scene'] = dict(s['scene'], image_prompt='changed')
    else: s['storage'].offset = -3500
    with pytest.raises((ValueError, OSError)): generate_reference(s)
    assert not s['state']['submits']
    assert not list((s['run']/'production/jimeng'/s['scene']['scene_id']).rglob('intent.json'))


def test_provenance_tampering_is_rejected_by_legacy_dispatch(setup):
    from image_selection_helpers import save
    from video_ai.config import read_json
    from video_ai.runtime.image_selection_records import _candidates
    s = setup; generate_reference(s)
    path = s['run']/'production/reference-images'/s['scene']['scene_id']/'provenance.json'
    value = read_json(path); value['references'][0]['object']['etag'] = 'tampered'
    save(path, value)
    with pytest.raises(ValueError):
        _candidates(s['frozen'], s['scene'], s['run']/'production/jimeng'/s['scene']['scene_id']/'candidates.json')


def test_source_change_after_intent_prevents_actual_submit(setup, monkeypatch):
    import video_ai.runtime.jimeng_reference_candidates as module
    s = setup
    def change(point, identity):
        if point == 'intent': Path(s['accepted'][0]['selections'][0]['path']).write_bytes(b'changed')
    monkeypatch.setattr(module, 'boundary', change)
    # A directly invoked generator now also holds native deny-write handles:
    # either mutation is refused by Windows, or the source checkpoint refuses
    # the changed bytes. Both paths must leave the paid transport untouched.
    with pytest.raises((ValueError, PermissionError)): generate_reference(s)
    assert not s['state']['submits']


def test_jimeng_ownership_guard_blocks_send_after_dns(monkeypatch):
    from http.client import HTTPSConnection
    from threading import Thread, Event
    from video_ai.adapters.jimeng import JimengClient
    from video_ai.adapters.common import AdapterError
    from video_ai.jimeng_config import parse_image_generation
    from unit.test_jimeng_config import image_settings
    ready, release = Event(), Event(); transmitted = []; owned = [True]; errors = []
    class Socket:
        def sendall(self, data): transmitted.append(data)
        def close(self): pass
        def shutdown(self, *a): pass
    def connect(connection):
        ready.set(); release.wait(2); connection.sock = Socket()
    monkeypatch.setattr(HTTPSConnection, 'connect', connect)
    monkeypatch.setenv('TEST_VOLC_AK', 'fixture-ak'); monkeypatch.setenv('TEST_VOLC_SK', 'fixture-sk')
    def ownership():
        if not owned[0]: raise ValueError('lost held lock')
    client = JimengClient(parse_image_generation(image_settings(), 'fixture'), ownership_check=ownership)
    def send():
        try: client.submit('bird', image_urls=['https://store.example/object?signature=private'])
        except AdapterError as exc: errors.append(exc)
    worker = Thread(target=send); worker.start()
    try:
        assert ready.wait(1)
        owned[0] = False
    finally: release.set()
    worker.join(2)
    assert not worker.is_alive()
    assert not transmitted and len(errors) == 1


def test_reference_prompt_length_is_advisory_and_complete_prompt_replays(runtime_run, tmp_path, monkeypatch):
    from video_ai.runtime.reference_image_records import verify_reference_provenance
    s = reference_setup(runtime_run, tmp_path, monkeypatch, capability_changes=dict(max_prompt_bytes=1))
    result = generate_reference(s)
    assert len(result['candidates']) == 2
    assert len(s['state']['submits']) == 2
    for payload in s['state']['submits']:
        assert payload['prompt'].startswith(s['scene']['image_prompt']+'\nVISUAL_')
        assert '白鸟' in payload['prompt']
        assert len(payload['prompt'].encode('utf-8')) > 1
    assert verify_reference_provenance(s['frozen'], s['scene'], s['bible'], s['plan'])
    before = deepcopy(s['state'])
    assert generate_reference(s) == result
    assert s['state'] == before


@pytest.mark.parametrize('limits', [dict(max_image_bytes=1),
                                   dict(max_width=100), dict(formats=['jpeg'])])
def test_verified_capability_limits_are_checked_before_intent(runtime_run, tmp_path, monkeypatch, limits):
    s = reference_setup(runtime_run, tmp_path, monkeypatch, capability_changes=limits)
    with pytest.raises(ValueError, match='capability'): generate_reference(s)
    assert not s['state']['submits'] and s['storage'].presigns == 0


@pytest.mark.parametrize('point', ['accepted', 'downloaded', 'provenance'])
def test_durable_boundary_interruptions_resume_original_requests(setup, monkeypatch, point):
    import video_ai.runtime.jimeng_reference_candidates as module
    s = setup; fired = []
    def interrupt(current, identity):
        if current == point and not fired:
            fired.append(identity); raise KeyboardInterrupt()
    monkeypatch.setattr(module, 'boundary', interrupt)
    with pytest.raises(KeyboardInterrupt): generate_reference(s)
    monkeypatch.setattr(module, 'boundary', lambda *a: None)
    result = generate_reference(s)
    assert len(result['candidates']) == 2
    assert len(s['state']['submits']) == 2
    assert s['state']['downloads'] == 2


def test_expired_unsent_url_can_be_resigned_on_resume(setup):
    s = setup; s['storage'].offset = -3500
    with pytest.raises(ValueError, match='TTL'): generate_reference(s)
    s['storage'].offset = 0
    assert len(generate_reference(s)['candidates']) == 2
    assert len(s['state']['submits']) == 2


def test_submit_ttl_guard_blocks_actual_send_after_dns_consumes_budget(setup, monkeypatch):
    from datetime import datetime, timedelta
    from http.client import HTTPSConnection
    from video_ai.adapters.external_https import ExternalHttpsClient
    from video_ai.adapters.common import AdapterError
    import video_ai.runtime.jimeng_reference_candidates as module
    s = setup; transmitted = []
    class Clock(datetime):
        offset = 0
        @classmethod
        def now(cls, tz=None): return datetime.now(tz)+timedelta(seconds=cls.offset)
    class Socket:
        def sendall(self, data): transmitted.append(data)
        def close(self): pass
        def shutdown(self, *a): pass
    def connect(connection):
        Clock.offset = 3500
        connection.sock = Socket()
    monkeypatch.setattr(module, 'datetime', Clock)
    monkeypatch.setattr(HTTPSConnection, 'connect', connect)
    s['client'].http = ExternalHttpsClient()
    with pytest.raises(AdapterError): generate_reference(s)
    assert not transmitted


def test_original_task_query_recovery_does_not_require_live_input_urls(setup, monkeypatch):
    from datetime import datetime, timedelta
    import video_ai.runtime.jimeng_reference_candidates as module
    s = setup; generate_reference(s)
    result = s['run']/'production/jimeng'/s['scene']['scene_id']/'request_01/result.json'
    result.unlink()
    result.parent.parent.joinpath('candidates.json').unlink()
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return datetime.now(tz)+timedelta(seconds=4000)
    monkeypatch.setattr(module, 'datetime', Clock)
    assert len(generate_reference(s)['candidates']) == 2
    assert len(s['state']['submits']) == 2
    assert s['state']['queries'][-1] == 'task_1'


@pytest.mark.parametrize('change', ['submit_body', 'url_sha'])
def test_single_intent_hash_tampering_is_rejected(setup, change):
    from image_selection_helpers import save
    from video_ai.config import read_json
    from video_ai.runtime.image_selection_records import _candidates
    s = setup; generate_reference(s)
    folder = s['run']/'production/jimeng'/s['scene']['scene_id']
    path = folder/'request_01/intent.json'; intent = read_json(path)
    if change == 'submit_body': intent['submit_body_sha256'] = 'f'*64
    else: intent['reference_urls'][0]['sha256'] = 'f'*64
    save(path, intent)
    with pytest.raises(ValueError): _candidates(s['frozen'], s['scene'], folder/'candidates.json')


def test_completed_reference_recovery_shares_frozen_loads(setup, monkeypatch):
    import video_ai.runtime.image_selection_records as images
    import video_ai.runtime.reference_settings as settings
    s = setup
    original = generate_reference(s)
    calls = []
    load = images.load_frozen_inputs

    def counted(run):
        calls.append(run)
        return load(run)

    monkeypatch.setattr(images, 'load_frozen_inputs', counted)
    monkeypatch.setattr(settings, 'load_frozen_inputs', counted)
    before = deepcopy(s['state'])
    assert generate_reference(s) == original
    assert s['state'] == before
    assert len(calls) == 2  # admission and full exit check, regardless of nested readers


@pytest.mark.parametrize('change', ['source', 'settings', 'request'])
def test_request_snapshot_change_after_dns_blocks_actual_send(setup, monkeypatch, change):
    from http.client import HTTPSConnection
    from video_ai.adapters.external_https import ExternalHttpsClient
    from video_ai.adapters.common import AdapterError
    s = setup
    sent = []

    class Socket:
        def sendall(self, data): sent.append(data)
        def close(self): pass
        def shutdown(self, *a): pass

    def connect(connection):
        if change == 'source':
            path = Path(s['accepted'][0]['selections'][0]['path'])
        elif change == 'settings':
            path = s['run']/'production/reference-images/settings.json'
        else:
            path = s['run']/'production/jimeng'/s['scene']['scene_id']/'request_01/request.json'
        import os
        metadata = path.stat()
        raw = path.read_bytes()
        path.write_bytes(bytes([raw[0] ^ 1])+raw[1:])
        os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        connection.sock = Socket()

    monkeypatch.setattr(HTTPSConnection, 'connect', connect)
    s['client'].http = ExternalHttpsClient()
    with pytest.raises((AdapterError, ValueError)):
        generate_reference(s)
    assert not sent
    assert not list((s['run']/'production/jimeng'/s['scene']['scene_id']).rglob('accepted.json'))


@pytest.mark.parametrize('event', ['intent', 'accepted'])
def test_full_history_checkpoint_blocks_new_submit_and_retains_paid_result(setup, monkeypatch, event):
    from types import SimpleNamespace
    import video_ai.runtime.jimeng_reference_candidates as module
    from video_ai.runtime.scene_revision_records import RevisionGuard
    s = setup
    history = s['run']/'history-source.json'
    history.write_bytes(b'{"v":1}')
    guard = RevisionGuard(SimpleNamespace(options={'script_path': str(s['run']/'production/script.txt')}))
    guard.capture(history, root=s['run'])
    original_request = module._request

    def request(store, *a, **kw):
        store.revision_guard = guard
        guard.verify_captured_bytes()
        return original_request(store, *a, **kw)

    def change(point, identity):
        if point == event:
            history.write_bytes(b'{"v":2}')

    monkeypatch.setattr(module, '_request', request)
    monkeypatch.setattr(module, 'boundary', change)
    with pytest.raises(ValueError, match='captured bytes changed'):
        generate_reference(s)
    assert len(s['state']['submits']) == (0 if event == 'intent' else 1)
    folder = s['run']/'production/jimeng'/s['scene']['scene_id']
    assert not (folder/'candidates.json').exists()
    if event == 'accepted':
        from video_ai.config import read_json
        assert read_json(folder/'request_01/accepted.json')['task_id'] == 'task_1'
        assert read_json(folder/'request_01/result.json')['task_id'] == 'task_1'
