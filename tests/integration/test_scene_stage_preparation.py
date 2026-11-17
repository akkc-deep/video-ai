"""Candidate uses unchanged locked transactions and real FFmpeg receipts."""
from contextlib import nullcontext
import json
from pathlib import Path
from threading import get_ident

import pytest

from scene_validation_helpers import isolated_runtime_run, scene_validation_config


@pytest.mark.parametrize('candidate',[False,True])
def test_phase_recovery_keeps_media_ids_and_closes_before_review(isolated_runtime_run,tmp_path,monkeypatch,candidate):
    from scene_validation_helpers import real_wan, validation_counters
    from scene_clip_helpers import generate
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from video_ai.runtime.scene_stage_preparation import candidate_scene_preparation
    setup, backend = real_wan(isolated_runtime_run,tmp_path,monkeypatch)
    owner = get_ident(); writes = []; original = SceneClipStore.write_bytes
    def write(store,*args,**kw):
        writes.append(get_ident())
        return original(store,*args,**kw)
    monkeypatch.setattr(SceneClipStore,'write_bytes',write)
    scope = candidate_scene_preparation if candidate else nullcontext
    with scope(): result = generate(setup,backend)
    assert result.status == 'awaiting_continuity_review',result.error
    assert backend.closes == 1
    assert writes and set(writes)=={owner}
    directory = setup['run']/'logs/production/scene-clips/performance'
    reports = list(directory.glob('*.json'))
    assert len(reports)==1
    report = json.loads(reports[0].read_bytes())
    assert report['counts']['actual_start']==report['counts']['close']==1
    assert report['preparation']['peak_jobs'] <= 1
    assert report['candidate'] == candidate
    if candidate:
        assert report['preparation']['submitted'] >= 1
        assert report['preparation']['consumed'] >= 1,report['preparation']
    root = setup['run']/'production/scene-clips'
    identity = {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    posts = len(backend.posts); closes = backend.closes
    with validation_counters() as counts,scope(): recovered = generate(setup,backend)
    assert recovered.status == result.status,recovered.error
    assert len(backend.posts)==posts and backend.closes==closes
    assert counts['producer_invocations']==0
    assert identity == {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
