"""Exclusive upscale preparation, independent video review and formal consumer."""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
from uuid import uuid4

from ..adapters.common import AdapterError,FailureKind
from ..config import ProjectConfig,load_config,read_json
from ..planning.upscale import upscale_frame_mapping
from .logging import RunLogger
from .manifest import ManifestStore,hash_file,now,thaw
from .timeline_checks import _run_path,_local,_again,_artifact,_fresh as artifact_fresh
from ._source_clip_inputs import same
from ._upscale_inputs import inputs,generated_inputs,fresh,required_capacity,shutil
from ._upscale_generation import generate
from ._upscale_evidence import validate,validation,requirements
from ._upscale_review import review,ReviewIncomplete


class UpscaleRefusal(ValueError):
    """Pre-run invocation/state refusal; never submit or replace owned evidence."""


@dataclass(frozen=True)
class UpscaledClipsResult:
    passed: bool
    run_dir: Path
    draft_path: Path
    clips_path: Path
    clip_count: int
    ready_for_composition: bool
    status: str


def result(run,status,count=0):
    completed=status=='completed'
    return UpscaledClipsResult(completed,run,run/'upscaled-clips-draft.json',run/'upscaled-clips.json',count,completed,status)


def entry(path):
    try:
        run=_run_path(path);store=ManifestStore.open(run);return run,store
    except (ValueError,OSError,TypeError) as exc:raise UpscaleRefusal(str(exc)) from exc


@contextmanager
def exclusive(run):
    owner=dict(pid=os.getpid(),token=uuid4().hex)
    try:
        path=_local(run,run/'.upscale.lock');fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except (ValueError,OSError,TypeError) as exc:raise UpscaleRefusal('upscale lock refused: '+str(exc)) from exc
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(owner,f);f.flush();os.fsync(f.fileno())
        yield owner
    finally:
        try:
            if read_json(path)==owner:path.unlink()
        except (OSError,ValueError):pass
        except KeyboardInterrupt:
            if ManifestStore.open(run).snapshot()['stages']['upscale']['status']!='completed':raise


def state_unchanged(current,snapshot,frames=False):
    for stage in ('preflight','speech','timeline','storyboard','start_images','source_clips'):
        if current['stages'][stage]!=snapshot['stages'][stage]:raise OSError('upstream stage changed during upscale: '+stage)
    for kind in ('speech','image','shot','shot_attempt'):
        if current['units'].get(kind,{})!=snapshot['units'].get(kind,{}):raise OSError('source unit changed during upscale: '+kind)
    if frames and (current['units']['frame']!=snapshot['units']['frame'] or current['stages']['upscale']!=snapshot['stages']['upscale']):raise OSError('upscale transaction state changed')


def unchanged(store,snapshot,ids,run,owner):
    if read_json(_local(run,run/'.upscale.lock'))!=owner:raise OSError('upscale lock owner replaced; retained')
    _again(ids);state_unchanged(store.snapshot(),snapshot,frames=True)


def atomic_report(run,path,data):
    path=_local(run,path);temporary=_local(run,path.with_name(path.name+'.'+uuid4().hex+'.tmp'))
    with temporary.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(thaw(data),f,ensure_ascii=False,allow_nan=False,indent=2);f.flush();os.fsync(f.fileno())
    os.link(temporary,path);temporary.unlink()
    if not same(read_json(path),data):raise OSError('upscale report readback differs')


def failure(run,store,logger,exc,count):
    if store.snapshot()['stages']['upscale']['status']=='completed':return result(run,'completed',count)
    status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'ambiguous' if isinstance(exc,AdapterError) and exc.kind==FailureKind.ambiguous else 'failed'
    paths=[]
    try:paths.append(logger.exception('upscale',None,exc))
    except (OSError,ValueError,KeyboardInterrupt):pass
    error=dict(kind=status,message=str(exc),traceback_path=str(paths[0]) if paths else None,evidence_paths=[str(p) for p in paths])
    if isinstance(exc,AdapterError):error['evidence_paths'] += [str(p) for p in exc.evidence_paths]
    try:
        def fail(data):
            stage=data['stages']['upscale']
            if stage['status']=='running':store._record_status(data,stage,status,stage['artifacts'],error,'upscale',None)
            for uid,unit in data['units']['frame'].items():
                if unit['status']=='running':store._record_status(data,unit,status,unit['artifacts'],error,'upscale',uid)
        store.update(fail)
    except (OSError,ValueError,KeyboardInterrupt):pass
    if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise exc
    return result(run,'failed',count)


