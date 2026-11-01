"""Stage-machine software providers; labels and measurements are synthetic."""
from copy import deepcopy
from pathlib import Path
import pytest
from natural_study_helpers import request_fixture,save


@pytest.fixture
def study(tmp_path,monkeypatch):
    from video_ai.runtime import natural_study as s,natural_study_measure as m
    from video_ai.runtime import natural_study_records as r
    from test_natural_repair_engine import conditional,samples
    request,contexts,observed=request_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'STUDY_ROOT',tmp_path/'studies')
    monkeypatch.setattr(s,'dependencies',lambda req:(None,conditional(),[req['conditional_profile']]))
    def measured(case,**kwargs):
        i=int(case['case_id'].split('_')[-1])%12
        row=deepcopy(samples()[i//3 if i%3==0 else -1])
        row.update(case_id=case['case_id'],scene_group=case['scene_group'],domain=case['domain'])
        projections=[]
        for op,d in s.DIRECTIONS:
            item=deepcopy(row);item.update(projection_operation=op,projection_direction=d)
            if (op,d)!=('exposure','negative'): item['natural_label']='unverified'
            projections.append(item)
        context=contexts[str(Path(case['material']['path']).parents[2])]
        return dict(schema_version=1,case=case,material=case['material'],epoch=context['epoch'],
            author=observed[case['observations'][0]['path']],report=case['manifest'],original=[],dry=[],fit=None,
            projections=projections,preview=None,controls={},reason=None,ready_for_propose=False)
    monkeypatch.setattr(s,'measure_case',measured)
    monkeypatch.setattr(s,'replay_case',lambda result,**kw:result)
    root=tmp_path/'studies'/request['study_id']
    path=save(tmp_path/'request.json',request)
    return s,root,path,request


def test_stage_order_resume_readonly_and_missing_actual_review(study):
    s,root,path,_=study
    with pytest.raises(ValueError): s.measure(root)
    assert s.freeze(path,root=root)['status']=='frozen'
    frozen=(root/'inputs.FROZEN.json').read_bytes()
    assert s.freeze(path,root=root)['status']=='frozen'
    with pytest.raises(ValueError): s.evaluate(root)
    assert s.measure(root)['status']=='measured'
    assert s.seal(root)['status']=='sealed'
    assert s.evaluate(root)['status']=='evaluated'
    assert s.evaluate(root)['status']=='evaluated'
    result=s.finalize(root)
    assert result['status']=='unqualified' and result['profile'] is None
    assert 'missing_actual_improvement_observation' in str(result)
    before={str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    s.status(root)
    assert before=={str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    assert frozen==(root/'inputs.FROZEN.json').read_bytes()


def test_partial_case_is_retained_never_automatically_remeasured(study,monkeypatch):
    s,root,path,_=study;s.freeze(path,root=root)
    def interrupt(*args,**kwargs): raise KeyboardInterrupt()
    monkeypatch.setattr(s,'measure_case',interrupt)
    with pytest.raises(KeyboardInterrupt): s.measure(root)
    partial=root/'development/fixture_0/intent.json';raw=partial.read_bytes()
    with pytest.raises(ValueError,match='partial'): s.measure(root)
    assert partial.read_bytes()==raw


def test_no_qualified_development_direction_skips_holdout_without_opening_labels(study,monkeypatch):
    s,root,path,_=study;s.freeze(path,root=root)
    original=s.measure_case
    def unknown(case,**kw):
        result=original(case,**kw)
        for p in result['projections']: p['natural_label']='unverified'
        return result
    monkeypatch.setattr(s,'measure_case',unknown)
    s.measure(root);s.seal(root)
    monkeypatch.setattr(s,'measure_case',lambda *a,**k:pytest.fail('holdout opened with no qualified direction'))
    assert s.evaluate(root)['evaluation_status']=='skipped_no_qualified_direction'
    assert s.finalize(root)['profile'] is None


def test_seal_or_software_drift_is_refused(study):
    s,root,path,_=study;s.freeze(path,root=root);s.measure(root);s.seal(root)
    import json
    p=root/'thresholds.SEALED.json';row=json.loads(p.read_bytes())
    row['directions']['exposure:negative']['thresholds']['noop_bias_ceiling']=99
    p.write_text(json.dumps(row),encoding='utf-8')
    with pytest.raises(ValueError): s.evaluate(root)


def test_handwritten_profile_has_no_qualification_authority(tmp_path):
    from video_ai.runtime.natural_repair_profile import load_natural_repair_profile
    ref=save(tmp_path/'natural-repair-profile.json',dict(schema_version=1,qualified_directions=['exposure:negative']))
    with pytest.raises(ValueError): load_natural_repair_profile(ref['path'])


def test_qualified_software_fixture_needs_actual_bound_review_and_loader_replays(study,monkeypatch):
    from test_natural_candidate_records import review_fixture
    from video_ai.runtime.natural_study_records import StudyReader
    from video_ai.runtime.natural_repair_profile import load_natural_repair_profile
    s,root,path,_=study;original=s.measure_case;reviews=[]
    def with_preview(case,**kw):
        result=original(case,**kw)
        if int(case['case_id'].split('_')[-1])%3==0:
            review,expected=review_fixture(root/'fixture-media'/case['case_id'])
            review['candidate_id']=case['case_id'];result['preview']=expected
            reviews.append(save(root/'fixture-reviews'/(case['case_id']+'.json'),review))
        return result
    monkeypatch.setattr(s,'measure_case',with_preview)
    s.freeze(path,root=root);s.measure(root);s.seal(root);s.evaluate(root)
    r=StudyReader();obs=save(root/'actual-reviews.json',dict(schema_version=1,evaluation=r.cap(root/'evaluation.json'),cases=reviews))
    result=s.finalize(root,observations=obs)
    assert result['status']=='qualified'
    profile=load_natural_repair_profile(result['profile']['path'])
    assert profile['qualified_directions']==[dict(operation='exposure',correction_direction='negative')]
    assert profile['production_eligible'] is False and profile['qualified_domains']==['fixture']


def test_profile_loader_rejects_refreshed_case_labels_independently_of_metric_hashes(study,monkeypatch):
    # The real measurement replay separately validates labels; this stage guard
    # also rejects changing a result without changing its original receipt.
    s,root,path,_=study;s.freeze(path,root=root);s.measure(root);s.seal(root)
    import json
    p=root/'development/fixture_0/result.json';value=json.loads(p.read_bytes())
    value['projections'][0]['initial_bias']=100
    p.write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ValueError): s.evaluate(root)


def test_new_study_uuid_cannot_reuse_reserved_blind_holdout(study):
    from uuid import uuid4
    s,root,path,request=study;s.freeze(path,root=root)
    second=deepcopy(request);second['study_id']=str(uuid4())
    path2=save(root.parent/'second-request.json',second)
    with pytest.raises(ValueError,match='holdout'): s.freeze(path2,root=root.parent/second['study_id'])


def test_domain_union_does_not_authorize_unobserved_direction_domain_combinations():
    from video_ai.runtime.natural_study import qualified_scope
    def case(cid,op,d,domain):
        return dict(projections=[dict(case_id=cid,operation=op,correction_direction=d,
            projection_operation=op,projection_direction=d,natural_label='mild_color_bias',domain=domain)])
    dev=[case('e0','exposure','negative','a'),case('g0','wb_g','positive','b')]
    holdout=[case('e1','exposure','negative','a'),case('g1','wb_g','positive','b')]
    ev=dict(directions={'exposure:negative':dict(status='technically_passed',domains=['a']),
        'wb_g:positive':dict(status='technically_passed',domains=['b'])})
    assert qualified_scope(dev,holdout,ev,{'e0','e1','g0','g1'})==([],[])


def test_failed_flag_cannot_skip_author_and_pixel_replay_with_measured_projections(study):
    s,root,path,_=study;s.freeze(path,root=root);s.measure(root)
    import json
    from video_ai.runtime._scene_continuity_io import artifact
    p=root/'development/fixture_0/result.json';value=json.loads(p.read_bytes());value['failed']=True
    save(p,value)
    receipt_path=p.parent/'receipt.json';receipt=json.loads(receipt_path.read_bytes());receipt['result']=artifact(p);save(receipt_path,receipt)
    index=json.loads((root/'development-index.json').read_bytes());index['cases'][0]=artifact(receipt_path);save(root/'development-index.json',index)
    with pytest.raises(ValueError,match='fail'): s.seal(root)


def test_holdout_does_not_silently_drop_unknown_label_or_status():
    from test_natural_repair_engine import samples,thresholds
    from video_ai.runtime.natural_study import evaluate_rows
    rows=[dict(projections=[p]) for p in samples()]
    rows[0]['projections'][0]['natural_label']='unrecognized'
    sealed=dict(directions={op+':'+d:dict(status='separated' if op=='exposure' else 'unqualified',thresholds=thresholds()) for op,d in [('exposure','negative'),('wb_r','negative'),('wb_g','positive'),('wb_g','negative')]})
    with pytest.raises(ValueError,match='label'): evaluate_rows(rows,sealed)


def test_authentic_failed_case_stays_in_denominator_even_without_exception_text(study,monkeypatch):
    s,root,path,_=study;original=s.measure_case
    def failed(case,**kw):
        if case['case_id']=='fixture_0': raise OSError()
        return original(case,**kw)
    monkeypatch.setattr(s,'measure_case',failed)
    s.freeze(path,root=root);s.measure(root)
    result=s.seal(root)
    assert result['directions']['exposure:negative']['status']=='unqualified'
    assert result['directions']['exposure:negative']['requested_cases']==12


def test_study_index_has_independent_case_budgets_without_resetting_a_case(study,monkeypatch):
    from video_ai.runtime.natural_study_records import StudyReader
    s,root,path,_=study;s.freeze(path,root=root);s.measure(root)
    _,receipt,request,config,conditional=s._frozen(root);clock=[0];original=s._read_case
    class Budget(StudyReader):
        def __init__(self,*a,**kw): super().__init__(*a,**kw);self.end=clock[0]+300
        def check(self):
            if clock[0]>=self.end: raise TimeoutError('individual metadata operation expired')
    monkeypatch.setattr(s,'StudyReader',Budget)
    def one_case(*a,**kw):
        result=original(*a,**kw);clock[0]+=200;return result
    monkeypatch.setattr(s,'_read_case',one_case)
    _,index,results=s._index(root,receipt,request,config,conditional,'development',replay=True)
    assert len(index['cases'])==len(results)==12


@pytest.mark.parametrize('problem',['bool_version','unknown_field'])
def test_success_case_has_an_exact_schema_before_replay(study,problem):
    import json
    from video_ai.runtime._scene_continuity_io import artifact
    s,root,path,_=study;s.freeze(path,root=root);s.measure(root)
    p=root/'development/fixture_0/result.json';value=json.loads(p.read_bytes())
    if problem=='bool_version': value['schema_version']=True
    else: value['ignore_replay']=True
    save(p,value);receipt_path=p.parent/'receipt.json';receipt=json.loads(receipt_path.read_bytes());receipt['result']=artifact(p);save(receipt_path,receipt)
    index=json.loads((root/'development-index.json').read_bytes());index['cases'][0]=artifact(receipt_path);save(root/'development-index.json',index)
    with pytest.raises(ValueError): s.seal(root)
