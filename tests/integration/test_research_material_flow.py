"""Real CPU ordinary-pair flow; synthetic source imagery is never natural qualification."""
from copy import deepcopy
from pathlib import Path
import pytest

from test_continuity_analysis_flow import continuity_fixture


def full_manifest(manifest):
    result = deepcopy(manifest)
    result['comparisons'] = [p for p in result['comparisons'] if p['kind'] == 'adjacent']
    result['comparisons'] += [dict(comparison_id=f'reference_{i:06d}', kind='reference',
        left='reference_origin', right=f'frame_{i}', region_ids=['subject']) for i in range(8)]
    return result


def test_full_cpu_report_preserves_every_comparison_and_rejects_missing_shard(continuity_fixture):
    from video_ai.media.research_pair_report import analyze_research_pairs, validate_research_pair_report
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.logging import RunLogger
    _, kw, manifest, _, _ = continuity_fixture
    manifest = full_manifest(manifest)
    logger = RunLogger(create_run(kw['paths']))
    report, _ = analyze_research_pairs(manifest, **dict(kw, logger=logger))
    path = logger.root / 'continuity/report.json'
    verified = validate_research_pair_report(path, manifest=manifest, config=kw['config'])
    assert verified['report'] == report
    assert len(report['comparisons']) == 15
    assert report['coverage']['requested_frames'] == 9
    assert report['production_eligible'] is False
    assert report['profile'] is None
    Path(report['comparisons'][0]['parts'][0]['path']).unlink()
    with pytest.raises((ValueError, OSError)):
        validate_research_pair_report(path, manifest=manifest, config=kw['config'])


def test_incomplete_reference_coverage_refused(continuity_fixture):
    from video_ai.media.research_pair_report import analyze_research_pairs
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.logging import RunLogger
    _, kw, manifest, _, _ = continuity_fixture
    manifest = full_manifest(manifest)
    manifest['comparisons'].pop()
    with pytest.raises(ValueError, match='coverage'):
        analyze_research_pairs(manifest, **dict(kw, logger=RunLogger(create_run(kw['paths']))))


def test_natural_baseline_covers_every_frame_without_qualification(continuity_fixture):
    from video_ai.media.research_pair_report import analyze_research_pairs
    from video_ai.runtime.research_material_baseline import measure_natural_manifest
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.logging import RunLogger
    _, kw, manifest, _, _ = continuity_fixture
    manifest = full_manifest(manifest)
    logger = RunLogger(create_run(kw['paths']))
    analyze_research_pairs(manifest, **dict(kw, logger=logger))
    from scene_continuity_helpers import artifact
    measured = measure_natural_manifest(manifest, artifact(logger.root/'continuity/report.json'), config=kw['config'])
    assert len(measured['frames']) == 8
    assert measured['thresholds'] is None
    assert measured['operation'] is None
    assert measured['ready_for_propose'] is False


def test_interrupted_shard_write_resumes_without_overwriting_evidence(continuity_fixture, monkeypatch):
    import video_ai.media.research_pair_report as module
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.logging import RunLogger
    _, kw, manifest, _, _ = continuity_fixture
    manifest = full_manifest(manifest)
    logger = RunLogger(create_run(kw['paths']))
    original = module.write_comparison
    retained = []
    def interrupt(folder, sequence, comparison, **kwargs):
        row = original(folder, sequence, comparison, **kwargs)
        retained.append(row)
        raise OSError('fault injected after real shard creation')
    monkeypatch.setattr(module, 'write_comparison', interrupt)
    with pytest.raises(OSError, match='fault injected'):
        module.analyze_research_pairs(manifest, **dict(kw, logger=logger))
    part = Path(retained[0]['parts'][0]['path'])
    before = part.stat().st_mtime_ns, part.read_bytes()
    monkeypatch.setattr(module, 'write_comparison', original)
    module.analyze_research_pairs(manifest, **dict(kw, logger=logger))
    assert (part.stat().st_mtime_ns, part.read_bytes()) == before
    module.validate_research_pair_report(logger.root/'continuity/report.json', manifest=manifest, config=kw['config'])
