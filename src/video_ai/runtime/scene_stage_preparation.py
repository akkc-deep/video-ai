"""Experimental read-only source prefetch; never an admission or media receipt."""
from contextlib import contextmanager
from contextvars import Context, ContextVar
from dataclasses import dataclass
import hashlib
from io import BytesIO
import math
import os
import re
from threading import Condition, Event, Thread
from time import perf_counter
from types import MappingProxyType


_candidate = ContextVar('scene_preparation_candidate', default=False)


@contextmanager
def candidate_scene_preparation():
    """Explicit experiment-only switch, independent of LVA-02 validation."""
    token = _candidate.set(True)
    try: yield
    finally: _candidate.reset(token)


def preparation_enabled():
    return _candidate.get()


@dataclass(frozen=True)
class PreparationJob:
    clip_id: str
    source: object
    parameters_sha256: str
    workflow_sha256: str
    graph_bytes: bytes
    parent_required: bool

    def __post_init__(self):
        # Copy away the caller's mutable Artifact without retaining its context.
        source = dict(self.source)
        if set(source) != {'path', 'bytes', 'sha256'}:
            raise ValueError('preparation requires a complete source Artifact')
        if (not isinstance(source['path'], str) or type(source['bytes']) is not int
                or source['bytes'] < 0 or not re.fullmatch('[0-9a-f]{64}', source['sha256'])):
            raise ValueError('invalid preparation source')
        if not isinstance(self.graph_bytes, bytes): raise TypeError('graph must be immutable bytes')
        object.__setattr__(self, 'source', MappingProxyType(source))

    @property
    def key(self):
        return (self.clip_id, self.source['path'], self.source['bytes'], self.source['sha256'],
                self.parameters_sha256, self.workflow_sha256,
                hashlib.sha256(self.graph_bytes).hexdigest(), self.parent_required)


@dataclass(frozen=True)
class PreparedSceneInput:
    job_key: tuple
    source_bytes: bytes
    actual_sha256: str
    graph_bytes: bytes
    read_seconds: float
    error: str | None = None


def _metadata(value):
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _read(job, cancel):
    from pathlib import Path
    started = perf_counter()
    def failed(reason):
        return PreparedSceneInput(job.key, b'', '', b'', perf_counter()-started, reason)
    try:
        if cancel.is_set(): return failed('cancelled')
        digest = hashlib.sha256()
        # Disable BufferedReader read-ahead: even a growing file must cause
        # at most the declared bytes plus the one-byte growth check to be read.
        with Path(job.source['path']).open('rb',buffering=0) as stream, BytesIO() as content:
            before = os.fstat(stream.fileno())
            if before.st_size != job.source['bytes']: return failed('source_changed')
            remaining = job.source['bytes']
            while remaining:
                if cancel.is_set(): return failed('cancelled')
                block = stream.read(min(1024*1024, remaining))
                if cancel.is_set(): return failed('cancelled')
                if not block: return failed('source_changed')
                digest.update(block); content.write(block); remaining -= len(block)
            # One bounded extra byte detects growth; it never enters the buffer.
            if cancel.is_set(): return failed('cancelled')
            extra = stream.read(1)
            after = os.fstat(stream.fileno())
            current = os.stat(job.source['path'])
            if (extra or _metadata(before) != _metadata(after)
                    # Python 3.12 Windows fstat ctime is handle change time,
                    # whereas path stat ctime can be creation time. Compare
                    # full handle metadata across the read, common fields
                    # across APIs, and always the complete declared SHA.
                    or _metadata(after)[:4] != _metadata(current)[:4]
                    or digest.hexdigest() != job.source['sha256']):
                return failed('source_changed')
            if cancel.is_set(): return failed('cancelled')
            return PreparedSceneInput(job.key, content.getvalue(), digest.hexdigest(),
                                      job.graph_bytes, perf_counter()-started)
    except (OSError, ValueError, MemoryError):
        return failed('read_failed')


