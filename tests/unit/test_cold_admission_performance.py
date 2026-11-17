"""Read-proof cost must follow unique dependencies, not capture nesting."""
import os
from types import SimpleNamespace

import pytest

from video_ai.runtime import _continuity_byte_guard as guards
from video_ai.runtime import _protected_continuity_inputs as native
from video_ai.runtime import manifest, scene_revision_records as revisions, verification


def proof(tmp_path):
    path = tmp_path / 'input.json'
    path.write_bytes(b'{"value":1}')
    with guards.capture_reads() as capture:
        manifest.hash_file(path)
        guards.observe_inventory(tmp_path, 'json_direct', [path])
        guards.observe_absence(tmp_path / 'missing.json')
    return capture.finish()


def test_stable_bytes_observes_protected_identity_once(tmp_path, monkeypatch):
    path = tmp_path / 'input.json'
    path.write_bytes(b'{"value":1}')
    observed = []
    original = guards.observe_file

    def observe(value):
        observed.append(value.path)
        return original(value)

    monkeypatch.setattr(guards, 'observe_file', observe)
    with verification.whole_input_protection():
        assert revisions.stable_bytes(path, root=tmp_path) == b'{"value":1}'
    assert observed == [str(path)]


def test_hash_file_observes_protected_text_once(tmp_path, monkeypatch):
    path = tmp_path / 'input.json'
    path.write_bytes(b'{"value":1}')
    observed = []
    original = guards.observe_file

    def observe(value):
        observed.append(value.path)
        return original(value)

    monkeypatch.setattr(guards, 'observe_file', observe)
    with verification.whole_input_protection():
        manifest.hash_file(path)
    assert observed == [str(path)]


def test_progress_scan_shares_one_read_transaction_and_artifact_batch(tmp_path):
    from video_ai.runtime.scene_clip_records import collect_progress
    path = tmp_path / 'source.json'
    path.write_bytes(b'original')
    context = dict(store=SimpleNamespace(run_dir=tmp_path), inputs={},
                   plan={'scenes': [{'scene_id': 'a'}, {'scene_id': 'b'}]})
    periods = []

    def read(current, scene):
        periods.append((revisions._read_transaction.get(), revisions._artifact_batch.get()))
        revisions.artifact(path, root=tmp_path)
        return dict(scene_id=scene['scene_id']), {}

    collect_progress(context, scene_reader=read)
    assert all(transaction is not None and batch is not None for transaction, batch in periods)
    assert periods[0][0] is periods[1][0] and periods[0][1] is periods[1][1]
    assert not periods[0][0]['active'] and not periods[0][1]['active']


@pytest.mark.skipif(os.name != 'nt', reason='real Windows native sharing')
def test_new_native_entries_share_parent_qualification_in_one_pass(tmp_path, monkeypatch):
    paths = [tmp_path / f'input-{i}.json' for i in range(4)]
    for path in paths:
        path.write_bytes(b'{"value":1}')
    checks = []
    original = native._Directory.verify

    def verify(self, **kwargs):
        checks.append(self.path)
        return original(self, **kwargs)

    with verification.whole_input_protection():
        # The first native entry establishes the common directory chain.
        with native.protected_read_pass():
            manifest.hash_file(paths[0])
            manifest.hash_file(paths[0])
            monkeypatch.setattr(native._Directory, 'verify', verify)
            for path in paths[1:]:
                manifest.hash_file(path)
                manifest.hash_file(path)
            assert not checks
        assert len(checks) == 2 * len(paths[0].parents)


@pytest.mark.skipif(os.name != 'nt', reason='real Windows native sharing')
def test_revision_ownership_reuses_live_read_pass_proof(tmp_path, monkeypatch):
    admitted = proof(tmp_path)
    path = tmp_path / 'input.json'
    expected = revisions.path_identity(path)
    with verification.whole_input_protection():
        native.prepare_continuity_inputs(admitted.files, immutable_roots=(tmp_path,))
        with revisions.revision_read_transaction():
            admitted.verify()
            with monkeypatch.context() as patch:
                def forbidden(self, *args, **kwargs):
                    raise AssertionError('ownership repeated a verified native file stat')
                patch.setattr(type(path), 'stat', forbidden)
                for _ in range(10):
                    assert revisions.path_identity(path) == expected


