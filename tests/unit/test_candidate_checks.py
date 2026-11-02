from copy import deepcopy
import json
from pathlib import Path
import os
import pytest

from candidate_helpers import make_candidate_fixture, write
from video_ai.runtime.manifest import hash_file, thaw
from video_ai.runtime.timeline_checks import _artifact


@pytest.fixture
def candidate(runtime_run, monkeypatch):
    return make_candidate_fixture(runtime_run, monkeypatch)


def module():
    from video_ai.runtime import candidate_checks
    return candidate_checks


def refresh_report(run, store, report):
    write(run/'candidate-validation.json', report)
    data = store.snapshot(); identity = hash_file(run/'candidate-validation.json')
    data['workflows']['candidate_validation'] = thaw(identity)
    data['stages']['validation']['artifacts'] = [_artifact(identity)]
    write(run/'manifest.json', data)


def test_missing_composition_refuses_before_stage(run_store):
    config = __import__('video_ai.config', fromlist=['load_config']).load_config(Path(run_store.snapshot()['config_snapshot']['path']))
    before = (run_store.run_dir/'manifest.json').read_bytes()
    with pytest.raises(module().CandidateRefusal): module().validate_candidate(config, run_dir=run_store.run_dir)
    assert (run_store.run_dir/'manifest.json').read_bytes() == before


def test_unlimited_candidate_receipts_are_readable_outside_production_scope(candidate,monkeypatch):
    from dataclasses import replace
    from datetime import datetime,timedelta
    from video_ai.runtime.execution_limits import production_execution
    from video_ai.media import composition_video
    original=composition_video.run_logged
    def slow_command(*a,**k):
        result=original(*a,**k)
        return replace(result,started_at=(datetime.fromisoformat(result.started_at)-timedelta(seconds=600)).isoformat())
    monkeypatch.setattr(composition_video,'run_logged',slow_command)
    run,config,_,_=candidate
    result=production_execution(module().validate_candidate)(config,run_dir=run)
    assert result.passed
    execution=json.loads((run/'logs/validation/execution.json').read_text(encoding='utf-8'))
    assert all(r['timeout_seconds'] is None and r.get('time_limits')=='unlimited_v1' for r in execution['commands'])
    assert module().load_committed_candidate(run)['passed']


def test_completed_validation_is_fresh_staging_only_and_preserves_upstream(candidate):
    run, config, store, composition = candidate; before = store.snapshot()
    result = module().validate_candidate(config, run_dir=run)
    assert result.passed and result.ready_for_review and result.staging_only
    assert result.total_frames == 48 and result.total_samples == 144000
    report = module().load_committed_candidate(run)
    assert report['validation']['actual_final_video_semantics'] == 'unverified'
    assert report['validation']['actual_final_video_sync'] == 'unverified'
    assert report['validation']['full_film_acceptance'] == 'unverified'
    assert report['provenance'] == composition['provenance']
    after = store.snapshot()
    assert all(before['stages'][s] == after['stages'][s] for s in before['stages'] if s != 'validation')
    assert before['units'] == after['units'] and before['inputs'] == after['inputs']
    assert len(report['request_evidence']) == 17
    assert all(k.startswith('logs/validation/') for k in report['request_evidence'])
    with pytest.raises(module().CandidateRefusal): module().validate_candidate(config, run_dir=run)


@pytest.mark.parametrize('orphan', ['.validation.lock', 'candidate-validation.json', 'logs/validation/plan.json'])
def test_orphan_and_foreign_lock_are_not_reused(candidate, orphan):
    run, config, store, _ = candidate; path = run/orphan
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'foreign')
    before = (run/'manifest.json').read_bytes()
    with pytest.raises(module().CandidateRefusal): module().validate_candidate(config, run_dir=run)
    assert path.read_bytes() == b'foreign' and (run/'manifest.json').read_bytes() == before


