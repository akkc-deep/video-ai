"""Sequential stage coordination with fresh evidence and explicit author gates."""
from dataclasses import dataclass, replace
from collections.abc import Mapping
import json
from pathlib import Path
from uuid import uuid4
from datetime import datetime

from .config import ProjectConfig, load_config, read_json
from .runtime.manifest import ManifestStore, create_manifest, hash_file, now, thaw, STAGES
from .runtime.paths import RuntimePaths, create_run, validate_output_pair, _validate_spelling
from .runtime.timeline_checks import _run_path, _local, _again, _artifact
from .runtime import pipeline_stages as stages
from .runtime.pipeline_evidence import (exclusive, check_lock, check_stage_locks,
    fresh_identity, save_record, write_exclusive, protected_snapshot,register_pipeline_evidence)


class PipelineRefusal(ValueError):
    """Admission, stale evidence or author refusal; never permission to retry."""


def _admit(function,*args,**kwargs):
    try:return function(*args,**kwargs)
    except PipelineRefusal:raise
    except (ValueError,OSError,KeyError,TypeError,AssertionError) as exc:raise PipelineRefusal(str(exc)) from exc


@dataclass(frozen=True)
class PipelineResult:
    run_dir: Path
    parent_run_dir: Path | None
    status: str
    active_stage: str | None
    waiting_for: tuple[str, ...]
    candidate_path: Path | None
    subtitle_path: Path | None
    published: bool
    report_path: Path | None


def _flags(retry_failed, publish, changes_path):
    if type(retry_failed) is not bool or type(publish) is not bool:
        raise PipelineRefusal('pipeline flags must be bool')
    if publish and (retry_failed or changes_path is not None):
        raise PipelineRefusal('--publish is mutually exclusive with --changes/--retry-failed')


def _config_projection(config,identities):
    from .runtime.pipeline_inventory import config_projection
    return config_projection(config,identities)


def _frozen_config(config, snapshot, *, changes=False):
    if read_json(config.config_file) != thaw(config.raw) or read_json(config.voice.config_file) != thaw(config.voice.raw):
        raise PipelineRefusal('loaded config differs from its current source')
    if changes: return
    resolved = thaw(config); resolved.pop('voice'); resolved.pop('raw')
    voice = thaw(config.voice); voice.pop('raw')
    if (resolved != snapshot['config_snapshot']['resolved'] or voice != snapshot['voice_snapshot']['resolved']
            or thaw(config.raw) != snapshot['config_snapshot']['raw'] or thaw(config.voice.raw) != snapshot['voice_snapshot']['raw']):
        raise PipelineRefusal('configuration differs from frozen run; explicit --changes required')


def _identity_index(value, destination):
    """Retain identities admitted by consumers; unbound path strings grant no read."""
    if isinstance(value, Mapping):
        if set(value) == {'path', 'bytes', 'mtime_ns', 'sha256', 'verified_at'}:
            record = thaw(value); actual = fresh_identity(record)
            previous = destination.get(actual.path)
            if previous is not None and (previous.bytes, previous.mtime_ns, previous.sha256) != (actual.bytes, actual.mtime_ns, actual.sha256):
                raise PipelineRefusal('conflicting consumed origin')
            destination[actual.path] = actual
        else:
            for child in value.values(): _identity_index(child, destination)
    elif isinstance(value, (tuple, list)):
        for child in value: _identity_index(child, destination)
    elif hasattr(value, '__dataclass_fields__'): _identity_index(thaw(value), destination)


from .runtime.verification import verified_read


