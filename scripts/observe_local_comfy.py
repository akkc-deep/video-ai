"""Run a NEW, bounded, local-only Comfy diagnostic process after authorization.

Does not submit graphs, resume production, install nodes, or change Comfy files.
Use --help without importing Comfy, torch, or starting any service.
"""
import argparse
import builtins
import _thread
from functools import wraps
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from threading import Event,Thread
from time import perf_counter

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE/'src'))
from video_ai.runtime.paths import RUNTIME_ROOT


def comfy_arguments(root, port):
    return ['--listen', '127.0.0.1', '--port', str(port), '--disable-auto-launch',
        '--offline', '--disable-all-custom-nodes', '--disable-assets',
        '--models-directory', str(RUNTIME_ROOT/'shared/models/comfyui'),
        '--database-url', 'sqlite:///'+(root/'user/comfyui.db').as_posix(),
        '--input-directory', str(root/'input'), '--output-directory', str(root/'output'),
        '--temp-directory', str(root/'temp'), '--user-directory', str(root/'user')]


def stop_requested(root,pid):
    try:
        return json.loads((Path(root)/'stop.request.json').read_text(encoding='utf-8')).get('pid')==pid
    except (OSError,ValueError):
        return False


def worker(args):
    from video_ai.runtime.local_comfy_metrics import ComfyNodeMetrics
    from video_ai.runtime.resources import find_nvidia_smi
    root, comfy_root = args.experiment_root.resolve(), args.comfy_root.resolve(strict=True)
    if not (root/'experiment.json').is_file():
        raise ValueError('new experiment marker required')
    sys.argv = [str(comfy_root/'main.py'), *comfy_arguments(root, args.port)]
    sys.path.insert(0, str(comfy_root))
    os.chdir(comfy_root)
    # Let native main set allocator/device environment before its first torch
    # import. Observe imports after they finish; never preload nodes/torch.
    original_import = builtins.__import__
    node_hooks = []
    stop=Event()
    metrics_root=Path(getattr(args,'metrics_root',root));stop_root=Path(getattr(args,'stop_root',root))
    def stop_watcher():
        while not stop.wait(.5):
            if stop_requested(stop_root,os.getpid()):
                _thread.interrupt_main();return
    watcher=Thread(target=stop_watcher,name='lva01-owned-stop',daemon=True)
    with ComfyNodeMetrics(metrics_root/'node-metrics.jsonl', force_sampling=True) as metrics:
        def observed_import(name, globals=None, locals=None, fromlist=(), level=0):
            imported = original_import(name, globals, locals, fromlist, level)
            if name in ('comfy', 'comfy.model_management'):
                management = sys.modules.get('comfy.model_management')
                if management is not None:
                    metrics.install_models(management)
            if name == 'nodes' and not node_hooks:
                nodes = sys.modules.get('nodes')
                if nodes is not None and hasattr(nodes, 'init_extra_nodes'):
                    original = nodes.init_extra_nodes
                    @wraps(original)
                    async def initialize(*a, **kw):
                        result = await original(*a, **kw)
                        metrics.install_nodes(nodes.NODE_CLASS_MAPPINGS)
                        callback=getattr(args,'on_nodes_ready',None)
                        if callback is not None:callback(nodes.NODE_CLASS_MAPPINGS)
                        return result
                    node_hooks.append((nodes, original))
                    nodes.init_extra_nodes = initialize
            return imported
        executable = find_nvidia_smi()
        if executable is not None:
            metrics.start_gpu_sampler(executable)
        builtins.__import__ = observed_import
        watcher.start()
        try:
            runpy.run_path(str(comfy_root/'main.py'), run_name='__main__')
        finally:
            stop.set();watcher.join(timeout=1)
            builtins.__import__ = original_import
            for nodes, original in reversed(node_hooks):
                nodes.init_extra_nodes = original


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-root', type=Path, required=True)
    parser.add_argument('--comfy-root', type=Path,
        default=RUNTIME_ROOT/'shared/tools/ComfyUI_windows_portable/ComfyUI')
    parser.add_argument('--comfy-python', type=Path,
        default=RUNTIME_ROOT/'shared/tools/ComfyUI_windows_portable/python_embeded/python.exe')
    parser.add_argument('--port', type=int, default=8189)
    parser.add_argument('--max-seconds', type=int, default=1800)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = args.experiment_root.resolve()
    if not root.is_relative_to((RUNTIME_ROOT/'scratch/benchmarks').resolve()):
        parser.error('experiment-root must be a NEW directory under runtime scratch/benchmarks')
    if not 1024 <= args.port <= 65535 or not 30 <= args.max_seconds <= 14400:
        parser.error('port must be 1024..65535 and runtime 30..14400 seconds')
    if args.worker:
        return worker(args)
    comfy = args.comfy_root.resolve(strict=True)
    python = args.comfy_python.resolve(strict=True)
    if not (comfy/'main.py').is_file():
        parser.error('Comfy main.py required')
    root.mkdir(parents=True, exist_ok=False)
    for name in ('input', 'output', 'temp', 'user'):
        (root/name).mkdir()
    (root/'experiment.json').write_text(json.dumps(dict(kind='LVA-01_diagnostic_only',
        graph_submissions=0, port=args.port, max_seconds=args.max_seconds,
        parameters='original quality workflow supplied separately; this launcher never submits'))+'\n', encoding='utf-8')
    command = [str(python), '-B', '-s', str(Path(__file__).resolve()), '--worker',
        '--experiment-root', str(root), '--comfy-root', str(comfy), '--port', str(args.port)]
    started, timed_out = perf_counter(), False
    with (root/'comfy.stdout').open('xb') as stdout, (root/'comfy.stderr').open('xb') as stderr:
        from video_ai.config import load_config
        from video_ai.runtime.environment import build_child_env
        from video_ai.runtime.paths import RuntimePaths
        environment = build_child_env(RuntimePaths.from_config(load_config(SOURCE/'config/production.example.json')))
        process = subprocess.Popen(command, cwd=comfy, env=environment, stdout=stdout, stderr=stderr, shell=False)
        try:
            from video_ai.runtime.production_state import process_started_at
            with (root/'service-owner.json').open('x', encoding='utf-8') as owner:
                owner.write(json.dumps(dict(pid=process.pid, process_started_at=process_started_at(process.pid),
                    experiment_root=str(root), port=args.port, parent_pid=os.getpid()))+'\n')
                owner.flush(); os.fsync(owner.fileno())
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
    result = dict(exit_code=code, timed_out=timed_out, seconds=perf_counter()-started,
        scope='Only this new owned process was stopped; node metrics are CPU wall intervals; no quality claim.')
    try:
        with (root/'node-metrics.jsonl').open('rb') as telemetry:
            telemetry.seek(0, 2)
            size = telemetry.tell(); telemetry.seek(max(0, size-65536))
            last = json.loads(telemetry.read().splitlines()[-1])
        result['metrics_finalized'] = last.get('kind') == 'summary' and last.get('finalized') is True
    except (OSError, ValueError, IndexError):
        result['metrics_finalized'] = False
    result['partial_metrics_policy'] = 'On forced stop, use the last valid checkpoint only; the in-flight node and unsampled GPU peak remain unverified.'
    (root/'service-result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(experiment_root=str(root), **result)))
    return 124 if timed_out else code


if __name__ == '__main__':
    raise SystemExit(main())
