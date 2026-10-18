from pathlib import Path
from types import SimpleNamespace
import pytest
from video_ai.runtime.pipeline_recovery import ReconciliationContext, reconcile_submission
from video_ai.runtime.manifest import hash_file, thaw


class Http:
    timeout=2
    def __init__(self,responses,directory):
        self.responses=responses;self.calls=[];self.directory=directory
    def request(self,method,path,**kwargs):
        assert method=='GET'
        self.calls.append((method,path,kwargs))
        result=self.responses[path]
        if isinstance(result,Exception):raise result
        p=self.directory/f'get-{len(self.calls)}.json'
        import json
        p.write_text(json.dumps(result),encoding='utf-8')
        return SimpleNamespace(evidence_path=p,data=result)
    def parse_json(self,response,**kwargs):return response.data


def context(tmp_path,*,prompt_id=None,history=None,queue=None,validator=None):
    graph={'1':{'class_type':'SaveImage','inputs':{'filename_prefix':'actual','seed':23}}}
    request=tmp_path/'graph.json'
    import json
    request.write_text(json.dumps(graph),encoding='utf-8')
    submission=dict(attempt_id='attempt',client_id='client',prompt_id=prompt_id,
        state='intent' if prompt_id is None else 'accepted',request_path=str(request))
    snapshot={'units':{'image':{'shot_0001':{'submission':submission}}},
              'workflows':{'attempt':thaw(hash_file(request))}}
    http=Http({'/queue':queue or {'queue_running':[],'queue_pending':[]},
        '/history'+('/'+prompt_id if prompt_id else ''):history or {}},tmp_path)
    c=ReconciliationContext(run_dir=tmp_path,snapshot=snapshot,http=http,
        revalidate=validator)
    return c,http,graph


def entry(graph,*,state='success',client_id='client',outputs=None):
    return dict(prompt=[1,'p1',graph,{'client_id':client_id},['1']],
        status={'status_str':state,'completed':True},
        outputs=outputs or {'1':{'images':[{'filename':'actual.png','subfolder':'','type':'output'}]}})


def test_empty_queue_and_history_does_not_prove_unsubmitted(tmp_path):
    c,http,_=context(tmp_path)
    result=reconcile_submission(c,'start_images','shot_0001')
    assert result.state=='unresolved' and result.prompt_id is None
    assert len(http.calls)==2 and result.evidence_identities
    assert c.snapshot['units']['image']['shot_0001']['submission']['state']=='intent'


def test_saved_id_requests_only_same_id_history(tmp_path):
    c,http,graph=context(tmp_path,prompt_id='p1')
    http.responses['/queue']={'queue_running':[[1,'p1',graph,{'client_id':'client'},[]]],'queue_pending':[]}
    result=reconcile_submission(c,'start_images','shot_0001')
    assert result.state=='still_running' and result.prompt_id=='p1'
    assert [p for _,p,_ in http.calls]==['/queue','/history/p1']


def test_intent_unique_matching_metadata_graph_required(tmp_path):
    c,http,graph=context(tmp_path)
    http.responses['/queue']={'queue_running':[[1,'p1',graph,{'client_id':'client'},[]]],'queue_pending':[]}
    result=reconcile_submission(c,'start_images','shot_0001')
    assert result.state=='still_running' and result.prompt_id=='p1'


def test_ambiguous_duplicate_matching_candidates_stays_unresolved(tmp_path):
    c,http,graph=context(tmp_path)
    http.responses['/history']={'p1':entry(graph),'p2':dict(entry(graph),prompt=[1,'p2',graph,{'client_id':'client'},['1']])}
    assert reconcile_submission(c,'start_images','shot_0001').state=='unresolved'


def test_matching_filename_without_exact_graph_is_not_a_match(tmp_path):
    c,http,graph=context(tmp_path)
    import copy
    different=copy.deepcopy(graph);different['1']['inputs']['seed']=24
    http.responses['/history']={'p1':entry(different)}
    assert reconcile_submission(c,'start_images','shot_0001').state=='unresolved'


