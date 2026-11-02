"""Exclusive native-frame extraction and fully decoded 1080p encoding."""
from pathlib import Path
from time import monotonic

from .images import _deadline, _remaining, _record_name, inspect_image
from .video import _dimensions, _video_path, inspect_video
from ..runtime.environment import build_child_env
from ..runtime.manifest import FileIdentity, hash_file, thaw
from ..runtime.processes import run_logged
from ..runtime.timeline_checks import _again, _local
from ..runtime.execution_limits import command_timeout


def _count(value):
    if type(value) is not int or value <= 0:
        raise ValueError('frame count must be a positive integer')
    return value


def _directory(path, logger, paths):
    path=_local(logger.run_dir,Path(path))
    paths.policy.validate_write(path,'run')
    return path


def _sequence(directory, count, logger):
    expected=[directory/f'frame_{index:06d}.png' for index in range(1,count+1)]
    if not directory.is_dir() or {p.name for p in directory.iterdir()}!={p.name for p in expected}:
        raise ValueError('exact contiguous numeric PNG frame sequence required; missing/extra files refused')
    for path in expected:
        _local(logger.run_dir,path)
        if path.is_symlink() or not path.is_file():
            raise ValueError('regular owned PNG frame files required')
    return expected


def _command(args, *, paths, logger, unit_id, timeout):
    result=run_logged(tuple(str(a) for a in args),cwd=logger.run_dir,
        env=build_child_env(paths),timeout=command_timeout(timeout,300),logger=logger,stage='upscale',unit_id=unit_id)
    if result.returncode!=0 or result.timed_out:
        raise RuntimeError(f'{unit_id}: frame media command failed: {result.stderr_path}')
    return result


def _images(sequence, *, width, height, deadline, config, paths, logger, unit_id):
    rows=[];evidence=[];identities={}
    for index,path in enumerate(sequence,1):
        info,more=inspect_image(path,config=config,paths=paths,logger=logger,unit_id=unit_id,
                                stage='upscale',timeout=_remaining(deadline,monotonic()))
        if (info['width'],info['height'],info['format'],info['pixel_format'])!=(width,height,'png','rgb24'):
            raise ValueError('frame must be target-size single RGB24 PNG')
        fresh=hash_file(path)
        if any(getattr(fresh,k)!=info['identity'][k] for k in ('path','bytes','mtime_ns','sha256')):
            raise OSError('frame changed after complete PNG validation')
        identity=FileIdentity(**info['identity'])
        rows.append(dict(index=index,source_frame_index=index-1,identity=thaw(identity)))
        identities[str(index)]=identity
        evidence.extend(more)
    return rows,evidence,identities


def extract_video_frames(source,directory, *, expected_frames,width,height,config,paths,logger,unit_id,timeout):
    deadline=_deadline(timeout,monotonic());_count(expected_frames);_dimensions(width,height)
    source=_video_path(source,logger,paths);directory=_directory(directory,logger,paths)
    name=_record_name(logger,'extract',unit_id,'upscale')
    if directory.exists() or directory.is_symlink():raise FileExistsError(directory)
    identity=hash_file(source)
    directory.parent.mkdir(parents=True,exist_ok=True)
    directory.mkdir()  # Exclusive ownership; never reuse a preexisting frame directory.
    command=_command((config.tools['ffmpeg'],'-nostdin','-n','-v','error','-xerror','-i',source,
        '-map','0:v:0','-vf','format=rgb24','-fps_mode','passthrough','-start_number','1',
        directory/'frame_%06d.png'),paths=paths,logger=logger,unit_id=unit_id,timeout=_remaining(deadline,monotonic()))
    _again({'source':identity})
    sequence=_sequence(directory,expected_frames,logger)
    rows,more,identities=_images(sequence,width=width,height=height,deadline=deadline,
                                config=config,paths=paths,logger=logger,unit_id=unit_id)
    _sequence(directory,expected_frames,logger);_again(dict(identities,source=identity))
    record=logger.save_json(name,dict(source_identity=thaw(identity),width=width,height=height,
        frames=rows,command=thaw(command)))
    _remaining(deadline,monotonic())
    return rows,[record,command.stdout_path,command.stderr_path,*more]


