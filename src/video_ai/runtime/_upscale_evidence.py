"""Reconstruct every frame, whole workflow, raw HTTP, media command and mapping."""
from datetime import datetime
import math
from pathlib import Path
from uuid import UUID

from ..config import read_json
from ..planning.start_images import keys
from ..planning.upscale import upscale_frame_mapping,clip_deadline_seconds
from ..media.video import validate_video_probe
from .manifest import thaw,_timestamp
from .timeline_checks import _local,_again,_fresh as artifact_fresh
from .component_checks import output_path
from ._source_clip_evidence import command,names
from ._upscale_inputs import fresh,same,graph,validate_remote
from ._legacy_execution_policy import unlimited_receipt,receipt_fields

DRAFT_FIELDS='schema_version run_id created_at status passed source_clips_identity source_review_identity source_review_method source_validation effective_media clips requirement_clips frame_mappings model_identity workflow_identity mapping_identity provenance validation request_evidence'
CLIP_FIELDS='shot_id primary_unit_id budget source_identity upscaled_identity width height native_fps source_frames upscaled_frames parameters frames evidence_identities'
FRAME_FIELDS='schema_version run_id shot_id frame_index source_frame_index source_identity input_identity input_copy_identity workflow_identity mapping_identity model_identity parameters submission output_identity upscaled_frame_identity evidence_identities'


def validation(ready):
    return dict(structure_passed=True,media_passed=True,frame_mapping_passed=True,
        video_text_semantics_passed=ready,motion_semantics_passed=ready,upscale_quality_passed=ready,
        ready_for_composition=ready,final_video_sync='unverified',full_film_acceptance='unverified')


def requirements(source,clips):
    targets={c['shot_id']:c['upscaled_identity'] for c in clips}
    return [dict(row,actual_artifact=targets[row['clip_shot_id']],source_actual_artifact=row['actual_artifact']) for row in source['requirement_clips']]


def identity_equal(a,b):
    return all(same(a[k],b[k]) for k in ('path','bytes','sha256','mtime_ns'))


def frame_command(record,args,run,covered, *, start,end,json_output=False,unlimited=False):
    """Task10 commands must fit their total interval and report no raw errors."""
    out=command(record,args,run,covered)
    started=datetime.fromisoformat(record['started_at']).timestamp();finished=datetime.fromisoformat(record['finished_at']).timestamp()
    if started<start or (end is not None and finished>end) or (not unlimited and finished-started>300):
        raise ValueError('frame media command exceeds absolute deadline or durable frame completion')
    if Path(record['stderr_path']).read_bytes():raise ValueError('frame media command stderr reports errors contradicting success')
    if not json_output and out.read_bytes():raise ValueError('frame media command reports errors contradicting success')
    return out


