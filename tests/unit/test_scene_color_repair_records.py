"""Research repair admission must reject stale, ambiguous and production input."""
from copy import deepcopy
import importlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from scene_continuity_helpers import artifact, save, snapshot


def module():
    assert importlib.util.find_spec('video_ai.runtime.scene_color_repair_records'), 'repair record validators missing'
    return importlib.import_module('video_ai.runtime.scene_color_repair_records')


def request_fixture(run):
    from video_ai.runtime.manifest import now
    refs = {key: artifact(save(run/(key+'.json'), {'fixture_only': key})) for key in
            ('source_clip', 'assessment', 'profile', 'manifest', 'precheck')}
    value = dict(schema_version=1, run_id=run.name, candidate_id=str(uuid4()),
        policy='research_candidate_v1', clip_id='scene_0001_clip_0001',
        **{k: refs[k] for k in ('source_clip','assessment','profile','manifest')},
        operation='exposure', context=dict(comparable=True, intentional_lighting_change=False,
            confirmed_motion_defect=False, subject_structure_intact=True,
            operator_basis='fixture_only known exposure and target selected image', review=refs['precheck']),
        revision_of=None, requested_at=now(), reason='fixture_only mild exposure')
    return value


def test_strict_request_rejects_unknown_bool_version_future_and_unsupported_axis(runtime_run):
    run, _, _ = runtime_run
    value = request_fixture(run)
    records = module()
    assert records.validate_repair_request(value, {'run_id': run.name}) == value
    for key, bad in [('schema_version',True), ('candidate_id',str(uuid4()).upper()),
                     ('operation','chroma'), ('policy','production'), ('requested_at','2999-01-01T00:00:00+00:00')]:
        changed = deepcopy(value); changed[key] = bad
        with pytest.raises(ValueError): records.validate_repair_request(changed, {'run_id':run.name})
    changed=deepcopy(value); changed['force']=True
    with pytest.raises(ValueError): records.validate_repair_request(changed, {'run_id':run.name})


@pytest.mark.parametrize('key,bad', [('comparable',False),('intentional_lighting_change',True),
    ('confirmed_motion_defect',True),('subject_structure_intact',False),('comparable',1),('operator_basis','')])
def test_request_context_never_overrides_missing_or_conflicting_support(runtime_run,key,bad):
    value=request_fixture(runtime_run[0]);value['context'][key]=bad
    with pytest.raises(ValueError): module().validate_repair_request(value, {'run_id':runtime_run[0].name})


def test_request_detects_same_size_mtime_byte_drift(runtime_run):
    import os
    value=request_fixture(runtime_run[0]); path=Path(value['manifest']['path']);stamp=path.stat()
    raw=path.read_bytes();path.write_bytes(raw.replace(b'manifest',b'manifesz'))
    os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    with pytest.raises(ValueError): module().validate_repair_request(value, {'run_id':runtime_run[0].name})


@pytest.mark.parametrize('value', [
    {'policy':'research_candidate_v1'}, {'production_eligible':False,'candidate_id':str(uuid4())},
    {'source':{'path':'D:/VideoSi/runs/x/production/scene-color-repair/candidates/x/master.mp4'}},
    {'state':'research_candidate_reviewed'}, {'kind':'adopt_color_repair'}])
def test_research_origin_refused_even_through_nested_production_source(value):
    with pytest.raises(ValueError,match='research|repair'): module().require_production_repair_origin(value)


def test_ordinary_source_remains_compatible_and_status_is_zero_write(runtime_run):
    run,config,_=runtime_run
    script=save(run/'production/script.txt',{'fixture_only':True})
    frozen=SimpleNamespace(config=config,options={'script_path':str(script)})
    records=module()
    records.require_production_repair_origin({'source': {'path': str(run/'production/scene-clips/c/source.mp4')}})
    before=snapshot(run)
    assert records.load_scene_color_repair_progress(frozen)==dict(schema_version=1,run_id=run.name,candidates=[],production_ready=False)
    assert snapshot(run)==before


def test_public_proposal_rejects_another_runs_lock_before_reading_or_writing(runtime_run):
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.production_scene_color_repair import propose_scene_color_repair
    run,config,paths=runtime_run;frozen=SimpleNamespace(config=config,options={'script_path':str(run/'production/script.txt')})
    with RunLock(create_run(paths)) as wrong:
        result=propose_scene_color_repair(frozen,[],None,run/'missing-request.json',paths=paths,logger=None,lock=wrong)
    assert result.status=='blocked' and 'lock' in result.error['message']
    assert not (run/'production/scene-color-repair').exists()
