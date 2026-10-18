import json
import os
from pathlib import Path

import pytest


def state_store(runtime_run):
    from video_ai.runtime.production_state import ProductionStateStore
    run, _, _ = runtime_run
    (run / 'production').mkdir()
    (run / 'production/options.json').write_text('{}', encoding='utf-8')
    return ProductionStateStore.create(run)


def test_bound_state_does_not_commit_after_held_run_lock_is_lost(runtime_run):
    from video_ai.runtime.production_state import RunLock
    store=state_store(runtime_run)
    with RunLock(store.run_dir) as lock:
        store._run_lock_owner=dict(lock.owner)
        original=lock.path.read_bytes();before=store.path.read_bytes();lock.path.unlink()
        try:
            with pytest.raises(ValueError):store.set_invocation('blocked')
            assert store.path.read_bytes()==before
        finally:lock.path.write_bytes(original)


def test_production_state_requires_report_before_advancing(runtime_run):
    store = state_store(runtime_run)
    store.start_stage('preflight')
    with pytest.raises(ValueError, match='report'):
        store.complete_stage('preflight')
    assert store.snapshot()['active_stage'] == 'preflight'
    report = store.write_report('preflight', {'checks': [dict(name='local', passed=True, details='ok')]})
    store.complete_stage('preflight')
    data = store.snapshot()
    assert data['active_stage'] == 'units'
    assert data['stages']['preflight']['report_path'] == str(report)
    with pytest.raises(FileExistsError):
        store.write_report('preflight', {'checks': [dict(name='local', passed=True, details='ok')]})


@pytest.mark.parametrize('corruption', ['unknown', 'bool', 'duplicate', 'nan', 'missing_report', 'escape'])
def test_state_open_rejects_corruption(runtime_run, corruption):
    from video_ai.runtime.production_state import ProductionStateStore
    store = state_store(runtime_run)
    data = store.snapshot()
    if corruption == 'unknown': data['extra'] = 1
    if corruption == 'bool': data['schema_version'] = True
    if corruption == 'escape': data['options_path'] = str(store.run_dir.parent / 'foreign/options.json')
    if corruption == 'missing_report':
        data['stages']['preflight'].update(status='completed', report_path=str(store.run_dir/'production/preflight.json'), started_at=data['created_at'], finished_at=data['created_at'])
        data['active_stage'] = 'units'
    raw = json.dumps(data)
    if corruption == 'duplicate': raw = raw.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
    if corruption == 'nan': raw = raw.replace('"error": null', '"error": NaN')
    store.path.write_text(raw, encoding='utf-8')
    with pytest.raises(ValueError): ProductionStateStore.open(store.run_dir)


@pytest.mark.parametrize('point', ['fsync', 'replace'])
def test_state_atomic_failure_preserves_cursor(runtime_run, monkeypatch, point):
    import video_ai.runtime.production_state as module
    store = state_store(runtime_run)
    before = store.path.read_bytes()
    def fail(*args): raise OSError('injected')
    monkeypatch.setattr(module.os, point, fail)
    with pytest.raises(OSError): store.start_stage('preflight')
    assert store.path.read_bytes() == before


def test_report_rejects_failed_checks_and_unknown_fields(runtime_run):
    store = state_store(runtime_run)
    with pytest.raises(ValueError): store.write_report('preflight', {'checks': [dict(name='bad', passed=False, details='fail')]})
    with pytest.raises(ValueError): store.write_report('preflight', {'checks': [], 'extra': 1})
    assert not (store.run_dir/'production/preflight.json').exists()


def test_unit_checkpoint_and_request_identity_are_durable(runtime_run):
    from video_ai.runtime.production_state import ArtifactStamp
    store = state_store(runtime_run)
    store.start_stage('preflight')
    store.write_report('preflight', {'checks': [dict(name='ok', passed=True, details='ok')]})
    store.complete_stage('preflight')
    store.start_stage('units')
    intent = store.save_exclusive('logs/production/intent.json', {'text': '原文'})
    request = dict(state='intent', intent_path=str(intent), client_id='client', prompt_id=None, response_paths=[])
    store.record_unit('units', 'batch_0001', status='running', request=request)
    with pytest.raises(ValueError):
        store.record_unit('units', 'batch_0001', status='running', request=dict(request, client_id='replacement'))
    output = store.save_exclusive('production/unit-output.json', {'text': '原文'})
    stamp = ArtifactStamp.read(output).to_dict()
    with pytest.raises(ValueError):
        store.record_unit('units', 'batch_0001', status='completed', outputs={'response': stamp})
    checkpoint = store.write_checkpoint('units', 'batch_0001', outputs={'response': stamp}, request=dict(request, state='completed'))
    store.record_unit('units', 'batch_0001', status='completed', checkpoint_path=checkpoint,
                      outputs={'response': stamp}, request=dict(request, state='completed'))
    assert store.snapshot()['units']['units']['batch_0001']['status'] == 'completed'
    with pytest.raises(ValueError): store.record_unit('units', 'batch_0001', status='running')


