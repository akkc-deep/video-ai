"""Decoded native16 media and retained-frame evidence using real FFmpeg."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import pytest


@pytest.fixture
def media_context(runtime_run):
    from video_ai.config import load_config
    from video_ai.runtime.logging import RunLogger
    run, config, paths = runtime_run
    actual = load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    config = replace(config, tools=dict(config.tools, ffmpeg=actual.tools['ffmpeg'],
                                      ffprobe=actual.tools['ffprobe']))
    return run, dict(config=config, paths=paths, logger=RunLogger(run),
                     unit_id='shot_0001:attempt_0001')


def make_video(context, *, frames=69, fps=16, width=128, height=72,
               audio=False, vfr=False, name='generated.mp4'):
    from video_ai.runtime.environment import build_child_env
    from video_ai.runtime.processes import run_logged
    run, kwargs = context
    target = run / name
    args = [kwargs['config'].tools['ffmpeg'], '-nostdin', '-n', '-v', 'error',
            '-f', 'lavfi', '-i', f'testsrc2=size={width}x{height}:rate={fps}']
    if audio:
        args += ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000']
    if vfr:
        args += ['-vf', "select='not(eq(n,10))'", '-fps_mode', 'passthrough']
    args += ['-frames:v', str(frames), '-c:v', 'libx264', '-pix_fmt', 'yuv420p']
    args += ['-c:a', 'aac', '-shortest'] if audio else ['-an']
    args += ['-movflags', '+faststart', target]
    result = run_logged(tuple(str(a) for a in args), cwd=run,
                        env=build_child_env(kwargs['paths']), timeout=300,
                        logger=kwargs['logger'], stage='test_fixture', unit_id=kwargs['unit_id'])
    assert result.returncode == 0 and not result.timed_out, result.stderr_path.read_text()
    return target


@pytest.fixture
def valid_probe(media_context):
    from video_ai.media import video
    path = make_video(media_context)
    _, evidence = video.inspect_video(path, width=128, height=72, **media_context[1])
    record = json.loads(evidence[0].read_text())
    return record['probe'], record['frames']


def test_real_69_frames_trim_to_68_with_complete_evidence(media_context):
    from video_ai.media import video
    run, kwargs = media_context
    source = make_video(media_context)
    before = source.read_bytes()
    info, evidence = video.inspect_video(source, width=128, height=72, **kwargs)
    assert set(info) == {'identity', 'width', 'height', 'codec', 'pixel_format', 'fps', 'frames', 'duration'}
    assert (info['fps'], info['frames']) == (16, 69)
    assert abs(info['duration'] - 4.3125) <= .1
    record = json.loads(evidence[0].read_text())
    assert set(record) == {'info', 'probe', 'frames', 'commands'}
    assert record['info'] == info
    assert len(record['commands']) == 3
    assert len(record['frames']['frames']) == 69
    assert record['frames']['frames'][-1]['best_effort_timestamp'] == 69632
    assert len(evidence) == 7 and len(set(evidence)) == 7
    for command in record['commands']:
        assert command['returncode'] == 0 and command['timed_out'] is False
        assert Path(command['stdout_path']) in evidence and Path(command['stderr_path']) in evidence
    assert '-show_frames' in record['commands'][1]['args']
    assert record['commands'][2]['args'][1:] == [
        '-nostdin', '-v', 'error', '-xerror', '-i', str(source), '-f', 'null', '-']
    pure = video.validate_video_probe(record['probe'], record['frames'], width=128, height=72)
    assert pure == {key: value for key, value in info.items() if key != 'identity'}
    target = run / 'shots' / 'shot_0001' / 'source.mp4'
    trimmed, trim_evidence = video.trim_video(source, target, frames=68, width=128, height=72, **kwargs)
    assert (trimmed['frames'], trimmed['codec'], trimmed['pixel_format']) == (68, 'h264', 'yuv420p')
    assert abs(trimmed['duration'] - 4.25) <= .1
    assert source.read_bytes() == before
    trim_records = [json.loads(p.read_text()) for p in trim_evidence if p.name.startswith('trim-')]
    assert len(trim_records) == 1
    trim = trim_records[0]
    assert set(trim) == {'source', 'target', 'frames', 'filter', 'command'}
    assert trim['source']['identity']['sha256'] == info['identity']['sha256']
    assert trim['source']['frames'] == 69 and trim['target'] == trimmed and trim['frames'] == 68
    assert trim['filter'] == 'trim=start_frame=0:end_frame=68,setpts=N/(16*TB)'
    args = trim['command']['args']
    for flag, value in [('-vf', trim['filter']), ('-c:v', 'libx264'), ('-preset', 'medium'),
                        ('-crf', '18'), ('-pix_fmt', 'yuv420p'), ('-fps_mode', 'passthrough')]:
        assert args[args.index(flag)+1] == value
    assert '-an' in args and '-n' in args
    assert all(p.is_file() and p.is_relative_to(run / 'logs') for p in trim_evidence)
    events = [json.loads(line) for line in (run/'logs/events.jsonl').read_text().splitlines()]
    media_events = [e for e in events if e['stage'] == 'source_clips']
    assert media_events and all(e['unit_id'] == kwargs['unit_id'] for e in media_events)
    assert all(0 < e['details']['timeout'] <= 300 for e in media_events)


@pytest.mark.parametrize('frames', [1, 65, 73])
def test_valid_short_or_long_media_has_its_actual_count(media_context, frames):
    from video_ai.media import video
    source = make_video(media_context, frames=frames)
    info, _ = video.inspect_video(source, width=128, height=72, **media_context[1])
    assert info['frames'] == frames and abs(info['duration'] - frames / 16) <= .1


@pytest.mark.parametrize('options', [dict(fps=24), dict(width=144), dict(audio=True), dict(vfr=True)])
def test_real_wrong_fps_dimensions_audio_or_vfr_rejected(media_context, options):
    from video_ai.media import video
    source = make_video(media_context, **options)
    with pytest.raises(ValueError):
        video.inspect_video(source, width=128, height=72, **media_context[1])


def test_corrupt_video_rejected_with_raw_evidence(media_context):
    from video_ai.media import video
    run, kwargs = media_context
    source = make_video(media_context)
    source.write_bytes(source.read_bytes()[:source.stat().st_size // 2])
    with pytest.raises((RuntimeError, ValueError)):
        video.inspect_video(source, width=128, height=72, **kwargs)
    assert list((run / 'logs/processes').glob('*.stderr'))


@pytest.mark.parametrize('field,value', [('nb_read_frames', 'N/A'), ('nb_read_frames', '0'),
    ('nb_read_frames', True), ('nb_read_frames', 69.0), ('nb_read_frames', '68'),
    ('nb_frames', '68'), ('avg_frame_rate', '16.0000001'), ('r_frame_rate', '32/1'),
    ('width', True), ('height', 72.0), ('duration', 'NaN'), ('duration', '4.5'),
    ('time_base', '0/1'), ('codec_name', 'hevc')])
def test_pure_probe_rejects_unreliable_counts_rates_and_metadata(valid_probe, field, value):
    from video_ai.media.video import validate_video_probe
    probe, frames = deepcopy(valid_probe)
    probe['streams'][0][field] = value
    with pytest.raises(ValueError):
        validate_video_probe(probe, frames, width=128, height=72)


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'gap', 'disagree', 'count', 'bool', 'float', 'wrong_stream', 'duration'])
def test_pure_probe_checks_every_frame_and_exact_pts(valid_probe, fault):
    from video_ai.media.video import validate_video_probe
    probe, frames = deepcopy(valid_probe)
    frame = frames['frames'][40]
    if fault == 'missing':
        frame.pop('best_effort_timestamp', None)
        frame.pop('pts', None)
    elif fault in ('duplicate', 'gap'):
        for key in ('best_effort_timestamp', 'pts'):
            frame[key] += -1024 if fault == 'duplicate' else 1
    elif fault == 'disagree':
        frame['best_effort_timestamp'] += 1
    elif fault == 'count':
        frames['frames'].pop()
    elif fault in ('bool', 'float'):
        frame['best_effort_timestamp'] = True if fault == 'bool' else float(frame['best_effort_timestamp'])
    elif fault == 'wrong_stream':
        frame['stream_index'] = 1
    else:
        frame['pkt_duration'] = 2048
        frame['duration'] = 2048
    with pytest.raises(ValueError):
        validate_video_probe(probe, frames, width=128, height=72)


def test_pure_probe_rejects_container_duration_and_extra_stream(valid_probe):
    from video_ai.media.video import validate_video_probe
    probe, frames = deepcopy(valid_probe)
    probe['format']['duration'] = '100'
    with pytest.raises(ValueError):
        validate_video_probe(probe, frames, width=128, height=72)
    probe, frames = deepcopy(valid_probe)
    probe['streams'].append(dict(codec_type='audio'))
    with pytest.raises(ValueError):
        validate_video_probe(probe, frames, width=128, height=72)


@pytest.mark.parametrize('frames', [0, True, 68.0, 70])
def test_trim_refuses_invalid_count_or_insufficient_source(media_context, frames):
    from video_ai.media.video import trim_video
    run, kwargs = media_context
    source = make_video(media_context)
    target = run / 'source.mp4'
    with pytest.raises(ValueError):
        trim_video(source, target, frames=frames, width=128, height=72, **kwargs)
    assert not target.exists()


def test_paths_and_existing_target_refused_before_commands(media_context):
    from video_ai.media.video import inspect_video, trim_video
    run, kwargs = media_context
    source = make_video(media_context)
    target = run / 'source.mp4'
    target.write_bytes(b'preserve')
    before = set((run/'logs/processes').iterdir())
    with pytest.raises(FileExistsError):
        trim_video(source, target, frames=68, width=128, height=72, **kwargs)
    for outside in [run.parent / 'escape.mp4', run / '..' / 'escape.mp4', run / 'alias.mp4:extra']:
        with pytest.raises(ValueError):
            trim_video(source, outside, frames=68, width=128, height=72, **kwargs)
        with pytest.raises(ValueError):
            inspect_video(outside, width=128, height=72, **kwargs)
    assert target.read_bytes() == b'preserve'
    assert set((run/'logs/processes').iterdir()) == before


def test_inspection_detects_source_change_during_decode(media_context, monkeypatch):
    from video_ai.media import video
    source = make_video(media_context)
    original = video.run_logged
    def changing_command(*args, **kwargs):
        result = original(*args, **kwargs)
        if '-xerror' in args[0]:
            source.write_bytes(source.read_bytes() + b'drift')
        return result
    monkeypatch.setattr(video, 'run_logged', changing_command)
    with pytest.raises(OSError):
        video.inspect_video(source, width=128, height=72, **media_context[1])


def test_paths_refuse_alias_within_current_run_before_commands(media_context):
    from video_ai.media.video import inspect_video, trim_video
    run, kwargs = media_context
    source = make_video(media_context)
    alias = run / 'subdir' / '..' / source.name
    before = set((run / 'logs/processes').iterdir())
    with pytest.raises(ValueError):
        inspect_video(alias, width=128, height=72, **kwargs)
    with pytest.raises(ValueError):
        trim_video(source, run / 'subdir' / '..' / 'source.mp4', frames=68, width=128, height=72, **kwargs)
    assert set((run / 'logs/processes').iterdir()) == before


def test_trim_rechecks_source_after_conversion(media_context, monkeypatch):
    from video_ai.media import video
    run, kwargs = media_context
    source = make_video(media_context)
    original = video.run_logged
    def changing_command(*args, **kwargs):
        result = original(*args, **kwargs)
        if '-vf' in args[0]:
            source.write_bytes(source.read_bytes() + b'drift')
        return result
    monkeypatch.setattr(video, 'run_logged', changing_command)
    with pytest.raises(OSError):
        video.trim_video(source, run / 'source.mp4', frames=68, width=128, height=72, **kwargs)


@pytest.mark.parametrize('width,height', [(768,432), (1280,720)])
def test_equal_count_still_runs_frame_trim_for_both_profiles(media_context, width, height):
    from video_ai.media.video import trim_video
    run, kwargs = media_context
    source = make_video(media_context, frames=3, width=width, height=height)
    result, evidence = trim_video(source, run / 'source.mp4', frames=3,
                                  width=width, height=height, **kwargs)
    assert (result['width'], result['height'], result['frames']) == (width, height, 3)
    trim = json.loads(evidence[0].read_text())
    assert '-vf' in trim['command']['args'] and trim['command']['returncode'] == 0


def test_full_decode_failure_cannot_be_replaced_by_probe_counts(media_context):
    from video_ai.media.video import inspect_video
    run, kwargs = media_context
    source = make_video(media_context)
    damaged = bytearray(source.read_bytes())
    payload = damaged.index(b'mdat') + 4
    damaged[payload + 2000:payload + 3000] = b'\xff' * 1000
    source.write_bytes(damaged)
    with pytest.raises(RuntimeError, match='command failed'):
        inspect_video(source, width=128, height=72, **kwargs)
    events = [json.loads(line) for line in (run/'logs/events.jsonl').read_text().splitlines()]
    decodes = [e['details'] for e in events if e['event'] == 'command_finished'
               and e['stage'] == 'source_clips' and '-xerror' in e['details']['args']]
    assert len(decodes) == 1 and decodes[0]['returncode'] != 0
    assert Path(decodes[0]['stderr_path']).stat().st_size > 0


def test_upscale_video_stage_and_total_trim_budget(media_context,monkeypatch):
    from video_ai.media import video
    run,kwargs=media_context;source=make_video(media_context,frames=3)
    clock=[100.];original=video.run_logged
    def command(*args,**kw):
        result=original(*args,**kw);clock[0]+=1;return result
    monkeypatch.setattr(video,'run_logged',command)
    monkeypatch.setattr(video,'monotonic',lambda:clock[0],raising=False)
    info,evidence=video.trim_video(source,run/'upscaled.mp4',frames=3,width=128,height=72,
                                   stage='upscale',timeout=10,**kwargs)
    assert info['frames']==3
    assert all(p.parent==run/'logs/upscale' for p in evidence if p.suffix=='.json')
    events=[json.loads(l) for l in (run/'logs/events.jsonl').read_text().splitlines()]
    starts=[e for e in events if e['event']=='command_started' and e['stage']=='upscale']
    assert [e['details']['timeout'] for e in starts]==[10,9,8,7,6,5,4]
    assert all(e['unit_id']==kwargs['unit_id'] for e in starts)


def test_video_rejects_success_after_total_budget_expires(media_context,monkeypatch):
    from video_ai.media import video
    source=make_video(media_context,frames=3);clock=[100.];original=video.run_logged
    def command(*args,**kw):
        result=original(*args,**kw);clock[0]+=4;return result
    monkeypatch.setattr(video,'run_logged',command)
    monkeypatch.setattr(video,'monotonic',lambda:clock[0],raising=False)
    with pytest.raises(TimeoutError):video.inspect_video(source,width=128,height=72,stage='upscale',timeout=10,**media_context[1])
