"""Production defaults and mixed historical/new request selection (no inference)."""
from copy import deepcopy
import importlib.util
import inspect
import pytest


def api():
    assert importlib.util.find_spec('video_ai.runtime.wan_production') is not None, 'production Wrapper routing missing'
    from video_ai.runtime import wan_production
    return wan_production


def parameters():
    return dict(positive='full original prompt\n原文 ' * 100,negative='negative',seed_high=123456789012345,
        seed_low=99,width=768,height=432,length=81,fps=16,batch=1,steps=40,cfg=3.5,
        sampler='euler',scheduler='simple',split_step=15,shift_high=5.000000000000001,
        shift_low=5.000000000000001,lora_enabled=False)


def test_public_production_default_fast():
    from video_ai.production import make_video
    assert inspect.signature(make_video).parameters.get('wan_mode') is not None, 'ordinary entry has no fast option'
    assert inspect.signature(make_video).parameters['wan_mode'].default == 'fast'


@pytest.mark.parametrize('mode',['fast','control','native'])
def test_public_entry_scopes_both_new_and_resumed_runs(runtime_run,monkeypatch,mode):
    import video_ai.production as module
    from types import SimpleNamespace
    w=api();run,config,_=runtime_run
    monkeypatch.setattr(module,'_make_legacy_video',lambda *args,**kwargs:w.current_mode())
    monkeypatch.setattr(module,'load_frozen_inputs',lambda *args,**kwargs:SimpleNamespace(config=config))
    assert module.make_video(config,text='new',wan_mode=mode)==mode
    assert module.make_video(run_dir=run,wan_mode=mode)==mode
    assert module.make_video(config,text='default')=='fast'
    assert module.make_video(run_dir=run)=='fast'
    assert w.current_mode()=='native'


@pytest.mark.parametrize('flag,expected',[([], 'fast'),(['--wan-mode','native'],'native'),(['--wan-mode','control'],'control')])
def test_cli_forwards_recipe_without_requiring_new_flags(monkeypatch,capsys,flag,expected):
    from video_ai.cli import main
    from types import SimpleNamespace
    observed=[]
    def fake(*args,**kwargs):
        observed.append(kwargs['wan_mode'])
        return SimpleNamespace(to_dict=lambda:{'status':'blocked'},exit_code=2)
    monkeypatch.setattr('video_ai.managed_production.make_managed_video',fake)
    assert main(['make-video','--video','0001','--json',*flag])==2
    assert observed==[expected]


def test_scope_default_and_reset():
    w=api()
    assert w.current_mode()=='native'  # standalone historical component APIs
    with w.mode_scope('fast'):
        assert w.select_mode(None)=='fast'
        with w.mode_scope('control'): assert w.select_mode(None)=='control'
        assert w.current_mode()=='fast'
    assert w.current_mode()=='native'
    with pytest.raises(ValueError):
        with w.mode_scope('typo'): pass


@pytest.mark.parametrize('mode,steps,cfg,lora',[('fast',4,1.,True),('control',40,3.5,False)])
def test_graph_binds_full_dynamic_request(mode,steps,cfg,lora):
    w=api();p=parameters();actual=w.effective_parameters(p,mode)
    template=w.wrapper_template(mode)
    graph=w.request_graph(template,actual,'run/scene_clips/c/start.png','run/scene_clips/c/attempt_0001')
    assert w.select_mode(graph)==mode
    prep=graph['10']['inputs']
    assert prep.get('recipe_sha256')==w.production_profile(mode).digest(), 'request does not freeze the numerical recipe'
    assert prep['positive_prompt']==p['positive'] and prep['negative_prompt']==p['negative']
    assert (prep['num_frames'],prep['seed_high'],prep['seed_low'])==(81,p['seed_high'],99)
    assert actual['steps']==steps and actual['cfg']==cfg and actual['lora_enabled'] is lora
    assert graph['30']['inputs']['seed']==p['seed_high'] and graph['40']['inputs']['seed']==99
    assert graph['108']['inputs']['filename_prefix']=='run/scene_clips/c/attempt_0001'
    assert template.mapping['output']==dict(node_id='108',collection='images')
    assert parameters()==p


