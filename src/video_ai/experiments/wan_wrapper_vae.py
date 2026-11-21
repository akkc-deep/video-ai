"""Reclaim unused CUDA storage at original VAE operation boundaries."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path


@contextmanager
def vae_memory_scope(vae):
    import comfy.model_management as mm
    saved=[]
    def replace(obj,name,returns=False):
        original=getattr(obj,name)
        saved.append((obj,name,name in vars(obj),vars(obj).get(name)))
        def call(*args,**kwargs):
            if not returns:
                device=kwargs.get('device',args[0] if args else None)
                kind=device.split(':',1)[0] if isinstance(device,str) else getattr(device,'type',None)
                if kind=='cpu':mm.soft_empty_cache()
            result=original(*args,**kwargs)
            if returns:mm.soft_empty_cache()
            return result
        setattr(obj,name,call)
    try:
        replace(vae,'encode',returns=True);replace(vae,'decode',returns=True)
        replace(vae,'to');replace(vae.model,'to')
        yield
    finally:
        for obj,name,owned,value in reversed(saved):
            if owned:setattr(obj,name,value)
            else:delattr(obj,name)


def copy_image_conditioning(image):
    return deepcopy(image)


def prepare_native_image(context,fixture):
    vae=None
    profiles=getattr(context,'profiles',{})
    matrix=bool(profiles and profiles['control'].identity_dict()['schema_version']==2)
    frames=fixture['budget']['generated_frames'] if matrix else 93
    shape=(16,(frames-1)//4+1,54,96)
    try:
        with context.stage('vae_i2v_prepare'):
            start=context.invoke('LoadImage',image=fixture['input_relative'])[0]
            vae=context.invoke('WanVideoVAELoader',model_name=Path(context.models['vae']['path']).name,precision='fp32')[0]
            with vae_memory_scope(vae):
                image=context.invoke('WanVideoImageToVideoEncode',width=768,height=432,num_frames=frames,force_offload=True,
                    noise_aug_strength=0.,start_latent_strength=1.,end_latent_strength=1.,start_image=start,
                    fun_or_fl2v_model=False,tiled_vae=False,vae=vae)[0]
            tensor=image['image_embeds']
            if tuple(tensor.shape)!=shape:raise ValueError('original image conditioning shape differs')
            finite=tensor.isfinite().all().item() if hasattr(tensor,'isfinite') else __import__('numpy').isfinite(tensor).all()
            if not finite:raise ValueError('original image conditioning nonfinite')
            if str(vae.dtype)!='torch.float32' or any(p.device.type!='cpu' or str(p.dtype)!='torch.float32' for p in vae.model.parameters()):
                raise ValueError('original fp32 VAE CPU handoff differs')
        return image,vae,dict(image_prepared=True,vae_cpu=True,vae_precision='fp32',image_embeds_finite=True,
            image_input_sha256=fixture['input_sha256'],image_embeds_shape=list(tensor.shape))
    except BaseException:
        vae=None
        import gc
        import comfy.model_management as mm
        gc.collect();mm.soft_empty_cache()
        raise
