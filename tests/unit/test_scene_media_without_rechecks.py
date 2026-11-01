"""Whole media honors the user's removal of repeated input/environment audits."""
from types import SimpleNamespace
import pytest

from test_scene_upscale_transactions import transaction, Client
from video_ai.runtime.production_state import RunLock, ProductionRefused
from video_ai.runtime.scene_media_records import SceneMediaStore


def frozen(mode='whole_scene_v1'):
    return SimpleNamespace(options={'model_stamps': {}},
                           config=SimpleNamespace(raw={'scene_rendering': {'mode': mode}}))


def unwanted(*args, **kwargs):
    raise AssertionError('removed repeated input audit was called')


@pytest.mark.parametrize('operation', ['write', 'global', 'captured', 'send', 'tools'])
def test_whole_media_uses_no_repeated_dependency_audit(runtime_run, operation):
    run=runtime_run[0]
    with RunLock(run) as lock:
        store=SceneMediaStore(frozen(), run, lock=lock, clip_ids=('scene_0001_clip_0001',))
        request={'frame_id': 'scene_0001_clip_0001:frame_000001'}
        graph={'node': 1}
        store.write('inputs.json', {})
        store.write(store.frame_dir(request['frame_id'])/'request.json', request)
        store.write(store.frame_dir(request['frame_id'])/'graph.json', graph)
        store.continuity_check=unwanted
        store.continuity_read_guard=unwanted
        store.execution_guard=unwanted
        store.revision_context={'guard': SimpleNamespace(verify_captured_bytes=unwanted)}
        store.guard_paths[str(run/'no-longer-rechecked.json')]={'path':str(run/'no-longer-rechecked.json'),'bytes':1,'sha256':'f'*64}
        store.guard_tool_stamps={'ffmpeg':SimpleNamespace(verify=unwanted)}
        actions={'write':lambda:store.write('next.json', {'next':1}),
                 'global':store.verify_global, 'captured':store.verify_captured_bytes,
                 'send':lambda:store.capture_guard(request,graph)(), 'tools':store.verify_tools}
        actions[operation]()


def test_whole_lexical_path_does_not_walk_parent_metadata(runtime_run, monkeypatch):
    from pathlib import Path
    run=runtime_run[0]
    store=SceneMediaStore(frozen(),run)
    monkeypatch.setattr(Path,'lstat',unwanted)
    assert store._lexical(run/'comfy/output/frame.png')==run/'comfy/output/frame.png'
    with pytest.raises(ProductionRefused):store._lexical(run.parent/'outside.png')


def test_whole_context_admits_once_without_constructing_byte_guard(runtime_run,monkeypatch):
    from video_ai.runtime import scene_media_records as media,scene_continuity_records as continuity
    store=SceneMediaStore(frozen(),runtime_run[0]);calls=[]
    store.continuity_check=lambda:calls.append('initial_admission')
    context={'store':store}
    monkeypatch.setattr(media,'_scene_media_base_context',lambda *a,**kw:context)
    monkeypatch.setattr(continuity,'capture_scene_continuity_guard',unwanted)
    assert media.scene_media_context(store.frozen,[],None) is context
    assert calls==['initial_admission']
    assert store.continuity_check is None and store.continuity_read_guard is None


def test_whole_frame_omits_object_info_and_completed_replay_never_posts_again(runtime_run,transaction):
    from video_ai.runtime.scene_upscale_transactions import recover_or_submit_scene_frame
    run=runtime_run[0]
    _,request,graph,template=transaction
    with RunLock(run) as lock:
        store=SceneMediaStore(frozen(),run,lock=lock,clip_ids=(request['clip_id'],))
        store.write('inputs.json',{})
        store.write(store.frame_dir(request['frame_id'])/'request.json',request)
        store.write(store.frame_dir(request['frame_id'])/'graph.json',graph)
        client=Client(store,request,graph);client.object_info=unwanted
        client.ownership_check=store.assert_owned
        result=recover_or_submit_scene_frame(store,request,graph,client=client,template=template,
            ensure_service=lambda:None,logger=None,timeout=180)
        assert client.posts==1 and result['prompt_id']==client.pid
        again=recover_or_submit_scene_frame(store,request,graph,client=client,template=template,
            ensure_service=unwanted,logger=None,timeout=180)
        assert again==result and client.posts==1


def test_whole_media_still_refuses_after_run_lock_loss(runtime_run):
    run=runtime_run[0]
    with RunLock(run) as lock:
        store=SceneMediaStore(frozen(),run,lock=lock)
        lock.path.write_text('{}',encoding='utf-8')
        try:
            with pytest.raises(ProductionRefused):store.write('forbidden.json',{})
            assert not (store.root/'forbidden.json').exists()
        finally:
            import json
            lock.path.write_text(json.dumps(lock.owner),encoding='utf-8')


def test_historical_media_retains_existing_callback(runtime_run):
    run=runtime_run[0]
    with RunLock(run) as lock:
        store=SceneMediaStore(frozen('segmented_v1'),run,lock=lock)
        store.continuity_check=unwanted
        with pytest.raises(AssertionError,match='removed repeated input audit'):store.assert_write()
