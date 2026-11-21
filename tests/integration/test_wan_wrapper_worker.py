import importlib.util
from pathlib import Path
import types
import subprocess
import sys

import pytest

from video_ai.experiments import wan_wrapper_nodes as n


def test_cpu_node_registration_and_execution_refusal(tmp_path):
    registry={};context=n.WorkerContext(tmp_path,mode='cpu',epoch='fixture')
    n.register_nodes(registry,context)
    assert set(registry)=={'LVA07Prepare','LVA07Sampler','LVA07SaveVideo'}
    for name,cls in registry.items():
        assert cls.INPUT_TYPES()['required']
        with pytest.raises(ValueError,match='CPU'):
            getattr(cls(),cls.FUNCTION)()
    with pytest.raises(ValueError,match='CPU'):context.admit('unused')


def test_duplicate_registration_rejected(tmp_path):
    registry={};ctx=n.WorkerContext(tmp_path,mode='cpu',epoch='fixture')
    n.register_nodes(registry,ctx)
    with pytest.raises(ValueError):n.register_nodes(registry,ctx)


def test_conditioning_rejects_schedules_and_extra_entries():
    import numpy as np
    valid=[[np.ones((1,5,4096),dtype=np.float32),{}]]
    assert n.validate_conditioning(valid) is valid
    for invalid in [valid+valid,[[valid[0][0],{'start_percent':.1}]],[[np.ones((2,5,4096)),{}]],[[np.full((1,5,4096),float('nan')),{}]]]:
        with pytest.raises(ValueError):n.validate_conditioning(invalid)


def test_cpu_request_gate_blocks_graph_and_admission(tmp_path):
    ctx=n.WorkerContext(tmp_path,mode='cpu',epoch='fixture')
    for route in ('/prompt','/api/prompt','/lva07/admit-pair','/api/lva07/admit-pair'):
        with pytest.raises(ValueError,match='CPU'):ctx.allow_request('POST',route)
    ctx.allow_request('GET','/object_info/LVA07Prepare')


