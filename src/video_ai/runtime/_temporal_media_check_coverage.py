"""Independent strict native execution proof, backed by actual admitted bytes."""
from pathlib import Path
from dataclasses import dataclass
import sys

from ..planning.production_scenes import canonical_digest
from .manifest import thaw
from .production_state import ProductionRefused
from ._continuity_byte_guard import ByteGuard,capture_reads,observe_file,observe_inventory,observe_absence
from ._scene_media_check_coverage import _reader_contract,_original_method,_Unsupported


class TemporalExecutionCheck:
    def __init__(self,store,frozen,budget_artifact,evidence):
        self.store,self.frozen=store,frozen
        self.budget_artifact=budget_artifact
        self.evidence=evidence
        try:state=_reader_contract(evidence['guard'])
        except (TypeError,ValueError,AttributeError,KeyError) as exc:
            raise ProductionRefused('unknown native admission proof') from exc
        if frozen.config.raw.get('scene_rendering',{}).get('mode')!='temporal_extension_v1':
            raise ProductionRefused('native execution proof requires exact frozen mode')
        with capture_reads() as capture:
            if store.artifact(budget_artifact['path'])!=budget_artifact:raise ProductionRefused('native execution budget drift')
            evidence['guard'].verify()
        self.proof=capture.finish()
        if type(self.proof) is not ByteGuard or not self.proof.files:raise ProductionRefused('native execution proof is incomplete')
        from ._protected_continuity_inputs import prepare_continuity_inputs
        prepare_continuity_inputs(self.proof.files,immutable_roots=(store.run_dir/'production/scene-rendering',))
        self.proof.verify()
        self.baseline=self.contract()

    def contract(self):
        if type(self.proof) is not ByteGuard:raise ProductionRefused('native execution byte proof replaced')
        return canonical_digest(dict(options=thaw(self.frozen.options),raw=thaw(self.frozen.config.raw),
            budget=self.budget_artifact,root=self.evidence['root'],reader_identity=id(self.evidence['guard']),
            reader=_reader_contract(self.evidence['guard']),value=thaw(self.evidence.get('value')),proof=thaw(self.proof)))

    def extend_proof(self,proof):
        from ._scene_media_check_coverage import _proof_covers
        if not known_temporal_execution(self) or self.contract()!=self.baseline or not _proof_covers(proof,self.proof):
            raise ProductionRefused('native media proof omits original admission closure')
        proof.verify()
        from ._protected_continuity_inputs import prepare_continuity_inputs
        prepare_continuity_inputs(proof.files,immutable_roots=(self.store.run_dir/'production/scene-rendering',self.store.run_dir/'production/scene-clips'))
        self.proof=proof;self.baseline=self.contract()

    def captured_artifact(self,path):
        if not known_temporal_execution(self) or self.contract()!=self.baseline:raise ProductionRefused('native artifact proof changed')
        row=next((row for row in self.proof.files if row.path==str(path)),None)
        if row is not None:ByteGuard((row,),(),()).verify()
        return None if row is None else dict(path=row.path,bytes=row.bytes,sha256=row.sha256)

    def __call__(self):
        if not known_temporal_execution(self) or self.contract()!=self.baseline:
            raise ProductionRefused('native execution validator/closure changed')
        self.proof.verify()
        # Nested continuity captures must carry the actual native closure too.
        for row in self.proof.files:observe_file({key:getattr(row,key) for key in ('path','bytes','mtime_ns','sha256','verified_at')})
        for row in self.proof.inventories:observe_inventory(row.path,row.kind,row.expected,pattern=row.pattern)
        for path in self.proof.absences:observe_absence(path)


def known_temporal_execution(value):
    methods=('__call__','contract','extend_proof','captured_artifact')
    return (type(value) is TemporalExecutionCheck and not any(name in value.__dict__ for name in methods)
        and all(_original_method(getattr(TemporalExecutionCheck,name),sys.modules[__name__],
            'TemporalExecutionCheck.'+name) for name in methods))


def native_external_artifact(store,path,expected=None):
    path=Path(path)
    check=getattr(store,'execution_guard',None)
    if not known_temporal_execution(check) or check.frozen is not store.frozen or check.store.run_dir!=store.run_dir:return None
    actual=check.captured_artifact(path)
    if actual is None:return None
    if expected is not None and actual!=expected:raise ProductionRefused('external native Artifact differs from admitted bytes')
    return actual


def _coverage_contract(check,revision):
    from ._scene_media_check_coverage import _revision_contract
    if not known_temporal_execution(check):raise _Unsupported('unknown native execution check')
    return canonical_digest(dict(execution=check.contract(),
        revision=None if revision is None else _revision_contract(revision,None)))


@dataclass(frozen=True)
class _TemporalCoverage:
    callback:object
    tag:object
    execution:object
    revision:object
    frozen:object
    run_dir:object
    contract_sha256:str

    def applies(self,store):
        try:
            revision=None if store.revision_context is None else store.revision_context['guard']
            return (store.frozen is self.frozen and store.run_dir==self.run_dir
                and store.execution_guard is self.execution and revision is self.revision
                and store.continuity_check is self.callback and store.continuity_read_guard is self.callback
                and getattr(self.callback,'_ready_media_byte_guard',None) is self.tag
                and _coverage_contract(self.execution,revision)==self.contract_sha256)
        except (TypeError,ValueError,AttributeError,KeyError,RecursionError,ProductionRefused):return False


def native_media_checks_covered(store):
    value=getattr(store,'_media_check_coverage',None)
    return type(value) is _TemporalCoverage and value.applies(store)


def capture_native_media_check_coverage(store,callback,*,maximum_files=32768,maximum_inventory_entries=65536):
    from ._scene_media_check_coverage import _ReadyTag,_proof_covers
    from ._continuity_byte_guard import CaptureLimit
    check=getattr(store,'execution_guard',None);tag=getattr(callback,'_ready_media_byte_guard',None)
    revision=None if store.revision_context is None else store.revision_context.get('guard')
    if (not known_temporal_execution(check) or check.frozen is not store.frozen or check.store.run_dir!=store.run_dir
            or type(tag) is not _ReadyTag or tag.callback is not callback
            or store.continuity_check is not callback or store.continuity_read_guard is not callback):return None
    try:
        callback();check();baseline=_coverage_contract(check,revision)
        with capture_reads(maximum_files=maximum_files,maximum_inventory_entries=maximum_inventory_entries) as capture:
            check()
            if revision is not None:revision.verify_captured_bytes()
        required=capture.finish()
        if not required.files or not _proof_covers(tag.proof,required):return None
        callback()
        value=_TemporalCoverage(callback,tag,check,revision,store.frozen,store.run_dir,baseline)
        return value if value.applies(store) else None
    except _Unsupported:return None
    except CaptureLimit:
        check()
        if revision is not None:revision.verify_captured_bytes()
        callback()
        return None
