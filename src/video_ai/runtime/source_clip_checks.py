"""Exclusive source preparation, continuous-video review commit and fresh consume."""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
from uuid import uuid4

from ..adapters.common import AdapterError,FailureKind
from ..config import ProjectConfig,load_config,read_json
from ..planning.source_clips import frame_mapping,requirement_clips
from .logging import RunLogger
from .manifest import ManifestStore,hash_file,now,thaw
from .timeline_checks import _run_path,_local,_again,_artifact,_fresh as artifact_fresh
from ._source_clip_inputs import inputs,fresh,same,MODEL_NAMES
from ._source_clip_generation import generate
from ._source_clip_evidence import validate,validation
from ._source_clip_review import review,ReviewIncomplete


class SourceClipRefusal(ValueError):
    """Illegal invocation or pre-run state; preserve pending and never post."""


@dataclass(frozen=True)
class SourceClipsResult:
    passed: bool
    run_dir: Path
    draft_path: Path
    clips_path: Path
    clip_count: int
    ready_for_upscale: bool
    status: str


def result(run,status,count=0):
    completed=status=='completed'
    return SourceClipsResult(completed,run,run/'source-clips-draft.json',run/'source-clips.json',count,completed,status)


def run_path(path):
    try:return _run_path(path)
    except (ValueError,OSError,TypeError) as exc:raise SourceClipRefusal(str(exc)) from exc


def entry_store(run):
    try:return ManifestStore.open(run)
    except (ValueError,OSError,TypeError) as exc:raise SourceClipRefusal(str(exc)) from exc


def entry_snapshot(store):
    try:return store.snapshot()
    except (ValueError,OSError,TypeError) as exc:raise SourceClipRefusal(str(exc)) from exc


@contextmanager
def exclusive(run):
    owner=dict(pid=os.getpid(),token=uuid4().hex)
    try:
        path=_local(run,run/'.source-clips.lock')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError as exc:raise SourceClipRefusal('existing source clip lock; no takeover') from exc
    except (ValueError,OSError,TypeError) as exc:raise SourceClipRefusal(str(exc)) from exc
    try:
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(owner,f);f.flush();os.fsync(f.fileno())
        except (ValueError,OSError,TypeError) as exc:raise SourceClipRefusal(str(exc)) from exc
        yield owner
    finally:
        try:
            if read_json(path)==owner:path.unlink()
        except (OSError,ValueError):pass
        except KeyboardInterrupt:
            if ManifestStore.open(run).snapshot()['stages']['source_clips']['status']!='completed':raise


def check_lock(run,owner):
    if read_json(_local(run,run/'.source-clips.lock'))!=owner:raise OSError('source clip lock owner replaced; retained')


def review_path(run,path):
    try:
        actual=_local(run,Path(path).absolute())
        if actual!=run/'logs/source-clips/semantic-review.json':raise ValueError('review must be canonical logs/source-clips/semantic-review.json')
        return actual
    except (ValueError,OSError,TypeError) as exc:raise SourceClipRefusal(str(exc)) from exc


def atomic_report(run,path,data):
    """Publish complete fsynced bytes exclusively, without replacing an orphan."""
    path=_local(run,path);temporary=_local(run,path.with_name(path.name+'.'+uuid4().hex+'.tmp'))
    with temporary.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(thaw(data),f,ensure_ascii=False,allow_nan=False,indent=2);f.flush();os.fsync(f.fileno())
    # Linking an already fsynced file atomically refuses any existing destination.
    os.link(temporary,path)
    temporary.unlink()
    if not same(read_json(path),data):raise OSError('source report readback differs')


def state_unchanged(current,snapshot,source=True):
    stages=('speech','timeline','storyboard','start_images')+(('source_clips',) if source else ())
    for stage in stages:
        if current['stages'][stage]!=snapshot['stages'][stage]:raise OSError(f'{stage} changed during source transaction')
    groups=('speech','image')+(('shot','shot_attempt') if source else ())
    for kind in groups:
        if current['units'].get(kind,{})!=snapshot['units'].get(kind,{}):raise OSError(f'{kind} units changed during source transaction')


def unchanged(store,snapshot,ids,run,owner,source=True):
    check_lock(run,owner);_again(ids);state_unchanged(store.snapshot(),snapshot,source)


