"""Native admission has its own typed byte proof; foreign proofs never suppress checks."""
from types import SimpleNamespace

import pytest

from unit.test_temporal_scene_records import request_fixture,put


def test_native_execution_check_refuses_unknown_or_replaced_proof(runtime_run):
    from video_ai.runtime._temporal_media_check_coverage import TemporalExecutionCheck,known_temporal_execution
    from video_ai.runtime._whole_scene_admission import EvidenceReader
    from video_ai.runtime.production_state import ProductionRefused
    context,row,_,_=request_fixture(runtime_run)
    frozen=context['frozen'];frozen.config=SimpleNamespace(raw={'scene_rendering':{'mode':'temporal_extension_v1'}})
    with pytest.raises(ProductionRefused):
        TemporalExecutionCheck(context['store'],frozen,context['execution_budget'],dict(root=context['evidence']['root'],guard=SimpleNamespace(verify=lambda:None)))
    reader=EvidenceReader();reader.capture(context['evidence']['root']['path'],context['evidence']['root'])
    evidence=dict(root=context['evidence']['root'],guard=reader)
    check=TemporalExecutionCheck(context['store'],frozen,context['execution_budget'],evidence)
    check()
    assert known_temporal_execution(check)
    check.__call__=lambda:None
    assert not known_temporal_execution(check)


def test_native_execution_proof_detects_changed_bytes(runtime_run):
    from video_ai.runtime._temporal_media_check_coverage import TemporalExecutionCheck
    from video_ai.runtime._whole_scene_admission import EvidenceReader
    context,row,_,_=request_fixture(runtime_run)
    frozen=context['frozen'];frozen.config=SimpleNamespace(raw={'scene_rendering':{'mode':'temporal_extension_v1'}})
    reader=EvidenceReader();reader.capture(context['evidence']['root']['path'],context['evidence']['root'])
    check=TemporalExecutionCheck(context['store'],frozen,context['execution_budget'],dict(root=context['evidence']['root'],guard=reader))
    from pathlib import Path
    Path(context['evidence']['root']['path']).write_bytes(b'changed')
    with pytest.raises((ValueError,RuntimeError,OSError)):check()


def test_admitted_artifact_checks_only_its_own_bytes_not_entire_closure(runtime_run,tmp_path,monkeypatch):
    from video_ai.runtime._temporal_media_check_coverage import TemporalExecutionCheck,native_external_artifact
    from video_ai.runtime._whole_scene_admission import EvidenceReader
    from video_ai.runtime._continuity_byte_guard import ByteGuard
    context,row,_,_=request_fixture(runtime_run)
    frozen=context['frozen'];frozen.config=SimpleNamespace(raw={'scene_rendering':{'mode':'temporal_extension_v1'}})
    external=put(tmp_path/'bundle.json',dict(fixture_only='external admitted bundle'))
    reader=EvidenceReader();reader.capture(context['evidence']['root']['path'],context['evidence']['root']);reader.capture(external['path'],external)
    check=TemporalExecutionCheck(context['store'],frozen,context['execution_budget'],dict(root=context['evidence']['root'],guard=reader))
    context['store'].execution_guard=check
    scopes=[];original=ByteGuard.verify
    def verify(proof):scopes.append(len(proof.files));return original(proof)
    monkeypatch.setattr(ByteGuard,'verify',verify)
    assert native_external_artifact(context['store'],external['path'],external)==external
    assert scopes and all(size==1 for size in scopes), 'per-artifact reads must not repeat the whole dependency proof'


def test_native_coverage_requires_same_callback_and_exact_execution_proof(runtime_run):
    from video_ai.runtime._temporal_media_check_coverage import TemporalExecutionCheck
    from video_ai.runtime._whole_scene_admission import EvidenceReader
    from video_ai.runtime._continuity_byte_guard import capture_reads
    from video_ai.runtime._scene_media_check_coverage import _tag_ready_continuity_guard,capture_media_check_coverage,media_checks_covered
    context,row,_,_=request_fixture(runtime_run);store=context['store']
    frozen=context['frozen'];frozen.config=SimpleNamespace(raw={'scene_rendering':{'mode':'temporal_extension_v1'}})
    reader=EvidenceReader();reader.capture(context['evidence']['root']['path'],context['evidence']['root'])
    check=TemporalExecutionCheck(store,frozen,context['execution_budget'],dict(root=context['evidence']['root'],guard=reader))
    store.execution_guard=check
    with capture_reads() as capture:check()
    proof=capture.finish()
    callback=lambda:proof.verify()
    _tag_ready_continuity_guard(callback,proof)
    store.continuity_check=store.continuity_read_guard=callback
    store._media_check_coverage=capture_media_check_coverage(store,callback)
    assert media_checks_covered(store)
    store.execution_guard=lambda:None
    assert not media_checks_covered(store)
