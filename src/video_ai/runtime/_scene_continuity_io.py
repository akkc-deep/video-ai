"""Bounded, read-only byte identities and immutable continuity storage."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from time import monotonic
from uuid import UUID, uuid4

from ..adapters.common import strict_json
from .manifest import hash_file, thaw, validate_run_dir
from .production_state import ProductionRefused, RunLock, object_fields, integer, run_path
from .paths import RUNTIME_ROOT, _validate_spelling


class SceneContinuityPending(ProductionRefused):
    """Valid media is waiting for a current diagnostic or playback response."""


def run_for(frozen):
    return validate_run_dir(Path(frozen.options['script_path']).parent.parent)


def uid(value):
    try:
        if type(value) is not str or str(UUID(value)) != value: raise ValueError()
    except (ValueError, TypeError, AttributeError) as exc:
        raise ProductionRefused('canonical continuity UUID required') from exc
    return value


def instant(value):
    try:
        result = datetime.fromisoformat(value) if isinstance(value, str) else value
        if not isinstance(result, datetime) or result.tzinfo is None or result.utcoffset() is None: raise ValueError()
    except (ValueError, TypeError) as exc:
        raise ProductionRefused('timezone-aware continuity timestamp required') from exc
    return result


def nonempty(value):
    if type(value) is not str or not value.strip(): raise ProductionRefused('nonempty author text required')
    return value


def local(path, *, runtime=True, exists=True):
    p = Path(_validate_spelling(str(path)))
    if not p.is_absolute() or (runtime and not p.is_relative_to(RUNTIME_ROOT)):
        raise ProductionRefused('explicit local continuity path required')
    if any(part in ('.', '..') for part in re.split(r'[/\\]', str(path))):
        raise ProductionRefused('continuity path alias forbidden')
    if any(x.is_symlink() or x.is_junction() for x in (p, *p.parents)):
        raise ProductionRefused('redirected continuity path forbidden')
    if exists:
        if not p.is_file() or p.stat().st_nlink != 1 or p.resolve() != p:
            raise ProductionRefused('continuity artifact unavailable or aliased')
    return p


def artifact(path, *, runtime=True, empty=False):
    p = local(path, runtime=runtime)
    value = thaw(hash_file(p))
    integer(value['bytes'], 'continuity artifact bytes', 0 if empty else 1)
    return {k: value[k] for k in ('path', 'bytes', 'sha256')}


def verify(value, *, runtime=True, empty=False):
    object_fields(value, ('path', 'bytes', 'sha256'), 'continuity Artifact')
    integer(value['bytes'], 'continuity artifact bytes', 0 if empty else 1)
    if type(value['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', value['sha256']):
        raise ProductionRefused('continuity SHA256 required')
    p = local(value['path'], runtime=runtime)
    if artifact(p, runtime=runtime, empty=empty) != value:
        raise ProductionRefused('continuity artifact bytes changed: '+str(p))
    return p


class Reader:
    def __init__(self, timeout=300):
        from .execution_limits import unlimited_execution, execution_deadline
        if not unlimited_execution() and (type(timeout) not in (int, float) or not 0 < timeout <= 300):
            raise ProductionRefused('continuity timeout must be within 300 seconds')
        self.deadline = execution_deadline(timeout,monotonic())
        self.bytes = 0
        self.json_paths = {}

    def check(self):
        if self.deadline is not None and monotonic() >= self.deadline: raise TimeoutError('continuity deadline expired')

    def remaining(self):
        self.check()
        return None if self.deadline is None else max(.001,self.deadline-monotonic())

    def charge(self,path,size):
        self.check();key=str(path)
        if size>16777216:raise ProductionRefused('resource_limit: continuity JSON')
        if key in self.json_paths:
            if self.json_paths[key]!=size:raise ProductionRefused('metadata size changed during validation')
            return
        if self.bytes+size>67108864:raise ProductionRefused('resource_limit: continuity metadata')
        self.json_paths[key]=size;self.bytes+=size

    def read(self, source):
        self.check()
        p = verify(source) if isinstance(source, dict) else local(source)
        size = p.stat().st_size
        self.charge(p,size)
        identity = artifact(p)
        raw = p.read_bytes()
        if len(raw) != identity['bytes'] or hashlib.sha256(raw).hexdigest() != identity['sha256']:
            raise ProductionRefused('continuity input changed during read')
        value = strict_json(raw)
        self.check()
        return value


class ContinuityStore:
    def __init__(self, frozen, lock=None):
        self.run_dir, self.lock = run_for(frozen), lock
        self.root = run_path(self.run_dir, self.run_dir/'production/scene-continuity')

    def owned(self):
        if (not isinstance(self.lock, RunLock) or self.lock.run_dir != self.run_dir
                or Reader().read(self.lock.path) != self.lock.owner):
            raise ProductionRefused('continuity lost held run lock')

    def write_bytes(self, relative, raw):
        self.owned()
        target = run_path(self.run_dir, self.root/relative)
        if not target.is_relative_to(self.root): raise ProductionRefused('continuity write escapes root')
        local(target, exists=False)
        if target.exists():
            if target.read_bytes() != raw: raise ProductionRefused('immutable continuity bytes differ')
            self.owned(); return target
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name+'.'+uuid4().hex+'.tmp')
        with temporary.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        self.owned(); os.rename(temporary, target); self.owned()
        return target

    def write(self, relative, value):
        target = self.root/relative
        if target.exists():
            self.owned()
            if Reader().read(target) != value: raise ProductionRefused('immutable continuity record differs')
            return target
        return self.write_bytes(relative, (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n').encode())
