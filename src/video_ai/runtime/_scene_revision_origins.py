"""Strict read-only admission of a node and its necessary source ancestors."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import wave

from ..planning.production_scenes import canonical_digest, validate_scene_plan
from ..planning.production_timeline import ProductionTimeline
from ..config import parse_scene_planning
from .manifest import thaw
from .production_state import ArtifactStamp, ProductionRefused, object_fields, timestamp
from .scene_revision_records import (RevisionGuard, _json, artifact, require_scene_revision,
    require_revision_import, safe_path, token)
from .verification import verified_read


def run_of(frozen): return Path(frozen.options['script_path']).parent.parent


def inherited(frozen,domain,key):
    if 'scene_revision' not in frozen.options: return None
    proof = require_scene_revision(frozen)
    if domain+':'+key not in proof['imports']: return None
    return require_revision_import(frozen,domain,key,context=proof)


def owned_common(frozen):
    run = run_of(frozen); values = []
    for stage in ('units','timeline'):
        value = _json(run/f'production/{stage}.json',root=run)
        object_fields(value,('schema_version','execution_mode','run_id','stage','created_at','status','input_records','payload'),'source common report')
        if (type(value['schema_version']) is not int or value['schema_version'] != 1 or value['execution_mode'] != 'automatic'
                or value['run_id'] != run.name or value['stage'] != stage or value['status'] != 'completed'):
            raise ProductionRefused('source common report identity differs')
        timestamp(value['created_at']); values.append(value['payload'])
    units,timeline = values[0],ProductionTimeline.from_dict(values[1])
    if (run/'production/production-state.json').exists():
        from .production_state import ProductionStateStore
        state=ProductionStateStore.open(run).snapshot()
        if any(state['stages'][s]['status']!='completed' for s in ('units','speech','timeline')) or not (run/'production/speech.json').is_file():
            raise ProductionRefused('automatic common requires original completed speech/checkpoints')
        _automatic_common(frozen,run,state,units,timeline)
    if units['decoded_text'] != frozen.script.text or units['has_bom'] != frozen.script.has_bom:
        raise ProductionRefused('common original text differs')
    if units['spans'] != [asdict(s) for s in timeline.source_spans]: raise ProductionRefused('common source spans differ')
    if timeline.original_text != frozen.script.text or timeline.has_bom != frozen.script.has_bom:
        raise ProductionRefused('common timeline original differs')
    if thaw(timeline.effective_settings) != thaw(frozen.config.media.timeline): raise ProductionRefused('common timeline settings differ')
    for clip in timeline.clips:
        path = safe_path(clip.pcm.path,run)
        clip.pcm.stamp.verify()
        before = artifact(path,root=run)
        with wave.open(str(path),'rb') as stream:
            if (stream.getframerate(),stream.getnchannels(),stream.getsampwidth(),stream.getnframes(),stream.getcomptype()) != (48000,1,2,clip.samples,'NONE'):
                raise ProductionRefused('source PCM sample format/length differs')
            count = 0
            while chunk := stream.readframes(65536): count += len(chunk)
            if count != clip.samples*2: raise ProductionRefused('truncated source PCM')
        if artifact(path,root=run) != before: raise ProductionRefused('source PCM changed while admitting')
    return dict(units=units,timeline=timeline.as_dict())


def _automatic_common(frozen,run,state,units,timeline):
    """Replay original requests and reports without invoking any writer/service."""
    from ..adapters.common import strict_json
    from ..adapters.ollama import parse_completed_response,OllamaFormatError
    from ..adapters.tts import TtsClient
    from ..planning.segments import TextSpan,SegmentedScript
    from ..planning.production_timeline import build_production_timeline,ProductionAudioInfo
    from ..planning.production_timing import AutomaticSlotPlan,validate_automatic_slots
    from .production_speech import _validate_intent,validate_speech_payload
    from .production_support import recover_http
    from .production_timeline import parse_estimate
    for uid,record in state['units']['units'].items():
        checkpoint=_json(record['checkpoint_path'],root=run);request=checkpoint['request']
        if request is None:continue
        intent=_json(request['intent_path'],root=run)
        if intent['request_id']!=uid or intent['context']['client_id']!=request['client_id'] or intent['context']['script_identity']!=frozen.options['execution_policy']['input_identities']['script']:
            raise ProductionRefused('original units request identity differs')
        raw,_,_=recover_http(None,uid=uid,url=frozen.config.services['ollama']+'/api/generate',payload=intent['body'],evidence_paths=request['response_paths'],durable=False)
        try:proposal=parse_completed_response(strict_json(raw),schema=intent['schema'],request_id=uid,evidence_paths=request['response_paths'])
        except OllamaFormatError:
            if checkpoint['payload']['format_valid']:raise ProductionRefused('original units response differs')
        else:
            if checkpoint['payload']['format_valid'] and checkpoint['payload']['proposal']!=proposal:
                raise ProductionRefused('original units proposal differs')
    speech=_json(run/'production/speech.json',root=run)['payload']
    validate_speech_payload(speech,run=run,units=units)
    spans={s['unit_id']:TextSpan(**s) for s in units['spans'] if s['kind']=='speech'}
    client=TtsClient(None,frozen.config.voice);audio={};estimates={}
    for item in speech['spans']:
        if item['kind']!='speech':continue
        uid=item['unit_id'];record=state['units']['speech'][uid]
        checkpoint=_json(record['checkpoint_path'],root=run);request=checkpoint['request']
        intent=_validate_intent(safe_path(request['intent_path'],run),frozen,spans[uid],client)
        if intent['client_id']!=request['client_id'] or checkpoint['payload']['span']!=item:
            raise ProductionRefused('original speech checkpoint association differs')
        raw,_,_=recover_http(None,uid=uid,url=frozen.config.services['tts']+'/tts',payload=intent['payload'],evidence_paths=request['response_paths'],durable=False)
        from .scene_revision_records import stable_bytes
        if raw!=stable_bytes(item['raw']['path'],root=run):raise ProductionRefused('original TTS response differs from saved WAV')
        audio[uid]=ProductionAudioInfo.from_dict(dict(stamp=item['pcm'],sample_rate=item['sample_rate'],channels=item['channels'],sample_width=item['sample_width'],samples=item['samples']))
        estimates[uid]=parse_estimate(checkpoint['payload']['estimate'])
    script=SegmentedScript(frozen.script.text,frozen.script.has_bom,tuple(TextSpan(**s) for s in units['spans']))
    expected=build_production_timeline(script,audio,settings=frozen.config.media.timeline,fps=16)
    if expected.as_dict()!=timeline.as_dict():raise ProductionRefused('original timeline differs from speech checkpoints')
    slots=_json(state['units']['timeline']['automatic-slots']['checkpoint_path'],root=run)['payload']
    validate_automatic_slots(timeline,AutomaticSlotPlan.from_dict(slots),estimates)


def common(frozen):
    value = inherited(frozen,'common','all')
    return value if value is not None else owned_common(frozen)


def origin_media_context(frozen,units,timeline,*,scene_ids,clip_ids):
    """Reuse source admission only inside this invocation and exact ancestry."""
    from .scene_revision_records import _context
    from .scene_media_records import _scene_media_base_context,scene_media_context
    from .scene_continuity_records import load_continuity_policy
    active=_context.get()
    key=canonical_digest(dict(options=thaw(frozen.options),config=thaw(frozen.config.raw),
        units=units,timeline=timeline.as_dict() if timeline is not None else None,
        scenes=sorted(scene_ids),clips=sorted(clip_ids)))
    contexts=active.setdefault('origin_media_contexts',{}) if active is not None else {}
    context=contexts.get(key)
    if context is None:
        reader=_scene_media_base_context if load_continuity_policy(frozen) is not None else scene_media_context
        context=reader(frozen,units,timeline)
        contexts[key]=context
    store=context['store'];store.verify_captured_bytes();store.verify_tools()
    for stamp in frozen.options['model_stamps'].values():ArtifactStamp.from_dict(thaw(stamp)).verify()
    return context


def _origin_scene_ids(frozen,domain,key):
    prefix=common(frozen)
    from .image_selection_records import load_committed_plan
    _,plan=load_committed_plan(frozen,prefix['units'],ProductionTimeline.from_dict(prefix['timeline']))
    if domain in ('image','choice'):sid=key
    else:
        from .production_scene_revision import _source_execution
        execution=_source_execution(frozen,plan,ProductionTimeline.from_dict(prefix['timeline']))
        clips=execution['clips'] if execution is not None else plan['clips']
        sid=next(c['scene_id'] for c in clips if c['clip_id']==key.split(':')[0])
    required=set()
    def include(scene_id):
        if scene_id in required:return
        required.add(scene_id)
        for ref in next(s for s in plan['scenes'] if s['scene_id']==scene_id)['reference_bindings']:include(ref['source_scene_id'])
    include(sid)
    return required


def _origin_clip_ids(frozen,key):
    prefix=common(frozen)
    from .image_selection_records import load_committed_plan
    _,plan=load_committed_plan(frozen,prefix['units'],ProductionTimeline.from_dict(prefix['timeline']))
    from .production_scene_revision import _source_execution
    execution=_source_execution(frozen,plan,ProductionTimeline.from_dict(prefix['timeline']))
    clips=execution['clips'] if execution is not None else plan['clips']
    by_id={c['clip_id']:c for c in clips};required=set();cid=key.split(':')[0]
    while cid is not None:
        if cid in required or cid not in by_id:raise ProductionRefused('invalid original clip ancestry')
        required.add(cid);cid=by_id[cid]['parent_clip_id']
    return required,set(by_id)


@verified_read
def source_clip_record(frozen,key):
    from ._scene_revision_origin_images import origin_image_scope
    from ._scene_revision_origin_clips import origin_clip_scope
    required,known=_origin_clip_ids(frozen,key)
    with origin_image_scope(frozen,_origin_scene_ids(frozen,'clip',key)),origin_clip_scope(frozen,required,all_ids=known):
        return _source_clip_record(frozen,key)


def _source_clip_record(frozen, key):
    if 'scene_revision' in frozen.options:
        from ._scene_revision_readers import inherited_clip_record
        value = inherited_clip_record(frozen,key)
        if value is not None:return value
    value = common(frozen); units = value['units']; timeline = ProductionTimeline.from_dict(value['timeline'])
    from .scene_clip_records import scene_context,validate_clip
    context = scene_context(frozen,units,timeline)
    target = next((row for row in context['rows'] if row['budget']['clip_id']==key),None)
    if target is None: raise ProductionRefused('unknown source clip')
    parent = None
    for row in context['rows']:
        if row['budget']['scene_id'] != target['budget']['scene_id']: continue
        result = validate_clip(context,row,parent)
        if result is None or result['accepted'] is None or result['rejected'] is not None:
            raise ProductionRefused('source clip/ancestor lacks passed process observation')
        if row['budget']['clip_id']==key: return result
        parent = result
    raise ProductionRefused('source clip missing')


@verified_read
def require_origin_node(frozen,domain,key):
    """Reconstruct owned transactions; inherited nodes recurse through their proof."""
    imported = inherited(frozen,domain,key)
    if imported is not None: return imported
    if domain in ('clip','upscale'):
        from ._scene_revision_origin_images import origin_image_scope
        from ._scene_revision_origin_clips import origin_clip_scope
        required,known=_origin_clip_ids(frozen,key)
        with origin_image_scope(frozen,_origin_scene_ids(frozen,domain,key)),origin_clip_scope(frozen,required,all_ids=known):
            return _owned_origin_node(frozen,domain,key)
    if domain in ('image','choice','clip','upscale'):
        from ._scene_revision_origin_images import origin_image_scope
        with origin_image_scope(frozen,_origin_scene_ids(frozen,domain,key)):
            return _owned_origin_node(frozen,domain,key)
    return _owned_origin_node(frozen,domain,key)


def _owned_origin_node(frozen,domain,key):
    prefix = common(frozen) if domain != 'common' else owned_common(frozen)
    if domain=='common': return prefix
    units,timeline = prefix['units'],ProductionTimeline.from_dict(prefix['timeline'])
    from . import image_selection_records as images
    bible,plan = images.load_committed_plan(frozen,units,timeline)
    run = run_of(frozen)
    if domain=='plan': return dict(bible=bible,scene_plan=plan)
    if domain=='reference_settings':
        from .reference_settings import load_reference_settings
        return load_reference_settings(frozen)
    if domain=='image':
        scene = next((s for s in plan['scenes'] if s['scene_id']==key),None)
        if scene is None: raise ProductionRefused('unknown source image scene')
        _,candidates = images._candidates(frozen,scene,run/'production/jimeng'/key/'candidates.json')
        return dict(scene_id=key,candidates=candidates)
    if domain=='choice':
        index = next((i for i,ids in enumerate(plan['batches'],1) if key in ids),None)
        if index is None: raise ProductionRefused('unknown source choice scene')
        accepted = images._load_accepted(frozen,units,timeline,bible,plan,before=index+1)
        choice = images._choices(accepted).get(key)
        if choice is None: raise ProductionRefused('source choice is not accepted')
        return choice
    if domain=='image_group': return images.require_complete_image_acceptance(frozen,units,timeline)
    if domain=='clip': return source_clip_record(frozen,key)['clip']
    if domain=='upscale':
        from ._scene_upscale_records import validate_frame,validate_extraction
        required,_=_origin_clip_ids(frozen,key)
        context = origin_media_context(frozen,units,timeline,
            scene_ids=_origin_scene_ids(frozen,domain,key),clip_ids=required)
        row = next((r for r in context['rows'] if r['frame_id']==key),None)
        if row is None: raise ProductionRefused('unknown source upscale frame')
        clip = next(c for c in context['scene_clips']['clips'] if c['clip_id']==row['clip_id'])
        extraction = validate_extraction(context,clip)
        result = validate_frame(context,row,extraction)
        if result is None: raise ProductionRefused('source upscale frame not ready')
        return result
    raise ProductionRefused('unknown import domain')


def media_for_node(frozen,domain,key,value):
    """Only enumerated media roles are copied; original evidence stays original."""
    run = run_of(frozen)
    def original(row): return {k:row[k] for k in ('path','bytes','sha256')}
    if domain=='common':
        timeline = ProductionTimeline.from_dict(value['timeline'])
        return [(f'pcm_{i:06d}',artifact(c.pcm.path,root=run)) for i,c in enumerate(timeline.clips,1)]
    if domain=='image': return [(f'candidate_{i:06d}',original(c)) for i,c in enumerate(value['candidates'],1)]
    if domain=='choice': return [('selected_image',original(value))]
    if domain=='clip':
        record = source_clip_record(frozen,key)
        return [('generated',value['generated']),('source',value['source']),('last_frame',record['last_frame']['image'])]
    if domain=='upscale': return [(role,value[role]) for role in ('input','input_copy','model_output','output')]
    return []


def remap_media(value,mappings):
    paths = {m['source']['path']:m['target'] for m in mappings}
    def visit(row):
        if isinstance(row,dict):
            if {'path','bytes','sha256'} <= set(row) and row['path'] in paths:
                target = paths[row['path']]
                return dict(row,**target)
            return {k:visit(v) for k,v in row.items()}
        if isinstance(row,list): return [visit(v) for v in row]
        return deepcopy(row)
    return visit(value)


def make_import_view(target,domain,key,original,mappings,*,common_view=None):
    view = remap_media(original,mappings)
    if domain=='common':
        paths = {row['source']['path']:row['target']['path'] for row in mappings}
        for clip in view['timeline']['clips']:
            original_path = clip['pcm']['stamp']['path']
            if original_path not in paths: raise ProductionRefused('PCM copy mapping missing')
            clip['pcm']['stamp'] = ArtifactStamp.read(paths[original_path]).to_dict()
    elif domain=='plan':
        if common_view is None: raise ProductionRefused('inherited plan lacks common view')
        old_run = original['scene_plan']['run_id']
        def rebase(value):
            if isinstance(value,dict):
                return {k:(target.name if k=='run_id' and v==old_run else
                           canonical_digest(common_view['timeline']) if k=='timeline_sha256' else rebase(v))
                        for k,v in value.items()}
            if isinstance(value,list): return [rebase(v) for v in value]
            return value
        view = rebase(view)
        if 'visual_bible_sha256' in view['scene_plan']:
            view['scene_plan']['visual_bible_sha256'] = canonical_digest(view['bible'])
    return view


def verify_import_view(frozen,sidecar,original,*,origin_frozen=None):
    if sidecar['source_identity_sha256'] != canonical_digest(original): raise ProductionRefused('original node semantic identity differs')
    domain,key = sidecar['domain'],sidecar['key']
    common_view = None
    if domain=='plan':
        root = run_of(frozen)/'production/scene-revision'
        path = root/'views/common'/(token('common','all')+'.json')
        common_view = _json(path,root=root)
    wanted = make_import_view(run_of(frozen),domain,key,original,sidecar['local_artifacts'],common_view=common_view)
    if canonical_digest(wanted) != canonical_digest(sidecar['view']): raise ProductionRefused('inherited view changes original semantics')
    if domain=='common':
        timeline = ProductionTimeline.from_dict(wanted['timeline'])
        if timeline.original_text != frozen.script.text or thaw(timeline.effective_settings) != thaw(frozen.config.media.timeline):
            raise ProductionRefused('inherited common differs from target original/settings')
    if domain=='reference_settings':
        from ._scene_revision_reference import source_reference_context,target_reference_digest,marker_digest
        context=source_reference_context(origin_frozen)
        if context is None or target_reference_digest(frozen,context)!=marker_digest(original):
            raise ProductionRefused('inherited reference settings differ from target effective identity')
    if domain=='plan':
        view = common_view
        settings = parse_scene_planning(wanted['scene_plan']['settings'])
        validate_scene_plan(frozen.script,dict(view['units'],run_id=frozen.options['run_id'],
            source_sha256=frozen.options['execution_policy']['input_identities']['script']['sha256']),
            ProductionTimeline.from_dict(view['timeline']),wanted['bible'],wanted['scene_plan'],settings=settings)


@verified_read
def capture_origin(frozen,domain,key):
    """Capture the node's source closure before admitting it; never entire later scenes."""
    run = run_of(frozen); guard = RevisionGuard(frozen)
    files = {run/'production/options.json',run/'production/units.json',run/'production/timeline.json'}
    directories = {run/'production/inputs',run/'production/workflows'};declaration_directories=set()
    absent = {run/'.make-video.lock'}
    for role in ('script',): files.add(Path(frozen.options['execution_policy']['input_identities'][role]['path']))
    if 'scene_revision' in frozen.options:
        prefix = common(frozen)
    else:
        for stage in ('units','timeline'): guard.capture(run/f'production/{stage}.json',root=run)
        prefix = {stage:_json(run/f'production/{stage}.json',root=run)['payload'] for stage in ('units','timeline')}
        state_path=run/'production/production-state.json'
        if state_path.exists():
            # Bind original checkpoints and their HTTP/command evidence before
            # semantic admission. Empty command logs are evidence too.
            guard.capture(state_path,root=run);files.add(state_path)
            state=_json(state_path,root=run)
            visited=set()
            def references(value):
                if isinstance(value,dict):
                    for child in value.values():references(child)
                elif isinstance(value,list):
                    for child in value:references(child)
                elif isinstance(value,str):
                    path=Path(value)
                    if not path.is_absolute() or not path.is_relative_to(run) or path in visited:return
                    visited.add(path);safe_path(path,run)
                    if not path.exists():absent.add(path)
                    elif path.is_file():
                        if path.suffix=='.json':
                            guard.capture(path,root=run);files.add(path);references(_json(path,root=run))
                        else:guard.capture(path,root=run,allow_empty=True)
            for stage in ('units','speech','timeline'):
                report=run/f'production/{stage}.json';files.add(report)
                directories.add(run/'logs/production/checkpoints'/stage)
                references(state['units'].get(stage,{}))
                if report.exists():
                    guard.capture(report,root=run);references(_json(report,root=run))
    for clip in ProductionTimeline.from_dict(prefix['timeline']).clips: guard.capture(clip.pcm.path,root=run)
    if domain != 'common':
        files |= {run/'production/visual-bible.json',run/'production/scene-plan.json',run/'production/scene-plan-commit.json'}
        directories.add(run/'production/scene-planning')
    if domain in ('image','choice','image_group','clip','upscale','reference_settings'):
        from .image_selection_records import load_committed_plan
        bible,plan = load_committed_plan(frozen,prefix['units'],ProductionTimeline.from_dict(prefix['timeline']))
        closure = set()
        def include(sid):
            if sid in closure:return
            closure.add(sid)
            scene = next(s for s in plan['scenes'] if s['scene_id']==sid)
            for binding in scene['reference_bindings']: include(binding['source_scene_id'])
        if domain in ('image','choice'):
            include(key)
            required_choices={ref['source_scene_id'] for scene in plan['scenes'] if scene['scene_id'] in closure for ref in scene['reference_bindings']}
            if domain=='choice':required_choices.add(key)
            last=max((i for i,ids in enumerate(plan['batches'],1) if set(ids)&required_choices),default=0)
            for i,ids in enumerate(plan['batches'][:last],1):
                directories.add(run/'production/image-selection'/f'image_batch_{i:04d}')
                for sid in ids:files.add(run/'production/jimeng'/sid/'candidates.json')
        elif domain=='reference_settings':closure=set()
        else:
            closure = {s['scene_id'] for s in plan['scenes']}
            directories.add(run/'production/image-selection')
        for sid in closure:
            directories |= {run/'production/jimeng'/sid,run/'production/reference-images'/sid}
        needs_reference=domain=='reference_settings' or any(s['reference_bindings'] for s in plan['scenes'] if s['scene_id'] in closure)
        if needs_reference:
            files |= {run/'production/reference-images/settings.json',run/'production/reference-images/config-source.json',
                      run/'production/reference-images/capability.json'}
            directories.add(run/'production/reference-images/capabilities')
            if domain!='reference_settings':
                selected={}
                for batch in sorted((run/'production/image-selection').glob('image_batch_*/accepted.json')):
                    for row in _json(batch,root=run)['selections']:selected[row['scene_id']]=row['sha256']
                from .image_selection_records import _sha
                for scene in plan['scenes']:
                    if scene['scene_id'] not in closure:continue
                    for binding in scene['reference_bindings']:
                        sha=selected.get(binding['source_scene_id'])
                        if sha is not None:directories.add(run/'production/reference-storage'/_sha(sha))
    if domain in ('clip','upscale'):
        from .production_scene_revision import _source_execution
        execution=_source_execution(frozen,plan,ProductionTimeline.from_dict(prefix['timeline']))
        source_clips=execution['clips'] if execution is not None else plan['clips']
        if execution is not None:
            files.add(run/'production/scene-rendering/execution-budget.json')
            # Admission bytes and external closure must remain verifiable in
            # the source run, regardless of the target's mode or budget.
            if execution['mode']=='whole_scene_v1':
                from .scene_execution_records import verify_whole_scene_frozen
                verify_whole_scene_frozen(frozen)
                records=frozen.options['execution_policy']['input_identities']
                files.update(Path(records[role]['path']) for role in ('whole_scene_evidence','whole_scene_evidence_closure'))
        from .scene_continuity_records import load_continuity_policy
        if load_continuity_policy(frozen) is not None:
            # Retain late raw failures as well as receipts when media is inherited.
            directories.add(run/'production/scene-continuity')
        if 'scene_rendering' in frozen.config.raw:
            # A cached import proof must keep guarding the exact prompt bytes
            # that produced this source, not only its options/request digests.
            files.add(Path(frozen.options['execution_policy']['input_identities']['scene_video_prompts']['path']))
        files.add(run/'production/reference-images/wan-inputs.json')
        files.add(run/'production/scene-clips/inputs.json')
        if domain=='upscale': relevant = source_clips
        else:
            target = next(c for c in source_clips if c['clip_id']==key)
            relevant = [c for c in source_clips if c['scene_id']==target['scene_id'] and c['ordinal']<=target['ordinal']]
        for clip in relevant:
            folder = run/'production/scene-clips'/clip['clip_id']; directories.add(folder)
            absent.add(folder/'observation-rejected.json')
        if domain=='upscale':
            required,_=_origin_clip_ids(frozen,key)
            declaration_directories={run/'production/scene-clips'/c['clip_id'] for c in relevant if c['clip_id'] not in required}
    if domain=='upscale':
        cid,name = key.split(':'); directories.add(run/'production/scene-upscale'/cid/name)
        directories.add(run/'production/scene-upscale'/cid/'input-frames')
        files |= {run/'production/scene-upscale'/cid/'extraction.json',run/'production/scene-upscale'/cid/'extraction-ready.json'}
        files.add(run/'production/scene-upscale/inputs.json')
    if 'scene_revision' in frozen.options: directories.add(run/'production/scene-revision')
    raw=[value for value,_,empty,_ in guard.files.values() if empty]
    json_files, inventories, absent_paths = [], [], []
    for directory in sorted(directories):
        paths = guard.capture_directory(directory,root=run)
        inventories.append(dict(directory=str(directory),paths=paths))
        files.update(Path(p) for p in paths)
        for path in directory.rglob('*'):
            if path.is_file() and path.suffix != '.json':
                if directory in declaration_directories and path.suffix.lower() in ('.png','.mp4'):continue
                raw.append(guard.capture(path,root=run,allow_empty=True))
    for path in sorted(files):
        if path.exists(): json_files.append(guard.capture(path,root=run))
        else: absent.add(path)
    for path in sorted(absent):
        if not path.exists(): guard.capture_absent(path,root=run); absent_paths.append(str(path))
    value = require_origin_node(frozen,domain,key)
    media = media_for_node(frozen,domain,key,value)
    for _,bound in media: guard.capture(bound['path'],root=run,expected=bound)
    guard.verify_captured_bytes()
    return dict(value=value,media=media,guard=guard,
        snapshot=dict(files=json_files,inventories=inventories,absent_paths=absent_paths),raw_files=raw)
