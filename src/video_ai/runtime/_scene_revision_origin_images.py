"""Source-only image metadata for siblings that are not admitted as content."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
import re

from ..planning.production_scenes import canonical_digest
from .production_state import ProductionRefused,object_fields,integer,run_path
from .scene_revision_records import artifact,_json

_source_images=ContextVar('scene_revision_source_images',default=None)


@contextmanager
def origin_image_scope(frozen,required_ids):
    marker=_source_images.set((canonical_digest(frozen.options),frozenset(required_ids),frozen))
    try:yield
    finally:_source_images.reset(marker)


def source_image_required(frozen,scene_id):
    scope=_source_images.get()
    return scope is None or scope[0]!=canonical_digest(frozen.options) or scene_id in scope[1]


def source_candidate_metadata(frozen,scene,manifest_path):
    if source_image_required(frozen,scene['scene_id']):return None
    from .image_selection_records import CANDIDATE_FIELDS,_sha,_nonempty
    run=Path(frozen.options['script_path']).parent.parent
    path=run/'production/jimeng'/scene['scene_id']/'candidates.json'
    if run_path(run,manifest_path)!=path:raise ProductionRefused('source metadata path differs')
    before=artifact(path,root=run);value=_json(path,root=run)
    object_fields(value,'schema_version run_id scene_id identity candidates'.split(),'source candidate metadata')
    if type(value['schema_version']) is not int or value['schema_version']!=2 or value['run_id']!=run.name or value['scene_id']!=scene['scene_id']:
        raise ProductionRefused('source candidate metadata identity differs')
    _sha(value['identity'])
    if type(value['candidates']) is not list or not value['candidates']:raise ProductionRefused('source candidate metadata missing')
    seen=set()
    for row in value['candidates']:
        object_fields(row,CANDIDATE_FIELDS,'source candidate metadata row')
        if not re.fullmatch(r'request_[0-9]{2}_image_[0-9]{2}',row['candidate_id']) or row['candidate_id'] in seen:
            raise ProductionRefused('source candidate metadata ID differs')
        seen.add(row['candidate_id']);rid=row['candidate_id'].rsplit('_image_',1)[0]
        if row['request_id']!=rid or run_path(run,row['path'])!=path.parent/rid/(row['candidate_id']+'.original'):
            raise ProductionRefused('source candidate metadata request/path differs')
        for name in ('bytes','width','height'):integer(row[name],'source candidate '+name,1)
        _sha(row['sha256'])
        for name in ('task_id','req_key','format'):_nonempty(row[name],'source candidate '+name)
    if artifact(path,root=run)!=before:raise ProductionRefused('source candidate metadata changed')
    return before,deepcopy(value['candidates'])


def source_image_artifact(frozen,value):
    """Only an excluded sibling's original declared by its exact manifest."""
    scope=_source_images.get()
    if scope is None or scope[0]!=canonical_digest(frozen.options):return None
    run=Path(frozen.options['script_path']).parent.parent;path=Path(value['path']);root=run/'production/jimeng'
    if not path.is_relative_to(root):return None
    parts=path.relative_to(root).parts
    if len(parts)!=3 or not re.fullmatch(r'request_[0-9]{2}_image_[0-9]{2}\.original',parts[2]) or source_image_required(frozen,parts[0]):return None
    metadata=source_candidate_metadata(frozen,{'scene_id':parts[0]},root/parts[0]/'candidates.json')
    if not any(all(row[k]==value[k] for k in ('path','bytes','sha256')) for row in metadata[1]):
        raise ProductionRefused('excluded sibling image differs from original batch metadata')
    return run_path(run,path)


def declared_observation_image(run,value):
    scope=_source_images.get()
    if scope is None:return False
    frozen=scope[2]
    if Path(frozen.options['script_path']).parent.parent!=Path(run):return False
    return source_image_artifact(frozen,value) is not None
