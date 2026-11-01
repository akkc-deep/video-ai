"""Reproducible, unqualified natural-color features for a complete research input."""
from pathlib import Path

from ..media.colorimetry import load_color_analysis_set
from ..media.natural_color_repair import natural_patch_features, ALGORITHM
from ..media.research_pair_report import read_comparison, validate_research_pair_report
from ._scene_continuity_io import artifact
from .manifest import now, thaw
from .production_state import RunLock
from .research_material_records import ResearchReader, load_research_material_context


def measure_natural_manifest(manifest, report_path, *, config, timeout=300):
    import numpy as np
    reader = ResearchReader(timeout)
    verified = validate_research_pair_report(report_path, manifest=manifest, config=config, timeout=reader.remaining())
    report = verified['report']
    source_regions = reader.read(manifest['regions'])['regions']
    targets = manifest['clips'][0]['frames']
    reference = manifest['references'][0]
    rid_to_region = {r['region_id']: r for r in source_regions}
    trajectory = {t['region_id']: {s['frame_id']: s for s in t['samples']} for t in report['trajectories']}
    by_right = {r['right']: r for r in report['comparisons'] if r['kind'] == 'reference'}
    features = []
    paths = [reference['record']['path']] + [t['record']['path'] for t in targets]
    with load_color_analysis_set(paths, config=config, timeout=reader.remaining()) as colors:
        records = {f['record_identity']['path']: f['record'] for f in colors.frames}
        sidecars = colors.sidecars

        def pixels(entry):
            record = records[entry['record']['path']]
            side = sidecars[record['sidecar']['path']]['probe']['video']
            raw = colors.read_rgb(entry['record']['path'])
            if raw is None:
                raise ValueError('natural baseline needs complete sRGB pixel evidence')
            return np.frombuffer(raw, np.uint8).reshape(side['height'], side['width'], 3)

        clean = pixels(reference)
        for index, frame in enumerate(targets):
            reader.check()
            pair_index = by_right[frame['frame_id']]
            pair = read_comparison(pair_index, folder=Path(report['producer'])/'logs/continuity', reader=reader,
                producer=report['producer'], input_sha256=report['input_sha256'])
            reasons = []
            coordinates = []
            regions = {}
            for region in pair['regions']:
                rid = region['region_id']
                if region['comparability'] != 'comparable':
                    reasons += [rid + ':' + reason for reason in region['reasons']]
                    continue
                declared = rid_to_region[rid]
                anchor = next(a for a in declared['anchors'] if a['frame']['path'] == reference['record']['path'])
                current_box = trajectory.get(rid, {}).get(frame['frame_id'], {}).get('box')
                if current_box is None:
                    reasons.append(rid + ':missing_propagated_region')
                    continue
                regions[rid] = dict(role=declared['role'], reference_rect=anchor['rect'], current_rect=current_box)
                coordinates += [dict(region_id=rid, reference=points[0], current=points[1])
                                for points in region['geometry']['sampled_pairs']]
            if reasons:
                measured = None
                status = 'not_comparable'
            else:
                measured = natural_patch_features(clean, pixels(frame), coordinates, regions)
                status = measured['status']
            features.append(dict(source_frame_index=index, comparison_id=pair['comparison_id'],
                comparison=pair_index, status=status, reasons=reasons, features=measured))
        for identity in colors.identities:
            reader.capture(identity, package=True)
    reader.verify_all()
    return dict(schema_version=1, algorithm=ALGORITHM, kind='unqualified_natural_diagnostic_v1',
        report=reader.capture(report_path), implementation=[artifact(Path(__file__), runtime=False),
        artifact(Path(__file__).parent.parent/'media/natural_color_repair.py', runtime=False)],
        frames=features, all_frames_supported=all(f['status'] == 'measured' for f in features),
        operation=None, thresholds=None, qualification='awaiting_qualification',
        full_video_observation='unverified', production_eligible=False, ready_for_propose=False)


def measure_research_material(run_dir, *, timeout=300):
    from ..config import load_config
    from .production_research_material import _save
    reader = ResearchReader(timeout)
    run = Path(run_dir)
    with RunLock(run) as lock:
        context = load_research_material_context(run, reader=reader)
        if context['assessment'] is None:
            raise ValueError('research material needs a complete current ordinary assessment')
        assessment = reader.read(context['assessment'])
        manifest = reader.read(assessment['manifest'])
        options = reader.read(run/'research/options.json')
        config = load_config(Path(options['config']['path']))
        result = measure_natural_manifest(manifest, assessment['report'], config=config, timeout=reader.remaining())
        result.update(commit=context['commit'], assessment=context['assessment'])
        path = run/'research/continuity/natural-baseline.json'
        saved = _save(path, result, lock)
        return dict(schema_version=1, run_dir=str(run), status='research_input_ready', baseline=saved,
            native_frames=len(result['frames']), all_frames_supported=result['all_frames_supported'],
            qualification='awaiting_qualification', ready_for_propose=False)
