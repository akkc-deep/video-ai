"""Tiny genuine CPU evidence with synthetic fixture-only playback declarations."""
import importlib
import importlib.util
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

import pytest

from scene_continuity_helpers import (analysis_request, artifact, manifest_for,
    review_request, save, snapshot, tiny_scene_context)


def runtime_module():
    assert importlib.util.find_spec('video_ai.runtime.production_scene_continuity') is not None, (
        'explicit local continuity analysis/review transactions missing')
    return importlib.import_module('video_ai.runtime.production_scene_continuity')


def test_public_local_analysis_and_review_transactions_exist():
    module = runtime_module()
    assert callable(module.analyze_scene_continuity)
    assert callable(module.reassess_scene_continuity)
    assert callable(module.consume_scene_continuity_review)


@pytest.fixture
def tiny_scene(runtime_run, monkeypatch):
    return tiny_scene_context(runtime_run, monkeypatch)


def initialize(setup, module):
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.scene_continuity_records import load_scene_continuity_progress
    with RunLock(setup['run']) as lock:
        module.ensure_initial_epoch(setup['frozen'], setup['units'], setup['timeline'],
            paths=setup['paths'], logger=setup['logger'], lock=lock)
    progress = load_scene_continuity_progress(setup['frozen'], setup['units'], setup['timeline'])
    assert progress['current_epoch'] is not None, progress
    return progress['current_epoch']


def analyze(setup, module, request):
    from video_ai.runtime.production_state import RunLock
    with RunLock(setup['run']) as lock:
        return module.analyze_scene_continuity(setup['frozen'], setup['units'], setup['timeline'], request,
            paths=setup['paths'], logger=setup['logger'], lock=lock)


def consume(setup, module, request):
    from video_ai.runtime.production_state import RunLock
    with RunLock(setup['run']) as lock:
        return module.consume_scene_continuity_review(setup['frozen'], setup['units'], setup['timeline'], request,
            paths=setup['paths'], logger=setup['logger'], lock=lock)


def test_real_tiny_frames_to_report_and_explicit_fixture_review(tiny_scene, monkeypatch):
    from video_ai.runtime.scene_continuity_records import (load_scene_continuity_progress,
        require_scene_continuity_acceptance)
    module = runtime_module()
    setup = tiny_scene
    epoch = initialize(setup, module)
    original_media = snapshot(setup['run']/'production/scene-clips')
    # The evidence is 3 x 2 retained native frames and one independent reference,
    # with explicit SDR metadata. No production quality claim is made.
    assert len(setup['all_frames']) == 3
    assert [len(row['frames']) for row in setup['all_frames']] == [2, 2, 2]
    for sidecar in setup['sidecars']:
        assert sidecar['probe']['video']['width'] == 64
        assert sidecar['probe']['video']['height'] == 36
    assessments = []
    for count in (1, 2, 3):
        request = analysis_request(setup, epoch, count=count)
        result = analyze(setup, module, request)
        assert result.status == 'awaiting_review', result.error
        aid = json.loads(request.read_text(encoding='utf-8'))['assessment_id']
        assessment_path = setup['run']/f'production/scene-continuity/jobs/{aid}/assessment.json'
        assessment = json.loads(assessment_path.read_text(encoding='utf-8'))
        report = json.loads(Path(assessment['report']['path']).read_text(encoding='utf-8'))
        assert report['coverage']['requested_frames'] == count*2+1
        assert report['profile'] is None
        assert all(row['status'] != 'passed' for row in report['detectors'])
        assert assessment['concerns'], 'unprofiled machine concerns must await an explicit response'
        progress = load_scene_continuity_progress(setup['frozen'], setup['units'], setup['timeline'])
        assert progress['clips'][count-1]['state'] == 'awaiting_review'
        assert progress['ready'] is False
        review = review_request(setup, assessment_path)
        outcome = consume(setup, module, review)
        assert outcome.status in ('awaiting_continuity_review', 'source_clips_ready'), outcome.error
        if count == 3:
            prefix = json.loads(review.read_text(encoding='utf-8'))['prefix_observation']
            archived = setup['run']/f"production/scene-continuity/prefix-observations/{prefix['sha256']}.json"
            assert archived.is_file(), 'exact original PrefixObservation bytes must be preserved'
            assert archived.read_bytes() == Path(prefix['path']).read_bytes()
        assessments.append(artifact(assessment_path))
    progress = require_scene_continuity_acceptance(setup['frozen'], setup['units'], setup['timeline'])
    assert progress['ready'] is True
    assert [row['assessment'] for row in progress['clips']] == assessments
    assert snapshot(setup['run']/'production/scene-clips') == original_media
    # The report remains machine evidence after readiness; synthetic review does
    # not rewrite its uncalibrated detector states to passed.
    assert all(row['status'] != 'passed' for row in json.loads(
        Path(assessment['report']['path']).read_text(encoding='utf-8'))['detectors'])
    before = snapshot(setup['run'])
    def forbidden(*args, **kwargs):
        raise AssertionError('readonly status must not decode, remeasure, or write')
    monkeypatch.setattr('video_ai.media.continuity_analysis.analyze_continuity', forbidden)
    monkeypatch.setattr('video_ai.media.colorimetry.decode_analysis_frame', forbidden)
    assert load_scene_continuity_progress(setup['frozen'], setup['units'], setup['timeline'])['ready'] is True
    assert snapshot(setup['run']) == before


