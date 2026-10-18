"""Exclusive storyboard draft/review transaction over verified, immutable inputs."""
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from ..adapters.common import AdapterError, FailureKind, HttpClient
from ..adapters.ollama import OllamaFormatError, OllamaPlanner
from ..config import load_config, read_json
from ..media.timing import measure_envelope
from ..planning.storyboard import (SpeechTimingEvidence, UnitTiming, SemanticCue, plan_slots,
    validate_timing, make_model_schema, validate_model_content, source_catalog, primary_model_slots, expand_boundary_requirements,
    UnsupportedSemanticTimingError, integer)
from ..planning.timeline import SlotRange, budget_slots, sample_to_frame, build_timeline
from .logging import RunLogger
from .manifest import ManifestStore, hash_file, now, thaw, _timestamp
from .paths import RuntimePaths, PathPolicy
from .resources import GpuLease, ResourceSampler
from .services import ServiceManager, ServiceConflictError
from .service_specs import build_service_specs
from .timeline_checks import _run_path, _local, _fresh, _again, _inputs, _artifact, load_committed_timeline
from .visual_contracts import load_visual_contract,check_contract_presence


class StoryboardRefusal(ValueError):
    """Illegal invocation/state/redirected path; no evidence overwritten."""


@dataclass(frozen=True)
class StoryboardResult:
    passed: bool
    run_dir: Path
    storyboard_path: Path
    draft_path: Path
    shot_count: int
    ready_for_images: bool
    status: str


def _result(run,status,shots=0):
    done=status=='completed'
    return StoryboardResult(done,run,run/'storyboard.json',run/'storyboard-draft.json',shots,done,status)


def _keys(data,keys,name):
    if not isinstance(data,dict) or set(data)!=set(keys.split()): raise ValueError(f'{name}: missing/unknown fields')


def _text(value,name):
    if not isinstance(value,str) or not value.strip(): raise ValueError(f'{name}: nonempty text required')


def _passed(data,key='verdict'):
    if data.get(key)!='passed': raise ValueError(f'{key}: review not passed')


def _review_header(data,run,method):
    if type(data['schema_version']) is not int or data['schema_version']!=1 or data['run_id']!=run.name:
        raise ValueError('review schema/run mismatch')
    if type(data['review_method']) is not str or data['review_method'] not in method: raise ValueError('unsupported review method')
    _timestamp(data['reviewed_at']);_text(data['reviewer'],'reviewer');_text(data['reason'],'reason')


def _review_path(run,path):
    try:
        local=_local(run,Path(path).absolute())
        if local.parent!=run/'logs/storyboard' or local.suffix!='.json': raise ValueError('review must be in this run logs/storyboard')
        return local
    except ValueError as exc:raise StoryboardRefusal(str(exc)) from exc


@contextmanager
def _exclusive(run):
    path=_local(run,run/'.storyboard.lock'); owner=dict(pid=os.getpid(),token=uuid4().hex)
    try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError as exc:raise StoryboardRefusal('existing storyboard lock; no takeover') from exc
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(owner,f);f.flush();os.fsync(f.fileno())
        yield owner
    finally:
        try:
            if read_json(path)==owner:path.unlink()
        except (OSError,ValueError):pass
        except KeyboardInterrupt:
            if ManifestStore.open(run).snapshot()['stages']['storyboard']['status']!='completed':raise
            try:
                if read_json(path)==owner:path.unlink()
            except (OSError,ValueError,KeyboardInterrupt):pass


def _check_lock(run,owner):
    if read_json(_local(run,run/'.storyboard.lock'))!=owner: raise OSError('storyboard lock replaced; foreign lock retained')


def atomic_report(path,data):
    """Publish a fully flushed file atomically, with no replacement window."""
    run=_run_path(path.parent);path=_local(run,path)
    temporary=_local(run,path.with_name(f'{path.name}.{uuid4().hex}.tmp'))
    with temporary.open('x',encoding='utf-8',newline='\n') as file:
        json.dump(data,file,ensure_ascii=False,allow_nan=False,indent=2)
        file.flush();os.fsync(file.fileno())
    # NTFS hard-link creation fails if the destination already exists. A
    # pre-check followed by replace/rename would permit a competing overwrite.
    os.link(temporary,_local(run,path))
    temporary.unlink()