def test_resume_keeps_original_graph_then_switches_unsent_clip():
    w=api();native={'1':dict(class_type='KSamplerAdvanced',inputs={})}
    fast=w.wrapper_template('fast').graph;control=w.wrapper_template('control').graph
    with w.mode_scope('fast'):
        assert w.select_mode(native)=='native'
        assert w.select_mode(control)=='control'
        assert w.select_mode(fast)=='fast'
        assert w.select_mode(None)=='fast'
    with w.mode_scope('native'): assert w.select_mode(fast)=='fast'


@pytest.mark.parametrize('change',[dict(width=1280,height=720),dict(length=97),dict(length=80),dict(fps=24)])
def test_unsupported_wrapper_budget_fails_before_submit(change):
    w=api();p=parameters();p.update(change)
    with pytest.raises(ValueError,match='Wrapper'):
        w.effective_parameters(p,'fast')


def test_native_parameters_are_preserved():
    w=api();p=parameters();p.update(width=1280,height=720,length=145)
    assert w.effective_parameters(p,'native')==p


def test_cli_exposes_default_fast(capsys):
    from video_ai.cli import main
    assert main(['make-video','--help'])==0
    assert '--wan-mode' in capsys.readouterr().out


def test_worker_is_separate_production_protocol():
    w=api()
    profile=w.production_profile('fast')
    assert profile.identity_dict()['kind']=='production'
    assert profile.identity_dict()['recipe']['expected_forward_counts']==[2,2]
    assert 'fixture_contracts' not in profile.identity_dict()


def test_worker_launch_uses_owned_run_and_isolated_runtime(runtime_run):
    from video_ai.runtime.services import ServiceSpec
    w=api();run,config,paths=runtime_run
    spec=ServiceSpec('comfyui','http://127.0.0.1:8188',('native',),run,60)
    result=w.service_spec(config,run,spec)
    assert result.name=='comfyui' and result.url==spec.url
    assert str(w.ENVIRONMENT/'python_embeded/python.exe')==result.args[0]
    assert result.args[result.args.index('--run')+1]==str(run)
    assert result.cwd==w.ENVIRONMENT/'ComfyUI'


def test_production_worker_has_no_experiment_authorization():
    assert importlib.util.find_spec('video_ai.runtime.wan_production_worker') is not None, 'production worker missing'
    from video_ai.runtime.wan_production_worker import ProductionContext
    assert not issubclass(ProductionContext,__import__('video_ai.experiments.wan_wrapper_nodes',fromlist=['WorkerContext']).WorkerContext)


def test_production_claim_is_once_only_and_binds_original_graph(runtime_run):
    from video_ai.runtime.wan_production_worker import ProductionContext
    from video_ai.runtime.production_state import RunLock,write_exclusive
    from video_ai.config import read_json
    from uuid import uuid4
    w=api();run,config,_=runtime_run
    with RunLock(run):
        context=ProductionContext(run,read_json(w.prepare_launch(config,run)))
        p=w.effective_parameters(parameters(),'fast');prefix=f'{run.name}/scene_clips/c/attempt_0001'
        graph=w.request_graph(w.wrapper_template('fast'),p,f'{run.name}/scene_clips/c/start.png',prefix)
        cid=str(uuid4());folder=run/'production/scene-clips/c'
        from video_ai.runtime.manifest import hash_file,thaw
        from video_ai.experiments.wan_fast_profiles import digest
        target=run/f'comfy/input/{run.name}/scene_clips/c/start.png';target.parent.mkdir(parents=True);target.write_bytes(b'original image')
        image=thaw(hash_file(target));input_record={'target':image}
        write_exclusive(folder/'input.json',input_record)
        write_exclusive(folder/'request.json',dict(input_sha256=digest(input_record),graph_sha256=digest(graph)))
        write_exclusive(folder/'graph.json',graph);write_exclusive(folder/'intent.json',dict(client_id=cid))
        with pytest.raises(ValueError,match='differs'):
            context.claim_prompt(dict(prompt=graph,client_id=str(uuid4())))
        claim=context.claim_prompt(dict(prompt=graph,client_id=cid))
        assert claim['graph']==graph and claim['client_id']==cid
        assert claim.get('input_image')==image, 'worker must lease the originally frozen input bytes'
        with pytest.raises(ValueError,match='GET only'):
            context.claim_prompt(dict(prompt=graph,client_id=cid))
    with pytest.raises((ValueError,OSError)):context.require_gpu()


