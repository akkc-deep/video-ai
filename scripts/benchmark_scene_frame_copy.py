"""Offline byte-copy benchmark in a new fixture run; no production or cloud work."""
import argparse
import json
from pathlib import Path
import shutil
import socket
from statistics import mean
import subprocess
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch

from video_ai.config import load_config, read_json
from video_ai.runtime.paths import RuntimePaths, create_run
from video_ai.runtime.production_state import RunLock
from video_ai.runtime.scene_revision_records import RevisionGuard, artifact, verify_artifact
from video_ai.runtime._scene_composition_materialized import copy_bytes, copy_frame_sequence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('D:/VideoSi/cache/video-ai/logs/scene-frame-copy-benchmark.json'))
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(Path('D:/VideoSi/cache/video-ai/logs')):
        parser.error('report must be inside the cache log directory')
    config = load_config(Path(__file__).resolve().parents[1]/'config/production.example.json')
    run = create_run(RuntimePaths.from_config(config))
    frames = run/'source-frames'
    frames.mkdir()
    history = run/'history'
    history.mkdir()

    def denied(*a, **kw):
        raise RuntimeError('offline benchmark forbids network')

    with (patch.object(socket.socket, 'connect', denied), patch.object(socket.socket, 'connect_ex', denied),
          patch.object(socket, 'create_connection', denied)):
        png = run/'fixture.png'
        subprocess.run([str(config.tools['ffmpeg']), '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
            'color=c=blue:s=1920x1080', '-frames:v', '1', '-pix_fmt', 'rgb24', str(png)],
            check=True, capture_output=True)
        guard = RevisionGuard(SimpleNamespace(options={'script_path': str(run/'production/script.txt')}))
        for i in range(64):
            path = history/f'{i}.json'
            path.write_text(json.dumps({'index': i, 'payload': 'x'*16384}), encoding='utf-8')
            guard.capture(path, root=run)
        rows = []
        for i in range(24):
            path = frames/f'{i}.png'
            shutil.copyfile(png, path)
            rows.append({'image': guard.capture(path, root=run)})
        timings = {}
        counts = {}
        with RunLock(run) as held:
            audits = []

            def full():
                audits.append(True)
                guard.verify_captured_bytes()

            def owned():
                if read_json(held.path) != held.owner:
                    raise RuntimeError('fixture lock changed')

            store = SimpleNamespace(run_dir=run, verify_global=full, assert_write=owned,
                validate_artifact=lambda value: verify_artifact(value, root=run),
                artifact=lambda path: artifact(path, root=run))
            for name in ('prior_per_frame_audit', 'batch_boundary_audit'):
                elapsed = []
                call_counts = []
                for attempt in range(3):
                    folder = run/f'{name}-{attempt}'
                    (folder/'frames').mkdir(parents=True)
                    guard.verify_captured_bytes()  # same local cache warm-up for both paths
                    audits.clear()
                    start = perf_counter()
                    if name == 'prior_per_frame_audit':
                        result = [copy_bytes(store, row['image'], folder/'frames'/f'frame_{i:06d}.png')
                                  for i, row in enumerate(rows, 1)]
                    else:
                        result = copy_frame_sequence(store, rows, folder)
                    elapsed.append(round(perf_counter()-start, 6))
                    call_counts.append(len(audits))
                    if [a['sha256'] for a in result] != [row['image']['sha256'] for row in rows]:
                        raise RuntimeError('copied frame bytes changed')
                timings[name] = elapsed
                counts[name] = call_counts
    before, after = (mean(timings[key]) for key in ('prior_per_frame_audit', 'batch_boundary_audit'))
    report = dict(fixture_run=str(run), frame_count=24, source_history_files=64, timings_seconds=timings,
        full_source_audits=counts, before_mean=before, after_mean=after,
        reduction_percent=100*(1-after/before), exact_frame_sha256_preserved=True,
        real_network_requests=0, paid_submissions=0,
        scope='real local PNG copies, SHA/lock/fsync kept; only fixture source-history size, not full-film elapsed time')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
