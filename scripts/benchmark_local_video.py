"""LVA-01 offline media observations in a NEW isolated scratch fixture.

No GPU, network, cloud, production resume or quality claim. Four repeats are
process-warm media tests, NOT the required cold/warm Wan GPU experiments.
"""
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import platform
import socket
import subprocess
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4

from video_ai.config import load_config
from video_ai.media.frames import extract_native_frame
from video_ai.media.video import inspect_video, inspection_reuse, trim_scene_video
from video_ai.runtime.environment import build_child_env
from video_ai.runtime.local_video_metrics import LocalVideoMetrics, write_report
from video_ai.runtime.logging import RunLogger
from video_ai.runtime.manifest import hash_file
from video_ai.runtime.paths import RUNTIME_ROOT, RuntimePaths, create_run
from video_ai.runtime.processes import run_logged
from video_ai.runtime.storage import test_runtime_scope


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=RUNTIME_ROOT/'scratch/logs/LVA-01-offline.json')
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1]/'config/production.example.json')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if not output.is_relative_to((RUNTIME_ROOT/'scratch/logs').resolve()) or output.suffix != '.json':
        parser.error('output must be a new .json inside runtime scratch/logs')
    calls_dir = output.with_name(output.stem+'-calls')
    if output.exists() or output.with_suffix('.md').exists() or calls_dir.exists():
        parser.error('report already exists; choose a new output name')
    config = load_config(args.config.resolve())
    tools = {Path(config.tools[k]).resolve() for k in ('ffmpeg', 'ffprobe')}
    tool_identities = {k: dict(sha256=hash_file(Path(config.tools[k])).sha256)
                       for k in ('ffmpeg', 'ffprobe')}
    fixture_root = RUNTIME_ROOT/'scratch/benchmarks'/('LVA-01-'+uuid4().hex)
    fixture_root.mkdir(parents=True, exist_ok=False)
    calls_dir.mkdir(parents=True, exist_ok=False)
    popen = subprocess.Popen
    process_counts = []

    def deny_network(*args, **kwargs):
        raise RuntimeError('offline LVA-01 benchmark forbids network')

    def media_only(command, *args, **kwargs):
        if not isinstance(command, (list, tuple)) or not command or Path(command[0]).resolve() not in tools:
            raise RuntimeError('offline benchmark allows only configured FFmpeg and FFprobe')
        process_counts.append(Path(command[0]).stem)
        return popen(command, *args, **kwargs)

    results = []
    with (test_runtime_scope(fixture_root), patch.object(socket.socket, 'connect', deny_network),
          patch.object(socket.socket, 'connect_ex', deny_network),
          patch.object(socket, 'create_connection', deny_network),
          patch.object(subprocess, 'Popen', media_only)):
        paths = RuntimePaths.from_config(config)
        run = create_run(paths)
        logger = RunLogger(run)
        kwargs = dict(config=config, paths=paths, logger=logger, unit_id='lva01_fixture')
        width, height, frames = 128, 72, 9
        source = run/'fixture.mp4'
        result = run_logged(tuple(map(str, [config.tools['ffmpeg'], '-nostdin', '-n', '-v', 'error',
            '-f', 'lavfi', '-i', f'testsrc2=size={width}x{height}:rate=16', '-frames:v', frames,
            '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', source])), cwd=run,
            env=build_child_env(paths), timeout=30, logger=logger, stage='test_fixture')
        if result.returncode or result.timed_out:
            raise RuntimeError('fixture generation failed')
        source_identity = hash_file(source)
        # Pair order alternates to expose, rather than hide, uncontrolled OS cache effects.
        for mode in ('normal', 'recovery'):
            for repeat in range(4):
                identities = []
                for observed in ((False, True) if repeat % 2 == 0 else (True, False)):
                    token = f'{mode}-{repeat}-'+('observed' if observed else 'plain')
                    metrics = LocalVideoMetrics(mode=mode) if observed else None
                    process_counts.clear()
                    started = perf_counter()
                    with metrics if metrics else nullcontext():
                        with inspection_reuse():
                            info, _ = inspect_video(source, width=width, height=height, **kwargs)
                            if mode == 'normal':
                                # Exercises existing same-content reuse without changing it.
                                inspect_video(source, width=width, height=height, **kwargs)
                                target = run/(token+'.mp4')
                                trim_scene_video(source, target, source_info=info, start_frame=0,
                                    end_frame=frames, width=width, height=height, **kwargs)
                                png = run/token/f'frame_{frames:06d}.png'
                                extract_native_frame(source, png, source_frame_index=frames-1,
                                    expected_frames=frames, width=width, height=height, **kwargs)
                    seconds = perf_counter()-started
                    # Recovery here means a fresh proof of an existing media file,
                    # not the production durable-intent recovery protocol.
                    identity = [hash_file(p).sha256 for p in (target, png)] if mode == 'normal' else [info['identity']['sha256']]
                    identities.append(identity)
                    record = dict(mode=mode, repeat=repeat, observed=observed,
                        seconds=seconds, media_processes=len(process_counts), output_sha256=identity)
                    if metrics:
                        report_path = calls_dir/(token+'.json')
                        report = metrics.report()
                        if not report['complete']:
                            raise RuntimeError('observation incomplete')
                        write_report(report, report_path)
                        record.update(calls_report=str(report_path), counters=report['totals'])
                    results.append(record)
                if identities[0] != identities[1]:
                    raise RuntimeError('observed/plain output bytes differ')
        if hash_file(source).sha256 != source_identity.sha256:
            raise RuntimeError('source media changed')
    summary = {}
    for mode in ('normal', 'recovery'):
        plain = [r['seconds'] for r in results if r['mode'] == mode and not r['observed']]
        observed = [r['seconds'] for r in results if r['mode'] == mode and r['observed']]
        summary[mode] = dict(plain_mean_seconds=sum(plain)/len(plain), observed_mean_seconds=sum(observed)/len(observed),
            observer_ratio=sum(observed)/sum(plain), samples_per_condition=len(plain))
    report = dict(schema_version=1, kind='offline_media_only', fixture_run=str(run),
        environment=dict(python=platform.python_version(), platform=platform.platform(), tools=tool_identities),
        parameters=dict(width=width, height=height, frames=frames, fps=16),
        source_sha256=source_identity.sha256, source_unchanged=True, paired_output_bytes_equal=True,
        results=results, summary=summary, gpu_inference_runs=0, network_requests=0,
        production_runs_modified=0, limitations=[
            'Synthetic media is not a selected-image GPU quality fixture.',
            'No true cold GPU run, node times, VRAM, quality acceptance or full-film baseline.',
            'OS disk cache uncontrolled; pairs alternate observer order.',
            'Recovery is media-only readback; production recovery is covered by the separate integration test.'])
    with output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)+'\n')
    lines = ['# LVA-01 offline media benchmark', '',
        'Real FFmpeg on a new synthetic fixture; GPU/quality/end-to-end remain unverified.', '',
        '| Mode | Plain mean seconds | Observed mean seconds | Observer ratio | Samples |',
        '| --- | ---: | ---: | ---: | ---: |']
    for mode, row in summary.items():
        lines.append(f'| {mode} | {row["plain_mean_seconds"]:.6f} | {row["observed_mean_seconds"]:.6f} | {row["observer_ratio"]:.3f} | 4 |')
    lines += ['', 'Paired outputs and source SHA256 preserved.', '', *report['limitations']]
    with output.with_suffix('.md').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines)+'\n')
    print(json.dumps(dict(report=str(output), fixture_run=str(run), summary=summary), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
