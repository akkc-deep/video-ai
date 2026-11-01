"""Exact coverage of duplicated, already admitted media input obligations.

The source callback still checks its complete immutable byte proof on every
write/send. This module only proves when execution/revision checks describe a
subset of that same proof. Unknown or changed validator contracts stay strict.
"""
from dataclasses import dataclass
from pathlib import Path
from ._continuity_byte_guard import ByteGuard, CaptureLimit, capture_reads
from .manifest import thaw
from ..planning.production_scenes import canonical_digest


class _Unsupported(ValueError):
    pass


@dataclass(frozen=True)
class _ReadyTag:
    callback: object
    proof: ByteGuard


def _tag_ready_continuity_guard(callback, proof):
    if type(proof) is not ByteGuard or not proof.files or not callable(callback):
        raise ValueError('complete ready byte proof required')
    callback._ready_media_byte_guard = _ReadyTag(callback, proof)


def _frozen_contract(frozen):
    return dict(options=thaw(frozen.options), raw=thaw(frozen.config.raw))


def _original_method(method, module, qualname):
    return (getattr(method,'__module__',None)==module.__name__
        and getattr(method,'__qualname__',None)==qualname
        and getattr(method,'__code__',None) is not None
        and Path(method.__code__.co_filename)==Path(module.__file__))


def _reader_contract(reader, active=None, budget=None):
    from . import _whole_scene_admission as implementation
    from ._whole_scene_admission import EvidenceReader
    active = set() if active is None else active
    budget = [64] if budget is None else budget
    if type(reader) is not EvidenceReader or reader.reader is not None:
        raise _Unsupported('unknown whole evidence guard')
    methods=('verify','inventory','capture','raw','json','linked')
    if (any(name in reader.__dict__ for name in methods)
            or any(not _original_method(getattr(EvidenceReader,name),implementation,
                       'EvidenceReader.'+name) for name in methods)):
        raise _Unsupported('custom whole evidence validator')
    if id(reader) in active or budget[0] <= 0:
        raise _Unsupported('cyclic or oversized whole guard graph')
    budget[0] -= 1; active.add(id(reader))
    try:
        return dict(artifacts=reader.artifacts,methods=[id(getattr(EvidenceReader,name)) for name in methods],
            inventories=sorted((str(path), pattern, tuple(items))
                               for (path, pattern), items in reader.inventories.items()),
            guards=[_reader_contract(child, active, budget) for child in reader.guards])
    finally:
        active.remove(id(reader))


class WholeExecutionCheck:
    """The unchanged whole media execution check with an explicit data binding."""
    def __init__(self, store, frozen, budget_artifact):
        self.store, self.frozen = store, frozen
        self.budget_artifact = budget_artifact
        self.admission_guard = None

    def __call__(self):
        from .scene_clip_records import equal
        from .scene_execution_records import verify_whole_scene_frozen
        equal(self.store.artifact(self.budget_artifact['path']), self.budget_artifact,
              'media execution budget')
        evidence = verify_whole_scene_frozen(self.frozen)
        self.admission_guard = evidence['guard']

    def contract(self):
        from .scene_execution_records import cached_whole_scene_admission_guard
        if cached_whole_scene_admission_guard(self.frozen) is not self.admission_guard:
            raise _Unsupported('whole admission cache binding changed')
        return dict(frozen=_frozen_contract(self.frozen), budget=self.budget_artifact,
                    admission_identity=id(self.admission_guard),
                    admission=_reader_contract(self.admission_guard))


def _known_execution(execution):
    import sys
    methods=('__call__','contract')
    return (type(execution) is WholeExecutionCheck
        and not any(name in execution.__dict__ for name in methods)
        and all(_original_method(getattr(WholeExecutionCheck,name),sys.modules[__name__],
                    'WholeExecutionCheck.'+name) for name in methods))


