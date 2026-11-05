"""Reference hot paths keep lock checks and defer history scans to checkpoints."""
from types import SimpleNamespace

import pytest

from video_ai.runtime import scene_revision_records as records
from video_ai.runtime.production_state import RunLock


@pytest.mark.parametrize('store_kind', ['candidate', 'batch'])
def test_small_reference_records_do_not_rescan_source_history(runtime_run, monkeypatch, store_kind):
    from video_ai.runtime.jimeng_reference_candidates import _Records as Candidates
    from video_ai.runtime.production_reference_images import _Records as Batch
    run, _, _ = runtime_run
    path = run/'source.json'
    path.write_bytes(b'{"v":1}')
    guard = records.RevisionGuard(SimpleNamespace(options={'script_path': str(run/'production/script.txt')}))
    guard.capture(path, root=run)
    calls = []
    original = records.verify_artifact

    def counted(*a, **kw):
        calls.append(True)
        return original(*a, **kw)

    monkeypatch.setattr(records, 'verify_artifact', counted)
    with RunLock(run) as held:
        store = (Candidates if store_kind == 'candidate' else Batch)(run, held)
        store.revision_guard = guard
        with records.revision_checkpoint_transaction():
            guard.verify_captured_bytes()
            calls.clear()
            for i in range(5):
                store.save(run/f'small-{i}.json', {'v': i})
            store.image(run/'output.original', b'image output')
            assert not calls
        assert len(calls) == 1


def test_checkpoint_detects_restored_mtime_content_change(runtime_run):
    import os
    run, _, _ = runtime_run
    path = run/'source.json'
    path.write_bytes(b'{"v":1}')
    metadata = path.stat()
    guard = records.RevisionGuard(SimpleNamespace(options={'script_path': str(run/'production/script.txt')}))
    guard.capture(path, root=run)
    with pytest.raises(ValueError, match='captured bytes changed'):
        with records.revision_checkpoint_transaction():
            guard.verify_captured_bytes()
            path.write_bytes(b'{"v":2}')
            os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
            records.revision_read_checkpoint()


def test_checkpoint_refreshes_original_input_baseline():
    value = {'v': 1}
    with pytest.raises(ValueError, match='read input changed'):
        with records.revision_checkpoint_transaction():
            assert records.revision_read_matches('config', {'v': 1}, lambda: value)
            value['v'] = 2
            records.revision_read_checkpoint()


def test_checkpointed_record_still_refuses_lost_lock(runtime_run):
    import json
    from video_ai.runtime.jimeng_reference_candidates import _Records
    run, _, _ = runtime_run
    with RunLock(run) as held:
        original = held.path.read_bytes()
        with records.revision_checkpoint_transaction():
            held.path.write_text(json.dumps(dict(held.owner, token='0'*32)), encoding='utf-8')
            try:
                with pytest.raises(ValueError, match='lost held run lock'):
                    _Records(run, held).save(run/'must-not-exist.json', {})
                assert not (run/'must-not-exist.json').exists()
            finally:
                held.path.write_bytes(original)


def test_checkpointed_store_preserves_nested_dependency_capture(runtime_run):
    from video_ai.runtime._continuity_byte_guard import capture_reads
    from video_ai.runtime.jimeng_reference_candidates import _Records
    run, _, _ = runtime_run
    path = run/'captured-source.json'
    path.write_bytes(b'{}')
    guard = records.RevisionGuard(SimpleNamespace(options={'script_path': str(run/'production/script.txt')}))
    guard.capture(path, root=run)
    with RunLock(run) as held, records.revision_checkpoint_transaction():
        store = _Records(run, held)
        store.revision_guard = guard
        guard.verify_captured_bytes()
        with capture_reads() as capture:
            store.owned()
        assert capture.finish().file_count == 1


def test_closed_checkpoint_context_cannot_skip_store_source_checks(runtime_run):
    from contextvars import copy_context
    from video_ai.runtime.jimeng_reference_candidates import _Records
    run, _, _ = runtime_run
    path = run/'closed-source.json'
    path.write_bytes(b'{"v":1}')
    guard = records.RevisionGuard(SimpleNamespace(options={'script_path': str(run/'production/script.txt')}))
    guard.capture(path, root=run)
    with RunLock(run) as held:
        store = _Records(run, held)
        store.revision_guard = guard
        with records.revision_checkpoint_transaction():
            guard.verify_captured_bytes()
            copied = copy_context()
        path.write_bytes(b'{"v":2}')
        with pytest.raises(ValueError, match='captured bytes changed'):
            copied.run(store.save, run/'must-not-write.json', {})
        assert not (run/'must-not-write.json').exists()