def test_live_and_foreign_lock_are_preserved(runtime_run):
    from video_ai.runtime.production_state import RunLock, ProductionRefused
    run, _, _ = runtime_run
    path = run / '.make-video.lock'
    with RunLock(run):
        before = path.read_bytes()
        with pytest.raises(ProductionRefused):
            with RunLock(run): pass
        assert path.read_bytes() == before
    assert not path.exists()
    path.write_text('foreign lock', encoding='utf-8')
    with pytest.raises(ProductionRefused):
        with RunLock(run): pass
    assert path.read_text() == 'foreign lock'


def test_lock_cleanup_does_not_replace_original_exception(runtime_run):
    from video_ai.runtime.production_state import RunLock
    run, _, _ = runtime_run
    with pytest.raises(RuntimeError, match='original'):
        with RunLock(run):
            (run / '.make-video.lock').write_text('foreign replacement', encoding='utf-8')
            raise RuntimeError('original')
    assert (run / '.make-video.lock').read_text() == 'foreign replacement'


def test_stamp_rejects_bool_and_detects_media_change(runtime_run):
    from video_ai.runtime.production_state import ArtifactStamp
    run, _, _ = runtime_run
    media = run/'media.bin'; media.write_bytes(b'original')
    stamp = ArtifactStamp.read(media)
    stamp.verify()
    with pytest.raises(ValueError): ArtifactStamp.from_dict(dict(stamp.to_dict(), bytes=True))
    media.write_bytes(b'changed size')
    with pytest.raises(ValueError): stamp.verify()


def test_proven_dead_lock_is_audited_and_archived(runtime_run, monkeypatch):
    import video_ai.runtime.production_state as module
    run, _, _ = runtime_run
    lock = module.RunLock(run)
    dead = dict(lock.owner, pid=2147483647, process_started_at='1')
    (run/'.make-video.lock').write_text(json.dumps(dead), encoding='utf-8')
    real = module.process_started_at
    monkeypatch.setattr(module, 'process_started_at', lambda pid: None if pid == 2147483647 else real(pid))
    with lock:
        current = json.loads((run/'.make-video.lock').read_text())
        assert current['token'] == lock.owner['token']
    audits = list((run/'logs/production/locks').glob('*.json'))
    assert len(audits) == 1
    assert json.loads(audits[0].read_text())['owner'] == dead
    assert json.loads(audits[0].with_suffix('.lock').read_text()) == dead


def test_unsynced_report_cannot_advance_state(runtime_run, monkeypatch):
    import video_ai.runtime.production_state as module
    store = state_store(runtime_run); store.start_stage('preflight')
    report_path = store.run_dir/'production/preflight.json'
    real = module.os.fsync
    def fail_report(fd):
        if report_path.exists() and os.fstat(fd).st_ino == report_path.stat().st_ino:
            raise OSError('report fsync failure')
        return real(fd)
    monkeypatch.setattr(module.os, 'fsync', fail_report)
    with pytest.raises(OSError): store.write_report('preflight', {'checks': [dict(name='ok', passed=True, details='ok')]})
    before = store.path.read_bytes()
    with pytest.raises(OSError, match='report fsync'):
        store.complete_stage('preflight')
    assert store.path.read_bytes() == before


def test_stale_lock_reclamation_cannot_move_another_resumers_live_lock(runtime_run, monkeypatch):
    import video_ai.runtime.production_state as module
    run, _, _ = runtime_run
    outer = module.RunLock(run)
    dead = dict(outer.owner, pid=2147483647, process_started_at='1')
    (run/'.make-video.lock').write_text(json.dumps(dead), encoding='utf-8')
    real_process = module.process_started_at
    monkeypatch.setattr(module, 'process_started_at', lambda pid: None if pid == 2147483647 else real_process(pid))
    real_rename = module.os.rename
    nested = module.RunLock(run); entered = []
    inside = False
    def competing_rename(source, target):
        nonlocal inside
        if Path(source) == run/'.make-video.lock' and not inside:
            inside = True
            try:
                nested.__enter__(); entered.append(True)
            except module.ProductionRefused: pass
            finally: inside = False
        return real_rename(source, target)
    monkeypatch.setattr(module.os, 'rename', competing_rename)
    with outer:
        assert not entered
        assert json.loads((run/'.make-video.lock').read_text())['token'] == outer.owner['token']