@verified_read
def _collect_inventory(config, run, *, reviews=None):
    from .planning.recovery import ValidatedInventory, signature
    store = ManifestStore.open(run); snapshot = store.snapshot(); _frozen_config(config, snapshot)
    ids = {'config': hash_file(config.config_file), 'voice': hash_file(config.voice.config_file)}
    records = {k:dict(v) for k,v in snapshot['stages'].items()}
    signatures = {}; checkpoints = {}; consumed = {}; author = {}
    # Old single-stage production has no preflight transaction. Adoption does
    # not change its pending historical row or falsely claim a new preflight.
    if records['preflight']['status']=='pending' and records['speech']['status']=='completed':
        records['preflight'] = dict(records['preflight'], status='completed', adopted=True)
    for name in STAGES:
        record = records[name]
        if record['status']=='completed':
            result = dict(adopted=True) if record.get('adopted') else stages.consume(name, config, run)
            consumed[name] = result; signatures[name] = {'__stage__':signature(thaw(result))}
            records[name]['receipt'] = thaw(result.get('report',result) if isinstance(result,Mapping) else result)
            if name=='speech' and result.get('report',{}).get('schema_version')==1:
                # The speech consumer authenticates the complete bound legacy
                # report closure and returns current identities. Its original
                # report retains historical canonical TTS YAML metadata, whose
                # narrow inherited payload rule must not be reinterpreted as a
                # current receipt. Every returned current identity stays strict.
                _identity_index({key:value for key,value in result.items() if key!='report'},ids)
            else:
                _identity_index(result, ids)
            for artifact in snapshot['stages'][name]['artifacts']:
                current = hash_file(Path(artifact['path']))
                if (current.bytes, current.sha256)!=(artifact['bytes'], artifact['sha256']):
                    raise PipelineRefusal('completed stage artifact drift')
                ids[current.path] = current
            if name=='speech' and result.get('accepted') is True: author['voice_acceptance'] = True
            if isinstance(result, dict):
                if result.get('timing_review_identity'): author['timing'] = result['timing_review_identity']
                if result.get('review_identity'): author[name] = result['review_identity']
                for role,field in (('final_review','final_review_identity'),('full_film_acceptance','acceptance_identity')):
                    if result.get(field):author[role]=result[field]
        elif record['status']=='running' and stages.BY_NAME[name].draft:
            if (run/stages.BY_NAME[name].draft).exists():
                checkpoints[name] = dict(stages.validate_checkpoint(name, config, run, snapshot), draft_complete=True)
                _identity_index(checkpoints[name], ids)
    unit_stage = {'speech':'speech','image':'start_images','shot':'source_clips','frame':'upscale','shot_attempt':'source_clips'}
    units = {name:{} for name in STAGES}; submissions = {name:{} for name in STAGES}
    for kind, rows in snapshot['units'].items():
        name = unit_stage[kind]
        for uid, record in rows.items():
            units[name][uid] = record
            if record['submission'] is not None: submissions[name][uid] = record['submission']
    if any(r['status'] not in ('pending','completed') and name not in checkpoints for name,r in records.items()):
        from .runtime.pipeline_import import collect_partial_inventory
        partial = collect_partial_inventory(config, run, snapshot)
        for name, checkpoint in partial.items():
            if name not in STAGES or name in checkpoints:
                raise PipelineRefusal('invalid partial inventory stage')
            checkpoints[name] = thaw(checkpoint)
            _identity_index(checkpoint,ids)
    from .runtime.pipeline_inventory import enrich_inventory
    enriched, semantic_signatures = enrich_inventory(snapshot,consumed,checkpoints)
    for name in STAGES:
        units[name].update(enriched.get(name,{}))
        signatures.setdefault(name,{}).update(semantic_signatures.get(name,{}))
        for uid, verified in checkpoints.get(name,{}).get('verified_units',{}).items():
            units[name][uid] = dict(units[name].get(uid,{}),**thaw(verified['record']))
            signatures[name][uid] = verified['signature']
    _identity_index(units,ids)
    if 'pipeline_import' in snapshot['workflows']:
        from .runtime.pipeline_import import import_source_identities
        for path, identity in import_source_identities(run).items(): ids[path] = fresh_identity(identity)
    projection=_config_projection(config,ids)
    _again(ids)
    if store.snapshot()!=snapshot: raise PipelineRefusal('manifest changed during admission')
    snapshot_identity = hash_file(run/'manifest.json')
    inventory = ValidatedInventory(run_dir=run, snapshot=dict(snapshot,identity=thaw(snapshot_identity)),
        config_projection=projection, input_identities=ids, stage_records=records,
        unit_records=units, checkpoints=checkpoints, signatures=signatures, submissions=submissions, reviews=author)
    return inventory, consumed


