"""Bounded owned LVA-04 Comfy launcher. Never installs nodes or submits graphs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE/'src'))
from video_ai.experiments.wan_fast_profiles import digest, verify_profile, write_once
from video_ai.runtime.paths import RUNTIME_ROOT


def observer_api():
    spec = importlib.util.spec_from_file_location('_lva04_observer', SOURCE/'scripts/observe_local_comfy.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_root(root):
    root = Path(root).resolve()
    if not root.is_relative_to((RUNTIME_ROOT/'scratch/benchmarks').resolve()) or not root.name.startswith('LVA-04-'):
        raise ValueError('new LVA-04 root under scratch/benchmarks required')
    return root


def native_arguments(root, port):
    return observer_api().comfy_arguments(Path(root), port)


def environment_binding(environment):
    # Do not persist unrelated secrets inherited from the coordinator.
    return {k: v for k, v in sorted(environment.items()) if k.upper() in ('PATH', 'PYTHONPATH',
        'PYTHONHOME', 'PYTHONNOUSERSITE', 'VIDEO_AI_RUNTIME_ROOT') or k.upper().startswith(
            ('CUDA_', 'PYTORCH_', 'TORCH_', 'COMFY_'))}


def verify_installation(profile, comfy_root, python):
    identity = json.loads(profile.environment_json)
    if (Path(comfy_root).resolve() != Path(identity['comfy_root']).resolve()
            or Path(python).resolve() != Path(identity['python_executable']).resolve()):
        raise ValueError('actual Comfy/Python differs from profiled installation')


def worker(args):
    from video_ai.experiments.wan_fast_experiment import read
    from video_ai.experiments.wan_fast_nodes import register_nodes
    from video_ai.runtime.local_comfy_metrics import ComfyNodeMetrics
    from video_ai.runtime.verification import whole_input_protection
    root = validate_root(args.experiment_root)
    with whole_input_protection():
        profile = verify_profile(root, args.profile_digest)
        verify_installation(profile, args.comfy_root, sys.executable)
        launch = read(root/'frozen/service-launch.json')
        expected_argv = [str(args.comfy_root.resolve()/'main.py'), *native_arguments(root, args.port)]
        if (launch['comfy_argv'] != expected_argv or launch['profile_sha256'] != args.profile_digest
                or launch['environment_binding'] != environment_binding(os.environ)
                or Path(sys.executable).resolve() != Path(launch['command'][0]).resolve()):
            raise ValueError('worker argv/environment differs from frozen launch')
        import importlib.metadata as metadata
        current = {n: metadata.version(n) for n in json.loads(profile.environment_json)['packages']}
        if current != json.loads(profile.environment_json)['packages']:
            raise ValueError('worker package versions differ from profile')
        original_install = ComfyNodeMetrics.install_nodes
        installed = False

        def install(metrics, mapping):
            nonlocal installed
            if not installed:
                register_nodes(SimpleNamespace(NODE_CLASS_MAPPINGS=mapping), root, args.profile_digest)
                installed = True
                write_once(root/'worker-attestation.json', dict(pid=os.getpid(), profile_sha256=args.profile_digest,
                    launch_sha256=digest(launch), node_source_sha256=dict(profile.assets)['node_source'].sha256,
                    python=sys.version, packages=current))
            return original_install(metrics, mapping)

        ComfyNodeMetrics.install_nodes = install
        try:
            return observer_api().worker(args)
        finally:
            ComfyNodeMetrics.install_nodes = original_install


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-root', required=True, type=Path)
    parser.add_argument('--profile-digest', required=True)
    parser.add_argument('--comfy-root', type=Path, default=RUNTIME_ROOT/'shared/tools/ComfyUI_windows_portable/ComfyUI')
    parser.add_argument('--comfy-python', type=Path, default=RUNTIME_ROOT/'shared/tools/ComfyUI_windows_portable/python_embeded/python.exe')
    parser.add_argument('--port', type=int, default=8189)
    parser.add_argument('--max-seconds', type=int, default=3600)
    parser.add_argument('--authorized-gpu', action='store_true')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = validate_root(args.experiment_root)
    if not 1024 <= args.port <= 65535 or not 30 <= args.max_seconds <= 3600:
        parser.error('port 1024..65535, bounded runtime 30..3600 required')
    if args.worker:
        return worker(args)
    if not args.authorized_gpu:
        parser.error('this concrete LVA-04 GPU experiment requires authorization')
    from video_ai.experiments.wan_fast_experiment import read
    from video_ai.config import load_config
    from video_ai.runtime.environment import build_child_env
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.runtime.production_state import process_started_at
    from video_ai.runtime.verification import whole_input_protection
    with whole_input_protection():
        profile = verify_profile(root, args.profile_digest)
        marker = read(root/'experiment.json')
        if marker != dict(kind='LVA-04_diagnostic_only', port=args.port, profile_sha256=args.profile_digest):
            raise ValueError('new profile experiment marker required')
        if (root/'service-owner.json').exists():
            raise ValueError('this experiment already owns a historical process; use original recovery, never replace it')
        comfy, python = args.comfy_root.resolve(strict=True), args.comfy_python.resolve(strict=True)
        verify_installation(profile, comfy, python)
        environment = build_child_env(RuntimePaths.from_config(load_config(SOURCE/'config/production.example.json')))
        command = [str(python), '-B', '-s', str(Path(__file__).resolve()), '--worker',
            '--experiment-root', str(root), '--profile-digest', args.profile_digest,
            '--comfy-root', str(comfy), '--port', str(args.port)]
        launch = dict(profile_sha256=args.profile_digest, port=args.port, command=command,
            comfy_argv=[str(comfy/'main.py'), *native_arguments(root, args.port)],
            environment=json.loads(profile.environment_json), environment_binding=environment_binding(environment),
            max_seconds=args.max_seconds)
        write_once(root/'frozen/service-launch.json', launch)
        started = time.perf_counter()
        timed_out = False
        with (root/'comfy.stdout').open('xb') as stdout, (root/'comfy.stderr').open('xb') as stderr:
            process = subprocess.Popen(command, cwd=comfy, env=environment, stdout=stdout, stderr=stderr,
                shell=False, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            try:
                write_once(root/'service-owner.json', dict(pid=process.pid,
                    process_started_at=process_started_at(process.pid), experiment_root=str(root), port=args.port,
                    parent_pid=os.getpid(), profile_sha256=args.profile_digest, launch_sha256=digest(launch)))
                try:
                    code = process.wait(timeout=args.max_seconds)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    process.terminate()
                    try:
                        code = process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill(); code = process.wait(timeout=5)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=5)
        write_once(root/'service-result.json', dict(exit_code=code, timed_out=timed_out,
            seconds=time.perf_counter()-started, profile_sha256=args.profile_digest,
            scope='only this owned process; no quality or full-film throughput claim'))
        return 124 if timed_out else code


if __name__ == '__main__':
    raise SystemExit(main())