def prepare_upscaled_clips(config:ProjectConfig, *, run_dir:Path, execution_policy=None, verify_integrity=True)->UpscaledClipsResult:
    if execution_policy not in (None,'pipeline'):raise UpscaleRefusal('unknown upscale execution policy')
    if type(verify_integrity) is not bool:raise UpscaleRefusal('verify_integrity must be a boolean')
    run,store=entry(run_dir)
    with exclusive(run) as owner:
        try:
            snapshot=store.snapshot()
            if snapshot['stages']['upscale']['status']!='pending' or snapshot['units']['frame'] or 'upscale_report' in snapshot['workflows'] or any((run/p).exists() for p in ('upscaled-clips-draft.json','upscaled-clips.json')):raise ValueError('pending empty upscale stage required; no orphan report/unit')
            from ._pipeline_model_paths import prepare_or_consume_model_binding
            if verify_integrity:prepare_or_consume_model_binding(config,run,'upscale',create=True)
            context=inputs(config,run) if verify_integrity else generated_inputs(config,run)
            if execution_policy=='pipeline':context['no_total_timeout']=True
            logs=_local(run,run/'logs/upscale')
            if logs.exists() and any(p.name.startswith(('frame-','clip-','extract-','encode-')) for p in logs.iterdir()):raise ValueError('orphan upscale checkpoint/media log')
            for plan in context['plans']:
                for name in ('frames','upscaled-frames','upscaled.mp4'):
                    path=_local(run,run/'shots'/plan.shot_id/name)
                    if path.exists() or path.is_symlink():raise ValueError('orphan upscale frame/video target')
            for name in ('input','output','temp','user'):_local(run,run/'comfy'/name)
            for name in ('input','output'):
                path=_local(run,run/'comfy'/name/run.name/'upscale')
                if path.exists():raise ValueError('orphan Comfy upscale namespace')
            if shutil.disk_usage(run).free<required_capacity(context['source']):raise ValueError('insufficient upscale disk capacity')
            if verify_integrity:_again(context['identities'])
            state_unchanged(store.snapshot(),snapshot)
        except (ValueError,OSError,KeyError,TypeError) as exc:raise UpscaleRefusal(str(exc)) from exc
        logger=RunLogger(run);clips=[];records={}
        try:
            def begin(data):
                state_unchanged(data,snapshot);store._record_status(data,data['stages']['upscale'],'running',[],None,'upscale',None)
            store.update(begin)
            if execution_policy=='pipeline':
                from ._upscale_resume import policy
                policy_path=logger.save_json('upscale/execution-policy.json',policy(config));policy_identity=hash_file(policy_path)
                store.update(lambda data:data['workflows'].update(upscale_execution_policy=thaw(policy_identity)))
            generate(config,run,store,logger,context,records,clips)
            if verify_integrity:
                current=inputs(config,run)
                _again(context['identities'])
                if not same(current['source'],context['source']):raise ValueError('fresh source report changed before draft')
            draft=dict(schema_version=1,run_id=run.name,created_at=now(),status='review_required',passed=False,
                source_clips_identity=thaw(context['identities']['source_clips']),source_review_identity=thaw(context['identities']['source_review']),
                source_review_method=context['source_review_method'],source_validation=context['source']['validation'],
                effective_media=context['source']['effective_media'],clips=clips,requirement_clips=requirements(context['source'],clips),
                frame_mappings=[upscale_frame_mapping(m,upscaled_identity=c['upscaled_identity']) for m,c in zip(context['source']['frame_mappings'],clips)],
                model_identity=thaw(context['identities']['model']),workflow_identity=thaw(context['identities']['workflow']),mapping_identity=thaw(context['identities']['mapping']),
                provenance=context['provenance'],validation=validation(False),request_evidence=records)
            if execution_policy=='pipeline':
                from ._upscale_resume import policy
                draft.update(schema_version=3,import_identity=None,reused_units={},execution_policy=policy(config))
            state_unchanged(store.snapshot(),snapshot);ready=store.snapshot()
            ids=validate(config,run,draft,context,ready) if verify_integrity else {}
            if verify_integrity:unchanged(store,ready,ids,run,owner)
            atomic_report(run,run/'upscaled-clips-draft.json',draft)
            draft_id=hash_file(run/'upscaled-clips-draft.json')
            if verify_integrity:
                unchanged(store,ready,ids,run,owner);_again({'draft':draft_id})
            store.record_stage('upscale','running',artifacts=[_artifact(draft_id)])
            return result(run,'review_required',len(clips))
        except BaseException as exc:return failure(run,store,logger,exc,len(clips))


