"""Native retained-frame extraction and read-only full RGB24 pixel proofs."""
from pathlib import Path
import hashlib
import json
import subprocess
import struct
import re
import zlib
from ..runtime.manifest import hash_file
from ..runtime.production_state import ProductionRefused
from .frames import _count
from .video import _dimensions
from ..runtime.execution_limits import command_timeout


class InvalidScenePng(ProductionRefused):
    """Confirmed PNG byte/format/dimension defect, rather than local tooling failure."""


def _decode(path,config,*,image=False,timeout=300):
    args=[str(config.tools['ffmpeg']),'-nostdin','-v','error','-xerror','-i',str(path),
          '-map','0:v:0','-vf','format=rgb24','-fps_mode','passthrough','-pix_fmt','rgb24','-f','rawvideo','-']
    result=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,timeout=command_timeout(timeout),
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode: raise RuntimeError('complete RGB24 decode tool failed: '+str(path))
    return result.stdout


def _check_png(path,*,width,height):
    """Check every encoded chunk; batch decoders still prove all RGB pixels."""
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
        if kind in (b'acTL',b'fcTL',b'fdAT'):raise InvalidScenePng('PNG animation is not a single complete frame')
        if kind==b'tRNS':raise InvalidScenePng('exact RGB24 PNG without transparency required')
        if kind==b'IHDR' and kinds:raise InvalidScenePng('PNG must have exactly one IHDR')
        if not kinds:
            if kind!=b'IHDR' or length!=13: raise InvalidScenePng('PNG IHDR required')
            w,h,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',data)
            if (w,h,depth,color)!=(width,height,8,2): raise InvalidScenePng('exact RGB24 PNG dimensions/format required')
        kinds.append(kind); offset=end
        if kind==b'IEND': break
    if offset!=len(raw_png) or not kinds or kinds[-1]!=b'IEND' or b'IDAT' not in kinds:
        raise InvalidScenePng('complete single PNG required')


def verify_png(path,*,width,height,config,timeout=300,remaining_timeout=None):
    def budget():
        if remaining_timeout is None:return command_timeout(timeout)
        return command_timeout(remaining_timeout(),command_timeout(timeout))
    _check_png(path,width=width,height=height)
    probe=subprocess.run([str(config.tools['ffprobe']),'-v','error','-show_streams','-show_format','-of','json',str(path)],
        stdin=subprocess.DEVNULL,capture_output=True,timeout=budget(),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if probe.returncode: raise RuntimeError('PNG probe tool failed')
    info=json.loads(probe.stdout); streams=info.get('streams',[])
    if len(streams)!=1 or any(streams[0].get(k)!=v for k,v in dict(codec_name='png',width=width,height=height,pix_fmt='rgb24').items()):
        raise InvalidScenePng('exact RGB24 PNG dimensions/format required')
    raw=_decode(path,config,timeout=budget())
    if remaining_timeout is not None:budget()
    if len(raw)!=width*height*3: raise InvalidScenePng('single complete PNG required')
    return raw


def png_sequence_hashes(images,*,width,height,config,timeout=1200,remaining_timeout=None):
    """One complete image2 decode, after checking every PNG CRC and IHDR.

    Only an exact one-based owned sequence is eligible; an arbitrary list must
    never be silently replaced by a wildcard or sampled by the media tool.
    """
    images=[Path(p) for p in images]
    if not images:raise ProductionRefused('nonempty native PNG sequence required')
    folder=images[0].parent
    expected=[folder/f'frame_{i:06d}.png' for i in range(1,len(images)+1)]
    if images!=expected or set(folder.iterdir())!=set(expected):
        raise ProductionRefused('exact contiguous native PNG sequence required')
    def budget():
        return command_timeout(remaining_timeout() if remaining_timeout else timeout)
    for path in images:
        budget();_check_png(path,width=width,height=height)
    result=subprocess.run([str(config.tools['ffmpeg']),'-nostdin','-v','error','-xerror',
        '-framerate','16','-start_number','1','-i',str(folder/'frame_%06d.png'),
        '-map','0:v:0','-vf','format=rgb24','-fps_mode','passthrough','-c:v','rawvideo',
        '-pix_fmt','rgb24','-f','framehash','-hash','sha256','-'],
        stdin=subprocess.DEVNULL,capture_output=True,timeout=budget(),
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    budget()
    if result.returncode:raise RuntimeError('complete PNG sequence decode tool failed')
    # Hash every completely decoded RGB24 frame in FFmpeg, rather than keeping
    # a second entire decoded video in Python. The source is independently
    # decoded and hashed frame by frame by the caller; no pixel is sampled.
    hashes=[]
    for line in result.stdout.decode('ascii').splitlines():
        if line.startswith('#'):continue
        fields=[value.strip() for value in line.split(',')]
        if (len(fields)!=6 or fields[0]!='0' or fields[4]!=str(width*height*3)
                or re.fullmatch(r'[0-9a-f]{64}',fields[5]) is None):
            raise InvalidScenePng('complete RGB24 PNG frame hashes required')
        hashes.append(fields[5])
    if len(hashes)!=len(images):raise InvalidScenePng('single complete PNG required for every native frame')
    return hashes


def verify_scene_frame_pixels(source,images,*,expected_frames,width,height,config,timeout=1200):
    """One sequential source decode; compare every retained frame without writes."""
    _count(expected_frames); _dimensions(width,height)
    before=hash_file(Path(source)); image_before=[hash_file(Path(p)) for p in images]
    raw=_decode(source,config,timeout=timeout)
    size=width*height*3
    if len(images)!=expected_frames or len(raw)!=size*expected_frames:
        raise ProductionRefused('native retained decode frame count differs')
    hashes=png_sequence_hashes(images,width=width,height=height,config=config,timeout=timeout)
    if any(digest!=hashlib.sha256(raw[i*size:(i+1)*size]).hexdigest() for i,digest in enumerate(hashes)):
        raise ProductionRefused('PNG pixels differ from retained source frame')
    def identity(value): return value.path,value.bytes,value.sha256
    if identity(before)!=identity(hash_file(Path(source))) or any(identity(a)!=identity(hash_file(Path(p))) for a,p in zip(image_before,images)):
        raise ProductionRefused('native pixels source/images changed during verification')


def extract_scene_frames(source,target_dir,*,expected_frames,width,height,config,paths,logger,unit_id,timeout=1200):
    from .scene_native_batch import extract_native_scene_batch
    return extract_native_scene_batch(source,target_dir,expected_frames=expected_frames,width=width,height=height,
        config=config,paths=paths,logger=logger,unit_id=unit_id,timeout=timeout,aggregate_png=True)

