"""Windows whole-admission IO protection, not model or playback evidence."""
from contextvars import copy_context
import ctypes
from ctypes import wintypes
import os

import pytest

from video_ai.runtime import manifest, verification

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows mandatory sharing')


def window():
    assert hasattr(verification, 'whole_input_protection'), 'whole input protection window missing'
    return verification.whole_input_protection()


def test_default_small_inputs_remain_fully_rehashed(tmp_path):
    path = tmp_path/'leaf.json'; path.write_bytes(b'original')
    with verification.validation_session():
        before = manifest.hash_file(path)
        stamp = path.stat()
        path.write_bytes(b'changed!')
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        assert manifest.hash_file(path).sha256 != before.sha256


@pytest.mark.parametrize('change', ['write','replace','unlink'])
def test_small_external_input_is_immutable_for_the_window(tmp_path, change):
    scope = window()
    path = tmp_path/'帧.json'; path.write_bytes(b'original')
    replacement = tmp_path/'replacement.json'; replacement.write_bytes(b'changed!')
    with verification.validation_session(), scope:
        first = manifest.hash_file(path)
        with pytest.raises(OSError):
            if change == 'write': path.write_bytes(b'changed!')
            elif change == 'replace': os.replace(replacement, path)
            else: path.unlink()
        assert manifest.hash_file(path).sha256 == first.sha256
    path.write_bytes(b'changed!')