def test_manifest_binding_rejects_incomplete_frames_wrong_join_and_reference(tiny_scene):
    from video_ai.runtime.scene_continuity_records import _binding, validate_manifest_binding
    from video_ai.runtime.manifest import hash_file, thaw
    setup = tiny_scene
    context = setup['context'](setup['frozen'], setup['units'], setup['timeline'])
    binding = _binding(context, setup['records'], setup['rows'][-1]['budget']['clip_id'])
    original = manifest_for(setup)
    validate_manifest_binding(original, binding, config=setup['config'])
    for fault in ('missing_frame', 'wrong_join', 'missing_reference_pair', 'wrong_timeline', 'captured', 'missing_reference_roi'):
        manifest = deepcopy(original)
        if fault == 'missing_frame':
            manifest['clips'][-1]['frames'].pop()
        elif fault == 'wrong_join':
            join = next(row for row in manifest['comparisons'] if row['kind'] == 'parent_join')
            join['left'] = manifest['clips'][0]['frames'][0]['frame_id']
        elif fault == 'missing_reference_pair':
            manifest['comparisons'] = [row for row in manifest['comparisons']
                if not (row['kind'] == 'reference' and row['right'] == 'clip_2_frame_1')]
        elif fault == 'wrong_timeline':
            manifest['timeline']['fps_num'] = 24
        elif fault == 'captured':
            manifest['domain']['source_kind'] = 'captured'
        else:
            regions = json.loads(Path(manifest['regions']['path']).read_text(encoding='utf-8'))
            reference_path = manifest['references'][0]['record']['path']
            for region in regions['regions']:
                region['anchors'] = [a for a in region['anchors'] if a['frame']['path'] != reference_path]
            region_file = setup['run']/'fixture_only-missing-reference-roi.json'
            region_file.write_text(json.dumps(regions), encoding='utf-8')
            manifest['regions'] = thaw(hash_file(region_file))
        with pytest.raises(ValueError):
            validate_manifest_binding(manifest, binding, config=setup['config'])


def test_three_clip_prefix_requires_same_author_and_all_risk_responses(tiny_scene):
    from video_ai.runtime.scene_continuity_records import load_scene_continuity_progress
    module = runtime_module()
    setup = tiny_scene
    epoch = initialize(setup, module)
    request = analysis_request(setup, epoch)
    result = analyze(setup, module, request)
    assert result.status == 'awaiting_review', result.error
    aid = json.loads(request.read_text(encoding='utf-8'))['assessment_id']
    assessment = setup['run']/f'production/scene-continuity/jobs/{aid}/assessment.json'
    for kwargs in (dict(prefix_author='fixture_only different author'), dict(omit_response=True)):
        rejected = consume(setup, module, review_request(setup, assessment, **kwargs))
        assert rejected.status == 'blocked', rejected.error
        progress = load_scene_continuity_progress(setup['frozen'], setup['units'], setup['timeline'])
        assert progress['clips'][-1]['state'] == 'awaiting_review'
        assert progress['ready'] is False
    waiting = consume(setup, module, review_request(setup, assessment, disposition='unverified'))
    assert waiting.status == 'awaiting_continuity_review', waiting.error
    assert not (assessment.parent.parent.parent/'reviews'/aid/'receipt.json').exists()
    progress = load_scene_continuity_progress(setup['frozen'], setup['units'], setup['timeline'])
    assert progress['clips'][-1]['state'] == 'awaiting_review'


