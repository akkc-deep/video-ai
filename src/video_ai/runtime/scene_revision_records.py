"""Explicit inherited views and origin byte guards, never external-path fallback."""
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
from copy import deepcopy
import os
from pathlib import Path
import stat
from uuid import UUID

from ..adapters.common import strict_json
from ..planning.production_scenes import canonical_digest
from ..planning.scene_revision import IDENTITY_FIELDS, DOMAINS, STRATEGY
from .manifest import thaw, validate_run_dir
from .verification import verified_read
from .production_state import (ArtifactStamp, ProductionRefused, RunLock, integer,
                               object_fields, run_path, timestamp)

COMMIT_FIELDS = ('schema_version production_strategy run_id revision_id source_run_id source_run_dir '
                 'source_options request target_identity invalidation imports created_at').split()
IMPORT_FIELDS = ('schema_version production_strategy run_id import_id domain key source_run_id '
                 'source_options_sha256 source_identity_sha256 dependency_import_ids source_json_snapshot '
                 'raw_files source_artifacts local_artifacts view view_sha256 view_artifact created_at').split()
IMPORT_DOMAINS = ('common','plan','reference_settings','image','choice','image_group','clip','upscale')
_context = ContextVar('scene_revision_context', default=None)


@contextmanager
def revision_scope():
    if _context.get() is not None:
        yield
        return
    saved = _context.set(dict(stack=[],validated={},identities={}))
    try: yield
    finally: _context.reset(saved)


def revision_validation(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        with revision_scope(): return function(*args,**kwargs)
    return wrapped


def safe_path(path, root):
    """Check lexical containment and every existing ancestor before reading."""
    path, root = Path(path), Path(root)
    if not path.is_absolute() or '..' in path.parts or not path.is_relative_to(root):
        raise ProductionRefused('revision evidence path escapes root')
    for item in (path, *path.parents):
        try: metadata = item.lstat()
        except FileNotFoundError: continue
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata,'st_file_attributes',0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ProductionRefused('redirected revision evidence path')
    return path


def stable_bytes(path, *, root):
    path = safe_path(path, root)
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno()); raw = stream.read(); after = os.fstat(stream.fileno())
    current = path.stat()
    def key(value): return value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns
    if key(before) != key(after) or key(after) != key(current):
        raise ProductionRefused('revision evidence changed during read')
    return raw


def artifact(path, *, root=None, allow_empty=False):
    path = Path(path); root = Path(root) if root is not None else path.parent
    safe_path(path, root)
    from .manifest import hash_file
    value=hash_file(path)
    safe_path(path,root)
    integer(value.bytes,'revision artifact bytes',0 if allow_empty else 1)
    return dict(path=str(path),bytes=value.bytes,sha256=value.sha256)


def verify_artifact(value, *, root, allow_empty=False):
    object_fields(value, ('path','bytes','sha256'), 'revision Artifact')
    integer(value['bytes'], 'revision artifact bytes',0 if allow_empty else 1)
    if artifact(value['path'],root=root,allow_empty=allow_empty) != value:
        raise ProductionRefused('revision captured bytes changed: '+value['path'])
    return Path(value['path'])


def _json(path, *, root): return strict_json(stable_bytes(path,root=root).removeprefix(b'\xef\xbb\xbf'))


