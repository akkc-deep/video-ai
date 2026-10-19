from scene_media_helpers import prepared_upscaled,prepared_scene_sources,OfflineUpscale
import json
from pathlib import Path
import pytest


def test_authentic_scene_upscale_and_readonly_replay(runtime_run,tmp_path,monkeypatch):
    from video_ai.runtime.scene_media_records import require_scene_upscale_acceptance
    from video_ai.runtime.production_scene_upscale import produce_scene_upscaled_clips
    setup=prepared_upscaled(runtime_run,tmp_path,monkeypatch)
    complete=require_scene_upscale_acceptance(setup['frozen'],setup['units'],setup['timeline'])
    assert len(complete['frames'])==setup['timeline'].total_frames
    count=len(setup['upscale_backend'].posts)
    before={str(p):p.stat().st_mtime_ns for p in (setup['run']/'production/scene-upscale').rglob('*') if p.is_file()}
    again=produce_scene_upscaled_clips(setup['frozen'],setup['units'],setup['timeline'],
        paths=setup['paths'],logger=setup['logger'],**setup['upscale_backend'].kwargs)
    assert again.status=='upscale_ready',again.error
    assert len(setup['upscale_backend'].posts)==count
    assert before=={str(p):p.stat().st_mtime_ns for p in (setup['run']/'production/scene-upscale').rglob('*') if p.is_file()}


def test_accepted_local_media_receipts_restore_outer_commits_without_reextract_or_post(runtime_run,tmp_path,monkeypatch):
    from video_ai.runtime.scene_media_records import require_scene_upscale_acceptance
    from video_ai.runtime.production_scene_upscale import produce_scene_upscaled_clips
    from video_ai.runtime.production_state import ProductionRefused
    import video_ai.media.scene_upscale as media
    setup=prepared_upscaled(runtime_run,tmp_path,monkeypatch); root=setup['run']/'production/scene-upscale'
    original=require_scene_upscale_acceptance(setup['frozen'],setup['units'],setup['timeline'])
    frame=original['frames'][0]; folder=root.joinpath(*frame['frame_id'].split(':'))
    paths=[root/'complete.json',folder/'frame.json',folder.parent/'extraction.json']
    raw={p:p.read_bytes() for p in paths}
    for path in paths: path.unlink()
    before={str(p):p.stat().st_mtime_ns for p in root.rglob('*') if p.is_file()}
    with pytest.raises(ProductionRefused): require_scene_upscale_acceptance(setup['frozen'],setup['units'],setup['timeline'])
    assert before=={str(p):p.stat().st_mtime_ns for p in root.rglob('*') if p.is_file()}
    monkeypatch.setattr(media,'extract_scene_frames',lambda *a,**kw:pytest.fail('accepted native images re-extracted'))
    posts=len(setup['upscale_backend'].posts); ensures=setup['upscale_backend'].ensures
    result=produce_scene_upscaled_clips(setup['frozen'],setup['units'],setup['timeline'],paths=setup['paths'],logger=setup['logger'],**setup['upscale_backend'].kwargs)
    assert result.status=='upscale_ready',result.error
    assert len(setup['upscale_backend'].posts)==posts and setup['upscale_backend'].ensures==ensures
    assert all(p.read_bytes()==value for p,value in raw.items())


