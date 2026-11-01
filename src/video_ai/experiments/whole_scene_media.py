"""Native media audit; technical evidence can never stand in for playback."""
import hashlib
from fractions import Fraction
from pathlib import Path
import subprocess
from uuid import uuid4

from ..media.video import validate_video_probe
from ..runtime.workflows import safe_comfy_path
from .whole_scene_case import Evidence, identity, read_json, write_json, verify_identity


def _command(root, args):
    p = subprocess.run([str(a) for a in args], cwd=root, capture_output=True, timeout=300)
    token=uuid4().hex; evidence=Evidence(root)
    evidence.save_bytes(f'media-commands/{token}.stdout',p.stdout)
    evidence.save_bytes(f'media-commands/{token}.stderr',p.stderr)
    evidence.save_json(f'media-commands/{token}.json',dict(args=[str(a) for a in args],returncode=p.returncode))
    if p.returncode: raise ValueError('media command failed: '+token)
    return p.stdout


def _probe(root, path, tools, width, height, count):
    from ..adapters.common import strict_json
    probe=strict_json(_command(root,[tools['ffprobe'],'-v','error','-count_frames','-show_streams','-show_format','-of','json',path]))
    frames=strict_json(_command(root,[tools['ffprobe'],'-v','error','-show_frames','-of','json',path]))
    result=validate_video_probe(probe,frames,width=width,height=height)
    if result['frames'] != count: raise ValueError('wrong native output frame count')
    time_base=Fraction(probe['streams'][0]['time_base'])
    for i,frame in enumerate(frames['frames']):
        if Fraction(frame.get('pts',frame.get('best_effort_timestamp')))*time_base != Fraction(i,16):
            raise ValueError('native PTS must be exactly i/16 from zero')
    if Fraction(probe['streams'][0]['duration']) != Fraction(count,16):
        raise ValueError('native duration must be exactly frame count/16')
    _command(root,[tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',path,'-f','null','-'])
    return result,probe,frames


def audit_output(root, output):
    root=Path(root).resolve(strict=True)
    if not isinstance(output,dict) or not {'filename','subfolder','type'} <= set(output) or output['type']!='output':
        raise ValueError('mapped output metadata required')
    safe_comfy_path(output['filename']); safe_comfy_path(output['subfolder'],allow_empty=True)
    if Path(output['filename']).name != output['filename']: raise ValueError('output filename must be basename')
    generated=(root/'output'/output['subfolder']/output['filename']).resolve(strict=False)
    if not generated.is_relative_to(root/'output') or generated.suffix.lower()!='.mp4':
        raise ValueError('output escapes owned output directory')
    if (root/'media.json').exists():
        previous=read_json(root/'media.json')
        if identity(generated)!=previous['generated_identity']: raise ValueError('generated identity changed')
        for key in ('review_identity','mapping_identity','native_manifest_identity'):
            verify_identity(previous[key])
        for item in read_json(root/'native-frame-identities.json'): verify_identity(item)
        create_playback_review(root)
        return previous
    tools=read_json(root/'case.json')['runtime']['tools']
    inputs=read_json(root/'graph.json')['129:98']['inputs']; width,height=inputs['width'],inputs['height']
    generated_identity=identity(generated)
    technical,probe,frames=_probe(root,generated,tools,width,height,321)
    write_json(root/'generated-probe.json',dict(probe=probe,frames=frames))
    native=root/'native-frames'; native.mkdir(exist_ok=False)
    _command(root,[tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',generated,
        '-fps_mode','passthrough','-start_number','0','-pix_fmt','rgb24',native/'frame_%06d.png'])
    paths=sorted(native.glob('*.png'))
    if len(paths)!=321: raise ValueError('native PNG extraction count differs')
    write_json(root/'native-frame-identities.json',[identity(p) for p in paths])
    mapping=dict(requested_frames=321,retained_frames=320,source_start=0,source_end=320,
        discarded_source_frames=[320],frames=[dict(review_frame=i,source_frame=i,pts=f'{i}/16') for i in range(320)])
    write_json(root/'mapping.json',mapping)
    review=root/'review.mp4'
    _command(root,[tools['ffmpeg'],'-nostdin','-v','error','-framerate','16','-start_number','0',
        '-i',native/'frame_%06d.png','-frames:v','320','-c:v','libx264rgb','-crf','0','-preset','fast',review])
    reviewed,rprobe,rframes=_probe(root,review,tools,width,height,320)
    write_json(root/'review-probe.json',dict(probe=rprobe,frames=rframes))
    source_hashes=_command(root,[tools['ffmpeg'],'-nostdin','-v','error','-framerate','16','-start_number','0',
        '-i',native/'frame_%06d.png','-frames:v','320','-pix_fmt','rgb24','-f','framemd5','-'])
    review_hashes=_command(root,[tools['ffmpeg'],'-nostdin','-v','error','-i',review,'-pix_fmt','rgb24','-f','framemd5','-'])
    def digests(raw):
        return [line.split(',')[-1].strip() for line in raw.decode().splitlines() if line and not line.startswith('#')]
    if len(digests(source_hashes))!=320 or digests(source_hashes)!=digests(review_hashes):
        raise ValueError('review pixels differ from retained native RGB frames')
    _statistics(root,paths)
    if identity(generated)!=generated_identity: raise ValueError('generated changed during audit')
    value=dict(generated=technical,review=reviewed,generated_identity=generated_identity,
        review_identity=identity(review),mapping_identity=identity(root/'mapping.json'),rgb_preserved=True,
        native_manifest_identity=identity(root/'native-frame-identities.json'),
        full_video_observation='unverified',sampled_appearance='unverified',production_eligible=False,
        color_metadata={k:probe['streams'][0].get(k,'unknown') for k in
            ('color_space','color_primaries','color_transfer','color_range')})
    write_json(root/'media.json',value)
    create_playback_review(root)
    return value


def create_playback_review(root):
    """Add an OS-compatible copy, retaining the RGB lossless audit unchanged.

    libx264rgb lossless uses High 4:4:4 Predictive, unsupported by many standard
    H.264 players. This separate, explicitly lossy High/yuv420p copy is encoded
    from the original YUV movie, avoiding a round trip through the RGB audit.
    """
    root=Path(root).resolve(strict=True);media=read_json(root/'media.json')
    for key in ('generated_identity','review_identity','mapping_identity'):
        verify_identity(media[key])
    receipt=root/'playback-review.json';target=root/'review-playback.mp4'
    if receipt.exists():
        value=read_json(receipt)
        if (value['generated_identity']!=media['generated_identity']
                or value['lossless_review_identity']!=media['review_identity']
                or value['mapping_identity']!=media['mapping_identity']
                or Path(value['playback_identity']['path'])!=target):
            raise ValueError('playback source identity changed')
        verify_identity(value['playback_identity'])
        return value
    tools=read_json(root/'case.json')['runtime']['tools']
    generated=Path(media['generated_identity']['path'])
    if not generated.is_relative_to(root/'output'):
        raise ValueError('playback source escapes owned output')
    width,height=media['generated']['width'],media['generated']['height']
    _command(root,[tools['ffmpeg'],'-nostdin','-v','error','-n','-i',generated,
        '-map','0:v:0','-vf','trim=start_frame=0:end_frame=320,setpts=PTS-STARTPTS',
        '-fps_mode','passthrough','-c:v','libx264','-crf','16','-preset','medium',
        '-profile:v','high','-pix_fmt','yuv420p','-movflags','+faststart','-an',target])
    video,probe,frames=_probe(root,target,tools,width,height,320)
    stream=probe['streams'][0]
    if stream.get('profile')!='High' or video['pixel_format']!='yuv420p':
        raise ValueError('playback requires standard High profile / 8-bit yuv420p')
    for key in ('generated_identity','review_identity','mapping_identity'):
        verify_identity(media[key])
    probe_path=root/'playback-probes'/f'{uuid4().hex}.json'
    write_json(probe_path,dict(probe=probe,frames=frames))
    value=dict(schema_version=1,generated_identity=media['generated_identity'],
        lossless_review_identity=media['review_identity'],mapping_identity=media['mapping_identity'],
        playback_identity=identity(target),video=dict(video,profile=stream['profile']),
        source_frame_range=[0,320],lossless=False,
        encoding='libx264 CRF16 High/yuv420p; faststart; no scaling, fps change or color correction',
        producer_identity=identity(Path(__file__)),ffmpeg_identity=identity(tools['ffmpeg']),
        probe_identity=identity(probe_path),
        full_video_observation='unverified',production_eligible=False)
    write_json(receipt,value)
    return value


def _statistics(root, paths):
    import cv2
    import numpy as np
    rows=[]
    for i,path in enumerate(paths):
        bgr=cv2.imread(str(path),cv2.IMREAD_COLOR)
        if bgr is None: raise ValueError('cannot read native PNG')
        rgb=bgr[:,:,::-1].astype(np.float32)/255
        # Statistics of decoded RGB code values, not inferred physical luminance.
        y=rgb@np.array([.2126,.7152,.0722]); chroma=rgb.max(axis=2)-rgb.min(axis=2)
        rows.append(dict(source_frame=i,pts=f'{i}/16',rgb_means=rgb.mean(axis=(0,1)).tolist(),
            code_luma_quantiles=np.quantile(y,[0,.01,.5,.99,1]).tolist(),
            rgb_chroma_quantiles=np.quantile(chroma,[0,.1,.5,.9,1]).tolist(),
            high_clip_fraction=float((rgb>=1).any(axis=2).mean()),
            dark_clip_fraction=float((rgb<=0).all(axis=2).mean())))
    write_json(root/'rgb-statistics.json',dict(
        interpretation='Unpaired decoded RGB code-value diagnostics; unknown source color interpretation is not inferred. No automatic color acceptance.',
        frames=rows))
    indices=[0,16,64,128,192,256,304,319,320]
    sheet=np.full((3*170,768,3),22,dtype=np.uint8)
    for ordinal,index in enumerate(indices):
        bgr=cv2.imread(str(paths[index]),cv2.IMREAD_COLOR)
        ratio=min(256/bgr.shape[1],144/bgr.shape[0])
        thumb=cv2.resize(bgr,(round(bgr.shape[1]*ratio),round(bgr.shape[0]*ratio)))
        x=(ordinal%3)*256;y=(ordinal//3)*170
        sheet[y:y+thumb.shape[0],x:x+thumb.shape[1]]=thumb
        cv2.putText(sheet,f'source {index}   {index/16:.4f}s',(x+4,y+160),
                    cv2.FONT_HERSHEY_SIMPLEX,.4,(255,255,255),1,cv2.LINE_AA)
    if not cv2.imwrite(str(root/'samples.png'),sheet): raise ValueError('cannot write samples')
