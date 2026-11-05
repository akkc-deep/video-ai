"""One visible video number, complete production bundles and explicit cleanup."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
import os
import json
import re

from .paths import RUNTIME_ROOT, _validate_spelling
from .storage_files import inventory, read_record, remove_tree, safe_path, write_record
from .storage_lock import storage_lock

_allocation = ContextVar('video_storage_allocation', default=None)
_sandbox = ContextVar('video_storage_test_runtime', default=None)
_activity_counts = {}
_test_runtimes = {}


def _now():
    return datetime.now(timezone.utc).isoformat()


class VideoStorage:
    def __init__(self, runtime_root=None):
        self.runtime_root = Path(runtime_root or _sandbox.get() or RUNTIME_ROOT).absolute()
        safe_path(self.runtime_root, self.runtime_root)
        self.project_root = self.runtime_root/'projects/video-ai'
        self.production_root = self.project_root/'productions'
        self.output_root = self.runtime_root/'output/video-ai'
        self.disposable_root = self.runtime_root/'disposable/video-ai'
        self.index_root = self.project_root/'storage/videos'
        self.lock_path = self.project_root/'storage/lifecycle.lock'
        self._activities = _activity_counts.setdefault(str(self.runtime_root).casefold(),{})

    def _lock(self):
        safe_path(self.lock_path, self.runtime_root)
        return storage_lock(self.lock_path)

    def _write_video(self, value):
        path = safe_path(self.index_root/(value['number']+'.json'), self.index_root)
        write_record(path, value)

    def _validate(self, value):
        number, directory = value.get('number'), value.get('directory')
        if (value.get('schema_version') != 1 or not isinstance(number, str)
                or not re.fullmatch(r'[0-9]{4,}', number)
                or not isinstance(directory, str) or not directory.startswith(number+'-')
                or Path(directory).name != directory or '/' in directory or '\\' in directory):
            raise ValueError('invalid video storage index')
        _validate_spelling(directory)
        if value.get('state') not in ('active','closing','closed','cleaning','cleaned'):
            raise ValueError('invalid video lifecycle state')
        for root in (self.production_root, self.output_root, self.disposable_root/'completed'):
            safe_path(root/directory, self.runtime_root)
        return value

    def videos(self):
        safe_path(self.index_root, self.runtime_root)
        if not self.index_root.exists():
            return []
        result = []
        for path in sorted(self.index_root.glob('*.json')):
            safe_path(path, self.index_root)
            value = self._validate(read_record(path))
            if path.stem != value['number']:
                raise ValueError('video index filename differs from number')
            result.append(value)
        return result

    def find(self, selector):
        if isinstance(selector, dict):
            selector = selector['number']
        selector = str(selector)
        if any(c in selector for c in '/\\:') or selector in ('.','..'):
            raise ValueError('use a video number or name, never a filesystem path')
        number = str(int(selector)).zfill(4) if selector.isascii() and selector.isdigit() else None
        matches = [v for v in self.videos() if (v['number'] == number if number else
            selector in (v['title'],v['directory']))]
        if len(matches) != 1:
            raise ValueError('video not found' if not matches else 'ambiguous video name; use its number')
        return matches[0]

    def video_dir(self, video):
        value = self._validate(video if isinstance(video,dict) else self.find(video))
        return safe_path(self.production_root/value['directory'], self.runtime_root)

    def output_dir(self, video):
        value = self._validate(video if isinstance(video,dict) else self.find(video))
        return safe_path(self.output_root/value['directory'], self.runtime_root)

    def _completed(self, video):
        return safe_path(self.disposable_root/'completed'/video['directory'], self.disposable_root)

    def create(self, title):
        if not isinstance(title,str) or not title.strip():
            raise ValueError('video title must be nonempty')
        clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title.strip()).rstrip('. ')[:64].rstrip('. ')
        if not clean:
            raise ValueError('invalid video title')
        with self._lock():
            serial_path = safe_path(self.project_root/'storage/sequence.json', self.runtime_root)
            sequence = read_record(serial_path)['last'] if serial_path.exists() else 0
            number = max([sequence,*[int(v['number']) for v in self.videos()]])+1
            # Reserve the number before creating files; interrupted creation never reuses it.
            write_record(serial_path,dict(last=number))
            value = dict(schema_version=1,storage_layout_version=2,number=str(number).zfill(4),
                title=title.strip(),directory=str(number).zfill(4)+'-'+clean,state='active',
                current_revision=None,created_at=_now(),deliveries=[])
            folder = self.video_dir(value)
            folder.mkdir(parents=True,exist_ok=False)
            write_record(folder/'project.json',value)
            self._write_video(value)
            return value

    def allocate_revision(self, video, *, revision_key=None):
        with self._lock():
            value = self.find(video)
            if value['state'] != 'active':
                raise ValueError('video is closed or cleaned; cannot create another run')
            folder = self.video_dir(value)/'process/revisions'
            safe_path(folder,self.runtime_root); folder.mkdir(parents=True,exist_ok=True)
            if revision_key is not None:
                keys = value.get('revision_keys',{})
                if revision_key in keys:
                    return safe_path(folder/keys[revision_key],self.production_root)
            number = max([0,*[int(p.name) for p in folder.iterdir() if p.name.isascii() and p.name.isdigit()]])+1
            name = str(number).zfill(2)
            target = safe_path(folder/name,self.production_root)
            target.mkdir(exist_ok=False)
            if revision_key is None:
                value['current_revision'] = name
            if revision_key is not None:
                value.setdefault('revision_keys',{})[revision_key] = name
            self._write_video(value)
            write_record(self.video_dir(value)/'project.json',value)
            if revision_key is None:
                write_record(self.video_dir(value)/'process/current.json',dict(revision=name))
            return target

    def current_run(self, video):
        value = self.find(video)
        if value['state'] != 'active':
            raise ValueError('video is closed or cleaned; original progress is unavailable')
        name = value.get('current_revision')
        if not isinstance(name,str) or not re.fullmatch(r'[0-9]{2,}',name):
            raise ValueError('video has no allocated production revision')
        path = safe_path(self.video_dir(value)/'process/revisions'/name,self.production_root)
        if not path.is_dir():
            raise ValueError('production revision is missing; refusing to create an empty replacement')
        return path

    def set_current(self, video, run):
        with self._lock():
            value = self.find(video)
            path = safe_path(run,self.video_dir(value)/'process/revisions')
            if path.parent != self.video_dir(value)/'process/revisions' or not path.is_dir():
                raise ValueError('current revision must belong to this video')
            value['current_revision'] = path.name
            self._write_video(value)
            write_record(self.video_dir(value)/'process/current.json',dict(revision=path.name))

    @contextmanager
    def activity(self, video):
        with self._lock():
            value = self.find(video)
            if value['state'] != 'active':
                raise ValueError('video is closed or cleaned')
            number = value['number']
            self._activities[number] = self._activities.get(number,0)+1
            try:
                yield value
            finally:
                self._activities[number] -= 1

    def record_delivery(self, video, run, folder):
        with self._lock():
            value = self.find(video)
            if value['state'] != 'active':
                raise ValueError('video is closed; cannot register another delivery')
            folder = safe_path(folder,self.output_dir(value))
            self._check_package(value,folder)
            relative = folder.relative_to(self.output_dir(value)).as_posix()
            entry = dict(version=relative,revision=Path(run).name)
            if entry not in value['deliveries']:
                value['deliveries'].append(entry)
            self._write_video(value)
            write_record(self.output_dir(value)/'latest.json',dict(version=relative))

    def _check_package(self, video, folder):
        path = safe_path(folder/'delivery.json',self.output_dir(video))
        record = read_record(path)
        if record.get('schema_version') != 1 or record.get('video') != video['number']:
            raise ValueError('independent delivery manifest differs from video')
        files = record.get('files',{})
        if not {'video.mp4','video.srt','script.txt'} <= set(files):
            raise ValueError('incomplete independent delivery package')
        for name, info in files.items():
            if Path(name).name != name:
                raise ValueError('delivery manifest must contain local files')
            target = safe_path(folder/name,self.output_dir(video))
            if not target.is_file() or target.stat().st_size != info['bytes']:
                raise ValueError(f'delivery file missing or changed: {target}')

    def _check_dependencies(self, video, records):
        # Request facts are small JSON records; media/model contents are never read here.
        for path in records:
            if path.name == 'production-state.json':
                state = read_record(path)
                for units in state.get('units',{}).values():
                    for unit in units.values():
                        request = unit.get('request') or {}
                        if request.get('state') in ('ambiguous','unknown') or (
                                request.get('state') in ('intent','accepted','submitted','running')
                                and unit.get('status') != 'completed'):
                            raise ValueError(f'unresolved model request in production state: {path}')
            if path.name != 'intent.json':
                continue
            parent = path.parent
            if 'scene-revision' in path.parts:
                continue  # Local copying transaction, not a model submission.
            intent = read_record(path)
            if 'message_id' in intent:
                if not any((parent/name).is_file() for name in ('receipt.json','rejected.json')):
                    raise ValueError(f'unresolved mail request: {path}')
                continue
            if 'reference-storage' in path.parts:
                if not (parent/'object.json').is_file():
                    raise ValueError(f'unresolved reference upload: {path}')
                continue
            if not any(k in intent for k in ('client_id','request_id','status','state','identity','model','req_key')):
                continue
            settled=False
            for name in ('result.json','terminal.json','submission.json'):
                evidence=parent/name
                if not evidence.is_file():
                    continue
                try:
                    terminal=read_record(evidence)
                except (ValueError,OSError):
                    continue
                if not terminal or terminal.get('state') in ('unknown','ambiguous','running','intent','accepted'):
                    continue
                if 'identity' in intent and 'identity' in terminal and intent['identity'] != terminal['identity']:
                    continue
                settled=True; break
            if not settled:
                raise ValueError(f'unresolved model request; reconcile original request first: {path}')
        origin = str(self.video_dir(video)).replace('\\','/').casefold()+'/'
        for other in self.videos():
            if other['number'] == video['number'] or other['state'] in ('cleaned',):
                continue
            original = self.video_dir(other)
            folder = original if original.exists() else self._completed(other)
            for path in inventory(folder)['json_paths']:
                with path.open(encoding='utf-8-sig') as file:
                    values=[json.load(file)]
                while values:
                    item=values.pop()
                    if isinstance(item,dict):
                        values.extend(item.values())
                    elif isinstance(item,list):
                        values.extend(item)
                    elif isinstance(item,str):
                        raw=item.replace('\\','/').casefold()
                        if origin in raw or raw.rstrip('/')==origin.rstrip('/'):
                            raise ValueError(f'another video depends on this production bundle: {path}')

    def close(self, selector, *, dry_run=False):
        with self._lock():
            video = self.find(selector)
            if self._activities.get(video['number'],0):
                raise ValueError('video is active/occupied')
            if video['state'] in ('closed','cleaned'):
                return dict(status=video['state'],video=video['number'])
            if not video['deliveries']:
                raise ValueError('video has no independent published delivery')
            for entry in video['deliveries']:
                folder = safe_path(self.output_dir(video)/entry['version'],self.output_dir(video))
                self._check_package(video,folder)
            source, target = self.video_dir(video), self._completed(video)
            if source.exists() and target.exists():
                raise ValueError('both original and completed production exist; resolve storage transaction')
            active = source if source.exists() else target
            if not active.exists():
                raise ValueError('production bundle missing')
            listing = inventory(active)
            if any(p.name in ('.make-video.lock','.make-video-reclaim.lock') for p in active.rglob('.*lock')):
                raise ValueError('run lock remains; resolve original owner before close')
            self._check_dependencies(video,listing['json_paths'])
            result = dict(status='close_ready',video=video['number'],directory=str(target),
                logical_bytes=listing['logical_bytes'])
            if dry_run:
                return result
            video['state'] = 'closing'; self._write_video(video)
            target.parent.mkdir(parents=True,exist_ok=True)
            if source.exists():
                source.rename(target)
            video['state'] = 'closed'; video['closed_at'] = _now()
            self._write_video(video)
            write_record(target/'project.json',video)
            return dict(result,status='closed')

    def clean(self, selector=None, *, dry_run=False):
        with self._lock():
            videos = [self.find(selector)] if selector is not None else [v for v in self.videos() if v['state'] in ('closed','cleaning')]
            results = []
            for video in videos:
                if video['state'] == 'cleaned':
                    results.append(dict(status='cleaned',video=video['number'])); continue
                if video['state'] not in ('closed','cleaning'):
                    raise ValueError('close the video before cleaning its production data')
                target = self._completed(video)
                listing = inventory(target)
                result = dict(status='clean_ready',video=video['number'],directory=str(target),logical_bytes=listing['logical_bytes'])
                if not dry_run:
                    video['state'] = 'cleaning'; self._write_video(video)
                    remove_tree(target,self.disposable_root)
                    video['state'] = 'cleaned'; video['cleaned_at'] = _now(); self._write_video(video)
                    write_record(self.project_root/'storage/reports'/('clean-'+video['number']+'.json'),dict(result,status='cleaned'))
                    result['status'] = 'cleaned'
                results.append(result)
            if selector is not None:
                return results[0]
            shared, skipped = self._clean_shared(dry_run=dry_run)
            return dict(status='clean_ready' if dry_run else 'cleaned',videos=results,shared=shared,skipped=skipped)

    def _clean_shared(self, *, dry_run):
        shared,skipped = [],[]
        if any(self._activities.values()):
            return shared,[dict(reason='generation active; shared data retained')]
        allowed_caches = {'pip','uv','pycache','cuda','torchinductor','triton','matplotlib','numba','xdg'}
        candidates = []
        for group in ('cache','downloads','tests','diagnostics','logs','tmp','trash'):
            root = safe_path(self.disposable_root/group,self.disposable_root)
            if not root.exists():
                continue
            if group == 'logs':
                active_log=os.environ.get('VIDEO_AI_ACTIVE_LOG')
                for child in root.iterdir():
                    if active_log and child == Path(active_log):
                        skipped.append(dict(directory=str(child),reason='current launcher log')); continue
                    candidates.append(child)
            elif group in ('cache','tests'):
                for child in root.iterdir():
                    if group=='cache' and child.name not in allowed_caches:
                        skipped.append(dict(directory=str(child),reason='unclassified cache; retained')); continue
                    if group=='tests':
                        owner_path = child/'owner.json'
                        if not owner_path.is_file():
                            skipped.append(dict(directory=str(child),reason='unclassified test directory; retained')); continue
                        from .production_state import process_started_at
                        owner = read_record(safe_path(owner_path,root))
                        try:
                            current = process_started_at(owner['pid'])
                        except (OSError,ValueError,KeyError):
                            skipped.append(dict(directory=str(child),reason='test process ownership unknown')); continue
                        if current is not None:
                            skipped.append(dict(directory=str(child),reason='test process still active')); continue
                    candidates.append(child)
            else:
                candidates.append(root)
        for path in candidates:
            safe_path(path,self.disposable_root)
            listing = inventory(path)
            shared.append(dict(directory=str(path),logical_bytes=listing['logical_bytes']))
            if not dry_run:
                remove_tree(path,self.disposable_root)
        return shared,skipped

    def report(self, selector=None):
        with self._lock():
            values = [self.find(selector)] if selector is not None else self.videos()
            reports = []
            for video in values:
                folder = self.video_dir(video) if video['state'] in ('active','closing') else self._completed(video)
                listing = inventory(folder)
                reports.append(dict(number=video['number'],title=video['title'],state=video['state'],
                    directory=str(folder),output=str(self.output_dir(video)),**{k:listing[k] for k in ('logical_bytes','files','directories')}))
            shared = []
            if selector is None:
                for name in ('cache','downloads','tests','diagnostics','logs','tmp','trash'):
                    folder = safe_path(self.disposable_root/name,self.disposable_root)
                    listing = inventory(folder)
                    shared.append(dict(category=name,directory=str(folder),**{k:listing[k] for k in ('logical_bytes','files','directories')}))
            return dict(schema_version=1,videos=reports,shared=shared,size_kind='logical; hardlinks may be counted more than once',
                legacy_runs='retained; not automatically classified or deleted')


@contextmanager
def allocation_scope(storage, video):
    token = _allocation.set((storage,storage.find(video)))
    try:
        yield
    finally:
        _allocation.reset(token)


def allocated_run():
    active = _allocation.get()
    return active[0].allocate_revision(active[1]) if active else None


@contextmanager
def test_runtime_scope(root):
    """Only test fixtures call this; production paths never come from a CLI override."""
    root = Path(root).absolute()
    _test_runtimes[root] = _test_runtimes.get(root,0)+1
    token = _sandbox.set(root)
    try:
        yield
    finally:
        _sandbox.reset(token)
        _test_runtimes[root] -= 1
        if not _test_runtimes[root]:
            del _test_runtimes[root]


def test_root_for_paths(paths):
    """Fixture worker threads receive RuntimePaths explicitly, not ContextVars."""
    if _sandbox.get() is not None:
        return _sandbox.get()
    return next((root for root in _test_runtimes if paths.project_root == root/'projects/video-ai'),None)


def managed_output(run):
    location = managed_location(run)
    if location is None:
        return None
    # A frozen revision always keeps this output path; later revisions never overwrite it.
    # Lifecycle/index admission belongs at invocation boundaries, not each frozen-input read.
    return location[0]/'output/video-ai'/location[1].name/('v'+str(int(Path(run).name)).zfill(3))/'video.mp4'


def remote_namespace(run):
    """Short local revision numbers are qualified before use as remote object keys."""
    location = managed_location(run)
    if location is None:
        return Path(run).name
    number = location[1].name.split('-',1)[0]
    return 'video_'+number+'_revision_'+Path(run).name


def revision_target(source_run, key):
    location = managed_location(source_run)
    if location is None:
        return None
    storage = VideoStorage(location[0])
    return storage.allocate_revision(storage.find(location[1].name),revision_key=key)


def managed_location(run):
    """Lexical recognition only; full index validation happens at invocation boundaries."""
    run = Path(run)
    parts = run.parts
    if len(parts) < 8 or run.parent.name != 'revisions' or run.parent.parent.name != 'process':
        return None
    video = run.parent.parent.parent
    if video.parent.name != 'productions' or video.parent.parent.name != 'video-ai' or video.parent.parent.parent.name != 'projects':
        return None
    if not re.fullmatch(r'[0-9]{2,}',run.name) or not re.match(r'[0-9]{4,}-.+',video.name):
        return None
    return video.parent.parent.parent.parent, video


@contextmanager
def managed_lease(run):
    location = managed_location(run)
    if location is None:
        root=next((root for root in _test_runtimes if Path(run).is_relative_to(root)),None)
        storage=VideoStorage(root)
        with storage._lock():
            storage._activities['__legacy__']=storage._activities.get('__legacy__',0)+1
            try:
                yield
            finally:
                storage._activities['__legacy__']-=1
        return
    storage = VideoStorage(location[0])
    video = storage.find(location[1].name)
    with storage.activity(video):
        yield
