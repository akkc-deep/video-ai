"""Owned bounded independent Wrapper worker. Default controller only probes CPU schemas."""
from __future__ import annotations
import argparse
import asyncio
import builtins
import ctypes
from ctypes import wintypes
import hashlib
import importlib
import json
import os
from pathlib import Path
import runpy
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.request import Request,urlopen
from uuid import uuid4

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE/'src'))
from video_ai.experiments.wan_fast_profiles import Artifact,artifact,digest,write_once
from video_ai.experiments.wan_fast_experiment import read
from video_ai.experiments.wan_wrapper_backend import REQUIRED_NODES,capabilities,freeze_comparison,WrapperProfile,contract

ENVIRONMENT=Path('E:/VideoAI/scratch/benchmarks/LVA-07-04-environment')
MODEL_ROOT=Path('E:/VideoAI/shared/models/comfyui')
SCRATCH=Path('E:/VideoAI/scratch/benchmarks')


def verify_environment():
    execution=read(SOURCE/'docs/task-designs/LVA-07-03-preparation-execution.json')
    for stage in ('sources','runtime','wheels','install'):
        marker=execution['stage_markers'][stage]
        if hashlib.sha256(Path(marker['path']).read_bytes()).hexdigest()!=marker['sha256']:raise ValueError('environment stage identity drift')
    root=ENVIRONMENT/'ComfyUI/custom_nodes/ComfyUI-WanVideoWrapper-LVA07'
    for row in read(ENVIRONMENT/'sources.json')['wrapper_files']:
        Artifact(str((root/row['path']).resolve()),row['bytes'],row['sha256']).verify()
    return root


def bootstrap_software():
    from video_ai.experiments.wan_wrapper_runtime_support import SoftwareVerifier,SOFTWARE_SHA256
    p=SOURCE/'docs/task-designs/LVA-07-04-software.json'
    if hashlib.sha256(p.read_bytes()).hexdigest()!=SOFTWARE_SHA256:raise ValueError('software inventory identity differs')
    rows=read(p)['files'];verifier=SoftwareVerifier(rows,[ENVIRONMENT/'python_embeded'])
    for row in rows:
        path=Path(row['path'])
        if path.parent==ENVIRONMENT/'python_embeded' and path.suffix.lower() in ('.exe','.dll','.zip','.pth'):verifier.verify(path)
    return verifier


def make_profiles():
    manifest=read(SOURCE/'docs/task-designs/LVA-07-environment-manifest.json')
    aliases={'wan_high':'base_high','wan_low':'base_low','text_encoder':'t5'}
    models={aliases.get(m['role'],m['role']):{k:m[k] for k in ('path','bytes','sha256','header_sha256')} for m in manifest['models']}
    source_paths=[SOURCE/'docs/task-designs/LVA-07-04-contract.json',SOURCE/'docs/task-designs/LVA-07-04-node-contract.json',
                  SOURCE/'docs/task-designs/LVA-07-04-software.json',Path(__file__).resolve(),SOURCE/'scripts/benchmark_wan_wrapper.py',
                  *sorted((SOURCE/'src').rglob('*.py')),
                  SOURCE/'scripts/benchmark_local_gpu.py',SOURCE/'src/video_ai/experiments/wan_fast_profiles.py',
                  SOURCE/'src/video_ai/experiments/wan_fast_experiment.py',SOURCE/'src/video_ai/experiments/wan_fast_media.py']
    for relative in ('docs/task-designs/LVA-07-06-node-contract.json','scripts/benchmark_wan_wrapper_matrix.py',
                     'scripts/inspect_wan_wrapper_matrix_tokens.py','scripts/postprocess_local_gpu.py','scripts/observe_local_comfy.py','workflows/upscale_api.json'):
        if (SOURCE/relative).exists():source_paths.append(SOURCE/relative)
    tools={name:artifact(f'E:/VideoAI/shared/tools/ffmpeg/bin/{name}.exe').identity_dict() for name in ('ffmpeg','ffprobe')}
    tools['artifacts']=list(tools.values())
    common=dict(source=dict(root=str(SOURCE),artifacts=[artifact(p).identity_dict() for p in source_paths]),
        runtime=dict(executable=str(ENVIRONMENT/'python_embeded/python.exe'),comfy_root=str(ENVIRONMENT/'ComfyUI'),
            artifacts=[artifact(ENVIRONMENT/(s+'.json')).identity_dict() for s in ('sources','runtime','wheels','install')]),
        tool=tools,models=models,policy=dict(sha256=read(SOURCE/'docs/task-designs/LVA-07-04-contract.json')['source_policy_sha256']))
    return {m:WrapperProfile.create(m,common) for m in ('control','fast')}


