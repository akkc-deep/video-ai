import copy
import json
from pathlib import Path
import pytest
from storyboard_helpers import content_for


from storyboard_helpers import mock_generation, review_for, write_review


def test_missing_timing_never_posts(storyboard_run,monkeypatch):
    from video_ai.runtime.storyboard_checks import plan_storyboard
    run,config,store,timing,path=storyboard_run;calls=mock_generation(monkeypatch);path.unlink()
    result=plan_storyboard(config,run_dir=run,timing_review_path=path)
    assert not result.passed and not calls and not (run/'storyboard-draft.json').exists()
    assert store.snapshot()['stages']['storyboard']['status']=='pending'


@pytest.mark.parametrize('bad',['unknown','missing','verdict','pcm_sha','timeline_sha','run','method','method_array','method_object','timestamp','evidence','cue','semantic','bool'])
def test_timing_identity_and_full_coverage_required(storyboard_run,bad):
    from video_ai.runtime.storyboard_checks import load_timing_review
    from video_ai.runtime.timeline_checks import load_committed_timeline
    run,config,store,data,path=storyboard_run
    if bad=='unknown':data['unknown']=1
    if bad=='missing':data['units'].pop()
    if bad=='verdict':data['verdict']='unverified'
    if bad=='pcm_sha':data['units'][0]['pcm_identity']['sha256']='a'*64
    if bad=='timeline_sha':data['timeline_identity']['sha256']='a'*64
    if bad=='run':data['run_id']='another'
    if bad=='method':data['review_method']='agent_text'
    if bad=='method_array':data['review_method']=[]
    if bad=='method_object':data['review_method']={}
    if bad=='timestamp':data['reviewed_at']='2026-10-04'
    if bad=='evidence':Path(data['units'][0]['evidence_identity']['path']).write_text('changed')
    if bad=='cue':data['cues'][0]['absolute_sample']+=1
    if bad=='semantic':data['units'][0]['semantic_unit_verdict']='unverified'
    if bad=='bool':data['units'][0]['spoken_start_sample']=True
    path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises((ValueError,OSError)):load_timing_review(run,path,load_committed_timeline(run))


def test_draft_needs_bound_text_review(storyboard_run,monkeypatch):
    from video_ai.runtime.storyboard_checks import plan_storyboard,load_committed_storyboard,finalize_storyboard
    run,config,store,timing,path=storyboard_run;calls=mock_generation(monkeypatch)
    before=store.snapshot();result=plan_storyboard(config,run_dir=run,timing_review_path=path)
    assert not result.passed and result.status=='review_required' and not result.ready_for_images and len(calls)==1
    assert store.snapshot()['stages']['storyboard']['status']=='running'
    with pytest.raises(ValueError):load_committed_storyboard(run)
    review=write_review(run,review_for(run));result=finalize_storyboard(config,run_dir=run,review_path=review)
    assert result.passed and result.ready_for_images and result.shot_count==3
    data=load_committed_storyboard(run)
    assert data['validation']['actual_visual_semantics']==data['validation']['actual_video_sync']=='unverified'
    for name in ('speech','timeline'):assert store.snapshot()['stages'][name]==before['stages'][name]


@pytest.mark.parametrize('bad',['draft_sha','timing_sha','timeline_sha','run','missing','duplicate','failed','unverified','index','requirement','global','unknown'])
def test_finalize_requires_every_current_requirement_passed(storyboard_run,monkeypatch,bad):
    from video_ai.runtime.storyboard_checks import plan_storyboard,finalize_storyboard
    run,config,store,timing,path=storyboard_run;mock_generation(monkeypatch)
    plan_storyboard(config,run_dir=run,timing_review_path=path);review=review_for(run)
    if bad.endswith('_sha'):review[bad.replace('_sha','_identity') if bad!='timing_sha' else 'timing_review_identity']['sha256']='a'*64
    if bad=='run':review['run_id']='other'
    if bad=='missing':review['entries'].pop()
    if bad=='duplicate':review['entries'].append(copy.deepcopy(review['entries'][0]))
    if bad in ('failed','unverified'):review['entries'][0]['verdict']=bad
    if bad=='index':review['entries'][0]['requirement_index']=True
    if bad=='requirement':review['entries'][0]['requirement_id']='invented'
    if bad=='global':review['global_verdict']='failed'
    if bad=='unknown':review['unknown']=1
    result=finalize_storyboard(config,run_dir=run,review_path=write_review(run,review))
    assert not result.passed and not (run/'storyboard.json').exists()
    assert store.snapshot()['stages']['storyboard']['status']=='failed'


