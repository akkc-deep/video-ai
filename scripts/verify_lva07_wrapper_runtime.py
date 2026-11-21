"""Run only the new small CPU fixtures against pinned real function bodies."""
from __future__ import annotations
import argparse
import ast
import hashlib
import importlib
import importlib.machinery
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest
from typing import Callable,Optional

SOURCE=Path(__file__).resolve().parents[1]
RECORDS=[]


def load_components(wrapper,comfy):
    import torch
    if str(torch.__version__)!='2.14.1+cpu' or torch.version.cuda is not None:
        raise ValueError('independent CPU-only torch required')
    torch.set_num_threads(2)
    marker=json.loads((wrapper.parents[2]/'sources.json').read_text(encoding='utf-8'))
    expected={r['path']:r['sha256'] for r in marker['wrapper_files']}
    for name in ('custom_linear.py','lva07_mixed_delta.py','lva07_applicability.py','lva07_img_policy.json','nodes_model_loading.py','utils.py'):
        p=wrapper/name;sha=hashlib.sha256(p.read_bytes()).hexdigest()
        if expected[name]!=sha:raise ValueError('fixed source differs '+name)
        RECORDS.append(dict(path=str(p),sha256=sha))
    for name,path in [('lva07_runtime',wrapper),('lva07_runtime.gguf',wrapper/'gguf')]:
        pkg=types.ModuleType(name);pkg.__path__=[str(path)];pkg.__spec__=importlib.machinery.ModuleSpec(name,None,is_package=True);sys.modules[name]=pkg
    custom=importlib.import_module('lva07_runtime.custom_linear')
    repair=importlib.import_module('lva07_runtime.lva07_mixed_delta')
    scope=importlib.import_module('lva07_runtime.lva07_applicability')
    def extract(path,names,ns):
        raw=path.read_bytes();tree=ast.parse(raw)
        if path.is_relative_to(comfy) and not path.is_relative_to(wrapper):
            inventory=json.loads((SOURCE/'docs/task-designs/LVA-07-04-software.json').read_bytes())
            rows={str(Path(r['path']).resolve()).lower():r for r in inventory['files'] if r.get('group')=='comfy'}
            if rows[str(path.resolve()).lower()]['sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('fixed Comfy source differs')
        selected=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
        if {n.name for n in selected}!=set(names):raise ValueError('source symbols missing')
        exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),'exec'),ns)
        RECORDS.append(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),symbols=names))
    class Progress:
        def __init__(self,*a):pass
        def update(self,*a):pass
        def update_absolute(self,*a):pass
    ns=dict(torch=torch,nn=torch.nn,Optional=Optional,Callable=Callable,logging=logging,F=torch.nn.functional,
        log=logging.getLogger('fixture'),ProgressBar=Progress,tqdm=lambda x,**kw:x)
    extract(wrapper/'utils.py',['check_device_same','set_module_tensor_to_device','get_module_memory_mb_per_device'],ns)
    extract(wrapper/'nodes_model_loading.py',['load_weights','model_lora_keys_unet','standardize_lora_key_format'],ns)
    # Actual parser/mapper bodies, ordinary LoRA registry only, as in prior proof.
    extract(comfy/'comfy/weight_adapter/base.py',['WeightAdapterBase'],ns)
    extract(comfy/'comfy/weight_adapter/lora.py',['LoRAAdapter'],ns)
    ns['weight_adapter']=types.SimpleNamespace(adapters=[ns['LoRAAdapter']],WeightAdapterBase=ns['WeightAdapterBase'])
    extract(comfy/'comfy/lora.py',['bias_key','load_lora'],ns)
    extract(comfy/'comfy/utils.py',['unet_to_diffusers'],ns)
    ns['comfy']=types.SimpleNamespace(utils=types.SimpleNamespace(unet_to_diffusers=ns['unet_to_diffusers']))
    def load(owner):
        ns['load_weights'](owner.transformer,owner.patcher.model['sd'],torch.float8_e4m3fn,torch.float16,torch.device('cpu'),None)
    return types.SimpleNamespace(custom=custom,repair=repair,scope=scope,load=load,ns=ns)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wrapper-root',type=Path,required=True);p.add_argument('--comfy-root',type=Path,required=True)
    p.add_argument('--cpu-python',type=Path);p.add_argument('--cpu-site',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
    args=p.parse_args(argv)
    if not args.child:
        if not args.cpu_python or not args.cpu_site: p.error('explicit CPU interpreter/site required')
        args.output.mkdir(parents=True,exist_ok=False)
        command=[str(args.cpu_python),'-X','utf8','-B',str(Path(__file__).resolve()),'--child','--wrapper-root',str(args.wrapper_root),
            '--comfy-root',str(args.comfy_root),'--cpu-site',str(args.cpu_site),'--output',str(args.output)]
        with (args.output/'unittest.log').open('xb') as log:
            code=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=180,env=dict(os.environ,CUDA_VISIBLE_DEVICES='',HF_HUB_OFFLINE='1')).returncode
        print((args.output/'unittest.log').read_text(encoding='utf-8')[-5000:]);return code
    sys.dont_write_bytecode=True
    sys.path[:0]=[str(SOURCE/'src'),str(SOURCE/'scripts'),str(SOURCE/'tests/experiments'),str(args.cpu_site)]
    os.environ.update(LVA07_RUNTIME_FIXTURE='1',LVA07_WRAPPER=str(args.wrapper_root),LVA07_COMFY=str(args.comfy_root),CUDA_VISIBLE_DEVICES='')
    # Running as __main__: use this same module to retain the source record list.
    sys.modules['verify_lva07_wrapper_runtime']=sys.modules[__name__]
    suite=unittest.defaultTestLoader.loadTestsFromName('test_lva07_wrapper_runtime')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    import torch,psutil
    report=dict(passed=result.wasSuccessful(),tests_run=result.testsRun,failures=[str(t) for t,_ in result.failures],
        errors=[str(t) for t,_ in result.errors],sources=RECORDS,executable=sys.executable,torch=str(torch.__version__),torch_cuda=torch.version.cuda,
        evidence_scope='small synthetic CPU fixtures using unchanged pinned function/class bodies; progress/logging bookkeeping replaced',
        full_model_verified=False,gpu_used=False,checkpoint_payload_bytes=0,rss_bytes=psutil.Process().memory_info().rss,
        production_ready=False)
    (args.output/'results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
