from types import SimpleNamespace
import pytest
from video_ai.runtime import scene_revision_records as records


@pytest.mark.parametrize('depth', [0, 2, 4, 8])
def test_shared_ancestor_verified_once_per_pass(tmp_path, monkeypatch, depth):
    path = tmp_path / 'source.json'
    path.write_bytes(b'original')
    frozen = SimpleNamespace(options={'script_path': str(tmp_path / 'production/script.txt')})
    leaf = records.RevisionGuard(frozen)
    leaf.capture(path, root=tmp_path)
    root = leaf
    for _ in range(depth):
        parent = records.RevisionGuard(frozen)
        parent.ancestors = [root, root]
        root = parent
    checks = []
    original = records.verify_artifact
    def counted(*args, **kwargs):
        checks.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(records, 'verify_artifact', counted)
    root.verify_captured_bytes()
    assert len(checks) == 1
    path.write_bytes(b'modified')
    with pytest.raises(ValueError, match='captured bytes changed'):
        root.verify_captured_bytes()

def test_admission_uses_one_local_read_boundary(monkeypatch, tmp_path):
    frozen = SimpleNamespace(options={'script_path': str(tmp_path/'production/script.txt'), 'scene_revision': {}})
    path = tmp_path/'shared.json'
    path.write_bytes(b'original')
    guard = records.RevisionGuard(frozen)
    guard.capture(path, root=tmp_path)
    checks = []
    original = records.verify_artifact
    def counted(*args, **kwargs):
        checks.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(records, 'verify_artifact', counted)
    with records.revision_scope():
        records._context.get()['validated'][str(tmp_path)] = {'guard': guard}
        records.require_scene_revision(frozen)
    # One access check and one boundary check, even on the admitted fast path.
    assert len(checks) == 2

def test_structure_artifact_batch_checks_unique_bindings_and_exit(tmp_path, monkeypatch):
    path = tmp_path/'shared.json'
    path.write_bytes(b'original')
    bound = records.artifact(path, root=tmp_path)
    calls = []
    original = records.artifact
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(records, 'artifact', counted)
    with records.revision_artifact_batch():
        for _ in range(100):
            records.verify_artifact(bound, root=tmp_path)
    assert len(calls) == 2
    with pytest.raises(ValueError, match='captured bytes changed'):
        with records.revision_artifact_batch():
            records.verify_artifact(bound, root=tmp_path)
            path.write_bytes(b'modified')

@pytest.mark.parametrize('mutate', [False, True])
def test_inventory_batch_scans_unique_directory_and_rechecks_exit(tmp_path, monkeypatch, mutate):
    folder = tmp_path/'inputs'
    folder.mkdir()
    (folder/'first.json').write_text('{}')
    frozen = SimpleNamespace(options={'script_path': str(tmp_path/'production/script.txt')})
    guard = records.RevisionGuard(frozen)
    calls = []
    original = type(folder).rglob
    def counted(self, pattern, *args, **kwargs):
        if self == folder:
            calls.append(1)
        return original(self, pattern, *args, **kwargs)
    monkeypatch.setattr(type(folder), 'rglob', counted)
    def read():
        with records.revision_artifact_batch():
            for _ in range(30):
                guard.capture_directory(folder, root=tmp_path)
            if mutate:
                (folder/'added.json').write_text('{}')
    if mutate:
        with pytest.raises(ValueError, match='inventory changed'):
            read()
    else:
        read()
    assert len(calls) == 2

@pytest.mark.parametrize('checkpoint', [False, True])
def test_boundary_shares_ancestor_pass_across_registered_guards(tmp_path, monkeypatch, checkpoint):
    path = tmp_path/'shared.json'
    path.write_bytes(b'original')
    frozen = SimpleNamespace(options={'script_path': str(tmp_path/'production/script.txt')})
    leaf = records.RevisionGuard(frozen)
    leaf.capture(path, root=tmp_path)
    parents = [records.RevisionGuard(frozen) for _ in range(8)]
    for parent in parents:
        parent.ancestors = [leaf]
    checks = []
    original = records.verify_artifact
    def counted(*args, **kwargs):
        checks.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(records, 'verify_artifact', counted)
    with records.revision_read_transaction():
        for parent in parents:
            parent.verify_captured_bytes()
        assert len(checks) == 1
        if checkpoint:
            records.revision_read_checkpoint()
            assert len(checks) == 2
    assert len(checks) == (3 if checkpoint else 2)

