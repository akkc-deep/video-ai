"""Deterministic composition frames, bounded encoding and final media checks."""
from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path
import shutil
import struct
from uuid import uuid4

from ..runtime.environment import build_child_env
from ..runtime.manifest import hash_file,thaw
from ..runtime.processes import run_logged
from ..runtime.timeline_checks import _again,_local


def command(args,*,config,paths,logger,cwd,operation):
    cwd=_local(logger.run_dir,Path(cwd))
    result=run_logged(tuple(str(x) for x in args),cwd=cwd,env=build_child_env(paths),timeout=300,logger=logger,stage='composition')
    record=dict(operation=operation,timeout_seconds=300,**thaw(result))
    path=logger.save_json(f'composition/command-{uuid4().hex}.json',record)
    record['record_path']=str(path)
    if result.returncode!=0 or result.timed_out:
        raise OSError(f'composition {operation} failed: {result.stderr_path}')
    return record


def ffmpeg(config):return [config.tools['ffmpeg'],'-nostdin','-n','-v','error','-xerror']


def validate_sequence(directory,count):
    if type(count) is not int or count<1:raise ValueError('positive frame count required')
    expected=[Path(directory)/f'frame_{i:06d}.png' for i in range(1,count+1)]
    if not Path(directory).is_dir() or set(Path(directory).iterdir())!=set(expected):raise ValueError('exact contiguous PNG sequence required')
    for p in expected:
        if p.is_symlink() or not p.is_file():raise ValueError('regular owned PNG frames required')
        with p.open('rb') as f:
            header=f.read(33)
        if len(header)!=33 or header[:8]!=b'\x89PNG\r\n\x1a\n' or header[12:16]!=b'IHDR':raise ValueError('invalid PNG frame')
        if struct.unpack('>II',header[16:24])!=(1920,1080) or header[24:29]!=bytes((8,2,0,0,0)):
            raise ValueError('every composition frame must be 1920x1080 RGB24 PNG')
    return expected