@pytest.mark.parametrize('field', ['ready_for_review', 'validation', 'requirement_bindings', 'cue_checks', 'request_evidence', 'extra', 'plan', 'argv', 'pts', 'packets'])
def test_reconstruction_refuses_forged_report_even_with_fresh_receipts(candidate, field):
    run, config, store, _ = candidate
    assert module().validate_candidate(config, run_dir=run).passed
    report = json.loads((run/'candidate-validation.json').read_text(encoding='utf-8'))
    if field == 'ready_for_review': report[field] = 1
    elif field == 'validation': report[field]['actual_final_video_semantics'] = 'passed'
    elif field in ('requirement_bindings', 'cue_checks'): report[field].reverse()
    elif field == 'request_evidence': report[field].pop(next(iter(report[field])))
    elif field == 'extra': report['ready_for_publish'] = True
    else:
        execution_path = run/'logs/validation/execution.json'
        execution = json.loads(execution_path.read_text(encoding='utf-8'))
        if field == 'plan':
            path = run/'logs/validation/plan.json'; plan = json.loads(path.read_text(encoding='utf-8'))
            plan['expected_media']['frames'] += 1; write(path, plan); report['plan_identity'] = thaw(hash_file(path))
        elif field == 'argv':
            record = execution['commands'][0]; record['args'].insert(1, '-show_packets')
            path = Path(record['record_path']); write(path, {k: v for k, v in record.items() if k != 'record_path'})
            write(execution_path, execution); report['execution_identity'] = thaw(hash_file(execution_path))
            report['request_evidence'][execution_path.relative_to(run).as_posix()] = thaw(hash_file(execution_path))
        else:
            operation = 'pts' if field == 'pts' else 'audio_packets'
            record = next(r for r in execution['commands'] if r['operation'] == operation)
            path = Path(record['stdout_path']); data = json.loads(path.read_text(encoding='utf-8'))
            if field == 'pts': data['frames'][0]['best_effort_timestamp_time'] = '0.1'
            else: data['packets'][1]['pts'] += 1
            write(path, data)
        report['request_evidence'][path.relative_to(run).as_posix()] = thaw(hash_file(path))
    refresh_report(run, store, report)
    with pytest.raises((ValueError, OSError)): module().load_committed_candidate(run)


@pytest.mark.parametrize('target', ['candidate', 'subtitle', 'timeline', 'script', 'config', 'pcm'])
def test_consumer_refuses_input_drift(candidate, target):
    run, config, store, composition = candidate
    assert module().validate_candidate(config, run_dir=run).passed
    paths = {'candidate': run/'staging/composition/candidate.mp4', 'subtitle': run/'staging/composition/subtitle.srt', 'timeline': run/'timeline.json', 'script': run/'script.txt', 'config': config.config_file}
    paths['pcm'] = Path(next(v['path'] for k, v in composition['input_identities'].items() if k.startswith('pcm/')))
    with paths[target].open('ab') as f: f.write(b'changed')
    with pytest.raises((ValueError, OSError)): module().load_committed_candidate(run)


def test_publish_progress_and_new_audit_logs_do_not_invalidate_candidate(candidate):
    run, config, store, _ = candidate
    assert module().validate_candidate(config, run_dir=run).passed
    store.record_stage('publish', 'running')
    (run/'logs/validation/later-observation.json').write_text('{}', encoding='utf-8')
    assert module().load_committed_candidate(run)['passed']


def test_media_failure_after_start_records_failed_diagnostic(candidate, monkeypatch):
    run, config, store, _ = candidate
    monkeypatch.setattr(module(), 'inspect_composition', lambda *a, **kw: (_ for _ in ()).throw(OSError('TEST ONLY failed decode')))
    result = module().validate_candidate(config, run_dir=run)
    assert not result.passed and not result.ready_for_review
    assert store.snapshot()['stages']['validation']['status'] == 'failed'
    assert list((run/'logs/validation').glob('diagnostic-*.json'))
    assert not (run/'.validation.lock').exists()


def test_interruption_retains_foreign_lock(candidate, monkeypatch):
    run, config, store, _ = candidate
    def interrupt(*a, **kw):
        write(run/'.validation.lock', {'pid': 1, 'token': 'foreign'})
        raise KeyboardInterrupt()
    monkeypatch.setattr(module(), 'inspect_composition', interrupt)
    with pytest.raises(KeyboardInterrupt): module().validate_candidate(config, run_dir=run)
    assert store.snapshot()['stages']['validation']['status'] == 'interrupted'
    assert json.loads((run/'.validation.lock').read_text())['token'] == 'foreign'


def test_real_24fps_candidate_and_consumer(runtime_run, monkeypatch):
    run, config, store, _ = make_candidate_fixture(runtime_run, monkeypatch, fps=24)
    result = module().validate_candidate(config, run_dir=run)
    assert result.passed and result.total_frames == 72 and result.total_samples == 144000
    assert module().load_committed_candidate(run)['effective_media']['fps'] == 24


