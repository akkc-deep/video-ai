"""Explicit experiment-only Comfy node/model wall timers; no torch import.

Installed in a NEW Comfy experiment process, never into an existing service.
Node times are CPU wall intervals, not synchronized CUDA kernel durations.
"""
from functools import wraps
import inspect
import json
from pathlib import Path
import re
import subprocess
import sys
from threading import Event, RLock, Thread
from time import perf_counter, time
from uuid import UUID


_NODE_STAGES = {'LoadImage': 'wan.image_load', 'WanImageToVideo': 'wan.image_conditioning',
    'CLIPTextEncode': 'wan.text_encode', 'KSamplerAdvanced': 'wan.sample_unknown',
    'VAEDecode': 'wan.vae_decode', 'CreateVideo': 'wan.video_prepare', 'SaveVideo': 'wan.encode',
    'ImageUpscaleWithModel': 'upscale.inference', 'UpscaleModelLoader': 'upscale.model_loader',
    'UNETLoader': 'wan.model_loader', 'CLIPLoader': 'wan.text_loader', 'VAELoader': 'wan.vae_loader'}


def parse_gpu_sample(stdout):
    rows = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        values = [int(part.strip()) for part in line.split(',')]
        if len(values) != 3 or min(values) < 0 or values[2] > 100:
            raise ValueError('invalid numeric GPU sample')
        rows.append(dict(index=values[0], used_mib=values[1], utilization_percent=values[2]))
    if not rows:
        raise ValueError('empty GPU sample')
    return rows


