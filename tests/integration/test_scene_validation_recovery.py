"""Real FFmpeg, original request recovery, and existing inspection reuse."""
from pathlib import Path
from contextlib import nullcontext

import pytest

from scene_validation_helpers import isolated_runtime_run as runtime_run, scene_validation_config
from integration.test_scene_upscale_flow import (
    test_accepted_local_media_receipts_restore_outer_commits_without_reextract_or_post,
    test_future_frame_conflict_stops_earlier_new_posts_and_transient_copy_keeps_original_task,
)


@pytest.fixture
def local_wan(runtime_run, tmp_path, monkeypatch):
    from scene_validation_helpers import real_wan
    return real_wan(runtime_run, tmp_path, monkeypatch)


@pytest.mark.parametrize('reuse', [False, True])
def test_real_generated_receipt_recovers_without_second_post(local_wan, monkeypatch, reuse):
    from scene_clip_helpers import generate
    from video_ai.media import video
    from video_ai.runtime.scene_validation_pass import scene_validation_pass, candidate_scene_validation
    from video_ai.runtime.local_video_metrics import LocalVideoMetrics
    setup, backend = local_wan
    original = video.trim_scene_video
    def interrupted(*args, **kwargs):
        raise RuntimeError('interrupt after generated receipt')
    monkeypatch.setattr(video, 'trim_scene_video', interrupted)
    scope = lambda: candidate_scene_validation() if reuse else scene_validation_pass(reuse=False)
    with scope(): result = generate(setup, backend)
    assert result.status == 'failed', result.error
    cid = setup['plan']['clips'][0]['clip_id']; folder = setup['run']/'production/scene-clips'/cid
    assert (folder/'media-ready/generated.json').exists()
    saved = (folder/'submission.json').read_bytes(); posts = len(backend.posts)
    generated = (folder/'generated.mp4').read_bytes()
    monkeypatch.setattr(video, 'trim_scene_video', original)
    with LocalVideoMetrics(mode='recovery') as metrics, scope():
        restored = generate(setup, backend)
    assert restored.status == 'awaiting_continuity_review', restored.error
    assert len(backend.posts) == posts
    assert (folder/'submission.json').read_bytes() == saved
    assert (folder/'generated.mp4').read_bytes() == generated
    assert metrics.report()['totals']['probe_processes'] > 0
    # A new public invocation reauthenticates completed media without a producer.
    backend.factory = lambda *a, **kw: pytest.fail('completed request must not submit')
    with scope(): completed = generate(setup, backend)
    assert completed.status == 'awaiting_continuity_review', completed.error


def test_completed_media_identity_and_frame_count_reject_tamper(local_wan):
    from scene_clip_helpers import generate
    setup, backend = local_wan
    assert generate(setup, backend).status == 'awaiting_continuity_review'
    root = setup['run']/'production/scene-clips'
    source = next(root.glob('*/source.mp4'))
    stamp = source.stat(); raw = source.read_bytes()
    source.write_bytes(bytes([raw[0] ^ 1])+raw[1:])
    import os
    os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    posts = len(backend.posts)
    result = generate(setup, backend)
    assert result.status == 'blocked', result.error
    assert len(backend.posts) == posts
