"""Native16 decoded video validation and frame trimming with raw command evidence."""
from fractions import Fraction
from pathlib import Path
import re
from time import monotonic

from .images import _deadline, _remaining, _record_name as _media_record_name
from ..adapters.common import positive_timeout

from ..config import read_json
from ..runtime.environment import build_child_env
from ..runtime.manifest import hash_file, thaw
from ..runtime.processes import run_logged
from ..runtime.timeline_checks import _again, _local


def _integer(value, label, *, minimum=0):
    if isinstance(value, str) and re.fullmatch(r'-?[0-9]+', value):
        value = int(value)
    if type(value) is not int or value < minimum:
        raise ValueError(f'{label}: reliable integer required')
    return value


def _fraction(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'-?[0-9]+(?:/[0-9]+|\.[0-9]+)?', value):
        raise ValueError(f'{label}: reliable rational required')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f'{label}: invalid rational') from exc


def _dimensions(width, height):
    if any(type(v) is not int or v <= 0 for v in (width, height)):
        raise ValueError('video dimensions must be positive integers')


def validate_video_probe(probe: dict, frame_data: dict, *, width: int, height: int) -> dict:
    """Validate decoded count, every PTS, and duration without reading any files."""
    _dimensions(width, height)
    if not isinstance(probe, dict) or not isinstance(frame_data, dict):
        raise ValueError('video probe and frame data must be objects')
    streams = probe.get('streams')
    if not isinstance(streams, list) or len(streams) != 1 or not isinstance(streams[0], dict):
        raise ValueError('exactly one h264 video stream and no audio required')
    stream = streams[0]
    if stream.get('codec_type') != 'video' or stream.get('codec_name') != 'h264':
        raise ValueError('exactly one h264 video stream and no audio required')
    if any(type(stream.get(k)) is not int or stream[k] != expected
           for k, expected in (('width', width), ('height', height))):
        raise ValueError('video dimensions differ from target')
    pixel_format = stream.get('pix_fmt')
    if not isinstance(pixel_format, str) or not pixel_format or pixel_format == 'unknown':
        raise ValueError('known video pixel format required')
    for key in ('r_frame_rate', 'avg_frame_rate'):
        if _fraction(stream.get(key), key) != 16:
            raise ValueError('native16 frame rate required')
    count = _integer(stream.get('nb_read_frames'), 'decoded frame count', minimum=1)
    if 'nb_frames' in stream and stream['nb_frames'] != 'N/A':
        if _integer(stream['nb_frames'], 'header frame count', minimum=1) != count:
            raise ValueError('header count differs from decoded frame count')
    time_base = _fraction(stream.get('time_base'), 'time base')
    if time_base <= 0:
        raise ValueError('positive time base required')
    frames = frame_data.get('frames')
    if not isinstance(frames, list) or len(frames) != count:
        raise ValueError('all-frame count differs from decoded frame count')
    stream_index = _integer(stream.get('index'), 'stream index')
    previous = None
    for frame in frames:
        if not isinstance(frame, dict) or frame.get('media_type') != 'video':
            raise ValueError('all frames must belong to the video stream')
        if _integer(frame.get('stream_index'), 'frame stream index') != stream_index:
            raise ValueError('frame belongs to a different stream')
        timestamps = [_integer(frame[key], key, minimum=-(2**63))
                      for key in ('best_effort_timestamp', 'pts') if key in frame]
        if not timestamps or len(set(timestamps)) != 1:
            raise ValueError('reliable consistent frame PTS required')
        pts = timestamps[0] * time_base
        if previous is not None and pts - previous != Fraction(1, 16):
            raise ValueError('every PTS must strictly increase at CFR16')
        previous = pts
        for key in ('duration', 'pkt_duration'):
            if key in frame and _integer(frame[key], key, minimum=1) * time_base != Fraction(1, 16):
                raise ValueError('frame duration differs from CFR16')
        for key, expected in (('width', width), ('height', height)):
            if key in frame and (type(frame[key]) is not int or frame[key] != expected):
                raise ValueError('decoded frame dimensions changed')
        if 'pix_fmt' in frame and frame['pix_fmt'] != pixel_format:
            raise ValueError('decoded frame pixel format changed')
    container = probe.get('format')
    if not isinstance(container, dict) or 'mp4' not in str(container.get('format_name', '')).split(','):
        raise ValueError('MP4 container required')
    expected_duration = Fraction(count, 16)
    durations = []
    for record in (stream, container):
        if 'duration' in record:
            duration = _fraction(record['duration'], 'video duration')
            if duration <= 0 or abs(duration - expected_duration) > Fraction(1, 10):
                raise ValueError('video duration differs from decoded count / 16')
            durations.append(duration)
    if not durations:
        raise ValueError('reliable video duration required')
    if 'duration_ts' in stream:
        duration_ts = _integer(stream['duration_ts'], 'stream duration ticks', minimum=1) * time_base
        if abs(duration_ts - expected_duration) > Fraction(1, 10):
            raise ValueError('stream duration ticks differ from decoded count / 16')
    return dict(width=width, height=height, codec='h264', pixel_format=pixel_format,
                fps=16, frames=count, duration=float(durations[0]))


