"""Whole-mode services retain owned resource sampling and release their lease."""
from types import SimpleNamespace

import pytest
from unit.test_scene_comfy_transactions import transaction,Client


@pytest.mark.parametrize('occupied_user_directory',[False,True])
def test_owned_service_prepares_comfy_directories_before_resources(runtime_run,monkeypatch,occupied_user_directory):
    from video_ai.runtime.production_scene_clips import _OwnedService
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.logging import RunLogger
    run,config,paths=runtime_run
    script=run/'script.txt';script.write_text('CPU service preparation fixture',encoding='utf-8')
    frozen=SimpleNamespace(config=config,options={'script_path':str(script)})
    user=run/'comfy/user'
    if occupied_user_directory:
        user.parent.mkdir(parents=True);user.write_bytes(b'preserve occupied path')
    def check_prepared(manifest):
        assert all((run/'comfy'/name).is_dir() for name in ('input','output','temp','user'))
    class Manager:
        def __init__(self,*args,**kwargs):pass
        def ensure(self,spec):
            check_prepared(None)
            return SimpleNamespace(owned=True)
    monkeypatch.setattr('video_ai.runtime.services.ServiceManager',Manager)
    monkeypatch.setattr('video_ai.runtime.services.port_listening',lambda *a:False)
    monkeypatch.setattr('video_ai.runtime.service_specs.build_service_specs',lambda *a,**k:{'comfyui':object()})
    with RunLock(run) as lock:
        service=_OwnedService(frozen,paths,RunLogger(run,production=True),lock)
        monkeypatch.setattr(service,'_start_resources',check_prepared)
        if occupied_user_directory:
            with pytest.raises((FileExistsError,NotADirectoryError)):
                service.ensure()
            assert user.read_bytes()==b'preserve occupied path'
        else:
            service.ensure()
            assert service.handle.owned


def test_whole_resource_session_precedes_service_and_stops_on_cleanup(monkeypatch):
    from video_ai.runtime.production_scene_clips import _OwnedService
    events=[]
    class Lease:
        def __init__(self,*args,**kwargs): events.append('lease-created')
        def acquire(self,*args,**kwargs): events.append('lease-acquired'); return self
        def release(self): events.append('lease-released')
    class Sampler:
        def __init__(self,*args,**kwargs): events.append('sampler-created')
        def start(self): events.append('sampler-started'); return self
        def stop(self): events.append('sampler-stopped')
        def summary(self): return {'verified_samples':1}
    monkeypatch.setattr('video_ai.runtime.resources.GpuLease',Lease)
    monkeypatch.setattr('video_ai.runtime.resources.ResourceSampler',Sampler)
    logger=SimpleNamespace(run_dir='D:/VideoSi/projects/video-ai/runs/20261030-000000-abcdefabcdef',
        save_json=lambda *a,**k:events.append('resource-summary'))
    frozen=SimpleNamespace(config=SimpleNamespace(raw={'scene_rendering':{'mode':'whole_scene_v1'}}))
    service=_OwnedService(frozen,None,logger,None)
    service._start_resources(SimpleNamespace())
    service.close()
    assert events==['lease-created','lease-acquired','sampler-created','sampler-started',
        'sampler-stopped','resource-summary','lease-released']


def test_legacy_service_does_not_start_new_resource_session(monkeypatch):
    from video_ai.runtime.production_scene_clips import _OwnedService
    def forbidden(*a,**k): raise AssertionError('legacy service behavior changed')
    monkeypatch.setattr('video_ai.runtime.resources.GpuLease',forbidden)
    service=_OwnedService(SimpleNamespace(config=SimpleNamespace(raw={})),None,SimpleNamespace(run_dir='unused'),None)
    service._start_resources(SimpleNamespace())
    service.close()


