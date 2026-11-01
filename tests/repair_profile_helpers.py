"""Compact complete sealed evidence for repair integration tests; no real media."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

REAL = Path('D:/VideoSi/projects/video-ai/continuity-benchmark/AI-repair-calibration-20261027-r2')

def identity(path):
    return dict(path=str(path), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), mtime_ns=path.stat().st_mtime_ns)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return identity(path)


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _control_rows(sid,split,green_axis,row_payload_bytes):
    rows=[]
    for op in ('exposure','wb_r','wb_g','wb_b','chroma'):
        for sign in (-1,1):
            for level in (1/64,1/32,1/16,1/8,1/4,1/2,1.):
                amplitude=-sign*(.0366 if green_axis and op=='wb_g' else .02)
                passed=(level==1/64 and (split=='calibration' or (op=='exposure' and sign==1) or (green_axis and op=='wb_g')))
                rows.append(dict(source_id=sid,split=split,case_id=f'{op}_{"neg" if sign<0 else "pos"}_{level:g}',
                    operation=op,injection_direction=sign,level=level,estimated_amplitude=amplitude,
                    conditional_operator_and_correspondence=True,passed=passed,status='measured',
                    fit=dict(status='estimated',amplitude=amplitude,fit_pairs=81,reason=None),frames=[],
                    parameter_temporal_variation=0.,temporal_mean_error_differences=[]))
    rows.append(dict(source_id=sid,split=split,case_id='identity',operation='identity',injection_direction=0,
        level=0.,estimated_amplitude=0.,conditional_operator_and_correspondence=True,passed=True,status='measured',
        fit=dict(status='noop',amplitude=0.,reason='identical_pixels'),frames=[],parameter_temporal_variation=0.,temporal_mean_error_differences=[]))
    for name in ('allowed_lighting','not_comparable','motion_defect'):
        rows.append(dict(source_id=sid,split=split,case_id=name,operation='context_gate',injection_direction=0,
            level=0.,estimated_amplitude=None,conditional_operator_and_correspondence=True,passed=True,status='context_rejected',
            fit=dict(status='abstained',amplitude=None,reason='context_gate'),frames=[],
            negative_construction='exposure +0.125 with explicit author context; tests gate, not semantic detector'))
    if row_payload_bytes:
        rows[0]['frames']=[{'fixture_only_opaque_payload':'x'*row_payload_bytes}]
    return rows


def make_profile(tmp_path, *, control_targets=False, row_payload_bytes=0, holdout_finished_at=None, green_axis=False):
    """Complete compact 24-source fixture; no measurement/refit or real media."""
    root = tmp_path / 'fixture_only_repair_study'; root.mkdir(parents=True)
    old = load(REAL / 'inputs.FROZEN.json')
    protocol = load(REAL / 'protocol.FROZEN.json'); protocol['created_at'] = '2026-10-26T00:00:00+00:00'
    protocol_ref = save(root / 'protocol.FROZEN.json', protocol)
    software = [identity(Path(ref['path'])) for ref in old['software']]
    archive = root / 'software/calibrator.py'; archive.parent.mkdir(); archive.write_bytes(Path(software[0]['path']).read_bytes())
    entries = []; results = {'calibration': [], 'holdout': []}; metas = {}
    genres = ['people', 'animals', 'transport', 'outdoor', 'indoor', 'animation']
    for split in ('calibration', 'holdout'):
        for genre in genres:
            for n in range(2):
                sid = f'{split}_{genre}_{n}'
                source = dict(source_id=sid, genre=genre, source_kind='animation' if genre == 'animation' else 'captured',
                    scene_group=sid, interval=dict(start_pts=0, end_pts=1, time_base='1/16'), rights_note='fixture_only', context=None)
                identities = []
                for key in ('media', 'regions', 'truth', 'frame'):
                    ref = save(tmp_path / 'original' / (sid + '.' + key), {'fixture_only': sid + key})
                    identities.append(ref)
                    source['frame_records' if key == 'frame' else key] = [dict(ref, verified_at='2026-10-25T00:00:00+00:00')] if key == 'frame' else ref
                entry = dict(source=source, split=split, ROI_origin='fixture_only', ROI_uncertainties=None)
                if control_targets and not entries:
                    source['control_targets'] = dict(local_color=dict(region_ids=['background'], authorization=source['truth']))
                entries.append(entry)
                pack = root / 'source-packs' / (sid + '.npz'); pack.parent.mkdir(exist_ok=True); pack.write_bytes(b'fixture_only_not_decoded')
                meta = dict(source_id=sid, scene_group=sid, genre=genre, split=split, eligible=True,
                    eligibility_reason='all frames >=81 pairs and >=81 informative fitting pairs',
                    frames=1, timeline=[dict(frame_index=0, pts=0, time_base='1/16')], interval=source['interval'],
                    counts=[dict(points=81, regions=[dict(region_id='background', role='background', points_before_role_cap=81)])],
                    informative_pairs=81, sampling='oracle paired coordinates; visible ROI; at most 1024 pixels per role',
                    ROI_origin=entry['ROI_origin'], ROI_uncertainties=None, source_identities=identities,
                    pack=identity(pack), pixel_allocation_bound=16777216)
                metas[sid] = meta
                save(root / 'source-packs' / (sid + '.json'), meta)
                result = dict(status='completed', closure_verified=True, source=meta,
                    rows=_control_rows(sid,split,green_axis,row_payload_bytes), elapsed_seconds=1.,
                    finished_at='2026-10-26T00:01:00+00:00' if split == 'calibration' else (holdout_finished_at or '2026-10-26T00:03:00+00:00'))
                ref = save(root / 'source-results' / (sid + '.json'), result)
                save(root / 'source-results' / (sid + '.identity.json'), ref)
                results[split].append(ref)
    original = save(tmp_path / 'original' / 'original-index.json', dict(sources=entries))
    inputs = dict(created_at='2026-10-26T00:00:01+00:00', authorization='fixture_only authorization', index=original,
        protocol=protocol_ref, software=software, versions=dict(python=sys.version,
            numpy=importlib.metadata.version('numpy'), opencv=importlib.metadata.version('opencv-python-headless')),
        sources=entries, source_count=24, requested_controls_per_source=74, production_eligible=False,
        limitations=old['limitations'])
    inputs_ref = save(root / 'inputs.FROZEN.json', inputs); save(root / 'inputs-identity.json', inputs_ref)
    fields = dict(schema_version=1, algorithm='AI_conditional_constant_color_repair_v1',
                  purpose='offline_AI_repair_calibration', production_eligible=False, inputs=inputs_ref)
    bounds = []; checks = []
    for op in ('exposure', 'wb_r', 'wb_g', 'wb_b', 'chroma'):
        for sign in (-1, 1):
            eligible = [e['source']['source_id'] for e in entries if e['split'] == 'calibration']
            bounds.append(dict(operation=op, injection_direction=sign, max_injection_level=.015625,
                correction_direction=-sign, correction_amplitude_ceiling=.0366 if green_axis and op == 'wb_g' else .02,
                eligible_sources=eligible, coverage_sufficient=True, reason=None))
            eligible = [e['source']['source_id'] for e in entries if e['split'] == 'holdout']
            passed = (op == 'exposure' and sign == 1) or (green_axis and op == 'wb_g')
            checks.append(dict(operation=op, injection_direction=sign, qualified=passed, coverage_sufficient=True,
                eligible_sources=eligible, cases=[dict(source_id=sid, level=.015625, measured=True,
                    passed=passed, within_fitted_parameter_domain=True) for sid in eligible], reason=None))
    sealed = dict(fields, created_at='2026-10-26T00:02:00+00:00', calibration_results=results['calibration'],
                  bounds=bounds, sources=[{k: m[k] for k in ('source_id','scene_group','genre','split','eligible')}
                    for m in metas.values() if m['split'] == 'calibration'])
    seal_ref = save(root / 'thresholds.SEALED.json', sealed); save(root / 'threshold-seal-identity.json', seal_ref)
    evaluation = dict(fields, created_at='2026-10-26T00:04:00+00:00', thresholds=seal_ref,
        holdout_results=results['holdout'], checks=checks,
        context_gates={k:dict(requested=24,refused=24,not_exercised=0) for k in ('allowed_lighting','not_comparable','motion_defect')},
        requested_sources=24, requested_controls=1776, source_groups_not_certified_independent=True,
        limitations=inputs['limitations'], qualified_directions=[{k:c[k] for k in ('operation','injection_direction')} for c in checks if c['qualified']],
        temporal_policy=protocol['temporal_policy'], unsupported=['time-varying drift','local correction','unknown lighting intent',
            'unmatched pixels','automatic model/axis selection','combined parameter axes','arbitrary hue rotation'])
    evaluation_ref = save(root / 'evaluation.json', evaluation)
    path = root / 'experimental-repair-profile.json'
    save(path, dict(evaluation, evaluation=evaluation_ref, calibrated_bounds=bounds, evidence_only=True))
    return path