def encode_video_frames(directory,target, *, frames,config,paths,logger,unit_id,timeout):
    deadline=_deadline(timeout,monotonic());_count(frames)
    directory=_directory(directory,logger,paths);target=_video_path(target,logger,paths)
    name=_record_name(logger,'encode',unit_id,'upscale')
    if target.exists() or target.is_symlink():raise FileExistsError(target)
    sequence=_sequence(directory,frames,logger)
    rows,evidence,identities=_images(sequence,width=1920,height=1080,deadline=deadline,
        config=config,paths=paths,logger=logger,unit_id=unit_id)
    _sequence(directory,frames,logger);_again(identities)
    target.parent.mkdir(parents=True,exist_ok=True)
    command=_command((config.tools['ffmpeg'],'-nostdin','-n','-v','error','-xerror','-framerate','16',
        '-start_number','1','-i',directory/'frame_%06d.png','-an','-c:v','libx264','-preset','medium',
        '-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough',target),
        paths=paths,logger=logger,unit_id=unit_id,timeout=_remaining(deadline,monotonic()))
    _sequence(directory,frames,logger);_again(identities)
    info,more=inspect_video(target,width=1920,height=1080,config=config,paths=paths,logger=logger,
                            unit_id=unit_id,stage='upscale',timeout=_remaining(deadline,monotonic()))
    if info['frames']!=frames or info['pixel_format']!='yuv420p':
        raise ValueError('encoded video must contain exactly every native frame in yuv420p')
    _sequence(directory,frames,logger);_again(identities)
    record=logger.save_json(name,dict(frames=rows,target=info,command=thaw(command)))
    _remaining(deadline,monotonic())
    return info,[record,*evidence,command.stdout_path,command.stderr_path,*more]


def extract_native_frame(source, target, *, source_frame_index, expected_frames, width, height,
                         config, paths, logger, unit_id, timeout=300):
    """Extract one exact zero-based generated frame after full native16 validation."""
    from .video import _command as video_command

    deadline = _deadline(timeout, monotonic())
    _count(expected_frames); _dimensions(width, height)
    if type(source_frame_index) is not int or not 0 <= source_frame_index < expected_frames:
        raise ValueError('source_frame_index must be within exact generated frames')
    source = _video_path(source, logger, paths)
    target = _local(logger.run_dir, Path(target))
    paths.policy.validate_write(target, 'run')
    if target.name != f'frame_{source_frame_index+1:06d}.png':
        raise ValueError('native frame target must use exact one-based numeric PNG name')
    if target.exists() or target.is_symlink(): raise FileExistsError(target)
    kwargs = dict(config=config, paths=paths, logger=logger, unit_id=unit_id, stage='source_clips')
    source_info, evidence = inspect_video(source, width=width, height=height,
        timeout=_remaining(deadline, monotonic()), **kwargs)
    if source_info['frames'] != expected_frames:
        raise ValueError('generated video must contain exactly expected_frames')
    identity = FileIdentity(**source_info['identity'])
    _again({'source': identity})
    target.parent.mkdir(parents=True, exist_ok=True)
    filter_value = f'select=eq(n\\,{source_frame_index}),format=rgb24'
    command = video_command((config.tools['ffmpeg'], '-nostdin', '-n', '-v', 'error', '-xerror',
        '-i', source, '-map', '0:v:0', '-vf', filter_value, '-frames:v', '1',
        '-fps_mode', 'passthrough', target), paths=paths, logger=logger, unit_id=unit_id,
        timeout=_remaining(deadline, monotonic()))
    _again({'source': identity})
    info, more = inspect_image(target, timeout=_remaining(deadline, monotonic()), **kwargs)
    if (info['width'], info['height'], info['format'], info['pixel_format']) != (width, height, 'png', 'rgb24'):
        raise ValueError('native extracted frame must be target-size single RGB24 PNG')
    _again({'source': identity, 'target': FileIdentity(**info['identity'])})
    record = logger.save_json(_record_name(logger, 'extract-native', unit_id, 'source_clips'),
        dict(source=source_info, target=info, source_frame_index=source_frame_index,
             expected_frames=expected_frames, filter=filter_value, command=thaw(command)))
    _remaining(deadline, monotonic())
    return info, [record, *evidence, command.stdout_path, command.stderr_path, *more]
