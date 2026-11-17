from unit.test_frames import media_context, make_video
from unit.test_production_inputs import production_config


def test_real_media_probe_decode_and_readonly_replay(media_context):
    from video_ai.media.video import inspect_video, inspection_reuse
    from video_ai.runtime.local_video_metrics import LocalVideoMetrics
    from video_ai.runtime.manifest import hash_file
    run, kwargs = media_context
    source = make_video(media_context, frames=3)
    before = hash_file(source)
    with LocalVideoMetrics(mode='normal') as normal:
        with inspection_reuse():
            first, _ = inspect_video(source, width=128, height=72, **kwargs)
            second, _ = inspect_video(source, width=128, height=72, **kwargs)
    assert first['identity']['sha256'] == second['identity']['sha256']
    assert {k: v for k, v in first.items() if k != 'identity'} == {k: v for k, v in second.items() if k != 'identity'}
    report = normal.report()
    assert report['totals']['probe_processes'] == 2
    assert report['totals']['full_decode_processes'] == 3  # two frame probes plus FFmpeg
    inspections = [r for r in report['calls'] if r['source'].endswith(':inspect_video')]
    assert len(inspections) == 2
    assert inspections[0]['counters']['full_decode_processes'] == 3
    assert inspections[1]['counters']['full_decode_processes'] == 0
    with LocalVideoMetrics(mode='recovery') as recovery:
        restored = hash_file(source)
    assert restored.sha256 == before.sha256
    assert recovery.report()['totals']['full_decode_processes'] == 0
    assert recovery.report()['totals']['probe_processes'] == 0
    assert hash_file(source).sha256 == before.sha256


def test_authentic_generation_and_recovery_keep_original_tasks(runtime_run, production_config, tmp_path, monkeypatch):
    import json
    import shutil
    from video_ai.config import load_config
    from pathlib import Path
    from scene_clip_helpers import prepared_wan, OfflineWan, generate
    from video_ai.runtime.local_video_metrics import LocalVideoMetrics, write_report
    actual = load_config(Path('E:/VideoAI/shared/config/production.json'))
    for key in ('ffmpeg', 'ffprobe'):
        shutil.copyfile(actual.tools[key], production_config.tools[key])
    # Actual executables under the isolated fixture's permitted tool roots.
    setup = prepared_wan((runtime_run[0], production_config, runtime_run[2]), tmp_path, monkeypatch)
    backend = OfflineWan(setup)
    with LocalVideoMetrics(mode='normal') as normal:
        ready = generate(setup, backend)
    assert ready.status == 'awaiting_continuity_review', ready.error
    normal_report = normal.report()
    assert normal_report['aggregate_complete']
    assert any(':verify_global' in c['source'] for c in normal_report['calls'])
    assert any(':guard' in c['source'] for c in normal_report['calls'])
    assert normal_report['totals']['hash_computations'] > 0
    root = setup['run']/'production/scene-clips'
    originals = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    posts, gets, ensures = len(backend.posts), len(backend.gets), backend.ensures
    with LocalVideoMetrics(mode='recovery') as recovery:
        replay = generate(setup, backend)
    assert replay.status == 'awaiting_continuity_review', replay.error
    assert (len(backend.posts), len(backend.gets), backend.ensures) == (posts, gets, ensures)
    assert all(p.read_bytes() == raw for p, raw in originals.items())
    assert recovery.report()['aggregate_complete']
    assert recovery.report()['totals']['media_processes'] > 0  # re-authenticate existing bytes
    for mode, metrics in [('normal', normal), ('recovery', recovery)]:
        write_report(metrics.report(), setup['run']/('LVA-01-'+mode+'.json'))
    print(json.dumps(dict(offline_production_fixture=str(setup['run']), posts=posts,
        normal=normal_report['totals'], recovery=recovery.report()['totals'])))
