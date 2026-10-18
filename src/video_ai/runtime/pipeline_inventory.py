"""Build explicit semantic projections from freshly consumed stage receipts.

Original complete identities remain in unit signature_projection records for
the coordinator's freshness closure. Hashes normalize only file identity
metadata and declared Comfy input/output namespace fields.
"""
from collections.abc import Mapping
from pathlib import Path

from ..config import read_json
from ..planning.recovery import signature
from .manifest import STAGES, hash_file, thaw


def _tts_intent_evidence(snapshot, *, run_dir=None):
    """Freshly collect durable TTS sends lacking a committed unit response.

    TTS has no saved query key. Intent/event/actual POST evidence survives a
    lost first response even though the manifest has no Comfy submission.
    Completed units are admitted only by their separate speech consumer.
    """
    snapshot=thaw(snapshot);units=snapshot.get('units',{}).get('speech',{})
    if snapshot.get('stages',{}).get('speech',{}).get('status')=='completed':return {}
    if run_dir is None:
        root=snapshot.get('config_snapshot',{}).get('resolved',{}).get('project_root')
        run_dir=Path(root)/'runs'/snapshot['run_id'] if root and snapshot.get('run_id') else None
    run=Path(run_dir) if run_dir is not None else None
    unknown={}
    def mark(uid,path=None):
        from .manifest import validate_unit
        validate_unit('speech',uid)
        if units.get(uid,{}).get('status')=='completed':return
        row=unknown.setdefault(uid,dict(durable_tts_intent=True,evidence_identities={}))
        if path is not None:
            path=Path(path)
            if run is None or not path.resolve().is_relative_to(run/'logs'):
                raise ValueError('TTS intent evidence outside original run logs')
            if path.is_file():
                identity=hash_file(path);row['evidence_identities'][identity.path]=thaw(identity)
            else:row['missing_evidence']=True
    for event in snapshot.get('events',()):
        if event.get('stage')=='speech' and event.get('action')=='tts_intent':
            mark(event['unit_id'])
            for path in event.get('evidence_paths',()):mark(event['unit_id'],path)
    for uid,unit in units.items():
        if unit.get('status')=='ambiguous' and unit.get('submission') is None:mark(uid)
    if run is not None:
        for path in (run/'logs/tts').glob('*.intent.json'):
            data=read_json(path);uid=path.name[:-len('.intent.json')]
            mark(uid,path)
            if data.get('unit_id')!=uid:raise ValueError('TTS intent file/unit association differs')
        service=snapshot.get('config_snapshot',{}).get('resolved',{}).get('services',{}).get('tts')
        for path in (run/'logs/http').glob('*.request.json'):
            data=read_json(path)
            if data.get('method')=='POST' and (data.get('stage')=='speech' or service and data.get('url')==service+'/tts'):
                uid=data.get('unit_id');mark(uid,path)
                stem=path.name[:-len('.request.json')]
                for suffix in ('.response.json','.body'):
                    companion=path.parent/(stem+suffix)
                    if companion.exists():mark(uid,companion)
    if not unknown and snapshot.get('stages',{}).get('speech',{}).get('status')=='ambiguous':
        mark('reference_replay')
    return unknown