class RevisionGuard:
    """Invocation-local immutable captures; re-capture never replaces a baseline."""
    def __init__(self, frozen, *, lock=None):
        self.frozen, self.lock = frozen, lock
        self.run = Path(frozen.options['script_path']).parent.parent
        self.options_sha256=canonical_digest(frozen.options)
        self.files, self.directories, self.absent, self.views = {}, {}, {}, {}
        self.ancestors = []

    def capture(self, path, *, root, allow_empty=False, expected=None):
        value = artifact(path, root=root, allow_empty=allow_empty)
        key = str(Path(path))
        if key in self.absent or (expected is not None and value != expected): raise ProductionRefused('revision captured bytes changed')
        previous = self.files.get(key)
        if previous is not None and previous[0] != value: raise ProductionRefused('revision captured bytes changed')
        identity = path_identity(path)
        if previous is not None and previous[3] != identity: raise ProductionRefused('revision captured file ownership changed')
        self.files[key] = (value,str(root),allow_empty,identity)
        return value

    def capture_directory(self, path, *, root, expected=None):
        folder = safe_path(path,root)
        inventory = sorted(str(safe_path(p,root)) for p in folder.rglob('*.json'))
        key = str(folder)
        if (expected is not None and inventory != sorted(expected)) or (key in self.directories and self.directories[key][0] != inventory):
            raise ProductionRefused('revision evidence inventory changed')
        self.directories[key] = (inventory,str(root))
        return inventory

    def capture_absent(self, path, *, root):
        path = safe_path(path,root)
        if path.exists() or str(path) in self.files: raise ProductionRefused('revision expected absent evidence changed')
        self.absent[str(path)] = str(root)

    def register(self, import_id, view):
        digest = canonical_digest(view)
        previous=self.views.get(digest)
        if previous is not None and previous.split('#',1)[0]!=import_id.split('#',1)[0]:
            raise ProductionRefused('ambiguous inherited view')
        self.views.setdefault(digest,import_id)

    def is_registered(self, value): return canonical_digest(value) in self.views

    def verify_frozen(self,frozen):
        if canonical_digest(frozen.options)!=self.options_sha256:
            raise ProductionRefused('revision proof frozen options changed')

    def verify_captured_bytes(self):
        self.verify_frozen(self.frozen)
        for ancestor in self.ancestors:ancestor.verify_captured_bytes()
        for value,root,empty,identity in self.files.values():
            verify_artifact(value,root=root,allow_empty=empty)
            if path_identity(value['path'])!=identity: raise ProductionRefused('revision captured file ownership changed')
        for directory,(inventory,root) in self.directories.items():
            current = sorted(str(safe_path(p,root)) for p in safe_path(directory,root).rglob('*.json'))
            if current != inventory: raise ProductionRefused('revision evidence inventory changed')
        for path,root in self.absent.items():
            if safe_path(path,root).exists(): raise ProductionRefused('revision absent evidence appeared')

    def verify_global(self):
        self.verify_captured_bytes()
        if (not isinstance(self.lock,RunLock) or self.lock.run_dir != self.run
                or _json(self.lock.path,root=self.run) != self.lock.owner):
            raise ProductionRefused('revision lost held run lock')
        for stamp in self.frozen.options['model_stamps'].values(): ArtifactStamp.from_dict(thaw(stamp)).verify()


def token(domain,key): return canonical_digest(dict(domain=domain,key=key))


def path_identity(path):
    value = Path(path).stat()
    return value.st_dev,value.st_ino