def _revision_contract(guard, shared_admission, active=None, budget=None):
    from . import scene_revision_records as implementation
    from .scene_revision_records import RevisionGuard
    active = set() if active is None else active
    budget = [64] if budget is None else budget
    if type(guard) is not RevisionGuard:
        raise _Unsupported('unknown revision validator')
    methods=('verify_frozen','verify_captured_bytes')
    if (any(name in guard.__dict__ for name in methods)
            or any(not _original_method(getattr(RevisionGuard,name),implementation,
                       'RevisionGuard.'+name) for name in methods)):
        raise _Unsupported('custom revision validator')
    if id(guard) in active or budget[0] <= 0:
        raise _Unsupported('cyclic or oversized revision graph')
    budget[0] -= 1; active.add(id(guard))
    try:
        whole=guard.frozen.options.get('config_snapshot',{}).get('raw',{}).get('scene_rendering',{}).get('mode')=='whole_scene_v1'
        if whole:
            from .scene_execution_records import cached_whole_scene_admission_guard
            if cached_whole_scene_admission_guard(guard.frozen) is not shared_admission:
                raise _Unsupported('revision whole admission is not the bound execution graph')
        return dict(frozen=_frozen_contract(guard.frozen), options_sha256=guard.options_sha256,
            methods=[id(getattr(RevisionGuard,name)) for name in methods],
            whole_admission_identity=id(shared_admission) if whole else None,
            files=guard.files, directories=guard.directories, absent=guard.absent, views=guard.views,
            ancestors=[_revision_contract(parent, shared_admission, active, budget) for parent in guard.ancestors])
    finally:
        active.remove(id(guard))


def _proof_covers(full, required):
    if type(full) is not ByteGuard or type(required) is not ByteGuard:
        return False
    files = {row.path: row.key() for row in full.files}
    if len(files) != len(full.files) or len({row.path for row in required.files}) != len(required.files):
        return False
    return (all(files.get(row.path) == row.key() for row in required.files)
        and set(required.inventories) <= set(full.inventories)
        and set(required.absences) <= set(full.absences))


def media_checks_covered(store):
    certificate = getattr(store, '_media_check_coverage', None)
    return type(certificate) is _Coverage and certificate.applies(store)


def _contract(execution, revision):
    if not _known_execution(execution):raise _Unsupported('custom execution validator')
    return canonical_digest(dict(execution=execution.contract(),
        methods=[id(WholeExecutionCheck.__call__),id(WholeExecutionCheck.contract)],
        revision=None if revision is None else _revision_contract(revision,execution.admission_guard)))


@dataclass(frozen=True)
class _Coverage:
    callback: object
    tag: _ReadyTag
    execution: WholeExecutionCheck
    revision: object
    frozen: object
    run_dir: object
    contract_sha256: str

    def applies(self, store):
        try:
            revision = None if store.revision_context is None else store.revision_context['guard']
            return (store.frozen is self.frozen and store.run_dir == self.run_dir
                and store.execution_guard is self.execution and revision is self.revision
                and store.continuity_check is self.callback
                and store.continuity_read_guard is self.callback
                and getattr(self.callback, '_ready_media_byte_guard', None) is self.tag
                and _contract(self.execution, revision) == self.contract_sha256)
        except (TypeError, ValueError, AttributeError, KeyError, RecursionError):
            return False


def capture_media_check_coverage(store, callback, *, maximum_files=32768,
                                 maximum_inventory_entries=65536):
    """Return a certificate only after successful live subset validation."""
    tag = getattr(callback, '_ready_media_byte_guard', None)
    execution = getattr(store, 'execution_guard', None)
    revision = None if store.revision_context is None else store.revision_context.get('guard')
    if (type(tag) is not _ReadyTag or tag.callback is not callback
            or not _known_execution(execution) or execution.frozen is not store.frozen
            or store.continuity_check is not callback or store.continuity_read_guard is not callback):
        return None
    try:
        callback()
        execution()  # Populate the actual cached whole-admission guard binding.
        baseline = _contract(execution, revision)
        with capture_reads(maximum_files=maximum_files,
                           maximum_inventory_entries=maximum_inventory_entries) as capture:
            execution()
            if revision is not None: revision.verify_captured_bytes()
        required = capture.finish()
        if not required.files or not _proof_covers(tag.proof, required):
            return None
        callback()
        certificate = _Coverage(callback, tag, execution, revision, store.frozen, store.run_dir, baseline)
        return certificate if certificate.applies(store) else None
    except _Unsupported:
        return None
    except CaptureLimit:
        # A bounded capture failure can never certify a partial dependency set.
        execution()
        if revision is not None: revision.verify_captured_bytes()
        callback()
        return None
