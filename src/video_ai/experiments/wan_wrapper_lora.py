"""Single-owner preparation. Only static targets receive private writable storage.

The legacy CPU pair helper and its 256MiB cap are deliberately untouched.
"""
from __future__ import annotations
from dataclasses import dataclass
import gc
import importlib
import json
import os
from pathlib import Path
from types import MappingProxyType
import weakref
import hashlib

from .wan_fast_profiles import digest,write_once


@dataclass
class ExpertOwner:
    patcher: object
    transformer: object
    original_sd: dict
    components: object
    role: str
    prepared: bool=False
    closed: bool=False


@dataclass(frozen=True)
class ExpertCertificate:
    static: object
    dynamic: object
    witness: dict


@dataclass(frozen=True)
class CertifiedPair:
    high: ExpertCertificate
    low: ExpertCertificate
    receipt: dict
    leases: object


class OwnerGuard:
    def __init__(self):self.refs=[]
    def check(self):
        gc.collect()
        if any(ref() is not None for ref in self.refs):raise ValueError('previous Wan owner still live')
        self.refs=[]
    def acquire(self,owner):
        self.check();self.refs=[weakref.ref(owner),weakref.ref(owner.transformer)]
    def release(self,owner):
        owner.closed=True
        owner.patcher=None;owner.transformer=None;owner.original_sd=None


def assert_clean(owner):
    if owner.closed or owner.prepared or owner.patcher.patches:
        raise ValueError('fresh unpatched owner required')
    for m in owner.transformer.modules():
        if getattr(m,'lora_diffs',[]) or hasattr(m,'lora_diff_0_0') or getattr(m,'_lva07_prepared',False):
            raise ValueError('control/prepared owner contains LoRA')
        if getattr(m,'fp8_matmul_enabled',False) or getattr(m,'fp8_fast',False):raise ValueError('fast FP8 unsupported')
    if owner.patcher.model['sd'] is not owner.original_sd:raise ValueError('unexpected static overlay')


def _set_parameter(model,name,tensor):
    import torch
    path,_,attr=name.rpartition('.')
    setattr(model.get_submodule(path),attr,torch.nn.Parameter(tensor,requires_grad=False))


def probe_dynamic(module,entries):
    """Observe four final effective coordinates during an actual CustomLinear forward.

    Independent rank-sized dot products avoid allocating a second expected matrix.
    """
    import torch
    r,c=module.weight.shape;coords=list(dict.fromkeys([(0,0),(0,c-1),(r-1,0),(r-1,c-1)]))
    expected=[]
    for i,j in coords:
        value=module.weight[i,j].to(module.compute_dtype)
        if module.scale_weight is not None:value=value*module.scale_weight
        # Match each low-precision operation in the actual CustomLinear math.
        for strength,payload,_,_,_ in entries:
            if isinstance(payload,tuple):delta=payload[1][0][i,j].to(module.compute_dtype)
            else:
                up,down,alpha,*_=payload.weights
                delta=torch.dot(up[i].to(module.compute_dtype),down[:,j].to(module.compute_dtype))
                strength*=1. if alpha is None else alpha/down.shape[0]
            value=value+delta*strength
        expected.append(float(value))
    original=module._linear_forward_impl;observed=[]
    def observe(x,weight,bias):
        observed.extend(float(weight[i,j]) for i,j in coords)
        return original(x,weight,bias)
    module._linear_forward_impl=observe
    try:
        with torch.no_grad():out=module(torch.ones((1,c),dtype=module.compute_dtype,device='cpu'))
        if not torch.isfinite(out).all().item():raise ValueError('dynamic forward nonfinite')
        torch.testing.assert_close(torch.tensor(observed),torch.tensor(expected),rtol=.003,atol=.003)
        for idx,(_,payload,_,_,_) in enumerate(entries):
            weights=payload[1] if isinstance(payload,tuple) else payload.weights
            for slot,tensor in enumerate(weights[:1] if isinstance(payload,tuple) else weights[:2]):
                actual=getattr(module,f'lora_diff_{idx}_{slot}')
                torch.testing.assert_close(actual,tensor.to(actual),rtol=0,atol=0)
        return dict(coordinates=[list(x) for x in coords],observed=observed,expected=expected,finite=True,step_reset=0)
    finally:
        module._linear_forward_impl=original;module._step.zero_()