def validate_revision_structure(options, run):
    """Loader-safe byte/structure binding; no current FrozenInputs recursion."""
    value = options.get('scene_revision')
    if value is None: raise ProductionRefused('scene revision is not frozen')
    root = Path(run)/'production/scene-revision'
    path = verify_artifact(value,root=root)
    if path != root/'commit.json': raise ProductionRefused('revision commit path differs')
    commit = _json(path,root=root); object_fields(commit,COMMIT_FIELDS,'revision commit')
    if (type(commit['schema_version']) is not int or commit['schema_version'] != 2
            or commit['production_strategy'] != STRATEGY or commit['run_id'] != Path(run).name
            or str(UUID(commit['revision_id'])) != commit['revision_id']):
        raise ProductionRefused('revision commit identity differs')
    timestamp(commit['created_at']); object_fields(commit['target_identity'],IDENTITY_FIELDS,'revision target identity')
    source = validate_run_dir(commit['source_run_dir'])
    if source.name != commit['source_run_id'] or source == Path(run): raise ProductionRefused('revision source identity differs')
    if Path(commit['source_options']['path']) != source/'production/options.json': raise ProductionRefused('revision source options path differs')
    verify_artifact(commit['source_options'],root=source)
    for name in ('request','invalidation','imports'): verify_artifact(commit[name],root=root)
    if Path(commit['invalidation']['path']) != root/'invalidation.json' or Path(commit['imports']['path']) != root/'imports.json':
        raise ProductionRefused('revision index path differs')
    index = _json(commit['imports']['path'],root=root)
    object_fields(index,('schema_version','production_strategy','run_id','revision_id','imports'),'revision imports index')
    if type(index['schema_version']) is not int or any(index[k] != commit[k] for k in ('schema_version','production_strategy','run_id','revision_id')):
        raise ProductionRefused('revision imports index identity differs')
    invalidation = _json(commit['invalidation']['path'],root=root)
    object_fields(invalidation,('schema_version algorithm source_run_id request_sha256 target_identity_sha256 content_edges admission_edges dirty reusable blocked_effects reasons').split(),'revision invalidation')
    if type(invalidation['schema_version']) is not int or invalidation['schema_version']!=2 or invalidation['algorithm']!='scene_revision_v1':
        raise ProductionRefused('revision invalidation schema differs')
    for name in ('dirty','reusable'):
        object_fields(invalidation[name],DOMAINS,'revision '+name)
        for rows in invalidation[name].values():
            if type(rows) is not list or any(type(key) is not str for key in rows) or len(set(rows))!=len(rows):
                raise ProductionRefused('revision node IDs differ')
    if invalidation['source_run_id'] != source.name or invalidation['target_identity_sha256'] != canonical_digest(commit['target_identity']):
        raise ProductionRefused('revision invalidation identity differs')
    imports = {}
    for bound in index['imports']:
        sidecar = _json(verify_artifact(bound,root=root),root=root)
        object_fields(sidecar,IMPORT_FIELDS,'revision import')
        timestamp(sidecar['created_at'])
        domain,key = sidecar['domain'],sidecar['key']; iid = domain+':'+key
        if domain not in IMPORT_DOMAINS or sidecar['import_id'] != iid or iid in imports:
            raise ProductionRefused('unknown or duplicate import')
        if type(sidecar['schema_version']) is not int or any(sidecar[k] != commit[k] for k in ('schema_version','production_strategy','run_id','source_run_id')):
            raise ProductionRefused('revision import identity differs')
        if sidecar['source_options_sha256'] != commit['source_options']['sha256']: raise ProductionRefused('import source options differs')
        if Path(bound['path']) != root/'imports'/(token(domain,key)+'.json'): raise ProductionRefused('revision import path differs')
        expected_view_path = root/'views'/domain/(token(domain,key)+'.json')
        if Path(sidecar['view_artifact']['path']) != expected_view_path: raise ProductionRefused('inherited view path differs')
        view_path = verify_artifact(sidecar['view_artifact'],root=root)
        view = _json(view_path,root=root)
        if canonical_digest(view) != sidecar['view_sha256'] or canonical_digest(view) != canonical_digest(sidecar['view']):
            raise ProductionRefused('inherited view digest differs')
        snapshot = sidecar['source_json_snapshot']
        object_fields(snapshot,('files','inventories','absent_paths'),'origin JSON snapshot')
        for item in snapshot['files']: verify_artifact(item,root=source)
        for item in sidecar['raw_files']: verify_artifact(item,root=source,allow_empty=True)
        for item in sidecar['source_artifacts']: verify_artifact(item,root=source)
        for item in sidecar['local_artifacts']:
            object_fields(item,('role','source','target'),'local import mapping')
            verify_artifact(item['source'],root=source); verify_artifact(item['target'],root=root)
            if any(item['source'][k] != item['target'][k] for k in ('bytes','sha256')): raise ProductionRefused('revision copy differs')
            from ._scene_revision_copy import file_id
            ready_path = root/'copy-ready'/token(domain,key)/(item['role']+'.json')
            ready = _json(ready_path,root=root)
            object_fields(ready,('schema_version run_id import_id role intent source staging target file_id recipe created_at').split(),'import copy-ready')
            if (ready['target']!=item['target'] or ready['source']!=item['source'] or ready['import_id']!=iid
                    or ready['role']!=item['role'] or ready['file_id']!=file_id(item['target']['path'])
                    or safe_path(ready['staging']['path'],root).exists()):
                raise ProductionRefused('inherited copy ownership differs')
            verify_artifact(ready['intent'],root=root)
        for item in snapshot['inventories']:
            object_fields(item,('directory','paths'),'origin inventory')
            folder = safe_path(item['directory'],source)
            if sorted(str(safe_path(p,source)) for p in folder.rglob('*.json')) != item['paths']:
                raise ProductionRefused('origin inventory changed')
        for item in snapshot['absent_paths']:
            if safe_path(item,source).exists(): raise ProductionRefused('origin absent evidence appeared')
        if any(parent not in imports for parent in sidecar['dependency_import_ids']): raise ProductionRefused('import dependency missing or not topological')
        required=[] if domain=='common' else ['common:all'] if domain=='plan' else ['common:all','plan:all']
        if any(parent not in sidecar['dependency_import_ids'] for parent in required):
            raise ProductionRefused('import omits required common/plan dependency')
        domain_map = {'image':'images','choice':'choices','clip':'clips'}
        d = domain_map.get(domain,domain)
        if d in DOMAINS and key not in invalidation['reusable'][d]: raise ProductionRefused('dirty or unaccepted import')
        imports[iid] = (sidecar,bound)
    plan=imports['plan:all'][0]['view']['scene_plan'] if 'plan:all' in imports else None
    from ._scene_revision_plan import import_dependencies
    for iid,(sidecar,_) in imports.items():
        if sidecar['dependency_import_ids']!=import_dependencies(sidecar['domain'],sidecar['key'],plan,imports):
            raise ProductionRefused('import dependency closure differs')
    from ._scene_revision_copy import preflight_copies
    domain_map={'images':'image','choices':'choice','clips':'clip'}
    required={domain_map.get(domain,domain)+':'+key for domain in ('common','plan','images','choices','image_group','clips','upscale') for key in invalidation['reusable'][domain]}
    if set(imports)-{'reference_settings:all'}!=required:raise ProductionRefused('revision import coverage differs from reusable nodes')
    expected={str(root/'copy-ready'/token(s['domain'],s['key'])/(m['role']+'.json')) for s,_ in imports.values() for m in s['local_artifacts']}
    preflight_copies(root,Path(run).name,expected=expected)
    return dict(commit=commit,imports=imports,invalidation=invalidation,source_run=source)


