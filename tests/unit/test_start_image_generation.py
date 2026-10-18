from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import json
import pytest
from http_helpers import Response,ScriptedTransport
from image_helpers import write_png
from start_image_helpers import fake_media


def setup(run_store,runtime_run,monkeypatch,mode):
    from video_ai.runtime import start_image_checks as sc
    from video_ai.runtime.manifest import hash_file,thaw
    from video_ai.runtime.workflows import WorkflowTemplate
    from unit.test_workflows import remote_info
    run,config,paths=runtime_run
    model=run/config.models['sdxl'].name;model.write_bytes(b'test-only weights')
    config=replace(config,models=dict(config.models,sdxl=model),services=dict(config.services,ollama='http://127.0.0.1:11435'))
    template=WorkflowTemplate.load(config.workflows['sdxl'],config.workflows['sdxl'].with_suffix('.mapping.json'),config.models)
    if mode in ('mapping','swapped_prompts','extra_node'):
        if mode=='mapping':template.mapping['inputs']['width']=dict(node_id='12',input='steps')
        elif mode=='swapped_prompts':
            template.mapping['inputs']['positive_prompt'],template.mapping['inputs']['negative_prompt']=template.mapping['inputs']['negative_prompt'],template.mapping['inputs']['positive_prompt']
        else:template.graph['999']=dict(class_type='UnvalidatedReferenceNode',inputs={})
        monkeypatch.setattr(sc.WorkflowTemplate,'load',lambda *a:template)
    monkeypatch.setattr(sc,'_model',lambda c:(hash_file(model),dict(model=thaw(hash_file(model)))))
    fake_media(monkeypatch);actions=[];prompt_id=str(uuid4());outputs=[]
    class Manager:
        owned_pids=set()
        def __init__(self,*a,**kw):pass
        def ensure(self,spec):
            if mode=='missing_dirs':
                for name in ('input','output','temp','user'):
                    assert (run/'comfy'/name).is_dir(),f'Comfy {name} directory missing before startup'
            actions.append('start');return SimpleNamespace(owned=mode!='external',process=SimpleNamespace(poll=lambda:0))
        def stop(self,handle):actions.append('stop')
        def release_comfy_models(self,handle):actions.append('free')
    class Lease:
        def __init__(self,*a,**kw):pass
        def acquire(self,*a,**kw):
            if mode=='gpu_busy':raise sc.ServiceConflictError('external GPU')
            if mode=='gpu_unavailable':raise OSError('GPU telemetry unavailable')
            return nullcontext()
    monkeypatch.setattr(sc,'ServiceManager',Manager);monkeypatch.setattr(sc,'GpuLease',Lease,raising=False)
    def sampler(*a,**kw):
        if mode=='gpu_unavailable':raise OSError('GPU telemetry unavailable')
        return nullcontext()
    monkeypatch.setattr(sc,'ResourceSampler',sampler,raising=False)
    def route(request,timeout):
        assert timeout<=config.timeouts['comfy_request']
        if request.full_url.endswith('/object_info'):return Response(remote_info(template))
        if request.method=='POST':
            body=json.loads(request.data);graph=body['prompt'];prefix=graph['7']['inputs']['filename_prefix']
            source=run/'comfy/output'/(prefix+'_00001_.png');source.parent.mkdir(parents=True,exist_ok=True)
            write_png(source,1280,720)
            outputs[:]=[dict(filename=source.name,subfolder=str(source.parent.relative_to(run/'comfy/output')).replace('\\','/'),type='output')]
            if mode=='lost':raise ConnectionResetError('accepted but reply lost')
            if mode=='two':outputs.append(outputs[0])
            if mode=='prefix':outputs[0]['subfolder']='wrong'
            return Response(dict(prompt_id=prompt_id,number=0,node_errors={}))
        if '/history' in request.full_url:
            return Response({prompt_id:dict(status=dict(completed=True,status_str='success'),outputs={'7':{'images':outputs}})})
        return Response(dict(queue_running=[],queue_pending=[]))
    transport=ScriptedTransport(route);original=sc._DeadlineHttp.__init__
    def http_init(self,*a,**kw):original(self,*a,transport=transport,**kw)
    monkeypatch.setattr(sc._DeadlineHttp,'__init__',http_init)
    logger=sc.RunLogger(run)
    shot=dict(shot_id='shot_0001',primary_unit_id='speech_0001',entity_ids=[],image_prompt='all original image words')
    board=dict(global_visual=dict(style='cinematic',color_palette='blue',lighting='night',entities=[]),shots=[shot])
    return sc,config,run,run_store,logger,board,shot,transport,actions