def failure(run,store,logger,exc,count):
    snap=store.snapshot()
    if snap['stages']['source_clips']['status']=='completed':return result(run,'completed',count)
    status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'ambiguous' if isinstance(exc,AdapterError) and exc.kind==FailureKind.ambiguous else 'failed'
    paths=[]
    try:paths.append(logger.exception('source_clips',None,exc))
    except (OSError,ValueError,KeyboardInterrupt):pass
    error=dict(kind=status,message=str(exc),traceback_path=str(paths[0]) if paths else None,evidence_paths=[str(p) for p in paths])
    if isinstance(exc,AdapterError):error['evidence_paths'] += [str(p) for p in exc.evidence_paths]
    try:
        def fail(data):
            stage=data['stages']['source_clips']
            if stage['status']=='running':store._record_status(data,stage,status,stage['artifacts'],error,'source_clips',None)
            for kind in ('shot','shot_attempt'):
                for uid,unit in data['units'].get(kind,{}).items():
                    if unit['status']=='running':store._record_status(data,unit,status,unit['artifacts'],error,'source_clips',uid)
        store.update(fail)
    except (OSError,ValueError,KeyboardInterrupt):pass
    if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise exc
    return result(run,'failed',count)


def prepare_source_clips(config:ProjectConfig, *, run_dir:Path)->SourceClipsResult:
    run=run_path(run_dir);store=entry_store(run)
    with exclusive(run) as owner:
        snapshot=entry_snapshot(store)
        if snapshot['stages']['source_clips']['status']!='pending' or any((run/p).exists() for p in ('source-clips-draft.json','source-clips.json')) or snapshot['units']['shot'] or snapshot['units'].get('shot_attempt') or 'source_clips_report' in snapshot['workflows']:
            raise SourceClipRefusal('source stage already started or orphan report/unit exists')
        try:
            from ._pipeline_model_paths import prepare_or_consume_model_binding
            prepare_or_consume_model_binding(config,run,'wan',create=True)
            context=inputs(config,run)
            for name in ('input','output','temp','user'):_local(run,run/'comfy'/name)
            for plan in context['plans']:
                uid=plan.shot_id
                targets=[run/'shots'/uid/name for name in ('generated.mp4','source.mp4')]+[run/'comfy/input'/run.name/'source_clips'/uid/'start.png',run/'logs/source-clips'/f'clip-{uid}.json']
                for target in targets:
                    target=_local(run,target)
                    if target.exists() or target.is_symlink():raise ValueError('orphan source clip target; no overwrite')
            output=_local(run,run/'comfy/output'/run.name/'source_clips')
            if output.exists() and any(output.rglob('*.mp4')):raise ValueError('orphan generated MP4; no overwrite')
            unchanged(store,snapshot,context['identities'],run,owner)
        except (ValueError,OSError,KeyError,TypeError) as exc:raise SourceClipRefusal(str(exc)) from exc
        logger=RunLogger(run);clips=[];records={}
        try:
            def begin(data):
                state_unchanged(data,snapshot)
                store._record_status(data,data['stages']['source_clips'],'running',[],None,'source_clips',None)
            store.update(begin)
            generate(config,run,store,logger,context,records,clips)
            mappings={c['shot_id']:frame_mapping(p,generated_identity=c['generated_identity'],source_identity=c['source_identity'],generated_frames=c['generated_frames'],output_fps=context['board']['effective_media']['fps']) for p,c in zip(context['plans'],clips)}
            draft=dict(schema_version=1,run_id=run.name,created_at=now(),status='review_required',passed=False,
                **{k+'_identity':thaw(context['identities'][k]) for k in ('images','storyboard','timeline')},
                effective_media=context['board']['effective_media'],clips=clips,
                requirement_clips=requirement_clips(context['board'],source_identities={c['shot_id']:c['source_identity'] for c in clips},frame_mappings=mappings,total_samples=context['timeline']['total_samples']),
                frame_mappings=list(mappings.values()),model_identities={n:thaw(context['identities'][n]) for n in MODEL_NAMES},
                workflow_identity=thaw(context['identities']['workflow']),mapping_identity=thaw(context['identities']['mapping']),
                provenance=context['provenance'],validation=validation(False),request_evidence=records)
            state_unchanged(store.snapshot(),snapshot,source=False)
            ready_snapshot=store.snapshot();ids=validate(config,run,draft,context,ready_snapshot)
            unchanged(store,ready_snapshot,ids,run,owner)
            atomic_report(run,run/'source-clips-draft.json',draft);draft_id=hash_file(run/'source-clips-draft.json')
            unchanged(store,ready_snapshot,ids,run,owner)
            store.record_stage('source_clips','running',artifacts=[_artifact(draft_id)])
            return result(run,'review_required',len(clips))
        except BaseException as exc:return failure(run,store,logger,exc,len(clips))


