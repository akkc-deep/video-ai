import asyncio
import json
from types import SimpleNamespace

import pytest


def test_node_methods_keep_results_signatures_and_restore_descriptors(tmp_path):
    from video_ai.runtime.local_comfy_metrics import ComfyNodeMetrics
    class Sample:
        FUNCTION = 'sample'
        def sample(self, start_at_step, end_at_step, steps, positive):
            return positive
    class Encode:
        @classmethod
        async def execute(cls, text):
            return text
    original_sample = Sample.__dict__['sample']
    original_encode = Encode.__dict__['execute']
    nodes = {'KSamplerAdvanced': Sample, 'CLIPTextEncode': Encode}
    value = object()
    with ComfyNodeMetrics(tmp_path/'nodes.jsonl') as metrics:
        metrics.install_nodes(nodes)
        metrics.install_nodes(nodes)  # init hook must be idempotent
        assert Sample().sample(0, 20, 40, value) is value
        assert Sample().sample(20, 40, 40, value) is value
        assert asyncio.run(Encode.execute('SECRET prompt')) == 'SECRET prompt'
    assert Sample.__dict__['sample'] is original_sample
    assert Encode.__dict__['execute'] is original_encode
    rows = [json.loads(line) for line in (tmp_path/'nodes.jsonl').read_text().splitlines()]
    assert [r['stage'] for r in rows if r['kind'] == 'node'] == ['wan.high_sample', 'wan.low_sample', 'wan.text_encode']
    assert 'SECRET' not in json.dumps(rows)
    assert all(row['seconds'] >= 0 for row in rows if row['kind'] == 'node')


def test_model_operations_and_failures_are_observed_without_masking(tmp_path):
    from video_ai.runtime.local_comfy_metrics import ComfyNodeMetrics
    class Loaded:
        def model_load(self):
            return 7
        def model_unload(self):
            raise ValueError('SECRET error')
    management = SimpleNamespace(LoadedModel=Loaded)
    with ComfyNodeMetrics(tmp_path/'models.jsonl') as metrics:
        metrics.install_models(management)
        assert Loaded().model_load() == 7
        with pytest.raises(ValueError, match='SECRET'):
            Loaded().model_unload()
    rows = [json.loads(line) for line in (tmp_path/'models.jsonl').read_text().splitlines()]
    events = [r for r in rows if r['kind'] == 'model']
    assert [r['failed'] for r in events] == [False, True]
    assert 'SECRET' not in json.dumps(rows)


def test_v3_inherited_classmethod_and_bounded_raw_events(tmp_path):
    from video_ai.runtime.local_comfy_metrics import ComfyNodeMetrics
    class Base:
        @classmethod
        def execute(cls, image):
            return image
    class Child(Base):
        pass
    with ComfyNodeMetrics(tmp_path/'bounded.jsonl', max_events=1) as metrics:
        metrics.install_nodes({'SaveVideo': Child})
        for n in range(3):
            assert Child.execute(n) == n
    assert 'execute' not in Child.__dict__
    rows = [json.loads(line) for line in (tmp_path/'bounded.jsonl').read_text().splitlines()]
    assert rows[-1]['kind'] == 'summary'
    assert rows[-1]['dropped_events'] == 2
    assert rows[-1]['stages']['wan.encode']['calls'] == 3


def test_gpu_samples_keep_only_numeric_fields_and_report_scope():
    from video_ai.runtime.local_comfy_metrics import parse_gpu_sample
    sample = parse_gpu_sample('0, 100, 20\n1, 200, 40\n')
    assert sample == [dict(index=0, used_mib=100, utilization_percent=20),
                      dict(index=1, used_mib=200, utilization_percent=40)]
    with pytest.raises(ValueError):
        parse_gpu_sample('token=SECRET')


