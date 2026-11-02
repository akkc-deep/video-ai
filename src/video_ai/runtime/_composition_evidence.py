"""Rebuild composition associations and verify every command/output receipt."""
from datetime import datetime
from pathlib import Path
import json

from ..config import read_json
from ..planning.start_images import keys
from ..planning.source_clips import _same
from ..planning.composition import CompositionSettings
from ..media.composition_audio import validate_narration,validate_mix
from ..media.font_metrics import PrivateFont
from ..media.subtitles import plan_subtitles,srt_text,ass_text
from ..media.composition_video import validate_sequence,validate_probe,inspect_composition,ffmpeg,validate_audio_packets,verify_encoded_bytes,validate_blended_pixels,validate_normalized_music
from .logging import RunLogger
from .manifest import hash_file,thaw,_timestamp
from .timeline_checks import _local,_again
from ._composition_inputs import fresh,equal_identity
from .execution_limits import command_receipt_policy

FIELDS='schema_version run_id created_at status passed staging_only input_identities settings settings_identity plan_identity frame_mappings requirement_bindings cue_checks narration_identity mixed_audio_identity subtitles candidate_identity effective_media provenance validation request_evidence'
EXECUTION_FIELDS='schema_version run_id plan_identity output_frames audio_plan normalized_music_identity mixed_audio_plan subtitle_render font_metrics commands'


def index_evidence(run,folder,plan,execution,commands):
    files={plan,execution,*[p for p in folder.rglob('*') if p.is_file()]}
    for record in commands:
        files.update(Path(record[k]) for k in ('record_path','stdout_path','stderr_path'))
    return {p.relative_to(run).as_posix():thaw(hash_file(_local(run,p))) for p in sorted(files)}


def _same_sources(actual,expected):
    if isinstance(actual,dict) and isinstance(expected,dict):
        if set(actual)==set('path bytes mtime_ns sha256 verified_at'.split()) and set(expected)==set(actual):return equal_identity(actual,expected)
        return set(actual)==set(expected) and all(_same_sources(actual[k],expected[k]) for k in actual)
    if isinstance(actual,(list,tuple)) and isinstance(expected,(list,tuple)):
        return len(actual)==len(expected) and all(_same_sources(a,b) for a,b in zip(actual,expected))
    return _same(actual,expected)