def test_captured_input_comparison_replays_one_loader_proof(tmp_path):
    path = tmp_path / 'input.json'
    path.write_bytes(b'{"value":1}')
    calls = []

    def read():
        calls.append(True)
        return revisions._json(path, root=tmp_path)

    with verification.whole_input_protection(), revisions.revision_read_transaction():
        for _ in range(4):
            with guards.capture_reads() as capture:
                assert revisions.revision_read_matches('same', {'value': 1}, read)
            assert {row.path for row in capture.finish().files} == {str(path)}
        assert len(calls) == 1
    assert len(calls) == 2  # A fresh complete loader runs at the boundary.


@pytest.mark.skipif(os.name != 'nt', reason='real Windows native sharing')
def test_immutable_guard_reuses_complete_qualified_closure(tmp_path, monkeypatch):
    admitted = proof(tmp_path)
    checks = []
    original = native._Protection.verify_record

    def verify(self, row):
        checks.append(row.path)
        return original(self, row)

    with verification.whole_input_protection():
        native.prepare_continuity_inputs(admitted.files, immutable_roots=(tmp_path,))
        monkeypatch.setattr(native._Protection, 'verify_record', verify)
        with revisions.revision_read_transaction():
            for _ in range(5):
                admitted.verify()
            assert len(checks) == 1


@pytest.mark.skipif(os.name != 'nt', reason='real Windows native sharing')
def test_qualified_file_reuse_does_not_rebuild_ancestor_paths(tmp_path, monkeypatch):
    admitted = proof(tmp_path)
    row = admitted.files[0]
    with verification.whole_input_protection(), revisions.revision_read_transaction():
        native.prepare_continuity_inputs(admitted.files, immutable_roots=(tmp_path,))
        assert native.verify_protected_continuity_file(row)
        with monkeypatch.context() as patch:
            def forbidden(self):
                raise AssertionError('qualified native record rebuilt parent chain')
            patch.setattr(type(tmp_path), 'parents', property(forbidden))
            for _ in range(5):
                assert native.verify_protected_continuity_file(row, prepare_existing=True)


@pytest.mark.skipif(os.name != 'nt', reason='real Windows native sharing')
def test_semantic_memo_miss_does_not_rewalk_admitted_proof(tmp_path, monkeypatch):
    admitted = proof(tmp_path)
    with verification.whole_input_protection(), revisions.revision_read_transaction():
        native.prepare_continuity_inputs(admitted.files, immutable_roots=(tmp_path,))
        with revisions.revision_artifact_batch():
            def read():
                revisions.replay_revision_reads(admitted)
                return {'value': 1}

            with monkeypatch.context() as patch:
                def forbidden(*args, **kwargs):
                    raise AssertionError('successful memo read redundantly walked its complete proof')
                patch.setattr(native, 'verify_protected_continuity_file', forbidden)
                assert revisions.revision_cached_read('qualified-fixture', 'key', read) == {'value': 1}
            # First actual proof verification can anchor an existing lease;
            # cache hits and the batch/read boundaries still verify all rows.
            assert revisions.revision_cached_read('qualified-fixture', 'key', read) == {'value': 1}


@pytest.mark.skipif(os.name != 'nt', reason='real Windows native sharing')
def test_guard_memo_never_reuses_unleased_owned_files(tmp_path):
    admitted = proof(tmp_path)
    path = tmp_path / 'input.json'
    stamp = path.stat()
    with verification.whole_input_protection(), verification.writable_validation_session(tmp_path):
        with revisions.revision_read_transaction():
            admitted.verify()
            path.write_bytes(b'{"value":2}')
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            with pytest.raises(ValueError, match='byte proof file changed'):
                admitted.verify()


def test_trusted_replay_only_merges_existing_proof_rows(tmp_path, monkeypatch):
    admitted = proof(tmp_path)
    with monkeypatch.context() as patch:
        def forbidden(*args, **kwargs):
            raise AssertionError('replay repeated filesystem path qualification')
        patch.setattr(guards, '_safe', forbidden)
        with guards.capture_reads() as outer:
            revisions.replay_revision_reads(admitted)
            with guards.capture_reads() as inner:
                revisions.replay_revision_reads(admitted)
                revisions.replay_revision_reads(admitted)
    assert outer.finish() == admitted
    assert inner.finish() == admitted
    outer.finish().verify()


