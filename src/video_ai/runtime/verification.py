"""Operation-local digest reuse protected by Windows mandatory file sharing.

No consumer verdicts are cached. Writes and submissions live outside these read
windows; mutable manifests only retain a lock during their complete digest.
Other platforms always perform full hashes.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import os

_current = ContextVar('video_ai_validation_session', default=None)
_MAX_PROTECTED_FILES = 256
_MODEL_SUFFIXES = frozenset(('.bin', '.ckpt', '.pth', '.pt', '.safetensors', '.gguf'))


def file_stamp(file):
    stat = os.fstat(file.fileno())
    change = stat.st_ctime_ns
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        import msvcrt
        class BasicInfo(ctypes.Structure):
            _fields_ = [('creation', ctypes.c_longlong), ('access', ctypes.c_longlong),
                        ('write', ctypes.c_longlong), ('change', ctypes.c_longlong),
                        ('attributes', wintypes.DWORD)]
        api = ctypes.WinDLL('kernel32', use_last_error=True).GetFileInformationByHandleEx
        api.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        api.restype = wintypes.BOOL
        info = BasicInfo()
        if not api(msvcrt.get_osfhandle(file.fileno()), 0, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        change = info.change
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, change


def check_path(path, file, stamp):
    stat = path.stat()
    if (path.resolve(strict=True) != path or file_stamp(file) != stamp
            or (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns) != stamp[:4]):
        raise OSError(f'file changed during verification: {path}')


def _locked_reader(path):
    import ctypes
    from ctypes import wintypes
    import msvcrt
    api = ctypes.WinDLL('kernel32', use_last_error=True).CreateFileW
    api.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                    ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.restype = wintypes.HANDLE
    handle = api(str(path), 0x80000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close = ctypes.WinDLL('kernel32', use_last_error=True).CloseHandle
        close.argtypes = [wintypes.HANDLE]; close.restype = wintypes.BOOL
        close(handle)
        raise
    return os.fdopen(descriptor, 'rb')


@contextmanager
def validation_session():
    """Share protected digests only through nested read consumers in this call."""
    if _current.get() is not None:
        yield
        return
    entries = {}
    token = _current.set(entries)
    try:
        yield
        for path, (file, stamp, identity) in entries.items():
            check_path(path, file, stamp)
    finally:
        _current.reset(token)
        for file, _, _ in entries.values():
            file.close()
        entries.clear()


def protected_hash(path, compute):
    entries = _current.get()
    if os.name != 'nt':
        with path.open('rb') as file:
            return compute(file, path)
    if entries is None or path.name.casefold() == 'manifest.json':
        with _locked_reader(path) as file:
            return compute(file, path)
    if path in entries:
        file, stamp, identity = entries[path]
        check_path(path, file, stamp)
        return identity
    # Small HTTP/JSON leaves are cheap to hash and can number in the tens of
    # thousands. Keep a bounded set of expensive leaves; the fallback performs
    # a fresh digest under a short-lived lock, never an unprotected hit. Windows
    # ChangeTime can remain equal across a fast write and restored mtime.
    if (len(entries) >= _MAX_PROTECTED_FILES or
            path.suffix.casefold() not in _MODEL_SUFFIXES and path.stat().st_size < 1024**2):
        with _locked_reader(path) as file:
            return compute(file, path)
    file = _locked_reader(path)
    try:
        identity = compute(file, path)
        stamp = file_stamp(file)
        check_path(path, file, stamp)
        entries[path] = file, stamp, identity
        return identity
    except BaseException:
        file.close()
        raise


def verified_read(function):
    @wraps(function)
    def consume(*args, **kwargs):
        with validation_session():
            return function(*args, **kwargs)
    return consume
