"""Immutable read dependencies from one successful continuity admission.

Observation is opt-in and context-local. Proofs retain data only, so a copied
HTTP context can check them without retaining an admission reader or deadline.
"""
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
import stat
from threading import RLock
from time import monotonic


class CaptureLimit(ValueError):
    """The complete dependency set cannot fit in the configured capture."""


_captures = ContextVar('continuity_byte_captures', default=())
_KINDS = frozenset(('children', 'json_direct', 'assessment_paths', 'job_intents',
                    'nonempty_files', 'revision_json', 'whole_files',
                    'continuity_sources'))


def _safe(path):
    # Imports must remain lazy: manifest.hash_file is itself an observation site.
    from .paths import _validate_spelling
    from .scene_revision_records import safe_path
    path = Path(_validate_spelling(path))
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('byte proof requires canonical absolute paths')
    safe_path(path, path.anchor)
    if path.resolve(strict=False) != path:
        raise ValueError('byte proof rejects path aliases')
    return path


def _ownership(metadata):
    return (metadata.st_dev, metadata.st_ino, metadata.st_nlink,
            getattr(metadata, 'st_uid', None), getattr(metadata, 'st_gid', None))


@dataclass(frozen=True, slots=True)
class _File:
    path: str
    bytes: int
    mtime_ns: int
    sha256: str
    verified_at: str
    ownership: tuple

    def key(self):
        return self.path, self.bytes, self.mtime_ns, self.sha256, self.ownership


@dataclass(frozen=True, slots=True)
class _Inventory:
    path: str
    kind: str
    expected: tuple[str, ...]
    pattern: str | None


def _check_time(deadline):
    if monotonic() >= deadline:
        raise ValueError('byte proof verification interval exceeded')


def _assessment_paths(root, deadline, name='assessment.json'):
    # glob('*/assessment.json') can enter a junction before yielding a match.
    # Check the first level before asking pathlib to enumerate the second.
    from .scene_revision_records import safe_path
    for directory in root.glob('*'):
        _check_time(deadline)
        safe_path(directory, root)
        _check_time(deadline)
        is_directory = directory.is_dir()
        _check_time(deadline)
        if is_directory:
            yield from directory.glob(name)
    _check_time(deadline)


