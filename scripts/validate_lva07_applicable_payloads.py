"""Stream approved original LoRA inputs through real parser and CPU target math.

AST specialization executes original function/class bodies for the frozen
ordinary-LoRA/diff formats; it is not complete Comfy module registration.
Target rows are tiled to bound memory. No actual14B base/model is loaded.
"""
from __future__ import annotations
import argparse
import ast
from collections import defaultdict
import gc
import hashlib
import importlib
import importlib.machinery
import json
import logging
import math
import os
from pathlib import Path
import sys
import time
import types
import struct
import subprocess
from typing import Callable, Optional


def components(comfy_root, evidence_path):
    import torch
    expected=json.loads(evidence_path.read_text(encoding='utf-8'))['local_comfy_sources']
    hashes={Path(x['path']).resolve().as_posix().lower():x['sha256'] for x in expected}
    records=[]
    def extract(relative,names,namespace):
        p=comfy_root/relative;raw=p.read_bytes();h=hashlib.sha256(raw).hexdigest()
        if hashes.get(p.resolve().as_posix().lower())!=h:raise RuntimeError(f'Frozen Comfy source mismatch: {relative}')
        tree=ast.parse(raw);nodes=[n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names]
        if {n.name for n in nodes}!=set(names):raise RuntimeError(f'Source symbol missing: {relative}')
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'),namespace)
        records.append({'path':str(p),'sha256':h,'symbols':names})
    ns={'__name__':'lva07_real_components','torch':torch,'nn':torch.nn,'Optional':Optional,'Callable':Callable,'logging':logging,'F':torch.nn.functional}
    extract('comfy/weight_adapter/base.py',['WeightAdapterBase'],ns)
    extract('comfy/weight_adapter/lora.py',['LoRAAdapter'],ns)
    ns['weight_adapter']=types.SimpleNamespace(adapters=[ns['LoRAAdapter']],WeightAdapterBase=ns['WeightAdapterBase'])
    extract('comfy/lora.py',['bias_key','load_lora'],ns)
    extract('comfy/utils.py',['unet_to_diffusers'],ns)
    return ns,records


def verify_source(root, trusted):
    """Admit the complete prepared file set before importing any Wrapper code."""
    root=root.resolve();raw=(root/'.lva07-manifest.json').read_bytes();manifest=json.loads(raw)
    expected={r['path']:r['sha256'] for r in trusted['baseline_files']}
    expected.update(trusted.get('patched_files',{}))
    expected.update({k:v for k,v in trusted['artifacts'].items() if k!='mixed-delta.patch'})
    actual={r['path']:r['sha256'] for r in manifest['files']}
    if len(actual)!=len(manifest['files']) or actual!=expected or manifest['upstream_reference']!=trusted['upstream_reference'] or manifest['patch_sha256']!=trusted['artifacts']['mixed-delta.patch']:
        raise RuntimeError('Prepared source manifest identity mismatch')
    for name,digest in expected.items():
        path=(root/name).resolve();path.relative_to(root)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise RuntimeError(f'Wrapper source identity mismatch: {name}')
    return {'source_root':str(root),'manifest_sha256':hashlib.sha256(raw).hexdigest(),'manifest':manifest}


def read_header(path, identity):
    """Read only a bounded current header; historical full SHA is not rehashed."""
    before=path.stat()
    if before.st_size!=identity['bytes']:raise RuntimeError('Current file size identity mismatch')
    with path.open('rb') as f:
        length=f.read(8)
        if len(length)!=8:raise RuntimeError('Invalid header length prefix')
        n=struct.unpack('<Q',length)[0]
        if n<2 or n>16*1024**2 or n>before.st_size-8:raise RuntimeError('Invalid bounded header length')
        raw=f.read(n)
    digest=hashlib.sha256(raw).hexdigest()
    if len(raw)!=n or ('header_sha256' in identity and digest!=identity['header_sha256']):raise RuntimeError('Current header identity mismatch')
    header=json.loads(raw);header.pop('__metadata__',None)
    return header,{'path':str(path.resolve()),'bytes':before.st_size,'mtime_ns':before.st_mtime_ns,'ino':before.st_ino,'header_bytes':n,'header_sha256':digest,'historical_identity':identity}


def schema_model(header):
    import torch
    model=torch.nn.Module()
    dtypes={'F16':torch.float16,'BF16':torch.bfloat16,'F32':torch.float32,'F64':torch.float64,'F8_E4M3':torch.float8_e4m3fn}
    for target,meta in header.items():
        parts=target.split('.');owner=model
        for name in parts[:-1]:
            if name not in owner._modules:owner.add_module(name,torch.nn.Module())
            owner=owner._modules[name]
        if parts[-1] not in owner._parameters:
            owner.register_parameter(parts[-1],torch.nn.Parameter(torch.empty(meta['shape'],device='meta',dtype=dtypes[meta['dtype']]),requires_grad=False))
    return model


