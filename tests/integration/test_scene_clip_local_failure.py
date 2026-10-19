def test_transient_trim_failure_recovers_original_submission_without_terminal(runtime_run,tmp_path,monkeypatch):
    from scene_clip_helpers import prepared_wan,OfflineWan,generate
    from video_ai.media import video
    s=prepared_wan(runtime_run,tmp_path,monkeypatch);backend=OfflineWan(s)
    cid=s['plan']['clips'][0]['clip_id'];folder=s['run']/'production/scene-clips'/cid
    original=video.trim_scene_video
    failed=False
    def temporary(*args,**kwargs):
        nonlocal failed
        if not failed:
            failed=True
            raise RuntimeError('temporary encoder unavailable after valid generated receipt')
        return original(*args,**kwargs)
    monkeypatch.setattr(video,'trim_scene_video',temporary)
    result=generate(s,backend)
    assert result.status=='failed',result.error
    assert (folder/'media-ready/generated.json').exists()
    assert not (folder/'terminal.json').exists()
    submitted=len(backend.posts)
    resumed=generate(s,backend)
    assert resumed.status=='awaiting_continuity_review',resumed.error
    assert len(backend.posts)==submitted
    assert (folder/'clip.json').exists()


def test_failed_raw_observation_survives_interruption_before_rejection_receipt(runtime_run,tmp_path,monkeypatch):
    from pathlib import Path
    from scene_clip_helpers import prepared_wan,OfflineWan,generate,observation
    import video_ai.runtime.production_scene_clips as module
    s=prepared_wan(runtime_run,tmp_path,monkeypatch,long_scene=True);backend=OfflineWan(s)
    first=generate(s,backend);template=first.observation_templates[0];folder=Path(template).parent
    fired=[]
    def interrupt(point):
        if point=='observation-original' and not fired:
            fired.append(point);raise KeyboardInterrupt('failed original durable, rejected marker absent')
    monkeypatch.setattr(module,'boundary',interrupt)
    result,_,_=observation(s,template,verdict='failed')
    assert result.status=='interrupted' and fired
    assert len(list((folder/'observations').glob('*.json')))==1
    assert not (folder/'observation-rejected.json').exists()
    attempted,_,_=observation(s,template)
    assert attempted.status=='blocked',attempted.error
    assert not (folder/'observation-accepted.json').exists()
    resumed=generate(s,backend)
    assert resumed.status=='blocked' and resumed.scenes[0]['status']=='continuity_failed',resumed.error
    assert (folder/'observation-rejected.json').exists()
    assert not (folder.parent/'scene_0001_clip_0002/intent.json').exists()
    assert len(backend.posts)==3