def test_success_history_needs_full_real_output_and_parameter_revalidation(tmp_path):
    c,http,graph=context(tmp_path)
    http.responses['/history']={'p1':entry(graph)}
    result=reconcile_submission(c,'start_images','shot_0001')
    assert result.state=='unresolved' and not result.output_identities


def test_revalidated_completed_saved_submission_preserves_old_intent(tmp_path):
    output=tmp_path/'comfy/output/actual.png';output.parent.mkdir(parents=True)
    output.write_bytes(b'test-only output; validator fixture')
    seen=[]
    def verify(stage,unit_id,submission,history,graph):
        seen.append((stage,unit_id,submission['attempt_id']))
        assert graph['1']['inputs']['seed']==23
        return (hash_file(output),)
    c,http,graph=context(tmp_path,validator=verify)
    http.responses['/history']={'p1':entry(graph)}
    result=reconcile_submission(c,'start_images','shot_0001')
    assert result.state=='completed' and result.prompt_id=='p1'
    assert result.output_identities[0].sha256==hash_file(output).sha256
    assert seen==[('start_images','shot_0001','attempt')]
    assert c.snapshot['units']['image']['shot_0001']['submission']['prompt_id'] is None


def test_explicit_execution_failure_is_failed(tmp_path):
    c,http,graph=context(tmp_path,prompt_id='p1')
    http.responses['/history/p1']={'p1':entry(graph,state='error')}
    assert reconcile_submission(c,'start_images','shot_0001').state=='failed'


def test_service_unavailable_finite_no_start_no_post(tmp_path):
    c,http,_=context(tmp_path)
    http.responses={p:OSError('service unavailable') for p in http.responses}
    result=reconcile_submission(c,'start_images','shot_0001')
    assert result.state=='unresolved' and len(http.calls)==2


def test_saved_graph_drift_refused_before_network(tmp_path):
    c,http,_=context(tmp_path)
    Path(c.snapshot['units']['image']['shot_0001']['submission']['request_path']).write_text('{}')
    result=reconcile_submission(c,'start_images','shot_0001')
    assert result.state=='unresolved' and not http.calls


def test_tts_unknown_is_not_reposted_or_queried_comfy(tmp_path):
    c,http,_=context(tmp_path)
    c.snapshot['units']['speech']={'speech_0001':{'submission':{'state':'ambiguous','attempt_id':'tts'}}}
    assert reconcile_submission(c,'speech','speech_0001').state=='unresolved'
    assert not http.calls


def test_success_does_not_admit_unmapped_output_identity(tmp_path):
    output=tmp_path/'wrong.png';output.write_bytes(b'wrong output')
    c,http,graph=context(tmp_path,validator=lambda *args:(hash_file(output),))
    http.responses['/history']={'p1':entry(graph)}
    assert reconcile_submission(c,'start_images','shot_0001').state=='unresolved'


def test_saved_history_graph_mismatch_refuses_even_success(tmp_path):
    c,http,graph=context(tmp_path,prompt_id='p1')
    import copy
    altered=copy.deepcopy(graph);altered['1']['inputs']['seed']=25
    http.responses['/history/p1']={'p1':entry(altered)}
    assert reconcile_submission(c,'start_images','shot_0001').state=='unresolved'


def test_graph_late_mutation_during_output_consumer_refuses(tmp_path):
    output=tmp_path/'comfy/output/actual.png';output.parent.mkdir(parents=True);output.write_bytes(b'fixture')
    def verify(stage,unit,sub,*args):
        Path(sub['request_path']).write_text('{}')
        return (hash_file(output),)
    c,http,graph=context(tmp_path,validator=verify)
    http.responses['/history']={'p1':entry(graph)}
    assert reconcile_submission(c,'start_images','shot_0001').state=='unresolved'


