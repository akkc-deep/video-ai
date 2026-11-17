import json
import sys

import pytest


def test_real_hashes_are_distinct_from_protected_cache_requests(tmp_path):
    from video_ai.runtime.local_video_metrics import LocalVideoMetrics
    from video_ai.runtime.manifest import hash_file
    from video_ai.runtime.verification import whole_input_protection
    path = tmp_path/'api-key-SECRET-prompt.txt'
    path.write_bytes(b'private prompt and access_token=SECRET')
    with LocalVideoMetrics(mode='normal') as metrics:
        with whole_input_protection():
            first = hash_file(path)
            second = hash_file(path)
    report = metrics.report()
    assert first == second
    assert report['totals']['hash_requests'] == 2
    assert report['totals']['hash_computations'] == (1 if sys.platform == 'win32' else 2)
    assert report['totals']['hashed_bytes'] == path.stat().st_size * report['totals']['hash_computations']
    assert 'SECRET' not in json.dumps(report)
    assert str(tmp_path) not in json.dumps(report)


def test_profile_cleanup_preserves_exception_and_refuses_existing_profiler():
    from video_ai.runtime.local_video_metrics import LocalVideoMetrics
    prior = sys.getprofile()
    with pytest.raises(RuntimeError, match='secret failure'):
        with LocalVideoMetrics(mode='recovery') as metrics:
            raise RuntimeError('secret failure')
    assert sys.getprofile() is prior
    assert metrics.report()['outcome'] == 'interrupted_or_failed'
    assert 'secret failure' not in json.dumps(metrics.report())
    callback = lambda *args: None
    sys.setprofile(callback)
    try:
        with pytest.raises(RuntimeError, match='profiler'):
            with LocalVideoMetrics(mode='normal'):
                pass
        assert sys.getprofile() is callback
    finally:
        sys.setprofile(prior)


def test_events_are_bounded_and_nested_cost_is_not_added_to_wall(tmp_path):
    from video_ai.runtime.local_video_metrics import LocalVideoMetrics
    from video_ai.runtime.manifest import hash_file
    path = tmp_path/'input.bin'; path.write_bytes(b'x'*17)
    with LocalVideoMetrics(mode='recovery', max_events=2) as metrics:
        for _ in range(6):
            hash_file(path)
    report = metrics.report()
    assert len(report['calls']) == 2
    assert report['dropped_events'] > 0 and report['complete'] is False
    assert report['totals']['hash_requests'] == 6
    assert report['aggregate_complete'] is True
    assert sum(r['calls'] for r in report['callsite_totals'] if r['source'].endswith(':hash_file')) == 6
    assert all(0 <= row['self_seconds'] <= row['seconds'] for row in report['calls'])
    assert report['mode'] == 'recovery'


def test_samples_split_normal_recovery_wait_and_invalid_quality():
    from video_ai.runtime.local_video_metrics import summarize_samples
    samples = [dict(mode='normal', temperature='warm', wall_seconds=v,
                    human_wait_seconds=2, usable_video_seconds=2,
                    accepted=True, failed=False, redone=False) for v in (4, 6, 8)]
    samples += [dict(mode='recovery', temperature='warm', wall_seconds=1,
                     human_wait_seconds=0, usable_video_seconds=0,
                     accepted=False, failed=True, redone=True)]
    groups = summarize_samples(samples)
    normal = groups['normal/warm']; recovery = groups['recovery/warm']
    assert normal['clip_p50_seconds'] == 4
    assert normal['clip_p95_seconds'] == pytest.approx(5.8)
    assert normal['wall_seconds_per_usable_video_second'] == 2
    assert normal['human_wait_seconds'] == 6
    assert recovery['wall_seconds_per_usable_video_second'] is None
    assert recovery['failure_rate'] == recovery['redo_rate'] == 1
    assert summarize_samples([]) == {}
    with pytest.raises(ValueError):
        summarize_samples([dict(samples[0], human_wait_seconds=10)])
    with pytest.raises(ValueError):
        summarize_samples([dict(samples[0], wall_seconds=float('nan'))])


def test_observation_never_adds_file_reads_and_report_does_not_overwrite(tmp_path, monkeypatch):
    from video_ai.runtime.local_video_metrics import LocalVideoMetrics, write_report
    from video_ai.runtime.manifest import hash_file
    path = tmp_path/'input'; path.write_bytes(b'unchanged')
    from pathlib import Path
    original = Path.open
    calls = []
    def opened(self, *args, **kwargs):
        if self == path:
            calls.append(args)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', opened)
    hash_file(path); plain = len(calls); calls.clear()
    with LocalVideoMetrics(mode='normal') as metrics:
        hash_file(path)
    assert len(calls) == plain
    target = tmp_path/'metrics.json'
    write_report(metrics.report(), target)
    assert target.with_suffix('.md').is_file()
    with pytest.raises(FileExistsError):
        write_report(metrics.report(), target)


def test_context_rejects_reuse_and_invalid_mode():
    from video_ai.runtime.local_video_metrics import LocalVideoMetrics
    with pytest.raises(ValueError):
        LocalVideoMetrics(mode='unknown')
    metrics = LocalVideoMetrics(mode='normal')
    with metrics:
        pass
    with pytest.raises(RuntimeError):
        with metrics:
            pass


@pytest.mark.parametrize('args,full,partial', [
    (['ffmpeg.exe', '-i', 'input.mp4', '-f', 'rawvideo', '-'], 1, 0),
    (['ffmpeg.exe', '-i', 'input.mp4', '-frames:v', '1', '-f', 'rawvideo', '-'], 0, 1),
    (['ffmpeg.exe', '-i', 'input.mp4', '-vf', 'select=eq(n,5)', '-f', 'rawvideo', '-'], 0, 1),
    (['ffmpeg.exe', '-f', 'rawvideo', '-i', '-', '-c:v', 'libx264', 'out.mp4'], 0, 0),
    (['ffmpeg.exe', '-i', 'input.mp4', '-t', '1', '-f', 'null', '-'], 0, 1),
    (['ffprobe.exe', '-show_frames', 'input.mp4'], 1, 0),
    (['ffprobe.exe', '-read_intervals', '0%1', '-show_frames', 'input.mp4'], 0, 1),
])
def test_media_decode_classification_excludes_single_frames_and_input_formats(args, full, partial):
    from video_ai.runtime.local_video_metrics import classify_media_command
    counts = classify_media_command(args)
    assert counts['full_decode_processes'] == full
    assert counts['partial_decode_processes'] == partial
