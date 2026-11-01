import hashlib
import os
from pathlib import Path

import pytest

from video_ai.runtime import manifest


def test_validation_memo_is_namespaced_nested_and_cleared_after_exception():
    from video_ai.runtime.verification import validation_memo
    assert validation_memo('admission') is None
    with pytest.raises(RuntimeError,match='end memo operation'):
        with session():
            memo=validation_memo('admission');memo['authenticated']='captured bytes'
            assert validation_memo('different')=={} and validation_memo('different') is not memo
            with session():assert validation_memo('admission') is memo
            raise RuntimeError('end memo operation')
    assert validation_memo('admission') is None
    with session():assert validation_memo('admission')=={}


def session():
    # The missing boundary is itself the initial regression.
    assert hasattr(manifest, 'validation_session'), 'operation-scoped protected verification is missing'
    return manifest.validation_session()


def test_repeated_read_hashes_once_and_new_operation_reads_again(tmp_path, monkeypatch):
    path = tmp_path/'weights.bin'; path.write_bytes(b'original model')
    calls = []
    digest = hashlib.file_digest
    def counted(file, algorithm):
        calls.append(file.name)
        return digest(file, algorithm)
    monkeypatch.setattr(hashlib, 'file_digest', counted)
    with session():
        first = manifest.hash_file(path)
        with session():
            assert manifest.hash_file(path).sha256 == first.sha256
        manifest.hash_file(path)
    assert len(calls) == (1 if os.name == 'nt' else 3)
    with session():
        manifest.hash_file(path)
    assert len(calls) == (2 if os.name == 'nt' else 4)


def test_same_size_mtime_content_change_between_operations_is_rejected(tmp_path):
    from video_ai.runtime.timeline_checks import _again
    path = tmp_path/'weights.bin'; path.write_bytes(b'old bytes')
    with session():
        identity = manifest.hash_file(path)
    old = path.stat()
    path.write_bytes(b'new bytes')
    os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
    with session(), pytest.raises(OSError, match='changed'):
        _again({'model': identity})


@pytest.mark.skipif(os.name != 'nt', reason='Windows mandatory sharing')
@pytest.mark.parametrize('change', ['write', 'replace', 'unlink'])
def test_operation_blocks_content_change_and_releases_after_exception(tmp_path, change):
    path = tmp_path/'weights.bin'; path.write_bytes(b'original')
    replacement = tmp_path/'replacement.bin'; replacement.write_bytes(b'changed!')
    with pytest.raises(RuntimeError, match='end operation'):
        with session():
            manifest.hash_file(path)
            with pytest.raises(OSError):
                if change == 'write': path.write_bytes(b'changed!')
                elif change == 'replace': os.replace(replacement, path)
                else: path.unlink()
            assert path.read_bytes() == b'original'
            raise RuntimeError('end operation')
    path.write_bytes(b'changed!')


def test_mutable_manifest_never_reuses_a_digest(tmp_path, monkeypatch):
    path = tmp_path/'manifest.json'; path.write_bytes(b'first')
    calls = []
    digest = hashlib.file_digest
    def counted(file, algorithm):
        calls.append(1)
        return digest(file, algorithm)
    monkeypatch.setattr(hashlib, 'file_digest', counted)
    with session():
        before = manifest.hash_file(path)
        path.write_bytes(b'other')
        after = manifest.hash_file(path)
    assert before.sha256 != after.sha256 and len(calls) == 2


def test_existing_writer_refuses_protected_read(tmp_path):
    if os.name != 'nt': pytest.skip('Windows mandatory sharing')
    path = tmp_path/'weights.bin'; path.write_bytes(b'original')
    with path.open('r+b'), session(), pytest.raises(OSError):
        manifest.hash_file(path)


def test_mutation_during_unprotected_digest_is_rejected(tmp_path, monkeypatch):
    path = tmp_path/'weights.bin'; path.write_bytes(b'original')
    old = path.stat(); digest = hashlib.file_digest
    def changed(file, algorithm):
        value = digest(file, algorithm)
        path.write_bytes(b'changed!')
        os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
        return value
    monkeypatch.setattr(hashlib, 'file_digest', changed)
    with pytest.raises(OSError):
        manifest.hash_file(path)


@pytest.mark.skipif(os.name != 'nt', reason='Windows existing writable section')
def test_existing_writable_mapping_cannot_hide_content_change(tmp_path):
    import mmap
    path = tmp_path/'weights.bin'; path.write_bytes(b'original')
    with path.open('r+b') as writable:
        mapped = mmap.mmap(writable.fileno(), 0)
    try:
        with pytest.raises(OSError):
            with session():
                manifest.hash_file(path)
                mapped[:] = b'changed!'
                manifest.hash_file(path)
    finally:
        mapped.close()


def test_separate_threads_never_share_operation_digests(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    path=tmp_path/'weights.bin';path.write_bytes(b'original')
    barrier=Barrier(2); calls=[]; digest=hashlib.file_digest
    def counted(file,algorithm):
        calls.append(1)
        return digest(file,algorithm)
    monkeypatch.setattr(hashlib,'file_digest',counted)
    def consume():
        with session():
            barrier.wait(timeout=5)
            manifest.hash_file(path);manifest.hash_file(path)
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _:consume(),range(2)))
    assert len(calls)==(2 if os.name=='nt' else 4)


