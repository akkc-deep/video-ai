"""No model requests or semantic video observations are made by these tests."""
import importlib.util
from pathlib import Path

import pytest

from test_natural_pilot import pilot


@pytest.mark.parametrize('operation',['acquire_pilot_case','prepare_pilot_case'])
def test_unknown_case_never_creates_directory_or_dispatches(pilot,monkeypatch,operation):
    from video_ai.experiments import natural_pilot_runtime as runtime
    _,root=pilot
    calls=[];monkeypatch.setattr(runtime,'_generate_pilot',lambda *a:calls.append(a))
    with pytest.raises(ValueError): getattr(runtime,operation)(root,'extra_fifth_case')
    assert calls==[] and not (root/'cases').exists()


def test_existing_uncertain_case_can_never_be_dispatched_as_new(pilot,monkeypatch):
    from video_ai.experiments import natural_pilot_runtime as runtime
    module,root=pilot;cid=module.load_pilot(root)['cases'][0]['case_id']
    (root/'cases'/cid).mkdir(parents=True)
    calls=[];monkeypatch.setattr(runtime,'_generate_pilot',lambda *a:calls.append(a))
    with pytest.raises(ValueError,match='existing|original|locator'): runtime.acquire_pilot_case(root,cid)
    assert calls==[]


def test_pending_case_uses_original_recovery_without_new_generation(pilot,monkeypatch):
    from video_ai.experiments import natural_pilot_runtime as runtime
    from video_ai.experiments.natural_acquisition import write_json
    module,root=pilot;cid=module.load_pilot(root)['cases'][0]['case_id']
    write_json(root/'cases'/cid/'generation-run.json',dict(fixture_only=True))
    monkeypatch.setattr(runtime,'_generate_pilot',lambda *a:pytest.fail('new POST path'))
    calls=[];monkeypatch.setattr(runtime,'_recover_case',lambda *a:calls.append(a) or dict(status='recovered_original'))
    assert runtime.acquire_pilot_case(root,cid)['status']=='recovered_original'
    assert len(calls)==1


def test_completed_case_only_uses_actual_source_verifier(pilot,monkeypatch):
    from video_ai.experiments import natural_pilot_runtime as runtime
    from video_ai.experiments.natural_acquisition import write_json
    module,root=pilot;cid=module.load_pilot(root)['cases'][0]['case_id']
    write_json(root/'cases'/cid/'evidence/generation-result.json',dict(not_real_model_evidence=True))
    monkeypatch.setattr(runtime,'_generate_pilot',lambda *a:pytest.fail('new POST path'))
    with pytest.raises((ValueError,OSError,KeyError)): runtime.acquire_pilot_case(root,cid)


def test_missing_generated_video_is_not_prepared_or_generated(pilot,monkeypatch):
    from video_ai.experiments import natural_pilot_runtime as runtime
    module,root=pilot;cid=module.load_pilot(root)['cases'][0]['case_id']
    monkeypatch.setattr(runtime,'_generate_pilot',lambda *a:pytest.fail('prepare must not generate'))
    with pytest.raises((ValueError,OSError,KeyError)): runtime.prepare_pilot_case(root,cid)


def test_external_comfy_service_is_not_taken_over_or_reserved_as_new_case(pilot,resource_config,monkeypatch):
    from video_ai.experiments import natural_pilot_runtime as runtime
    from video_ai.runtime import services
    module,root=pilot;cid=module.load_pilot(root)['cases'][0]['case_id']
    monkeypatch.setattr(runtime,'load_config',lambda path:resource_config)
    monkeypatch.setattr(services,'port_listening',lambda *a:True)
    with pytest.raises(RuntimeError,match='external'): runtime.acquire_pilot_case(root,cid)
    assert not (root/'cases').exists()