def review_path(run,path):
    try:
        actual=_local(run,Path(path).absolute())
        if actual!=run/'logs/upscale/semantic-review.json':raise ValueError('canonical logs/upscale/semantic-review.json required')
        return actual
    except (ValueError,OSError,TypeError) as exc:raise UpscaleRefusal(str(exc)) from exc


def resume_upscaled_clips(config:ProjectConfig, *, run_dir:Path)->UpscaledClipsResult:
    """Resume a verified unsubmitted prefix once, with no cumulative deadline."""
    from ._upscale_resume import reconstruct,freeze,policy,draft_data,StagedServiceStore
    run,store=entry(run_dir)
    with exclusive(run) as owner:
        try:
            snapshot=store.snapshot()
            if any((run/p).exists() for p in ('upscaled-clips-draft.json','upscaled-clips.json')):raise ValueError('resume forbids an existing draft/formal report')
            context=inputs(config,run)
            reuse,records,clips=reconstruct(config,run,snapshot,context)
            for name in ('input','output','temp','user'):_local(run,run/'comfy'/name)
            if shutil.disk_usage(run).free<required_capacity(context['source']):raise ValueError('insufficient upscale disk capacity')
            _again(context['identities'])
            if store.snapshot()!=snapshot:raise ValueError('resume admission manifest drift')
            reuse['service_store']=StagedServiceStore(store)
        except (ValueError,OSError,KeyError,TypeError) as exc:raise UpscaleRefusal(str(exc)) from exc
        logger=RunLogger(run);committed=False;receipt_id=None
        try:
            def commit_resume():
                nonlocal committed,receipt_id
                if read_json(_local(run,run/'.upscale.lock'))!=owner:raise ValueError('resume lock ownership changed')
                _again(context['identities'])
                # Reconstruct again after owned admission: no persistent path cache.
                reconstruct(config,run,snapshot,context)
                receipt_id=freeze(run,snapshot,records,config,context)
                store.resume_unsubmitted_upscale(receipt_id,expected_snapshot=snapshot,unit_id=reuse['unit_id'])
                committed=True
                reuse['service_store'].activate()
            generate(config,run,store,logger,context,records,clips,resume=reuse,before_generate=commit_resume)
            current=inputs(config,run);_again(context['identities'])
            if not same(current['source'],context['source']):raise ValueError('fresh source changed before resume draft')
            draft=draft_data(run,context,clips,records,execution_policy=dict(policy(config),resume_identity=thaw(receipt_id)))
            state_unchanged(store.snapshot(),snapshot);ready=store.snapshot();ids=validate(config,run,draft,context,ready)
            unchanged(store,ready,ids,run,owner);atomic_report(run,run/'upscaled-clips-draft.json',draft)
            draft_id=hash_file(run/'upscaled-clips-draft.json');unchanged(store,ready,ids,run,owner);_again({'draft':draft_id})
            store.record_stage('upscale','running',artifacts=[_artifact(draft_id)])
            return result(run,'review_required',len(clips))
        except BaseException as exc:
            if not committed:
                if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise
                raise UpscaleRefusal(str(exc)) from exc
            return failure(run,store,logger,exc,len(clips))