@pytest.mark.parametrize('when',['before_commit','after_commit','orphan','drift','review_drift','lock_replace'])
def test_transaction_faults_preserve_evidence(storyboard_run,monkeypatch,when):
    from video_ai.runtime import storyboard_checks as sc
    from video_ai.runtime.manifest import ManifestStore
    run,config,store,timing,path=storyboard_run;mock_generation(monkeypatch)
    sc.plan_storyboard(config,run_dir=run,timing_review_path=path);review=write_review(run,review_for(run))
    if when in ('before_commit','after_commit'):
        original=ManifestStore.record_stage
        def interrupt(self,stage,status,**kw):
            if stage=='storyboard' and status=='completed':
                if when=='after_commit':original(self,stage,status,**kw)
                raise KeyboardInterrupt()
            return original(self,stage,status,**kw)
        monkeypatch.setattr(ManifestStore,'record_stage',interrupt)
    else:
        original=sc.atomic_report
        def fault(p,data):
            result=original(p,data)
            if p.name=='storyboard.json':
                if when=='orphan':raise OSError('after write')
                if when=='drift':(run/'script.txt').write_bytes(b'changed')
                if when=='review_drift':review.write_bytes(b'changed')
                if when=='lock_replace':(run/'.storyboard.lock').write_text('{"token":"foreign"}')
            return result
        monkeypatch.setattr(sc,'atomic_report',fault)
    if when=='before_commit':
        with pytest.raises(KeyboardInterrupt):sc.finalize_storyboard(config,run_dir=run,review_path=review)
    else:
        result=sc.finalize_storyboard(config,run_dir=run,review_path=review)
        assert result.passed==(when=='after_commit')
    assert store.snapshot()['stages']['storyboard']['status']==('completed' if when=='after_commit' else 'interrupted' if when=='before_commit' else 'failed')
    if when=='lock_replace':assert (run/'.storyboard.lock').exists()


def test_foreign_lock_and_completed_stage_refused(storyboard_run,monkeypatch):
    from video_ai.runtime import storyboard_checks as sc
    run,config,store,timing,path=storyboard_run;calls=mock_generation(monkeypatch)
    lock=run/'.storyboard.lock';lock.write_text('foreign');before=(run/'manifest.json').read_bytes()
    with pytest.raises(sc.StoryboardRefusal):sc.plan_storyboard(config,run_dir=run,timing_review_path=path)
    assert lock.read_text()=='foreign' and (run/'manifest.json').read_bytes()==before and not calls


@pytest.mark.parametrize('responses,posts,success',[(('format','good'),2,True),(('schema','good'),2,True),
    (('format','format'),2,False),(('ambiguous','good'),1,False),(('finer','good'),1,False)])
def test_only_explicit_format_failure_gets_one_correction(storyboard_run,responses,posts,success):
    from video_ai.runtime.storyboard_checks import _request_content,load_timing_review
    from video_ai.runtime.timeline_checks import load_committed_timeline
    from video_ai.planning.storyboard import plan_slots,primary_model_slots
    from video_ai.adapters.common import AdapterError
    from video_ai.adapters.ollama import OllamaFormatError
    from video_ai.runtime.logging import RunLogger
    run,config,store,timing,path=storyboard_run;t=load_committed_timeline(run);slots=plan_slots(t,timing=load_timing_review(run,path,t));calls=[]
    class Planner:
        def generate(self,prompt,*,schema,request_id):
            calls.append(request_id);kind=responses[len(calls)-1]
            if kind=='format':raise OllamaFormatError('bad JSON')
            if kind=='ambiguous':raise AdapterError('ambiguous','lost response')
            content=content_for(primary_model_slots(slots))
            if kind=='schema':content['shots'][0]['text']='forbidden'
            if kind=='finer':content['shots'][0]['visual_requirements'][0]['needs_finer_audio']=True
            return content
    if success:assert _request_content(Planner(),slots,RunLogger(run))['schema_version']==1
    else:
        with pytest.raises((ValueError,AdapterError)):_request_content(Planner(),slots,RunLogger(run))
    assert len(calls)==posts and calls[0]=='initial'


@pytest.mark.parametrize('bad',['script','timeline','pcm','timing','notes','review','draft','storyboard'])
def test_committed_reader_rejects_all_identity_drift(storyboard_run,monkeypatch,bad):
    from video_ai.runtime import storyboard_checks as sc
    run,config,store,timing,path=storyboard_run;mock_generation(monkeypatch)
    sc.plan_storyboard(config,run_dir=run,timing_review_path=path)
    review=write_review(run,review_for(run));assert sc.finalize_storyboard(config,run_dir=run,review_path=review).passed
    targets=dict(script=run/'script.txt',timeline=run/'timeline.json',pcm=Path(timing['units'][0]['pcm_identity']['path']),
        timing=path,notes=Path(timing['units'][0]['evidence_identity']['path']),review=review,draft=run/'storyboard-draft.json',storyboard=run/'storyboard.json')
    targets[bad].write_bytes(b'changed')
    with pytest.raises((ValueError,OSError)):sc.load_committed_storyboard(run)


