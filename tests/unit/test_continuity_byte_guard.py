"""Byte proofs use real runtime files; no model or service is involved."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import Context, copy_context
from dataclasses import FrozenInstanceError, replace
import importlib
import os
from pathlib import Path
import subprocess

import pytest

from video_ai.runtime.manifest import hash_file, thaw


@pytest.fixture
def evidence(tmp_path):
    path = tmp_path / 'original.json'
    path.write_bytes(b'{"ok":true}')
    return path


def proof(module, path):
    with module.capture_reads() as capture:
        module.observe_file(hash_file(path))
    return capture.finish()


def directory_link(alias, target):
    try:
        alias.symlink_to(target, target_is_directory=True)
    except OSError:
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(target)],
                                capture_output=True, check=False)
        if result.returncode:
            pytest.skip('OS does not permit symbolic links or junctions')


def test_repeated_checks_and_frozen_snapshot(evidence):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    module = guard_module
    identity = thaw(hash_file(evidence))
    with module.capture_reads() as capture:
        module.observe_file(identity)
        module.observe_file(dict(identity, verified_at='descriptive'))
    guard = capture.finish()
    identity['sha256'] = '0' * 64
    assert guard.file_count == 1
    assert guard.verify() is None
    assert guard.verify() is None
    with pytest.raises((AttributeError, FrozenInstanceError)):
        guard.files = ()


@pytest.mark.parametrize('change', ['content', 'mtime', 'replace', 'hardlink'])
def test_file_identity_drift_is_rejected(evidence, change):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    guard = proof(guard_module, evidence)
    before = evidence.stat()
    if change == 'content':
        evidence.write_bytes(b'{"ok":fals}')
        os.utime(evidence, ns=(before.st_atime_ns, before.st_mtime_ns))
    elif change == 'mtime':
        os.utime(evidence, ns=(before.st_atime_ns, before.st_mtime_ns + 10_000_000))
    elif change == 'replace':
        other = evidence.with_name('replacement')
        other.write_bytes(evidence.read_bytes())
        os.utime(other, ns=(before.st_atime_ns, before.st_mtime_ns))
        os.replace(other, evidence)
    else:
        os.link(evidence, evidence.with_name('added-link'))
    with pytest.raises((ValueError, OSError)):
        guard.verify()


@pytest.mark.parametrize(('kind', 'relative', 'directory'), [
    ('children', 'epoch_0002', True),
    ('children', 'attempt_0002', True),
    ('json_direct', 'receipt.json', False),
    ('json_direct', 'invalid.json', True),
    ('assessment_paths', 'audit/assessment.json', False),
    ('nonempty_files', 'audit/output.raw', False),
    ('revision_json', 'nested/revision.json', False),
    ('revision_json', 'invalid.json', True),
    ('whole_files', 'raw/output.bin', False),
    ('whole_files', 'receipt.json', False),
    ('continuity_sources', 'new_continuity.py', False),
])
def test_new_inventory_dependencies_are_rejected(tmp_path, kind, relative, directory):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    with guard_module.capture_reads() as capture:
        guard_module.observe_inventory(tmp_path, kind, [])
    guard = capture.finish()
    assert guard.verify() is None
    new = tmp_path / relative
    new.parent.mkdir(parents=True, exist_ok=True)
    if directory:
        new.mkdir()
    else:
        new.write_bytes(b'new evidence')
    with pytest.raises((ValueError, OSError)):
        guard.verify()


def test_inventory_copies_sorts_and_deduplicates_keys(tmp_path):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    first, second = tmp_path / 'a.json', tmp_path / 'b.json'
    first.write_bytes(b'a')
    second.write_bytes(b'b')
    expected = [second, str(first)]
    with guard_module.capture_reads(maximum_inventory_entries=2) as capture:
        guard_module.observe_inventory(tmp_path, 'json_direct', expected)
        guard_module.observe_inventory(tmp_path, 'json_direct', reversed(expected))
    expected.clear()
    guard = capture.finish()
    assert guard.inventory_count == 1
    assert guard.inventory_entry_count == 2
    guard.verify()


def test_whole_inventory_preserves_patterns_and_exclusions(tmp_path):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    for name in ['keep.json', 'other.bin', '.git/private.json', '__pycache__/cache.json']:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b'data')
    with guard_module.capture_reads() as capture:
        guard_module.observe_inventory(tmp_path, 'whole_files', [tmp_path / 'keep.json'], pattern='*.json')
    guard = capture.finish()
    guard.verify()
    (tmp_path / 'added.json').write_bytes(b'data')
    with pytest.raises(ValueError):
        guard.verify()


def test_absence_and_nonexistent_glob_root(tmp_path):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    absent = tmp_path / 'missing'
    with guard_module.capture_reads() as capture:
        guard_module.observe_absence(absent)
        guard_module.observe_inventory(absent, 'json_direct', [])
    guard = capture.finish()
    assert guard.absence_count == 1
    guard.verify()
    absent.mkdir()
    with pytest.raises(ValueError):
        guard.verify()


def test_no_capture_does_not_inspect_or_consume_inputs():
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    def forbidden():
        raise AssertionError('must not consume')
        yield
    guard_module.observe_inventory(object(), object(), forbidden())
    guard_module.observe_file(object())
    guard_module.observe_absence(object())


def test_nested_isolated_exceptional_and_late_contexts(evidence, tmp_path):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    module = guard_module
    identity = hash_file(evidence)
    with module.capture_reads() as outer:
        with module.capture_reads() as inner:
            module.observe_file(identity)
            late = copy_context()
        assert inner.finish().file_count == 1
        assert Context().run(lambda: proof(module, evidence)).file_count == 1
        with pytest.raises(RuntimeError):
            with module.capture_reads() as failed:
                raise RuntimeError('abort')
        with pytest.raises(ValueError):
            failed.finish()
        module.observe_absence(tmp_path / 'absent')
    guard = outer.finish()
    assert guard.file_count == 1
    assert guard.absence_count == 1
    late.run(module.observe_inventory, object(), object(), iter([object()]))
    assert outer.finish() == guard
    guard.verify()


def test_finish_requires_normal_scope_exit():
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    with guard_module.capture_reads() as capture:
        with pytest.raises(ValueError):
            capture.finish()
    capture.finish().verify()


@pytest.mark.parametrize('limit', [True, False, -1, 1.5, None])
@pytest.mark.parametrize('name', ['maximum_files', 'maximum_inventory_entries'])
def test_invalid_limits_rejected(limit, name):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    with pytest.raises(ValueError):
        with guard_module.capture_reads(**{name: limit}):
            pass


def test_overflow_poisoned_capture_cannot_emit_partial_proof(evidence):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    module = guard_module
    with module.capture_reads(maximum_files=0) as capture:
        with pytest.raises(module.CaptureLimit):
            module.observe_file(hash_file(evidence))
    with pytest.raises(ValueError):
        capture.finish()


def test_generator_overflow_is_bounded_and_propagates_to_outer(tmp_path):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    consumed = []
    def names():
        for index in range(100):
            consumed.append(index)
            yield tmp_path / f'{index}.json'
    with guard_module.capture_reads(maximum_inventory_entries=1) as outer:
        with guard_module.capture_reads() as inner:
            with pytest.raises(guard_module.CaptureLimit):
                guard_module.observe_inventory(tmp_path, 'json_direct', names())
    assert consumed == [0, 1]
    for capture in (outer, inner):
        with pytest.raises(ValueError):
            capture.finish()


def test_duplicate_conflicts_and_stat_mismatch_reject_capture(evidence):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    identity = hash_file(evidence)
    with pytest.raises(ValueError):
        with guard_module.capture_reads():
            guard_module.observe_file(identity)
            guard_module.observe_file(replace(identity, sha256='0' * 64))
    with pytest.raises(ValueError):
        with guard_module.capture_reads():
            guard_module.observe_file(replace(identity, mtime_ns=identity.mtime_ns + 1))


def test_repeated_file_identity_rechecks_canonical_resolution(evidence,monkeypatch):
    module=importlib.import_module('video_ai.runtime._continuity_byte_guard')
    identity=hash_file(evidence);original=module._safe;calls=[]
    def counted(path):
        calls.append(str(path));return original(path)
    monkeypatch.setattr(module,'_safe',counted)
    with module.capture_reads() as capture:
        for _ in range(100):module.observe_file(identity)
    assert calls==[str(evidence)]*100
    capture.finish().verify()


def test_sibling_inventory_rechecks_each_canonical_leaf(evidence,monkeypatch):
    module=importlib.import_module('video_ai.runtime._continuity_byte_guard')
    paths=[evidence.parent/f'{i}.json' for i in range(100)]
    for path in paths:path.write_text('{}')
    original=module._safe;calls=[]
    def counted(path):
        calls.append(str(path));return original(path)
    monkeypatch.setattr(module,'_safe',counted)
    with module.capture_reads() as capture:module.observe_inventory(evidence.parent,'json_direct',paths+[evidence])
    assert set(map(str,paths+[evidence])).issubset(calls)
    capture.finish().verify()


def test_duplicate_observation_still_checks_original_ownership(evidence):
    module=importlib.import_module('video_ai.runtime._continuity_byte_guard')
    identity=hash_file(evidence)
    with pytest.raises(ValueError):
        with module.capture_reads():
            module.observe_file(identity)
            replacement=evidence.with_name('replacement.json');replacement.write_bytes(evidence.read_bytes())
            os.utime(replacement,ns=(evidence.stat().st_atime_ns,identity.mtime_ns))
            os.replace(replacement,evidence)
            module.observe_file(identity)


def test_duplicate_observation_rejects_parent_redirect_with_same_leaf(tmp_path):
    module=importlib.import_module('video_ai.runtime._continuity_byte_guard')
    parent=tmp_path/'parent';moved=tmp_path/'moved'
    parent.mkdir();path=parent/'one.json';path.write_text('{}');identity=hash_file(path)
    assert parent.resolve().is_relative_to(tmp_path.resolve()) and moved.resolve().is_relative_to(tmp_path.resolve())
    with pytest.raises(ValueError):
        with module.capture_reads():
            module.observe_file(identity)
            parent.rename(moved);directory_link(parent,moved)
            module.observe_file(identity)


def test_inventory_rejects_transient_parent_redirect_during_generator(tmp_path):
    module=importlib.import_module('video_ai.runtime._continuity_byte_guard')
    parent=tmp_path/'parent';moved=tmp_path/'moved';parent.mkdir()
    first=parent/'one.json';second=parent/'two.json'
    first.write_text('{}');second.write_text('{}')
    assert parent.resolve().is_relative_to(tmp_path.resolve()) and moved.resolve().is_relative_to(tmp_path.resolve())
    def names():
        yield first
        parent.rename(moved);directory_link(parent,moved)
        try:yield second
        finally:
            if parent.is_symlink():parent.unlink()
            else:parent.rmdir()
            moved.rename(parent)
    with pytest.raises(ValueError):
        with module.capture_reads():module.observe_inventory(parent,'json_direct',names())


def test_parent_aliases_rejected(evidence):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    identity = hash_file(evidence)
    alias = evidence.parent / 'missing' / '..' / evidence.name
    with pytest.raises(ValueError):
        with guard_module.capture_reads():
            guard_module.observe_file(replace(identity, path=str(alias)))


def test_redirected_roots_and_parents_rejected(tmp_path):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    target = tmp_path / 'target'
    target.mkdir()
    alias = tmp_path / 'alias'
    directory_link(alias, target)
    for kind in ['children', 'json_direct', 'assessment_paths', 'nonempty_files',
                 'revision_json', 'whole_files', 'continuity_sources']:
        with pytest.raises(ValueError):
            with guard_module.capture_reads():
                guard_module.observe_inventory(alias, kind, [])
    with pytest.raises(ValueError):
        with guard_module.capture_reads():
            guard_module.observe_absence(alias / 'missing')


def test_verification_suppresses_observations_and_restores_outer(evidence, tmp_path, monkeypatch):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    import video_ai.runtime.manifest as manifest
    module = guard_module
    guard = proof(module, evidence)
    original = manifest.hash_file
    def observing_hash(path):
        identity = original(path)
        module.observe_file(identity)
        return identity
    monkeypatch.setattr(manifest, 'hash_file', observing_hash)
    with module.capture_reads() as outer:
        guard.verify()
        module.observe_absence(tmp_path / 'missing')
    assert outer.finish().file_count == 0
    assert outer.finish().absence_count == 1


def test_copied_thread_context_capture_and_repeated_verification(evidence):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    module = guard_module
    with module.capture_reads() as capture:
        contexts = [copy_context() for _ in range(16)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda ctx: ctx.run(module.observe_file, hash_file(evidence)), contexts))
    guard = capture.finish()
    assert guard.file_count == 1
    contexts = [copy_context() for _ in range(24)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda ctx: ctx.run(guard.verify), contexts)) == [None] * 24


def test_fresh_verification_deadline_checks_after_io(evidence, monkeypatch):
    guard_module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    import video_ai.runtime.manifest as manifest
    module = guard_module
    guard = proof(module, evidence)
    ticks = [1000.0]
    monkeypatch.setattr(module, 'monotonic', lambda: ticks[0])
    guard.verify()
    ticks[0] = 9000.0
    guard.verify()
    original = manifest.hash_file
    def slow_hash(path):
        identity = original(path)
        ticks[0] += 301
        return identity
    monkeypatch.setattr(manifest, 'hash_file', slow_hash)
    with pytest.raises(ValueError, match='interval'):
        guard.verify()


@pytest.mark.parametrize('kind', ['assessment_paths', 'whole_files', 'revision_json', 'nonempty_files'])
def test_redirected_inventory_descendants_rejected_before_following(tmp_path, kind):
    module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    root, target = tmp_path / 'inventory', tmp_path / 'elsewhere'
    root.mkdir()
    target.mkdir()
    with module.capture_reads() as capture:
        module.observe_inventory(root, kind, [])
    directory_link(root / 'redirect', target)
    with pytest.raises(ValueError):
        capture.finish().verify()


def test_verification_failure_restores_surrounding_capture(evidence, tmp_path):
    module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    guard = proof(module, evidence)
    evidence.write_bytes(b'changed')
    with module.capture_reads() as capture:
        with pytest.raises(ValueError):
            guard.verify()
        module.observe_absence(tmp_path / 'missing')
    assert capture.finish().absence_count == 1


def test_deadline_checked_after_inventory_scan(tmp_path, monkeypatch):
    module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    from video_ai.runtime._whole_scene_admission import EvidenceReader
    with module.capture_reads() as capture:
        module.observe_inventory(tmp_path, 'whole_files', [])
    ticks = [0.0]
    monkeypatch.setattr(module, 'monotonic', lambda: ticks[0])
    original = EvidenceReader.inventory
    def slow_inventory(self, folder, pattern='*'):
        result = original(self, folder, pattern)
        ticks[0] += 301.0
        return result
    monkeypatch.setattr(EvidenceReader, 'inventory', slow_inventory)
    with pytest.raises(ValueError, match='interval'):
        capture.finish().verify()


def test_nested_observation_error_invalidates_both_and_outer_recovers_context(evidence):
    module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    with module.capture_reads() as outer:
        with pytest.raises(ValueError):
            with module.capture_reads() as inner:
                module.observe_file(object())
        module.observe_file(hash_file(evidence))
    for capture in (outer, inner):
        with pytest.raises(ValueError):
            capture.finish()


def test_file_limit_allows_identical_duplicate(evidence):
    module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    identity = hash_file(evidence)
    with module.capture_reads(maximum_files=1) as capture:
        module.observe_file(identity)
        module.observe_file(identity)
    assert capture.finish().file_count == 1


@pytest.mark.parametrize('kind', ['json_direct', 'assessment_paths', 'nonempty_files', 'revision_json', 'continuity_sources'])
def test_glob_inventory_accepts_nonexistent_root(tmp_path, kind):
    module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    with module.capture_reads() as capture:
        module.observe_inventory(tmp_path / 'nonexistent', kind, [])
    capture.finish().verify()


def test_nonempty_inventory_ignores_new_empty_regular_file(tmp_path):
    module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    with module.capture_reads() as capture:
        module.observe_inventory(tmp_path, 'nonempty_files', [])
    (tmp_path / 'empty').touch()
    capture.finish().verify()


@pytest.mark.parametrize('excluded', ['.git', '__pycache__'])
def test_whole_inventory_ignores_redirects_below_excluded_subtrees(tmp_path, excluded):
    module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    root, target = tmp_path / 'inventory', tmp_path / 'elsewhere'
    root.mkdir()
    target.mkdir()
    keep = root / 'keep.json'
    keep.write_bytes(b'unchanged')
    with module.capture_reads() as capture:
        module.observe_inventory(root, 'whole_files', [keep])
    excluded_root = root / 'nested' / excluded
    excluded_root.mkdir(parents=True)
    directory_link(excluded_root / 'redirect', target)
    capture.finish().verify()


@pytest.mark.parametrize('stage', ['path', 'stat'])
def test_expired_pre_hash_metadata_does_not_start_hash(evidence, monkeypatch, stage):
    module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    import video_ai.runtime.manifest as manifest
    guard = proof(module, evidence)
    ticks = [0.0]
    monkeypatch.setattr(module, 'monotonic', lambda: ticks[0])
    original_safe, original_stat = module._safe, Path.stat
    if stage == 'path':
        def slow_safe(path):
            result = original_safe(path)
            ticks[0] += 301.0
            return result
        monkeypatch.setattr(module, '_safe', slow_safe)
    else:
        def slow_stat(path, *args, **kwargs):
            result = original_stat(path, *args, **kwargs)
            if path == evidence:
                ticks[0] += 301.0
            return result
        monkeypatch.setattr(Path, 'stat', slow_stat)
    original_hash, hashes = manifest.hash_file, []
    def record_hash(path):
        hashes.append(path)
        return original_hash(path)
    monkeypatch.setattr(manifest, 'hash_file', record_hash)
    with pytest.raises(ValueError, match='interval'):
        guard.verify()
    assert hashes == []


@pytest.mark.parametrize('stage', ['last_metadata', 'empty_scan'])
def test_expired_whole_prepass_does_not_start_inventory(tmp_path, monkeypatch, stage):
    module = importlib.import_module('video_ai.runtime._continuity_byte_guard')
    from video_ai.runtime._whole_scene_admission import EvidenceReader
    root = tmp_path / 'inventory'
    root.mkdir()
    leaf = root / 'last.json'
    expected = []
    if stage == 'last_metadata':
        leaf.write_bytes(b'unchanged')
        expected.append(leaf)
    with module.capture_reads() as capture:
        module.observe_inventory(root, 'whole_files', expected)
    ticks = [0.0]
    monkeypatch.setattr(module, 'monotonic', lambda: ticks[0])
    if stage == 'last_metadata':
        original_lstat = Path.lstat
        def slow_lstat(path, *args, **kwargs):
            result = original_lstat(path, *args, **kwargs)
            if path == leaf:
                ticks[0] += 301.0
            return result
        monkeypatch.setattr(Path, 'lstat', slow_lstat)
    else:
        original_scandir = os.scandir
        def slow_scandir(path):
            result = original_scandir(path)
            if Path(path) == root:
                ticks[0] += 301.0
            return result
        monkeypatch.setattr(os, 'scandir', slow_scandir)
    original_inventory, inventories = EvidenceReader.inventory, []
    def record_inventory(self, folder, pattern='*'):
        inventories.append(folder)
        return original_inventory(self, folder, pattern)
    monkeypatch.setattr(EvidenceReader, 'inventory', record_inventory)
    with pytest.raises(ValueError, match='interval'):
        capture.finish().verify()
    assert inventories == []
