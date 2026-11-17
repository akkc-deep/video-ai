"""LVA-04 isolated profiles: offline simulation, manifest, authorized prepare/run.

No default model downloads, package installation, GPU inference or adoption.
"""
import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE/'src'))
from video_ai.experiments import wan_fast_profiles as profiles
from video_ai.experiments.wan_fast_profiles import Artifact, artifact, digest, write_once
from video_ai.experiments.wan_fast_experiment import (FastExperimentClient, baseline_api, read,
    build_trial_fixture, prepare_request, profile_graph, accepted_parent_binding, run_trial)
from video_ai.runtime.paths import RUNTIME_ROOT
from video_ai.runtime.verification import whole_input_protection

TRIALS = ('cold_1', 'warm_1', 'warm_2', 'warm_3')


def launcher_api():
    spec = importlib.util.spec_from_file_location('_lva04_launcher', SOURCE/'scripts/observe_fast_comfy.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def offline_report():
    """Tiny fake artifacts/HTTP only. Never mistaken for native compatibility."""
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='LVA04-offline-') as directory:
        root = Path(directory)
        assets = {}
        for role in profiles.BASE_ROLES | {'lora_high', 'lora_low'}:
            path = root/(role+'.bin'); path.write_bytes(role.encode())
            assets[role] = artifact(path)
        pins = {r: dict(filename=Path(assets[r].path).name, bytes=assets[r].bytes,
                       sha256=assets[r].sha256) for r in ('lora_high', 'lora_low')}
        from unittest.mock import patch
        with patch.object(profiles, 'LORA_PINS', pins):
            profile = profiles.load_profile('fast_experimental', factor='distill', assets=assets,
                                            capabilities={'environment': {'kind': 'offline_tiny_fixture'}})
            profiles.freeze_profile(root, profile)
            graph = {'97': {'inputs': {'image': 'start.png'}},
                     '108': {'inputs': {'filename_prefix': 'fixture/cold_1'}}}
            fixture = build_trial_fixture(dict(fixture_id='fixture', source_graph_sha256='a'*64,
                source_request_sha256='b'*64, source_clip_id='fixture', parameters={'seed_high': 17},
                budget={'generated_frames': 93}, requires_new_parent=False), profile, graph)
            prepare_request(root, profile, fixture, graph)
            calls, pid = [], str(uuid4())

            def http(method, route, payload=None):
                calls.append(method)
                if method == 'POST':
                    raise TimeoutError('offline simulated lost response')
                intent = read(root/'trials/cold_1/intent.json')
                return {pid: {'prompt': [0, pid, graph, {'client_id': intent['client_id']}]}} if route == '/history' else {}

            client = FastExperimentClient(root, profile_digest=profile.digest(), port=8189, http=http)
            try:
                client.submit('cold_1', graph)
            except TimeoutError:
                pass
            assert client.submit('cold_1', graph) == pid
            assert calls.count('POST') == 1
            recovered_calls = len(calls)
            result = {}
            for role in ('generated', 'retained', 'last_frame'):
                path = root/(role+'.bin'); path.write_bytes(role.encode())
                result[role] = str(path); result[role+'_sha256'] = artifact(path).sha256
            result.update(trial_id='cold_1', prompt_id=pid, graph_sha256=digest(graph), input_sha256=None)
            write_once(root/'trials/cold_1/technical-complete.json', result)
            assert client.completed('cold_1', graph) == result
            assert len(calls) == recovered_calls
            return dict(schema_version=1, task_id='LVA-04', scope='offline_tiny_artifacts_and_fake_HTTP_only',
                status='passed', real_network_calls=0, real_gpu_trials=0, real_media_checks=0,
                unknown_recovery=dict(simulated_initial_posts=1, recovery_posts=0, original_id_recovered=True),
                completed_recovery=dict(posts=0, producers=0), elapsed_seconds=time.perf_counter()-started,
                fast_validated=False, quality='not_run', default_adoption=False,
                factors={k: {'status': 'not_run' if k == 'distill' else 'rejected_unsupported',
                    'gpu_seconds': None, 'quality': 'not_run'} for k in ('distill','sage','cache','compile','combination')})


