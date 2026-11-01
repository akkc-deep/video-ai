"""Operation-local digest reuse protected by Windows mandatory file sharing.

Authenticated admission semantics may be memoized within one session; every hit
rehashes unprotected artifacts and checks directory inventories. Explicit scene
writers extend protected immutable-input handles over their invocation. Owned
run files and mutable manifests retain locks only during complete digests. Other platforms
always perform full hashes.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps, lru_cache
import os
from pathlib import Path
from threading import RLock

_current = ContextVar('video_ai_validation_session', default=None)
_memos = ContextVar('video_ai_validation_memos', default=None)
_writable_roots = ContextVar('video_ai_writable_validation_roots', default=())
_MAX_PROTECTED_FILES = 256
_MODEL_SUFFIXES = frozenset(('.bin', '.ckpt', '.pth', '.pt', '.safetensors', '.gguf'))
_whole_inputs = ContextVar('video_ai_whole_input_protection', default=None)
_MAX_WHOLE_INPUTS = 32768


@lru_cache(maxsize=1)
def _windows_input_api():
    import ctypes
    from ctypes import wintypes
    from types import SimpleNamespace
    library = ctypes.WinDLL('kernel32', use_last_error=True)
    class BasicInfo(ctypes.Structure):
        _fields_ = [('creation',ctypes.c_longlong), ('access',ctypes.c_longlong),
                    ('write',ctypes.c_longlong), ('change',ctypes.c_longlong),
                    ('attributes',wintypes.DWORD)]
    current = library.GetCurrentProcess
    current.argtypes = []; current.restype = wintypes.HANDLE
    duplicate = library.DuplicateHandle
    duplicate.argtypes = [wintypes.HANDLE,wintypes.HANDLE,wintypes.HANDLE,
                          ctypes.POINTER(wintypes.HANDLE),wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    duplicate.restype = wintypes.BOOL
    close = library.CloseHandle
    close.argtypes = [wintypes.HANDLE]; close.restype = wintypes.BOOL
    info = library.GetFileInformationByHandleEx
    info.argtypes = [wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    info.restype = wintypes.BOOL
    final = library.GetFinalPathNameByHandleW
    final.argtypes = [wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD]
    final.restype = wintypes.DWORD
    return SimpleNamespace(ctypes=ctypes, types=wintypes, library=library, BasicInfo=BasicInfo,
                           current=current, duplicate=duplicate, close=close, info=info, final=final)


class _NativeInput:
    """Duplicate the deny-write/delete handle, without retaining a CRT fd."""
    def __init__(self, path, file, stamp, identity):
        import msvcrt
        self.api = _windows_input_api()
        api = self.api; copied = api.types.HANDLE(); process = api.current()
        if not api.duplicate(process,msvcrt.get_osfhandle(file.fileno()),process,
                             api.ctypes.byref(copied),0,False,2):
            raise api.ctypes.WinError(api.ctypes.get_last_error())
        self.handle = copied.value
        try:
            self.stamp, self.identity = stamp, identity
            self.metadata = self._metadata()
            if self.metadata[0] != stamp[4]:
                raise OSError(f'file changed during verification: {path}')
            self.verify(path)
        except BaseException:
            self.close()
            raise

    def _metadata(self):
        api = self.api; value = api.BasicInfo()
        if not api.info(self.handle,0,api.ctypes.byref(value),api.ctypes.sizeof(value)):
            raise api.ctypes.WinError(api.ctypes.get_last_error())
        # AccessTime may change after another reader. It never authenticates bytes.
        return value.change, value.write, value.creation, value.attributes

    def _canonical_path(self):
        api = self.api; size = 512
        value = api.ctypes.create_unicode_buffer(size)
        length = api.final(self.handle,value,size,0)
        if not length:
            raise api.ctypes.WinError(api.ctypes.get_last_error())
        if length >= size:
            if length > 32768:
                raise OSError('canonical input path exceeds Windows limit')
            size = length+1; value = api.ctypes.create_unicode_buffer(size)
            length = api.final(self.handle,value,size,0)
            if not length or length >= size:
                raise OSError('canonical input path changed during verification')
        name = value.value
        if name.startswith('\\\\?\\UNC\\'): name = '\\\\'+name[8:]
        elif name.startswith('\\\\?\\'): name = name[4:]
        return Path(name)

    def verify(self, path):
        stat = path.stat()
        if ((stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns) != self.stamp[:4]
                or self._metadata() != self.metadata or self._canonical_path() != path):
            raise OSError(f'file changed during verification: {path}')

    def close(self):
        if self.handle is not None:
            handle, self.handle = self.handle, None
            if not self.api.close(handle):
                raise self.api.ctypes.WinError(self.api.ctypes.get_last_error())


class _WholeInputWindow:
    def __init__(self):
        self.entries = {}
        self.lock = RLock()
        self.closed = False
        self.writable_roots = {}
        self.continuity = None
        for root in _writable_roots.get():
            self.writable_roots[root] = self.writable_roots.get(root,0)+1

    def _owned(self, path):
        return any(path.is_relative_to(root) for root in self.writable_roots)

    def get(self, path):
        with self.lock:
            entry = None if self.closed or self._owned(path) else self.entries.get(path)
            if entry is not None:
                entry.verify(path)
                return entry.identity
        return None

    def hash(self, path, compute):
        found = self.get(path)
        if found is not None: return found
        with _locked_reader(path) as file:
            with self.lock:
                retain = not self.closed and not self._owned(path) and len(self.entries) < _MAX_WHOLE_INPUTS
            if not retain: return compute(file,path)
            before = file_stamp(file)
            identity = compute(file,path)
            if file_stamp(file) != before:
                raise OSError(f'file changed during verification: {path}')
            with self.lock:
                # A timed-out copied context must never populate a closed window.
                if self.closed or self._owned(path) or len(self.entries) >= _MAX_WHOLE_INPUTS:
                    return identity
                existing = self.entries.get(path)
                if existing is not None:
                    existing.verify(path)
                    return existing.identity
                self.entries[path] = _NativeInput(path,file,before,identity)
            return identity

    def enter_writer(self, root):
        with self.lock:
            if self.closed: return
            # This state is shared with earlier copy_context workers. Their
            # context-local writable-root tuples cannot see a later writer.
            self.writable_roots[root] = self.writable_roots.get(root,0)+1
            if self.continuity is not None:
                self.continuity.enter_writer(root)
            for path, entry in tuple(self.entries.items()):
                if path.is_relative_to(root):
                    entry.verify(path)
                    del self.entries[path]
                    entry.close()

    def leave_writer(self, root):
        with self.lock:
            count = self.writable_roots.get(root,0)
            if count > 1: self.writable_roots[root] = count-1
            else: self.writable_roots.pop(root,None)

    def verify(self):
        with self.lock:
            for path, entry in self.entries.items():
                entry.verify(path)
            if self.continuity is not None:
                self.continuity.verify()

    def close(self):
        with self.lock:
            self.closed = True
            entries = list(self.entries.values())
            if self.continuity is not None:
                entries.append(self.continuity)
                self.continuity = None
            self.entries.clear()
            self.writable_roots.clear()
        error = None
        for entry in entries:
            try: entry.close()
            except OSError as exc:
                if error is None: error = exc
        if error is not None: raise error


@contextmanager
def whole_input_protection():
    """Scope native read protection to an explicit whole-scene operation.

    Only a complete first digest under mandatory deny-write/delete sharing can
    enter this window. Every reuse checks the live handle metadata, canonical
    handle path and path identity. Unprotected and owned files always rehash.
    """
    current = _whole_inputs.get()
    if current is not None and not current.closed:
        yield
        return
    window = _WholeInputWindow()
    token = _whole_inputs.set(window)
    try:
        yield
        window.verify()
    finally:
        _whole_inputs.reset(token)
        window.close()


def _whole_cached_identity(path):
    window = _whole_inputs.get()
    if (os.name != 'nt' or window is None or _current.get() is None
            or not isinstance(path,Path) or path.name.casefold() == 'manifest.json'
            or any(path.is_relative_to(root) for root in _writable_roots.get())):
        return None
    # Only an already canonical, still-live protected entry can skip a fresh
    # path open. Relative names and aliases miss and take the original path.
    return window.get(path)


def validation_memo(namespace):
    """Return this read operation's namespace, or None outside a read session.

    Authenticated structures may be reused here only when their consumer still
    rechecks original byte and directory guards on every access.
    """
    memos=_memos.get()
    return None if memos is None else memos.setdefault(namespace,{})


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
    memos = {}
    memo_token = _memos.set(memos)
    try:
        yield
        for path, (file, stamp, identity) in entries.items():
            check_path(path, file, stamp)
    finally:
        _current.reset(token)
        _memos.reset(memo_token)
        memos.clear()
        for file, _, _ in entries.values():
            file.close()
        entries.clear()


@contextmanager
def writable_validation_session(root):
    """Keep external input handles while fully rehashing this writer's files.

    Owned staging files must be movable after hashing. They retain mandatory
    read sharing during each complete digest, but no handle beyond that digest.
    Nested writer roots are scoped independently and restored on every exit.
    """
    root=Path(root).resolve(strict=True)
    token=_writable_roots.set((*_writable_roots.get(),root))
    window=None
    try:
        with validation_session():
            window = _whole_inputs.get()
            if window is not None: window.enter_writer(root)
            # A writer may be entered from a larger read validation. Recheck
            # and release any already-protected owned files before promotion;
            # external/ancestor inputs keep their existing mandatory handles.
            entries=_current.get()
            for path,(file,stamp,identity) in tuple(entries.items()):
                if path.is_relative_to(root):
                    check_path(path,file,stamp)
                    del entries[path]
                    file.close()
            yield
    finally:
        try:
            if window is not None: window.leave_writer(root)
            # A window may have been created inside this already-active writer.
            current = _whole_inputs.get()
            if current is not None and current is not window: current.leave_writer(root)
        finally:_writable_roots.reset(token)


def protected_hash(path, compute):
    entries = _current.get()
    if os.name != 'nt':
        with path.open('rb') as file:
            return compute(file, path)
    if (entries is None or path.name.casefold() == 'manifest.json'
            or any(path.is_relative_to(root) for root in _writable_roots.get())):
        with _locked_reader(path) as file:
            return compute(file, path)
    if path in entries:
        file, stamp, identity = entries[path]
        check_path(path, file, stamp)
        return identity
    window = _whole_inputs.get()
    if window is not None:
        return window.hash(path,compute)
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
