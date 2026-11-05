"""Locked, immutable scene proposals and commit-last planning transactions."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from ..adapters.common import AdapterError, HttpClient, strict_json
from ..adapters.ollama import OllamaFormatError, OllamaPlanner, SceneCapacityError, ollama_body, parse_completed_response
from ..adapters.ollama_scenes import is_environment_transport
from ..config import parse_scene_planner_model, parse_scene_planning, read_json
from ..jimeng_config import STRATEGY
from ..planning.production_scenes import (build_scene_plan, canonical_digest, make_scene_schema,
                                          paragraphs_from_script, validate_scene_plan,prune_unused_visual_entries)
from ..planning.production_timeline import validate_production_timeline
from ..planning.segments import SegmentedScript, TextSpan
from .manifest import ManifestStore, create_manifest, hash_file, thaw, validate_run_dir
from .owned_cleanup import stop_owned_preserving_exception
from .execution_limits import production_execution
from .production_inputs import _same_json, load_frozen_inputs
from .production_state import ProductionRefused, RunLock, object_fields, run_path, write_exclusive
from .production_support import recover_http,http_recovery_scope
from .service_specs import build_service_specs
from .services import ServiceManager, port_listening


def boundary(point):
    """Transaction boundary used by fault-injection tests and coordinators."""


def check_scene_context_log(path):
    """Do not turn a server-truncated request into a valid source-grounded plan."""
    text=Path(path).read_text(encoding='utf-8',errors='replace')
    if 'truncating input prompt' in text:
        raise ProductionRefused('Ollama truncated the original scene input; result cannot be committed')


def use_grouped_compact(folder, logger):
    """Recover prior results before starting an independent transport version."""
    prior=folder/'compact-v1'
    if any((folder/name/'initial.intent.json').exists() for name in ('compact-v2','compact-v3','compact-v4')):return True
    if not (prior/'initial.intent.json').exists():return True
    if any((prior/name).exists() for name in ('proposal.json','initial.response.json','correction.intent.json')):
        return False
    return failed_empty_scene_request(logger,read_json(prior/'initial.intent.json'))


def failed_empty_scene_request(logger,original):
    matches=[]
    for path in logger.path('http').glob('*.request.json'):
        request=read_json(path)
        if request.get('unit_id')==original['request_id'] and request.get('method')=='POST':matches.append((path,request))
    if len(matches)!=1:return False
    path,request=matches[0]
    if request.get('json_body')!=original.get('body'):return False
    response=path.with_name(path.name.removesuffix('.request.json')+'.response.json')
    if not response.exists():return False
    result=read_json(response)
    # A completed result or unknown in-flight request must be consumed by v1.
    # Only a recorded failed response with no content can start the new mode.
    return result.get('error') is not None and result.get('bytes')==0


def use_source_set_compact(folder,logger):
    if any((folder/name/'initial.intent.json').exists() for name in ('compact-v3','compact-v4')):return True
    prior=folder/'compact-v2'
    if not (prior/'initial.intent.json').exists():return True
    if (prior/'proposal.json').exists():return False
    suffix='correction' if (prior/'correction.intent.json').exists() else 'initial'
    if (prior/(suffix+'.response.json')).exists():return False
    return failed_empty_scene_request(logger,read_json(prior/(suffix+'.intent.json')))


def use_direct_compact(folder,logger):
    if (folder/'compact-v4/initial.intent.json').exists():return True
    prior=folder/'compact-v3'
    if not (prior/'initial.intent.json').exists():return True
    if (prior/'proposal.json').exists():return False
    suffix='correction' if (prior/'correction.intent.json').exists() else 'initial'
    if (prior/(suffix+'.response.json')).exists():return False
    original=read_json(prior/(suffix+'.intent.json'))
    for path in logger.path('http').glob('*.request.json'):
        request=read_json(path)
        if request.get('unit_id')!=original['request_id'] or request.get('json_body')!=original['body']:continue
        token=path.name.removesuffix('.request.json');meta=path.with_name(token+'.response.json');raw=path.with_name(token+'.body')
        if not meta.exists() or not raw.exists():return False
        response=read_json(meta)
        if response.get('status')!=500 or response.get('error') is not None:return False
        error=read_json(raw).get('error','')
        return isinstance(error,str) and 'llama-server response stream event exceeded' in error
    return False


def direct_attempt(base,logger):
    """Only an explicit, body-bound retirement opens a new local attempt."""
    index=0
    while True:
        folder=base if index==0 else base/f'attempt_{index:04d}'
        prefix='scene_plan_direct_' if index==0 else f'scene_plan_direct_attempt_{index:04d}_'
        path=folder/'retired.json'
        if not path.exists():return folder,prefix
        if (folder/'proposal.json').exists():raise ProductionRefused('cannot retire a completed scene proposal')
        suffix='correction' if (folder/'correction.intent.json').exists() else 'initial'
        if (folder/(suffix+'.response.json')).exists():raise ProductionRefused('cannot retire a completed scene response')
        intent=read_json(folder/(suffix+'.intent.json'));record=read_json(path)
        object_fields(record,('request_id','body_sha256','reason'),'explicit local attempt retirement')
        if (record['request_id']!=intent['request_id'] or record['body_sha256']!=canonical_digest(intent['body'])
                or not isinstance(record['reason'],str) or not record['reason'].strip()):
            raise ProductionRefused('explicit local attempt retirement differs from original request')
        matches=[]
        for request_path in logger.path('http').glob('*.request.json'):
            request=read_json(request_path)
            if request.get('unit_id')==intent['request_id'] and request.get('method')=='POST':
                if request.get('json_body')!=intent['body']:raise ProductionRefused('retired local HTTP identity differs')
                matches.append(request_path)
        if len(matches)>1:raise ProductionRefused('retired local HTTP evidence has duplicate submissions')
        if matches:
            request_path=matches[0];token=request_path.name.removesuffix('.request.json')
            meta=request_path.with_name(token+'.response.json');raw=request_path.with_name(token+'.body')
            if meta.exists() and raw.exists():
                response=read_json(meta);status=response.get('status')
                if (type(status) is int and 200<=status<300 and response.get('error') is None
                        and response.get('truncated') is False and response.get('bytes')==raw.stat().st_size):
                    raise ProductionRefused('cannot retire a completed original HTTP response')
        index+=1


class _Records:
    def __init__(self, run, lock):
        self.run, self.lock = run, lock

    def owned(self):
        if (not isinstance(self.lock, RunLock) or self.lock.run_dir != self.run
                or read_json(self.lock.path) != self.lock.owner):
            raise ProductionRefused('scene planning lost held run lock')

    def save(self, path, value):
        self.owned(); path = run_path(self.run, path)
        if path.exists():
            if not _same_json(read_json(path), value):
                raise ProductionRefused(f'immutable scene planning record differs: {path.name}')
            return
        temporary = run_path(self.run, path.with_name(path.name+'.'+uuid4().hex+'.tmp'))
        write_exclusive(temporary, value)
        self.owned(); os.rename(temporary, path)


def _prompt(script, units, timeline, settings):
    return ('Plan contextual key scenes using the ENTIRE original script. Narration and subtitles stay '
            'lossless; do not emit replacement narration, frame cuts or task identities. '
            'Group contiguous speech units within each paragraph, at most the configured target, '
            'and allow multiple sentences in one scene. Shared physical subjects use the same entity key; '
            'keep fixed appearance, clothing variants and environment groups separate. '
            'source_facts contain exact unit/range/quote evidence; creative_choices are only proposals. '
            'Changes of appearance/location need current or prior original sources, never future events. '
            'Never claim user selection, human review or visual consistency passed. '
            'Output only the supplied fixed-key proposal schema.\nSCENE_INPUT_JSON\n'+
            json.dumps(dict(decoded_text=script.text, has_bom=script.has_bom,
                paragraphs=paragraphs_from_script(script), finalized_units=units,
                narration_timeline=timeline.as_dict(), settings=asdict(settings)), ensure_ascii=False,
                sort_keys=True, separators=(',', ':'), allow_nan=False))


def _evidence(paths, run):
    result = []
    for value in paths:
        path = run_path(run, value)
        identity = hash_file(path)
        result.append(dict(path=str(path), bytes=identity.bytes, sha256=identity.sha256))
    return result


def _settings(store, folder, base, raw):
    path = folder/'inputs.json'
    explicit = thaw(raw.get('scene_planning'))
    if path.exists():
        saved = read_json(path)
        object_fields(saved, ('inputs', 'explicit_settings', 'settings'), 'scene planning inputs')
        if not _same_json(saved['inputs'], base) or not _same_json(saved['explicit_settings'], explicit):
            raise ProductionRefused('scene planning source inputs/settings identity differs')
        # Persisted effective values, including defaults, are the recovery contract.
        settings = parse_scene_planning(saved['settings'])
        if set(saved['settings']) != {'target_scenes_per_paragraph','max_clip_seconds'}:
            raise ProductionRefused('incomplete effective scene planning settings')
        if explicit is not None:
            for key, value in explicit.items():
                if not _same_json(value, saved['settings'][key]):
                    raise ProductionRefused('explicit scene planning settings differ')
        return settings
    settings = parse_scene_planning(explicit)
    store.save(path, dict(inputs=base, explicit_settings=explicit, settings=asdict(settings)))
    return settings


@production_execution
@http_recovery_scope()
def produce_scene_plan(frozen, units, timeline, *, paths, logger, lock=None, planner=None):
    """Produce/recover proposed scene data; no image, video or email submissions.

    The caller may inject an OllamaPlanner for a local test server. Without one,
    this function starts and stops its own frozen Ollama service. A supplied
    RunLock stays owned by the caller. Downstream code must require the commit.
    """
    run = validate_run_dir(Path(frozen.options['script_path']).parent.parent)
    if lock is None:
        with RunLock(run) as held:
            return produce_scene_plan(frozen, units, timeline, paths=paths, logger=logger,
                                      lock=held, planner=planner)
    store = _Records(run, lock); store.owned()
    fresh = load_frozen_inputs(run)
    if not _same_json(fresh, frozen) or frozen.options['run_id'] != run.name:
        raise ProductionRefused('scene planning frozen input/run identity differs')
    if frozen.config.production_strategy != STRATEGY:
        raise ProductionRefused('scene planning requires paragraph_jimeng_v1')
    if logger.run_dir != run or not logger.production:
        raise ProductionRefused('scene planning requires matching production logger')
    validate_production_timeline(timeline)
    script = SegmentedScript(frozen.script.text, frozen.script.has_bom, tuple(TextSpan(**s) for s in units['spans']))
    source = frozen.options['execution_policy']['input_identities']['script']['sha256']
    if hashlib.sha256((b'\xef\xbb\xbf' if script.has_bom else b'')+script.text.encode('utf-8')).hexdigest() != source:
        raise ProductionRefused('scene planning script identity differs')
    if 'run_id' in units or 'source_sha256' in units:
        raise ProductionRefused('units payload cannot override frozen scene identities')
    bound_units = dict(units, run_id=run.name, source_sha256=source)
    base = dict(schema_version=2, production_strategy=STRATEGY, algorithm='scene_planning_v1',
                run_id=run.name, source_sha256=source, units_sha256=canonical_digest(units),
                timeline_sha256=canonical_digest(timeline.as_dict()),
                frozen_options_sha256=canonical_digest(frozen.options))
    folder = run_path(run, run/'production/scene-planning')
    settings = _settings(store, folder, base, frozen.config.raw)
    schema = make_scene_schema(script, bound_units, timeline, settings)
    prompt = _prompt(script, units, timeline, settings)
    identity = dict(base, settings=asdict(settings), schema_sha256=canonical_digest(schema),
                    prompt_sha256=hashlib.sha256(prompt.encode('utf-8')).hexdigest())
    # This selects a representation, never a source-length refusal. Historical
    # single-request evidence stays untouched in its original directory.
    compact=len(prompt.encode('utf-8'))>32768
    grouped=compact and settings.target_scenes_per_paragraph==1 and any(
        len(row['unit_ids'])>1 for row in paragraphs_from_script(script)) and use_grouped_compact(folder,logger)
    source_sets=grouped and use_source_set_compact(folder,logger)
    direct=source_sets and use_direct_compact(folder,logger)
    if compact:folder=run_path(run,folder/('compact-v4' if direct else 'compact-v3' if source_sets else 'compact-v2' if grouped else 'compact-v1'))
    prefix=None
    if direct:folder,prefix=direct_attempt(folder,logger)
    manager = None; handle = None
    model = parse_scene_planner_model(frozen.config.raw.get('scene_planner_model', 'qwen3:8b'))
    if planner is not None and (not isinstance(planner, OllamaPlanner)
            or planner.http.logger is not logger or planner.http.base_url != frozen.config.services['ollama'].rstrip('/')
            or planner.cpu_only != frozen.options['cpu_planner'] or planner.model != model):
        raise ProductionRefused('scene planner differs from frozen local binding')
    try:
        last_error = None
        for suffix in ('initial', 'correction'):
            uid = (prefix if direct else 'scene_plan_compact3_' if source_sets else 'scene_plan_compact2_' if grouped else 'scene_plan_compact_' if compact else 'scene_plan_')+suffix
            current = prompt if suffix == 'initial' else prompt+'\nCORRECTION\n'+last_error
            intent_path = folder/(suffix+'.intent.json')
            if intent_path.exists():
                intent = read_json(intent_path)
                object_fields(intent, ('identity','request_id','prompt','schema','body','context'), 'scene intent')
                context = intent['context']
                object_fields(context, ('client_id','scene_identity')+
                              (('model_session',) if 'model_session' in context else ()), 'scene intent context')
                original_body = None
                versions=[(True,True,True,True,True,True)]+[(a,b,c,d,False,True) for a,b,c,d in
                    ((False,False,False,False),(True,False,False,False),(True,True,False,False),(True,True,True,False),(True,True,True,True))]
                if source_sets:versions.append((True,True,True,True,True,False))
                for grounded,reasoning,keys,environment,unlimited,source_nonempty in versions:
                    try:
                        candidate=ollama_body(current,schema,cpu_only=frozen.options['cpu_planner'],
                            scene_planning=True,scene_source_constraints=grounded,scene_reasoning=reasoning,model=model,
                            scene_key_constraints=keys,scene_environment_constraints=environment,scene_unlimited=unlimited,
                            scene_compact=compact,scene_grouped=grouped,scene_source_sets=source_sets,
                            scene_source_nonempty=source_nonempty,scene_direct=direct,
                            model_session=context.get('model_session'))
                    except SceneCapacityError:
                        # An unused legacy representation can be larger than
                        # the durable compact request. It cannot match here.
                        continue
                    if _same_json(intent['body'],candidate):
                        original_body = candidate
                        break
                expected = dict(identity=identity, request_id=uid, prompt=current, schema=schema,
                    body=original_body, context=context)
                if (original_body is None or not _same_json(intent,expected) or not _same_json(context['scene_identity'],identity)
                        or not isinstance(context['client_id'],str) or len(context['client_id']) != 32):
                    raise ProductionRefused('original scene planning intent/prompt differs')
            else:
                if (run/'production/scene-plan-commit.json').exists() or (folder/'proposal.json').exists():
                    raise ProductionRefused('committed scene plan lacks original intent')
                context = dict(client_id=uuid4().hex, scene_identity=identity)
                if planner is None or handle is not None and handle.owned:context['model_session']='owned_stage_v1'
                intent = dict(identity=identity, request_id=uid, prompt=current, schema=schema,
                    body=ollama_body(current,schema,cpu_only=frozen.options['cpu_planner'],scene_planning=True,model=model,
                        scene_compact=compact,scene_grouped=grouped,scene_source_sets=source_sets,scene_direct=direct,
                        model_session=context.get('model_session')), context=context)
                store.save(intent_path,intent)
                boundary('intent'); store.owned()
                if planner is None:
                    # A standalone planner can create the usual production manifest;
                    # an existing coordinator manifest remains authoritative.
                    if (run/'manifest.json').exists():
                        manifest = ManifestStore.open(run,verify_integrity=False)
                    else:
                        store.owned()
                        manifest = create_manifest(run, frozen.config,
                            inputs={'script':hash_file(Path(frozen.options['script_path']))},
                            models={}, workflows={}, verify_integrity=False)
                    manager = ServiceManager(paths,manifest,logger)
                    store.owned()
                    if port_listening(frozen.config.services['ollama'],3):
                        raise ProductionRefused('external Ollama service at '+frozen.config.services['ollama'])
                    handle = manager.ensure(build_service_specs(frozen.config,run,production=True,
                        frozen=frozen,store=manifest,planner_transport='llama_direct' if direct else None)['ollama'])
                    if not handle.owned:
                        raise ProductionRefused('external Ollama service at '+handle.url)
                    planner = OllamaPlanner(HttpClient(frozen.config.services['ollama'],
                        frozen.options['execution_policy']['ollama_request_seconds'],logger),
                        cpu_only=frozen.options['cpu_planner'],model=model)
                if handle is not None:
                    record=manifest.snapshot()['services'].get('ollama',{})
                    if record.get('pid')==handle.pid and record.get('stderr_path'):
                        store.save(folder/(suffix+'.service.json'),dict(request_id=uid,
                            body_sha256=canonical_digest(intent['body']),stderr_path=record['stderr_path']))
                def on_intent(path, body):
                    store.owned()
                    if not _same_json(body,intent['body']):
                        raise ProductionRefused('scene planner changed original request body')
                store.owned()
                try:
                    planner.generate(current,schema=schema,request_id=uid,
                                     intent_context=context,on_intent=on_intent)
                except OllamaFormatError:
                    pass # Only confirmed completed evidence can authorize correction.
            store.owned()
            try:
                raw, _, evidence = recover_http(logger,uid=uid,
                    url=frozen.config.services['ollama'].rstrip('/')+'/api/generate',payload=intent['body'])
            except AdapterError as exc:
                raise ProductionRefused('scene planning original submission response unavailable; no POST retry') from exc
            response = dict(identity=identity, request_id=uid,
                            response_sha256=hashlib.sha256(raw).hexdigest(), evidence=_evidence(evidence,run))
            store.save(folder/(suffix+'.response.json'),response)
            boundary('response'); store.owned()
            try:
                outer = strict_json(raw)
            except ValueError as exc:
                raise ProductionRefused('unknown original scene outer response; no correction POST') from exc
            if outer.get('done_reason') == 'length':
                raise ProductionRefused('scene planning response truncated; full context/output required, no automatic retry')
            service_path=folder/(suffix+'.service.json')
            if service_path.exists():
                record=read_json(service_path)
                object_fields(record,('request_id','body_sha256','stderr_path'),'scene service binding')
                if record['request_id']!=uid or record['body_sha256']!=canonical_digest(intent['body']):
                    raise ProductionRefused('scene service binding differs from original request')
                check_scene_context_log(run_path(run,record['stderr_path']))
            try:
                content = parse_completed_response(outer,schema=schema,request_id=uid,evidence_paths=evidence,expected_model=model,
                    scene_prompt=current if is_environment_transport(intent['body']) else None,wire_schema=intent['body']['format'])
                try:
                    bible, plan = build_scene_plan(script,bound_units,timeline,content,settings=settings)
                except ValueError as exc:
                    if not direct or str(exc)!='unused proposal visual entry':raise
                    if (suffix=='initial' and (folder/'correction.intent.json').exists()
                            and not (folder/'initial.catalog-pruning.json').exists()):raise
                    normalized,removed=prune_unused_visual_entries(content)
                    if not removed:raise
                    store.save(folder/(suffix+'.catalog-pruning.json'),dict(schema_version=1,
                        algorithm='drop_unreferenced_visual_rows_v1',identity=identity,request_id=uid,
                        response_sha256=response['response_sha256'],original_proposal_sha256=canonical_digest(content),
                        normalized_proposal_sha256=canonical_digest(normalized),removed=removed))
                    content=normalized
                    bible, plan = build_scene_plan(script,bound_units,timeline,content,settings=settings)
                validate_scene_plan(script,bound_units,timeline,bible,plan,settings=settings)
            except (OllamaFormatError,ValueError) as exc:
                last_error = str(exc)
                if suffix == 'correction':
                    raise ProductionRefused('second completed scene proposal invalid: '+last_error) from exc
                notes=getattr(exc,'__notes__',())
                if notes:
                    detailed=last_error+'\n'+'\n'.join(notes)
                    saved=folder/'correction.intent.json'
                    # Reconstruct either historical generic feedback or current
                    # exact source feedback; the complete intent/body is checked above.
                    if not saved.exists() or read_json(saved).get('prompt')!=prompt+'\nCORRECTION\n'+last_error:
                        last_error=detailed
                continue
            proposal = dict(schema_version=2, identity=identity, request_id=uid,
                            response_sha256=response['response_sha256'], proposal=content)
            store.save(folder/'proposal.json',proposal)
            boundary('proposal'); store.owned()
            # Validate every existing output before filling any missing output.
            outputs = [(run/'production/visual-bible.json',bible), (run/'production/scene-plan.json',plan)]
            commit = {k:plan[k] for k in ('schema_version','run_id','source_sha256','units_sha256',
                                        'timeline_sha256','settings','visual_bible_sha256')}
            commit['scene_plan_sha256'] = canonical_digest(plan)
            outputs.append((run/'production/scene-plan-commit.json',commit))
            for path, value in outputs:
                if path.exists() and not _same_json(read_json(path),value):
                    raise ProductionRefused('immutable scene output/commit identity differs')
            if outputs[-1][0].exists() and not all(path.exists() for path,_ in outputs):
                raise ProductionRefused('committed scene plan lacks required output')
            for (path,value),point in zip(outputs,('visual-bible','scene-plan','commit')):
                store.save(path,value); boundary(point); store.owned()
            return bible, plan
        raise ProductionRefused('scene planning failed')
    finally:
        stop_owned_preserving_exception(manager,handle,logger,'scene_planning')
