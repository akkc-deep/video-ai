"""Ordinary audit closure validation; synthetic media conveys no quality verdict."""
from copy import deepcopy
import importlib
import importlib.util
import json
import os
from pathlib import Path

import pytest


def module():
    assert importlib.util.find_spec('video_ai.media.continuity_report') is not None, 'readonly continuity report verifier missing'
    return importlib.import_module('video_ai.media.continuity_report')


def artifact(path):
    from video_ai.runtime.manifest import hash_file, thaw
    value = thaw(hash_file(Path(path)))
    return {key: value[key] for key in ('path', 'bytes', 'sha256')}


@pytest.fixture(scope='module')
def ordinary_report():
    from video_ai.config import load_config
    from video_ai.runtime.paths import RuntimePaths, create_run
    from video_ai.runtime.logging import RunLogger
    from video_ai.media.continuity_analysis import analyze_continuity
    # Reuse genuine tiny VCO-02 records, commands, native PTS and raw pixels.
    helper_path = Path(__file__).parents[1] / 'integration/test_continuity_analysis_flow.py'
    spec = importlib.util.spec_from_file_location('vco04_report_fixture', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    config = load_config(Path(__file__).parents[2] / 'config/production.example.json')
    paths = RuntimePaths.from_config(config)
    fixture = helper._make_continuity_fixture((create_run(paths), config, paths))
    run, kw, manifest, records, sidecar = fixture
    logger = RunLogger(create_run(paths))
    report, _ = analyze_continuity(manifest, **dict(kw, logger=logger))
    path = logger.root / 'continuity/report.json'
    manifest_path = run / 'ordinary-manifest.json'
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    return dict(report=report, path=path, manifest=manifest_path, run=run,
                audit=logger.run_dir, config=kw['config'], records=records,
                source=Path(sidecar['source']['path']), helper=helper)


def test_engine_capture_is_readonly_and_matches_dependency_definition(runtime_run):
    m = module()
    import cv2
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.media._continuity_schema import PARAMETERS
    run = runtime_run[0]
    before = set(run.rglob('*'))
    threads = cv2.getNumThreads()
    sources = m.capture_engine_sources()
    engine = sources['engine']
    assert set(engine) == {'algorithm', 'parameters_sha256', 'implementation', 'dependency_fingerprint'}
    assert engine['algorithm'] == 'continuity_cv_v1'
    assert engine['parameters_sha256'] == canonical_digest(PARAMETERS)
    assert engine == m.capture_continuity_engine()
    assert {Path(i['path']).name for i in engine['implementation']} >= {
        'continuity_analysis.py', '_continuity_schema.py', '_continuity_geometry.py',
        '_continuity_scores.py', '_continuity_audit.py', 'colorimetry.py', 'continuity_report.py'}
    assert all(set(i) == {'path', 'bytes', 'sha256'} for i in engine['implementation'])
    assert all(set(i) == {'path', 'bytes', 'mtime_ns', 'sha256', 'verified_at'} for i in sources['files'])
    assert [i['path'] for i in sources['files']] == sorted(set(i['path'] for i in sources['files']))
    assert engine['dependency_fingerprint'] == canonical_digest(dict(
        **sources['versions'], build_information=sources['build_information'],
        package_files=__import__('video_ai.media._continuity_schema', fromlist=['stable']).stable(sources['files'])))
    assert cv2.getNumThreads() == threads and set(run.rglob('*')) == before


def test_complete_report_has_readonly_deep_closure(ordinary_report, monkeypatch):
    m = module(); f = ordinary_report
    import video_ai.media.continuity_analysis as analyzer
    def forbidden(*args, **kwargs):
        raise AssertionError('readonly verification must not remeasure or execute commands')
    monkeypatch.setattr(analyzer, 'measure_continuity', forbidden)
    import video_ai.runtime.processes as processes
    monkeypatch.setattr(processes, 'run_logged', forbidden)
    roots = (f['run'], f['audit'])
    before = [f['helper'].snapshot(root) for root in roots]
    result = m.validate_continuity_report(artifact(f['path']), manifest=artifact(f['manifest']),
        expected_audit_run_dir=f['audit'], config=f['config'])
    assert result['report'] == f['report']
    assert result['manifest'] == f['report']['inputs']['manifest']
    closure = result['closure']; paths = [i['path'] for i in closure]
    assert paths == sorted(set(paths))
    assert all(set(i) == {'path', 'bytes', 'sha256'} for i in closure)
    for p in (f['path'], f['manifest'], f['source'], Path(f['records'][0]['path']),
              f['path'].parent/'metrics.json', f['path'].parent/'pairs/000000.json',
              f['path'].parent/'build-information.txt'):
        assert str(p) in paths
    assert any(p.endswith('.rgb') for p in paths) and any(p.endswith('.png') for p in paths)
    assert [f['helper'].snapshot(root) for root in roots] == before


def test_packed_measurement_keeps_logical_report_and_original_evidence(ordinary_report,monkeypatch):
    from video_ai.media import _continuity_storage as storage
    from video_ai.media.continuity_analysis import analyze_continuity
    from video_ai.runtime.paths import RuntimePaths,create_run
    from video_ai.runtime.logging import RunLogger
    f=ordinary_report;old=f['path'].read_bytes()
    monkeypatch.setattr(storage,'PACK_THRESHOLD',1)
    paths=RuntimePaths.from_config(f['config']);logger=RunLogger(create_run(paths))
    logical,_=analyze_continuity(f['report']['inputs']['manifest'],config=f['config'],paths=paths,logger=logger)
    report=logger.root/'continuity/report.json'
    for path in (report,report.parent/'metrics.json',report.parent/'pairs/000000.json'):
        stored=json.loads(path.read_text(encoding='utf-8'))
        assert stored['schema_version']==2 and stored['continuity_storage']==storage.MODE
    verified=module().validate_continuity_report(artifact(report),manifest=artifact(f['manifest']),
        expected_audit_run_dir=logger.run_dir,config=f['config'])
    assert verified['report']==logical and f['path'].read_bytes()==old
    original=report.read_bytes();stored=json.loads(original)
    block=next(r['geometry']['sampled_pairs'] for p in stored['comparisons'] for r in p['regions']
        if isinstance(r['geometry']['sampled_pairs'],dict))
    block['sha256']='0'*64
    try:
        report.write_text(json.dumps(stored),encoding='utf-8')
        with pytest.raises(ValueError,match='geometry'):
            module().validate_continuity_report(artifact(report),config=f['config'])
    finally:report.write_bytes(original)


def test_documented_report_api_binds_positional_manifest_and_expected_engine(ordinary_report):
    m=module();f=ordinary_report;engine=m.capture_continuity_engine()
    result=m.validate_continuity_report(artifact(f['path']),artifact(f['manifest']),
        config=f['config'],expected_engine=engine)
    assert result['report']==f['report']
    with pytest.raises(ValueError):
        m.validate_continuity_report(artifact(f['path']),artifact(f['manifest']),
            config=f['config'],expected_engine=dict(engine,parameters_sha256='0'*64))


def test_report_rejects_tampered_outputs_even_when_report_hash_is_current(ordinary_report):
    m = module(); f = ordinary_report
    changes = [
        lambda r: r.update(scene_id='other_scene'),
        lambda r: r.update(extra='unknown'),
        lambda r: r.update(schema_version=True),
        lambda r: r['coverage'].update(ready_frames=0),
        lambda r: r['frame_results'][0].update(pts=999),
        lambda r: r['comparisons'][0].update(kind='reference'),
        lambda r: r['detectors'][0].update(status='passed'),
        lambda r: r['dependencies'].update(fingerprint='0'*64),
        lambda r: r['inputs']['manifest'].update(purpose='benchmark_control'),
        lambda r: r.update(profile={'purpose':'fixture_only'}),
    ]
    original = f['path'].read_bytes()
    try:
        for change in changes:
            value = deepcopy(f['report']); change(value)
            f['path'].write_text(json.dumps(value), encoding='utf-8')
            with pytest.raises((ValueError, OSError)):
                m.validate_continuity_report(f['path'], expected_audit_run_dir=f['audit'], config=f['config'])
    finally:
        f['path'].write_bytes(original)


def test_report_rejects_missing_or_changed_pair_and_evidence(ordinary_report):
    m = module(); f = ordinary_report
    pair = f['path'].parent/'pairs/000000.json'
    image = next((f['path'].parent/'evidence').glob('*.png'))
    for path in (pair, image):
        original = path.read_bytes(); stat = path.stat()
        try:
            damaged = bytearray(original); damaged[-2] ^= 1
            path.write_bytes(damaged); os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            with pytest.raises((ValueError, OSError)):
                m.validate_continuity_report(f['path'], config=f['config'])
        finally:
            path.write_bytes(original); os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    backup = pair.with_suffix('.saved'); pair.rename(backup)
    try:
        with pytest.raises((ValueError, OSError)):
            m.validate_continuity_report(f['path'], config=f['config'])
    finally:
        backup.rename(pair)


def test_report_rejects_same_size_mtime_source_drift_and_foreign_producer(ordinary_report):
    m = module(); f = ordinary_report
    source = f['source']; original = source.read_bytes(); stat = source.stat()
    try:
        damaged = bytearray(original); damaged[-1] ^= 1
        source.write_bytes(damaged); os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        with pytest.raises((ValueError, OSError)):
            m.validate_continuity_report(f['path'], config=f['config'])
    finally:
        source.write_bytes(original); os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises((ValueError, OSError)):
        m.validate_continuity_report(f['path'], expected_audit_run_dir=f['run'], config=f['config'])
    with pytest.raises((ValueError, OSError)):
        m.validate_continuity_report(f['path'], manifest=artifact(f['records'][0]['path']), config=f['config'])


def test_report_deadline_and_identity_rejections(ordinary_report):
    m = module(); f = ordinary_report
    with pytest.raises((ValueError, TimeoutError)):
        m.validate_continuity_report(f['path'], timeout=0, config=f['config'])
    wrong = artifact(f['path']); wrong['sha256'] = '0'*64
    with pytest.raises((ValueError, OSError)):
        m.validate_continuity_report(wrong, config=f['config'])
    with pytest.raises((ValueError, OSError)):
        m.validate_continuity_report(dict(wrong, mtime_ns=0), config=f['config'])


def test_historical_report_uses_archived_sources_without_current_capture(ordinary_report, monkeypatch):
    m = module(); f = ordinary_report
    from video_ai.runtime.paths import RUNTIME_ROOT
    deps = f['report']['dependencies']
    folder = f['run']/'historical-engine'; folder.mkdir(exist_ok=True)
    archives = {}
    for index, identity in enumerate(deps['package_files']):
        original = Path(identity['path'])
        # Package records already live in D:/VideoSi; copy repository sources
        # away from installation so archive lookup is exercised independently.
        target = original
        if not original.is_relative_to(RUNTIME_ROOT):
            target = folder/f'{index:06d}.py'
            target.write_bytes(original.read_bytes())
        archives[identity['path']] = artifact(target)
    history = dict(engine=dict(algorithm='continuity_cv_v1',
        parameters_sha256=f['report']['parameters_sha256'], implementation=[],
        dependency_fingerprint=deps['fingerprint']), versions={k:deps[k] for k in ('python','numpy','opencv')},
        build_information=(f['path'].parent/'build-information.txt').read_text(encoding='utf-8'),
        files=deps['package_files'], archives=archives)
    def forbidden():
        raise AssertionError('historical evidence must not recapture the installation')
    monkeypatch.setattr(m, 'capture_engine_sources', forbidden)
    result = m.validate_continuity_report(f['path'], historical_engine=history, config=f['config'])
    assert result['report'] == f['report']
    assert any(Path(i['path']).parent == folder for i in result['closure'])
    # Historical bytes stay readable after current parameter/score semantics
    # change. Current admission must reject that same stale report.
    changed = deepcopy(m.PARAMETERS); changed['windows']['minimum_pairs'] = 999
    monkeypatch.setattr(m, 'PARAMETERS', changed)
    import video_ai.media._continuity_scores as score_module
    def changed_scores(*args, **kwargs):
        raise AssertionError('historical verification cannot execute current scoring')
    monkeypatch.setattr(score_module, 'scores', changed_scores)
    assert m.validate_continuity_report(f['path'], historical_engine=history, config=f['config'])['report'] == f['report']
    with pytest.raises((ValueError, OSError)):
        m.validate_continuity_report(f['path'], config=f['config'])


def test_context_nested_identity_is_in_closure_and_rechecked(ordinary_report):
    m = module(); f = ordinary_report
    from video_ai.runtime.manifest import hash_file, thaw, now
    from video_ai.runtime.paths import create_run, RuntimePaths
    from video_ai.runtime.logging import RunLogger
    from video_ai.media.continuity_analysis import analyze_continuity
    leaf = f['run']/'context-leaf.txt'; leaf.write_text('authored supporting evidence', encoding='utf-8')
    nested = f['run']/'context-proof.json'
    nested.write_text(json.dumps(dict(source=thaw(hash_file(leaf)))), encoding='utf-8')
    context = f['run']/'nested-context.json'
    context.write_text(json.dumps(dict(schema_version=1, author='fixture_only', reviewed_at=now(), events=[
        dict(event_id='authored_change', kind='lighting', frame_ids=['frame_7'], region_ids=['subject'],
             detector_ids=['local_color'], description='Explicit software fixture declaration',
             references=[thaw(hash_file(nested))])])), encoding='utf-8')
    manifest = deepcopy(f['report']['inputs']['manifest']); manifest['context'] = thaw(hash_file(context))
    paths = RuntimePaths.from_config(f['config']); logger = RunLogger(create_run(paths))
    analyze_continuity(manifest, config=f['config'], paths=paths, logger=logger)
    report = logger.root/'continuity/report.json'
    checked = m.validate_continuity_report(report, config=f['config'])
    assert str(leaf) in {i['path'] for i in checked['closure']}
    stat = leaf.stat(); original = leaf.read_bytes()
    try:
        leaf.write_bytes(b'X' + original[1:]); os.utime(leaf, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        with pytest.raises((ValueError, OSError)):
            m.validate_continuity_report(report, config=f['config'])
    finally:
        leaf.write_bytes(original); os.utime(leaf, ns=(stat.st_atime_ns, stat.st_mtime_ns))


def test_profile_validation_cannot_refund_unique_json_budget(runtime_run, monkeypatch):
    m = module()
    from time import monotonic
    from video_ai.runtime.manifest import hash_file, thaw
    import video_ai.media.continuity_calibration as calibration
    run = runtime_run[0]
    first = run/'first.json'; first.write_bytes(b'{}')
    second = run/'second.json'; second.write_bytes(b'{}')
    window = m._ReadWindow(monotonic()+30, run)
    monkeypatch.setattr(m, 'MAX_METADATA', 3)
    # Exercise the real profile wrapper's finally assignment without creating
    # a sealed benchmark corpus merely to test its accounting side effect.
    def read_profile_metadata(profile, identity, active_window):
        return active_window.read_json(thaw(hash_file(first)))
    monkeypatch.setattr(calibration, '_verify_profile_records', read_profile_metadata)
    calibration._verify_profile_evidence({}, {}, window)
    assert window.json_bytes == 2
    with pytest.raises(ValueError, match='resource_limit'):
        window.read_path(second)


def test_distinct_report_validations_share_one_metadata_budget(runtime_run):
    m = module()
    from time import monotonic
    from video_ai.runtime.paths import create_run
    paths = runtime_run[2]
    class SharedBudget:
        def __init__(self):
            self.deadline = monotonic()+30
            self.paths = set()
            self.bytes = 0
        def charge(self, path, size):
            if str(path) in self.paths:
                return
            if self.bytes+size > 3:
                raise ValueError('resource_limit: shared metadata budget')
            self.paths.add(str(path)); self.bytes += size
    budget = SharedBudget()
    reports = []
    for _ in range(2):
        audit = create_run(paths)
        report = audit/'logs/continuity/report.json'
        report.parent.mkdir(parents=True)
        report.write_bytes(b'{}')
        reports.append(report)
    # The report is deliberately structurally incomplete. Parsing it still
    # consumes the call-wide budget before the schema rejection is reported.
    with pytest.raises(ValueError, match='ordinary report'):
        m.validate_continuity_report(reports[0], _budget=budget)
    assert budget.bytes == 2
    with pytest.raises(ValueError, match='resource_limit: shared'):
        m.validate_continuity_report(reports[1], _budget=budget)
    assert budget.bytes == 2
    with pytest.raises(ValueError, match='ordinary report'):
        m.validate_continuity_report(reports[0], _budget=budget)
    budget.deadline = monotonic()-1
    with pytest.raises(TimeoutError):
        m.validate_continuity_report(reports[0], _budget=budget)