def test_artifact_cache_replays_complete_nested_capture_without_path_walk(tmp_path, monkeypatch):
    path = tmp_path / 'fact.json'
    path.write_bytes(b'fact')
    with revisions.revision_artifact_batch():
        with guards.capture_reads() as first:
            expected = revisions.artifact(path, root=tmp_path)
        with monkeypatch.context() as patch:
            def forbidden(*args, **kwargs):
                raise AssertionError('cached artifact repeated path walk')
            patch.setattr(revisions, 'safe_path', forbidden)
            with guards.capture_reads() as second:
                assert revisions.artifact(path, root=tmp_path) == expected
        assert first.finish() == second.finish()


def test_reference_prior_replays_complete_proof_without_path_walk(tmp_path, monkeypatch):
    from video_ai.runtime import reference_image_records as refs
    path = tmp_path / 'accepted.json'
    path.write_bytes(b'original')

    def load(*args, **kwargs):
        manifest.hash_file(path)
        guards.observe_inventory(tmp_path, 'json_direct', [path])
        guards.observe_absence(tmp_path / 'missing.json')
        return [{'accepted': True}]

    monkeypatch.setattr(refs.images, '_load_accepted', load)
    frozen = SimpleNamespace(options={})
    with revisions.revision_artifact_batch():
        with guards.capture_reads() as first:
            expected = refs._prior(frozen, {}, {'batches': [['s']]}, {'scene_id': 's'})
        with monkeypatch.context() as patch:
            def forbidden(*args, **kwargs):
                raise AssertionError('reference prior replay repeated filesystem qualification')
            patch.setattr(guards, '_safe', forbidden)
            with guards.capture_reads() as second:
                assert refs._prior(frozen, {}, {'batches': [['s']]}, {'scene_id': 's'}) == expected
        assert first.finish() == second.finish()


def test_inventory_cache_replays_capture_without_rescanning(tmp_path, monkeypatch):
    path = tmp_path / 'fact.json'
    path.write_bytes(b'fact')
    scans = []
    original = type(tmp_path).rglob

    def scan(self, *args, **kwargs):
        scans.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(type(tmp_path), 'rglob', scan)
    with revisions.revision_artifact_batch():
        with guards.capture_reads() as first:
            assert revisions.revision_inventory(tmp_path, root=tmp_path) == [str(path)]
        for _ in range(5):
            with guards.capture_reads() as second:
                assert revisions.revision_inventory(tmp_path, root=tmp_path) == [str(path)]
            assert first.finish() == second.finish()
        assert len(scans) == 1
    assert len(scans) == 2


