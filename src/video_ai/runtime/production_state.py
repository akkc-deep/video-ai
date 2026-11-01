"""Automatic production records. Call mutations while holding this run's RunLock."""
from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import datetime
import ctypes
from ctypes import wintypes
import json
from functools import wraps
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

from ..config import read_json
from .manifest import now, validate_run_dir
from .paths import PathPolicy, _validate_spelling

STAGES = ('preflight', 'units', 'speech', 'timeline', 'storyboard', 'start_images',
          'source_clips', 'upscale', 'composition', 'delivery')
REPORT_NAMES = dict(zip(STAGES, ('preflight', 'units', 'speech', 'timeline', 'storyboard',
                               'images', 'source-clips', 'upscaled-clips', 'composition', 'delivery-report')))
PAYLOAD_FIELDS = {
    'preflight': {'checks'}, 'units': {'decoded_text', 'has_bom', 'spans', 'semantic_specs', 'planner'},
    'speech': {'script_path', 'spans', 'total_speech_samples'}, 'timeline': None,
    'storyboard': {'global_visual','effective_media','shots','transitions'}, 'start_images': {'images'},
    'source_clips': {'clips', 'frame_mappings'}, 'upscale': {'clips', 'frame_mappings'},
    'composition': {'candidate', 'subtitle', 'frames', 'samples', 'subtitle_events', 'encoding', 'probe'},
    'delivery': None,
}


class ProductionRefused(ValueError):
    """An input, ownership or recovery rejection; no automatic resubmission."""


_validation_cache = ContextVar('production_validation_cache', default=None)


def _validation_scope(function):
    """Share observations within one read-only validation, never across calls."""
    @wraps(function)
    def scoped(*args, **kwargs):
        if _validation_cache.get() is not None:
            return function(*args, **kwargs)
        token = _validation_cache.set(dict(absolute_paths={}, run_paths={}, stamps={}))
        try:
            return function(*args, **kwargs)
        finally:
            _validation_cache.reset(token)
    return scoped