def resume_source_clips(config:ProjectConfig, *, run_dir:Path,reuse_context)->SourceClipsResult:
    """Continue a new child after strict origin consumption; never reset parent."""
    from .pipeline_import import verify_reuse_context,reused_source_clips
    run=run_path(run_dir);store=entry_store(run)
    with exclusive(run) as owner:
        snapshot=entry_snapshot(store)
        try:
            if snapshot['stages']['source_clips']['status']!='pending' or any((run/p).exists() for p in ('source-clips-draft.json','source-clips.json')) or snapshot['units'].get('shot_attempt'):
                raise ValueError('partial resume requires fresh pending child with no native attempt')
            from ._pipeline_model_paths import prepare_or_consume_model_binding
            prepare_or_consume_model_binding(config,run,'wan',create=True)
            context=inputs(config,run)
            reuse=verify_reuse_context(run,reuse_context,stage='source_clips',unit_ids=tuple(p.shot_id for p in context['plans']),current_input_identities=context['identities'])
            reused=reused_source_clips(run,reuse.verified_units,context)
            if set(snapshot['units']['shot'])!=set(reused):raise ValueError('child source units differ from consumed reuse context')
            for plan in context['plans']:
                if plan.shot_id in reused:continue
                for name in ('generated.mp4','source.mp4'):
                    if _local(run,run/'shots'/plan.shot_id/name).exists():raise ValueError('orphan remaining source target')
            unchanged(store,snapshot,context['identities'],run,owner)
        except (ValueError,OSError,KeyError,TypeError) as exc:raise SourceClipRefusal(str(exc)) from exc
        logger=RunLogger(run);clips=[];records={}
        try:
            store.record_stage('source_clips','running')
            remaining=dict(context,plans=tuple(p for p in context['plans'] if p.shot_id in reuse.remaining_units))
            if remaining['plans']:generate(config,run,store,logger,remaining,records,clips)
            by_id={**reused,**{c['shot_id']:c for c in clips}};clips=[by_id[p.shot_id] for p in context['plans']]
            mappings={c['shot_id']:frame_mapping(p,generated_identity=c['generated_identity'],source_identity=c['source_identity'],generated_frames=c['generated_frames'],output_fps=context['board']['effective_media']['fps']) for p,c in zip(context['plans'],clips)}
            draft=dict(schema_version=2,run_id=run.name,created_at=now(),status='review_required',passed=False,
                **{k+'_identity':thaw(context['identities'][k]) for k in ('images','storyboard','timeline')},
                effective_media=context['board']['effective_media'],clips=clips,
                requirement_clips=requirement_clips(context['board'],source_identities={c['shot_id']:c['source_identity'] for c in clips},frame_mappings=mappings,total_samples=context['timeline']['total_samples']),
                frame_mappings=list(mappings.values()),model_identities={n:thaw(context['identities'][n]) for n in MODEL_NAMES},
                workflow_identity=thaw(context['identities']['workflow']),mapping_identity=thaw(context['identities']['mapping']),
                provenance=context['provenance'],validation=validation(False),request_evidence=records,
                import_identity=thaw(reuse.import_identity),reused_units=thaw(reuse.verified_units))
            current=store.snapshot();ids=validate(config,run,draft,context,current)
            unchanged(store,current,ids,run,owner);atomic_report(run,run/'source-clips-draft.json',draft)
            draft_id=hash_file(run/'source-clips-draft.json');unchanged(store,current,ids,run,owner)
            store.record_stage('source_clips','running',artifacts=[_artifact(draft_id)])
            return result(run,'review_required',len(clips))
        except BaseException as exc:return failure(run,store,logger,exc,len(clips))


