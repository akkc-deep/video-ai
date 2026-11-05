"""Local repeated-work counters with actual MIME and path results."""
from unit.test_selection_email import email_batch, build


def test_final_mail_page_is_encoded_only_once(email_batch, monkeypatch):
    from video_ai.adapters import selection_email as email
    calls = []
    original = email._encode
    def counted(*a, **kw):
        key = (tuple((e['scene']['scene_id'], e['attachment']['sha256']) for e in a[2]),
               kw['part'], kw['total'])
        calls.append(key)
        return original(*a, **kw)
    monkeypatch.setattr(email, '_encode', counted)
    result = build(*email_batch)
    assert len(result) == 1
    assert len(calls) == len(set(calls))


def test_cached_mail_bytes_are_hashed_once_per_path(email_batch, monkeypatch):
    from pathlib import Path
    from video_ai.adapters import selection_email as email
    calls = []
    raw = Path(email_batch[1]['images'][0]['path']).read_bytes()
    original = email.hashlib.sha256
    def counted(data=b''):
        if data == raw: calls.append(True)
        return original(data)
    monkeypatch.setattr(email.hashlib, 'sha256', counted)
    assert build(*email_batch)
    assert len(calls) == len(email_batch[1]['images'])


def test_batch_directory_loads_run_once(monkeypatch, runtime_run):
    from video_ai.runtime import image_selection_records as records
    calls = []
    run = runtime_run[0]
    monkeypatch.setattr(records, '_run', lambda _: calls.append(True) or run)
    assert records.batch_directory(None, 'image_batch_0001') == run/'production/image-selection/image_batch_0001'
    assert len(calls) == 1


def test_smtp_session_connects_once_and_keeps_each_data_intent(monkeypatch):
    from unit.test_selection_email import smtp
    monkeypatch.setenv('VIDEO_AI_SMTP_AUTH_CODE', 'secret-password')
    sender, events, contexts = smtp()
    assert hasattr(sender, 'session')
    with sender.session():
        for _ in range(2):
            assert sender.send(b'mime', before_data=lambda: events.append('intent')) == {'smtp_code': 250}
        assert events.count('close') == 0
    assert len(contexts) == 1
    assert events == ['ehlo', 'login', 'mail', 'rcpt', 'intent', 'data',
                      'mail', 'rcpt', 'intent', 'data', 'close']


def test_smtp_unknown_session_never_reuses_connection(monkeypatch):
    import pytest
    from unit.test_selection_email import smtp
    from video_ai.adapters.selection_email import EmailDeliveryUnknown
    monkeypatch.setenv('VIDEO_AI_SMTP_AUTH_CODE', 'secret-password')
    sender, events, contexts = smtp(failure='data')
    assert hasattr(sender, 'session')
    with sender.session():
        with pytest.raises(EmailDeliveryUnknown): sender.send(b'mime', before_data=lambda: None)
    assert len(contexts) == 1 and events.count('data') == 1 and events.count('close') == 1


def test_interrupted_receipt_cannot_return_connection_to_smtp_session(monkeypatch):
    import pytest
    from unit.test_selection_email import smtp
    from video_ai.adapters import selection_email as email
    monkeypatch.setenv('VIDEO_AI_SMTP_AUTH_CODE', 'secret-password')
    queue = email.queue.Queue
    class InterruptAccepted(queue):
        def get(self, *a, **kw):
            value = super().get(*a, **kw)
            if value[0] == 'accepted': raise KeyboardInterrupt()
            return value
    monkeypatch.setattr(email.queue, 'Queue', InterruptAccepted)
    sender, events, _ = smtp()
    with sender.session():
        with pytest.raises(KeyboardInterrupt): sender.send(b'mime', before_data=lambda: None)
        with pytest.raises(BaseException) as rejected:
            sender.send(b'mime', before_data=lambda: None)
        assert isinstance(rejected.value, email.EmailPreconditionError)
    assert events.count('data') == 1


def test_ordinary_candidate_and_selection_records_defer_history_with_checkpoints(runtime_run, monkeypatch):
    from types import SimpleNamespace
    from video_ai.runtime import scene_revision_records as revisions
    from video_ai.runtime.jimeng_candidates import _Records as Candidates
    from video_ai.runtime.production_image_selection import _Records as Selection
    from video_ai.runtime.production_state import RunLock
    run = runtime_run[0]
    source = run/'history.json'; source.write_bytes(b'{}')
    guard = revisions.RevisionGuard(SimpleNamespace(options={'script_path': str(run/'production/script.txt')}))
    guard.capture(source, root=run)
    calls = []
    check = guard.verify_captured_bytes
    def counted(*a, **kw): calls.append(True); return check(*a, **kw)
    monkeypatch.setattr(guard, 'verify_captured_bytes', counted)
    with RunLock(run) as held, revisions.revision_checkpoint_transaction():
        guard.verify_captured_bytes(); calls.clear()
        for cls in (Candidates, Selection):
            store = cls(run, held); store.revision_guard = guard
            store.save(run/(cls.__module__.split('.')[-1]+'.json'), {'v': 1})
        assert not calls


def test_loading_accepted_batch_rebuilds_candidates_once(runtime_run, tmp_path, monkeypatch):
    from image_selection_helpers import setup_selection
    from unit.test_image_selection_records import batch, accept_batch
    from video_ai.runtime import image_selection_records as records
    s = setup_selection(runtime_run, tmp_path)
    expected = accept_batch(s, batch(s), accepted=[])
    builds = []
    original = records._expected_batch
    def counted(*a, **kw): builds.append(True); return original(*a, **kw)
    monkeypatch.setattr(records, '_expected_batch', counted)
    assert records.load_accepted_batches(s['frozen'], s['units'], s['timeline']) == [expected]
    assert len(builds) == 1


def test_building_selection_batch_loads_frozen_inputs_at_two_boundaries(runtime_run, tmp_path, monkeypatch):
    from image_selection_helpers import setup_selection, candidate_manifest
    from video_ai.runtime import image_selection_records as records
    s = setup_selection(runtime_run, tmp_path)
    manifest = candidate_manifest(s, 'scene_0001')
    calls = []
    original = records.load_frozen_inputs
    def counted(*a, **kw): calls.append(True); return original(*a, **kw)
    monkeypatch.setattr(records, 'load_frozen_inputs', counted)
    result = records.build_batch(s['frozen'], s['units'], s['timeline'], [manifest], batch_index=1)
    assert result['scenes'][0]['scene_id'] == 'scene_0001'
    assert len(calls) == 2
