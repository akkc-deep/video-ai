"""Full ordinary measurements in a separate, lossless research report format."""
from copy import deepcopy
import json
from pathlib import Path
from time import monotonic

from ._continuity_audit import AuditWindow, dependencies
from ._continuity_schema import ALGORITHM, PARAMETERS, stable, validate_continuity_manifest
from .continuity_analysis import _resolve_manifest, _ReaderProvider, measure_continuity
from .colorimetry import load_color_analysis_set
from .continuity_report import _finite_tree, _verify_frames
from ._continuity_schema import finite, _int, array
from ..planning.production_scenes import canonical_digest
from ..runtime._scene_continuity_io import artifact, local
from ..runtime.manifest import now, validate_run_dir
from ..runtime.production_state import ProductionRefused, object_fields
from ..runtime.research_material_records import MIB, ResearchReader, ref

POLICY = 'research_pair_report_v1'


def _bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')


def _write_raw(path, raw):
    if len(raw) > 16 * MIB:
        raise ProductionRefused('resource_limit: research output JSON')
    path = local(path, exists=False)
    if path.exists():
        if path.read_bytes() != raw:
            raise ProductionRefused('immutable research output differs')
        return artifact(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
    return artifact(path)


def _write(path, value):
    return _write_raw(path, _bytes(value))


def write_comparison(folder, sequence, comparison, *, producer, input_sha256):
    """Fragment the canonical JSON text, never round/drop numerical evidence."""
    raw = _bytes(comparison)
    if len(raw) > 48 * MIB:
        raise ProductionRefused('resource_limit: live research comparison metadata')
    text = raw.decode('utf-8')
    chunks = [text] if len(raw) <= 12 * MIB else [text[i:i + MIB] for i in range(0, len(text), MIB)]
    parts = []
    for number, payload in enumerate(chunks):
        path = Path(folder) / 'pairs' / f'{sequence:06d}_{number:04d}.json'
        parts.append(_write(path, dict(schema_version=2, policy=POLICY, producer=producer,
            input_sha256=input_sha256, sequence=sequence,
            comparison_id=comparison['comparison_id'], part_index=number, part_count=len(chunks), payload=payload)))
    return dict(sequence=sequence, **{k: comparison[k] for k in ('comparison_id', 'kind', 'left', 'right')}, parts=parts)


def read_comparison(row, *, folder, reader, producer, input_sha256):
    object_fields(row, 'sequence comparison_id kind left right parts'.split(), 'research comparison index')
    if type(row['sequence']) is not int or row['sequence'] < 0 or not 1 <= len(row['parts']) <= 64:
        raise ProductionRefused('invalid research comparison sequence/parts')
    payloads = []
    size = 0
    for i, part_ref in enumerate(row['parts']):
        expected = Path(folder) / 'pairs' / f'{row["sequence"]:06d}_{i:04d}.json'
        if Path(part_ref['path']) != expected:
            raise ProductionRefused('foreign/reordered research comparison shard')
        part = reader.read(part_ref)
        object_fields(part, 'schema_version policy producer input_sha256 sequence comparison_id part_index part_count payload'.split(), 'research shard')
        if (type(part['schema_version']) is not int or part['schema_version'] != 2 or part['policy'] != POLICY
                or part['sequence'] != row['sequence'] or part['comparison_id'] != row['comparison_id']
                or part['producer'] != producer or part['input_sha256'] != input_sha256
                or part['part_index'] != i or part['part_count'] != len(row['parts']) or type(part['payload']) is not str):
            raise ProductionRefused('research comparison shard producer differs')
        size += len(part['payload'].encode('utf-8'))
        if size > 48 * MIB:
            raise ProductionRefused('resource_limit: live research comparison metadata')
        payloads.append(part['payload'])
    from ..adapters.common import strict_json
    value = strict_json(''.join(payloads).encode('utf-8'))
    if any(value[k] != row[k] for k in ('comparison_id', 'kind', 'left', 'right')):
        raise ProductionRefused('comparison payload differs from root index')
    return value


def validate_comparison(value, *, declared, records, reader):
    object_fields(value, 'comparison_id kind left right regions'.split(), 'research comparison')
    if any(value[k] != declared[k] for k in ('comparison_id', 'kind', 'left', 'right')):
        raise ProductionRefused('research comparison producer differs')
    if [r['region_id'] for r in array(value['regions'], nonempty=True)] != declared['region_ids']:
        raise ProductionRefused('research comparison region coverage differs')
    _finite_tree(value)
    for region in value['regions']:
        object_fields(region, 'region_id comparability reasons geometry confidence confidence_kind confidence_components metrics evidence'.split(), 'research region')
        status = region['comparability']
        if (status not in ('comparable', 'not_comparable', 'unverified')
                or region['confidence_kind'] != 'match_support' or not 0 <= finite(region['confidence']) <= 1):
            raise ProductionRefused('invalid research region status/confidence')
        reasons = array(region['reasons'])
        if any(type(r) is not str or not r for r in reasons) or (status != 'comparable' and not reasons):
            raise ProductionRefused('research comparability reasons missing/invalid')
        if (status == 'comparable') != (region['metrics'] is not None):
            raise ProductionRefused('research comparability/metrics differ')
        geometry = region['geometry']
        object_fields(geometry, 'basis working_size candidate_points valid_points occupied_cells overlap_fraction fb_error_p90 ncc_median affine vectors sampled_pairs'.split(), 'research geometry')
        for key in ('candidate_points', 'valid_points', 'occupied_cells'):
            _int(geometry[key], key)
        if geometry['working_size'] is not None:
            if len(geometry['working_size']) != 2:
                raise ProductionRefused('invalid research geometry size')
            for size in geometry['working_size']:
                _int(size, 'working dimension', 1)
        for vector in array(geometry['vectors']):
            object_fields(vector, 'left right residual fb_error ncc'.split(), 'research vector')
            for side in ('left', 'right'):
                if len(vector[side]) != 2:
                    raise ProductionRefused('invalid research vector coordinates')
                for coordinate in vector[side]:
                    finite(coordinate)
        for pair in array(geometry['sampled_pairs']):
            if type(pair) is not list or len(pair) != 2:
                raise ProductionRefused('invalid research sampled pair')
            for point in pair:
                if type(point) is not list or len(point) != 2:
                    raise ProductionRefused('invalid research sampled coordinates')
                for coordinate in point:
                    _int(coordinate, 'sample coordinate')
        matching = PARAMETERS['geometry']['matching']
        if status == 'comparable' and (geometry['valid_points'] < matching['min_points']
                or not geometry['vectors'] or len(geometry['sampled_pairs']) < matching['min_sample_pairs']
                or geometry['occupied_cells'] < matching['min_grid_cells']
                or geometry['overlap_fraction'] is None or geometry['overlap_fraction'] < matching['min_overlap']):
            raise ProductionRefused('comparable research region lacks ordinary geometry support')
        if region['metrics'] is not None:
            object_fields(region['metrics'], ('delta_lab_median delta_e_median delta_e_p90 left_luma_median right_luma_median '
                'luma_log_ratio left_chroma_median right_chroma_median chroma_delta left_clipped_fractions '
                'right_clipped_fractions sampled_clipped_delta').split(), 'research metrics')
        expected_evidence = [records[value[side]] for side in ('left', 'right')]
        if region['evidence'] != expected_evidence:
            raise ProductionRefused('research comparison source evidence differs')
        for identity in region['evidence']:
            reader.capture(identity)


def _full_manifest(manifest):
    data = validate_continuity_manifest(manifest)
    if len(data['clips']) != 1 or len(data['references']) != 1 or data['profile'] is not None:
        raise ProductionRefused('research report requires one full clip, one reference, no qualification profile')
    frames = [v['frame_id'] for v in data['clips'][0]['frames']]
    reference = data['references'][0]['frame_id']
    expected = {('adjacent', a, b) for a, b in zip(frames, frames[1:])}
    expected |= {('reference', reference, frame) for frame in frames}
    actual = [(p['kind'], p['left'], p['right']) for p in data['comparisons']]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ProductionRefused('full research comparison coverage required, including reference frame zero')
    return data


class _ResearchWindow(AuditWindow):
    def __init__(self, paths, logger, deadline, intent):
        from ..runtime.logging import RunLogger
        paths.validate()
        if not isinstance(logger, RunLogger) or logger.production:
            raise ProductionRefused('independent non-production research logger required')
        run = validate_run_dir(logger.run_dir)
        if (run.parent != paths.runs_root or logger.root != run/'logs'
                or any(p.name != 'logs' for p in run.iterdir())
                or any(p.name not in ('events.jsonl','errors','processes','continuity') for p in logger.root.iterdir())):
            raise ProductionRefused('independent research audit location required')
        self.logger, self.deadline = logger, deadline
        self.frozen, self.outputs, self.json_bytes = {}, [], 0
        from ._continuity_storage import GeometryDecoder
        self.geometry_decoder = GeometryDecoder()
        self.packed_geometry = False
        self.intent = _write(logger.root/'continuity/research-input.json', intent)

    def save_bytes(self, name, data):
        self.check_time()
        output = self.logger.path('continuity/'+name)
        _write_raw(output, data)
        self.outputs.append(output)
        from ..runtime.manifest import hash_file, thaw
        return thaw(hash_file(output))

    def save(self, name, value):
        raw = _bytes(value)
        if len(raw) > 16 * MIB:
            raise ProductionRefused('resource_limit: research output JSON')
        return self.save_bytes(name, raw)


def analyze_research_pairs(manifest, *, config, paths, logger, timeout=300):
    data = _full_manifest(manifest)
    budget = ResearchReader(timeout)
    intent = dict(schema_version=2, policy=POLICY, producer=str(logger.run_dir),
        manifest_sha256=canonical_digest(stable(data)), parameters_sha256=canonical_digest(PARAMETERS),
        implementation=[artifact(Path(__file__), runtime=False),
            artifact(Path(__file__).parent.parent/'runtime/research_material_records.py', runtime=False)])
    if (logger.root/'continuity/report.json').exists():
        report = validate_research_pair_report(logger.root/'continuity/report.json', manifest=data, config=config, timeout=budget.remaining())['report']
        return report, [logger.root/'continuity/report.json']
    window = _ResearchWindow(paths, logger, budget.deadline, intent)
    deps = dependencies(window)
    implementation = [window.freeze(Path(__file__), package=True),
        window.freeze(Path(__file__).parent.parent / 'runtime/research_material_records.py', package=True)]
    records_in = [f['record']['path'] for c in data['clips'] for f in c['frames']] + [f['record']['path'] for f in data['references']]
    with load_color_analysis_set(records_in, config=config, timeout=budget.remaining()) as reader:
        plan, records = _resolve_manifest(data, reader, window)
        provider = _ReaderProvider(plan, records, reader)
        result = measure_continuity(plan, provider, deadline=budget.deadline)
        for frame in result['frame_results']:
            frame['source'] = records[frame['frame_id']]['source']
            frame['risks'] = records[frame['frame_id']]['risks']
        files = {**{i['path']: i for i in reader.identities}, **window.frozen}
        inputs = dict(manifest=data, files=[files[k] for k in sorted(files)])
        digest = canonical_digest(dict(inputs=stable(inputs), algorithm=ALGORITHM,
            parameters=PARAMETERS, dependencies=deps['fingerprint'], implementation=stable(implementation)))
        rows = []
        risks = []
        for i, comparison in enumerate(result['comparisons']):
            budget.check()
            source_records = {f['frame_id']: f['source_record'] for f in plan['frames']}
            for region in comparison['regions']:
                region['evidence'] = [source_records[comparison[side]] for side in ('left', 'right')]
            rows.append(write_comparison(logger.root / 'continuity', i, comparison,
                producer=str(logger.run_dir), input_sha256=digest))
            for region in comparison['regions']:
                for reason in region['reasons']:
                    risks.append(dict(code=reason, comparison_id=comparison['comparison_id'], region_id=region['region_id']))
        window.verify()
    risks.append(dict(code='missing_natural_qualification', comparison_id=None, region_id=None))
    report = dict(schema_version=2, algorithm=ALGORITHM, policy=POLICY,
        parameters=deepcopy(PARAMETERS), parameters_sha256=canonical_digest(PARAMETERS),
        input_sha256=digest, inputs=inputs, dependencies=deps, implementation=implementation,
        producer=str(logger.run_dir), analysis_intent=window.intent, scope=data['scope'], scene_id=data['scene_id'], domain=data['domain'],
        coverage=result['coverage'], frame_results=result['frame_results'], comparisons=rows,
        trajectories=result['trajectories'], detectors=result['detectors'], profile=None,
        production_eligible=False, risks=risks, created_at=now())
    window.save('report.json', report)
    return report, [*window.outputs, *(Path(p['path']) for row in rows for p in row['parts'])]


def validate_research_pair_report(path, *, manifest, config, timeout=300):
    budget = ResearchReader(timeout)
    report = budget.read(path)
    object_fields(report, ('schema_version algorithm policy parameters parameters_sha256 input_sha256 inputs '
        'dependencies implementation producer analysis_intent scope scene_id domain coverage frame_results comparisons '
        'trajectories detectors profile production_eligible risks created_at').split(), 'research report')
    data = _full_manifest(manifest)
    folder = Path(path['path'] if isinstance(path, dict) else path).parent
    run = validate_run_dir(Path(report['producer']))
    if (folder != run / 'logs/continuity' or type(report['schema_version']) is not int or report['schema_version'] != 2
            or report['algorithm'] != ALGORITHM or report['policy'] != POLICY or report['profile'] is not None
            or report['production_eligible'] is not False or report['parameters'] != PARAMETERS
            or report['parameters_sha256'] != canonical_digest(PARAMETERS) or report['inputs']['manifest'] != data):
        raise ProductionRefused('research report identity/policy/manifest differs')
    for identity in report['inputs']['files'] + report['implementation']:
        budget.capture(identity, package=True)
    expected_implementation = [Path(__file__), Path(__file__).parent.parent / 'runtime/research_material_records.py']
    if [p['path'] for p in report['implementation']] != [str(p) for p in expected_implementation]:
        raise ProductionRefused('research report implementation differs')
    intent = budget.read(report['analysis_intent'])
    if (Path(report['analysis_intent']['path']) != folder/'research-input.json' or intent != dict(
            schema_version=2, policy=POLICY, producer=str(run), manifest_sha256=canonical_digest(stable(data)),
            parameters_sha256=canonical_digest(PARAMETERS), implementation=[ref(v) for v in report['implementation']])):
        raise ProductionRefused('research analysis intent differs')
    deps = report['dependencies']
    for identity in deps['package_files']:
        budget.capture(identity, package=True)
    build = Path(budget.capture(deps['build_information'])['path']).read_text(encoding='utf-8')
    fingerprint = canonical_digest(dict(python=deps['python'], numpy=deps['numpy'], opencv=deps['opencv'],
        build_information=build, package_files=stable(deps['package_files'])))
    digest = canonical_digest(dict(inputs=stable(report['inputs']), algorithm=ALGORITHM,
        parameters=PARAMETERS, dependencies=fingerprint, implementation=stable(report['implementation'])))
    if deps['fingerprint'] != fingerprint or report['input_sha256'] != digest:
        raise ProductionRefused('research report dependency/input digest differs')
    if len(report['comparisons']) != len(data['comparisons']):
        raise ProductionRefused('research report comparison coverage differs')
    counts = dict(comparable=0, not_comparable=0, unverified=0)
    for i, (row, expected) in enumerate(zip(report['comparisons'], data['comparisons'])):
        if row['sequence'] != i or any(row[k] != expected[k] for k in ('comparison_id', 'kind', 'left', 'right')):
            raise ProductionRefused('research report comparison order/coverage differs')
        value = read_comparison(row, folder=folder, reader=budget, producer=str(run), input_sha256=report['input_sha256'])
        source_records = {f['frame_id']: f['record'] for c in data['clips'] for f in c['frames']}
        source_records.update({f['frame_id']: f['record'] for f in data['references']})
        validate_comparison(value, declared=expected, records=source_records, reader=budget)
        if [r['region_id'] for r in value['regions']] != expected['region_ids']:
            raise ProductionRefused('research comparison region coverage differs')
        statuses = [r['comparability'] for r in value['regions']]
        status = 'comparable' if 'comparable' in statuses else 'unverified' if 'unverified' in statuses else 'not_comparable'
        counts[status] += 1
    record_paths = [f['record']['path'] for c in data['clips'] for f in c['frames']] + [f['record']['path'] for f in data['references']]
    with load_color_analysis_set(record_paths, config=config, timeout=budget.remaining()) as color:
        class ResolveWindow:
            def read_json(self, identity): return budget.read(identity)
            def check(self, identity): return budget.capture(identity)
        plan, records = _resolve_manifest(data, color, ResolveWindow())
        _verify_frames(report, plan, records)
        expected_ids = [f['frame_id'] for c in data['clips'] for f in c['frames']] + [f['frame_id'] for f in data['references']]
        if [r['frame_id'] for r in report['frame_results']] != expected_ids:
            raise ProductionRefused('research report frame coverage differs')
        for saved, current in zip(report['frame_results'], color.frames):
            if (stable(saved['record']) != stable(current['record_identity']) or saved['source'] != current['record']['source']
                    or saved['source_frame_index'] != current['record']['frame_index']):
                raise ProductionRefused('research report frame identity differs')
    expected_counts = dict(requested_frames=len(record_paths), ready_frames=sum(f['status'] == 'ready' for f in report['frame_results']),
        requested_pairs=len(data['comparisons']), comparable_pairs=counts['comparable'],
        not_comparable_pairs=counts['not_comparable'], unverified_pairs=counts['unverified'])
    if report['coverage'] != expected_counts:
        raise ProductionRefused('research report coverage statistics differ')
    budget.verify_all()
    return dict(report=report, closure=[budget.frozen[k] for k in sorted(budget.frozen)])
