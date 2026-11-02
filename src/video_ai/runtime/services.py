"""Fresh service identity probes and Popen ownership confined to this manager."""
from dataclasses import dataclass
from collections.abc import Mapping
from pathlib import Path
import socket
import subprocess
import time
from urllib.parse import urlsplit
from uuid import uuid4

from ..adapters.common import AdapterError, HttpClient, JSON_LIMIT, positive_timeout, validate_base_url
from .environment import build_child_env
from .manifest import now
from .processes import stop_process, validate_command
from .resources import gpu_guard


class ServiceConflictError(RuntimeError):
    pass


class ServiceStartError(RuntimeError):
    pass


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    url: str
    args: tuple[str,...]
    cwd: Path
    start_timeout: float
    env_overrides: Mapping[str,str] | None = None
    revision_run_dir: Path | None = None
    production_services: Mapping[str,str] | None = None


def service_environment(paths, spec):
    overrides = dict(spec.env_overrides or {})
    if spec.production_services is not None:
        urls=dict(spec.production_services)
        if set(urls)!={'ollama','tts','comfyui'} or spec.name not in urls or spec.url!=urls[spec.name]:
            raise ValueError('service URL differs from frozen production binding')
        for url in urls.values(): validate_base_url(url)
        expected={'OLLAMA_HOST':urlsplit(urls['ollama']).netloc} if spec.name=='ollama' else {}
        if overrides!=expected or spec.revision_run_dir is not None:
            raise ValueError('service environment differs from frozen production binding')
        env=build_child_env(paths)
        env.update(overrides)
        return env
    if overrides:
        baseline=(spec.name=='ollama' and set(overrides)=={'OLLAMA_HOST'}
            and overrides['OLLAMA_HOST']=='127.0.0.1:11435' and spec.url=='http://127.0.0.1:11435')
        if not baseline:
            if spec.name!='ollama' or set(overrides)!={'OLLAMA_HOST'} or spec.revision_run_dir is None:
                raise ValueError('only the dedicated or author-bound Ollama child binding is permitted')
            from ..config import load_config
            from .manifest import ManifestStore
            from .service_specs import build_service_specs
            snapshot=ManifestStore.open(spec.revision_run_dir).snapshot()
            config=load_config(Path(snapshot['config_snapshot']['path']))
            expected=build_service_specs(config,spec.revision_run_dir)['ollama']
            if expected!=spec:
                raise ValueError('Ollama environment differs from current author-bound service specification')
    env = build_child_env(paths)
    env.update(overrides)
    return env


@dataclass(frozen=True)
class ServiceHandle:
    name: str
    url: str
    owned: bool
    pid: int | None
    process: subprocess.Popen | None
    started_at: str | None


def port_listening(url, timeout):
    parts = urlsplit(url)
    try:
        with socket.create_connection((parts.hostname,parts.port),timeout=timeout):
            return True
    except ConnectionRefusedError:
        return False
    except OSError as exc:
        raise ServiceConflictError(f'port availability unverified: {exc}') from exc


