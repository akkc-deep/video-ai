"""Import fully replayed saved requests without editing their original state."""
from pathlib import Path
from uuid import uuid4
from collections.abc import Mapping

from ..config import load_config, read_json
from ..planning.recovery import signature
from .manifest import ManifestStore, create_manifest, hash_file, thaw, STAGES, now
from .paths import RuntimePaths, create_run
from .logging import RunLogger
from .timeline_checks import _run_path, _artifact, _again
from . import pipeline_import as imports
from .pipeline_recovery import (
    Reconciliation, _native_saved_validation, _metadata, _matches, _same_identity,
    _history_matches, _require_saved_history,
)


_FIELDS=set('schema_version parent_run_id stage unit_id attempt_id prompt_id source_record graph_identity history_identity source_identities native_record processing_identities created_at'.split())


def _without_verification(value):
    value=thaw(value)
    if isinstance(value,dict):
        if set(value)=={'path','bytes','sha256','mtime_ns','verified_at'}:
            return {key:value[key] for key in ('path','bytes','sha256','mtime_ns')}
        return {key:_without_verification(child) for key,child in value.items()}
    if isinstance(value,list):return [_without_verification(child) for child in value]
    return value


def _successful_history(response, saved, graph):
    matches=[]
    for identity in response.evidence_identities:
        path=Path(identity.path)
        if path.suffix not in ('.body','.json'):continue
        try:data=read_json(path)
        except ValueError:continue
        entry=data.get(response.prompt_id)
        if not isinstance(entry,dict):continue
        if _history_matches(entry,saved,graph,prompt_id=response.prompt_id):
            matches.append((identity,entry))
    if len(matches)!=1:raise ValueError('saved success requires one exact bound queue/history response')
    return matches[0]


def _proof_signature(stage, record, graph):
    from .pipeline_inventory import _content_signature, _roles
    projection={key:value for key,value in record.items() if key not in ('evidence_identities','submission','attempts','run_id','checkpoint_identity')}
    projection['graph']=graph
    return _content_signature(projection,_roles(graph,('graph',)))


def _verify_processing(proof):
    """Verify a child-owned real trim with its actual immutable argv receipts."""
    record=proof['native_record'];identities=proof['processing_identities']
    if proof['stage']!='source_clips':
        if identities:raise ValueError('unexpected processing evidence for saved PNG')
        return
    source=imports.fresh(record['source_identity'])
    generated=imports.fresh(record['generated_identity'])
    matches=[]
    for path,identity in identities.items():
        imports.fresh(identity)
        if Path(path).suffix=='.json':
            value=read_json(Path(path))
            if set(value)=={'source','target','frames','filter','command'}:matches.append(value)
    if len(matches)!=1:raise ValueError('saved source requires one real child-owned trim receipt')
    trim=matches[0];frames=record['source_frames'];expected_filter=f'trim=start_frame=0:end_frame={frames},setpts=N/(16*TB)'
    if trim['frames']!=frames or trim['filter']!=expected_filter or not _same_identity(trim['target']['identity'],source):
        raise ValueError('saved source trim frame mapping or target identity differs')
    copied=imports.fresh(trim['source']['identity'])
    if (copied.bytes,copied.sha256)!=(generated.bytes,generated.sha256):raise ValueError('trim original input content differs from saved model output')
    command=trim['command'];child=_run_path(command['cwd']);config=load_config(Path(ManifestStore.open(child).snapshot()['config_snapshot']['path']))
    expected=[str(v) for v in (config.tools['ffmpeg'],'-nostdin','-n','-v','error','-xerror','-i',Path(copied.path),
        '-vf',expected_filter,'-an','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough',Path(source.path))]
    if command['args']!=expected or type(command['returncode']) is not int or command['returncode']!=0 or command['timed_out'] is not False:
        raise ValueError('saved source actual child trim command differs')
    for key in ('stdout_path','stderr_path'):
        if command[key] not in identities or Path(command[key]).read_bytes():raise ValueError('saved source trim raw success evidence missing')
    from ..media.video import inspect_video
    info,_=inspect_video(Path(source.path),width=record['width'],height=record['height'],config=config,
        paths=RuntimePaths.from_config(config),logger=RunLogger(child),unit_id=record['shot_id'],timeout=300)
    if info['frames']!=frames or info['pixel_format']!='yuv420p':raise ValueError('saved source transformed media differs from retained budget')


