"""Invocation-local native leases for already admitted continuity records.

No handles escape the whole-input window. Directory handles exclude rename and
deletion, but do not freeze reparse attributes: those are read on every check.
"""
import hashlib
import os
from pathlib import Path
import stat
from types import SimpleNamespace

_MAX_SOURCE_PINS = 32768
_MAX_DIRECTORIES = 65536
_MAX_RECORDS = 32768


def _ownership(value):
    return (value.st_dev, value.st_ino, value.st_nlink,
            getattr(value, 'st_uid', None), getattr(value, 'st_gid', None))


def _key(record):
    return (record.path, record.bytes, record.mtime_ns, record.sha256,
            tuple(record.ownership))


def _matches(path, metadata, expected):
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_size != expected[1]
            or metadata.st_mtime_ns != expected[2]
            or _ownership(metadata) != expected[4]):
        raise ValueError(f'protected continuity file changed: {path}')


def _identity(entry, expected):
    value = entry.identity
    if (value.path, value.bytes, value.mtime_ns, value.sha256) != expected[:4]:
        raise ValueError(f'protected continuity identity changed: {expected[0]}')


class _Directory:
    def __init__(self, path):
        from .verification import _windows_input_api
        self.api = _windows_input_api()
        api = self.api
        create = api.library.CreateFileW
        create.argtypes = [api.types.LPCWSTR, api.types.DWORD, api.types.DWORD,
                           api.ctypes.c_void_p, api.types.DWORD, api.types.DWORD,
                           api.types.HANDLE]
        create.restype = api.types.HANDLE
        # GENERIC_READ participates in Windows sharing enforcement; an
        # attributes-only handle does not reliably exclude DELETE access.
        # Share readers/writers, never deletion, and open the directory itself
        # so a setup race cannot follow a junction.
        handle = create(str(path), 0x80000000, 3, None, 3, 0x02200000, None)
        if handle == api.ctypes.c_void_p(-1).value:
            raise api.ctypes.WinError(api.ctypes.get_last_error())
        self.handle, self.path = handle, path
        try:
            self.verify(canonical=True)
        except BaseException:
            self.close()
            raise

    def verify(self, *, canonical=False):
        from .verification import _NativeInput
        api = self.api; value = api.BasicInfo()
        if not api.info(self.handle, 0, api.ctypes.byref(value), api.ctypes.sizeof(value)):
            raise api.ctypes.WinError(api.ctypes.get_last_error())
        if value.attributes & 0x400 or not value.attributes & 0x10:
            raise ValueError(f'protected continuity directory redirected: {self.path}')
        if canonical and _NativeInput._canonical_path(self) != self.path:
            raise ValueError(f'protected continuity directory alias: {self.path}')

    def close(self):
        if self.handle is not None:
            handle, self.handle = self.handle, None
            if not self.api.close(handle):
                raise self.api.ctypes.WinError(self.api.ctypes.get_last_error())


def _close_all(entries):
    error = None
    for entry in entries:
        try:
            entry.close()
        except OSError as exc:
            if error is None:
                error = exc
    if error is not None:
        raise error