class ReadTrace(dict):
    def __init__(self,mapping,reader,metadata):
        super().__init__({k:None for k in mapping});self.mapping=mapping;self.reader=reader;self.metadata=metadata;self.read=set();self.cache={}
    def __getitem__(self,key):
        import torch
        if key not in self.mapping:raise KeyError(key)
        if key not in self.cache:
            value=self.reader(self.mapping[key]);meta=self.metadata[self.mapping[key]]
            if list(value.shape)!=meta['shape'] or not value.is_floating_point() or not torch.isfinite(value).all().item():raise RuntimeError(f'Invalid original tensor: {key}')
            self.cache[key]=value
        self.read.add(key);return self.cache[key]
    def get(self,key,default=None):return self[key] if key in self.mapping else default


def verify_retained_inputs(data, parsed, rows):
    """A read counts only when its exact tensor remains in the final payload."""
    expected={'diffusion_model.'+rows[k]['target'] for k in data.mapping}
    if data.read!=set(data.mapping) or set(parsed)!=expected:
        raise RuntimeError('Parser retained target/input set mismatch')
    for key in data.mapping:
        payload=parsed['diffusion_model.'+rows[key]['target']]
        if key.endswith(('.lora_up.weight','.lora_B.weight')):
            retained=getattr(payload,'weights',(None,None))[0]
        elif key.endswith(('.lora_down.weight','.lora_A.weight')):
            retained=getattr(payload,'weights',(None,None))[1]
        elif key.endswith(('.diff','.diff_b')) and isinstance(payload,tuple) and payload[0]=='diff':
            retained=payload[1][0]
        else:raise RuntimeError(f'Parser retained unsupported slot: {key}')
        if retained is not data.cache[key]:raise RuntimeError(f'Parser retained tensor identity mismatch: {key}')