def raw_rgb(path,**kw):
    record=command([*ffmpeg(kw['config']),'-i',str(path),'-map','0:v:0','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],operation='raw_rgb',**kw)
    return Path(record['stdout_path']).read_bytes(),record


def validate_blended_pixels(plan,outputs,**kw):
    records=[]
    for row,path in zip(plan.ordered_frame_map,outputs,strict=True):
        positive=[c for c in row['contributors'] if c['weight_numerator']>0]
        if len(positive)!=2:continue
        a,b=positive;den=a['weight_denominator']
        payloads=[]
        for source in (a['frame_identity']['path'],b['frame_identity']['path'],path):
            raw,record=raw_rgb(source,**kw);payloads.append(raw);records.append(record)
        left,right,actual=payloads
        if not left or len(left)!=len(right) or len(left)!=len(actual):raise ValueError('blend RGB payload sizes differ')
        for x,y,value in zip(left,right,actual):
            wanted=min(255,max(0,(2*(x*a['weight_numerator']+y*b['weight_numerator'])+den)//(2*den)))
            if abs(value-wanted)>1:raise ValueError('blended pixels differ from original rational contributors')
    return records


def validate_normalized_music(source,normalized,**kw):
    before=hash_file(Path(source))
    record=command([*ffmpeg(kw['config']),'-i',str(source),'-vn','-ar','48000','-ac','2','-c:a','pcm_f32le','-f','f32le','pipe:1'],operation='verify_normalized_music',**kw)
    actual=hash_file(Path(normalized));expected=hash_file(Path(record['stdout_path']))
    if (actual.bytes,actual.sha256)!=(expected.bytes,expected.sha256):raise ValueError('normalized music differs from configured original source')
    _again({'music':before})
    return record


def blend_frame(left,right,target,*,left_numerator,right_numerator,denominator,**kw):
    if any(type(v) is not int for v in (left_numerator,right_numerator,denominator)) or min(left_numerator,right_numerator)<0 or denominator<1 or left_numerator+right_numerator!=denominator:raise ValueError('invalid rational blend weights')
    target=_local(kw['logger'].run_dir,Path(target))
    if target.exists():raise FileExistsError(target)
    expr=f'clip(floor((A*{left_numerator}+B*{right_numerator})/{denominator}+0.5),0,255)'
    return command([*ffmpeg(kw['config']),'-i',str(left),'-i',str(right),'-filter_complex',f"[0:v]format=gbrp[a];[1:v]format=gbrp[b];[a][b]blend=all_expr='{expr}',format=rgb24",'-frames:v','1',str(target)],operation='blend',**kw)


def materialize_frames(plan,**kw):
    folder=kw['cwd']/'video-frames';folder.mkdir()
    records=[];identities=[]
    for row in plan.ordered_frame_map:
        target=_local(kw['logger'].run_dir,folder/f'frame_{row["output_frame"]+1:06d}.png')
        positive=[c for c in row['contributors'] if c['weight_numerator']>0]
        originals={str(i):hash_file(Path(c['frame_identity']['path'])) for i,c in enumerate(row['contributors'])}
        for c,ident in zip(row['contributors'],originals.values()):
            if any(thaw(ident)[k]!=c['frame_identity'][k] for k in ('path','bytes','mtime_ns','sha256')):raise OSError('source PNG drift before copy/blend')
        if len(positive)==1:
            with Path(positive[0]['frame_identity']['path']).open('rb') as source,target.open('xb') as out:shutil.copyfileobj(source,out)
        elif len(positive)==2:
            a,b=positive
            records.append(blend_frame(Path(a['frame_identity']['path']),Path(b['frame_identity']['path']),target,left_numerator=a['weight_numerator'],right_numerator=b['weight_numerator'],denominator=a['weight_denominator'],**kw))
        else:raise ValueError('missing actual frame contributor')
        _again(originals);identities.append(thaw(hash_file(target)))
        if len(positive)==1 and identities[-1]['sha256']!=positive[0]['frame_identity']['sha256']:raise OSError('frame copy mismatch')
    validate_sequence(folder,plan.total_frames)
    return identities,records


def _number(value):
    try:return Fraction(value)
    except (TypeError,ValueError,ZeroDivisionError) as exc:raise ValueError('invalid media numeric field') from exc


def validate_probe(probe,frame_data,*,fps,total_frames,channels):
    if type(fps) is not int or fps not in (16,24) or type(total_frames) is not int or total_frames<1 or channels not in (1,2):raise ValueError('invalid expected composition format')
    streams=probe.get('streams')
    if not isinstance(streams,list) or len(streams)!=2:raise ValueError('exactly one video and one audio stream required')
    video=[s for s in streams if s.get('codec_type')=='video'];audio=[s for s in streams if s.get('codec_type')=='audio']
    if len(video)!=1 or len(audio)!=1:raise ValueError('wrong composition streams')
    v,a=video[0],audio[0]
    if (v.get('codec_name'),v.get('pix_fmt'),v.get('width'),v.get('height'))!=('h264','yuv420p',1920,1080):raise ValueError('wrong composition video format')
    if _number(v.get('avg_frame_rate'))!=fps or _number(v.get('r_frame_rate'))!=fps:raise ValueError('wrong output fps')
    if str(v.get('nb_read_frames'))!=str(total_frames):raise ValueError('wrong output frame count')
    if (a.get('codec_name'),str(a.get('sample_rate')),a.get('channels'))!=('aac','48000',channels):raise ValueError('wrong composition audio format')
    duration=Fraction(total_frames,fps);vd=_number(v.get('duration'));ad=_number(a.get('duration'))
    if abs(vd-duration)>Fraction(1,100000) or abs(ad-duration)>Fraction(1,10):raise ValueError('audio/video duration mismatch')
    if abs(_number(v.get('start_time','0')))>Fraction(1,48000) or abs(_number(a.get('start_time','0')))>Fraction(1,48000):raise ValueError('video/audio origin must be zero')
    if a.get('time_base','1/48000')!='1/48000':raise ValueError('AAC sample time base differs')
    frames=frame_data.get('frames')
    if not isinstance(frames,list) or len(frames)!=total_frames:raise ValueError('PTS frame coverage differs')
    for i,frame in enumerate(frames):
        if abs(_number(frame.get('best_effort_timestamp_time'))-Fraction(i,fps))>Fraction(1,100000):raise ValueError('non-CFR or nonzero-origin PTS')
    return dict(width=1920,height=1080,codec='h264',pixel_format='yuv420p',fps=fps,frames=total_frames,duration=float(duration),audio_codec='aac',sample_rate=48000,channels=channels,audio_duration=float(ad))


def validate_audio_packets(packets,samples):
    if not isinstance(packets,list) or not packets:raise ValueError('missing AAC packets')
    first=packets[0]
    skip=sum(x.get('skip_samples',0) for x in first.get('side_data_list',[]) if x.get('side_data_type')=='Skip Samples')
    if type(skip) is not int or skip!=1024 or type(first.get('pts')) is not int or first['pts']!=-skip:raise ValueError('AAC priming/effective origin differs')
    cursor=-skip
    for packet in packets:
        pts=packet.get('pts');duration=packet.get('duration')
        if type(pts) is not int or type(duration) is not int or duration<=0 or pts!=cursor:raise ValueError('AAC packet timeline gap/overlap')
        cursor=pts+duration
    # MP4 edit-list duration has millisecond precision. Preserve the complete
    # lossless PCM proof and allow at most that container quantization here.
    if abs(cursor-samples)>48:raise ValueError('AAC effective end differs from full narration budget')
    return skip


def inspect_composition(path,*,fps,frames,channels,**kw):
    path=Path(path);before=hash_file(path);config=kw['config']
    probe=command([config.tools['ffprobe'],'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],operation='probe',**kw)
    pts=command([config.tools['ffprobe'],'-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(path)],operation='pts',**kw)
    p=json.loads(Path(probe['stdout_path']).read_text(encoding='utf-8'));f=json.loads(Path(pts['stdout_path']).read_text(encoding='utf-8'))
    info=validate_probe(p,f,fps=fps,total_frames=frames,channels=channels)
    decode=command([*ffmpeg(config),'-i',str(path),'-map','0:v:0','-map','0:a:0','-f','null','-'],operation='decode',**kw)
    audio=command([*ffmpeg(config),'-i',str(path),'-map','0:a:0','-f','s16le','-acodec','pcm_s16le','pipe:1'],operation='decode_audio',**kw)
    decoded=Path(audio['stdout_path']).stat().st_size
    samples=decoded//(channels*2);expected=frames*(48000//fps)
    if decoded%(channels*2) or samples<expected or samples-expected>=2048:raise ValueError('AAC decoded duration truncated or padding exceeds encoder budget')
    packets=command([config.tools['ffprobe'],'-v','error','-select_streams','a:0','-show_packets','-of','json',str(path)],operation='audio_packets',**kw)
    data=json.loads(Path(packets['stdout_path']).read_text(encoding='utf-8'))['packets']
    skip=validate_audio_packets(data,expected)
    info.update(decoded_audio_samples=samples,tail_padding_samples=samples-expected,priming_samples=skip,identity=thaw(before))
    _again({'candidate':before})
    return info,[probe,pts,decode,audio,packets]


def encode_composition(sequence,audio,*,fps,frames,channels,**kw):
    sequence=Path(sequence);paths=validate_sequence(sequence,frames)
    ids={str(i):hash_file(p) for i,p in enumerate(paths)}
    folder=kw['cwd'];base=folder/'video-base.mp4';candidate=folder/'candidate.mp4';config=kw['config']
    for p in (base,candidate):
        if p.exists():raise FileExistsError(p)
    encode=command([*ffmpeg(config),'-framerate',str(fps),'-start_number','1','-i',str(sequence/'frame_%06d.png'),'-an','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough',str(base)],operation='encode_base',**kw)
    filter_path=folder/'burn.filter'
    with filter_path.open('x',encoding='ascii',newline='\n') as file:file.write("[0:v:0]subtitles=filename=subtitles.ass:fontsdir=fonts[v]\n")
    mux=command([*ffmpeg(config),'-i',str(base),'-i',str(audio),'-/filter_complex',str(filter_path),'-map','[v]','-map','1:a:0','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough','-c:a','aac','-b:a','192k','-ar','48000','-ac',str(channels),'-movflags','+faststart',str(candidate)],operation='burn_mux',**kw)
    validate_sequence(sequence,frames);_again(ids)
    info,records=inspect_composition(candidate,fps=fps,frames=frames,channels=channels,**kw)
    return info,[encode,mux,*records]


def verify_encoded_bytes(plan,*,channels,audio,**kw):
    """Reproduce into a unique audit namespace, never alter canonical outputs."""
    folder=kw['cwd'];config=kw['config'];run=kw['logger'].run_dir
    audit=_local(run,run/'logs/composition'/('replay-'+uuid4().hex));audit.mkdir()
    base=audit/'video-base.mp4';candidate=audit/'candidate.mp4'
    first=command([*ffmpeg(config),'-framerate',str(plan.output_fps),'-start_number','1','-i',str(folder/'video-frames/frame_%06d.png'),'-an','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough',str(base)],operation='replay_base',**kw)
    second=command([*ffmpeg(config),'-i',str(base),'-i',str(audio),'-/filter_complex',str(folder/'burn.filter'),'-map','[v]','-map','1:a:0','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough','-c:a','aac','-b:a','192k','-ar','48000','-ac',str(channels),'-movflags','+faststart',str(candidate)],operation='replay_mux',**kw)
    for name in ('video-base.mp4','candidate.mp4'):
        actual=hash_file(folder/name);expected=hash_file(audit/name)
        if (actual.bytes,actual.sha256)!=(expected.bytes,expected.sha256):raise ValueError('encoded bytes differ from canonical PNG/narration/subtitle replay: '+name)
    return [first,second]


def check_subtitle_render(events,settings,**kw):
    config=kw['config'];checks=[];records=[]
    for ordinal,event in enumerate(events,1):
        # A black control frame isolates only subtitle pixels; it is not motion review.
        at=(event['start_cs']+event['end_cs'])/200
        args=[*ffmpeg(config),'-f','lavfi','-i','color=c=black:s=1920x1080:r=100',
            '-vf',f"setpts=PTS+{at}/TB,subtitles=filename=subtitles.ass:fontsdir=fonts",'-frames:v','1','-pix_fmt','gray','-f','rawvideo','pipe:1']
        record=command(args,operation='subtitle_render',**kw);records.append(record)
        raw=Path(record['stdout_path']).read_bytes()
        if len(raw)!=1920*1080:raise ValueError('subtitle render frame incomplete')
        xs=[];ys=[];active=[]
        for y in range(1080):
            row=raw[y*1920:(y+1)*1920]
            points=[i for i,v in enumerate(row) if v>24]
            if points:xs.extend((min(points),max(points)));ys.append(y);active.append(y)
        if not xs:raise ValueError('subtitle has no rendered glyphs')
        bbox=[min(xs),min(ys),max(xs)+1,max(ys)+1]
        line_count=1+sum(b-a>settings.font_size//3 for a,b in zip(active,active[1:]))
        if bbox[0]<settings.margin or bbox[2]>1920-settings.margin or bbox[1]<settings.margin or bbox[3]>1080-settings.margin+settings.outline or line_count!=len(event['layout']['lines']):raise ValueError('actual subtitle exceeds margins/line layout')
        checks.append(dict(event_index=ordinal,bbox=bbox,line_count=line_count,literal_text='\n'.join(event['layout']['lines']),render_identity=thaw(hash_file(Path(record['stdout_path'])))))
    return dict(events=checks,commands=records)
