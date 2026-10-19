"""Native retained-frame extraction and read-only full RGB24 pixel proofs."""
from pathlib import Path
import hashlib
import json
import subprocess
import struct
import zlib
from ..runtime.manifest import hash_file
from ..runtime.production_state import ProductionRefused
from .frames import extract_video_frames,_count
from .video import inspect_video,_dimensions


class InvalidScenePng(ProductionRefused):
    """Confirmed PNG byte/format/dimension defect, rather than local tooling failure."""


def _decode(path,config,*,image=False,timeout=300):
    args=[str(config.tools['ffmpeg']),'-nostdin','-v','error','-xerror','-i',str(path),
          '-map','0:v:0','-vf','format=rgb24','-fps_mode','passthrough','-pix_fmt','rgb24','-f','rawvideo','-']
    result=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,timeout=timeout,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode: raise RuntimeError('complete RGB24 decode tool failed: '+str(path))
    return result.stdout


def verify_png(path,*,width,height,config,timeout=300):
    _dimensions(width,height)
    # Pure byte defects are definitive media failures; tool launch/IO failures stay resumable.
    raw_png=Path(path).read_bytes()
    if raw_png[:8]!=b'\x89PNG\r\n\x1a\n': raise InvalidScenePng('model output is not PNG')
    offset=8; kinds=[]
    while offset<len(raw_png):
        if len(raw_png)-offset<12: raise InvalidScenePng('truncated PNG chunk')
        length=struct.unpack('>I',raw_png[offset:offset+4])[0]; kind=raw_png[offset+4:offset+8]
        end=offset+12+length
        if end>len(raw_png): raise InvalidScenePng('truncated PNG data')
        data=raw_png[offset+8:offset+8+length]
        if zlib.crc32(kind+data)&0xffffffff!=struct.unpack('>I',raw_png[end-4:end])[0]: raise InvalidScenePng('PNG chunk CRC differs')
        if not kinds:
            if kind!=b'IHDR' or length!=13: raise InvalidScenePng('PNG IHDR required')
            w,h,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',data)
            if (w,h,depth,color)!=(width,height,8,2): raise InvalidScenePng('exact RGB24 PNG dimensions/format required')
        kinds.append(kind); offset=end
        if kind==b'IEND': break
    if offset!=len(raw_png) or not kinds or kinds[-1]!=b'IEND' or b'IDAT' not in kinds:
        raise InvalidScenePng('complete single PNG required')
    probe=subprocess.run([str(config.tools['ffprobe']),'-v','error','-show_streams','-show_format','-of','json',str(path)],
        stdin=subprocess.DEVNULL,capture_output=True,timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if probe.returncode: raise RuntimeError('PNG probe tool failed')
    info=json.loads(probe.stdout); streams=info.get('streams',[])
    if len(streams)!=1 or any(streams[0].get(k)!=v for k,v in dict(codec_name='png',width=width,height=height,pix_fmt='rgb24').items()):
        raise InvalidScenePng('exact RGB24 PNG dimensions/format required')
    raw=_decode(path,config,timeout=timeout)
    if len(raw)!=width*height*3: raise InvalidScenePng('single complete PNG required')
    return raw


def verify_scene_frame_pixels(source,images,*,expected_frames,width,height,config,timeout=1200):
    """One sequential source decode; compare every retained frame without writes."""
    _count(expected_frames); _dimensions(width,height)
    before=hash_file(Path(source)); image_before=[hash_file(Path(p)) for p in images]
    raw=_decode(source,config,timeout=timeout)
    size=width*height*3
    if len(images)!=expected_frames or len(raw)!=size*expected_frames:
        raise ProductionRefused('native retained decode frame count differs')
    for index,path in enumerate(images):
        if verify_png(path,width=width,height=height,config=config,timeout=min(300,timeout))!=raw[index*size:(index+1)*size]:
            raise ProductionRefused('PNG pixels differ from retained source frame')
    def identity(value): return value.path,value.bytes,value.sha256
    if identity(before)!=identity(hash_file(Path(source))) or any(identity(a)!=identity(hash_file(Path(p))) for a,p in zip(image_before,images)):
        raise ProductionRefused('native pixels source/images changed during verification')


def extract_scene_frames(source,target_dir,*,expected_frames,width,height,config,paths,logger,unit_id,timeout=1200):
    before=hash_file(Path(source))
    info,evidence=inspect_video(source,width=width,height=height,config=config,paths=paths,logger=logger,
        unit_id=unit_id,stage='upscale',timeout=min(300,timeout))
    if info['frames']!=expected_frames: raise ValueError('retained source count differs')
    rows,more=extract_video_frames(source,target_dir,expected_frames=expected_frames,width=width,height=height,
        config=config,paths=paths,logger=logger,unit_id=unit_id,timeout=timeout)
    images=[Path(target_dir)/f'frame_{k+1:06d}.png' for k in range(expected_frames)]
    verify_scene_frame_pixels(source,images,expected_frames=expected_frames,width=width,height=height,config=config,timeout=timeout)
    after=hash_file(Path(source))
    if (before.path,before.bytes,before.sha256)!=(after.path,after.bytes,after.sha256): raise ProductionRefused('source changed during extraction')
    artifacts=[{k:getattr(hash_file(path),k) for k in ('path','bytes','sha256')} for path in images]
    return artifacts,[*evidence,*more]

