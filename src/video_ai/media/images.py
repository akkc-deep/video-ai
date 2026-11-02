"""Single-image full decoding, RGB PNG validation, and lossless-source contain adaptation."""
from uuid import uuid4
import re
from time import monotonic
from ..config import read_json
from ..planning.start_images import contain_filter, validate_dimensions
from ..runtime.environment import build_child_env
from ..runtime.manifest import hash_file, thaw
from ..runtime.processes import run_logged
from ..runtime.timeline_checks import _again, _local
from ..runtime.execution_limits import command_timeout, execution_deadline, execution_remaining


def _deadline(timeout, now):
    return execution_deadline(timeout, now)


def _remaining(deadline, now):
    return execution_remaining(deadline, now)


def _record_name(logger, prefix, unit_id, stage):
    if not isinstance(stage,str) or not re.fullmatch(r'[a-z][a-z0-9_]*',stage):
        raise ValueError('safe media stage required')
    if not isinstance(unit_id,str) or not unit_id or any(c in unit_id for c in '/\\'):
        raise ValueError('safe media unit ID required')
    name=f'{stage.replace("_", "-")}/{prefix}-{unit_id.replace(":", "_")}-{uuid4().hex}.json'
    logger.path(name)
    return name


def _command(args, *, config, paths, logger, unit_id, stage='start_images', timeout=300):
    result=run_logged(tuple(str(a) for a in args),cwd=logger.run_dir,env=build_child_env(paths),
        timeout=command_timeout(timeout,300),logger=logger,stage=stage,unit_id=unit_id)
    if result.returncode != 0 or result.timed_out:
        raise RuntimeError(f'{unit_id}: image command failed: {result.stderr_path}')
    return result


def inspect_image(path, *, config, paths, logger, unit_id, stage='start_images', timeout=300, production=False):
    deadline=_deadline(timeout,monotonic())
    name=_record_name(logger,'media',unit_id,stage)
    if production:
        from ..runtime.production_state import ArtifactStamp
        identity=ArtifactStamp.read(path)
    else:identity=hash_file(path)
    probe=_command((config.tools['ffprobe'],'-v','error','-count_frames','-show_streams','-show_format','-of','json',path),
        config=config,paths=paths,logger=logger,unit_id=unit_id,stage=stage,timeout=_remaining(deadline,monotonic()))
    data=read_json(probe.stdout_path);streams=data.get('streams')
    if not isinstance(streams,list) or len(streams)!=1 or streams[0].get('codec_type')!='video':
        raise ValueError('single image stream required')
    stream=streams[0]
    if stream.get('nb_read_frames')!='1': raise ValueError('single frame image required; animation refused')
    if any(type(stream.get(k)) is not int or stream[k]<=0 for k in ('width','height')):
        raise ValueError('invalid image dimensions')
    if stream.get('codec_name') not in {'png','mjpeg','webp','bmp','tiff','gif','jpeg2000','targa','ppm','pgm'}:
        raise ValueError('unsupported still-image codec')
    decode=_command((config.tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',path,'-f','null','-'),
        config=config,paths=paths,logger=logger,unit_id=unit_id,stage=stage,timeout=_remaining(deadline,monotonic()))
    if production:identity.verify()
    else:_again({'image':identity})
    _remaining(deadline,monotonic())
    info=dict({('stamp' if production else 'identity'):thaw(identity)},width=stream['width'],height=stream['height'],
        format=stream['codec_name'],pixel_format=stream['pix_fmt'])
    record=logger.save_json(name,
        dict(info=info,probe=data,commands=[thaw(probe),thaw(decode)]))
    _remaining(deadline,monotonic())
    return info,[record,probe.stdout_path,probe.stderr_path,decode.stdout_path,decode.stderr_path]


def validate_start_png(path, *, width, height, **kwargs):
    validate_dimensions(width,height)
    _local(kwargs['logger'].run_dir,path)
    info,evidence=inspect_image(path,**kwargs)
    if (info['width'],info['height'],info['format'],info['pixel_format']) != (width,height,'png','rgb24'):
        raise ValueError('start image must be target-size single RGB24 PNG')
    return info,evidence


def adapt_image(source,target, *, width,height,**kwargs):
    filter_value=contain_filter(width,height)
    target=_local(kwargs['logger'].run_dir,target)
    if target.exists():raise FileExistsError(target)
    info,evidence=inspect_image(source,**kwargs)
    target.parent.mkdir(parents=True,exist_ok=True)
    command=_command((kwargs['config'].tools['ffmpeg'],'-nostdin','-n','-v','error','-xerror','-i',source,
        '-vf',filter_value,'-frames:v','1','-pix_fmt','rgb24',target),**kwargs)
    result,more=validate_start_png(target,width=width,height=height,**kwargs)
    _again({'source':hash_file(source)})
    if hash_file(source).sha256!=info['identity']['sha256']:raise OSError('user source changed during conversion')
    stage=kwargs.get('stage','start_images')
    name=(_record_name(kwargs['logger'],'convert',kwargs['unit_id'],stage) if stage=='source_clips'
          else f'start-images/convert-{kwargs["unit_id"]}.json')
    record=kwargs['logger'].save_json(name,
        dict(source=info,target=result,filter=filter_value,command=thaw(command)))
    return result,evidence+[record,command.stdout_path,command.stderr_path]+more
