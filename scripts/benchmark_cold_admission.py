"""Bounded, read-only cold source admission probe; never advances generation.

Only the public RunLock lifecycle and the requested JSON report may write.
ffmpeg/ffprobe decoding to stdout is allowed; rendering to files is refused.
Use a separate process per source version. Cold means fresh application scopes,
not an operating-system disk-cache flush. Instrumentation adds timing overhead.
"""
import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from functools import lru_cache, wraps
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys
from time import perf_counter
from types import SimpleNamespace


class ProbeSideEffect(RuntimeError):
    pass


@lru_cache(maxsize=1)
def windows_argument_api():
    import ctypes
    from ctypes import wintypes
    shell32 = ctypes.WinDLL('shell32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    parse = shell32.CommandLineToArgvW
    parse.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int))
    parse.restype = ctypes.POINTER(wintypes.LPWSTR)
    release = kernel32.LocalFree
    release.argtypes = (ctypes.c_void_p,)
    release.restype = ctypes.c_void_p
    return ctypes, parse, release


def process_arguments(command):
    """Audit events contain Windows' serialized command line, without a shell."""
    if isinstance(command, (list, tuple)):
        return [str(item) for item in command]
    if not isinstance(command, str) or os.name != 'nt' or not command or '\0' in command:
        raise ProbeSideEffect('probe requires an explicit native decoder command')
    ctypes, parse, release = windows_argument_api()
    count = ctypes.c_int()
    arguments = parse(command, ctypes.byref(count))
    if not arguments:
        raise ProbeSideEffect('Windows refused decoder command-line parsing')
    try:
        return [arguments[index] for index in range(count.value)]
    finally:
        release(ctypes.cast(arguments, ctypes.c_void_p))


class ReadOnlyGuard:
    """Audit Python mutations and process/network entrypoints during admission."""
    def __init__(self):
        self.active = False
        self.processes = Counter()
        sys.addaudithook(self.check)

    def __enter__(self):
        self.active = True
        return self

    def __exit__(self, *exc):
        self.active = False

    @contextmanager
    def suspended(self):
        previous = self.active
        self.active = False
        try: yield
        finally: self.active = previous

    def check(self, event, args):
        if not self.active: return
        if event == 'open':
            if args[0] == os.devnull:
                return
            flags = args[2] or 0
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                raise ProbeSideEffect('probe refused file write: '+str(args[0]))
        elif event in ('os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.link',
                       'os.symlink', 'os.truncate', 'os.chmod', 'os.utime'):
            raise ProbeSideEffect('probe refused filesystem mutation: '+event)
        elif event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo',
                       'os.system', 'os.exec', 'os.posix_spawn', 'os.spawn'):
            raise ProbeSideEffect('probe refused external effect: '+event)
        elif event == 'subprocess.Popen':
            executable, command = args[:2]
            command = process_arguments(command)
            if not command: raise ProbeSideEffect('probe refused an empty process command')
            if executable is None: executable = command[0]
            name = Path(str(executable)).name.casefold()
            environment = args[3] if len(args) > 3 and args[3] is not None else os.environ
            if '-report' in command or environment.get('FFREPORT'):
                raise ProbeSideEffect('probe refused decoder log-file output')
            allowed = name in ('ffprobe', 'ffprobe.exe') and '-o' not in command
            if name in ('ffmpeg', 'ffmpeg.exe'):
                allowed = (len(command) >= 4 and command[-1] in ('-', 'pipe:1')
                    and '-i' in command and '-f' in command
                    and command[command.index('-f')+1] in ('null', 'rawvideo'))
            if not allowed:
                raise ProbeSideEffect('probe refused non-decoder process: '+str(executable))
            self.processes[name] += 1


def select_source(root):
    try: root = Path(root).resolve(strict=True)
    except OSError as exc: raise ValueError('source root does not exist: '+str(root)) from exc
    source = root/'src' if (root/'src/video_ai/__init__.py').is_file() else root
    if not (source/'video_ai/__init__.py').is_file():
        raise ValueError('source root must contain src/video_ai or video_ai')
    return source


