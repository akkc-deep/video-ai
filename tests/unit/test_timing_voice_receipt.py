"""Delegated timing consumes the registered current voice acceptance chain."""
import array
import json
from pathlib import Path
import wave

import pytest

from unit.test_pipeline_reviews import complete_voice_fixture


@pytest.fixture
def receipt_timing_run(timeline_run):
    from video_ai.runtime.manifest import hash_file, now, thaw
    from video_ai.runtime.pipeline_reviews import accept_voice_review
    from video_ai.runtime.timeline_checks import plan_timeline
    from video_ai.runtime.speech_checks import _artifact
    from unit.test_timeline_checks import rewrite_segments
    run, config, store, data, author, acceptance = complete_voice_fixture(timeline_run)
    payload = array.array('h', [0]*200 + [100]*3600 + [0]*1000).tobytes()
    manifest = store.snapshot()
    speech = [span for span in data['spans'] if span['kind'] == 'speech']
    for span in [data['reference_replay'], *speech]:
        for key in ('raw', 'pcm'):
            path = Path(span[key]['path'])
            with wave.open(str(path), 'wb') as audio:
                audio.setparams((1, 2, 48000, 0, 'NONE', ''))
                audio.writeframes(payload)
            span[key] = _artifact(path)
        manifest['units']['speech'][span['unit_id']]['artifacts'] = [span['raw'], span['pcm']]
    preview = Path(data['listening_preview']['identity']['path'])
    with wave.open(str(preview), 'wb') as audio:
        audio.setparams((1, 2, 48000, 0, 'NONE', ''))
        audio.writeframes(payload * 3)
    data['listening_preview']['identity'] = _artifact(preview)
    (run/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    rewrite_segments(run, store, data)
    acceptance.update(segments_identity=thaw(hash_file(run/'segments.json')),
        reference_identity=thaw(hash_file(Path(data['reference_replay']['pcm']['path']))),
        preview_identity=thaw(hash_file(preview)),
        audio_identities=[dict(unit_id=span['unit_id'], text=span['text'], samples=span['samples'],
            raw=thaw(hash_file(Path(span['raw']['path']))), pcm=thaw(hash_file(Path(span['pcm']['path'])))) for span in speech])
    author.write_text(json.dumps(acceptance), encoding='utf-8')
    legacy = run/'voice-listening.json'
    legacy.write_text(json.dumps(dict(schema_version=1, listened=False, accepted=False,
        audio=[{k:span[k] for k in ('unit_id','text','pcm','samples')} for span in speech])), encoding='utf-8')
    receipt = accept_voice_review(config, run, author)
    assert plan_timeline(config, run_dir=run).listening_accepted is True
    folder = run/'logs/storyboard'
    folder.mkdir(parents=True, exist_ok=True)
    delegation = folder/'delegation.json'
    delegation.write_text(json.dumps(dict(schema_version=1, run_id=run.name, authority='user_message',
        scope='delegate_audio_timing', statement='TEST ONLY user delegates timing for current accepted audio', granted_at=now(),
        script_identity=thaw(hash_file(run/'script.txt')), timeline_identity=thaw(hash_file(run/'timeline.json')),
        voice_listening_identity=thaw(receipt))), encoding='utf-8')
    return run, config, store, delegation, Path(receipt.path), legacy


def test_registered_voice_receipt_allows_reproducible_timing_without_rewriting_legacy(receipt_timing_run):
    # Fixed legacy-path lookup currently rejects this valid, registered receipt.
    from video_ai.runtime.storyboard_checks import create_automated_timing_review, load_timing_review
    from video_ai.runtime.timeline_checks import load_committed_timeline
    run, config, store, delegation, receipt, legacy = receipt_timing_run
    before_legacy, before_receipt = legacy.read_bytes(), receipt.read_bytes()
    path = create_automated_timing_review(config, run_dir=run, delegation_path=delegation,
        semantic_reasons={f'speech_{i:04d}':'TEST ONLY one scene per source unit' for i in range(1,4)})
    record = json.loads(path.read_text(encoding='utf-8'))
    assert record['review_method'] == 'automated_audio'
    assert record['human_boundary_reviewed'] is False
    assert [(row['spoken_start_sample'],row['spoken_end_sample'],row['boundary_uncertainty_samples']) for row in record['units']] == [(200,3800,240)]*3
    assert load_timing_review(run, path, load_committed_timeline(run)).review_method == 'automated_audio'
    assert legacy.read_bytes() == before_legacy and receipt.read_bytes() == before_receipt
    assert store.snapshot()['stages']['storyboard']['status'] == 'pending'


@pytest.mark.parametrize('bad', ['unregistered_copy','wrong_bound_file','receipt_drift','audio_drift','stale_segments','missing_registration'])
def test_delegated_timing_rejects_untrusted_or_stale_voice_acceptance(receipt_timing_run, bad):
    from video_ai.runtime.manifest import hash_file, thaw
    from video_ai.runtime.storyboard_checks import create_automated_timing_review
    run, config, store, delegation, receipt, legacy = receipt_timing_run
    data = json.loads(delegation.read_text(encoding='utf-8'))
    if bad == 'unregistered_copy':
        copied = run/'logs/pipeline/unregistered-acceptance.json'
        copied.write_bytes(receipt.read_bytes())
        data['voice_listening_identity'] = thaw(hash_file(copied))
    elif bad == 'wrong_bound_file':
        data['voice_listening_identity'] = thaw(hash_file(run/'timeline.json'))
    elif bad == 'receipt_drift':
        with receipt.open('a', encoding='utf-8') as stream:stream.write(' ')
        data['voice_listening_identity'] = thaw(hash_file(receipt))
    elif bad == 'audio_drift':
        pcm = Path(json.loads(receipt.read_text(encoding='utf-8'))['audio_identities'][0]['pcm']['path'])
        with pcm.open('ab') as stream:stream.write(b'changed')
    elif bad == 'stale_segments':
        with (run/'segments.json').open('a', encoding='utf-8') as stream:stream.write(' ')
    else:
        snapshot = store.snapshot()
        snapshot['workflows'].pop('voice_acceptance')
        (run/'manifest.json').write_text(json.dumps(snapshot), encoding='utf-8')
    delegation.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises((OSError, ValueError)):
        create_automated_timing_review(config, run_dir=run, delegation_path=delegation,
            semantic_reasons={f'speech_{i:04d}':'TEST ONLY one scene' for i in range(1,4)})
    assert not (run/'logs/storyboard/timing-review.json').exists()
    assert json.loads(legacy.read_text(encoding='utf-8'))['accepted'] is False


def test_timing_consumer_rejects_delegation_replacement_during_validation(receipt_timing_run, monkeypatch):
    from video_ai.runtime import storyboard_checks as checks
    from video_ai.runtime.timeline_checks import load_committed_timeline
    run, config, store, delegation, receipt, legacy = receipt_timing_run
    path = checks.create_automated_timing_review(config, run_dir=run, delegation_path=delegation,
        semantic_reasons={f'speech_{i:04d}':'TEST ONLY single scene' for i in range(1,4)})
    original = checks._delegation
    def replace_then_consume(run_dir, author):
        data = json.loads(author.read_text(encoding='utf-8'))
        data['statement'] = 'TEST ONLY replacement delegation with different bytes'
        author.write_text(json.dumps(data), encoding='utf-8')
        return original(run_dir, author)
    monkeypatch.setattr(checks, '_delegation', replace_then_consume)
    with pytest.raises((OSError, ValueError)):
        checks.load_timing_review(run, path, load_committed_timeline(run))


@pytest.mark.parametrize('operation', ['create','consume'])
def test_timing_rejects_registration_removed_during_measurement(receipt_timing_run, monkeypatch, operation):
    from video_ai.runtime import storyboard_checks as checks
    from video_ai.runtime.timeline_checks import load_committed_timeline
    run, config, store, delegation, receipt, legacy = receipt_timing_run
    reasons = {f'speech_{i:04d}':'TEST ONLY single scene' for i in range(1,4)}
    if operation == 'consume':
        path = checks.create_automated_timing_review(config, run_dir=run, delegation_path=delegation,
            semantic_reasons=reasons)
        timeline = load_committed_timeline(run)
    original = checks.measure_envelope
    def remove_then_measure(pcm):
        snapshot = store.snapshot()
        snapshot['workflows'].pop('voice_acceptance', None)
        (run/'manifest.json').write_text(json.dumps(snapshot), encoding='utf-8')
        return original(pcm)
    monkeypatch.setattr(checks, 'measure_envelope', remove_then_measure)
    with pytest.raises((OSError, ValueError)):
        if operation == 'consume':
            checks.load_timing_review(run, path, timeline)
        else:
            checks.create_automated_timing_review(config, run_dir=run, delegation_path=delegation,
                semantic_reasons=reasons)
    if operation == 'create':
        assert not (run/'logs/storyboard/timing-review.json').exists()


def test_inherited_receipt_accepts_exact_origin_and_rechecks_origin_registration(receipt_timing_run, monkeypatch):
    from video_ai.runtime import speech_checks as speech, storyboard_checks as checks
    from video_ai.runtime.pipeline_import import create_pipeline_import, load_pipeline_import
    from video_ai.runtime.paths import create_run, RuntimePaths
    from video_ai.runtime.manifest import create_manifest, hash_file, thaw, now
    from video_ai.runtime.timeline_checks import plan_timeline, load_committed_timeline
    parent, config, parent_store, author, receipt, legacy = receipt_timing_run
    child = create_run(RuntimePaths.from_config(config))
    target = create_manifest(child, config, inputs=parent_store.snapshot()['inputs'], models={}, workflows={})
    inventory = speech.speech_import_inventory(parent,child)
    identity = create_pipeline_import(config, run_dir=child, parent_run_dir=parent, reason='TEST ONLY timing of reused accepted audio',
        source_identities=inventory['source_identities'], copies=inventory['copies'], stages=[inventory['stage']], units=inventory['units'])
    imported = load_pipeline_import(child)
    reused = {row['id']:dict(origin_run_id=row['imported_record']['origin_run_id'],source_report_identity=row['imported_record']['source_report_identity'],
        source_unit_id=row['imported_record']['source_unit_id'],signature=row['signature'],import_identity=thaw(identity)) for row in imported['units']}
    report = speech.serialize_imported_speech(config,child,source_report=speech.load_committed_speech(parent)['report'],
        import_identity=identity,reused_units=reused,copies=imported['copies'])
    (child/'segments.json').write_text(json.dumps(report),encoding='utf-8')
    target.record_stage('speech','running')
    for uid in reused:
        target.record_unit('speech',uid,'running')
        target.record_unit('speech',uid,'completed',artifacts=[speech._artifact(child/'audio'/uid/name) for name in ('raw.wav','pcm-48000.wav')])
    target.record_stage('speech','completed',artifacts=[speech._artifact(child/'segments.json')])
    assert speech.load_committed_speech(child)['listening_identity'].path == str(receipt)
    assert plan_timeline(config,run_dir=child).listening_accepted is True
    folder = child/'logs/storyboard'
    folder.mkdir(parents=True,exist_ok=True)
    delegation = folder/'delegation.json'
    delegation.write_text(json.dumps(dict(schema_version=1,run_id=child.name,authority='user_message',scope='delegate_audio_timing',
        statement='TEST ONLY delegate timing of unchanged accepted origin audio',granted_at=now(),
        script_identity=thaw(hash_file(child/'script.txt')),timeline_identity=thaw(hash_file(child/'timeline.json')),
        voice_listening_identity=thaw(hash_file(receipt)))),encoding='utf-8')
    timing = checks.create_automated_timing_review(config,run_dir=child,delegation_path=delegation,
        semantic_reasons={f'speech_{i:04d}':'TEST ONLY single scene' for i in range(1,4)})
    timeline = load_committed_timeline(child)
    assert checks.load_timing_review(child,timing,timeline).review_method == 'automated_audio'
    original = checks.measure_envelope
    def remove_origin_then_measure(pcm):
        snapshot = parent_store.snapshot()
        snapshot['workflows'].pop('voice_acceptance',None)
        (parent/'manifest.json').write_text(json.dumps(snapshot),encoding='utf-8')
        return original(pcm)
    monkeypatch.setattr(checks,'measure_envelope',remove_origin_then_measure)
    with pytest.raises((OSError,ValueError)):
        checks.load_timing_review(child,timing,timeline)
