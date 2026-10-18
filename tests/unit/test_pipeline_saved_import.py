"""Explicit TEST ONLY saved outputs; no model is loaded or requested."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import json
import subprocess
import pytest


def fixture(runtime_run,monkeypatch):
    from video_ai.config import load_config
    from video_ai.runtime import start_image_checks as owner
    from video_ai.runtime.manifest import create_manifest,hash_file,thaw,now
    from video_ai.planning.start_images import image_parameters
    from video_ai.runtime.pipeline_recovery import Reconciliation,_native_saved_validation
    run,_,_=runtime_run;config=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    model=run/'TEST-ONLY-model.bin';model.write_bytes(b'fixture model never loaded')
    raw=thaw(config.raw);raw['models']['sdxl']=str(model)
    raw['voice_config']=str(config.voice.config_file)
    raw['workflows']={key:str(path) for key,path in config.workflows.items()}
    raw['media']['profile']='fast'
    test_config=run/'TEST-ONLY-config.json';test_config.write_text(json.dumps(raw))
    config=load_config(test_config)
    script=run/'TEST-ONLY-script.txt';script.write_text('Test only one original bird scene.')
    store=create_manifest(run,config,inputs={'script':hash_file(script),'config':hash_file(config.config_file),'voice':hash_file(config.voice.config_file)},models={},workflows={})
    from video_ai.runtime import preflight as admission
    monkeypatch.setattr(admission,'preflight',lambda *a,**k:admission.PreflightReport((admission.PreflightCheck('TEST ONLY',True,'isolated resource admission'),)))
    board={'global_visual':{'style':'TEST ONLY','color_palette':'red','lighting':'day','entities':[]},
           'shots':[{'shot_id':'shot_0001','primary_unit_id':'speech_0001','image_prompt':'one red bird','entity_ids':[]}]}
    p=image_parameters(board['shots'][0],board['global_visual'],768,432)
    def instantiate(values,*,output_prefix):return {'1':{'class_type':'SaveImage','inputs':dict(values,filename_prefix=output_prefix)}}
    template=SimpleNamespace(instantiate=instantiate,mapping={'output':{'node_id':'1','collection':'images'},
        'inputs':{'width':{'node_id':'1','input':'width'},'height':{'node_id':'1','input':'height'}}})
    graph=instantiate(dict(positive_prompt=p['positive'],negative_prompt=p['negative'],seed=p['seed'],width=768,height=432),output_prefix=f'{run.name}/start_images/shot_0001')
    monkeypatch.setattr(owner,'_input_files',lambda *a:(board,{}))
    monkeypatch.setattr(owner,'_directions',lambda *a:({},{}))
    monkeypatch.setattr(owner,'_model',lambda *a:(hash_file(model),{}))
    monkeypatch.setattr(owner,'_template',lambda *a:template)
    attempt,client=str(uuid4()),str(uuid4())
    request=run/'workflows'/f'{attempt}.json';request.parent.mkdir(exist_ok=True);request.write_text(json.dumps(graph))
    logs=run/'logs/http';logs.mkdir(parents=True,exist_ok=True)
    (logs/'original.request.json').write_text(json.dumps(dict(method='POST',url=config.services['comfyui']+'/prompt',stage='start_images',unit_id='shot_0001',timeout=2,json_body={'client_id':client,'prompt':graph})))
    output=run/'comfy/output'/run.name/'start_images/shot_0001_00001_.png';output.parent.mkdir(parents=True)
    subprocess.run([str(config.tools['ffmpeg']),'-nostdin','-v','error','-n','-f','lavfi','-i','color=red:s=768x432','-frames:v','1','-pix_fmt','rgb24',str(output)],check=True)
    saved=dict(attempt_id=attempt,client_id=client,state='intent',request_path=str(request),response_path=None,prompt_id=None,
        number=None,submitted_at='2026-01-01T00:00:00+00:00',last_seen_at=None)
    store.record_stage('start_images','running');store.record_unit('image','shot_0001','running')
    def register(data):data['units']['image']['shot_0001']['submission']=saved;data['workflows'][attempt]=thaw(hash_file(request))
    store.update(register)
    history={'prompt':[1,'test-prompt',graph,{'client_id':client},['1']],'status':{'completed':True,'status_str':'success'},
        'outputs':{'1':{'images':[{'filename':output.name,'subfolder':f'{run.name}/start_images','type':'output'}]}}}
    history_path=run/'logs/pipeline/TEST-ONLY-history.json';history_path.parent.mkdir(exist_ok=True);history_path.write_text(json.dumps({'test-prompt':history}))
    verified=_native_saved_validation(config,run,'start_images','shot_0001',saved,history,graph)
    response=Reconciliation('start_images','shot_0001',attempt,'test-prompt','completed',
        tuple(verified.evidence_identities)+(hash_file(history_path),),verified.output_identities,'TEST ONLY fully decoded fixture')
    return run,config,store,output,response


def test_saved_image_child_reaches_stage_facade_without_post_and_waits_review(runtime_run,monkeypatch):
    from video_ai.runtime._pipeline_saved_import import derive_reconciled_run
    from video_ai.runtime import start_image_checks as owner,pipeline_stages
    from video_ai.runtime.manifest import ManifestStore,hash_file,thaw
    run,config,store,output,response=fixture(runtime_run,monkeypatch)
    board,_=owner._input_files(config,run)
    board['shots'][0]['visual_requirements']=[]
    board['shots'][0]['bindings']=[]
    before=store.snapshot()
    child=derive_reconciled_run(config,parent_run_dir=run,plan=SimpleNamespace(reused=()),reconciliations=(response,))
    # The upstream storyboard owner is a TEST ONLY boundary. The child import,
    # stage dispatcher, resume facade, draft validator and PNG decode are real.
    review=child/'TEST-ONLY-storyboard-review.json';review.write_text('{}')
    board['run_id']=child.name
    board['review_identity']=thaw(hash_file(review))
    (child/'storyboard.json').write_text(json.dumps(board))
    (child/'storyboard-draft.json').write_text('{}')
    def inputs(c,r):
        if r==run:return board,{}
        return board,{key:hash_file(path) for key,path in dict(storyboard=r/'storyboard.json',
            config=c.config_file,storyboard_draft=r/'storyboard-draft.json',storyboard_review=review,
            ffmpeg=c.tools['ffmpeg'],ffprobe=c.tools['ffprobe']).items()}
    monkeypatch.setattr(owner,'_input_files',inputs)
    monkeypatch.setattr(owner,'load_committed_storyboard',lambda r:board)
    # Saved native fixture uses a synthetic model; current accepted-model owner
    # provides the same test leaf, and never loads weights.
    config=replace(config,models=dict(config.models,sdxl=run/'TEST-ONLY-model.bin'))
    def forbidden(*a,**k):raise AssertionError('saved completed image must make zero model POSTs')
    monkeypatch.setattr(owner,'_generate_owned',forbidden)
    result=pipeline_stages.prepare('start_images',config,child,options={},reviews={},store=ManifestStore.open(child))
    assert result.status=='review_required' and not result.passed,ManifestStore.open(child).snapshot()['stages']['start_images']['error']
    assert (child/'images-draft.json').exists() and not (child/'images.json').exists()
    snapshot=ManifestStore.open(child).snapshot()
    assert snapshot['stages']['start_images']['status']=='running'
    assert snapshot['units']['image']['shot_0001']['submission'] is None
    assert store.snapshot()==before


def test_saved_request_import_keeps_parent_intent_and_true_origin(runtime_run,monkeypatch):
    from video_ai.runtime._pipeline_saved_import import derive_reconciled_run,consume_reconciled_unit
    from video_ai.runtime.pipeline_import import load_pipeline_import
    from video_ai.runtime.manifest import ManifestStore
    run,config,store,output,response=fixture(runtime_run,monkeypatch);before=store.snapshot()
    child=derive_reconciled_run(config,parent_run_dir=run,plan=SimpleNamespace(reused=()),reconciliations=(response,))
    receipt=load_pipeline_import(child);row=receipt['units'][0]
    assert row['origin']=='completed_saved_submission'
    assert row['imported_record']['source_kind']=='image'
    assert (child/'shots/shot_0001/start.png').read_bytes()==output.read_bytes()
    assert store.snapshot()==before and before['units']['image']['shot_0001']['submission']['state']=='intent'
    current=ManifestStore.open(child).snapshot()
    assert current['stages']['preflight']['status']=='completed'
    from video_ai import pipeline
    options,option_ids=pipeline._options(child)
    assert options['script']==Path(before['inputs']['script']['path']) and 'options' in option_ids
    assert current['stages']['start_images']['status']=='pending'
    assert current['units']['image']['shot_0001']['status']=='completed'
    assert current['units']['image']['shot_0001']['submission'] is None
    original=consume_reconciled_unit(run,row)
    assert original['image_identity']['sha256']==response.output_identities[0].sha256
    output.write_bytes(b'changed original output')
    with pytest.raises(ValueError):load_pipeline_import(child)


def test_saved_child_creation_failure_keeps_independent_diagnostic_and_original_exception(runtime_run,monkeypatch):
    from video_ai.runtime._pipeline_saved_import import derive_reconciled_run
    from video_ai.runtime import pipeline_import
    run,config,store,output,response=fixture(runtime_run,monkeypatch);before=store.snapshot();runs=set(run.parent.iterdir())
    def failed_copy(*a,**k):raise OSError('TEST ONLY child import copy failed')
    monkeypatch.setattr(pipeline_import,'create_pipeline_import',failed_copy)
    with pytest.raises(OSError,match='child import copy failed'):
        derive_reconciled_run(config,parent_run_dir=run,plan=SimpleNamespace(reused=()),reconciliations=(response,))
    children=set(run.parent.iterdir())-runs
    assert len(children)==1
    child=children.pop();proofs=list((child/'logs/pipeline').glob('child-derivation-failure-*.json'))
    assert len(proofs)==1
    failure=json.loads(proofs[0].read_text())
    assert failure['parent_run_id']==run.name and failure['stage']=='start_images'
    assert failure['error_type']=='OSError' and 'child import copy failed' in failure['message']
    assert Path(failure['traceback_path']).is_file() and store.snapshot()==before


def test_saved_child_requires_fresh_preflight_before_allocating_run(runtime_run,monkeypatch):
    from video_ai.runtime._pipeline_saved_import import derive_reconciled_run
    from video_ai.runtime import preflight as admission
    run,config,store,output,response=fixture(runtime_run,monkeypatch);runs=set(run.parent.iterdir())
    monkeypatch.setattr(admission,'preflight',lambda *a,**k:admission.PreflightReport((admission.PreflightCheck('TEST ONLY',False,'fresh refusal'),)))
    with pytest.raises(ValueError,match='fresh preflight'):
        derive_reconciled_run(config,parent_run_dir=run,plan=SimpleNamespace(reused=()),reconciliations=(response,))
    assert set(run.parent.iterdir())==runs


def test_submitted_unknown_sibling_cannot_become_remaining_post(runtime_run,monkeypatch):
    from video_ai.runtime._pipeline_saved_import import derive_reconciled_run
    from video_ai.runtime.manifest import hash_file,thaw
    run,config,store,output,response=fixture(runtime_run,monkeypatch)
    store.record_unit('image','shot_0002','running')
    unknown=dict(store.snapshot()['units']['image']['shot_0001']['submission']);unknown['attempt_id']=str(uuid4());unknown['client_id']=str(uuid4())
    def register(data):
        data['units']['image']['shot_0002']['submission']=unknown
        data['workflows'][unknown['attempt_id']]=thaw(hash_file(Path(unknown['request_path'])))
    store.update(register)
    before=store.snapshot()
    with pytest.raises(ValueError,match='sibling is still unknown'):
        derive_reconciled_run(config,parent_run_dir=run,plan=SimpleNamespace(reused=()),reconciliations=(response,))
    assert store.snapshot()==before


def test_completed_history_with_failed_corrupt_media_requires_inactive_queue(runtime_run,monkeypatch):
    from video_ai.runtime.pipeline_recovery import ReconciliationContext,reconcile_submission,_native_saved_validation
    from video_ai.runtime.logging import RunLogger
    run,config,store,output,response=fixture(runtime_run,monkeypatch)
    history=run/'logs/pipeline/TEST-ONLY-history.json'
    prompt=str(uuid4());entry=json.loads(history.read_text())['test-prompt'];entry['prompt'][1]=prompt
    history.write_text(json.dumps({prompt:entry}))
    def accepted(data):
        data['units']['image']['shot_0001']['submission'].update(state='accepted',prompt_id=prompt,number=1,response_path=str(history))
    store.update(accepted)
    store.update(lambda data:data['units']['image']['shot_0001']['submission'].update(state='completed'))
    output.write_bytes(b'corrupt PNG from completed original submission')
    trace=RunLogger(run).exception('start_images','shot_0001',ValueError('original output media decode failed'))
    store.record_unit('image','shot_0001','failed',error=dict(kind='failed',message='original output media decode failed',traceback_path=str(trace),evidence_paths=[str(trace)]))
    before=store.snapshot()
    class Http:
        timeout=2
        queue_available=True
        def request(self,method,path,**kwargs):
            assert method=='GET'
            if path=='/queue' and not self.queue_available:raise OSError('queue unavailable')
            data={'queue_running':[],'queue_pending':[]} if path=='/queue' else json.loads(history.read_text())
            path=RunLogger(run).save_json('pipeline/GET-'+uuid4().hex+'.json',data)
            return SimpleNamespace(data=data,evidence_path=path)
        def parse_json(self,response,**kwargs):return response.data
    http=Http()
    context=ReconciliationContext(run,before,http,lambda stage,uid,saved,entry,graph:_native_saved_validation(config,run,stage,uid,saved,entry,graph))
    result=reconcile_submission(context,'start_images','shot_0001')
    assert result.state=='failed' and 'invalid media' in result.reason
    assert result.evidence_identities and not result.output_identities
    http.queue_available=False
    assert reconcile_submission(context,'start_images','shot_0001').state=='unresolved'
    assert store.snapshot()==before


def test_rejected_post_without_response_path_requires_immutable_registered_graph(runtime_run,monkeypatch):
    from video_ai.runtime.pipeline_recovery import validate_failed_submission
    run,config,store,output,response=fixture(runtime_run,monkeypatch)
    request=run/'logs/http/original.request.json'
    # Companions use the original unique HTTP token, irrespective of whether
    # submit_once received its HttpResponse object before the HTTP 400 raised.
    body=run/'logs/http/original.body';body.write_text(json.dumps({'error':{'type':'prompt_outputs_failed_validation'}}))
    (run/'logs/http/original.response.json').write_text(json.dumps(dict(method='POST',url=config.services['comfyui']+'/prompt',
        status=400,truncated=False,error=None)))
    store.update(lambda data:data['units']['image']['shot_0001']['submission'].update(state='rejected'))
    saved=store.snapshot()['units']['image']['shot_0001']['submission']
    proof=validate_failed_submission(run,'start_images','shot_0001',saved)
    assert str(body) in {identity.path for identity in proof} and saved['response_path'] is None
    graph_path=Path(saved['request_path']);graph=json.loads(graph_path.read_text());graph['1']['inputs']['seed']+=1
    graph_path.write_text(json.dumps(graph));http=json.loads(request.read_text());http['json_body']['prompt']=graph;request.write_text(json.dumps(http))
    with pytest.raises(ValueError,match='graph identity changed'):
        validate_failed_submission(run,'start_images','shot_0001',saved)


def test_nested_saved_child_flattens_both_real_request_origins_and_waits_review(runtime_run,monkeypatch):
    from video_ai.runtime._pipeline_saved_import import derive_reconciled_run,consume_reconciled_unit
    from video_ai.runtime.pipeline_import import load_pipeline_import
    from video_ai.runtime.pipeline_recovery import Reconciliation,_native_saved_validation
    from video_ai.runtime import start_image_checks as owner,pipeline_stages
    from video_ai.runtime.manifest import ManifestStore,hash_file,thaw
    from video_ai.planning.start_images import image_parameters
    root,config,root_store,first_output,first_response=fixture(runtime_run,monkeypatch)
    board,_=owner._input_files(config,root)
    board['shots'].append(dict(shot_id='shot_0002',primary_unit_id='speech_0002',image_prompt='a second blue bird',entity_ids=[]))
    for shot in board['shots']:shot.update(visual_requirements=[],bindings=[])
    monkeypatch.setattr(owner,'load_committed_storyboard',lambda r:board)
    first=derive_reconciled_run(config,parent_run_dir=root,plan=SimpleNamespace(reused=()),reconciliations=(first_response,))
    old_receipt=load_pipeline_import(first);first_store=ManifestStore.open(first)
    first_store.record_stage('start_images','running');first_store.record_unit('image','shot_0002','running')
    p=image_parameters(board['shots'][1],board['global_visual'],768,432)
    graph=owner._template(config).instantiate(dict(positive_prompt=p['positive'],negative_prompt=p['negative'],seed=p['seed'],width=768,height=432),
        output_prefix=f'{first.name}/start_images/shot_0002')
    attempt,client=str(uuid4()),str(uuid4());request=first/'workflows'/f'{attempt}.json';request.parent.mkdir(exist_ok=True);request.write_text(json.dumps(graph))
    logs=first/'logs/http';logs.mkdir(parents=True,exist_ok=True)
    (logs/'second.request.json').write_text(json.dumps(dict(method='POST',url=config.services['comfyui']+'/prompt',stage='start_images',
        unit_id='shot_0002',timeout=2,json_body={'prompt':graph,'client_id':client})))
    output=first/'comfy/output'/first.name/'start_images/shot_0002_00001_.png';output.parent.mkdir(parents=True);output.write_bytes(first_output.read_bytes())
    saved=dict(attempt_id=attempt,client_id=client,state='intent',request_path=str(request),response_path=None,prompt_id=None,number=None,
        submitted_at='2026-01-01T00:00:00+00:00',last_seen_at=None)
    def register(data):data['units']['image']['shot_0002']['submission']=saved;data['workflows'][attempt]=thaw(hash_file(request))
    first_store.update(register)
    history={'prompt':[1,'second-prompt',graph,{'client_id':client},['1']],'status':{'completed':True,'status_str':'success'},
        'outputs':{'1':{'images':[dict(filename=output.name,subfolder=f'{first.name}/start_images',type='output')]}}}
    history_path=first/'logs/pipeline/TEST-ONLY-second-history.json';history_path.write_text(json.dumps({'second-prompt':history}))
    checked=_native_saved_validation(config,first,'start_images','shot_0002',saved,history,graph)
    response=Reconciliation('start_images','shot_0002',attempt,'second-prompt','completed',
        (*checked.evidence_identities,hash_file(history_path)),checked.output_identities,'TEST ONLY second saved response')
    root_before=root_store.snapshot();first_before=first_store.snapshot()
    second=derive_reconciled_run(config,parent_run_dir=first,plan=SimpleNamespace(reused=()),reconciliations=(response,))
    receipt=load_pipeline_import(second);rows={row['id']:row for row in receipt['units']}
    assert rows['shot_0001']['imported_record']['origin_run_id']==root.name
    assert rows['shot_0001']['imported_record']['source_report_identity']==old_receipt['units'][0]['imported_record']['source_report_identity']
    assert rows['shot_0002']['imported_record']['origin_run_id']==first.name
    assert consume_reconciled_unit(first,rows['shot_0001'])['submission']['attempt_id']==first_response.attempt_id
    assert consume_reconciled_unit(first,rows['shot_0002'])['submission']['attempt_id']==attempt
    review=second/'TEST-ONLY-storyboard-review.json';review.write_text('{}');board['review_identity']=thaw(hash_file(review));board['run_id']=second.name
    (second/'storyboard.json').write_text(json.dumps(board));(second/'storyboard-draft.json').write_text('{}')
    def inputs(c,r):
        if r!=second:return board,{}
        return board,{key:hash_file(path) for key,path in dict(storyboard=r/'storyboard.json',config=c.config_file,
            storyboard_draft=r/'storyboard-draft.json',storyboard_review=review,ffmpeg=c.tools['ffmpeg'],ffprobe=c.tools['ffprobe']).items()}
    monkeypatch.setattr(owner,'_input_files',inputs)
    def forbidden(*a,**k):raise AssertionError('both saved origins must produce zero child POSTs')
    monkeypatch.setattr(owner,'_generate_owned',forbidden)
    result=pipeline_stages.prepare('start_images',config,second,options={},reviews={},store=ManifestStore.open(second))
    assert result.status=='review_required',ManifestStore.open(second).snapshot()['stages']['start_images']['error']
    assert all(unit['submission'] is None for unit in ManifestStore.open(second).snapshot()['units']['image'].values())
    assert root_store.snapshot()==root_before and first_store.snapshot()==first_before
    first_output.write_bytes(b'late root origin media corruption')
    with pytest.raises(ValueError):load_pipeline_import(second)


def test_coordinator_reconciles_saved_images_derives_admitted_child_and_waits_review(timeline_run,monkeypatch):
    """Real PCM/timeline/storyboard/import/media; no handmade child artifacts."""
    import shutil
    from video_ai.config import load_config
    from video_ai import pipeline
    from video_ai.runtime import start_image_checks as owner,pipeline_inventory,pipeline_recovery,preflight as admission
    from video_ai.runtime.paths import RuntimePaths,create_run
    from video_ai.runtime.manifest import create_manifest,hash_file,thaw,ManifestStore,now
    from video_ai.runtime.timeline_checks import _artifact
    from video_ai.runtime.pipeline_recovery import ReconciliationContext,_completed_stage_validator
    from video_ai.runtime.logging import RunLogger
    from video_ai.planning.start_images import image_parameters
    from storyboard_helpers import make_storyboard_run,mock_generation,review_for,write_review
    from video_ai.runtime.storyboard_checks import plan_storyboard,finalize_storyboard,load_committed_storyboard
    old,base,_,legacy=timeline_run;run=create_run(RuntimePaths.from_config(base))
    model=run/'TEST-ONLY-model.bin';model.write_bytes(b'fixture model never loaded')
    raw=thaw(base.raw);raw['models']['sdxl']=str(model);raw['voice_config']=str(base.voice.config_file)
    raw['workflows']={key:str(value) for key,value in base.workflows.items()}
    raw['media']['profile']='fast';path=run/'TEST-ONLY-config.json';path.write_text(json.dumps(raw))
    config=load_config(path);data=json.loads(json.dumps(legacy));data['run_dir']=str(run)
    inputs={key:hash_file(value) for key,value in dict(script=Path(data['source']['path']),config=path,voice=config.voice.config_file).items()}
    store=create_manifest(run,config,inputs=inputs,models={},workflows={});store.record_stage('speech','running')
    (run/'script.txt').write_bytes((old/'script.txt').read_bytes());data['script_copy']=thaw(hash_file(run/'script.txt'));data['inputs']=thaw(inputs)
    for item in data['spans']:
        if item['kind']!='speech':continue
        pcm=run/'audio'/item['unit_id']/'pcm-48000.wav';pcm.parent.mkdir(parents=True);shutil.copyfile(item['pcm']['path'],pcm)
        item['pcm']=_artifact(hash_file(pcm));store.record_unit('speech',item['unit_id'],'running');store.record_unit('speech',item['unit_id'],'completed',artifacts=[item['pcm']])
    (run/'segments.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');store.record_stage('speech','completed',artifacts=[_artifact(hash_file(run/'segments.json'))])
    # Explicit TEST ONLY author record, bound to these actual PCM copies.
    (run/'voice-listening.json').write_text(json.dumps(dict(schema_version=1,listened=True,accepted=True,segments_identity=thaw(hash_file(run/'segments.json')),
        user_statement='TEST ONLY fixture acceptance',accepted_at=now(),audio=[dict(unit_id=i['unit_id'],text=i['text'],samples=i['samples'],pcm=i['pcm']) for i in data['spans'] if i['kind']=='speech'])))
    _,_,_,_,timing=make_storyboard_run((run,config,store,data));mock_generation(monkeypatch)
    assert plan_storyboard(config,run_dir=run,timing_review_path=timing).status=='review_required'
    assert finalize_storyboard(config,run_dir=run,review_path=write_review(run,review_for(run))).passed
    board=load_committed_storyboard(run)
    def instantiate(values,*,output_prefix):return {'1':{'class_type':'SaveImage','inputs':dict(values,filename_prefix=output_prefix)}}
    template=SimpleNamespace(instantiate=instantiate,mapping={'output':{'node_id':'1','collection':'images'},
        'inputs':{'width':{'node_id':'1','input':'width'},'height':{'node_id':'1','input':'height'}}})
    monkeypatch.setattr(owner,'_model',lambda *a:(hash_file(model),{}));monkeypatch.setattr(owner,'_template',lambda *a:template)
    store.record_stage('start_images','running');history={};first=None
    for shot in board['shots']:
        uid=shot['shot_id'];parameters=image_parameters(shot,board['global_visual'],768,432)
        graph=instantiate(dict(positive_prompt=parameters['positive'],negative_prompt=parameters['negative'],seed=parameters['seed'],width=768,height=432),
            output_prefix=f'{run.name}/start_images/{uid}')
        attempt,client,prompt=str(uuid4()),str(uuid4()),str(uuid4());request=run/'workflows'/f'{attempt}.json';request.parent.mkdir(exist_ok=True);request.write_text(json.dumps(graph))
        logger=RunLogger(run);logger.save_json('http/POST-'+uid+'.request.json',dict(method='POST',url=config.services['comfyui']+'/prompt',stage='start_images',unit_id=uid,
            timeout=2,json_body={'prompt':graph,'client_id':client}))
        output=run/'comfy/output'/run.name/'start_images'/(uid+'_00001_.png');output.parent.mkdir(parents=True,exist_ok=True)
        if first is None:
            subprocess.run([str(config.tools['ffmpeg']),'-nostdin','-v','error','-n','-f','lavfi','-i','color=red:s=768x432','-frames:v','1','-pix_fmt','rgb24',str(output)],check=True);first=output
        else:output.write_bytes(first.read_bytes())
        store.record_unit('image',uid,'running')
        saved=dict(attempt_id=attempt,client_id=client,state='intent',request_path=str(request),response_path=None,prompt_id=None,number=None,
            submitted_at='2026-01-01T00:00:00+00:00',last_seen_at=None)
        def register(value,u=uid,s=saved,a=attempt,p=request):value['units']['image'][u]['submission']=s;value['workflows'][a]=thaw(hash_file(p))
        store.update(register)
        history[prompt]=dict(prompt=[1,prompt,graph,{'client_id':client},['1']],status={'completed':True,'status_str':'success'},
            outputs={'1':{'images':[dict(filename=output.name,subfolder=f'{run.name}/start_images',type='output')]}})
    class Http:
        timeout=2
        def __init__(self,r):self.run=r
        def request(self,method,path,**kwargs):
            assert method=='GET'
            data={'queue_running':[],'queue_pending':[]} if path=='/queue' else history
            evidence=RunLogger(self.run).save_json('pipeline/GET-'+uuid4().hex+'.json',data)
            return SimpleNamespace(data=data,evidence_path=evidence)
        def parse_json(self,response,**kwargs):return response.data
    monkeypatch.setattr(pipeline_recovery,'_context',lambda r:ReconciliationContext(r,ManifestStore.open(r).snapshot(),Http(r),_completed_stage_validator(config,r)))
    monkeypatch.setattr(admission,'preflight',lambda *a,**k:admission.PreflightReport((admission.PreflightCheck('TEST ONLY',True,'fresh resource admission'),)))
    def projection(c,identities):
        value=thaw(c);value.pop('raw');value['voice'].pop('raw');return value
    monkeypatch.setattr(pipeline_inventory,'config_projection',projection)
    def forbidden(*a,**k):raise AssertionError('saved output recovery must not generate models')
    monkeypatch.setattr(owner,'_generate_owned',forbidden)
    before=store.snapshot();result=pipeline.resume_pipeline(config,run_dir=run)
    child=result.run_dir;assert child!=run and result.parent_run_dir==run
    assert result.status=='awaiting_review' and result.waiting_for==('start_images',)
    current=ManifestStore.open(child).snapshot()
    assert all(current['stages'][stage]['status']=='completed' for stage in ('preflight','speech','timeline','storyboard'))
    assert current['stages']['start_images']['status']=='running' and (child/'images-draft.json').exists()
    assert not (child/'images.json').exists() and not (child/'logs/http').exists()
    options,_=pipeline._options(child);assert options['script']==Path(inputs['script'].path)
    assert all(unit['submission'] is None for unit in current['units']['image'].values())
    after=store.snapshot();assert after['stages']==before['stages'] and after['units']==before['units']
    assert all(after['workflows'][key]==value for key,value in before['workflows'].items())
    assert after['events'][:len(before['events'])]==before['events']
