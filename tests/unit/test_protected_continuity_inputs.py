"""Real Windows leases: an unprotected or stale dependency cannot fast-pass."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import dataclass, replace
import hashlib
import importlib.util
import os
from pathlib import Path
import struct

import pytest

from video_ai.runtime import manifest, verification


@dataclass(frozen=True)
class Record:
    path: str
    bytes: int
    mtime_ns: int
    sha256: str
    ownership: tuple


def core():
    name = 'video_ai.runtime._protected_continuity_inputs'
    assert importlib.util.find_spec(name) is not None, 'native continuity protection is missing'
    return __import__(name, fromlist=['prepare_continuity_inputs'])


def record(path):
    path = path.resolve(strict=True)
    value = path.stat()
    return Record(str(path), value.st_size, value.st_mtime_ns,
                  hashlib.sha256(path.read_bytes()).hexdigest(),
                  (value.st_dev, value.st_ino, value.st_nlink,
                   getattr(value, 'st_uid', None), getattr(value, 'st_gid', None)))


def test_without_window_never_claims_protection(tmp_path):
    path = tmp_path/'file.bin'; path.write_bytes(b'original')
    row = record(path); api = core()
    api.prepare_continuity_inputs([row], immutable_roots=[tmp_path])
    assert api.verify_protected_continuity_file(row) is False
    path.write_bytes(b'changed!')


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
@pytest.mark.parametrize('field,value', [
    ('sha256', '0'*64), ('bytes', 9), ('mtime_ns', 1),
    ('ownership', (0, 0, 1, None, None)),
])
def test_existing_native_entry_rejects_forged_record(tmp_path, field, value):
    path = tmp_path/'file.bin'; path.write_bytes(b'original'); row = record(path)
    api = core()
    with verification.whole_input_protection(), verification.validation_session():
        manifest.hash_file(path)
        api.prepare_continuity_inputs([row])
        assert api.verify_protected_continuity_file(row) is True
        with pytest.raises((ValueError, OSError)):
            api.verify_protected_continuity_file(replace(row, **{field: value}))


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
def test_owned_exact_records_pin_and_unlisted_mutable_files_stay_writable(tmp_path):
    source = tmp_path/'source'; source.mkdir()
    path = source/'file.bin'; path.write_bytes(b'original')
    mutable = tmp_path/'manifest.json'; mutable.write_bytes(b'mutable')
    row = record(path); other = record(mutable); api = core()
    with verification.writable_validation_session(tmp_path), verification.whole_input_protection():
        api.prepare_continuity_inputs([row, other], immutable_roots=[source])
        assert api.verify_protected_continuity_file(row) is True
        assert api.verify_protected_continuity_file(other) is False
        with pytest.raises(OSError): path.write_bytes(b'changed!')
        with pytest.raises(OSError): path.unlink()
        with pytest.raises(OSError): source.rename(tmp_path/'moved')
        mutable.write_bytes(b'updated')
    path.write_bytes(b'changed!')
    source.rename(tmp_path/'moved')


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
def test_fresh_source_hash_rejects_restored_size_and_mtime(tmp_path):
    path = tmp_path/'file.bin'; path.write_bytes(b'original'); row = record(path)
    stamp = path.stat(); path.write_bytes(b'changed!')
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    api = core()
    with verification.writable_validation_session(tmp_path), verification.whole_input_protection():
        with pytest.raises((ValueError, OSError)):
            api.prepare_continuity_inputs([row], immutable_roots=[path])
        assert api.verify_protected_continuity_file(row) is False
        path.write_bytes(b'released')


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
def test_hardlinks_fall_back_without_a_retained_pin(tmp_path):
    path = tmp_path/'file.bin'; path.write_bytes(b'original')
    os.link(path, tmp_path/'alias.bin'); row = record(path); api = core()
    with verification.whole_input_protection():
        api.prepare_continuity_inputs([row])
        assert api.verify_protected_continuity_file(row) is False
        path.write_bytes(b'changed!')


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
def test_close_releases_exception_and_late_copied_context(tmp_path):
    path = tmp_path/'file.bin'; path.write_bytes(b'original'); row = record(path); api = core()
    with pytest.raises(RuntimeError, match='operation failed'):
        with verification.whole_input_protection():
            api.prepare_continuity_inputs([row]); late = copy_context()
            assert api.verify_protected_continuity_file(row)
            raise RuntimeError('operation failed')
    path.write_bytes(b'changed!')
    assert late.run(api.verify_protected_continuity_file, row) is False
    late.run(api.prepare_continuity_inputs, [row])
    path.write_bytes(b'released')


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
def test_nested_writer_revokes_ordinary_entry_in_copied_threads(tmp_path):
    path = tmp_path/'file.bin'; path.write_bytes(b'original'); row = record(path); api = core()
    with verification.whole_input_protection(), verification.validation_session():
        manifest.hash_file(path); api.prepare_continuity_inputs([row])
        copied = copy_context()
        with verification.writable_validation_session(tmp_path):
            assert api.verify_protected_continuity_file(row) is False
            with ThreadPoolExecutor(max_workers=2) as executor:
                assert executor.submit(api.verify_protected_continuity_file, row).result() is False
                assert executor.submit(copied.run, api.verify_protected_continuity_file, row).result() is False
            path.write_bytes(b'changed!')
            tmp_path.rename(tmp_path.with_name(tmp_path.name + '-moved'))


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
def test_directory_child_changes_do_not_invalidate_live_proof(tmp_path):
    path = tmp_path/'file.bin'; path.write_bytes(b'original'); row = record(path); api = core()
    with verification.whole_input_protection():
        api.prepare_continuity_inputs([row])
        (tmp_path/'unrelated').write_bytes(b'child list changed')
        os.utime(tmp_path, None)
        assert api.verify_protected_continuity_file(row)


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
@pytest.mark.parametrize('limit', ['_MAX_SOURCE_PINS', '_MAX_RECORDS', '_MAX_DIRECTORIES'])
def test_capacity_miss_preserves_existing_protection_and_closes_partial_setup(tmp_path, monkeypatch, limit):
    api = core()
    first = tmp_path/'first.bin'; first.write_bytes(b'first')
    nested = tmp_path/'nested'; nested.mkdir()
    second = nested/'second.bin'; second.write_bytes(b'second')
    first_row, second_row = record(first), record(second)
    with verification.whole_input_protection():
        api.prepare_continuity_inputs([first_row])
        maximum = len(first.parents) if limit == '_MAX_DIRECTORIES' else 1
        monkeypatch.setattr(api, limit, maximum)
        api.prepare_continuity_inputs([second_row])
        assert api.verify_protected_continuity_file(first_row)
        assert api.verify_protected_continuity_file(second_row) is False
        with pytest.raises(OSError): first.write_bytes(b'other')
        second.write_bytes(b'other!')
        nested.rename(tmp_path/'released')
    first.write_bytes(b'after')


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
def test_partial_setup_failure_does_not_retain_directory_handles(tmp_path):
    api = core(); directory = tmp_path/'source'; directory.mkdir()
    path = directory/'file.bin'; path.write_bytes(b'original'); row = record(path)
    path.write_bytes(b'changed!'); os.utime(path, ns=(row.mtime_ns, row.mtime_ns))
    with verification.whole_input_protection():
        with pytest.raises(ValueError): api.prepare_continuity_inputs([row])
        assert api.verify_protected_continuity_file(row) is False
        directory.rename(tmp_path/'released')


def test_non_windows_uses_strict_fallback(tmp_path, monkeypatch):
    api = core(); path = tmp_path/'file.bin'; path.write_bytes(b'original'); row = record(path)
    class OtherPlatform:
        name = 'posix'
        def __getattr__(self, name): return getattr(os, name)
    monkeypatch.setattr(verification, 'os', OtherPlatform())
    with verification.whole_input_protection():
        api.prepare_continuity_inputs([row])
        assert api.verify_protected_continuity_file(row) is False
        path.write_bytes(b'changed!')


def reparse_writer(path):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    handle = create(str(path), 0x100, 7, None, 3, 0x02200000, None)
    if handle == ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    return kernel, handle


def reparse_control(kernel, handle, code, payload):
    import ctypes
    from ctypes import wintypes
    control = kernel.DeviceIoControl
    control.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                        ctypes.c_void_p]
    control.restype = wintypes.BOOL
    data = ctypes.create_string_buffer(payload); returned = wintypes.DWORD()
    if not control(handle, code, data, len(payload), None, 0, ctypes.byref(returned), None):
        raise ctypes.WinError(ctypes.get_last_error())


def mount_payload(target):
    substitute = ('\\??\\' + str(target)).encode('utf-16-le')
    printed = str(target).encode('utf-16-le')
    data = substitute + b'\0\0' + printed + b'\0\0'
    return struct.pack('<LHHHHHH', 0xA0000003, 8 + len(data), 0,
                       0, len(substitute), len(substitute) + 2, len(printed)) + data


@pytest.mark.skipif(os.name != 'nt', reason='Windows reparse attributes')
def test_live_directory_query_refuses_fsctl_reparse_then_recovers_after_delete(tmp_path):
    import ctypes
    from ctypes import wintypes
    api = core(); directory = tmp_path/'empty'; directory.mkdir()
    target = tmp_path/'target'; target.mkdir()
    held = api._Directory(directory)
    kernel, writer = reparse_writer(directory)
    installed = False
    try:
        reparse_control(kernel, writer, 0x900A4, mount_payload(target)); installed = True
        assert directory.lstat().st_file_attributes & 0x400
        with pytest.raises((ValueError, OSError)): held.verify()
        reparse_control(kernel, writer, 0x900AC, struct.pack('<LHH', 0xA0000003, 0, 0))
        installed = False
        held.verify()
    finally:
        if installed:
            reparse_control(kernel, writer, 0x900AC, struct.pack('<LHH', 0xA0000003, 0, 0))
        close = kernel.CloseHandle; close.argtypes = [wintypes.HANDLE]; close.restype = wintypes.BOOL
        assert close(writer)
        held.close()


@pytest.mark.skipif(os.name != 'nt', reason='Windows reparse attributes')
def test_nonempty_reparse_is_refused_per_file_and_at_final_window_check(tmp_path):
    from ctypes import wintypes
    api = core(); directory = tmp_path/'source'; directory.mkdir()
    target = tmp_path/'target'; target.mkdir()
    path = directory/'file.bin'; path.write_bytes(b'original'); row = record(path)
    kernel, writer = reparse_writer(directory)
    installed = False
    try:
        with verification.whole_input_protection():
            api.prepare_continuity_inputs([row]); assert api.verify_protected_continuity_file(row)
            try:
                reparse_control(kernel, writer, 0x900A4, mount_payload(target)); installed = True
            except OSError as exc:
                # NTFS normally refuses junction installation on a nonempty
                # directory. This is an explicit optional-feature result.
                assert exc.winerror in (145, 4390, 4393), exc
                print(f'nonempty FSCTL_SET_REPARSE_POINT unavailable: winerror={exc.winerror}; live proof intact')
                assert api.verify_protected_continuity_file(row)
            else:
                with pytest.raises((ValueError, OSError)): api.verify_protected_continuity_file(row)
                with pytest.raises((ValueError, OSError)): verification._whole_inputs.get().verify()
                reparse_control(kernel, writer, 0x900AC, struct.pack('<LHH', 0xA0000003, 0, 0))
                installed = False
    finally:
        if installed:
            reparse_control(kernel, writer, 0x900AC, struct.pack('<LHH', 0xA0000003, 0, 0))
        close = kernel.CloseHandle; close.argtypes = [wintypes.HANDLE]; close.restype = wintypes.BOOL
        assert close(writer)


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
def test_immutable_source_pin_survives_later_nested_writer_and_thread(tmp_path):
    api = core(); root = tmp_path/'source'; root.mkdir()
    path = root/'file.bin'; path.write_bytes(b'original'); row = record(path)
    with verification.whole_input_protection():
        api.prepare_continuity_inputs([row], immutable_roots=[root])
        copied = copy_context()
        with verification.writable_validation_session(tmp_path):
            with verification.writable_validation_session(root):
                with ThreadPoolExecutor(max_workers=1) as executor:
                    assert executor.submit(copied.run, api.verify_protected_continuity_file, row).result()
                with pytest.raises(OSError): path.write_bytes(b'changed!')
        assert api.verify_protected_continuity_file(row)
    path.write_bytes(b'released')


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
def test_unlisted_native_entry_requires_parent_preparation(tmp_path):
    api = core(); path = tmp_path/'file.bin'; path.write_bytes(b'original'); row = record(path)
    with verification.whole_input_protection(), verification.validation_session():
        manifest.hash_file(path)
        assert api.verify_protected_continuity_file(row) is False
        api.prepare_continuity_inputs([row])
        assert api.verify_protected_continuity_file(row)


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
def test_directory_hidden_attribute_is_permitted_and_not_cached(tmp_path):
    import ctypes
    from ctypes import wintypes
    api = core(); path = tmp_path/'file.bin'; path.write_bytes(b'original'); row = record(path)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    set_attributes = kernel.SetFileAttributesW
    set_attributes.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    set_attributes.restype = wintypes.BOOL
    old = tmp_path.stat().st_file_attributes
    with verification.whole_input_protection():
        api.prepare_continuity_inputs([row])
        try:
            assert set_attributes(str(tmp_path), old | 2)
            assert api.verify_protected_continuity_file(row)
        finally:
            assert set_attributes(str(tmp_path), old)


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
def test_unqualified_parent_open_falls_back_and_releases_partial_ancestors(tmp_path):
    import ctypes
    from ctypes import wintypes
    api = core(); directory = tmp_path/'source'; directory.mkdir()
    path = directory/'file.bin'; path.write_bytes(b'original'); row = record(path)
    kernel, attributes_handle = reparse_writer(directory)
    # A preexisting DELETE-capable handle cannot coexist with a deny-delete
    # directory lease. All parents acquired before this miss must be released.
    blocker = kernel.CreateFileW(str(directory), 0x10000, 7, None, 3, 0x02200000, None)
    # Close the helper's attributes handle too; only DELETE sharing matters.
    close = kernel.CloseHandle; close.argtypes = [wintypes.HANDLE]; close.restype = wintypes.BOOL
    assert close(attributes_handle)
    assert blocker != ctypes.c_void_p(-1).value
    try:
        with verification.whole_input_protection():
            api.prepare_continuity_inputs([row])
            assert api.verify_protected_continuity_file(row) is False
            path.write_bytes(b'changed!')
            directory.rename(tmp_path/'released')
    finally:
        assert close(blocker)


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
def test_empty_directory_lease_itself_blocks_rename_delete_and_releases(tmp_path):
    api = core(); directory = tmp_path/'empty'; directory.mkdir()
    held = api._Directory(directory)
    try:
        with pytest.raises(OSError): directory.rename(tmp_path/'moved')
        with pytest.raises(OSError): directory.rmdir()
        held.verify(canonical=True)
    finally:
        held.close()
    directory.rename(tmp_path/'moved')
    (tmp_path/'moved').rmdir()


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
def test_prepare_existing_only_qualifies_an_already_live_native_entry(tmp_path):
    api = core(); path = tmp_path/'file.bin'; path.write_bytes(b'original'); row = record(path)
    with verification.whole_input_protection(), verification.validation_session():
        assert api.verify_protected_continuity_file(row, prepare_existing=True) is False
        path.write_bytes(b'changed!'); path.write_bytes(b'original'); row = record(path)
        manifest.hash_file(path)
        assert api.verify_protected_continuity_file(row, prepare_existing=True)
        with pytest.raises(OSError): tmp_path.rename(tmp_path.with_name(tmp_path.name + '-moved'))
        with verification.writable_validation_session(tmp_path):
            assert api.verify_protected_continuity_file(row, prepare_existing=True) is False
            path.write_bytes(b'changed!')


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
def test_prepare_existing_only_never_pins_owned_or_mutable_files(tmp_path):
    api = core(); path = tmp_path/'file.bin'; path.write_bytes(b'original'); row = record(path)
    with verification.writable_validation_session(tmp_path), verification.whole_input_protection():
        manifest.hash_file(path)
        assert api.verify_protected_continuity_file(row, prepare_existing=True) is False
        path.write_bytes(b'changed!')


@pytest.mark.skipif(os.name != 'nt', reason='Windows native sharing')
def test_prepare_existing_only_rejects_forged_native_identity(tmp_path):
    api = core(); path = tmp_path/'file.bin'; path.write_bytes(b'original'); row = record(path)
    with verification.whole_input_protection(), verification.validation_session():
        manifest.hash_file(path)
        with pytest.raises((ValueError, OSError)):
            api.verify_protected_continuity_file(replace(row, sha256='0'*64), prepare_existing=True)
        assert api.verify_protected_continuity_file(row, prepare_existing=True)


@pytest.mark.skipif(os.name != 'nt', reason='Windows native metadata')
def test_final_window_verification_checks_extra_source_pins_and_releases_on_error(tmp_path):
    import ctypes
    from ctypes import wintypes
    api = core(); path = tmp_path/'file.bin'; path.write_bytes(b'original'); row = record(path)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    set_attributes = kernel.SetFileAttributesW
    set_attributes.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    set_attributes.restype = wintypes.BOOL
    old = path.stat().st_file_attributes
    try:
        with pytest.raises(OSError):
            with verification.whole_input_protection():
                api.prepare_continuity_inputs([row])
                assert set_attributes(str(path), old | 2)
        assert set_attributes(str(path), old)
        path.write_bytes(b'released')
    finally:
        assert set_attributes(str(path), old)


@pytest.mark.skipif(os.name != 'nt', reason='Windows native handles')
def test_native_close_failure_still_releases_all_other_handles(tmp_path):
    api = core(); path = tmp_path/'file.bin'; path.write_bytes(b'original'); row = record(path)
    with pytest.raises(OSError):
        with verification.whole_input_protection():
            api.prepare_continuity_inputs([row])
            state = verification._whole_inputs.get().continuity
            directory = state.directories[tmp_path]
            # A real invalidated handle produces an actual native close error.
            assert directory.api.close(directory.handle)
    path.write_bytes(b'released')
    tmp_path.rename(tmp_path.with_name(tmp_path.name + '-released'))


@pytest.mark.skipif(os.name != 'nt', reason='Windows native metadata')
def test_writer_promotion_validates_extra_ordinary_pin_before_release(tmp_path):
    import ctypes
    from ctypes import wintypes
    api = core(); path = tmp_path/'file.bin'; path.write_bytes(b'original'); row = record(path)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    set_attributes = kernel.SetFileAttributesW
    set_attributes.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    set_attributes.restype = wintypes.BOOL
    old = path.stat().st_file_attributes
    try:
        with pytest.raises((ValueError, OSError)):
            with verification.whole_input_protection():
                api.prepare_continuity_inputs([row])
                assert set_attributes(str(path), old | 2)
                with verification.writable_validation_session(tmp_path):
                    pass
    finally:
        assert set_attributes(str(path), old)
    path.write_bytes(b'released')


@pytest.mark.skipif(os.name != 'nt', reason='Windows native metadata')
def test_failed_writer_promotion_does_not_lose_previously_validated_pin(tmp_path):
    import ctypes
    from ctypes import wintypes
    api = core(); first = tmp_path/'first.bin'; first.write_bytes(b'first')
    second = tmp_path/'second.bin'; second.write_bytes(b'second')
    rows = [record(first), record(second)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    set_attributes = kernel.SetFileAttributesW
    set_attributes.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    set_attributes.restype = wintypes.BOOL
    old = second.stat().st_file_attributes
    try:
        with pytest.raises((ValueError, OSError)):
            with verification.whole_input_protection():
                api.prepare_continuity_inputs(rows)
                assert set_attributes(str(second), old | 2)
                with verification.writable_validation_session(tmp_path):
                    pass
    finally:
        assert set_attributes(str(second), old)
    first.write_bytes(b'released')
    second.write_bytes(b'released')
    tmp_path.rename(tmp_path.with_name(tmp_path.name + '-released'))
