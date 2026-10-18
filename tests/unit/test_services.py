from dataclasses import replace
import sys
import pytest
from http_helpers import Response, ScriptedTransport


class Process:
    def __init__(self):
        self.pid=4321
        self.returncode=None
        self.terminated=False
    def poll(self): return self.returncode
    def terminate(self): self.terminated=True; self.returncode=-15
    def wait(self,timeout=None): return self.returncode


def manager(run_store,runtime_run,handler):
    from video_ai.runtime.services import ServiceManager
    from video_ai.runtime.logging import RunLogger
    from video_ai.adapters.common import HttpClient
    logger=RunLogger(run_store.run_dir)
    transport=ScriptedTransport(handler)
    return ServiceManager(runtime_run[2],run_store,logger,
                          lambda url,timeout,logger:HttpClient(url,timeout,logger,transport=transport)),transport


def spec(runtime_run,timeout=5):
    # Ownership tests do real durable logging; their success must not depend
    # on finishing Windows filesystem operations within 50 milliseconds.
    # Deadline tests supply their own deliberately short timeout below.
    from video_ai.runtime.services import ServiceSpec
    return ServiceSpec('comfyui','http://127.0.0.1:8188',(sys.executable,'-c','pass'),runtime_run[0],timeout)


def healthy(request,timeout):
    if request.full_url.endswith('/system_stats'):
        return Response({'system':{'comfyui_version':'0.37.0'},'devices':[]})
    return Response({'queue_running':[],'queue_pending':[]})


def test_external_healthy_service_is_not_owned_stopped_or_freed(run_store,runtime_run):
    mgr,transport=manager(run_store,runtime_run,healthy)
    handle=mgr.ensure(spec(runtime_run))
    assert not handle.owned and handle.process is None
    mgr.stop(handle)
    assert not mgr.release_comfy_models(handle)
    assert all(call[0]=='GET' for call in transport.calls)
    assert run_store.snapshot()['services']['comfyui']['owned'] is False


def test_wrong_service_on_occupied_port_never_starts_process(run_store,runtime_run,monkeypatch):
    import video_ai.runtime.services as module
    mgr,_=manager(run_store,runtime_run,lambda r,t:Response({'unrelated':True}))
    monkeypatch.setattr(module,'port_listening',lambda *a,**k:True)
    def forbidden(*a,**k): pytest.fail('must not start on occupied port')
    monkeypatch.setattr(module.subprocess,'Popen',forbidden)
    with pytest.raises(module.ServiceConflictError):
        mgr.ensure(spec(runtime_run))


def test_windows_delayed_connection_refusal_has_bounded_probe_budget(run_store,runtime_run,monkeypatch):
    import video_ai.runtime.services as module
    process=Process()
    started=False
    def route(r,t):
        if not started:raise ConnectionRefusedError('closed')
        return healthy(r,t)
    mgr,_=manager(run_store,runtime_run,route)
    def probe(url,timeout):
        if timeout<2.1:raise module.ServiceConflictError('Windows refusal arrives after two seconds')
        assert timeout<=3
        return False
    monkeypatch.setattr(module,'port_listening',probe)
    def launch(*a,**kwargs):
        nonlocal started
        started=True
        return process
    monkeypatch.setattr(module.subprocess,'Popen',launch)
    handle=mgr.ensure(spec(runtime_run,timeout=10))
    assert handle.owned
    mgr.stop(handle)


@pytest.mark.parametrize('exited',[False,True])
def test_owned_process_can_only_be_stopped_by_its_own_manager(run_store,runtime_run,monkeypatch,exited):
    import video_ai.runtime.services as module
    process=Process()
    started=False
    def route(r,t):
        if not started: raise ConnectionRefusedError('closed')
        return healthy(r,t)
    mgr,_=manager(run_store,runtime_run,route)
    monkeypatch.setattr(module,'port_listening',lambda *a,**k:False)
    def launch(*a,**k):
        nonlocal started
        started=True
        assert k['shell'] is False
        assert k['env']['TEMP'].startswith('D:')
        return process
    monkeypatch.setattr(module.subprocess,'Popen',launch)
    handle=mgr.ensure(spec(runtime_run))
    assert handle.owned and handle.process is process
    if exited: process.returncode=0
    forged=replace(handle,process=Process())
    with pytest.raises(ValueError): mgr.stop(forged)
    mgr.stop(handle)
    assert process.terminated is (not exited)
    assert run_store.snapshot()['services']['comfyui']['returncode']==(0 if exited else -15)


def test_start_timeout_only_cleans_its_process(run_store,runtime_run,monkeypatch):
    import video_ai.runtime.services as module
    process=Process()
    def unavailable(r,t): raise ConnectionRefusedError('unavailable')
    mgr,_=manager(run_store,runtime_run,unavailable)
    monkeypatch.setattr(module,'port_listening',lambda *a,**k:False)
    monkeypatch.setattr(module.subprocess,'Popen',lambda *a,**k:process)
    with pytest.raises(module.ServiceStartError): mgr.ensure(spec(runtime_run,timeout=.2))
    assert process.terminated
    assert run_store.snapshot()['services']['comfyui']['status']=='failed'