def apply_target(custom,repair,payload,shape,chunk_rows):
    """Apply every target element; independent double probes audit the math."""
    import torch
    if isinstance(payload,tuple) and payload[0]=='diff':
        delta=payload[1][0]
        model=torch.nn.Module();model.register_parameter('weight',torch.nn.Parameter(torch.zeros(shape,dtype=torch.float32),requires_grad=False))
        plan=repair._Plan('weight','weight','static_parameter',((1.,payload,1.,None,None),))
        repair.apply_static_deltas(model,[plan]);actual=model.weight
        if not torch.isfinite(actual).all().item():raise RuntimeError('Non-finite static output')
        want=delta.flatten()[:4].double();got=actual.flatten()[:4].double()
        if not torch.allclose(got,want,atol=1e-6,rtol=2e-5):raise RuntimeError('Static reference mismatch')
        return {'route':'real_repair_static','target_elements':actual.numel(),'chunks':1,'max_probe_error':(got-want).abs().max().item()}
    up,down,alpha,mid,dora,reshape=payload.weights
    if len(shape)!=2 or any(x is not None for x in (mid,dora,reshape)):raise RuntimeError('Unsupported original adapter extension')
    if list(shape)!=[up.shape[0],down.shape[1]] or up.shape[1]!=down.shape[0]:raise RuntimeError('Original rank/shape mismatch')
    scale=1. if alpha is None else float(alpha)/down.shape[0]
    if not math.isfinite(scale) or alpha==0:raise RuntimeError('Unsupported alpha')
    max_error=0.;chunks=0;elements=0
    for start in range(0,shape[0],chunk_rows):
        end=min(start+chunk_rows,shape[0]);count=end-start
        model=torch.nn.Module()
        linear=custom.CustomLinear(shape[1],count,bias=False,compute_dtype=torch.float32,device=torch.device('meta'))
        linear.weight=torch.nn.Parameter(torch.zeros((count,shape[1]),dtype=torch.float32),requires_grad=False)
        model.add_module('proj',linear)
        sliced=type(payload)(set(payload.loaded_keys),(up[start:end],down,alpha,None,None,None))
        custom.set_lora_params(model,{'diffusion_model.proj.weight':[(1.,sliced,1.,None,None)]})
        if len(linear.lora_diffs)!=1:raise RuntimeError('Dynamic tensor was not installed')
        with torch.no_grad():actual=linear._get_weight_with_lora(linear.weight)
        if not torch.isfinite(actual).all().item():raise RuntimeError('Non-finite dynamic output')
        u=up[start:min(start+2,end)].double().tolist();d=down[:,:min(2,shape[1])].double().tolist()
        want=torch.tensor([[sum(row[k]*d[k][j] for k in range(len(d)))*scale for j in range(len(d[0]))] for row in u],dtype=torch.float64)
        got=actual[:len(u),:want.shape[1]].double()
        if not torch.allclose(got,want,atol=1e-6,rtol=2e-5):raise RuntimeError('Dynamic independent double reference mismatch')
        max_error=max(max_error,(got-want).abs().max().item());chunks+=1;elements+=actual.numel()
        del actual,linear,model,sliced
    return {'route':'real_custom_linear_dynamic_tiled','target_elements':elements,'chunks':chunks,'max_probe_error':max_error}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True)
    p.add_argument('--chunk-rows',type=int,default=2048);p.add_argument('--threads',type=int,default=8)
    args=p.parse_args();sys.dont_write_bytecode=True;os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['HF_HUB_OFFLINE']='1'
    repo=Path(__file__).resolve().parents[1]
    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    trusted=json.loads((repo/'patches/wanvideo-wrapper/manifest.json').read_bytes())
    source_identity=verify_source(args.source_root,trusted)
    source_identity['local_git_commit']=subprocess.check_output(['git','-C',str(args.source_root),'rev-parse','HEAD'],text=True).strip()
    source_identity['local_git_dirty']=bool(subprocess.check_output(['git','-C',str(args.source_root),'status','--porcelain'],text=True))
    import torch,psutil
    from safetensors import safe_open
    if str(torch.__version__)!='2.14.1+cpu' or torch.version.cuda is not None:raise RuntimeError('CPU-only environment required')
    if args.chunk_rows<1 or args.chunk_rows>2048:raise RuntimeError('chunk rows must be1..2048')
    torch.set_num_threads(args.threads);torch.set_num_interop_threads(1)
    args.output_root.mkdir(parents=True,exist_ok=False)
    for name,path in [('lva07_stream',args.source_root),('lva07_stream.gguf',args.source_root/'gguf')]:
        pkg=types.ModuleType(name);pkg.__path__=[str(path.resolve())];pkg.__spec__=importlib.machinery.ModuleSpec(name,None,is_package=True);sys.modules[name]=pkg
    custom=importlib.import_module('lva07_stream.custom_linear');repair=importlib.import_module('lva07_stream.lva07_mixed_delta');scope=importlib.import_module('lva07_stream.lva07_applicability')
    comfy=Path('E:/VideoAI/shared/tools/ComfyUI_windows_portable/ComfyUI')
    ns,source_records=components(comfy,repo/'docs/task-designs/LVA-07-environment-review.json')
    ns['comfy']=types.SimpleNamespace(utils=types.SimpleNamespace(unet_to_diffusers=ns['unet_to_diffusers']))
    node_source=(args.source_root/'nodes_model_loading.py').read_text(encoding='utf-8');node=next(n for n in ast.parse(node_source).body if isinstance(n,ast.FunctionDef) and n.name=='model_lora_keys_unet')
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(args.source_root/'nodes_model_loading.py'),'exec'),ns)
    policy=json.loads((args.source_root/'lva07_img_policy.json').read_text(encoding='utf-8'))
    source_identity['mapper_function_sha256']=hashlib.sha256(ast.get_source_segment(node_source,node).encode()).hexdigest()
    source_identity['normalizer_function_sha256']=policy['normalizer_function_sha256']
    source_identity['policy_sha256']=hashlib.sha256((args.source_root/'lva07_img_policy.json').read_bytes()).hexdigest()
    base=Path('E:/VideoAI/shared/models/comfyui/loras');start=time.monotonic();process=psutil.Process();records=[];groups_done=0;peak=0;role_results=[];current_files=[]
    def persist(status):
        memory=process.memory_info()
        data={'status':status,'groups_done':groups_done,'input_records':len(records),'elapsed_seconds':time.monotonic()-start,'rss_bytes':memory.rss,'peak_observed_rss_bytes':peak,'os_peak_working_set_bytes':getattr(memory,'peak_wset',None)}
        (args.output_root/'progress.json').write_bytes((json.dumps(data,indent=2)+'\n').encode());return data
    try:
        with (args.output_root/'tensor-trace.jsonl').open('w',encoding='utf-8') as output:
            for role in ['high','low']:
                profile=policy['profiles'][role]
                base_path=base.parent/'diffusion_models'/f'wan2.2_i2v_{role}_noise_14B_fp8_scaled.safetensors'
                base_header,base_evidence=read_header(base_path,profile['base_identity']);current_files.append(base_evidence)
                if any('img' in k for k in base_header):raise RuntimeError('Current base header has img targets')
                model=schema_model(base_header)
                wrapper=torch.nn.Module();wrapper.add_module('diffusion_model',model);wrapper.model_config=types.SimpleNamespace(unet_config={})
                key_map=ns['model_lora_keys_unet'](wrapper,{})
                path=base/f'wan2.2_i2v_A14b_{role}_noise_lora_rank64_lightx2v_4step_1022.safetensors';before=path.stat()
                if before.st_size!=profile['lora_identity']['bytes']:raise RuntimeError('LoRA size changed')
                header,lora_evidence=read_header(path,profile['lora_identity']);current_files.append(lora_evidence)
                plan=scope.plan_lora_applicability(role,header,model,{'lora':profile['lora_identity'],'base':profile['base_identity']})
                rows={r['normalized_key']:dict(r) for r in plan.manifest};grouped=defaultdict(dict)
                for normalized,original in plan.applicable.items():
                    stem=None
                    for suffix in ['.lora_down.weight','.lora_up.weight','.lora_A.weight','.lora_B.weight','.diff_b','.diff']:
                        if normalized.endswith(suffix):stem=normalized[:-len(suffix)];break
                    if stem is None or stem not in key_map:raise RuntimeError(f'Unmapped source: {normalized}')
                    grouped[stem][normalized]=original
                for r in plan.excluded:
                    row=dict(r)|{'expert':role,'parser_consumed':False,'parser_retained':False,'cpu_target_fixture_applied':False,'full_model_applied':None};records.append(row);output.write(json.dumps(row)+'\n')
                consumed_count=0;role_targets=0
                with safe_open(path,framework='pt',device='cpu') as handle:
                    for stem,mapping in grouped.items():
                        data=ReadTrace(mapping,handle.get_tensor,header)
                        parsed=ns['load_lora'](data,{stem:key_map[stem]},log_missing=False)
                        verify_retained_inputs(data,parsed,rows)
                        applied={}
                        for target,payload in parsed.items():
                            bare=target.removeprefix('diffusion_model.')
                            if bare not in model.state_dict():raise RuntimeError(f'Parsed target missing: {target}')
                            applied[target]=apply_target(custom,repair,payload,list(model.get_parameter(bare).shape),args.chunk_rows);role_targets+=1
                        for normalized,original in mapping.items():
                            row=rows[normalized]|{'expert':role,'parser_consumed':True,'parser_retained':True,'cpu_target_fixture_applied':True,'full_model_applied':None,'target_evidence':applied['diffusion_model.'+rows[normalized]['target']]}
                            records.append(row);output.write(json.dumps(row)+'\n');consumed_count+=1
                        groups_done+=1;peak=max(peak,process.memory_info().rss)
                        memory=process.memory_info()
                        if max(peak,getattr(memory,'peak_wset',0))>2*1024**3:raise RuntimeError('CPU process memory exceeded2GiB budget')
                        if groups_done%20==0:output.flush();persist('running');print(json.dumps({'role':role,'groups':groups_done,'records':len(records),'elapsed':round(time.monotonic()-start,1)}),flush=True)
                        del parsed,data,applied
                after=path.stat()
                if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino):raise RuntimeError('Original LoRA changed during read')
                role_results.append({'role':role,'input':len(header),'excluded':len(plan.excluded),'parser_consumed':consumed_count,'parser_retained':consumed_count,'cpu_target_fixture_applied':consumed_count,'target_parameters_exercised':role_targets,'full_model_applied':False,'schema_source':'current base header; meta parameters in actual storage dtype; arithmetic fixtures FP32'})
                del model,wrapper,plan;gc.collect()
        if verify_source(args.source_root,trusted)!= {k:source_identity[k] for k in ['source_root','manifest_sha256','manifest']}:raise RuntimeError('Source changed during execution')
        if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=script_sha256:raise RuntimeError('Executing script changed during run')
        for item in source_records:
            if hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Comfy source changed during execution')
        for item in current_files:
            stat=Path(item['path']).stat()
            if (stat.st_size,stat.st_mtime_ns,stat.st_ino)!=(item['bytes'],item['mtime_ns'],item['ino']):raise RuntimeError('Admitted input changed during execution')
        result=persist('passed')|{'roles':role_results,'wrapper_source':source_identity,'current_files':current_files,'trace_sha256':hashlib.sha256((args.output_root/'tensor-trace.jsonl').read_bytes()).hexdigest(),'source_components':source_records,'torch':str(torch.__version__),'torch_cuda':torch.version.cuda,'chunk_rows':args.chunk_rows,'full_model_verified':False,'component_scope':'Original AST class/function bodies; ordinary LoRA adapter registry only; real normalizer/key mapper/parser and full target row-tiling math. No complete Comfy imports/registration.', 'identity_limit':'Historical admitted SHA descriptors plus current headers/stat, not a repeated full-file hash','file_sha256':script_sha256}
        (args.output_root/'results.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result),flush=True);return 0
    except Exception as exc:
        persist('failed');(args.output_root/'failure.json').write_bytes((json.dumps({'error':repr(exc),'groups_done':groups_done,'records':len(records)},indent=2)+'\n').encode());raise


if __name__=='__main__':raise SystemExit(main())