class BoundedJob:
    def __init__(self,process,private_limit,*,cpu=True):
        self.handle=None
        if os.name!='nt':raise ValueError('Windows Job required for this fixed environment')
        class Basic(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),('flags',wintypes.DWORD),
                ('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active',wintypes.DWORD),
                ('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class IO(ctypes.Structure):_fields_=[('count'+str(i),ctypes.c_ulonglong) for i in range(6)]
        class Extended(ctypes.Structure):
            _fields_=[('basic',Basic),('io',IO)]+[(name,ctypes.c_size_t) for name in ('process_memory','job_memory','peak_process','peak_job')]
        api=ctypes.WinDLL('kernel32',use_last_error=True);self.api=api
        api.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];api.CreateJobObjectW.restype=wintypes.HANDLE
        api.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD];api.SetInformationJobObject.restype=wintypes.BOOL
        api.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];api.AssignProcessToJobObject.restype=wintypes.BOOL
        api.CloseHandle.argtypes=[wintypes.HANDLE];api.CloseHandle.restype=wintypes.BOOL
        handle=api.CreateJobObjectW(None,None)
        if not handle:raise ctypes.WinError(ctypes.get_last_error())
        info=Extended();info.basic.flags=0x2000|0x100|(0x8 if cpu else 0);info.basic.active=1 if cpu else 0;info.process_memory=private_limit
        if not api.SetInformationJobObject(handle,9,ctypes.byref(info),ctypes.sizeof(info)) or not api.AssignProcessToJobObject(handle,process._handle):
            error=ctypes.get_last_error();api.CloseHandle(handle);raise ctypes.WinError(error)
        self.handle=handle
    def close(self):
        if self.handle is not None:self.api.CloseHandle(self.handle);self.handle=None


def owned_listener(port,pid):
    from video_ai.experiments.whole_scene_runner import _listener_owned
    try:_listener_owned(port,pid)
    except RuntimeError as exc:raise ValueError('listener owner/address differs') from exc


def request(port,route,*,method='GET',body=None):
    data=None if body is None else json.dumps(body).encode()
    with urlopen(Request(f'http://127.0.0.1:{port}'+route,data=data,method=method,headers={'Content-Type':'application/json'}),timeout=2) as response:
        raw=response.read(2*1024**2+1)
        if len(raw)>2*1024**2:raise ValueError('bounded HTTP response exceeded')
        return json.loads(raw)


def stop_owned(process,root,epoch):
    forced=False
    if process.poll() is None:
        write_once(root/'stop.request.json',dict(pid=process.pid,epoch=epoch))
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            forced=True;process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    return dict(exit_code=process.returncode,forced=forced,graceful=not forced and process.returncode==0,exited=process.poll() is not None)


def controller_passed(result):
    return bool(result.get('passed') and result.get('exited') and result.get('port_closed') and result.get('exit_code')==0
        and result.get('graceful') and not result.get('forced') and not result.get('error') and not result.get('timed_out'))