@pytest.mark.parametrize('kind',['foreign_service','external_gpu'])
def test_owned_generation_preserves_external_work(storyboard_run,monkeypatch,kind):
    from video_ai.runtime import storyboard_checks as sc
    from video_ai.runtime import resources
    from video_ai.runtime.services import ServiceHandle,ServiceManager
    from video_ai.runtime.logging import RunLogger
    run,config,store,timing,path=storyboard_run
    monkeypatch.setattr(sc,'_model_files',lambda paths:{})
    monkeypatch.setattr(sc,'build_service_specs',lambda config,run:dict(ollama=object()))
    monkeypatch.setattr(resources,'gpu_guard',lambda *args:dict(status='verified',external_pids=[1234] if kind=='external_gpu' else []))
    monkeypatch.setattr(ServiceManager,'ensure',lambda *args:ServiceHandle('ollama','http://127.0.0.1:11435',False,None,None,None))
    def stop(*args):pytest.fail('external service was stopped')
    monkeypatch.setattr(ServiceManager,'stop',stop)
    with pytest.raises(RuntimeError):sc._generate_owned(config,run,store,RunLogger(run),())
    assert not list((run/'logs/storyboard').glob('*.intent.json'))


def test_model_manifest_and_blobs_are_freshly_verified(tmp_path):
    from types import SimpleNamespace
    from uuid import uuid4
    import hashlib
    from video_ai.runtime.storyboard_checks import _model_files
    from video_ai.runtime.paths import PathPolicy
    root=Path('D:/VideoSi/models/tests')/uuid4().hex/'identity';manifest=root/'models/ollama/manifests/registry.ollama.ai/library/qwen3/8b'
    manifest.parent.mkdir(parents=True);data=b'model test blob';digest=hashlib.sha256(data).hexdigest()
    blob=root/'models/ollama/blobs'/('sha256-'+digest);blob.parent.mkdir();blob.write_bytes(data)
    definition=dict(config=dict(digest='sha256:'+digest,size=len(data)),layers=[])
    manifest.write_text(json.dumps(definition),encoding='utf-8');paths=SimpleNamespace(runtime_root=root,policy=PathPolicy())
    assert _model_files(paths)['blob_0'].sha256==digest
    blob.write_bytes(b'changed')
    with pytest.raises(OSError):_model_files(paths)


@pytest.mark.parametrize('phase',['draft','final'])
def test_competing_artifact_is_never_overwritten(storyboard_run,monkeypatch,phase):
    from video_ai.runtime import storyboard_checks as sc
    run,config,store,timing,path=storyboard_run
    if phase=='draft':
        def generate(config,run,store,logger,slots,**kwargs):
            (run/'storyboard-draft.json').write_bytes(b'foreign artifact')
            return content_for(slots),{}
        monkeypatch.setattr(sc,'_generate_owned',generate)
        result=sc.plan_storyboard(config,run_dir=run,timing_review_path=path)
        assert (run/'storyboard-draft.json').read_bytes()==b'foreign artifact'
    else:
        mock_generation(monkeypatch);sc.plan_storyboard(config,run_dir=run,timing_review_path=path)
        review=write_review(run,review_for(run));original=sc._review
        def competing(*args,**kwargs):
            identity=original(*args,**kwargs);(run/'storyboard.json').write_bytes(b'foreign artifact');return identity
        monkeypatch.setattr(sc,'_review',competing)
        result=sc.finalize_storyboard(config,run_dir=run,review_path=review)
        assert (run/'storyboard.json').read_bytes()==b'foreign artifact'
    assert not result.passed and store.snapshot()['stages']['storyboard']['status']=='failed'


@pytest.mark.parametrize('phase',['finalize','reader'])
def test_raw_request_evidence_identity_drift_blocks_use(storyboard_run,monkeypatch,phase):
    from video_ai.runtime import storyboard_checks as sc
    run,config,store,timing,path=storyboard_run;mock_generation(monkeypatch)
    http=run/'logs/http';http.mkdir();body=http/'generated.body';body.write_bytes(b'raw model response')
    sc.plan_storyboard(config,run_dir=run,timing_review_path=path);review=write_review(run,review_for(run))
    if phase=='reader':assert sc.finalize_storyboard(config,run_dir=run,review_path=review).passed
    body.write_bytes(b'altered')
    if phase=='finalize':assert not sc.finalize_storyboard(config,run_dir=run,review_path=review).passed
    else:
        with pytest.raises(OSError):sc.load_committed_storyboard(run)