def _render(raw,event,settings):
    if len(raw)!=1920*1080:raise ValueError('incomplete actual subtitle render')
    xs=[];ys=[]
    for y in range(1080):
        points=[x for x,v in enumerate(raw[y*1920:(y+1)*1920]) if v>24]
        if points:xs.extend((min(points),max(points)));ys.append(y)
    if not xs:raise ValueError('no rendered subtitle pixels')
    box=[min(xs),min(ys),max(xs)+1,max(ys)+1]
    count=1+sum(b-a>settings.font_size//3 for a,b in zip(ys,ys[1:]))
    if box[0]<settings.margin or box[2]>1920-settings.margin or box[1]<settings.margin or box[3]>1080-settings.margin+settings.outline or count!=len(event['layout']['lines']):raise ValueError('actual subtitle layout exceeds limits')
    return box,count


def _commands(config,run,execution,folder,plan,covered):
    commands=execution['commands'];expected_ops=['blend']*sum(1 for row in plan.ordered_frame_map if sum(c['weight_numerator']>0 for c in row['contributors'])==2)
    if execution['normalized_music_identity']:expected_ops+=['normalize_music']
    expected_ops+=['subtitle_render']*len(plan.subtitle_events)+['encode_base','burn_mux','probe','pts','decode','decode_audio','audio_packets']
    if not isinstance(commands,list) or [r.get('operation') for r in commands]!=expected_ops:raise ValueError('missing/extra/reordered composition commands')
    outputs=[];record_paths=set()
    for record in commands:
        fields='operation timeout_seconds args cwd returncode timed_out stdout_path stderr_path started_at finished_at record_path'
        if 'time_limits' in record:fields+=' time_limits'
        keys(record,fields,'command receipt')
        if record['record_path'] in record_paths:raise ValueError('repeated command receipt')
        record_paths.add(record['record_path'])
        if type(record['returncode']) is not int or record['returncode']!=0 or record['timed_out'] is not False or not command_receipt_policy(record) or record['cwd']!=str(folder):raise ValueError('failed/invalid command execution policy')
        start,end=(datetime.fromisoformat(record[k]) for k in ('started_at','finished_at'))
        elapsed=(end-start).total_seconds()
        if (not start.tzinfo or not end.tzinfo or elapsed<0
                or record['timeout_seconds'] is not None and elapsed>301):raise ValueError('command deadline/time evidence differs')
        for k in ('record_path','stdout_path','stderr_path'):
            p=_local(run,Path(record[k]));name=p.relative_to(run).as_posix()
            if name not in covered:raise ValueError('command evidence omitted')
        stored=read_json(Path(record['record_path']))
        if not _same(stored,{k:v for k,v in record.items() if k!='record_path'}):raise ValueError('command receipt differs from raw record')
        if Path(record['stderr_path']).read_bytes():raise ValueError('composition command reported errors')
        args=record['args']
        if not isinstance(args,list) or not args or args[0]!=str(config.tools['ffprobe' if record['operation'] in ('probe','pts','audio_packets') else 'ffmpeg']):raise ValueError('command executable differs')
        if '-shortest' in args or '-t' in args or '-y' in args:raise ValueError('composition command truncates/overwrites')
        outputs.append(record)
    candidate=folder/'candidate.mp4';base=folder/'video-base.mp4';audio=folder/('mixed.wav' if execution['mixed_audio_plan'] else 'narration.wav')
    expected={
        'normalize_music':[*ffmpeg(config),'-i',str(config.media.music),'-vn','-ar','48000','-ac','2','-c:a','pcm_f32le','-f','f32le',str(folder/'music.f32')],
        'encode_base':[*ffmpeg(config),'-framerate',str(plan.output_fps),'-start_number','1','-i',str(folder/'video-frames/frame_%06d.png'),'-an','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough',str(base)],
        'burn_mux':[*ffmpeg(config),'-i',str(base),'-i',str(audio),'-/filter_complex',str(folder/'burn.filter'),'-map','[v]','-map','1:a:0','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough','-c:a','aac','-b:a','192k','-ar','48000','-ac','2' if execution['mixed_audio_plan'] else '1','-movflags','+faststart',str(candidate)],
        'probe':[config.tools['ffprobe'],'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(candidate)],
        'pts':[config.tools['ffprobe'],'-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(candidate)],
        'decode':[*ffmpeg(config),'-i',str(candidate),'-map','0:v:0','-map','0:a:0','-f','null','-'],
        'decode_audio':[*ffmpeg(config),'-i',str(candidate),'-map','0:a:0','-f','s16le','-acodec','pcm_s16le','pipe:1'],
        'audio_packets':[config.tools['ffprobe'],'-v','error','-select_streams','a:0','-show_packets','-of','json',str(candidate)]}
    expected={k:[str(x) for x in v] for k,v in expected.items()}
    blends=[]
    for row in plan.ordered_frame_map:
        positive=[c for c in row['contributors'] if c['weight_numerator']>0]
        if len(positive)!=2:continue
        a,b=positive
        expr=f"clip(floor((A*{a['weight_numerator']}+B*{b['weight_numerator']})/{a['weight_denominator']}+0.5),0,255)"
        blends.append([str(x) for x in [*ffmpeg(config),'-i',a['frame_identity']['path'],'-i',b['frame_identity']['path'],'-filter_complex',f"[0:v]format=gbrp[a];[1:v]format=gbrp[b];[a][b]blend=all_expr='{expr}',format=rgb24",'-frames:v','1',folder/'video-frames'/f'frame_{row["output_frame"]+1:06d}.png']])
    if [r['args'] for r in commands if r['operation']=='blend']!=blends:raise ValueError('composition blend arguments changed')
    for record in commands:
        if record['operation'] in expected and record['args']!=expected[record['operation']]:raise ValueError('composition media command arguments changed')
    return {r['operation']:r for r in commands if r['operation'] in expected}


def validate(config,run,report,context,*,inspect_actual=True):
    from .composition_checks import validation
    keys(report,FIELDS,'composition report')
    if type(report['schema_version']) is not int or report['schema_version']!=1 or report['run_id']!=run.name or report['status']!='completed' or report['passed'] is not True or report['staging_only'] is not True:raise ValueError('invalid composition report status/run')
    _timestamp(report['created_at'])
    if not _same(report['validation'],validation()):raise ValueError('composition validation/final review limits differ')
    plan=context['plan'];settings=context['settings'];folder=_local(run,run/'staging/composition');ids={}
    for field,want in [('settings',settings),('frame_mappings',plan.ordered_frame_map),('requirement_bindings',plan.requirement_bindings),('cue_checks',plan.cue_checks)]:
        if not _same(report[field],want):raise ValueError('composition '+field+' differs from reconstruction')
    if not _same_sources(report['input_identities'],thaw(context['identities'])) or not _same_sources(report['provenance'],context['provenance']) or not equal_identity(report['settings_identity'],thaw(context['settings_identity'])):raise ValueError('composition frozen inputs/provenance differ')
    evidence=report['request_evidence']
    if not isinstance(evidence,dict) or not evidence:raise ValueError('composition evidence index missing')
    aliases=set()
    for name,identity in evidence.items():
        if type(name) is not str or '\\' in name or Path(name).is_absolute() or Path(name).drive or Path(name).root or Path(name).as_posix()!=name or any(p in ('.','..') for p in name.split('/')) or name.casefold() in aliases:raise ValueError('evidence alias/path escape')
        aliases.add(name.casefold());ids[name]=fresh(identity,run=run,expected=_local(run,run/name))
    required=['logs/composition/plan.json','logs/composition/execution.json']
    if not all(name in evidence for name in required):raise ValueError('missing plan/execution evidence')
    fresh(report['plan_identity'],run=run,expected=run/required[0])
    if not _same(read_json(run/required[0]),plan):raise ValueError('saved plan differs from complete reconstruction')
    execution=read_json(run/required[1]);keys(execution,EXECUTION_FIELDS,'composition execution')
    if type(execution['schema_version']) is not int or execution['schema_version']!=1 or execution['run_id']!=run.name or not equal_identity(execution['plan_identity'],report['plan_identity']):raise ValueError('execution plan/run differs')
    output=validate_sequence(folder/'video-frames',plan.total_frames)
    if not isinstance(execution['output_frames'],list) or len(execution['output_frames'])!=len(output):raise ValueError('output frame evidence coverage differs')
    for row,path,ident in zip(plan.ordered_frame_map,output,execution['output_frames']):
        fresh(ident,run=run,expected=path)
        if path.relative_to(run).as_posix() not in evidence or not equal_identity(ident,evidence[path.relative_to(run).as_posix()]):raise ValueError('frame evidence omitted/different')
        contributors=[c for c in row['contributors'] if c['weight_numerator']>0]
        if len(contributors)==1 and (ident['sha256'],ident['bytes'])!=(contributors[0]['frame_identity']['sha256'],contributors[0]['frame_identity']['bytes']):raise ValueError('actual output frame differs from selected native frame')
    fresh(report['narration_identity'],run=run,expected=folder/'narration.wav')
    if not _same(validate_narration(context['timeline'],folder/'narration.wav'),execution['audio_plan']):raise ValueError('narration plan/sample payload differs')
    if config.media.music:
        fresh(execution['normalized_music_identity'],run=run,expected=folder/'music.f32');fresh(report['mixed_audio_identity'],run=run,expected=folder/'mixed.wav')
        if not _same(validate_mix(folder/'narration.wav',folder/'music.f32',folder/'mixed.wav',settings=settings),execution['mixed_audio_plan']):raise ValueError('music mix differs')
    elif any(execution[k] is not None for k in ('normalized_music_identity','mixed_audio_plan')) or report['mixed_audio_identity'] is not None:raise ValueError('unexpected music branch')
    font=folder/'fonts/font.ttc';font_name=font.relative_to(run).as_posix()
    if font_name not in evidence or evidence[font_name]['sha256']!=context['identities']['font'].sha256:raise ValueError('font copy/source differs')
    with PrivateFont(font,settings.font_name,settings.font_size) as metrics:
        events=plan_subtitles(context['timeline'],settings,measure=metrics.measure)
        if not _same(execution['font_metrics'],dict(requested_face=metrics.name,selected_face=metrics.selected_face,size=metrics.size)):raise ValueError('font measurement selection differs')
    keys(report['subtitles'],'srt_identity ass_identity events','subtitles')
    if not _same(events,report['subtitles']['events']):raise ValueError('subtitle text/timing/layout differs')
    for key,name,text in [('srt_identity','subtitle.srt',srt_text(events)),('ass_identity','subtitles.ass',ass_text(events,settings))]:
        fresh(report['subtitles'][key],run=run,expected=folder/name)
        if (folder/name).read_bytes()!=text.encode('utf-8'):raise ValueError('actual subtitle characters/serialization differ')
    if (folder/'burn.filter').read_text(encoding='ascii')!="[0:v:0]subtitles=filename=subtitles.ass:fontsdir=fonts[v]\n":raise ValueError('unsafe subtitle filter')
    media_commands=_commands(config,run,execution,folder,plan,evidence)
    render=execution['subtitle_render'];keys(render,'events commands','subtitle render')
    actual_render=[r for r in execution['commands'] if r['operation']=='subtitle_render']
    if not _same(render['commands'],actual_render) or len(render['events'])!=len(events):raise ValueError('subtitle render evidence coverage differs')
    for ordinal,(event,saved,record) in enumerate(zip(events,render['events'],actual_render),1):
        at=(event['start_cs']+event['end_cs'])/200
        wanted=[*ffmpeg(config),'-f','lavfi','-i','color=c=black:s=1920x1080:r=100','-vf',f'setpts=PTS+{at}/TB,subtitles=filename=subtitles.ass:fontsdir=fonts','-frames:v','1','-pix_fmt','gray','-f','rawvideo','pipe:1']
        if record['args']!=[str(x) for x in wanted]:raise ValueError('subtitle render command differs')
        identity=fresh(saved['render_identity'],run=run,expected=Path(record['stdout_path']))
        box,count=_render(Path(record['stdout_path']).read_bytes(),event,settings)
        expected=dict(event_index=ordinal,bbox=box,line_count=count,literal_text='\n'.join(event['layout']['lines']),render_identity=thaw(identity))
        if not _same_sources(saved,expected):raise ValueError('actual subtitle bbox/layout differs')
    p=json.loads(Path(media_commands['probe']['stdout_path']).read_text(encoding='utf-8'));f=json.loads(Path(media_commands['pts']['stdout_path']).read_text(encoding='utf-8'))
    channels=2 if config.media.music else 1
    media=validate_probe(p,f,fps=plan.output_fps,total_frames=plan.total_frames,channels=channels)
    decoded=Path(media_commands['decode_audio']['stdout_path']).stat().st_size
    samples=decoded//(channels*2)
    if decoded%(channels*2) or not 0<=samples-plan.video_samples<2048:raise ValueError('AAC decoded samples/padding differ')
    packets=json.loads(Path(media_commands['audio_packets']['stdout_path']).read_text(encoding='utf-8'))['packets']
    skip=validate_audio_packets(packets,plan.video_samples)
    media.update(decoded_audio_samples=samples,tail_padding_samples=samples-plan.video_samples,priming_samples=skip)
    if not _same(media,report['effective_media']):raise ValueError('actual candidate format differs from report')
    fresh(report['candidate_identity'],run=run,expected=folder/'candidate.mp4')
    if inspect_actual:
        kw=dict(config=config,paths=context['paths'],logger=RunLogger(run),cwd=folder)
        validate_blended_pixels(plan,output,**kw)
        if config.media.music:validate_normalized_music(config.media.music,folder/'music.f32',**kw)
        verify_encoded_bytes(plan,channels=channels,audio=folder/('mixed.wav' if channels==2 else 'narration.wav'),**kw)
        actual,_=inspect_composition(folder/'candidate.mp4',fps=plan.output_fps,frames=plan.total_frames,channels=channels,config=config,paths=context['paths'],logger=RunLogger(run),cwd=folder)
        if not _same({k:v for k,v in actual.items() if k!='identity'},media):raise ValueError('fresh candidate decode/probe differs')
    required_files={p.relative_to(run).as_posix() for p in folder.rglob('*') if p.is_file()}
    required_files.update(required)
    for record in execution['commands']:required_files.update(Path(record[k]).relative_to(run).as_posix() for k in ('record_path','stdout_path','stderr_path'))
    if set(evidence)!=required_files:raise ValueError('composition evidence missing/extra files')
    _again(ids);_again(context['identities'])
    return ids