def execution_deadline_seconds(mode,max_seconds,authorization):
    if mode not in ('cpu','gpu'):raise ValueError('worker mode')
    if mode=='gpu' and max_seconds==0:
        if (not authorization or authorization.get('approved') is not True or not authorization.get('user_evidence')
                or 'max_service_seconds' not in authorization or authorization['max_service_seconds'] is not None):
            raise ValueError('explicit unlimited GPU duration authorization required')
        return float('inf')
    if not 10<=max_seconds<=(180 if mode=='cpu' else 14400):raise ValueError('bounded worker deadline')
    return max_seconds


def worker_private_limit(mode):
    if mode not in ('cpu','gpu'):raise ValueError('worker mode')
    return 4*1024**3 if mode=='cpu' else contract()['future_full_model_limits']['process_private_commit_bytes']


def host_available_commit_bytes():
    class MemoryStatus(ctypes.Structure):
        _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(name,ctypes.c_ulonglong) for name in
            ('total_phys','avail_phys','total_pagefile','avail_pagefile','total_virtual','avail_virtual','avail_extended')]
    value=MemoryStatus();value.length=ctypes.sizeof(value)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):raise ctypes.WinError()
    return value.avail_pagefile


def preflight_host_commit():
    available=host_available_commit_bytes();limits=contract()['future_full_model_limits']
    if available<limits['min_available_commit_bytes']:raise ValueError('host available commit below configured minimum')
    return dict(available_commit_bytes=available,min_available_commit_bytes=limits['min_available_commit_bytes'],
        process_private_commit_bytes=worker_private_limit('gpu'))