def _timing(run,path,timeline):
    identities={'timing':hash_file(path)};data=read_json(path)
    automatic=data.get('review_method')=='automated_audio'
    registration={'manifest':hash_file(run/'manifest.json')} if automatic else {}
    extra=' delegation_identity boundary_basis human_boundary_reviewed' if automatic else ''
    _keys(data,'schema_version run_id script_identity timeline_identity review_method reviewer reviewed_at verdict reason units cues'+extra,'timing review')
    _review_header(data,run,{'human_audio','automated_audio'});_passed(data)
    if automatic:
        if data['boundary_basis']!='pcm_envelope_v1' or data['human_boundary_reviewed'] is not False:raise ValueError('automatic timing must not claim human boundary review')
        identities['delegation']=_fresh(data['delegation_identity'],run=run)
        identities.update({'authorization/'+key:value for key,value in _delegation(run,Path(identities['delegation'].path)).items()})
    for key,expected in [('script_identity',run/'script.txt'),('timeline_identity',run/'timeline.json')]:
        identities[key]=_fresh(data[key],run=run,expected=expected)
    if not isinstance(data['units'],list) or not isinstance(data['cues'],list):raise ValueError('timing arrays required')
    units=[];cues=[]
    if [u.get('unit_id') for u in data['units']]!=[c.unit_id for c in timeline.clips]:raise ValueError('timing unit coverage/order')
    for unit,clip in zip(data['units'],timeline.clips):
        _keys(unit,'unit_id pcm_identity semantic_unit_verdict semantic_reason spoken_start_sample spoken_end_sample boundary_uncertainty_samples verified_internal_silences verdict reason evidence_identity','timing unit')
        for key in ('reason','semantic_reason'):_text(unit[key],key)
        pcm=_fresh(unit['pcm_identity'],run=run,expected=clip.pcm.path)
        if pcm.sha256!=clip.pcm.sha256 or pcm.bytes!=clip.pcm.bytes:raise ValueError('timing PCM differs from timeline')
        identities['pcm/'+clip.unit_id]=pcm
        evidence=_fresh(unit['evidence_identity'],run=run)
        identities['annotation/'+clip.unit_id]=evidence
        if automatic:
            note=read_json(Path(evidence.path))
            _keys(note,'schema_version run_id interpretation units','signal annotation')
            if type(note['schema_version']) is not int or note['schema_version']!=1 or note['run_id']!=run.name or note['interpretation']!='signal_estimate_not_phoneme_alignment':raise ValueError('invalid automatic annotation basis')
            records=note['units']
            if not isinstance(records,list) or [r.get('unit_id') for r in records]!=[c.unit_id for c in timeline.clips]:raise ValueError('automatic annotation coverage/order')
            recorded=next(r for r in records if r['unit_id']==clip.unit_id)
            _keys(recorded,'unit_id estimate semantic_reason','automatic annotation unit')
            measured=measure_envelope(clip.pcm.path)
            if json.dumps(recorded['estimate'],sort_keys=True)!=json.dumps(thaw(measured),sort_keys=True) or recorded['semantic_reason']!=unit['semantic_reason']:raise ValueError('automatic annotation is not reproducible')
            for key in ('spoken_start_sample','spoken_end_sample','boundary_uncertainty_samples','verified_internal_silences'):
                if json.dumps(unit[key])!=json.dumps(thaw(getattr(measured,key))):raise ValueError('timing differs from measured signal envelope')
        if not isinstance(unit['verified_internal_silences'],list):raise ValueError('silence array required')
        silences=[]
        for interval in unit['verified_internal_silences']:
            if not isinstance(interval,list) or len(interval)!=2:raise ValueError('invalid internal silence')
            silences.append(tuple(interval))
        units.append(UnitTiming(unit['unit_id'],unit['spoken_start_sample'],unit['spoken_end_sample'],
            unit['boundary_uncertainty_samples'],tuple(silences),unit['verdict'],unit['semantic_unit_verdict']))
    for cue in data['cues']:
        _keys(cue,'cue_id from_unit_id to_unit_id absolute_sample verdict reason','cue');_text(cue['reason'],'cue reason')
        cues.append(SemanticCue(**{k:cue[k] for k in ('cue_id','from_unit_id','to_unit_id','absolute_sample','verdict')}))
    timing=SpeechTimingEvidence(tuple(units),tuple(cues),data['review_method']);validate_timing(timeline,timing)
    if automatic:_verify_import(run,read_json(run/'segments.json'))
    _again(identities);_again(registration)
    return timing,identities


def load_timing_review(run_dir,path,timeline) -> SpeechTimingEvidence:
    run=_run_path(run_dir);path=_review_path(run,path)
    return _timing(run,path,timeline)[0]


def _delegation(run,path):
    registration={'manifest':hash_file(run/'manifest.json')}
    path=_review_path(run,path);identity=hash_file(path);data=read_json(path)
    _keys(data,'schema_version run_id authority scope statement granted_at script_identity timeline_identity voice_listening_identity','user timing delegation')
    if type(data['schema_version']) is not int or data['schema_version']!=1 or data['run_id']!=run.name or data['authority']!='user_message' or data['scope']!='delegate_audio_timing':raise ValueError('invalid user timing delegation')
    _text(data['statement'],'user delegation');_timestamp(data['granted_at'])
    identities={'delegation':identity}
    for key,expected in [('script_identity',run/'script.txt'),('timeline_identity',run/'timeline.json')]:
        identities['delegation/'+key]=_fresh(data[key],run=run,expected=expected)
    from .speech_checks import load_committed_speech
    speech=load_committed_speech(run)
    listening=speech['listening_identity']
    if speech['accepted'] is not True or listening is None:raise ValueError('delegated automatic timing requires accepted original audio')
    bound=_fresh(data['voice_listening_identity'],expected=Path(listening.path))
    if (bound.bytes,bound.mtime_ns,bound.sha256)!=(listening.bytes,listening.mtime_ns,listening.sha256):raise ValueError('delegation differs from current voice acceptance')
    identities.update({'delegation/speech/'+key:value for key,value in speech['input_identities'].items()})
    identities['delegation/voice_listening_identity']=bound
    _again(identities);_again(registration);return identities