class ScenePreparationPool:
    """One daemon worker, one unconsumed job, no coordinator references."""
    def __init__(self, *, enabled=False, max_source_bytes=64*1024*1024, max_graph_bytes=32*1024*1024):
        if not 0 <= max_source_bytes <= 64*1024*1024 or not 0 <= max_graph_bytes <= 32*1024*1024:
            raise ValueError('preparation budget exceeds 96MiB')
        self.enabled = enabled
        self.max_source_bytes, self.max_graph_bytes = max_source_bytes, max_graph_bytes
        self._condition = Condition(); self._closed = False; self._busy = False
        self._job = self._result = self._thread = None
        self._cancel = Event()
        self._failure_reasons={}
        self._stats = dict(submitted=0, consumed=0, discarded=0, cancelled=0,
                           failed=0, peak_jobs=0, peak_bytes=0, retained_bytes=0,
                           unfinished_worker=False, read_seconds=0.,resource_failures=0)

    def submit(self, job):
        with self._condition:
            if (not self.enabled or self._closed or self._job is not None or self._busy
                    or job.parent_required or not re.fullmatch(r'scene_\d+_clip_0001', job.clip_id)
                    or job.source['bytes'] > self.max_source_bytes
                    or len(job.graph_bytes) > self.max_graph_bytes): return False
            self._job = job; self._cancel = Event()
            size = job.source['bytes']+len(job.graph_bytes)
            if self._thread is None:
                self._thread = Thread(target=Context().run, args=(self._work,),
                                      name='scene-read-preparation', daemon=True)
                try:self._thread.start()
                except (RuntimeError,OSError,MemoryError):
                    self._thread=None;self._discard_locked()
                    self._stats['resource_failures']+=1
                    return False
            self._stats['submitted'] += 1; self._stats['peak_jobs'] = 1
            self._stats['peak_bytes'] = max(size, self._stats['peak_bytes'])
            self._condition.notify_all()
            return True

    def _work(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or (self._job is not None and self._result is None))
                if self._closed: return
                job, cancel = self._job, self._cancel; self._busy = True
            result = _read(job, cancel)
            with self._condition:
                self._busy = False
                self._stats['read_seconds'] += result.read_seconds
                if result.error:
                    self._stats['failed'] += 1
                    self._failure_reasons[result.error]=self._failure_reasons.get(result.error,0)+1
                if not self._closed and not cancel.is_set() and self._job is job:
                    self._result = result
                    self._stats['retained_bytes'] = len(result.source_bytes)+len(result.graph_bytes)
                self._condition.notify_all()
            # Drop local references while waiting; late reads cannot publish.
            del job, result, cancel

    def take(self, job):
        with self._condition:
            if self._closed or self._job is None: return None
            if self._job.key != job.key:
                self._discard_locked(); return None
            if self._result is None: return None
            result = self._result
            self._job = self._result = None
            self._stats['retained_bytes'] = 0
            self._stats['consumed'] += int(result.error is None)
            self._stats['discarded'] += int(result.error is not None)
            return result

    def _discard_locked(self):
        if self._job is not None:
            self._stats['discarded'] += 1
            self._stats['cancelled'] += int(self._busy)
        self._cancel.set(); self._job = self._result = None
        self._stats['retained_bytes'] = 0

    def discard(self):
        with self._condition: self._discard_locked()

    def close(self):
        with self._condition:
            if self._closed: return
            self._closed = True; self._discard_locked(); self._condition.notify_all()
        if self._thread is not None: self._thread.join(2)
        with self._condition:
            self._stats['unfinished_worker'] = self._thread is not None and self._thread.is_alive()

    def report(self):
        with self._condition:return dict(self._stats,failure_reasons=dict(self._failure_reasons))


class ScenePhaseMetrics:
    """Small coordinator-only diagnostic; no artifact reads or admission proof."""
    def __init__(self):
        self._start = perf_counter(); self._events = []; self._counts = {}; self._dropped = 0

    def event(self, name, *, clip_id=None, service_identity=None, seconds=None):
        if not re.fullmatch('[a-z_]+', name): raise ValueError('invalid phase event')
        value = dict(name=name, offset_seconds=perf_counter()-self._start)
        if clip_id is not None and re.fullmatch(r'scene_\d+_clip_\d+', clip_id): value['clip_id'] = clip_id
        if service_identity is not None:
            value['service_identity_sha256'] = hashlib.sha256(repr(service_identity).encode()).hexdigest()
        if seconds is not None:
            if not math.isfinite(seconds) or seconds < 0: raise ValueError('invalid event duration')
            value['seconds'] = seconds
        self._counts[name] = self._counts.get(name, 0)+1
        if len(self._events) < 8192: self._events.append(value)
        else: self._dropped += 1

    def report(self):
        return dict(wall_seconds=perf_counter()-self._start, counts=dict(self._counts),
                    events=[dict(v) for v in self._events], dropped_events=self._dropped)
