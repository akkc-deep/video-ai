"""Read-only reference replay benchmark. All sockets and production writes fail closed."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import socket
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch

from video_ai.runtime import scene_revision_records as revisions, verification
from video_ai.runtime import jimeng_reference_candidates as candidates
from video_ai.runtime import image_selection_records as images
from video_ai.runtime.production_inputs import load_frozen_inputs
from video_ai.runtime.reference_image_records import reference_candidates
from video_ai.runtime.manifest import thaw
from video_ai.jimeng_config import parse_image_generation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scene', default='scene_0019')
    args = parser.parse_args()
    run = args.run.resolve(strict=True)
    if args.output.resolve().is_relative_to(run):
        parser.error('report must be outside the production run')
    counts = Counter()

    def denied(*a, **kw):
        raise RuntimeError('offline benchmark forbids network and production writes')

    def existing_save(store, path, value, **kw):
        store.owned()
        if not path.is_file() or images._read(path) != thaw(value):
            raise RuntimeError('read-only replay would change a production record: '+str(path))

    folder = run/'production'
    immutable = [folder/name for name in ('inputs', 'workflows', 'options.json', 'script.txt')]
    revision = folder/'scene-revision'
    immutable.extend(revision/name for name in ('imports', 'media', 'views'))
    immutable.extend(revision.glob('*.json'))
    immutable.extend(p for p in (folder/'jimeng').glob('scene_*') if (p/'candidates.json').is_file())
    immutable.extend(p for p in (folder/'image-selection').glob('image_batch_*') if (p/'accepted.json').is_file())
    timings = {}

    def measure(name, function, repeats=1):
        elapsed = []
        value = None
        for _ in range(repeats):
            start = perf_counter()
            value = function()
            elapsed.append(round(perf_counter()-start, 6))
        timings[name] = elapsed
        print(json.dumps(dict(stage=name, seconds=elapsed)), flush=True)
        return value

    protected = [run/'.make-video.lock', *folder.rglob('*.original'),
                 *folder.rglob('accepted.json'), *folder.rglob('result.json'),
                 *folder.rglob('candidates.json')]

    def fingerprints():
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}

    original_mkdir = Path.mkdir

    def existing_mkdir(path, *a, **kw):
        if path.is_relative_to(run):
            if not path.is_dir():
                denied()
            return
        return original_mkdir(path, *a, **kw)

    before = fingerprints()
    with (patch.object(socket.socket, 'connect', denied), patch.object(socket.socket, 'connect_ex', denied),
          patch.object(socket, 'create_connection', denied), patch.object(Path, 'mkdir', existing_mkdir),
          patch.object(candidates._Records, 'save', existing_save), patch.object(candidates._Records, 'image', denied),
          verification.whole_input_protection(immutable_roots=[p for p in immutable if p.exists()]),
          verification.writable_validation_session(run), revisions.revision_scope()):
        frozen = measure('initial_load', lambda: load_frozen_inputs(run))
        proof = measure('initial_revision_admission', lambda: revisions.require_scene_revision(frozen))
        guard = proof['guard']
        measure('warm_full_source_check', guard.verify_captured_bytes, 3)
        measure('warm_full_config_load', lambda: load_frozen_inputs(run), 3)
        plan = proof['imports']['plan:all'][0]['view']['scene_plan']
        bible = proof['imports']['plan:all'][0]['view']['bible']
        scene = next(s for s in plan['scenes'] if s['scene_id'] == args.scene)
        manifest_path = folder/'jimeng'/args.scene/'candidates.json'
        provenance = images._read(folder/'reference-images'/args.scene/'provenance.json')
        settings = images._read(folder/'reference-images/settings.json')
        model = parse_image_generation(settings['model_settings'], 'benchmark')
        client = SimpleNamespace(settings=model, submit=denied, query=denied, download=denied)
        # This object only observes the paused owner's lock. No RunLock acquisition,
        # process control, production CLI, or write-capable store is used.
        lock = SimpleNamespace(run_dir=run, path=run/'.make-video.lock', owner=images._read(run/'.make-video.lock'))
        verify_artifact = revisions.verify_artifact
        config_load = images.load_frozen_inputs

        def counted_artifact(*a, **kw):
            counts['source_artifacts_verified'] += 1
            return verify_artifact(*a, **kw)

        def counted_load(*a, **kw):
            counts['frozen_loads'] += 1
            return config_load(*a, **kw)

        with patch.object(revisions, 'verify_artifact', counted_artifact), patch.object(images, 'load_frozen_inputs', counted_load):
            measure('existing_candidate_validation', lambda: reference_candidates(frozen, scene, manifest_path))
            counts.clear()
            result = measure('completed_scene_recovery', lambda: candidates.generate_reference_candidates(
                frozen, scene, bible, provenance['references'], settings=settings, capability=settings['capability'],
                client=client, paths=None, logger=None, lock=lock), 3)
        report = dict(run=str(run), scene=args.scene, timings_seconds=timings, recovery_counts=dict(counts),
                      recovered_candidates=len(result['candidates']), real_network_requests=0,
                      production_writes=0, protected_fingerprints_unchanged=before == fingerprints())
    if not report['protected_fingerprints_unchanged']:
        raise RuntimeError('production evidence changed during read-only benchmark')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