class _Protection:
    """All methods are serialized by the owning window's RLock."""
    def __init__(self, window):
        self.window = window
        self.pins = {}
        self.directories = {}
        self.records = {}
        self.immutable_pins = set()

    def enter_writer(self, root):
        # Ordinary read entries retain the established writer lifecycle. Only
        # explicitly authorized immutable source pins survive a nested writer.
        released = []
        paths = tuple(path for path in self.records
                      if path.is_relative_to(root) and path not in self.immutable_pins)
        # Validate the entire release set before removing any ownership: a
        # failure on a later row must leave earlier handles available to close.
        for path in paths:
            entry = self.pins.get(path) or self.window.entries.get(path)
            if entry is None or entry.handle is None:
                raise OSError(f'protected continuity lease lost: {path}')
            self._verify(path, self.records[path], entry)
        for path in paths:
            del self.records[path]
            entry = self.pins.pop(path, None)
            if entry is not None:
                released.append(entry)
        needed = {parent for path in self.records for parent in path.parents}
        for parent in tuple(self.directories):
            if parent not in needed:
                released.append(self.directories.pop(parent))
        _close_all(released)

    def _parents(self, path):
        return tuple(self.directories[parent] for parent in reversed(path.parents))

    def _verify(self, path, expected, entry):
        parents = self._parents(path)
        for parent in parents:
            parent.verify()
        before = path.stat()
        _matches(path, before, expected)
        if before.st_nlink != 1:
            raise ValueError(f'protected continuity hardlink changed: {path}')
        _identity(entry, expected)
        entry.verify(path)
        _matches(path, path.stat(), expected)
        for parent in parents:
            parent.verify()

    def prepare(self, record, roots, *, existing_only=False):
        from ._continuity_byte_guard import _safe
        from .verification import _NativeInput, _locked_reader, file_stamp, check_path
        expected = _key(record)
        path = Path(expected[0])
        if path in self.records:
            if expected != self.records[path]:
                raise ValueError(f'protected continuity baseline changed: {path}')
            self.verify_record(record)
            return
        if expected[4][2] != 1 or len(self.records) >= _MAX_RECORDS:
            return
        if self.window._owned(path) and not any(path.is_relative_to(root) for root in roots):
            return
        entry = self.window.entries.get(path) or self.pins.get(path)
        if existing_only and (entry is None or entry.handle is None):
            return
        if entry is None and len(self.pins) >= _MAX_SOURCE_PINS:
            return
        ancestors = tuple(reversed(path.parents))
        missing = tuple(parent for parent in ancestors if parent not in self.directories)
        if len(self.directories) + len(missing) > _MAX_DIRECTORIES:
            return
        # Strict policy is used once for admission, before any optimization.
        if _safe(path) != path:
            raise ValueError('protected continuity path is not canonical')
        _matches(path, path.stat(), expected)
        pending = {}
        new_entry = None
        committed = False
        try:
            for parent in ancestors:
                held = self.directories.get(parent)
                if held is None:
                    # Native open unavailability is an optimization miss.
                    # Qualification failures remain explicit refusals.
                    try:
                        held = _Directory(parent)
                    except OSError:
                        return
                    pending[parent] = held
                held.verify(canonical=True)
            # Recheck strict spelling under the entire anchored chain.
            _safe(path)
            for held in (*self.directories_for(ancestors), *pending.values()):
                held.verify()
            if entry is None:
                try:
                    reader = _locked_reader(path)
                except OSError:
                    return
                with reader as file:
                    before = file_stamp(file)
                    _matches(path, os.fstat(file.fileno()), expected)
                    _matches(path, path.stat(), expected)
                    digest = hashlib.file_digest(file, 'sha256').hexdigest()
                    check_path(path, file, before)
                    _matches(path, os.fstat(file.fileno()), expected)
                    _matches(path, path.stat(), expected)
                    if digest != expected[3]:
                        raise ValueError(f'protected continuity SHA changed: {path}')
                    identity = SimpleNamespace(path=expected[0], bytes=expected[1],
                                               mtime_ns=expected[2], sha256=digest)
                    new_entry = _NativeInput(path, file, before, identity)
                    entry = new_entry
            _identity(entry, expected)
            entry.verify(path)
            _matches(path, path.stat(), expected)
            for parent in ancestors:
                (self.directories.get(parent) or pending[parent]).verify(canonical=True)
            self.directories.update(pending)
            if new_entry is not None:
                self.pins[path] = new_entry
                if any(path.is_relative_to(root) for root in roots):
                    self.immutable_pins.add(path)
            self.records[path] = expected
            committed = True
        finally:
            if not committed:
                _close_all(([new_entry] if new_entry is not None else []) + list(pending.values()))

    def directories_for(self, ancestors):
        return tuple(self.directories[parent] for parent in ancestors if parent in self.directories)

    def verify_record(self, record):
        path = Path(record.path)
        expected = self.records.get(path)
        if expected is None:
            return False
        if _key(record) != expected:
            raise ValueError(f'protected continuity baseline changed: {path}')
        entry = self.pins.get(path) or self.window.entries.get(path)
        if entry is None or entry.handle is None:
            return False
        if any(parent not in self.directories for parent in path.parents):
            return False
        self._verify(path, expected, entry)
        return True

    def verify(self):
        for path, expected in self.records.items():
            entry = self.pins.get(path) or self.window.entries.get(path)
            if entry is None or entry.handle is None:
                raise OSError(f'protected continuity lease lost: {path}')
            self._verify(path, expected, entry)

    def close(self):
        entries = [*self.pins.values(), *self.directories.values()]
        self.records.clear()
        self.immutable_pins.clear()
        self.pins.clear()
        self.directories.clear()
        _close_all(entries)


def prepare_continuity_inputs(records, *, immutable_roots=()):
    """Pin only supplied admitted records; unsupported protection stays strict."""
    from . import verification
    window = verification._whole_inputs.get()
    if verification.os.name != 'nt' or window is None:
        return
    with window.lock:
        if window.closed:
            return
        roots = tuple(Path(root) for root in immutable_roots)
        if window.continuity is None:
            window.continuity = _Protection(window)
        for index, record in enumerate(records):
            if index >= _MAX_RECORDS:
                break
            window.continuity.prepare(record, roots)


def verify_protected_continuity_file(record, *, prepare_existing=False):
    """Check a live lease; optionally anchor an already held native entry.

    ``prepare_existing`` only qualifies existing physical protection. It never
    hashes, opens a new source pin, or establishes semantic ready admission.
    """
    from . import verification
    window = verification._whole_inputs.get()
    if verification.os.name != 'nt' or window is None:
        return False
    with window.lock:
        if window.closed:
            return False
        if prepare_existing:
            if window.continuity is None:
                window.continuity = _Protection(window)
            if Path(record.path) not in window.continuity.records:
                window.continuity.prepare(record, (), existing_only=True)
        if window.continuity is None:
            return False
        return window.continuity.verify_record(record)