def png(config,run,path,record,covered,width,height, *, start,end,unlimited=False):
    keys(record,'info probe commands','PNG inspection');info=record['info']
    keys(info,'identity width height format pixel_format','PNG info')
    if not identity_equal(info['identity'],thaw(fresh(info['identity'],run=run,expected=path))):raise ValueError('PNG receipt differs')
    streams=record['probe'].get('streams')
    if not isinstance(streams,list) or len(streams)!=1:raise ValueError('one PNG stream required')
    stream=streams[0]
    wanted=dict(codec_type='video',codec_name='png',pix_fmt='rgb24',nb_read_frames='1',width=width,height=height)
    if any(not same(stream.get(k),v) for k,v in wanted.items()) or not same([info[k] for k in ('width','height','format','pixel_format')],[width,height,'png','rgb24']):raise ValueError('raw PNG probe contradicts RGB24 single-frame dimensions')
    commands=record['commands']
    if not isinstance(commands,list) or len(commands)!=2:raise ValueError('complete PNG probe/decode commands required')
    probe_args=(config.tools['ffprobe'],'-v','error','-count_frames','-show_streams','-show_format','-of','json',path)
    decode_args=(config.tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',path,'-f','null','-')
    out=frame_command(commands[0],probe_args,run,covered,start=start,end=end,json_output=True,unlimited=unlimited)
    if not same(read_json(out),record['probe']):raise ValueError('raw PNG stdout differs from inspection')
    frame_command(commands[1],decode_args,run,covered,start=start,end=end,unlimited=unlimited)


def media(config,run,clip,source,records,snapshot, *, clip_start,clip_end,partial=False,v2=False,reused_frames=()):
    unlimited=unlimited_receipt(clip)
    covered=names(clip['evidence_identities'],records);uid=clip['shot_id'];images={};extracts=[];encodes=[];videos=[]
    expected={};generated={}
    extraction=[read_json(run/n) for n in covered if n.startswith('logs/upscale/extract-') and n.endswith('.json')]
    if len(extraction)!=1:raise ValueError('one independent clip extraction required')
    rows=extraction[0]['frames']
    for row in rows:expected[Path(row['identity']['path'])]=(source['width'],source['height'])
    for frame in clip['frames']:
        if f"{uid}:frame_{frame['frame_index']:06d}" in reused_frames:
            if partial:
                # An interrupted child has not encoded/inspected its copied
                # PNGs yet. The import consumer has replayed native decode;
                # preserve that origin and recheck the exact current copy.
                fresh(frame['upscaled_frame_identity'],run=run,expected=run/'shots'/uid/'upscaled-frames'/f"frame_{frame['frame_index']:06d}.png")
            else:expected[Path(frame['upscaled_frame_identity']['path'])]=(1920,1080)
            continue
        expected[Path(frame['input_identity']['path'])]=(source['width'],source['height'])
        for key in (('output_identity',) if partial else ('output_identity','upscaled_frame_identity')):expected[Path(frame[key]['path'])]=(1920,1080)
        generated[Path(frame['output_identity']['path'])]=frame
    for name in covered:
        path=run/name
        if path.parent!=run/'logs/upscale' or path.suffix!='.json':continue
        if path.name.startswith('media-'):
            if not path.name.startswith('media-'+uid+'-') and not path.name.startswith('media-'+uid+'_frame_'):raise ValueError('PNG inspection belongs to another clip')
            record=read_json(path);target=Path(record['info']['identity']['path'])
            if target not in expected:raise ValueError('PNG inspection targets an unregistered frame')
            start,end=clip_start,clip_end;command_unlimited=unlimited
            if target in generated:
                frame=generated[target];unit_id=f"{uid}:frame_{frame['frame_index']:06d}"
                origin=frame_origin(frame,snapshot,v2)
                start=max(start,origin)
                command_unlimited=unlimited_receipt(frame)
                frame_limit=min(frame['checkpoint_identity']['mtime_ns']/1e9,
                    datetime.fromisoformat(snapshot['units']['frame'][unit_id]['finished_at']).timestamp())
                if not command_unlimited:frame_limit=min(frame_limit,origin+config.timeouts['upscale_frame'])
                end=frame_limit if end is None else min(end,frame_limit)
            # Source extraction and later encoding-copy inspection use the clip interval.
            # Only the actual generated PNG belongs to the original frame interval.
            png(config,run,target,record,covered,*expected[target],start=start,end=end,unlimited=command_unlimited);images.setdefault(target,[]).append(name)
        elif path.name.startswith('extract-'):extracts.append(read_json(path))
        elif path.name.startswith('encode-'):encodes.append(read_json(path))
        elif path.name.startswith('video-'):videos.append(read_json(path))
    if set(images)!=set(expected) or len(extracts)!=1 or len(encodes)!=(0 if partial else 1) or len(videos)!=(0 if partial else 1):raise ValueError('all PNGs and one extract/encode/video inspection required')
    if (partial or v2) and any(len(items)!=1 for items in images.values()):raise ValueError('duplicate resumed PNG inspection evidence')
    extract=extracts[0];keys(extract,'source_identity width height frames command','extraction')
    original=[dict(index=i,source_frame_index=i-1,identity=row['identity']) for i,row in enumerate(rows,1)]
    if len(rows)!=clip['source_frames']:raise ValueError('complete ordered extraction required')
    for i,row in enumerate(rows,1):
        keys(row,'index source_frame_index identity','extraction frame')
        target=run/'shots'/uid/'frames'/f'frame_{i:06d}.png'
        fresh(row['identity'],run=run,expected=target)
        if type(row['index']) is not int or row['index']!=i or type(row['source_frame_index']) is not int or row['source_frame_index']!=i-1:raise ValueError('extraction frame numeric order differs')
    for frame,row in zip(clip['frames'],rows):
        if not same(frame['input_identity'],row['identity']):raise ValueError('checkpoint extraction input differs')
    if not identity_equal(extract['source_identity'],clip['source_identity']) or not same(extract['frames'],original) or not same([extract['width'],extract['height']],[source['width'],source['height']]):raise ValueError('ordered extraction frames/source differ')
    frame_command(extract['command'],(config.tools['ffmpeg'],'-nostdin','-n','-v','error','-xerror','-i',Path(clip['source_identity']['path']),
        '-map','0:v:0','-vf','format=rgb24','-fps_mode','passthrough','-start_number','1',run/'shots'/uid/'frames/frame_%06d.png'),run,covered,start=clip_start,end=clip_end,unlimited=unlimited)
    for frame in clip['frames']:
        if f"{uid}:frame_{frame['frame_index']:06d}" in reused_frames:continue
        frame_names=names(frame['evidence_identities'],records)
        output=Path(frame['output_identity']['path'])
        if not set(images[output])&frame_names:raise ValueError('frame omits independent generated PNG inspection')
        for name in set(images[output])&frame_names:
            for c in read_json(run/name)['commands']:
                if any(Path(c[k]).relative_to(run).as_posix() not in frame_names for k in ('stdout_path','stderr_path')):raise ValueError('frame PNG raw evidence missing')
    if partial:return
    encoded=encodes[0];keys(encoded,'frames target command','encoding')
    if not isinstance(encoded['frames'],list) or len(encoded['frames'])!=clip['source_frames']:raise ValueError('encoding sequence incomplete')
    for index,(row,frame) in enumerate(zip(encoded['frames'],clip['frames']),1):
        keys(row,'index source_frame_index identity','encoding frame')
        if type(row['index']) is not int or row['index']!=index or type(row['source_frame_index']) is not int or row['source_frame_index']!=index-1 or not identity_equal(row['identity'],frame['upscaled_frame_identity']):raise ValueError('encoding numeric frame mapping differs')
    target=Path(clip['upscaled_identity']['path'])
    frame_command(encoded['command'],(config.tools['ffmpeg'],'-nostdin','-n','-v','error','-xerror','-framerate','16','-start_number','1','-i',
        run/'shots'/uid/'upscaled-frames/frame_%06d.png','-an','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough',target),run,covered,start=clip_start,end=clip_end,unlimited=unlimited)
    video=videos[0];keys(video,'info probe frames commands','video inspection');info=video['info']
    keys(info,'identity width height codec pixel_format fps frames duration','video info')
    metadata=validate_video_probe(video['probe'],video['frames'],width=1920,height=1080)
    if not same({k:v for k,v in info.items() if k!='identity'},metadata) or info['pixel_format']!='yuv420p' or type(info['frames']) is not int or info['frames']!=clip['source_frames'] or abs(info['duration']-clip['source_frames']/16)>.1 or not identity_equal(info['identity'],clip['upscaled_identity']) or not same(encoded['target'],info):raise ValueError('encoded media count/PTS/duration/identity differs')
    args=[(config.tools['ffprobe'],'-v','error','-count_frames','-show_streams','-show_format','-of','json',target),
        (config.tools['ffprobe'],'-v','error','-show_frames','-of','json',target),
        (config.tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',target,'-f','null','-')]
    if not isinstance(video['commands'],list) or len(video['commands'])!=3:raise ValueError('complete video probe/PTS/decode commands required')
    for index,(c,a) in enumerate(zip(video['commands'],args)):
        out=frame_command(c,a,run,covered,start=clip_start,end=clip_end,json_output=index<2,unlimited=unlimited)
        if index<2 and not same(read_json(out),video['probe' if index==0 else 'frames']):raise ValueError('raw video probe/PTS differs')


def frame_origin(frame,snapshot,v2):
    origin=frame['input_copy_identity']['mtime_ns']/1e9
    if v2:
        uid=f"{frame['shot_id']}:frame_{frame['frame_index']:06d}"
        origin=max(origin,datetime.fromisoformat(snapshot['units']['frame'][uid]['started_at']).timestamp())
    return origin


def http(config,run,frame,saved,t,wanted,records,clip_end, *, frame_start=None,durable_end=None):
    covered=names(frame['evidence_identities'],records);prompt=frame['submission']['prompt_id'];uid=f"{frame['shot_id']}:frame_{frame['frame_index']:06d}"
    intent=Path(saved['request_path']);history=Path(saved['response_path'])
    if not {intent.relative_to(run).as_posix(),history.relative_to(run).as_posix()}<=covered:raise ValueError('frame intent/history evidence missing')
    data=read_json(history);entry=data.get(prompt,{})
    if entry.get('status',{}).get('completed') is not True or entry.get('status',{}).get('status_str')!='success':raise ValueError('successful frame history required')
    outputs=entry.get('outputs',{}).get('5',{}).get('images')
    if not isinstance(outputs,list) or len(outputs)!=1 or output_path(run,outputs[0])!=Path(frame['output_identity']['path']):raise ValueError('frame history mapped output differs')
    posts=0;remote=False;tracking=False
    if frame_start is None:frame_start=frame['input_copy_identity']['mtime_ns']/1e9
    unlimited=unlimited_receipt(frame)
    frame_end=None if unlimited else frame_start+config.timeouts['upscale_frame']
    if clip_end is not None:frame_end=clip_end if frame_end is None else min(frame_end,clip_end)
    for name in covered:
        if not name.startswith('logs/http/') or not name.endswith('.request.json'):continue
        stem=name[:-len('.request.json')]
        if not {name,stem+'.response.json',stem+'.body'}<=covered:raise ValueError('frame HTTP trio incomplete')
        req=read_json(run/name);res=read_json(run/(stem+'.response.json'));body=run/(stem+'.body')
        keys(req,'method url headers json_body timeout stage unit_id started_at','HTTP request');keys(res,'method url stage unit_id status headers bytes truncated finished_at error','HTTP response')
        _timestamp(req['started_at']);_timestamp(res['finished_at'])
        if datetime.fromisoformat(res['finished_at'])<datetime.fromisoformat(req['started_at']):raise ValueError('HTTP time reversed')
        cap=config.timeouts['comfy_request'] if unlimited else min(config.timeouts['comfy_request'],config.timeouts['upscale_frame'])
        if type(req['timeout']) not in (int,float) or not math.isfinite(req['timeout']) or not 0<req['timeout']<=cap:raise ValueError('HTTP exceeds bounded frame/request budget')
        started=datetime.fromisoformat(req['started_at']).timestamp();finished=datetime.fromisoformat(res['finished_at']).timestamp()
        if (started<frame_start or (frame_end is not None and (finished>frame_end or req['timeout']>min(config.timeouts['comfy_request'],frame_end-started)))
                or finished-started>req['timeout']):
            raise ValueError('HTTP evidence exceeds absolute frame/clip deadline or request budget')
        if durable_end is not None and finished>durable_end:raise ValueError('HTTP response evidence postdates durable frame completion')
        if any(not same(req[k],res[k]) for k in ('method','url','stage','unit_id')) or req['stage']!='upscale' or req['unit_id']!=uid or type(res['bytes']) is not int or res['bytes']!=body.stat().st_size or type(res['truncated']) is not bool:raise ValueError('HTTP association/body bytes differ')
        good=type(res['status']) is int and res['status']==200 and res['truncated'] is False and res['error'] is None
        if req['url']==config.services['comfyui']+'/prompt' and req['method']=='POST':
            posts+=1;keys(req['json_body'],'prompt client_id','prompt body')
            if not good or not same(req['json_body']['prompt'],wanted) or req['json_body']['client_id']!=saved['client_id']:raise ValueError('actual frame POST graph differs')
            accepted=read_json(body);keys(accepted,'prompt_id number node_errors','acceptance')
            if accepted['prompt_id']!=prompt or not same(accepted['number'],saved['number']) or not isinstance(accepted['node_errors'],dict):raise ValueError('actual HTTP prompt acceptance differs')
            if datetime.fromisoformat(req['started_at'])<datetime.fromisoformat(saved['submitted_at']):raise ValueError('POST predates intent')
        elif req['url']==config.services['comfyui']+'/object_info' and req['method']=='GET' and good:validate_remote(t,read_json(body));remote=True
        elif req['url']==config.services['comfyui']+'/history/'+prompt and req['method']=='GET' and good:
            if body==history:
                if not same(read_json(body),data):raise ValueError('raw history differs')
                tracking=True
        elif req['url']!=config.services['comfyui']+'/queue':raise ValueError('unexpected frame HTTP route')
    if posts!=1 or not remote or not tracking:raise ValueError('one frame POST plus full remote and same-ID history required')


def validate(config,run,draft,context,snapshot, *, _partial=False,_reused_frames=None,_reused_clips=None):
    if draft.get('schema_version')==3 and draft.get('import_identity') is not None and _reused_frames is None:
        from .pipeline_import import validate_mixed_upscale
        return validate_mixed_upscale(config,run,draft,context,snapshot)
    v3=type(draft.get('schema_version')) is int and draft['schema_version']==3
    v2=type(draft.get('schema_version')) is int and draft['schema_version'] in (2,3)
    keys(draft,DRAFT_FIELDS+(' execution_policy' if v2 else '')+(' import_identity reused_units' if v3 else ''),'upscale draft')
    if type(draft['schema_version']) is not int or draft['schema_version'] not in (1,2,3) or draft['run_id']!=run.name or draft['status']!='review_required' or draft['passed'] is not False:raise ValueError('upscale draft schema/state differs')
    _timestamp(draft['created_at'])
    if not same(draft['validation'],validation(False)) or not same(draft['effective_media'],context['source']['effective_media']) or not same(draft['source_validation'],context['source']['validation']) or draft['source_review_method']!=context['source_review_method']:raise ValueError('source validation/review/media preservation differs')
    identities={}
    if v3:
        from ._upscale_resume import check_config_policy
        check_config_policy(draft['execution_policy'],config)
        if _reused_frames is None and (draft['import_identity'] is not None or draft['reused_units']!={}):raise ValueError('imported upscale requires origin consumer')
    elif v2:
        from ._upscale_resume import replay
        identities.update(replay(config,run,draft,snapshot))
    def bind(name,record,path,local=False):
        identity=fresh(record,run=run if local else None,expected=path);identities[name]=identity;return identity
    for name in ('source_clips','source_review','model','workflow','mapping'):
        wanted=thaw(context['identities'][name]);record=draft[name+'_identity']
        if not identity_equal(record,wanted):raise ValueError('draft input identity differs from fresh context')
        if name=='source_review':
            from .pipeline_import import fresh_origin_review
            identities[name]=fresh_origin_review(run,context['source'],record)
        else:bind(name,record,Path(wanted['path']),name=='source_clips')
    keys(draft['provenance'],' '.join(context['provenance']),'upscale provenance')
    for name,wanted in context['provenance'].items():
        if not identity_equal(draft['provenance'][name],wanted):raise ValueError('upscale provenance differs')
        bind(name,draft['provenance'][name],Path(wanted['path']),Path(wanted['path']).is_relative_to(run))
    records=draft['request_evidence']
    if not isinstance(records,dict) or not records and not _reused_clips:raise ValueError('complete upscale evidence map required')
    aliases=set()
    for name,record in records.items():
        if type(name) is not str or '\\' in name or Path(name).is_absolute() or Path(name).drive or Path(name).root or Path(name).as_posix()!=name or any(p in ('.','..') for p in name.split('/')) or name.casefold() in aliases:raise ValueError('upscale evidence alias/collision')
        aliases.add(name.casefold());bind('evidence/'+name,record,_local(run,run/name),True)
    clips=draft['clips'];plans=context['plans'];units=set();uuids=set();prompts=set();mappings=[]
    wanted_shots=[p.shot_id for p in plans]
    if not isinstance(clips,list) or [c.get('shot_id') for c in clips]!=(wanted_shots[:len(clips)] if _partial else wanted_shots):raise ValueError('upscale shot order/coverage differs')
    for clip,plan,source,mapped in zip(clips,plans,context['source']['clips'],context['source']['frame_mappings']):
        keys(clip,CLIP_FIELDS+receipt_fields(clip),'upscale clip');uid=plan.shot_id
        if _reused_clips is not None and uid in _reused_clips:
            if not same(clip,_reused_clips[uid]):raise ValueError('reused complete clip serializer differs')
            bind('video/'+uid,clip['upscaled_identity'],run/'shots'/uid/'upscaled.mp4',True)
            for frame in clip['frames']:
                unit_id=f"{uid}:frame_{frame['frame_index']:06d}";units.add(unit_id)
                unit=snapshot['units']['frame'].get(unit_id)
                if unit is None or unit['status']!='completed' or unit['submission'] is not None:raise ValueError('reused clip frame must not have child submission')
                bind('copied_frame/'+unit_id,frame['upscaled_frame_identity'],run/'shots'/uid/'upscaled-frames'/f"frame_{frame['frame_index']:06d}.png",True)
            mappings.append(upscale_frame_mapping(mapped,upscaled_identity=clip['upscaled_identity']))
            continue
        if clip['primary_unit_id']!=plan.primary_unit_id or not same(clip['budget'],plan.budget) or not (identity_equal(clip['source_identity'],thaw(plan.source_identity)) if v2 or _partial else same(clip['source_identity'],plan.source_identity)) or not same(clip['parameters'],plan.parameters):raise ValueError('upscale primary/source/budget/parameters differ')
        for key,value in [('width',1920),('height',1080),('native_fps',16),('source_frames',plan.source_frames),('upscaled_frames',plan.source_frames)]:
            if type(clip[key]) is not int or clip[key]!=value:raise ValueError('upscale integer dimensions/count/rate differ')
        incomplete=_partial and clip['upscaled_identity'] is None
        if not incomplete:bind('video/'+uid,clip['upscaled_identity'],run/'shots'/uid/'upscaled.mp4',True)
        covered=names(clip['evidence_identities'],records);frames=clip['frames']
        if not isinstance(frames,list) or (len(frames)>plan.source_frames if incomplete else len(frames)!=plan.source_frames):raise ValueError('complete independent frame checkpoints required')
        extraction_names=[n for n in covered if n.startswith('logs/upscale/extract-') and n.endswith('.json')]
        if len(extraction_names)!=1:raise ValueError('one independent clip extraction required')
        clip_started=read_json(run/extraction_names[0])['command']['started_at'];_timestamp(clip_started)
        clip_start=datetime.fromisoformat(clip_started).timestamp()
        clip_end=None if v2 or unlimited_receipt(clip) else clip_start+clip_deadline_seconds(frame_count=plan.source_frames,base_seconds=config.timeouts['upscale_clip'])
        for index,frame in enumerate(frames,1):
            keys(frame,FRAME_FIELDS+' checkpoint_identity'+receipt_fields(frame),'upscale frame');unit_id=f'{uid}:frame_{index:06d}';units.add(unit_id)
            if _reused_frames is not None and unit_id in _reused_frames:
                if not same(frame,_reused_frames[unit_id]):raise ValueError('reused upscale frame serializer mismatch')
                continue
            if type(frame['schema_version']) is not int or frame['schema_version']!=1 or frame['run_id']!=run.name or frame['shot_id']!=uid or type(frame['frame_index']) is not int or frame['frame_index']!=index or type(frame['source_frame_index']) is not int or frame['source_frame_index']!=index-1:raise ValueError('upscale frame numeric order/schema differs')
            if not same(frame['parameters'],clip['parameters']) or not (identity_equal(frame['source_identity'],clip['source_identity']) if v2 or _partial else same(frame['source_identity'],clip['source_identity'])) or any(not (identity_equal(frame[k],draft[k]) if v2 or _partial else same(frame[k],draft[k])) for k in ('model_identity','workflow_identity','mapping_identity')):raise ValueError('frame frozen inputs differ')
            paths=dict(input_identity=run/'shots'/uid/'frames'/f'frame_{index:06d}.png',input_copy_identity=run/'comfy/input'/run.name/'upscale'/uid/f'frame_{index:06d}.png',upscaled_frame_identity=run/'shots'/uid/'upscaled-frames'/f'frame_{index:06d}.png',checkpoint_identity=run/'logs/upscale'/f'frame-{uid}-{index:06d}.json')
            frame_names=names(frame['evidence_identities'],records)
            if not frame_names<=covered:raise ValueError('clip omits frame evidence')
            for key,path in paths.items():
                bind(key+'/'+unit_id,frame[key],path,True)
                if path.relative_to(run).as_posix() not in (covered if key=='checkpoint_identity' else frame_names):raise ValueError('frame file absent from indexed evidence')
            for a,b in [('input_identity','input_copy_identity'),('output_identity','upscaled_frame_identity')]:
                if frame[a]['bytes']!=frame[b]['bytes'] or frame[a]['sha256']!=frame[b]['sha256'] or frame[a]['path']==frame[b]['path']:raise ValueError('independent copied frame bytes differ')
            checkpoint=read_json(paths['checkpoint_identity'])
            if not same(checkpoint,{k:v for k,v in frame.items() if k!='checkpoint_identity'}):raise ValueError('frame differs from durable checkpoint')
            unit=snapshot['units']['frame'].get(unit_id)
            if unit is None or unit['status']!='completed' or unit['submission'] is None or unit['submission']['state']!='completed':raise ValueError('frame terminal submission unit differs')
            saved=unit['submission'];sub=frame['submission'];keys(sub,'attempt_id prompt_id intent_identity','frame submission')
            origin=frame_origin(frame,snapshot,v2)
            frame_end=None if unlimited_receipt(frame) else origin+config.timeouts['upscale_frame']
            if clip_end is not None:frame_end=clip_end if frame_end is None else min(frame_end,clip_end)
            if frame_end is not None and (datetime.fromisoformat(unit['finished_at']).timestamp()>frame_end or frame['checkpoint_identity']['mtime_ns']/1e9>frame_end):
                raise ValueError('durable frame/checkpoint exceeds absolute frame/clip deadline')
            durable_end=min(frame['checkpoint_identity']['mtime_ns']/1e9,datetime.fromisoformat(unit['finished_at']).timestamp())
            for key,seen in [('attempt_id',uuids),('prompt_id',prompts)]:
                if type(sub[key]) is not str or str(UUID(sub[key]))!=sub[key] or sub[key] in seen or sub[key]!=saved[key]:raise ValueError('unique actual frame UUID identity required')
                seen.add(sub[key])
            intent=bind('intent/'+unit_id,sub['intent_identity'],Path(saved['request_path']),True)
            registered=snapshot['workflows'].get(sub['attempt_id'])
            if registered is None:raise ValueError('frame graph receipt missing')
            bind('registered/'+unit_id,registered,Path(intent.path),True)
            wanted=graph(context['template'],run,plan,index)
            if not same(read_json(Path(intent.path)),wanted):raise ValueError('actual full frame graph differs')
            output=bind('output/'+unit_id,frame['output_identity'],Path(frame['output_identity']['path']),True);path=Path(output.path)
            if path.parent!=run/'comfy/output'/run.name/'upscale'/uid or not path.name.startswith(f'frame_{index:06d}_') or path.suffix.lower()!='.png' or output.mtime_ns<int(datetime.fromisoformat(saved['submitted_at']).timestamp()*1e9) or path.relative_to(run).as_posix() not in frame_names:raise ValueError('frame output prefix/mtime/coverage differs')
            if v2 and (output.mtime_ns/1e9<origin or output.mtime_ns/1e9>durable_end):raise ValueError('schema2 output exceeds actual durable frame window')
            wanted_artifacts=[paths['checkpoint_identity'],paths['input_identity'],paths['upscaled_frame_identity']]
            if [Path(a['path']) for a in unit['artifacts']]!=wanted_artifacts:raise ValueError('frame completed artifacts differ')
            for artifact in unit['artifacts']:identities['artifact/'+artifact['path']]=artifact_fresh(artifact,run=run)
            http(config,run,frame,saved,context['template'],wanted,records,clip_end,frame_start=origin,durable_end=durable_end if v2 else None)
        for directory in ('frames','upscaled-frames'):
            path=_local(run,run/'shots'/uid/directory)
            count=len(frames) if incomplete and directory=='upscaled-frames' else plan.source_frames
            if {p.name for p in path.iterdir()}!={f'frame_{i:06d}.png' for i in range(1,count+1)}:raise ValueError('numeric PNG sequence missing/extra files')
        checkpoint=run/'logs/upscale'/f'clip-{uid}.json'
        if not incomplete and (checkpoint.relative_to(run).as_posix() not in records or not same(read_json(checkpoint),clip)):raise ValueError('clip checkpoint is not fresh covered exact content')
        media(config,run,clip,source,records,snapshot,clip_start=clip_start,clip_end=clip_end,partial=incomplete,v2=v2,reused_frames=_reused_frames or ())
        if not incomplete:mappings.append(upscale_frame_mapping(mapped,upscaled_identity=clip['upscaled_identity']))
    expected_units={uid for uid,u in snapshot['units']['frame'].items() if u['status']=='completed'} if _partial else set(snapshot['units']['frame'])
    if expected_units!=units:raise ValueError('unexpected/missing frame units')
    if not _partial and (not same(draft['frame_mappings'],mappings) or not same(draft['requirement_clips'],requirements(context['source'],clips))):raise ValueError('reconstructed full frame mapping/requirement associations differ')
    _again(identities);return identities