def create_automated_timing_review(config, *, run_dir, delegation_path, semantic_reasons) -> Path:
    """User-delegated marking over already accepted audio, with honest provenance."""
    run=_run_path(run_dir);store=ManifestStore.open(run)
    with _exclusive(run) as owner:
        registration={'manifest':hash_file(run/'manifest.json')}
        snapshot=store.snapshot();output=_review_path(run,run/'logs/storyboard/timing-review.json')
        if snapshot['stages']['storyboard']['status']!='pending' or output.exists():raise StoryboardRefusal('automatic timing requires pending stage and absent review')
        timeline,identities=_verified_inputs(config,run,snapshot);identities.update(_delegation(run,delegation_path))
        expected={c.unit_id for c in timeline.clips}
        if not isinstance(semantic_reasons,dict) or set(semantic_reasons)!=expected:raise ValueError('full agent text semantic review required')
        units=[];note_units=[]
        for clip in timeline.clips:
            reason=semantic_reasons[clip.unit_id];_text(reason,'semantic reason')
            measured=measure_envelope(clip.pcm.path)
            units.append(dict(unit_id=clip.unit_id,pcm_identity=thaw(identities['pcm/'+clip.unit_id]),
                semantic_unit_verdict='passed',semantic_reason=reason,spoken_start_sample=measured.spoken_start_sample,
                spoken_end_sample=measured.spoken_end_sample,boundary_uncertainty_samples=measured.boundary_uncertainty_samples,
                verified_internal_silences=thaw(measured.verified_internal_silences),verdict='passed',
                reason='User delegated automated signal-envelope estimation over accepted PCM. Multi-threshold spread plus 240-sample guard; not human listening or phoneme alignment.'))
            note_units.append(dict(unit_id=clip.unit_id,estimate=thaw(measured),semantic_reason=reason))
        cues=[dict(cue_id=f'cue_{i:04d}',from_unit_id=a['unit_id'],to_unit_id=b['unit_id'],absolute_sample=clip.start_sample+b['spoken_start_sample'],
            verdict='passed',reason='Next accepted PCM signal-envelope onset estimate; final video sync remains unverified.') for i,(a,b,clip) in enumerate(zip(units,units[1:],timeline.clips[1:]),1)]
        timing=SpeechTimingEvidence(tuple(UnitTiming(**{k:u[k] for k in ('unit_id','spoken_start_sample','spoken_end_sample','boundary_uncertainty_samples','verified_internal_silences','verdict','semantic_unit_verdict')}) for u in units),
            tuple(SemanticCue(**{k:c[k] for k in ('cue_id','from_unit_id','to_unit_id','absolute_sample','verdict')}) for c in cues),'automated_audio')
        validate_timing(timeline,timing);_verify_import(run,read_json(run/'segments.json'))
        _again(identities);_again(registration);_check_lock(run,owner)
        logger=RunLogger(run);notes=logger.save_json(f'storyboard/timing-analysis-{uuid4().hex}.json',
            dict(schema_version=1,run_id=run.name,interpretation='signal_estimate_not_phoneme_alignment',units=note_units))
        note_identity=hash_file(notes)
        for unit in units:unit['evidence_identity']=thaw(note_identity)
        report=dict(schema_version=1,run_id=run.name,script_identity=thaw(identities['script_copy']),timeline_identity=thaw(identities['timeline']),
            review_method='automated_audio',reviewer='Codex: reproducible PCM signal analysis and agent text semantic review, explicitly delegated by user',reviewed_at=now(),verdict='passed',
            reason='User accepts existing audio and delegates sample marking. Signal estimate and one-frame math verified; actual audible/semantic video synchronization still unverified.',
            units=units,cues=cues,delegation_identity=thaw(identities['delegation']),boundary_basis='pcm_envelope_v1',human_boundary_reviewed=False)
        _again(identities);_again(registration);_check_lock(run,owner)
        logger.save_json('storyboard/timing-review.json',report)
        _timing(run,output,timeline)
        return output


def _verify_import(run,segments):
    """A bound import receipt does not create a new human listening acceptance."""
    if type(segments.get('schema_version')) is int and segments['schema_version']==2 and segments.get('import_identity') is not None:
        from .speech_checks import load_committed_speech
        consumed=load_committed_speech(run)
        if consumed['report']!=segments:raise ValueError('speech import differs from freshly consumed formal report')
        return
    listening=read_json(run/'voice-listening.json') if (run/'voice-listening.json').exists() else {}
    if 'import_provenance_identity' not in segments:
        if 'inherited_acceptance_identity' in listening:raise ValueError('inherited acceptance needs bound import evidence')
        return
    identity=_fresh(segments['import_provenance_identity'],run=run,expected=run/'logs/storyboard/upstream-import.json')
    receipt=read_json(Path(identity.path))
    _keys(receipt,'schema_version parent_run created_at reason parent_manifest parent_timeline parent_segments parent_voice_listening copies','upstream import')
    if type(receipt['schema_version']) is not int or receipt['schema_version']!=1:raise ValueError('invalid import schema')
    _timestamp(receipt['created_at']);_text(receipt['reason'],'import reason')
    parent=_run_path(receipt['parent_run'])
    if parent==run:raise ValueError('import cannot reference itself')
    identities={'import':identity}
    for key,name in [('parent_manifest','manifest.json'),('parent_timeline','timeline.json'),('parent_segments','segments.json'),('parent_voice_listening','voice-listening.json')]:
        identities[key]=_fresh(receipt[key],expected=parent/name)
    if 'import_provenance_identity' in read_json(parent/'segments.json'):raise ValueError('nested imports are unsupported')
    original=read_json(parent/'voice-listening.json')
    if original.get('listened') is not True or original.get('accepted') is not True:raise ValueError('original imported audio was not accepted')
    _fresh(original['segments_identity'],expected=parent/'segments.json')
    inherited=_fresh(listening['inherited_acceptance_identity'],expected=parent/'voice-listening.json')
    if (inherited.bytes,inherited.sha256)!=(identities['parent_voice_listening'].bytes,identities['parent_voice_listening'].sha256):raise ValueError('inherited acceptance identity differs')
    _text(original.get('user_statement'),'original acceptance statement');_timestamp(original.get('accepted_at'))
    _keys(segments['import_provenance_identity'],'path bytes mtime_ns sha256 verified_at','import identity')
    records=receipt['copies'];seen=set()
    if not isinstance(records,list) or not records:raise ValueError('import copies required')
    for index,record in enumerate(records):
        _keys(record,'original copy','import copy')
        copied=_fresh(record['copy'],run=run)
        target=Path(copied.path)
        if not target.is_relative_to(run/'audio') or target in seen:raise ValueError('invalid/duplicate imported audio copy')
        source=_fresh(record['original'],expected=parent/target.relative_to(run))
        if (source.bytes,source.sha256)!=(copied.bytes,copied.sha256):raise ValueError('imported audio differs from original')
        seen.add(target);identities[f'copy/{index}']=copied;identities[f'original/{index}']=source
    if seen!={p for p in (run/'audio').rglob('*') if p.is_file()}:raise ValueError('incomplete imported audio evidence')
    for key,path in [('parent_script',parent/'script.txt'),('copy_script',run/'script.txt')]:identities[key]=hash_file(path)
    if identities['parent_script'].sha256!=identities['copy_script'].sha256:raise ValueError('imported script differs')
    old_audio=original['audio'];new_audio=listening['audio']
    def signature(items):return [(item['unit_id'],item['text'],item['samples'],item['pcm']['bytes'],item['pcm']['sha256']) for item in items]
    if signature(old_audio)!=signature(new_audio):raise ValueError('inherited audio acceptance association differs')
    _again(identities)


