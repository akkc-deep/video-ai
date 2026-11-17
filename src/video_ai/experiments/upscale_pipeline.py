"""LVA-05 CPU-only slots. Results are data, never durable acceptance proofs."""
from contextvars import Context
from dataclasses import dataclass, replace
import hashlib
import os
from pathlib import Path
import re
from threading import Condition, Event, Thread, get_ident
from time import monotonic, perf_counter
from types import MappingProxyType

from ..runtime.scene_stage_preparation import PreparationJob, ScenePreparationPool, _metadata

MiB = 1024**2


def _artifact(value):
    value = dict(value)
    if (set(value) != {'path', 'bytes', 'sha256'} or not isinstance(value['path'], str)
            or not Path(value['path']).is_absolute() or type(value['bytes']) is not int
            or value['bytes'] < 0 or not re.fullmatch('[0-9a-f]{64}', value['sha256'])):
        raise ValueError('complete absolute Artifact required')
    return MappingProxyType(value)


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    prefetch: bool = False
    writeback: bool = False
    max_prefetch_bytes: int = 64*MiB
    max_writeback_bytes: int = 32*MiB

    def __post_init__(self):
        if (type(self.prefetch) is not bool or type(self.writeback) is not bool
                or type(self.max_prefetch_bytes) is not int
                or type(self.max_writeback_bytes) is not int
                or not 0 <= self.max_prefetch_bytes <= 64*MiB
                or not 0 <= self.max_writeback_bytes <= 32*MiB):
            raise ValueError('payload budgets must fit 64+32MiB')


@dataclass(frozen=True, slots=True)
class UpscaleFrameJob:
    frame_id: int
    source: object
    graph_bytes: bytes
    parameters_sha256: str
    profile_sha256: str

    def __post_init__(self):
        if type(self.frame_id) is not int or self.frame_id < 1:
            raise ValueError('positive frame ordinal required')
        if not isinstance(self.graph_bytes, bytes): raise TypeError('immutable graph bytes required')
        for value in (self.parameters_sha256, self.profile_sha256):
            if not re.fullmatch('[0-9a-f]{64}', value): raise ValueError('complete digest required')
        object.__setattr__(self, 'source', _artifact(self.source))

    @property
    def key(self):
        return (self.frame_id, self.source['path'], self.source['bytes'], self.source['sha256'],
                hashlib.sha256(self.graph_bytes).hexdigest(), self.parameters_sha256, self.profile_sha256)

    def preparation(self):
        # The pool's first-clip namespace is only a CPU slot key. No media/parent
        # approval is inferred from this namespace; the coordinator supplies it.
        return PreparationJob(f'scene_{self.frame_id:06d}_clip_0001', self.source,
                              self.parameters_sha256, self.profile_sha256, self.graph_bytes, False)


@dataclass(frozen=True, slots=True)
class StagedFrame:
    job_key: tuple
    artifact: object
    copy_seconds: float
    error: str | None = None

    def __post_init__(self):
        object.__setattr__(self, 'artifact', MappingProxyType(dict(self.artifact)))


def _copy_output(job, captured, staging_path, cancel):
    """Only copy bounded captured bytes; never promote or write a receipt."""
    started = perf_counter()
    key=job if isinstance(job,tuple) else job.key
    def failed(reason): return StagedFrame(key, {}, perf_counter()-started, reason)
    try:
        if cancel.is_set(): return failed('cancelled')
        path = Path(captured['path']); target = Path(staging_path)
        if path.resolve() == target.resolve(): return failed('source_alias')
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with path.open('rb', buffering=0) as source:
            before = os.fstat(source.fileno())
            if before.st_size != captured['bytes']: return failed('source_changed')
            with target.open('xb', buffering=0) as output:
                remaining = captured['bytes']
                while remaining:
                    if cancel.is_set(): return failed('cancelled')
                    block = source.read(min(MiB, remaining))
                    if not block: return failed('source_changed')
                    digest.update(block)
                    view = memoryview(block)
                    while view:
                        size = output.write(view)
                        if not size: raise OSError('short write')
                        view = view[size:]
                    remaining -= len(block)
                if cancel.is_set(): return failed('cancelled')
                extra = source.read(1)
                after, current = os.fstat(source.fileno()), path.stat()
                if (extra or _metadata(before) != _metadata(after)
                        or _metadata(after)[:4] != _metadata(current)[:4]
                        or digest.hexdigest() != captured['sha256']):
                    return failed('source_changed')
                output.flush(); os.fsync(output.fileno())
        if cancel.is_set(): return failed('cancelled')
        return StagedFrame(key, dict(path=str(target), bytes=captured['bytes'],
                           sha256=digest.hexdigest()), perf_counter()-started)
    except (OSError, ValueError, MemoryError):
        return failed('copy_failed')


