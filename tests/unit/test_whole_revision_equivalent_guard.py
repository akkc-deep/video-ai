"""Typed frozen copies may share an admission scan only with identical JSON."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest


@pytest.fixture
def equivalent_proof(runtime_run,monkeypatch):
    from video_ai.runtime import scene_revision_records as revisions
    from video_ai.runtime import scene_execution_records as executions
    from video_ai.runtime.production_inputs import FrozenInputs
    from video_ai.planning.segments import SegmentedScript
    run,config,_=runtime_run
    script=run/'production/script.txt';script.parent.mkdir();script.write_text('Example.',encoding='utf-8')
    options=dict(script_path=str(script),scene_revision={'sha256':'a'*64},number=1,
        config_snapshot={'raw':{'scene_rendering':{'mode':'whole_scene_v1'}}})
    config=replace(config,production_strategy='paragraph_jimeng_v1',raw=dict(config.raw,typed_number=1))
    frozen=FrozenInputs(config,SegmentedScript.read(script),options)
    source=run/'origin.json';source.write_bytes(b'{"value":1}')
    guard=revisions.RevisionGuard(frozen);guard.capture(source,root=run)
    caller=replace(frozen,options=deepcopy(options),config=replace(config,raw=dict(config.raw)),
        script=SegmentedScript.read(script))
    calls=[];monkeypatch.setattr(executions,'verify_whole_scene_frozen',lambda value:calls.append(value))
    proof={'guard':guard}
    with revisions.revision_scope():
        revisions._context.get()['validated'][str(run)]=proof
        yield SimpleNamespace(frozen=frozen,caller=caller,calls=calls,source=source,records=revisions,proof=proof)


def test_equal_typed_frozen_copies_do_not_duplicate_whole_admission(equivalent_proof):
    case=equivalent_proof
    assert case.caller is not case.frozen and case.caller.config is not case.frozen.config
    assert case.records.require_scene_revision(case.caller) is case.proof
    assert len(case.calls)==1 and case.calls[0] is case.frozen


@pytest.mark.parametrize('change',['resolved_config','raw_bool','script_bool'])
def test_different_typed_state_keeps_both_original_checks(equivalent_proof,change):
    case=equivalent_proof;caller=case.caller
    if change=='resolved_config':caller=replace(caller,config=replace(caller.config,timeouts=dict(caller.config.timeouts,wan=1)))
    elif change=='raw_bool':caller=replace(caller,config=replace(caller.config,raw=dict(caller.config.raw,typed_number=True)))
    else:caller=replace(caller,script=replace(caller.script,has_bom=0))
    assert case.records.require_scene_revision(caller) is case.proof
    assert len(case.calls)==2 and case.calls[0] is caller and case.calls[1] is case.frozen


def test_python_equal_but_different_json_options_are_still_rejected(equivalent_proof):
    case=equivalent_proof;case.caller.options['number']=True
    assert case.caller.options==case.frozen.options
    with pytest.raises(ValueError,match='frozen options changed'):
        case.records.require_scene_revision(case.caller)


def test_equal_frozen_copy_still_rechecks_original_source_bytes(equivalent_proof):
    case=equivalent_proof;case.source.write_bytes(b'{"value":2}')
    with pytest.raises(ValueError,match='changed'):
        case.records.require_scene_revision(case.caller)