class ServiceManager:
    def __init__(self, paths, manifest, logger, http_factory=HttpClient, *, resource_policy=None):
        self.paths,self.manifest,self.logger,self.http_factory = paths,manifest,logger,http_factory
        self._handles = {}
        self._streams = {}
        self.resource_policy = resource_policy

    @property
    def owned_pids(self):
        return {handle.pid for handle in self._handles.values()
                if handle.owned and handle.process is not None and handle.process.poll() is None}

    def _health(self, name, url, timeout):
        http = self.http_factory(url,timeout,self.logger)
        deadline = time.monotonic()+positive_timeout(timeout)
        def get(path):
            remaining = deadline-time.monotonic()
            if remaining<=0:
                raise ServiceStartError('service health deadline exhausted')
            result = http.get_json(path,max_bytes=JSON_LIMIT,timeout=remaining)
            if time.monotonic()>=deadline:
                raise ServiceStartError('service health deadline exhausted')
            return result
        if name == 'comfyui':
            stats = get('/system_stats')
            queue = get('/queue')
            if (not isinstance(stats,dict) or not isinstance(stats.get('system'),dict)
                    or not isinstance(stats['system'].get('comfyui_version'),str)
                    or not isinstance(queue,dict) or not all(isinstance(queue.get(k),list) for k in ('queue_running','queue_pending'))):
                raise ServiceConflictError('port identity does not match ComfyUI')
            return {'version':stats['system']['comfyui_version'],'stats':stats,'queue':queue}
        if name == 'ollama':
            version = get('/api/version')
            tags = get('/api/tags')
            ps = get('/api/ps')
            if (not isinstance(version,dict) or not isinstance(version.get('version'),str)
                    or not isinstance(tags,dict) or not isinstance(tags.get('models'),list)
                    or not isinstance(ps,dict) or not isinstance(ps.get('models'),list)):
                raise ServiceConflictError('port identity does not match Ollama')
            return {'version':version['version'],'tags':tags,'ps':ps}
        if name == 'tts':
            api = get('/openapi.json')
            if not isinstance(api,dict) or not isinstance(api.get('openapi'),str) or not isinstance(api.get('paths'),dict) or '/tts' not in api['paths']:
                raise ServiceConflictError('port identity does not match GPT-SoVITS API')
            return {'version':api.get('info',{}).get('version'), 'openapi':api}
        raise ValueError('unknown service name')

    def _record(self, handle, status, **details):
        record = dict(name=handle.name,url=handle.url,owned=handle.owned,pid=handle.pid,
                      started_at=handle.started_at,status=status,updated_at=now(),**details)
        self.manifest.update(lambda data:data['services'].update({handle.name:record}))
        self.logger.event('preflight',None,'service_'+status,record)

    def ensure(self, spec):
        from .owned_cleanup import best_effort,cleanup_preserving_exception
        from .execution_limits import execution_deadline, request_timeout
        validate_base_url(spec.url)
        env = service_environment(self.paths,spec)
        deadline = execution_deadline(spec.start_timeout,time.monotonic())
        if spec.name not in ('comfyui','ollama','tts'):
            raise ValueError('unknown service name')
        known = self._handles.get(spec.name)
        if known is not None and known.url != spec.url:
            raise ServiceConflictError('service name already bound to a different URL')
        try:
            health = self._health(spec.name,spec.url,min(2,spec.start_timeout))
        except (AdapterError,ServiceConflictError,ServiceStartError) as exc:
            best_effort(lambda:self.logger.exception('preflight',None,exc))
            remaining = 3 if deadline is None else deadline-time.monotonic()
            if remaining <= 0:
                raise ServiceStartError('service identity deadline exhausted') from exc
            # Windows can take about two seconds to return WSAECONNREFUSED.
            if port_listening(spec.url,min(3,remaining)):
                handle = ServiceHandle(spec.name,spec.url,False,None,None,None)
                best_effort(lambda:self._record(handle,'conflict',error=str(exc)))
                raise ServiceConflictError('occupied port has unavailable or wrong identity') from exc
        else:
            handle = known if known is not None and known.owned and known.process.poll() is None else ServiceHandle(spec.name,spec.url,False,None,None,None)
            self._handles[spec.name] = handle
            self._record(handle,'healthy',health=health)
            return handle
        args,cwd = validate_command(spec.args,spec.cwd,env)
        token = uuid4().hex
        stdout_path,stdout = self.logger.open_exclusive(f'services/{token}.stdout')
        stderr_path,stderr = self.logger.open_exclusive(f'services/{token}.stderr')
        process = None
        try:
            process = subprocess.Popen(args,cwd=cwd,env=env,stdout=stdout,stderr=stderr,shell=False)
            handle = ServiceHandle(spec.name,spec.url,True,process.pid,process,now())
            self._handles[spec.name] = handle
            self._streams[spec.name] = (stdout,stderr)
            self._record(handle,'starting',args=list(args),cwd=str(cwd),stdout_path=str(stdout_path),stderr_path=str(stderr_path))
            while deadline is None or time.monotonic()<deadline:
                if process.poll() is not None:
                    raise ServiceStartError(f'service exited before health: {process.returncode}')
                try:
                    health = self._health(spec.name,spec.url,request_timeout(deadline,2,time.monotonic()))
                except (AdapterError,ServiceConflictError,ServiceStartError):
                    remaining = .1 if deadline is None else deadline-time.monotonic()
                    if remaining>0:
                        time.sleep(min(.1,remaining))
                    continue
                self._record(handle,'healthy',health=health,stdout_path=str(stdout_path),stderr_path=str(stderr_path))
                return handle
            raise ServiceStartError('service start deadline exceeded')
        except BaseException as exc:
            if process is not None:
                cleanup_preserving_exception(lambda:stop_process(process),logger=self.logger,stage='preflight')
            for stream in (stdout,stderr):
                cleanup_preserving_exception(stream.close,logger=self.logger,stage='preflight')
            self._streams.pop(spec.name,None)
            best_effort(lambda:self.logger.exception('preflight',None,exc))
            if process is not None:
                best_effort(lambda:self._record(handle,'failed',returncode=process.returncode,error=str(exc),stdout_path=str(stdout_path),stderr_path=str(stderr_path)))
            if isinstance(exc,(KeyboardInterrupt,SystemExit)):
                raise
            raise ServiceStartError(str(exc)) from exc

    def _check_handle(self, handle):
        if self._handles.get(handle.name) is not handle:
            raise ValueError('handle is not owned/registered by this manager')

    def stop(self, handle):
        self._check_handle(handle)
        if not handle.owned:
            self._record(handle,'external',action='stop_skipped')
            return
        returncode = stop_process(handle.process)
        for stream in self._streams.pop(handle.name,()):
            stream.close()
        self._record(handle,'stopped',returncode=returncode)

    def release_comfy_models(self, handle):
        self._check_handle(handle)
        if handle.name!='comfyui' or not handle.owned or handle.process is None or handle.process.poll() is not None:
            self.logger.event(None,None,'model_release_skipped',dict(name=handle.name,reason='no live owned Comfy process'))
            return False
        health = self._health(handle.name,handle.url,2)
        sample = gpu_guard(self.manifest.run_dir,{handle.pid})
        if self.resource_policy is not None:
            sample = self.resource_policy(self.manifest.run_dir,sample)
        self.manifest.update(lambda data:data['resources'].update(latest=sample))
        queue = health['queue']
        if queue['queue_running'] or queue['queue_pending'] or sample.get('status')!='verified' or sample.get('external_pids'):
            self.logger.event(None,None,'model_release_skipped',dict(reason='queue active or GPU ownership unverified',sample=sample))
            return False
        http = self.http_factory(handle.url,2,self.logger)
        queue=http.get_json('/queue',max_bytes=JSON_LIMIT)
        if (not isinstance(queue,dict) or not all(isinstance(queue.get(k),list) for k in ('queue_running','queue_pending'))
                or queue['queue_running'] or queue['queue_pending']):
            self.logger.event(None,None,'model_release_skipped',dict(reason='queue changed during resource sampling'))
            return False
        self._check_handle(handle)
        if handle.process.poll() is not None:
            self.logger.event(None,None,'model_release_skipped',dict(reason='owned process exited during verification'))
            return False
        response = http.request('POST','/free',json_body={'unload_models':True,'free_memory':True},max_bytes=JSON_LIMIT)
        self._record(handle,'models_released',response_path=str(response.evidence_path))
        return True