class CallCounts:
    """Wrap named functions and imported aliases, avoiding a global profiler."""
    def __init__(self):
        self.counts = Counter()
        self.restore = []

    def install(self):
        aliases = {}
        targets = {
            '_scene_revision_origins': ('capture_origin', '_read_source_clip_record', '_source_clip_record'),
            'reference_image_records': ('_verify_reference_provenance', 'build_reference_image_acceptance',
                'require_reference_image_acceptance', '_prior'),
            'image_selection_records': ('load_committed_plan', '_load_accepted', '_candidates'),
            'scene_revision_records': ('require_scene_revision', 'revision_inventory', 'revision_raw_inventory',
                'revision_cached_read', '_verify_read_boundary'),
            'scene_clip_records': ('scene_context', 'collect_progress', 'validate_clip'),
            '_protected_continuity_inputs': ('verify_protected_continuity_file',),
            'manifest': ('_hash_open_file',),
        }
        for module_name, names in targets.items():
            module = importlib.import_module('video_ai.runtime.'+module_name)
            for name in names:
                function = getattr(module, name, None)
                if function is not None:
                    aliases[function] = self.wrapper(module_name+'.'+name, function)
        scenes = importlib.import_module('video_ai.planning.production_scenes')
        aliases[scenes.canonical_digest] = self.wrapper('canonical_digest', scenes.canonical_digest)
        for module in tuple(sys.modules.values()):
            if not getattr(module, '__name__', '').startswith('video_ai.'): continue
            for name, value in tuple(vars(module).items()):
                try: replacement = aliases.get(value)
                except TypeError: continue
                if replacement is not None: self.patch(module, name, replacement)
        methods = {
            'scene_revision_records': {'RevisionGuard': ('verify_captured_bytes', 'verify_frozen')},
            '_continuity_byte_guard': {'ByteGuard': ('verify',)},
            '_protected_continuity_inputs': {'_Directory': ('verify',), '_Protection': ('_verify', 'verify_record', 'verify')},
            'verification': {'_NativeInput': ('verify', '_canonical_path'), '_WholeInputWindow': ('verify', 'close')},
        }
        for module_name, classes in methods.items():
            module = importlib.import_module('video_ai.runtime.'+module_name)
            for class_name, names in classes.items():
                cls = getattr(module, class_name)
                for name in names:
                    self.patch(cls, name, self.wrapper(class_name+'.'+name, getattr(cls, name)))
        self.patch(Path, 'stat', self.wrapper('Path.stat', Path.stat))
        self.patch(os, 'scandir', self.wrapper('os.scandir', os.scandir))
        return self

    def wrapper(self, label, function):
        @wraps(function)
        def counted(*args, **kwargs):
            self.counts[label] += 1
            if label == '_scene_revision_origins.capture_origin' and self.counts[label] % 25 == 1:
                print('[cold-probe] source '+str(args[0].options['run_id'])+' '+str(args[1])+':'+str(args[2])
                      +' (node '+str(self.counts[label])+')', flush=True)
            return function(*args, **kwargs)
        return counted

    def patch(self, owner, name, replacement):
        self.restore.append((owner, name, getattr(owner, name)))
        setattr(owner, name, replacement)

    def close(self):
        for owner, name, original in reversed(self.restore): setattr(owner, name, original)
        self.restore.clear()


def measure_probe(runtime, *, max_seconds, counts=None, publish=None):
    """Keep phase cleanup inside timings and retain partial results on failure."""
    counts = counts if counts is not None else Counter()
    report = dict(complete=False, status='running', phases={}, collected_records=None)
    started = perf_counter()
    report['bound_policy'] = ('Cooperative deadline at admission checkpoints; single OS reads/decoder '
        'calls and cleanup may overrun. Incomplete phases are never completion measurements.')
    def stopped(): return perf_counter()-started >= max_seconds
    def save():
        report['elapsed_seconds'] = perf_counter()-started
        report['deadline_exceeded'] = report['elapsed_seconds'] >= max_seconds
        report['calls'] = dict(counts)
        if publish is not None: publish(report)
    @contextmanager
    def phase(name):
        before = Counter(counts); begin = perf_counter()
        row = report['phases'][name] = dict(status='running')
        save()
        try:
            yield
            row['status'] = 'completed'
        except BaseException as exc:
            row['status'] = 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed'
            row['error'] = dict(kind=type(exc).__name__, message=str(exc))
            raise
        finally:
            row['seconds'] = perf_counter()-begin
            row['calls'] = dict(Counter(counts)-before)
            save()
    stack = ExitStack()
    try:
        with runtime.revision_scope(), runtime.control(stopped):
            try:
                with phase('load_frozen_inputs'):
                    if stopped(): raise KeyboardInterrupt('probe deadline')
                    frozen = runtime.load_frozen()
                with phase('protection_setup'):
                    stack.enter_context(runtime.lock())
                    stack.enter_context(runtime.protection(frozen))
                with phase('load_prepared_inputs'):
                    if stopped(): raise KeyboardInterrupt('probe deadline')
                    units, timeline = runtime.load_prepared(frozen)
                with phase('entry_preflight_and_collect'):
                    if stopped(): raise KeyboardInterrupt('probe deadline')
                    def operation(context):
                        _, records = runtime.collect(context)
                        report['collected_records'] = len(records)
                        return SimpleNamespace(status='probe_complete', error=None)
                    result = runtime.entry(frozen, units, timeline, operation)
                    report['entry_status'] = result.status
                    if result.status == 'interrupted': raise KeyboardInterrupt(str(result.error))
                    if result.status != 'probe_complete':
                        raise RuntimeError('entry refused preflight: '+str(result.error))
            finally:
                with phase('final_protection_cleanup'): stack.close()
        report.update(complete=True, status='completed')
    except KeyboardInterrupt as exc:
        report.update(status='interrupted', error=dict(kind=type(exc).__name__, message=str(exc)))
    except Exception as exc:
        report.update(status='failed', error=dict(kind=type(exc).__name__, message=str(exc)))
    finally:
        save()
    return report