def object_fields(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ProductionRefused(f'{label}: expected exact fields {sorted(fields)}')


def integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ProductionRefused(f'{label}: expected integer >= {minimum}')


def string(value, label):
    if not isinstance(value, str) or not value:
        raise ProductionRefused(f'{label}: expected nonempty string')


def timestamp(value, nullable=False):
    if value is None and nullable: return
    try:
        if not isinstance(value, str) or datetime.fromisoformat(value).tzinfo is None: raise ValueError()
    except ValueError as exc:
        raise ProductionRefused('expected timezone-aware timestamp') from exc


def absolute_path(value):
    if not isinstance(value, str): raise ProductionRefused('expected absolute path string')
    cache = _validation_cache.get()
    if cache is not None and value in cache['absolute_paths']:
        return cache['absolute_paths'][value]
    path = Path(_validate_spelling(value))
    if not path.is_absolute(): raise ProductionRefused('expected absolute path')
    if cache is not None: cache['absolute_paths'][value] = path
    return path


def run_path(run, value):
    value = str(value)
    cache = _validation_cache.get()
    key = (str(run), value)
    if cache is not None and key in cache['run_paths']:
        return cache['run_paths'][key]
    path = PathPolicy().validate_write(absolute_path(value), 'run')
    if not path.is_relative_to(run): raise ProductionRefused(f'path outside this run: {path}')
    if cache is not None: cache['run_paths'][key] = path
    return path


def json_bytes(data):
    # A JSON roundtrip also rules out non-JSON objects in nested payloads.
    return (json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')


def write_exclusive(path, data):
    raw = json_bytes(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as file:
        file.write(raw); file.flush(); os.fsync(file.fileno())
    return path


def sync_file(path):
    """Re-establish durability of an existing immutable artifact before cursor commit."""
    # Windows CRT _commit requires a writable handle; r+b neither truncates nor edits.
    with path.open('r+b') as file:
        os.fsync(file.fileno())


@dataclass(frozen=True)
class ArtifactStamp:
    path: str
    bytes: int
    mtime_ns: int

    def __post_init__(self):
        absolute_path(self.path)
        integer(self.bytes, 'stamp.bytes')
        integer(self.mtime_ns, 'stamp.mtime_ns')

    @classmethod
    def read(cls, path):
        path = Path(path).resolve(strict=True)
        if not path.is_file(): raise ProductionRefused(f'expected artifact file: {path}')
        stat = path.stat()
        return cls(str(path), stat.st_size, stat.st_mtime_ns)

    @classmethod
    def from_dict(cls, data):
        object_fields(data, ('path', 'bytes', 'mtime_ns'), 'ArtifactStamp')
        return cls(**data)

    def to_dict(self): return asdict(self)

    def verify(self):
        cache = _validation_cache.get()
        if cache is None:
            actual = self.read(self.path)
        else:
            actual = cache['stamps'].get(self.path)
            if actual is None:
                actual = self.read(self.path)
                cache['stamps'][self.path] = actual
        if self != actual: raise ProductionRefused(f'artifact stamp changed: {self.path}')


def _stamps(records, *, run=None, verify=False):
    if not isinstance(records, dict): raise ProductionRefused('expected artifact records object')
    for role, data in records.items():
        string(role, 'artifact role')
        stamp = ArtifactStamp.from_dict(data)
        if run is not None: run_path(run, stamp.path)
        if verify: stamp.verify()


def validate_error(error, run):
    if error is None: return
    object_fields(error, ('kind', 'message', 'evidence_paths'), 'error')
    string(error['kind'], 'error.kind'); string(error['message'], 'error.message')
    if not isinstance(error['evidence_paths'], list): raise ProductionRefused('expected evidence_paths list')
    for path in error['evidence_paths']: run_path(run, path)


def validate_request(request, run):
    if request is None: return
    object_fields(request, ('state', 'intent_path', 'client_id', 'prompt_id', 'response_paths'), 'request')
    if request['state'] not in ('intent', 'accepted', 'ambiguous', 'completed', 'failed'):
        raise ProductionRefused('invalid request.state')
    run_path(run, request['intent_path']); string(request['client_id'], 'request.client_id')
    if request['prompt_id'] is not None: string(request['prompt_id'], 'request.prompt_id')
    if not isinstance(request['response_paths'], list): raise ProductionRefused('expected response paths list')
    for path in request['response_paths']: run_path(run, path)


def _header(data, run):
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ProductionRefused('schema_version must be integer 1')
    if data['execution_mode'] != 'automatic' or data['run_id'] != run.name:
        raise ProductionRefused('automatic record run identity differs')
    timestamp(data['created_at'])


@_validation_scope
def validate_report(data, run, stage):
    object_fields(data, ('schema_version', 'execution_mode', 'run_id', 'stage', 'created_at',
                         'status', 'input_records', 'payload'), 'stage report')
    _header(data, run)
    if stage not in STAGES or data['stage'] != stage or data['status'] != 'completed':
        raise ProductionRefused('invalid completed report stage/status')
    _stamps(data['input_records'])
    payload = data['payload']
    if not isinstance(payload, dict): raise ProductionRefused('report payload must be object')
    fields = PAYLOAD_FIELDS[stage]
    if fields is not None: object_fields(payload, fields, f'{stage} payload')
    if stage == 'preflight':
        if not isinstance(payload['checks'], list) or not payload['checks']:
            raise ProductionRefused('preflight checks must be nonempty')
        for check in payload['checks']:
            object_fields(check, ('name', 'passed', 'details'), 'preflight check')
            string(check['name'], 'check.name'); string(check['details'], 'check.details')
            if check['passed'] is not True: raise ProductionRefused('preflight report requires passed checks')
    elif stage == 'units':
        from ..planning.production_units import validate_production_units
        from ..planning.composition import CompositionSettings
        # Structural validation here; the runtime rechecks actual frozen font widths before TTS.
        validate_production_units(payload,measure=lambda text:0,composition_settings=CompositionSettings())
    elif stage == 'speech':
        from .production_speech import validate_speech_payload
        validate_speech_payload(payload,run=run)
    elif stage == 'timeline':
        from ..planning.production_timeline import ProductionTimeline
        ProductionTimeline.from_dict(payload)
    elif stage in ('storyboard','start_images','source_clips'):
        from .production_visual_records import validate_visual_report
        validate_visual_report(stage,payload,run)
    elif stage == 'upscale':
        from .production_upscale_records import validate_upscale_report
        validate_upscale_report(payload, run)
    elif stage == 'composition':
        from .production_composition_records import validate_composition_report
        validate_composition_report(payload, run)
    elif stage == 'delivery':
        from .production_delivery_records import validate_delivery_receipt
        validate_delivery_receipt(payload, run)
        expected = {'options','composition','technical_checks','transaction','final_checkpoint'}
        object_fields(data['input_records'], expected, 'delivery report inputs')
        _stamps(data['input_records'],run=run,verify=True)
        for role,name in (('options','production/options.json'),('composition','production/composition.json'),
                          ('technical_checks','production/technical-checks.json'),('transaction','production/delivery.json'),
                          ('final_checkpoint','logs/production/checkpoints/delivery/final.json')):
            if run_path(run,data['input_records'][role]['path'])!=run/name:
                raise ProductionRefused('delivery report input path differs')
        final=read_json(run/'logs/production/checkpoints/delivery/final.json')
        validate_checkpoint(final,run,'delivery','final')
        if final['payload']['receipt']!=payload:raise ProductionRefused('delivery report receipt differs')
    json_bytes(data)


@_validation_scope
def validate_checkpoint(data, run, stage, unit_id):
    object_fields(data, ('schema_version', 'execution_mode', 'run_id', 'stage', 'unit_id',
                         'created_at', 'status', 'request', 'outputs', 'payload'), 'checkpoint')
    _header(data, run)
    if data['stage'] != stage or data['unit_id'] != unit_id or data['status'] != 'completed':
        raise ProductionRefused('checkpoint identity/status differs')
    validate_request(data['request'], run)
    if (stage in ('speech','start_images','source_clips') or
        stage=='units' and re.fullmatch(r'units_batch_[0-9]{4}_(initial|correction)',unit_id) or
        stage=='storyboard' and re.fullmatch(r'storyboard_batch_[0-9]{4}_(initial|correction|entityrepair)',unit_id)) and data['request'] is None:
        raise ProductionRefused('completed model checkpoint requires original request')
    if data['request'] is not None and data['request']['state'] != 'completed':
        raise ProductionRefused('checkpoint request is not completed')
    _stamps(data['outputs'], run=run, verify=True)
    if not isinstance(data['payload'], dict): raise ProductionRefused('checkpoint payload must be object')
    payload=data['payload']
    if stage=='units' and re.fullmatch(r'units_batch_[0-9]{4}_(initial|correction)',unit_id):
        object_fields(payload,('format_valid','proposal','error'),'unit response payload')
        if type(payload['format_valid']) is not bool: raise ProductionRefused('format_valid must be boolean')
        if payload['format_valid']:
            if not isinstance(payload['proposal'],dict) or payload['error'] is not None:
                raise ProductionRefused('valid response requires proposal and no error')
        else:
            if payload['proposal'] is not None: raise ProductionRefused('invalid response has no proposal')
            string(payload['error'],'format error')
    elif stage=='speech':
        from ..planning.production_timeline import ProductionAudioInfo
        from ..planning.segments import TextSpan
        from .production_speech import SPAN_FIELDS,AUDIO_FIELDS
        from .production_timeline import parse_estimate
        object_fields(payload,('text','span','estimate'),'speech checkpoint payload')
        item=payload['span'];object_fields(item,(*SPAN_FIELDS,*AUDIO_FIELDS),'speech checkpoint span')
        span=TextSpan(**{k:item[k] for k in SPAN_FIELDS})
        if span.unit_id!=unit_id or span.kind!='speech' or span.text!=payload['text']:
            raise ProductionRefused('speech checkpoint text/identity differs')
        info=ProductionAudioInfo.from_dict(dict(stamp=item['pcm'],sample_rate=item['sample_rate'],channels=item['channels'],
            sample_width=item['sample_width'],samples=item['samples']))
        ArtifactStamp.from_dict(item['raw'])
        if data['outputs'].get('raw')!=item['raw'] or data['outputs'].get('pcm')!=item['pcm']:
            raise ProductionRefused('speech checkpoint outputs differ')
        estimate=parse_estimate(payload['estimate'])
        if estimate.samples!=info.samples: raise ProductionRefused('speech checkpoint sample count differs')
    elif stage=='timeline' and unit_id=='automatic-slots':
        from ..planning.production_timing import AutomaticSlotPlan
        AutomaticSlotPlan.from_dict(payload)
        if data['request'] is not None or set(data['outputs'])!={'timing'}:
            raise ProductionRefused('automatic slots require timing output and no request')
    elif stage in ('storyboard','start_images','source_clips'):
        from .production_visual_records import validate_visual_checkpoint
        validate_visual_checkpoint(stage,unit_id,payload,run)
    elif stage == 'upscale':
        from .production_upscale_records import validate_upscale_checkpoint
        validate_upscale_checkpoint(unit_id, payload, run)
        if unit_id.endswith('_extract'):
            if data['request'] is not None: raise ProductionRefused('extraction has no model request')
            for row in payload['frames']:
                if row['input'] not in data['outputs'].values(): raise ProductionRefused('extracted input is not registered')
            for key in ('stdout_path', 'stderr_path'):
                if not any(s['path'] == payload['command'][key] for s in data['outputs'].values()):
                    raise ProductionRefused('extraction command evidence is not registered')
        else:
            for key in ('input','input_copy','output','model_output'):
                if data['outputs'].get(key) != payload[key]: raise ProductionRefused('frame checkpoint outputs differ')
            req, sub = data['request'], payload['submission']
            if req is None or any(req[k] != sub[k] for k in ('intent_path','client_id','prompt_id','response_paths')):
                raise ProductionRefused('frame checkpoint request/submission differs')
            for path in (*sub['response_paths'], *payload['media_evidence_paths']):
                if not any(s['path'] == path for s in data['outputs'].values()):
                    raise ProductionRefused('frame evidence is not registered')
    elif stage == 'composition':
        from .production_composition_records import validate_composition_checkpoint
        validate_composition_checkpoint(unit_id, payload, run)
        if data['request'] is not None: raise ProductionRefused('composition has no model request')
        required = ({'subtitle':payload['subtitle'],'ass':payload['ass'],'font':payload['font'],
                    'narration':payload['narration']['stamp']} if unit_id == 'materialized'
                    else {'candidate':payload['candidate']})
        if unit_id == 'final': required['subtitle'] = payload['subtitle']
        for key, stamp in required.items():
            if data['outputs'].get(key) != stamp: raise ProductionRefused('composition outputs differ')
        if unit_id == 'materialized':
            for row in payload['contributions']:
                for key in ('input','output'):
                    if row[key] not in data['outputs'].values(): raise ProductionRefused('contribution stamp is not registered')
        elif unit_id == 'encoded':
            if payload['materialized_checkpoint'] not in data['outputs'].values():
                raise ProductionRefused('materialized checkpoint stamp is not registered')
            for key in ('stdout_path','stderr_path'):
                if not any(s['path'] == payload['encoding'][key] for s in data['outputs'].values()):
                    raise ProductionRefused('encoding command evidence is not registered')
        from .production_composition_records import validate_composition_links
        validate_composition_links(data, run)
    elif stage == 'delivery':
        from .production_delivery_records import validate_delivery_checkpoint
        validate_delivery_checkpoint(data,run)
    json_bytes(data)


def _unit_id(unit_id):
    if not isinstance(unit_id, str) or not re.fullmatch('[A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+)*', unit_id):
        raise ProductionRefused('invalid production unit ID')


@_validation_scope
def validate_state(data, run):
    object_fields(data, ('schema_version', 'execution_mode', 'run_id', 'created_at', 'updated_at',
                         'invocation_status', 'active_stage', 'options_path', 'stages', 'units',
                         'delivery', 'error'), 'production state')
    _header(data, run); timestamp(data['updated_at'])
    if data['invocation_status'] not in ('running', 'delivered', 'failed', 'blocked', 'interrupted'):
        raise ProductionRefused('invalid invocation_status')
    if run_path(run, data['options_path']) != run/'production/options.json':
        raise ProductionRefused('options path differs')
    object_fields(data['stages'], STAGES, 'stages')
    first = None
    for stage in STAGES:
        record = data['stages'][stage]
        object_fields(record, ('status', 'report_path', 'started_at', 'finished_at'), 'stage record')
        status = record['status']
        if status not in ('pending', 'running', 'completed'): raise ProductionRefused('invalid stage status')
        timestamp(record['started_at'], nullable=True); timestamp(record['finished_at'], nullable=True)
        if status == 'completed':
            if first is not None or record['started_at'] is None or record['finished_at'] is None:
                raise ProductionRefused('stages must complete in order with timestamps')
            path = run_path(run, record['report_path'])
            if path != run/'production'/f'{REPORT_NAMES[stage]}.json': raise ProductionRefused('report path differs')
            validate_report(read_json(path), run, stage)
        else:
            if first is None: first = stage
            elif status != 'pending': raise ProductionRefused('only active stage may run')
            if record['report_path'] is not None or record['finished_at'] is not None:
                raise ProductionRefused('unfinished stage cannot register completion')
            if (status == 'running') != (record['started_at'] is not None):
                raise ProductionRefused('stage start timestamp differs')
    if data['active_stage'] != first: raise ProductionRefused('active stage differs from completed prefix')
    if data['invocation_status'] == 'delivered' and first is not None:
        raise ProductionRefused('delivered requires all stages completed')
    if not isinstance(data['units'], dict) or set(data['units']) - set(STAGES):
        raise ProductionRefused('invalid unit stages')
    for stage, units in data['units'].items():
        if not isinstance(units, dict): raise ProductionRefused('unit records must be object')
        for uid, record in units.items():
            _unit_id(uid)
            object_fields(record, ('status', 'checkpoint_path', 'request', 'outputs', 'error'), 'unit record')
            if record['status'] not in ('pending', 'running', 'completed', 'failed'):
                raise ProductionRefused('invalid unit status')
            validate_request(record['request'], run); _stamps(record['outputs'], run=run)
            validate_error(record['error'], run)
            if record['status'] == 'completed':
                path = run_path(run, record['checkpoint_path'])
                checkpoint = read_json(path)
                validate_checkpoint(checkpoint, run, stage, uid)
                if checkpoint['outputs'] != record['outputs'] or checkpoint['request'] != record['request']:
                    raise ProductionRefused('unit differs from checkpoint')
            elif record['checkpoint_path'] is not None: raise ProductionRefused('unfinished unit has checkpoint')
    for stage in ('units','speech','timeline','storyboard','start_images','source_clips','upscale','composition'):
        if data['stages'][stage]['status'] != 'completed': continue
        units = data['units'].get(stage,{})
        if not units: raise ProductionRefused(f'completed {stage} requires actual checkpoint units')
        report = read_json(run/'production'/f'{REPORT_NAMES[stage]}.json')
        if stage == 'units':
            expected={uid for batch in report['payload']['planner']['batches'] for uid in batch['request_ids']}
        elif stage == 'speech':expected={row['unit_id'] for row in report['payload']['spans'] if row['kind']=='speech'}
        elif stage == 'timeline':expected={'automatic-slots'}
        elif stage == 'storyboard':
            expected=set()
            for index in range(1,(len(report['payload']['shots'])+7)//8+1):
                uid=f'storyboard_batch_{index:04d}_initial';expected.add(uid)
                record=units.get(uid)
                if record is None:raise ProductionRefused('completed storyboard lacks initial request')
                cp=read_json(run_path(run,record['checkpoint_path']))
                if not cp['payload']['format_valid']:
                    uid=f'storyboard_batch_{index:04d}_correction';expected.add(uid)
                    record=units.get(uid)
                    if record is None:raise ProductionRefused('completed storyboard lacks correction request')
                    cp=read_json(run_path(run,record['checkpoint_path']))
                    if not cp['payload']['format_valid']:
                        if cp['payload']['error']!='unknown entity identity':raise ProductionRefused('completed storyboard has invalid correction')
                        uid=f'storyboard_batch_{index:04d}_entityrepair';expected.add(uid)
                        record=units.get(uid)
                        if record is None:raise ProductionRefused('completed storyboard lacks entity repair request')
                        cp=read_json(run_path(run,record['checkpoint_path']))
                        if not cp['payload']['format_valid']:raise ProductionRefused('completed storyboard has invalid entity repair')
        elif stage == 'start_images':expected={row['shot_id'] for row in report['payload']['images']}
        elif stage == 'source_clips':expected={row['shot_id'] for row in report['payload']['clips']}
        elif stage == 'upscale':
            expected = {f'{clip["shot_id"]}_extract' for clip in report['payload']['clips']}
            expected.update(f'{clip["shot_id"]}:frame_{row["frame_index"]:06d}'
                            for clip in report['payload']['clips'] for row in clip['frames'])
        else: expected = {'materialized','encoded','final'}
        if set(units) != expected or any(row['status'] != 'completed' for row in units.values()):
            raise ProductionRefused(f'completed {stage} checkpoint coverage differs')
        if stage == 'composition':
            final = read_json(run_path(run,units['final']['checkpoint_path']))
            if final['payload'] != report['payload']: raise ProductionRefused('composition report differs from final checkpoint')
            from .production_composition_records import validate_technical_checks
            validate_technical_checks(read_json(run/'production/technical-checks.json'),run)
    if data['delivery'] is not None:
        from .production_delivery_records import validate_delivery_transaction
        path=run_path(run,data['delivery'])
        if path!=run/'production/delivery.json':raise ProductionRefused('delivery transaction path differs')
        validate_delivery_transaction(read_json(path),run)
    if data['stages']['delivery']['status']=='completed':
        if data['delivery'] is None:raise ProductionRefused('completed delivery has no transaction')
        tx=read_json(Path(data['delivery']))
        units=data['units'].get('delivery',{})
        if tx['status']!='completed' or set(units)!={'final'} or units['final']['status']!='completed':
            raise ProductionRefused('completed delivery lacks final transaction/checkpoint')
        report=read_json(run/'production/delivery-report.json')
        if report['payload']!=tx['receipt']:raise ProductionRefused('delivery completed records disagree')
    validate_error(data['error'], run)
    json_bytes(data)


class ProductionStateStore:
    def __init__(self, run_dir):
        self.run_dir = validate_run_dir(run_dir)
        self.path = run_path(self.run_dir, self.run_dir/'production/production-state.json')

    @classmethod
    def create(cls, run_dir):
        store = cls(run_dir); stamp = now()
        data = dict(schema_version=1, execution_mode='automatic', run_id=store.run_dir.name,
                    created_at=stamp, updated_at=stamp, invocation_status='running', active_stage='preflight',
                    options_path=str(store.run_dir/'production/options.json'),
                    stages={s: dict(status='pending', report_path=None, started_at=None, finished_at=None) for s in STAGES},
                    units={}, delivery=None, error=None)
        validate_state(data, store.run_dir); write_exclusive(store.path, data)
        return store

    @classmethod
    def open(cls, run_dir):
        store = cls(run_dir); store.snapshot(); return store

    def snapshot(self):
        data = read_json(self.path)
        try: validate_state(data, self.run_dir)
        except (TypeError, KeyError, AttributeError) as exc: raise ProductionRefused('invalid state field type') from exc
        return data

    def save_exclusive(self, relative, data):
        self._assert_owned()
        return write_exclusive(run_path(self.run_dir, self.run_dir/relative), data)

    def _assert_owned(self):
        owner=getattr(self,'_run_lock_owner',None)
        if owner is not None:
            path=run_path(self.run_dir,self.run_dir/'.make-video.lock')
            if not path.is_file() or read_json(path)!=owner:raise ProductionRefused('state lost held run lock ownership')

    def _commit(self, data, action):
        self._assert_owned()
        data['updated_at'] = now(); validate_state(data, self.run_dir)
        temporary = run_path(self.run_dir, self.path.with_name(f'production-state.{uuid4().hex}.tmp'))
        write_exclusive(temporary, data)
        self._assert_owned();os.replace(temporary, self.path)
        if self.snapshot() != data: raise OSError('state readback differs')
        events = run_path(self.run_dir, self.run_dir/'logs/production/events.jsonl')
        events.parent.mkdir(parents=True, exist_ok=True)
        with events.open('a', encoding='utf-8', newline='\n') as file:
            file.write(json.dumps(dict(time=now(), action=action, active_stage=data['active_stage']), allow_nan=False)+'\n')
            file.flush(); os.fsync(file.fileno())

    def start_stage(self, stage):
        data = self.snapshot()
        if stage != data['active_stage']: raise ProductionRefused('stage is not active')
        record = data['stages'][stage]
        if record['status'] == 'running': return
        record.update(status='running', started_at=now())
        self._commit(data, f'{stage}:running')

    def write_report(self, stage, payload, *, input_records=None):
        report = dict(schema_version=1, execution_mode='automatic', run_id=self.run_dir.name,
                      stage=stage, created_at=now(), status='completed', input_records=input_records or {}, payload=payload)
        validate_report(report, self.run_dir, stage)
        return self.save_exclusive(f'production/{REPORT_NAMES[stage]}.json', report)

    def complete_stage(self, stage):
        data = self.snapshot()
        if stage != data['active_stage'] or data['stages'][stage]['status'] != 'running':
            raise ProductionRefused('stage must be active and running')
        path = run_path(self.run_dir, self.run_dir/f'production/{REPORT_NAMES[stage]}.json')
        if not path.is_file(): raise ProductionRefused('completed stage report must be persisted first')
        validate_report(read_json(path), self.run_dir, stage)
        sync_file(path)
        if any(unit['status'] != 'completed' for unit in data['units'].get(stage, {}).values()):
            raise ProductionRefused('stage still has incomplete units')
        data['stages'][stage].update(status='completed', report_path=str(path), finished_at=now())
        index = STAGES.index(stage)+1
        data['active_stage'] = STAGES[index] if index < len(STAGES) else None
        self._commit(data, f'{stage}:completed')

    def set_invocation(self, status, error=None):
        data = self.snapshot(); data.update(invocation_status=status, error=error)
        self._commit(data, f'invocation:{status}')

    def set_delivery(self,path):
        path=run_path(self.run_dir,path)
        if path!=self.run_dir/'production/delivery.json':raise ProductionRefused('delivery transaction path differs')
        from .production_delivery_records import validate_delivery_transaction
        validate_delivery_transaction(read_json(path),self.run_dir)
        data=self.snapshot()
        if data['delivery'] is not None and data['delivery']!=str(path):raise ProductionRefused('cannot replace delivery identity')
        if data['delivery'] is None:
            data['delivery']=str(path);self._commit(data,'delivery:transaction')

    def write_checkpoint(self, stage, unit_id, *, outputs, request=None, payload=None):
        if stage not in STAGES: raise ProductionRefused('unknown stage')
        _unit_id(unit_id)
        data = dict(schema_version=1, execution_mode='automatic', run_id=self.run_dir.name,
                    stage=stage, unit_id=unit_id, created_at=now(), status='completed',
                    request=request, outputs=outputs, payload=payload or {})
        validate_checkpoint(data, self.run_dir, stage, unit_id)
        return self.save_exclusive(f'logs/production/checkpoints/{stage}/{unit_id.replace(":", "_")}.json', data)

    def record_unit(self, stage, unit_id, *, status, checkpoint_path=None, request=None, outputs=None, error=None):
        _unit_id(unit_id); data = self.snapshot()
        if stage != data['active_stage'] or data['stages'][stage]['status'] != 'running':
            raise ProductionRefused('unit stage must be active and running')
        group = data['units'].setdefault(stage, {})
        old = group.get(unit_id, dict(status='pending', checkpoint_path=None, request=None, outputs={}, error=None))
        record = dict(status=status, checkpoint_path=str(checkpoint_path) if checkpoint_path else None,
                      request=deepcopy(request if request is not None else old['request']),
                      outputs=deepcopy(outputs if outputs is not None else old['outputs']), error=error)
        if old['status'] in ('completed', 'failed') and old != record:
            raise ProductionRefused('cannot change terminal unit')
        if old['status'] == 'pending' and status != 'running': raise ProductionRefused('unit must start running')
        if old['status'] == 'running' and status == 'pending': raise ProductionRefused('cannot reset unit')
        previous, current = old['request'], record['request']
        if previous is not None:
            for key in ('intent_path', 'client_id'):
                if current[key] != previous[key]: raise ProductionRefused('cannot replace request identity')
            if previous['prompt_id'] is not None and current['prompt_id'] != previous['prompt_id']:
                raise ProductionRefused('cannot replace accepted prompt_id')
            transitions = {'intent': {'accepted', 'ambiguous', 'completed', 'failed'},
                           'accepted': {'ambiguous', 'completed', 'failed'}, 'ambiguous': {'accepted', 'completed', 'failed'},
                           'completed': set(), 'failed': set()}
            if current['state'] != previous['state'] and current['state'] not in transitions[previous['state']]:
                raise ProductionRefused('cannot reset request state')
        elif current is not None and current['state'] != 'intent': raise ProductionRefused('request must begin as intent')
        if status == 'completed':
            path = run_path(self.run_dir, checkpoint_path)
            checkpoint = read_json(path)
            validate_checkpoint(checkpoint, self.run_dir, stage, unit_id)
            for output in checkpoint['outputs'].values(): sync_file(run_path(self.run_dir, output['path']))
            sync_file(path)
        group[unit_id] = record; self._commit(data, f'{stage}/{unit_id}:{status}')


def process_started_at(pid):
    """Return a live process's creation FILETIME; None means absent or exited."""
    integer(pid, 'pid', 1)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4))
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == 87: return None
        raise ProductionRefused(f'cannot establish process ownership: pid={pid}, Windows error={error}')
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            raise ProductionRefused(f'cannot read process start time: pid={pid}')
        if times[1].dwHighDateTime or times[1].dwLowDateTime:
            return None
        return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
    finally: kernel.CloseHandle(handle)


class RunLock:
    def __init__(self, run_dir):
        self.run_dir = validate_run_dir(run_dir)
        self.path = run_path(self.run_dir, self.run_dir/'.make-video.lock')
        self.owner = dict(schema_version=1, execution_mode='automatic', run_id=self.run_dir.name,
                          pid=os.getpid(), process_started_at=process_started_at(os.getpid()), token=uuid4().hex)

    @contextmanager
    def _reclaim_guard(self):
        path = run_path(self.run_dir, self.run_dir/'.make-video-reclaim.lock')
        try: write_exclusive(path, self.owner)
        except FileExistsError as exc: raise ProductionRefused(f'lock reclamation already guarded: {path}') from exc
        try: yield
        finally:
            has_error = sys.exc_info()[0] is not None
            try:
                if read_json(path) != self.owner: raise ProductionRefused('reclaim guard owner changed; retained')
                run_path(self.run_dir, path).unlink()
            except (OSError, ValueError):
                if not has_error: raise

    def __enter__(self):
        if self.path.exists():
            try:
                with self._reclaim_guard():
                    owner = read_json(self.path)
                    object_fields(owner, self.owner.keys(), 'run lock')
                    if type(owner['schema_version']) is not int or owner['schema_version'] != 1 or owner['execution_mode'] != 'automatic' or owner['run_id'] != self.run_dir.name:
                        raise ProductionRefused('foreign lock identity')
                    if not isinstance(owner['token'], str) or not re.fullmatch('[0-9a-f]{32}', owner['token']): raise ProductionRefused('foreign lock token')
                    if not isinstance(owner['process_started_at'], str) or not owner['process_started_at'].isdigit(): raise ProductionRefused('invalid process start time')
                    current = process_started_at(owner['pid'])
                    if current is not None: raise ProductionRefused(f'live or reused PID lock: pid={owner["pid"]}')
                    audit = run_path(self.run_dir, self.run_dir/f'logs/production/locks/{uuid4().hex}.json')
                    write_exclusive(audit, dict(action='archive_ended_owner', owner=owner, checked_at=now()))
                    if read_json(self.path) != owner: raise ProductionRefused('lock changed while checking owner')
                    archived = run_path(self.run_dir, audit.with_suffix('.lock'))
                    os.rename(self.path, archived)
            except (OSError, ValueError) as exc:
                raise ProductionRefused(f'run lock refused: {self.path}: {exc}') from exc
        try: write_exclusive(self.path, self.owner)
        except FileExistsError as exc: raise ProductionRefused(f'run already locked: {self.path}') from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if read_json(self.path) != self.owner: raise ProductionRefused('lock owner changed; lock retained')
            run_path(self.run_dir, self.path).unlink()
        except (OSError, ValueError):
            if exc is None: raise
        return False