def consume_reconciled_unit(parent, row):
    """Return a strictly replayed original image/clip/frame for explicit serializers."""
    parent=_run_path(parent);source=row['imported_record'];identity=source['source_report_identity']
    imports.fresh(identity);proof=read_json(Path(identity['path']))
    if set(proof)!=_FIELDS or type(proof['schema_version']) is not int or proof['schema_version']!=1:
        raise ValueError('invalid saved-submission origin proof')
    origin=_run_path(parent.parent/proof['parent_run_id'])
    if Path(identity['path']).parent!=origin/'logs/pipeline' or not Path(identity['path']).name.startswith('reconciled-'):
        raise ValueError('saved submission proof must retain canonical original origin')
    snapshot=ManifestStore.open(origin).snapshot();stage=proof['stage']
    kind={'start_images':'image','source_clips':'shot_attempt','upscale':'frame'}[stage]
    unit=snapshot['units'][kind].get(proof['unit_id'])
    if unit!=proof['source_record'] or unit is None or unit['submission'] is None:
        raise ValueError('saved original source unit/submission changed')
    for value in proof['source_identities'].values():imports.fresh(value)
    imports.fresh(proof['graph_identity']);imports.fresh(proof['history_identity'])
    graph=read_json(Path(proof['graph_identity']['path']));entry=read_json(Path(proof['history_identity']['path']))[proof['prompt_id']]
    saved=unit['submission']
    if saved['attempt_id']!=proof['attempt_id'] or not _matches(_metadata(entry.get('prompt')),saved,graph):
        raise ValueError('saved submission original graph/client/history binding differs')
    _require_saved_history(entry,saved,graph,prompt_id=proof['prompt_id'])
    config=load_config(Path(snapshot['config_snapshot']['path']))
    verified=_native_saved_validation(config,origin,stage,proof['unit_id'],saved,entry,graph)
    expected=thaw(verified.record);actual=thaw(proof['native_record'])
    for value in (expected,actual):value.pop('evidence_identities',None);value.pop('checkpoint_identity',None)
    if stage=='source_clips':actual.pop('source_identity',None)
    # Attempt evidence references bind real origins and may include later
    # child trim logs; all those leaves are separately freshly protected.
    for value in (expected,actual):
        for attempt in value.get('attempts',()):attempt.pop('evidence_identities',None)
    if _without_verification(expected)!=_without_verification(actual):raise ValueError('saved native record differs from fresh full parameter/media replay')
    if row['signature']!=_proof_signature(stage,proof['native_record'],graph):raise ValueError('saved origin semantic signature differs')
    _verify_processing(proof);imports.fresh(identity)
    result=thaw(proof['native_record'])
    if stage=='upscale':result['checkpoint_identity']=thaw(identity)
    return result


def reconciled_image_context(parent, rows):
    """Native settings/reference context for an incomplete original image stage."""
    from . import start_image_checks as owner
    parent=_run_path(parent);snapshot=ManifestStore.open(parent).snapshot()
    config=load_config(Path(snapshot['config_snapshot']['path']));board,_=owner._input_files(config,parent)
    images={row['id']:consume_reconciled_unit(parent,row) for row in rows if row['origin']=='completed_saved_submission'}
    user={};mapping_path=parent/'logs/start-images/input-map.json'
    if mapping_path.is_file():
        mapping=read_json(mapping_path)
        for eid,path in mapping.get('entities',{}).items():
            identity=thaw(hash_file(Path(path)));user[eid]=(identity,identity)
    references=owner._references(board,images,user)
    return dict(effective_image_settings=dict(width=config.media.profile.width,height=config.media.profile.height,
        aspect_ratio='16:9',adaptation='contain_black_pad'),references=references,global_visual=board['global_visual'])