def test_future_frame_conflict_stops_earlier_new_posts_and_transient_copy_keeps_original_task(runtime_run,tmp_path,monkeypatch):
    from video_ai.runtime.production_scene_upscale import produce_scene_upscaled_clips
    import video_ai.runtime.production_scene_upscale as production
    setup=prepared_scene_sources(runtime_run,tmp_path,monkeypatch); backend=OfflineUpscale(setup)
    from video_ai.runtime.scene_clip_records import require_scene_clip_acceptance
    clips=require_scene_clip_acceptance(setup['frozen'],setup['units'],setup['timeline'])
    last=clips['clips'][-1]; root=setup['run']/'production/scene-upscale'
    future=root/last['clip_id']/f'frame_{last["budget"]["retained_frames"]:06d}'/'graph.json'
    future.parent.mkdir(parents=True); future.write_text('{}',encoding='utf-8')
    def produce(**kwargs):
        return produce_scene_upscaled_clips(setup['frozen'],setup['units'],setup['timeline'],paths=setup['paths'],logger=setup['logger'],**(kwargs or backend.kwargs))
    blocked=produce()
    assert blocked.status=='blocked' and not backend.posts and backend.ensures==0
    malformed=future.parent/'terminal.json'
    for raw in (b'{malformed-json',b'[]'):
        malformed.write_bytes(raw)
        malformed_result=produce()
        assert malformed_result.status in ('blocked','failed') and malformed_result.error
        assert not backend.posts and backend.ensures==0
    malformed.unlink()
    future.unlink()
    original=production._copy; failed=[]
    def transient(context,row,operation,source):
        if operation=='output' and not failed:
            failed.append(row['frame_id']); raise OSError('synthetic temporary copy failure')
        return original(context,row,operation,source)
    monkeypatch.setattr(production,'_copy',transient)
    failed_result=produce()
    assert failed_result.status=='failed' and len(backend.posts)==1
    first=root.joinpath(*failed[0].split(':'))
    assert (first/'submission.json').exists() and not (first/'terminal.json').exists()
    first_pid=json.loads((first/'submission.json').read_bytes())['prompt_id']
    monkeypatch.setattr(production,'_copy',original)
    def cleanup_failure(frozen,paths,logger,lock):
        service=backend.service_factory(frozen,paths,logger,lock)
        class Service:
            def ensure(self): service.ensure()
            def close(self): service.close(); raise RuntimeError('synthetic service cleanup failure')
        return Service()
    failed_cleanup=produce(**dict(backend.kwargs,service_factory=cleanup_failure))
    assert failed_cleanup.status=='failed' and 'cleanup failure' in failed_cleanup.error['message']
    assert (root/'complete.json').is_file()
    ready=produce()
    assert ready.status=='upscale_ready',ready.error
    assert len(backend.posts)==setup['timeline'].total_frames
    assert json.loads((first/'submission.json').read_bytes())['prompt_id']==first_pid


def test_authentic_200_frame_chain_submits_only_93_92_15_and_contributes_every_retained_frame(runtime_run,tmp_path,monkeypatch):
    from collections import Counter
    from video_ai.runtime.scene_clip_records import require_scene_clip_acceptance
    from video_ai.runtime.scene_media_records import require_scene_upscale_acceptance
    from video_ai.planning.scene_media import plan_scene_contributions
    setup=prepared_upscaled(runtime_run,tmp_path,monkeypatch,long_scene=True)
    clips=require_scene_clip_acceptance(setup['frozen'],setup['units'],setup['timeline'])
    upscaled=require_scene_upscale_acceptance(setup['frozen'],setup['units'],setup['timeline'])
    chain=clips['clips'][:3]; ids=[c['clip_id'] for c in chain]
    assert [c['budget']['retained_frames'] for c in chain]==[93,92,15]
    counts=Counter(Path(post['prompt']['5']['inputs']['filename_prefix']).parts[-3] for post in setup['upscale_backend'].posts)
    assert [counts[cid] for cid in ids]==[93,92,15]
    frames=[f for f in upscaled['frames'] if f['mapping']['clip_id'] in ids]
    assert len(frames)==len({f['frame_id'] for f in frames})==200
    assert [f['mapping']['output_frame_index'] for f in frames]==list(range(200))
    assert [f['mapping']['generated_frame_index'] for f in frames[-15:]]==list(range(1,16))
    assert frames[93]['mapping']['retained_frame_index']==0 and frames[93]['mapping']['generated_frame_index']==1
    contributions=plan_scene_contributions(clips,upscaled,setup['timeline'])
    assert [f['image'] for f in contributions[:200]]==[f['output'] for f in frames]


