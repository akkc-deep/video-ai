"""Prepare native text once before Wan admission; preserve the original context."""
from contextlib import nullcontext
import gc
import weakref

MAX_TEXT_TOKENS = 664
EXPECTED_TOKENS = {'prompt_embeds': 664, 'negative_prompt_embeds': 512}


def validate_conditioning(value,*,max_tokens=MAX_TEXT_TOKENS):
    import numpy as np
    if not isinstance(value,(list,tuple)) or len(value)!=1 or len(value[0])!=2:
        raise ValueError('single unscheduled conditioning required')
    tensor,metadata=value[0]
    if not isinstance(metadata,dict) or any(k!='pooled_output' or v is not None for k,v in metadata.items()):
        raise ValueError('unsupported extra/scheduled conditioning')
    shape=tuple(tensor.shape)
    if len(shape)!=3 or shape[0]!=1 or not 1<=shape[1]<=max_tokens or shape[2]!=4096:
        raise ValueError('conditioning batch/token/dim')
    finite=tensor.isfinite().all().item() if hasattr(tensor,'detach') else np.isfinite(tensor).all()
    if not finite:raise ValueError('conditioning finite')
    return value


def set_context_length(transformer,args,kwargs,*,max_tokens=MAX_TEXT_TOKENS):
    context=kwargs.get('context') if 'context' in kwargs else args[2] if len(args)>2 else None
    if context is None:return None
    if len(context)!=1:raise ValueError('single context required')
    row=context[0]
    if len(row.shape)!=2 or row.shape[1]!=4096 or not 1<=row.shape[0]<=max_tokens:
        raise ValueError('original context shape differs')
    transformer.text_len=max(512,int(row.shape[0]))
    return transformer.text_len


def encode_native_text(context,fixture):
    import comfy.model_management as mm
    from pathlib import Path
    clip=pos=neg=None;model_ref=None
    scope=nullcontext()
    if context.mode=='gpu':
        import torch
        scope=torch.inference_mode()
    try:
        with scope,context.stage('native_t5_prepare'):
            clip=context.invoke('CLIPLoader',clip_name=Path(context.models['t5']['path']).name,type='wan',device='default')[0]
            model_ref=weakref.ref(getattr(clip,'cond_stage_model',clip))
            pos=context.invoke('CLIPTextEncode',text=fixture['positive'],clip=clip)[0]
            neg=context.invoke('CLIPTextEncode',text=fixture['negative'],clip=clip)[0]
            matrix=getattr(context,'is_matrix',False)
            maximum=max(fixture['expected_tokens'].values()) if matrix else MAX_TEXT_TOKENS
            validate_conditioning(pos,max_tokens=maximum);validate_conditioning(neg,max_tokens=maximum)
            text=context.invoke('WanVideoTextEmbedBridge',positive=pos,negative=neg)[0]
            text={k:v.detach().cpu() if hasattr(v,'detach') else v for k,v in text.items()}
    finally:
        clip=pos=neg=None
        mm.unload_all_models();gc.collect();mm.cleanup_models();mm.soft_empty_cache()
    released=model_ref is not None and model_ref() is None
    if not released:raise ValueError('native text encoder still retained')
    return text,dict(encoder_released=True,shapes={k:list(v.shape) for k,v in text.items()})


def save_prepared_text(context,fixture,text,proof,probe_id):
    import torch
    from safetensors.torch import save_file
    from .wan_fast_profiles import artifact,digest
    expected=fixture['expected_tokens'] if getattr(context,'is_matrix',False) else EXPECTED_TOKENS
    if set(text)!=set(expected):raise ValueError('native text slots differ')
    for key,count in expected.items():
        if tuple(text[key].shape)!=(1,count,4096) or text[key].dtype!=torch.float32:
            raise ValueError('original native token count/dtype differs: '+key)
    path=context.root/'text/embeddings.safetensors'
    if path.exists():raise ValueError('prepared text output already exists')
    save_file({k:v.contiguous() for k,v in text.items()},str(path))
    return dict(probe_id=probe_id,epoch=context.epoch,comparison_sha256=context.comparison_sha256,
        control_profile_sha256=context.profiles['control'].digest(),fixture_sha256=digest(fixture),
        prompt_sha256=digest({k:fixture[k] for k in ('positive','negative')}),
        t5_sha256=context.models['t5']['sha256'],embedding_artifact=artifact(path).identity_dict(),
        dtypes={k:str(v.dtype) for k,v in text.items()},**proof)
