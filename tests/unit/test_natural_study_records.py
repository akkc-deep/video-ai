"""Real schemas/paths/hashes, isolated synthetic source providers; no model calls."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from natural_study_helpers import request_fixture,save


@pytest.fixture
def study_request(tmp_path,monkeypatch):
    request,contexts,observed=request_fixture(tmp_path,monkeypatch)
    return tmp_path,request,contexts,observed


def test_complete_two_split_request_binds_real_provider_identities(study_request):
    from video_ai.runtime.natural_study_records import check_inputs
    _,request,_,_=study_request
    result=check_inputs(request)
    assert result['structurally_complete'] is True and result['cases']==24
    assert result['development_cases']==result['holdout_cases']==12
    assert result['holdout_labels_opened'] is False and result['ready_for_propose'] is False


@pytest.mark.parametrize('problem',['bool_schema','unknown_key','duplicate','cross_group','same_ref_cross_split','seen_holdout',
    'missing_observation','bad_commit','future','missing_case'])
def test_frozen_input_contract_refuses_shortcuts(study_request,problem):
    from video_ai.runtime.natural_study_records import check_inputs
    root,request,contexts,_=study_request;value=deepcopy(request)
    if problem=='bool_schema': value['schema_version']=True
    elif problem=='unknown_key': value['ready_for_propose']=True
    elif problem=='duplicate': value['cases'][1]['case_id']=value['cases'][0]['case_id']
    elif problem=='cross_group': value['cases'][12]['scene_group']=value['cases'][0]['scene_group']
    elif problem=='same_ref_cross_split': contexts[str(Path(value['cases'][12]['material']['path']).parents[2])]['selected_image']=contexts[str(Path(value['cases'][0]['material']['path']).parents[2])]['selected_image']
    elif problem=='seen_holdout':
        ctx=contexts[str(Path(value['cases'][12]['material']['path']).parents[2])]
        value['seen']=save(root/'new_seen.json',dict(schema_version=1,video_sha256=[ctx['source']['sha256']],reference_sha256=[]))
    elif problem=='missing_observation': value['cases'][0]['observations']=[]
    elif problem=='bad_commit': value['cases'][0]['material']['sha256']='9'*64
    elif problem=='future': value['requested_at']='2999-01-01T00:00:00+00:00'
    else: value['cases'].pop()
    with pytest.raises(ValueError): check_inputs(value)


def test_readiness_can_report_incomplete_data_without_creating_freeze(study_request):
    from video_ai.runtime.natural_study_records import check_inputs
    root,request,_,_=study_request;request['cases']=request['cases'][:4]
    result=check_inputs(request,require_complete=False)
    assert result['structurally_complete'] is False and result['cases']==4 and result['ready_for_propose'] is False
    assert not list(root.rglob('inputs.FROZEN.json'))


def test_holdout_observations_are_never_decoded_by_input_check(study_request,monkeypatch):
    from video_ai.runtime import natural_study_records as records
    _,request,_,_=study_request
    original=records.read_author_observations
    def guarded(case,*args):
        assert case['split']=='development','holdout semantic leakage'
        return original(case,*args)
    monkeypatch.setattr(records,'read_author_observations',guarded)
    records.check_inputs(request)


def test_atomic_json_preserves_existing_bytes_and_refuses_changed_replay(tmp_path):
    from video_ai.runtime.natural_study_records import put_json
    p=tmp_path/'row.json';ref=put_json(p,dict(a=1));raw=p.read_bytes()
    assert put_json(p,dict(a=1))==ref and p.read_bytes()==raw
    with pytest.raises(ValueError): put_json(p,dict(a=2))
    assert p.read_bytes()==raw


def test_study_guard_refuses_second_owner_and_releases_only_own_lock(tmp_path):
    from video_ai.runtime.natural_study_records import StudyLock
    with StudyLock(tmp_path):
        with pytest.raises(RuntimeError):
            with StudyLock(tmp_path): pass
    assert not (tmp_path/'.natural-study.lock').exists()


def test_reader_budget_does_not_refund_repeated_or_new_paths(tmp_path):
    from video_ai.runtime.natural_study_records import StudyReader
    r=StudyReader();r.charge(tmp_path/'a',16*1024**2)
    r.charge(tmp_path/'a',16*1024**2)
    assert sum(r.json_paths.values())==16*1024**2
    with pytest.raises(ValueError): r.charge(tmp_path/'b',16*1024**2+1)


def test_raw_unknown_or_noncolor_observation_is_never_promoted(tmp_path,monkeypatch):
    from test_natural_acquisition_observation import observation
    from video_ai.runtime import natural_study_records as records
    row=observation();row.update(natural_label='unverified',subject_structure_intact=False)
    path=save(tmp_path/'actual_unknown.json',row)
    case=dict(case_id=row['case_id'],observations=[path])
    context=dict(source=row['video'],selected_image=row['reference'])
    monkeypatch.setattr(records,'observation_sources',lambda *a:([row['video']],[row['reference']],None))
    result=records.read_author_observations(case,context,records.StudyReader())
    assert result['natural_label']=='unverified' and result['hard_noncolor_failure'] is True


def test_empty_observation_file_is_not_a_frozen_input(study_request):
    from video_ai.runtime.natural_study_records import check_inputs
    from video_ai.runtime._scene_continuity_io import artifact
    root,request,_,_=study_request
    p=root/'empty.json';p.write_bytes(b'')
    request['cases'][12]['observations']=[artifact(p,empty=True)]
    with pytest.raises(ValueError,match='empty'): check_inputs(request)


def test_blind_context_does_not_use_pixel_validating_context_loader(study_request,monkeypatch):
    from video_ai.runtime import natural_study_records as records
    _,request,contexts,_=study_request
    holdout=request['cases'][12]
    monkeypatch.setattr(records,'load_research_material_context',lambda *a,**k:pytest.fail('holdout pixels opened before seal'))
    monkeypatch.setattr(records,'opaque_holdout_context',lambda run,reader:deepcopy(contexts[str(run)]),raising=False)
    records.case_context(holdout,records.StudyReader())


def test_formal_case_cannot_rename_original_generated_family_or_split(study_request,monkeypatch):
    from video_ai.runtime import natural_study_records as records
    _,request,_,_=study_request
    original=request['cases'][0]['scene_group']
    def require_registration(case,*args):
        if case['case_id']=='fixture_0' and case['scene_group']!=original: raise ValueError('original source registration differs')
    monkeypatch.setattr(records,'bind_source_registration',require_registration,raising=False)
    for case in request['cases'][:3]: case['scene_group']='invented_independent_family'
    with pytest.raises(ValueError,match='registration'): records.check_inputs(request)


def test_shared_schema_validation_refuses_boolean_version():
    from video_ai.runtime.natural_study_records import fields
    with pytest.raises(ValueError): fields(dict(schema_version=True),'schema_version')


def test_study_history_completeness_is_opaque_before_seal(tmp_path,monkeypatch):
    from video_ai.runtime import natural_study_records as r
    earlier=save(tmp_path/'safe.json',dict(case_id='fixture',natural_label='neutral'))
    later=save(tmp_path/'adverse.json',dict(case_id='fixture',motion_intact=False))
    monkeypatch.setattr(r,'registered_observation_refs',lambda *a,**kw:('fixture',[earlier,later]),raising=False)
    case=dict(case_id='fixture',observations=[earlier])
    reader=r.StudyReader()
    with pytest.raises(ValueError,match='history'): r.require_complete_observations(case,{},reader)
    assert not reader.json_paths
