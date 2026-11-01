"""Durable run evidence. Unknown submissions and existing locks never imply retry."""
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
from threading import RLock
from uuid import uuid4

from ..config import read_json, ProjectConfig
from .paths import PathPolicy, PROJECT_ROOT, shot_dir
from .verification import validation_session, protected_hash, file_stamp, check_path, _whole_cached_identity

STAGES = ('preflight', 'speech', 'timeline', 'storyboard', 'start_images',
          'source_clips', 'upscale', 'composition', 'validation', 'publish')
STATUSES = {'pending', 'running', 'completed', 'failed', 'ambiguous', 'interrupted'}
SUBMISSION_STATES = {'intent', 'accepted', 'ambiguous', 'rejected', 'completed', 'failed'}
_mutex = RLock()


def now() -> str:
    return datetime.now().astimezone().isoformat()


def thaw(value):
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        result = {f.name: thaw(getattr(value, f.name)) for f in fields(value)}
        # Preserve the exact historical serialized config for schema-1 consumers.
        if isinstance(value, ProjectConfig) and value.production_strategy == 'legacy':
            result.pop('production_strategy'); result.pop('image_generation')
        return result
    if isinstance(value, Mapping):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(v) for v in value]
    return value


@dataclass(frozen=True)
class FileIdentity:
    path: str
    bytes: int | None
    mtime_ns: int | None
    sha256: str | None
    verified_at: str | None


def hash_file(path: Path) -> FileIdentity:
    from ._continuity_byte_guard import observe_file
    protected = _whole_cached_identity(path)
    if protected is None:
        path = path.resolve(strict=True)
        protected = protected_hash(path, _hash_open_file)
    observe_file(protected)
    return protected


def _hash_open_file(file, path):
    before = file_stamp(file)
    digest = hashlib.file_digest(file, 'sha256').hexdigest()
    check_path(path, file, before)
    return FileIdentity(str(path), before[2], before[3], digest, now())


class ManifestBusyError(RuntimeError):
    pass


def validate_run_dir(run_dir: Path) -> Path:
    run = PathPolicy().validate_write(run_dir, 'run')
    if run.parent != PROJECT_ROOT / 'runs' or not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[0-9a-f]{12}', run.name):
        raise ValueError('expected a concrete generated run directory')
    return run


def validate_unit(kind: str, unit_id: str):
    if kind not in ('speech', 'shot', 'frame', 'image', 'shot_attempt') or not isinstance(unit_id, str):
        raise ValueError('invalid unit kind/ID')
    if kind in ('shot', 'image'):
        shot_dir(PROJECT_ROOT / 'runs', unit_id)
    elif kind == 'shot_attempt':
        match = re.fullmatch(r'shot_([0-9]{4}):attempt_([0-9]{4})', unit_id)
        if not match or int(match[1]) < 1 or int(match[2]) < 1:
            raise ValueError('invalid shot attempt ID')
    elif kind == 'frame':
        match = re.fullmatch(r'(shot_[0-9]{4,}):frame_([0-9]{6,})', unit_id)
        if not match or int(match[2]) < 1:
            raise ValueError('invalid frame ID')
        shot_dir(PROJECT_ROOT / 'runs', match[1])
    elif not re.fullmatch(r'[A-Za-z0-9_-]+', unit_id):
        raise ValueError('invalid speech ID')


def _timestamp(value, *, nullable=False):
    if value is None and nullable:
        return
    if not isinstance(value, str) or datetime.fromisoformat(value).tzinfo is None:
        raise ValueError('expected timezone-aware timestamp')


