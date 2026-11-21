import sys
import types
from contextlib import nullcontext

import numpy as np
import pytest


def test_original_long_conditioning_and_separate_padding_lengths():
    from video_ai.experiments.wan_wrapper_text import validate_conditioning, set_context_length
    positive=np.ones((1,664,4096),dtype=np.float32)
    assert validate_conditioning([[positive,{}]])[0][0] is positive
    with pytest.raises(ValueError):validate_conditioning([[np.ones((1,665,4096)),{}]])
    model=types.SimpleNamespace(text_len=512)
    assert set_context_length(model,(),{'context':positive})==664
    assert model.text_len==664 and positive.shape[1]==664
    negative=np.ones((1,512,4096),dtype=np.float32)
    assert set_context_length(model,('x','t',negative),{})==512
    assert model.text_len==512
    with pytest.raises(ValueError):set_context_length(model,(),{'context':np.ones((2,664,4096))})


@pytest.mark.parametrize('fail',[False,True])
def test_native_encoder_released_on_success_and_encoding_failure(monkeypatch,fail):
    import weakref
    from video_ai.experiments.wan_wrapper_text import encode_native_text
    events=[];refs=[]
    management=types.SimpleNamespace(unload_all_models=lambda:events.append('unload'),
        cleanup_models=lambda:None,soft_empty_cache=lambda:None)
    monkeypatch.setitem(sys.modules,'comfy',types.SimpleNamespace(model_management=management))
    monkeypatch.setitem(sys.modules,'comfy.model_management',management)
    class Clip:pass
    def invoke(name,**kwargs):
        if name=='CLIPLoader':
            obj=Clip();refs.append(weakref.ref(obj));return (obj,)
        if name=='CLIPTextEncode':
            if fail:raise RuntimeError('encode failed')
            return ([[np.ones((1,5,4096),dtype=np.float32),{}]],)
        return ({'prompt_embeds':kwargs['positive'][0][0],
                 'negative_prompt_embeds':kwargs['negative'][0][0]},)
    ctx=types.SimpleNamespace(mode='cpu',invoke=invoke,models={'t5':{'path':'t5.safetensors'}},stage=lambda _:nullcontext())
    if fail:
        with pytest.raises(RuntimeError,match='encode failed'):
            encode_native_text(ctx,{'positive':'p','negative':'n'})
    else:
        text,proof=encode_native_text(ctx,{'positive':'p','negative':'n'})
        assert proof['encoder_released'] is True and text['prompt_embeds'].shape==(1,5,4096)
    assert refs[0]() is None and events==['unload']


def test_missing_or_wrong_epoch_text_blocks_vae_and_admission(tmp_path,monkeypatch):
    from video_ai.experiments import wan_wrapper_nodes as n
    ctx=n.WorkerContext(tmp_path,mode='gpu',epoch='current')
    monkeypatch.setattr(ctx,'require_gpu',lambda:None)
    with pytest.raises(ValueError,match='text'):ctx.admit('9b107b38-cbb5-46e9-bfe8-9e6beed8cf89')
    ctx.text_cache={'prompt_embeds':np.ones((1,664,4096))}
    ctx.text_receipt={'epoch':'previous'}
    with pytest.raises(ValueError,match='text'):ctx.require_text('positive','negative')


def test_text_response_loss_uses_original_get_only(tmp_path):
    from video_ai.experiments import wan_wrapper_backend as b
    from tests.unit.test_wan_wrapper_backend import profiles,fixture
    ps=profiles();b.freeze_comparison(tmp_path,ps,fixture());calls=[]
    def http(method,route,payload=None):
        calls.append((method,route))
        if method=='POST':raise TimeoutError()
        return {'status':'unknown'}
    client=b.WrapperExperimentClient(tmp_path,profile_digest=ps['control'].digest(),port=8297,http=http)
    with pytest.raises(TimeoutError):client.prepare_text()
    assert client.prepare_text()=={'status':'unknown'}
    assert [x[0] for x in calls]==['POST','GET'] and calls[1][1].startswith('/lva07/text/')


def test_text_receipt_binds_its_inner_original_id(tmp_path):
    from video_ai.experiments import wan_wrapper_backend as b
    from tests.unit.test_wan_wrapper_backend import profiles,fixture
    ps=profiles();f=fixture();marker=b.freeze_comparison(tmp_path,ps,f)
    def http(method,route,payload=None):
        return dict(probe_id=payload['probe_id'],receipt=dict(probe_id='wrong-id',epoch='offline-fixture',
            comparison_sha256=marker['comparison_sha256'],control_profile_sha256=ps['control'].digest(),
            fixture_sha256=b.digest(f),prompt_sha256=b.digest({k:f[k] for k in ('positive','negative')}),encoder_released=True))
    client=b.WrapperExperimentClient(tmp_path,profile_digest=ps['control'].digest(),port=8297,http=http)
    with pytest.raises(ValueError,match='binding'):client.prepare_text()
    assert not (tmp_path/'text/client-accepted.json').exists()


def test_controller_uses_sealed_private_cap():
    from tests.unit.test_wan_wrapper_host_budget import controller_module
    c=controller_module()
    assert c.worker_private_limit('gpu')==18*1024**3
    assert c.worker_private_limit('cpu')==4*1024**3


