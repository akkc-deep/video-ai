"""Opt-in current-thread observations with bounded raw event detail.

Use around an already-authorized local operation. This module does not start a
service, change requests, interpret success from Python returns, or observe
Comfy's child process. Missing measurements remain explicit.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import inspect
import json
import math
from pathlib import Path
import platform
import sys
from time import perf_counter


_FIELDS = ('hash_requests', 'hash_computations', 'hashed_bytes', 'file_accesses',
           'referenced_bytes', 'unknown_size_accesses', 'probe_processes',
           'full_decode_processes', 'partial_decode_processes', 'media_processes', 'model_stamp_checks')
_CHECKS = {'verify_global', 'capture_guard', 'guard', 'validate_artifact',
           'validate_clip', 'verify_artifact', 'verify_captured_bytes',
           'validate_media_receipt', 'validate_scene_submission',
           '_record_http', '_remote_validate', 'validate_upscale_frames',
           '_capture_composition_guard', 'verify_materialized'}
_STAGES = {
    'production_scene_clips': {'ensure': 'comfy.ensure', 'close': 'comfy.close',
        '_input': 'wan.image_prepare', '_technical': 'clip.technical'},
    'scene_comfy_transactions': {'recover_or_submit_scene_clip': 'wan.submit_and_track'},
    'scene_upscale_transactions': {'recover_or_submit_scene_frame': 'upscale.submit_and_track'},
    'production_scene_upscale': {'_extract': 'upscale.extract', '_copy': 'upscale.io',
        '_produce': 'upscale.batch'},
    'production_scene_composition': {'_produce': 'composition.total', '_inspect': 'composition.delivery_check'},
    '_scene_composition_materialized': {'materialize': 'composition.io'},
    '_scene_composition_commands': {'media_operation': 'composition.encode_or_probe'},
    'video': {'inspect_video': 'clip.probe', 'trim_scene_video': 'clip.trim'},
    'frames': {'extract_native_frame': 'clip.last_frame'},
    'scene_upscale': {'extract_scene_frames': 'upscale.extract',
        'verify_png': 'upscale.png_proof', 'png_sequence_hashes': 'upscale.batch_proof'},
    'production_scene_delivery': {'produce_scene_delivery': 'delivery.check'},
}
_MISSING = [
    'Comfy child-process model load/unload counts and cold/warm timings',
    'Wan text encoding, high/low sampling, VAE and SaveVideo node timings',
    'GPU utilization and sampled peak VRAM (requires independent sampler)',
    'per-frame GPU inference separate from HTTP tracking and IO',
    'selection-to-delivery wall clock and human parent acceptance intervals',
    'real GPU fixtures and human quality acceptance',
    'pre-existing HTTP worker threads and file hashing outside the named identity helpers',
]


def _zeros():
    return dict.fromkeys(_FIELDS, 0)


def classify_media_command(args):
    """Classify dedicated validation processes, without retaining argv/content.

    A validation output format must occur after the last input. A frame/time
    bound or selection filter makes this partial work, even with raw output.
    This counts attempts, never successful or complete execution evidence.
    """
    own = _zeros()
    tool = Path(str(args[0])).stem.lower() if args else ''
    if tool not in ('ffmpeg', 'ffprobe'):
        return own
    own['media_processes'] = 1
    own['probe_processes'] = int(tool == 'ffprobe')
    limited = any(flag in args for flag in ('-frames:v', '-vframes', '-frames',
                  '-t', '-to', '-ss', '-sseof', '-read_intervals'))
    limited = limited or any(isinstance(value, str) and any(part in value for part in
        ('select=', 'trim=', 'thumbnail=')) for value in args)
    if tool == 'ffprobe':
        decoding = '-count_frames' in args or '-show_frames' in args
    else:
        last_input = max((i+1 for i, value in enumerate(args) if value == '-i'), default=len(args))
        decoding = any(value == '-f' and i > last_input and i+1 < len(args) and
                       args[i+1] in ('null', 'rawvideo', 'framehash', 'framemd5')
                       for i, value in enumerate(args))
    own['full_decode_processes'] = int(decoding and not limited)
    own['partial_decode_processes'] = int(decoding and limited)
    return own


class LocalVideoMetrics:
    def __init__(self, *, mode, max_events=20000):
        if mode not in ('normal', 'recovery'):
            raise ValueError('mode must be normal or recovery')
        if type(max_events) is not int or max_events < 1:
            raise ValueError('max_events must be positive')
        self.mode, self.max_events = mode, max_events
        self.calls, self._active, self._codes = [], {}, {}
        self._callsites = {}
        self._stack, self._files = [], set()
        self.totals, self.dropped = _zeros(), 0
        self._started = False
        self._ended = False
        self._observation_errors = 0

    def __enter__(self):
        if self._started:
            raise RuntimeError('metrics context cannot be reused')
        if sys.getprofile() is not None:
            raise RuntimeError('an existing profiler is active')
        self._started = True
        self._start = perf_counter()
        sys.setprofile(self._profile)
        return self

    def __exit__(self, exc_type, exc, traceback):
        sys.setprofile(None)
        self._elapsed = perf_counter()-self._start
        self._ended = True
        self.outcome = 'returned' if exc_type is None else 'interrupted_or_failed'
        # A return event also occurs during exception unwinding. No per-call
        # success claim is inferred from it; operation results belong to caller.
        self._active.clear()
        self._stack.clear()
        return False

    def _select(self, code, module):
        if code in self._codes:
            return self._codes[code]
        selected = None
        name, short = code.co_name, module.rsplit('.', 1)[-1]
        if not code.co_flags & (inspect.CO_GENERATOR | inspect.CO_COROUTINE | inspect.CO_ASYNC_GENERATOR):
            if module == 'subprocess' and name == '__init__' and code.co_qualname == 'Popen.__init__':
                selected = ('media', 'media.process', 'stdlib/subprocess.py')
            elif module.startswith('video_ai.') and short != 'local_video_metrics':
                source = module.replace('.', '/')+'.py'
                if short == 'manifest' and name in ('hash_file', '_hash_open_file'):
                    selected = ('hash', 'validation.hash', source)
                elif short == 'verification' and name in ('_read_open_bytes', 'protected_hash', 'protected_bytes', 'verify'):
                    selected = ('check', 'validation.protection', source)
                elif short == 'production_state' and code.co_qualname == 'ArtifactStamp.verify':
                    selected = ('check', 'validation.model_stamp', source)
                elif short in _STAGES and name in _STAGES[short]:
                    selected = ('stage', _STAGES[short][name], source)
                elif (short in {'scene_clip_records', 'scene_revision_records', 'scene_comfy_transactions',
                        'scene_upscale_transactions', 'scene_media_records', 'production_scene_composition',
                        '_scene_composition_materialized', '_scene_upscale_records'} and name in _CHECKS):
                    selected = ('check', 'validation.'+name, source)
        self._codes[code] = selected
        return selected

    def _profile(self, frame, event, arg):
        # Observer bugs must not alter original generation or mask exceptions.
        try:
            if event == 'call':
                spec = self._select(frame.f_code, frame.f_globals.get('__name__', ''))
                if spec is None:
                    return
                kind, stage, source = spec
                command = None
                if kind == 'media':
                    args = frame.f_locals.get('args')
                    if not isinstance(args, (tuple, list)) or not args:
                        return
                    tool = Path(str(args[0])).stem.lower()
                    if tool not in ('ffmpeg', 'ffprobe'):
                        return
                    # Keep only flags needed to classify work. No argv is retained.
                    command = classify_media_command(args)
                caller = frame.f_back
                caller_module = caller.f_globals.get('__name__', '') if caller else ''
                caller_location = ((caller_module.replace('.', '/')+'.py:'+str(caller.f_lineno))
                                   if caller_module.startswith('video_ai.') else 'external')
                row = dict(id=len(self.calls)+self.dropped, parent_id=self._stack[-1]['id'] if self._stack else None,
                    kind=kind, stage=stage, mode=self.mode,
                    source=source+':'+str(frame.f_code.co_firstlineno)+':'+frame.f_code.co_name,
                    caller=caller_location, offset_seconds=perf_counter()-self._start,
                    seconds=0.0, self_seconds=0.0, counters=_zeros(), unique_files=0)
                state = dict(row=row, start=perf_counter(), child_seconds=0.0, files=set(), command=command)
                self._active[id(frame)] = state
                self._stack.append(row)
                if len(self.calls) < self.max_events:
                    self.calls.append(row)
                else:
                    self.dropped += 1
            elif event == 'return':
                state = self._active.pop(id(frame), None)
                if state is None:
                    return
                row = state['row']
                self._stack.pop()
                elapsed = perf_counter()-state['start']
                row['seconds'] = elapsed
                row['self_seconds'] = max(0.0, elapsed-state['child_seconds'])
                own = self._own_counts(frame, arg, state)
                for key, value in own.items():
                    row['counters'][key] += value
                    self.totals[key] += value
                row['unique_files'] = len(state['files'])
                self._files.update(state['files'])
                key = (row['source'], row['caller'], row['stage'])
                summary = self._callsites.setdefault(key, dict(source=row['source'], caller=row['caller'],
                    stage=row['stage'], calls=0, seconds=0.0, self_seconds=0.0, counters=_zeros()))
                summary['calls'] += 1
                summary['seconds'] += row['seconds']
                summary['self_seconds'] += row['self_seconds']
                for field in _FIELDS:
                    summary['counters'][field] += row['counters'][field]
                parent_id = row['parent_id']
                if parent_id is not None:
                    # Stack depth is small; no frame or argument survives exit.
                    parent = next((p for p in reversed(tuple(self._active.values())) if p['row']['id'] == parent_id), None)
                    if parent is not None:
                        parent['child_seconds'] += elapsed
                        parent['files'].update(state['files'])
                        for key in _FIELDS:
                            parent['row']['counters'][key] += row['counters'][key]
        except Exception:
            self._observation_errors += 1

    def _own_counts(self, frame, result, state):
        own = _zeros()
        name = frame.f_code.co_name
        module = frame.f_globals.get('__name__', '')
        identity = None
        if module == 'video_ai.runtime.manifest' and name == 'hash_file':
            own['hash_requests'] = own['file_accesses'] = 1
            identity = result
            size = getattr(identity, 'bytes', None)
            if type(size) is int:
                own['referenced_bytes'] = size
            else:
                own['unknown_size_accesses'] = 1
        elif (module == 'video_ai.runtime.manifest' and name == '_hash_open_file') or (
                module == 'video_ai.runtime.verification' and name == '_read_open_bytes'):
            identity = result[1] if name == '_read_open_bytes' and isinstance(result, tuple) else result
            # Only completed digests with an actual byte count are computations.
            if type(getattr(identity, 'bytes', None)) is int:
                own['hash_computations'] = 1
                own['hashed_bytes'] = identity.bytes
        elif module == 'video_ai.runtime.production_state' and frame.f_code.co_qualname == 'ArtifactStamp.verify':
            own['model_stamp_checks'] = 1
        command = state['command']
        if command is not None:
            for key, value in command.items():
                own[key] += value
        path = getattr(identity, 'path', None)
        if isinstance(path, str):
            state['files'].add(hashlib.sha256(path.encode('utf-8')).hexdigest())
        return own

    def report(self):
        if not self._ended:
            raise RuntimeError('exit metrics scope before reading the report')
        return deepcopy(dict(schema_version=1, mode=self.mode, outcome=self.outcome,
            wall_seconds=self._elapsed, calls=self.calls, totals=self.totals,
            callsite_totals=list(self._callsites.values()),
            aggregate_complete=not self._observation_errors,
            unique_files=len(self._files), dropped_events=self.dropped,
            observation_errors=self._observation_errors,
            complete=not (self.dropped or self._observation_errors),
            environment=dict(python=platform.python_version(), platform=platform.system(),
                             machine=platform.machine()),
            missing_measurements=_MISSING,
            semantics=dict(timing='inclusive and self; do not sum nested inclusive durations',
                file_accesses='hash requests, including protected cache hits; not OS reads',
                hash_requests='manifest.hash_file entries only; direct protected-byte hashes are separate computations, so subtraction is not a cache-hit rate',
                full_decode_processes='attempted unbounded frame-scanning probes and dedicated full-decoding FFmpeg outputs; bounded extraction counted separately',
                aggregate_complete='no observer errors within the selected current-thread function scope; not whole-process coverage',
                scope='current thread only; caller supplies quality, waits and end-to-end boundaries')))


def summarize_samples(samples):
    groups = defaultdict(list)
    for sample in samples:
        for key in ('wall_seconds', 'human_wait_seconds', 'usable_video_seconds'):
            value = sample[key]
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError('sample times must be finite nonnegative numbers')
        if sample['human_wait_seconds'] > sample['wall_seconds']:
            raise ValueError('human wait exceeds wall time')
        if sample['mode'] not in ('normal', 'recovery') or sample['temperature'] not in ('cold', 'warm'):
            raise ValueError('explicit mode and cold/warm identity required')
        if any(type(sample[key]) is not bool for key in ('accepted', 'failed', 'redone')):
            raise ValueError('explicit outcome booleans required')
        if sample['accepted'] and sample['failed']:
            raise ValueError('failed sample cannot be accepted')
        groups[sample['mode']+'/'+sample['temperature']].append(sample)
    result = {}
    for key, rows in groups.items():
        times = sorted(s['wall_seconds']-s['human_wait_seconds'] for s in rows)
        def percentile(p):
            position = (len(times)-1)*p
            lo, hi = math.floor(position), math.ceil(position)
            return times[lo]+(times[hi]-times[lo])*(position-lo)
        usable = sum(s['usable_video_seconds'] for s in rows if s['accepted'])
        result[key] = dict(samples=len(rows), clip_p50_seconds=percentile(.5), clip_p95_seconds=percentile(.95),
            human_wait_seconds=sum(s['human_wait_seconds'] for s in rows), usable_video_seconds=usable,
            wall_seconds_per_usable_video_second=sum(times)/usable if usable else None,
            failure_rate=sum(s['failed'] for s in rows)/len(rows), redo_rate=sum(s['redone'] for s in rows)/len(rows))
    return result


def write_report(report, output):
    """Write new report files only. Pass the observer's redacted report."""
    output = Path(output)
    markdown = output.with_suffix('.md')
    if output.suffix != '.json':
        raise ValueError('report must have a .json suffix')
    if output.exists() or markdown.exists():
        raise FileExistsError('report already exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = ['# Local video observations', '',
             'Current-thread observations; GPU/quality and full-film speedup are unverified.', '',
             f'Raw detail complete: {report["complete"]}; dropped detail events: {report["dropped_events"]}; '
             f'aggregates complete: {report["aggregate_complete"]}.', '',
             '| Source | Calls | Inclusive seconds | Self seconds | Hashes | Decodes |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    grouped = {}
    for row in report['callsite_totals']:
        values = grouped.setdefault(row['source'], [0, 0.0, 0.0, 0, 0])
        values[0] += row['calls']; values[1] += row['seconds']; values[2] += row['self_seconds']
        values[3] += row['counters']['hash_computations']; values[4] += row['counters']['full_decode_processes']
    for source, (count, inclusive, own, hashes, decodes) in sorted(grouped.items()):
        lines.append(f'| {source} | {count} | {inclusive:.6f} | {own:.6f} | {hashes} | {decodes} |')
    lines += ['', 'Nested inclusive times and counters overlap; do not add rows.', '',
              'Missing: '+ '; '.join(report['missing_measurements'])]
    with output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)+'\n')
    with markdown.open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines)+'\n')
