"""Own one service, send at most one job, and recover only its original identity."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
from threading import Event, Thread
import time
from uuid import UUID, uuid4

from ..adapters.common import AdapterError, FailureKind, HttpClient
from ..runtime.resources import windows_memory, find_nvidia_smi
from .whole_scene_case import (Evidence, identity, now, read_json, verify_case,
                              verify_identity, write_json)


@contextmanager
def case_lock(root):
    path = Path(root)/'execution.lock'
    # A crashed owner's lock is deliberately not stolen automatically.
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(dict(pid=os.getpid(), created_at=now())))
        stream.flush(); os.fsync(stream.fileno())
    try: yield
    finally: path.unlink()


@contextmanager
def gpu_slot(path,root):
    path=Path(path);path.parent.mkdir(exist_ok=True,parents=True)
    owner=dict(token=uuid4().hex,pid=os.getpid(),experiment=str(root),created_at=now())
    write_json(path,owner)
    try: yield
    finally:
        if read_json(path)!=owner: raise RuntimeError('GPU lease ownership changed')
        path.unlink()


def _matching_prompt(prompt, intent, graph, pid=None):
    return (isinstance(prompt, list) and len(prompt) >= 4
        and (pid is None or prompt[1] == pid) and prompt[2] == graph
        and isinstance(prompt[3], dict) and prompt[3].get('client_id') == intent['client_id'])


def submit_or_recover(root, http, *, poll_seconds=2, before_post=None,service_alive=None):
    with case_lock(root):
        verify_case(root)
        return _submit_or_recover(Path(root), http, poll_seconds=poll_seconds,before_post=before_post,service_alive=service_alive)


def _submit_or_recover(root, http, *, poll_seconds=2, before_post=None,service_alive=None):
    case = read_json(root/'case.json'); graph = read_json(root/'graph.json')
    case_sha = identity(root/'case.json')['sha256']; graph_sha = identity(root/'graph.json')['sha256']
    intent_path = root/'intent.json'
    if intent_path.exists():
        intent = read_json(intent_path)
        if intent['case_sha256'] != case_sha or intent['graph_sha256'] != graph_sha:
            raise ValueError('original intent identity changed')
    else:
        if before_post is not None: before_post()
        intent = dict(case_sha256=case_sha, graph_sha256=graph_sha, client_id=str(uuid4()),
                      created_at=now(), deadline_unix=time.time()+case['runtime']['wan_seconds'])
        write_json(intent_path, intent)
        try:
            response = http.request('POST', '/prompt', json_body=dict(prompt=graph, client_id=intent['client_id']),
                                    timeout=min(600, max(.001, intent['deadline_unix']-time.time())))
            value = http.parse_json(response, method='POST')
            pid = value.get('prompt_id')
            if (not isinstance(pid, str) or str(UUID(pid)) != pid
                    or not isinstance(value.get('node_errors'), dict) or value['node_errors']):
                raise ValueError('invalid original acceptance')
            write_json(root/'acceptance.json', dict(prompt_id=pid, response=value, received_at=now()))
        except Exception as exc:
            Evidence(root).exception(None, None, exc)
            if isinstance(exc, AdapterError) and exc.kind == FailureKind.explicit:
                return _terminal(root, 'failed', None, reason='explicit HTTP rejection')
            # An exception after durable intent can never authorize another POST.
    if (root/'submission-result.json').exists():
        return read_json(root/'submission-result.json')
    known = read_json(root/'acceptance.json')['prompt_id'] if (root/'acceptance.json').exists() else None
    while time.time() < intent['deadline_unix']:
        if service_alive is not None: service_alive()
        remaining = intent['deadline_unix']-time.time()
        try:
            queue = http.get_json('/queue', timeout=min(10, remaining))
            history = http.get_json('/history'+('/'+known if known else ''), timeout=min(10, max(.001,intent['deadline_unix']-time.time())))
        except AdapterError as exc:
            Evidence(root).exception(None, None, exc)
            time.sleep(min(poll_seconds, max(0, intent['deadline_unix']-time.time())))
            continue
        if not isinstance(queue, dict) or not isinstance(history, dict):
            raise ValueError('invalid original queue/history')
        queues = queue.get('queue_running', [])+queue.get('queue_pending', [])
        candidates = {str(p[1]) for p in queues if _matching_prompt(p, intent, graph)}
        candidates.update(pid for pid, entry in history.items()
                          if isinstance(entry, dict) and _matching_prompt(entry.get('prompt'), intent, graph, pid))
        if known:
            for p in queues:
                if isinstance(p, list) and len(p) > 1 and p[1] == known and not _matching_prompt(p,intent,graph,known):
                    raise ValueError('original queue identity conflict')
            if known in history and not _matching_prompt(history[known].get('prompt'), intent, graph, known):
                raise ValueError('original history identity conflict')
        if len(candidates) > 1 or known and candidates and candidates != {known}:
            raise ValueError('multiple original task identity conflict')
        if not known and candidates:
            known = candidates.pop()
            write_json(root/'acceptance.json', dict(prompt_id=known, recovered_at=now(), response=None))
        if known and known in history:
            entry = history[known]; status = entry.get('status', {})
            if status.get('status_str') == 'error' or any(isinstance(m,list) and m and m[0]=='execution_error' for m in status.get('messages', [])):
                return _terminal(root, 'failed', known, history=entry, reason='original execution failed')
            if status.get('completed') is True and status.get('status_str') == 'success':
                outputs = entry.get('outputs', {}).get('108', {}).get('images')
                if not isinstance(outputs, list) or len(outputs) != 1:
                    return _terminal(root, 'failed', known, history=entry, reason='invalid mapped output')
                return _terminal(root, 'completed', known, output=outputs[0], history=entry)
        time.sleep(min(poll_seconds, max(0, intent['deadline_unix']-time.time())))
    # Keep the deadline receipt without falsely turning an unknown remote job into a failure.
    value = dict(status='unknown', prompt_id=known, reason='original absolute deadline expired', recorded_at=now())
    write_json(root/'tracking'/f'{uuid4().hex}.json', value)
    return value


def _terminal(root, status, pid, **details):
    value = dict(status=status, prompt_id=pid, recorded_at=now(), **details)
    write_json(root/'submission-result.json', value)
    return value


def resource_sample(root, pid=None):
    result = dict(recorded_at=now(), pid=pid, verified=False)
    try:
        smi = find_nvidia_smi()
        if smi is None: raise OSError('nvidia-smi unavailable')
        records = []
        for query in ('--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu', '--query-compute-apps=pid,used_gpu_memory'):
            p = subprocess.run([str(smi),query,'--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5)
            records.append(dict(args=[str(smi),query], returncode=p.returncode, stdout=p.stdout, stderr=p.stderr))
        result['gpu'] = records
        result['memory'] = windows_memory({pid} if pid else set())
        result['verified'] = all(r['returncode'] == 0 for r in records)
    except Exception as exc: result['error'] = str(exc)
    write_json(Path(root)/'resources'/f'{uuid4().hex}.json', result)
    return result


def validate_gpu_processes(processes):
    # WDDM reports desktop graphics contexts as compute-apps with N/A memory.
    # They are not model inference jobs, and must never be terminated here.
    desktop={'dwm','shellhost','crossdeviceresume','nvidia overlay','phoneexperiencehost',
        'ledkeeper2','awesun','cef_server','pycharm64','explorer','searchhost',
        'shellexperiencehost','startmenuexperiencehost','msedgewebview2','textinputhost',
        'qqlive','applicationframehost','systemsettings','m365copilot','browser','pixpin',
        'chrome','msedge','firefox','codex','chatgpt','code'}
    if any(p['ProcessName'].lower() not in desktop for p in processes):
        raise RuntimeError('external or unidentified GPU workload; no trial started')
    return sorted(p['Id'] for p in processes)


def _resource_guard(sample,root):
    if not sample['verified']: raise RuntimeError('resource availability unverified')
    rows = [r.strip() for r in sample['gpu'][1]['stdout'].splitlines() if r.strip()]
    if rows:
        pids=[int(r.split(',')[0]) for r in rows]
        script='Get-Process -Id '+','.join(str(pid) for pid in pids)+' -ErrorAction Stop | Select-Object Id,ProcessName | ConvertTo-Json -Compress'
        result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',script],
                              capture_output=True,text=True,timeout=10)
        if result.returncode: raise RuntimeError('GPU process identity unverified')
        processes=json.loads(result.stdout)
        if isinstance(processes,dict): processes=[processes]
        if {p['Id'] for p in processes}!=set(pids): raise RuntimeError('GPU PID identity incomplete')
        write_json(Path(root)/'desktop-gpu-contexts.json',dict(processes=processes,
            classification='Known desktop WDDM graphics contexts, not inference ownership',
            preserved_pids=validate_gpu_processes(processes)))
    devices = sample['gpu'][0]['stdout'].strip().splitlines()
    if len(devices) != 1 or float(devices[0].split(',')[-2]) <= 0:
        raise RuntimeError('GPU availability unverified')


def _listener_owned(port, pid):
    p = subprocess.run(['netstat', '-ano', '-p', 'tcp'], capture_output=True, text=True, timeout=10)
    matches = [line.split() for line in p.stdout.splitlines()
               if 'LISTENING' in line and line.split()[1] == f'127.0.0.1:{port}']
    if p.returncode or len(matches) != 1 or matches[0][-1] != str(pid):
        raise RuntimeError('service listener ownership differs')


def execute_case(root):
    from ..runtime.paths import PathPolicy,CACHE_ROOT
    root = Path(root).resolve(strict=True); PathPolicy().validate_write(root, 'cache')
    with case_lock(root),gpu_slot(CACHE_ROOT/'locks/gpu.lock',root):
        case = verify_case(root)
        if (root/'result.json').exists(): return read_json(root/'result.json')
        if (root/'intent.json').exists():
            # Read durable local completion first, otherwise query the original URL only.
            if (root/'submission-result.json').exists(): return read_json(root/'submission-result.json')
            old = read_json(root/'service.json')
            return _submit_or_recover(root, HttpClient(old['url'],10,Evidence(root)))
        if (root/'service.json').exists():
            raise RuntimeError('previous service attempt retained; no automatic restart')
        prepared = read_json(root/'prepared.json')
        if prepared['case_sha256'] != identity(root/'case.json')['sha256']:
            raise ValueError('prepared case identity changed')
        for item in [prepared['start'],prepared['prompt'],*prepared['software']]: verify_identity(item)
        runtime = case['runtime']; tools = runtime['tools']; port = 8198
        _resource_guard(resource_sample(root),root)
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1',port))
        for name in ('input','output','temp','user'): (root/name).mkdir(exist_ok=True)
        args = [tools['comfy_python'],'-B','-s',str(Path(tools['comfy_root'])/'main.py'),
                '--listen','127.0.0.1','--port',str(port),'--models-directory',runtime['model_root']]
        for name in ('input','output','temp','user'): args += ['--'+name+'-directory',str(root/name)]
        # All required nodes are built-ins. Custom hooks must not alter search paths.
        args += ['--database-url','sqlite:///'+(root/'user/comfyui.db').as_posix(),'--disable-all-custom-nodes']
        stop = Event(); process = None; monitor = None; started = time.monotonic()
        value = dict(status='failed', technical='not_produced', resources='unverified',
                     sampled_appearance='unverified', full_video_observation='unverified',
                     production_eligible=False, cross_subject='not_authorized', started_at=now())
        with (root/'service.stdout').open('xb') as stdout, (root/'service.stderr').open('xb') as stderr:
            try:
                from ..runtime.production_inputs import load_frozen_inputs
                from ..runtime.paths import RuntimePaths
                from ..runtime.environment import build_child_env
                env=build_child_env(RuntimePaths.from_config(load_frozen_inputs(case['source_run']).config))
                process = subprocess.Popen(args, cwd=tools['comfy_root'], stdout=stdout, stderr=stderr,env=env,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                url = f'http://127.0.0.1:{port}'
                write_json(root/'service.json',dict(pid=process.pid,owned=True,url=url,args=args,started_at=now()))
                def sample_loop():
                    while not stop.is_set():
                        resource_sample(root,process.pid)
                        stop.wait(2)
                monitor=Thread(target=sample_loop,daemon=True); monitor.start()
                http = HttpClient(url,10,Evidence(root)); end = time.monotonic()+runtime['service_start_seconds']
                while True:
                    if process.poll() is not None: raise RuntimeError('owned service exited during startup')
                    if time.monotonic() >= end: raise TimeoutError('owned service startup deadline')
                    try:
                        health = http.get_json('/system_stats', timeout=min(2,end-time.monotonic()))
                        if not isinstance(health.get('system',{}).get('comfyui_version'),str): raise ValueError('wrong service')
                        break
                    except AdapterError: time.sleep(.5)
                _listener_owned(port,process.pid)
                from ..runtime.workflows import WorkflowTemplate
                from ..runtime.paths import SOURCE_ROOT
                template = WorkflowTemplate(read_json(root/'graph.json'), read_json(SOURCE_ROOT/'workflows/wan22_i2v_14b_api.mapping.json'))
                template.validate_remote(http.get_json('/object_info'))
                queue=http.get_json('/queue')
                if queue.get('queue_running') != [] or queue.get('queue_pending') != []:
                    raise RuntimeError('owned service has unexpected jobs')
                # All evidence and adapted bytes are checked immediately before the sole POST.
                verify_case(root); verify_identity(prepared['start']); verify_identity(prepared['prompt'])
                def before_post():
                    if process.poll() is not None: raise RuntimeError('owned service exited before POST')
                    _listener_owned(port,process.pid)
                    from .whole_scene_case import validate_model_loading
                    validate_model_loading({role:case['dependencies']['model/'+role]['path'] for role in
                        ('wan_high','wan_low','text_encoder','vae')},runtime['model_root'],tools['comfy_root'])
                def service_alive():
                    if process.poll() is not None: raise RuntimeError('owned process exited; original task result unknown, no re-POST')
                tracking = _submit_or_recover(root,http,before_post=before_post,service_alive=service_alive)
                value.update(status=tracking['status'], submission=tracking, resources='recorded')
                if tracking['status']=='completed':
                    from .whole_scene_media import audit_output
                    media = audit_output(root,tracking['output'])
                    value.update(status='awaiting_video_observation', technical='passed',media=media)
            except BaseException as exc:
                trace=Evidence(root).exception(None,None,exc)
                value.update(error=str(exc),traceback_path=str(trace))
                if (root/'intent.json').exists() and not (root/'submission-result.json').exists(): value['status']='unknown'
            finally:
                stop.set()
                if monitor: monitor.join(timeout=15)
                if process is not None and process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=20)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=20)
                value.update(elapsed_seconds=time.monotonic()-started,finished_at=now(),
                             owned_service_exit=process.returncode if process else None)
                # A failed inference still requires a complete source preservation check.
                try:
                    verify_case(root); value['source_unchanged']=True
                except Exception as exc:
                    value.update(source_unchanged=False,preservation_error=str(exc),production_eligible=False)
                samples=[read_json(p) for p in (root/'resources').glob('*.json')]
                value['resources']='recorded' if samples and all(s['verified'] for s in samples) else 'unverified'
                write_json(root/'result.json',value)
        return value
