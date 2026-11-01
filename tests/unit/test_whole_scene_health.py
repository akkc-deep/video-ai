"""Comfy health probes retain network deadlines and lock-checked evidence."""
import json
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('network_seconds,lose_lock',[(.01,False),(3,False),(.01,True)])
def test_owned_health_keeps_network_budget_without_repeating_model_admission(runtime_run,monkeypatch,network_seconds,lose_lock):
    import video_ai.runtime.services as services
    from video_ai.runtime.production_scene_clips import _OwnedService,_GuardedLogger
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    from video_ai.runtime.logging import RunLogger
    run,config,paths=runtime_run
    script=run/'script.txt';script.write_text('CPU health fixture',encoding='utf-8')
    clock=[0.0]
    monkeypatch.setattr(services.time,'monotonic',lambda:clock[0])
    def model_admission():clock[0]+=7
    class Client:
        def __init__(self,url,request_timeout,ownership_check):self.guard=ownership_check
        def response(self,body):
            self.guard();clock[0]+=network_seconds
            if lose_lock:lock.path.write_text('{}',encoding='utf-8')
            return dict(status=200,headers={},body=json.dumps(body).encode())
        def system_stats(self,*,timeout):return self.response({'system':{'comfyui_version':'fixture-comfy'}})
        def queue(self,*,timeout):return self.response({'queue_running':[],'queue_pending':[]})
    class Manager(services.ServiceManager):
        def ensure(self,spec):
            health=self._health('comfyui',config.services['comfyui'],2)
            assert health['version']=='fixture-comfy'
            return SimpleNamespace(owned=True)
    monkeypatch.setattr('video_ai.adapters.scene_comfy.SceneComfyClient',Client)
    monkeypatch.setattr(services,'ServiceManager',Manager)
    monkeypatch.setattr(services,'port_listening',lambda *a:False)
    monkeypatch.setattr('video_ai.runtime.service_specs.build_service_specs',lambda *a,**k:{'comfyui':object()})
    with RunLock(run) as lock:
        owner_bytes=lock.path.read_bytes()
        logger=_GuardedLogger(RunLogger(run,production=True),model_admission)
        service=_OwnedService(SimpleNamespace(config=config,options={'script_path':str(script)}),paths,logger,lock)
        monkeypatch.setattr(service,'_start_resources',lambda manifest:None)
        if lose_lock:
            try:
                with pytest.raises(ProductionRefused,match='service lost run lock'):
                    service.ensure()
                assert not list((run/'logs/production/scene-clips/service').glob('*.json'))
            finally:lock.path.write_bytes(owner_bytes)
        elif network_seconds>2:
            with pytest.raises(services.ServiceStartError,match='health deadline exhausted'):
                service.ensure()
        else:
            service.ensure()
            records=[json.loads(p.read_text(encoding='utf-8')) for p in (run/'logs/production/scene-clips/service').glob('*.json')]
            assert sorted(r['route'] for r in records)==['/queue','/system_stats']
            assert service.handle.owned
