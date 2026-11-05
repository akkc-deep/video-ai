"""Owned native subprocess supervision, without an inference wall-clock limit."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4

from ..adapters.common import strict_json
from ..planning.production_scenes import canonical_digest
from .environment import build_child_env
from .manifest import now
from .processes import stop_process, validate_command
from .production_state import ProductionRefused, process_started_at
from .resources import GpuLease, find_nvidia_smi
from .scene_clip_observations import _time
from .temporal_scene_admission import _refused

GIB = 1024**3
STARTUP = dict(physical=8*GIB, commit=10*GIB, gpu=18*GIB, disk=32*GIB)
RUNNING = dict(physical=2*GIB, commit=4*GIB, gpu=GIB, disk=32*GIB)


def resource_snapshot(root):
    class Memory(ctypes.Structure):
        _fields_ = [('length', wintypes.DWORD), ('load', wintypes.DWORD)] + [(key, ctypes.c_ulonglong) for key in
            ('total_physical', 'available_physical', 'total_pagefile', 'available_pagefile',
             'total_virtual', 'available_virtual', 'available_extended_virtual')]
    data = Memory(); data.length = ctypes.sizeof(data)
    memory = ctypes.WinDLL('kernel32', use_last_error=True).GlobalMemoryStatusEx
    memory.argtypes = [ctypes.POINTER(Memory)]; memory.restype = wintypes.BOOL
    if not memory(ctypes.byref(data)): raise ctypes.WinError(ctypes.get_last_error())
    smi = find_nvidia_smi()
    if smi is None: raise ProductionRefused('native GPU free-capacity query unavailable')
    result = subprocess.run([str(smi), '--query-gpu=memory.free', '--format=csv,noheader,nounits'],
        stdin=subprocess.DEVNULL, capture_output=True, timeout=5,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode: raise ProductionRefused('native GPU free-capacity query failed')
    lines = result.stdout.decode('utf-8').strip().splitlines()
    if len(lines) != 1: raise ProductionRefused('one native GPU required')
    return dict(physical=data.available_physical, commit=data.available_pagefile,
                gpu=int(lines[0].strip())*1024**2, disk=shutil.disk_usage(root).free)


def _reserve(sample, limits):
    if not isinstance(sample, dict) or set(sample) != set(limits):
        raise ProductionRefused('native resource sample fields differ')
    for key, minimum in limits.items():
        if type(sample[key]) is not int or sample[key] < 0: raise ProductionRefused('native resource sample is unverified')
        if sample[key] < minimum: return key+'_reserve'
    return None


def _gpu_owned(store):
    store.assert_owned()
    lease = getattr(store, 'gpu_lease', None)
    if (type(lease) is not GpuLease or lease._token is None or lease.paths != store.paths
            or lease.manifest.run_dir != store.run_dir):
        raise ProductionRefused('native worker requires actual held GPU lease')
    expected = store.paths.policy.validate_write(store.paths.cache_root/'locks/gpu.lock', 'cache')
    if lease.lock_path != expected: raise ProductionRefused('native GPU lock path differs')
    owner = strict_json(expected.read_bytes())
    if owner.get('token') != lease._token or owner.get('run_id') != store.run_dir.name or owner.get('pid') != os.getpid():
        raise ProductionRefused('native worker lost actual GPU ownership')
    return dict(path=str(expected), token=lease._token)


def _start(store, path, identity):
    previous = store.read(path)
    if previous is not None:
        if {key: previous.get(key) for key in identity} != identity:
            raise ProductionRefused('native original start identity differs')
        if _time(previous['started_at'], 'native original start') > _time(now(), 'now'):
            raise ProductionRefused('native original start is in the future')
        return store.artifact(path)
    store.write(path, dict(identity, started_at=now()))
    return store.artifact(path)


def _committed(store, folder, digest):
    sample = store.read(folder/'sample-complete.json')
    if sample is not None:
        if sample.get('request_sha256') != digest or sample.get('native_diffusion_completed') is not True:
            raise ProductionRefused('native committed sample request differs')
    result = store.read(folder/'native-result.json')
    if result is not None:
        if result.get('request_sha256') != digest or sample is None or store.read(folder/'intent.json') is None:
            raise ProductionRefused('native result lacks original matching sample/intent')
        return 'completed'
    return 'sampled_decode_pending' if sample is not None else None


def _observed_owner(store, folder, digest, workflow_sha):
    owner = store.read(folder/'owner.json')
    if owner is None: return None
    if owner.get('request_sha256') != digest or owner.get('workflow_sha256') != workflow_sha:
        raise ProductionRefused('native original owner request differs')
    terminal = store.read(folder/'process-terminal.json')
    if terminal is not None:
        if terminal.get('request_sha256') != digest or terminal.get('token') != owner.get('token'):
            raise ProductionRefused('native process terminal owner differs')
        return 'stopped'
    current = process_started_at(owner['pid'])
    if current is None: return 'stopped'
    return 'running' if current == owner.get('process_started_at') else 'unknown'


def _revision_launch_state(store, folder, request, workflow_sha, operation):
    """Observe the durable supervisor journal without acquiring process control."""
    digest=canonical_digest(request)
    launch=store.read(folder/'launch-intent.json')
    owner=store.read(folder/'owner.json')
    terminal=store.read(folder/'process-terminal.json')
    if launch is None:
        if owner is not None or terminal is not None:
            raise ProductionRefused('native revision journal lacks original launch')
        return None
    if (launch.get('request_sha256')!=digest or launch.get('workflow_sha256')!=workflow_sha
            or launch.get('operation')!=operation or launch.get('automatic_retry') is not False):
        raise ProductionRefused('native revision launch identity differs')
    if owner is not None and any(owner.get(key)!=launch.get(key) for key in
            ('request_sha256','workflow_sha256','token','operation')):
        raise ProductionRefused('native revision owner differs from launch')
    if terminal is not None:
        if owner is None or any(terminal.get(key)!=launch.get(key) for key in
                ('request_sha256','workflow_sha256','token','operation')):
            raise ProductionRefused('native revision terminal differs from launch/owner')
        if terminal.get('worker_pid')!=owner.get('pid') or type(terminal.get('worker_exit_code')) is not int:
            raise ProductionRefused('native revision terminal process differs')
        return 'failed' if terminal['worker_exit_code']!=0 else 'unknown'
    if (owner is not None and owner.get('process_started_at') is not None
            and process_started_at(owner['pid'])==owner['process_started_at']):
        return 'running'
    return 'unknown'


@_refused
def native_revision_effects(context, records):
    """Include launches durable before worker intent, including separate encoders."""
    from . import temporal_native_worker as worker
    store=context['store'];effects=[];requests={}
    for row in context['rows']:
        cid=row['budget']['clip_id'];folder=store.clip_dir(cid)
        request=store.read(folder/'request.json')
        if request is None:
            if any((folder/name).exists() for name in ('launch-intent.json','owner.json','process-terminal.json','intent.json')):
                raise ProductionRefused('native revision journal lacks frozen request')
            continue
        workflow=store.read(folder/'workflow.json')
        if workflow is None or canonical_digest(workflow)!=request.get('workflow_sha256'):
            raise ProductionRefused('native revision workflow differs')
        requests[cid]=request
        state=_revision_launch_state(store,folder,request,canonical_digest(workflow),'one-window')
        committed=_committed(store,folder,canonical_digest(request))
        if committed=='completed' or records.get(cid) is not None:continue
        # A failed sampler with a committed latent still owns decode recovery.
        if state=='failed' and committed is None:continue
        intent=store.read(folder/'intent.json')
        if state is not None or intent is not None or committed is not None:
            launch=store.read(folder/'launch-intent.json')
            effects.append(dict(node='clips:'+cid,intent_sha256=canonical_digest(launch or intent),
                status='running' if state=='running' else 'unknown'))
    for folder in sorted(store.path('text-context').glob('*')):
        if not folder.is_dir() or not (folder/'launch-intent.json').exists():continue
        request=store.read(folder/'request.json')
        if request is None or request.get('text_cache_key')!=folder.name:
            raise ProductionRefused('native revision cache request differs')
        matching=[(cid,value) for cid,value in requests.items() if value['text_cache_key']==folder.name]
        if not matching:raise ProductionRefused('native revision cache launch lacks frozen video request')
        launch=store.read(folder/'launch-intent.json')
        workflow_sha=launch.get('workflow_sha256')
        if workflow_sha not in {value['workflow_sha256'] for _,value in matching}:
            raise ProductionRefused('native revision cache workflow lacks matching video request')
        state=_revision_launch_state(store,folder,request,workflow_sha,'prepare-cache')
        if (worker.TEXT_CACHE_ROOT/folder.name/'binding.json').is_file():
            try:
                worker.existing_native_text_context(request,cache_root=worker.TEXT_CACHE_ROOT)
                continue
            except worker.MissingNativeTextCache:pass
        if state=='failed':continue
        launch=store.read(folder/'launch-intent.json')
        effects.extend(dict(node='clips:'+cid,intent_sha256=canonical_digest(launch),status=state)
            for cid,_ in matching)
    return effects


@_refused
def recover_or_prepare_native_cache(store,request,workflow,*,worker_factory=None,resource_sampler=None,sleeper=time.sleep):
    """A new prompt encodes in its own owned job, before any video launch intent."""
    from .temporal_native_worker import existing_native_text_context,MissingNativeTextCache
    store.assert_owned()
    try:return dict(status='prepared',new_worker_started=False,**existing_native_text_context(request))
    except MissingNativeTextCache:pass
    folder=store.path('text-context')/request['text_cache_key']
    if (folder/'launch-intent.json').exists():return dict(status='unknown',new_worker_started=False)
    window=store.clip_dir(request['clip_id'])
    if store.read(window/'request.json')!=request or store.read(window/'workflow.json')!=workflow:
        raise ProductionRefused('native cache requires frozen video request/workflow')
    if canonical_digest(workflow)!=request['workflow_sha256']:raise ProductionRefused('native cache workflow differs')
    gpu_owner=_gpu_owned(store)
    sampler=resource_sampler or (lambda:resource_snapshot(store.run_dir))
    if _reserve(sampler(),STARTUP):raise ProductionRefused('native cache startup reserve below required free capacity')
    policy=dict(time_limit_seconds=None,max_gpu_allocated_bytes=None)
    _start(store,store.path('native-start.json'),dict(schema_version=1,algorithm='temporal_native_start_v1',
        run_id=store.run_dir.name,inputs_sha256=request['inputs_sha256'],execution_budget=request['execution_budget'],**policy))
    cache_request=dict(schema_version=1,algorithm='temporal_native_text_request_v1',
        **{key:workflow[key] for key in ('runtime_bundle','model_manifest','native_python','production_worker','package_versions')},
        parameters={key:request['parameters'][key] for key in ('positive','negative')},
        text_identity=request['text_identity'],text_cache_key=request['text_cache_key'])
    store.write(folder/'request.json',cache_request)
    token=uuid4().hex;digest=canonical_digest(cache_request);workflow_sha=canonical_digest(workflow)
    command=[workflow['native_python']['path'],'-B',workflow['production_worker']['path'],'--operation','prepare-cache',
        '--request',str(folder/'request.json'),'--output',str(folder),'--owner-file',str(folder/'owner.json'),'--owner-token',token]
    env=build_child_env(store.paths)
    env.update(PYTORCH_CUDA_ALLOC_CONF='backend:cudaMallocAsync',PYTORCH_ALLOC_CONF='backend:cudaMallocAsync',PYTHONUNBUFFERED='1')
    command,cwd=validate_command(command,folder,env)
    store.write(folder/'launch-intent.json',dict(schema_version=1,request_sha256=digest,workflow_sha256=workflow_sha,
        token=token,operation='prepare-cache',command=list(command),gpu_owner=gpu_owner,automatic_retry=False,started_at=now(),**policy))
    process=None;exit_code=None;reason=None;snapshot=None
    try:
        with (folder/'worker.stdout.log').open('xb') as stdout,(folder/'worker.stderr.log').open('xb') as stderr:
            process=(worker_factory or subprocess.Popen)(command,cwd=cwd,env=env,stdout=stdout,stderr=stderr,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            store.write(folder/'owner.json',dict(schema_version=1,request_sha256=digest,workflow_sha256=workflow_sha,
                pid=process.pid,process_started_at=process_started_at(process.pid),token=token,operation='prepare-cache'))
            while process.poll() is None:
                store.assert_owned();sample=sampler();stop=_reserve(sample,RUNNING)
                if stop:
                    reason,snapshot=stop,dict(sample);exit_code=stop_process(process);break
                sleeper(2)
            if exit_code is None:exit_code=process.wait(timeout=None)
    except BaseException:
        if process is not None:reason=reason or 'supervisor_exception';exit_code=stop_process(process)
        raise
    finally:
        if process is not None:
            store.write(folder/'process-terminal.json',dict(schema_version=1,request_sha256=digest,workflow_sha256=workflow_sha,
                token=token,operation='prepare-cache',worker_pid=process.pid,worker_exit_code=exit_code,stop_reason=reason,
                stop_snapshot=snapshot,stop_thresholds=RUNNING,finished_at=now(),**policy))
    try:return dict(status='prepared',new_worker_started=True,**existing_native_text_context(request))
    except MissingNativeTextCache:return dict(status='failed' if exit_code else 'unknown',new_worker_started=True)


@_refused
def recover_or_start_native_window(store, request, workflow, *, worker_factory=None,
                                   resource_sampler=None, sleeper=time.sleep) -> dict:
    """Observe existing jobs; start at most one sample or a committed-latent decode.

    Only a newly created live Popen object may be stopped. Recovered PID records
    support read-only observation; they never become process-control handles.
    The caller validates complete technical media separately before acceptance.
    """
    store.assert_owned()
    folder = store.clip_dir(request['clip_id'])
    digest, workflow_sha = canonical_digest(request), canonical_digest(workflow)
    if request.get('workflow_sha256') != workflow_sha: raise ProductionRefused('native workflow request differs')
    if store.read(folder/'request.json') != request or store.read(folder/'workflow.json') != workflow:
        raise ProductionRefused('native process requires exact frozen request/workflow')
    committed = _committed(store, folder, digest)
    if committed == 'completed': return dict(status='completed', new_worker_started=False)
    owner_state = _observed_owner(store, folder, digest, workflow_sha)
    if owner_state in ('running', 'unknown'): return dict(status=owner_state, new_worker_started=False)
    if committed is None and any((folder/name).exists() for name in ('intent.json', 'launch-intent.json', 'process-terminal.json')):
        return dict(status='failed' if (folder/'process-terminal.json').exists() else 'unknown', new_worker_started=False)
    operation = 'decode-only' if committed == 'sampled_decode_pending' else 'one-window'
    # An unknown earlier decoder may still own files/GPU. Do not launch alongside it.
    for launch in folder.glob('decode-launch-*.json'):
        decode = store.read(launch)
        token = decode['token']
        decoded_owner = store.read(folder/f'decode-owner-{token}.json')
        terminal = store.read(folder/f'decode-terminal-{token}.json')
        if decoded_owner is None and terminal is None: return dict(status='unknown', new_worker_started=False)
        if terminal is None and process_started_at(decoded_owner['pid']) is not None:
            return dict(status='running', new_worker_started=False)
    gpu_owner = _gpu_owned(store)
    sampler = resource_sampler or (lambda: resource_snapshot(store.run_dir))
    initial = sampler()
    shortage = _reserve(initial, STARTUP)
    if shortage: raise ProductionRefused('native startup '+shortage)
    policy = dict(time_limit_seconds=None, max_gpu_allocated_bytes=None)
    case_start = _start(store, store.path('native-start.json'), dict(schema_version=1, algorithm='temporal_native_start_v1',
        run_id=store.run_dir.name, inputs_sha256=request['inputs_sha256'], execution_budget=request['execution_budget'], **policy))
    _start(store, folder/'window-start.json', dict(schema_version=1, algorithm='temporal_native_window_start_v1',
        request_sha256=digest, workflow_sha256=workflow_sha, case_start=case_start, **policy))
    token = uuid4().hex
    launch_path = folder/'launch-intent.json' if operation == 'one-window' else folder/f'decode-launch-{token}.json'
    owner_path = folder/'owner.json' if operation == 'one-window' else folder/f'decode-owner-{token}.json'
    terminal_path = folder/'process-terminal.json' if operation == 'one-window' else folder/f'decode-terminal-{token}.json'
    command = [workflow['native_python']['path'], '-B', workflow['production_worker']['path'], '--operation', operation,
        '--request', str(folder/'request.json'), '--output', str(folder), '--owner-file', str(owner_path), '--owner-token', token]
    env = build_child_env(store.paths)
    env.update(PYTORCH_CUDA_ALLOC_CONF='backend:cudaMallocAsync', PYTORCH_ALLOC_CONF='backend:cudaMallocAsync', PYTHONUNBUFFERED='1')
    command, cwd = validate_command(command, folder, env)
    store.write(launch_path, dict(schema_version=1, request_sha256=digest, workflow_sha256=workflow_sha,
        token=token, operation=operation, command=list(command), gpu_owner=gpu_owner, parent_pid=os.getpid(),
        parent_process_started_at=process_started_at(os.getpid()), started_at=now(), automatic_retry=False, **policy))
    stdout_path, stderr_path = folder/f'worker-{token}.stdout.log', folder/f'worker-{token}.stderr.log'
    process = None; stop_reason = None; stop_snapshot = None; exit_code = None
    try:
        with stdout_path.open('xb') as stdout, stderr_path.open('xb') as stderr:
            store.assert_owned()
            process = (worker_factory or subprocess.Popen)(command, cwd=cwd, env=env, stdout=stdout, stderr=stderr,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            started = process_started_at(process.pid)
            store.write(owner_path, dict(schema_version=1, request_sha256=digest, workflow_sha256=workflow_sha,
                pid=process.pid, process_started_at=started, token=token, operation=operation,
                command=list(command), stdout_path=str(stdout_path), stderr_path=str(stderr_path)))
            while process.poll() is None:
                store.assert_owned()
                sample = sampler()
                reason = _reserve(sample, RUNNING)
                if reason:
                    stop_reason, stop_snapshot = reason, dict(sample)
                    exit_code = stop_process(process)
                    break
                sleeper(2)
            if exit_code is None: exit_code = process.wait(timeout=None)
    except BaseException:
        if process is not None:
            stop_reason = stop_reason or 'supervisor_exception'
            exit_code = stop_process(process)
        raise
    finally:
        if process is not None:
            store.write(terminal_path, dict(schema_version=1, request_sha256=digest, workflow_sha256=workflow_sha,
                token=token, operation=operation, worker_pid=process.pid, worker_exit_code=exit_code,
                stop_reason=stop_reason, stop_snapshot=stop_snapshot, stop_thresholds=RUNNING,
                finished_at=now(), stdout_path=str(stdout_path), stderr_path=str(stderr_path), **policy))
    state = _committed(store, folder, digest)
    return dict(status=state or ('failed' if exit_code else 'unknown'), worker_exit_code=exit_code,
                new_worker_started=True, operation=operation, stop_reason=stop_reason)
