"""Finite frame encoding and a single full RGB decode shared with last-frame extraction."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import struct
import zlib

from .wan_fast_profiles import artifact,digest,write_once
from .wan_fast_experiment import baseline_api,read
from fractions import Fraction
from .wan_fast_media import black_frame_summary

_PROOFS={}
_TOOLS={}
DEFAULT_FFMPEG='E:/VideoAI/shared/tools/ffmpeg/bin/ffmpeg.exe'
DEFAULT_FFPROBE='E:/VideoAI/shared/tools/ffmpeg/bin/ffprobe.exe'


def clear_proofs():_PROOFS.clear()


def _png_rgb(rgb,width,height):
    def chunk(name,payload):
        return struct.pack('>I',len(payload))+name+payload+struct.pack('>I',zlib.crc32(name+payload)&0xffffffff)
    scanlines=b''.join(b'\0'+rgb[i*width*3:(i+1)*width*3] for i in range(height))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(scanlines))+chunk(b'IEND',b'')


def rgb_frames(images,*,width=768,height=432,expected_frames=93):
    import numpy as np
    if hasattr(images,'detach'):images=images.detach().cpu().numpy()
    frames=np.asarray(images)
    if frames.shape!=(expected_frames,height,width,3) or not np.issubdtype(frames.dtype,np.floating):raise ValueError('exact RGB floating frames required')
    if not np.isfinite(frames).all():raise ValueError('finite IMAGE required before uint8')
    return np.ascontiguousarray(np.clip(np.rint(frames*255),0,255).astype(np.uint8))


def encode_frames(root,target,images,*,width=768,height=432,expected_frames=93,ffmpeg=DEFAULT_FFMPEG):
    root=Path(root);target=Path(target);frames=rgb_frames(images,width=width,height=height,expected_frames=expected_frames)
    if not target.resolve().is_relative_to(root.resolve()):raise ValueError('output escapes experiment')
    partial=target.with_suffix('.partial.mp4');intent=target.with_suffix('.encoder-intent.json')
    if target.exists() or partial.exists() or intent.exists():raise ValueError('existing encoder intent/output; do not overwrite/reproduce')
    target.parent.mkdir(parents=True,exist_ok=True)
    argv=[str(ffmpeg),'-nostdin','-v','error','-n','-f','rawvideo','-pix_fmt','rgb24',
        '-s:v',f'{width}x{height}','-r','16','-i','pipe:0','-an','-c:v','libx264',
        '-preset','medium','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(partial)]
    source_sha=hashlib.sha256(memoryview(frames)).hexdigest()
    write_once(intent,dict(argv=argv,source_rgb_sha256=source_sha,frames=expected_frames,width=width,height=height,fps=16,
        finite_before_uint8=True,ffmpeg=artifact(ffmpeg).identity_dict()))
    with (target.with_suffix('.encoder.stderr')).open('xb') as error:
        process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=error,shell=False)
        try:
            process.communicate(input=memoryview(frames),timeout=180)
        except BaseException:
            if process.poll() is None:process.kill();process.wait(timeout=5)
            raise
    write_once(target.with_suffix('.encoder-result.json'),dict(returncode=process.returncode,source_rgb_sha256=source_sha))
    if process.returncode:raise RuntimeError('encoder failed; original intent retained, no overwrite')
    # The candidate remains partial until a full technical check succeeds.
    return partial


def _tools(ffmpeg,ffprobe):
    result=[]
    for name in (ffmpeg,ffprobe):
        p=Path(name).resolve(strict=True);s=p.stat();key=(str(p),s.st_size,s.st_mtime_ns,s.st_ino)
        if key not in _TOOLS:_TOOLS[key]=artifact(p).identity_dict()
        result.append(_TOOLS[key])
    return result


def _proof_key(root,identity,width,height,frames,ffmpeg,ffprobe):
    return digest(dict(root=str(Path(root).resolve()),source_sha256=identity.sha256,source_bytes=identity.bytes,width=width,height=height,frames=frames,
                    tools=_tools(ffmpeg,ffprobe),rules='lva07-one-rgb-v1'))


def _pinned_tools(profile):
    from .wan_fast_profiles import Artifact
    tools=profile.identity_dict()['common']['tool']
    if profile.identity_dict()['kind']=='experiment':
        for name in ('ffmpeg','ffprobe'):Artifact(**tools[name]).verify()
    return tools


def inspect_media(root,source,*,width,height,expected_frames,ffmpeg=DEFAULT_FFMPEG,ffprobe=DEFAULT_FFPROBE,save_frames=False):
    from video_ai.media.video import validate_video_probe
    root=Path(root);source=Path(source).resolve(strict=True);identity=artifact(source)
    key=_proof_key(root,identity,width,height,expected_frames,ffmpeg,ffprobe)
    if key in _PROOFS:
        proof=_PROOFS[key]
        if artifact(proof['last_frame']).sha256!=proof['last_frame_sha256']:raise ValueError('last frame drift')
        return json.loads(json.dumps(proof))
    # Rebuild the same immutable proof after a process restart, including the
    # ordered PNG archive produced by the original necessary decode.
    durable=root/'media-checks'/(key+'.json')
    if durable.exists() and read(durable).get('frames'):save_frames=True
    api=baseline_api()
    probe=json.loads(api.media_command(root,'probe',[ffprobe,'-v','error','-count_frames','-show_streams','-show_format','-of','json',source]))
    frames=json.loads(api.media_command(root,'frames',[ffprobe,'-v','error','-show_frames','-of','json',source]))
    technical=validate_video_probe(probe,frames,width=width,height=height)
    if technical['frames']!=expected_frames or technical['pixel_format']!='yuv420p':raise ValueError('frame budget/format differs')
    rgb=api.media_command(root,'decode-rgb24',[ffmpeg,'-nostdin','-v','error','-xerror','-i',source,'-map','0:v:0','-pix_fmt','rgb24','-f','rawvideo','-'])
    black=black_frame_summary(rgb,width=width,height=height)
    if black['frames']!=expected_frames or black['suspect_black']:raise ValueError('full RGB frame budget/black signal failed')
    technical['pts']=[dict(pts=f.get('pts',f.get('best_effort_timestamp')),time_base=probe['streams'][0]['time_base']) for f in frames['frames']]
    last=root/'media-checks'/(identity.sha256+'-last.png');last.parent.mkdir(parents=True,exist_ok=True)
    raw=_png_rgb(rgb[-width*height*3:],width,height)
    if last.exists():
        if last.read_bytes()!=raw:raise ValueError('existing last frame differs')
    else:
        with last.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    if artifact(source)!=identity:raise ValueError('media changed during validation')
    proof=dict(source_sha256=identity.sha256,technical=technical,black=black,last_frame=str(last),
               last_frame_sha256=hashlib.sha256(raw).hexdigest(),quality='awaiting_human_review')
    if save_frames:
        folder=root/'media-checks'/'frames'/identity.sha256;folder.mkdir(parents=True,exist_ok=True);rows=[]
        stride=width*height*3
        for index in range(expected_frames):
            target=folder/f'frame_{index+1:06d}.png'
            payload=_png_rgb(rgb[index*stride:(index+1)*stride],width,height)
            if target.exists():
                if target.read_bytes()!=payload:raise ValueError('saved RGB frame differs')
            else:
                with target.open('xb') as output:output.write(payload)
            rows.append(dict(path=str(target),sha256=hashlib.sha256(payload).hexdigest()))
        proof['frames']=rows
    write_once(root/'media-checks'/(key+'.json'),proof);_PROOFS[key]=proof
    return json.loads(json.dumps(proof))


def promote_encoded(root,target,partial,*,width=768,height=432,expected_frames=93,save_frames=False,ffmpeg=DEFAULT_FFMPEG,ffprobe=DEFAULT_FFPROBE):
    proof=inspect_media(root,partial,width=width,height=height,expected_frames=expected_frames,save_frames=save_frames,ffmpeg=ffmpeg,ffprobe=ffprobe)
    target=Path(target)
    if target.exists():raise ValueError('output already exists')
    os.rename(partial,target)
    write_once(target.with_suffix('.media-proof.json'),proof)
    return proof


def collect_media(root,target,*,trial_id,prompt_id,profile,fixture,graph):
    root=Path(root);target=Path(target)
    tools=_pinned_tools(profile)
    ffmpeg=tools['ffmpeg']['path'];ffprobe=tools['ffprobe']['path']
    proof=read(target.with_suffix('.media-proof.json'))
    matrix=profile.identity_dict()['schema_version']==2
    count=fixture['budget']['generated_frames'] if matrix else 93
    if proof.get('source_sha256')!=artifact(target).sha256:raise ValueError('promoted media content differs')
    technical=proof['technical']
    if any(technical.get(k)!=v for k,v in dict(width=768,height=432,frames=count,fps=16,codec='h264',pixel_format='yuv420p').items()):
        raise ValueError('promoted frame contract differs')
    pts=technical.get('pts',[])
    times=[Fraction(p['pts'])*Fraction(p['time_base']) for p in pts]
    if len(times)!=count or any(y-x!=Fraction(1,16) for x,y in zip(times,times[1:])):raise ValueError('promoted full PTS differs')
    intent=read(target.with_suffix('.encoder-intent.json'));encoded=read(target.with_suffix('.encoder-result.json'))
    if (intent.get('finite_before_uint8') is not True or intent.get('frames')!=count or intent.get('width')!=768 or intent.get('height')!=432
            or encoded.get('returncode')!=0 or encoded.get('source_rgb_sha256')!=intent.get('source_rgb_sha256')):
        raise ValueError('promoted encoder receipt differs')
    expected_argv=[str(ffmpeg),'-nostdin','-v','error','-n','-f','rawvideo','-pix_fmt','rgb24','-s:v','768x432','-r','16','-i','pipe:0',
        '-an','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(target.with_suffix('.partial.mp4'))]
    if intent.get('argv')!=expected_argv:raise ValueError('promoted encoder argv/tool differs')
    if profile.identity_dict()['kind']=='experiment':
        generation=read(target.with_suffix('.generation-binding.json'));owner=read(root/'service-owner.json')
        original=read(root/'trials'/trial_id/'intent.json');claim=read(root/'worker-submissions'/(trial_id+'.json'))
        expected=dict(**claim,prompt_id=prompt_id,media_proof_sha256=digest(proof),encoder_intent_sha256=digest(intent),encoder_result_sha256=digest(encoded))
        if (generation!=expected or claim.get('profile_sha256')!=profile.digest() or claim.get('graph_sha256')!=digest(graph)
                or original.get('graph')!=graph or original.get('graph_sha256')!=digest(graph)
                or claim.get('client_id')!=original['client_id'] or claim.get('epoch')!=owner['epoch']):raise ValueError('promoted original generation binding differs')
        if intent.get('ffmpeg')!=tools['ffmpeg']:raise ValueError('promoted tool identity differs')
        # Consume the owned worker's content-bound full-decode proof; no second decode.
    else:
        actual=inspect_media(root,target,width=768,height=432,expected_frames=count,ffmpeg=ffmpeg,ffprobe=ffprobe)
        if actual!=proof:raise ValueError('promoted offline proof differs')
    if proof.get('black',{}).get('suspect_black') is not False or proof['black']['frames']!=count:raise ValueError('promoted black check differs')
    if not Path(proof['last_frame']).resolve().is_relative_to(root.resolve()):raise ValueError('promoted last frame escapes root')
    if artifact(proof['last_frame']).sha256!=proof['last_frame_sha256']:raise ValueError('promoted last frame differs')
    _PROOFS[_proof_key(root,artifact(target),768,432,count,ffmpeg,ffprobe)]=proof
    result=dict(schema_version=2 if matrix else 1,trial_id=trial_id,prompt_id=prompt_id,profile_sha256=profile.digest(),
        fixture_sha256=digest(fixture),graph_sha256=digest(graph),input_sha256=fixture['input_sha256'],
        generated=str(target),retained=str(target),last_frame=proof['last_frame'],
        generated_sha256=proof['source_sha256'],retained_sha256=proof['source_sha256'],last_frame_sha256=proof['last_frame_sha256'],
        technical=proof['technical'],quality='awaiting_human_review',tools=dict(ffmpeg=ffmpeg,ffprobe=ffprobe),
        full_model_verified=read(root/'admission/pair.json')['full_model_verified'] if profile.identity_dict()['kind']=='experiment' else False,upscaled_1080p=False)
    if matrix:
        retained=fixture['budget']['retained_frames'];start=fixture['budget']['retained_source_start']
        if not proof.get('frames') or len(proof['frames'])!=count:raise ValueError('single-decode frame archive required')
        result.update(generated_frames=count,retained_frames=retained,generated_technical=proof['technical'])
        rproof=proof
        if retained!=count:
            target,rproof=retain_matrix_frames(root,target,proof,start=start,count=retained,ffmpeg=ffmpeg,ffprobe=ffprobe)
            result.update(retained=str(target),retained_sha256=rproof['source_sha256'],technical=rproof['technical'],
                          last_frame=rproof['last_frame'],last_frame_sha256=rproof['last_frame_sha256'])
        result['frames']=rproof['frames']
    return result


def validate_result(root,result,*,profile):
    root=Path(root).resolve()
    pinned=_pinned_tools(profile)
    tools={name:pinned[name]['path'] for name in ('ffmpeg','ffprobe')}
    if result.get('tools')!=tools:raise ValueError('completed tool pins differ')
    info=result['technical']
    matrix=profile.identity_dict()['schema_version']==2
    fixture=read(root/'fixture.json') if matrix else None
    retained=fixture['budget']['retained_frames'] if matrix else 93
    generated=fixture['budget']['generated_frames'] if matrix else 93
    if any(info.get(k)!=v for k,v in dict(width=768,height=432,frames=retained,fps=16).items()):raise ValueError('completed frame contract differs')
    for role in ('generated','retained','last_frame'):
        path=Path(result[role]).resolve(strict=True)
        if not path.is_relative_to(root) or path.is_symlink():raise ValueError('media escapes root')
        if artifact(path).sha256!=result[role+'_sha256']:raise ValueError('completed media content differs')
    if matrix and retained!=generated:
        inspect_media(root,result['generated'],width=768,height=432,expected_frames=generated,**tools)
    proof=inspect_media(root,result['retained'],width=768,height=432,expected_frames=retained,**tools)
    if proof['technical']!=info or proof['last_frame_sha256']!=result['last_frame_sha256']:
        raise ValueError('technical/last frame proof differs')
    if retained==generated and result['retained']!=result['generated']:raise ValueError('untrimmed retained must reuse original generated media')
    if matrix:
        if result.get('generated_frames')!=generated or result.get('retained_frames')!=retained:raise ValueError('completed matrix frame budget differs')
        frames=result.get('frames',[])
        if frames!=proof.get('frames'):raise ValueError('ordered retained PNG proof differs')
        if len(frames)!=retained:raise ValueError('retained frame sources missing')
        for item in frames:
            path=Path(item['path']).resolve(strict=True)
            if not path.is_relative_to(root) or artifact(path).sha256!=item['sha256']:raise ValueError('retained PNG source differs')


def _saved_rgb(item,width,height):
    import numpy as np
    path=Path(item['path']);payload=path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=item['sha256'] or payload[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('source PNG differs')
    offset=8;compressed=[]
    while offset<len(payload):
        size=struct.unpack('>I',payload[offset:offset+4])[0];name=payload[offset+4:offset+8];data=payload[offset+8:offset+8+size]
        if name==b'IHDR' and struct.unpack('>IIBBBBB',data)!=(width,height,8,2,0,0,0):raise ValueError('source PNG geometry differs')
        if name==b'IDAT':compressed.append(data)
        offset+=size+12
    raw=zlib.decompress(b''.join(compressed));row=width*3+1
    if len(raw)!=height*row or any(raw[i*row]!=0 for i in range(height)):raise ValueError('owned RGB PNG layout differs')
    return np.frombuffer(b''.join(raw[i*row+1:(i+1)*row] for i in range(height)),dtype=np.uint8).reshape(height,width,3)


def retain_matrix_frames(root,source,proof,*,start,count,width=768,height=432,ffmpeg=DEFAULT_FFMPEG,ffprobe=DEFAULT_FFPROBE):
    import numpy as np
    source=Path(source);root=Path(root);target=source.with_name(source.stem+'-retained.mp4')
    if not 0<=start<start+count<=len(proof.get('frames',[])):raise ValueError('retained source interval differs')
    selected=proof['frames'][start:start+count]
    binding=dict(source_sha256=artifact(source).sha256,source_start=start,source_end=start+count,source_frames=selected)
    write_once(target.with_suffix('.trim-binding.json'),binding)
    if target.exists():
        saved=read(target.with_suffix('.media-proof.json'))
        if saved['source_sha256']!=artifact(target).sha256:raise ValueError('retained media differs')
        return target,saved
    partial=target.with_suffix('.partial.mp4')
    if not partial.exists():
        frames=np.stack([_saved_rgb(item,width,height) for item in selected]).astype(np.float32)/255
        partial=encode_frames(root,target,frames,width=width,height=height,expected_frames=count,ffmpeg=ffmpeg)
    else:
        receipt=read(target.with_suffix('.encoder-result.json'))
        if receipt['returncode']!=0:raise ValueError('original retained encoder failure; no overwrite')
    result=promote_encoded(root,target,partial,width=width,height=height,expected_frames=count,save_frames=True,ffmpeg=ffmpeg,ffprobe=ffprobe)
    return target,result