class Runtime:
    def __init__(self, run, guard):
        from video_ai.runtime import production_inputs, production_image_selection, production_scene_clips
        from video_ai.runtime import scene_clip_records, scene_revision_records, scene_review_control, verification
        from video_ai.runtime.production_state import RunLock
        self.inputs, self.prepared, self.clips = production_inputs, production_image_selection, production_scene_clips
        self.records, self.revisions, self.verification = scene_clip_records, scene_revision_records, verification
        self.revision_scope = scene_revision_records.revision_scope
        self.control = lambda stop: scene_review_control.review_admission_control(stop_requested=stop)
        self.run, self.guard, self.RunLock = run, guard, RunLock
        self.held_lock = None

    def load_frozen(self):
        with self.revisions.revision_read_transaction(): return self.inputs.load_frozen_inputs(self.run)

    @contextmanager
    def lock(self):
        # This is the sole authorized production write: the public lock lifecycle.
        with self.guard.suspended():
            lock = self.RunLock(self.run)
            lock.__enter__()
        self.held_lock = lock
        try: yield lock
        finally:
            with self.guard.suspended(): lock.__exit__(*sys.exc_info())
            self.held_lock = None

    def protection(self, frozen): return self.verification.scene_input_protection(frozen)

    def load_prepared(self, frozen):
        with self.revisions.revision_read_transaction(): return self.prepared.load_prepared_inputs(frozen)

    def collect(self, context): return self.records.collect_progress(context)

    def entry(self, frozen, units, timeline, operation):
        from video_ai.runtime.paths import RuntimePaths
        from video_ai.runtime.scene_execution_records import rendering_mode
        if rendering_mode(frozen) is not None and not (self.run/'production/scene-rendering/execution-budget.json').is_file():
            raise ProbeSideEffect('read-only probe requires existing execution-budget.json')
        # _entry uses only these logger attributes during read-only preflight.
        # Constructing RunLogger would create directories, so use no writer API.
        logger = SimpleNamespace(run_dir=self.run, production=True)
        return self.clips._entry(frozen, units, timeline, paths=RuntimePaths.from_config(frozen.config),
            logger=logger, lock=self.held_lock, operation=operation)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-seconds', type=float, default=120)
    parser.add_argument('--source-root', type=Path, help='Checkout/snapshot root or its src directory; selected before imports')
    args = parser.parse_args(argv)
    if not math.isfinite(args.max_seconds) or args.max_seconds <= 0:
        parser.error('max-seconds must be a positive finite number')
    if any(name == 'video_ai' or name.startswith('video_ai.') for name in sys.modules):
        parser.error('source selection requires a fresh Python process')
    try: source = select_source(args.source_root or Path(__file__).resolve().parents[1])
    except (OSError, ValueError) as exc: parser.error(str(exc))
    run = args.run_dir.resolve(strict=True); output = args.output.resolve()
    if output.is_relative_to(run) or output.is_relative_to(Path('E:/VideoAI/work')):
        parser.error('report must be outside production work and the probed run')
    output.parent.mkdir(parents=True, exist_ok=True)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source))
    guard = ReadOnlyGuard()
    runtime = Runtime(run, guard)
    from video_ai.runtime.execution_limits import production_execution
    production_probe = production_execution(measure_probe)
    metadata = dict(schema_version=1, run_dir=str(run), source_root=str(source), max_seconds=args.max_seconds,
        execution_policy='unlimited_v1 with an independent cooperative max-seconds cap',
        scope='Read-only real cold admission; no generation, observation admission, persistence or network. '
              'Public RunLock lifecycle may write/reclaim its own lock evidence. Decoding to stdout is allowed.',
        timing='Instrumented wall time; fresh application admission scopes, OS cache unchanged. '
               'Incomplete/interrupted timings are bounded prefixes, not full baseline completion.',
        source_sha256={str(path.relative_to(source)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((source/'video_ai/runtime').glob('*.py'))})
    def publish(report):
        with guard.suspended():
            output.write_text(json.dumps(dict(metadata, **report), indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
        print('[cold-probe] '+report['status']+' '+str(round(report['elapsed_seconds'], 3))+'s '
            +', '.join(name+':'+value['status'] for name, value in report['phases'].items()), flush=True)
    instrumentation = CallCounts().install()
    try:
        with guard:
            report = production_probe(runtime, max_seconds=args.max_seconds, counts=instrumentation.counts, publish=publish)
    finally:
        instrumentation.close()
    report['decoder_processes'] = dict(guard.processes)
    publish(report)
    return 0 if report['complete'] else 130 if report['status'] == 'interrupted' else 1


if __name__ == '__main__':
    raise SystemExit(main())