@verified_read
def require_scene_revision(frozen):
    """Admit original nodes and compare registered views under one recursion scope."""
    run = Path(frozen.options['script_path']).parent.parent
    if 'scene_revision' not in frozen.options: raise ProductionRefused('scene revision is not frozen')
    active = _context.get()
    if active is not None and str(run) in active['validated']:
        result = active['validated'][str(run)]
        result['guard'].verify_frozen(frozen)
        result['guard'].verify_captured_bytes()
        return result
    root_call = active is None
    if root_call: active = dict(stack=[],validated={},identities={})
    identity = frozen.options['scene_revision']['sha256']
    if frozen.options['run_id'] in active['identities'] and active['identities'][frozen.options['run_id']] != identity:
        raise ProductionRefused('conflicting revision commit for same run')
    if str(run) in active['stack']: raise ProductionRefused('revision origin cycle')
    active['identities'][frozen.options['run_id']] = identity
    context_token = _context.set(active)
    active['stack'].append(str(run))
    try:
        result = validate_revision_structure(frozen.options,run)
        guard = RevisionGuard(frozen); result['guard'] = guard
        root = run/'production/scene-revision'
        guard.capture(frozen.options['scene_revision']['path'],root=root,expected=frozen.options['scene_revision'])
        for name in ('request','invalidation','imports'):
            bound = result['commit'][name]; guard.capture(bound['path'],root=root,expected=bound)
        source = result['source_run']; bound = result['commit']['source_options']
        guard.capture(bound['path'],root=source,expected=bound)
        from ._scene_revision_origins import capture_origin,verify_import_view
        from .production_inputs import load_frozen_inputs
        origin = load_frozen_inputs(source)
        if 'scene_revision' in origin.options:
            guard.ancestors.append(require_scene_revision(origin)['guard'])
        originals={}
        for iid,(sidecar,bound) in result['imports'].items():
            guard.capture(bound['path'],root=root,expected=bound)
            view_bound = sidecar['view_artifact']; guard.capture(view_bound['path'],root=root,expected=view_bound)
            snapshot = sidecar['source_json_snapshot']
            for value in snapshot['files']+sidecar['source_artifacts']:
                guard.capture(value['path'],root=source,expected=value)
            for value in sidecar['raw_files']: guard.capture(value['path'],root=source,allow_empty=True,expected=value)
            for value in snapshot['inventories']: guard.capture_directory(value['directory'],root=source,expected=value['paths'])
            for path in snapshot['absent_paths']: guard.capture_absent(path,root=source)
            for value in sidecar['local_artifacts']:
                guard.capture(value['target']['path'],root=root,expected=value['target'])
                copy_ready=root/'copy-ready'/token(sidecar['domain'],sidecar['key'])/(value['role']+'.json')
                guard.capture(copy_ready,root=root)
                copy_record=_json(copy_ready,root=root)
                guard.capture(copy_record['intent']['path'],root=root,expected=copy_record['intent'])
            captured=capture_origin(origin,sidecar['domain'],sidecar['key'])
            if canonical_digest(captured['snapshot'])!=canonical_digest(snapshot):
                raise ProductionRefused('import omits or changes required source snapshot closure')
            def raw_bindings(rows):return {row['path']:row for row in rows}
            if raw_bindings(captured['raw_files'])!=raw_bindings(sidecar['raw_files']):
                raise ProductionRefused('import raw evidence closure differs')
            if sidecar['source_artifacts']!=[value for _,value in captured['media']] or [(m['role'],m['source']) for m in sidecar['local_artifacts']]!=captured['media']:
                raise ProductionRefused('import media roles differ from original node')
            original=captured['value'];originals[iid]=original
            guard.verify_captured_bytes()
            verify_import_view(frozen,sidecar,original,origin_frozen=origin)
            guard.register(iid,sidecar['view'])
        from ._scene_revision_plan import verify_invalidation
        verify_invalidation(frozen,origin,result,originals)
        guard.verify_captured_bytes()
        active['validated'][str(run)] = result
        return result
    finally:
        active['stack'].pop(); _context.reset(context_token)


def require_revision_import(frozen,domain,key,*,context):
    proof = context if context is not None else require_scene_revision(frozen)
    proof['guard'].verify_frozen(frozen)
    iid = domain+':'+key
    if iid not in proof['imports']: raise ProductionRefused('required revision import missing')
    proof['guard'].verify_captured_bytes()
    return deepcopy(proof['imports'][iid][0]['view'])


def load_scene_common_prefix(frozen):
    from ..planning.production_timeline import ProductionTimeline
    if 'scene_revision' in frozen.options:
        proof = require_scene_revision(frozen)
        if 'common:all' in proof['imports']:
            view = require_revision_import(frozen,'common','all',context=proof)
            return view['units'], ProductionTimeline.from_dict(view['timeline'])
    from .production_image_selection import load_prepared_inputs
    return load_prepared_inputs(frozen)