def _options(run):
    path = _local(run, run/'logs/pipeline/pipeline-options.json')
    if not path.exists():
        return dict(script=None,unit_review_path=None,image_inputs_path=None,settings_path=None,output_path=None,cpu_planner=False), {}
    identity = hash_file(path); data = read_json(path)
    expected = set('schema_version run_id created_at input_identities unit_review_identity image_inputs_identity settings_identity output_path cpu_planner execution_policy'.split())
    if (set(data)!=expected or type(data['schema_version']) is not int or data['schema_version']!=1
            or data['run_id']!=run.name or type(data['cpu_planner']) is not bool): raise PipelineRefusal('invalid pipeline options')
    from .runtime.manifest import _timestamp
    _timestamp(data['created_at'])
    if datetime.fromisoformat(data['created_at'])>datetime.now().astimezone():raise PipelineRefusal('future pipeline options')
    policy=data['execution_policy']
    if (not isinstance(policy,dict) or set(policy)!=set(('gpu_management','total_timeout_seconds','media_command_timeout_seconds'))
            or policy['gpu_management']!='disabled' or policy['total_timeout_seconds'] is not None
            or type(policy['media_command_timeout_seconds']) is not int or policy['media_command_timeout_seconds']!=300):
        raise PipelineRefusal('invalid pipeline execution policy')
    ids = {name:fresh_identity(value) for name,value in data['input_identities'].items()}
    for name in ('unit_review_identity','image_inputs_identity','settings_identity'):
        if data[name] is not None: ids[name] = fresh_identity(data[name])
    if data['unit_review_identity'] is not None and Path(ids['unit_review_identity'].path)!=run/'logs/pipeline/unit-review.json':
        raise PipelineRefusal('unit review must be the canonical bound copy')
    if data['output_path'] is not None:validate_output_pair(Path(_validate_spelling(data['output_path'])))
    ids['options'] = identity
    return dict(script=Path(ids['script'].path),unit_review_path=Path(data['unit_review_identity']['path']) if data['unit_review_identity'] else None,
        image_inputs_path=Path(data['image_inputs_identity']['path']) if data['image_inputs_identity'] else None,
        settings_path=Path(data['settings_identity']['path']) if data['settings_identity'] else None,
        output_path=Path(data['output_path']) if data['output_path'] else None,cpu_planner=data['cpu_planner']),ids


def _load_changes(path, config, run, snapshot):
    if path is None: return None, {}
    from .planning.recovery import validate_changes
    original = Path(_validate_spelling(path)).absolute()
    if original.resolve(strict=True)!=original: raise PipelineRefusal('redirected changes path')
    identity = hash_file(original); data = read_json(original)
    if data['base_run_id']!=run.name: raise PipelineRefusal('changes base run differs')
    base = data['base_manifest_snapshot_identity']; source = _local(run,Path(base['path']))
    if source.parent!=run/'logs/pipeline': raise PipelineRefusal('changes snapshot must be in base run logs/pipeline')
    ids = {'changes':identity,'base_snapshot':fresh_identity(base),'config':fresh_identity(data['config_identity'])}
    if Path(ids['config'].path)!=config.config_file or read_json(source)!=snapshot:
        raise PipelineRefusal('changes config or base snapshot differs')
    for name in ('script_identity','unit_review_identity'):
        if data[name] is not None: ids[name] = fresh_identity(data[name])
    board = read_json(run/'storyboard.json') if (run/'storyboard.json').exists() else None
    available = {s['shot_id'] for s in board['shots']} if board else set()
    validate_changes(data,run_id=run.name,shot_ids=available)
    if any(row['shot_id'] not in available for row in data['shot_changes']): raise PipelineRefusal('changes contains unknown shot')
    _again(ids)
    return data,ids


