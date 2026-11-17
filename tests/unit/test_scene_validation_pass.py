"""Real native leases, complete captures, and narrow scene proof lifetimes."""
from contextlib import contextmanager
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from video_ai.runtime import manifest, verification
from video_ai.runtime import _continuity_byte_guard as byte
from video_ai.runtime import _protected_continuity_inputs as protected
from video_ai.runtime.scene_clip_records import SceneClipStore


def api():
    import importlib.util
    name = 'video_ai.runtime.scene_validation_pass'
    assert importlib.util.find_spec(name) is not None, 'scene validation pass is missing'
    return __import__(name, fromlist=['scene_validation_pass'])


def prepared(runtime_run):
    run, _, paths = runtime_run
    frozen = SimpleNamespace(options={'model_stamps': {}}, config=SimpleNamespace(raw={}))
    store = SceneClipStore(frozen, run, paths=paths)
    target = run/'source.bin'; target.write_bytes(b'original')
    return store, target, store.artifact(target)


def counted(store):
    calls = []
    def strict(value):
        calls.append(value)
        return store._validate_artifact_uncached(value)
    return strict, calls


def test_same_lease_once_nested_scope_and_capture_replay(runtime_run):
    core = api(); store, path, value = prepared(runtime_run); strict, calls = counted(store)
    with verification.whole_input_protection():
        manifest.hash_file(path)  # Already held; the memo may not open its own pin.
        with core.scene_validation_pass():
            assert core.validate_artifact_once(store, value, strict) == path
            with core.scene_validation_pass(), byte.capture_reads() as capture:
                assert core.validate_artifact_once(store, dict(value), strict) == path
        proof = capture.finish()
        assert proof.file_count == 1
        proof.verify()
        with pytest.raises(OSError): path.write_bytes(b'changed!')
    assert len(calls) == 1
    path.write_bytes(b'changed!')
    with pytest.raises(ValueError): proof.verify()


def test_fresh_scene_scope_flushes_before_outer_native_scope(runtime_run):
    core = api(); store, path, value = prepared(runtime_run)
    directory = path.parent/'inventory'; directory.mkdir()
    with verification.whole_input_protection(), protected.protected_read_pass():
        outer = protected._current_read_pass()
        with pytest.raises(ValueError, match='inventory'):
            with core.scene_validation_pass():
                assert protected._current_read_pass() is not outer
                core.verify_inventory_once(directory, set(), recursive=False, strict_check=lambda: None)
                (directory/'new.json').write_text('{}')
        assert protected._current_read_pass() is outer


def test_strict_marker_propagates_into_later_window(runtime_run):
    core = api(); store, path, value = prepared(runtime_run); strict, calls = counted(store)
    scans = []
    with core.scene_validation_pass(reuse=False), verification.whole_input_protection():
        manifest.hash_file(path)
        with core.scene_validation_pass():
            assert protected._current_read_pass() is None
            for _ in range(3):
                core.validate_artifact_once(store, value, strict)
                core.verify_inventory_once(path.parent, set(), recursive=True, strict_check=lambda: scans.append(1))
    assert len(calls) == len(scans) == 3


def test_without_existing_lease_and_without_window_stays_strict(runtime_run):
    core = api(); store, path, value = prepared(runtime_run); strict, calls = counted(store)
    with core.scene_validation_pass():
        for _ in range(2): core.validate_artifact_once(store, value, strict)
    assert len(calls) == 2
    with verification.writable_validation_session(path.parent), verification.whole_input_protection(), core.scene_validation_pass():
        for _ in range(2): core.validate_artifact_once(store, value, strict)
        path.write_bytes(b'original')
    assert len(calls) == 4


def test_outer_capture_miss_not_memoized(runtime_run):
    core = api(); store, path, value = prepared(runtime_run); strict, calls = counted(store)
    with verification.whole_input_protection():
        manifest.hash_file(path)
        with core.scene_validation_pass(), byte.capture_reads() as capture:
            for _ in range(2): core.validate_artifact_once(store, value, strict)
    assert len(calls) == 2
    assert capture.finish().file_count == 1


def test_local_overflow_falls_back_only_after_capture_closed(runtime_run, monkeypatch):
    core = api(); store, path, value = prepared(runtime_run); strict, calls = counted(store)
    original = byte.capture_reads
    @contextmanager
    def tiny():
        with original(maximum_files=0) as capture: yield capture
    monkeypatch.setattr(core, 'capture_reads', tiny)
    with verification.whole_input_protection():
        manifest.hash_file(path)
        with core.scene_validation_pass():
            core.validate_artifact_once(store, value, strict)
            core.validate_artifact_once(store, value, strict)
    assert len(calls) == 3  # failed memo, strict retry, memo additions disabled


