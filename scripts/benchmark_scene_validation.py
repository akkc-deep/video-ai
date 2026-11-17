"""LVA-02: new offline fixtures, real FFmpeg, in-memory Comfy, no GPU/network."""
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import platform
import socket
import subprocess
import sys
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tests'))
from pytest import MonkeyPatch
from scene_validation_helpers import isolated_config, real_wan, validation_counters
from scene_clip_helpers import generate
from video_ai.config import load_config
from video_ai.runtime.paths import RUNTIME_ROOT, RuntimePaths, create_run
from video_ai.runtime.storage import test_runtime_scope
from video_ai.runtime.manifest import hash_file
from video_ai.runtime.scene_validation_pass import scene_validation_pass, candidate_scene_validation
from video_ai.runtime.scene_validation_pass import verify_inventory_once
from video_ai.runtime.scene_clip_records import SceneClipStore
from video_ai.runtime import verification
from video_ai.runtime.local_video_metrics import LocalVideoMetrics


def enrich_existing_evidence(report):
    """Read existing receipts/probes, without decoding or generating again."""
    from fractions import Fraction
    for row in report['results']:
        run = Path(row['fixture_run'])
        probes = []
        for path in (run/'logs/production/source-clips').glob('video-*.json'):
            value = json.loads(path.read_bytes())
            probes.append((path, value))
        actual = []
        for media in row['media']:
            for role in ('source', 'generated'):
                artifact = media[role]
                matching = [(p, v) for p, v in probes if v.get('info', {}).get('identity', {}).get('sha256') == artifact['sha256']]
                if not matching: raise RuntimeError('missing original full-frame probe evidence')
                path, value = matching[0]
                frames = value['frames']['frames']
                stream = value['probe']['streams'][0]
                time_base = Fraction(stream['time_base'])
                pts = [v['best_effort_timestamp'] for v in frames]
                if len(frames) != value['info']['frames'] or any((b-a)*time_base != Fraction(1,16) for a,b in zip(pts,pts[1:])):
                    raise RuntimeError('recorded full-frame PTS evidence differs')
                actual.append(dict(role=role, sha256=artifact['sha256'], width=value['info']['width'],
                    height=value['info']['height'], frames=len(frames), pts=pts,
                    time_base=str(time_base), pts_cfr16=True, evidence=str(path)))
        row['actual_media'] = actual
        receipts = list((run/'production/scene-clips').glob('*/media-ready/*.json'))
        by_operation = {}
        for path in receipts:
            value = json.loads(path.read_bytes())
            by_operation[value['operation']] = by_operation.get(value['operation'], 0)+1
        # An immutable media-ready receipt is produced only after its producer.
        # Recovery's exact same file set and hashes prove no additional receipt
        # or staging output was created. Distinguish this evidence from a spy.
        row['producer_receipts'] = by_operation if row['mode'] == 'normal' else {}
        row['additional_media_outputs_on_recovery'] = 0 if row['original_evidence_preserved'] else None
        row['producer_count_basis'] = ('direct spy' if 'producer_invocations' in row['counts'] else
            'successful immutable receipt count; direct invocation count was not instrumented')
        row['direct_producer_invocations'] = row['counts'].get('producer_invocations')
        row['inventory_scan_comparison_supported'] = False
    if 'Direct glob scans were not counted in the original production samples.' not in report['limitations']:
        report['limitations'].append('Direct glob scans were not counted in the original production samples.')
    report['parameters'] = dict(production_width=768, production_height=432, fps=16,
        size_rationale='Production accepts only fast 768x432 or quality 1280x720; do not weaken it for a 128x72 fixture.')
    return report