def prepare_private(owner,parsed):
    import torch
    assert_clean(owner)
    parameters=dict(owner.transformer.named_parameters(remove_duplicate=False))
    module_aliases=[]
    # The fixed Wan constructor exposes these same-module references. They are
    # alternate paths to patch_embedding, not independently installed targets.
    for alias in ('original_patch_embedding','expanded_patch_embedding'):
        module=getattr(owner.transformer,alias,None)
        if module is None:continue
        if module is not getattr(owner.transformer,'patch_embedding',None):
            raise ValueError('unsupported patch_embedding module alias: '+alias)
        for name in list(parameters):
            if not name.startswith(alias+'.'):continue
            canonical='patch_embedding.'+name[len(alias)+1:]
            if name in owner.original_sd or canonical not in parameters or parameters[name] is not parameters[canonical]:
                raise ValueError('unsupported patch_embedding parameter alias: '+name)
            del parameters[name]
        module_aliases.append(alias)
    # No legacy _model_info/deepcopy of model. Actual parameters are checked here.
    seen=set()
    for name,p in parameters.items():
        if p.device.type!='cpu' or p.layout!=torch.strided:raise ValueError('materialized dense CPU parameter required')
        ptr=p.untyped_storage().data_ptr()
        if p.numel() and ptr in seen:raise ValueError('aliased actual parameter')
        seen.add(ptr)
        if name in owner.original_sd:
            source=owner.original_sd[name]
            expected=torch.float32 if name.startswith('patch_embedding.') else source.dtype
            if p.shape!=source.shape or p.dtype!=expected:raise ValueError('runtime shape/dtype conversion differs: '+name)
    from .wan_wrapper_head import HEAD_KEY,preflight_head,install_head
    head=preflight_head(owner,parsed,parameters)
    ordinary={key:entries for key,entries in parsed.items() if key!=HEAD_KEY}
    plans=owner.components.repair._preflight(owner.transformer,ordinary,1.,parameters=parameters)
    static_plan=tuple(p for p in plans if p.route=='static_parameter')
    dynamic_keys={p.key for p in plans if p.route=='dynamic_weight'}
    dynamic_keys.update(head)
    # Clone before *any* repair copy_ can run: original values may be read-only mmap.
    for plan in static_plan:
        _set_parameter(owner.transformer,plan.target,parameters[plan.target].detach().clone())
    owner.components.repair.apply_static_deltas(owner.transformer,static_plan)
    cached={p.target:owner.transformer.get_parameter(p.target).detach().cpu().clone() for p in static_plan}
    overlay=dict(owner.original_sd)
    overlay.update({k:v.clone() for k,v in cached.items()})
    dynamic={key:parsed[key] for key in dynamic_keys}
    owner.components.custom.set_lora_params(owner.transformer,dynamic)
    install_head(owner,dynamic)
    probes=[]
    for key,entries in dynamic.items():
        module=owner.transformer.get_submodule(key.removeprefix('diffusion_model.').rpartition('.')[0])
        probes.append(dict(target=key,**probe_dynamic(module,entries)))
    owner.patcher.model['sd']=overlay;owner.patcher.patches=dynamic
    options=owner.patcher.model_options.setdefault('transformer_options',{})
    options.update(merge_loras=False,lora_scheduling_enabled=False)
    owner.prepared=True
    witness=dict(role=owner.role,static_targets=len(cached),dynamic_targets=len(dynamic),dynamic_probes=probes,
        canonical_module_aliases=module_aliases,
        head_full_delta_adapter=bool(head),
        static_overlay_bytes=sum(v.numel()*v.element_size() for v in cached.values()),
        full_model_verified=False,source_parameters_mutated=False)
    return ExpertCertificate(MappingProxyType(cached),MappingProxyType(dynamic),witness)