def test_srt_literal_mismatch_cannot_pass_automatic_check(candidate):
    run, config, store, composition = candidate
    path = run/'staging/composition/subtitle.srt'
    path.write_bytes(path.read_bytes().replace('夜'.encode(), '日'.encode()))
    composition['subtitles']['srt_identity'] = thaw(hash_file(path))
    write(run/'composition.json', composition)
    result = module().validate_candidate(config, run_dir=run)
    assert not result.passed and not result.ready_for_review
    assert store.snapshot()['stages']['validation']['status'] == 'failed'


def test_input_mutation_during_media_check_keeps_failed_stage(candidate, monkeypatch):
    run, config, store, _ = candidate; original = module().inspect_composition
    def mutate(*a, **kw):
        inspected = original(*a, **kw)
        with (run/'script.txt').open('ab') as f: f.write(b'drift during media')
        return inspected
    monkeypatch.setattr(module(), 'inspect_composition', mutate)
    result = module().validate_candidate(config, run_dir=run)
    assert not result.passed and store.snapshot()['stages']['validation']['status'] == 'failed'
    assert not (run/'candidate-validation.json').exists()


def test_nested_upstream_frame_mutation_during_inspection_is_refused(candidate, monkeypatch):
    run, config, store, composition = candidate; original = module().inspect_composition
    identity = composition['frame_mappings'][0]['contributors'][0]['frame_identity']
    def mutate(*a, **kw):
        inspected = original(*a, **kw)
        with Path(identity['path']).open('ab') as f: f.write(b'nested source drift')
        return inspected
    monkeypatch.setattr(module(), 'inspect_composition', mutate)
    result = module().validate_candidate(config, run_dir=run)
    assert not result.passed and store.snapshot()['stages']['validation']['status'] == 'failed'


def linked_upstream(run, store, composition):
    leaf = run/'fixture-upstream/transitive-source.bin'
    leaf.write_bytes(b'TEST ONLY transitive original source/model/HTTP payload')
    source = write(run/'logs/source_clips/linked-source.json', {'leaf_identity': thaw(hash_file(leaf))})
    upscale = write(run/'upscaled-clips.json', {'source_report_identity': thaw(hash_file(source))})
    composition['input_identities']['upscaled_clips'] = thaw(hash_file(upscale))
    write(run/'composition.json', composition)
    # TEST ONLY receipt fixture refresh, before validation ever starts.
    data = store.snapshot(); ident = hash_file(run/'composition.json')
    data['workflows']['composition_report'] = thaw(ident)
    data['stages']['composition']['artifacts'] = [_artifact(ident)]
    write(run/'manifest.json', data)
    return leaf, source, upscale


def test_linked_upstream_leaf_mutation_after_report_write_refuses_commit(candidate, monkeypatch):
    run, config, store, composition = candidate
    leaf, _, _ = linked_upstream(run, store, composition)
    original = module().atomic_report
    def mutate(*args, **kwargs):
        original(*args, **kwargs)
        with leaf.open('ab') as out: out.write(b'changed after report write')
    monkeypatch.setattr(module(), 'atomic_report', mutate)
    result = module().validate_candidate(config, run_dir=run)
    assert not result.passed and store.snapshot()['stages']['validation']['status'] == 'failed'
    assert 'candidate_validation' not in store.snapshot()['workflows']


def test_linked_upstream_leaf_mutation_during_consumer_inspection_refuses(candidate, monkeypatch):
    run, config, store, composition = candidate
    leaf, _, _ = linked_upstream(run, store, composition)
    assert module().validate_candidate(config, run_dir=run).passed
    original = module().inspect_composition
    def mutate(*args, **kwargs):
        inspected = original(*args, **kwargs)
        with leaf.open('ab') as out: out.write(b'changed during consumer inspection')
        return inspected
    monkeypatch.setattr(module(), 'inspect_composition', mutate)
    with pytest.raises((ValueError, OSError)): module().load_committed_candidate(run)


def test_bound_identity_closure_follows_verified_json_only(runtime_run, tmp_path):
    from video_ai.runtime._candidate_evidence import capture_bound_identities
    run, _, _ = runtime_run
    leaf = run/'leaf.bin'; leaf.write_bytes(b'TEST ONLY leaf')
    document = write(run/'linked.json', {'leaf': thaw(hash_file(leaf)), 'unbound_path': str(run/'must-not-read.json')})
    external = write(tmp_path/'external.json', {'unbound_external_leaf': {'path': 'C:/must-not-read', 'bytes': 1, 'mtime_ns': 1, 'sha256': '0'*64, 'verified_at': '2026-01-01T00:00:00+08:00'}})
    ids = capture_bound_identities({'linked': thaw(hash_file(document)), 'duplicate': thaw(hash_file(document)), 'external': thaw(hash_file(external))}, run=run)
    assert {i.path for i in ids.values()} == {str(p) for p in (document, leaf, external)}