def derive_reconciled_run(config, *, parent_run_dir, plan, reconciliations):
    """Create one new child from every saved request in the affected stage.

    Remaining submitted siblings must have an explicit completed reconciliation;
    completed native siblings replay their original same-ID history. An unknown
    request can never disappear into a child's remaining POST list.
    """
    parent=_run_path(parent_run_dir);snapshot=ManifestStore.open(parent).snapshot()
    responses=tuple(reconciliations)
    if not responses or any(not isinstance(r,Reconciliation) or r.state!='completed' for r in responses):
        raise ValueError('saved import requires completed immutable reconciliations')
    stages={r.stage for r in responses}
    if len(stages)!=1:raise ValueError('saved import must advance one dependent stage at a time')
    stage=next(iter(stages));kind={'start_images':'image','source_clips':'shot_attempt','upscale':'frame'}[stage]
    response_by_uid={r.unit_id:r for r in responses}
    if len(response_by_uid)!=len(responses):raise ValueError('duplicate reconciliation unit')
    original_config=load_config(Path(snapshot['config_snapshot']['path']))
    child_kind={'start_images':'image','source_clips':'shot','upscale':'frame'}[stage]
    prior_receipt=imports.load_pipeline_import(parent) if 'pipeline_import' in snapshot['workflows'] else None
    prior_rows={row['id']:row for row in prior_receipt['units'] if row['imported_record'].get('stage')==stage} if prior_receipt else {}
    inherited=[];ordinary={}
    for uid,row in prior_rows.items():
        unit=snapshot['units'].get(child_kind,{}).get(uid)
        if unit is None or unit['status']!='completed' or unit['submission'] is not None:
            raise ValueError('existing imported unit must retain completed child copy and no submission')
        if row['origin']=='completed_saved_submission':record=consume_reconciled_unit(parent,row)
        else:
            ordinary[uid]=dict(origin_run_id=row['imported_record']['origin_run_id'],source_report_identity=row['imported_record']['source_report_identity'],
                source_unit_id=row['imported_record']['source_unit_id'],signature=row['signature'],import_identity=snapshot['workflows']['pipeline_import'])
            record=None
        inherited.append((uid,row,unit,record))
    if ordinary:
        if stage=='start_images':
            from . import start_image_checks as owner
            board,_=owner._input_files(original_config,parent)
            reused={uid:dict(origin_run_id=row['imported_record']['origin_run_id'],source_report_identity=row['imported_record']['source_report_identity'],
                source_unit_id=row['imported_record']['source_unit_id'],signature=row['signature'],import_identity=snapshot['workflows']['pipeline_import']) for uid,row in prior_rows.items()}
            records,_=owner._verified_reused_images(original_config,parent,board,snapshot,snapshot['workflows']['pipeline_import'],reused)
        elif stage=='source_clips':
            from ._source_clip_inputs import inputs
            records=imports.reused_source_clips(parent,ordinary,inputs(original_config,parent))
        else:
            from ._upscale_inputs import inputs
            records=imports.reused_upscale_frames(original_config,parent,ordinary,inputs(original_config,parent))
        if stage=='start_images':
            # The new saved-stage serializer binds each ordinary row directly
            # to its actual reviewed native origin, retaining its old receipt
            # and all intermediate copy leaves through the flattened closure.
            for uid,row in prior_rows.items():
                if row['origin']=='reused_verified':
                    origin=_run_path(parent.parent/row['imported_record']['origin_run_id'])
                    report=owner.load_committed_start_images(origin)
                    if not imports.same_identity(hash_file(origin/'images.json'),row['imported_record']['source_report_identity']):
                        raise ValueError('nested original reviewed image report differs')
                    records[uid]=next(image for image in report['images'] if image['shot_id']==row['imported_record']['source_unit_id'])
        inherited=[(uid,row,unit,records[uid] if record is None else record) for uid,row,unit,record in inherited]
    native={}
    for uid,unit in snapshot['units'].get(kind,{}).items():
        saved=unit['submission']
        if saved is None:
            if unit['status']=='completed' and uid not in prior_rows:raise ValueError('completed submission-free unit lacks its consumed import origin')
            continue
        native[uid]=(unit,saved)
    if stage=='source_clips':
        selected={}
        for uid,(unit,saved) in native.items():
            shot,attempt=uid.split(':');ordinal=int(attempt.split('_')[1])
            if shot not in selected or ordinal>selected[shot][0]:selected[shot]=(ordinal,uid)
        native={uid:native[uid] for _,uid in selected.values()}
    if set(response_by_uid)-set(native):raise ValueError('reconciliation unit differs from immutable original submissions')
    prepared=[]
    for uid,(unit,saved) in native.items():
        graph_id=snapshot['workflows'][saved['attempt_id']];imports.fresh(graph_id);graph=read_json(Path(graph_id['path']))
        response=response_by_uid.get(uid)
        if response is None:
            if saved['state']!='completed' or not saved['response_path']:raise ValueError('submitted sibling is still unknown; no child POST admission')
            history_id=hash_file(Path(saved['response_path']));history=read_json(Path(history_id.path));entry=history[saved['prompt_id']]
        else:
            for identity in (*response.evidence_identities,*response.output_identities):imports.fresh(identity)
            if response.attempt_id!=saved['attempt_id']:raise ValueError('saved reconciliation attempt differs')
            history_id,entry=_successful_history(response,saved,graph)
        verified=_native_saved_validation(original_config,parent,stage,uid,saved,entry,graph)
        if response is not None and any(not _same_identity(a,b) for a,b in zip(verified.output_identities,response.output_identities)):
            raise ValueError('saved reconciliation output changed before child derivation')
        prepared.append((uid,unit,saved,graph_id,history_id,entry,verified,response))
    # Recheck local admission and persist the original invocation options before
    # allocating an independently resumable child. No model/service operations.
    from ..pipeline import _options
    from .preflight import preflight
    options,option_ids=_options(parent)
    script=imports.fresh(snapshot['inputs']['script'])
    if options.get('script') is not None and options['script']!=Path(script.path):
        raise ValueError('saved child original script/options differ')
    preflight_result=preflight(config,script=Path(script.path),output=options.get('output_path'))
    if not preflight_result.passed:raise ValueError('saved child fresh preflight failed')
    if 'unit_review_identity' in option_ids:
        from .pipeline_reviews import load_unit_review
        load_unit_review(Path(option_ids['unit_review_identity'].path),script_path=Path(script.path))
    child_inputs=dict(snapshot['inputs'],script=thaw(script),config=thaw(hash_file(config.config_file)),voice=thaw(hash_file(config.voice.config_file)))
    admission_ids={}
    for value in (*child_inputs.values(),*option_ids.values(),*getattr(plan,'input_identities',{}).values()):
        value=thaw(value)
        if Path(value['path'])==parent/'manifest.json':continue
        current=imports.fresh(value);admission_ids[current.path]=thaw(current)
    if ManifestStore.open(parent).snapshot()!=snapshot:raise ValueError('parent changed during saved child admission')
    run=create_run(RuntimePaths.from_config(config))
    try:
        return _write_saved_child(config,run,parent,snapshot,plan,stage,kind,prior_receipt,inherited,prepared,
            child_inputs,preflight_result,options,option_ids,admission_ids)
    except BaseException as exc:
        # Preserve the independent partial child and the original exception.
        # Diagnostic failures cannot replace the real derivation failure.
        try:
            logger=RunLogger(run);trace=logger.exception('pipeline',None,exc)
            logger.save_json('pipeline/child-derivation-failure-'+uuid4().hex+'.json',dict(schema_version=1,
                run_id=run.name,parent_run_id=parent.name,stage=stage,error_type=type(exc).__name__,message=str(exc),
                traceback_path=str(trace),recorded_at=now()))
        except BaseException:pass
        raise