def test_later_frame_pending_raw_conflict_and_orphan_body_prevent_all_earlier_new_posts(runtime_run,tmp_path,monkeypatch):
    from copy import deepcopy
    from uuid import uuid4
    from video_ai.runtime.production_scene_upscale import produce_scene_upscaled_clips,_extract,_copy
    from video_ai.runtime.scene_media_records import scene_media_context
    from video_ai.runtime.scene_upscale_transactions import recover_or_submit_scene_frame
    from video_ai.runtime._scene_upscale_records import graph_for,expected_request
    from video_ai.runtime.production_state import RunLock
    setup=prepared_scene_sources(runtime_run,tmp_path,monkeypatch); backend=OfflineUpscale(setup)
    run=setup['run']
    def produce(): return produce_scene_upscaled_clips(setup['frozen'],setup['units'],setup['timeline'],paths=setup['paths'],logger=setup['logger'],**backend.kwargs)
    with RunLock(run) as lock:
        context=scene_media_context(setup['frozen'],setup['units'],setup['timeline'],paths=setup['paths'],lock=lock)
        store=context['store']; row=context['rows'][-1]; folder=store.frame_dir(row['frame_id'])
        orphan=folder/'http'/(str(uuid4())+'.body'); orphan.parent.mkdir(parents=True); orphan.write_bytes(b'')
    result=produce()
    assert result.status=='blocked' and not backend.posts and backend.ensures==0
    orphan.unlink()
    with RunLock(run) as lock:
        context=scene_media_context(setup['frozen'],setup['units'],setup['timeline'],paths=setup['paths'],lock=lock)
        store=context['store']; store.write('inputs.json',context['inputs']); row=context['rows'][-1]
        clip=context['scene_clips']['clips'][-1]; extraction=_extract(context,clip,setup['logger'])
        image=extraction['frames'][row['retained_frame_index']]['image']; copied=_copy(context,row,'input_copy',image)
        graph=graph_for(context,row); request=expected_request(context,row,image,copied['target']); folder=store.frame_dir(row['frame_id'])
        store.write(folder/'request.json',request); store.write(folder/'graph.json',graph)
        client=backend.factory(setup['frozen'].config.services['comfyui'],request_timeout=1,ownership_check=store.capture_guard(request,graph))
        history=client.history
        def conflicting(prompt_id=None,*,timeout):
            response=history(prompt_id,timeout=timeout); value=json.loads(response['body'])
            for entry in value.values(): entry['prompt'][2]={}
            return backend.response(value)
        client.history=conflicting; original=store.write
        def interrupt_terminal(name,value):
            if str(name).endswith('terminal.json'): raise KeyboardInterrupt()
            return original(name,value)
        monkeypatch.setattr(store,'write',interrupt_terminal)
        # Reach the deliberate terminal-write interruption under the same full
        # byte guards and frozen tracking budget as the production entrypoint.
        with pytest.raises(KeyboardInterrupt):
            recover_or_submit_scene_frame(store,request,graph,client=client,template=context['template'],ensure_service=lambda:None,logger=setup['logger'],timeout=setup['frozen'].config.timeouts['upscale_frame'])
        assert len(backend.posts)==1 and not (folder/'terminal.json').exists() and not (folder/'submission.json').exists()
    before={str(p):p.read_bytes() for p in (run/'production/scene-upscale').rglob('*') if p.is_file()}
    result=produce()
    assert result.status=='blocked' and len(backend.posts)==1 and backend.ensures==0
    assert before=={str(p):p.read_bytes() for p in (run/'production/scene-upscale').rglob('*') if p.is_file()}
    from video_ai.runtime.scene_media_records import load_scene_media_progress
    progress=load_scene_media_progress(setup['frozen'],setup['units'],setup['timeline'])
    assert progress['upscale']['status']=='blocked' and progress['upscale']['record'] is None
    assert progress['upscale']['error']['evidence_paths'] and progress['upscale']['completed_items']==0