def release_expert(owner):
    if owner.closed:return
    close=getattr(owner.components,'close',None)
    if close:close(owner)
    owner.closed=True;owner.patcher=None;owner.transformer=None;owner.original_sd=None
    gc.collect()


def prepare_control_expert(factory,role):
    factory.guard.check();owner=factory.build_unpatched(role);factory.guard.acquire(owner)
    try:assert_clean(owner);return owner
    except BaseException:
        release_expert(owner);raise


def prepare_expert(factory,role,certificate):
    if certificate is None or certificate.receipt['epoch']!=factory.epoch:raise ValueError('current pair certificate required')
    if certificate.receipt['comparison_sha256']!=factory.comparison_sha256:raise ValueError('pair comparison differs')
    if certificate.leases is not None:certificate.leases.verify()
    owner=prepare_control_expert(factory,role)
    try:
        cert=getattr(certificate,role);parameters=dict(owner.transformer.named_parameters())
        overlay=dict(owner.original_sd)
        for key,value in cert.static.items():
            if key not in parameters or tuple(parameters[key].shape)!=tuple(value.shape):raise ValueError('static target shape drift')
            overlay[key]=value.clone()
        owner.patcher.model['sd']=overlay;owner.patcher.patches=dict(cert.dynamic)
        owner.patcher.model_options['transformer_options'].update(merge_loras=False,lora_scheduling_enabled=False)
        owner.prepared=True;return owner
    except BaseException:
        release_expert(owner);raise


def admit_pair(factory,fast_profile,leases):
    if hasattr(fast_profile,'mode') and fast_profile.mode!='fast':raise ValueError('fast profile only')
    if factory.full_model and leases is None:raise ValueError('protected identity leases required')
    if leases is not None:leases.verify()
    guard=getattr(factory,'guard',None)
    if guard is None:factory.guard=OwnerGuard()
    def one(role):
        owner=prepare_control_expert(factory,role)
        try:
            parsed,trace=factory.parse(owner)
            factory.materialize(owner)
            cert=prepare_private(owner,parsed)
            cert=ExpertCertificate(cert.static,cert.dynamic,{**cert.witness,'trace':trace,'full_model_verified':factory.full_model})
            write_once(factory.root/f'admission/{role}-witness.json',cert.witness)
            return cert
        finally:
            factory.release(owner);release_expert(owner)
    high=one('high');factory.guard.check()
    low=one('low');factory.guard.check()
    if leases is not None:leases.verify()
    receipt=dict(schema_version=1,profile_sha256=fast_profile.digest() if hasattr(fast_profile,'digest') else fast_profile,
        comparison_sha256=factory.comparison_sha256,epoch=factory.epoch,full_model_verified=factory.full_model,
        admission_id=getattr(factory,'admission_id',None),
        high_witness_sha256=hashlib.sha256((factory.root/'admission/high-witness.json').read_bytes()).hexdigest(),
        low_witness_sha256=hashlib.sha256((factory.root/'admission/low-witness.json').read_bytes()).hexdigest())
    target=factory.root/'admission/pair.json';target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():raise ValueError('pair already published; do not repeat admission')
    partial=target.with_suffix('.partial.json');write_once(partial,receipt);os.rename(partial,target)
    return CertifiedPair(high,low,receipt,leases)


def validate_runtime_targets(owner,manifest):
    actual=dict(owner.transformer.named_parameters())
    if any('img' in key for key in owner.transformer.state_dict()):raise ValueError('actual model has img targets; exact exclusion invalid')
    for row in manifest:
        target=row['target']
        if row['classification']=='declared_not_applicable':
            if owner.role!='low' or target in actual:raise ValueError('actual exclusion condition differs')
        elif (target not in actual or target not in owner.original_sd
                or actual[target].shape!=owner.original_sd[target].shape):raise ValueError('actual target missing/shape differs')