def environment_identity(config):
    # Metadata only: never import torch or initialize a GPU in the coordinator.
    code = """import importlib.metadata as m, json, sys
names=('torch','numpy','sageattention','triton','comfy-aimdo','comfy-kitchen')
packages={}
for n in names:
 try: packages[n]=m.version(n)
 except m.PackageNotFoundError: pass
print(json.dumps(dict(python=sys.version,packages=packages)))
"""
    completed = subprocess.run([str(config.tools['comfy_python']), '-B', '-s', '-c', code],
                               capture_output=True, text=True, timeout=30, check=True)
    value = json.loads(completed.stdout)
    comfy = config.tools['comfy_root']
    value.update(comfy_root=str(comfy.resolve()), python_executable=str(config.tools['comfy_python'].resolve()))
    sources = [SOURCE/'src/video_ai/experiments'/name for name in
        ('wan_fast_profiles.py','wan_fast_nodes.py','wan_fast_experiment.py','wan_fast_media.py')]
    sources += [SOURCE/'scripts'/name for name in
        ('observe_fast_comfy.py','benchmark_wan_fast.py','benchmark_local_gpu.py','observe_local_comfy.py')]
    sources += [SOURCE/'src/video_ai/runtime/local_comfy_metrics.py', config.tools['comfy_python']]
    sources += [comfy/'nodes.py', comfy/'main.py', comfy/'comfyui_version.py']
    sources += sorted((comfy/'comfy').rglob('*.py'))
    sources += sorted((comfy/'comfy_extras').rglob('*.py'))
    torch_root = config.tools['comfy_python'].parent/'Lib/site-packages/torch'
    sources += [torch_root/'version.py', *sorted(torch_root.glob('_C*.pyd'))]
    # Bind the actual CUDA runtime binary as well as source and package metadata.
    sources += [torch_root/'lib/torch_cuda.dll']
    for source in sources:
        if not source.is_file():
            raise ValueError('required environment source/binary missing: '+str(source))
    value['artifacts'] = {str(p.resolve()): artifact(p).identity_dict() for p in sources}
    import ast
    version_tree = ast.parse((torch_root/'version.py').read_text(encoding='utf-8'))
    value['cuda'] = next(ast.literal_eval(node.value) for node in version_tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and
        ((isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'cuda' for t in node.targets)) or
         (isinstance(node, ast.AnnAssign) and getattr(node.target, 'id', None) == 'cuda')))
    from video_ai.runtime.resources import find_nvidia_smi
    smi = find_nvidia_smi()
    if smi is None:
        raise ValueError('explicit driver identity required')
    result = subprocess.run([str(smi), '--query-gpu=name,driver_version', '--format=csv,noheader'],
                            capture_output=True, text=True, timeout=30, check=True)
    value['driver_devices'] = result.stdout.strip().splitlines()
    value['artifacts']['nvidia_smi'] = artifact(smi).identity_dict()
    return value


def baseline_sources(cases):
    sources = {}
    for row in cases:
        fixture = read(Path(row['root'])/'fixture.json')
        key = 'child' if fixture['requires_new_parent'] else row['fixture_id']
        if key in sources:
            raise ValueError('ambiguous baseline source fixture: '+key)
        sources[key] = row['root']
    return sources