def classify_tts_intents(snapshot, *, run_dir=None):
    """Separate complete bound TTS failures from lost or ambiguous responses."""
    from ..adapters.common import positive_timeout
    from ..adapters.tts import TtsClient
    from ..config import load_config
    from .manifest import _timestamp
    from .timeline_checks import _again
    from datetime import datetime
    snapshot=thaw(snapshot);unknown=_tts_intent_evidence(snapshot,run_dir=run_dir);failed={}
    if not unknown:return unknown,failed
    if run_dir is None:
        root=snapshot.get('config_snapshot',{}).get('resolved',{}).get('project_root')
        run_dir=Path(root)/'runs'/snapshot['run_id'] if root and snapshot.get('run_id') else None
    if run_dir is None:return unknown,failed
    run=Path(run_dir)
    for uid,row in tuple(unknown.items()):
        unit=snapshot.get('units',{}).get('speech',{}).get(uid,{})
        if unit.get('status')!='failed' or unit.get('submission') is not None:continue
        try:
            config=load_config(Path(snapshot['config_snapshot']['path']))
            intent_path=run/'logs/tts'/f'{uid}.intent.json';intent=read_json(intent_path)
            if (intent.get('unit_id')!=uid or intent.get('automatic_retry') is not False
                    or intent.get('payload')!=TtsClient(None,config.voice).payload(intent.get('text'))
                    or intent.get('voice_sha256')!=hash_file(config.voice.config_file).sha256):
                raise ValueError('original TTS intent/payload/voice differs')
            _timestamp(intent['created_at'])
            requests=[]
            for path in (run/'logs/http').glob('*.request.json'):
                request=read_json(path)
                if request.get('stage')=='speech' and request.get('unit_id')==uid and request.get('method')=='POST':requests.append((path,request))
            if len(requests)!=1:raise ValueError('one original actual TTS POST required')
            request_path,request=requests[0];stem=request_path.name[:-len('.request.json')]
            body_path=request_path.parent/(stem+'.body');response_path=request_path.parent/(stem+'.response.json')
            response=read_json(response_path);body_identity=hash_file(body_path);body=body_path.read_bytes();budget=request['timeout']
            if (request.get('url')!=config.services['tts']+'/tts' or request.get('json_body')!=intent['payload']
                    or type(budget) not in (int,float) or positive_timeout(budget)>config.timeouts['tts_request']
                    or response.get('method')!='POST' or response.get('url')!=request['url']
                    or response.get('stage')!='speech' or response.get('unit_id')!=uid
                    or type(response.get('status')) is not int or response.get('error') is not None
                    or response.get('truncated') is not False or type(response.get('bytes')) is not int or response['bytes']!=len(body)):
                raise ValueError('TTS response is incomplete or not the exact original request')
            _timestamp(request['started_at'])
            if datetime.fromisoformat(request['started_at'])<datetime.fromisoformat(intent['created_at']):raise ValueError('TTS POST predates intent')
            invalid_wav=(len(body)<12 or body[:4]!=b'RIFF' or body[8:12]!=b'WAVE')
            if response['status']==200 and not invalid_wav:
                from ..media.audio import _wave_duration
                try:_wave_duration(body_path)
                except ValueError as exc:
                    if str(exc) not in ('empty/compressed WAV','truncated WAV frames'):raise
                    invalid_wav=True
            if not (400<=response['status']<500 or response['status']==200 and invalid_wav):
                raise ValueError('TTS response does not prove explicit rejection or invalid WAV media')
            error=unit.get('error')
            if not isinstance(error,Mapping):raise ValueError('TTS original local failure evidence missing')
            failure_paths=list(error.get('evidence_paths',()))
            if error.get('traceback_path'):failure_paths.append(error['traceback_path'])
            if not failure_paths:raise ValueError('TTS original local failure evidence missing')
            evidence=dict(row['evidence_identities']);evidence[body_identity.path]=thaw(body_identity)
            for path in (intent_path,request_path,body_path,response_path,config.config_file,config.voice.config_file,
                    *[Path(value) for value in failure_paths]):
                if path not in (config.config_file,config.voice.config_file) and not path.resolve().is_relative_to(run/'logs'):
                    raise ValueError('TTS failure evidence outside original logs')
                identity=body_identity if path==body_path else hash_file(path);evidence[identity.path]=thaw(identity)
            from .manifest import FileIdentity
            _again({path:FileIdentity(**value) for path,value in evidence.items()})
            failed[uid]=dict(reason='complete original HTTP rejection' if response['status']!=200 else 'complete original invalid WAV response',
                evidence_identities=evidence,intent_identity=thaw(hash_file(intent_path)),request_identity=thaw(hash_file(request_path)),
                response_identity=thaw(hash_file(response_path)),body_identity=thaw(body_identity))
            unknown.pop(uid)
        except (ValueError,KeyError,TypeError,OSError,EOFError):continue
    return unknown,failed


def unknown_tts_intents(snapshot, *, run_dir=None):
    return classify_tts_intents(snapshot,run_dir=run_dir)[0]


def derived_workflow_files(config):
    workflows=config.workflows if hasattr(config,'workflows') else config.get('workflows',{})
    upscale=workflows.get('upscale')
    return {'upscale_mapping':Path(upscale).with_suffix('.mapping.json')} if upscale is not None else {}


