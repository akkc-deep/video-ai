"""Offline checks for the production probe's bounds and read-only contract."""
from contextlib import contextmanager, nullcontext
import importlib.util
from pathlib import Path
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest


def probe_module():
    path = Path(__file__).resolve().parents[2]/'scripts/benchmark_cold_admission.py'
    assert path.is_file(), 'cold probe must be implemented'
    spec = importlib.util.spec_from_file_location('cold_probe_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_measures_cleanup_and_never_advances_generation():
    probe = probe_module(); events = []
    @contextmanager
    def scope(name):
        events.append(name+' enter')
        try: yield
        finally: events.append(name+' exit')
    class Runtime:
        revision_scope = lambda self: scope('revision')
        control = lambda self, stop: nullcontext()
        load_frozen = lambda self: events.append('frozen') or 'frozen'
        lock = lambda self: scope('lock')
        protection = lambda self, frozen: scope('protection')
        def load_prepared(self, frozen):
            with scope('prepared boundary'): return 'units', 'timeline'
        def entry(self, frozen, units, timeline, operation):
            events.append('entry'); operation('context')
            return SimpleNamespace(status='probe_complete', error=None)
        def collect(self, context): events.append('collect'); return [], {'clip': {}}
    report = probe.measure_probe(Runtime(), max_seconds=10)
    assert report['complete'] is True
    assert list(report['phases']) == ['load_frozen_inputs', 'protection_setup',
        'load_prepared_inputs', 'entry_preflight_and_collect', 'final_protection_cleanup']
    assert events.index('prepared boundary exit') < events.index('entry')
    assert events.index('collect') < events.index('protection exit') < events.index('lock exit')
    assert events[-1] == 'revision exit'
    assert report['collected_records'] == 1


def test_interrupted_probe_reports_partial_phase_and_closes_protection():
    probe = probe_module(); closed = []
    @contextmanager
    def protection():
        try: yield
        finally: closed.append(True)
    runtime = SimpleNamespace(revision_scope=nullcontext, control=lambda stop:nullcontext(),
        load_frozen=lambda:object(), lock=nullcontext, protection=lambda frozen:protection(),
        load_prepared=lambda frozen:(_ for _ in ()).throw(KeyboardInterrupt('deadline')))
    report = probe.measure_probe(runtime, max_seconds=1)
    assert not report['complete'] and report['status'] == 'interrupted'
    assert report['phases']['load_prepared_inputs']['status'] == 'interrupted'
    assert report['phases']['final_protection_cleanup']['status'] == 'completed'
    assert closed == [True]


def test_readonly_guard_refuses_mutation_network_and_rendering(tmp_path):
    probe = probe_module(); guard = probe.ReadOnlyGuard()
    with guard:
        with pytest.raises(probe.ProbeSideEffect): (tmp_path/'forbidden.json').write_text('{}')
        with pytest.raises(probe.ProbeSideEffect): guard.check('socket.connect', ())
        with pytest.raises(probe.ProbeSideEffect):
            guard.check('subprocess.Popen', ('ffmpeg.exe', ['ffmpeg.exe', '-i', 'x', 'movie.mp4']))
        guard.check('subprocess.Popen', ('ffmpeg.exe', ['ffmpeg.exe', '-i', 'x', '-f', 'null', '-']))
        guard.check('subprocess.Popen', ('ffprobe.exe', ['ffprobe.exe', '-show_streams', 'x']))
    assert not (tmp_path/'forbidden.json').exists()


def test_readonly_guard_allows_the_exact_null_device_only(tmp_path):
    probe = probe_module(); guard = probe.ReadOnlyGuard()
    with guard:
        with open(os.devnull, 'wb') as sink:
            assert sink.write(b'discarded decoder diagnostics') > 0
        with pytest.raises(probe.ProbeSideEffect):
            (tmp_path / 'nul.log').write_bytes(b'file')


@pytest.mark.skipif(os.name != 'nt', reason='Exercises native Windows command-line parsing')
@pytest.mark.parametrize('format_name', ['null', 'rawvideo'])
@pytest.mark.parametrize('explicit_executable', [True, False])
def test_windows_audit_command_string_allows_stdout_decode(format_name, explicit_executable):
    probe = probe_module(); guard = probe.ReadOnlyGuard()
    executable = r'C:\Program Files\Video Tools\ffmpeg.exe'
    arguments = [executable, '-nostdin', '-v', 'error', '-xerror', '-i',
        r'C:\Video Work\scene input.mp4', '-f', format_name, '-']
    command = subprocess.list2cmdline(arguments)
    with guard:
        guard.check('subprocess.Popen', (executable if explicit_executable else None, command, None, {}))
    assert guard.processes['ffmpeg.exe'] == 1


@pytest.mark.skipif(os.name != 'nt', reason='Exercises native Windows command-line parsing')
def test_windows_quoted_ffprobe_and_escaping_round_trip():
    probe = probe_module(); guard = probe.ReadOnlyGuard()
    executable = r'C:\Program Files\Video Tools\ffprobe.exe'
    arguments = [executable, '-v', 'error', '-show_streams', '-of', 'json',
        'C:\\Video Work\\input "quoted".mp4']
    command = subprocess.list2cmdline(arguments)
    assert probe.process_arguments(command) == arguments
    with guard:
        guard.check('subprocess.Popen', (executable, command, None, {}))
    assert guard.processes['ffprobe.exe'] == 1


@pytest.mark.parametrize(('tool', 'arguments', 'environment'), [
    ('ffmpeg.exe', ['-i', 'input.mp4', '-f', 'rawvideo', 'render.raw'], {}),
    ('ffprobe.exe', ['-show_streams', '-o', 'metadata.json', 'input.mp4'], {}),
    ('ffmpeg.exe', ['-report', '-i', 'input.mp4', '-f', 'null', '-'], {}),
    ('ffmpeg.exe', ['-i', 'input.mp4', '-f', 'null', '-'], {'FFREPORT': 'file=leak.log'}),
    ('ffprobe.exe', ['-report', '-show_streams', 'input.mp4'], {}),
])
def test_decoder_file_and_report_outputs_remain_forbidden(tool, arguments, environment):
    probe = probe_module(); guard = probe.ReadOnlyGuard()
    executable = str(Path(r'C:\Program Files\Video Tools')/tool) if os.name == 'nt' else tool
    arguments = [executable, *arguments]
    command = subprocess.list2cmdline(arguments) if os.name == 'nt' else arguments
    with guard, pytest.raises(probe.ProbeSideEffect):
        guard.check('subprocess.Popen', (executable, command, None, environment))
    assert not guard.processes


def test_source_root_selection_accepts_snapshot_root_before_product_imports(tmp_path):
    probe = probe_module(); package = tmp_path/'src/video_ai'; package.mkdir(parents=True)
    (package/'__init__.py').write_text('')
    assert probe.select_source(tmp_path) == tmp_path/'src'
    with pytest.raises(ValueError): probe.select_source(tmp_path/'missing')


def test_cli_missing_options_is_partial_readonly_report(tmp_path):
    root = Path(__file__).resolve().parents[2]
    run = tmp_path/'unprepared-run'; run.mkdir()
    output = tmp_path/'probe.json'
    result = subprocess.run([sys.executable, str(root/'scripts/benchmark_cold_admission.py'),
        '--run-dir', str(run), '--output', str(output), '--max-seconds', '1'],
        capture_output=True, text=True, timeout=30, cwd=root)
    assert result.returncode == 1, result.stdout+result.stderr
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['complete'] is False and report['status'] == 'failed'
    assert report['phases']['load_frozen_inputs']['status'] == 'failed'
    assert report['phases']['final_protection_cleanup']['status'] == 'completed'
    assert report['source_root'] == str(root/'src')
    assert report['execution_policy'] == 'unlimited_v1 with an independent cooperative max-seconds cap'
    assert report['source_sha256'] and report['calls'] is not None
    assert list(run.iterdir()) == []