def make_manifest():
    from video_ai.config import load_config
    config = load_config(SOURCE/'config/production.example.json')
    baseline = read(SOURCE/'docs/task-designs/LVA-01-gpu-experiments.json')
    source_request = Path(baseline['fixtures'][0]['source_request'])
    historical = read(source_request.parent.parent/'inputs.json')['model_stamps']
    with whole_input_protection():
        # Resolve and admit small source inventory before reading base weights,
        # so a missing version file never wastes a large-model admission pass.
        env = environment_identity(config)
        base_assets = {}
        for role in ('wan_high', 'wan_low', 'text_encoder', 'vae'):
            path = config.models[role]
            stamp = path.stat(); expected = historical[role]
            if (path.resolve() != Path(expected['path']).resolve() or stamp.st_size != expected['bytes']
                    or stamp.st_mtime_ns != expected['mtime_ns']):
                raise ValueError('baseline model stamp differs: '+role)
            base_assets[role] = artifact(path).identity_dict()
        assets_by_mode = {}
        for mode in ('quality', 'fast_experimental'):
            fast = mode == 'fast_experimental'
            stem = 'wan22_i2v_14b_fast_api' if fast else 'wan22_i2v_14b_api'
            assets = deepcopy(base_assets)
            for role, path in dict(workflow=SOURCE/'workflows'/(stem+'.json'),
                    mapping=SOURCE/'workflows'/(stem+'.mapping.json'),
                    provenance=SOURCE/'workflows/wan22_i2v_14b_fast_api.provenance.json',
                    node_source=SOURCE/'src/video_ai/experiments/wan_fast_nodes.py',
                    media_source=SOURCE/'src/video_ai/experiments/wan_fast_media.py').items():
                assets[role] = artifact(path).identity_dict()
            if fast:
                for role, pin in profiles.LORA_PINS.items():
                    assets[role] = dict(path=str((RUNTIME_ROOT/'shared/models/comfyui/loras'/pin['filename']).resolve()),
                                        bytes=pin['bytes'], sha256=pin['sha256'])
            assets_by_mode[mode] = assets
    baseline_results = read(SOURCE/'docs/task-designs/LVA-01-gpu-results.json')
    sources = baseline_sources(baseline_results['cases'])
    # This is a plan, not a claim that any of these services or GPU trials ran.
    return dict(schema_version=1, task_id='LVA-04', revision=profiles.REVISION,
        source_quality_sha256=profiles.QUALITY_SHA, baseline_inputs=artifact(source_request.parent.parent/'inputs.json').identity_dict(),
        historical_content_limitation='Historical base evidence contains path/size/mtime stamps only. Full SHA admitted now; historical full-content equality cannot be retroactively proved.',
        environment=env, assets=assets_by_mode,
        capabilities=dict(sage='sageattention' in env['packages'], triton='triton' in env['packages'],
                          cache=False, residency_policy='native'),
        downloads=[dict(role=role, target=assets_by_mode['fast_experimental'][role]['path'], **pin,
            url=f'https://huggingface.co/lightx2v/Wan2.2-Distill-Loras/resolve/{profiles.REVISION}/{pin["filename"]}')
            for role, pin in profiles.LORA_PINS.items()],
        total_download_bytes=sum(p['bytes'] for p in profiles.LORA_PINS.values()),
        source_roots=sources, trials=list(TRIALS), frames_policy='original budget, seeds, 768x432/16fps unchanged',
        proposed_roots={mode: {fixture: str(RUNTIME_ROOT/'scratch/benchmarks'/
            f'LVA-04-{mode}-{fixture}-20261116-01') for fixture in ('low_motion','high_motion','parent_child','child')}
            for mode in ('quality','fast_experimental')},
        child_policy='New stopped/reviewed parent of SAME profile only; never borrow quality parent for fast child.',
        gpu_authorized=False, downloads_authorized=False, default_adoption=False, fast_validated=False)


def download_weights(manifest):
    from urllib.request import urlopen
    import os
    for entry in manifest['downloads']:
        pin = profiles.LORA_PINS[entry['role']]
        target = (RUNTIME_ROOT/'shared/models/comfyui/loras'/pin['filename']).resolve()
        expected_url = f'https://huggingface.co/lightx2v/Wan2.2-Distill-Loras/resolve/{profiles.REVISION}/{pin["filename"]}'
        if entry != dict(role=entry['role'], target=str(target), **pin, url=expected_url):
            raise ValueError('download differs from fixed official manifest')
        expected = Artifact(str(target), pin['bytes'], pin['sha256'])
        if target.exists():
            expected.verify()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        stage = target.with_name(target.name+'.LVA04-'+uuid4().hex+'.staging')
        try:
            with urlopen(expected_url, timeout=60) as response, stage.open('xb') as stream:
                count = 0
                while chunk := response.read(4*1024*1024):
                    count += len(chunk)
                    if count > pin['bytes']:
                        raise ValueError('download exceeds pinned size')
                    stream.write(chunk)
                stream.flush(); os.fsync(stream.fileno())
            Artifact(str(stage), pin['bytes'], pin['sha256']).verify()
            # Atomic no-overwrite promotion on the same volume.
            os.link(stage, target)
        finally:
            if stage.exists():
                stage.unlink()