@pytest.mark.parametrize('document,position', [('segments.json', 'inputs'), ('voice-listening.json', 'voice'), ('logs/upscale/resume-manifest-'+'a'*32+'.json', 'inputs')])
def test_historical_tts_mtime_only_change_freezes_current_identity(runtime_run, monkeypatch, document, position):
    from video_ai.runtime import _candidate_evidence as evidence
    from video_ai.runtime.timeline_checks import _again
    run, _, _ = runtime_run
    tts = run/'fixture-tts-api.yaml'; tts.write_bytes(b'TEST ONLY unchanged TTS settings')
    historical = thaw(hash_file(tts))
    os.utime(tts, ns=(tts.stat().st_atime_ns, historical['mtime_ns']+1000000))
    monkeypatch.setattr(evidence, 'HISTORICAL_TTS_CONFIG', tts, raising=False)
    doc = write(run/document, {position: {'tts_yaml': historical}})
    ids = evidence.capture_bound_identities(thaw(hash_file(doc)), run=run)
    current = next(i for i in ids.values() if i.path == str(tts))
    assert current.mtime_ns == tts.stat().st_mtime_ns != historical['mtime_ns']
    _again(ids)
    os.utime(tts, ns=(tts.stat().st_atime_ns, current.mtime_ns+1000000))
    with pytest.raises(OSError): _again(ids)


def test_historical_tts_payload_change_and_current_receipt_drift_are_refused(runtime_run, monkeypatch):
    from video_ai.runtime import _candidate_evidence as evidence
    run, _, _ = runtime_run
    tts = run/'fixture-tts-api.yaml'; tts.write_bytes(b'TEST ONLY TTS settings')
    historical = thaw(hash_file(tts)); monkeypatch.setattr(evidence, 'HISTORICAL_TTS_CONFIG', tts, raising=False)
    doc = write(run/'segments.json', {'inputs': {'tts_yaml': historical}})
    os.utime(tts, ns=(tts.stat().st_atime_ns, historical['mtime_ns']+1000000))
    with pytest.raises(OSError):
        evidence.capture_bound_identities({'historical': thaw(hash_file(doc)), 'ordinary_receipt': historical}, run=run)
    with tts.open('ab') as out: out.write(b'payload changed')
    with pytest.raises(OSError): evidence.capture_bound_identities(thaw(hash_file(doc)), run=run)


def test_history_exception_requires_exact_document_role_and_tts_path(runtime_run, monkeypatch):
    from video_ai.runtime import _candidate_evidence as evidence
    run, _, _ = runtime_run
    tts = run/'fixture-tts-api.yaml'; tts.write_bytes(b'TEST ONLY TTS settings')
    old = thaw(hash_file(tts)); os.utime(tts, ns=(tts.stat().st_atime_ns, old['mtime_ns']+1000000))
    monkeypatch.setattr(evidence, 'HISTORICAL_TTS_CONFIG', run/'different-tts.yaml', raising=False)
    doc = write(run/'segments.json', {'inputs': {'tts_yaml': old}})
    with pytest.raises(OSError): evidence.capture_bound_identities(thaw(hash_file(doc)), run=run)
    monkeypatch.setattr(evidence, 'HISTORICAL_TTS_CONFIG', tts)
    doc = write(run/'ordinary.json', {'inputs': {'tts_yaml': old}})
    with pytest.raises(OSError): evidence.capture_bound_identities(thaw(hash_file(doc)), run=run)


def test_bound_identity_closure_detects_json_mutation_during_parse(runtime_run, monkeypatch):
    from video_ai.runtime import _candidate_evidence as evidence
    run, _, _ = runtime_run; document = write(run/'linked.json', {'TEST ONLY': True})
    identity = thaw(hash_file(document)); original = evidence.read_json
    def mutate(path):
        value = original(path)
        with Path(path).open('ab') as out: out.write(b'changed during parse')
        return value
    monkeypatch.setattr(evidence, 'read_json', mutate)
    with pytest.raises(OSError): evidence.capture_bound_identities(identity, run=run)
