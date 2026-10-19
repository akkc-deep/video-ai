"""Schema-2 delivery files: immutable attempts, file ownership, receipt last."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import re
import shutil
import sys
from uuid import uuid4

from ..config import read_json
from ..jimeng_config import STRATEGY
from ..planning.production_scenes import canonical_digest
from .manifest import now
from .production_state import (ProductionRefused,integer,object_fields,process_started_at,
                               run_path,timestamp,write_exclusive,json_bytes)
from .production_delivery_records import output_path,validate_targets,file_identity,validate_file_id

ROLES=('movie','subtitle','receipt')
TX_FIELDS=('schema_version production_strategy run_id transaction_id created_at updated_at status lock_record '
           'composition_sha256 acceptance_sha256 sources output_paths operations receipt').split()
OP_FIELDS='status temp_path file_id temp output archives'.split()
RECEIPT_FIELDS=('schema_version production_strategy run_id transaction_id delivered_at composition_sha256 '
                'final_observation_acceptance_sha256 scene_clips_sha256 image_acceptance_sha256 movie subtitle '
                'media technical_checks actual_final_video_consistency full_narration subtitles').split()


def boundary(event,role):
    """Durable caller-thread interruption boundary."""


def _equal(actual,expected,label):
    if canonical_digest(actual)!=canonical_digest(expected): raise ProductionRefused(label+' differs')


def _token(value):
    if not isinstance(value,str) or re.fullmatch('[0-9a-f]{32}',value) is None: raise ProductionRefused('invalid UUID token')


def _write_guard(store):
    getattr(store,'assert_write',store.assert_owned)()


def _header(value,run):
    _equal({k:value[k] for k in ('schema_version','production_strategy','run_id')},
           dict(schema_version=2,production_strategy=STRATEGY,run_id=run.name),'scene delivery header')


def _owner(value,run,movie):
    object_fields(value,'schema_version production_strategy run_id pid process_started_at token target_movie'.split(),'scene output lock owner')
    _header(value,run);integer(value['pid'],'output lock PID',1);_token(value['token'])
    if not isinstance(value['process_started_at'],str) or not value['process_started_at'].isdigit(): raise ProductionRefused('invalid output process start')
    if output_path(value['target_movie'])!=movie: raise ProductionRefused('output lock target differs')


class SceneOutputLock:
    def __init__(self,store,source,movie):
        self.store=store;self.run=store.run_dir;self.movie=output_path(movie)
        self.path=self.movie.with_name('.'+self.movie.stem+'.make-video.lock')
        self.owner=dict(schema_version=2,production_strategy=STRATEGY,run_id=self.run.name,pid=os.getpid(),
            process_started_at=process_started_at(os.getpid()),token=uuid4().hex,target_movie=str(self.movie))
        self.intent_path=store.path('locks/'+self.owner['token']+'.json')

    @property
    def record(self): return dict(owner=deepcopy(self.owner),intent_path=str(self.intent_path),lock_path=str(self.path))

    def check(self):
        self.store.assert_owned()
        _equal(read_json(output_path(self.path)),self.owner,'held scene output lock')

    @contextmanager
    def _reclaim_guard(self):
        guard=output_path(self.path.with_name(self.path.name+'.reclaim'))
        _write_guard(self.store)
        try:write_exclusive(guard,self.owner)
        except FileExistsError as exc:raise ProductionRefused('output reclaim already guarded') from exc
        try:yield
        finally:
            active=sys.exc_info()[0] is not None
            try:
                _write_guard(self.store);_equal(read_json(guard),self.owner,'output reclaim owner');guard.unlink()
            except Exception:
                if not active:raise

    def __enter__(self):
        _write_guard(self.store);self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists():
            with self._reclaim_guard():
                owner=read_json(output_path(self.path));_owner(owner,self.run,self.movie)
                intent_path=self.store.path('locks/'+owner['token']+'.json')
                intent=read_json(intent_path)
                object_fields(intent,('owner','lock_path','created_at'),'scene output lock intent');timestamp(intent['created_at'])
                _equal(intent['owner'],owner,'old output lock intent');_equal(intent['lock_path'],str(self.path),'old output lock path')
                if process_started_at(owner['pid']) is not None: raise ProductionRefused('live or reused PID output lock')
                self.store.write('reclaims/'+uuid4().hex+'.json',dict(owner=owner,lock_path=str(self.path),checked_at=now(),action='archive_ended_owner'))
                _write_guard(self.store);_equal(read_json(self.path),owner,'output owner during reclaim')
                os.rename(output_path(self.path),output_path(self.path.with_name(self.path.name+'.'+uuid4().hex+'.archive')))
        self.store.write(self.intent_path,dict(owner=self.owner,lock_path=str(self.path),created_at=now()))
        _write_guard(self.store)
        try:write_exclusive(output_path(self.path),self.owner)
        except FileExistsError as exc:raise ProductionRefused('output is already locked') from exc
        self.check();return self

    def __exit__(self,kind,exc,tb):
        try:self.check();_write_guard(self.store);output_path(self.path).unlink()
        except Exception as cleanup:
            if exc is None:raise
            exc.add_note('output lock cleanup failed: '+str(cleanup))
        return False


def _stage(context):
    store=context['store']
    return store if store.root==store.run_dir/'production/scene-delivery' else store.for_root('production/scene-delivery')


def _artifact(path):
    path=output_path(path)
    with path.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
        size=os.fstat(stream.fileno()).st_size
    integer(size,'delivery Artifact bytes',1)
    return dict(path=str(path),bytes=size,sha256=digest)


def _validate_artifact(value,*,expected_path=None):
    object_fields(value,('path','bytes','sha256'),'delivery Artifact');integer(value['bytes'],'Artifact bytes',1)
    if not isinstance(value['sha256'],str) or re.fullmatch('[0-9a-f]{64}',value['sha256']) is None: raise ProductionRefused('invalid artifact SHA')
    path=output_path(value['path'])
    if expected_path is not None and path!=expected_path: raise ProductionRefused('delivery Artifact path differs')
    _equal(_artifact(path),value,'delivery Artifact bytes');return path


def _temporary(targets,run,txid,role):
    target=output_path(targets[role]);return str(target.with_name('.'+target.stem+'.'+run.name+'.'+txid+'.'+role+'.'+uuid4().hex+'.tmp'))


def _temp_path(value,targets,run,txid,role):
    path=output_path(value);target=targets[role]
    pattern=r'\.'+re.escape(target.stem)+r'\.'+re.escape(run.name)+r'\.'+txid+r'\.'+role+r'\.[0-9a-f]{32}\.tmp'
    if path.parent!=target.parent or re.fullmatch(pattern,path.name) is None: raise ProductionRefused('temporary role or directory differs')
    return path


def _source(tx,role):
    return canonical_digest(tx['receipt']) if role=='receipt' else tx['sources']['candidate' if role=='movie' else 'subtitle']


def _attempts(store,tx,targets):
    result={};folder=store.path('temp-attempts')
    if not folder.exists():return result
    for path in folder.glob('*.json'):
        if not path.is_file():raise ProductionRefused('invalid delivery attempt entry')
        _token(path.stem);value=store.read(path)
        object_fields(value,'schema_version run_id transaction_id role temp_path source created_at'.split(),'delivery temporary attempt')
        timestamp(value['created_at'])
        _equal({k:value[k] for k in ('schema_version','run_id','transaction_id')},
               dict(schema_version=2,run_id=store.run_dir.name,transaction_id=tx['transaction_id']),'temporary attempt identity')
        role=value['role']
        if role not in ROLES or (role=='receipt' and tx['receipt'] is None):raise ProductionRefused('temporary attempt source absent')
        _temp_path(value['temp_path'],targets,store.run_dir,tx['transaction_id'],role)
        _equal(value['source'],_source(tx,role),'temporary attempt source')
        if value['temp_path'] in result: raise ProductionRefused('duplicate temporary attempt path')
        result[value['temp_path']]=value
    return result


def _owned(path,op,artifact):
    if file_identity(path)!=op['file_id']:raise ProductionRefused('delivery file ownership differs')
    actual=_artifact(path)
    _equal({k:actual[k] for k in ('bytes','sha256')},{k:artifact[k] for k in ('bytes','sha256')},'owned delivery bytes')


def _expected_receipt(context,candidate,acceptance,tx):
    return dict(schema_version=2,production_strategy=STRATEGY,run_id=context['store'].run_dir.name,
        transaction_id=tx['transaction_id'],delivered_at=tx['receipt']['delivered_at'] if tx['receipt'] else now(),
        composition_sha256=canonical_digest(candidate),final_observation_acceptance_sha256=canonical_digest(acceptance),
        scene_clips_sha256=canonical_digest(context['scene_clips']),image_acceptance_sha256=canonical_digest(context['image_acceptance']),
        movie=deepcopy(tx['operations']['movie']['output']),subtitle=deepcopy(tx['operations']['subtitle']['output']),
        media=dict(width=1920,height=1080,fps=16,frames=context['timeline'].total_frames,audio_sample_rate=48000,audio_channels=1),
        technical_checks=deepcopy(candidate['technical_checks']),actual_final_video_consistency='passed',full_narration='passed',subtitles='passed')


def validate_transaction(context,candidate,acceptance,tx):
    """Validate a partial or complete transaction against admitted source identities."""
    store=_stage(context);run=store.run_dir
    object_fields(tx,TX_FIELDS,'scene delivery transaction');_header(tx,run);_token(tx['transaction_id'])
    timestamp(tx['created_at']);timestamp(tx['updated_at'])
    if tx['status'] not in ('publishing','completed'):raise ProductionRefused('invalid transaction status')
    targets=validate_targets(tx['output_paths'],run,frozen=context['frozen'])
    _equal(tx['composition_sha256'],canonical_digest(candidate),'delivery composition')
    _equal(tx['acceptance_sha256'],canonical_digest(acceptance),'delivery acceptance')
    _equal(tx['sources'],{k:candidate[k] for k in ('candidate','subtitle')},'delivery sources')
    for value in tx['sources'].values():store.validate_artifact(value)
    record=tx['lock_record'];object_fields(record,('owner','intent_path','lock_path'),'scene transaction lock')
    _owner(record['owner'],run,targets['movie'])
    lock_path=targets['movie'].with_name('.'+targets['movie'].stem+'.make-video.lock')
    _equal(record['lock_path'],str(lock_path),'transaction output lock path')
    intent_path=store.path('locks/'+record['owner']['token']+'.json')
    if run_path(run,record['intent_path'])!=intent_path:raise ProductionRefused('lock intent path differs')
    intent=store.read(intent_path);object_fields(intent,('owner','lock_path','created_at'),'lock intent');timestamp(intent['created_at'])
    _equal(intent['owner'],record['owner'],'transaction lock intent owner');_equal(intent['lock_path'],record['lock_path'],'transaction lock intent path')
    object_fields(tx['operations'],ROLES,'delivery operations');attempts=_attempts(store,tx,targets)
    prior=True
    for role in ROLES:
        op=tx['operations'][role];object_fields(op,OP_FIELDS,'delivery operation')
        if op['status'] not in ('pending','prepared','published'):raise ProductionRefused('invalid delivery operation state')
        if not prior and op['status']!='pending':raise ProductionRefused('publication order differs')
        temp=_temp_path(op['temp_path'],targets,run,tx['transaction_id'],role)
        if op['file_id'] is not None:validate_file_id(op['file_id'])
        if not isinstance(op['archives'],list):raise ProductionRefused('delivery archives must be array')
        for artifact in op['archives']:
            archived=_temp_path(artifact['path'],targets,run,tx['transaction_id'],role)
            if str(archived) not in attempts or archived==temp:raise ProductionRefused('archive lacks original attempt')
            _validate_artifact(artifact,expected_path=archived)
        if op['status']=='pending':
            if op['temp'] is not None or op['output'] is not None:raise ProductionRefused('pending delivery contains prepared bytes')
            if op['file_id'] is not None:
                if str(temp) not in attempts or not temp.exists() or file_identity(temp)!=op['file_id']:
                    raise ProductionRefused('known interrupted temporary ownership changed')
            if targets[role].exists():raise ProductionRefused('unowned output already exists')
        else:
            if op['file_id'] is None or str(temp) not in attempts:raise ProductionRefused('prepared output lacks durable file identity/attempt')
            object_fields(op['temp'],('path','bytes','sha256'),'prepared temporary')
            if op['temp']['path']!=str(temp):raise ProductionRefused('prepared temporary path differs')
            if op['status']=='prepared':
                if op['output'] is not None:raise ProductionRefused('prepared cursor ahead of output')
                if temp.exists() and targets[role].exists():raise ProductionRefused('temporary and target both exist')
                actual=temp if temp.exists() else targets[role]
                if not actual.exists():raise ProductionRefused('prepared temporary and target missing')
                _owned(actual,op,op['temp'])
            else:
                if temp.exists():raise ProductionRefused('published temporary unexpectedly exists')
                _validate_artifact(op['output'],expected_path=targets[role]);_owned(targets[role],op,op['temp'])
            expected=json_bytes(tx['receipt']) if role=='receipt' else None
            stamp=op['temp']
            if role=='receipt':
                if tx['receipt'] is None or stamp['bytes']!=len(expected) or stamp['sha256']!=hashlib.sha256(expected).hexdigest():
                    raise ProductionRefused('prepared receipt bytes differ')
            else:
                source=tx['sources']['candidate' if role=='movie' else 'subtitle']
                _equal({k:stamp[k] for k in ('bytes','sha256')},{k:source[k] for k in ('bytes','sha256')},'published source bytes')
        prior=prior and op['status']=='published'
    if tx['receipt'] is not None:
        object_fields(tx['receipt'],RECEIPT_FIELDS,'scene delivery receipt');timestamp(tx['receipt']['delivered_at'])
        if any(tx['operations'][r]['status']!='published' for r in ('movie','subtitle')):raise ProductionRefused('receipt precedes media')
        _equal(tx['receipt'],_expected_receipt(context,candidate,acceptance,tx),'scene receipt')
    if tx['status']=='completed' and (not prior or tx['receipt'] is None):raise ProductionRefused('completed transaction lacks all outputs')
    return tx


def _save(store,tx,lock,guard,*,initial=False):
    guard();lock.check();_write_guard(store);path=store.path('transaction.json')
    prior=store.read(path)
    if prior is not None and prior['status']=='completed':
        _equal(tx,prior,'immutable completed transaction');return
    if initial:store.write(path,tx)
    else:
        tx['updated_at']=now();temp=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
        store.write(temp,tx);guard();lock.check();_write_guard(store);os.replace(temp,path);lock.check()
    _equal(store.read(path),tx,'transaction readback')


def _copy(store,tx,role,stream):
    _write_guard(store)
    if role=='receipt':stream.write(json_bytes(tx['receipt']));return
    source=tx['sources']['candidate' if role=='movie' else 'subtitle'];store.validate_artifact(source)
    digest=hashlib.sha256();count=0
    with Path(source['path']).open('rb') as original:
        while raw:=original.read(1024*1024):
            _write_guard(store)
            stream.write(raw);digest.update(raw);count+=len(raw)
    if count!=source['bytes'] or digest.hexdigest()!=source['sha256']:raise ProductionRefused('open source bytes changed while copying')
    store.validate_artifact(source)


def _publish_role(context,candidate,acceptance,tx,role,lock,guard):
    store=_stage(context);op=tx['operations'][role];target=output_path(tx['output_paths'][role])
    if op['status']=='published':return
    if op['status']=='pending':
        temp=output_path(op['temp_path'])
        targets=validate_targets(tx['output_paths'],store.run_dir,frozen=context['frozen'])
        prior_attempts=_attempts(store,tx,targets)
        if temp.exists() or str(temp) in prior_attempts:
            if temp.exists() and op['file_id'] is not None:
                if file_identity(temp)!=op['file_id']:raise ProductionRefused('interrupted temporary owner changed')
                if temp.stat().st_size:op['archives'].append(_artifact(temp))
            # Unknown exclusive-create crash files remain untouched with original intent.
            op.update(temp_path=_temporary(tx['output_paths'],store.run_dir,tx['transaction_id'],role),file_id=None)
            _save(store,tx,lock,guard);temp=output_path(op['temp_path'])
        guard();lock.check()
        attempt=dict(schema_version=2,run_id=store.run_dir.name,transaction_id=tx['transaction_id'],role=role,
                     temp_path=str(temp),source=deepcopy(_source(tx,role)),created_at=now())
        store.write('temp-attempts/'+uuid4().hex+'.json',attempt);boundary('temp-attempt',role)
        guard();lock.check()
        if target.exists():raise ProductionRefused('foreign output before temporary creation')
        _write_guard(store)
        with temp.open('xb') as stream:
            boundary('temp-created',role)
            stat=os.fstat(stream.fileno());op['file_id']=dict(device=stat.st_dev,inode=stat.st_ino)
            _save(store,tx,lock,guard)
            _copy(store,tx,role,stream);_write_guard(store);stream.flush();os.fsync(stream.fileno());boundary('temp-fsynced',role)
        guard();lock.check();op.update(status='prepared',temp=_artifact(temp))
        _save(store,tx,lock,guard);boundary('prepared',role)
    if op['status']=='prepared':
        validate_transaction(context,candidate,acceptance,tx);guard();lock.check();temp=output_path(op['temp_path'])
        if temp.exists():
            if target.exists():raise ProductionRefused('foreign target before no-overwrite rename')
            _owned(temp,op,op['temp']);guard();lock.check()
            _write_guard(store)
            # Windows rename is atomic and fails if the target exists.
            os.rename(output_path(temp),output_path(target));boundary('renamed',role)
        _owned(target,op,op['temp']);guard();lock.check()
        op.update(status='published',output=_artifact(target));_save(store,tx,lock,guard);boundary('published',role)


def publish(context,candidate,acceptance,lock,guard):
    store=_stage(context);tx=store.read('transaction.json')
    if tx is None:
        targets=dict(context['frozen'].options['output_paths']);validate_targets(targets,store.run_dir,frozen=context['frozen'])
        if any(output_path(p).exists() for p in targets.values()):raise ProductionRefused('unowned formal output already exists')
        needed=candidate['candidate']['bytes']+candidate['subtitle']['bytes']+64*1024*1024
        if shutil.disk_usage(output_path(targets['movie']).parent).free<needed:raise OSError('insufficient scene delivery space')
        stamp=now();txid=uuid4().hex
        tx=dict(schema_version=2,production_strategy=STRATEGY,run_id=store.run_dir.name,transaction_id=txid,
            created_at=stamp,updated_at=stamp,status='publishing',lock_record=lock.record,
            composition_sha256=canonical_digest(candidate),acceptance_sha256=canonical_digest(acceptance),
            sources={k:deepcopy(candidate[k]) for k in ('candidate','subtitle')},output_paths=targets,
            operations={role:dict(status='pending',temp_path=_temporary(targets,store.run_dir,txid,role),file_id=None,temp=None,output=None,archives=[]) for role in ROLES},receipt=None)
        _save(store,tx,lock,guard,initial=True)
    validate_transaction(context,candidate,acceptance,tx)
    if tx['status']=='completed':return tx['receipt']
    for role in ROLES:
        guard();lock.check()
        if role=='receipt' and tx['receipt'] is None:
            tx['receipt']=_expected_receipt(context,candidate,acceptance,tx);_save(store,tx,lock,guard);boundary('receipt-ready',role)
        _publish_role(context,candidate,acceptance,tx,role,lock,guard)
    validate_transaction(context,candidate,acceptance,tx);guard();lock.check()
    tx['status']='completed';_save(store,tx,lock,guard);boundary('completed','receipt')
    return validate_completed(context,candidate,acceptance)


def validate_delivery_state(context,*,candidate=None,acceptance=None):
    if candidate is None:
        from .production_scene_composition import require_scene_composition_record
        candidate=require_scene_composition_record(context)
    if acceptance is None:
        from .production_scene_delivery import require_scene_final_acceptance_record
        acceptance=require_scene_final_acceptance_record(context)
    store=_stage(context);tx=store.read('transaction.json')
    if tx is None:
        if store.root.exists() and any(p.name not in ('locks','reclaims') for p in store.root.iterdir()):
            raise ProductionRefused('delivery evidence lacks original transaction')
        return None
    return validate_transaction(context,candidate,acceptance,tx)


def validate_completed(context,candidate,acceptance):
    tx=validate_delivery_state(context,candidate=candidate,acceptance=acceptance)
    if tx is None or tx['status']!='completed':raise ProductionRefused('complete scene delivery missing')
    path=output_path(tx['output_paths']['receipt'])
    if path.read_bytes()!=json_bytes(tx['receipt']):raise ProductionRefused('external receipt bytes differ')
    _equal(read_json(path),tx['receipt'],'external receipt')
    return deepcopy(tx['receipt'])
