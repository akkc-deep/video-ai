"""Owned small-file recovery restricted to an explicit revision freeze scope."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import os
from pathlib import Path
from uuid import uuid4

from ..config import read_json
from .manifest import now
from .production_state import ProductionRefused, object_fields
from .scene_revision_records import artifact,token,verify_artifact
from ._scene_revision_copy import file_id

_store = ContextVar('revision_freeze_store',default=None)


@contextmanager
def revision_freeze_scope(store):
    store.owned(); saved = _store.set(store)
    try: yield
    finally: _store.reset(saved)


def save_frozen_file(path,raw):
    store = _store.get()
    if store is None: return False
    store.owned(); path = store.path(path)
    relative = str(path.relative_to(store.run))
    ready_path = store.path('freeze-ready/'+token('frozen',relative)+'.json')
    wanted = dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    if ready_path.exists():
        ready = read_json(ready_path)
        object_fields(ready,('schema_version','run_id','target','staging','file_id','created_at'),'revision frozen-file ready')
        if type(ready['schema_version']) is not int or ready['schema_version']!=2 or ready['run_id']!=store.run.name or ready['target']!=wanted:
            raise ProductionRefused('revision frozen-file identity differs')
        staging = store.path(ready['staging']['path'])
        if path.exists():
            verify_artifact(wanted,root=store.run)
            if staging.exists() or file_id(path)!=ready['file_id']: raise ProductionRefused('revision frozen-file ownership differs')
            return True
        verify_artifact(ready['staging'],root=store.root)
        if file_id(staging)!=ready['file_id']: raise ProductionRefused('revision frozen staging ownership differs')
    else:
        if path.exists(): raise ProductionRefused('unowned revision frozen file exists')
        staging = store.path('freeze-staging/'+str(uuid4())+'.bin')
        staging.parent.mkdir(parents=True,exist_ok=True)
        with staging.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        ready = dict(schema_version=2,run_id=store.run.name,target=wanted,staging=artifact(staging,root=store.root),file_id=file_id(staging),created_at=now())
        store.save(ready_path,ready)
    store.owned(); path.parent.mkdir(parents=True,exist_ok=True); os.rename(staging,path)
    verify_artifact(wanted,root=store.run)
    if file_id(path)!=ready['file_id']: raise ProductionRefused('revision frozen promotion ownership differs')
    return True


def recover_options(store,path):
    ready_path = store.path('freeze-ready/'+token('frozen',str(path.relative_to(store.run)))+'.json')
    if not ready_path.exists(): return False
    ready = read_json(ready_path)
    staging = verify_artifact(ready['staging'],root=store.root)
    save_frozen_file(path,staging.read_bytes())
    return True