def finalize_source_clips(config:ProjectConfig, *, run_dir:Path,review_path:Path)->SourceClipsResult:
    run=run_path(run_dir);path=globals()['review_path'](run,review_path);store=entry_store(run)
    with exclusive(run) as owner:
        snapshot=entry_snapshot(store);stage=snapshot['stages']['source_clips'];draft_path=run/'source-clips-draft.json'
        if stage['status']!='running' or not draft_path.is_file() or (run/'source-clips.json').exists() or 'source_clips_report' in snapshot['workflows']:raise SourceClipRefusal('running source draft required; no terminal/orphan overwrite')
        logger=RunLogger(run);count=0
        try:
            draft=read_json(draft_path);count=len(draft.get('clips',[]))
            artifacts=[a for a in stage['artifacts'] if Path(a['path'])==draft_path]
            if len(artifacts)!=1:raise ValueError('source draft not registered exactly once')
            draft_id=artifact_fresh(artifacts[0],run=run,expected=draft_path)
            context=inputs(config,run);ids=validate(config,run,draft,context,snapshot);ids['draft']=draft_id
            review_ids,review_method=review(run,path,draft,draft_id);ids.update(review_ids)
            report=dict(draft,status='completed',passed=True,validation=validation(True,review_method=review_method),review_identity=thaw(ids['review']))
            unchanged(store,snapshot,ids,run,owner)
            atomic_report(run,run/'source-clips.json',report);report_id=hash_file(run/'source-clips.json')
            unchanged(store,snapshot,ids,run,owner);_again({'report':report_id})
            def commit(data):
                state_unchanged(data,snapshot)
                if 'source_clips_report' in data['workflows']:raise ValueError('orphan formal source report receipt')
                data['workflows']['source_clips_report']=thaw(report_id)
                for clip in draft['clips']:
                    uid=clip['shot_id']
                    if uid in draft.get('reused_units',{}):continue
                    store._record_status(data,data['units']['shot'][uid],'completed',[_artifact(report_id),_artifact(fresh(clip['source_identity'],run=run)),_artifact(ids['review'])],None,'source_clips',uid)
                store._record_status(data,data['stages']['source_clips'],'completed',[_artifact(report_id)],None,'source_clips',None)
            store.update(commit)
            return result(run,'completed',count)
        except ReviewIncomplete as exc:
            try:logger.exception('source_clips',None,exc)
            except (OSError,ValueError):pass
            return result(run,'review_required',count)
        except BaseException as exc:return failure(run,store,logger,exc,count)


from .verification import verified_read


@verified_read
def load_committed_source_clips(run_dir:Path)->dict:
    run=run_path(run_dir);store=ManifestStore.open(run);snapshot=store.snapshot();stage=snapshot['stages']['source_clips']
    if (run/'source-clips.json').is_file() and read_json(run/'source-clips.json').get('schema_version')==2 and not (run/'source-clips-draft.json').exists():
        from .pipeline_import import load_imported_stage
        return load_imported_stage(run,'source_clips')
    if stage['status']!='completed':raise ValueError('source clips not completed')
    artifacts=stage['artifacts'];report_path=run/'source-clips.json'
    if len(artifacts)!=1 or Path(artifacts[0]['path'])!=report_path:raise ValueError('formal source clip artifact missing/extra')
    identity=artifact_fresh(artifacts[0],run=run,expected=report_path);report=read_json(report_path)
    receipt=snapshot['workflows'].get('source_clips_report')
    if receipt is None:raise ValueError('formal source report freshness receipt missing')
    identity=fresh(receipt,run=run,expected=report_path)
    config=load_config(Path(snapshot['config_snapshot']['path']));context=inputs(config,run)
    draft_id=hash_file(_local(run,run/'source-clips-draft.json'));draft=read_json(Path(draft_id.path))
    ids=validate(config,run,draft,context,snapshot);ids['draft']=draft_id;ids['report']=identity
    path=review_path(run,Path(report['review_identity']['path']));review_id=fresh(report['review_identity'],run=run,expected=path)
    review_ids,review_method=review(run,path,draft,draft_id);ids.update(review_ids)
    if (review_id.sha256,review_id.mtime_ns)!=(ids['review'].sha256,ids['review'].mtime_ns):raise ValueError('committed review drift')
    expected=dict(draft,status='completed',passed=True,validation=validation(True,review_method=review_method),review_identity=report['review_identity'])
    if not same(report,expected):raise ValueError('formal source clips differs from fully reviewed draft')
    for clip in report['clips']:
        if clip['shot_id'] in report.get('reused_units',{}):continue
        unit=snapshot['units']['shot'][clip['shot_id']]
        wanted=[report_path,Path(clip['source_identity']['path']),path]
        if unit['status']!='completed' or [Path(a['path']) for a in unit['artifacts']]!=wanted:raise ValueError('main source clip completed artifacts differ')
        for a in unit['artifacts']:ids['main/'+a['path']]=artifact_fresh(a,run=run)
    _again(ids);_again(context['identities']);state_unchanged(store.snapshot(),snapshot)
    return report