def test_active_queue_conflicting_final_history_does_not_allow_retry(tmp_path):
    c,http,graph=context(tmp_path,prompt_id='p1')
    http.responses['/queue']={'queue_running':[[1,'p1',graph,{'client_id':'client'},[]]],'queue_pending':[]}
    http.responses['/history/p1']={'p1':entry(graph,state='error')}
    assert reconcile_submission(c,'start_images','shot_0001').state=='unresolved'


def test_invalid_parameter_or_media_consumer_failure_remains_unresolved(tmp_path):
    def verify(*args):raise ValueError('actual media or graph parameter mismatch')
    c,http,graph=context(tmp_path,validator=verify)
    http.responses['/history']={'p1':entry(graph)}
    assert reconcile_submission(c,'start_images','shot_0001').state=='unresolved'


def test_unavailable_queue_does_not_prove_failed_request_no_longer_running(tmp_path):
    c,http,graph=context(tmp_path,prompt_id='p1')
    http.responses['/queue']=OSError('unknown queue')
    http.responses['/history/p1']={'p1':entry(graph,state='error')}
    assert reconcile_submission(c,'start_images','shot_0001').state=='unresolved'


def test_checkpointless_native_saved_image_replays_parameters_and_real_full_png_decode(run_store,monkeypatch):
    """Model input owners are explicit TEST ONLY boundaries; media decoding is real."""
    from dataclasses import replace
    import json
    import subprocess
    from video_ai.config import load_config
    from video_ai.runtime.pipeline_recovery import _native_saved_validation
    from video_ai.runtime import start_image_checks as owner
    from video_ai.planning.start_images import image_parameters
    from types import SimpleNamespace
    store=run_store;run=store.run_dir
    base=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    config=replace(base,media=replace(base.media,profile=replace(base.media.profile,width=768,height=432)))
    board={'global_visual':{'style':'TEST ONLY','color_palette':'red','lighting':'day','entities':[]},
           'shots':[{'shot_id':'shot_0001','primary_unit_id':'speech_0001','image_prompt':'one red bird','entity_ids':[]}]}
    p=image_parameters(board['shots'][0],board['global_visual'],768,432)
    def instantiate(values,*,output_prefix):
        return {'1':{'class_type':'TEST ONLY','inputs':dict(values,filename_prefix=output_prefix)}}
    template=SimpleNamespace(instantiate=instantiate,mapping={'output':{'node_id':'1','collection':'images'},
        'inputs':{'width':{'node_id':'1','input':'width'},'height':{'node_id':'1','input':'height'}}})
    actual=instantiate(dict(positive_prompt=p['positive'],negative_prompt=p['negative'],seed=p['seed'],width=768,height=432),
        output_prefix=f'{run.name}/start_images/shot_0001')
    leaf=run/'TEST-ONLY-model.bin';leaf.write_bytes(b'fixture model never loaded')
    workflow=run/'TEST-ONLY-workflow.json';workflow.write_text('{}');workflow.with_suffix('.mapping.json').write_text('{}')
    config=replace(config,workflows=dict(config.workflows,sdxl=workflow))
    monkeypatch.setattr(owner,'_input_files',lambda *a:(board,{}))
    monkeypatch.setattr(owner,'_directions',lambda *a:({},{}))
    monkeypatch.setattr(owner,'_model',lambda *a:(hash_file(leaf),{}))
    monkeypatch.setattr(owner,'_template',lambda *a:template)
    request=run/'workflows/TEST-ONLY-request.json';request.parent.mkdir(exist_ok=True);request.write_text(json.dumps(actual))
    logs=run/'logs/http';logs.mkdir(parents=True,exist_ok=True)
    (logs/'original.request.json').write_text(json.dumps(dict(method='POST',url=config.services['comfyui']+'/prompt',
        stage='start_images',unit_id='shot_0001',timeout=2,json_body={'client_id':'test-client','prompt':actual})))
    output=run/'comfy/output'/run.name/'start_images/shot_0001_00001_.png';output.parent.mkdir(parents=True)
    subprocess.run([str(config.tools['ffmpeg']),'-nostdin','-v','error','-n','-f','lavfi','-i','color=red:s=768x432',
        '-frames:v','1','-pix_fmt','rgb24',str(output)],check=True)
    saved={'attempt_id':'test-attempt','client_id':'test-client','request_path':str(request),
           'submitted_at':'2026-01-01T00:00:00+00:00'}
    history={'prompt':[1,'test-prompt',actual,{'client_id':'test-client'},['1']],
        'status':{'completed':True,'status_str':'success'},
        'outputs':{'1':{'images':[{'filename':output.name,'subfolder':f'{run.name}/start_images','type':'output'}]}}}
    before=store.snapshot()
    validation=_native_saved_validation(config,run,'start_images','shot_0001',saved,history,actual)
    assert validation.output_identities[0].sha256==hash_file(output).sha256
    assert validation.record['parameters']==p and validation.evidence_identities
    assert store.snapshot()==before
    wrong=json.loads(json.dumps(actual));wrong['1']['inputs']['seed']+=1
    history['prompt'][2]=wrong
    (logs/'original.request.json').write_text(json.dumps(dict(method='POST',url=config.services['comfyui']+'/prompt',
        stage='start_images',unit_id='shot_0001',timeout=2,json_body={'client_id':'test-client','prompt':wrong})))
    with pytest.raises(ValueError,match='reconstructed parameters'):
        _native_saved_validation(config,run,'start_images','shot_0001',saved,history,wrong)