def plan_resume(config:ProjectConfig, *, run_dir:Path,reviews_path:Path|None=None,
        changes_path:Path|None=None,retry_failed:bool=False,publish:bool=False):
    from .planning.recovery import build_recovery_plan
    from .runtime.pipeline_reviews import load_reviews
    _flags(retry_failed,publish,changes_path); run = _run_path(run_dir); check_stage_locks(run)
    reviews = load_reviews(run,reviews_path); snapshot = ManifestStore.open(run).snapshot()
    requested={role:hash_file(path) for role,path in reviews.items()}
    changes,ids = _load_changes(changes_path,config,run,snapshot)
    original_config = load_config(Path(snapshot['config_snapshot']['path'])) if changes else config
    inventory,_ = _collect_inventory(original_config,run,reviews=reviews)
    if changes:
        inventory = replace(inventory,snapshot=dict(thaw(inventory.snapshot),identity=changes['base_manifest_snapshot_identity']))
    projection=_config_projection(config,ids) if changes else inventory.config_projection
    result = build_recovery_plan(inventory,config_projection=projection,changes=changes,
        retry_failed=retry_failed,publish=publish,reviews=requested)
    _again(requested)
    _again(ids)
    return result


def run_pipeline(config:ProjectConfig, *, script:Path,unit_review_path:Path,
        image_inputs_path:Path|None=None,settings_path:Path|None=None,
        output_path:Path|None=None,cpu_planner:bool=False)->PipelineResult:
    from .runtime.preflight import preflight
    from .runtime.pipeline_reviews import load_unit_review
    if type(cpu_planner) is not bool: raise PipelineRefusal('cpu_planner must be bool')
    script = Path(_validate_spelling(script)).absolute(); review = _admit(load_unit_review,unit_review_path,script_path=script)
    if not any(s.kind=='speech' for s in review.script.spans): raise PipelineRefusal('unit review has no speech')
    report = _admit(preflight,config,script=script,output=output_path)
    if not report.passed: raise PipelineRefusal('preflight failed: '+json.dumps(report.as_dict(),ensure_ascii=False))
    inputs = {key:_admit(hash_file,path) for key,path in dict(script=script,config=config.config_file,voice=config.voice.config_file).items()}
    if inputs['script'].sha256!=review.script_identity.sha256: raise PipelineRefusal('script changed after semantic admission')
    optional = {}
    for role,path in (('image_inputs_identity',image_inputs_path),('settings_identity',settings_path)):
        if path is not None:
            original = Path(_validate_spelling(path)).absolute()
            if original.resolve(strict=True)!=original: raise PipelineRefusal('redirected pipeline author input')
            optional[role] = _admit(hash_file,original)
    _admit(_again,dict(inputs,**optional,unit_review=review.identity))
    run = create_run(RuntimePaths.from_config(config))
    copied = write_exclusive(run,run/'logs/pipeline/unit-review.json',Path(review.identity.path).read_bytes(),raw=True)
    preflight_id = write_exclusive(run,run/'logs/pipeline/preflight.json',report.as_dict())
    write_exclusive(run,run/'logs/pipeline/pipeline-options.json',dict(schema_version=1,run_id=run.name,created_at=now(),
        input_identities=thaw(inputs),unit_review_identity=thaw(copied),image_inputs_identity=thaw(optional.get('image_inputs_identity')),
        settings_identity=thaw(optional.get('settings_identity')),output_path=str(output_path) if output_path else None,
        cpu_planner=cpu_planner,execution_policy=dict(gpu_management='disabled',total_timeout_seconds=None,media_command_timeout_seconds=300)))
    store = create_manifest(run,config,inputs=inputs,models={},workflows={})
    store.record_stage('preflight','running'); store.record_stage('preflight','completed',artifacts=[_artifact(preflight_id)])
    return resume_pipeline(config,run_dir=run)