def _verified_inputs(config,run,snapshot):
    timeline=load_committed_timeline(run)
    script,audio,identities,accepted,listening=_inputs(config,run,snapshot)
    if not accepted and (run/'voice-listening.json').exists():raise ValueError('existing listening acceptance is not passed')
    rebuilt=build_timeline(script,audio,settings=config.media.timeline,fps=config.media.fps)
    if rebuilt.as_dict()!=timeline.as_dict():raise ValueError('timeline/config/PCM reconstruction mismatch')
    identities['timeline']=hash_file(run/'timeline.json')
    provenance=read_json(run/'timeline.json')['provenance']
    for key in ('source','script_copy','segments','config','voice'):
        actual=_fresh(provenance[key],expected=Path(identities[key].path))
        if actual.sha256!=identities[key].sha256:raise ValueError('timeline provenance mismatch')
    if set(provenance['pcm'])!=set(audio):raise ValueError('timeline PCM provenance coverage')
    for uid in audio:_fresh(provenance['pcm'][uid],run=run,expected=audio[uid].path)
    if provenance['voice_listening'] is not None:
        if listening is None:raise ValueError('timeline listening provenance lost')
        expected=Path(listening.path)
        _fresh(provenance['voice_listening'],run=run if expected.is_relative_to(run) else None,expected=expected)
    if provenance['speech_evidence']!=snapshot['stages']['speech']:raise ValueError('timeline speech provenance differs')
    _verify_import(run,read_json(run/'segments.json'))
    contract=run/'logs/storyboard/visual-contract.json'
    if contract.exists():identities['visual_contract']=hash_file(_local(run,contract))
    _again(identities)
    return timeline,identities


def _unchanged(store,snapshot,identities,run,owner):
    check_contract_presence(run,identities)
    _verify_import(run,read_json(run/'segments.json'))
    _again(identities);_check_lock(run,owner)
    latest=store.snapshot()
    for key in ('speech','timeline'):
        if latest['stages'][key]!=snapshot['stages'][key]:raise OSError('upstream stage changed during storyboard')
    for key in ('voice_acceptance','pipeline_import'):
        if latest['workflows'].get(key)!=snapshot['workflows'].get(key):raise OSError('speech acceptance registration changed during storyboard')
    if latest['stages']['storyboard']['status']!='running':raise OSError('storyboard transaction state changed')


def _model_files(paths):
    root=paths.policy.validate_write(paths.runtime_root/'models/ollama','model')
    manifest=root/'manifests/registry.ollama.ai/library/qwen3/8b'
    identity=hash_file(manifest);definition=read_json(manifest);identities={'manifest':identity}
    for i,layer in enumerate([definition['config'],*definition['layers']]):
        if not isinstance(layer,dict) or not re.fullmatch(r'sha256:[0-9a-f]{64}',str(layer.get('digest',''))):raise ValueError('invalid Ollama blob digest')
        integer(layer.get('size'),'blob size',1)
        path=root/'blobs'/layer['digest'].replace(':','-')
        if PathPolicy().validate_write(path,'model')!=path:raise ValueError('redirected model blob')
        blob=hash_file(path)
        if blob.bytes!=layer['size'] or blob.sha256!=layer['digest'].split(':')[1]:raise OSError('Ollama blob identity mismatch')
        identities[f'blob_{i}']=blob
    _again(identities);return identities


