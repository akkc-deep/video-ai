"""Transaction tests with isolated source/authority providers; no natural labels."""
from copy import deepcopy
from uuid import uuid4
import pytest
from natural_study_helpers import save
from video_ai.runtime.manifest import now


@pytest.fixture
def candidate(tmp_path,monkeypatch):
    from video_ai.runtime import production_natural_repair as p
    run=tmp_path/'run';material=save(run/'research/material/commit.json',dict(source='fixture'))
    epoch=save(run/'epoch.json',dict(epoch=1));source=save(run/'video.json',dict(video=1));manifest=save(run/'manifest.json',dict(manifest=1))
    report=save(run/'report.json',dict(report=1));assessment=save(run/'assessment.json',dict(manifest=manifest,report=report,created_at=now()))
    conditional=save(run/'conditional.json',dict(conditional=1));precheck=save(run/'precheck.json',dict(precheck='unknown'))
    context=dict(commit=material,epoch=epoch,assessment=assessment,source=source,frames=[source])
    request=dict(schema_version=1,run_id=run.name,candidate_id=str(uuid4()),policy='research_candidate_natural_v1',
        material=material,epoch=epoch,assessment=assessment,pair_manifest=manifest,conditional_profile=conditional,natural_profile=None,
        precheck=precheck,operation='exposure',operator_basis='fixture only',revision_of=None,requested_at=now(),reason='software fixture')
    monkeypatch.setattr(p,'_prepare',lambda req:(run,deepcopy(context),{},dict(report=1),None,None))
    return p,run,request


def test_missing_profile_preserves_original_without_fit_or_encode(candidate,monkeypatch):
    p,run,req=candidate
    monkeypatch.setattr(p,'fit_natural_parameter',lambda *a,**kw:pytest.fail('unauthorized fitting'))
    monkeypatch.setattr(p,'render_media',lambda *a,**kw:pytest.fail('unauthorized encoding'))
    result=p.propose(save(run/'request.json',req))
    assert result['status']=='awaiting_qualification' and result['original_preserved'] is True
    assert p.propose(run/'request.json')==result
    before={str(f):(f.read_bytes(),f.stat().st_mtime_ns) for f in run.rglob('*') if f.is_file()}
    p.status(run,req['candidate_id'])
    assert before=={str(f):(f.read_bytes(),f.stat().st_mtime_ns) for f in run.rglob('*') if f.is_file()}


def test_three_attempt_limit_includes_waiting_and_failed_attempts(candidate):
    p,run,req=candidate;parent=None
    for i in range(3):
        value=deepcopy(req);value.update(candidate_id=str(uuid4()),revision_of=parent)
        result=p.propose(save(run/f'request{i}.json',value));parent=result['terminal']
    value=deepcopy(req);value.update(candidate_id=str(uuid4()),revision_of=parent)
    with pytest.raises(ValueError,match='three'): p.propose(save(run/'request4.json',value))


def test_reusing_uuid_with_changed_request_or_unlinked_branch_is_refused(candidate):
    p,run,req=candidate;p.propose(save(run/'request.json',req))
    changed=deepcopy(req);changed['reason']='changed'
    with pytest.raises(ValueError): p.propose(save(run/'changed.json',changed))
    changed['candidate_id']=str(uuid4())
    with pytest.raises(ValueError,match='revision'): p.propose(save(run/'branch.json',changed))


def test_interrupted_intent_is_retained_without_automatic_retry(candidate,monkeypatch):
    p,run,req=candidate
    def interrupt(point):
        if point=='intent': raise KeyboardInterrupt()
    monkeypatch.setattr(p,'boundary',interrupt)
    with pytest.raises(KeyboardInterrupt): p.propose(save(run/'request.json',req))
    folder=run/'research/natural-color-repair'/req['candidate_id'];raw=(folder/'intent.json').read_bytes()
    with pytest.raises(ValueError,match='partial'): p.propose(run/'request.json')
    assert (folder/'intent.json').read_bytes()==raw