def resume_pipeline(config:ProjectConfig, *, run_dir:Path,reviews_path:Path|None=None,
        changes_path:Path|None=None,retry_failed:bool=False,publish:bool=False,
        output_path:Path|None=None)->PipelineResult:
    _flags(retry_failed,publish,changes_path); run = _run_path(run_dir)
    try:
        with exclusive(run) as owner:
            result,child = _invocation(config,run,owner,reviews_path=reviews_path,changes_path=changes_path,
                retry_failed=retry_failed,publish=publish,output_path=output_path)
    except PipelineRefusal: raise
    except (ValueError,OSError,KeyError,TypeError,AssertionError) as exc: raise PipelineRefusal(str(exc)) from exc
    if child is not None:
        return resume_pipeline(config,run_dir=child,publish=False,output_path=output_path)
    return result


def _invocation(config,run,owner,*,reviews_path,changes_path,retry_failed,publish,output_path):
    from .planning.recovery import build_recovery_plan
    from .runtime.pipeline_reviews import load_reviews,accept_voice_review
    check_stage_locks(run); store = ManifestStore.open(run); original = store.snapshot()
    _frozen_config(config,original,changes=changes_path is not None); options,option_ids = _options(run)
    if output_path is not None:
        output_path = Path(_validate_spelling(output_path)).absolute(); validate_output_pair(output_path); options['output_path'] = output_path
    reviews = dict(load_reviews(run,reviews_path)); review_ids = {role:hash_file(path) for role,path in reviews.items()}
    if reviews_path is not None: review_ids['reviews_index'] = hash_file(Path(reviews_path))
    changes,change_ids = _load_changes(changes_path,config,run,original)
    original_config = load_config(Path(original['config_snapshot']['path'])) if changes else config
    active = None; steps = []; consumed = {}; ids = dict(option_ids,**review_ids,**change_ids);audit=[]
    invocation = save_record(run,'invocation',dict(schema_version=1,run_id=run.name,started_at=now(),
        request=dict(reviews_path=reviews_path,changes_path=changes_path,retry_failed=retry_failed,publish=publish,output_path=output_path),input_identities=thaw(ids)))
    audit.append(invocation)
    if not (run/'logs/pipeline/pipeline-options.json').exists():
        save_record(run,'adoption',dict(schema_version=1,run_id=run.name,created_at=now(),
            config_identity=thaw(hash_file(config.config_file)),manifest_protected_projection=original,
            target='published' if publish else 'staging',operation_plan='fresh admission at each step'))
    try:
        while True:
            check_lock(run,owner); check_stage_locks(run); _again(ids)
            inventory,consumed = _collect_inventory(original_config,run,reviews=reviews)
            if changes:
                inventory = replace(inventory,snapshot=dict(thaw(inventory.snapshot),identity=changes['base_manifest_snapshot_identity']))
            ids.update(inventory.input_identities)
            if (not publish and inventory.stage_records['validation']['status']=='completed'
                    and 'full_film_acceptance' in reviews and 'final_review' not in reviews):
                raise PipelineRefusal('supplied acceptance requires matching final_review')
            if not publish and inventory.stage_records['validation']['status']=='completed' and 'final_review' in reviews:
                from .runtime._publication_review import load_final_review,load_gate
                if 'full_film_acceptance' in reviews:
                    author=load_gate(run,consumed['validation'],reviews['final_review'],reviews['full_film_acceptance'])
                else:author=load_final_review(run,consumed['validation'],reviews['final_review'])
                ids.update(author['identities'])
            projection=_config_projection(config,ids) if changes else inventory.config_projection
            plan = build_recovery_plan(inventory,config_projection=projection,changes=changes,
                retry_failed=retry_failed,publish=publish,reviews={role:review_ids[role] for role in reviews})
            plan_id = save_record(run,'plan',dict(schema_version=1,run_id=run.name,created_at=now(),plan=thaw(plan)))
            audit.append(plan_id)
            if plan.refusal_reasons:
                if publish and inventory.stage_records['validation']['status']=='completed' and all(
                        reason.startswith('publication requires') for reason in plan.refusal_reasons):
                    # The established publication owner writes its exact gate
                    # refusal diagnostic even when authors have not supplied files.
                    stages.prepare('publish',config,run,options=options,reviews=reviews,store=store)
                raise PipelineRefusal('; '.join(plan.refusal_reasons))
            if plan.requires_child_run:
                from .runtime.pipeline_import import derive_run
                check_lock(run,owner); _again(ids)
                child=derive_run(config,parent_run_dir=run,plan=plan,changes=changes,changes_identity=change_ids.get('changes'))
                register_pipeline_evidence(store,audit)
                return None,child
            remaining = [op for op in plan.operations if op.action!='consume']
            if not remaining:
                status = 'published' if inventory.stage_records['publish']['status']=='completed' else 'awaiting_acceptance'
                waiting = () if status=='published' else ('final_review','full_film_acceptance'); active = 'publish' if status=='published' else 'validation'; break
            operation = remaining[0]; active = operation.stage
            if operation.action=='wait':
                waiting = tuple(plan.waiting_for or operation.required_review_roles)
                status = 'awaiting_acceptance' if inventory.stage_records['validation']['status']=='completed' else 'awaiting_review'; break
            if operation.action=='reconcile':
                from .runtime.pipeline_recovery import reconcile_submission
                response = reconcile_submission(run,operation.stage,operation.unit_id)
                save_record(run,'diagnostic',dict(schema_version=1,run_id=run.name,reconciliation=thaw(response)))
                if response.state!='completed': raise PipelineRefusal(response.reason)
                reconciliations=[response]
                for uid,submission in inventory.submissions.get(operation.stage,{}).items():
                    if uid==operation.unit_id or submission.get('state') not in ('intent','accepted','ambiguous','still_running','unresolved'): continue
                    other=reconcile_submission(run,operation.stage,uid)
                    save_record(run,'diagnostic',dict(schema_version=1,run_id=run.name,reconciliation=thaw(other)))
                    if other.state!='completed': raise PipelineRefusal(other.reason)
                    reconciliations.append(other)
                check_lock(run,owner); _again(ids)
                from .runtime._pipeline_saved_import import derive_reconciled_run
                child=derive_reconciled_run(config,parent_run_dir=run,plan=plan,reconciliations=tuple(reconciliations))
                register_pipeline_evidence(store,audit)
                return None,child
            check_lock(run,owner); _again(ids)
            if store.snapshot()!={k:thaw(v) for k,v in inventory.snapshot.items() if k!='identity'}: raise PipelineRefusal('manifest changed after plan')
            if active=='timeline' and 'voice_acceptance' in reviews and inventory.reviews.get('voice_acceptance') is not True:
                accept_voice_review(config,run,reviews['voice_acceptance']); continue
            if operation.action=='finalize':
                stage_result = stages.finalize(active,config,run,reviews[stages.BY_NAME[active].review_role])
            elif operation.action in ('prepare','publish'):
                if active=='speech' and not options['unit_review_path'] and 'pipeline_import' not in store.snapshot()['workflows']:
                    raise PipelineRefusal('pending speech requires bound unit review/options')
                stage_result = stages.prepare(active,config,run,options=options,reviews=reviews,store=store)
            else: raise PipelineRefusal('unsupported operation: '+operation.action)
            steps.append(dict(operation=thaw(operation),plan_identity=thaw(plan_id),result=thaw(stage_result),input_identities=thaw(inventory.input_identities),finished_at=now()))
            check_lock(run,owner); _again(ids); state = store.snapshot()['stages'][active]['status']
            if state in ('failed','interrupted','ambiguous'):
                status = 'interrupted' if state=='interrupted' else 'failed'; waiting = (); break
            if state not in ('completed','running'): raise PipelineRefusal('stage did not commit or register a draft')
            protected_snapshot(store.snapshot(),original)
        if status=='awaiting_acceptance' and any(s['operation']['stage']=='validation' for s in steps):
            status='candidate_ready'
        result=_finish(run,store,owner,status,active,waiting,ids,consumed,invocation,steps,original)
        register_pipeline_evidence(store,[*audit,hash_file(result.report_path)])
        return result,None
    except KeyboardInterrupt as exc:
        try:
            save_record(run,'diagnostic',dict(schema_version=1,run_id=run.name,created_at=now(),status='interrupted',stage=active,units=store.snapshot()['units'],message=str(exc)))
            result=_finish(run,store,owner,'interrupted',active,(),ids,consumed,invocation,steps,original)
            register_pipeline_evidence(store,[*audit,hash_file(result.report_path)])
            return result,None
        except (Exception,KeyboardInterrupt):
            raise exc
    except BaseException as exc:
        try: save_record(run,'diagnostic',dict(schema_version=1,run_id=run.name,created_at=now(),status='refused',stage=active,message=str(exc),input_identities=thaw(ids),units=store.snapshot()['units']))
        except (Exception,KeyboardInterrupt): pass
        raise


