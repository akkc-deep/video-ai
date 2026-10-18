"""Cross-validate decoded media, raw HTTP and immutable attempt receipts."""
from datetime import datetime
import math
from pathlib import Path

from ..config import read_json
from ..media.video import validate_video_probe
from ..planning.start_images import keys
from ..planning.source_clips import frame_mapping,requirement_clips,supplement_frames
from .manifest import hash_file,thaw,_timestamp
from .timeline_checks import _local,_again
from .component_checks import output_path
from ._source_clip_inputs import fresh,same,graph,MODEL_NAMES

DRAFT_FIELDS='schema_version run_id created_at status passed images_identity storyboard_identity timeline_identity effective_media clips requirement_clips frame_mappings model_identities workflow_identity mapping_identity provenance validation request_evidence'
CLIP_FIELDS='shot_id primary_unit_id budget start_image_identity input_copy_identity selected_attempt_id attempts generated_identity source_identity width height native_fps generated_frames source_frames parameters evidence_identities'
ATTEMPT_FIELDS='attempt_id ordinal unit_id requested_frames status submission output_identity actual_frames evidence_identities'


def validation(ready, *, review_method=None):
    observed=ready and review_method!='user_acceptance'
    return dict(structure_passed=True,media_passed=True,video_text_semantics_passed=observed,
        motion_semantics_passed=observed,ready_for_upscale=ready,final_video_sync='unverified',full_film_acceptance='unverified')


def names(value,records):
    if not isinstance(value,list) or not value or any(type(n) is not str or n not in records for n in value) or len(set(value))!=len(value):
        raise ValueError('nonempty unique covered source evidence list required')
    return set(value)


def command(record,args,run,covered):
    keys(record,'args cwd returncode timed_out stdout_path stderr_path started_at finished_at','source media command')
    if type(record['returncode']) is not int or record['returncode']!=0 or record['timed_out'] is not False or record['cwd']!=str(run) or not same(record['args'],[str(a) for a in args]):
        raise ValueError('source media command arguments/result/cwd differ')
    _timestamp(record['started_at']);_timestamp(record['finished_at'])
    if datetime.fromisoformat(record['finished_at'])<datetime.fromisoformat(record['started_at']):raise ValueError('media command time reversed')
    for k in ('stdout_path','stderr_path'):
        path=_local(run,Path(record[k]))
        if path.relative_to(run).as_posix() not in covered:raise ValueError('raw media command stdout/stderr missing')
    return Path(record['stdout_path'])