def test_bad_precheck_cannot_fit_even_with_profile_provider(candidate,monkeypatch):
    p,run,req=candidate
    req['natural_profile']=save(run/'natural.json',dict(profile='fixture'))
    monkeypatch.setattr(p,'load_natural_repair_profile',lambda *a,**k:dict(conditional_profile=req['conditional_profile']))
    monkeypatch.setattr(p,'validate_precheck',lambda *a,**k:(_ for _ in ()).throw(ValueError('known non-color failure')))
    monkeypatch.setattr(p,'fit_natural_parameter',lambda *a,**k:pytest.fail('non-color fit'))
    monkeypatch.setattr(p,'render_media',lambda *a,**k:pytest.fail('non-color encode'))
    result=p.propose(save(run/'request.json',req))
    assert result['status']=='abstained' and 'non-color' in str(result)


def test_candidate_keeps_original_request_bytes_not_reserialized_equivalent(candidate):
    import json
    p,run,req=candidate;path=run/'pretty-request.json'
    raw=(json.dumps(req,ensure_ascii=False,indent=3)+'\n').encode('utf-8');path.write_bytes(raw)
    p.propose(path)
    assert (run/'research/natural-color-repair'/req['candidate_id']/'request.json').read_bytes()==raw


def test_cloning_folder_cannot_create_new_candidate_identity(candidate):
    import shutil
    import json
    from video_ai.runtime._scene_continuity_io import artifact
    p,run,req=candidate;p.propose(save(run/'request.json',req))
    root=run/'research/natural-color-repair';other=str(uuid4())
    shutil.copytree(root/req['candidate_id'],root/other)
    terminal=json.loads((root/other/'terminal.json').read_bytes())
    terminal['intent']=artifact(root/other/'intent.json')
    save(root/other/'terminal.json',terminal)
    with pytest.raises(ValueError): p.status(run,other)


def test_unknown_review_only_keeps_original_raw_bytes_without_receipt(candidate,monkeypatch):
    from test_natural_candidate_records import review_fixture
    from video_ai.runtime.natural_study_records import put_json
    p,run,req=candidate;row,media=review_fixture(run/'fixture-media')
    folder=run/'research/natural-color-repair'/req['candidate_id'];folder.mkdir(parents=True)
    request_ref=save(run/'request.json',req)
    save(folder/'intent.json',dict(request=request_ref))
    m=save(run/'media.json',media)
    save(folder/'terminal.json',dict(status='awaiting_review',reasons=[],media=m))
    monkeypatch.setattr(p,'_saved',lambda *a,**k:{})
    row['candidate_id']=req['candidate_id'];row['checks']['color_improvement']='unverified';row['verdict']='unverified'
    ref=save(run/'unknown.json',row)
    assert p.review(run,req['candidate_id'],ref)['status']=='awaiting_review'
    assert not list((folder/'reviews').glob('*/receipt.json'))
    assert len(list((folder/'reviews').glob('*/raw.json')))==1


@pytest.mark.parametrize('state',['awaiting_review','research_candidate_reviewed','noop'])
def test_waiting_terminal_cannot_fabricate_technical_or_reviewed_success(candidate,state):
    import json
    p,run,req=candidate;result=p.propose(save(run/'request.json',req))
    terminal=result['terminal'];row=json.loads(__import__('pathlib').Path(terminal['path']).read_bytes());row['status']=state
    save(__import__('pathlib').Path(terminal['path']),row)
    with pytest.raises(ValueError): p.status(run,req['candidate_id'])


