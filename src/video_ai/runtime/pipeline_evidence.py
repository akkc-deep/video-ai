"""Exclusive coordinator evidence and ownership; no terminal-state rewrites."""
from contextlib import contextmanager
from datetime import datetime
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from ..config import read_json
from .manifest import hash_file, now, thaw, _identity
from .timeline_checks import _local, _run_path, _again


def fresh_identity(record):
    value = thaw(record)
    _identity(value)
    if any(v is None for v in value.values()):
        raise ValueError('pipeline requires complete file identity')
    path = Path(value['path'])
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError('pipeline identity path is redirected/noncanonical')
    if datetime.fromisoformat(value['verified_at']) > datetime.now().astimezone():
        raise ValueError('future pipeline identity')
    actual = hash_file(path)
    if any(getattr(actual, k) != value[k] for k in ('path', 'bytes', 'mtime_ns', 'sha256')):
        raise OSError(f'pipeline evidence changed: {path}')
    return actual


def write_exclusive(run, path, data, *, raw=False):
    path = _local(run, Path(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = data if raw else json.dumps(thaw(data), ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')
    with path.open('xb') as file:
        file.write(payload)
        file.flush()
        os.fsync(file.fileno())
    return hash_file(path)


def save_record(run, kind, data):
    if kind not in ('plan', 'invocation', 'result', 'diagnostic', 'adoption', 'manifest', 'parent-manifest'):
        raise ValueError('unknown pipeline evidence kind')
    return write_exclusive(run, run/'logs/pipeline'/f'{kind}-{uuid4().hex}.json', data)


@contextmanager
def exclusive(run):
    run = _run_path(run)
    path = _local(run, run/'.pipeline.lock')
    owner = dict(pid=os.getpid(), token=uuid4().hex)
    try:
        descriptor = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError(f'existing pipeline lock: {path}') from exc
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
            json.dump(owner, file); file.flush(); os.fsync(file.fileno())
        yield owner
    finally:
        try:
            if read_json(path) == owner:
                _local(run, path).unlink()
        except (OSError, ValueError, KeyboardInterrupt):
            pass


def check_lock(run, owner):
    if read_json(_local(run, run/'.pipeline.lock')) != owner:
        raise ValueError('pipeline lock replaced during invocation')


def check_stage_locks(run):
    for name in ('manifest', 'speech', 'timeline', 'storyboard', 'start-images', 'images',
                 'source-clips', 'upscale', 'composition', 'validation', 'publish'):
        path = _local(run, run/f'.{name}.lock')
        if path.exists() or path.is_symlink():
            raise ValueError(f'existing stage lock: {path}')


def protected_snapshot(current, original):
    """Later legal additions cannot erase the protected provenance prefix."""
    for key in ('schema_version', 'run_id', 'created_at', 'config_snapshot', 'voice_snapshot'):
        if current[key] != original[key]:
            raise OSError('pipeline protected manifest changed: '+key)
    for group in ('inputs','models'):
        for name,old in original[group].items():
            new=current[group].get(name)
            if new is None or any(new[k]!=old[k] for k in ('path','bytes','mtime_ns','sha256')):
                raise OSError('pipeline protected '+group+' changed: '+name)
        if original['stages']['speech']['status']=='completed' and set(current[group])!=set(original[group]):
            raise OSError('pipeline completed provenance set changed: '+group)
    for name, record in original['stages'].items():
        if record['status'] not in ('pending', 'running') and current['stages'][name] != record:
            raise OSError('pipeline terminal stage changed: '+name)
    for kind, units in original['units'].items():
        for uid, record in units.items():
            if record['status'] not in ('pending', 'running') and current['units'].get(kind, {}).get(uid) != record:
                raise OSError('pipeline terminal unit changed: '+uid)
            saved = record['submission']
            if saved is not None:
                new = current['units'][kind][uid]['submission']
                if new is None or any(new[k] != saved[k] for k in ('attempt_id', 'client_id', 'request_path', 'submitted_at')):
                    raise OSError('pipeline original submission identity changed')
                if saved['prompt_id'] is not None and new['prompt_id'] != saved['prompt_id']:
                    raise OSError('pipeline saved prompt changed')
    if current['events'][:len(original['events'])] != original['events']:
        raise OSError('pipeline event prefix changed')


_AUDIT_KEY=re.compile(r'pipeline_(invocation|plan|result)_([0-9a-f]{32})\Z')


def _audit_record(run,key,record):
    match=_AUDIT_KEY.fullmatch(key)
    if match is None:raise ValueError('invalid pipeline audit registration')
    kind,token=match.groups();path=run/'logs/pipeline'/f'{kind}-{token}.json'
    identity=fresh_identity(record)
    if identity.path!=str(_local(run,path)):raise ValueError('pipeline audit path differs')
    data=read_json(path)
    fields={
        'invocation':'schema_version run_id started_at request input_identities',
        'plan':'schema_version run_id created_at plan',
        'result':'schema_version run_id finished_at invocation_identity final_snapshot_identity input_identities result steps waiting_details validation'}
    if set(data)!=set(fields[kind].split()) or type(data['schema_version']) is not int or data['schema_version']!=1 or data['run_id']!=run.name:
        raise ValueError('pipeline audit schema/run differs')
    timestamp=data[{'invocation':'started_at','plan':'created_at','result':'finished_at'}[kind]]
    from .manifest import _timestamp
    _timestamp(timestamp)
    if datetime.fromisoformat(timestamp)>datetime.now().astimezone():raise ValueError('future pipeline audit')
    fresh_identity(identity)
    return data,identity


def register_pipeline_evidence(store,records):
    values={}
    for identity in records:
        path=Path(identity.path);key='pipeline_'+path.stem.replace('-','_')
        _audit_record(store.run_dir,key,identity);values[key]=thaw(identity)
    def add(data):
        for key,value in values.items():
            if key in data['workflows'] and data['workflows'][key]!=value:raise ValueError('pipeline audit replacement')
            data['workflows'][key]=value
    store.update(add)


def media_workflows(current,previous):
    """Only validated, append-only coordinator audit references are ancillary."""
    from .paths import PROJECT_ROOT
    run=_run_path(PROJECT_ROOT/'runs'/current['run_id'])
    for key,record in previous['workflows'].items():
        if key.startswith('pipeline_') and _AUDIT_KEY.fullmatch(key):
            if current['workflows'].get(key)!=record:raise OSError('pipeline audit registration changed')
    cleaned=[]
    for snapshot in (current,previous):
        group={}
        for key,record in snapshot['workflows'].items():
            if _AUDIT_KEY.fullmatch(key):_audit_record(run,key,record)
            else:group[key]=record
        cleaned.append(group)
    return tuple(cleaned)


def load_pipeline_result(path):
    """Fresh-process audit consumer, with immutable invocation and input proof."""
    path = Path(path)
    run = _run_path(path.parents[2])
    if path.parent != run/'logs/pipeline' or not path.name.startswith('result-'):
        raise ValueError('canonical pipeline result path required')
    from .manifest import ManifestStore
    snapshot=ManifestStore.open(run).snapshot();key='pipeline_'+path.stem.replace('-','_')
    if key not in snapshot['workflows']:raise ValueError('pipeline result is not registered')
    data,identity=_audit_record(run,key,snapshot['workflows'][key])
    result=data['result']
    fields='run_dir parent_run_dir status active_stage waiting_for candidate_path subtitle_path published report_path'.split()
    if not isinstance(result,dict) or set(result)!=set(fields):raise ValueError('pipeline result fields differ')
    status=result['status']
    if status not in ('candidate_ready','awaiting_review','awaiting_acceptance','published','failed','interrupted','refused'):
        raise ValueError('unknown pipeline result status')
    from .manifest import STAGES
    if result['run_dir']!=str(run) or result['report_path']!=str(path) or result['active_stage'] not in (*STAGES,None):
        raise ValueError('pipeline result run/stage/path differs')
    if type(result['published']) is not bool or result['published']!=(status=='published'):
        raise ValueError('pipeline publication status differs')
    if (result['candidate_path'] is None)!=(result['subtitle_path'] is None):raise ValueError('pipeline media path pair differs')
    candidate=None
    if result['candidate_path'] is not None and status!='published':
        if snapshot['stages']['validation']['status']!='completed':raise ValueError('pipeline media has no committed candidate')
        from .candidate_checks import load_committed_candidate
        candidate=load_committed_candidate(run)
        if result['candidate_path']!=candidate['candidate_identity']['path'] or result['subtitle_path']!=candidate['subtitle_identity']['path']:
            raise ValueError('pipeline media paths differ')
    from .pipeline_stages import REVIEW_PATHS
    waiting=result['waiting_for']
    if (not isinstance(waiting,list) or any(type(role) is not str or role not in (*REVIEW_PATHS,'publish') for role in waiting)
            or len(set(waiting))!=len(waiting) or bool(waiting)!=(status in ('awaiting_review','awaiting_acceptance','candidate_ready'))):
        raise ValueError('pipeline wait/status differs')
    if not isinstance(data['waiting_details'],list) or [row.get('role') for row in data['waiting_details']]!=waiting:
        raise ValueError('pipeline wait details differ')
    for row in data['waiting_details']:
        canonical=str(run/REVIEW_PATHS[row['role']]) if row['role']!='publish' else None
        if set(row)!=set('role canonical_path stage draft_identity stage_artifact_identities'.split()) or row['canonical_path']!=canonical or row['stage'] not in STAGES:
            raise ValueError('pipeline wait evidence differs')
        if row['draft_identity'] is not None:fresh_identity(row['draft_identity'])
        for record in row['stage_artifact_identities']:fresh_identity(record)
    expected_parent=None
    if 'pipeline_import' in snapshot['workflows']:
        from .pipeline_import import load_pipeline_import
        expected_parent=str(run.parent/load_pipeline_import(run)['parent_run_id'])
    if result['parent_run_dir']!=expected_parent:raise ValueError('pipeline parent differs')
    ids = {name: fresh_identity(value) for name, value in data['input_identities'].items()}
    ids['invocation'] = fresh_identity(data['invocation_identity'])
    ids['snapshot'] = fresh_identity(data['final_snapshot_identity'])
    if Path(ids['invocation'].path).parent!=run/'logs/pipeline' or Path(ids['snapshot'].path).parent!=run/'logs/pipeline':raise ValueError('pipeline audit source path differs')
    invocation_key='pipeline_'+Path(ids['invocation'].path).stem.replace('-','_')
    if not re.fullmatch(r'pipeline_invocation_[0-9a-f]{32}',invocation_key) or invocation_key not in snapshot['workflows']:raise ValueError('pipeline invocation not registered as invocation')
    invocation,_=_audit_record(run,invocation_key,snapshot['workflows'][invocation_key])
    request=invocation['request']
    if (not isinstance(request,dict) or set(request)!=set('reviews_path changes_path retry_failed publish output_path'.split())
            or type(request['retry_failed']) is not bool or type(request['publish']) is not bool
            or request['publish'] and (request['retry_failed'] or request['changes_path'] is not None)
            or status=='published' and request['publish'] is not True):
        raise ValueError('pipeline invocation request differs')
    if datetime.fromisoformat(data['finished_at'])<datetime.fromisoformat(invocation['started_at']):raise ValueError('pipeline result predates invocation')
    for name,record in invocation['input_identities'].items():
        original=fresh_identity(record)
        if name not in ids or any(getattr(ids[name],field)!=getattr(original,field) for field in ('path','bytes','mtime_ns','sha256')):
            raise ValueError('pipeline invocation inputs differ')
    if not re.fullmatch(r'manifest-[0-9a-f]{32}\.json',Path(ids['snapshot'].path).name):raise ValueError('pipeline final snapshot path differs')
    final_snapshot=read_json(Path(ids['snapshot'].path))
    from .manifest import _validate
    _validate(final_snapshot,run)
    protected_snapshot(snapshot,final_snapshot)
    if status in ('candidate_ready','awaiting_acceptance') and (final_snapshot['stages']['validation']['status']!='completed' or final_snapshot['stages']['publish']['status']=='completed'):
        raise ValueError('pipeline candidate/result stage relation differs')
    if status=='published' and final_snapshot['stages']['publish']['status']!='completed':raise ValueError('pipeline published stage differs')
    if not isinstance(data['steps'],list):raise ValueError('pipeline steps required')
    for step in data['steps']:
        if set(step)!=set('operation plan_identity result input_identities finished_at'.split()):raise ValueError('pipeline step fields differ')
        plan_identity=fresh_identity(step['plan_identity']);plan_key='pipeline_'+Path(plan_identity.path).stem.replace('-','_')
        if not re.fullmatch(r'pipeline_plan_[0-9a-f]{32}',plan_key) or plan_key not in snapshot['workflows']:raise ValueError('pipeline plan not registered as plan')
        plan,_=_audit_record(run,plan_key,snapshot['workflows'][plan_key])
        if step['operation'] not in plan['plan']['operations']:raise ValueError('pipeline step was not planned')
    if status in ('awaiting_acceptance', 'candidate_ready', 'published'):
        from .candidate_checks import load_committed_candidate
        candidate = candidate if candidate is not None else load_committed_candidate(run)
        if snapshot['stages']['validation']['status']!='completed':raise ValueError('pipeline candidate stage differs')
        if status!='published' and (result['candidate_path']!=candidate['candidate_identity']['path'] or result['subtitle_path']!=candidate['subtitle_identity']['path']):
            raise ValueError('pipeline candidate paths differ')
        if candidate['validation'] != data['validation'] and status != 'published':
            raise ValueError('pipeline candidate verdicts changed')
    if status == 'published':
        from .publication import load_committed_publication
        publication=load_committed_publication(run)
        if result['candidate_path']!=publication['output_video_identity']['path'] or result['subtitle_path']!=publication['output_subtitle_identity']['path'] or data['validation']!=publication['validation']:
            raise ValueError('pipeline publication paths/verdict differ')
    elif status not in ('awaiting_acceptance','candidate_ready') and not {'actual_final_video_semantics','actual_final_video_sync','full_film_acceptance'}<=set(data['validation']):
        raise ValueError('pipeline unverified verdicts missing')
    _again(ids); _again({'result': identity})
    return data