def resume_upscale_generation(config:ProjectConfig, *, run_dir:Path,reuse_context)->UpscaledClipsResult:
    """Generate only remaining frames in a fresh imported child."""
    from .pipeline_import import verify_reuse_context,reused_upscale_frames,reused_upscale_clips
    from ._upscale_resume import draft_data,policy
    run,store=entry(run_dir)
    with exclusive(run) as owner:
        snapshot=store.snapshot()
        try:
            if snapshot['stages']['upscale']['status']!='pending' or any((run/p).exists() for p in ('upscaled-clips-draft.json','upscaled-clips.json')):raise ValueError('partial upscale requires fresh pending child')
            from ._pipeline_model_paths import prepare_or_consume_model_binding
            prepare_or_consume_model_binding(config,run,'upscale',create=True)
            context=inputs(config,run)
            unit_ids=tuple(f'{p.shot_id}:frame_{i:06d}' for p in context['plans'] for i in range(1,p.source_frames+1))
            reuse=verify_reuse_context(run,reuse_context,stage='upscale',unit_ids=unit_ids,current_input_identities=context['identities'])
            reused=reused_upscale_frames(config,run,reuse.verified_units,context)
            complete=reused_upscale_clips(config,run,reuse.verified_units,context,reused)
            if set(snapshot['units']['frame'])!=set(reused):raise ValueError('child frame set differs from consumed import')
            for plan in context['plans']:
                if plan.shot_id in complete:continue
                if (run/'shots'/plan.shot_id/'frames').exists() or (run/'shots'/plan.shot_id/'upscaled.mp4').exists():raise ValueError('orphan current extraction/encoding target')
            context.update(no_total_timeout=True,imported_frames=reused)
            _again(context['identities']);state_unchanged(store.snapshot(),snapshot,frames=True)
        except (ValueError,OSError,KeyError,TypeError) as exc:raise UpscaleRefusal(str(exc)) from exc
        logger=RunLogger(run);records={};clips=list(complete.values())
        try:
            store.record_stage('upscale','running')
            remaining=dict(context,plans=tuple(p for p in context['plans'] if p.shot_id not in complete),source=dict(context['source'],clips=[c for c in context['source']['clips'] if c['shot_id'] not in complete]))
            if remaining['plans']:generate(config,run,store,logger,remaining,records,clips)
            by_id={c['shot_id']:c for c in clips};clips=[by_id[p.shot_id] for p in context['plans']]
            draft=draft_data(run,context,clips,records,execution_policy=policy(config))
            draft.update(schema_version=3,import_identity=thaw(reuse.import_identity),reused_units=thaw(reuse.verified_units))
            current=store.snapshot();ids=validate(config,run,draft,context,current)
            unchanged(store,current,ids,run,owner);atomic_report(run,run/'upscaled-clips-draft.json',draft)
            draft_id=hash_file(run/'upscaled-clips-draft.json');unchanged(store,current,ids,run,owner)
            store.record_stage('upscale','running',artifacts=[_artifact(draft_id)])
            return result(run,'review_required',len(clips))
        except BaseException as exc:return failure(run,store,logger,exc,len(clips))