def config_projection(config, identities):
    """Retain every config leaf while canonicalizing declared content paths.

    identities is the collector's mutable freshness index: each newly captured
    file leaf is added to it. Directories use already consumed relative leaves;
    unused execution roots remain lexical conservative dependencies. Arbitrary
    text fields, including prompts/reference text, are never interpreted paths.
    """
    value=thaw(config);value.pop('raw',None);value.get('voice',{}).pop('raw',None)
    known={record.path:record for record in identities.values() if hasattr(record,'path')}
    for record in identities.values():
        if isinstance(record,Mapping) and {'path','bytes','sha256'}<=set(record):
            known[record['path']]=record

    def file_content(path):
        path=Path(path);record=known.get(str(path))
        if record is None:
            record=hash_file(path);identities[record.path]=record;known[record.path]=record
        else:
            from .pipeline_import import fresh
            fresh(record)
        return record

    for group,names in (('models',tuple(value.get('models',{}))),
                        ('workflows',tuple(value.get('workflows',{}))),
                        ('tools',tuple(n for n in value.get('tools',{}) if not n.endswith('_root')))):
        for name in names:value[group][name]=thaw(file_content(value[group][name]))
    derived=derived_workflow_files(config)
    if derived:
        value['derived_workflows']={name:thaw(file_content(path)) for name,path in derived.items()}
    for name in ('font_file','music'):
        if value.get('media',{}).get(name) is not None:
            value['media'][name]=thaw(file_content(value['media'][name]))
    for name in ('gpt_weights','sovits_weights','reference_audio'):
        if name in value.get('voice',{}):value['voice'][name]=thaw(file_content(value['voice'][name]))
    directory_fields=[('voice',name) for name in ('bert_root','hubert_root') if name in value.get('voice',{})]
    directory_fields += [('tools',name) for name in value.get('tools',{}) if name.endswith('_root')]
    for group,name in directory_fields:
        root=Path(value[group][name]);leaves={}
        for path,record in known.items():
            path=Path(path)
            if path.is_relative_to(root):leaves[path.relative_to(root).as_posix()]=thaw(record)
        if group=='voice':
            if not root.is_dir() or root.resolve()!=root:raise ValueError('voice model content directory missing or redirected')
            actual=tuple(path for path in sorted(root.rglob('*')) if path.is_file())
            actual_names={path.relative_to(root).as_posix() for path in actual}
            if leaves and set(leaves)!=actual_names:raise ValueError('voice model directory file set changed')
            leaves={path.relative_to(root).as_posix():thaw(file_content(path)) for path in actual}
            if not leaves:raise ValueError('voice model content directory empty')
            value[group][name]={'relative_content':leaves}
        elif leaves:
            value[group][name]={'relative_content':{key:leaves[key] for key in sorted(leaves)}}
        else:
            value[group][name]={'unconsumed_directory_path':str(root)}
    return value


def _bound_json(record):
    if record is None:
        return None
    record = thaw(record)
    path = Path(record['path'])
    before = hash_file(path)
    keys = ('path', 'bytes', 'sha256', 'mtime_ns') if 'mtime_ns' in record else ('path', 'bytes', 'sha256')
    if any(thaw(before)[key] != record[key] for key in keys):
        raise ValueError('semantic projection source identity drift: '+str(path))
    result = read_json(path)
    after = hash_file(path)
    if any(thaw(before)[key] != thaw(after)[key] for key in keys):
        raise ValueError('semantic projection source changed while reading')
    return result


def _semantic(value):
    value = thaw(value)
    if isinstance(value, Mapping):
        # FileIdentity and registered media ArtifactIdentity are the only
        # content-path normalizations. Unrelated path/prompt strings survive.
        if set(value) in ({'path','bytes','sha256','mtime_ns','verified_at'},
                          {'path','bytes','sha256','category','verified_at'}):
            if type(value['bytes']) is not int or not isinstance(value['sha256'], str):
                raise ValueError('semantic projection requires verified file content')
            return {'bytes':value['bytes'], 'sha256':value['sha256']}
        return {k:_semantic(v) for k,v in value.items()}
    if isinstance(value, list):
        return [_semantic(v) for v in value]
    return value