class UpscalePipeline:
    """One read slot + one write slot; only creator thread can coordinate."""
    def __init__(self, config=PipelineConfig()):
        self.config = config
        self._owner = get_ident()
        self._reads = ScenePreparationPool(enabled=config.prefetch,
            max_source_bytes=48*MiB, max_graph_bytes=16*MiB)
        self._condition = Condition()
        self._closed = False
        self._write = self._result = self._thread = None
        self._cancel = Event()
        self._prefetch_bytes = self._write_bytes = 0
        self._stats = dict(peak_payload_bytes=0, peak_writeback_jobs=0, writeback_submitted=0,
                           writeback_consumed=0, writeback_failed=0, copy_seconds=0., unfinished_worker=False)

    def _coordinator(self):
        if get_ident() != self._owner: raise RuntimeError('coordinator thread required')

    def _peak(self):
        self._stats['peak_payload_bytes'] = max(self._stats['peak_payload_bytes'],
                                                self._prefetch_bytes+self._write_bytes)

    def prepare(self, job):
        self._coordinator()
        size = job.source['bytes']+len(job.graph_bytes)
        if self._closed or size > self.config.max_prefetch_bytes: return False
        if not self._reads.submit(job.preparation()): return False
        with self._condition:
            self._prefetch_bytes = size; self._peak()
        return True

    def consume(self, job):
        self._coordinator()
        value = self._reads.take(job.preparation())
        if value is not None:
            with self._condition: self._prefetch_bytes = 0
            return replace(value, job_key=job.key)
        # Misses stay bounded until caller falls back/drains or close; a mismatched
        # key causes the underlying pool to discard, never relabel a stale read.
        return None

    def discard_prefetch(self):
        self._coordinator(); self._reads.discard()
        with self._condition: self._prefetch_bytes = 0

    def stage_output(self, job, captured_output, staging_path):
        self._coordinator()
        captured = _artifact(captured_output)
        target = Path(staging_path)
        if not target.is_absolute(): raise ValueError('absolute private staging path required')
        with self._condition:
            if (self._closed or not self.config.writeback or self._write is not None
                    or captured['bytes'] > self.config.max_writeback_bytes): return False
            self._cancel = Event()
            # The writer needs only the digest key, not the current graph/source
            # payload. Retaining a second graph here would exceed 64+32MiB.
            self._write = (job.key, captured, str(target), self._cancel)
            self._write_bytes = captured['bytes']; self._peak()
            if self._thread is None:
                self._thread = Thread(target=Context().run, args=(self._work,),
                                      name='upscale-private-writeback', daemon=True)
                try: self._thread.start()
                except (RuntimeError, OSError, MemoryError):
                    self._thread = None; self._write = None; self._write_bytes = 0
                    return False
            self._stats['peak_writeback_jobs'] = 1
            self._stats['writeback_submitted'] += 1
            self._condition.notify_all()
            return True

    def _work(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or (self._write is not None and self._result is None))
                if self._closed: return
                work = self._write
            result = _copy_output(*work)
            with self._condition:
                self._stats['copy_seconds'] += result.copy_seconds
                self._stats['writeback_failed'] += int(result.error is not None)
                if not self._closed and self._write is work and not work[3].is_set(): self._result = result
                self._condition.notify_all()
            del result, work

    def finish_output(self, job):
        self._coordinator()
        with self._condition:
            if self._closed or self._write is None: return None
            if self._write[0] != job.key: raise ValueError('pending writeback job differs')
            if self._result is None: return None
            result = self._result
            self._write = self._result = None; self._write_bytes = 0
            self._stats['writeback_consumed'] += int(result.error is None)
            return result

    def close(self):
        self._coordinator()
        started = monotonic()
        with self._condition:
            self._closed = True; self._cancel.set()
            self._write = self._result = None; self._write_bytes = self._prefetch_bytes = 0
            self._condition.notify_all()
        self._reads.close()
        if self._thread is not None: self._thread.join(max(0, 2-(monotonic()-started)))
        with self._condition:
            self._stats['unfinished_worker'] = bool(self._thread and self._thread.is_alive()) or self._reads.report()['unfinished_worker']

    def report(self):
        with self._condition:
            return dict(self._stats, reserved_payload_bytes=self._prefetch_bytes+self._write_bytes,
                        preparation=self._reads.report())