def _saved_native_media_fixture(store,config,stage,uid,graph,output):
    import json
    request=store.run_dir/'workflows/TEST-ONLY-native-request.json';request.parent.mkdir(exist_ok=True)
    request.write_text(json.dumps(graph))
    logs=store.run_dir/'logs/http';logs.mkdir(parents=True,exist_ok=True)
    (logs/'TEST-ONLY-native.request.json').write_text(json.dumps(dict(method='POST',url=config.services['comfyui']+'/prompt',
        stage=stage,unit_id=uid,timeout=2,json_body={'client_id':'test-client','prompt':graph})))
    saved=dict(attempt_id='test-attempt',client_id='test-client',request_path=str(request),submitted_at='2026-01-01T00:00:00+00:00')
    entry=dict(prompt=[1,'test-prompt',graph,{'client_id':'test-client'},['1']],status={'completed':True,'status_str':'success'},
        outputs={'1':{'gifs' if stage=='source_clips' else 'images':[dict(filename=output.name,
            subfolder=output.parent.relative_to(store.run_dir/'comfy/output').as_posix(),type='output')]}})
    return saved,entry


def test_native_saved_source_replays_real_mp4_frames_and_refuses_stale_output_or_changed_input(run_store,monkeypatch):
    import subprocess,os
    from video_ai.config import load_config
    from video_ai.runtime.pipeline_recovery import _native_saved_validation
    from video_ai.runtime import _source_clip_inputs as owner
    run=run_store.run_dir;config=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    original=run/'TEST-ONLY-start.png'
    subprocess.run([str(config.tools['ffmpeg']),'-nostdin','-v','error','-n','-f','lavfi','-i','color=red:s=768x432','-frames:v','1','-pix_fmt','rgb24',str(original)],check=True)
    copied=run/'comfy/input'/run.name/'source_clips/shot_0001/start.png';copied.parent.mkdir(parents=True);copied.write_bytes(original.read_bytes())
    plan=SimpleNamespace(shot_id='shot_0001',primary_unit_id='speech_0001',parameters=dict(width=768,height=432,length=5,seed=23),
        budget=dict(required_native_frames=4),start_image_identity=thaw(hash_file(original)))
    graph={'1':{'class_type':'VHS_VideoCombine','inputs':dict(length=5,seed=23,filename_prefix=f'{run.name}/source_clips/shot_0001/attempt_0001')}}
    template=SimpleNamespace(mapping={'output':{'node_id':'1','collection':'gifs'}})
    monkeypatch.setattr(owner,'inputs',lambda *a:dict(identities={'start':hash_file(original)},template=template,plans=[plan]))
    monkeypatch.setattr(owner,'graph',lambda *a:graph)
    output=run/'comfy/output'/run.name/'source_clips/shot_0001/attempt_0001_00001_.mp4';output.parent.mkdir(parents=True)
    subprocess.run([str(config.tools['ffmpeg']),'-nostdin','-v','error','-n','-f','lavfi','-i','color=red:s=768x432:r=16',
        '-frames:v','5','-c:v','libx264','-pix_fmt','yuv420p',str(output)],check=True)
    saved,entry=_saved_native_media_fixture(run_store,config,'source_clips','shot_0001:attempt_0001',graph,output)
    before=run_store.snapshot()
    checked=_native_saved_validation(config,run,'source_clips','shot_0001:attempt_0001',saved,entry,graph)
    assert checked.record['generated_frames']==5 and checked.record['source_frames']==4
    assert checked.record['selected_attempt_id']=='attempt_0001' and run_store.snapshot()==before
    timestamp=output.stat().st_mtime_ns;os.utime(output,ns=(1,1))
    with pytest.raises(ValueError,match='predates'):_native_saved_validation(config,run,'source_clips','shot_0001:attempt_0001',saved,entry,graph)
    os.utime(output,ns=(timestamp,timestamp));copied.write_bytes(b'changed actual Wan input')
    with pytest.raises(ValueError,match='input copy differs'):_native_saved_validation(config,run,'source_clips','shot_0001:attempt_0001',saved,entry,graph)