def amplified(paths, *, protected, reuse):
    run = create_run(paths)
    store = SceneClipStore(SimpleNamespace(options={'model_stamps': {}}, config=SimpleNamespace(raw={})), run)
    values = []
    for index in range(32):
        path = run/f'input-{index:02d}.bin'; path.write_bytes(bytes([index])*1024)
        values.append(store.artifact(path))
    window = verification.whole_input_protection() if protected else nullcontext()
    directory = run/'inventory'; directory.mkdir()
    def strict_inventory():
        if set(directory.rglob('*.json')): raise RuntimeError('fixture inventory changed')
    with window:
        if protected:
            for value in values: hash_file(Path(value['path']))
        with validation_counters() as counts:
            started = perf_counter()
            # Four repeated audits within ONE callback; never cross send boundaries.
            with scene_validation_pass(reuse=reuse):
                for _ in range(4):
                    for value in values: store.validate_artifact(value)
                    verify_inventory_once(directory,set(),recursive=True,strict_check=strict_inventory)
            wall = perf_counter()-started
    expected = 32 if protected and reuse else 128
    if counts['strict_validations'] != expected:
        raise RuntimeError(f'amplified strict count differs: {counts}')
    return dict(protected=protected, candidate=reuse, wall_seconds=wall, **counts)