def _content_signature(projection, roles=None):
    return signature(_semantic(projection), graph_roles=roles)


def _report(value):
    value = thaw(value)
    return value.get('report', value) if isinstance(value, Mapping) else {}


def _tool_identities(snapshot, names):
    tools = snapshot.get('config_snapshot', {}).get('resolved', {}).get('tools', {})
    result = {}
    for name in names:
        path = tools.get(name)
        if path is not None:
            result[name] = thaw(hash_file(Path(path)))
    return result


def _voice(snapshot, report):
    value = dict(report.get('voice_snapshot', snapshot.get('voice_snapshot', {}).get('resolved', {})))
    # The exact referenced content is carried by reference/models identities,
    # not absolute directory/file placement or serialization of raw config.
    for key in ('config_file','raw','gpt_weights','sovits_weights','bert_root','hubert_root','reference_audio'):
        value.pop(key, None)
    return value


def _graph(row, snapshot):
    if 'actual_graph' in row:
        return row['actual_graph']
    submission = row.get('submission')
    if submission:
        identity = submission.get('intent_identity')
        if identity is None:
            identity = snapshot.get('workflows', {}).get(submission.get('attempt_id'))
        if identity:
            return _bound_json(identity)
        raise ValueError('saved submitted unit has no validated actual graph identity')
    return None


def _roles(graph, prefix):
    result = {}
    for node, record in (graph or {}).items():
        kind = record.get('class_type')
        inputs = record.get('inputs', {})
        if kind in ('LoadImage', 'LoadImageMask') and 'image' in inputs:
            result[prefix+(node,'inputs','image')] = 'model_input_image'
        if kind in ('SaveImage', 'VHS_VideoCombine', 'SaveVideo'):
            for field in ('filename_prefix', 'output_prefix'):
                if field in inputs:
                    result[prefix+(node,'inputs',field)] = 'model_output'
    return result


def _audio_info(value):
    value = thaw(value)
    if isinstance(value, Mapping) and 'path' in value and 'samples' in value:
        return {k:v for k,v in value.items() if k != 'path'}
    return value


def _spans(report):
    # Preserve exact ordered TextSpan values while excluding runtime status and
    # waveform receipt fields. PCM content belongs to the timeline projection.
    names = ('kind','unit_id','start','end','text_start','text_end','text','boundary')
    return [{key:row[key] for key in names if key in row} for row in report.get('spans', ())]