def test_explicit_recovery_keeps_single_analysis_and_same_author_bytes(tiny_scene, monkeypatch):
    import video_ai.media.continuity_analysis as analyzer
    module = runtime_module()
    setup = tiny_scene
    epoch = initialize(setup, module)
    request = analysis_request(setup, epoch)
    aid = json.loads(request.read_text(encoding='utf-8'))['assessment_id']
    folder = setup['run']/f'production/scene-continuity/jobs/{aid}'
    media_before = snapshot(setup['run']/'production/scene-clips')
    calls = []
    actual_analyze = analyzer.analyze_continuity
    def measured(*args, **kwargs):
        calls.append(1)
        return actual_analyze(*args, **kwargs)
    monkeypatch.setattr(analyzer, 'analyze_continuity', measured)
    target = [None]
    def interrupt(point):
        if point == target[0]:
            raise KeyboardInterrupt('fixture_only interruption at '+point)
    monkeypatch.setattr(module, 'boundary', interrupt)
    for point in ('job-intent', 'attempt-intent', 'analysis-report', 'attempt-terminal', 'assessment'):
        target[0] = point
        result = analyze(setup, module, request)
        assert result.status == 'interrupted', (point, result.error)
    target[0] = None
    result = analyze(setup, module, request)
    assert result.status == 'awaiting_review', result.error
    assert (folder/'review-template.json').is_file(), 'resume must restore template after durable assessment'
    assert calls == [1], 'complete report/terminal/assessment recovery must not measure again'
    assert snapshot(setup['run']/'production/scene-clips') == media_before
    review = review_request(setup, folder/'assessment.json')
    original_review = review.read_bytes()
    for point in ('review-original', 'review-receipt'):
        target[0] = point
        result = consume(setup, module, review)
        assert result.status == 'interrupted', (point, result.error)
    target[0] = None
    result = consume(setup, module, review)
    assert result.status == 'awaiting_continuity_review', result.error
    assert review.read_bytes() == original_review
    stored = list((setup['run']/'production/scene-continuity/reviews').glob('*.json'))
    assert len(stored) == 1 and stored[0].read_bytes() == original_review
    before = snapshot(setup['run']/'production/scene-continuity')
    assert consume(setup, module, review).status == 'awaiting_continuity_review'
    assert snapshot(setup['run']/'production/scene-continuity') == before
    assert calls == [1]


def test_confirmed_raw_defect_survives_ready_receipt_and_same_media_reassessment(tiny_scene):
    from video_ai.runtime.manifest import now
    from video_ai.runtime.production_state import RunLock, ProductionRefused
    from video_ai.runtime.scene_continuity_records import (load_scene_continuity_progress,
        require_scene_continuity_acceptance)
    module = runtime_module()
    setup = tiny_scene
    epoch = initialize(setup, module)
    request_path = analysis_request(setup, epoch, count=1)
    request = json.loads(request_path.read_text(encoding='utf-8'))
    media_before = snapshot(setup['run']/'production/scene-clips')
    result = analyze(setup, module, request_path)
    assert result.status == 'awaiting_review', result.error
    assessment = Path(result.assessment['path'])
    review = review_request(setup, assessment)
    assert consume(setup, module, review).status == 'awaiting_continuity_review'
    cid = request['clip_id']
    assert require_scene_continuity_acceptance(setup['frozen'], setup['units'], setup['timeline'],
        clip_id=cid)['clips'][0]['state'] == 'ready_for_next_stage'
    receipt = setup['run']/f"production/scene-continuity/reviews/{request['assessment_id']}/receipt.json"
    ready_bytes = receipt.read_bytes()
    issue_review = review_request(setup, assessment, disposition='confirmed_issue')
    consume(setup, module, issue_review)
    assert receipt.read_bytes() == ready_bytes, 'later defect must retain the original ready receipt'
    progress = load_scene_continuity_progress(setup['frozen'], setup['units'], setup['timeline'])
    assert progress['clips'][0]['state'] == 'blocked'
    with pytest.raises(ProductionRefused):
        require_scene_continuity_acceptance(setup['frozen'], setup['units'], setup['timeline'], clip_id=cid)
    reassess = save(setup['run']/'fixture_only-defect-reassess.json', dict(schema_version=1,
        run_id=setup['run'].name, epoch_id=str(uuid4()), previous_commit=epoch,
        reason='fixture_only explicit diagnostic reassessment of same media', requested_at=now()))
    with RunLock(setup['run']) as lock:
        newer = module.reassess_scene_continuity(setup['frozen'], setup['units'], setup['timeline'], reassess,
            paths=setup['paths'], logger=setup['logger'], lock=lock)
    assert newer.status == 'awaiting_analysis', newer.error
    # Reuse the original frozen manifest and ROI bytes. Rebuilding a fixture
    # manifest would rewrite its region file and invalidate previous evidence.
    next_request = dict(request, assessment_id=str(uuid4()), epoch=newer.epoch)
    next_path = save(setup['run']/'fixture_only-same-media-request.json', next_request)
    result = analyze(setup, module, next_path)
    assert result.status == 'awaiting_review', result.error
    progress = load_scene_continuity_progress(setup['frozen'], setup['units'], setup['timeline'])
    assert progress['clips'][0]['state'] == 'blocked', 'same-media historical defect must survive new epoch'
    assert snapshot(setup['run']/'production/scene-clips') == media_before
    assert receipt.read_bytes() == ready_bytes