def test_preparation_replaces_clip_conditioning_and_reuses_owner_pair(runtime_run,monkeypatch):
    from video_ai.runtime.wan_production_worker import ProductionContext
    from video_ai.runtime.production_state import RunLock,write_exclusive
    from video_ai.config import read_json
    from types import SimpleNamespace
    from uuid import uuid4
    w=api();run,config,_=runtime_run;events=[];leases=[]
    class Lease:
        def __init__(self,*args):self.closed=False;leases.append(self)
        def verify(self):assert not self.closed
        def close(self):self.closed=True
    monkeypatch.setattr('video_ai.experiments.wan_wrapper_runtime_support.InputLeases',Lease)
    def encode(context,fixture):
        events.append(('text',fixture['positive'],fixture['seed_high'],fixture['budget']['generated_frames']))
        return {'prompt_embeds':fixture['positive']},{'encoder_released':True}
    def image(context,fixture):return {'image_embeds':fixture['input_sha256']},object(),{'image_prepared':True}
    def admit(*args):events.append(('admit',));return SimpleNamespace(receipt={'epoch':'test'})
    monkeypatch.setattr('video_ai.experiments.wan_wrapper_text.encode_native_text',encode)
    monkeypatch.setattr('video_ai.experiments.wan_wrapper_vae.prepare_native_image',image)
    monkeypatch.setattr('video_ai.experiments.wan_wrapper_lora.admit_pair',admit)
    with RunLock(run):
        context=ProductionContext(run,read_json(w.prepare_launch(config,run)))
        context.preflight_resources=lambda **kwargs:context.require_gpu()
        context.token_counts=lambda kwargs:{'prompt_embeds':1200,'negative_prompt_embeds':512}
        context.factory=object()
        for index,frames in enumerate((81,53),1):
            p=parameters();p.update(positive=f'clip {index} full prompt',length=frames,seed_high=index)
            p=w.effective_parameters(p,'fast');prefix=f'{run.name}/scene_clips/c{index}/attempt_0001'
            image_path=f'{run.name}/scene_clips/c{index}/start.png'
            target=run/'comfy/input'/image_path;target.parent.mkdir(parents=True);target.write_bytes(bytes([index]))
            graph=w.request_graph(w.wrapper_template('fast'),p,image_path,prefix);cid=str(uuid4())
            folder=run/f'production/scene-clips/c{index}'
            from video_ai.runtime.manifest import hash_file,thaw
            from video_ai.experiments.wan_fast_profiles import digest
            input_record={'target':thaw(hash_file(target))}
            write_exclusive(folder/'input.json',input_record)
            write_exclusive(folder/'request.json',dict(input_sha256=digest(input_record),graph_sha256=digest(graph)))
            write_exclusive(folder/'graph.json',graph);write_exclusive(folder/'intent.json',dict(client_id=cid))
            context.claim_prompt(dict(prompt=graph,client_id=cid))
            prepared=context.prepare(**graph['10']['inputs'])
            assert prepared[1]['prompt_embeds']==p['positive']
            assert read_json(context.root/'fixture.json')['expected_tokens']['prompt_embeds']==1200
        assert [event[0] for event in events]==['text','admit','text']
        assert leases[1].closed  # previous clip's image lease
        context.close()
        assert all(lease.closed for lease in leases)


def test_runtime_location_and_inventory_rebase_follow_config(runtime_run,tmp_path):
    from dataclasses import replace
    w=api();_,config,_=runtime_run
    moved=replace(config,runtime_root=tmp_path/'moved runtime')
    assert hasattr(w,'environment_for'), 'Wrapper runtime is fixed to the old drive'
    assert w.environment_for(moved)==moved.runtime_root/'scratch/benchmarks/LVA-07-04-environment'
    from video_ai.runtime.wan_production_worker import software_rows
    rows=[dict(path='E:/VideoAI/scratch/benchmarks/LVA-07-04-environment/python_embeded/a.pyd',sha256='a'*64,bytes=1)]
    actual=software_rows(rows,w.environment_for(moved))
    assert actual[0]['path']==str(w.environment_for(moved)/'python_embeded/a.pyd')
    assert actual[0]['sha256']==rows[0]['sha256'] and actual[0]['bytes']==1


