from contextlib import nullcontext
import sys
import types

import numpy as np
import pytest


def setup_pool(monkeypatch):
    pool={'reserved':0,'trims':0}
    def trim():pool.update(reserved=0,trims=pool['trims']+1)
    mm=types.SimpleNamespace(soft_empty_cache=trim)
    monkeypatch.setitem(sys.modules,'comfy',types.SimpleNamespace(model_management=mm))
    monkeypatch.setitem(sys.modules,'comfy.model_management',mm)
    class Model:
        def to(self,device):
            if device=='cpu' and pool['reserved']:raise MemoryError('pool overlaps CPU allocation')
            return self
        def parameters(self):return [types.SimpleNamespace(device=types.SimpleNamespace(type='cpu'),dtype='torch.float32')]
    class Vae(Model):
        dtype='torch.float32'
        def __init__(self):self.model=Model()
        def encode(self,value):pool['reserved']=8;return value
        def decode(self,value):pool['reserved']=8;return value
    return Vae(),pool


def test_return_and_cpu_offload_release_only_unused_pool_and_restore(monkeypatch):
    from video_ai.experiments.wan_wrapper_vae import vae_memory_scope
    vae,pool=setup_pool(monkeypatch);before=dict(vars(vae));model_before=dict(vars(vae.model));value=object()
    with vae_memory_scope(vae):
        assert vae.to('cuda') is vae and pool['trims']==0
        assert vae.encode(value) is value and pool['reserved']==0
        pool['reserved']=8
        assert vae.model.to('cpu') is vae.model and pool['reserved']==0
        assert vae.decode(value) is value and pool['reserved']==0
        pool['reserved']=8
        assert vae.to('cpu') is vae and pool['reserved']==0
    assert vars(vae)==before and vars(vae.model)==model_before


def test_exception_restores_existing_instance_methods(monkeypatch):
    from video_ai.experiments.wan_wrapper_vae import vae_memory_scope
    vae,pool=setup_pool(monkeypatch)
    def broken(_):raise RuntimeError('original encoding failure')
    vae.encode=broken;original_to=lambda device:vae.model;vae.model.to=original_to
    before=dict(vars(vae));model_before=dict(vars(vae.model))
    with pytest.raises(RuntimeError,match='original encoding failure'):
        with vae_memory_scope(vae):vae.encode('input')
    assert vars(vae)==before and vars(vae.model)==model_before and pool['trims']==0


def test_native_image_preparation_keeps_original_precision_and_budget(monkeypatch):
    from video_ai.experiments.wan_wrapper_vae import prepare_native_image
    vae,pool=setup_pool(monkeypatch);calls=[]
    image={'image_embeds':np.ones((16,24,54,96),dtype=np.float32),'mask':np.ones((4,24,54,96),dtype=np.float32),'num_frames':93}
    def invoke(name,**kw):
        calls.append(name)
        if name=='LoadImage':assert kw=={'image':'original.png'};return ('original-image',)
        if name=='WanVideoVAELoader':assert kw['precision']=='fp32';return (vae,)
        assert name=='WanVideoImageToVideoEncode' and kw['start_image']=='original-image'
        assert (kw['width'],kw['height'],kw['num_frames'])==(768,432,93)
        assert kw['force_offload'] and not kw['tiled_vae'] and kw['noise_aug_strength']==0
        vae.encode('original');pool['reserved']=8;vae.model.to('cpu')
        return (image,)
    ctx=types.SimpleNamespace(invoke=invoke,models={'vae':{'path':'original-vae.safetensors'}},stage=lambda _:nullcontext())
    cache,actual_vae,proof=prepare_native_image(ctx,{'input_relative':'original.png','input_sha256':'a'*64})
    assert actual_vae is vae and cache is image and proof['image_prepared'] and proof['vae_cpu']
    assert proof['image_input_sha256']=='a'*64 and proof['image_embeds_shape']==[16,24,54,96]
    assert calls==['LoadImage','WanVideoVAELoader','WanVideoImageToVideoEncode']