def _request_content(planner,slots,logger, *, semantic_reasons=None,semantic_specs=None,depiction_policy=None):
    original_slots=slots
    slots=primary_model_slots(slots)
    schema=make_model_schema(slots,semantic_specs=semantic_specs,depiction_policy=depiction_policy)
    context=dict(planning_mode='source_contract_v2' if depiction_policy is not None else 'source_contract_v1' if semantic_specs is not None else 'primary_only_v1',frozen_sources=list(source_catalog(slots).values()),frozen_slots=thaw(slots),
        image_requirements=dict(aspect_ratio='16:9',default_width=1280,default_height=720),
        rules='Return only schema JSON, with concise visual descriptions. Each shot has exactly one primary unit. '
              'Use its primary_text and grounded semantic_reason for all shot visual fields. '
              'Preserve subject, action/state, setting, quantity, denial, reference and source order. '
              'Other original units support context/reference resolution only; do not turn them into this shot scene or end action. '
              'The program handles quantized frame-edge associations, so describe only this primary scene throughout. '
              'Image prompt shows a visible action start; video prompt shows a visible start/process/end and camera path. '
              'Do not replace an audible event with abstract sound words: use the visible source described by the original context. '
              'Presentation choices must not invent unsupported focal subjects, people counts or new events. '
              'Entities require original support and shared identity only when the source supports repetition. '
              'Quantity is a specified count; null if unspecified. Negation is an actual source denial; null if absent. '
              'Context sources are complete exact original unit records including punctuation. '
              'Resolved reference_quote must be inside this primary unit. context_source_indices are local zero-based indices '
              'inside this requirement context_sources, never unit numbers. Resolve actual omitted subjects using their supporting unit. '
              'Every primary passed single-semantic-unit admission; missing word alignment alone is not needs_finer_audio. '
              'Never invent internal word timing. The wire objects are keyed by fixed shot_id/unit_id; fill every required key once.')
    context['primary_scenes']={s.shot_id:dict(primary_unit_id=s.primary_unit_id,primary_text=source_catalog(slots)[s.primary_unit_id]['text'],
        semantic_reason=(semantic_reasons or {}).get(s.primary_unit_id,''),source_facts=(semantic_specs or {}).get(s.primary_unit_id)) for s in slots}
    if semantic_specs is not None:
        context['rules']+=' source_facts are reviewed original interpretations, fixed by schema. All visual fields must depict that subject/action/setting and references. Do not introduce unmentioned stopping, disappearing, new events or other scenes as an end action. Keep the supported action/state continuing at the end. For a source state, show that state and a subtle camera path, not invented object motion.'
    if depiction_policy is not None:
        from ..planning.storyboard import depiction_anchor,CAMERA_PATHS
        context['depiction_policy']=depiction_policy;context['camera_paths']=list(CAMERA_PATHS)
        for s in slots:context['primary_scenes'][s.shot_id]['depiction_anchor']=depiction_anchor(semantic_specs[s.primary_unit_id])
        context['rules']+=' Start composition, action_start, action_end, image_prompt, video_prompt and visual_expression with the exact depiction_anchor, then add a concise visible presentation. Never contradict the anchor or omit its subject in the presentation. Describe visible source motion instead of abstract sound words. Choose an explicit camera_motion from camera_paths. End video_prompt with exactly " Camera path: " + camera_motion + ".". Keep all suffixes concise; generate these complete strings directly, without editing source facts.'
    prompt=json.dumps(context,ensure_ascii=False)
    logger.save_json('storyboard/model-schema.json',schema);logger.save_json('storyboard/model-context.json',context)
    for request_id in ('initial','correction'):
        try:
            content=planner.generate(prompt,schema=schema,request_id=request_id)
            try:validate_model_content(content,slots,semantic_specs=semantic_specs,depiction_policy=depiction_policy)
            except UnsupportedSemanticTimingError:raise
            except ValueError as exc:
                # Persist explicit schema failure before granting correction eligibility.
                logger.save_json(f'storyboard/{request_id}.schema-error.json',dict(message=str(exc),content=content))
                raise OllamaFormatError(str(exc)) from exc
            expanded,associations=expand_boundary_requirements(content,original_slots)
            try:
                logger.save_json('storyboard/primary-content.json',content)
                logger.save_json('storyboard/binding-expansion.json',dict(schema_version=1,
                    original_slots=thaw(original_slots),model_slots=thaw(slots),associations=associations))
            except OSError as exc:
                raise AdapterError(FailureKind.ambiguous,'model completed but primary expansion evidence persistence failed') from exc
            return expanded
        except OllamaFormatError as exc:
            if request_id=='correction':raise
            prompt=json.dumps(dict(immutable_context=context,format_error=str(exc),instruction='Correct all visual fields using the original schema; do not change frozen source identities or time.'),ensure_ascii=False)
    raise RuntimeError('unreachable request budget')


def _generate_owned(config,run,store,logger,slots, *, cpu_only=False,semantic_reasons=None,semantic_specs=None,depiction_policy=None):
    paths=RuntimePaths.from_config(config);models=_model_files(paths)
    specs=build_service_specs(config,run);manager=ServiceManager(paths,store,logger)
    handle=manager.ensure(specs['ollama'])
    if not handle.owned:raise ServiceConflictError('external 11435 Ollama instance; refuse takeover')
    try:
        # Text planning may run entirely on CPU alongside desktop GPU
        # applications. The request explicitly disables GPU offload.
        timeout=max(config.timeouts['ollama_request'],1800) if cpu_only else config.timeouts['ollama_request']
        http=HttpClient(config.services['ollama'],timeout,logger)
        logger.save_json('storyboard/execution-mode.json',dict(mode='cpu' if cpu_only else 'gpu',
            num_gpu=0 if cpu_only else None,effective_request_timeout_seconds=timeout,
            configured_request_timeout_seconds=config.timeouts['ollama_request']))
        version=http.get_json('/api/version',stage='storyboard');tags=http.get_json('/api/tags',stage='storyboard')
        matches=[m for m in tags.get('models',[]) if m.get('name')=='qwen3:8b']
        if not isinstance(version.get('version'),str) or len(matches)!=1 or matches[0].get('digest')!=models['manifest'].sha256:
            raise OSError('Ollama version/model digest unverified')
        _again(models)
        logger.save_json('storyboard/model-identities.json',dict(models=thaw(models),version=version,tags=tags))
        content=_request_content(OllamaPlanner(http,cpu_only=cpu_only),slots,logger,semantic_reasons=semantic_reasons,semantic_specs=semantic_specs,depiction_policy=depiction_policy)
        _again(models)
        return content,models
    finally:
        from .owned_cleanup import stop_owned_preserving_exception
        stop_owned_preserving_exception(manager,handle,logger,'storyboard')


def _media(config):
    return dict(fps=config.media.fps,native_fps=16,profile=thaw(config.media.profile),
        image_aspect_ratio='16:9',default_image_width=1280,default_image_height=720,
        transition=config.media.transition,transition_seconds=config.media.transition_seconds)