def test_batch_reuses_common_file_capture_across_node_guards(tmp_path, monkeypatch):
    from video_ai.runtime import manifest
    path = tmp_path/'common.pcm'
    path.write_bytes(b'original')
    frozen = SimpleNamespace(options={'script_path': str(tmp_path/'production/script.txt')})
    checks = []
    original = manifest.hash_file
    def counted(*args, **kwargs):
        checks.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(manifest, 'hash_file', counted)
    with records.revision_artifact_batch():
        for _ in range(30):
            records.RevisionGuard(frozen).capture(path, root=tmp_path)
    assert len(checks) == 2
    with pytest.raises(ValueError, match='captured bytes changed'):
        with records.revision_artifact_batch():
            records.RevisionGuard(frozen).capture(path, root=tmp_path)
            path.write_bytes(b'modified')

@pytest.mark.parametrize('mutate', [False, True])
def test_raw_inventory_batch_shares_history_scan_and_detects_new_media(tmp_path, monkeypatch, mutate):
    folder = tmp_path/'history'
    folder.mkdir()
    (folder/'image.png').write_bytes(b'image')
    calls = []
    original = type(folder).rglob
    def counted(self, pattern, *args, **kwargs):
        if self == folder:
            calls.append(1)
        return original(self, pattern, *args, **kwargs)
    monkeypatch.setattr(type(folder), 'rglob', counted)
    def read():
        with records.revision_artifact_batch():
            for _ in range(30):
                assert records.revision_raw_inventory(folder, root=tmp_path) == [folder/'image.png']
            if mutate:
                (folder/'new.png').write_bytes(b'new')
    if mutate:
        with pytest.raises(ValueError, match='inventory changed'):
            read()
    else:
        read()
    assert len(calls) == 2

def test_batch_rejects_same_bytes_file_replacement(tmp_path):
    import os
    path = tmp_path/'source.json'
    path.write_bytes(b'original')
    old = path.stat()
    replacement = tmp_path/'replacement.json'
    replacement.write_bytes(b'original')
    with pytest.raises(ValueError, match='ownership changed'):
        with records.revision_artifact_batch():
            records.artifact(path, root=tmp_path)
            os.replace(replacement, path)
            os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))

def test_batch_rejects_previously_missing_empty_directory(tmp_path):
    folder = tmp_path/'missing'
    with pytest.raises(ValueError, match='ownership changed'):
        with records.revision_artifact_batch():
            assert records.revision_inventory(folder, root=tmp_path) == []
            folder.mkdir()


def test_artifact_batch_preserves_nested_dependency_observation(tmp_path):
    from video_ai.runtime._continuity_byte_guard import capture_reads
    path = tmp_path/'common.json'
    path.write_bytes(b'original')
    with records.revision_artifact_batch():
        records.artifact(path, root=tmp_path)
        with capture_reads() as captured:
            records.artifact(path, root=tmp_path)
        assert captured.finish().file_count == 1

def test_shared_guard_pass_does_not_hide_nested_capture_dependencies(tmp_path):
    from video_ai.runtime._continuity_byte_guard import capture_reads
    path = tmp_path/'dependency.json'
    path.write_bytes(b'original')
    frozen = SimpleNamespace(options={'script_path': str(tmp_path/'production/script.txt')})
    leaf = records.RevisionGuard(frozen)
    leaf.capture(path, root=tmp_path)
    class Reader:
        @records._unique_guard_pass
        def read(self):
            leaf.verify_captured_bytes()
            with capture_reads() as captured:
                leaf.verify_captured_bytes()
            assert captured.finish().file_count == 1
    Reader().read()