def _write_saved_child(config,run,parent,snapshot,plan,stage,kind,prior_receipt,inherited,prepared,
        child_inputs,preflight_result,options,option_ids,admission_ids):
    child_kind={'start_images':'image','source_clips':'shot','upscale':'frame'}[stage]
    store=create_manifest(run,config,inputs=child_inputs,models=snapshot['models'],workflows={})
    preflight_id=imports.write_exclusive(run,run/'logs/pipeline/preflight.json',preflight_result.as_dict())
    store.record_stage('preflight','running');store.record_stage('preflight','completed',artifacts=[_artifact(preflight_id)])
    copied_review=imports.copy_exclusive(run,option_ids['unit_review_identity'],run/'logs/pipeline/unit-review.json') if 'unit_review_identity' in option_ids else None
    image_inputs=None
    if 'image_inputs_identity' in option_ids:
        old=imports.fresh(option_ids['image_inputs_identity']);mapping=read_json(Path(old.path))
        imports.keys(mapping,'schema_version run_id shots entities','image input map')
        image_inputs=imports.write_exclusive(run,run/'logs/pipeline/image-inputs.json',dict(mapping,run_id=run.name))
    settings=option_ids.get('settings_identity')
    imports.write_exclusive(run,run/'logs/pipeline/pipeline-options.json',dict(schema_version=1,run_id=run.name,created_at=now(),
        input_identities=child_inputs,unit_review_identity=thaw(copied_review),image_inputs_identity=thaw(image_inputs),
        settings_identity=thaw(settings),output_path=options.get('output_path'),cpu_planner=options.get('cpu_planner',False),
        execution_policy=dict(gpu_management='disabled',total_timeout_seconds=None,media_command_timeout_seconds=300)))
    sources={};imports.merge_sources(sources,admission_ids)
    copies=[];stage_rows=[];unit_rows=[];reports={};targets=set()
    complete=tuple(r.stage for r in plan.reused if r.unit_id is None and r.stage in imports.STAGE_FILES
                   and STAGES.index(r.stage)<STAGES.index(stage))

    def copy_request(original,target,role,copy_stage,uid):
        if target in targets:return
        targets.add(target);copies.append(dict(original_identity=thaw(original),copy_path=target,role=role,stage=copy_stage,unit_id=uid))

    for completed in complete:
        report=imports.stage_consumer(completed)(parent);reports[completed]=report
        if completed=='speech':
            from .speech_checks import speech_import_inventory
            inventory=speech_import_inventory(parent,run);imports.merge_sources(sources,inventory['source_identities'])
            copies.extend(inventory['copies']);targets.update(r['copy_path'] for r in inventory['copies'])
            stage_rows.append(inventory['stage']);unit_rows.extend(inventory['units']);continue
        source_id=hash_file(parent/imports.STAGE_FILES[completed]);imports.merge_sources(sources,imports.collect_report_sources(report,parent))
        sources[source_id.path]=thaw(source_id)
        stage_rows.append(dict(id=completed,source_record=snapshot['stages'][completed],
            imported_record=dict(source_report_identity=thaw(source_id)),signature=imports.content_signature(report),origin='reused_verified'))
        for uid in imports.stage_unit_ids(completed,report):
            unit_kind={'start_images':'image','source_clips':'shot','upscale':'frame'}.get(completed)
            source_record=snapshot['units'][unit_kind][uid] if unit_kind else next(s for s in report['shots'] if s['shot_id']==uid)
            old=report.get('reused_units',{}).get(uid)
            unit_rows.append(dict(id=uid,source_record=source_record,imported_record=dict(stage=completed,
                origin_run_id=old['origin_run_id'] if old else parent.name,
                source_report_identity=old['source_report_identity'] if old else thaw(source_id),
                source_unit_id=old['source_unit_id'] if old else uid),signature=old['signature'] if old else imports.content_signature(source_record),origin='reused_verified'))
        for uid,role,original in imports.stage_media(completed,report):
            if role=='start_image':relative=Path('shots')/uid/'start.png'
            elif role in ('generated_identity','source_identity','upscaled_clip'):
                relative=Path('shots')/uid/{'generated_identity':'generated.mp4','source_identity':'source.mp4','upscaled_clip':'upscaled.mp4'}[role]
            else:
                shot,frame=uid.split(':');relative=Path('shots')/shot/('frames' if role=='input_identity' else 'upscaled-frames')/(frame+'.png')
            copy_request(original,run/relative,role,completed,uid)

    for uid,row,unit,record in inherited:
        meta=thaw(row['imported_record'])
        if row['origin']=='completed_saved_submission':meta.update(parent_kind=child_kind,parent_unit_id=uid)
        unit_rows.append(dict(id=uid,source_record=unit,imported_record=meta,signature=row['signature'],origin=row['origin']))
        if stage=='start_images':
            copy_request(record['image_identity'],run/'shots'/uid/'start.png','start_image',stage,uid)
        elif stage=='source_clips':
            for role,filename in (('generated_identity','generated.mp4'),('source_identity','source.mp4')):
                copy_request(record[role],run/'shots'/uid/filename,role,stage,uid)
        else:
            shot,frame=uid.split(':')
            copy_request(record['upscaled_frame_identity'],run/'shots'/shot/'upscaled-frames'/(frame+'.png'),'upscaled_frame_identity',stage,uid)
    if stage=='upscale' and prior_receipt is not None:
        inherited_shots={uid.split(':')[0] for uid,_,_,_ in inherited}
        for copied in prior_receipt['copies']:
            if copied['stage']==stage and copied['role']=='upscaled_clip' and copied['unit_id'] in inherited_shots:
                original=imports.fresh(copied['copy_identity'])
                copy_request(original,run/'shots'/copied['unit_id']/'upscaled.mp4','upscaled_clip',stage,copied['unit_id'])

    for uid,unit,saved,graph_id,history_id,entry,verified,response in prepared:
        record=thaw(verified.record);processing={}
        raw_sources={identity.path:thaw(identity) for identity in verified.evidence_identities}
        if response is not None:
            raw_sources.update({identity.path:thaw(identity) for identity in response.evidence_identities})
        raw_sources[history_id.path]=thaw(history_id);raw_sources[graph_id['path']]=thaw(graph_id)
        reuse_id=record['shot_id'] if stage!='upscale' else uid
        if stage=='source_clips':
            from ..media.video import trim_video
            folder=run/'logs/pipeline'/('saved-media-'+uuid4().hex)
            generated=imports.copy_exclusive(run,record['generated_identity'],folder/'generated.mp4')
            target,logs=trim_video(Path(generated.path),folder/'source.mp4',frames=record['source_frames'],
                width=record['width'],height=record['height'],config=config,paths=RuntimePaths.from_config(config),
                logger=RunLogger(run),unit_id=reuse_id,timeout=300)
            record['source_identity']=target['identity']
            for path in [Path(generated.path),Path(target['identity']['path']),*logs]:
                identity=hash_file(path);processing[identity.path]=thaw(identity);raw_sources[identity.path]=thaw(identity)
            copy_request(record['generated_identity'],run/'shots'/reuse_id/'generated.mp4','generated_identity',stage,reuse_id)
            copy_request(record['source_identity'],run/'shots'/reuse_id/'source.mp4','source_identity',stage,reuse_id)
        elif stage=='start_images':
            copy_request(record['image_identity'],run/'shots'/reuse_id/'start.png','start_image',stage,reuse_id)
        else:
            shot,frame=uid.split(':')
            copy_request(record['upscaled_frame_identity'],run/'shots'/shot/'upscaled-frames'/(frame+'.png'),'upscaled_frame_identity',stage,uid)
        proof=dict(schema_version=1,parent_run_id=parent.name,stage=stage,unit_id=uid,attempt_id=saved['attempt_id'],
            prompt_id=entry['prompt'][1],source_record=unit,graph_identity=thaw(graph_id),history_identity=thaw(history_id),
            source_identities=raw_sources,native_record=record,processing_identities=processing,created_at=now())
        proof_id=imports.write_exclusive(parent,parent/'logs/pipeline'/('reconciled-'+uuid4().hex+'.json'),proof)
        raw_sources[proof_id.path]=thaw(proof_id);imports.merge_sources(sources,raw_sources)
        unit_rows.append(dict(id=reuse_id,source_record=unit,imported_record=dict(stage=stage,source_kind=kind,
            origin_run_id=parent.name,source_report_identity=thaw(proof_id),source_unit_id=uid),
            signature=_proof_signature(stage,record,read_json(Path(graph_id['path']))),origin='completed_saved_submission'))
    stage_rows.append(dict(id=stage,source_record=snapshot['stages'][stage],imported_record=dict(partial=True),
        signature=signature([row['signature'] for row in unit_rows if row['imported_record'].get('stage')==stage]),origin='completed_saved_submission'))
    if ManifestStore.open(parent).snapshot()!=snapshot:raise ValueError('parent changed while deriving saved submissions')
    import_id=imports.create_pipeline_import(config,run_dir=run,parent_run_dir=parent,reason='Explicit resume of fully revalidated saved submissions',
        source_identities=sources,copies=copies,stages=stage_rows,units=unit_rows)
    receipt=imports.load_pipeline_import(run)
    for completed,origin in reports.items():
        report=imports.serialize_stage_import(completed,origin,run=run,import_identity=import_id,receipt=receipt)
        report_id=imports.write_exclusive(run,run/imports.STAGE_FILES[completed],report);store.record_stage(completed,'running')
        unit_kind={'speech':'speech','start_images':'image','source_clips':'shot','upscale':'frame'}.get(completed)
        if unit_kind:
            for uid in report['reused_units']:
                artifacts=[_artifact(report_id)]+[_artifact(imports.fresh(row['copy_identity'])) for row in receipt['copies'] if row['stage']==completed and row['unit_id']==uid]
                store.record_unit(unit_kind,uid,'running');store.record_unit(unit_kind,uid,'completed',artifacts=artifacts)
        store.update(lambda data,s=completed,i=report_id:data['workflows'].update({imports.STAGE_WORKFLOWS[s]:thaw(i)}))
        store.record_stage(completed,'completed',artifacts=[_artifact(report_id)])
        imports.stage_consumer(completed)(run)
        if completed=='speech' and snapshot['stages']['timeline']['status']=='completed':
            from .timeline_checks import plan_timeline
            result=plan_timeline(config,run_dir=run)
            if not result.passed:raise ValueError('saved child native timeline reconstruction failed')
    for row in receipt['units']:
        if row['imported_record'].get('stage')==stage:
            uid=row['id'];child_kind={'start_images':'image','source_clips':'shot','upscale':'frame'}[stage]
            artifacts=[_artifact(imports.fresh(copy['copy_identity'])) for copy in receipt['copies'] if copy['stage']==stage and copy['unit_id']==uid]
            store.record_unit(child_kind,uid,'running');store.record_unit(child_kind,uid,'completed',artifacts=artifacts)
    imports.load_pipeline_import(run)
    return run