def _validation(ready):
    return dict(structural_passed=True,timing_evidence_passed=True,text_semantics_passed=ready,
                actual_visual_semantics='unverified',actual_video_sync='unverified',ready_for_images=ready)


def _timing_basis(timing):
    return dict(method=timing.review_method,human_boundary_reviewed=timing.review_method=='human_audio',
                boundary_basis='human_marked' if timing.review_method=='human_audio' else 'pcm_envelope_v1',actual_video_sync='unverified')


VISUAL_FIELDS=('entity_ids','composition','camera_motion','action_start','action_end','image_prompt','video_prompt','visual_requirements')


def _shots(slots,content,budget):
    shots=[]
    for slot,visual,source_budget in zip(slots,content['shots'],budget.shots):
        shot=thaw(slot)
        for key in VISUAL_FIELDS:
            if key=='visual_requirements':
                shot[key]=[dict(r,requirement_id=f'{slot.shot_id}:req_{i:04d}') for i,r in enumerate(visual[key],1)]
            else:shot[key]=visual[key]
        shot['budget']=thaw(source_budget);shots.append(shot)
    return shots


def _draft(config,run,timeline,identities,timing,slots,content,models,logger):
    budget=budget_slots(timeline,[SlotRange(s.shot_id,s.start_frame,s.end_frame) for s in slots],
        transition=config.media.transition,transition_seconds=config.media.transition_seconds)
    cues=[dict(thaw(c),frame=sample_to_frame(c.absolute_sample,timeline.output_fps)) for c in timing.cues]
    evidence={p.relative_to(logger.root).as_posix():thaw(hash_file(p)) for folder in ('storyboard','http')
              for p in (logger.root/folder).rglob('*') if p.is_file()}
    return dict(schema_version=1,run_id=run.name,status='review_required',passed=False,created_at=now(),
        timeline_identity=thaw(identities['timeline']),script_identity=thaw(identities['script_copy']),
        timing_review_identity=thaw(identities['timing']),cues=cues,effective_media=_media(config),
        global_visual=content['global_visual'],shots=_shots(slots,content,budget),transitions=thaw(budget.transitions),
        provenance=dict(inputs=thaw(identities),models=thaw(models)),validation=_validation(False),request_evidence=evidence,timing_basis=_timing_basis(timing))


def _validate_draft(config,run,draft,timeline,timing,identities):
    _keys(draft,'schema_version run_id status passed created_at timeline_identity script_identity timing_review_identity cues effective_media global_visual shots transitions provenance validation request_evidence timing_basis','draft')
    if type(draft['schema_version']) is not int or draft['schema_version']!=1 or draft['run_id']!=run.name or draft['status']!='review_required' or draft['passed'] is not False:raise ValueError('invalid draft status/run')
    _timestamp(draft['created_at'])
    if draft['timing_basis']!=_timing_basis(timing):raise ValueError('draft timing provenance differs')
    if draft['validation']!=_validation(False) or draft['effective_media']!=_media(config):raise ValueError('invalid draft validation/media')
    for key,source in [('timeline_identity','timeline'),('script_identity','script_copy'),('timing_review_identity','timing')]:
        bound=_fresh(draft[key],expected=Path(identities[source].path))
        if bound.sha256!=identities[source].sha256:raise ValueError('draft input mismatch')
    _keys(draft['provenance'],'inputs models','draft provenance')
    if set(draft['provenance']['inputs'])!=set(identities):raise ValueError('draft provenance input coverage')
    for key,record in draft['provenance']['inputs'].items():
        fresh=_fresh(record,expected=Path(identities[key].path))
        if fresh.sha256!=identities[key].sha256:raise ValueError('draft provenance changed')
    for key,record in draft['provenance']['models'].items():identities['model/'+key]=_fresh(record)
    for key,record in draft['request_evidence'].items():
        if not isinstance(key,str) or Path(key).is_absolute() or '..' in Path(key).parts:raise ValueError('invalid request evidence path')
        identities['request/'+key]=_fresh(record,run=run,expected=run/'logs'/key)
    slots=plan_slots(timeline,timing=timing)
    if len(draft['shots'])!=len(slots):raise ValueError('draft shot coverage')
    content=dict(schema_version=1,global_visual=draft['global_visual'],shots=[])
    for shot,slot in zip(draft['shots'],slots):
        _keys(shot,'shot_id start_frame end_frame primary_unit_id bindings budget '+' '.join(VISUAL_FIELDS),'draft shot')
        visual={k:shot[k] for k in VISUAL_FIELDS if k!='visual_requirements'};visual['shot_id']=shot['shot_id']
        requirements=[]
        for i,r in enumerate(shot['visual_requirements'],1):
            if r.get('requirement_id')!=f'{slot.shot_id}:req_{i:04d}':raise ValueError('stable requirement identity changed')
            requirements.append({k:v for k,v in r.items() if k!='requirement_id'})
        visual['visual_requirements']=requirements;content['shots'].append(visual)
    contract=load_visual_contract(run,slots,identities);specs=contract.facts if contract else None;policy=contract.depiction_policy if contract else None
    validate_model_content(content,slots,semantic_specs=specs,depiction_policy=policy)
    evidence_keys={Path(k).as_posix().casefold():k for k in draft['request_evidence']}
    if len(evidence_keys)!=len(draft['request_evidence']):raise ValueError('duplicate normalized request evidence')
    expansion_keys={'storyboard/primary-content.json','storyboard/binding-expansion.json'}
    mode=read_json(run/'logs/storyboard/model-context.json').get('planning_mode') if 'storyboard/model-context.json' in evidence_keys else None
    if mode in ('source_contract_v1','source_contract_v2') and specs is None:raise ValueError('source contract required for this generation mode')
    if mode=='source_contract_v2' and policy is None:raise ValueError('grounded source contract required for this generation mode')
    primary_mode=mode in ('primary_only_v1','source_contract_v1','source_contract_v2')
    if primary_mode or expansion_keys & set(evidence_keys):
        if not expansion_keys<=set(evidence_keys):raise ValueError('incomplete primary expansion evidence')
        primary=read_json(run/'logs/storyboard/primary-content.json')
        validate_model_content(primary,primary_model_slots(slots),semantic_specs=specs,depiction_policy=policy)
        expanded,associations=expand_boundary_requirements(primary,slots)
        expected=dict(schema_version=1,original_slots=thaw(slots),model_slots=thaw(primary_model_slots(slots)),associations=associations)
        if json.dumps(read_json(run/'logs/storyboard/binding-expansion.json'),sort_keys=True)!=json.dumps(expected,sort_keys=True):
            raise ValueError('primary expansion association differs')
        if json.dumps(expanded,sort_keys=True)!=json.dumps(content,sort_keys=True):raise ValueError('primary model text modified during expansion')
    budget=budget_slots(timeline,[SlotRange(s.shot_id,s.start_frame,s.end_frame) for s in slots],
        transition=config.media.transition,transition_seconds=config.media.transition_seconds)
    if json.dumps(draft['shots'],sort_keys=True)!=json.dumps(_shots(slots,content,budget),sort_keys=True):raise ValueError('draft immutable slots/budget modified')
    if draft['transitions']!=thaw(budget.transitions) or draft['cues']!=[dict(thaw(c),frame=sample_to_frame(c.absolute_sample,timeline.output_fps)) for c in timing.cues]:raise ValueError('draft transition/cue mapping changed')