@pytest.mark.parametrize('whole,expected_calls', [(True,1),(False,2)])
def test_confirmed_inference_failure_stops_whole_batch_only(tmp_path,monkeypatch,whole,expected_calls):
    from video_ai.runtime import production_scene_clips as module
    calls=[]
    store=SimpleNamespace(run_dir=tmp_path,lock=None,assert_owned=lambda:None,
        write=lambda *a:None,read=lambda *a:None,clip_dir=lambda cid:tmp_path/cid,
        capture_guard=lambda *a:(lambda:None))
    context=dict(store=store,frozen=SimpleNamespace(config=SimpleNamespace(
        services={'comfyui':'http://127.0.0.1:8198'},timeouts={'comfy_request':5,'wan':7200})),
        units=[],timeline=None,execution={'mode':'whole_scene_v1'} if whole else None,
        template=None,plan={'scenes':[{'scene_id':'scene_0001'},{'scene_id':'scene_0002'}]},
        inputs={},rows=[{'budget':{'scene_id':f'scene_{i:04d}','clip_id':f'scene_{i:04d}_clip_0001','generated_frames':1}}
            for i in (1,2)])
    monkeypatch.setattr('video_ai.runtime.production_inputs.check_stage_space',lambda *a,**k:None)
    monkeypatch.setattr('video_ai.runtime.scene_continuity_records.load_continuity_policy',lambda *a:None)
    monkeypatch.setattr(module,'graph_for',lambda *a:{})
    monkeypatch.setattr(module,'_restore_outer',lambda *a,**k:None)
    monkeypatch.setattr(module,'collect_progress',lambda *a:({'scenes':[]},{}))
    monkeypatch.setattr(module,'validate_clip',lambda *a:None)
    monkeypatch.setattr(module,'_input',lambda *a,**k:{})
    monkeypatch.setattr(module,'expected_request',lambda c,row,*a:{'clip_id':row['budget']['clip_id']})
    monkeypatch.setattr(module,'_finish',lambda *a:SimpleNamespace(status='failed',error=None))
    def failure(store,request,*a,**k):
        calls.append(request['clip_id'])
        raise RuntimeError('fixture_only confirmed inference failure')
    monkeypatch.setattr('video_ai.runtime.scene_comfy_transactions.recover_or_submit_scene_clip',failure)
    module._produce(context,paths=None,logger=SimpleNamespace(),client_factory=lambda *a,**k:None,service_factory=None)
    assert len(calls)==expected_calls


def test_whole_resume_does_not_restart_expired_original_deadline(transaction,monkeypatch):
    from video_ai.runtime import scene_comfy_transactions as module
    store,request,graph,template=transaction
    store.execution_mode='whole_scene_v1'
    client=Client(store,request,graph)
    original=store.write
    def interrupt_after_intent(name,value):
        result=original(name,value)
        if getattr(name,'name',None)=='intent.json': raise KeyboardInterrupt('fixture interruption after original intent')
        return result
    monkeypatch.setattr(store,'write',interrupt_after_intent)
    monkeypatch.setattr(module,'now',lambda:'2000-01-01T00:00:00+00:00')
    with pytest.raises(KeyboardInterrupt):
        module.recover_or_submit_scene_clip(store,request,graph,client=client,template=template,
            ensure_service=lambda:None,logger=None,timeout=7200)
    monkeypatch.setattr(store,'write',original)
    ensures=[]
    with pytest.raises(module.SceneSubmitUnknown):
        module.recover_or_submit_scene_clip(store,request,graph,client=client,template=template,
            ensure_service=lambda:ensures.append(True),logger=None,timeout=7200)
    assert not ensures and client.posts==0


def test_completed_whole_media_can_replay_after_original_deadline(transaction,monkeypatch):
    from video_ai.runtime import scene_comfy_transactions as module
    store,request,graph,template=transaction
    store.execution_mode='whole_scene_v1'
    client=Client(store,request,graph)
    result=module.recover_or_submit_scene_clip(store,request,graph,client=client,template=template,
        ensure_service=lambda:None,logger=None,timeout=7200)
    wall=module.time.time()
    monkeypatch.setattr(module.time,'time',lambda:wall+7201)
    assert module.recover_or_submit_scene_clip(store,request,graph,client=None,template=template,
        ensure_service=lambda:pytest.fail('completed replay restarted service'),logger=None,timeout=7200)==result
    assert client.posts==1


def test_expired_whole_recovers_local_success_after_submission_marker_interruption(transaction,monkeypatch):
    from video_ai.runtime import scene_comfy_transactions as module
    store,request,graph,template=transaction
    store.execution_mode='whole_scene_v1'
    client=Client(store,request,graph)
    original=store.write
    def interrupt_commit(name,value):
        if getattr(name,'name',None)=='submission.json': raise KeyboardInterrupt('fixture raw success persisted before derived submission marker')
        return original(name,value)
    monkeypatch.setattr(store,'write',interrupt_commit)
    with pytest.raises(KeyboardInterrupt):
        module.recover_or_submit_scene_clip(store,request,graph,client=client,template=template,
            ensure_service=lambda:None,logger=None,timeout=7200)
    monkeypatch.setattr(store,'write',original)
    wall=module.time.time()
    monkeypatch.setattr(module.time,'time',lambda:wall+7201)
    result=module.recover_or_submit_scene_clip(store,request,graph,client=None,template=template,
        ensure_service=lambda:pytest.fail('local raw success recovery restarted service'),logger=None,timeout=7200)
    assert result['output']==store.artifact(client.output) and client.posts==1