def test_hit_overflow_poisoned_outer_capture_is_not_repaired(runtime_run):
    core = api(); store, path, value = prepared(runtime_run); strict, calls = counted(store)
    with verification.whole_input_protection():
        manifest.hash_file(path)
        with core.scene_validation_pass(), pytest.raises(byte.CaptureLimit):
            core.validate_artifact_once(store, value, strict)
            with byte.capture_reads(maximum_files=0) as capture:
                core.validate_artifact_once(store, value, strict)
        with pytest.raises(ValueError, match='successful scope'): capture.finish()
    assert len(calls) == 1


@pytest.mark.parametrize('binding', ['frozen', 'root', 'run_dir', 'revision_context'])
def test_store_binding_change_refused(runtime_run, binding):
    core = api(); store, path, value = prepared(runtime_run); strict, calls = counted(store)
    with verification.whole_input_protection():
        manifest.hash_file(path)
        with core.scene_validation_pass(), pytest.raises(ValueError, match='binding'):
            core.validate_artifact_once(store, value, strict)
            setattr(store, binding, object())
            core.validate_artifact_once(store, value, strict)
    assert len(calls) == 1


def test_copied_thread_and_expired_scope_do_not_reuse(runtime_run):
    core = api(); store, path, value = prepared(runtime_run); strict, calls = counted(store)
    with verification.whole_input_protection():
        manifest.hash_file(path)
        with core.scene_validation_pass():
            core.validate_artifact_once(store, value, strict)
            copied = copy_context(); late = copy_context()
            with ThreadPoolExecutor(max_workers=1) as pool:
                assert pool.submit(copied.run, core.validate_artifact_once, store, value, strict).result() == path
        assert late.run(core.validate_artifact_once, store, value, strict) == path
    assert len(calls) == 3