def _record_name(logger, prefix, unit_id, stage='source_clips'):
    return _media_record_name(logger,prefix,unit_id,stage)


def _video_path(path, logger, paths):
    path = _local(logger.run_dir, Path(path))
    paths.policy.validate_write(path, 'run')
    if path.suffix.lower() != '.mp4':
        raise ValueError('video path must name an MP4')
    return path


def _command(args, *, paths, logger, unit_id, stage='source_clips', timeout=300):
    result = run_logged(tuple(str(a) for a in args), cwd=logger.run_dir,
                        env=build_child_env(paths), timeout=min(300,positive_timeout(timeout)), logger=logger,
                        stage=stage, unit_id=unit_id)
    if result.returncode != 0 or result.timed_out:
        raise RuntimeError(f'{unit_id}: video command failed: {result.stderr_path}')
    return result


def inspect_video(path, *, width, height, config, paths, logger, unit_id, stage='source_clips', timeout=300):
    deadline=_deadline(timeout,monotonic())
    _dimensions(width, height)
    path = _video_path(path, logger, paths)
    name = _record_name(logger, 'video', unit_id, stage)
    identity = hash_file(path)
    kwargs = dict(paths=paths, logger=logger, unit_id=unit_id,stage=stage)
    probe = _command((config.tools['ffprobe'], '-v', 'error', '-count_frames',
                      '-show_streams', '-show_format', '-of', 'json', path), timeout=_remaining(deadline,monotonic()), **kwargs)
    frames = _command((config.tools['ffprobe'], '-v', 'error', '-show_frames',
                       '-of', 'json', path), timeout=_remaining(deadline,monotonic()), **kwargs)
    decode = _command((config.tools['ffmpeg'], '-nostdin', '-v', 'error', '-xerror',
                       '-i', path, '-f', 'null', '-'), timeout=_remaining(deadline,monotonic()), **kwargs)
    _again({'video': identity})
    data, frame_data = read_json(probe.stdout_path), read_json(frames.stdout_path)
    metadata = validate_video_probe(data, frame_data, width=width, height=height)
    info = dict(identity=thaw(identity), **metadata)
    commands = (probe, frames, decode)
    record = logger.save_json(name, dict(info=info, probe=data, frames=frame_data,
                                        commands=[thaw(c) for c in commands]))
    _remaining(deadline,monotonic())
    return info, [record, *[p for c in commands for p in (c.stdout_path, c.stderr_path)]]


