from types import SimpleNamespace
import json

import pytest


def test_default_health_classifies_unavailable_service_for_owned_start(runtime_run,tmp_path,monkeypatch):
    from image_selection_helpers import setup_selection
    from video_ai.runtime.production_scene_clips import _OwnedService
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.logging import RunLogger
    from video_ai.adapters.common import AdapterError
    s=setup_selection(runtime_run,tmp_path)
    class Client:
        def __init__(self,*args,**kwargs): pass
        def system_stats(self,**kwargs): raise ConnectionRefusedError('not listening yet')
    class Manager:
        def __init__(self,paths,manifest,logger,http_factory): self.http_factory=http_factory
        def ensure(self,spec):
            with pytest.raises(AdapterError):
                self.http_factory(spec.url,2,None).get_json('/system_stats',timeout=2)
            return SimpleNamespace(owned=True)
        def stop(self,handle): pass
    monkeypatch.setattr('video_ai.adapters.scene_comfy.SceneComfyClient',Client)
    monkeypatch.setattr('video_ai.runtime.services.ServiceManager',Manager)
    monkeypatch.setattr('video_ai.runtime.services.port_listening',lambda *args:False)
    with RunLock(s['run']) as held:
        service=_OwnedService(s['frozen'],s['paths'],RunLogger(s['run'],production=True),held)
        service.ensure();service.close()


@pytest.mark.parametrize('interrupted',[False,True])
def test_service_cleanup_keeps_primary_error_and_scene_state(runtime_run,monkeypatch,interrupted):
    import video_ai.runtime.production_scene_clips as module
    from video_ai.runtime.scene_comfy_transactions import SceneSubmitUnknown
    run,_,paths=runtime_run;cid='scene_0001_clip_0001'
    store=SimpleNamespace(run_dir=run,lock=None,assert_owned=lambda:None,clip_dir=lambda _:run/'production/scene-clips'/cid,
        write=lambda *args:None,read=lambda *args:None,capture_guard=lambda *args:lambda:None,verify_global=lambda:None)
    row={'budget':dict(clip_id=cid,scene_id='scene_0001',generated_frames=1)}
    scene=dict(scene_id='scene_0001',status='pending',completed_clip_ids=[],accepted_clip_ids=[],waiting_clip_id=cid,error=None)
    frozen=SimpleNamespace(config=SimpleNamespace(timeouts={'wan':1,'comfy_request':1},services={'comfyui':'http://127.0.0.1:8188'}))
    context=dict(store=store,frozen=frozen,rows=[row],plan={'scenes':[{'scene_id':'scene_0001'}]},inputs={},template=None)
    monkeypatch.setattr(module,'graph_for',lambda *args:{})
    monkeypatch.setattr(module,'collect_progress',lambda *args:({'scenes':[dict(scene)]},{}))
    monkeypatch.setattr(module,'_restore_outer',lambda *args,**kwargs:None)
    monkeypatch.setattr(module,'validate_clip',lambda *args:None)
    monkeypatch.setattr(module,'_input',lambda *args,**kwargs:{})
    monkeypatch.setattr(module,'expected_request',lambda *args:{})
    monkeypatch.setattr('video_ai.runtime.production_inputs.check_stage_space',lambda *args,**kwargs:None)
    def fail(*args,**kwargs):
        kwargs['ensure_service']()
        if interrupted: raise KeyboardInterrupt('primary interruption')
        raise SceneSubmitUnknown('primary generation outcome unknown')
    monkeypatch.setattr('video_ai.runtime.scene_comfy_transactions.recover_or_submit_scene_clip',fail)
    class Service:
        def ensure(self):pass
        def close(self):raise OSError('secondary stop failure')
    kwargs=dict(paths=paths,logger=None,client_factory=lambda *args,**kwargs:object(),service_factory=lambda *args:Service())
    if interrupted:
        with pytest.raises(KeyboardInterrupt) as caught:module._produce(context,**kwargs)
        assert any('secondary stop failure' in note for note in caught.value.__notes__)
    else:
        result=module._produce(context,**kwargs)
        assert result.status=='failed'
        assert result.scenes[0]['status']=='submit_unknown'
        assert 'primary generation outcome unknown' in result.error['message']
        assert 'secondary stop failure' in result.error['message']


def test_media_logger_cannot_persist_after_lock_loss(runtime_run):
    from video_ai.runtime.production_scene_clips import _GuardedLogger
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.production_state import RunLock
    run,_,paths=runtime_run
    logger=RunLogger(run,production=True)
    with RunLock(run) as held:
        store=SceneClipStore(None,run,paths=paths,lock=held)
        guarded=_GuardedLogger(logger,store.assert_owned)
        guarded.save_json('before.json',{'owned':True})
        held.path.write_text('{}',encoding='utf-8')
        for action in (lambda:guarded.save_json('late.json',{}),lambda:guarded.event('source_clips',None,'late',{}),
                       lambda:guarded.open_exclusive('late.raw')):
            with pytest.raises(ValueError):action()
        assert not logger.path('late.json').exists() and not logger.path('late.raw').exists()
        held.path.write_text(json.dumps(held.owner),encoding='utf-8')


def test_unknown_unprepared_run_has_no_fabricated_result_paths(runtime_run):
    from video_ai.runtime.production_scene_clips import produce_scene_clips
    from video_ai.runtime.logging import RunLogger
    run,_,paths=runtime_run
    frozen=SimpleNamespace(options={'script_path':str(run/'production/script.txt'),'run_id':run.name})
    result=produce_scene_clips(frozen,{},None,paths=paths,logger=RunLogger(run,production=True))
    assert result.status=='blocked'
    assert result.run_id is None and result.run_dir is None and result.log_dir is None
    assert result.source_clips is None and result.scenes==[]
    assert not (run/'.make-video.lock').exists()