class PinnedExpertFactory:
    """Full-model adapter, usable only inside a separately authorized GPU worker.

    No constructor loads tensors. Admission alone materializes one CPU expert.
    """
    full_model=True
    def __init__(self,context,loading,custom,repair,scope,comfy_lora,utils):
        self.context=context;self.root=context.root;self.epoch=context.epoch
        self.comparison_sha256=context.comparison_sha256;self.guard=OwnerGuard()
        self.loading=loading;self.custom=custom;self.repair=repair;self.scope=scope
        self.comfy_lora=comfy_lora;self.utils=utils

    def build_unpatched(self,role):
        self.context.require_gpu()
        import torch
        p=self.loading.WanVideoModelLoader().loadmodel(
            model=Path(self.context.models['base_'+role]['path']).name,base_precision='fp16',
            load_device='offload_device',quantization='disabled',attention_mode='sdpa',lora=None,
            compile_args=None,block_swap_args=dict(blocks_to_swap=40,offload_img_emb=True,offload_txt_emb=True,
                use_non_blocking=False,vace_blocks_to_swap=0,prefetch_blocks=0,block_swap_debug=False),
            rms_norm_function='default')[0]
        m=p.model
        if (m['fp8_matmul'] or m['base_dtype']!=torch.float16 or 'scaled' not in m['quantization']
                or len(m.diffusion_model.blocks)!=40 or m['sd'] is None or p.patches):raise ValueError('actual loader configuration differs')
        return ExpertOwner(p,m.diffusion_model,m['sd'],self,role)

    def materialize(self,owner):
        import torch
        # Admission scales are private CPU copies. Sampling uses a fresh owner.
        for m in owner.transformer.modules():
            if isinstance(getattr(m,'scale_weight',None),torch.Tensor):m.scale_weight=m.scale_weight.detach().cpu().clone()
        self.loading.load_weights(owner.transformer,owner.original_sd,owner.patcher.model['weight_dtype'],
            base_dtype=torch.float16,transformer_load_device=torch.device('cpu'),block_swap_args=None)

    def parse(self,owner):
        import torch
        from safetensors import safe_open
        policy,_=self.scope._load();pin=policy['profiles'][owner.role]
        # Classify the original storage schema; runtime dtype is checked separately.
        schema=torch.nn.Module()
        for key,value in owner.original_sd.items():
            if key=='scaled_fp8':continue
            current=schema;parts=key.split('.')
            for part in parts[:-1]:
                if part not in current._modules:current.add_module(part,torch.nn.Module())
                current=current._modules[part]
            current.register_parameter(parts[-1],torch.nn.Parameter(torch.empty(value.shape,dtype=value.dtype,device='meta'),requires_grad=False))
        path=Path(self.context.models['lora_'+owner.role]['path'])
        from .wan_wrapper_runtime_support import read_safetensors_header,TraceInputs,verify_retained
        header=read_safetensors_header(path)
        plan=self.scope.plan_lora_applicability(owner.role,header,schema,{'base':pin['base_identity'],'lora':pin['lora_identity']})
        validate_runtime_targets(owner,plan.manifest)
        mapping=dict(plan.applicable)
        with safe_open(path,framework='pt',device='cpu') as handle:
            data=TraceInputs(mapping,handle.get_tensor,header)
            keymap=self.loading.model_lora_keys_unet(owner.patcher.model,{})
            parsed=self.comfy_lora.load_lora(data,keymap,log_missing=False)
            verify_retained(data,parsed,plan.manifest)
        wrapped={key:[(1.,payload,1.,None,None)] for key,payload in parsed.items()}
        return wrapped,dict(source_count=len(header),applicable=len(mapping),excluded=len(plan.excluded),
            retained=len(data.cache),entries=[dict(x) for x in plan.manifest])

    def close(self,owner):
        import comfy.model_management as mm
        mm.unload_all_models();mm.cleanup_models();mm.soft_empty_cache()

    def release(self,owner):pass
