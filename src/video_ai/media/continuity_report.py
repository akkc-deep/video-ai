"""Read-only verification of ordinary persisted continuity audit evidence.

This module never starts a process, creates a logger, decodes a frame, or runs
registration. Existing color evidence and manifest validators remain the source
of truth for native source, processing, mapping and color interpretation.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from time import monotonic
from types import SimpleNamespace

from ._continuity_schema import (ALGORITHM, PARAMETERS, DETECTORS, array, finite,
    stable, validate_continuity_manifest)
from .colorimetry import _object, _int, _local_file, _command_record
from ..planning.production_scenes import canonical_digest
from ..runtime.manifest import hash_file, thaw, _identity, _timestamp, validate_run_dir
from ..runtime.paths import RUNTIME_ROOT, _validate_spelling

REPORT_FIELDS = ('schema_version algorithm parameters parameters_sha256 input_sha256 inputs dependencies '
    'scope scene_id domain frame_results comparisons trajectories detectors coverage profile risks created_at').split()
IDENTITY_FIELDS = {'path', 'bytes', 'mtime_ns', 'sha256', 'verified_at'}
ARTIFACT_FIELDS = {'path', 'bytes', 'sha256'}
MAX_JSON = 16 * 1024 * 1024
MAX_METADATA = 64 * 1024 * 1024


def _artifact(identity):
    return {key: identity[key] for key in ('path', 'bytes', 'sha256')}


def _equal(left, right):
    # Python equates True with 1; the persisted contracts do not.
    return canonical_digest(left) == canonical_digest(right)


def _same_json(left,right,check):
    """Typed JSON equality without serializing a second large logical tree."""
    check()
    if type(left) is not type(right):return False
    if isinstance(left,dict):
        return left.keys()==right.keys() and all(_same_json(left[k],right[k],check) for k in left)
    if isinstance(left,list):
        return len(left)==len(right) and all(_same_json(a,b,check) for a,b in zip(left,right))
    if type(left) is float:return repr(left)==repr(right)
    return left==right


def _source_path(value):
    """Installation files may live outside the runtime media root."""
    text = _validate_spelling(str(value))
    path = Path(text)
    if (not path.is_absolute() or any(p in ('.', '..') for p in re.split(r'[/\\]', text))
            or path != path.resolve(strict=True)
            or any(p.is_symlink() or p.is_junction() for p in (path, *path.parents))
            or not path.is_file() or path.stat().st_nlink != 1):
        raise ValueError('regular non-aliased dependency/source required')
    return path


class _CaptureWindow:
    """Adapter for the analyzer's dependency inventory; save stays in memory."""
    def __init__(self):
        self.files = {}
        self.build = None

    def freeze(self, path, *, package=False):
        path = _source_path(path)
        key = str(path)
        if key not in self.files:
            self.files[key] = thaw(hash_file(path))
        return deepcopy(self.files[key])

    def save_bytes(self, name, data):
        if name != 'build-information.txt':
            raise ValueError('unexpected dependency output')
        self.build = data.decode('utf-8')
        return None


def capture_engine_sources():
    """Capture Engine and archive inputs without files, logs or thread changes.

    Return {engine, versions, build_information, files}; files are original
    five-field FileIdentity values, sorted by path. build_information is text.
    """
    from ._continuity_audit import dependencies
    window = _CaptureWindow()
    deps = dependencies(window)
    directory = Path(__file__).parent
    implementations = {str(p) for p in directory.glob('*continuity*.py')}
    implementations.add(str(directory / 'colorimetry.py'))
    files = deps['package_files']
    engine = dict(algorithm=ALGORITHM, parameters_sha256=canonical_digest(PARAMETERS),
        implementation=[_artifact(i) for i in files if i['path'] in implementations],
        dependency_fingerprint=deps['fingerprint'])
    return dict(engine=engine, versions={k: deps[k] for k in ('python', 'numpy', 'opencv')},
        build_information=window.build, files=files)


