"""Independent fixed encoding factor and one complete RGB decode per output."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
from time import perf_counter
from types import SimpleNamespace


def encoding_args(ffmpeg, folder, output, *, encoder='libx264'):
    from ..runtime._scene_composition_commands import encode_args
    folder=Path(folder)
    context=dict(materialized=dict(ass=dict(path=str(folder/'subtitles.ass')),
        narration=dict(audio=dict(path=str(folder/'narration.wav')))),
        frozen=SimpleNamespace(config=SimpleNamespace(tools={'ffmpeg':ffmpeg})))
    args=encode_args(context,output)
    if encoder=='libx264':return args
    if encoder!='h264_nvenc':raise ValueError('unreviewed encoder')
    a,b=args.index('-c:v')+1,args.index('-fps_mode')
    args[a:b]=['h264_nvenc','-preset','p4','-rc','constqp','-qp','18','-pix_fmt','yuv420p']
    return args


def capability_from_text(encoders, help_text):
    available='h264_nvenc' in encoders and all(word in help_text for word in ('preset','p4','rc','constqp','qp'))
    return dict(status='available_driver_unverified' if available else 'unsupported',
        gpu_executed=False,reason='Encoder/options found; driver execution still requires authorization.' if available else
        'Required native h264_nvenc encoder/options missing; no flags changed or packages installed.')


def encoder_capability(ffmpeg):
    commands=[[str(ffmpeg),'-hide_banner','-encoders'],[str(ffmpeg),'-hide_banner','-h','encoder=h264_nvenc']]
    texts=[];rows=[]
    for args in commands:
        result=subprocess.run(args,capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        raw=result.stdout+result.stderr;texts.append(raw.decode('utf-8',errors='replace'))
        rows.append(dict(args=args,returncode=result.returncode,stdout_stderr_sha256=hashlib.sha256(raw).hexdigest()))
    value=capability_from_text(*texts)
    if any(row['returncode'] for row in rows):value.update(status='unsupported',reason='Capability command failed')
    return dict(value,commands=rows)


def compare_evidence(baseline, candidate):
    media_fields=('pts','frame_count','width','height','fps','colors')
    mismatches=[key for key in media_fields if baseline.get(key)!=candidate.get(key)]
    pixels=baseline.get('frame_rgb_sha256')==candidate.get('frame_rgb_sha256')
    return dict(status='rejected_media_contract' if mismatches else
        'rejected_pixel_contract' if not pixels else 'awaiting_human_review',
        mismatches=mismatches,pixels_equal=pixels,human_quality='unverified',
        default_encoder='libx264',qp_is_crf=False)


def inspect_encoded(path, *, ffmpeg, ffprobe, expected_frames):
    """PTS metadata probe plus exactly one streamed full RGB framehash decode."""
    path=Path(path)
    probe_args=[str(ffprobe),'-v','error','-show_streams','-of','json',str(path)]
    result=subprocess.run(probe_args,capture_output=True,timeout=600,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('encoded media probe failed')
    info=json.loads(result.stdout);videos=[v for v in info['streams'] if v['codec_type']=='video']
    if len(videos)!=1:raise ValueError('one complete video stream required')
    video=videos[0]
    if (video['width'],video['height'],Fraction(video['avg_frame_rate']))!=(1920,1080,16):
        raise ValueError('1080P/16fps contract differs')
    args=[str(ffmpeg),'-nostdin','-v','error','-xerror','-copyts','-i',str(path),'-map','0:v:0',
        '-vf','format=rgb24','-fps_mode','passthrough','-c:v','rawvideo','-pix_fmt','rgb24',
        '-enc_time_base:v','demux','-f','framehash','-hash','sha256','-']
    decoded=subprocess.run(args,capture_output=True,timeout=1200,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if decoded.returncode:raise RuntimeError('complete encoded RGB decode failed')
    hashes=[];pts=[];timebase=None
    for line in decoded.stdout.decode('ascii').splitlines():
        if line.startswith('#tb 0:'):timebase=Fraction(line.split(':',1)[1].strip())
        if line.startswith('#'):continue
        fields=[v.strip() for v in line.split(',')]
        if len(fields)!=6 or fields[0]!='0' or fields[4]!=str(1920*1080*3) or len(fields[5])!=64:
            raise ValueError('full RGB frame hash missing')
        if timebase is None:raise ValueError('decoded time base missing')
        hashes.append(fields[5]);pts.append(str(Fraction(fields[2])*timebase))
    if len(hashes)!=expected_frames or pts!=[str(Fraction(i,16)) for i in range(expected_frames)]:
        raise ValueError('complete RGB frame count/PTS differs')
    return dict(frame_rgb_sha256=hashes,pts=pts,frame_count=len(hashes),width=video['width'],
        height=video['height'],fps=video['avg_frame_rate'],
        colors={k:video.get(k) for k in ('color_range','color_space','color_transfer','color_primaries')},
        decode_count=1,probe_args=probe_args,decode_args=args)


def encode_once(folder, output, *, ffmpeg, encoder):
    from .upscale_experiment import baseline_api, read
    from .wan_fast_profiles import artifact, digest, Artifact
    folder,output=Path(folder).resolve(),Path(output).resolve()
    api=baseline_api();args=encoding_args(ffmpeg,folder,output,encoder=encoder)
    inputs={str(p.relative_to(folder)):artifact(p).identity_dict() for p in
        sorted([*folder.glob('frames/*.png'),folder/'subtitles.ass',folder/'narration.wav',*folder.glob('fonts/*')])}
    identity=dict(args=args,cwd=str(folder),inputs=inputs,ffmpeg=artifact(ffmpeg).identity_dict())
    request=Path(str(output)+'.intent.json');receipt=Path(str(output)+'.success.json')
    api.write_once(request,identity)
    if receipt.exists():
        value=read(receipt)
        if value['request_sha256']!=digest(identity):raise ValueError('encoding request drift')
        Artifact(**value['output']).verify();return value
    if output.exists():raise api.OutcomeUnknown('uncommitted encode retained; no overwrite/reencode')
    output.parent.mkdir(parents=True,exist_ok=True)
    started=perf_counter()
    result=subprocess.run(args,cwd=folder,capture_output=True,timeout=1200,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    seconds=perf_counter()-started
    Path(str(output)+'.stdout').write_bytes(result.stdout);Path(str(output)+'.stderr').write_bytes(result.stderr)
    if result.returncode:raise RuntimeError('fixed encoding command failed; raw diagnostics retained')
    for value in inputs.values():Artifact(**value).verify()
    value=dict(request_sha256=digest(identity),output=artifact(output).identity_dict(),encode_seconds=seconds)
    api.write_once(receipt,value);return value
