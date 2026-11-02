"""Explicit authored final-film acceptance and schema-2 scene delivery."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
from pathlib import Path

from ..adapters.common import strict_json,JSON_LIMIT
from ..config import read_json
from ..planning.production_scenes import canonical_digest
from .manifest import now,validate_run_dir
from .production_state import ProductionRefused,RunLock,object_fields,run_path,timestamp
from .scene_final_observations import build_scene_final_observation_template,validate_scene_final_observation
from .execution_limits import production_execution


def boundary(point):
    """Caller-thread durability boundary for interruption tests."""


def _validate(value,expected,*,now):
    try:return validate_scene_final_observation(value,expected,now=now)
    except ValueError as exc:raise ProductionRefused(str(exc)) from exc


def _remember_artifact(store,value):
    previous=store.guard_paths.get(value['path'])
    if previous is not None and canonical_digest(previous)!=canonical_digest(value):
        raise ProductionRefused('previously captured composition bytes changed')
    store.guard_paths.setdefault(value['path'],deepcopy(value))


def _remember_inventory(store,folder,inventory):
    previous=store.guard_directories.get(str(folder))
    if previous is not None and previous!=inventory:
        raise ProductionRefused('previously captured composition inventory changed')
    store.guard_directories.setdefault(str(folder),set(inventory))


def _merge_guards(target,source):
    for value in source.guard_paths.values():_remember_artifact(target,value)
    for folder,inventory in source.guard_directories.items():_remember_inventory(target,folder,inventory)
    for field in ('guard_empty_paths','guard_absent_paths'):
        if not hasattr(target,field):setattr(target,field,set())
        getattr(target,field).update(getattr(source,field,set()))


def _observation_context(context,candidate=None):
    from .scene_media_records import require_scene_upscale_acceptance_record
    from .production_scene_composition import require_scene_composition_record
    candidate=candidate if candidate is not None else require_scene_composition_record(context)
    # Composition validates in its independent root; carry every captured byte
    # into the caller's publication guard without including the new observations.
    composition_store=context.get('composition_store')
    if composition_store is not None:
        _merge_guards(context['store'],composition_store)
    upscaled=context.get('upscaled')
    if upscaled is None: upscaled=require_scene_upscale_acceptance_record(context)
    store=context['store'].for_root('production/scene-composition')
    for name in ('candidate-commit.json','materialized.json','materialized-ready.json','media-ready/candidate.json'):
        record=store.path(name)
        if record.is_file():_remember_artifact(context['store'],store.artifact(record))
    for directory in ('commands','media-ready'):
        folder=store.path(directory);inventory={str(p) for p in folder.rglob('*.json')}
        _remember_inventory(context['store'],folder,inventory)
        for record in inventory:_remember_artifact(context['store'],store.artifact(record))
    from ._scene_revision_readers import final_comparison_request
    requests=[final_comparison_request(context,c['clip_id']) for c in context['scene_clips']['clips']]
    template=build_scene_final_observation_template(context['frozen'],context['units'],context['timeline'],candidate,
        context['scene_clips'],upscaled,context['image_acceptance'],requests)
    saved=store.read('final-observation-template.json')
    if saved is not None and canonical_digest(saved)!=canonical_digest(template):
        raise ProductionRefused('final observation template differs from admitted candidate')
    _merge_guards(store,context['store'])
    return store,candidate,dict(template=template,created_at=candidate['created_at'])


def _observation_receipt(store,candidate,value,original,time_key,stamp):
    return dict(schema_version=2,run_id=store.run_dir.name,composition_sha256=canonical_digest(candidate),
                observation=store.artifact(original),observation_sha256=canonical_digest(value),**{time_key:stamp})


def _verify_observation_snapshot(store,state):
    """Recheck the actual bytes/inventory validated by a completed source scan."""
    snapshot=state['_snapshot'];folder=run_path(store.run_dir,snapshot['folder'])
    if {str(path) for path in folder.glob('*.json')}!=snapshot['inventory']:
        raise ProductionRefused('final observation source inventory changed after validation')
    for original in state['originals']:store.validate_artifact(original['observation'])
    for path,artifact in snapshot['receipts'].items():
        path=run_path(store.run_dir,path)
        if artifact is None:
            if path.exists():raise ProductionRefused('final observation receipt appeared after validation')
        else:store.validate_artifact(artifact)


def final_observation_state(context,*,candidate=None):
    """Reconstruct all final evidence read-only, including failed raw crash state."""
    store,candidate,expected=_observation_context(context,candidate)
    originals=[]; folder=store.path('final-observations')
    source_paths=sorted(folder.glob('*.json'))
    snapshot=dict(folder=str(folder),inventory={str(path) for path in source_paths},receipts={})
    if folder.exists():
        # Incomplete same-directory immutable-write temporaries are not authored
        # sources; preserve them without treating them as accepted JSON.
        for path in source_paths:
            if not path.is_file(): raise ProductionRefused('invalid final observation source')
            raw=path.read_bytes()
            artifact=dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            store.validate_artifact(artifact)
            if path.name!=artifact['sha256']+'.json': raise ProductionRefused('final observation raw SHA filename differs')
            if len(raw)>JSON_LIMIT: raise ProductionRefused('final observation too large')
            value=_validate(strict_json(raw),expected,now=datetime.now(timezone.utc))
            originals.append(dict(value=value,observation=artifact,observation_sha256=canonical_digest(value)))
    result=dict(candidate=candidate,template=expected['template'],accepted=None,rejected=None,originals=originals,_snapshot=snapshot)
    for name,time_key,key,verdict in (
        ('final-observation-accepted.json','accepted_at','accepted','passed'),
        ('final-observation-rejected.json','rejected_at','rejected','failed')):
        receipt_path=store.path(name)
        if not receipt_path.exists():
            snapshot['receipts'][str(receipt_path)]=None
            continue
        raw=receipt_path.read_bytes()
        if len(raw)>JSON_LIMIT:raise ProductionRefused('final observation receipt too large')
        receipt=strict_json(raw)
        receipt_artifact=dict(path=str(receipt_path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        store.validate_artifact(receipt_artifact)
        snapshot['receipts'][str(receipt_path)]=receipt_artifact
        object_fields(receipt,('schema_version run_id composition_sha256 observation observation_sha256 '+time_key).split(),'final observation receipt')
        timestamp(receipt[time_key]); path=store.validate_artifact(receipt['observation'])
        if path.parent!=folder or path.name!=receipt['observation']['sha256']+'.json': raise ProductionRefused('final receipt source path differs')
        value=_validate(read_json(path),expected,now=receipt[time_key])
        wanted=_observation_receipt(store,candidate,value,path,time_key,receipt[time_key])
        if canonical_digest(wanted)!=canonical_digest(receipt) or value['verdict']!=verdict:
            raise ProductionRefused('final observation receipt identity or verdict differs')
        if not any(row['observation']==receipt['observation'] for row in originals): raise ProductionRefused('receipt original missing')
        result[key]=receipt
    failed=[r for r in originals if r['value']['verdict']=='failed']
    if result['accepted'] and (result['rejected'] or failed): raise ProductionRefused('accepted candidate contains conflicting failed evidence')
    if failed and result['rejected'] is None:
        result['rejected']=dict(_raw_only=True,**failed[0])
    _verify_observation_snapshot(store,result)
    return result


def require_scene_final_acceptance_record(context):
    state=final_observation_state(context)
    if state['rejected']: raise ProductionRefused('explicit failed final-film observation requires a revision')
    if state['accepted'] is None: raise ProductionRefused('complete passed final-film acceptance missing')
    store=context['store'];_verify_observation_snapshot(store,state)
    snapshot=state['_snapshot']
    _remember_inventory(store,snapshot['folder'],snapshot['inventory'])
    for original in state['originals']:_remember_artifact(store,original['observation'])
    if not hasattr(store,'guard_absent_paths'):store.guard_absent_paths=set()
    for path,artifact in snapshot['receipts'].items():
        if artifact is None:store.guard_absent_paths.add(path)
        else:_remember_artifact(store,artifact)
    return state['accepted']


def _check_replacement(state,value):
    digest=canonical_digest(value)
    if state['accepted'] and (value['verdict']!='passed' or state['accepted']['observation_sha256']!=digest):
        raise ProductionRefused('accepted final observation cannot be replaced')
    if state['rejected'] and (value['verdict']!='failed' or state['rejected']['observation_sha256']!=digest):
        raise ProductionRefused('failed final observation permanently blocks this candidate version')


def _consume(context,path):
    store,candidate,expected=_observation_context(context)
    state=final_observation_state(context,candidate=candidate)
    # Recover the failed receipt from the exact failed raw before considering a replacement.
    if state['rejected'] and state['rejected'].get('_raw_only'):
        raw=state['rejected']
        receipt=_observation_receipt(store,candidate,raw['value'],Path(raw['observation']['path']),'rejected_at',now())
        store.verify_global();_verify_observation_snapshot(store,state);store.validate_artifact(raw['observation'])
        store.write('final-observation-rejected.json',receipt)
        boundary('observation-rejected')
        # The repaired immutable receipt legitimately changes the old absence
        # snapshot; derive the current receipt proof before considering reuse.
        state=final_observation_state(context,candidate=candidate)
    raw=Path(path).read_bytes()
    if len(raw)>JSON_LIMIT: raise ProductionRefused('final observation exceeds JSON limit')
    current=now(); value=_validate(strict_json(raw),expected,now=current)
    _check_replacement(state,value)
    if state['accepted'] or state['rejected']:
        store.verify_global();_verify_observation_snapshot(store,state)
        status='final_review_ready' if state['accepted'] else 'final_review_failed'
        return _result(context,status,'final_review',candidate=candidate)
    store.verify_global()
    original=store.write_bytes('final-observations/'+hashlib.sha256(raw).hexdigest()+'.json',raw)
    original_identity=dict(path=str(original),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    boundary('observation-original')
    store.verify_global()
    fresh=final_observation_state(context,candidate=candidate)
    # The just-saved failed original intentionally appears as a raw-only rejection.
    _check_replacement(fresh,value)
    if value['verdict'] in ('passed','failed'):
        time_key='accepted_at' if value['verdict']=='passed' else 'rejected_at'
        name='final-observation-accepted.json' if value['verdict']=='passed' else 'final-observation-rejected.json'
        receipt=_observation_receipt(store,candidate,value,original,time_key,current)
        store.verify_global();_verify_observation_snapshot(store,fresh);store.validate_artifact(original_identity)
        store.write(name,receipt)
        boundary('observation-receipt')
    status={'passed':'final_review_ready','failed':'final_review_failed','unverified':'awaiting_final_review'}[value['verdict']]
    return _result(context,status,'final_review',candidate=candidate)


def require_scene_delivery_record(context):
    from .scene_delivery_files import validate_completed
    acceptance=require_scene_final_acceptance_record(context)
    from .production_scene_composition import require_scene_composition_record
    candidate=require_scene_composition_record(context)
    context['validated_final_acceptance']=acceptance
    context['validated_candidate']=candidate
    return validate_completed(context,candidate,acceptance)


def _produce(context):
    from .scene_delivery_files import SceneOutputLock,publish,validate_completed
    from .scene_continuity_records import require_scene_continuity_acceptance
    require_scene_continuity_acceptance(context['frozen'],context['units'],context['timeline'])
    acceptance=require_scene_final_acceptance_record(context)
    from .production_scene_composition import require_scene_composition_record
    candidate=require_scene_composition_record(context)
    stage=context['store'].for_root('production/scene-delivery')
    prior=stage.read('transaction.json')
    if prior is not None and prior.get('status')=='completed':
        validate_completed(context,candidate,acceptance)
    else:
        # Guards include the original candidate, all accepted sources and raw authored evidence.
        def guard(): context['store'].verify_global()
        with SceneOutputLock(stage,candidate['candidate'],context['frozen'].options['output_paths']['movie']) as output_lock:
            publish(dict(context,store=stage),candidate,acceptance,output_lock,guard)
    return _result(context,'delivered','delivery',candidate=candidate)


def _result(context,status,stage,*,candidate=None,error=None):
    from .scene_media_records import SceneMediaResult
    run=context['store'].run_dir if context else None
    template=run/'production/scene-composition/final-observation-template.json' if run else None
    return SceneMediaResult(run_id=run.name if run else None,run_dir=run,status=status,active_stage=stage,
        upscaled_clips=run/'production/scene-upscale/complete.json' if candidate else None,
        candidate=Path(candidate['candidate']['path']) if candidate else None,
        final_observation_template=template if candidate and template.is_file() else None,
        delivery_receipt=Path(context['frozen'].options['output_paths']['receipt']) if status=='delivered' else None,
        log_dir=run/'logs/production' if run else None,error=error)


from .scene_revision_records import revision_validation


from .scene_execution_records import verified_scene_execution_write


@revision_validation
@verified_scene_execution_write
@production_execution
def _entry(frozen,units,timeline,*,paths,logger,lock,stage,operation):
    from .scene_media_records import scene_media_context
    from .image_selection_records import _run
    acquired=None;context=None;result=None
    try:
        try:run=_run(frozen)
        except (OSError,ValueError) as exc:raise ProductionRefused(str(exc)) from exc
        if (frozen.options['run_id']!=run.name or not run.is_dir()
            or not run_path(run,run/'production/options.json').is_file()): raise ProductionRefused('unknown prepared scene media run')
        if logger.run_dir!=run or not logger.production: raise ProductionRefused('matching production logger required')
        if lock is None: acquired=RunLock(run);acquired.__enter__();lock=acquired
        context=scene_media_context(frozen,units,timeline,paths=paths,lock=lock)
        context['store'].assert_owned();result=operation(context)
    except (KeyboardInterrupt,Exception) as exc:
        status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'blocked' if isinstance(exc,ProductionRefused) else 'failed'
        message='; '.join([str(exc) or type(exc).__name__,*getattr(exc,'__notes__',())])
        result=_result(context,status,stage,error=dict(kind=type(exc).__name__,message=message,evidence_paths=[]))
    finally:
        if acquired is not None:
            try: acquired.__exit__(None,None,None)
            except Exception as exc:
                prior=result.error['message']+'; cleanup: ' if result and result.error else ''
                result=_result(context,'failed',stage,error=dict(kind=type(exc).__name__,message=prior+str(exc),evidence_paths=[]))
    return result


def consume_scene_final_observation(frozen,units,timeline,observation_path,*,paths,logger,lock=None):
    return _entry(frozen,units,timeline,paths=paths,logger=logger,lock=lock,stage='final_review',operation=lambda ctx:_consume(ctx,observation_path))


def produce_scene_delivery(frozen,units,timeline,*,paths,logger,lock=None):
    return _entry(frozen,units,timeline,paths=paths,logger=logger,lock=lock,stage='delivery',operation=_produce)