def finalize_upscaled_clips(config:ProjectConfig, *, run_dir:Path,review_path:Path)->UpscaledClipsResult:
    run,store=entry(run_dir);path=globals()['review_path'](run,review_path)
    with exclusive(run) as owner:
        snapshot=store.snapshot();stage=snapshot['stages']['upscale'];draft_path=run/'upscaled-clips-draft.json'
        if stage['status']!='running' or not draft_path.is_file() or (run/'upscaled-clips.json').exists() or 'upscale_report' in snapshot['workflows']:raise UpscaleRefusal('running full upscale draft required; no terminal/orphan overwrite')
        logger=RunLogger(run);count=0
        try:
            draft=read_json(draft_path);count=len(draft.get('clips',[]))
            if len(stage['artifacts'])!=1 or Path(stage['artifacts'][0]['path'])!=draft_path:raise ValueError('upscale draft not registered exactly once')
            draft_id=artifact_fresh(stage['artifacts'][0],run=run,expected=draft_path)
            context=inputs(config,run);ids=validate(config,run,draft,context,snapshot);ids['draft']=draft_id
            review_ids,_=review(run,path,draft,draft_id);ids.update(review_ids)
            report=dict(draft,status='completed',passed=True,validation=validation(True),review_identity=thaw(ids['review']))
            unchanged(store,snapshot,ids,run,owner);atomic_report(run,run/'upscaled-clips.json',report);report_id=hash_file(run/'upscaled-clips.json')
            unchanged(store,snapshot,ids,run,owner);_again({'report':report_id})
            # Reconstruct freshly again after fsynced publication, before the single manifest transaction.
            validate(config,run,draft,context,store.snapshot());review(run,path,draft,draft_id)
            def commit(data):
                state_unchanged(data,snapshot,frames=True)
                if 'upscale_report' in data['workflows']:raise ValueError('orphan upscale formal receipt')
                data['workflows']['upscale_report']=thaw(report_id)
                store._record_status(data,data['stages']['upscale'],'completed',[_artifact(report_id)],None,'upscale',None)
            store.update(commit);return result(run,'completed',count)
        except ReviewIncomplete as exc:
            try:logger.exception('upscale',None,exc)
            except (OSError,ValueError):pass
            return result(run,'review_required',count)
        except BaseException as exc:return failure(run,store,logger,exc,count)


from .verification import verified_read


@verified_read
def load_committed_upscaled_clips(run_dir:Path)->dict:
    run=_run_path(run_dir);store=ManifestStore.open(run);snapshot=store.snapshot();stage=snapshot['stages']['upscale'];report_path=run/'upscaled-clips.json'
    if report_path.is_file() and read_json(report_path).get('schema_version')==3 and read_json(report_path).get('import_identity') is not None and not (run/'upscaled-clips-draft.json').exists():
        from .pipeline_import import load_imported_stage
        return load_imported_stage(run,'upscale')
    if stage['status']!='completed' or len(stage['artifacts'])!=1 or Path(stage['artifacts'][0]['path'])!=report_path:raise ValueError('completed formal upscale stage/artifact required')
    artifact=artifact_fresh(stage['artifacts'][0],run=run,expected=report_path)
    receipt=snapshot['workflows'].get('upscale_report')
    if receipt is None:raise ValueError('formal upscale freshness receipt missing')
    identity=fresh(receipt,run=run,expected=report_path);report=read_json(report_path)
    config=load_config(Path(snapshot['config_snapshot']['path']));context=inputs(config,run)
    draft_id=hash_file(_local(run,run/'upscaled-clips-draft.json'));draft=read_json(Path(draft_id.path))
    ids=validate(config,run,draft,context,snapshot);ids.update(draft=draft_id,report=identity,artifact=artifact)
    path=review_path(run,Path(report['review_identity']['path']));review_id=fresh(report['review_identity'],run=run,expected=path)
    review_ids,_=review(run,path,draft,draft_id);ids.update(review_ids)
    if (review_id.sha256,review_id.mtime_ns)!=(ids['review'].sha256,ids['review'].mtime_ns):raise ValueError('committed upscale review drift')
    if not same(report,dict(draft,status='completed',passed=True,validation=validation(True),review_identity=report['review_identity'])):raise ValueError('formal upscale report differs from independently reviewed draft')
    _again(ids);_again(context['identities']);state_unchanged(store.snapshot(),snapshot,frames=True)
    return report
