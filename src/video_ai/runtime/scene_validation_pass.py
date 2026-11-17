"""Bounded scene proofs inside one synchronous, independently flushed read.

This layer never acquires a file lease. It only interprets an already protected
Artifact once; ByteGuard still checks every unprotected auxiliary dependency.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from threading import get_ident
from time import monotonic

from . import _continuity_byte_guard as byte
from ._continuity_byte_guard import capture_reads
from . import _protected_continuity_inputs as protected
from .production_state import ProductionRefused

_scope = ContextVar('scene_validation_pass', default=None)
_MAX_ARTIFACTS = 4096
_MAX_EDGES = 65536
_candidate_guards = ContextVar('candidate_scene_validation', default=False)


@contextmanager
def candidate_scene_validation():
    """Offline experiment opt-in; measured default guards retain strict checks.

    LVA-02 reduced logical validations but regressed production-fixture wall
    time. Keep this candidate out of the default generation path.
    """
    token = _candidate_guards.set(True)
    try:
        yield
    finally:
        _candidate_guards.reset(token)


@contextmanager
def scene_guard_validation(*stores):
    with scene_validation_pass(reuse=_candidate_guards.get() and all(_ordinary(s) for s in stores)):
        yield


def _active():
    state = _scope.get()
    if (state is None or not state['active'] or not state['reuse']
            or state['thread'] != get_ident()):
        return None
    current = protected._current_read_pass()
    if (current is None or current is not state['read']
            or state['window'].read_generation != state['generation']):
        return None
    return state


@contextmanager
def scene_validation_pass(*, reuse=True):
    previous = _scope.get()
    if previous is not None:
        # Never reactivate a foreign, closed or invalidated context. A disabled
        # outer scope remains disabled even if a window is opened later.
        if reuse and _active() is not None:
            yield
            return
        reuse = False
    state = dict(active=True, reuse=reuse, thread=get_ident(), read=None,
                 window=None, generation=None, bindings={}, artifacts={},
                 paths={}, files=0, entries=0, inventories={}, additions=True)
    token = _scope.set(state)
    try:
        if not reuse:
            yield
        else:
            with protected.protected_read_pass(fresh=True):
                current = protected._current_read_pass()
                if current is not None:
                    state.update(read=current, window=current['window'],
                                 generation=current['window'].read_generation)
                yield
    finally:
        state['active'] = False
        for name in ('bindings', 'artifacts', 'paths', 'inventories'):
            state[name].clear()
        state['read'] = state['window'] = None
        _scope.reset(token)


def _refuse(state, exc):
    state['active'] = False
    state['artifacts'].clear()
    protected.fail_protected_read_pass()
    if isinstance(exc, byte.CaptureLimit):
        raise exc
    if isinstance(exc, ProductionRefused):
        raise exc
    if str(exc) == 'byte proof verification interval exceeded':
        raise exc
    raise ProductionRefused('cached scene validation proof changed') from exc


def _binding(store, strict):
    # Keep strong references, not ids vulnerable to reuse during the scope.
    return (type(store), store.frozen, store.run_dir, store.root,
            store.revision_context, getattr(strict, '__func__', strict))


def _same_binding(old, new):
    return (old[0] is new[0] and old[1] is new[1] and old[2:4] == new[2:4]
            and old[4] is new[4] and old[5] is new[5])


def _ordinary(store):
    # Origin views have non-byte admission obligations; keep them strict.
    from ._scene_revision_origin_images import _source_images
    from ._scene_revision_origin_clips import _scope as origins
    mode = getattr(getattr(store.frozen, 'config', None), 'raw', {}).get('scene_rendering', {}).get('mode')
    return (mode is None and store.revision_context is None
            and getattr(store, 'execution_mode', None) != 'temporal_extension_v1'
            and _source_images.get() is None and origins.get() is None)


def _lease(state, path):
    window = state['window']
    with window.lock:
        entry = window.entries.get(path)
        if entry is None and window.continuity is not None:
            entry = window.continuity.pins.get(path)
        return entry if entry is not None and entry.handle is not None else None


def validate_artifact_once(store, value, strict_validator):
    state = _active()
    if state is None:
        return strict_validator(value)
    binding = _binding(store, strict_validator)
    saved = state['bindings'].get(store)
    if saved is not None and not _same_binding(saved, binding):
        state['active'] = False
        raise ProductionRefused('scene validation store binding changed')
    if not _ordinary(store):
        return strict_validator(value)
    if (type(value) is not dict or set(value) != {'path', 'bytes', 'sha256'}
            or type(value['path']) is not str or type(value['bytes']) is not int
            or value['bytes'] < 1 or type(value['sha256']) is not str
            or len(value['sha256']) != 64
            or any(c not in '0123456789abcdef' for c in value['sha256'])):
        return strict_validator(value)
    path = Path(value['path'])
    if not path.is_absolute() or '..' in path.parts:
        return strict_validator(value)
    key = (store, value['path'], value['bytes'], value['sha256'])
    old_key = state['paths'].get((store, value['path']))
    if old_key is not None and old_key != key:
        state['active'] = False
        raise ProductionRefused('scene validation Artifact binding changed')
    found = state['artifacts'].get(key)
    entry = _lease(state, path)
    if found is not None:
        result, proof, original_entry = found
        if entry is not original_entry:
            _refuse(state, ProductionRefused('scene validation lease binding changed'))
        try:
            proof.verify()
            byte.replay_guard(proof)
        except byte.CaptureLimit:
            state['active'] = False
            raise
        except ValueError as exc:
            _refuse(state, exc)
        except BaseException:
            state['active'] = False
            state['artifacts'].clear()
            protected.fail_protected_read_pass()
            raise
        return result
    if (entry is None or not state['additions'] or byte._captures.get()
            or len(state['artifacts']) >= _MAX_ARTIFACTS
            or state['files'] >= _MAX_EDGES or state['entries'] >= _MAX_EDGES):
        return strict_validator(value)
    identity = entry.identity
    if (identity.path, identity.bytes, identity.sha256) != (value['path'], value['bytes'], value['sha256']):
        return strict_validator(value)
    try:
        with capture_reads() as capture:
            result = strict_validator(value)
        proof = capture.finish()
    except byte.CaptureLimit:
        # This capture was the only builder on entry and is now fully closed.
        if byte._captures.get():
            raise
        state['additions'] = False
        return strict_validator(value)
    if _active() is not state:
        return result
    files, entries = proof.file_count + proof.absence_count, proof.inventory_entry_count
    if state['files'] + files <= _MAX_EDGES and state['entries'] + entries <= _MAX_EDGES:
        state['bindings'][store] = binding
        state['paths'][(store, value['path'])] = key
        state['artifacts'][key] = (result, proof, entry)
        state['files'] += files
        state['entries'] += entries
    return result


def verify_inventory_once(directory, expected, *, recursive, strict_check):
    state = _active()
    if state is None:
        return strict_check()
    # Callers retain their lexical/path policy checks before this helper.
    spec = byte._Inventory(str(directory), 'revision_json' if recursive else 'json_direct',
                           tuple(sorted(str(p) for p in expected)), None)
    key = spec.path, spec.kind
    old = state['inventories'].get(key)
    if old is not None and old != spec:
        _refuse(state, ValueError('scene inventory binding changed'))
    if old is None and (len(state['inventories']) >= _MAX_ARTIFACTS
                        or state['entries'] + len(spec.expected) > _MAX_EDGES):
        return strict_check()
    from .execution_limits import execution_deadline
    try:
        protected.verify_read_inventory(spec, execution_deadline(300, monotonic()))
        byte.observe_inventory(directory, spec.kind, spec.expected)
    except byte.CaptureLimit:
        raise
    except ValueError as exc:
        # Preserve the caller's original refusal wording. A second scan is only
        # diagnostic on failure: even if it now succeeds, the first mismatch is
        # still refused and cannot establish a replacement baseline.
        state['active'] = False
        protected.fail_protected_read_pass()
        if str(exc) != 'byte proof verification interval exceeded':
            strict_check()
        _refuse(state, exc)
    if old is None:
        state['inventories'][key] = spec
        state['entries'] += len(spec.expected)