def test_a_new_window_never_reuses_an_old_digest(tmp_path):
    first_scope = window()
    path = tmp_path/'leaf.json'; path.write_bytes(b'original')
    with verification.validation_session(), first_scope:
        before = manifest.hash_file(path)
    stamp = path.stat()
    path.write_bytes(b'changed!')
    os.utime(path, ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    with verification.validation_session(), window():
        assert manifest.hash_file(path).sha256 != before.sha256


def test_attribute_changes_are_denied_or_detected(tmp_path):
    scope = window()
    path = tmp_path/'leaf.json'; path.write_bytes(b'original')
    with pytest.raises(OSError):
        with verification.validation_session(), scope:
            manifest.hash_file(path)
            stamp = path.stat()
            os.utime(path, ns=(stamp.st_atime_ns,stamp.st_mtime_ns+1_000_000_000))
            manifest.hash_file(path)
    path.write_bytes(b'afterwards')


def test_entering_a_writer_releases_only_its_own_inputs(tmp_path):
    scope = window()
    root = tmp_path/'run'; root.mkdir()
    owned = root/'staging.json'; owned.write_bytes(b'owned')
    external = tmp_path/'external.json'; external.write_bytes(b'external')
    with verification.validation_session(), scope:
        manifest.hash_file(owned); manifest.hash_file(external)
        with verification.writable_validation_session(root):
            first = manifest.hash_file(owned)
            stamp = owned.stat()
            owned.write_bytes(b'other')
            os.utime(owned,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            assert manifest.hash_file(owned).sha256 != first.sha256
            promoted = root/'promoted.json'
            os.rename(owned,promoted)
            with pytest.raises(OSError): external.write_bytes(b'blocked!')
        manifest.hash_file(promoted)
        with pytest.raises(OSError): promoted.write_bytes(b'blocked')
    promoted.write_bytes(b'after'); external.write_bytes(b'after')


def test_mutable_manifest_is_never_pinned(tmp_path):
    scope = window()
    path = tmp_path/'manifest.json'; path.write_bytes(b'first')
    with verification.validation_session(), scope:
        first = manifest.hash_file(path)
        path.write_bytes(b'other')
        assert manifest.hash_file(path).sha256 != first.sha256


def test_handle_limit_falls_back_to_complete_hashes(tmp_path,monkeypatch):
    scope = window()
    monkeypatch.setattr(verification,'_MAX_WHOLE_INPUTS',2)
    paths = [tmp_path/f'leaf-{number}.json' for number in range(3)]
    for path in paths: path.write_bytes(b'original')
    with verification.validation_session(), scope:
        identities = [manifest.hash_file(path) for path in paths]
        for path in paths[:2]:
            with pytest.raises(OSError): path.write_bytes(b'changed!')
        stamp = paths[2].stat()
        paths[2].write_bytes(b'changed!')
        os.utime(paths[2],ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        assert manifest.hash_file(paths[2]).sha256 != identities[2].sha256


def handle_count():
    api = ctypes.WinDLL('kernel32',use_last_error=True)
    api.GetCurrentProcess.restype = wintypes.HANDLE
    api.GetProcessHandleCount.argtypes = [wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    api.GetProcessHandleCount.restype = wintypes.BOOL
    value = wintypes.DWORD()
    assert api.GetProcessHandleCount(api.GetCurrentProcess(),ctypes.byref(value))
    return value.value


def test_large_closure_does_not_exhaust_crt_descriptors_or_leak_handles(tmp_path):
    scope = window()
    paths = [tmp_path/f'leaf-{number:05d}.json' for number in range(9000)]
    for path in paths: path.write_bytes(b'original')
    before = handle_count()
    with verification.validation_session(), scope:
        for path in paths: manifest.hash_file(path)
        assert handle_count() >= before+len(paths)
        with pytest.raises(OSError): paths[-1].write_bytes(b'changed!')
    assert handle_count() <= before+32
    paths[-1].write_bytes(b'changed!')


def test_exception_releases_all_inputs(tmp_path):
    scope = window()
    path = tmp_path/'leaf.json'; path.write_bytes(b'original')
    with pytest.raises(RuntimeError,match='operation failed'):
        with verification.validation_session(), scope:
            manifest.hash_file(path)
            raise RuntimeError('operation failed')
    path.write_bytes(b'changed!')


def test_late_copied_context_cannot_reuse_or_retain_closed_protection(tmp_path):
    scope = window()
    path = tmp_path/'leaf.json'; path.write_bytes(b'original')
    with verification.validation_session(), scope:
        first = manifest.hash_file(path)
        copied = copy_context()
    path.write_bytes(b'changed!')
    assert copied.run(manifest.hash_file,path).sha256 != first.sha256
    path.write_bytes(b'after!!!')


def test_network_style_copied_context_keeps_the_same_protection(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    scope = window()
    path = tmp_path/'leaf.json'; path.write_bytes(b'original')
    with verification.validation_session(), scope:
        first = manifest.hash_file(path)
        copied = copy_context()
        with ThreadPoolExecutor(max_workers=1) as executor:
            other = executor.submit(copied.run,manifest.hash_file,path).result(timeout=5)
        assert other.sha256 == first.sha256
        with pytest.raises(OSError): path.write_bytes(b'changed!')


@pytest.mark.parametrize('timing',['inflight','stale_read'])
@pytest.mark.parametrize('nested',[False,True])
def test_copied_worker_cannot_pin_a_root_after_writer_entry(tmp_path,monkeypatch,timing,nested):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    root = tmp_path/'run'; root.mkdir()
    owned = root/'staging.json'; owned.write_bytes(b'original')
    external = tmp_path/'external.json'; external.write_bytes(b'external')
    hashed, resume = Event(), Event()
    original = manifest._hash_open_file
    def paused(file,path):
        value = original(file,path)
        if path == owned and timing == 'inflight':
            hashed.set()
            assert resume.wait(10)
        return value
    monkeypatch.setattr(manifest,'_hash_open_file',paused)
    with verification.validation_session(), window():
        manifest.hash_file(external)
        copied = copy_context()  # Captured before this root becomes writable.
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(copied.run,manifest.hash_file,owned) if timing=='inflight' else None
            try:
                if timing=='inflight': assert hashed.wait(10)
                with verification.writable_validation_session(root):
                    if nested:
                        with verification.writable_validation_session(root): pass
                    if future is None:
                        future = executor.submit(copied.run,manifest.hash_file,owned)
                    resume.set()
                    assert future.result(timeout=10).sha256
                    owned.write_bytes(b'changed!')
                    promoted = root/'promoted.json'
                    os.rename(owned,promoted)
                    with pytest.raises(OSError): external.write_bytes(b'blocked!')
                manifest.hash_file(promoted)
                with pytest.raises(OSError): promoted.write_bytes(b'blocked!')
            finally:
                resume.set()
    promoted.write_bytes(b'after!!!'); external.write_bytes(b'after!!!')


def test_non_windows_platform_keeps_complete_hashes(tmp_path,monkeypatch):
    scope = window()
    class OtherPlatform:
        name = 'posix'
        def __getattr__(self,name): return getattr(os,name)
    monkeypatch.setattr(verification,'os',OtherPlatform())
    path = tmp_path/'leaf.json'; path.write_bytes(b'original')
    with verification.validation_session(), scope:
        first = manifest.hash_file(path)
        path.write_bytes(b'changed!')
        assert manifest.hash_file(path).sha256 != first.sha256


def frozen(mode):
    from types import SimpleNamespace
    raw = {}
    if mode is not None:
        rendering = dict(mode=mode,prompt_policy='visual_v2',prompt_contract='fixture.json')
        if mode == 'whole_scene_v1':
            rendering['whole_scene_evidence'] = 'D:/VideoSi/fixture-evidence.json'
        raw['scene_rendering'] = rendering
    return SimpleNamespace(config=SimpleNamespace(raw=raw),options={})


@pytest.mark.parametrize('mode',[None,'segmented_v1','whole_scene_v1'])
def test_writer_activates_small_input_protection_only_for_whole(tmp_path,mode):
    from video_ai.runtime.scene_execution_records import verified_scene_execution_write
    path = tmp_path/'external.json'; path.write_bytes(b'original')
    @verified_scene_execution_write
    def operation(inputs):
        manifest.hash_file(path)
        if mode == 'whole_scene_v1':
            with pytest.raises(OSError): path.write_bytes(b'changed!')
        else:
            path.write_bytes(b'changed!')
    operation(frozen(mode))


def test_cached_whole_admission_guard_keeps_inputs_protected(tmp_path):
    from video_ai.runtime import scene_execution_records as records
    from video_ai.planning.production_scenes import canonical_digest
    path = tmp_path/'external.json'; path.write_bytes(b'original')
    inputs = frozen('whole_scene_v1')
    inputs.options['execution_policy'] = dict(input_identities=dict(whole_scene_evidence={},whole_scene_evidence_closure={}))
    class Guard:
        def verify(self):
            manifest.hash_file(path)
            with pytest.raises(OSError): path.write_bytes(b'changed!')
    key = canonical_digest(dict(options=inputs.options,raw=inputs.config.raw))
    evidence = dict(guard=Guard())  # Fixture-only authenticated-semantic memo.
    token = records._writer_admissions.set({key:evidence})
    try:
        assert records.verify_whole_scene_frozen(inputs) is evidence
    finally:
        records._writer_admissions.reset(token)


def continuity_fixture(monkeypatch):
    from types import SimpleNamespace
    from video_ai.runtime import production_scene_continuity as writer
    monkeypatch.setattr(writer.records,'load_continuity_policy',lambda _:dict(schema_version=1,policy='advisory_v1'))
    monkeypatch.setattr(writer,'ContinuityStore',lambda *_:SimpleNamespace(owned=lambda:None))
    return writer


def test_continuity_entry_protects_admitted_inputs_through_the_operation(tmp_path,monkeypatch):
    writer = continuity_fixture(monkeypatch)
    path = tmp_path/'external.json'; path.write_bytes(b'original')
    def context(*args,**kwargs):
        manifest.hash_file(path)
        return {},{}
    def operation(store,context,source,reader):
        with pytest.raises(OSError): path.write_bytes(b'changed!')
        reader.check()
        return 'fixture-completed'
    monkeypatch.setattr(writer,'_context',context)
    assert writer._entry(frozen('whole_scene_v1'),[],None,operation,
                         paths=None,logger=None,lock=object()) == 'fixture-completed'


def test_continuity_shared_deadline_still_includes_preflight(monkeypatch):
    from types import SimpleNamespace
    from video_ai.runtime import _scene_continuity_io as io
    writer = continuity_fixture(monkeypatch)
    clock = [0.]
    monkeypatch.setattr(io,'monotonic',lambda:clock[0])
    def context(*args,**kwargs):
        clock[0] += 301
        return {},{}
    monkeypatch.setattr(writer,'_context',context)
    monkeypatch.setattr(writer,'_result',lambda _,status,**kwargs:SimpleNamespace(status=status,**kwargs))
    result = writer._entry(frozen('whole_scene_v1'),[],None,
        lambda store,context,source,reader:reader.check(),paths=None,logger=None,lock=object())
    assert result.status == 'blocked' and result.error['kind'] == 'TimeoutError'