def capture_continuity_engine():
    """Return the currently installed, read-only Engine identity."""
    return capture_engine_sources()['engine']


class _ReadWindow:
    def __init__(self, deadline, audit, budget=None):
        self.deadline = deadline
        self.audit = audit
        self.budget = budget
        self.frozen = {}
        self._json_bytes = 0
        self.json_paths = set()
        self.empty_logs = set()
        self.empty_package_files = set()
        self.logger = SimpleNamespace(run_dir=audit)
        from ._continuity_storage import GeometryDecoder
        self.geometry_decoder=GeometryDecoder()
        self.packed_documents=set()
        self.final_guards=[]

    @property
    def json_bytes(self):
        return self._json_bytes

    @json_bytes.setter
    def json_bytes(self, value):
        # The original profile validator restores its active-memory counter
        # in finally. This window instead counts unique parsed bytes for the
        # whole call; an external assignment must never refund that budget.
        _int(value, 'JSON metadata bytes')
        self._json_bytes = max(self._json_bytes, value)

    def charge_json(self, path, size):
        key = str(path)
        if key in self.json_paths:
            return
        if size < 1 or size > MAX_JSON or self._json_bytes+size > MAX_METADATA:
            raise ValueError('resource_limit: JSON/metadata budget')
        if self.budget is not None:
            self.budget.charge(key, size)
        self.json_paths.add(key)
        self._json_bytes += size

    def check_time(self):
        if self.deadline is not None and monotonic() >= self.deadline:
            raise TimeoutError('continuity report verification budget expired')

    def freeze(self, path, *, package=False):
        self.check_time()
        path = _source_path(path) if package else _local_file(path)
        key = str(path)
        if key not in self.frozen:
            self.frozen[key] = thaw(hash_file(path))
        return deepcopy(self.frozen[key])

    def check(self, identity):
        _identity(identity)
        if any(identity[k] is None for k in IDENTITY_FIELDS):
            raise ValueError('complete FileIdentity required')
        actual = self.freeze(identity['path'])
        if stable(actual) != stable(identity):
            raise OSError('input identity differs: ' + identity['path'])
        return actual

    def artifact(self, value, *, empty_package=False):
        _object(value, ARTIFACT_FIELDS, 'Artifact')
        _int(value['bytes'], 'bytes', 0 if empty_package else 1)
        if type(value['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', value['sha256']):
            raise ValueError('full Artifact SHA256 required')
        actual = self.freeze(value['path'])
        if _artifact(actual) != value:
            raise OSError('artifact bytes differ: ' + value['path'])
        if empty_package and actual['bytes'] == 0:
            self.empty_package_files.add(actual['path'])
        return actual

    def read_path(self, path):
        value = self.freeze(path)
        if value['bytes'] < 1 or value['bytes'] > MAX_JSON:
            raise ValueError('resource_limit: nonempty JSON <=16MiB required')
        self.charge_json(value['path'], value['bytes'])
        # Duplicate keys and non-finite JSON values must not disappear on parse.
        def pairs(items):
            result = {}
            for key, item in items:
                if key in result:
                    raise ValueError('duplicate JSON key')
                result[key] = item
            return result
        def constant(value):
            raise ValueError('non-finite JSON number')
        parsed=json.loads(Path(value['path']).read_text(encoding='utf-8'),
            object_pairs_hook=pairs, parse_constant=constant)
        decoded=self.geometry_decoder.decode(parsed)
        if isinstance(parsed,dict) and 'continuity_storage' in parsed:
            self.packed_documents.add(value['path'])
        return decoded

    def matches_json(self,path,expected,*,packed=False):
        """Prove a derived metrics/pair duplicate, parsing only on mismatch.

        Exact producer bytes cannot contain an extra key or a different JSON
        type. They remain frozen and in the final byte closure. Alternative
        representations take the original strict parser and metadata charges.
        """
        from ._continuity_storage import iter_document_bytes,EncodedJSONLimit
        actual=self.freeze(path)
        if not 1<=actual['bytes']<=MAX_JSON:
            raise ValueError('resource_limit: nonempty JSON <=16MiB required')
        digest=hashlib.sha256();size=0;complete=False
        try:
            for part in iter_document_bytes(expected,packed=packed,maximum=MAX_JSON,check=self.check_time):
                size+=len(part);digest.update(part)
            complete=True
        except EncodedJSONLimit:pass
        self.check_time()
        if complete and size==actual['bytes'] and digest.hexdigest()==actual['sha256']:
            return True
        return _same_json(self.read_path(path),expected,self.check_time)

    def read_json(self, identity):
        self.check(identity)
        return self.read_path(identity['path'])

    def release_json(self, identity):
        # The verification budget counts distinct parsed input bytes, including
        # sequential profile artifacts; releasing a Python object grants no reset.
        pass

    def verify(self):
        for expected in self.frozen.values():
            self.check_time()
            actual = thaw(hash_file(Path(expected['path'])))
            if stable(actual) != stable(expected):
                raise OSError('closure bytes changed: ' + expected['path'])
            if actual['bytes'] == 0 and actual['path'] not in self.empty_logs | self.empty_package_files:
                raise ValueError('empty artifact is not a verified command log')
        for guard in self.final_guards:guard()


def _commands(value, window):
    """Allow empty files only when a validated original CommandResult names them."""
    from .colorimetry import COMMAND_FIELDS
    if isinstance(value, dict):
        if set(value) == set(COMMAND_FIELDS):
            _command_record(value)
            for key in ('stdout_path', 'stderr_path'):
                window.empty_logs.add(str(_local_file(value[key])))
        for child in value.values():
            _commands(child, window)
    elif isinstance(value, list):
        for child in value:
            _commands(child, window)


def _finite_tree(value):
    if isinstance(value, float):
        finite(value)
    elif isinstance(value, dict):
        for child in value.values():
            _finite_tree(child)
    elif isinstance(value, list):
        for child in value:
            _finite_tree(child)


def _expand_evidence(window, identities, package_paths,sidecars=()):
    """Follow nested original JSON identities, without trusting its top hash."""
    visited = set()
    from ._continuity_promotions import PromotionResolver
    promotions=PromotionResolver(window,sidecars)
    window.final_guards.append(promotions.verify)

    def document(path):
        key = str(path)
        if key in visited or key in package_paths or Path(path).suffix.lower() != '.json':
            return
        visited.add(key)
        value=window.read_path(path)
        _commands(value,window)
        visit(value,key)

    def visit(value,context):
        if isinstance(value, dict):
            fields = set(value)
            if fields == IDENTITY_FIELDS or fields == ARTIFACT_FIELDS:
                if value['path'] in package_paths:
                    return
                if promotions.resolve(value,context):return
                if fields == IDENTITY_FIELDS:
                    window.check(value)
                else:
                    window.artifact(value)
                document(value['path'])
            else:
                for child in value.values():
                    visit(child,context)
        elif isinstance(value, list):
            for child in value:
                visit(child,context)

    for identity in [*identities,*promotions.proofs]:
        document(identity['path'])


def _verify_dependencies(report, window, historical, expected_engine=None):
    deps = report['dependencies']
    _object(deps, 'python numpy opencv build_information package_files fingerprint'.split(), 'dependencies')
    versions = {key: deps[key] for key in ('python', 'numpy', 'opencv')}
    if any(type(v) is not str or not v for v in versions.values()):
        raise ValueError('dependency versions required')
    files = array(deps['package_files'], nonempty=True)
    keys = []
    for identity in files:
        _identity(identity)
        if any(identity[k] is None for k in IDENTITY_FIELDS):
            raise ValueError('complete dependency FileIdentity required')
        keys.append(identity['path'])
    if keys != sorted(set(keys)):
        raise ValueError('sorted unique dependency inventory required')
    build_ref = deps['build_information']
    if Path(build_ref['path']) != window.audit/'logs/continuity/build-information.txt':
        raise ValueError('build information belongs to a different audit')
    window.check(build_ref)
    build = Path(build_ref['path']).read_text(encoding='utf-8')
    fingerprint = canonical_digest(dict(**versions, build_information=build, package_files=stable(files)))
    if fingerprint != deps['fingerprint']:
        raise ValueError('dependency build fingerprint differs')
    captured = historical if historical is not None else capture_engine_sources()
    if (versions != captured['versions'] or build != captured['build_information']
            or stable(files) != stable(captured['files'])
            or fingerprint != captured['engine']['dependency_fingerprint']):
        raise OSError('engine/dependency identity differs; reassess required')
    if historical is None:
        for identity in files:
            actual = window.freeze(identity['path'], package=True)
            if stable(actual) != stable(identity):
                raise OSError('installed dependency differs')
            if identity['bytes'] == 0:
                window.empty_package_files.add(identity['path'])
    else:
        archives = historical.get('archives')
        if not isinstance(archives, dict) or set(archives) != set(keys):
            raise ValueError('complete historical archive mapping required')
        for identity in files:
            archived = window.artifact(archives[identity['path']], empty_package=identity['bytes']==0)
            if any(archived[k] != identity[k] for k in ('bytes', 'sha256')):
                raise OSError('historical engine archive bytes differ')
    engine = captured['engine']
    if expected_engine is not None and not _equal(engine,expected_engine):
        raise ValueError('report engine differs from the frozen expected engine')
    if (engine['algorithm'] != report['algorithm']
            or engine['parameters_sha256'] != report['parameters_sha256']):
        raise ValueError('report engine algorithm/parameters differ')
    return files


def _verify_frames(report, plan, records):
    from ._continuity_scores import seconds
    used = {p[k] for p in plan['comparisons'] for k in ('left', 'right')}
    expected = []
    for frame in plan['frames']:
        record = records[frame['frame_id']]
        ready = frame['frame_id'] in used and record['status'] == 'ready'
        expected.append(dict(frame_id=frame['frame_id'], record=frame['source_record'],
            source=record['source'], source_frame_index=frame['source_frame_index'],
            pts=frame['source_pts'], time_base=frame['source_time_base'], output_frame_index=frame['output_frame_index'],
            timeline_seconds=float(seconds(frame)) if frame['output_frame_index'] is not None and seconds(frame) is not None else None,
            status='ready' if ready else 'unverified', risks=record['risks']))
    if not _equal(report['frame_results'], expected):
        raise ValueError('report frames/native mapping/time/risks differ')


def _verify_pairs(report, plan, window, *, packed=False):
    pairs = array(report['comparisons'])
    if len(pairs) != len(plan['comparisons']):
        raise ValueError('comparison coverage differs')
    frames = {f['frame_id']: f for f in plan['frames']}
    statuses = {f['frame_id']: f['status'] for f in report['frame_results']}
    counts = dict(comparable=0, not_comparable=0, unverified=0)
    for index, (pair, declared) in enumerate(zip(pairs, plan['comparisons'])):
        window.check_time()
        _object(pair, 'comparison_id kind left right regions'.split(), 'comparison result')
        if any(pair[k] != declared[k] for k in ('comparison_id', 'kind', 'left', 'right')):
            raise ValueError('comparison identity/order differs')
        regions = array(pair['regions'], nonempty=True)
        if [r['region_id'] for r in regions] != declared['region_ids']:
            raise ValueError('comparison region coverage differs')
        for ri, region in enumerate(regions):
            _object(region, 'region_id comparability reasons geometry confidence confidence_kind confidence_components metrics evidence'.split(), 'region result')
            if region['comparability'] not in counts or region['confidence_kind'] != 'match_support':
                raise ValueError('unknown region comparability/confidence')
            if not 0 <= finite(region['confidence']) <= 1:
                raise ValueError('invalid match confidence')
            if any(type(reason) is not str or not reason for reason in array(region['reasons'])):
                raise ValueError('invalid comparability reason')
            if (region['comparability'] == 'comparable') != (region['metrics'] is not None):
                raise ValueError('comparability and metrics differ')
            geometry = region['geometry']
            _object(geometry, 'basis working_size candidate_points valid_points occupied_cells overlap_fraction fb_error_p90 ncc_median affine vectors sampled_pairs'.split(), 'geometry')
            for key in ('candidate_points', 'valid_points', 'occupied_cells'):
                _int(geometry[key], key)
            if region['metrics'] is not None:
                _object(region['metrics'], ('delta_lab_median delta_e_median delta_e_p90 left_luma_median right_luma_median '
                    'luma_log_ratio left_chroma_median right_chroma_median chroma_delta left_clipped_fractions '
                    'right_clipped_fractions sampled_clipped_delta').split(), 'color metrics')
            evidence = array(region['evidence'])
            expected_paths = [frames[pair[side]]['source_record']['path'] for side in ('left', 'right')]
            expected_paths += [str(window.audit/f'logs/continuity/evidence/{index:06d}_{side}_{ri:04d}.png')
                for side in ('left', 'right') if statuses[pair[side]] == 'ready']
            if [i.get('path') for i in evidence] != expected_paths:
                raise ValueError('pair evidence producer/coverage differs')
            for identity in evidence:
                window.check(identity)
            if evidence[:2] != [frames[pair[side]]['source_record'] for side in ('left', 'right')]:
                raise ValueError('pair source evidence differs')
        status_set = {r['comparability'] for r in regions}
        status = 'comparable' if 'comparable' in status_set else ('unverified' if 'unverified' in status_set else 'not_comparable')
        counts[status] += 1
        expected=dict(schema_version=1, algorithm=ALGORITHM, input_sha256=report['input_sha256'], comparison=pair)
        if not window.matches_json(window.audit/f'logs/continuity/pairs/{index:06d}.json',expected,packed=packed):
            raise ValueError('persisted pair content differs from report')
    expected = dict(requested_frames=len(plan['frames']), ready_frames=sum(f['status']=='ready' for f in report['frame_results']),
        requested_pairs=len(pairs), comparable_pairs=counts['comparable'],
        not_comparable_pairs=counts['not_comparable'], unverified_pairs=counts['unverified'])
    if report['coverage'] != expected or any(type(v) is not int for v in report['coverage'].values()):
        raise ValueError('report coverage differs')


def _detector_rows(report, frames, regions, window):
    rows = array(report['detectors'], nonempty=True)
    for row in rows:
        _object(row, 'detector_id region_id frame_ids score threshold status reasons confidence evidence'.split(), 'detector result')
        if row['detector_id'] not in DETECTORS or (row['region_id'] is not None and row['region_id'] not in regions):
            raise ValueError('unknown detector/region')
        ids = array(row['frame_ids'])
        if any(fid not in frames for fid in ids):
            raise ValueError('invalid detector frame scope')
        for key in ('score', 'threshold'):
            if row[key] is not None:
                finite(row[key])
        if not 0 <= finite(row['confidence']) <= 1:
            raise ValueError('invalid detector confidence')
        if row['status'] not in ('candidate', 'no_candidate', 'not_comparable', 'unverified'):
            raise ValueError('invalid machine detector state')
        if any(type(reason) is not str or not reason for reason in array(row['reasons'])):
            raise ValueError('invalid detector reasons')
        for identity in array(row['evidence']):
            window.check(identity)
        if row['status'] in ('candidate', 'no_candidate'):
            if row['score'] is None or row['threshold'] is None or row['reasons']:
                raise ValueError('calibrated decision requires score/threshold')
        elif row['threshold'] is not None or not row['reasons']:
            raise ValueError('abstention requires reasons and no threshold')
    if {d['detector_id'] for d in rows} != set(DETECTORS):
        raise ValueError('six detector classes required')
    return rows


def _historical_profile(report, profile, source_fps):
    """Validate sealed decision use while preserving the archived raw scores."""
    if (profile['algorithm'] != report['algorithm']
            or profile['parameters_sha256'] != report['parameters_sha256']
            or profile['dependency_fingerprint'] != report['dependencies']['fingerprint']):
        raise ValueError('historical profile engine differs')
    manifest = report['inputs']['manifest']
    applicability = profile['applicability']
    covered = (manifest['domain']['genre'] in applicability['genres']
        and manifest['domain']['source_kind'] in applicability['source_kinds']
        and bool(source_fps)
        and all(dict(num=f.numerator, den=f.denominator) in applicability['source_fps'] for f in source_fps)
        and all(p['kind'] in applicability['comparison_kinds'] for p in manifest['comparisons']))
    detectors = {d['detector_id']:d for d in profile['detectors']}
    for row in report['detectors']:
        if row['score'] is None or row['status'] == 'not_comparable':
            continue
        info = detectors[row['detector_id']]
        if not covered:
            expected = dict(threshold=None, status='unverified', reasons=['out_of_calibration_scope'])
        elif not info['enabled']:
            expected = dict(threshold=None, status='unverified', reasons=['disabled_detector', info['reason']])
        else:
            expected = dict(threshold=info['threshold'],
                status='candidate' if row['score'] > info['threshold'] else 'no_candidate', reasons=[])
        if not _equal({k:row[k] for k in expected}, expected):
            raise ValueError('historical profile decision differs from sealed threshold')
    return dict(identity=manifest['profile'], applicability=applicability, status=profile['status'],
        enabled_detectors=[d['detector_id'] for d in profile['detectors'] if d['enabled']],
        domain_match=covered, reasons=[] if covered else ['out_of_calibration_scope'])


def _verify_detectors(report, plan, reader, window, *, historical=False):
    from .continuity_analysis import _apply_profile, _native_source_fps
    from ._continuity_scores import scores, seconds
    frames = {f['frame_id']: f for f in plan['frames']}
    regions = {r['region_id']: r for r in plan['regions']}
    rows = _detector_rows(report, frames, regions, window)
    trajectories = deepcopy(array(report['trajectories']))
    if [t.get('region_id') for t in trajectories] != list(regions):
        raise ValueError('trajectory region coverage differs')
    right_pairs = {p['right']:p for p in plan['comparisons'] if p['kind'] in ('adjacent', 'parent_join')}
    for trajectory in trajectories:
        _object(trajectory, ('region_id', 'samples'), 'trajectory')
        seen = set()
        for sample in array(trajectory['samples']):
            _object(sample, ('frame_id timestamp center box image_plane_velocity camera_compensated_velocity flow_direction direction_delta '
                'camera_translation camera_rotation camera_log_scale edge_margin status confidence').split(), 'trajectory sample')
            fid = sample['frame_id']
            if fid not in frames or fid in seen:
                raise ValueError('unknown/duplicate trajectory frame')
            seen.add(fid)
            f = frames[fid]
            if sample['timestamp'] != dict(pts=f['display_pts'], time_base=f['display_time_base']):
                raise ValueError('trajectory native time differs')
            if sample['status'] not in ('anchored', 'tracking_lost', 'tracked') or not 0 <= finite(sample['confidence']) <= 1:
                raise ValueError('invalid tracking state')
            camera = [sample[k] for k in ('camera_translation', 'camera_rotation', 'camera_log_scale')]
            if any(c is not None for c in camera):
                if any(c is None for c in camera) or fid not in right_pairs:
                    raise ValueError('incomplete trajectory camera evidence')
                pair = right_pairs[fid]
                dt = float(seconds(frames[fid])-seconds(frames[pair['left']]))
                if dt <= 0:
                    raise ValueError('invalid camera interval')
                sample['_camera_velocity'] = [camera[0][0]/dt, camera[0][1]/dt, camera[1]/dt, camera[2]/dt]
    # Derive the six score classes from saved geometry/trajectories only. No
    # image provider, tracking, registration, or feature extraction is invoked.
    expected = None if historical else dict(detectors=scores(plan, report['comparisons'], trajectories, deadline=window.deadline))
    profile = None
    if report['inputs']['manifest']['profile'] is not None:
        from .continuity_calibration import _verify_profile_evidence
        reference = report['inputs']['manifest']['profile']
        value = window.read_json(reference)
        if value.get('purpose') != 'real_benchmark':
            raise ValueError('only real_benchmark profile is ordinary evidence')
        _verify_profile_evidence(value, reference, window)
        source_fps = _native_source_fps(reader.sidecars)
        profile = (_historical_profile(report, value, source_fps) if historical else
            _apply_profile(expected, value, report['inputs']['manifest'],
                dependency_fingerprint=report['dependencies']['fingerprint'], source_fps=source_fps))
    elif any(row['threshold'] is not None or row['status'] in ('candidate','no_candidate') for row in rows):
        raise ValueError('uncalibrated historical report cannot contain decisions')
    if not _equal(report['profile'], profile) or (expected is not None and not _equal(report['detectors'], expected['detectors'])):
        raise ValueError('report profile/detector scores or decisions differ')
    if {d['detector_id'] for d in report['detectors']} != set(DETECTORS):
        raise ValueError('six detector classes required')
    risks = [dict(code=code, detail=f'{p["comparison_id"]}/{r["region_id"]}', frame_ids=[p['left'], p['right']])
        for p in report['comparisons'] for r in p['regions'] for code in r['reasons']]
    if profile is None:
        risks.append(dict(code='missing_profile', detail='Raw measurement only; no calibrated decision', frame_ids=[]))
    if report['risks'] != risks:
        raise ValueError('report risks differ')


def validate_continuity_report(report_identity, manifest_identity=None, *, manifest=None, expected_engine=None,
        expected_audit_run_dir=None, historical_engine=None, timeout=300, config=None, _budget=None):
    """Verify an ordinary report and return {report, manifest, closure}.

    report and optional manifest accept a path or a three-field Artifact. The
    runtime supplies its frozen config. Historical callers must supply verified
    capture metadata plus archives mapping original paths to archived Artifacts;
    archived code is hashed as data and is never imported or executed.
    Internal callers may share one metadata/deadline budget using an object
    with charge(canonical_path, bytes) and a monotonic absolute deadline.
    """
    from .images import _deadline
    from .colorimetry import load_color_analysis_set
    from .continuity_analysis import _resolve_manifest
    report=report_identity
    if manifest_identity is not None:
        if manifest is not None and not _equal(manifest,manifest_identity):
            raise ValueError('conflicting manifest identities')
        manifest=manifest_identity
    deadline = _deadline(timeout, monotonic())
    if _budget is not None:
        shared_deadline = getattr(_budget, 'deadline', None)
        if shared_deadline is not None:
            deadline = shared_deadline if deadline is None else min(deadline, shared_deadline)
    path = _local_file(report['path'] if isinstance(report, dict) else report)
    if len(path.parents) < 4 or path.name != 'report.json' or path.parent.name != 'continuity' or path.parent.parent.name != 'logs':
        raise ValueError('original logs/continuity/report.json required')
    audit = validate_run_dir(path.parents[2])
    if expected_audit_run_dir is not None and audit != Path(_validate_spelling(str(expected_audit_run_dir))):
        raise ValueError('report producer audit differs from bound attempt')
    window = _ReadWindow(deadline, audit, _budget)
    if isinstance(report, dict):
        window.artifact(report)
    value = window.read_path(path)
    _object(value, REPORT_FIELDS, 'ordinary report')
    if type(value['schema_version']) is not int or value['schema_version'] != 1 or value['algorithm'] != ALGORITHM:
        raise ValueError('unsupported ordinary report schema/algorithm')
    _finite_tree(value)
    _timestamp(value['created_at'])
    parameter_digest = canonical_digest(value['parameters'])
    expected_parameters = (historical_engine['engine']['parameters_sha256'] if historical_engine is not None
        else canonical_digest(PARAMETERS))
    if (value['parameters_sha256'] != parameter_digest or parameter_digest != expected_parameters
            or (historical_engine is None and not _equal(value['parameters'], PARAMETERS))):
        raise ValueError('report algorithm parameters differ')
    _object(value['inputs'], ('manifest', 'files'), 'report inputs')
    data = validate_continuity_manifest(value['inputs']['manifest'])
    if manifest is not None:
        if isinstance(manifest, dict):
            window.artifact(manifest)
            supplied = window.read_path(manifest['path'])
        else:
            supplied = window.read_path(_local_file(manifest))
        if supplied != data:
            raise ValueError('report manifest differs from bound input')
    if any(value[key] != data[key] for key in ('scope', 'scene_id', 'domain')):
        raise ValueError('report manifest scope/scene/domain differs')
    packages = _verify_dependencies(value, window, historical_engine, expected_engine)
    digest = canonical_digest(dict(inputs=stable(value['inputs']), algorithm=ALGORITHM,
        parameters=value['parameters'], dependencies=value['dependencies']['fingerprint']))
    if value['input_sha256'] != digest:
        raise ValueError('canonical report input digest differs')
    if config is None:
        from ..config import load_config
        config = load_config(RUNTIME_ROOT/'projects/video-ai/config/production.json')
    record_paths = [f['record']['path'] for c in data['clips'] for f in c['frames']]
    record_paths += [f['record']['path'] for f in data['references']]
    # Only original metadata read through this window contributes to inputs.
    before_sources = set(window.frozen)
    with load_color_analysis_set(record_paths, config=config, timeout=None if deadline is None else max(.001, deadline-monotonic())) as reader:
        # Share one metadata budget with the original color reader, including
        # raw probe stdout whose filename does not end in .json.
        for key in reader._json_paths:
            window.charge_json(key, reader.frozen[key]['bytes'])
        plan, records = _resolve_manifest(data, reader, window)
        _verify_frames(value, plan, records)
        for row in reader.frames:
            _commands(row['record'], window)
        for side in reader.sidecars.values():
            _commands(side, window)
        # The color reader already verifies every source, raw frame, tool and
        # sidecar. Add its captured bytes to this final closure guard as well.
        for identity in reader.identities:
            window.check(identity)
            if Path(identity['path']).suffix.lower() == '.json':
                _commands(window.read_path(identity['path']), window)
        _verify_detectors(value, plan, reader, window, historical=historical_engine is not None)
        source_files = {i['path']:i for i in packages}
        source_files.update({i['path']:i for i in reader.identities})
        source_files.update({p:i for p,i in window.frozen.items() if p not in before_sources})
        actual_inputs = [source_files[p] for p in sorted(source_files)]
        if stable(value['inputs']['files']) != stable(actual_inputs):
            raise ValueError('report input closure identity set differs')
        packed=str(path) in window.packed_documents
        _verify_pairs(value, plan, window,packed=packed)
        expected_metrics = dict(schema_version=1, algorithm=ALGORITHM, input_sha256=digest,
            **{k:value[k] for k in ('frame_results', 'comparisons', 'trajectories', 'detectors')})
        if not window.matches_json(path.parent/'metrics.json',expected_metrics,packed=packed):
            raise ValueError('persisted metrics differ from report')
        _expand_evidence(window, actual_inputs, {i['path'] for i in packages},reader.sidecars.values())
    window.verify()
    return dict(report=deepcopy(value), manifest=deepcopy(data),
        closure=[_artifact(window.frozen[p]) for p in sorted(window.frozen)])
