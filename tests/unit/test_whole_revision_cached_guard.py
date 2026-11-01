"""Whole cached proofs keep every live guard without duplicate admission scans."""
from copy import deepcopy
import os
from types import SimpleNamespace

import pytest


@pytest.fixture
def cached_proof(runtime_run,monkeypatch):
    from video_ai.runtime import scene_revision_records as revisions
    from video_ai.runtime import scene_execution_records as executions
    run,_,_=runtime_run
    origin=run/'cached-origin';origin.mkdir()
    source=origin/'input.json';source.write_bytes(b'{"value":1}')
    absent=origin/'later.json'
    frozen=SimpleNamespace(options=dict(script_path=str(run/'production/script.txt'),
        scene_revision={'sha256':'a'*64},config_snapshot={'raw':{'scene_rendering':{'mode':'whole_scene_v1'}}}))
    guard=revisions.RevisionGuard(frozen)
    guard.capture(source,root=run)
    guard.capture_directory(origin,root=run)
    guard.capture_absent(absent,root=run)
    calls=[]
    monkeypatch.setattr(executions,'verify_whole_scene_frozen',lambda value:calls.append(value))
    proof={'guard':guard}
    with revisions.revision_scope():
        revisions._context.get()['validated'][str(run)]=proof
        yield SimpleNamespace(run=run,origin=origin,source=source,absent=absent,
            frozen=frozen,guard=guard,calls=calls,proof=proof,records=revisions)


def test_same_whole_frozen_cached_proof_scans_admission_once(cached_proof):
    case=cached_proof
    assert case.records.require_scene_revision(case.frozen) is case.proof
    assert case.calls==[case.frozen]


@pytest.mark.parametrize('mode',[None,'segmented_v1'])
def test_historical_cached_proof_keeps_both_frozen_checks(cached_proof,monkeypatch,mode):
    case=cached_proof
    raw=case.frozen.options['config_snapshot']['raw']
    if mode is None:raw.clear()
    else:raw['scene_rendering']['mode']=mode
    # Establish the baseline after selecting the historical configuration.
    from video_ai.planning.production_scenes import canonical_digest
    case.guard.options_sha256=canonical_digest(case.frozen.options)
    checked=[];original=case.guard.verify_frozen
    def check(value):
        checked.append(value)
        return original(value)
    monkeypatch.setattr(case.guard,'verify_frozen',check)
    assert case.records.require_scene_revision(case.frozen) is case.proof
    assert checked==[case.frozen,case.frozen]


def test_distinct_frozen_objects_still_check_caller_and_stored_proof(cached_proof):
    case=cached_proof
    caller=SimpleNamespace(options=deepcopy(case.frozen.options))
    assert case.records.require_scene_revision(caller) is case.proof
    assert len(case.calls)==2 and case.calls[0] is caller and case.calls[1] is case.frozen


@pytest.mark.parametrize('mutation',['bytes_restored_mtime','inventory','absent'])
def test_cached_whole_proof_still_rejects_live_origin_drift(cached_proof,mutation):
    case=cached_proof
    if mutation=='bytes_restored_mtime':
        stamp=case.source.stat();case.source.write_bytes(b'{"value":2}')
        os.utime(case.source,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    elif mutation=='inventory':(case.origin/'added.json').write_text('{}')
    else:case.absent.write_text('{}')
    with pytest.raises(ValueError,match='changed|appeared'):
        case.records.require_scene_revision(case.frozen)


def test_cached_whole_proof_rejects_changed_same_object_options(cached_proof):
    case=cached_proof
    case.frozen.options['changed']=True
    with pytest.raises(ValueError,match='frozen options changed'):
        case.records.require_scene_revision(case.frozen)
    assert not case.calls


def test_distinct_caller_cannot_hide_changed_stored_frozen(cached_proof):
    case=cached_proof
    caller=SimpleNamespace(options=deepcopy(case.frozen.options))
    case.frozen.options['changed']=True
    with pytest.raises(ValueError,match='frozen options changed'):
        case.records.require_scene_revision(caller)
    assert case.calls==[caller]