def test_platform_without_mandatory_sharing_always_rehashes(tmp_path,monkeypatch):
    from video_ai.runtime import verification
    class OtherPlatform:
        name='posix'
        def __getattr__(self,name):return getattr(os,name)
    monkeypatch.setattr(verification,'os',OtherPlatform())
    path=tmp_path/'weights.bin';path.write_bytes(b'original')
    with session():
        before=manifest.hash_file(path)
        path.write_bytes(b'changed!')
        after=manifest.hash_file(path)
    assert before.sha256!=after.sha256


def test_large_closure_never_exhausts_protected_file_descriptors(tmp_path,monkeypatch):
    if os.name!='nt':pytest.skip('Windows mandatory sharing')
    from video_ai.runtime import verification
    calls=[];reader=verification._locked_reader
    def tracked(path):
        opened=reader(path);calls.append(opened)
        assert sum(not file.closed for file in calls)<=257,'unbounded protected handles'
        return opened
    monkeypatch.setattr(verification,'_locked_reader',tracked)
    with session():
        for number in range(300):
            path=tmp_path/f'weights-{number}.bin';path.write_bytes(b'weights')
            assert manifest.hash_file(path).bytes==7
            assert sum(not file.closed for file in calls)<=256
        from video_ai.runtime.timeline_checks import _again
        identity=manifest.hash_file(path);old=path.stat()
        path.write_bytes(b'changed')
        os.utime(path,ns=(old.st_atime_ns,old.st_mtime_ns))
        with pytest.raises(OSError,match='changed'):
            _again({'overflow_leaf':identity})
    assert all(file.closed for file in calls)


@pytest.mark.skipif(os.name != 'nt', reason='Windows mandatory sharing')
@pytest.mark.parametrize('case', ['outside', 'small', 'manifest', 'overflow'])
def test_every_windows_digest_blocks_writers_even_without_cache(tmp_path, monkeypatch, case):
    from contextlib import nullcontext
    name = 'manifest.json' if case == 'manifest' else 'leaf.json' if case == 'small' else 'weights.bin'
    path = tmp_path/name; path.write_bytes(b'original')
    digest = hashlib.file_digest
    with nullcontext() if case == 'outside' else session():
        if case == 'overflow':
            for number in range(256):
                model = tmp_path/f'cached-{number}.bin'; model.write_bytes(b'weights')
                manifest.hash_file(model)
        def guarded(file, algorithm):
            with pytest.raises(OSError):
                path.write_bytes(b'changed!')
            return digest(file, algorithm)
        monkeypatch.setattr(hashlib, 'file_digest', guarded)
        assert manifest.hash_file(path).sha256 == hashlib.sha256(b'original').hexdigest()
    path.write_bytes(b'changed!')


def test_writable_validation_rehashes_owned_bytes_and_locks_only_during_each_digest(tmp_path,monkeypatch):
    from video_ai.runtime.verification import writable_validation_session
    from video_ai.runtime.timeline_checks import _again
    from video_ai.runtime._whole_scene_admission import EvidenceReader
    from video_ai.runtime.production_state import ProductionRefused
    root=tmp_path/'run';root.mkdir()
    path=root/'owned.bin';path.write_bytes(b'original')
    calls=[];digest=hashlib.file_digest
    def counted(file,algorithm):
        calls.append(1)
        if os.name=='nt':
            with pytest.raises(OSError):path.write_bytes(b'during!!')
        return digest(file,algorithm)
    monkeypatch.setattr(hashlib,'file_digest',counted)
    with writable_validation_session(root):
        original=manifest.hash_file(path);stamp=path.stat()
        assert manifest.hash_file(path).sha256==original.sha256 and len(calls)==2
        guard=EvidenceReader();guard.capture(path)
        assert len(calls)==3
        path.write_bytes(b'changed!');os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        with pytest.raises(OSError,match='changed'):_again({'owned':original})
        with pytest.raises(ProductionRefused,match='captured bytes'):guard.verify()
        assert len(calls)==5


@pytest.mark.skipif(os.name!='nt',reason='Windows mandatory sharing')
def test_nested_writable_roots_release_only_owned_handles_and_restore_after_exception(tmp_path):
    from video_ai.runtime.verification import writable_validation_session
    first_root=tmp_path/'first';second_root=tmp_path/'second'
    first_root.mkdir();second_root.mkdir()
    first=first_root/'staging.bin';first.write_bytes(b'first')
    second=second_root/'staging.bin';second.write_bytes(b'second')
    external=tmp_path/'external.safetensors';external.write_bytes(b'external')
    with session():
        # Entering a writer from an outer read safely releases an already-held
        # owned handle, without releasing any external immutable input.
        manifest.hash_file(first);manifest.hash_file(second);manifest.hash_file(external)
        with writable_validation_session(first_root):
            manifest.hash_file(first)
            first_target=first.with_name('promoted.bin');os.rename(first,first_target)
            with pytest.raises(RuntimeError,match='nested failure'):
                with writable_validation_session(second_root):
                    manifest.hash_file(second)
                    second.write_bytes(b'edited')
                    raise RuntimeError('nested failure')
            # The nested exclusion has ended; the parent root still permits
            # its own promotion, while the other root is read-protected again.
            manifest.hash_file(second)
            with pytest.raises(OSError):second.write_bytes(b'blocked')
            manifest.hash_file(first_target)
            final=first_target.with_name('final.bin');os.rename(first_target,final)
            with pytest.raises(OSError):external.write_bytes(b'blocked')
        manifest.hash_file(final)
        with pytest.raises(OSError):final.write_bytes(b'blocked')
    final.write_bytes(b'after');second.write_bytes(b'after');external.write_bytes(b'after')