def test_owned_job_deadline_stops_only_original_handle(tmp_path):
    path=Path(__file__).resolve().parents[2]/'scripts/observe_wan_wrapper_comfy.py'
    spec=importlib.util.spec_from_file_location('owned_wrapper',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    process=subprocess.Popen([sys._base_executable,'-c','import time;time.sleep(20)'],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    job=None
    try:
        job=module.BoundedJob(process,256*1024**2)
        result=module.stop_owned(process,tmp_path,'fixture')
        assert result['exited'] and result['forced'] and not result['graceful']
        with pytest.raises(ValueError):module.owned_listener(8297,process.pid)
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=5)
        if job:job.close()


def test_worker_claim_binds_original_client_and_allows_one_request_per_mode(tmp_path,monkeypatch):
    from uuid import uuid4
    from tests.unit.test_wan_wrapper_backend import profiles,fixture
    from video_ai.experiments.wan_wrapper_backend import freeze_comparison,build_graph,digest,write_once
    ps=profiles();f=fixture();freeze_comparison(tmp_path,ps,f)
    ctx=n.WorkerContext(tmp_path,mode='gpu',epoch='fixture')
    monkeypatch.setattr(ctx,'require_gpu',lambda:None)
    ctx.pair=types.SimpleNamespace(receipt={'epoch':'fixture','full_model_verified':True})
    graph=build_graph(ps['control'],f);client_id=str(uuid4())
    write_once(tmp_path/'trials/control_1/intent.json',dict(client_id=client_id,graph=graph,graph_sha256=digest(graph)))
    with pytest.raises(ValueError,match='envelope'):ctx.claim_prompt(dict(prompt=graph,client_id=client_id,prompt_id=str(uuid4())))
    with pytest.raises(ValueError,match='client'):ctx.claim_prompt(dict(prompt=graph,client_id=str(uuid4())))
    assert ctx.claim_prompt(dict(prompt=graph,client_id=client_id))['mode']=='control'
    with pytest.raises(ValueError,match='already'):ctx.claim_prompt(dict(prompt=graph,client_id=client_id))


def test_controller_never_passes_crash_error_or_forced_stop():
    path=Path(__file__).resolve().parents[2]/'scripts/observe_wan_wrapper_comfy.py'
    spec=importlib.util.spec_from_file_location('owned_wrapper_finish',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    for change in [dict(exit_code=1),dict(forced=True),dict(error='RSS exceeded'),dict(timed_out=True)]:
        value=dict(passed=True,exited=True,port_closed=True,exit_code=0,forced=False,graceful=True)
        value.update(change)
        assert module.controller_passed(value) is False


def test_actual_software_bytes_and_native_leases_reject_drift_before_execution(tmp_path):
    import hashlib
    from video_ai.experiments.wan_wrapper_runtime_support import SoftwareVerifier
    source=tmp_path/'comfy_parser.py';source.write_bytes(b'VALUE=1\n')
    row=dict(path=str(source.resolve()),bytes=8,sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    verifier=SoftwareVerifier([row],[tmp_path]);verifier.verify(source)
    with pytest.raises(OSError):source.write_bytes(b'VALUE=2\n')
    verifier.close();source.write_bytes(b'VALUE=2\n')
    verifier=SoftwareVerifier([row],[tmp_path])
    with pytest.raises(ValueError,match='content'):verifier.verify(source)
    verifier.close()


def test_prepare_releases_native_encoder_before_vae_lifetime(tmp_path,monkeypatch):
    import numpy as np
    import weakref
    events=[];refs=[]
    management=types.SimpleNamespace(unload_all_models=lambda:events.append('unload'),cleanup_models=lambda:None,soft_empty_cache=lambda:None)
    monkeypatch.setitem(sys.modules,'comfy',types.SimpleNamespace(model_management=management))
    monkeypatch.setitem(sys.modules,'comfy.model_management',management)
    class Clip:pass
    class Loader:
        FUNCTION='load'
        def load(self,**kw):
            obj=Clip();refs.append(weakref.ref(obj));events.append('t5');return (obj,)
    class Encode:
        FUNCTION='encode'
        def encode(self,**kw):events.append('text');return ([[np.ones((1,5,4096),dtype=np.float32),{}]],)
    class Bridge:
        FUNCTION='bridge'
        def bridge(self,positive,negative):events.append('bridge');return ({'prompt_embeds':positive[0][0],'negative_prompt_embeds':negative[0][0]},)
    class Vae:
        FUNCTION='load'
        def load(self,**kw):assert refs[0]() is None;events.append('vae');return ('fixture-vae',)
    class Image:
        FUNCTION='encode'
        def encode(self,**kw):assert kw['num_frames']==93 and kw['noise_aug_strength']==0;return ('image-latent',)
    ctx=n.WorkerContext(tmp_path,mode='cpu',epoch='fixture');ctx.models={'t5':{'path':'t5.safetensors'},'vae':{'path':'vae.safetensors'}}
    registry=dict(CLIPLoader=Loader,CLIPTextEncode=Encode,WanVideoTextEmbedBridge=Bridge,WanVideoVAELoader=Vae,WanVideoImageToVideoEncode=Image)
    n.register_nodes(registry,ctx)
    from video_ai.experiments.wan_wrapper_text import encode_native_text
    ctx.text_cache,proof=encode_native_text(ctx,{'positive':'positive','negative':'negative'})
    ctx.comparison_sha256='a'*64
    ctx.text_receipt=dict(epoch='fixture',comparison_sha256='a'*64,
        prompt_sha256=n.digest(dict(positive='positive',negative='negative')))
    assert proof['encoder_released']
    ctx.image_cache={'prepared':'image-latent'};ctx.vae_cache='fixture-vae';ctx.text_receipt['image_prepared']=True
    result=registry['LVA07Prepare']()._execute('image','positive','negative','t5.safetensors','vae.safetensors',768,432,93)
    assert result[0]=={'prepared':'image-latent'} and result[2]=='fixture-vae'
    assert events==['t5','text','text','bridge','unload']


def test_sampler_records_real_delegate_calls_keeps_first_latent_and_releases(tmp_path,monkeypatch):
    from tests.unit.test_wan_wrapper_backend import profiles
    from video_ai.experiments.wan_wrapper_lora import ExpertOwner,OwnerGuard
    from video_ai.experiments.wan_wrapper_backend import contract
    class Tensor:
        def __init__(self,value):self.value=value
        def detach(self):return self
        def cpu(self):return self
        def tolist(self):return self.value
    monkeypatch.setitem(sys.modules,'torch',types.SimpleNamespace(tensor=lambda value,**kw:Tensor(value),float32='float32'))
    management=types.SimpleNamespace(soft_empty_cache=lambda:None)
    monkeypatch.setitem(sys.modules,'comfy',types.SimpleNamespace(model_management=management))
    monkeypatch.setitem(sys.modules,'comfy.model_management',management)
    segment=contract()['recipes']['control']['high']
    delegate=types.SimpleNamespace(get_scheduler=lambda *a,**kw:(types.SimpleNamespace(sigmas=Tensor(segment['sigmas'])),Tensor(segment['timesteps']),0,14))
    monkeypatch.setitem(sys.modules,'lva07_fixture_sampler',delegate)
    first,second=object(),object();observed=[]
    class Transformer:
        blocks=[]
        def modules(self):return []
        def forward(self,*a,**kw):pass
    class Model(dict):pass
    class Factory:
        guard=OwnerGuard()
        def build_unpatched(self,role):
            transform=Transformer();sd={};model=Model(sd=sd);model.diffusion_model=transform
            patcher=types.SimpleNamespace(model=model,patches={},model_options={'transformer_options':{}})
            return ExpertOwner(patcher,transform,sd,types.SimpleNamespace(close=lambda o:observed.append('released')),role)
    class Delegate:
        FUNCTION='process';__module__='lva07_fixture_sampler';calls=30
        def process(self,model,**kw):
            assert kw['steps']==40 and kw['cfg']==3.5 and kw['sigmas'].value==contract()['recipes']['control']['sigmas_float32']
            delegate.get_scheduler()
            for _ in range(self.calls):model.model.diffusion_model.forward()
            return first,second
    ctx=n.WorkerContext(tmp_path,mode='cpu',epoch='fixture');ctx.profiles=profiles();ctx.models=ctx.profiles['control'].identity_dict()['common']['models'];ctx.factory=Factory()
    monkeypatch.setattr(ctx,'require_gpu',lambda:None)
    registry={'WanVideoSampler':Delegate};n.register_nodes(registry,ctx)
    kwargs=dict(role='high',mode='control',model_name='base_high.safetensors',image_embeds={},text_embeds={},seed=264244520398999)
    assert registry['LVA07Sampler']().execute(**kwargs)==(first,)
    assert observed==['released'];ctx.factory.guard.check()
    Delegate.calls=29
    with pytest.raises(ValueError,match='forward'):registry['LVA07Sampler']().execute(**kwargs)
    assert observed==['released','released'];ctx.factory.guard.check()