def _finish(run,store,owner,status,active,waiting,ids,consumed,invocation,steps,original):
    check_lock(run,owner); _again(ids); protected_snapshot(store.snapshot(),original)
    snapshot_id = save_record(run,'manifest',store.snapshot()); candidate = consumed.get('validation',{}); publication = consumed.get('publish',{})
    parent = None
    if 'pipeline_import' in store.snapshot()['workflows']:
        from .runtime.pipeline_import import load_pipeline_import
        parent = run.parent/load_pipeline_import(run)['parent_run_id']
    video = publication.get('output_video_identity') if status=='published' else candidate.get('candidate_identity')
    subtitle = publication.get('output_subtitle_identity') if status=='published' else candidate.get('subtitle_identity')
    report_path = run/'logs/pipeline'/f'result-{uuid4().hex}.json'
    result = PipelineResult(run,parent,status,active,tuple(waiting),Path(video['path']) if video else None,
        Path(subtitle['path']) if subtitle else None,status=='published',report_path)
    waiting_details=[]
    role_stage={'voice_acceptance':'speech','timing':'storyboard','visual_contract':'storyboard',
        'final_review':'validation','full_film_acceptance':'validation'}
    for role in waiting:
        if role not in stages.REVIEW_PATHS and role!='publish':continue
        stage=role_stage.get(role,role);spec=stages.BY_NAME[stage]
        path=run/spec.draft if spec.draft else None
        draft=hash_file(path) if path is not None and path.is_file() else None
        if draft is not None:ids[draft.path]=draft
        artifacts=[]
        for artifact in store.snapshot()['stages'][stage]['artifacts']:
            identity=hash_file(Path(artifact['path']));artifacts.append(thaw(identity));ids[identity.path]=identity
        waiting_details.append(dict(role=role,canonical_path=str(run/stages.REVIEW_PATHS[role]) if role!='publish' else None,
            stage=stage,draft_identity=thaw(draft),stage_artifact_identities=artifacts))
    report_id = write_exclusive(run,report_path,dict(schema_version=1,run_id=run.name,finished_at=now(),invocation_identity=thaw(invocation),
        final_snapshot_identity=thaw(snapshot_id),input_identities=thaw(ids),result=thaw(result),steps=steps,
        waiting_details=waiting_details,
        validation=publication.get('validation') if status=='published' else candidate.get('validation',dict(
            actual_final_video_semantics='unverified',actual_final_video_sync='unverified',full_film_acceptance='unverified'))))
    check_lock(run,owner); _again(ids); fresh_identity(snapshot_id); protected_snapshot(store.snapshot(),original)
    return replace(result,report_path=Path(report_id.path))
