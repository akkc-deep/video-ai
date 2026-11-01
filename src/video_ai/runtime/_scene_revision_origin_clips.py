"""Original gate declarations for clips outside the imported content ancestry."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path

from ..planning.production_scenes import canonical_digest
from .production_state import ProductionRefused,object_fields,integer
from .scene_revision_records import safe_path,_json

_scope=ContextVar('scene_revision_origin_clips',default=None)


@contextmanager
def origin_clip_scope(frozen,required_ids,*,all_ids):
    saved=_scope.set(dict(identity=canonical_digest(frozen.options),frozen=frozen,required=frozenset(required_ids),known=frozenset(all_ids),declarations={}))
    try:yield
    finally:_scope.reset(saved)


def source_clip_required(frozen,clip_id):
    value=_scope.get()
    return value is None or value['identity']!=canonical_digest(frozen.options) or clip_id in value['required'] or clip_id not in value['known']


def declared_artifact(store,value):
    from .scene_color_repair_records import require_production_repair_origin
    require_production_repair_origin(value)
    object_fields(value,('path','bytes','sha256'),'original declared media')
    integer(value['bytes'],'original declared media bytes',1)
    from .image_selection_records import _sha
    _sha(value['sha256'])
    return safe_path(value['path'],store.run_dir)


def media_declaration(frozen,path):
    from .scene_color_repair_records import require_production_repair_origin
    require_production_repair_origin(path)
    scope=_scope.get()
    if scope is None or scope['identity']!=canonical_digest(frozen.options):return None
    run=Path(frozen.options['script_path']).parent.parent;path=Path(path)
    if not path.is_relative_to(run) or path.suffix.lower() not in ('.png','.mp4'):return None
    parts=path.relative_to(run).parts;cid=None
    if len(parts)>=4 and parts[:2]==('production','scene-clips'):cid=parts[2]
    elif len(parts)>=6 and parts[0]=='comfy' and parts[1] in ('input','output') and parts[2:4]==(run.name,'scene_clips'):cid=parts[4]
    if cid is None or cid in scope['required'] or cid not in scope['known']:return None
    if cid not in scope['declarations']:
        folder=run/'production/scene-clips'/cid
        if not (folder/'clip.json').is_file():return None
        declarations={}
        for relative in ('clip.json','input.json','last-frame.json','submission.json',
                'media-ready/input.json','media-ready/generated.json','media-ready/source.json','media-ready/last_frame.json'):
            record=folder/relative
            if not record.is_file():continue
            value=_json(record,root=run)
            if not isinstance(value,dict):raise ProductionRefused('original clip protocol is not an object')
            for role in ('generated','source','target','staging','image','output'):
                media=value.get(role)
                if isinstance(media,dict) and set(media)=={'path','bytes','sha256'}:
                    safe_path(media['path'],run)
                    previous=declarations.get(media['path'])
                    if previous is not None and previous!=media:raise ProductionRefused('original media declarations conflict')
                    declarations[media['path']]=deepcopy(media)
        scope['declarations'][cid]=declarations
    return deepcopy(scope['declarations'][cid].get(str(path)))


def declared_observation_media(run,value):
    scope=_scope.get()
    if scope is not None:
        frozen=scope['frozen']
        if Path(frozen.options['script_path']).parent.parent==Path(run):
            declared=media_declaration(frozen,value['path'])
            if declared is not None:
                if declared!=value:raise ProductionRefused('original observation media declaration differs')
                return True
    from ._scene_revision_origin_images import declared_observation_image
    return declared_observation_image(run,value)