def test_pilot_status_is_readonly_and_preserves_all_four_unknown_cases(pilot):
    from video_ai.experiments.natural_pilot_runtime import pilot_status
    _,root=pilot
    before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result=pilot_status(root)
    assert result['max_requests']==4 and len(result['cases'])==4 and result['generated_videos']==0
    assert result['ready_for_propose'] is False
    assert all(c['natural_label']=='unverified' for c in result['cases'])
    assert before=={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_different_cases_share_the_entire_model_acquisition_lock(pilot,monkeypatch):
    from video_ai.experiments import natural_pilot_runtime as runtime
    module,root=pilot;ids=[c['case_id'] for c in module.load_pilot(root)['cases']]
    calls=[];monkeypatch.setattr(runtime,'_generate_pilot',lambda *a:calls.append(a) or dict(status='fixture_only'))
    with runtime._pilot_acquisition_lock(root):
        with pytest.raises(RuntimeError,match='locked'): runtime.acquire_pilot_case(root,ids[1])
    assert calls==[] and not (root/'cases').exists()
    assert runtime.acquire_pilot_case(root,ids[1])['status']=='fixture_only'
    assert len(calls)==1


@pytest.mark.parametrize('foreign',['request','result','reference','import_config'])
def test_cross_case_source_or_import_cannot_be_consumed(pilot,monkeypatch,foreign):
    from video_ai.experiments import natural_pilot_runtime as runtime
    from video_ai.experiments.natural_acquisition import identity,write_json
    module,root=pilot;plan,case,folder=module.pilot_case(root,module.load_pilot(root)['cases'][0]['case_id'])
    request=write_json(folder/'evidence/wan-material-request.json',dict(fixture_only=True))
    result_path=write_json(folder/'evidence/generation-result.json',dict(fixture_only=True))
    ref=write_json(folder/'ref-analysis.json',dict(fixture_only=True))
    other=write_json(folder/'other-case.json',dict(foreign=True))
    write_json(folder/'evidence/reference-gate.json',dict(analysis=ref))
    index=dict(request=request,result=result_path,reference=ref,frames=[])
    if foreign in ('request','result','reference'): index[foreign]=other
    index_ref=write_json(folder/'source-index.json',index)
    if foreign=='import_config': write_json(folder/'import-request.json',dict(source_index=index_ref,config=other))
    monkeypatch.setattr(runtime,'_verified_result',lambda *a:dict(request=request,video=case['reference']))
    monkeypatch.setattr(runtime,'verify_wan_material',lambda *a,**k:pytest.fail('foreign input must fail before import'))
    with pytest.raises(ValueError,match='binding|differs'): runtime.prepare_pilot_case(root,case['case_id'])


def test_pilot_cli_reports_missing_root_without_model_action(tmp_path,capsys):
    path=Path(__file__).parents[2]/'scripts/experiments/vco06_pilot.py'
    spec=importlib.util.spec_from_file_location('pilot_cli',path)
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    assert cli.main(['status','--root',str(tmp_path/'missing')])==2
    assert '"status": "blocked"' in capsys.readouterr().out


def test_empty_pilot_portal_never_invents_outputs_or_observations(pilot):
    from video_ai.experiments.natural_pilot_runtime import export_pilot_portal
    _,root=pilot
    result=export_pilot_portal(root)
    page=Path(result['portal']['path']).read_text(encoding='utf-8')
    assert result['cases']==0 and '"cases":[]' in page
    assert result['ready_for_propose'] is False


def test_portal_snapshots_can_grow_without_overwriting_old_evidence(pilot,monkeypatch):
    from video_ai.experiments import natural_pilot_runtime as runtime
    module,root=pilot
    empty=runtime.export_pilot_portal(root);old=Path(empty['portal']['path']).read_bytes()
    case=module.load_pilot(root)['cases'][0]
    # A fixture identity is enough to exercise snapshot publication; never a real video claim.
    fake=dict(case_id=case['case_id'],split='development',scene_group=case['scene_group'],
        reference=case['reference'],video=case['reference'])
    monkeypatch.setattr(runtime,'pilot_status',lambda root:dict(cases=[fake]))
    full=runtime.export_pilot_portal(root)
    assert full['cases']==1 and full['portal']['path']!=empty['portal']['path']
    assert Path(empty['portal']['path']).read_bytes()==old
    assert runtime.export_pilot_portal(root)['portal']==full['portal']


def test_pilot_intake_keeps_original_bytes_and_refuses_wrong_collection(tmp_path,monkeypatch):
    import json
    from test_natural_acquisition_observation import observation
    from video_ai.experiments import natural_pilot_runtime as runtime
    from video_ai.experiments.natural_acquisition import write_json
    row=observation();root=tmp_path/'intake';root.mkdir()
    write_json(root/'collection-receipt.json',dict(collection=row['collection']))
    case=dict(case_id=row['case_id'],reference=row['reference'],split='development')
    monkeypatch.setattr(runtime,'pilot_case',lambda *a:(None,case,root))
    monkeypatch.setattr(runtime,'_verified_result',lambda *a:dict(video=row['video'],finished_at=row['playback']['started_at']))
    source=root/'actual.json';raw=(json.dumps(row,indent=3)+'\n').encode();source.write_bytes(raw)
    result=runtime.record_pilot_observation(root,source)
    assert Path(result['observation']['path']).read_bytes()==raw
    assert result['ready_for_propose'] is False
    row['collection']['sha256']='9'*64;source.write_text(json.dumps(row),encoding='utf-8')
    with pytest.raises(ValueError): runtime.record_pilot_observation(root,source)