def trim_video(source, target, *, frames, width, height, config, paths, logger, unit_id, stage='source_clips', timeout=300):
    deadline=_deadline(timeout,monotonic())
    _dimensions(width, height)
    if type(frames) is not int or frames <= 0:
        raise ValueError('retained frame count must be a positive integer')
    source = _video_path(source, logger, paths)
    target = _video_path(target, logger, paths)
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    name = _record_name(logger, 'trim', unit_id,stage)
    kwargs = dict(config=config, paths=paths, logger=logger, unit_id=unit_id,stage=stage)
    source_info, evidence = inspect_video(source, width=width, height=height, timeout=_remaining(deadline,monotonic()), **kwargs)
    if source_info['frames'] < frames:
        raise ValueError('source has insufficient decoded frames to trim')
    source_identity = hash_file(source)
    if (source_identity.bytes, source_identity.mtime_ns, source_identity.sha256) != tuple(
            source_info['identity'][key] for key in ('bytes', 'mtime_ns', 'sha256')):
        raise OSError('source changed before trim')
    target.parent.mkdir(parents=True, exist_ok=True)
    filter_value = f'trim=start_frame=0:end_frame={frames},setpts=N/(16*TB)'
    command = _command((config.tools['ffmpeg'], '-nostdin', '-n', '-v', 'error', '-xerror',
                        '-i', source, '-vf', filter_value, '-an', '-c:v', 'libx264',
                        '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p',
                        '-fps_mode', 'passthrough', target), paths=paths, logger=logger, unit_id=unit_id,stage=stage,timeout=_remaining(deadline,monotonic()))
    result, more = inspect_video(target, width=width, height=height, timeout=_remaining(deadline,monotonic()), **kwargs)
    _again({'source': source_identity})
    if result['frames'] != frames or result['pixel_format'] != 'yuv420p':
        raise ValueError('trim target must have exactly the retained frames and yuv420p')
    record = logger.save_json(name, dict(source=source_info, target=result, frames=frames,
                                        filter=filter_value, command=thaw(command)))
    _remaining(deadline,monotonic())
    return result, [record, *evidence, command.stdout_path, command.stderr_path, *more]


def inspect_production_video(path, *, width, height, config, paths, logger, unit_id, stage='source_clips', timeout=300):
    """Decode/count/PTS once on first consumption; large media has only a stamp."""
    from ..runtime.production_state import ArtifactStamp
    path=_video_path(path,logger,paths);stamp=ArtifactStamp.read(path)
    kwargs=dict(paths=paths,logger=logger,unit_id=unit_id,stage=stage,timeout=timeout)
    probe=_command((config.tools['ffprobe'],'-v','error','-count_frames','-show_streams','-show_format','-of','json',path),**kwargs)
    frames=_command((config.tools['ffprobe'],'-v','error','-show_frames','-of','json',path),**kwargs)
    stamp.verify()
    data,frame_data=read_json(probe.stdout_path),read_json(frames.stdout_path)
    info=dict(stamp=stamp.to_dict(),**validate_video_probe(data,frame_data,width=width,height=height))
    record=logger.save_json(_record_name(logger,'video',unit_id,stage),dict(info=info,probe=data,frames=frame_data,commands=thaw((probe,frames))))
    return info,[record,probe.stdout_path,probe.stderr_path,frames.stdout_path,frames.stderr_path]


def trim_production_video(source,target,*,source_info,frames,width,height,config,paths,logger,unit_id,stage='source_clips',timeout=300):
    from ..runtime.production_state import ArtifactStamp,sync_file
    _integer(frames,'frames',minimum=1)
    source=_video_path(source,logger,paths);target=_video_path(target,logger,paths)
    before=ArtifactStamp.from_dict(source_info['stamp']);before.verify()
    if before.path!=str(source) or source_info['frames']<frames:raise ValueError('source insufficient for retained frames')
    if target.exists():raise FileExistsError(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    filter_value=f'trim=start_frame=0:end_frame={frames},setpts=N/(16*TB)'
    command=_command((config.tools['ffmpeg'],'-nostdin','-n','-v','error','-xerror','-i',source,'-vf',filter_value,
                      '-an','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough',target),
                     paths=paths,logger=logger,unit_id=unit_id,stage=stage,timeout=timeout)
    sync_file(target);before.verify()
    info,evidence=inspect_production_video(target,width=width,height=height,config=config,paths=paths,logger=logger,unit_id=unit_id,stage=stage,timeout=timeout)
    if info['frames']!=frames or info['pixel_format']!='yuv420p':raise ValueError('trim target frame count/pixel format differs')
    record=logger.save_json(_record_name(logger,'trim',unit_id,stage),dict(source=source_info,target=info,frames=frames,filter=filter_value,command=thaw(command)))
    return info,[record,command.stdout_path,command.stderr_path,*evidence]
