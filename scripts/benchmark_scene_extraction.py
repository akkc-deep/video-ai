"""Reproduce the 12-frame local extraction benchmark in a new fixture run.

Run with the existing video-ai environment. Only FFmpeg/FFprobe are executed;
no production run, model, service, network or cloud request is used.
"""
import argparse
import json
from pathlib import Path
import socket
import subprocess
from time import perf_counter
from unittest.mock import patch

from video_ai.config import load_config
from video_ai.media.frames import extract_video_frames
from video_ai.media.scene_upscale import _decode, extract_scene_frames, verify_png
from video_ai.media.video import inspect_video
from video_ai.runtime.environment import build_child_env
from video_ai.runtime.logging import RunLogger
from video_ai.runtime.manifest import hash_file
from video_ai.runtime.paths import RuntimePaths, create_run
from video_ai.runtime.processes import run_logged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
        default=Path('D:/VideoSi/cache/video-ai/logs/scene-extraction-benchmark.json'))
    args = parser.parse_args()
    output = args.output.resolve()
    log_root = Path('D:/VideoSi/cache/video-ai/logs').resolve()
    if not output.is_relative_to(log_root):
        parser.error('report must be inside the cache log directory')
    config = load_config(Path(__file__).resolve().parents[1]/'config/production.example.json')
    paths = RuntimePaths.from_config(config)
    run = create_run(paths)
    logger = RunLogger(run)
    frames, width, height, fps = 12, 128, 72, 16
    unit_id = 'scene-extraction-benchmark'
    kwargs = dict(config=config, paths=paths, logger=logger, unit_id=unit_id)
    source = run/'fixture.mp4'
    (run/'benchmark-fixture.json').write_text(json.dumps(dict(
        kind='offline_scene_extraction', frames=frames, width=width, height=height,
        fps=fps, production_run=False))+'\n', encoding='utf-8')

    def denied(*a, **kw):
        raise RuntimeError('offline extraction benchmark forbids network')

    popen = subprocess.Popen
    allowed = {Path(config.tools[key]).resolve() for key in ('ffmpeg', 'ffprobe')}
    commands = []

    def media_process(argv, *a, **kw):
        if isinstance(argv, (str, bytes)) or Path(argv[0]).resolve() not in allowed:
            raise RuntimeError('benchmark permits only explicit media-tool arguments')
        commands.append([str(value) for value in argv])
        return popen(argv, *a, **kw)

    with (patch.object(socket.socket, 'connect', denied),
          patch.object(socket.socket, 'connect_ex', denied),
          patch.object(socket, 'create_connection', denied)):
        fixture = run_logged(tuple(map(str, [config.tools['ffmpeg'], '-nostdin', '-n',
            '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size={width}x{height}:rate={fps}',
            '-frames:v', str(frames), '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-an', '-movflags', '+faststart', source])), cwd=run,
            env=build_child_env(paths), timeout=30, logger=logger,
            stage='test_fixture', unit_id=unit_id)
        if fixture.returncode or fixture.timed_out:
            raise RuntimeError(f'fixture creation failed: {fixture.stderr_path}')
        source_before = hash_file(source)

        with patch.object(subprocess, 'Popen', media_process):
            start = perf_counter()
            inspect_video(source, width=width, height=height, **kwargs)
            previous, _ = extract_video_frames(source, run/'previous', expected_frames=frames,
                width=width, height=height, timeout=1200, **kwargs)
            # Exact old checker: decode the source, then probe/decode EVERY PNG.
            # Do not substitute the now-optimized verify_scene_frame_pixels here.
            raw = _decode(source, config, timeout=1200)
            size = width*height*3
            if len(raw) != frames*size:
                raise RuntimeError('previous source decode frame count differs')
            for index in range(frames):
                pixels = verify_png(run/'previous'/f'frame_{index+1:06d}.png',
                    width=width, height=height, config=config)
                if pixels != raw[index*size:(index+1)*size]:
                    raise RuntimeError('previous extraction pixels differ from source')
            prior_seconds = perf_counter()-start
            prior_commands = list(commands)
            del raw, pixels
            commands.clear()

            start = perf_counter()
            current, _ = extract_scene_frames(source, run/'current', expected_frames=frames,
                width=width, height=height, **kwargs)
            current_seconds = perf_counter()-start
            current_commands = list(commands)

        previous_sha = [item['identity']['sha256'] for item in previous]
        current_sha = [item['sha256'] for item in current]
        if previous_sha != current_sha or len(current_sha) != frames:
            raise RuntimeError('complete PNG sequence SHA256 differs between extraction paths')
        source_after = hash_file(source)
        if (source_before.bytes, source_before.sha256) != (source_after.bytes, source_after.sha256):
            raise RuntimeError('source changed during benchmark')
        if (len(prior_commands), len(current_commands)) != (53, 6):
            raise RuntimeError('expected exactly 53 previous and 6 aggregate media processes')

    report = dict(schema_version=1, fixture_run=str(run), source=str(source),
        parameters=dict(frames=frames, width=width, height=height, fps=fps),
        timings_seconds=dict(previous=round(prior_seconds, 6), current=round(current_seconds, 6)),
        media_subprocesses=dict(previous=len(prior_commands), current=len(current_commands)),
        speedup=round(prior_seconds/current_seconds, 4),
        complete_png_sha256_preserved=True, frame_sha256=current_sha,
        source_sha256=source_after.sha256, source_unchanged=True,
        media_commands=dict(previous=prior_commands, current=current_commands),
        real_network_requests=0, paid_submissions=0, model_requests=0, production_runs_modified=0,
        scope='One local 12-frame 128x72 sample; cloud, model inference and full-film elapsed time are unmeasured.')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(report=str(output), fixture_run=str(run),
        timings_seconds=report['timings_seconds'], media_subprocesses=report['media_subprocesses'],
        speedup=report['speedup'], complete_png_sha256_preserved=True)), flush=True)


if __name__ == '__main__':
    main()