class ComfyNodeMetrics:
    def __init__(self, output, *, max_events=100000, force_sampling=False):
        if type(max_events) is not int or max_events < 1:
            raise ValueError('max_events must be positive')
        self.output, self.max_events = Path(output), max_events
        if type(force_sampling) is not bool:
            raise ValueError('force_sampling must be bool')
        self.force_sampling = force_sampling
        self._patches, self._installed = [], set()
        self._lock, self._stop = RLock(), Event()
        self._sampler = None
        self.stages, self.gpu_peaks = {}, {}
        self.events = self.dropped = self.errors = 0

    def __enter__(self):
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.output.open('x', encoding='utf-8')
        self._start = perf_counter()
        self._write(dict(kind='session', started_at_unix=time(), timing='CPU node/model wall time; no CUDA synchronization',
            sampler_cache='force sampling; native model/text/input cache retained' if self.force_sampling else 'native',
            gpu_scope='device-wide sampled usage; not attributable exclusively to this process'))
        return self

    def _write(self, row):
        with self._lock:
            try:
                self._file.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
                self._file.flush()
            except Exception:
                self.errors += 1

    def _record(self, kind, stage, start, failed):
        elapsed = perf_counter()-start
        with self._lock:
            summary = self.stages.setdefault(stage, dict(calls=0, failed=0, seconds=0.0))
            summary['calls'] += 1
            summary['failed'] += int(failed)
            summary['seconds'] += elapsed
            if self.events < self.max_events:
                identity = {}
                try:
                    module = sys.modules.get('comfy_execution.utils')
                    context = module.get_executing_context() if module is not None else None
                    if context is not None and str(UUID(context.prompt_id)) == context.prompt_id:
                        identity['prompt_id'] = context.prompt_id
                        if isinstance(context.node_id, str) and re.fullmatch(r'[0-9:]{1,40}', context.node_id):
                            identity['node_id'] = context.node_id
                except Exception:
                    self.errors += 1
                self._write(dict(kind=kind, stage=stage, offset_seconds=start-self._start,
                                 seconds=elapsed, failed=failed, **identity))
                self.events += 1
            else:
                self.dropped += 1
            # Windows TerminateProcess bypasses __exit__. Retain the aggregate
            # prefix after every completed node, including raw-detail overflow.
            self._checkpoint()

    def _checkpoint(self):
        self._write(dict(kind='checkpoint', finalized=False, seconds=perf_counter()-self._start,
            stages=self.stages, gpu_devices=self.gpu_peaks, dropped_events=self.dropped,
            telemetry_errors=self.errors))

    def _patch(self, owner, name, stage, *, kind='node', sampler=False):
        key = (owner, name)
        if key in self._installed:
            return
        descriptor = inspect.getattr_static(owner, name)
        function = descriptor.__func__ if isinstance(descriptor, (staticmethod, classmethod)) else descriptor
        if not callable(function):
            return
        signature = inspect.signature(function) if sampler else None
        def classify(args, kwargs):
            if signature is None:
                return stage
            try:
                bound = signature.bind_partial(*args, **kwargs).arguments
                start, end, steps = (bound.get(k) for k in ('start_at_step', 'end_at_step', 'steps'))
                if all(type(v) is int for v in (start, end, steps)) and 0 <= start < end <= steps:
                    if start == 0 and end < steps:
                        return 'wan.high_sample'
                    if start > 0 and end == steps:
                        return 'wan.low_sample'
            except (ValueError, TypeError):
                pass
            return stage
        if inspect.iscoroutinefunction(function):
            @wraps(function)
            async def wrapped(*args, **kwargs):
                label, started, failed = classify(args, kwargs), perf_counter(), True
                try:
                    result = await function(*args, **kwargs)
                    failed = False
                    return result
                finally:
                    self._record(kind, label, started, failed)
        else:
            @wraps(function)
            def wrapped(*args, **kwargs):
                label, started, failed = classify(args, kwargs), perf_counter(), True
                try:
                    result = function(*args, **kwargs)
                    failed = False
                    return result
                finally:
                    self._record(kind, label, started, failed)
        replacement = type(descriptor)(wrapped) if isinstance(descriptor, (staticmethod, classmethod)) else wrapped
        self._patches.append((owner, name, name in vars(owner), descriptor))
        setattr(owner, name, replacement)
        self._installed.add(key)

    def install_nodes(self, mapping):
        for node, stage in _NODE_STAGES.items():
            cls = mapping.get(node)
            if cls is None:
                continue
            name = getattr(cls, 'FUNCTION', None)
            if not isinstance(name, str) or not hasattr(cls, name):
                name = 'execute' if hasattr(cls, 'execute') else None
            if name is not None:
                self._patch(cls, name, stage, sampler=node == 'KSamplerAdvanced')
                if node == 'KSamplerAdvanced' and self.force_sampling and (cls, 'IS_CHANGED') not in self._installed:
                    original = inspect.getattr_static(cls, 'IS_CHANGED', None)
                    self._patches.append((cls, 'IS_CHANGED', 'IS_CHANGED' in vars(cls), original))
                    setattr(cls, 'IS_CHANGED', classmethod(lambda cls, **kwargs: float('nan')))
                    self._installed.add((cls, 'IS_CHANGED'))

    def install_models(self, management):
        cls = getattr(management, 'LoadedModel', None)
        if cls is not None:
            for name in ('model_load', 'model_unload'):
                if hasattr(cls, name):
                    self._patch(cls, name, 'comfy.'+name, kind='model')

    def start_gpu_sampler(self, executable, *, interval_seconds=2.0):
        if interval_seconds < 1 or self._sampler is not None:
            raise ValueError('one GPU sampler with interval >=1 second is required')
        def sample():
            while not self._stop.is_set():
                try:
                    result = subprocess.run([str(executable), '--query-gpu=index,memory.used,utilization.gpu',
                        '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5, shell=False)
                    if result.returncode:
                        raise ValueError('GPU sample unavailable')
                    rows = parse_gpu_sample(result.stdout)
                    with self._lock:
                        for row in rows:
                            peak = self.gpu_peaks.setdefault(str(row['index']), dict(sampled_peak_used_mib=0,
                                utilization_sum=0, samples=0))
                            peak['sampled_peak_used_mib'] = max(peak['sampled_peak_used_mib'], row['used_mib'])
                            peak['utilization_sum'] += row['utilization_percent']; peak['samples'] += 1
                    self._write(dict(kind='gpu', offset_seconds=perf_counter()-self._start, devices=rows))
                    self._checkpoint()
                except Exception:
                    self._write(dict(kind='gpu_unavailable', offset_seconds=perf_counter()-self._start))
                self._stop.wait(interval_seconds)
        self._sampler = Thread(target=sample, name='lva01-gpu-sampler', daemon=True)
        self._sampler.start()

    def __exit__(self, exc_type, exc, traceback):
        self._stop.set()
        if self._sampler is not None:
            self._sampler.join(timeout=6)
        for owner, name, owned, descriptor in reversed(self._patches):
            if owned:
                setattr(owner, name, descriptor)
            else:
                delattr(owner, name)
        self._write(dict(kind='summary', finalized=True, seconds=perf_counter()-self._start,
            stages=self.stages, gpu_devices=self.gpu_peaks, dropped_events=self.dropped,
            telemetry_errors=self.errors, missing='No CUDA kernel timing, full model byte-load proof, or human quality inference'))
        self._file.close()
        return False