def production_pair(paths, config, *, reuse, observed, repeat):
    run = create_run(paths); temporary = run/'fixture-config'; temporary.mkdir()
    with MonkeyPatch.context() as monkeypatch:
        setup, backend = real_wan((run, config, paths), temporary, monkeypatch)
        rows = []
        originals = None
        for mode in ('normal', 'recovery'):
            metrics = LocalVideoMetrics(mode=mode) if observed else None
            posts, gets, ensures = len(backend.posts), len(backend.gets), backend.ensures
            with validation_counters() as counts:
                started = perf_counter()
                # Candidate obtains only each production callback's own scope.
                outer = candidate_scene_validation() if reuse else scene_validation_pass(reuse=False)
                with outer, metrics if metrics else nullcontext():
                    result = generate(setup, backend)
                wall = perf_counter()-started
            if result.status != 'awaiting_continuity_review':
                raise RuntimeError(f'{mode}: {result.status}: {result.error}')
            root = run/'production/scene-clips'
            identity = {str(p.relative_to(root)): hash_file(p).sha256 for p in root.rglob('*') if p.is_file()}
            clips = [json.loads(p.read_bytes()) for p in root.glob('*/clip.json')]
            submissions = [json.loads(p.read_bytes()) for p in root.glob('*/submission.json')]
            mappings = [json.loads(p.read_bytes()) for p in root.glob('*/mapping.json')]
            if mode == 'normal': originals = identity
            elif identity != originals or len(backend.posts) != posts:
                raise RuntimeError('recovery changed original evidence or repeated POST')
            row = dict(mode=mode, candidate=reuse, observed=observed, repeat=repeat,
                fixture_run=str(run), wall_seconds=wall, counts=dict(counts),
                post_count=len(backend.posts)-posts, get_count=len(backend.gets)-gets,
                service_ensure_count=backend.ensures-ensures,
                original_prompt_ids=[v['prompt_id'] for v in submissions],
                media=[dict(source=v['source'], generated=v['generated']) for v in clips],
                frame_mappings=mappings, immutable_files=len(identity),
                original_evidence_preserved=mode == 'recovery',
                failure_count=int(result.status != 'awaiting_continuity_review'),
                redo_count=max(0,(len(backend.posts)-posts)-len(clips)) if mode == 'normal' else len(backend.posts)-posts)
            if metrics:
                report = metrics.report()
                if not report['aggregate_complete']: raise RuntimeError('incomplete metrics')
                row['diagnostics'] = report['totals']
                row['diagnostic_completeness'] = {key: report[key] for key in
                    ('complete', 'aggregate_complete', 'dropped_events', 'observation_errors')}
                diagnostic = run/f'LVA-02-{mode}-calls.json'
                diagnostic.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
                row['diagnostic_report'] = str(diagnostic)
            rows.append(row)
        return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=4)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    root = (RUNTIME_ROOT/'scratch/benchmarks').resolve()
    if (not output.is_relative_to(root) or not output.name.startswith('LVA-02-')
            or output.suffix != '.json' or args.repeats < 1):
        parser.error('use a new scratch/benchmarks/LVA-02-*.json and positive repeats')
    if output.exists() or output.with_suffix('.md').exists(): parser.error('report already exists')
    # Keep deeply nested immutable evidence paths below Windows' legacy limit.
    fixture = root/('LVA-02-'+uuid4().hex[:8]); fixture.mkdir(parents=True, exist_ok=False)
    base = load_config(Path(__file__).resolve().parents[1]/'config/production.example.json')
    results, amplification = [], []
    with test_runtime_scope(fixture):
        config = isolated_config(base, fixture/'shared')
        paths = RuntimePaths.from_config(config)
        tools = {p.resolve() for k, p in config.tools.items() if k in ('ffmpeg', 'ffprobe')}
        popen = subprocess.Popen
        def media_only(command, *a, **kw):
            if not isinstance(command, (list, tuple)) or Path(command[0]).resolve() not in tools:
                raise RuntimeError('benchmark only permits configured FFmpeg/FFprobe')
            return popen(command, *a, **kw)
        def deny_network(*a, **kw): raise RuntimeError('offline benchmark forbids network')
        with (patch.object(socket.socket, 'connect', deny_network),
              patch.object(socket.socket, 'connect_ex', deny_network),
              patch.object(socket, 'create_connection', deny_network), patch.object(subprocess, 'Popen', media_only)):
            for repeat in range(args.repeats):
                for reuse in ((False, True) if repeat % 2 == 0 else (True, False)):
                    results.extend(production_pair(paths, config, reuse=reuse, observed=False, repeat=repeat))
                    print(f'wall pair {repeat+1}/{args.repeats} candidate={reuse}', flush=True)
                for strong in (False, True):
                    for reuse in (False, True):
                        amplification.append(dict(repeat=repeat, **amplified(paths, protected=strong, reuse=reuse)))
            # Complete profiler is separate and never used for the wall comparison.
            for reuse in (False, True):
                results.extend(production_pair(paths, config, reuse=reuse, observed=True, repeat=0))
                print(f'diagnostics candidate={reuse}', flush=True)
        tool_sha = {k: hash_file(config.tools[k]).sha256 for k in ('ffmpeg', 'ffprobe')}
    summary = {}
    for mode in ('normal', 'recovery'):
        summary[mode] = {}
        for reuse, label in ((False, 'strict'), (True, 'candidate')):
            rows = [r for r in results if r['mode'] == mode and r['candidate'] == reuse and not r['observed']]
            summary[mode][label] = dict(samples=len(rows),
                wall_mean_seconds=sum(r['wall_seconds'] for r in rows)/len(rows),
                counts_mean={key: sum(r['counts'][key] for r in rows)/len(rows) for key in rows[0]['counts']})
    sha_sets = {tuple(v['source']['sha256'] for v in r['media']) for r in results}
    if len(sha_sets) != 1: raise RuntimeError('paired source media bytes differ')
    report = dict(schema_version=1, kind='offline_scene_validation', fixture_root=str(fixture),
        environment=dict(python=platform.python_version(), platform=platform.platform(), tool_sha256=tool_sha),
        results=results, amplified=amplification, summary=summary, paired_media_sha_equal=True,
        gpu_runs=0, network_connections=0, original_production_runs_modified=0,
        limitations=['Local validation/media only; no GPU or full-film speed claim.',
            'Process-warm; OS disk cache uncontrolled; alternating pair order.',
            'Counters are lightweight spies; full profiler samples are separate.',
            'Amplified 32-artifact sample repeats four checks within one callback, not across sends.'])
    enrich_existing_evidence(report)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    lines = ['# LVA-02 offline scene validation benchmark', '',
        '| Mode | Strict mean s | Candidate mean s | Strict Artifact calls | Candidate Artifact calls |',
        '| --- | ---: | ---: | ---: | ---: |']
    for mode, pair in summary.items():
        a, b = pair['strict'], pair['candidate']
        lines.append(f'| {mode} | {a["wall_mean_seconds"]:.6f} | {b["wall_mean_seconds"]:.6f} | {a["counts_mean"]["strict_validations"]:.1f} | {b["counts_mean"]["strict_validations"]:.1f} |')
    lines += ['', f'Fixtures: `{fixture}`; paired source media SHA identical.', '', *report['limitations']]
    output.with_suffix('.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(str(output), flush=True)


if __name__ == '__main__': main()