@pytest.mark.parametrize('change',['nested_unknown','bool_samples','bool_version','unknown_settings'])
def test_timeline_report_checks_concrete_payload_before_write(runtime_run,change):
    from test_production_timeline import make_timeline
    store=state_store(runtime_run)
    payload=make_timeline().as_dict()
    if change=='nested_unknown': payload['clips'][0]['pcm']['unknown']=1
    if change=='bool_samples': payload['clips'][0]['pcm']['samples']=True
    if change=='bool_version': payload['schema_version']=True
    if change=='unknown_settings': payload['effective_settings']['unknown']=0
    with pytest.raises(ValueError): store.write_report('timeline',payload)
    assert not (store.run_dir/'production/timeline.json').exists()


@pytest.mark.parametrize('payload',[dict(format_valid=1,proposal={},error=None),
    dict(format_valid=True,proposal={},error=None,unknown=1),
    dict(format_valid=False,proposal=None,error=None)])
def test_unit_response_checkpoint_rejects_invalid_payload(runtime_run,payload):
    store=state_store(runtime_run)
    with pytest.raises(ValueError): store.write_checkpoint('units','units_batch_0001_initial',outputs={},payload=payload)


@pytest.mark.parametrize('stage',['upscale','composition'])
def test_completed_make04_cursor_requires_actual_checkpoint_units(runtime_run,monkeypatch,stage):
    import video_ai.runtime.production_state as module
    store=state_store(runtime_run);data=store.snapshot()
    index=module.STAGES.index(stage)
    for name in module.STAGES[:index+1]:
        data['stages'][name].update(status='completed',report_path=str(store.run_dir/'production'/f'{module.REPORT_NAMES[name]}.json'),
            started_at=data['created_at'],finished_at=data['created_at'])
    data['active_stage']=module.STAGES[index+1]
    monkeypatch.setattr(module,'read_json',lambda path:{'payload':{'clips':[],'frames':0}})
    monkeypatch.setattr(module,'validate_report',lambda *args:None)
    with pytest.raises(ValueError,match='checkpoint'):module.validate_state(data,store.run_dir)


def duplicated_stamp_store(runtime_run):
    from video_ai.runtime.production_state import ArtifactStamp
    store=state_store(runtime_run);store.start_stage('preflight')
    store.write_report('preflight',{'checks':[dict(name='ok',passed=True,details='ok')]})
    store.complete_stage('preflight');store.start_stage('units')
    artifact=store.save_exclusive('production/duplicated-output.json',{'actual':'original'})
    stamp=ArtifactStamp.read(artifact).to_dict()
    outputs=dict(first=stamp,second=stamp)
    store.record_unit('units','batch_0001',status='running')
    cp=store.write_checkpoint('units','batch_0001',outputs=outputs)
    store.record_unit('units','batch_0001',status='completed',checkpoint_path=cp,outputs=outputs)
    return store,artifact


def test_one_snapshot_verifies_and_resolves_repeated_artifact_once(runtime_run,monkeypatch):
    import video_ai.runtime.production_state as module
    store,artifact=duplicated_stamp_store(runtime_run)
    reads=[];resolved=[]
    original_read=module.ArtifactStamp.read
    original_validate=module.PathPolicy.validate_write
    def read(cls,path):
        if str(path)==str(artifact):reads.append(str(path))
        return original_read(path)
    def validate(policy,path,category):
        if str(path)==str(artifact):resolved.append(str(path))
        return original_validate(policy,path,category)
    monkeypatch.setattr(module.ArtifactStamp,'read',classmethod(read))
    monkeypatch.setattr(module.PathPolicy,'validate_write',validate)
    store.snapshot()
    assert reads==[str(artifact)]
    assert resolved==[str(artifact)]
    store.snapshot()
    assert reads==[str(artifact),str(artifact)]
    assert resolved==[str(artifact),str(artifact)]


def test_snapshot_verification_cache_never_survives_between_calls(runtime_run):
    store,artifact=duplicated_stamp_store(runtime_run)
    store.snapshot()
    artifact.write_bytes(b'changed after the first snapshot')
    with pytest.raises(ValueError,match='stamp changed'):store.snapshot()


def test_same_path_with_different_stamp_is_rejected_within_one_validation(runtime_run):
    import video_ai.runtime.production_state as module
    store,artifact=duplicated_stamp_store(runtime_run)
    data=store.snapshot();row=data['units']['units']['batch_0001']
    cp=module.read_json(Path(row['checkpoint_path']))
    cp['outputs']['second']=dict(cp['outputs']['second'],bytes=cp['outputs']['second']['bytes']+1)
    with pytest.raises(ValueError,match='stamp changed'):
        module.validate_checkpoint(cp,store.run_dir,'units','batch_0001')
    # A failed validation must also discard its successfully verified prefix.
    artifact.write_bytes(b'changed after rejected checkpoint')
    with pytest.raises(ValueError,match='stamp changed'):store.snapshot()