def test_auxiliary_mutable_dependency_rechecked_on_hit(runtime_run):
    core = api(); store, path, value = prepared(runtime_run)
    auxiliary = path.parent/'mutable.bin'; auxiliary.write_bytes(b'original')
    def strict(value):
        manifest.hash_file(auxiliary)
        return store._validate_artifact_uncached(value)
    with verification.writable_validation_session(auxiliary.parent), verification.whole_input_protection():
        # Explicit pre-existing protection of the main file only, not the auxiliary.
        from unit.test_protected_continuity_inputs import record
        protected.prepare_continuity_inputs([record(path)], immutable_roots=[path])
        with core.scene_validation_pass(), pytest.raises(ValueError, match='proof changed'):
            core.validate_artifact_once(store, value, strict)
            stamp = auxiliary.stat(); auxiliary.write_bytes(b'changed!')
            import os
            os.utime(auxiliary, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            core.validate_artifact_once(store, value, strict)


@pytest.mark.parametrize('invalidator', ['checkpoint', 'writer'])
def test_invalidated_scope_never_restarts_memo(runtime_run, invalidator):
    core = api(); store, path, value = prepared(runtime_run); strict, calls = counted(store)
    with verification.whole_input_protection():
        manifest.hash_file(path)
        with core.scene_validation_pass():
            core.validate_artifact_once(store, value, strict)
            if invalidator == 'checkpoint': protected.invalidate_protected_read_pass()
            else:
                with verification.writable_validation_session(store.run_dir): pass
            for _ in range(2): core.validate_artifact_once(store, value, strict)
    assert len(calls) == 3


@pytest.mark.parametrize('capacity', ['_MAX_ARTIFACTS', '_MAX_EDGES'])
def test_budget_exhaustion_keeps_strict_path(runtime_run, monkeypatch, capacity):
    core = api(); store, path, value = prepared(runtime_run); strict, calls = counted(store)
    monkeypatch.setattr(core, capacity, 0)
    with verification.whole_input_protection():
        manifest.hash_file(path)
        with core.scene_validation_pass():
            for _ in range(2): core.validate_artifact_once(store, value, strict)
    assert len(calls) == 2


def test_rebinding_identity_and_implementation_refused(runtime_run):
    core = api(); store, path, value = prepared(runtime_run); strict, calls = counted(store)
    with verification.whole_input_protection():
        manifest.hash_file(path)
        for changed in ('identity', 'implementation'):
            with core.scene_validation_pass(), pytest.raises(ValueError, match='binding'):
                core.validate_artifact_once(store, value, strict)
                core.validate_artifact_once(store, dict(value, sha256='0'*64) if changed == 'identity' else value,
                                            strict if changed == 'identity' else store._validate_artifact_uncached)


def test_scope_does_not_share_stores_or_revision_origins(runtime_run):
    core = api(); store, path, value = prepared(runtime_run); strict, calls = counted(store)
    other = SceneClipStore(store.frozen, store.run_dir); second, second_calls = counted(other)
    with verification.whole_input_protection():
        manifest.hash_file(path)
        with core.scene_validation_pass():
            core.validate_artifact_once(store, value, strict)
            core.validate_artifact_once(other, value, second)
        store.revision_context = {'guard': object()}
        with core.scene_validation_pass():
            for _ in range(2): core.validate_artifact_once(store, value, strict)
    assert len(calls) == 3 and len(second_calls) == 1


@pytest.mark.parametrize('value', [None, {}, {'path': []}, dict(path='bad', bytes=True, sha256='x')])
def test_malformed_input_keeps_original_exception(runtime_run, value):
    core = api(); store, path, _ = prepared(runtime_run)
    with pytest.raises(Exception) as original: store._validate_artifact_uncached(value)
    with verification.whole_input_protection(), core.scene_validation_pass():
        with pytest.raises(type(original.value)) as actual: store.validate_artifact(value)
    assert str(actual.value) == str(original.value)


def test_outer_capture_overflow_on_miss_propagates(runtime_run):
    core = api(); store, path, value = prepared(runtime_run); strict, calls = counted(store)
    with verification.whole_input_protection():
        manifest.hash_file(path)
        with core.scene_validation_pass(), byte.capture_reads(maximum_files=0) as capture:
            with pytest.raises(byte.CaptureLimit): core.validate_artifact_once(store, value, strict)
        with pytest.raises(ValueError): capture.finish()
    assert len(calls) == 1


def test_file_error_on_hit_propagates_and_invalidates_memo(runtime_run, monkeypatch):
    core = api(); store, path, value = prepared(runtime_run); strict, calls = counted(store)
    verify = byte.ByteGuard.verify
    with verification.whole_input_protection():
        manifest.hash_file(path)
        with core.scene_validation_pass():
            core.validate_artifact_once(store, value, strict)
            def missing(self): raise FileNotFoundError('lease vanished')
            monkeypatch.setattr(byte.ByteGuard, 'verify', missing)
            with pytest.raises(FileNotFoundError, match='lease vanished'):
                core.validate_artifact_once(store, value, strict)
            monkeypatch.setattr(byte.ByteGuard, 'verify', verify)
            core.validate_artifact_once(store, value, strict)
    assert len(calls) == 2


def test_direct_and_recursive_inventory_are_distinct_and_conflicts_refuse(runtime_run):
    core = api(); _, path, _ = prepared(runtime_run)
    nested = path.parent/'nested'; nested.mkdir(); leaf = nested/'child.json'; leaf.write_text('{}')
    with verification.whole_input_protection(), core.scene_validation_pass():
        core.verify_inventory_once(path.parent, set(), recursive=False, strict_check=lambda: None)
        core.verify_inventory_once(path.parent, {str(leaf)}, recursive=True, strict_check=lambda: None)
        with pytest.raises(ValueError):
            core.verify_inventory_once(path.parent, set(), recursive=True, strict_check=lambda: None)


def test_inventory_mismatch_preserves_original_refusal(runtime_run):
    from video_ai.runtime.production_state import ProductionRefused
    core = api(); _, path, _ = prepared(runtime_run)
    (path.parent/'unexpected.json').write_text('{}')
    def strict(): raise ProductionRefused('parent observation inventory changed before send')
    with verification.whole_input_protection(), core.scene_validation_pass():
        with pytest.raises(ProductionRefused, match='^parent observation inventory changed before send$'):
            core.verify_inventory_once(path.parent, set(), recursive=False, strict_check=strict)


def test_proof_deadline_keeps_original_exception(runtime_run, monkeypatch):
    core = api(); store, path, value = prepared(runtime_run); strict, _ = counted(store)
    with verification.whole_input_protection():
        manifest.hash_file(path)
        with core.scene_validation_pass():
            core.validate_artifact_once(store, value, strict)
            def expired(self): raise ValueError('byte proof verification interval exceeded')
            monkeypatch.setattr(byte.ByteGuard, 'verify', expired)
            with pytest.raises(ValueError) as error: core.validate_artifact_once(store, value, strict)
            assert type(error.value) is ValueError
