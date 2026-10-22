"""Durable identity copies; same bytes do not prove ownership of a target."""
import os
from pathlib import Path
import re
import shutil
from threading import get_ident
from uuid import uuid4

from ..config import read_json
from .manifest import now
from .production_state import ProductionRefused, RunLock, json_bytes
from .scene_revision_records import artifact, safe_path, token, verify_artifact

READY_FIELDS=('schema_version run_id import_id role intent source staging target file_id recipe created_at').split()
INTENT_FIELDS=('schema_version run_id import_id role source staging_path target_path created_at').split()


def preflight_copies(root,run_id,*,expected=None):
    """Audit every durable receipt, including receipts outside the requested role."""
    from .production_state import object_fields,integer,timestamp
    from uuid import UUID
    root=Path(root)
    for path in (root/'copy-intents').glob('*.json'):
        safe_path(path,root);intent=read_json(path);object_fields(intent,INTENT_FIELDS,'revision copy intent')
        if type(intent['schema_version']) is not int or intent['schema_version']!=2 or intent['run_id']!=run_id:
            raise ProductionRefused('copy intent identity differs')
        if str(UUID(path.stem))!=path.stem:raise ProductionRefused('copy intent UUID differs')
        safe_path(intent['staging_path'],root/'staging');safe_path(intent['target_path'],root/'media')
        timestamp(intent['created_at'])
    for path in (root/'copy-ready').rglob('*.json'):
        safe_path(path,root);ready=read_json(path);object_fields(ready,READY_FIELDS,'revision copy-ready')
        domain,separator,key=ready['import_id'].partition(':')
        role=ready['role']
        if (type(ready['schema_version']) is not int or ready['schema_version']!=2 or ready['run_id']!=run_id
                or not separator or not key or domain not in ('common','image','choice','clip','upscale')
                or not re.fullmatch(r'(?:pcm_[0-9]{6}|generated|source|first_frame|last_frame|input|input_copy|model_output|output|selected_image|candidate_[0-9]{6}|comparison_[0-9]{6})',role)
                or path!=root/'copy-ready'/token(domain,key)/(role+'.json')
                or ready['recipe']!=dict(algorithm='identity_revision_copy_v1',parameters={})):
            raise ProductionRefused('copy-ready identity differs')
        if expected is not None and str(path) not in expected:raise ProductionRefused('orphan copy-ready receipt')
        timestamp(ready['created_at'])
        intent_path=verify_artifact(ready['intent'],root=root/'copy-intents');intent=read_json(intent_path)
        object_fields(intent,INTENT_FIELDS,'revision copy intent')
        if intent!=dict(schema_version=2,run_id=run_id,import_id=ready['import_id'],role=role,source=ready['source'],
                staging_path=ready['staging']['path'],target_path=ready['target']['path'],created_at=ready['created_at']):
            raise ProductionRefused('copy intent identity differs')
        object_fields(ready['file_id'],('device','inode'),'copy file ID')
        for value in ready['file_id'].values():integer(value,'copy file ID',0)
        for value in (ready['staging'],ready['target']):
            if any(value[k]!=ready['source'][k] for k in ('bytes','sha256')):raise ProductionRefused('copy-ready bytes differ')
        suffix=Path(ready['source']['path']).suffix.lower()
        if Path(ready['target']['path'])!=root/'media'/domain/token(domain,key)/(role+suffix):
            raise ProductionRefused('copy-ready target differs')
        staging=safe_path(ready['staging']['path'],root/'staging');target=safe_path(ready['target']['path'],root/'media')
        if staging.exists()==target.exists():raise ProductionRefused('copy-ready staging/target ownership differs')
        current=target if target.exists() else staging
        verify_artifact(ready['target'] if target.exists() else ready['staging'],root=root)
        if file_id(current)!=ready['file_id']:raise ProductionRefused('copy-ready file ownership differs')


def boundary(point):
    """Caller-thread fault injection only."""


def file_id(path):
    s = Path(path).stat()
    return dict(device=s.st_dev,inode=s.st_ino)


class RevisionStore:
    def __init__(self,run,lock):
        self.run = Path(run); self.root = self.run/'production/scene-revision'; self.lock = lock
        self.caller_thread = get_ident()

    def owned(self):
        if get_ident()!=self.caller_thread: raise ProductionRefused('revision write requires caller thread')
        if not isinstance(self.lock,RunLock) or self.lock.run_dir != self.run or read_json(self.lock.path) != self.lock.owner:
            raise ProductionRefused('revision lost held target lock')

    def path(self,relative):
        value = Path(relative)
        return safe_path(value if value.is_absolute() else self.root/value,self.run)

    def image(self,path,raw):
        self.owned(); path = self.path(path)
        if path.exists():
            if path.read_bytes() != raw: raise ProductionRefused('immutable revision bytes differ')
            return path
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary = path.with_name(path.name+'.'+uuid4().hex+'.tmp')
        with temporary.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        self.owned(); os.rename(temporary,path); self.owned()
        return path

    def save(self,path,value): return self.image(path,json_bytes(value))