def media(config,run,clip,records):
    covered=names(clip['evidence_identities'],records);uid=clip['shot_id'];width=clip['width'];height=clip['height']
    expected={Path(a['output_identity']['path']):a['actual_frames'] for a in clip['attempts']}
    generated=Path(clip['generated_identity']['path']);source=Path(clip['source_identity']['path'])
    expected.update({generated:clip['generated_frames'],source:clip['source_frames']})
    inspected={};trims=[]
    for name in sorted(covered):
        path=run/name
        if path.parent!=run/'logs/source-clips' or path.suffix!='.json':continue
        if path.name.startswith('video-'):
            if not path.name.startswith('video-'+uid+'_attempt_'):raise ValueError('inspection evidence belongs to another shot')
            record=read_json(path);keys(record,'info probe frames commands','video inspection')
            info=record['info'];keys(info,'identity width height codec pixel_format fps frames duration','decoded video info')
            identity=fresh(info['identity'],run=run);target=Path(identity.path)
            if target not in expected or type(info['frames']) is not int or info['frames']!=expected[target]:raise ValueError('inspection identity/count differs')
            metadata=validate_video_probe(record['probe'],record['frames'],width=width,height=height)
            if not same({k:v for k,v in info.items() if k!='identity'},metadata):raise ValueError('media info differs from raw probe/PTS')
            commands=record['commands']
            if not isinstance(commands,list) or len(commands)!=3:raise ValueError('three complete native video commands required')
            args=[(config.tools['ffprobe'],'-v','error','-count_frames','-show_streams','-show_format','-of','json',target),
                  (config.tools['ffprobe'],'-v','error','-show_frames','-of','json',target),
                  (config.tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',target,'-f','null','-')]
            for index,(c,a) in enumerate(zip(commands,args)):
                out=command(c,a,run,covered)
                if index<2 and not same(read_json(out),record['probe' if index==0 else 'frames']):raise ValueError('raw probe/PTS stdout differs from inspection')
                if index==2 and (out.read_bytes() or Path(c['stderr_path']).read_bytes()):raise ValueError('decode error output contradicts successful full decode')
            if target==source and info['pixel_format']!='yuv420p':raise ValueError('source must be yuv420p')
            inspected[target]=info
        elif path.name.startswith('trim-'):
            if not path.name.startswith('trim-'+uid+'_attempt_'):raise ValueError('trim belongs to another shot')
            record=read_json(path);keys(record,'source target frames filter command','trim evidence');trims.append(record)
    if set(inspected)!=set(expected) or len(trims)!=1:raise ValueError('all attempt/generated/source inspections and one trim required')
    trim=trims[0];required=clip['source_frames'];filter_value=f'trim=start_frame=0:end_frame={required},setpts=N/(16*TB)'
    if type(trim['frames']) is not int or trim['frames']!=required or trim['filter']!=filter_value:
        raise ValueError('retained frame trim differs')
    if not same(trim['source'],inspected[generated]) or not same(trim['target'],inspected[source]):raise ValueError('trim observations differ from inspected generated/source')
    command(trim['command'],(config.tools['ffmpeg'],'-nostdin','-n','-v','error','-xerror','-i',generated,'-vf',filter_value,
        '-an','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough',source),run,covered)
    for attempt in clip['attempts']:
        attempt_names=names(attempt['evidence_identities'],records)
        path=Path(attempt['output_identity']['path'])
        matching=[n for n in attempt_names if n.startswith('logs/source-clips/video-'+attempt['unit_id'].replace(':','_')+'-')]
        if len(matching)!=1:raise ValueError('attempt must bind its independent output inspection')
        observation=read_json(run/matching[0])
        if not same(observation['info']['identity'],attempt['output_identity']):raise ValueError('attempt output identity/inspection mismatch')
        for c in observation['commands']:
            for k in ('stdout_path','stderr_path'):
                if Path(c[k]).relative_to(run).as_posix() not in attempt_names:raise ValueError('attempt raw media commands missing')


def http(config,run,attempt,saved,t,expected_graph,records):
    covered=names(attempt['evidence_identities'],records);post=0;remote=False;tracking=False
    intent=Path(saved['request_path']);history=Path(saved['response_path'])
    if not {intent.relative_to(run).as_posix(),history.relative_to(run).as_posix()}<=covered:raise ValueError('attempt intent/history absent from evidence')
    history_data=read_json(history);prompt=attempt['submission']['prompt_id']
    entry=history_data.get(prompt,{})
    if entry.get('status',{}).get('completed') is not True or entry.get('status',{}).get('status_str')!='success':raise ValueError('attempt history not completed success')
    outputs=entry.get('outputs',{}).get(t.mapping['output']['node_id'],{}).get(t.mapping['output']['collection'])
    if not isinstance(outputs,list) or len(outputs)!=1 or output_path(run,outputs[0])!=Path(attempt['output_identity']['path']):raise ValueError('attempt output differs from mapped successful history')
    for name in covered:
        if not name.startswith('logs/http/') or not name.endswith('.request.json'):continue
        stem=name[:-len('.request.json')];required={name,stem+'.response.json',stem+'.body'}
        if not required<=covered:raise ValueError('raw HTTP request/response/body missing')
        request=read_json(run/name);response=read_json(run/(stem+'.response.json'));body_path=run/(stem+'.body')
        keys(request,'method url headers json_body timeout stage unit_id started_at','HTTP request')
        keys(response,'method url stage unit_id status headers bytes truncated finished_at error','HTTP response')
        _timestamp(request['started_at']);_timestamp(response['finished_at'])
        if datetime.fromisoformat(response['finished_at'])<datetime.fromisoformat(request['started_at']):raise ValueError('HTTP evidence time reversed')
        if type(request['timeout']) not in (int,float) or not math.isfinite(request['timeout']) or not 0<request['timeout']<=min(config.timeouts['comfy_request'],config.timeouts['wan']):raise ValueError('HTTP timeout exceeds attempt/request budget')
        if any(not same(request[k],response[k]) for k in ('method','url','stage','unit_id')) or type(response['bytes']) is not int or response['bytes']!=body_path.stat().st_size or type(response['truncated']) is not bool:
            raise ValueError('HTTP request/response/body association differs')
        good=type(response['status']) is int and response['status']==200 and response['truncated'] is False and response['error'] is None
        if request['url']==config.services['comfyui']+'/prompt' and request['method']=='POST':
            post+=1
            keys(request['json_body'],'prompt client_id','HTTP prompt body')
            if not good or request['stage']!='source_clips' or request['unit_id']!=attempt['unit_id'] or request['json_body']['client_id']!=saved['client_id'] or not same(request['json_body']['prompt'],expected_graph):raise ValueError('attempt actual HTTP submission differs')
            accepted=read_json(body_path);keys(accepted,'prompt_id number node_errors','HTTP prompt acceptance')
            if accepted['prompt_id']!=prompt or not same(accepted['number'],saved['number']) or not isinstance(accepted['node_errors'],dict):raise ValueError('HTTP prompt acceptance identity differs')
            if datetime.fromisoformat(request['started_at'])<datetime.fromisoformat(saved['submitted_at']):raise ValueError('POST predates saved submission intent')
        if good and request['url']==config.services['comfyui']+'/object_info' and request['method']=='GET':
            t.validate_remote(read_json(body_path));remote=True
        if good and request['url']==config.services['comfyui']+'/history/'+prompt and request['method']=='GET':
            if request['stage']!='source_clips' or request['unit_id']!=attempt['unit_id']:raise ValueError('HTTP tracking is not this attempt')
            if body_path==history and not same(read_json(body_path),history_data):raise ValueError('successful retrieval differs')
            if body_path==history:tracking=True
    if post!=1 or not remote or not tracking:raise ValueError('exactly one POST, remote validation and completed retrieval required')


def validate(config,run,draft,context,snapshot, *, _partial=False):
    if draft.get('schema_version')==2:
        from .pipeline_import import validate_mixed_source
        return validate_mixed_source(config,run,draft,context,snapshot)
    keys(draft,DRAFT_FIELDS,'source clips draft')
    if type(draft['schema_version']) is not int or draft['schema_version']!=1 or draft['run_id']!=run.name or draft['status']!='review_required' or draft['passed'] is not False:
        raise ValueError('source clip draft schema/state differs')
    _timestamp(draft['created_at'])
    if not same(draft['validation'],validation(False)) or not same(draft['effective_media'],context['board']['effective_media']):raise ValueError('source draft validation/media differs')
    identities={}
    def bind(name,record,path,local=False):
        identity=fresh(record,run=run if local else None,expected=path);identities[name]=identity;return identity
    for key in ('images','storyboard','timeline'):bind(key,draft[key+'_identity'],run/(key+'.json'),True)
    keys(draft['provenance'],' '.join(context['provenance']),'source provenance')
    for key,wanted in context['provenance'].items():
        record=draft['provenance'][key]
        if wanted is None:
            if record is not None:raise ValueError('optional provenance presence changed')
        else:bind(key,record,Path(wanted['path']),Path(wanted['path']).is_relative_to(run))
    keys(draft['model_identities'],' '.join(MODEL_NAMES),'Wan models')
    for name in MODEL_NAMES:bind('model/'+name,draft['model_identities'][name],config.models[name])
    bind('workflow',draft['workflow_identity'],config.workflows['wan']);bind('mapping',draft['mapping_identity'],config.workflows['wan_mapping'])
    records=draft['request_evidence']
    if not isinstance(records,dict) or not records:raise ValueError('source evidence map required')
    aliases=set()
    for name,record in records.items():
        if type(name) is not str or '\\' in name or Path(name).is_absolute() or Path(name).drive or Path(name).root or Path(name).as_posix()!=name or any(p in ('.','..') for p in name.split('/')) or name.casefold() in aliases:
            raise ValueError('source evidence key alias/collision')
        aliases.add(name.casefold());bind('evidence/'+name,record,_local(run,run/name),True)
    clips=draft['clips'];plans=context['plans']
    if _partial:plans=tuple(p for p in plans if p.shot_id in {c['shot_id'] for c in clips})
    if not isinstance(clips,list) or [c.get('shot_id') for c in clips]!=[p.shot_id for p in plans]:raise ValueError('source clip frozen order/coverage differs')
    mappings={};sources={};expected_attempt_units=set()
    for clip,plan in zip(clips,plans):
        keys(clip,CLIP_FIELDS,'source clip');uid=plan.shot_id
        if clip['primary_unit_id']!=plan.primary_unit_id or not same(clip['budget'],plan.budget) or not same(clip['start_image_identity'],plan.start_image_identity):raise ValueError('clip budget/start/primary association differs')
        bind('start/'+uid,clip['start_image_identity'],run/'shots'/uid/'start.png',True)
        copied=bind('input/'+uid,clip['input_copy_identity'],run/'comfy/input'/run.name/'source_clips'/uid/'start.png',True)
        if (copied.bytes,copied.sha256)!=(clip['start_image_identity']['bytes'],clip['start_image_identity']['sha256']):raise ValueError('copied start image differs')
        covered=names(clip['evidence_identities'],records)
        image_note=f'logs/source-clips/input-{uid}.json'
        needed={image_note,Path(clip['start_image_identity']['path']).relative_to(run).as_posix(),Path(copied.path).relative_to(run).as_posix()}
        if not needed<=covered or not same(read_json(run/image_note),dict(source=clip['start_image_identity'],target=clip['input_copy_identity'])):raise ValueError('original/copy image receipts missing or different')
        attempts=clip['attempts']
        if not isinstance(attempts,list) or not 1<=len(attempts)<=2:raise ValueError('one or two independent attempts required')
        requested=plan.parameters['length'];required=plan.budget['required_native_frames'];seen_uuids=set()
        for ordinal,attempt in enumerate(attempts,1):
            keys(attempt,ATTEMPT_FIELDS,'source attempt');local=f'attempt_{ordinal:04d}';unit_id=uid+':'+local
            if type(attempt['ordinal']) is not int or attempt['ordinal']!=ordinal or attempt['attempt_id']!=local or attempt['unit_id']!=unit_id or type(attempt['requested_frames']) is not int or attempt['requested_frames']!=requested or type(attempt['actual_frames']) is not int or attempt['actual_frames']<=0:
                raise ValueError('attempt identity/ordinal/frame request differs')
            expected_attempt_units.add(unit_id);last=ordinal==len(attempts);actual=attempt['actual_frames']
            if attempt['status']!=('selected' if last else 'short') or (actual!=requested if last else not actual<required):raise ValueError('only fully decoded short may precede selected exact sufficient attempt')
            if last and actual<required:raise ValueError('selected attempt short')
            unit=snapshot['units'].get('shot_attempt',{}).get(unit_id)
            if unit is None or unit['status']!=('completed' if last else 'failed'):raise ValueError('attempt terminal unit mismatch')
            sub=attempt['submission'];keys(sub,'attempt_id prompt_id intent_identity','attempt submission');saved=unit['submission']
            if saved is None or saved['state']!='completed' or saved['attempt_id']!=sub['attempt_id'] or saved['prompt_id']!=sub['prompt_id'] or sub['attempt_id'] in seen_uuids:raise ValueError('attempt successful submission identity differs')
            seen_uuids.add(sub['attempt_id'])
            intent=bind('intent/'+unit_id,sub['intent_identity'],Path(saved['request_path']),True)
            registered=snapshot['workflows'].get(sub['attempt_id'])
            if registered is None:raise ValueError('actual workflow absent from manifest')
            bind('registered/'+unit_id,registered,Path(intent.path),True)
            actual_graph=graph(context['template'],run,plan,requested,local)
            if not same(read_json(Path(intent.path)),actual_graph):raise ValueError('whole actual workflow differs from immutable parameters')
            out=bind('output/'+unit_id,attempt['output_identity'],_local(run,Path(attempt['output_identity']['path'])),True);path=Path(out.path)
            if path.parent!=run/'comfy/output'/run.name/'source_clips'/uid or not path.name.startswith(local+'_') or path.suffix.lower()!='.mp4' or out.mtime_ns<int(datetime.fromisoformat(saved['submitted_at']).timestamp()*1_000_000_000):raise ValueError('output path/prefix/submission mtime differs')
            attempt_names=names(attempt['evidence_identities'],records)
            if not attempt_names<=covered:raise ValueError('clip omits independent attempt evidence')
            http(config,run,attempt,saved,context['template'],actual_graph,records)
            if not last:requested=supplement_frames(requested_frames=requested,required_native_frames=required,actual_frames=actual)
        selected=attempts[-1]
        if clip['selected_attempt_id']!=selected['attempt_id']:raise ValueError('selected local attempt differs')
        params=thaw(plan.parameters);params['length']=selected['requested_frames']
        if not same(clip['parameters'],params) or not same([clip[k] for k in ('width','height','native_fps','generated_frames','source_frames')],[params['width'],params['height'],16,selected['actual_frames'],required]):raise ValueError('clip parameters/metadata differ')
        generated=bind('generated/'+uid,clip['generated_identity'],run/'shots'/uid/'generated.mp4',True)
        bind('source/'+uid,clip['source_identity'],run/'shots'/uid/'source.mp4',True)
        if (generated.bytes,generated.sha256)!=(selected['output_identity']['bytes'],selected['output_identity']['sha256']):raise ValueError('generated copy differs from selected independent output')
        media(config,run,clip,records)
        checkpoint=run/'logs/source-clips'/f'clip-{uid}.json'
        artifacts=snapshot['units']['shot_attempt'][selected['unit_id']]['artifacts']
        if [Path(a['path']) for a in artifacts]!=[checkpoint,Path(generated.path),Path(clip['source_identity']['path'])]:raise ValueError('selected checkpoint artifacts differ')
        from .timeline_checks import _fresh as afresh
        for a in artifacts:identities['artifact/'+a['path']]=afresh(a,run=run)
        if not same(read_json(checkpoint),clip):raise ValueError('clip differs from durable checkpoint')
        main=snapshot['units']['shot'].get(uid)
        if main is None or main['submission'] is not None or main['status'] not in (('running','completed','failed','interrupted','ambiguous') if _partial else ('running','completed')):raise ValueError('main shot must be prepared summary with no submission')
        mappings[uid]=frame_mapping(plan,generated_identity=clip['generated_identity'],source_identity=clip['source_identity'],generated_frames=clip['generated_frames'],output_fps=context['board']['effective_media']['fps'])
        sources[uid]=clip['source_identity']
    if not _partial and (set(snapshot['units'].get('shot_attempt',{}))!=expected_attempt_units or set(snapshot['units']['shot'])!=set(sources)):raise ValueError('unexpected stage main/attempt units')
    if not same(draft['frame_mappings'],list(mappings.values())):raise ValueError('frame mappings differ from fresh reconstructed budgets/identities')
    if not _partial:
        required_rows=requirement_clips(context['board'],source_identities=sources,frame_mappings=mappings,total_samples=context['timeline']['total_samples'])
        if not same(draft['requirement_clips'],required_rows):raise ValueError('continuous primary/edge requirement clips differ')
    _again(identities)
    return identities