def enrich_inventory(snapshot, consumed, checkpoints):
    """Return (stage->stable unit rows, stage->{__stage__, unit: signature}).

    All consumed receipts/checkpoint reports must already have passed their
    stage owner. Bound actual graph/plan JSON and execution tool identities are
    read afresh here; callers must add _identity_index(unit_records, identities)
    to protect every additional leaf before and after each planned operation.
    """
    snapshot = thaw(snapshot)
    receipts = {stage:_report(value) for stage,value in consumed.items()}
    for stage, checkpoint in checkpoints.items():
        if checkpoint.get('draft_complete') is True and checkpoint.get('report') is not None:
            receipts.setdefault(stage, _report(checkpoint['report']))
    units = {s:{} for s in STAGES}
    signatures = {s:{} for s in STAGES}
    kinds = {'speech':'speech','image':'start_images','shot':'source_clips',
             'shot_attempt':'source_clips','frame':'upscale'}
    for kind, rows in snapshot.get('units', {}).items():
        if kind not in kinds:
            raise ValueError('unknown manifest unit kind')
        units[kinds[kind]].update(thaw(rows))
    tts_unknown,tts_failed=classify_tts_intents(snapshot)
    for uid,proof in tts_unknown.items():
        units['speech'][uid]=dict(units['speech'].get(uid,{}),**proof)
        units['speech'][uid].setdefault('status','ambiguous')
    for uid,proof in tts_failed.items():
        units['speech'][uid]=dict(units['speech'].get(uid,{}),proven_tts_failure=True,failure_proof=proof)

    speech = receipts.get('speech', {})
    board = receipts.get('storyboard', {})
    board_rows = {row['shot_id']:row for row in board.get('shots', ())}
    timeline = receipts.get('timeline', {})
    images = receipts.get('start_images', {})
    source = receipts.get('source_clips', {})
    upscaled = receipts.get('upscale', {})
    source_rows = {row['shot_id']:row for row in source.get('clips', ())}
    config = snapshot.get('config_snapshot', {}).get('resolved', {})
    tools = {}
    timeline_projection = {}

    def stage_tools(stage, names):
        if stage not in tools:
            tools[stage] = _tool_identities(snapshot, names)
        return tools[stage]

    def put(stage, uid, row, projection, roles=None):
        status = units[stage].get(uid, {}).get('status', snapshot.get('stages', {}).get(stage, {}).get('status', 'pending'))
        units[stage][uid] = dict(units[stage].get(uid, {}))
        units[stage][uid].update(thaw(row))
        units[stage][uid].update(status=status, signature_projection=projection)
        signatures[stage][uid] = _content_signature(projection, roles)

    if 'speech' in receipts:
        frozen_inputs = speech.get('inputs', snapshot.get('inputs', {}))
        projection = dict(source=speech.get('source', frozen_inputs.get('script')),
            spans=_spans(speech), voice=_voice(snapshot,speech),
            reference=frozen_inputs.get('reference'),
            weights=speech.get('models', snapshot.get('models', {})),
            tools=stage_tools('speech',('ffmpeg','ffprobe','tts_python')))
        signatures['speech']['__stage__'] = _content_signature(projection)
        for row in speech.get('spans', ()):
            if row.get('kind') == 'speech':
                span = {key:row[key] for key in ('kind','unit_id','start','end','text_start','text_end','text','boundary') if key in row}
                put('speech',row['unit_id'],row,dict(projection,spans=[span]))

    if 'timeline' in receipts:
        clips = []
        for row in timeline.get('clips', ()):
            clip = dict(row)
            if 'pcm' in clip:
                clip['pcm'] = _audio_info(clip['pcm'])
            clips.append(clip)
        projection = dict(original_text=timeline.get('original_text'), source_spans=timeline.get('source_spans',_spans(speech)),
            clips=clips, settings=timeline.get('effective_settings',config.get('media',{}).get('timeline')),
            fps=timeline.get('output_fps',config.get('media',{}).get('fps')),
            cues=board.get('cues',()), timing_basis=board.get('timing_basis'),
            sample_plan={key:value for key,value in timeline.items() if key not in ('clips','source_spans','provenance','run_id','status','passed','created_at','validation')})
        signatures['timeline']['__stage__'] = _content_signature(projection)
        timeline_projection = projection

    if 'storyboard' in receipts:
        projected = []
        for uid,row in board_rows.items():
            projection = dict(shot=row,global_visual=board.get('global_visual'),
                timing=dict(cues=board.get('cues'),basis=board.get('timing_basis')),
                effective_media=board.get('effective_media'),transitions=board.get('transitions'),
                model_planning=board.get('model_result',board.get('planning_result')),
                models=board.get('provenance',{}).get('models'))
            put('storyboard',uid,row,projection);projected.append(projection)
        signatures['storyboard']['__stage__'] = _content_signature(projected)

    if 'start_images' in receipts:
        projected, stage_roles = [], {}
        for row in images.get('images', ()):
            uid=row['shot_id'];actual=_graph(row,snapshot)
            projection=dict(original_meaning=board_rows.get(uid),global_visual=images.get('global_visual',board.get('global_visual')),
                references=images.get('references',()),parameters=row.get('parameters'),
                settings=images.get('effective_image_settings'),graph=actual,
                model=row.get('model_identity'),workflow=row.get('workflow_identity'),mapping=row.get('mapping_identity'),
                input_image=row.get('source_identity'),image=row.get('image_identity'),
                tools=stage_tools('start_images',('ffmpeg','ffprobe','comfy_python')))
            enriched=dict(row,reference_index=images.get('references',()))
            put('start_images',uid,enriched,projection,_roles(actual,('graph',)))
            stage_roles.update(_roles(actual,(len(projected),'graph')));projected.append(projection)
        signatures['start_images']['__stage__']=_content_signature(projected,stage_roles)

    if 'source_clips' in receipts:
        projected,stage_roles=[],{}
        for clip in source.get('clips', ()):
            uid=clip['shot_id'];attempts=[];roles={}
            for attempt in clip.get('attempts', ()):
                actual=_graph(attempt,snapshot)
                row=dict(requested_frames=attempt.get('requested_frames'),actual_frames=attempt.get('actual_frames'),
                         graph=actual,output=attempt.get('output_identity'))
                roles.update(_roles(actual,('attempts',len(attempts),'graph')));attempts.append(row)
            projection=dict(budget=clip.get('budget'),parameters=clip.get('parameters'),
                original_meaning=board_rows.get(uid),start_image=clip.get('start_image_identity'),
                attempts=attempts,source=clip.get('source_identity'),
                mapping=[m for m in source.get('frame_mappings',()) if m.get('shot_id')==uid],
                models=source.get('model_identities'),workflow=source.get('workflow_identity'),mapping_template=source.get('mapping_identity'),
                tools=stage_tools('source_clips',('ffmpeg','ffprobe','comfy_python')))
            put('source_clips',uid,clip,projection,roles)
            for attempt in clip.get('attempts', ()):
                if attempt.get('unit_id') in units['source_clips']:
                    put('source_clips',attempt['unit_id'],attempt,projection,roles)
            stage_roles.update({(len(projected),)+key:value for key,value in roles.items()});projected.append(projection)
        signatures['source_clips']['__stage__']=_content_signature(projected,stage_roles)

    if 'upscale' in receipts:
        projected,stage_roles=[],{}
        for clip in upscaled.get('clips', ()):
            uid=clip['shot_id'];frames=[];roles={}
            for row in clip.get('frames', ()):
                frame_id=f"{uid}:frame_{row['frame_index']:06d}";actual=_graph(row,snapshot)
                projection=dict(budget=clip.get('budget'),parameters=row.get('parameters',clip.get('parameters')),
                    source=clip.get('source_identity'),input=row.get('input_identity'),
                    frame_index=row['frame_index'],source_frame_index=row.get('source_frame_index'),
                    graph=actual,output=row.get('output_identity'),model=row.get('model_identity',upscaled.get('model_identity')),
                    workflow=row.get('workflow_identity',upscaled.get('workflow_identity')),
                    mapping=row.get('mapping_identity',upscaled.get('mapping_identity')),
                    tools=stage_tools('upscale',('ffmpeg','ffprobe','comfy_python')))
                put('upscale',frame_id,row,projection,_roles(actual,('graph',)))
                roles.update(_roles(actual,('frames',len(frames),'graph')));frames.append(projection)
            projection=dict(budget=clip.get('budget'),parameters=clip.get('parameters'),source=clip.get('source_identity'),
                source_frames=clip.get('source_frames'),ordered_mapping=[m for m in upscaled.get('frame_mappings',()) if m.get('shot_id')==uid],
                frames=frames)
            put('upscale',uid,clip,projection,roles)
            stage_roles.update({(len(projected),)+key:value for key,value in roles.items()});projected.append(projection)
        signatures['upscale']['__stage__']=_content_signature(projected,stage_roles)

    if 'composition' in receipts:
        report=receipts['composition'];plan=report.get('plan')
        if plan is None and report.get('plan_identity'):
            plan=_bound_json(report['plan_identity'])
        provenance=report.get('provenance',{})
        projection=dict(plan=plan,settings=report.get('settings'),frame_mappings=report.get('frame_mappings'),
            subtitle_events=report.get('subtitles',{}).get('events'),
            pcm_plan=timeline_projection,requirement_bindings=report.get('requirement_bindings'),cue_checks=report.get('cue_checks'),
            font=provenance.get('font_identity'),music=provenance.get('music_identity'),
            encoding_tools={key:provenance[key] for key in ('ffmpeg_identity','ffprobe_identity') if key in provenance})
        signatures['composition']['__stage__']=_content_signature(projection)

    for stage in ('preflight','validation','publish'):
        if stage in receipts:
            report=receipts[stage]
            projection={key:report[key] for key in ('candidate_identity','subtitle_identity','output_video_identity','output_subtitle_identity','validation') if key in report}
            signatures[stage]['__stage__']=_content_signature(projection)
    return units,signatures