def test_native_saved_upscale_matches_real_source_frame_pixels_before_admitting_rgb_png(run_store,monkeypatch):
    import subprocess
    from video_ai.config import load_config
    from video_ai.runtime.pipeline_recovery import _native_saved_validation
    from video_ai.runtime import _upscale_inputs as owner
    run=run_store.run_dir;config=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    source=run/'TEST-ONLY-source.mp4'
    subprocess.run([str(config.tools['ffmpeg']),'-nostdin','-v','error','-n','-f','lavfi','-i','color=red:s=768x432:r=16',
        '-frames:v','1','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
    original=run/'shots/shot_0001/frames/frame_000001.png';original.parent.mkdir(parents=True)
    subprocess.run([str(config.tools['ffmpeg']),'-nostdin','-v','error','-n','-i',str(source),'-vf','select=eq(n\\,0),format=rgb24',
        '-frames:v','1',str(original)],check=True)
    copied=run/'comfy/input'/run.name/'upscale/shot_0001/frame_000001.png';copied.parent.mkdir(parents=True);copied.write_bytes(original.read_bytes())
    leaf=run/'TEST-ONLY-upscale-model.bin';leaf.write_bytes(b'never loaded')
    plan=SimpleNamespace(shot_id='shot_0001',source_identity=thaw(hash_file(source)),source_frames=1,parameters={'scale':4,'seed':23})
    graph={'1':{'class_type':'SaveImage','inputs':dict(scale=4,seed=23,filename_prefix=f'{run.name}/upscale/shot_0001/frame_000001')}}
    template=SimpleNamespace(mapping={'output':{'node_id':'1','collection':'images'}})
    context=dict(identities={name:hash_file(leaf) for name in ('workflow','mapping','model')},template=template,plans=[plan],
        source={'clips':[dict(shot_id='shot_0001',width=768,height=432)]})
    monkeypatch.setattr(owner,'inputs',lambda *a:context);monkeypatch.setattr(owner,'graph',lambda *a:graph)
    output=run/'comfy/output'/run.name/'upscale/shot_0001/frame_000001_00001_.png';output.parent.mkdir(parents=True)
    subprocess.run([str(config.tools['ffmpeg']),'-nostdin','-v','error','-n','-f','lavfi','-i','color=red:s=1920x1080',
        '-frames:v','1','-pix_fmt','rgb24',str(output)],check=True)
    saved,entry=_saved_native_media_fixture(run_store,config,'upscale','shot_0001:frame_000001',graph,output)
    before=run_store.snapshot();checked=_native_saved_validation(config,run,'upscale','shot_0001:frame_000001',saved,entry,graph)
    assert checked.record['source_frame_index']==0 and checked.output_identities[0].sha256==hash_file(output).sha256
    assert run_store.snapshot()==before
    alternate=run/'TEST-ONLY-wrong-frame.png'
    subprocess.run([str(config.tools['ffmpeg']),'-nostdin','-v','error','-n','-f','lavfi','-i','color=blue:s=768x432',
        '-frames:v','1','-pix_fmt','rgb24',str(alternate)],check=True)
    original.write_bytes(alternate.read_bytes());copied.write_bytes(alternate.read_bytes())
    with pytest.raises(ValueError,match='input pixels differ'):
        _native_saved_validation(config,run,'upscale','shot_0001:frame_000001',saved,entry,graph)


@pytest.mark.parametrize('defect',['none','history_client','history_graph','history_prompt','namespace','artifact','receipt','response_bytes','response_unit'])
def test_saved_wan_second_attempt_requires_exact_registered_known_short_origin(run_store,monkeypatch,defect):
    import json,subprocess
    from uuid import uuid4
    from video_ai.config import load_config
    from video_ai.runtime.pipeline_recovery import _native_saved_validation
    from video_ai.runtime import _source_clip_inputs as owner
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.timeline_checks import _artifact
    from video_ai.media.video import inspect_video
    from video_ai.planning.source_clips import supplement_frames
    run=run_store.run_dir;config=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    original=run/'TEST-ONLY-start.png';original.write_bytes(b'explicit owner input fixture')
    copied=run/'comfy/input'/run.name/'source_clips/shot_0001/start.png';copied.parent.mkdir(parents=True);copied.write_bytes(original.read_bytes())
    plan=SimpleNamespace(shot_id='shot_0001',primary_unit_id='speech_0001',parameters=dict(width=768,height=432,length=13,seed=23),
        budget=dict(required_native_frames=10),start_image_identity=thaw(hash_file(original)))
    template=SimpleNamespace(mapping={'output':{'node_id':'1','collection':'gifs'}})
    def graph(t,r,p,length,attempt):return {'1':{'class_type':'VHS_VideoCombine','inputs':dict(length=length,seed=23,
        filename_prefix=f'{r.name}/source_clips/shot_0001/{attempt}')}}
    monkeypatch.setattr(owner,'inputs',lambda *a:dict(identities={'start':hash_file(original)},template=template,plans=[plan]))
    monkeypatch.setattr(owner,'graph',graph)
    def save_attempt(ordinal,length,frames):
        uid=f'shot_0001:attempt_{ordinal:04d}';actual=graph(template,run,plan,length,f'attempt_{ordinal:04d}')
        attempt,client,prompt=str(uuid4()),str(uuid4()),str(uuid4())
        intent=run/'workflows'/f'{attempt}.json';intent.parent.mkdir(exist_ok=True);intent.write_text(json.dumps(actual))
        logs=run/'logs/http';logs.mkdir(parents=True,exist_ok=True);stem=f'POST-{ordinal}'
        (logs/(stem+'.request.json')).write_text(json.dumps(dict(method='POST',url=config.services['comfyui']+'/prompt',stage='source_clips',unit_id=uid,
            timeout=2,json_body={'prompt':actual,'client_id':client})))
        body=json.dumps(dict(prompt_id=prompt,number=ordinal,node_errors={})).encode()
        (logs/(stem+'.response.json')).write_text(json.dumps(dict(method='POST',url=config.services['comfyui']+'/prompt',stage='source_clips',unit_id=uid,
            status=200,truncated=False,error=None,bytes=len(body))))
        (logs/(stem+'.body')).write_bytes(body)
        output=run/'comfy/output'/run.name/'source_clips/shot_0001'/f'attempt_{ordinal:04d}_00001_.mp4';output.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run([str(config.tools['ffmpeg']),'-nostdin','-v','error','-n','-f','lavfi','-i','color=red:s=768x432:r=16',
            '-frames:v',str(frames),'-c:v','libx264','-pix_fmt','yuv420p',str(output)],check=True)
        history=dict(prompt=[ordinal,prompt,actual,{'client_id':client},['1']],status={'completed':True,'status_str':'success'},
            outputs={'1':{'gifs':[dict(filename=output.name,subfolder=f'{run.name}/source_clips/shot_0001',type='output')]}})
        hp=run/'logs/http'/f'history-{ordinal}.body';hp.write_text(json.dumps({prompt:history}))
        saved=dict(attempt_id=attempt,client_id=client,state='intent',request_path=str(intent),response_path=None,prompt_id=None,number=None,
            submitted_at='2026-01-01T00:00:00+00:00',last_seen_at=None)
        run_store.record_unit('shot_attempt',uid,'running')
        def register(data):data['units']['shot_attempt'][uid]['submission']=saved;data['workflows'][attempt]=thaw(hash_file(intent))
        run_store.update(register)
        return uid,saved,actual,history,hp,prompt,output
    prior_id,prior,prior_graph,prior_entry,hp,prompt,prior_output=save_attempt(1,13,5)
    run_store.update(lambda data:data['units']['shot_attempt'][prior_id]['submission'].update(state='accepted',response_path=str(hp),prompt_id=prompt,number=1))
    run_store.update(lambda data:data['units']['shot_attempt'][prior_id]['submission'].update(state='completed'))
    info,logs=inspect_video(prior_output,width=768,height=432,config=config,paths=RuntimePaths.from_config(config),logger=RunLogger(run),unit_id=prior_id)
    run_store.record_unit('shot_attempt',prior_id,'failed',artifacts=[_artifact(hash_file(prior_output))],error=dict(kind='known_short',
        message='decoded 5 < required 10',traceback_path=None,evidence_paths=[str(p) for p in logs]))
    requested=supplement_frames(requested_frames=13,required_native_frames=10,actual_frames=5)
    uid,saved,actual,entry,_,_,output=save_attempt(2,requested,requested)
    if defect=='history_client':prior_entry['prompt'][3]['client_id']='wrong client'
    if defect=='history_graph':prior_entry['prompt'][2]['1']['inputs']['seed']+=1
    if defect=='history_prompt':prior_entry['prompt'][1]='wrong prompt'
    if defect=='namespace':
        foreign=run/'comfy/output'/run.name/'foreign'/prior_output.name;foreign.parent.mkdir();foreign.write_bytes(prior_output.read_bytes())
        prior_entry['outputs']['1']['gifs'][0]['subfolder']=f'{run.name}/foreign'
    if defect=='artifact':prior_output.write_bytes(prior_output.read_bytes()+b'changed trailing bytes')
    if defect=='receipt':
        log=json.loads(logs[0].read_text());log['info']['frames']=9;logs[0].write_text(json.dumps(log))
    if defect in ('response_bytes','response_unit'):
        response_path=run/'logs/http/POST-1.response.json';meta=json.loads(response_path.read_text())
        if defect=='response_bytes':meta['bytes']+=1
        else:meta['unit_id']='shot_0002:attempt_0001'
        response_path.write_text(json.dumps(meta))
    hp.write_text(json.dumps({prompt:prior_entry}))
    before=run_store.snapshot()
    if defect=='none':
        checked=_native_saved_validation(config,run,'source_clips',uid,saved,entry,actual)
        assert checked.record['parameters']['length']==requested and checked.record['attempts'][0]['actual_frames']==5
    else:
        with pytest.raises(ValueError):_native_saved_validation(config,run,'source_clips',uid,saved,entry,actual)
    assert run_store.snapshot()==before