def test_partial_audit_resume_preserves_first_attempt_and_rejects_two_successes(tiny_scene, monkeypatch):
    import video_ai.media.continuity_analysis as analyzer
    from video_ai.runtime.manifest import now
    from video_ai.runtime.production_state import RunLock, ProductionRefused
    from video_ai.runtime.scene_continuity_records import load_scene_continuity_progress
    module = runtime_module()
    setup = tiny_scene
    epoch = initialize(setup, module)
    request = analysis_request(setup, epoch, count=1)
    aid = json.loads(request.read_text(encoding='utf-8'))['assessment_id']
    folder = setup['run']/f'production/scene-continuity/jobs/{aid}'
    actual = analyzer.analyze_continuity
    calls, partial = [], []
    def first_partial(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            path = save(kwargs['logger'].root/'continuity/fixture_only-partial.json', {'fixture_only': True})
            partial.append((path, path.read_bytes()))
            raise KeyboardInterrupt('fixture_only partial audit before complete report')
        return actual(*args, **kwargs)
    monkeypatch.setattr(analyzer, 'analyze_continuity', first_partial)
    assert analyze(setup, module, request).status == 'interrupted'
    result = analyze(setup, module, request)
    assert result.status == 'awaiting_review', result.error
    assert calls == [1, 1], 'one interrupted call plus exactly one complete measurement'
    attempts = sorted((folder/'attempts').glob('*/intent.json'))
    assert len(attempts) == 2
    terminals = [json.loads((p.parent/'terminal.json').read_text(encoding='utf-8')) for p in attempts]
    assert sorted(t['status'] for t in terminals) == ['completed', 'interrupted']
    assert partial[0][0].read_bytes() == partial[0][1]
    successful = next(p for p, terminal in zip(attempts, terminals) if terminal['status'] == 'completed')
    intent = json.loads(successful.read_text(encoding='utf-8'))
    terminal = json.loads((successful.parent/'terminal.json').read_text(encoding='utf-8'))
    second_id = str(uuid4())
    duplicate = folder/'attempts'/second_id
    with RunLock(setup['run']):
        save(duplicate/'intent.json', dict(intent, attempt_id=second_id, created_at=now()))
        save(duplicate/'terminal.json', dict(terminal, attempt_id=second_id, finished_at=now()))
    with pytest.raises(ProductionRefused):
        load_scene_continuity_progress(setup['frozen'], setup['units'], setup['timeline'])
    assert partial[0][0].read_bytes() == partial[0][1]


def test_partial_local_attempts_are_bounded_and_fourth_does_not_measure(tiny_scene, monkeypatch):
    import video_ai.media.continuity_analysis as analyzer
    module = runtime_module()
    setup = tiny_scene
    epoch = initialize(setup, module)
    request = analysis_request(setup, epoch, count=1)
    aid = json.loads(request.read_text(encoding='utf-8'))['assessment_id']
    folder = setup['run']/f'production/scene-continuity/jobs/{aid}'
    calls, partial = [], []
    def interrupted(*args, **kwargs):
        calls.append(1)
        path = save(kwargs['logger'].root/'continuity/fixture_only-partial.json',
            {'fixture_only': True, 'attempt': len(calls)})
        partial.append((path, path.read_bytes()))
        raise KeyboardInterrupt('fixture_only interruption for local retry bound')
    monkeypatch.setattr(analyzer, 'analyze_continuity', interrupted)
    for _ in range(3):
        result = analyze(setup, module, request)
        assert result.status == 'interrupted', result.error
    result = analyze(setup, module, request)
    assert result.status == 'blocked', result.error
    assert len(calls) == 3
    assert len(list((folder/'attempts').glob('*/intent.json'))) == 3
    assert all(path.read_bytes() == raw for path, raw in partial)