def _reject_redirected_descendants(root, deadline):
    # EvidenceReader checks matching files and their ancestors, but an empty
    # redirected directory has no matching file. Prune exclusions before the
    # top-down walk descends, and check each included entry before descent.
    excluded = {'.git', '__pycache__'}
    if not excluded.intersection(root.parts):
        for directory, folders, files in root.walk():
            _check_time(deadline)
            folders[:] = [name for name in folders if name not in excluded]
            for name in (*folders, *files):
                if name in excluded:
                    continue
                _check_time(deadline)
                metadata = (directory / name).lstat()
                _check_time(deadline)
                if (stat.S_ISLNK(metadata.st_mode)
                        or getattr(metadata, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                    raise ValueError('redirected byte proof inventory path')
    _check_time(deadline)


def _scan(spec, deadline):
    from .scene_revision_records import safe_path
    root = _safe(spec.path)
    _check_time(deadline)
    if spec.kind == 'whole_files':
        from ._whole_scene_admission import EvidenceReader
        _reject_redirected_descendants(root, deadline)
        _check_time(deadline)
        # Preserve the admission scanner's exclusions, matching, and same-scan
        # ancestor optimization. The temporary reader never enters the proof.
        paths = EvidenceReader().inventory(root, spec.pattern or '*')
    elif spec.kind == 'children':
        paths = root.iterdir()
    elif spec.kind == 'json_direct':
        paths = root.glob('*.json')
    elif spec.kind == 'assessment_paths':
        paths = _assessment_paths(root, deadline)
    elif spec.kind == 'job_intents':
        paths = _assessment_paths(root, deadline, 'intent.json')
    elif spec.kind == 'continuity_sources':
        paths = root.glob('*continuity*.py')
    else:
        paths = root.rglob('*')
    items = []
    for path in paths:
        _check_time(deadline)
        path = Path(path)
        # EvidenceReader already checks matched files and distinct ancestors
        # within its scan; do not undo that optimization with repeated walks.
        if spec.kind != 'whole_files':
            safe_path(path, root)
            _check_time(deadline)
        if spec.kind == 'nonempty_files':
            is_file = path.is_file()
            _check_time(deadline)
            if not is_file:
                continue
            size = path.stat().st_size
            _check_time(deadline)
            if size <= 0:
                continue
        elif spec.kind == 'revision_json' and not path.match('*.json'):
            continue
        items.append(str(path))
        if len(items) > len(spec.expected):
            raise ValueError('byte proof directory inventory changed: ' + spec.path)
    _check_time(deadline)
    _safe(root)
    _check_time(deadline)
    return tuple(sorted(items))


@dataclass(frozen=True, slots=True)
class ByteGuard:
    """A data-only snapshot; verify never changes its original baseline."""
    files: tuple[_File, ...]
    inventories: tuple[_Inventory, ...]
    absences: tuple[str, ...]

    @property
    def file_count(self):
        return len(self.files)

    @property
    def inventory_count(self):
        return len(self.inventories)

    @property
    def inventory_entry_count(self):
        return sum(len(spec.expected) for spec in self.inventories)

    @property
    def absence_count(self):
        return len(self.absences)

    def verify(self):
        from .manifest import hash_file
        from ._protected_continuity_inputs import verify_protected_continuity_file
        deadline = monotonic() + 300.0
        token = _captures.set(())
        try:
            for baseline in self.files:
                _check_time(deadline)
                if verify_protected_continuity_file(baseline):
                    _check_time(deadline)
                    continue
                path = _safe(baseline.path)
                _check_time(deadline)
                before = path.stat()
                if (not stat.S_ISREG(before.st_mode)
                        or _ownership(before) != baseline.ownership
                        or (before.st_size, before.st_mtime_ns) != (baseline.bytes, baseline.mtime_ns)):
                    raise ValueError('byte proof file ownership or metadata changed: ' + baseline.path)
                _check_time(deadline)
                actual = hash_file(path)
                _check_time(deadline)
                path = _safe(path)
                _check_time(deadline)
                after = path.stat()
                if ((actual.path, actual.bytes, actual.mtime_ns, actual.sha256)
                        != (baseline.path, baseline.bytes, baseline.mtime_ns, baseline.sha256)
                        or _ownership(after) != baseline.ownership
                        or (after.st_size, after.st_mtime_ns) != (baseline.bytes, baseline.mtime_ns)):
                    raise ValueError('byte proof file changed: ' + baseline.path)
            for spec in self.inventories:
                _check_time(deadline)
                if _scan(spec, deadline) != spec.expected:
                    raise ValueError('byte proof directory inventory changed: ' + spec.path)
                _check_time(deadline)
            for name in self.absences:
                _check_time(deadline)
                path = _safe(name)
                _check_time(deadline)
                if path.exists():
                    raise ValueError('byte proof absent path appeared: ' + name)
            _check_time(deadline)
        finally:
            _captures.reset(token)


class Capture:
    """Synchronized, bounded builder, inaccessible from the emitted proof."""
    def __init__(self, maximum_files, maximum_inventory_entries):
        self._maximum_files = maximum_files
        self._maximum_inventory_entries = maximum_inventory_entries
        self._files = {}
        self._inventories = {}
        self._absences = set()
        self._inventory_entries = 0
        self._lock = RLock()
        self._closed = False
        self._failed = False
        self._guard = None

    def _close(self, successful):
        with self._lock:
            self._closed = True
            if successful and not self._failed:
                self._guard = ByteGuard(
                    tuple(self._files[key] for key in sorted(self._files)),
                    tuple(self._inventories[key] for key in sorted(self._inventories)),
                    tuple(sorted(self._absences)))
            self._files.clear()
            self._inventories.clear()
            self._absences.clear()

    def finish(self):
        with self._lock:
            if not self._closed or self._guard is None:
                raise ValueError('byte capture requires successful scope closure')
            return self._guard


@contextmanager
def capture_reads(*, maximum_files=32768, maximum_inventory_entries=65536):
    for value in (maximum_files, maximum_inventory_entries):
        if type(value) is not int or value < 0:
            raise ValueError('byte capture limits require nonnegative integers')
    capture = Capture(maximum_files, maximum_inventory_entries)
    token = _captures.set((*_captures.get(), capture))
    successful = False
    try:
        yield capture
        successful = True
    finally:
        _captures.reset(token)
        capture._close(successful)


@contextmanager
def _builders():
    with ExitStack() as stack:
        # Parent-first locking is consistent across nested and copied contexts.
        active = []
        for capture in _captures.get():
            stack.enter_context(capture._lock)
            if not capture._closed:
                active.append(capture)
        try:
            yield active
        except BaseException:
            # Even a caught observation error must never emit a partial proof.
            for capture in active:
                capture._failed = True
            raise


def observe_file(identity):
    if not _captures.get():
        return
    with _builders() as captures:
        if not captures:
            return
        from .manifest import FileIdentity
        if isinstance(identity, FileIdentity):
            values = {name: getattr(identity, name) for name in
                      ('path', 'bytes', 'mtime_ns', 'sha256', 'verified_at')}
        elif isinstance(identity, dict) and set(identity) == {'path', 'bytes', 'mtime_ns', 'sha256', 'verified_at'}:
            values = dict(identity)
        else:
            raise ValueError('byte capture requires a complete FileIdentity')
        for name in ('bytes', 'mtime_ns'):
            if type(values[name]) is not int or values[name] < 0:
                raise ValueError('byte capture requires complete numeric identity fields')
        digest = values['sha256']
        if (not isinstance(digest, str) or len(digest) != 64
                or any(c not in '0123456789abcdef' for c in digest)
                or not isinstance(values['verified_at'], str)):
            raise ValueError('byte capture requires complete SHA256 and verification fields')
        # Repeated observations may reuse only continuously held native file
        # and ancestor objects. Live parent attributes are checked on every
        # reuse; unprotected/owned reads retain the exact strict fallback.
        old_rows = [capture._files.get(str(values['path'])) for capture in captures]
        if all(row is not None for row in old_rows):
            first=old_rows[0]
            actual_key=(str(values['path']),values['bytes'],values['mtime_ns'],digest)
            for row in old_rows:
                if ((row.path,row.bytes,row.mtime_ns,row.sha256)!=actual_key
                        or row.ownership!=first.ownership):
                    raise ValueError('conflicting observed file identity')
            from ._protected_continuity_inputs import verify_protected_continuity_file
            if verify_protected_continuity_file(first,prepare_existing=True):return
        path = _safe(values['path'])
        metadata = path.lstat()
        if (not stat.S_ISREG(metadata.st_mode)
                or (metadata.st_size, metadata.st_mtime_ns) != (values['bytes'], values['mtime_ns'])):
            raise ValueError('observed file metadata changed')
        row = _File(str(path), values['bytes'], values['mtime_ns'], digest,
                    values['verified_at'], _ownership(metadata))
        for capture in captures:
            old = capture._files.get(row.path)
            if row.path in capture._absences or (old is not None and old.key() != row.key()):
                raise ValueError('conflicting observed file identity')
            if old is None and len(capture._files) >= capture._maximum_files:
                raise CaptureLimit('byte capture file limit exceeded')
        for capture in captures:
            capture._files.setdefault(row.path, row)


def observe_inventory(path, kind, expected, *, pattern=None):
    if not _captures.get():
        return
    with _builders() as captures:
        if not captures:
            return
        root = _safe(path)
        if kind not in _KINDS:
            raise ValueError('unknown byte capture inventory kind')
        if pattern is not None and (kind != 'whole_files' or not isinstance(pattern, str)):
            raise ValueError('pattern requires a whole_files inventory')
        pattern = (pattern or '*') if kind == 'whole_files' else None
        key = str(root), kind, pattern or ''
        capacity = min(
            capture._maximum_inventory_entries - capture._inventory_entries
            + (len(capture._inventories[key].expected) if key in capture._inventories else 0)
            for capture in captures)
        names = []
        for value in expected:
            if len(names) >= capacity:
                raise CaptureLimit('byte capture inventory entry limit exceeded')
            name = _safe(value)
            if not name.is_relative_to(root):
                raise ValueError('inventory entry escapes root')
            names.append(str(name))
        row = _Inventory(str(root), kind, tuple(sorted(names)), pattern)
        for capture in captures:
            old = capture._inventories.get(key)
            if old is not None and old != row:
                raise ValueError('conflicting observed inventory')
            # Empty inventories also consume bounded builder space.
            if old is None and len(capture._inventories) >= capture._maximum_files:
                raise CaptureLimit('byte capture directory specification limit exceeded')
        for capture in captures:
            if key not in capture._inventories:
                capture._inventories[key] = row
                capture._inventory_entries += len(names)


def observe_absence(path):
    if not _captures.get():
        return
    with _builders() as captures:
        if not captures:
            return
        path = _safe(path)
        if path.exists():
            raise ValueError('observed absent path already exists')
        name = str(path)
        for capture in captures:
            if name in capture._files:
                raise ValueError('conflicting observed absence')
            if name not in capture._absences and len(capture._absences) >= capture._maximum_files:
                raise CaptureLimit('byte capture absence limit exceeded')
        for capture in captures:
            capture._absences.add(name)