def controller(root,*,port=8297,max_seconds=180,mode='cpu',authorization=None):
    from video_ai.runtime.resources import windows_memory
    from video_ai.runtime.production_state import process_started_at
    root=Path(root).resolve()
    if not root.is_relative_to(SCRATCH.resolve()) or root==SCRATCH.resolve():raise ValueError('new scratch experiment root required')
    if not 1024<=port<=65535:raise ValueError('bounded worker port')
    max_seconds=execution_deadline_seconds(mode,max_seconds,read(authorization) if authorization else None)
    if shutil.disk_usage(root.parent).free<512*1024**2:raise ValueError('512MiB disk reserve required')
    with socket.socket() as reserve:reserve.bind(('127.0.0.1',port))
    verify_environment()
    if mode=='cpu':
        root.mkdir(parents=True,exist_ok=False)
        for name in ('input','output','temp','user','cache'):(root/name).mkdir()
        fixture=dict(input_relative='probe-no-image.png',input_sha256='0'*64,positive='',negative='',seed_high=264244520398999,seed_low=0,probe_only=True)
        marker=freeze_comparison(root,make_profiles(),fixture,port=port)
    else:
        from video_ai.experiments.wan_wrapper_nodes import WorkerContext
        if authorization is None:raise ValueError('explicit LVA-07-05 authorization file required')
        auth=read(authorization);ctx=WorkerContext(root,mode='gpu',epoch='preflight',authorization=auth);ctx.require_gpu()
        marker=read(root/'experiment.json')
        if marker['port']!=port or read(root/'fixture.json').get('probe_only'):raise ValueError('non-probe sealed root/original port required')
        if (root/'service-owner.json').exists():raise ValueError('previous service epoch exists; explicit recovery design required, no auto-restart')
        # Read outside the bounded child: Windows may report Job-relative commit inside it.
        write_once(root/'host-commit-preflight.json',preflight_host_commit())
        for name in ('input','output','temp','user','cache'):(root/name).mkdir(exist_ok=True)
    epoch=str(uuid4());command=[str(ENVIRONMENT/'python_embeded/python.exe'),'-I','-B','-X','utf8',str(Path(__file__).resolve()),
        '--worker','--root',str(root),'--port',str(port),'--mode',mode]
    if authorization:command+=['--authorization',str(Path(authorization).resolve())]
    launch=dict(command=command,mode=mode,epoch=epoch,profiles=marker['profiles'],comparison_sha256=marker['comparison_sha256'],source_root=str(SOURCE),
        authorization_sha256=digest(read(authorization)) if authorization else None)
    if marker.get('schema_version')==2:
        from video_ai.experiments.wan_wrapper_matrix import utcnow
        launch.update(controller_started_at_utc=utcnow(),controller_started_monotonic=time.monotonic())
    write_once(root/'frozen/service-launch.json',launch)
    environment=dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HOME=str(root/'cache'),TEMP=str(root/'temp'),TMP=str(root/'temp'))
    if mode=='cpu':environment['CUDA_VISIBLE_DEVICES']=''
    bootstrap=bootstrap_software()
    started=time.monotonic();process=None;job=None;gpu_owner=None;sampler=None;result=dict(passed=False,mode=mode,graph_posts=0,checkpoint_payload_bytes=0,gpu_used=False if mode=='cpu' else None,peak_rss_observed_bytes=0)
    try:
        if mode=='gpu' and marker.get('schema_version')==2:
            from video_ai.experiments.wan_wrapper_matrix_observer import GpuOwnership
            gpu_owner=GpuOwnership();gpu_owner.__enter__()
        with (root/'stdout.log').open('xb') as out,(root/'stderr.log').open('xb') as err:
            process=subprocess.Popen(command,cwd=ENVIRONMENT/'ComfyUI',stdout=out,stderr=err,env=environment,shell=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            job=BoundedJob(process,worker_private_limit(mode),cpu=mode=='cpu')
            owner=dict(pid=process.pid,process_started_at=process_started_at(process.pid),port=port,experiment_root=str(root),epoch=epoch,
                       launch_sha256=digest(launch))
            write_once(root/'service-owner.json',owner)
            write_once(root/'controller-start.json',dict(epoch=epoch,pid=process.pid))
            result.update(pid=process.pid,process_started_at=owner['process_started_at'],epoch=epoch)
            if mode=='gpu' and marker.get('schema_version')==2:
                from video_ai.experiments.wan_wrapper_matrix_observer import DeviceSampler
                sampler=DeviceSampler(process,root/'resources.jsonl',epoch).start()
            while time.monotonic()-started<max_seconds:
                if process.poll() is not None:raise RuntimeError('owned worker exited before readiness')
                rss=windows_memory([process.pid])['process_rss_bytes'][str(process.pid)]
                result['peak_rss_observed_bytes']=max(result['peak_rss_observed_bytes'],rss)
                if rss>(4 if mode=='cpu' else 24)*1024**3:raise ValueError('worker RSS stop threshold')
                if any((root/log).stat().st_size>16*1024**2 for log in ('stdout.log','stderr.log')):raise ValueError('log size stop threshold')
                if (root/'worker-attestation.json').exists():
                    try:owned_listener(port,process.pid);break
                    except ValueError:pass
                time.sleep(.25)
            else:raise TimeoutError('CPU node probe deadline')
            owned_listener(port,process.pid)
            schemas={}
            for name in REQUIRED_NODES:
                if time.monotonic()-started>=max_seconds:raise TimeoutError('probe deadline')
                value=request(port,'/object_info/'+name)
                if name not in value:raise ValueError('node missing '+name)
                schemas[name]=value[name];write_once(root/'schemas'/(name+'.json'),value)
            proof=capabilities(schemas,origin='verified_current_worker_http',epoch=epoch,matrix=marker.get('schema_version')==2)
            proof['schemas']=schemas
            write_once(root/'current-http-capabilities.json',proof)
            result.update(passed=True,owned_listener_verified=True,schemas=len(schemas))
            if mode=='gpu':
                result.update(mode='gpu',graph_posts=None,checkpoint_payload_bytes=None)
                while process.poll() is None and time.monotonic()-started<max_seconds and not (root/'stop.request.json').exists():
                    rss=windows_memory([process.pid])['process_rss_bytes'][str(process.pid)]
                    result['peak_rss_observed_bytes']=max(result['peak_rss_observed_bytes'],rss)
                    if rss>24*1024**3:raise ValueError('GPU worker RSS stop threshold')
                    time.sleep(.25)
                result['timed_out']=process.poll() is None and time.monotonic()-started>=max_seconds
    except BaseException as exc:
        result['error']=repr(exc)
        result['passed']=False
    finally:
        if sampler:
            sampler.stop()
            if process.poll() is None:sampler.sample()
            if sampler.quota_failure:result.update(passed=False,error=sampler.quota_failure)
        if process is not None:result.update(stop_owned(process,root,epoch))
        if job is not None:job.close()
        bootstrap.close()
        if gpu_owner:gpu_owner.__exit__(None,None,None)
        with socket.socket() as check:
            result['port_closed']=check.connect_ex(('127.0.0.1',port))!=0
        result['seconds']=time.monotonic()-started
        result['passed']=controller_passed(result)
        write_once(root/'service-result.json',result)
    print(json.dumps(result));return 0 if result['passed'] else 1


def worker(root,port,mode,authorization=None):
    from video_ai.experiments.wan_wrapper_nodes import WorkerContext,register_nodes
    # Handshake: no Comfy/torch import before the controller assigns the Job.
    deadline=time.monotonic()+10
    while not (root/'controller-start.json').exists():
        if time.monotonic()>deadline:raise TimeoutError('owned Job handshake missing')
        time.sleep(.05)
    launch=read(root/'frozen/service-launch.json');owner=read(root/'service-owner.json')
    if owner['pid']!=os.getpid() or launch['mode']!=mode or owner['launch_sha256']!=digest(launch) or launch['epoch']!=owner['epoch']:
        raise ValueError('worker launch/owner identity differs')
    if Path(launch['source_root']).resolve()!=SOURCE:raise ValueError('running source root differs from launch')
    if Path(sys.executable).resolve()!=(ENVIRONMENT/'python_embeded/python.exe').resolve():raise ValueError('independent interpreter required')
    import importlib.metadata
    import re
    canonical=lambda name:re.sub(r'[-_.]+','-',name).lower()
    actual={canonical(d.metadata['Name']):d.version for d in importlib.metadata.distributions() if d.metadata.get('Name')}
    expected={canonical(k):v for k,v in read(ENVIRONMENT/'install.json')['versions'].items()}
    if actual!=expected:raise ValueError('installed dependency identities differ')
    wrapper=verify_environment()
    auth=read(authorization) if authorization else None
    if (digest(auth) if auth else None)!=launch['authorization_sha256']:raise ValueError('authorization identity differs')
    context=WorkerContext(root,mode=mode,epoch=owner['epoch'],authorization=auth)
    for p in context.profiles.values():
        if Path(p.identity_dict()['common']['source']['root']).resolve()!=SOURCE:raise ValueError('profile source root differs from running code')
    if mode=='gpu':context.require_gpu()
    for group in ('source','runtime','tool'):
        for item in context.profiles['control'].identity_dict()['common'][group]['artifacts']:Artifact(**item).verify()
    comfy=ENVIRONMENT/'ComfyUI'
    from video_ai.experiments.wan_wrapper_runtime_support import SoftwareVerifier,SOFTWARE_SHA256
    inventory=SOURCE/'docs/task-designs/LVA-07-04-software.json'
    if hashlib.sha256(inventory.read_bytes()).hexdigest()!=SOFTWARE_SHA256:raise ValueError('software inventory identity differs')
    rows=read(inventory)['files']
    rows+=[dict(path=str((wrapper/r['path']).resolve()),bytes=r['bytes'],sha256=r['sha256']) for r in read(ENVIRONMENT/'sources.json')['wrapper_files']]
    rows+=context.profiles['control'].identity_dict()['common']['source']['artifacts']
    verifier=SoftwareVerifier(rows,[comfy,ENVIRONMENT/'python_embeded',SOURCE/'src'])
    for row in rows:
        path=Path(row['path'])
        if (row.get('group')=='runtime' and path.suffix.lower() in ('.exe','.dll','.pyd','.zip','.pth')) or (row.get('group')=='comfy' and path.suffix=='.py'):
            verifier.verify(path)
    verifier.verify(wrapper/'__init__.py')
    verifier.verify(comfy/'main.py');verifier.install()
    sys.argv=[str(comfy/'main.py'),*(['--cpu'] if mode=='cpu' else []),'--listen','127.0.0.1','--port',str(port),'--disable-auto-launch','--offline',
        '--disable-all-custom-nodes','--whitelist-custom-nodes',wrapper.name,'--disable-assets','--cache-none',
        '--models-directory',str(MODEL_ROOT),'--database-url','sqlite:///'+(root/'user/comfyui.db').as_posix()]
    for name in ('input','output','temp','user'):sys.argv+=['--'+name+'-directory',str(root/name)]
    sys.path.insert(0,str(comfy));os.chdir(comfy)
    original_import=builtins.__import__;installed=[]
    def observed_import(name,globals=None,locals=None,fromlist=(),level=0):
        imported=original_import(name,globals,locals,fromlist,level)
        if name=='nodes' and not installed:
            nodes=sys.modules.get('nodes')
            if nodes is not None and hasattr(nodes,'init_extra_nodes'):
                original=nodes.init_extra_nodes;installed.append((nodes,original))
                async def initialize(*a,**kw):
                    result=await original(*a,**kw)
                    roots=[m for m in sys.modules.values() if getattr(m,'__file__',None) and Path(m.__file__).resolve()==(wrapper/'nodes_model_loading.py').resolve()]
                    if len(roots)!=1:raise ValueError('unique fixed Wrapper module root required')
                    import folder_paths
                    categories={'base_high':'diffusion_models','base_low':'diffusion_models','t5':'text_encoders','vae':'vae','lora_high':'loras','lora_low':'loras'}
                    for role,item in context.models.items():
                        actual_path=folder_paths.get_full_path(categories[role],Path(item['path']).name)
                        if actual_path is None or Path(actual_path).resolve()!=Path(item['path']).resolve():raise ValueError('actual model search path differs: '+role)
                    if mode=='gpu':
                        from video_ai.experiments.wan_wrapper_lora import PinnedExpertFactory
                        prefix=roots[0].__package__
                        context.factory=PinnedExpertFactory(context,roots[0],
                            importlib.import_module(prefix+'.custom_linear'),importlib.import_module(prefix+'.lva07_mixed_delta'),
                            importlib.import_module(prefix+'.lva07_applicability'),importlib.import_module('comfy.lora'),
                            importlib.import_module(prefix+'.utils'))
                        context.preflight_resources()
                    register_nodes(nodes.NODE_CLASS_MAPPINGS,context)
                    from server import PromptServer
                    from aiohttp import web
                    server=PromptServer.instance
                    @web.middleware
                    async def guard(request,handler):
                        try:
                            context.allow_request(request.method,request.path)
                            if request.method=='POST' and request.path in ('/prompt','/api/prompt'):
                                body=await request.json();claim=context.claim_prompt(body)
                        except ValueError as exc:return web.json_response({'error':str(exc)},status=403)
                        response=await handler(request)
                        if request.method=='POST' and request.path in ('/prompt','/api/prompt') and response.status==200:
                            from video_ai.experiments.wan_wrapper_backend import canonical_uuid
                            accepted=json.loads(response.body)
                            pid=canonical_uuid(accepted.get('prompt_id'))
                            if accepted.get('node_errors')!={}:raise ValueError('worker acceptance contains errors')
                            trial=claim['trial_id'] if context.is_matrix else claim['mode']+'_1'
                            write_once(root/'worker-submissions'/(trial+'-accepted.json'),dict(**claim,prompt_id=pid))
                        return response
                    server.app.middlewares.append(guard)
                    @server.routes.post('/lva07/prepare-text')
                    async def prepare_text(request):
                        try:
                            body=await request.json()
                            if set(body)!={'probe_id','profile_sha256'} or body['profile_sha256']!=context.profiles['control'].digest():raise ValueError('text request identity')
                            return web.json_response(await asyncio.to_thread(context.prepare_text,body['probe_id']))
                        except ValueError as exc:return web.json_response({'error':str(exc)},status=409)
                    @server.routes.get('/lva07/text/{probe_id}')
                    async def text_status(request):
                        probe_id=request.match_info['probe_id'];intent=root/'text/intent.json'
                        if not intent.exists() or read(intent).get('probe_id')!=probe_id:return web.json_response({'status':'unknown'})
                        for file in ('accepted.json','failed.json'):
                            if (root/'text'/file).exists():return web.json_response(read(root/'text'/file))
                        return web.json_response({'status':'unknown','probe_id':probe_id})
                    @server.routes.post('/lva07/admit-pair')
                    async def admission(request):
                        try:
                            body=await request.json()
                            if set(body)!={'admission_id','profile_sha256'} or body['profile_sha256']!=context.profiles['fast'].digest():raise ValueError('admission request identity')
                            result=await asyncio.to_thread(context.admit,body['admission_id'])
                            return web.json_response(result)
                        except ValueError as exc:return web.json_response({'error':str(exc)},status=409)
                    @server.routes.get('/lva07/admission/{admission_id}')
                    async def status(request):
                        original_id=request.match_info['admission_id']
                        intent=root/'admission/intent.json'
                        if not intent.exists() or read(intent).get('admission_id')!=original_id:return web.json_response({'status':'unknown'})
                        for file in ('accepted.json','failed.json'):
                            if (root/'admission'/file).exists():return web.json_response(read(root/'admission'/file))
                        return web.json_response({'status':'unknown','admission_id':original_id})
                    write_once(root/'worker-attestation.json',dict(pid=os.getpid(),epoch=owner['epoch'],mode=mode,gpu_authorized=mode=='gpu',
                        profiles=launch['profiles'],comparison_sha256=launch['comparison_sha256'],wrapper_root=str(wrapper),
                        source_root=str(SOURCE),origin='registered_in_current_worker; HTTP observed separately'))
                    return result
                nodes.init_extra_nodes=initialize
        return imported
    builtins.__import__=observed_import
    stop=threading.Event()
    def watcher():
        while not stop.wait(.25):
            path=root/'stop.request.json'
            if path.exists() and read(path)==dict(pid=os.getpid(),epoch=owner['epoch']):
                # Main's event loop has no portable cooperative shutdown API.
                # Interrupt first; the controller records a bounded forced stop if needed.
                import _thread
                _thread.interrupt_main();return
    thread=threading.Thread(target=watcher,daemon=True);thread.start()
    try:runpy.run_path(str(comfy/'main.py'),run_name='__main__')
    finally:
        stop.set();thread.join(timeout=1);builtins.__import__=original_import
        for nodes,original in installed:nodes.init_extra_nodes=original
        if context.leases:context.leases.close()
        verifier.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8297);parser.add_argument('--max-seconds',type=int,default=180)
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS);parser.add_argument('--mode',choices=['cpu','gpu'],default='cpu')
    parser.add_argument('--authorization',type=Path)
    args=parser.parse_args(argv)
    if args.worker:return worker(args.root.resolve(),args.port,args.mode,args.authorization)
    if args.mode=='gpu' and not args.authorization:parser.error('GPU requires a separate approved LVA-07-05 authorization file')
    return controller(args.root,port=args.port,max_seconds=args.max_seconds,mode=args.mode,authorization=args.authorization)


if __name__=='__main__':raise SystemExit(main())