def prepare_experiment(root, source_root, manifest, mode, factor, *, port=8189, parent_root=None, parent_trial='cold_1'):
    root = launcher_api().validate_root(root)
    source_root = Path(source_root).resolve(strict=True)
    assets = {k: Artifact(**v) for k,v in manifest['assets'][mode].items()}
    with whole_input_protection():
        profile = profiles.load_profile(mode, factor=factor, assets=assets,
                                       capabilities={'environment': manifest['environment']})
        if parent_root:
            source_fixture = read(source_root/'child-fixture.json')
            source_graph = read(source_root/'frozen/child-original-graph.json')
            request_path = source_root/'frozen/child-original-request.json'
            source_fixture['source_request_sha256'] = artifact(request_path).sha256
            binding = accepted_parent_binding(parent_root, parent_trial, profile.digest(), source_fixture)
            source_fixture.update(parent_binding=binding, requires_new_parent=False,
                input_sha256=binding['parent_last_frame_sha256'], input_relative='parent_child/start.png')
            input_path = Path(binding['last_frame'])
        else:
            source_fixture = read(source_root/'fixture.json')
            source_graph = read(source_root/'frozen'/source_fixture.get('graph_file', 'original-graph.json'))
            request_path = source_root/'frozen/original-request.json'
            if source_fixture.get('requires_new_parent'):
                raise ValueError('child preparation requires accepted same-profile parent')
            input_path = source_root/'input'/source_fixture['input_relative']
        if digest(source_graph) != source_fixture['source_graph_sha256']:
            raise ValueError('source quality graph differs')
        if artifact(input_path).sha256 != source_fixture['input_sha256']:
            raise ValueError('frozen source input differs')
        graph = profile_graph(source_graph, profile)
        fixture = build_trial_fixture(source_fixture, profile, graph)
        root.mkdir(parents=True, exist_ok=False)
        for name in ('input', 'output', 'temp', 'user'):
            (root/name).mkdir()
        target = root/'input'/fixture['input_relative']
        if not target.resolve().is_relative_to((root/'input').resolve()):
            raise ValueError('input escapes new experiment root')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(input_path.read_bytes())
        profiles.freeze_profile(root, profile)
        write_once(root/'frozen/original-request.json', read(request_path))
        prepare_request(root, profile, fixture, graph)
        write_once(root/'experiment.json', dict(kind='LVA-04_diagnostic_only', port=port, profile_sha256=profile.digest()))
        return dict(root=str(root), profile_sha256=profile.digest(), mode=mode, factor=factor)


def run_phase(root, *, port):
    root = launcher_api().validate_root(root)
    profile_digest = read(root/'frozen/profile.json')['profile_sha256']
    rows = []
    # Hold mandatory read leases through this one bounded phase, then release
    # before review. Never hash large models again at every HTTP boundary.
    failure = None
    try:
        with whole_input_protection():
            for trial in TRIALS:
                rows.append(run_trial(root, trial, profile_digest=profile_digest, port=port))
    except BaseException as exc:
        failure = exc
        raise
    finally:
        # Stop even when the original native request fails; never leave the
        # model resident across review, and never mask the original exception.
        if (root/'service-owner.json').exists():
            try:
                owner = read(root/'service-owner.json')
                write_once(root/'stop.request.json', dict(pid=owner['pid']))
            except Exception as stop_error:
                if failure is None:
                    raise
                failure.add_note('owned stop request failed: '+type(stop_error).__name__)
    return dict(task_id='LVA-04', trials=rows, fast_validated=False, quality='awaiting_human_review')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('quality','fast_experimental'), default='quality')
    parser.add_argument('--factor', choices=('distill','sage','cache','compile','combination'), default='distill')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--action', choices=('manifest','download','prepare','run'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--experiment-root', type=Path)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--parent-root', type=Path)
    parser.add_argument('--parent-trial', choices=TRIALS, default='cold_1')
    parser.add_argument('--port', type=int, default=8189)
    parser.add_argument('--authorized-download', action='store_true')
    parser.add_argument('--authorized-gpu', action='store_true')
    args = parser.parse_args(argv)
    if args.offline:
        result = offline_report()
    elif args.action == 'manifest':
        result = make_manifest()
    elif args.action == 'download':
        if not args.authorized_download or args.manifest is None:
            parser.error('concrete LVA-04 download authorization and manifest required')
        download_weights(read(args.manifest)); result = dict(downloads='verified', gpu_trials=0)
    elif args.action == 'prepare':
        if not args.manifest or not args.experiment_root or not args.source_root:
            parser.error('manifest, new experiment-root and fixed source-root required')
        result = prepare_experiment(args.experiment_root, args.source_root, read(args.manifest), args.mode,
            args.factor, port=args.port, parent_root=args.parent_root, parent_trial=args.parent_trial)
    elif args.action == 'run':
        if not args.authorized_gpu or args.experiment_root is None:
            parser.error('concrete LVA-04 GPU authorization and experiment-root required')
        result = run_phase(args.experiment_root, port=args.port)
    else:
        parser.error('--offline or explicit --action required')
    if args.output:
        write_once(args.output, result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('environment','assets','trials')},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