def _review(run,path,draft,draft_identity, *, origin_report=None):
    identity=hash_file(path);review=read_json(path)
    _keys(review,'schema_version run_id draft_identity timeline_identity timing_review_identity review_method reviewed_at reviewer global_verdict reason entries','text review')
    _review_header(review,run,{'human_text','agent_text'});_passed(review,'global_verdict')
    for key,expected in [('draft_identity',draft_identity),('timeline_identity',draft['timeline_identity']),('timing_review_identity',draft['timing_review_identity'])]:
        record=thaw(expected)
        if origin_report is not None and not Path(record['path']).is_relative_to(run):
            from .pipeline_import import fresh_origin_review
            fresh=fresh_origin_review(run,origin_report,review[key])
            if fresh.path!=record['path']:raise ValueError('review origin path differs')
        else:fresh=_fresh(review[key],run=run,expected=Path(record['path']))
        if (fresh.bytes,fresh.sha256)!=(record['bytes'],record['sha256']):raise ValueError('review binding differs from draft inputs')
    expected=[]
    for shot in draft['shots']:
        for index,requirement in enumerate(shot['visual_requirements']):
            expected.append(dict(shot_id=shot['shot_id'],requirement_id=requirement['requirement_id'],requirement_index=index,
                unit_id=requirement['unit_id'],source_quote=requirement['source_quote']))
    if not isinstance(review['entries'],list) or len(review['entries'])!=len(expected):raise ValueError('review entry coverage')
    seen=set()
    catalog={(e['shot_id'],e['requirement_id']):e for e in expected}
    for entry in review['entries']:
        _keys(entry,'shot_id requirement_id requirement_index unit_id source_quote verdict reason','review entry')
        integer(entry['requirement_index'],'requirement index');_text(entry['reason'],'entry reason');_passed(entry)
        key=(entry['shot_id'],entry['requirement_id'])
        if key in seen or key not in catalog or any(entry[k]!=v for k,v in catalog[key].items()):raise ValueError('review entry association/duplicate')
        seen.add(key)
    _again({'review':identity});return identity


def _failure(run,store,logger,exc,result):
    status=store.snapshot()['stages']['storyboard']['status']
    if status=='completed':
        load_committed_storyboard(run);return _result(run,'completed',result.shot_count)
    error=dict(kind=type(exc).__name__,message=str(exc),traceback_path=None,evidence_paths=[])
    try:error['traceback_path']=str(logger.exception('storyboard',None,exc))
    except (Exception,KeyboardInterrupt):pass
    terminal='interrupted' if isinstance(exc,KeyboardInterrupt) else 'ambiguous' if isinstance(exc,AdapterError) and exc.kind==FailureKind.ambiguous else 'failed'
    try:
        p=logger.save_json(f'storyboard/{uuid4().hex}.failure.json',dict(run_id=run.name,status=terminal,error=error))
        error['evidence_paths']=[str(p)]
    except (Exception,KeyboardInterrupt):pass
    if status=='running':store.record_stage('storyboard',terminal,error=error)
    if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise exc
    return _result(run,terminal,result.shot_count)


