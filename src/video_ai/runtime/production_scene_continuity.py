"""Explicit local continuity transactions. No model clients or service managers."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
from time import monotonic
from uuid import uuid4

from ..planning.production_scenes import canonical_digest
from .manifest import now, thaw, hash_file, validate_run_dir
from .production_state import ProductionRefused, RunLock
from ._scene_continuity_io import (Reader, ContinuityStore, SceneContinuityPending,
    artifact, verify, instant, uid, nonempty, local, run_for)
from . import scene_continuity_records as records
from .scene_execution_records import verified_scene_execution_write


def boundary(point):
    """Synchronous durable fault-injection boundary; production does nothing."""


@dataclass(frozen=True)
class SceneContinuityResult:
    schema_version: int = 1
    run_id: str | None = None
    run_dir: Path | None = None
    status: str = 'blocked'
    epoch: dict | None = None
    assessment: dict | None = None
    review_template: dict | None = None
    log_dir: Path | None = None
    error: dict | None = None

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1 or self.status not in (
            'awaiting_analysis','awaiting_review','reviewed','blocked','failed','interrupted'):
            raise ValueError('invalid continuity result')
        if self.run_dir is not None:
            run = validate_run_dir(Path(self.run_dir))
            if self.run_id != run.name: raise ValueError('continuity result run differs')
        elif self.run_id is not None: raise ValueError('continuity result requires known run')

    @property
    def exit_code(self):
        return dict(awaiting_analysis=3,awaiting_review=3,reviewed=0,blocked=2,failed=1,interrupted=130)[self.status]

    def to_dict(self): return thaw(self)


def _result(frozen,status,*,epoch=None,assessment=None,template=None,error=None):
    run=run_for(frozen)
    return SceneContinuityResult(run_id=run.name,run_dir=run,status=status,epoch=epoch,assessment=assessment,
        review_template=template,log_dir=run/'logs/production',error=error)


def _error(exc):
    return dict(kind=type(exc).__name__,message=str(exc) or type(exc).__name__,evidence_paths=[])


def _context(frozen,units,timeline,*,paths=None,lock=None):
    from .scene_clip_records import scene_context,collect_progress
    context=scene_context(frozen,units,timeline,paths=paths,lock=lock)
    _,source=collect_progress(context)
    return context,source


def _clip_ids(context): return [r['budget']['clip_id'] for r in context['rows']]


def _archive_engine(store,relative,capture,reader):
    from ..media._continuity_schema import stable
    existing=store.root/relative/'manifest.json'
    if existing.exists():
        store.owned()
        saved=records._archive(dict(engine_archive=artifact(existing)),dict(engine=capture['engine']),reader)
        if stable(saved['files'])!=stable(capture['files']):
            raise ProductionRefused('complete engine archive differs from installed sources')
        store.owned();return artifact(existing)
    sources=capture['files']; total=sum(s['bytes'] for s in sources)
    if total>536870912: raise ProductionRefused('resource_limit: engine archive exceeds 512MiB')
    if shutil.disk_usage(store.run_dir).free<total+1048576: raise ProductionRefused('insufficient engine archive disk space')
    files=[]
    for index,source in enumerate(sources):
        reader.check(); store.owned()
        path=local(source['path'],runtime=False)
        actual=thaw(hash_file(path))
        if stable(actual)!=stable(source): raise ProductionRefused('engine source changed before copy')
        destination=store.root/relative/'files'/f'{index:06d}.bin'
        if not destination.exists():
            destination.parent.mkdir(parents=True,exist_ok=True)
            temporary=destination.with_name(destination.name+'.'+uuid4().hex+'.tmp')
            with path.open('rb') as src,temporary.open('xb') as dst:
                for chunk in iter(lambda:src.read(1048576),b''):
                    reader.check();store.owned();dst.write(chunk)
                dst.flush();os.fsync(dst.fileno())
            store.owned();os.rename(temporary,destination);store.owned()
        copied=artifact(destination,empty=source['bytes']==0)
        if copied['bytes']!=source['bytes'] or copied['sha256']!=source['sha256'] or stable(thaw(hash_file(path)))!=stable(source):
            raise ProductionRefused('engine copy differs from captured source')
        files.append(dict(original=source,archived=copied))
    build=store.write_bytes(relative/'build-information.txt',capture['build_information'].encode('utf-8'))
    manifest=dict(schema_version=1,engine_digest=canonical_digest(capture['engine']),versions=capture['versions'],
        build_information=artifact(build),files=files)
    return artifact(store.write(relative/'manifest.json',manifest))


def _commit_epoch(store,intent,reader):
    from ..media.continuity_report import capture_engine_sources
    folder=Path('epochs')/uid(intent['epoch_id'])
    try:capture=capture_engine_sources()
    except (ImportError,RuntimeError) as exc:
        raise ProductionRefused('continuity engine unavailable: '+str(exc)) from exc
    reader.check()
    if capture['engine']!=intent['engine']: raise ProductionRefused('engine changed during epoch transaction')
    path=store.write(folder/'intent.json',intent);boundary('epoch-intent')
    archive=_archive_engine(store,folder/'engine',capture,reader)
    commit=store.root/folder/'commit.json'
    created=Reader().read(commit)['created_at'] if commit.exists() else now()
    value=dict(schema_version=1,run_id=store.run_dir.name,epoch_id=intent['epoch_id'],intent=artifact(path),
               engine_archive=archive,created_at=created)
    result=artifact(store.write(folder/'commit.json',value));boundary('epoch-commit')
    return result


def ensure_initial_epoch(frozen,units,timeline,*,paths,logger,lock):
    if records.load_continuity_policy(frozen) is None:return None
    store=ContinuityStore(frozen,lock);store.owned()
    context,_=_context(frozen,units,timeline,paths=paths,lock=lock)
    # Source admission may validate a large whole-scene evidence closure. Start
    # the shared epoch IO budget only once that independent preflight succeeds.
    reader=Reader()
    chain,pending=records._epochs(frozen,_clip_ids(context),reader)
    if chain and not pending:return chain[-1]['artifact']
    incomplete=[p for p in (store.root/'epochs').glob('*/intent.json') if not (p.parent/'commit.json').exists()]
    if incomplete:
        if len(incomplete)!=1:raise ProductionRefused('ambiguous incomplete epoch')
        return _commit_epoch(store,reader.read(incomplete[0]),reader)
    if chain:raise SceneContinuityPending('engine changed; explicit continuity reassess required')
    intent=dict(schema_version=1,run_id=store.run_dir.name,epoch_id=str(uuid4()),previous_commit=None,
        clip_ids=_clip_ids(context),engine=records._current_engine(),reason='Initial frozen diagnostic engine',requested_at=now())
    return _commit_epoch(store,intent,reader)


@verified_scene_execution_write
def _entry(frozen,units,timeline,operation,*,paths,logger,lock,timeout=300):
    acquired=None
    try:
        if records.load_continuity_policy(frozen) is None:raise ProductionRefused('run has no frozen continuity policy')
        if lock is None:acquired=RunLock(run_for(frozen));acquired.__enter__();lock=acquired
        store=ContinuityStore(frozen,lock);store.owned();reader=Reader(timeout)
        context,source=_context(frozen,units,timeline,paths=paths,lock=lock)
        result=operation(store,context,source,reader)
        store.owned();return result
    except KeyboardInterrupt as exc:return _result(frozen,'interrupted',error=_error(exc))
    except SceneContinuityPending as exc:return _result(frozen,'awaiting_analysis',error=_error(exc))
    except (ProductionRefused,ValueError,OSError,KeyError,TypeError) as exc:return _result(frozen,'blocked',error=_error(exc))
    except (RuntimeError,TimeoutError,ImportError) as exc:return _result(frozen,'failed',error=_error(exc))
    finally:
        if acquired is not None:acquired.__exit__(None,None,None)


def reassess_scene_continuity(frozen,units,timeline,request_path,*,paths,logger,lock=None):
    def operation(store,context,source,reader):
        request=reader.read(request_path)
        records._schema(request,'schema_version run_id epoch_id previous_commit reason requested_at',store.run_dir)
        uid(request['epoch_id']);nonempty(request['reason'])
        if instant(request['requested_at'])>datetime.now(timezone.utc):raise ProductionRefused('future reassess request')
        chain,pending=records._epochs(frozen,_clip_ids(context),reader,current=False)
        existing=store.root/'epochs'/request['epoch_id']/'intent.json'
        if existing.exists():
            intent=reader.read(existing)
            if any(intent[k]!=request[k] for k in request):raise ProductionRefused('reassess intent changed')
            if (existing.parent/'commit.json').exists():
                if not chain or chain[-1]['intent']['epoch_id']!=request['epoch_id']:raise ProductionRefused('reassess no longer current')
                return _result(frozen,'awaiting_analysis',epoch=chain[-1]['artifact'])
        else:
            if pending:raise ProductionRefused('incomplete epoch must be resumed first')
            if not chain or request['previous_commit']!=chain[-1]['artifact']:raise ProductionRefused('reassess previous commit is stale')
            intent=dict(request,clip_ids=_clip_ids(context),engine=records._current_engine())
        result=_commit_epoch(store,intent,reader)
        return _result(frozen,'awaiting_analysis',epoch=result)
    return _entry(frozen,units,timeline,operation,paths=paths,logger=logger,lock=lock)


def _terminal(store,relative,job,attempt,*,status,outputs,report=None,exc=None):
    value=dict(schema_version=1,run_id=store.run_dir.name,assessment_id=job['assessment_id'],attempt_id=attempt['attempt_id'],
        status=status,report=report,outputs=outputs,failure=None if exc is None else dict(kind=type(exc).__name__,
        message=str(exc) or type(exc).__name__,evidence=outputs),finished_at=now())
    path=store.write(relative/'terminal.json',value);boundary('attempt-terminal');return artifact(path)


def _outputs(audit):
    # Analyzer output ownership is its dedicated continuity directory.
    return [artifact(p) for p in sorted((audit/'logs/continuity').rglob('*')) if p.is_file() and p.stat().st_size>0]


def _analysis(store,context,source,reader,request_path,paths):
    from ..media.continuity_report import validate_continuity_report
    from ..media.continuity_analysis import analyze_continuity
    from .logging import RunLogger
    from .paths import create_run
    request=reader.read(request_path)
    records._schema(request,'schema_version run_id assessment_id epoch clip_id manifest',store.run_dir)
    aid=uid(request['assessment_id']);folder=Path('jobs')/aid
    chain,pending=records._epochs(context['frozen'],_clip_ids(context),reader)
    if not chain or pending or request['epoch']!=chain[-1]['artifact']:raise ProductionRefused('analysis requires current complete epoch')
    epoch=chain[-1];binding=records._binding(context,source,request['clip_id'])
    manifest=reader.read(request['manifest'])
    records.validate_manifest_binding(manifest,binding,config=context['frozen'].config,_reader=reader,timeout=max(.001,reader.deadline-monotonic()))
    # One assessment intent locks a clip in an epoch, before any audit is created.
    for p in (store.root/'jobs').glob('*/intent.json'):
        old=reader.read(p)
        if old['epoch']==request['epoch'] and old['clip_id']==request['clip_id'] and old['assessment_id']!=aid:
            raise ProductionRefused('clip already has an assessment intent in this epoch')
    job_path=store.root/folder/'intent.json'
    job=dict(schema_version=1,run_id=store.run_dir.name,assessment_id=aid,epoch=request['epoch'],clip_id=request['clip_id'],
        binding=binding,manifest=request['manifest'],created_at=reader.read(job_path)['created_at'] if job_path.exists() else now())
    job_artifact=artifact(store.write(folder/'intent.json',job));boundary('job-intent')
    assessment_path=store.root/folder/'assessment.json'
    if assessment_path.exists():
        existing=records._assessment(assessment_path,epoch,context,source,reader)
        template=_review_template(store,folder,existing,assessment_path)
        return _result(context['frozen'],'awaiting_review',epoch=epoch['artifact'],assessment=artifact(assessment_path),
            template=template)
    completed=[];unfinished=[]
    for p in sorted((store.root/folder/'attempts').glob('*/intent.json')):
        attempt=reader.read(p)
        records._schema(attempt,'schema_version run_id assessment_id attempt_id audit_run_dir job created_at',store.run_dir)
        uid(attempt['attempt_id'])
        if attempt['job']!=job_artifact or attempt['assessment_id']!=aid or p.parent.name!=attempt['attempt_id']:
            raise ProductionRefused('attempt intent producer differs')
        relative=p.parent.relative_to(store.root);terminal_path=p.parent/'terminal.json'
        audit=validate_run_dir(Path(attempt['audit_run_dir']))
        report_path=audit/'logs/continuity/report.json'
        if terminal_path.exists():
            terminal=reader.read(terminal_path)
            records._schema(terminal,'schema_version run_id assessment_id attempt_id status report outputs failure finished_at',store.run_dir)
            if terminal['assessment_id']!=aid or terminal['attempt_id']!=attempt['attempt_id']:
                raise ProductionRefused('terminal producer differs')
            if terminal['status']=='failed':raise ProductionRefused('failed analysis requires explicit new epoch')
            if terminal['status']=='completed':completed.append((attempt,artifact(terminal_path)));continue
            if terminal['status']!='interrupted':raise ProductionRefused('invalid attempt terminal')
        elif report_path.exists():
            verified=validate_continuity_report(report_path,manifest=request['manifest'],config=context['frozen'].config,_budget=reader,
                expected_engine=epoch['intent']['engine'],
                expected_audit_run_dir=audit,timeout=max(.001,reader.deadline-monotonic()))
            terminal=_terminal(store,relative,job,attempt,status='completed',outputs=_outputs(audit),report=artifact(report_path))
            completed.append((attempt,terminal))
        elif not audit.exists() or not any((audit/'logs/continuity').rglob('*')):
            unfinished.append((attempt,relative))
        else:
            _terminal(store,relative,job,attempt,status='interrupted',outputs=_outputs(audit),exc=InterruptedError('Retained partial local analysis'))
    if len(completed)>1:raise ProductionRefused('multiple successful analysis attempts conflict')
    if not completed:
        if len(unfinished)>1:raise ProductionRefused('multiple unfinished attempts')
        if unfinished:attempt,relative=unfinished[0];audit=Path(attempt['audit_run_dir'])
        else:
            if len(list((store.root/folder/'attempts').glob('*/intent.json')))>=3:
                raise ProductionRefused('local analysis attempt limit reached; new epoch required')
            audit=create_run(paths);attempt_id=str(uuid4());relative=folder/'attempts'/attempt_id
            attempt=dict(schema_version=1,run_id=store.run_dir.name,assessment_id=aid,attempt_id=attempt_id,
                audit_run_dir=str(audit),job=job_artifact,created_at=now())
            store.write(relative/'intent.json',attempt);boundary('attempt-intent')
        audit_logger=RunLogger(audit)
        try:
            analyze_continuity(manifest,config=context['frozen'].config,paths=paths,logger=audit_logger,
                timeout=max(.001,reader.deadline-monotonic()))
        except BaseException as exc:
            _terminal(store,relative,job,attempt,status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',
                outputs=_outputs(audit),exc=exc)
            raise
        boundary('analysis-report')
        report_path=audit/'logs/continuity/report.json'
        validate_continuity_report(report_path,manifest=request['manifest'],config=context['frozen'].config,_budget=reader,
            expected_engine=epoch['intent']['engine'],
            expected_audit_run_dir=audit,timeout=max(.001,reader.deadline-monotonic()))
        terminal=_terminal(store,relative,job,attempt,status='completed',outputs=_outputs(audit),report=artifact(report_path))
        completed.append((attempt,terminal))
    attempt,terminal=completed[0];terminal_value=reader.read(terminal)
    verified=validate_continuity_report(terminal_value['report'],manifest=request['manifest'],config=context['frozen'].config,_budget=reader,
        expected_engine=epoch['intent']['engine'],
        expected_audit_run_dir=attempt['audit_run_dir'],timeout=max(.001,reader.deadline-monotonic()))
    mandatory=verified['closure']+[request['manifest']]
    for row in binding['clips']:
        mandatory += [row[k] for k in ('clip_record','request','generated','source','mapping','last_frame')]
        mandatory.append(reader.read(row['last_frame'])['image'])
    closure=sorted({v['path']:v for v in mandatory}.values(),key=lambda v:v['path'])
    for ref in closure:verify(ref,runtime=False,empty=ref['bytes']==0)
    value=dict(schema_version=1,run_id=store.run_dir.name,assessment_id=aid,epoch=epoch['artifact'],clip_id=job['clip_id'],
        job=job_artifact,attempt=terminal,binding=binding,manifest=request['manifest'],report=terminal_value['report'],
        closure=closure,concerns=records.derive_concerns(verified['report']),created_at=now())
    path=store.write(folder/'assessment.json',value);boundary('assessment')
    template=_review_template(store,folder,value,path)
    return _result(context['frozen'],'awaiting_review',epoch=epoch['artifact'],assessment=artifact(path),template=template)


def _review_template(store,folder,assessment,path):
    value=dict(schema_version=1,run_id=store.run_dir.name,assessment_id=assessment['assessment_id'],assessment=artifact(path),
        video_observation=None,prefix_observation=None,reviewer='',reviewed_at=None,
        responses=[dict(concern_id=c['concern_id'],disposition='unverified',reason='',references=[]) for c in assessment['concerns']])
    target=store.write(folder/'review-template.json',value)
    explanation=['# Continuity review — complete video playback required','',
        'Clip: '+assessment['clip_id'], 'Full retained prefix: '+str([(r['clip_id'],r['source_frames']) for r in assessment['binding']['clips']]),
        'Analysis domain: ordinary sRGB; raw uncalibrated measurements remain unverified.',
        'Report: '+assessment['report']['path'], '',
        'Supply the original schema2 video observation and same-author full prefix playback for three or more clips.',
        'Respond to every concern. Static images and numerical scores do not prove playback.','']
    for c in assessment['concerns']:explanation.append(str(c))
    store.write_bytes(folder/'review.md',('\n'.join(explanation)+'\n').encode('utf-8'))
    return artifact(target)


def analyze_scene_continuity(frozen,units,timeline,request_path,*,paths,logger,lock=None,timeout=300):
    return _entry(frozen,units,timeline,lambda store,context,source,reader:
        _analysis(store,context,source,reader,request_path,paths),paths=paths,logger=logger,lock=lock,timeout=timeout)


def consume_scene_continuity_review(frozen,units,timeline,review_path,*,paths,logger,lock=None):
    """Store author evidence only; never advance generation or media production."""
    from .production_scene_clips import _entry as clip_entry, _consume, _finish, _result as clip_result, _error as clip_error
    def operation(context):
        store=ContinuityStore(frozen,context['store'].lock);store.owned();reader=Reader()
        if records.load_continuity_policy(frozen) is None:raise ProductionRefused('run has no continuity policy')
        path=local(review_path);raw=path.read_bytes()
        if len(raw)>16777216:raise ProductionRefused('resource_limit: review JSON')
        value=reader.read(path);aid=uid(value['assessment_id'])
        chain,pending=records._epochs(frozen,_clip_ids(context),reader)
        if not chain or pending:raise SceneContinuityPending('review requires current complete epoch')
        from .scene_clip_records import collect_progress
        _,source=collect_progress(context)
        assessment_path=store.root/'jobs'/aid/'assessment.json'
        assessment=records._assessment(assessment_path,chain[-1],context,source,reader)
        expected=records._review_expected(context,source,assessment,assessment_path,reader)
        records.validate_continuity_review(value,expected,now=datetime.now(timezone.utc))
        if len(assessment['binding']['clips'])>=3:
            prefix=value['prefix_observation']
            retained=store.root/'prefix-observations'/(prefix['sha256']+'.json')
            source_prefix=Path(prefix['path']) if Path(prefix['path']).exists() else retained
            prefix_raw=source_prefix.read_bytes()
            if len(prefix_raw)!=prefix['bytes'] or hashlib.sha256(prefix_raw).hexdigest()!=prefix['sha256']:
                raise ProductionRefused('prefix author bytes changed before retention')
            store.write_bytes(Path('prefix-observations')/(prefix['sha256']+'.json'),prefix_raw)
        original=store.write_bytes(Path('reviews')/(hashlib.sha256(raw).hexdigest()+'.json'),raw)
        boundary('review-original')
        state=records._review_state(value,reader)
        # A raw confirmed issue is durable even if old accepted video cannot be replaced.
        cid=assessment['clip_id'];video=reader.read(value['video_observation']);record=source[cid]
        verdict=video['verdict'];receipt_name='observation-rejected.json' if verdict=='failed' else 'observation-accepted.json'
        receipt_path=records._metadata_folder(frozen,cid,record)/receipt_name
        if verdict in ('passed','failed'):
            if receipt_path.exists():
                existing=reader.read(receipt_path)
                existing_ref=existing['observation'];submitted=value['video_observation']
                if (existing['observation_sha256']!=canonical_digest(video)
                        or any(existing_ref[k]!=submitted[k] for k in ('bytes','sha256'))):
                    if state=='blocked':return _finish(context)
                    raise ProductionRefused('review cannot replace original video observation')
            else:_consume(context,value['video_observation']['path'])
        elif record['accepted'] is None and record['rejected'] is None:
            _consume(context,value['video_observation']['path'])
        if state=='awaiting_review' or verdict=='unverified':return _finish(context)
        receipt=dict(schema_version=1,run_id=store.run_dir.name,assessment_id=aid,assessment=artifact(assessment_path),
            review=artifact(original),video_receipt=artifact(receipt_path),state=state,created_at=now())
        existing_path=store.root/'reviews'/aid/'receipt.json'
        if existing_path.exists():
            old=reader.read(existing_path)
            if any(old[k]!=receipt[k] for k in receipt if k!='created_at'):
                if state=='blocked':return _finish(context)
                raise ProductionRefused('terminal continuity review cannot be replaced')
            receipt=old
        store.write(Path('reviews')/aid/'receipt.json',receipt);boundary('review-receipt')
        return _finish(context)
    return clip_entry(frozen,units,timeline,paths=paths,logger=logger,lock=lock,operation=operation)