def test_launcher_worker_installs_after_builtin_nodes_without_importing_real_comfy(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    import sys
    from types import ModuleType
    spec = importlib.util.spec_from_file_location('lva_comfy_launcher', Path(__file__).parents[2]/'scripts/observe_local_comfy.py')
    launcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(launcher)
    root = tmp_path/'experiment'; root.mkdir(); (root/'experiment.json').write_text('{}')
    comfy_root = tmp_path/'comfy'; comfy_root.mkdir(); (comfy_root/'main.py').write_text('# stub only')
    package = ModuleType('comfy'); package.__path__ = []
    startup = []
    options = ModuleType('comfy.options'); options.enable_args_parsing = lambda: startup.append('early_options')
    management = ModuleType('comfy.model_management')
    package.options = options; package.model_management = management
    nodes = ModuleType('nodes'); nodes.NODE_CLASS_MAPPINGS = {}
    async def initialize(**kwargs):
        return 'initialized'
    nodes.init_extra_nodes = initialize
    for name, value in [('comfy', package), ('comfy.options', options),
                        ('comfy.model_management', management), ('nodes', nodes)]:
        monkeypatch.setitem(sys.modules, name, value)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setattr(sys, 'argv', list(sys.argv))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('video_ai.runtime.resources.find_nvidia_smi', lambda: None)
    called = []
    def run(path, run_name):
        assert startup == []  # main owns allocator/device/torch startup ordering
        startup.append('native_allocator_ready')
        __import__('comfy.model_management', fromlist=['LoadedModel'])
        __import__('nodes')
        assert nodes.init_extra_nodes is not initialize
        called.append(path)
        assert asyncio.run(nodes.init_extra_nodes()) == 'initialized'
    monkeypatch.setattr(launcher.runpy, 'run_path', run)
    launcher.worker(SimpleNamespace(experiment_root=root, comfy_root=comfy_root, port=8189))
    assert called == [str(comfy_root/'main.py')]
    assert nodes.init_extra_nodes is initialize
    assert (root/'node-metrics.jsonl').is_file()


def test_aggregate_checkpoint_is_available_before_context_finalization(tmp_path):
    from video_ai.runtime.local_comfy_metrics import ComfyNodeMetrics
    class Node:
        FUNCTION = 'call'
        def call(self):
            return 1
    with ComfyNodeMetrics(tmp_path/'checkpoints.jsonl', max_events=1) as metrics:
        metrics.install_nodes({'SaveVideo': Node})
        Node().call(); Node().call()
        rows = [json.loads(line) for line in (tmp_path/'checkpoints.jsonl').read_text().splitlines()]
        checkpoint = rows[-1]
        assert checkpoint['kind'] == 'checkpoint'
        assert checkpoint['stages']['wan.encode']['calls'] == 2
        assert checkpoint['dropped_events'] == 1
        assert checkpoint['finalized'] is False


def test_diagnostic_sampling_invalidates_only_sampler_cache_and_restores(tmp_path):
    import math
    from video_ai.runtime.local_comfy_metrics import ComfyNodeMetrics
    class Sampler:
        FUNCTION = 'sample'
        def sample(self, start_at_step, end_at_step, steps):
            return steps
    class Text:
        FUNCTION = 'encode'
        def encode(self, text):
            return text
    with ComfyNodeMetrics(tmp_path/'sampling.jsonl', force_sampling=True) as metrics:
        metrics.install_nodes({'KSamplerAdvanced': Sampler, 'CLIPTextEncode': Text})
        assert math.isnan(Sampler.IS_CHANGED())
        assert not hasattr(Text, 'IS_CHANGED')
        assert Sampler().sample(0, 15, 40) == 40
    assert not hasattr(Sampler, 'IS_CHANGED')


def test_launcher_terminates_its_child_when_owner_recording_fails(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('lva_comfy_launcher_failure', Path(__file__).parents[2]/'scripts/observe_local_comfy.py')
    launcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(launcher)
    monkeypatch.setattr(launcher, 'RUNTIME_ROOT', tmp_path)
    comfy = tmp_path/'comfy'; comfy.mkdir(); (comfy/'main.py').write_text('# stub')
    python = tmp_path/'python.exe'; python.write_bytes(b'stub never executed')
    class Process:
        pid = 123456
        returncode = None
        terminated = False
        def poll(self): return self.returncode
        def terminate(self): self.terminated = True; self.returncode = -1
        def wait(self, timeout): return self.returncode
    process = Process()
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *a, **kw: process)
    monkeypatch.setattr('video_ai.runtime.environment.build_child_env', lambda paths: {})
    def unavailable(pid):
        raise OSError('identity unavailable')
    monkeypatch.setattr('video_ai.runtime.production_state.process_started_at', unavailable)
    with pytest.raises(OSError, match='identity unavailable'):
        launcher.main(['--experiment-root', str(tmp_path/'scratch/benchmarks/new'),
                       '--comfy-root', str(comfy), '--comfy-python', str(python)])
    assert process.terminated


def test_cooperative_stop_request_is_bound_to_owned_worker_pid(tmp_path):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('lva_comfy_stop',Path(__file__).parents[2]/'scripts/observe_local_comfy.py')
    launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
    assert not launcher.stop_requested(tmp_path,17)
    (tmp_path/'stop.request.json').write_text(json.dumps(dict(pid=18)))
    assert not launcher.stop_requested(tmp_path,17)
    (tmp_path/'stop.request.json').write_text(json.dumps(dict(pid=17)))
    assert launcher.stop_requested(tmp_path,17)