def test_owned_free_requires_empty_queue_and_verified_gpu(run_store,runtime_run,monkeypatch):
    import video_ai.runtime.services as module
    process=Process()
    started=False
    queue=[]
    def route(r,t):
        if not started: raise ConnectionRefusedError('closed')
        if r.full_url.endswith('/queue'):return Response({'queue_running':queue,'queue_pending':[]})
        return healthy(r,t)
    mgr,transport=manager(run_store,runtime_run,route)
    monkeypatch.setattr(module,'port_listening',lambda *a,**k:False)
    def launch(*a,**k):
        nonlocal started
        started=True
        return process
    monkeypatch.setattr(module.subprocess,'Popen',launch)
    handle=mgr.ensure(spec(runtime_run))
    monkeypatch.setattr(module,'gpu_guard',lambda *a,**k: {'status':'verified','external_pids':[]})
    assert mgr.release_comfy_models(handle)
    assert sum(c[0]=='POST' for c in transport.calls)==1
    queue.append([1,'external-prompt',{},{}])
    assert not mgr.release_comfy_models(handle)
    assert sum(c[0]=='POST' for c in transport.calls)==1


def test_health_probes_share_one_start_deadline(run_store,runtime_run,monkeypatch):
    import time
    import video_ai.runtime.services as module
    budgets=[]
    def slow_health(r,timeout):
        budgets.append(timeout)
        time.sleep(.06)
        return healthy(r,timeout)
    mgr,_=manager(run_store,runtime_run,slow_health)
    monkeypatch.setattr(module,'port_listening',lambda *a,**k:True)
    with pytest.raises((module.ServiceConflictError,module.ServiceStartError)):
        mgr.ensure(spec(runtime_run,timeout=.09))
    assert len(budgets)==2 and budgets[1]<budgets[0]


def test_exit_during_gpu_query_prevents_free_of_replacement_service(run_store,runtime_run,monkeypatch):
    import video_ai.runtime.services as module
    process=Process()
    started=False
    def route(r,t):
        if not started:raise ConnectionRefusedError('closed')
        return healthy(r,t)
    mgr,transport=manager(run_store,runtime_run,route)
    monkeypatch.setattr(module,'port_listening',lambda *a,**k:False)
    def launch(*a,**k):
        nonlocal started
        started=True
        return process
    monkeypatch.setattr(module.subprocess,'Popen',launch)
    handle=mgr.ensure(spec(runtime_run,timeout=.3))
    def guard(*a,**k):
        process.returncode=0
        return {'status':'verified','external_pids':[]}
    monkeypatch.setattr(module,'gpu_guard',guard)
    assert not mgr.release_comfy_models(handle)
    assert not any(c[0]=='POST' for c in transport.calls)


def test_start_log_failure_still_stops_owned_process(run_store,runtime_run,monkeypatch):
    import video_ai.runtime.services as module
    process=Process()
    def unavailable(r,t):raise ConnectionRefusedError('closed')
    mgr,_=manager(run_store,runtime_run,unavailable)
    monkeypatch.setattr(module,'port_listening',lambda *a,**k:False)
    original=mgr.logger.exception
    def fail_after_launch(*a,**k):
        if launched:raise OSError('log disk full')
        return original(*a,**k)
    launched=False
    def launch(*a,**k):
        nonlocal launched
        launched=True
        return process
    monkeypatch.setattr(module.subprocess,'Popen',launch)
    monkeypatch.setattr(mgr.logger,'exception',fail_after_launch)
    with pytest.raises((OSError,module.ServiceStartError)):
        mgr.ensure(spec(runtime_run,timeout=.2))
    assert process.terminated


def test_queue_is_rechecked_after_resource_sampling(run_store,runtime_run,monkeypatch):
    import video_ai.runtime.services as module
    process=Process()
    started=False
    queue=[]
    def route(r,t):
        if not started:raise ConnectionRefusedError('closed')
        if r.full_url.endswith('/queue'):return Response({'queue_running':queue,'queue_pending':[]})
        return healthy(r,t)
    mgr,transport=manager(run_store,runtime_run,route)
    monkeypatch.setattr(module,'port_listening',lambda *a,**k:False)
    def launch(*a,**k):
        nonlocal started
        started=True
        return process
    monkeypatch.setattr(module.subprocess,'Popen',launch)
    handle=mgr.ensure(spec(runtime_run,timeout=.3))
    def guard(*a,**k):
        queue.append([1,'external-prompt',{},{}])
        return {'status':'verified','external_pids':[]}
    monkeypatch.setattr(module,'gpu_guard',guard)
    assert not mgr.release_comfy_models(handle)
    assert not any(c[0]=='POST' for c in transport.calls)