def test_shared_capture_reuses_original_filesystem_identity(tmp_path, monkeypatch):
    path = tmp_path/'common.pcm'
    path.write_bytes(b'original')
    frozen = SimpleNamespace(options={'script_path': str(tmp_path/'production/script.txt')})
    calls = []
    original = records.path_identity
    def counted(value):
        calls.append(1)
        return original(value)
    monkeypatch.setattr(records, 'path_identity', counted)
    with records.revision_artifact_batch():
        for _ in range(30):
            records.RevisionGuard(frozen).capture(path, root=tmp_path)
    # The admitted file proof supplies the first ownership baseline; only the
    # fresh batch-exit identity check needs another stat.
    assert len(calls) == 1

def test_shared_origin_timeline_parses_once_and_rejects_typed_change(monkeypatch):
    from unit.test_production_timeline import make_timeline
    from video_ai.runtime import _scene_revision_origins as origins
    from video_ai.planning.production_timeline import ProductionTimeline
    value = make_timeline().as_dict()
    calls = []
    original = ProductionTimeline.from_dict
    def counted(data):
        calls.append(1)
        return original(data)
    monkeypatch.setattr(ProductionTimeline, 'from_dict', counted)
    with records.revision_artifact_batch():
        first = origins.origin_timeline(value)
        for _ in range(30):
            assert origins.origin_timeline(dict(value)) is first
        with pytest.raises(ValueError):
            origins.origin_timeline(dict(value, has_bom=1))
    assert len(calls) == 2
    assert origins.origin_timeline(value) == first
    assert len(calls) == 3

def test_standalone_guard_reuses_protected_hashes_across_read_checks(tmp_path, monkeypatch):
    from video_ai.runtime import manifest, verification
    path = tmp_path/'source.json'
    path.write_bytes(b'original')
    frozen = SimpleNamespace(options={'script_path': str(tmp_path/'production/script.txt')})
    guard = records.RevisionGuard(frozen)
    guard.capture(path, root=tmp_path)
    calls = []
    original = verification._read_open_bytes
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(verification, '_read_open_bytes', counted)
    with verification.whole_input_protection():
        guard.verify_captured_bytes()
        guard.verify_captured_bytes()
    assert len(calls) == 1

@pytest.mark.parametrize('foreign_thread', [False, True])
def test_batch_context_does_not_reuse_after_close_or_on_foreign_thread(tmp_path, foreign_thread):
    from contextvars import copy_context
    from concurrent.futures import ThreadPoolExecutor
    path = tmp_path/'source.json'
    path.write_bytes(b'original')
    bound = records.artifact(path, root=tmp_path)
    with records.revision_artifact_batch():
        records.verify_artifact(bound, root=tmp_path)
        copied = copy_context()
        if foreign_thread:
            path.write_bytes(b'modified')
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    with pytest.raises(ValueError, match='captured bytes changed'):
                        executor.submit(copied.run, lambda: records.verify_artifact(bound, root=tmp_path)).result(timeout=5)
            finally:
                path.write_bytes(b'original')
    path.write_bytes(b'modified')
    with pytest.raises(ValueError, match='captured bytes changed'):
        copied.run(records.verify_artifact, bound, root=tmp_path)


def test_batch_exit_rechecks_redirected_path_even_with_identical_bytes(tmp_path, monkeypatch):
    import stat
    path = tmp_path/'source.json'
    path.write_bytes(b'original')
    original = type(path).lstat
    redirected = False
    def lstat(self):
        value = original(self)
        if self == path and redirected:
            return SimpleNamespace(st_mode=value.st_mode,
                                   st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return value
    monkeypatch.setattr(type(path), 'lstat', lstat)
    with pytest.raises(ValueError, match='redirected revision evidence'):
        with records.revision_artifact_batch():
            records.artifact(path, root=tmp_path)
            redirected = True

def test_checkpoint_inside_artifact_batch_checks_fresh_bytes_immediately(tmp_path):
    path = tmp_path/'source.json'
    path.write_bytes(b'original')
    frozen = SimpleNamespace(options={'script_path': str(tmp_path/'production/script.txt')})
    guard = records.RevisionGuard(frozen)
    guard.capture(path, root=tmp_path)
    with records.revision_artifact_batch(), records.revision_checkpoint_transaction():
        guard.verify_captured_bytes()
        path.write_bytes(b'modified')
        try:
            with pytest.raises(ValueError, match='captured bytes changed'):
                records.revision_read_checkpoint()
        finally:
            path.write_bytes(b'original')