def plan_storyboard(config, *, run_dir: Path, timing_review_path: Path, cpu_planner=False) -> StoryboardResult:
    if type(cpu_planner) is not bool:raise StoryboardRefusal('cpu_planner must be boolean')
    run=_run_path(run_dir);path=_review_path(run,timing_review_path);store=ManifestStore.open(run)
    with _exclusive(run) as owner:
        snapshot=store.snapshot()
        if snapshot['stages']['storyboard']['status']!='pending' or (run/'storyboard.json').exists() or (run/'storyboard-draft.json').exists():raise StoryboardRefusal('storyboard already started or artifact exists')
        logger=RunLogger(run);result=_result(run,'failed')
        try:
            timeline,identities=_verified_inputs(config,run,snapshot)
            timing,more=_timing(run,path,timeline);identities.update(more);slots=plan_slots(timeline,timing=timing)
            contract=load_visual_contract(run,slots,identities);specs=contract.facts if contract else None;policy=contract.depiction_policy if contract else None
            _check_lock(run,owner);_again(identities)
            store.record_stage('storyboard','running')
            reasons={u['unit_id']:u['semantic_reason'] for u in read_json(path)['units']}
            _again(identities)
            content,models=_generate_owned(config,run,store,logger,slots,cpu_only=cpu_planner,semantic_reasons=reasons,semantic_specs=specs,depiction_policy=policy)
            validate_model_content(content,slots,semantic_specs=specs,depiction_policy=policy)
            report=_draft(config,run,timeline,identities,timing,slots,content,models,logger)
            commit_identities=dict(identities,**{'model/'+k:v for k,v in models.items()})
            for key,record in report['request_evidence'].items():
                commit_identities['request/'+key]=_fresh(record,run=run,expected=run/'logs'/key)
            _unchanged(store,snapshot,commit_identities,run,owner)
            atomic_report(_local(run,run/'storyboard-draft.json'),report)
            if read_json(run/'storyboard-draft.json')!=report:raise OSError('draft readback differs')
            _unchanged(store,snapshot,commit_identities,run,owner)
            store.record_stage('storyboard','running',artifacts=[_artifact(hash_file(run/'storyboard-draft.json'))])
            return _result(run,'review_required',len(slots))
        except BaseException as exc:return _failure(run,store,logger,exc,result)


def finalize_storyboard(config, *, run_dir: Path, review_path: Path) -> StoryboardResult:
    run=_run_path(run_dir);path=_review_path(run,review_path);store=ManifestStore.open(run)
    if 'storyboard_revision' in store.snapshot()['workflows']:
        from ._pipeline_storyboard_revision import finalize_revision
        return finalize_revision(config,run,path)
    with _exclusive(run) as owner:
        snapshot=store.snapshot();stage=snapshot['stages']['storyboard'];draft_path=run/'storyboard-draft.json'
        if stage['status']!='running' or not draft_path.is_file() or (run/'storyboard.json').exists():raise StoryboardRefusal('running draft required; completed/orphan artifacts cannot be overwritten')
        logger=RunLogger(run);result=_result(run,'failed')
        try:
            timeline,identities=_verified_inputs(config,run,snapshot)
            registered=[a for a in stage['artifacts'] if Path(a['path'])==draft_path]
            if len(registered)!=1:raise ValueError('draft not registered in manifest')
            draft_identity=_fresh(registered[0],run=run,expected=draft_path);draft=read_json(draft_path)
            timing_path=_review_path(run,Path(draft['timing_review_identity']['path']))
            timing,more=_timing(run,timing_path,timeline);identities.update(more)
            _validate_draft(config,run,draft,timeline,timing,identities)
            identities['draft']=draft_identity;identities['review']=_review(run,path,draft,draft_identity)
            report=dict(draft,status='completed',passed=True,validation=_validation(True),review_identity=thaw(identities['review']))
            _unchanged(store,snapshot,identities,run,owner)
            atomic_report(_local(run,run/'storyboard.json'),report)
            identity=hash_file(run/'storyboard.json')
            if read_json(run/'storyboard.json')!=report:raise OSError('storyboard readback differs')
            _unchanged(store,snapshot,identities,run,owner);_again({'storyboard':identity})
            result=_result(run,'completed',len(report['shots']))
            store.record_stage('storyboard','completed',artifacts=[_artifact(identity)])
            return result
        except BaseException as exc:return _failure(run,store,logger,exc,result)


from .verification import verified_read


@verified_read
def load_committed_storyboard(run_dir: Path) -> dict:
    run=_run_path(run_dir);store=ManifestStore.open(run);snapshot=store.snapshot();stage=snapshot['stages']['storyboard']
    if 'storyboard_revision' in snapshot['workflows']:
        from ._pipeline_storyboard_revision import load_revision
        return load_revision(run)
    if (run/'storyboard.json').is_file() and read_json(run/'storyboard.json').get('schema_version')==2:
        from .pipeline_import import load_imported_stage
        return load_imported_stage(run,'storyboard')
    if stage['status']!='completed':raise ValueError('storyboard not completed')
    registered=[a for a in stage['artifacts'] if Path(a['path'])==run/'storyboard.json']
    if len(registered)!=1:raise ValueError('storyboard artifact missing/duplicate')
    identity=_fresh(registered[0],run=run,expected=run/'storyboard.json');report=read_json(run/'storyboard.json')
    if report.get('status')!='completed' or report.get('passed') is not True or report.get('validation')!=_validation(True):raise ValueError('storyboard not ready for images')
    config=load_config(Path(snapshot['config_snapshot']['path']));timeline,identities=_verified_inputs(config,run,snapshot)
    timing,more=_timing(run,_review_path(run,Path(report['timing_review_identity']['path'])),timeline);identities.update(more)
    draft_identity=hash_file(run/'storyboard-draft.json');draft=read_json(run/'storyboard-draft.json')
    _validate_draft(config,run,draft,timeline,timing,identities)
    review_path=_review_path(run,Path(report['review_identity']['path']))
    review_identity=_fresh(report['review_identity'],run=run,expected=review_path)
    bound=_review(run,review_path,draft,draft_identity)
    if bound.sha256!=review_identity.sha256:raise ValueError('review changed')
    expected=dict(draft,status='completed',passed=True,validation=_validation(True),review_identity=report['review_identity'])
    if json.dumps(report,sort_keys=True)!=json.dumps(expected,sort_keys=True):raise ValueError('committed storyboard differs from reviewed draft')
    identities.update(storyboard=identity,draft=draft_identity,review=review_identity);_again(identities)
    _verify_import(run,read_json(run/'segments.json'))
    if store.snapshot()['stages']['storyboard']!=stage:raise OSError('storyboard manifest changed during read')
    check_contract_presence(run,identities)
    return report
