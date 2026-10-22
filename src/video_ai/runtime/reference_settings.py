"""Bind optional reference-stage settings once without rewriting frozen inputs."""
import hashlib
from pathlib import Path

from ..adapters.common import strict_json
from ..adapters.jimeng import encode_body
from ..config import read_json
from ..reference_config import (REFERENCE_FIELDS, ReferenceConfigurationRequired, choose_reference_model,
                                parse_capability_paths, parse_reference_storage, require_url_budget)
from .manifest import thaw, validate_run_dir
from .production_inputs import _same_json, load_frozen_inputs
from .production_state import ProductionRefused, object_fields, run_path

SETTINGS_FIELDS = ('schema_version run_id frozen_options_sha256 config_source_sha256 model_settings '
                   'capability capability_sha256 storage').split()


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _run(frozen):
    run = validate_run_dir(Path(frozen.options['script_path']).parent.parent)
    if frozen.config.production_strategy != 'paragraph_jimeng_v1' or not _same_json(load_frozen_inputs(run), frozen):
        raise ProductionRefused('reference settings frozen identity differs')
    return run


def _options(frozen, supplement):
    values = {key: thaw(frozen.config.raw.get(key)) for key in REFERENCE_FIELDS}
    if supplement is not None:
        object_fields(supplement, REFERENCE_FIELDS, 'reference settings supplement')
        for key, value in supplement.items():
            if values[key] is not None and not _same_json(values[key], value):
                raise ProductionRefused('reference supplement cannot replace frozen configuration')
            if values[key] is None: values[key] = value
    return values


def _choose(frozen, values, capability_bytes):
    from ..reference_config import parse_capability
    capabilities = {}
    for key, raw in capability_bytes.items():
        try: capabilities[key] = parse_capability(strict_json(raw), req_key=key)
        except ValueError: continue
    model, cap = choose_reference_model(frozen.config.image_generation, values['reference_generation'], capabilities)
    storage = parse_reference_storage(values['reference_storage'])
    require_url_budget(model, storage)
    return model, cap, storage


def _expected(frozen, run, source_raw, model, cap, storage, cap_raw):
    return dict(schema_version=2, run_id=run.name, frozen_options_sha256=_digest(encode_body(frozen.options)),
                config_source_sha256=_digest(source_raw) if source_raw is not None else None,
                model_settings=thaw(model), capability=cap, capability_sha256=_digest(cap_raw), storage=storage)


def _bytes(store, path, raw):
    path = run_path(store.run, path); store.owned()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw: raise ProductionRefused('immutable reference settings source differs')
    else: store.image(path, raw)


def load_reference_settings(frozen):
    from ._scene_revision_origins import inherited,run_of
    imported = inherited(frozen,'reference_settings','all')
    if imported is not None:
        if (run_of(frozen)/'production/reference-images/settings.json').exists():
            raise ProductionRefused('owned reference settings competes with import')
        return imported
    run = _run(frozen); folder = run/'production/reference-images'
    marker = read_json(run_path(run, folder/'settings.json'))
    object_fields(marker, SETTINGS_FIELDS, 'reference settings')
    source_raw = None
    if marker['config_source_sha256'] is not None:
        source_raw = run_path(run, folder/'config-source.json').read_bytes()
        if _digest(source_raw) != marker['config_source_sha256']:
            raise ProductionRefused('reference configuration source SHA256 differs')
    supplement = strict_json(source_raw) if source_raw is not None else None
    values = _options(frozen, supplement)
    paths = parse_capability_paths(values['reference_capabilities'])
    raws = {}
    for key in paths:
        identity = frozen.options['execution_policy']['input_identities'].get('reference_capability/'+key)
        path = Path(identity['path']) if identity else folder/'capabilities'/(key+'.json')
        path = run_path(run, path)
        if path.exists(): raws[key] = path.read_bytes()
    try:
        model, cap, storage = _choose(frozen, values, raws)
        expected = _expected(frozen, run, source_raw, model, cap, storage, raws[model.req_key])
        if run_path(run, folder/'capability.json').read_bytes() != raws[model.req_key]:
            raise ProductionRefused('bound capability source differs')
        if not _same_json(marker, expected): raise ProductionRefused('immutable reference settings identity differs')
    except (KeyError, TypeError, ValueError) as exc:
        raise ProductionRefused('reference settings or capability identity differs') from exc
    return marker


def bind_reference_settings(frozen, *, store, reference_settings_path=None):
    from ._scene_revision_origins import inherited
    imported = inherited(frozen,'reference_settings','all')
    if imported is not None:
        if reference_settings_path is not None:
            raw = Path(reference_settings_path).read_bytes()
            if _digest(raw)!=imported['config_source_sha256']: raise ProductionRefused('reference settings import cannot be replaced')
        store.owned()
        return load_reference_settings(frozen)
    run = _run(frozen); folder = run/'production/reference-images'
    store.owned()
    if (folder/'settings.json').exists():
        result = load_reference_settings(frozen)
        if reference_settings_path is not None:
            raw = Path(reference_settings_path).read_bytes()
            if result['config_source_sha256'] != _digest(raw):
                raise ProductionRefused('reference configuration already bound; create a revision run')
        return result
    source_raw = None
    if reference_settings_path is not None:
        try: source_raw = Path(reference_settings_path).read_bytes(); supplement = strict_json(source_raw)
        except (OSError, ValueError):
            raise ReferenceConfigurationRequired('reference settings file unavailable or invalid') from None
    else: supplement = None
    values = _options(frozen, supplement)
    paths = parse_capability_paths(values['reference_capabilities'])
    raws = {}
    for key, source in paths.items():
        identity = frozen.options['execution_policy']['input_identities'].get('reference_capability/'+key)
        path = Path(identity['path']) if identity else Path(source)
        try: raws[key] = path.read_bytes()
        except OSError: continue
    # Only verified exact-schema profiles may be copied into the run, including unused profiles.
    from ..reference_config import parse_capability
    for key in list(raws):
        try: parse_capability(strict_json(raws[key]), req_key=key)
        except ValueError: del raws[key]
    model, cap, storage = _choose(frozen, values, raws)
    result = _expected(frozen, run, source_raw, model, cap, storage, raws[model.req_key])
    # All local validation precedes the immutable marker and any external I/O.
    if source_raw is not None: _bytes(store, folder/'config-source.json', source_raw)
    for key, raw in raws.items(): _bytes(store, folder/'capabilities'/(key+'.json'), raw)
    _bytes(store, folder/'capability.json', raws[model.req_key])
    folder.mkdir(parents=True, exist_ok=True)
    store.save(folder/'settings.json', result)
    return load_reference_settings(frozen)
