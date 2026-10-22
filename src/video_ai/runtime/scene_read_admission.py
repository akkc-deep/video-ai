"""Context-local semantic admissions retain their original immutable byte guards."""
from copy import deepcopy

from ..planning.production_scenes import canonical_digest
from .manifest import thaw
from .production_state import ArtifactStamp,ProductionRefused


def _identity(context):
    frozen=context['frozen']
    values={name:context.get(name) for name in ('units','inputs','scene_clips','image_acceptance',
        'composition_inputs','upscaled','contributions','materialized','subtitle_settings','subtitle_events')}
    values.update(options=thaw(frozen.options),config=thaw(frozen.config.raw),timeline=context['timeline'].as_dict())
    return canonical_digest(thaw(values))


def cached_admission(context,name):
    entry=context.get('_read_admissions',{}).get(name)
    if entry is None:return None
    if entry['frozen'] is not context['frozen'] or entry['identity']!=_identity(context):
        raise ProductionRefused('admitted scene context changed')
    if entry['store'] is not context.get('composition_store'):
        raise ProductionRefused('admitted scene store changed')
    for store in (context['store'],entry['store']):
        store.verify_captured_bytes();store.verify_tools()
    for stamp in context['frozen'].options['model_stamps'].values():ArtifactStamp.from_dict(thaw(stamp)).verify()
    return deepcopy(entry['value'])


def remember_admission(context,name,value):
    context.setdefault('_read_admissions',{})[name]=dict(identity=_identity(context),frozen=context['frozen'],
        store=context['composition_store'],value=deepcopy(value))


def merge_bound_guards(target,source):
    """Merge already-admitted baselines; callers recheck both sides around this."""
    for path,value in source.guard_paths.items():
        if path in target.guard_empty_paths or path in target.guard_absent_paths:
            raise ProductionRefused('admitted positive evidence conflicts with absent/empty guard')
        previous=target.guard_paths.get(path)
        if previous is not None and previous!=value:raise ProductionRefused('admitted evidence baseline changed')
        target.guard_paths.setdefault(path,deepcopy(value))
    for path,inventory in source.guard_directories.items():
        previous=target.guard_directories.get(path)
        if previous is not None and set(previous)!=set(inventory):raise ProductionRefused('admitted inventory baseline changed')
        target.guard_directories.setdefault(path,set(inventory))
    for field in ('guard_empty_paths','guard_absent_paths'):
        if any(path in target.guard_paths for path in getattr(source,field)):
            raise ProductionRefused('admitted absent/empty evidence conflicts with positive guard')
        getattr(target,field).update(getattr(source,field))
