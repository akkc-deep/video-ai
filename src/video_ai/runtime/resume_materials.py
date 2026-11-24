"""Read completed production materials as saved, under the owner's immutability promise.

This is an invocation-local resume policy, not a validation result. It never
marks an observation passed or turns an unfinished request into a finished one.
New outputs and the request submission protocol keep their normal checks.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
import hashlib
import json
from pathlib import Path
from time import time_ns

from .production_state import ProductionRefused

_current = ContextVar('resume_completed_materials', default=None)


def trusting_materials():
    return _current.get() is not None


@contextmanager
def trust_existing_materials(run):
    if trusting_materials():
        yield
        return
    run = Path(run)
    state = dict(cutoff=time_ns(), json={}, revisions={}, artifacts={}, clips={})
    state['clips'][run] = {p.parent.name for p in (run/'production/scene-clips').glob('*/clip.json')}
    token = _current.set(state)
    try:
        yield
    finally:
        _current.reset(token)


def resume_existing_materials(function):
    @wraps(function)
    def invoke(*args, **kwargs):
        run = kwargs.get('run_dir')
        if run is None or kwargs.get('revision') is not None or kwargs.get('publish', False):
            return function(*args, **kwargs)
        options_path = Path(run)/'production/options.json'
        if options_path.is_file():
            try:
                options = json.loads(options_path.read_bytes())
                mode = options.get('config_snapshot', {}).get('raw', {}).get('scene_rendering', {}).get('mode')
            except (OSError, ValueError, AttributeError):
                # The ordinary loader supplies the established invalid-input result.
                return function(*args, **kwargs)
            if mode is not None:
                return function(*args, **kwargs)
        with trust_existing_materials(run):
            return function(*args, **kwargs)
    return invoke


def existing_file(path):
    state = _current.get()
    path = Path(path)
    return state is not None and path.is_file() and path.stat().st_mtime_ns <= state['cutoff']


def remember(value):
    """Remember declared artifact identities, never recalculate old media hashes."""
    state = _current.get()
    if state is None:
        return
    if isinstance(value, dict):
        if {'path', 'bytes', 'sha256'} <= value.keys():
            state['artifacts'][Path(value['path'])] = {k: value[k] for k in ('path', 'bytes', 'sha256')}
        for child in value.values():
            remember(child)
    elif isinstance(value, list):
        for child in value:
            remember(child)


def saved_artifact(path):
    state = _current.get()
    value = state['artifacts'].get(Path(path)) if state is not None else None
    if value is not None:
        require_file(path)
        return deepcopy(value)
    return None


def require_file(path):
    path = Path(path)
    if not path.is_file():
        raise ProductionRefused('saved completed material is missing: '+str(path))
    return path


def read_saved(path, *, mutable=False):
    state = _current.get()
    path = require_file(path)
    if state is None:
        raise RuntimeError('saved material reader requires a resume scope')
    if mutable or path not in state['json']:
        value = json.loads(path.read_bytes())
        if mutable:
            return value
        state['json'][path] = value
    return state['json'][path]


class _SavedRevisionGuard:
    """The resume policy deliberately trusts the existing revision commit."""
    def verify_frozen(self, frozen):
        pass

    def verify_captured_bytes(self):
        pass

    def register(self, key, value):
        remember(value)

    def is_registered(self, value):
        return False

    def capture_absent(self, path, *, root):
        pass


class _SavedRevisionProof(dict):
    def __missing__(self, key):
        if key != 'source_frozen':
            raise KeyError(key)
        # Prompt inheritance occasionally needs the source configuration. It
        # does not need any source material reconstruction until requested.
        from .production_inputs import load_frozen_inputs
        value = load_frozen_inputs(self['source_run'])
        self[key] = value
        return value


def saved_revision(options, run):
    state = _current.get()
    if state is None:
        return None
    run = Path(run)
    if run in state['revisions']:
        return state['revisions'][run]
    root = run/'production/scene-revision'
    commit = read_saved(root/'commit.json')
    index = read_saved(commit['imports']['path'])
    imports = {}
    for bound in index['imports']:
        # Old snapshots can enumerate a large ancestor tree. Only the committed
        # view and copy mappings are needed to consume its completed materials.
        path = Path(bound['path'])
        sidecar = json.loads(require_file(path).read_bytes())
        sidecar = {k: sidecar[k] for k in
                   ('domain', 'key', 'view', 'local_artifacts', 'view_artifact') if k in sidecar}
        imports[sidecar['domain']+':'+sidecar['key']] = (sidecar, bound)
        remember(sidecar['view'])
        remember(sidecar['local_artifacts'])
        if 'view_artifact' in sidecar:
            remember(sidecar['view_artifact'])
    result = _SavedRevisionProof(commit=commit, imports=imports, source_run=Path(commit['source_run_dir']),
                  invalidation=read_saved(commit['invalidation']['path']), guard=_SavedRevisionGuard())
    state['revisions'][run] = result
    return result


def saved_wan_inputs(frozen):
    path = Path(frozen.options['script_path']).parent/'reference-images/wan-inputs.json'
    if not existing_file(path):
        return None
    value = read_saved(path)
    remember(value)
    for row in value['scenes']:
        require_file(row['path'])
    return deepcopy(value)


def saved_common(frozen):
    """A completed narration/timeline is loaded, never replayed from TTS evidence."""
    run = Path(frozen.options['script_path']).parent.parent
    paths = [run/f'production/{stage}.json' for stage in ('units', 'timeline')]
    if not all(existing_file(path) for path in paths):
        return None
    reports = [read_saved(path) for path in paths]
    if any(report.get('status') != 'completed' for report in reports):
        return None
    ready = run/'production/scene-pipeline/common-inputs-ready.json'
    if existing_file(ready):
        remember(read_saved(ready))
    units, value = [report['payload'] for report in reports]
    for clip in value['clips']:
        require_file(clip['pcm']['stamp']['path'])
    from ..planning.production_timeline import ProductionTimeline
    mode = 'automatic' if (run/'production/production-state.json').exists() else 'prepared'
    return units, ProductionTimeline.from_dict(value), mode


def _local_clip(run, cid):
    state = _current.get()
    if run not in state['clips']:
        state['clips'][run] = {p.parent.name for p in (run/'production/scene-clips').glob('*/clip.json')
                               if existing_file(p)}
    if cid not in state['clips'][run]:
        return None
    folder = run/'production/scene-clips'/cid
    result = {key: read_saved(folder/name) for key, name in
              (('clip', 'clip.json'), ('request', 'request.json'), ('mapping', 'mapping.json'),
               ('last_frame', 'last-frame.json'))}
    template = folder/'observation-template.json'
    result['template'] = read_saved(template) if template.is_file() else None
    result.update(accepted=None, rejected=None)
    # Review receipts are append-only, but may be added during this invocation.
    for key, name in (('accepted', 'observation-accepted.json'), ('rejected', 'observation-rejected.json')):
        path = folder/name
        if path.is_file():
            result[key] = read_saved(path, mutable=True)
    if result['accepted'] and result['rejected']:
        raise ProductionRefused('conflicting accepted and rejected observation')
    for path in (folder/'observations').glob('*.json'):
        raw = path.read_bytes()
        observation = json.loads(raw)
        if observation.get('verdict') == 'failed':
            if result['accepted']:
                raise ProductionRefused('accepted clip has a retained explicit failed observation')
            if result['rejected'] is None:
                from ..planning.production_scenes import canonical_digest
                result['rejected'] = dict(_raw_only=True, observation=dict(path=str(path), bytes=len(raw),
                                          sha256=hashlib.sha256(raw).hexdigest()),
                                          observation_sha256=canonical_digest(observation))
    from .scene_review_waiver import apply_clip_waiver
    result = apply_clip_waiver(run, result)
    remember(result)
    for value in (result['clip']['generated'], result['clip']['source'], result['last_frame']['image']):
        require_file(value['path'])
    return deepcopy(result)


def saved_clip(run, cid):
    """Follow saved import links iteratively; never rebuild source scene contexts."""
    if not trusting_materials():
        return None
    if Path(cid).name != cid or cid in ('.', '..'):
        raise ProductionRefused('unsafe saved clip ID')
    chain, visited = [], set()
    run = Path(run)
    while True:
        if run in visited:
            raise ProductionRefused('saved revision origin cycle')
        visited.add(run)
        record = _local_clip(run, cid)
        if record is not None:
            break
        if not existing_file(run/'production/scene-revision/commit.json'):
            if chain:
                raise ProductionRefused('saved completed clip record is missing: '+cid)
            return None
        proof = saved_revision({}, run)
        imported = proof['imports'].get('clip:'+cid)
        if imported is None:
            if chain:
                raise ProductionRefused('saved completed clip import is missing: '+cid)
            return None
        chain.append(imported[0])
        run = proof['source_run']
    if chain:
        from ._scene_revision_origins import remap_media
        for sidecar in reversed(chain):
            record = remap_media(record, sidecar['local_artifacts'])
            record['clip'] = deepcopy(sidecar['view'])
        remember(record)
        for value in (record['clip']['generated'], record['clip']['source'], record['last_frame']['image']):
            require_file(value['path'])
    return record