def test_post_text_phase_allows_own_cuda_overhead_but_keeps_workspace_floor(tmp_path,monkeypatch):
    from video_ai.experiments.wan_wrapper_nodes import WorkerContext
    free=[20.8*1024**3];available=[5*1024**3];calls=[]
    monkeypatch.setitem(sys.modules,'psutil',types.SimpleNamespace(virtual_memory=lambda:types.SimpleNamespace(available=available[0])))
    cuda=types.SimpleNamespace(is_available=lambda:True,mem_get_info=lambda:(free[0],24*1024**3),
        get_device_properties=lambda _:types.SimpleNamespace(total_memory=24*1024**3),
        set_per_process_memory_fraction=lambda value:calls.append(value))
    monkeypatch.setitem(sys.modules,'torch',types.SimpleNamespace(cuda=cuda,
        backends=types.SimpleNamespace(cuda=types.SimpleNamespace(enable_math_sdp=lambda _:None))))
    ctx=WorkerContext(tmp_path,mode='gpu',epoch='fixture')
    monkeypatch.setattr(ctx,'require_gpu',lambda:None);monkeypatch.setattr(ctx,'require_text',lambda:None)
    with pytest.raises(ValueError,match='RAM'):ctx.preflight_resources()
    ctx.preflight_resources(phase=True)
    assert calls==[20/24]
    free[0]=19.9*1024**3
    with pytest.raises(ValueError,match='VRAM'):ctx.preflight_resources(phase=True)
    free[0]=20.8*1024**3;available[0]=3.9*1024**3
    with pytest.raises(ValueError,match='RAM'):ctx.preflight_resources(phase=True)


@pytest.mark.parametrize('fail_image',[False,True])
def test_text_preparation_precedes_pair_and_reuses_one_live_lease_window(tmp_path,monkeypatch,fail_image):
    from uuid import uuid4
    from tests.unit.test_wan_wrapper_backend import profiles,fixture
    from video_ai.experiments import wan_wrapper_backend as b,wan_wrapper_nodes as n
    from video_ai.experiments import wan_wrapper_text as text,wan_wrapper_runtime_support as support,wan_wrapper_lora as lora
    ps=profiles();f=fixture();f['source_image']={'bytes':3};b.freeze_comparison(tmp_path,ps,f)
    ctx=n.WorkerContext(tmp_path,mode='gpu',epoch='epoch')
    monkeypatch.setattr(ctx,'require_gpu',lambda:None);monkeypatch.setattr(ctx,'preflight_resources',lambda **kw:None)
    events=[]
    class Lease:
        def __init__(self,models):events.append('lease')
        def verify(self):events.append('verify')
        def close(self):events.append('close')
    monkeypatch.setattr(support,'InputLeases',Lease)
    def needs_prompt(*args,**kwargs):raise AttributeError('last_prompt_id')
    utils=types.SimpleNamespace(PROGRESS_BAR_HOOK=needs_prompt)
    utils.set_progress_bar_global_hook=lambda hook:setattr(utils,'PROGRESS_BAR_HOOK',hook)
    monkeypatch.setitem(sys.modules,'comfy',types.SimpleNamespace(utils=utils))
    monkeypatch.setitem(sys.modules,'comfy.utils',utils)
    def encode(*args):
        utils.PROGRESS_BAR_HOOK(1,10,None)
        return {'prompt_embeds':np.ones((1,5,4096))},{'encoder_released':True}
    monkeypatch.setattr(text,'encode_native_text',encode)
    from video_ai.experiments import wan_wrapper_vae as vae
    def prepare_image(*args):
        events.append('image')
        if fail_image:raise RuntimeError('image preparation failure')
        return {'image_embeds':np.ones((1,))},'prepared-vae',{'image_prepared':True,'vae_cpu':True}
    monkeypatch.setattr(vae,'prepare_native_image',prepare_image)
    monkeypatch.setattr(text,'save_prepared_text',lambda context,fixture,t,p,uid:dict(probe_id=uid,
        epoch=context.epoch,comparison_sha256=context.comparison_sha256,
        prompt_sha256=b.digest({k:fixture[k] for k in ('positive','negative')}),**p))
    probe_id=str(uuid4());b.write_once(tmp_path/'text/client-intent.json',dict(probe_id=probe_id,profile_sha256=ps['control'].digest(),epoch='epoch'))
    original_write=n.write_once
    def publish(path,value):
        if path==tmp_path/'text/accepted.json':
            assert ctx.require_text(f['positive'],f['negative'])
            assert ctx.require_image()[1]=='prepared-vae'
        return original_write(path,value)
    monkeypatch.setattr(n,'write_once',publish)
    if fail_image:
        with pytest.raises(RuntimeError,match='image preparation failure'):ctx.prepare_text(probe_id)
        assert ctx.text_cache is ctx.image_cache is ctx.vae_cache is None
        assert not (tmp_path/'text/accepted.json').exists() and events==['lease','image','close']
        return
    assert ctx.prepare_text(probe_id)['receipt']['encoder_released']
    assert ctx.require_image()[1]=='prepared-vae'
    assert ctx.require_text(f['positive'],f['negative'])['prompt_embeds'].shape==(1,5,4096)
    with pytest.raises(ValueError,match='prompt'):ctx.require_text('changed',f['negative'])
    with pytest.raises(ValueError,match='GET'):ctx.prepare_text(probe_id)
    monkeypatch.setattr(lora,'admit_pair',lambda *a:types.SimpleNamespace(receipt={'full_model_verified':True}))
    ctx.factory=types.SimpleNamespace();uid=str(uuid4());b.write_once(tmp_path/'admission/client-intent.json',dict(admission_id=uid,profile_sha256=ps['fast'].digest(),epoch='epoch'))
    assert ctx.admit(uid)['receipt']['full_model_verified']
    assert events==['lease','image','verify']
