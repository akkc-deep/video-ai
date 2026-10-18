"""Coordinator tests use real durable manifests and isolated stage adapters."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from video_ai.runtime.manifest import create_manifest, hash_file, thaw
from video_ai.runtime.timeline_checks import _artifact


def module():
    from video_ai import pipeline
    return pipeline


@pytest.fixture
def flow(runtime_run, monkeypatch):
    run, config, paths = runtime_run
    store = create_manifest(run, config, inputs={'config': hash_file(config.config_file),
        'voice': hash_file(config.voice.config_file)}, models={}, workflows={})
    from video_ai.runtime import pipeline_stages as stages
    from video_ai.runtime import pipeline_inventory
    def isolated_projection(config,identities):
        value=thaw(config);value.pop('raw');value['voice'].pop('raw');return value
    monkeypatch.setattr(pipeline_inventory,'config_projection',isolated_projection)
    generated = []
    consumed = []
    def consume(name, config, run):
        consumed.append(name)
        path = run/(name+'.fixture.json')
        data = json.loads(path.read_text(encoding='utf-8'))
        registered = store.snapshot()['stages'][name]['artifacts'][0]
        assert hash_file(path).sha256 == registered['sha256']
        if name == 'speech':
            return dict(accepted=data.get('accepted', False), input_identities={})
        return data
    def prepare(name, config, run, *, options, reviews, store):
        generated.append(name)
        path = run/(name+'.fixture.json')
        store.record_stage(name, 'running')
        if stages.BY_NAME[name].draft:
            path = run/stages.BY_NAME[name].draft
            path.write_text(json.dumps(dict(status='review_required',run_id=run.name,passed=False)),encoding='utf-8')
            store.record_stage(name,'running',artifacts=[_artifact(hash_file(path))])
            return dict(passed=False,status='review_required')
        path.write_text(json.dumps(dict(status='completed', accepted=False)), encoding='utf-8')
        store.record_stage(name, 'completed', artifacts=[_artifact(hash_file(path))])
        return dict(passed=True, status='completed')
    monkeypatch.setattr(stages, 'consume', consume)
    monkeypatch.setattr(stages, 'prepare', prepare)
    def committed(name, **data):
        path = run/(name+'.fixture.json')
        path.write_text(json.dumps(dict(status='completed', **data)), encoding='utf-8')
        store.record_stage(name, 'running')
        store.record_stage(name, 'completed', artifacts=[_artifact(hash_file(path))])
    return SimpleNamespace(run=run, config=config, paths=paths, store=store,
        generated=generated, consumed=consumed, committed=committed, stages=stages)


def test_resume_completed_speech_stops_before_timeline_without_acceptance(flow):
    flow.committed('preflight', passed=True)
    flow.committed('speech')
    result = module().resume_pipeline(flow.config, run_dir=flow.run)
    assert result.status == 'awaiting_review'
    assert result.waiting_for == ('voice_acceptance',)
    assert flow.store.snapshot()['stages']['timeline']['status'] == 'pending'
    assert flow.generated == []
    assert result.report_path.is_file()
    assert json.loads(result.report_path.read_text(encoding='utf-8'))['result']['report_path']==str(result.report_path)


def test_completed_candidate_consumed_and_never_prepared_or_published(flow):
    for name in flow.stages.STAGES[:-1]:
        flow.committed(name, passed=True, accepted=True)
    before = (flow.run/'manifest.json').read_bytes()
    result = module().resume_pipeline(flow.config, run_dir=flow.run)
    assert result.status == 'awaiting_acceptance' and not result.published
    assert 'full_film_acceptance' in result.waiting_for
    assert flow.generated == []
    assert 'validation' in flow.consumed
    from video_ai.runtime.pipeline_evidence import protected_snapshot
    protected_snapshot(flow.store.snapshot(),json.loads(before))
    assert any(key.startswith('pipeline_result_') for key in flow.store.snapshot()['workflows'])


def test_legacy_preflight_pending_does_not_run_or_mutate_history(flow):
    for name in flow.stages.STAGES[1:-1]:
        flow.committed(name, accepted=True)
    before = (flow.run/'manifest.json').read_bytes()
    result = module().resume_pipeline(flow.config, run_dir=flow.run)
    assert result.status == 'awaiting_acceptance'
    assert 'preflight' not in flow.generated
    from video_ai.runtime.pipeline_evidence import protected_snapshot
    protected_snapshot(flow.store.snapshot(),json.loads(before))
    assert any(key.startswith('pipeline_result_') for key in flow.store.snapshot()['workflows'])


def test_speech_acceptance_allows_timeline_then_waits_for_timing(flow):
    flow.committed('preflight', passed=True)
    flow.committed('speech', accepted=True)
    result = module().resume_pipeline(flow.config, run_dir=flow.run)
    assert result.waiting_for == ('timing',)
    assert flow.store.snapshot()['stages']['timeline']['status'] == 'completed'
    assert flow.store.snapshot()['stages']['storyboard']['status'] == 'pending'


def test_explicit_current_timing_review_is_compared_with_prior_consumed_review(flow):
    from video_ai.runtime.manifest import now
    folder=flow.run/'logs/storyboard';folder.mkdir(parents=True)
    prior=folder/'timing-review.json';prior.write_bytes(b'{"version":"old"}')
    current=folder/'timing-revision.json';current.write_bytes(b'{"version":"new"}')
    for stage in ('preflight','speech','timeline'):flow.committed(stage,passed=True,accepted=True)
    flow.committed('storyboard',timing_review_identity=thaw(hash_file(prior)))
    pipeline_dir=flow.run/'logs/pipeline';pipeline_dir.mkdir(parents=True)
    index=pipeline_dir/'reviews.json'
    index.write_text(json.dumps(dict(schema_version=1,run_id=flow.run.name,created_at=now(),
        entries={'timing':thaw(hash_file(current))})),encoding='utf-8')
    plan=module().plan_resume(flow.config,run_dir=flow.run,reviews_path=index)
    assert any(row.field=='reviews.timing' for row in plan.changed_keys)
    assert any(row.stage=='timeline' for row in plan.invalidated)
    assert plan.requires_child_run


def test_running_draft_waits_without_preparing(flow):
    for name in ('preflight', 'speech', 'timeline'):
        flow.committed(name, passed=True, accepted=True)
    flow.store.record_stage('storyboard', 'running')
    draft = flow.run/'storyboard-draft.json'
    draft.write_text(json.dumps(dict(schema_version=1, run_id=flow.run.name,
        status='review_required', passed=False)), encoding='utf-8')
    flow.store.record_stage('storyboard', 'running', artifacts=[_artifact(hash_file(draft))])
    monkey = pytest.MonkeyPatch()
    monkey.setattr(flow.stages, 'validate_checkpoint', lambda *args: dict(draft_identity=thaw(hash_file(draft))))
    try:
        result = module().resume_pipeline(flow.config, run_dir=flow.run)
    finally:
        monkey.undo()
    assert result.waiting_for == ('storyboard',)
    assert flow.generated == []
    assert flow.store.snapshot()['stages']['storyboard']['status'] == 'running'
    details=json.loads(result.report_path.read_text(encoding='utf-8'))['waiting_details'][0]
    assert details['draft_identity']['sha256']==hash_file(draft).sha256
    assert details['stage']=='storyboard'


def test_foreign_pipeline_lock_rejected_and_preserved(flow):
    sentinel = flow.run/'.pipeline.lock'
    sentinel.write_bytes(b'foreign')
    with pytest.raises(ValueError): module().resume_pipeline(flow.config, run_dir=flow.run)
    assert sentinel.read_bytes() == b'foreign'


@pytest.mark.parametrize('kwargs', [{'publish': True, 'retry_failed': True},
    {'publish': True, 'changes_path': Path('D:/changes.json')}])
def test_publish_and_mutation_flags_are_mutually_exclusive(flow, kwargs):
    with pytest.raises(ValueError): module().resume_pipeline(flow.config, run_dir=flow.run, **kwargs)
    assert not list((flow.run/'logs/pipeline').glob('*'))


def test_completed_file_drift_refuses_without_repair(flow):
    flow.committed('preflight', passed=True)
    flow.committed('speech', accepted=True)
    (flow.run/'speech.fixture.json').write_bytes(b'corrupt')
    before = (flow.run/'manifest.json').read_bytes()
    with pytest.raises(ValueError): module().resume_pipeline(flow.config, run_dir=flow.run)
    assert (flow.run/'manifest.json').read_bytes() == before
    assert not flow.generated


def test_pipeline_registry_is_fixed_and_frozen():
    from video_ai.runtime.pipeline_stages import REGISTRY, STAGES
    assert tuple(s.name for s in REGISTRY) == STAGES
    with pytest.raises((AttributeError, TypeError)): REGISTRY[0].name = 'publish'


def test_inventory_retains_stage_receipts_and_verified_partial_units(flow, monkeypatch):
    from video_ai.runtime import pipeline_import, pipeline_inventory
    flow.committed('preflight', passed=True)
    flow.committed('speech', accepted=True)
    flow.store.record_stage('source_clips', 'running')
    flow.store.record_stage('source_clips', 'interrupted')
    checkpoint = flow.run/'clip.fixture.txt'; checkpoint.write_bytes(b'verified prefix')
    identity = thaw(hash_file(checkpoint))
    monkeypatch.setattr(pipeline_import, 'collect_partial_inventory', lambda *a: {
        'source_clips': dict(verified_units={'shot_0001':dict(record={'status':'completed'},
            checkpoint_identity=identity,signature='a'*64)}, remaining_units=('shot_0002',),
            input_identities={'checkpoint':identity}, evidence_identities={}, unsent_verified=True)})
    monkeypatch.setattr(pipeline_inventory, 'enrich_inventory', lambda *a: ({s:{} for s in flow.stages.STAGES},{}))
    inventory, consumed = module()._collect_inventory(flow.config,flow.run)
    assert inventory.stage_records['speech']['receipt']==consumed['speech']
    assert inventory.unit_records['source_clips']['shot_0001']['status']=='completed'
    assert inventory.checkpoints['source_clips']['remaining_units']==('shot_0002',)
    assert inventory.signatures['source_clips']['shot_0001']=='a'*64
    assert str(checkpoint) in inventory.input_identities


def test_identity_index_rejects_same_bytes_with_changed_mtime(flow):
    import os
    path=flow.run/'origin.txt';path.write_bytes(b'protected bytes')
    original=hash_file(path)
    os.utime(path,ns=(original.mtime_ns+1_000_000_000,original.mtime_ns+1_000_000_000))
    with pytest.raises((OSError,ValueError),match='changed'):
        module()._identity_index(thaw(original),{})


@pytest.fixture
def legacy_tts_speech(timeline_run, monkeypatch):
    """Actual old speech consumer, real WAVs and isolated historical YAML."""
    import os
    from video_ai.runtime import _candidate_evidence, pipeline_inventory
    from video_ai.runtime.speech_checks import _artifact as speech_artifact
    run, config, store, report = timeline_run
    yaml = run/'config/tts-api.yaml'
    yaml.parent.mkdir()
    yaml.write_bytes(b'TEST ONLY immutable historical TTS settings')
    original = hash_file(yaml)
    report['inputs']['tts_yaml'] = thaw(original)
    store.update(lambda data: data['inputs'].update(tts_yaml=thaw(original)))
    def bind_report():
        path = run/'segments.json'
        path.write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
        snapshot = store.snapshot()
        snapshot['stages']['speech']['artifacts'] = [speech_artifact(path)]
        (run/'manifest.json').write_text(json.dumps(snapshot), encoding='utf-8')
    bind_report()
    os.utime(yaml, ns=(original.mtime_ns+1_000_000_000, original.mtime_ns+1_000_000_000))
    monkeypatch.setattr(_candidate_evidence, 'HISTORICAL_TTS_CONFIG', yaml)
    def projection(config, identities):
        value = thaw(config); value.pop('raw'); value['voice'].pop('raw'); return value
    monkeypatch.setattr(pipeline_inventory, 'config_projection', projection)
    return SimpleNamespace(run=run, config=config, store=store, report=report,
        yaml=yaml, original=original, bind_report=bind_report)


def test_legacy_speech_and_coordinator_retain_historical_tts_payload_rule(legacy_tts_speech):
    from video_ai.runtime.speech_checks import load_committed_speech
    f = legacy_tts_speech
    protected = {str(p):p.read_bytes() for p in f.run.rglob('*') if p.is_file()}
    consumed = load_committed_speech(f.run)
    current = hash_file(f.yaml)
    assert current.mtime_ns != f.original.mtime_ns
    assert any(v.path == str(f.yaml) and v.mtime_ns == current.mtime_ns
        for v in consumed['input_identities'].values())
    assert consumed['report']['inputs']['tts_yaml'] == thaw(f.original)
    result = module().resume_pipeline(f.config, run_dir=f.run)
    assert result.status == 'awaiting_review' and result.waiting_for == ('voice_acceptance',)
    assert not result.published
    assert f.store.snapshot()['stages']['timeline']['status'] == 'pending'
    assert all(Path(path).read_bytes() == value for path,value in protected.items()
        if Path(path).name != 'manifest.json')
    assert not list((f.run/'logs/http').glob('*.request.json'))


@pytest.mark.parametrize('damage', ['payload', 'wrong_path', 'manifest_identity', 'ordinary_receipt',
    'schema2', 'report_future', 'report_null', 'manifest_future', 'manifest_null'])
def test_legacy_tts_compatibility_refuses_other_changes(legacy_tts_speech, damage):
    from video_ai.runtime.speech_checks import load_committed_speech
    f = legacy_tts_speech
    if damage == 'payload':
        f.yaml.write_bytes(b'TEST ONLY changed settings')
    elif damage == 'wrong_path':
        f.report['inputs']['tts_yaml']['path'] = str(f.run/'another-tts.yaml')
        Path(f.report['inputs']['tts_yaml']['path']).write_bytes(f.yaml.read_bytes())
        f.store.update(lambda data: data['inputs'].update(tts_yaml=f.report['inputs']['tts_yaml']))
        f.bind_report()
    elif damage == 'manifest_identity':
        f.store.update(lambda data: data['inputs']['tts_yaml'].update(mtime_ns=f.original.mtime_ns+1_000_000))
    elif damage == 'ordinary_receipt':
        f.report['ordinary_current_tts'] = thaw(f.original)
        f.bind_report()
    elif damage == 'schema2':
        from pipeline_helpers import unit_review
        review = unit_review(Path(f.report['source']['path']), f.run/'logs/pipeline/unit-review.json')
        f.report.update(schema_version=2, segmentation_identity=thaw(hash_file(review)),
            execution_policy=dict(gpu_management='disabled',total_timeout_seconds=None,
                media_command_timeout_seconds=300,tts_request_timeout_seconds=f.config.timeouts['tts_request']))
        f.bind_report()
    elif damage.startswith('report_'):
        f.report['inputs']['tts_yaml']['verified_at'] = None if damage.endswith('null') else '2999-01-01T00:00:00+00:00'
        f.bind_report()
    else:
        snapshot = f.store.snapshot()
        snapshot['inputs']['tts_yaml']['verified_at'] = None if damage.endswith('null') else '2999-01-01T00:00:00+00:00'
        (f.run/'manifest.json').write_text(json.dumps(snapshot),encoding='utf-8')
    before = (f.run/'manifest.json').read_bytes()
    with pytest.raises((OSError, ValueError)):
        load_committed_speech(f.run)
    with pytest.raises(module().PipelineRefusal):
        module().resume_pipeline(f.config, run_dir=f.run)
    assert (f.run/'manifest.json').read_bytes() == before
    assert not list((f.run/'logs/http').glob('*.request.json'))


def test_historical_tts_late_mtime_drift_refuses_coordinator(legacy_tts_speech, monkeypatch):
    import os
    from video_ai.runtime import pipeline_stages
    f = legacy_tts_speech
    consume = pipeline_stages.consume
    def late_drift(name, config, run):
        result = consume(name, config, run)
        if name == 'speech':
            current = hash_file(f.yaml)
            os.utime(f.yaml, ns=(current.mtime_ns+1_000_000, current.mtime_ns+1_000_000))
        return result
    monkeypatch.setattr(pipeline_stages, 'consume', late_drift)
    with pytest.raises(module().PipelineRefusal, match='changed'):
        module().resume_pipeline(f.config, run_dir=f.run)
    assert not list((f.run/'logs/http').glob('*.request.json'))


def test_actual_schema1_inherited_speech_keeps_original_tts_rule(legacy_tts_speech):
    from copy import deepcopy
    import shutil
    from video_ai.runtime.paths import RuntimePaths, create_run
    from video_ai.runtime.manifest import now
    from video_ai.runtime.speech_checks import load_committed_speech, _artifact as speech_artifact
    from video_ai.runtime.timeline_checks import plan_timeline
    from unit.test_timeline_checks import accept
    f = legacy_tts_speech
    original_acceptance = accept(f.run, f.report)
    assert plan_timeline(f.config,run_dir=f.run).passed
    protected = {str(p):p.read_bytes() for p in f.run.rglob('*') if p.is_file()}
    child = create_run(RuntimePaths.from_config(f.config))
    shutil.copytree(f.run/'audio',child/'audio')
    shutil.copy2(f.run/'script.txt',child/'script.txt')
    store = create_manifest(child,f.config,inputs=f.store.snapshot()['inputs'],models={},workflows={})
    report = deepcopy(f.report)
    report.update(run_dir=str(child),script_copy=thaw(hash_file(child/'script.txt')))
    store.record_stage('speech','running')
    for row in report['spans']:
        if row['kind']=='speech':
            row['pcm']['path'] = str(child/Path(row['pcm']['path']).relative_to(f.run))
            store.record_unit('speech',row['unit_id'],'running')
            store.record_unit('speech',row['unit_id'],'completed',artifacts=[row['pcm']])
    receipt = dict(schema_version=1,parent_run=str(f.run),created_at=now(),reason='TEST ONLY original accepted speech',
        parent_manifest=thaw(hash_file(f.run/'manifest.json')),parent_timeline=thaw(hash_file(f.run/'timeline.json')),
        parent_segments=thaw(hash_file(f.run/'segments.json')),parent_voice_listening=thaw(hash_file(f.run/'voice-listening.json')),
        copies=[dict(original=thaw(hash_file(p)),copy=thaw(hash_file(child/p.relative_to(f.run))))
            for p in (f.run/'audio').rglob('*') if p.is_file()])
    import_path = child/'logs/storyboard/upstream-import.json'
    import_path.parent.mkdir(parents=True)
    import_path.write_text(json.dumps(receipt),encoding='utf-8')
    report['import_provenance_identity'] = thaw(hash_file(import_path))
    (child/'segments.json').write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
    store.record_stage('speech','completed',artifacts=[speech_artifact(child/'segments.json')])
    accepted = deepcopy(original_acceptance)
    accepted.update(segments_identity=thaw(hash_file(child/'segments.json')),
        inherited_acceptance_identity=receipt['parent_voice_listening'])
    for row in accepted['audio']:
        row['pcm']['path'] = str(child/Path(row['pcm']['path']).relative_to(f.run))
    (child/'voice-listening.json').write_text(json.dumps(accepted),encoding='utf-8')
    consumed = load_committed_speech(child)
    assert consumed['accepted'] is True
    assert any(key.startswith('legacy_origin/') and value.path==str(f.yaml)
        for key,value in consumed['input_identities'].items())
    result = module().resume_pipeline(f.config,run_dir=child)
    assert result.status=='awaiting_review' and result.waiting_for==('timing',)
    assert not result.published
    assert all(Path(path).read_bytes()==value for path,value in protected.items())
    assert not list((child/'logs/http').glob('*.request.json'))


def test_replaced_lock_during_stage_preserved_without_success(flow,monkeypatch):
    flow.committed('preflight',passed=True);flow.committed('speech',accepted=True)
    original=flow.stages.prepare
    def replace_lock(*a,**kw):
        result=original(*a,**kw)
        (flow.run/'.pipeline.lock').write_bytes(b'{"pid":1,"token":"foreign"}')
        return result
    monkeypatch.setattr(flow.stages,'prepare',replace_lock)
    with pytest.raises(ValueError,match='lock replaced'):
        module().resume_pipeline(flow.config,run_dir=flow.run)
    assert json.loads((flow.run/'.pipeline.lock').read_bytes())['token']=='foreign'
    assert not list((flow.run/'logs/pipeline').glob('result-*'))


@pytest.mark.parametrize('policy',[
    dict(gpu_management='sampled',total_timeout_seconds=None,media_command_timeout_seconds=300),
    dict(gpu_management='disabled',total_timeout_seconds=3600,media_command_timeout_seconds=300),
    dict(gpu_management='disabled',total_timeout_seconds=None,media_command_timeout_seconds=True)])
def test_loaded_options_reject_non_pipeline_execution_policy(flow,policy):
    from video_ai.runtime.manifest import now
    script=flow.run/'original.txt';script.write_bytes(b'TEST ONLY')
    folder=flow.run/'logs/pipeline';folder.mkdir(parents=True)
    value=dict(schema_version=1,run_id=flow.run.name,created_at=now(),input_identities={'script':thaw(hash_file(script))},
        unit_review_identity=None,image_inputs_identity=None,settings_identity=None,output_path=None,cpu_planner=False,execution_policy=policy)
    (folder/'pipeline-options.json').write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ValueError,match='execution policy'):module()._options(flow.run)


def test_new_validation_returns_candidate_ready(flow):
    for name in flow.stages.STAGES[:-2]:
        flow.committed(name, passed=True, accepted=True)
    result = module().resume_pipeline(flow.config, run_dir=flow.run)
    assert result.status == 'candidate_ready'
    assert flow.store.snapshot()['stages']['validation']['status'] == 'completed'
    assert flow.store.snapshot()['stages']['publish']['status'] == 'pending'


def test_finalize_running_checkpoint_consumes_new_result_and_waits_next(flow, monkeypatch):
    for name in ('preflight','speech','timeline'):
        flow.committed(name, passed=True, accepted=True)
    flow.store.record_stage('storyboard','running')
    draft = flow.run/'storyboard-draft.json'; draft.write_bytes(b'{}')
    flow.store.record_stage('storyboard','running',artifacts=[_artifact(hash_file(draft))])
    path = flow.run/'logs/storyboard/semantic-review.json'; path.parent.mkdir(parents=True); path.write_bytes(b'{}')
    index = flow.run/'logs/pipeline/reviews.json'; index.parent.mkdir(parents=True)
    from video_ai.runtime.manifest import now
    index.write_text(json.dumps(dict(schema_version=1,run_id=flow.run.name,created_at=now(),entries={'storyboard':thaw(hash_file(path))})),encoding='utf-8')
    monkeypatch.setattr(flow.stages,'validate_checkpoint',lambda *a:dict(draft_complete=True,draft_identity=thaw(hash_file(draft))))
    def finalize(name, config, run, review_path):
        report = run/(name+'.fixture.json'); report.write_bytes(b'{"status":"completed"}')
        flow.store.record_stage(name,'completed',artifacts=[_artifact(hash_file(report))])
        return dict(status='completed')
    monkeypatch.setattr(flow.stages,'finalize',finalize)
    result = module().resume_pipeline(flow.config,run_dir=flow.run,reviews_path=index)
    assert result.waiting_for == ('start_images',)
    assert 'storyboard' not in flow.generated
    assert flow.store.snapshot()['stages']['storyboard']['status']=='completed'


def test_preflight_failure_never_creates_run(flow,monkeypatch):
    from video_ai.runtime import preflight as pf
    from video_ai.runtime import pipeline_reviews
    monkeypatch.setattr(pipeline_reviews,'load_unit_review',lambda *a,**kw:SimpleNamespace(
        script=SimpleNamespace(spans=(SimpleNamespace(kind='speech'),))))
    monkeypatch.setattr(pf,'preflight',lambda *a,**kw:pf.PreflightReport((pf.PreflightCheck('space',False,'full'),)))
    monkeypatch.setattr(module(),'create_run',lambda *a:pytest.fail('preflight failure created a run'))
    with pytest.raises(ValueError,match='preflight failed'):
        module().run_pipeline(flow.config,script=flow.run/'script.txt',unit_review_path=flow.run/'review.json')


def test_interruption_retains_prefix_and_returns_130_status(flow,monkeypatch):
    flow.committed('preflight',passed=True);flow.committed('speech',accepted=True)
    def interrupted(name,config,run,**kwargs):
        flow.store.record_stage(name,'running'); flow.store.record_stage(name,'interrupted')
        raise KeyboardInterrupt()
    monkeypatch.setattr(flow.stages,'prepare',interrupted)
    result=module().resume_pipeline(flow.config,run_dir=flow.run)
    assert result.status=='interrupted'
    assert flow.store.snapshot()['stages']['speech']['status']=='completed'
    assert list((flow.run/'logs/pipeline').glob('diagnostic-*.json'))


def test_interrupt_diagnostic_write_failure_preserves_original_interrupt(flow,monkeypatch):
    flow.committed('preflight',passed=True);flow.committed('speech',accepted=True)
    original_interrupt=KeyboardInterrupt('TEST ONLY original interruption')
    def interrupted(*a,**kw):raise original_interrupt
    monkeypatch.setattr(flow.stages,'prepare',interrupted)
    original=module().save_record
    def failed_diagnostic(run,kind,data):
        if kind=='diagnostic':raise OSError('TEST ONLY diagnostic disk failure')
        return original(run,kind,data)
    monkeypatch.setattr(module(),'save_record',failed_diagnostic)
    with pytest.raises(KeyboardInterrupt) as raised:
        module().resume_pipeline(flow.config,run_dir=flow.run)
    assert raised.value is original_interrupt
    assert not (flow.run/'.pipeline.lock').exists()


def test_unregistered_pipeline_result_cannot_be_self_authorized(flow):
    from video_ai.runtime.pipeline_evidence import load_pipeline_result,write_exclusive
    path=flow.run/'logs/pipeline'/('result-'+'f'*32+'.json')
    write_exclusive(flow.run,path,{'schema_version':1,'run_id':flow.run.name})
    with pytest.raises(ValueError,match='registered'):
        load_pipeline_result(path)


@pytest.mark.parametrize('field,value',[('status','invented'),('published',True),('active_stage','unknown'),('candidate_path','D:/VideoSi/foreign.mp4'),('waiting_for',[])])
def test_registered_audit_rejects_inconsistent_result_fields(flow,field,value):
    from video_ai.runtime.pipeline_evidence import load_pipeline_result
    flow.committed('preflight',passed=True);flow.committed('speech')
    result=module().resume_pipeline(flow.config,run_dir=flow.run)
    data=json.loads(result.report_path.read_text(encoding='utf-8'));data['result'][field]=value
    result.report_path.write_text(json.dumps(data),encoding='utf-8')
    key='pipeline_'+result.report_path.stem.replace('-','_')
    snapshot=flow.store.snapshot();snapshot['workflows'][key]=thaw(hash_file(result.report_path))
    (flow.run/'manifest.json').write_text(json.dumps(snapshot),encoding='utf-8')
    with pytest.raises(ValueError):load_pipeline_result(result.report_path)


def test_registered_audit_cannot_be_removed_or_replaced(flow):
    flow.committed('preflight',passed=True);flow.committed('speech')
    result=module().resume_pipeline(flow.config,run_dir=flow.run)
    key='pipeline_'+result.report_path.stem.replace('-','_')
    with pytest.raises(ValueError,match='pipeline audit'):
        flow.store.update(lambda data:data['workflows'].pop(key))


def test_fully_reviewed_staging_waits_for_explicit_publish_and_audit_accepts(flow,monkeypatch):
    from video_ai.runtime.pipeline_evidence import load_pipeline_result
    from video_ai.runtime import candidate_checks
    from video_ai.runtime._candidate_evidence import validation
    video=flow.run/'candidate.mp4';video.write_bytes(b'TEST ONLY candidate')
    subtitle=flow.run/'subtitle.srt';subtitle.write_bytes(b'TEST ONLY subtitles')
    candidate=dict(candidate_identity=thaw(hash_file(video)),subtitle_identity=thaw(hash_file(subtitle)),validation=validation())
    for name in flow.stages.STAGES[:-1]:
        flow.committed(name,accepted=True,**(candidate if name=='validation' else {}))
    collect=module()._collect_inventory
    from dataclasses import replace
    def reviewed(*a,**kw):
        inventory,consumed=collect(*a,**kw)
        return replace(inventory,reviews=dict(final_review=True,full_film_acceptance=True)),consumed
    monkeypatch.setattr(module(),'_collect_inventory',reviewed)
    monkeypatch.setattr(candidate_checks,'load_committed_candidate',lambda *a:candidate)
    result=module().resume_pipeline(flow.config,run_dir=flow.run)
    assert result.waiting_for==('publish',) and not result.published
    assert load_pipeline_result(result.report_path)['result']['waiting_for']==['publish']


def test_audit_invocation_must_be_registered_invocation_kind(flow):
    from video_ai.runtime.pipeline_evidence import load_pipeline_result
    flow.committed('preflight',passed=True);flow.committed('speech')
    result=module().resume_pipeline(flow.config,run_dir=flow.run)
    snapshot=flow.store.snapshot();plan=next(value for key,value in snapshot['workflows'].items() if key.startswith('pipeline_plan_'))
    data=json.loads(result.report_path.read_text(encoding='utf-8'));data['invocation_identity']=plan
    result.report_path.write_text(json.dumps(data),encoding='utf-8')
    key='pipeline_'+result.report_path.stem.replace('-','_');snapshot['workflows'][key]=thaw(hash_file(result.report_path))
    (flow.run/'manifest.json').write_text(json.dumps(snapshot),encoding='utf-8')
    with pytest.raises(ValueError,match='invocation'):load_pipeline_result(result.report_path)