@pytest.mark.parametrize('failure_mode',['checks','response'])
def test_revision_cannot_skip_sibling_noncolor_failure(candidate,failure_mode):
    from test_natural_candidate_records import review_fixture
    from video_ai.runtime.natural_study_records import StudyReader,copy_original
    p,run,req=candidate;first=p.propose(save(run/'a.json',req))
    second=deepcopy(req);second.update(candidate_id=str(uuid4()),revision_of=first['terminal'])
    b=p.propose(save(run/'b.json',second));folder=run/'research/natural-color-repair'/second['candidate_id']
    r=StudyReader();observation,media=review_fixture(run/'review-media')
    observation['candidate_id']=second['candidate_id'];media['source']=r.any(folder/'intent.json')['source'];observation['source']=media['source']
    observation['playback_ranges']=[dict(media=m,start_frame=0,end_frame=49,fps='16/1') for m in (media['source'],media['playback'])]
    observation['verdict']='failed'
    if failure_mode=='checks': observation['checks']['motion_process']='failed'
    else:
        risk=dict(phase='after',detector_id='motion_reset',concern_id='fixture-motion')
        media['risks']=[risk];observation['responses']=[dict(risk=risk,disposition='confirmed_issue',reason='actual fixture motion failure',references=[])]
    observation['issues']=[dict(check='motion_process' if failure_mode=='checks' else 'color_improvement',media=media['playback'],frames=[0,49],description='fixture failed observation')]
    mref=save(run/'b-media.json',media);terminal=r.any(b['terminal']);terminal.update(media=mref,status='awaiting_review');save(folder/'terminal.json',terminal)
    oref=save(run/'b-failed.json',observation);review_folder=folder/'reviews'/oref['sha256']
    copy_original(oref,review_folder/'raw.json');save(review_folder/'receipt.json',dict(schema_version=1,observation=oref,verdict='failed',created_at=now()))
    third=deepcopy(req);third.update(candidate_id=str(uuid4()),revision_of=first['terminal'])
    with pytest.raises(ValueError,match='non-color'): p.propose(save(run/'c.json',third))


def test_assess_cannot_omit_registered_later_adverse_observation(candidate,monkeypatch):
    from video_ai.runtime import natural_study_records as records
    p,run,req=candidate
    earlier=save(run/'earlier.json',dict(case_id='fixture',natural_label='neutral'))
    later=save(run/'later.json',dict(case_id='fixture',subject_structure_intact=False))
    context=dict(commit=req['material'],epoch=req['epoch'],source=req['material'],frames=[earlier])
    monkeypatch.setattr(p,'load_research_material_context',lambda *a,**kw:context)
    monkeypatch.setattr(p,'source_registration',lambda *a,**kw:('fixture',None,{}))
    monkeypatch.setattr(records,'registered_observation_refs',lambda *a,**kw:('fixture',[earlier,later]),raising=False)
    monkeypatch.setattr(p,'read_author_observations',lambda *a,**kw:pytest.fail('omitted adverse history reached semantic acceptance'))
    with pytest.raises(ValueError,match='history'): p.assess(run,observations=[earlier])


def test_multi_case_profile_verification_does_not_consume_candidate_case_budget(candidate,monkeypatch):
    from video_ai.runtime.natural_study_records import StudyReader
    p,run,req=candidate;clock=[0]
    class Budget(StudyReader):
        def __init__(self,*a,**kw): super().__init__(*a,**kw);self.end=clock[0]+300
        def check(self):
            if clock[0]>=self.end: raise TimeoutError('candidate case deadline expired')
    req['natural_profile']=save(run/'natural.json',dict(fixture_profile=True))
    def profile(*a,**kw): clock[0]=400;return dict(conditional_profile=req['conditional_profile'])
    monkeypatch.setattr(p,'StudyReader',Budget)
    monkeypatch.setattr(p,'load_natural_repair_profile',profile)
    monkeypatch.setattr(p,'validate_precheck',lambda *a,**kw:(_ for _ in ()).throw(ValueError('known non-color failure')))
    result=p.propose(save(run/'request.json',req))
    assert result['status']=='abstained' and result['reasons']==['known non-color failure']
