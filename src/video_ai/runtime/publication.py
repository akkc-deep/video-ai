"""Exclusive same-byte publication with marker and manifest consumption gates."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from ..config import read_json
from .manifest import ManifestStore, hash_file, thaw, now
from .paths import PathPolicy
from .timeline_checks import _run_path, _local, _again
from ._publication_review import author_path, load_gate, fresh
from ._publication_evidence import output_path as checked_output,artifact,index,same,validate


class PublicationRefusal(ValueError):
    """Admission refusal; the publish stage remains pending (CLI exit 2)."""
    def __init__(self,message,*,diagnostic_path=None,missing_checks=None):
        super().__init__(message);self.diagnostic_path=diagnostic_path;self.missing_checks=list(missing_checks or [])


@dataclass(frozen=True)
class PublicationResult:
    passed: bool
    run_dir: Path
    report_path: Path
    status: str
    staging_only: bool
    output_video_path: Path
    output_subtitle_path: Path
    published: bool


def result(run,status,video):
    completed=status=='completed'
    return PublicationResult(completed,run,run/'publication.json',status,not completed,video,video.with_suffix('.srt'),completed)


def atomic_json(path,data,*,run=None,output=False):
    path=checked_output(path) if output else _local(run,path)
    temporary=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    temporary=checked_output(temporary) if output else _local(run,temporary)
    with temporary.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(thaw(data),stream,ensure_ascii=False,allow_nan=False,indent=2);stream.flush();os.fsync(stream.fileno())
    if (checked_output(path) if output else _local(run,path))!=path:raise OSError('report path redirected during write')
    os.link(temporary,path);temporary.unlink()
    if not same(read_json(path),data):raise OSError('publication JSON readback differs')


def log_json(run,prefix,data):
    folder=_local(run,run/'logs/publication');folder.mkdir(parents=True,exist_ok=True)
    path=_local(run,folder/(prefix+'-'+uuid4().hex+'.json'));atomic_json(path,data,run=run);return path


def refuse(run,exc,checks=None,identities=None):
    path=None;checks=list(checks or ['publication_gate'])
    if run is not None:
        try:path=log_json(run,'diagnostic',dict(schema_version=1,run_id=run.name,created_at=now(),status='refused',message=str(exc),missing_checks=checks,evidence_identities=thaw(identities or {})))
        except (OSError,ValueError):pass
    return PublicationRefusal(str(exc),diagnostic_path=path,missing_checks=checks)


@contextmanager
def exclusive(path,*,run,output=False):
    path=checked_output(path) if output else _local(run,path)
    owner=dict(pid=os.getpid(),token=uuid4().hex)
    try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except (OSError,ValueError) as exc:raise refuse(run,ValueError('publication lock refused: '+str(exc)),['exclusive_lock']) from exc
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump(owner,stream);stream.flush();os.fsync(stream.fileno())
        yield path,owner
    finally:
        try:
            current=checked_output(path) if output else _local(run,path)
            if current==path and read_json(path)==owner:path.unlink()
        except (ValueError,OSError):pass
        except (KeyboardInterrupt,SystemExit):
            if ManifestStore.open(run).snapshot()['stages']['publish']['status']!='completed':raise


def check_locks(locks,run):
    for path,owner in locks:
        canonical=checked_output(path) if not path.is_relative_to(run) else _local(run,path)
        if canonical!=path or read_json(path)!=owner:raise OSError('publication lock token changed; foreign lock retained')


def upstream_unchanged(current,previous):
    for key in ('run_id','created_at','inputs','models','config_snapshot','voice_snapshot','units','services','resources'):
        if not same(current[key],previous[key]):raise OSError('publication upstream changed: '+key)
    for name,stage in previous['stages'].items():
        if name!='publish' and not same(current['stages'][name],stage):raise OSError('publication upstream stage changed: '+name)
    ignored={'publication_report','final_review','full_film_acceptance'}
    from .pipeline_evidence import media_workflows
    current_workflows,previous_workflows=media_workflows(current,previous)
    if not same({k:v for k,v in current_workflows.items() if k not in ignored},{k:v for k,v in previous_workflows.items() if k not in ignored}):raise OSError('publication upstream workflows changed')
    old=previous['events']
    if not same(current['events'][:len(old)],old):raise OSError('publication event prefix changed')
    if any(e.get('stage')!='publish' and e.get('action')!='manifest_update' for e in current['events'][len(old):]):raise OSError('unrelated manifest event during publication')


def copy_bytes(run,source_record,target):
    source_id=fresh(source_record,run=run);target=checked_output(target);source=Path(source_id.path)
    digest=hashlib.sha256();copied=0
    with source.open('rb') as incoming,target.open('xb') as outgoing:
        before=os.fstat(incoming.fileno())
        if (before.st_size,before.st_mtime_ns)!=(source_id.bytes,source_id.mtime_ns):raise OSError('source changed before copy')
        while block:=incoming.read(1024*1024):
            outgoing.write(block);digest.update(block);copied+=len(block)
        outgoing.flush();os.fsync(outgoing.fileno());after=os.fstat(incoming.fileno())
        if (after.st_size,after.st_mtime_ns)!=(before.st_size,before.st_mtime_ns):raise OSError('source changed during copy')
    _again({'source':source_id})
    if checked_output(target)!=target:raise OSError('output redirected during copy')
    target_id=hash_file(target)
    if (copied,digest.hexdigest(),target_id.bytes,target_id.sha256)!=(source_id.bytes,source_id.sha256,source_id.bytes,source_id.sha256):raise OSError('copied bytes differ from accepted source')
    evidence=log_json(run,'copy',dict(schema_version=1,run_id=run.name,created_at=now(),source_identity=thaw(source_id),target_identity=thaw(target_id),copied_bytes=copied,payload_sha256=digest.hexdigest()))
    return target_id,evidence


def publish_candidate(config,*,run_dir,review_path,acceptance_path,output_path=None):
    run=None
    try:run=_run_path(run_dir);store=ManifestStore.open(run)
    except (ValueError,OSError,TypeError) as exc:raise refuse(run,exc,['run']) from exc
    with exclusive(run/'.publish.lock',run=run) as run_lock:
        try:
            snapshot=store.snapshot();report_path=_local(run,run/'publication.json')
            if snapshot['stages']['publish']['status']!='pending' or any(k in snapshot['workflows'] for k in ('publication_report','final_review','full_film_acceptance')) or report_path.exists() or report_path.is_symlink():raise ValueError('pending publication without orphan report/receipts required')
            logs=_local(run,run/'logs/publication')
            if logs.exists() and any(not p.name.startswith('diagnostic-') for p in logs.iterdir()):raise ValueError('orphan publication transaction evidence')
            # Validate spelling before reading any author bytes, including missing files.
            review_path=author_path(run,review_path);acceptance_path=author_path(run,acceptance_path)
            missing=[name for name,path in [('final_review',review_path),('full_film_acceptance',acceptance_path)] if not path.is_file()]
            if missing:raise refuse(run,ValueError('missing final review or full-film acceptance'),missing)
            from .candidate_checks import load_committed_candidate
            candidate=load_committed_candidate(run)
            config_id=candidate['input_identities']['config'];fresh(config_id,expected=config.config_file)
            if not same(thaw(config.raw),read_json(config.config_file)) or config.config_file!=Path(snapshot['config_snapshot']['path']):raise ValueError('publication config differs from frozen candidate')
            gate=load_gate(run,candidate,review_path,acceptance_path)
            video=checked_output(output_path or config.output_root/(run.name+'.mp4'))
            if video.suffix.lower()!='.mp4':raise ValueError('output must have .mp4 extension')
            subtitle=checked_output(video.with_suffix('.srt'));marker=checked_output(video.with_suffix('.publication.json'))
            # Existing output root is permitted; no target directory creation on gate refusal.
            video.parent.mkdir(parents=True,exist_ok=True)
            if checked_output(video)!=video:raise ValueError('output directory redirected')
        except PublicationRefusal:raise
        except (ValueError,OSError,TypeError,KeyError) as exc:raise refuse(run,exc) from exc
        with exclusive(video.parent/('.'+video.stem+'.publish.lock'),run=run,output=True) as output_lock:
            locks=(run_lock,output_lock)
            try:
                for path in (video,subtitle,marker):
                    if path.exists() or path.is_symlink():raise ValueError('output already exists: '+str(path))
                required=candidate['candidate_identity']['bytes']+candidate['subtitle_identity']['bytes']+64*1024**2
                if shutil.disk_usage(video.parent).free<required:raise ValueError('insufficient publication disk capacity')
                _again(gate['identities']);upstream_unchanged(store.snapshot(),snapshot);check_locks(locks,run)
            except (ValueError,OSError,TypeError,KeyError) as exc:raise refuse(run,exc) from exc
            try:
                def begin(data):
                    upstream_unchanged(data,snapshot);check_locks(locks,run)
                    if data['stages']['publish']['status']!='pending':raise ValueError('publication stage changed before start')
                    store._record_status(data,data['stages']['publish'],'running',[],None,'publish',None)
                store.update(begin)
                video_id,video_log=copy_bytes(run,candidate['candidate_identity'],video)
                subtitle_id,subtitle_log=copy_bytes(run,candidate['subtitle_identity'],subtitle)
                # Full upstream consumer after copy, then author gate reconstruction again.
                current_candidate=load_committed_candidate(run)
                if not same(candidate,current_candidate):raise OSError('candidate changed during publication')
                current_gate=load_gate(run,current_candidate,review_path,acceptance_path)
                _again(gate['identities']);_again(current_gate['identities']);upstream_unchanged(store.snapshot(),snapshot);check_locks(locks,run)
                gate_log=log_json(run,'gate',dict(schema_version=1,run_id=run.name,created_at=now(),candidate_validation_identity=gate['candidate_identity'],final_review_identity=gate['review_identity'],acceptance_identity=gate['acceptance_identity'],review_collection_identities=gate['collection'],validation=gate['validation']))
                stamp=now();marker_data=dict(schema_version=1,run_id=run.name,created_at=stamp,candidate_validation_identity=gate['candidate_identity'],final_review_identity=gate['review_identity'],acceptance_identity=gate['acceptance_identity'],video_identity=thaw(video_id),subtitle_identity=thaw(subtitle_id))
                atomic_json(marker,marker_data,output=True);marker_id=hash_file(marker)
                evidence_paths=[video_log,subtitle_log,gate_log,acceptance_path,*[run/k for k in gate['collection']]]
                report=dict(schema_version=1,run_id=run.name,created_at=stamp,status='completed',passed=True,published=True,staging_only=False,candidate_validation_identity=gate['candidate_identity'],composition_identity=candidate['composition_identity'],input_identities=candidate['input_identities'],final_review_identity=gate['review_identity'],acceptance_identity=gate['acceptance_identity'],review_collection_identities=gate['collection'],accepted_candidate_identity=candidate['candidate_identity'],accepted_subtitle_identity=candidate['subtitle_identity'],output_video_identity=thaw(video_id),output_subtitle_identity=thaw(subtitle_id),output_marker_identity=thaw(marker_id),validation=gate['validation'],provenance=candidate['provenance'],request_evidence=index(run,evidence_paths))
                validate(run,report,gate);atomic_json(report_path,report,run=run)
                ids=validate(run,read_json(report_path),gate);report_id=hash_file(report_path)
                def commit(data):
                    upstream_unchanged(data,snapshot);check_locks(locks,run);_again(gate['identities']);_again(ids);_again({'report':report_id})
                    if data['stages']['publish']['status']!='running' or any(k in data['workflows'] for k in ('publication_report','final_review','full_film_acceptance')):raise ValueError('publication state/receipts changed before completion')
                    data['workflows'].update(publication_report=thaw(report_id),final_review=gate['review_identity'],full_film_acceptance=gate['acceptance_identity'])
                    store._record_status(data,data['stages']['publish'],'completed',[artifact(video_id,'output'),artifact(subtitle_id,'output'),artifact(report_id,'run')],None,'publish',None)
                store.update(commit)
                return result(run,'completed',video)
            except BaseException as exc:
                if store.snapshot()['stages']['publish']['status']=='completed':return result(run,'completed',video)
                status='interrupted' if isinstance(exc,(KeyboardInterrupt,SystemExit)) else 'failed';paths=[]
                try:paths.append(log_json(run,'failure',dict(schema_version=1,run_id=run.name,created_at=now(),status=status,message=str(exc))))
                except (ValueError,OSError,KeyboardInterrupt):pass
                error=dict(kind=status,message=str(exc),traceback_path=None,evidence_paths=[str(p) for p in paths])
                try:
                    def fail(data):
                        stage=data['stages']['publish']
                        if stage['status']=='running':store._record_status(data,stage,status,stage['artifacts'],error,'publish',None)
                    store.update(fail)
                except (ValueError,OSError,KeyboardInterrupt):pass
                if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise
                return result(run,'failed',video)


def load_committed_publication(run_dir):
    run=_run_path(run_dir);store=ManifestStore.open(run);snapshot=store.snapshot();stage=snapshot['stages']['publish']
    if stage['status']!='completed':raise ValueError('publication is not completed')
    path=_local(run,run/'publication.json')
    receipt=snapshot['workflows'].get('publication_report')
    if receipt is None:raise ValueError('publication report receipt missing')
    report_id=fresh(receipt,run=run,expected=path);report=read_json(path)
    from .candidate_checks import load_committed_candidate
    candidate=load_committed_candidate(run)
    review_path=author_path(run,Path(report['final_review_identity']['path']));acceptance_path=author_path(run,Path(report['acceptance_identity']['path']))
    for key,p in [('final_review',review_path),('full_film_acceptance',acceptance_path)]:
        registered=snapshot['workflows'].get(key)
        if registered is None:raise ValueError('publication '+key+' receipt missing')
        fresh(registered,run=run,expected=p)
        if not same(registered,report['final_review_identity' if key=='final_review' else 'acceptance_identity']):raise ValueError('publication author receipt replaced')
    gate=load_gate(run,candidate,review_path,acceptance_path);ids=validate(run,report,gate)
    expected=[artifact(ids['output_video_identity'],'output'),artifact(ids['output_subtitle_identity'],'output'),artifact(report_id,'run')]
    if not same(stage['artifacts'],expected):raise ValueError('publication artifacts missing/extra/replaced')
    _again(ids);_again(gate['identities']);_again({'publication':report_id})
    current=store.snapshot();upstream_unchanged(current,snapshot)
    if current['stages']['publish']!=stage or any(current['workflows'].get(k)!=snapshot['workflows'].get(k) for k in ('publication_report','final_review','full_film_acceptance')):raise OSError('publication committed state changed during consumption')
    return report