def test_sdxl_actual_workflow_and_owned_shutdown(run_store,runtime_run,monkeypatch):
    sc,c,run,store,logger,board,shot,transport,actions=setup(run_store,runtime_run,monkeypatch,'success')
    evidence={};images=sc._generate_owned(c,run,store,logger,board,[shot],1280,720,evidence)
    item=images['shot_0001'];assert item['parameters']['positive'].startswith(shot['image_prompt'])
    assert item['image_identity']['sha256']==item['source_identity']['sha256']
    assert item['submission']['prompt_id']==store.snapshot()['units']['image']['shot_0001']['submission']['prompt_id']
    assert actions==['start','stop']
    assert sum(call[0]=='POST' for call in transport.calls)==1
    assert store.snapshot()['units']['shot']=={}
    sc._media_evidence(c,run,item,board,evidence)


@pytest.mark.parametrize('mode',['gpu_busy','gpu_unavailable'])
def test_generation_ignores_gpu_resource_gates(run_store,runtime_run,monkeypatch,mode):
    sc,c,run,store,logger,board,shot,transport,actions=setup(run_store,runtime_run,monkeypatch,mode)
    images=sc._generate_owned(c,run,store,logger,board,[shot],1280,720,{})
    assert images['shot_0001']['submission']['prompt_id']
    assert (run/'shots/shot_0001/start.png').is_file()
    assert sum(call[0]=='POST' for call in transport.calls)==1
    assert actions==['start','stop']


def test_fresh_run_creates_comfy_directories_before_startup(run_store,runtime_run,monkeypatch):
    sc,c,run,store,logger,board,shot,transport,actions=setup(run_store,runtime_run,monkeypatch,'missing_dirs')
    images=sc._generate_owned(c,run,store,logger,board,[shot],1280,720,{})
    assert images['shot_0001']['submission']['prompt_id']
    assert (run/'shots/shot_0001/start.png').is_file()


def test_sdxl_submits_reviewed_direction_and_archives_it(run_store,runtime_run,monkeypatch):
    from video_ai.runtime.manifest import hash_file,thaw
    sc,c,run,store,logger,board,shot,transport,actions=setup(run_store,runtime_run,monkeypatch,'success')
    board['run_id']=run.name
    req=dict(requirement_id='r1',unit_id='speech_0001',source_quote='Original source words.')
    shot['visual_requirements']=[req]
    (run/'storyboard.json').write_text(json.dumps(board),encoding='utf-8')
    basis=run/'failed-basis.json';basis.write_text(json.dumps(dict(global_verdict='failed',entries=[dict(req,verdict='failed')])),encoding='utf-8')
    positive='A concrete reviewed static scene.'
    direction=dict(positive=positive,negative='wrong source object',reason='Correct actual failed image.',requirement_ids=['r1'])
    path=run/'logs/start-images/visual-directions.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(dict(schema_version=1,run_id=run.name,storyboard_identity=thaw(hash_file(run/'storyboard.json')),
        review_basis_identity=thaw(hash_file(basis)),shots={'shot_0001':direction})),encoding='utf-8')
    evidence={};images=sc._generate_owned(c,run,store,logger,board,[shot],1280,720,evidence)
    image=images['shot_0001']
    assert image['parameters']['positive'].startswith(positive)
    assert shot['image_prompt'] in image['parameters']['positive']
    assert 'wrong source object' in image['parameters']['negative']
    assert 'logs/start-images/visual-directions.json' in evidence
    workflow=json.loads(Path(store.snapshot()['units']['image']['shot_0001']['submission']['request_path']).read_text(encoding='utf-8'))
    assert any(node.get('inputs',{}).get('text')==image['parameters']['positive'] for node in workflow.values())


@pytest.mark.parametrize('mode',['lost','two','prefix','external','mapping','swapped_prompts','extra_node'])
def test_generation_failure_never_reposts_or_stops_external(run_store,runtime_run,monkeypatch,mode):
    sc,c,run,store,logger,board,shot,transport,actions=setup(run_store,runtime_run,monkeypatch,mode)
    with pytest.raises((ValueError,RuntimeError)):
        sc._generate_owned(c,run,store,logger,board,[shot],1280,720,{})
    assert sum(call[0]=='POST' for call in transport.calls)<=1
    assert 'free' not in actions
    assert ('stop' in actions)==(mode not in ('external','mapping','swapped_prompts','extra_node'))
    assert not (run/'shots/shot_0001/start.png').exists()


@pytest.mark.parametrize('missing',['probe','decode','http'])
def test_sdxl_media_and_http_coverage_required(run_store,runtime_run,monkeypatch,missing):
    sc,c,run,store,logger,board,shot,transport,actions=setup(run_store,runtime_run,monkeypatch,'success')
    evidence={};images=sc._generate_owned(c,run,store,logger,board,[shot],1280,720,evidence)
    image=images['shot_0001'];sc._media_evidence(c,run,image,board,evidence)
    marker={'probe':'probe-','decode':'decode-','http':'logs/http/'}[missing]
    image['evidence_identities']=[n for n in image['evidence_identities'] if marker not in n]
    with pytest.raises(ValueError):sc._media_evidence(c,run,image,board,evidence)