def test_image_cache_is_current_epoch_and_trial_copy_isolated(tmp_path):
    from video_ai.experiments.wan_wrapper_nodes import WorkerContext
    ctx=WorkerContext(tmp_path,mode='gpu',epoch='current');ctx.comparison_sha256='comparison'
    with pytest.raises(ValueError,match='prepared'):ctx.require_image()

    ctx.text_cache={};ctx.text_receipt={'epoch':'current','comparison_sha256':'comparison','image_prepared':True}
    ctx.image_cache={'image_embeds':np.ones((1,),dtype=np.float32),'mask':np.ones((1,),dtype=np.float32)};ctx.vae_cache=object()
    image,vae=ctx.require_image();image['image_embeds'][0]=42
    assert ctx.image_cache['image_embeds'][0]==1 and vae is ctx.vae_cache
    ctx.text_receipt['epoch']='old'
    with pytest.raises(ValueError,match='prepared'):ctx.require_image()


@pytest.mark.parametrize('fail',[False,True])
def test_registered_native_decode_releases_pool_before_pixels_and_restores(tmp_path,monkeypatch,fail):
    from video_ai.experiments.wan_wrapper_nodes import WorkerContext,register_nodes
    vae,pool=setup_pool(monkeypatch);before=dict(vars(vae));events=[]
    class Pixels:
        def cpu(self):
            if pool['reserved']:raise MemoryError('unused pool overlaps output copy')
            events.append('native pixels');return self
    pixels=Pixels()
    class Native:
        FUNCTION='decode'
        @classmethod
        def INPUT_TYPES(cls):return {'required':{'vae':('WANVAE',)}}
        def decode(self,vae,samples):
            value=vae.decode(samples)
            if fail:raise RuntimeError('native decode failed')
            value.cpu();vae.to('cpu');return (value,)
    ctx=WorkerContext(tmp_path,mode='gpu',epoch='current')
    monkeypatch.setattr(ctx,'require_gpu',lambda:None)
    registry={'WanVideoDecode':Native};register_nodes(registry,ctx)
    assert registry['WanVideoDecode'].INPUT_TYPES()==Native.INPUT_TYPES()
    if fail:
        with pytest.raises(RuntimeError,match='native decode failed'):registry['WanVideoDecode']().decode(vae=vae,samples=pixels)
    else:assert registry['WanVideoDecode']().decode(vae=vae,samples=pixels)==(pixels,) and events==['native pixels']
    assert vars(vae)==before


def test_changed_image_rejected_before_any_native_preparation(tmp_path,monkeypatch):
    import hashlib
    from uuid import uuid4
    from tests.unit.test_wan_wrapper_backend import profiles,fixture
    from video_ai.experiments import wan_wrapper_nodes as n,wan_wrapper_backend as b,wan_wrapper_text as text,wan_wrapper_runtime_support as support
    ps=profiles();f=fixture();f['source_image']={'bytes':3};b.freeze_comparison(tmp_path,ps,f)
    path=tmp_path/'input'/f['input_relative'];path.parent.mkdir(exist_ok=True);path.write_bytes(b'bad')
    class Lease:
        def __init__(self,assets):
            for item in assets:
                if Path(item['path'])==path and hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
                    raise ValueError('leased artifact content differs')
        def close(self):pass
    from pathlib import Path
    monkeypatch.setattr(support,'InputLeases',Lease)
    monkeypatch.setattr(support,'admission_progress_scope',nullcontext)
    monkeypatch.setattr(text,'encode_native_text',lambda *a:pytest.fail('changed image reached native encoder'))
    ctx=n.WorkerContext(tmp_path,mode='gpu',epoch='current')
    monkeypatch.setattr(ctx,'require_gpu',lambda:None);monkeypatch.setattr(ctx,'preflight_resources',lambda **kw:None)
    uid=str(uuid4());b.write_once(tmp_path/'text/client-intent.json',dict(probe_id=uid,profile_sha256=ps['control'].digest(),epoch='current'))
    with pytest.raises(ValueError,match='leased artifact content differs'):ctx.prepare_text(uid)
    assert ctx.text_cache is ctx.image_cache is ctx.vae_cache is None