def test_missing_wrapper_is_reported_before_service_or_external_requests(runtime_run,tmp_path):
    from dataclasses import replace
    from video_ai.runtime.production_inputs import production_preflight
    w=api();run,config,_=runtime_run
    moved=replace(config,runtime_root=tmp_path/'missing-runtime')
    def forbidden(*args,**kwargs):raise AssertionError('dependency refusal must precede service/external work')
    with w.mode_scope('fast'):
        report=production_preflight(moved,run,runner=forbidden,port_probe=forbidden)
    assert not report.passed and report.checks[0].name=='production.wan_wrapper'
    assert '--wan-mode native' in report.checks[0].details


def test_legacy_production_claim_leases_original_image_not_mutated_bytes(runtime_run,monkeypatch):
    from video_ai.runtime.wan_production_worker import ProductionContext
    from video_ai.runtime.production_state import RunLock,write_exclusive
    from video_ai.runtime.manifest import hash_file,thaw
    from video_ai.config import read_json
    from types import SimpleNamespace
    from uuid import uuid4
    w=api();run,config,_=runtime_run
    with RunLock(run):
        context=ProductionContext(run,read_json(w.prepare_launch(config,run)))
        p=w.effective_parameters(parameters(),'fast');prefix=f'{run.name}/source_clips/shot_0001/attempt_0001'
        image_path=f'{run.name}/source_clips/shot_0001/start.png'
        target=run/'comfy/input'/image_path;target.parent.mkdir(parents=True);target.write_bytes(b'original')
        image=thaw(hash_file(target));graph=w.request_graph(w.wrapper_template('fast'),p,image_path,prefix)
        path=run/'workflow.json';write_exclusive(path,graph);cid=str(uuid4())
        write_exclusive(run/'manifest.json',dict(units=dict(shot_attempt={'shot_0001:attempt_0001':dict(submission=dict(client_id=cid,request_path=str(path)))})))
        write_exclusive(run/'logs/production/source-clips/shot_0001.input-copy.json',dict(target=image))
        claim=context.claim_prompt(dict(prompt=graph,client_id=cid));assert claim['input_image']==image
        context.leases=SimpleNamespace(verify=lambda:None,close=lambda:None)
        context.preflight_resources=lambda **kwargs:context.require_gpu()
        target.write_bytes(b'changed!')
        try:
            with pytest.raises(ValueError,match='content differs'):context.prepare(**graph['10']['inputs'])
        finally:context.close()


def test_legacy_stage_switches_templates_without_ambiguous_adapter_signature(runtime_run):
    from video_ai.runtime.production_visuals import _Stage
    from video_ai.adapters.comfyui import ComfyClient
    from video_ai.runtime.workflows import WorkflowTemplate
    from video_ai.runtime.production_state import write_exclusive
    from types import SimpleNamespace
    w=api();run,_,_=runtime_run
    task=_Stage.__new__(_Stage)
    task.state=SimpleNamespace(run_dir=run);task.handle=None;task.wan_backend='wrapper';task.validated=True
    task.native_template=WorkflowTemplate({},{});task.template=w.wrapper_template('control')
    task.client=ComfyClient(None,None,None)
    # Prior modes have the same node-class signature. Only the active remotely
    # validated template may participate in submit_once's mapping resolution.
    task.client._templates=[w.wrapper_template('fast'),w.wrapper_template('control')]
    task.manifest=SimpleNamespace(snapshot=lambda:{'units':{}})
    p=parameters();prefix=f'{run.name}/source_clips/shot_0001/attempt_0001'
    with w.mode_scope('fast'):
        _,graph=task.wan_request('shot_0001',p,f'{run.name}/source_clips/shot_0001/start.png',prefix)
    task.client._templates.append(task.template)  # simulate fresh successful object_info validation
    assert task.client._mapping(graph)['output']['node_id']=='108'