def copy_identity(store,import_id,domain,key,role,source,*,guard):
    store.owned(); guard.verify_captured_bytes()
    if not getattr(store,'copies_preflighted',False):
        preflight_copies(store.root,store.run.name);store.copies_preflighted=True
    if not re.fullmatch(r'(?:pcm(?:_[0-9]{6})?|generated|source|first_frame|last_frame|input|input_copy|model_output|output|selected_image|candidate_[0-9]{6}|comparison_[0-9]{6})',role):
        raise ProductionRefused('invalid revision media role')
    suffix = Path(source['path']).suffix.lower()
    if not re.fullmatch(r'\.[a-z0-9]{1,12}',suffix): raise ProductionRefused('invalid source extension')
    target = store.path(Path('media')/domain/token(domain,key)/(role+suffix))
    ready_path = store.path(Path('copy-ready')/token(domain,key)/(role+'.json'))
    if ready_path.exists():
        ready = read_json(ready_path)
        from .production_state import object_fields
        object_fields(ready,('schema_version run_id import_id role intent source staging target file_id recipe created_at').split(),'revision copy-ready')
        if (ready['schema_version'] != 2 or type(ready['schema_version']) is not int or ready['run_id'] != store.run.name
                or ready['import_id'] != import_id or ready['role'] != role or ready['source'] != source
                or ready['target']['path'] != str(target) or ready['recipe'] != dict(algorithm='identity_revision_copy_v1',parameters={})):
            raise ProductionRefused('copy-ready identity differs')
        intent_path = verify_artifact(ready['intent'],root=store.root)
        intent = read_json(intent_path)
        object_fields(intent,('schema_version run_id import_id role source staging_path target_path created_at').split(),'revision copy intent')
        expected = dict(schema_version=2,run_id=store.run.name,import_id=import_id,role=role,source=source,
            staging_path=ready['staging']['path'],target_path=str(target),created_at=ready['created_at'])
        if intent != expected: raise ProductionRefused('copy intent identity differs')
        staging = store.path(ready['staging']['path'])
        if target.exists():
            if staging.exists(): raise ProductionRefused('copy target and original staging coexist')
            verify_artifact(ready['target'],root=store.root)
            if file_id(target) != ready['file_id']: raise ProductionRefused('revision target file ownership differs')
            guard.verify_captured_bytes(); return ready['target']
        verify_artifact(ready['staging'],root=store.root)
        if file_id(staging) != ready['file_id']: raise ProductionRefused('staging file ownership differs')
    else:
        if target.exists(): raise ProductionRefused('unowned revision copy target exists')
        attempt = str(uuid4()); staging = store.path(Path('staging')/(attempt+suffix))
        created = now()
        intent = dict(schema_version=2,run_id=store.run.name,import_id=import_id,role=role,source=source,
            staging_path=str(staging),target_path=str(target),created_at=created)
        intent_path = store.save('copy-intents/'+attempt+'.json',intent); boundary('copy-intent')
        staging.parent.mkdir(parents=True,exist_ok=True)
        store.owned(); guard.verify_captured_bytes()
        with Path(source['path']).open('rb') as incoming,staging.open('xb') as outgoing:
            shutil.copyfileobj(incoming,outgoing,1024*1024); outgoing.flush(); os.fsync(outgoing.fileno())
        boundary('copy-staging')
        guard.verify_captured_bytes(); copied = artifact(staging,root=store.root)
        if any(copied[k] != source[k] for k in ('bytes','sha256')): raise ProductionRefused('revision copied bytes differ')
        ready = dict(schema_version=2,run_id=store.run.name,import_id=import_id,role=role,
            intent=artifact(intent_path,root=store.root),source=source,staging=copied,
            target=dict(copied,path=str(target)),file_id=file_id(staging),
            recipe=dict(algorithm='identity_revision_copy_v1',parameters={}),created_at=created)
        store.save(ready_path,ready); boundary('copy-ready')
    store.owned(); guard.verify_captured_bytes()
    target.parent.mkdir(parents=True,exist_ok=True)
    os.rename(staging,target); boundary('copy-promoted')
    store.owned(); verify_artifact(ready['target'],root=store.root)
    if file_id(target) != ready['file_id']: raise ProductionRefused('promoted copy ownership differs')
    return ready['target']