def test_revision_guard_observes_each_inventory_once(tmp_path, monkeypatch):
    frozen = SimpleNamespace(options={'script_path': str(tmp_path / 'production/script.txt')})
    guard = revisions.RevisionGuard(frozen)
    guard.capture_directory(tmp_path, root=tmp_path)
    calls = []
    original = guards.observe_inventory

    def observe(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(guards, 'observe_inventory', observe)
    with guards.capture_reads() as captured:
        guard.verify_captured_bytes()
    assert captured.finish().inventory_count == 1
    assert len(calls) == 1


@pytest.mark.parametrize('strong_second', [False, True])
def test_artifact_cache_preserves_declaration_only_source_scope(tmp_path, monkeypatch, strong_second):
    import hashlib
    from video_ai.runtime._scene_revision_origin_images import origin_image_scope, source_image_required
    frozen = SimpleNamespace(options={})
    raw, metadata = tmp_path / 'raw.bin', tmp_path / 'metadata.json'
    payload = b'original data'
    metadata.write_bytes(b'original declaration')
    if strong_second:
        raw.write_bytes(payload)
    original = manifest.hash_file

    def declared(path):
        if path == raw and not source_image_required(frozen, 'b'):
            original(metadata)
            return manifest.FileIdentity(str(raw), len(payload), 0,
                hashlib.sha256(payload).hexdigest(), manifest.now())
        return original(path)

    monkeypatch.setattr(manifest, 'hash_file', declared)
    with revisions.revision_artifact_batch():
        with origin_image_scope(frozen, {'a'}), guards.capture_reads() as weak:
            result = revisions.artifact(raw, root=tmp_path)
        assert {row.path for row in weak.finish().files} == {str(metadata)}
        if strong_second:
            with origin_image_scope(frozen, {'a', 'b'}), guards.capture_reads() as strong:
                assert revisions.artifact(raw, root=tmp_path) == result
            assert str(raw) in {row.path for row in strong.finish().files}


def test_replay_retains_conflict_and_failed_capture_rules(tmp_path):
    admitted = proof(tmp_path)
    with guards.capture_reads() as capture:
        guards.observe_inventory(tmp_path, 'json_direct', [])
        with pytest.raises(ValueError, match='conflicting observed inventory'):
            revisions.replay_revision_reads(admitted)
    with pytest.raises(ValueError, match='successful scope closure'):
        capture.finish()


def test_replay_retains_capacity_and_failed_capture_rules(tmp_path):
    admitted = proof(tmp_path)
    with guards.capture_reads(maximum_files=0) as capture:
        with pytest.raises(guards.CaptureLimit):
            revisions.replay_revision_reads(admitted)
    with pytest.raises(ValueError, match='successful scope closure'):
        capture.finish()


@pytest.mark.skipif(os.name != 'nt', reason='real Windows native sharing')
def test_window_exit_checks_unique_entries_and_shared_parents_once(tmp_path, monkeypatch):
    paths = [tmp_path / f'input-{i}.json' for i in range(4)]
    for path in paths:
        path.write_bytes(b'{"value":1}')
    with verification.whole_input_protection():
        with guards.capture_reads() as capture:
            for path in paths:
                manifest.hash_file(path)
        native.prepare_continuity_inputs(capture.finish().files, immutable_roots=(tmp_path,))
        directory_checks = []
        file_checks = []
        verify_directory = native._Directory.verify
        verify_file = verification._NativeInput.verify

        def directory(self, **kwargs):
            directory_checks.append(self.path)
            return verify_directory(self, **kwargs)

        def file(self, path):
            file_checks.append(path)
            return verify_file(self, path)

        monkeypatch.setattr(native._Directory, 'verify', directory)
        monkeypatch.setattr(verification._NativeInput, 'verify', file)
        verification._whole_inputs.get().verify()
        parents = {parent for path in paths for parent in path.parents}
        assert len(directory_checks) == 2 * len(parents)
        assert len(file_checks) == len(paths)


@pytest.mark.skipif(os.name != 'nt', reason='real Windows native sharing')
def test_read_transaction_shares_native_checks_across_nested_captures(tmp_path, monkeypatch):
    admitted = proof(tmp_path)
    checked = []
    original = verification._NativeInput.verify
    with verification.whole_input_protection():
        native.prepare_continuity_inputs(admitted.files, immutable_roots=(tmp_path,))

        def verify(self, path):
            checked.append(path)
            return original(self, path)

        monkeypatch.setattr(verification._NativeInput, 'verify', verify)
        with revisions.revision_read_transaction():
            for _ in range(5):
                with guards.capture_reads() as capture:
                    admitted.verify()
                    revisions.replay_revision_reads(admitted)
                assert capture.finish() == admitted
            assert len(checked) == 1
        assert len(checked) == 2  # First use and fresh read-boundary verification.


@pytest.mark.parametrize('kind', ['images', 'clips'])
def test_semantic_memo_separates_effective_source_scope(kind):
    from video_ai.runtime._scene_revision_origin_images import origin_image_scope, source_image_required
    from video_ai.runtime._scene_revision_origin_clips import origin_clip_scope, source_clip_required
    frozen = SimpleNamespace(options={})
    calls = []

    def read():
        calls.append(True)
        return (source_image_required(frozen, 'b') if kind == 'images'
                else source_clip_required(frozen, 'b'))

    def scope(required):
        return (origin_image_scope(frozen, required) if kind == 'images'
                else origin_clip_scope(frozen, required, all_ids={'a', 'b'}))

    with revisions.revision_artifact_batch():
        with scope({'a'}):
            assert revisions.revision_cached_read('scope-fixture', 'same-input', read) is False
        with scope({'a', 'b'}):
            assert revisions.revision_cached_read('scope-fixture', 'same-input', read) is True
    assert len(calls) == 2


def test_growing_guard_rechecks_new_absence_before_return(tmp_path):
    frozen = SimpleNamespace(options={'script_path': str(tmp_path / 'production/script.txt')})
    guard = revisions.RevisionGuard(frozen)
    missing = tmp_path / 'new-dependency.json'
    with revisions.revision_read_transaction():
        guard.verify_captured_bytes()
        guard.capture_absent(missing, root=tmp_path)
        missing.write_bytes(b'new evidence')
        try:
            with pytest.raises(revisions.ProductionRefused, match='absent evidence appeared'):
                guard.verify_captured_bytes()
        finally:
            missing.unlink()


@pytest.mark.skipif(os.name != 'nt', reason='real Windows native sharing')
def test_growing_guard_shares_already_verified_absences(tmp_path, monkeypatch):
    frozen = SimpleNamespace(options={'script_path': str(tmp_path / 'production/script.txt')})
    guard = revisions.RevisionGuard(frozen)
    missing = tmp_path / 'missing.json'
    guard.capture_absent(missing, root=tmp_path)
    checks = []
    original = type(missing).stat

    def stat(self, *args, **kwargs):
        if self == missing:
            checks.append(True)
        return original(self, *args, **kwargs)

    with verification.whole_input_protection(), revisions.revision_read_transaction():
        with monkeypatch.context() as patch:
            patch.setattr(type(missing), 'stat', stat)
            for index in range(5):
                guard.capture_absent(tmp_path / f'other-{index}.json', root=tmp_path)
                with guards.capture_reads() as captured:
                    guard.verify_captured_bytes()
                assert str(missing) in captured.finish().absences
                if index == 0:
                    first_checks = len(checks)
            assert first_checks > 0 and len(checks) == first_checks


@pytest.mark.skipif(os.name != 'nt', reason='real Windows native sharing')
def test_write_in_already_active_writer_ends_physical_reuse(tmp_path):
    from video_ai.runtime.production_state import write_exclusive
    admitted = proof(tmp_path)
    missing = tmp_path / 'missing.json'
    with verification.whole_input_protection(immutable_roots=(tmp_path,)):
        native.prepare_continuity_inputs(admitted.files, immutable_roots=(tmp_path,))
        with verification.writable_validation_session(tmp_path):
            with revisions.revision_read_transaction():
                admitted.verify()
                write_exclusive(missing, {'new': True})
                try:
                    with pytest.raises(ValueError, match='inventory changed|absent path appeared'):
                        admitted.verify()
                finally:
                    missing.unlink()


@pytest.mark.skipif(os.name != 'nt', reason='real Windows native sharing')
@pytest.mark.parametrize('invalidate', ['write', 'failure'])
def test_invalidated_transaction_retains_all_exit_obligations(tmp_path, invalidate):
    from video_ai.runtime.production_state import write_exclusive
    frozen = SimpleNamespace(options={'script_path': str(tmp_path / 'production/script.txt')})
    guard = revisions.RevisionGuard(frozen)
    missing = tmp_path / 'missing.json'
    guard.capture_absent(missing, root=tmp_path)
    with verification.whole_input_protection(), verification.writable_validation_session(tmp_path):
        with pytest.raises(ValueError, match='absent evidence appeared'):
            with revisions.revision_read_transaction():
                guard.verify_captured_bytes()
                if invalidate == 'failure':
                    native.fail_protected_read_pass()
                write_exclusive(missing, {'new': True})
                # No later access: exit must still check the original absence.


@pytest.mark.skipif(os.name != 'nt', reason='real Windows native sharing')
def test_transaction_borrowing_outer_pass_is_invalidated_by_writer(tmp_path):
    from video_ai.runtime.production_state import write_exclusive
    frozen = SimpleNamespace(options={'script_path': str(tmp_path / 'production/script.txt')})
    guard = revisions.RevisionGuard(frozen)
    missing = tmp_path / 'missing.json'
    guard.capture_absent(missing, root=tmp_path)
    with verification.whole_input_protection(), verification.writable_validation_session(tmp_path):
        with native.protected_read_pass(), revisions.revision_read_transaction():
            guard.verify_captured_bytes()
            write_exclusive(missing, {'new': True})
            try:
                with pytest.raises(ValueError, match='absent evidence appeared'):
                    guard.verify_captured_bytes()
            finally:
                missing.unlink()


@pytest.mark.skipif(os.name != 'nt', reason='real Windows native sharing')
def test_foreign_writer_cannot_publish_an_older_inventory_scan(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    admitted = proof(tmp_path)
    started, released = Event(), Event()
    scan = guards._scan

    def delayed(spec, deadline):
        if not started.is_set():
            started.set()
            assert released.wait(3)
        return scan(spec, deadline)

    with verification.whole_input_protection():
        native.prepare_continuity_inputs(admitted.files, immutable_roots=(tmp_path,))
        window = verification._whole_inputs.get()
        monkeypatch.setattr(guards, '_scan', delayed)

        def writer():
            assert started.wait(3)
            try:
                window.enter_writer(tmp_path / 'other')
                window.leave_writer(tmp_path / 'other')
            finally:
                released.set()

        with ThreadPoolExecutor(max_workers=1) as workers:
            future = workers.submit(writer)
            with revisions.revision_read_transaction():
                with pytest.raises(ValueError, match='write interrupted proof scan'):
                    admitted.verify()
            future.result()
        assert not window.read_passes


@pytest.mark.skipif(os.name != 'nt', reason='real Windows native sharing')
def test_failed_physical_check_disables_earlier_success_marks(tmp_path, monkeypatch):
    first = tmp_path / 'input.json'
    first.write_bytes(b'first')
    second = tmp_path / 'second.json'
    second.write_bytes(b'second')
    with guards.capture_reads() as capture:
        manifest.hash_file(first)
        manifest.hash_file(second)
    rows = {row.path: row for row in capture.finish().files}
    with verification.whole_input_protection():
        native.prepare_continuity_inputs(rows.values(), immutable_roots=(tmp_path,))
        checks = []
        fail = [False]
        original_file = verification._NativeInput.verify

        def file(self, path):
            checks.append(path)
            if fail[0] and path == second:
                raise ValueError('native file check failed')
            return original_file(self, path)

        monkeypatch.setattr(verification._NativeInput, 'verify', file)
        with revisions.revision_read_transaction():
            assert native.verify_protected_continuity_file(rows[str(first)])
            fail[0] = True
            with pytest.raises(ValueError, match='native file check failed'):
                native.verify_protected_continuity_file(rows[str(second)])
            fail[0] = False
            assert native.verify_protected_continuity_file(rows[str(first)])
            assert checks.count(first) == 2


def test_default_guard_verify_remains_fresh_between_calls(tmp_path):
    admitted = proof(tmp_path)
    admitted.verify()
    (tmp_path / 'new.json').write_bytes(b'new')
    with pytest.raises(ValueError, match='inventory changed'):
        admitted.verify()


@pytest.mark.skipif(os.name != 'nt', reason='real Windows native sharing')
def test_protected_input_reader_qualifies_native_entries_once(tmp_path, monkeypatch):
    path = tmp_path / 'input.json'
    path.write_bytes(b'{"value":1}')
    checks = []
    original = verification._NativeInput.verify

    def verify(self, current):
        checks.append(current)
        return original(self, current)

    monkeypatch.setattr(verification._NativeInput, 'verify', verify)

    @verification.protected_input_read
    def read():
        manifest.hash_file(path)
        manifest.hash_file(path)
        primed = len(checks)
        for _ in range(8):
            assert revisions.stable_bytes(path, root=tmp_path) == b'{"value":1}'
        assert len(checks) == primed

    read()


@pytest.mark.skipif(os.name != 'nt', reason='real Windows reparse attributes')
def test_read_pass_rejects_live_reparse_at_its_boundary(tmp_path):
    import ctypes
    from ctypes import wintypes
    import struct
    from unit.test_protected_continuity_inputs import reparse_writer, reparse_control, mount_payload
    directory, target = tmp_path / 'empty', tmp_path / 'target'
    directory.mkdir()
    target.mkdir()
    with guards.capture_reads() as capture:
        guards.observe_inventory(directory, 'children', [])
    admitted = capture.finish()
    held = native._Directory(directory)
    kernel, writer = reparse_writer(directory)
    installed = False
    try:
        with verification.whole_input_protection():
            with pytest.raises((ValueError, OSError)):
                with revisions.revision_read_transaction():
                    admitted.verify()
                    reparse_control(kernel, writer, 0x900A4, mount_payload(target))
                    installed = True
            assert not verification._whole_inputs.get().read_passes
    finally:
        if installed:
            reparse_control(kernel, writer, 0x900AC, struct.pack('<LHH', 0xA0000003, 0, 0))
        close = kernel.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        close.restype = wintypes.BOOL
        assert close(writer)
        held.close()