def _identity(value, *, artifact=False):
    keys = {'path', 'bytes', 'sha256', 'verified_at', 'category' if artifact else 'mtime_ns'}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError('invalid file identity')
    from .paths import _validate_spelling
    path = Path(_validate_spelling(value['path']))
    if not path.is_absolute():
        raise ValueError('identity requires absolute path')
    if artifact:
        PathPolicy().validate_write(path, value['category'])
    for key in ('bytes',) if artifact else ('bytes', 'mtime_ns'):
        if value[key] is not None and (type(value[key]) is not int or value[key] < 0):
            raise ValueError(f'invalid {key}')
    if value['sha256'] is not None and (not isinstance(value['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', value['sha256'])):
        raise ValueError('invalid SHA256')
    _timestamp(value['verified_at'], nullable=True)
    if value['sha256'] is not None and (value['verified_at'] is None or value['bytes'] is None):
        raise ValueError('hash requires fresh verification metadata')


def _evidence_path(value, run):
    path = PathPolicy().validate_write(value, 'run')
    if not path.is_relative_to(run):
        raise ValueError('evidence outside this run')


def _absolute(value):
    from .paths import _validate_spelling
    if not isinstance(value,str) or not Path(_validate_spelling(value)).is_absolute():
        raise ValueError('expected absolute path')
    return Path(value)


def _config_snapshots(data):
    from ..config import ProjectConfig, VoiceConfig, TOOL_FIELDS, MODEL_FIELDS, WORKFLOW_FIELDS, TIMEOUT_DEFAULTS
    from ..adapters.common import validate_base_url, positive_timeout
    from .paths import RUNTIME_ROOT, OUTPUT_ROOT, CACHE_ROOT
    resolved=data['config_snapshot']['resolved']
    config_fields = {f.name for f in fields(ProjectConfig)}-{'voice','raw'}
    modern = resolved.get('production_strategy') == 'paragraph_jimeng_v1'
    if not modern: config_fields -= {'production_strategy', 'image_generation'}
    if set(resolved)!=config_fields:
        raise ValueError('invalid resolved project config fields')
    for name,expected in (('runtime_root',RUNTIME_ROOT),('project_root',PROJECT_ROOT),('output_root',OUTPUT_ROOT),('cache_root',CACHE_ROOT)):
        if _absolute(resolved[name])!=expected:
            raise ValueError(f'invalid resolved {name}')
    for name in ('config_file','voice_config'):
        _absolute(resolved[name])
    for group,names in (('tools',TOOL_FIELDS),('models',MODEL_FIELDS),('workflows',WORKFLOW_FIELDS)):
        expected = set(names)
        if modern and group in ('models', 'workflows') and 'sdxl' not in resolved[group]: expected.remove('sdxl')
        if not isinstance(resolved[group],dict) or set(resolved[group])!=expected:
            raise ValueError(f'invalid resolved {group}')
        for path in resolved[group].values():_absolute(path)
    if not isinstance(resolved['services'],dict) or set(resolved['services'])!={'ollama','comfyui','tts'}:
        raise ValueError('invalid resolved services')
    for url in resolved['services'].values():validate_base_url(url)
    if not isinstance(resolved['timeouts'],dict) or set(resolved['timeouts'])!=set(TIMEOUT_DEFAULTS):
        raise ValueError('invalid resolved timeouts')
    for timeout in resolved['timeouts'].values():positive_timeout(timeout)
    voice=data['voice_snapshot']['resolved']
    if not isinstance(voice,dict) or set(voice)!={f.name for f in fields(VoiceConfig)}-{'raw'}:
        raise ValueError('invalid resolved voice fields')
    for name in ('gpt_weights','sovits_weights','bert_root','hubert_root','reference_audio','config_file'):_absolute(voice[name])
    if data['voice_snapshot']['path']!=voice['config_file'] or data['config_snapshot']['path']!=resolved['config_file']:
        raise ValueError('snapshot source path mismatch')
    if not isinstance(resolved['media'],dict) or not isinstance(resolved['media'].get('profile'),dict):
        raise ValueError('invalid resolved media')
    from ..config import MediaConfig, parse_timeline_settings
    media_fields={f.name for f in fields(MediaConfig)}
    if set(resolved['media']) not in (media_fields,media_fields-{'timeline'}):
        raise ValueError('invalid resolved media fields')
    if 'timeline' in resolved['media']:
        settings=resolved['media']['timeline']
        if not isinstance(settings,dict) or set(settings)!={'sentence_pause_seconds','paragraph_pause_seconds','opening_seconds','closing_seconds'}:
            raise ValueError('invalid resolved timeline settings')
        parse_timeline_settings(settings,Path(resolved['config_file']))
    for name in ('font_file','music'):
        if resolved['media'].get(name) is not None:_absolute(resolved['media'][name])


def _services_resources(data,run):
    from ..adapters.common import validate_base_url
    required={'name','url','owned','pid','started_at','status','updated_at'}
    optional={'health','args','cwd','stdout_path','stderr_path','returncode','error','action','response_path'}
    for name,service in data['services'].items():
        if name not in ('comfyui','tts','ollama') or not isinstance(service,dict) or not required<=set(service) or set(service)-required-optional:
            raise ValueError('invalid service record')
        if service['name']!=name or type(service['owned']) is not bool or service['status'] not in {'starting','healthy','conflict','failed','stopped','external','models_released'}:
            raise ValueError('invalid service ownership/status')
        validate_base_url(service['url'])
        pid=service['pid']
        if pid is not None and (type(pid) is not int or pid<=0):raise ValueError('invalid service PID')
        if service['owned'] and (pid is None or service['started_at'] is None):raise ValueError('owned service requires PID/start evidence')
        _timestamp(service['started_at'],nullable=True)
        _timestamp(service['updated_at'])
        if 'returncode' in service and service['returncode'] is not None and type(service['returncode']) is not int:raise ValueError('invalid returncode')
        for key in ('stdout_path','stderr_path','response_path'):
            if key in service:_evidence_path(service[key],run)
        if 'cwd' in service:
            cwd=_absolute(service['cwd'])
            if not cwd.is_relative_to(Path('D:/VideoSi')):raise ValueError('service cwd outside runtime')
        if 'args' in service:
            if not isinstance(service['args'],list) or not service['args'] or not all(isinstance(a,str) for a in service['args']):raise ValueError('invalid service args')
            _absolute(service['args'][0])
    if set(data['resources'])-{'latest','summary'}:raise ValueError('invalid resources fields')
    if 'latest' in data['resources']:
        sample=data['resources']['latest']
        if not isinstance(sample,dict) or sample.get('status') not in ('verified','unverified'):
            raise ValueError('invalid resource sample')
        for key in ('external_pids','compute_pids'):
            pids=sample.get(key,[])
            if not isinstance(pids,list) or any(type(pid) is not int or pid<=0 for pid in pids):raise ValueError('invalid resource PIDs')
        for key in ('gpu_total_mib','gpu_used_mib','gpu_utilization_percent','system_used_bytes'):
            value=sample.get(key)
            if value is not None and (type(value) is not int or value<0):raise ValueError('invalid resource measurement')
        paths=sample.get('evidence_paths',[])
        if not isinstance(paths,list):raise ValueError('invalid resource evidence')
        for path in paths:_evidence_path(path,run)


def _record(value, run, *, unit=False):
    expected = {'status', 'started_at', 'finished_at', 'artifacts', 'error'} | ({'submission'} if unit else set())
    if not isinstance(value, dict) or set(value) != expected or value['status'] not in STATUSES:
        raise ValueError('invalid stage/unit record')
    for name in ('started_at', 'finished_at'):
        _timestamp(value[name], nullable=True)
    if value['status'] != 'pending' and value['started_at'] is None:
        raise ValueError('started status requires started_at')
    if value['status'] not in ('pending', 'running') and value['finished_at'] is None:
        raise ValueError('terminal status requires finished_at')
    if not isinstance(value['artifacts'], list):
        raise ValueError('artifacts must be list')
    for artifact in value['artifacts']:
        _identity(artifact, artifact=True)
    error = value['error']
    if error is not None:
        if not isinstance(error, dict) or set(error) != {'kind', 'message', 'traceback_path', 'evidence_paths'}:
            raise ValueError('invalid error record')
        if not all(isinstance(error[k], str) for k in ('kind', 'message')) or not isinstance(error['evidence_paths'], list):
            raise ValueError('invalid error fields')
        for path in error['evidence_paths'] + ([error['traceback_path']] if error['traceback_path'] is not None else []):
            if not isinstance(path,str):raise ValueError('error path must be string or null')
            _evidence_path(path, run)
    if unit and value['submission'] is not None:
        sub = value['submission']
        keys = {'attempt_id', 'client_id', 'state', 'request_path', 'response_path', 'prompt_id', 'number', 'submitted_at', 'last_seen_at'}
        if not isinstance(sub, dict) or set(sub) != keys or sub['state'] not in SUBMISSION_STATES:
            raise ValueError('invalid submission')
        from uuid import UUID
        import math
        for key in ('attempt_id', 'client_id', 'prompt_id'):
            if key == 'prompt_id' and sub[key] is None:
                continue
            if not isinstance(sub[key], str) or str(UUID(sub[key])) != sub[key]:
                raise ValueError('invalid submission UUID')
        if sub['number'] is not None and (type(sub['number']) not in (int, float) or not math.isfinite(sub['number'])):
            raise ValueError('invalid queue number')
        if sub['state'] in ('accepted', 'completed', 'failed') and sub['prompt_id'] is None:
            raise ValueError('accepted submission requires prompt_id')
        if sub['state']=='intent' and any(sub[k] is not None for k in ('prompt_id','number','response_path')):
            raise ValueError('intent cannot claim acceptance')
        if sub['state'] in ('accepted','completed','failed') and (sub['number'] is None or sub['response_path'] is None):
            raise ValueError('accepted submission requires number/response evidence')
        if sub['request_path'] is None:raise ValueError('submission requires actual workflow path')
        for key in ('request_path', 'response_path'):
            if sub[key] is not None:
                _evidence_path(sub[key], run)
        _timestamp(sub['submitted_at'])
        _timestamp(sub['last_seen_at'], nullable=True)


def _validate(data, run):
    required = {'schema_version', 'run_id', 'created_at', 'updated_at', 'inputs', 'config_snapshot',
                'voice_snapshot', 'models', 'workflows', 'stages', 'units', 'services', 'resources', 'events'}
    if not isinstance(data, dict) or set(data) != required or type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('invalid manifest schema')
    if data['run_id'] != run.name:
        raise ValueError('run_id mismatch')
    for key in ('created_at', 'updated_at'):
        _timestamp(data[key])
    for group in ('inputs', 'models', 'workflows'):
        if not isinstance(data[group], dict):
            raise ValueError('invalid identity group')
        for identity in data[group].values():
            _identity(identity)
    for key in ('config_snapshot', 'voice_snapshot'):
        value = data[key]
        if not isinstance(value, dict) or set(value) != {'path', 'raw', 'resolved'} or not isinstance(value['raw'], dict) or not isinstance(value['resolved'], dict) or not Path(value['path']).is_absolute():
            raise ValueError('invalid configuration snapshot')
    _config_snapshots(data)
    if not isinstance(data['stages'], dict) or list(data['stages']) != list(STAGES):
        raise ValueError('invalid ordered stages')
    for value in data['stages'].values():
        _record(value, run)
    if (not isinstance(data['units'], dict) or not {'speech', 'shot', 'frame'} <= set(data['units'])
            or set(data['units']) - {'speech', 'shot', 'frame', 'image', 'shot_attempt'}):
        raise ValueError('invalid unit groups')
    for kind, units in data['units'].items():
        if not isinstance(units, dict):
            raise ValueError('invalid units')
        for unit_id, value in units.items():
            validate_unit(kind, unit_id)
            _record(value, run, unit=True)
    for key in ('services', 'resources'):
        if not isinstance(data[key], dict):
            raise ValueError(f'invalid {key}')
    _services_resources(data,run)
    if not isinstance(data['events'], list):
        raise ValueError('invalid events')
    for event in data['events']:
        if not isinstance(event, dict) or not {'time', 'stage', 'unit_id', 'action', 'evidence_paths'} <= set(event):
            raise ValueError('invalid event')
        _timestamp(event['time'])
        if not isinstance(event['evidence_paths'],list) or not isinstance(event['action'],str):
            raise ValueError('invalid event evidence/action')
        for path in event['evidence_paths']:
            _evidence_path(path, run)
    json.dumps(data, allow_nan=False)


def pending_record(*, unit=False):
    record = dict(status='pending', started_at=None, finished_at=None, artifacts=[], error=None)
    if unit:
        record['submission'] = None
    return record


def _transition(previous, current):
    if 'submission' in previous:
        old,new=previous['submission'],current['submission']
        if old is None and new is not None and new['state']!='intent':raise ValueError('submission must begin as intent')
        if old is not None:
            if new is None:raise ValueError('cannot erase a submission for re-POST')
            for key in ('attempt_id','client_id','request_path','submitted_at'):
                if old[key]!=new[key]:raise ValueError('cannot replace submission identity')
            for key in ('prompt_id','number'):
                if old[key] is not None and old[key]!=new[key]:raise ValueError('cannot replace accepted prompt identity')
            allowed={'intent':{'accepted','ambiguous','rejected'},'accepted':{'ambiguous','completed','failed'},
                     'ambiguous':{'accepted','completed','failed'},'rejected':set(),'completed':set(),'failed':set()}
            if old['state']!=new['state'] and new['state'] not in allowed[old['state']]:raise ValueError('invalid submission transition')
    if previous == current:
        return
    if previous['status'] == current['status']:
        if previous['status'] not in ('pending', 'running'):
            raise ValueError('terminal record cannot change')
        return
    if not (previous['status'] == 'pending' and current['status'] == 'running' or
            previous['status'] == 'running' and current['status'] in STATUSES - {'pending', 'running'}):
        raise ValueError('invalid stage/unit transition')


class ManifestStore:
    def __init__(self, run_dir, *, verify_integrity=True):
        if type(verify_integrity) is not bool:raise ValueError('verify_integrity must be a boolean')
        self.run_dir = validate_run_dir(run_dir)
        self.verify_integrity = verify_integrity

    @classmethod
    def open(cls, run_dir, *, verify_integrity=True):
        store = cls(run_dir, verify_integrity=verify_integrity)
        store.snapshot()
        return store

    def snapshot(self):
        data = read_json(PathPolicy().validate_write(self.run_dir / 'manifest.json', 'run'))
        try:
            if self.verify_integrity:_validate(data, self.run_dir)
        except (TypeError,KeyError,OverflowError,AttributeError) as exc:
            raise ValueError('invalid manifest field type') from exc
        return data

    @contextmanager
    def _locked(self):
        with _mutex:
            path = PathPolicy().validate_write(self.run_dir / '.manifest.lock', 'run')
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError as exc:
                raise ManifestBusyError(f'existing write lock: {path}') from exc
            try:
                token=uuid4().hex
                with os.fdopen(fd, 'w', encoding='utf-8') as file:
                    file.write(json.dumps({'pid': os.getpid(), 'token': token}))
                yield
            finally:
                try:
                    owner=json.loads(path.read_text(encoding='utf-8'))
                except (OSError,ValueError) as exc:
                    raise ManifestBusyError('write lock ownership unavailable; retained') from exc
                if not isinstance(owner,dict) or owner.get('token')!=token:
                    raise ManifestBusyError('write lock belongs to another owner; retained')
                PathPolicy().validate_write(path,'run').unlink()

    def _write(self, data):
        if self.verify_integrity:_validate(data, self.run_dir)
        temporary = PathPolicy().validate_write(self.run_dir / f'manifest.{uuid4().hex}.tmp', 'run')
        with temporary.open('x', encoding='utf-8', newline='\n') as file:
            json.dump(data, file, ensure_ascii=False, allow_nan=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, PathPolicy().validate_write(self.run_dir / 'manifest.json', 'run'))

    def update(self, mutator):
        with self._locked():
            old = self.snapshot()
            data = deepcopy(old)
            mutator(data)
            if data == old:
                return
            if 'upscale_resume' in old['workflows'] and data['workflows'].get('upscale_resume')!=old['workflows']['upscale_resume']:
                raise ValueError('cannot replace or remove registered upscale resume receipt')
            for key,value in old['workflows'].items():
                if re.fullmatch(r'pipeline_(invocation|plan|result)_[0-9a-f]{32}',key) and data['workflows'].get(key)!=value:
                    raise ValueError('cannot replace or remove pipeline audit receipt')
            if self.verify_integrity:_validate(data, self.run_dir)
            for key in ('schema_version','run_id','created_at','config_snapshot','voice_snapshot'):
                if old[key]!=data[key]:raise ValueError(f'cannot change immutable {key}')
            if data['events'][:len(old['events'])]!=old['events']:raise ValueError('cannot erase historical events')
            if len(data['events'])==len(old['events']):
                data['events'].append(dict(time=now(),stage=None,unit_id=None,action='manifest_update',evidence_paths=[]))
            for stage in STAGES:
                _transition(old['stages'][stage], data['stages'][stage])
            if not set(old['units']) <= set(data['units']):
                raise ValueError('cannot remove unit groups')
            for kind, units in data['units'].items():
                for unit_id, record in units.items():
                    _transition(old['units'].get(kind, {}).get(unit_id, pending_record(unit=True)), record)
                if not set(old['units'].get(kind, {})) <= set(units):
                    raise ValueError('cannot remove unit records')
            data['updated_at'] = now()
            self._write(data)

    def resume_unsubmitted_upscale(self, receipt_identity, *, expected_snapshot, unit_id):
        """The only terminal reopening: a fresh receipt-bound, unsubmitted tail."""
        from ._upscale_resume import receipt, prefix, reconstruct, policy
        from ._upscale_evidence import identity_equal
        from .timeline_checks import _again
        with self._locked():
            old = self.snapshot()
            if old != expected_snapshot:raise ValueError('resume manifest changed')
            proof, original, proof_ids = receipt(self.run_dir, receipt_identity, old, replay=False)
            if original != old or prefix(old) != unit_id or proof['unit_id'] != unit_id:
                raise ValueError('resume snapshot/unsubmitted tail differs')
            from ..config import load_config
            from ._upscale_inputs import inputs
            config=load_config(Path(old['config_snapshot']['path']));context=inputs(config,self.run_dir)
            _,records,_=reconstruct(config,self.run_dir,old,context,_receipt_paths=(Path(thaw(receipt_identity)['path']),Path(proof['manifest_identity']['path'])))
            if proof['execution_policy']!=policy(config):raise ValueError('receipt execution policy differs from frozen config')
            expected=dict(records,**{'inputs/'+name:thaw(entry) for name,entry in context['identities'].items()})
            if set(expected)!=set(proof['reused_identities']):raise ValueError('resume reused input/evidence index differs')
            for name,entry in expected.items():
                if not identity_equal(entry,proof['reused_identities'][name]):raise ValueError('resume reused identity differs')
            _again(proof_ids);_again(context['identities'])
            if self.snapshot()!=old:raise ValueError('resume manifest changed during final admission')
            if (self.run_dir/'manifest.json').read_bytes() != Path(proof['manifest_identity']['path']).read_bytes():
                raise ValueError('resume original manifest bytes differ')
            data = deepcopy(old)
            stamp = now()
            data['stages']['upscale'] = dict(status='running', started_at=stamp, finished_at=None, artifacts=[], error=None)
            if unit_id is not None:data['units']['frame'][unit_id] = pending_record(unit=True)
            data['workflows']['upscale_resume'] = thaw(receipt_identity)
            data['events'].append(dict(time=stamp, stage='upscale', unit_id=unit_id,
                action='resume_unsubmitted_upscale', evidence_paths=[receipt_identity.path if isinstance(receipt_identity,FileIdentity) else receipt_identity['path']]))
            data['updated_at'] = stamp
            _validate(data, self.run_dir)
            self._write(data)

    def _record_status(self, data, record, status, artifacts, error, stage, unit_id):
        if status not in STATUSES:
            raise ValueError('invalid status')
        candidate = deepcopy(record)
        candidate.update(status=status, artifacts=thaw(artifacts), error=thaw(error))
        if status == 'running' and record['status'] == 'pending':
            candidate['started_at'] = now()
        if status not in ('pending', 'running') and record['status'] == 'running':
            candidate['finished_at'] = now()
        _transition(record, candidate)
        if record == candidate:
            return
        record.update(candidate)
        data['events'].append(dict(time=now(), stage=stage, unit_id=unit_id, action=status,
                                   evidence_paths=[a['path'] for a in artifacts if Path(a['path']).is_relative_to(self.run_dir)]))

    def record_stage(self, stage, status, *, artifacts=(), error=None):
        if stage not in STAGES:
            raise ValueError('unknown stage')
        self.update(lambda data: self._record_status(data, data['stages'][stage], status, artifacts, error, stage, None))

    def record_unit(self, kind, unit_id, status, *, artifacts=(), submission=None, error=None):
        validate_unit(kind, unit_id)
        def mutate(data):
            record = data['units'].setdefault(kind, {}).setdefault(unit_id, pending_record(unit=True))
            self._record_status(data, record, status, artifacts, error, kind, unit_id)
            if submission is not None:
                record['submission'] = thaw(submission)
        self.update(mutate)


def create_manifest(run_dir, config, *, inputs, models, workflows, verify_integrity=True):
    store = ManifestStore(run_dir, verify_integrity=verify_integrity)
    stamp = now()
    resolved = thaw(config)
    voice = resolved.pop('voice')
    resolved.pop('raw')
    voice.pop('raw')
    data = dict(schema_version=1, run_id=store.run_dir.name, created_at=stamp, updated_at=stamp,
                inputs=thaw(inputs), models=thaw(models), workflows=thaw(workflows),
                config_snapshot={'path':str(config.config_file), 'raw':thaw(config.raw), 'resolved':resolved},
                voice_snapshot={'path':str(config.voice.config_file), 'raw':thaw(config.voice.raw), 'resolved':voice},
                stages={stage:pending_record() for stage in STAGES},
                units={kind:{} for kind in ('speech','shot','frame')}, services={}, resources={}, events=[])
    with store._locked():
        if (store.run_dir / 'manifest.json').exists():
            raise FileExistsError('manifest already exists')
        store._write(data)
    return store
