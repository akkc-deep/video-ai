"""Effective reference identity from verified source binding and target bytes."""
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

from ..planning.production_scenes import canonical_digest
from ..reference_config import REFERENCE_FIELDS,ReferenceConfigurationRequired,parse_capability_paths
from .manifest import thaw
from .production_state import ProductionRefused
from .scene_revision_records import require_scene_revision,stable_bytes,verify_artifact


def marker_digest(marker):
    return canonical_digest({k:marker[k] for k in ('model_settings','capability','capability_sha256','storage')})


def source_reference_context(frozen):
    """Follow an explicit settings import to its actual owned binding, locally."""
    run=Path(frozen.options['script_path']).parent.parent
    if 'scene_revision' in frozen.options:
        proof=require_scene_revision(frozen)
        if 'reference_settings:all' in proof['imports']:
            from .production_inputs import load_frozen_inputs
            result=source_reference_context(load_frozen_inputs(proof['source_run']))
            proof['guard'].verify_captured_bytes()
            return result
    folder=run/'production/reference-images'
    if not (folder/'settings.json').exists():return None
    from .reference_settings import load_reference_settings,_options
    from ..adapters.common import strict_json
    marker=load_reference_settings(frozen)
    supplement=None
    if marker['config_source_sha256'] is not None:
        raw=stable_bytes(folder/'config-source.json',root=run)
        if hashlib.sha256(raw).hexdigest()!=marker['config_source_sha256']:raise ProductionRefused('reference source bytes changed')
        supplement=strict_json(raw.removeprefix(b'\xef\xbb\xbf'))
    values=_options(frozen,supplement);raws={}
    for key in parse_capability_paths(values['reference_capabilities']):
        bound=frozen.options['execution_policy']['input_identities'].get('reference_capability/'+key)
        path=verify_artifact({k:bound[k] for k in ('path','bytes','sha256')},root=run) if bound else folder/'capabilities'/(key+'.json')
        if path.exists():raws[key]=stable_bytes(path,root=run)
    return dict(values=values,raws=raws,marker=marker,digest=marker_digest(marker))


def target_reference_digest(frozen,source_context):
    """No network/credentials; None means target still needs configuration."""
    from .reference_settings import _choose
    values={key:thaw(frozen.config.raw.get(key)) for key in REFERENCE_FIELDS}
    if source_context is not None:
        for key in REFERENCE_FIELDS:
            if values[key] is None:values[key]=deepcopy(source_context['values'][key])
    try:
        paths=parse_capability_paths(values['reference_capabilities']);raws={}
        explicit=frozen.config.raw.get('reference_capabilities') is not None
        for key,path in paths.items():
            bound=frozen.options.get('execution_policy',{}).get('input_identities',{}).get('reference_capability/'+key)
            if bound is not None:
                root=Path(frozen.options['script_path']).parent.parent
                copied=verify_artifact({k:bound[k] for k in ('path','bytes','sha256')},root=root)
                raws[key]=stable_bytes(copied,root=root)
            elif explicit:
                path=Path(path)
                if path.is_file():raws[key]=stable_bytes(path,root=path.parent)
            elif source_context is not None and key in source_context['raws']:
                raws[key]=source_context['raws'][key]
        model,cap,storage=_choose(frozen,values,raws)
        return canonical_digest(dict(model_settings=thaw(model),capability=cap,
            capability_sha256=hashlib.sha256(raws[model.req_key]).hexdigest(),storage=storage))
    except ReferenceConfigurationRequired:return None
