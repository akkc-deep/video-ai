import json
from pathlib import Path
import pytest


def test_create_manifest_integrity_mode_preserves_default_and_skips_old_tree(runtime_run, monkeypatch):
    import video_ai.runtime.manifest as module
    run, config, paths = runtime_run
    calls = []
    def forbidden(*args):
        calls.append(args)
        raise ValueError('historical tree should not be consumed')
    monkeypatch.setattr(module, '_validate', forbidden)
    store = module.create_manifest(run, config, inputs={}, models={}, workflows={}, verify_integrity=False)
    assert store.verify_integrity is False
    store.record_stage('preflight', 'running')
    assert not calls
    with pytest.raises(ValueError, match='historical tree'):
        module.ManifestStore.open(run)
    with pytest.raises(ValueError):
        module.create_manifest(run, config, inputs={}, models={}, workflows={}, verify_integrity=1)


@pytest.mark.parametrize('optional',[(),('image',),('shot_attempt',),('image','shot_attempt')])
def test_optional_groups_remain_lazy_and_protect_terminal_attempts(run_store,optional):
    from video_ai.runtime.manifest import ManifestStore
    for kind in optional:
        uid='shot_0001:attempt_0001' if kind=='shot_attempt' else 'shot_0001'
        run_store.record_unit(kind,uid,'running')
        run_store.record_unit(kind,uid,'completed')
    assert set(ManifestStore.open(run_store.run_dir).snapshot()['units'])=={'speech','shot','frame',*optional}
    for kind in optional:
        uid='shot_0001:attempt_0001' if kind=='shot_attempt' else 'shot_0001'
        with pytest.raises(ValueError):run_store.record_unit(kind,uid,'running')
        with pytest.raises(ValueError):run_store.update(lambda d:d['units'].pop(kind))
        with pytest.raises(ValueError):run_store.update(lambda d:d['units'][kind].pop(uid))


@pytest.mark.parametrize('uid',['shot_0000:attempt_0001','shot_0001:attempt_0000','shot_0001:attempt_1','shot_00001:attempt_0001','shot_0001:attempt_00001','shot_0001','shot_0001:frame_000001'])
def test_attempt_ids_require_strict_positive_four_digits(run_store,uid):
    with pytest.raises(ValueError):run_store.record_unit('shot_attempt',uid,'running')


def test_image_group_is_lazy_and_cannot_be_removed(run_store):
    from video_ai.runtime.manifest import ManifestStore
    assert set(run_store.snapshot()['units']) == {'speech', 'shot', 'frame'}
    run_store.record_unit('image', 'shot_0001', 'running')
    assert ManifestStore.open(run_store.run_dir).snapshot()['units']['image']['shot_0001']['status'] == 'running'
    run_store.record_unit('shot', 'shot_0001', 'running')
    for group in ('speech', 'shot', 'frame', 'image'):
        with pytest.raises(ValueError):
            run_store.update(lambda d: d['units'].pop(group))
    with pytest.raises(ValueError):
        run_store.update(lambda d: d['units']['image'].pop('shot_0001'))



def test_snapshot_and_state_roundtrip(runtime_run):
    from video_ai.runtime.manifest import create_manifest, ManifestStore, FileIdentity, hash_file
    run, config, paths = runtime_run
    source = run / 'script.txt'
    source.write_text('原文', encoding='utf-8')
    identity = hash_file(source)
    store = create_manifest(run, config, inputs={'script': identity},
                            models={'sdxl': FileIdentity(str(config.models['sdxl']), None, None, None, None)}, workflows={})
    snap = store.snapshot()
    assert snap['inputs']['script']['bytes'] == 6
    assert len(snap['inputs']['script']['sha256']) == 64
    assert snap['models']['sdxl']['sha256'] is None
    assert snap['config_snapshot']['raw']['media']['profile'] == 'fast'
    assert snap['config_snapshot']['resolved']['media']['profile']['width'] == 768
    assert snap['voice_snapshot']['path'] == str(config.voice.config_file)
    snap['stages']['speech']['status'] = 'failed'
    assert store.snapshot()['stages']['speech']['status'] == 'pending'
    store.record_stage('speech', 'running')
    store.record_unit('speech', 'speech_0001', 'running')
    artifact = {'path': str(source), 'category': 'run', 'bytes': 6, 'sha256': identity.sha256, 'verified_at': identity.verified_at}
    store.record_unit('speech', 'speech_0001', 'completed', artifacts=[artifact])
    store.record_stage('speech', 'completed', artifacts=[artifact])
    assert ManifestStore.open(run).snapshot() == store.snapshot()
    store.record_stage('speech', 'completed', artifacts=[artifact])
    with pytest.raises(ValueError):
        store.record_stage('speech', 'running')


@pytest.mark.parametrize('failure', ['replace', 'fsync'])
def test_failed_atomic_write_preserves_old_file(run_store, monkeypatch, failure):
    import video_ai.runtime.manifest as module
    path = run_store.run_dir / 'manifest.json'
    before = path.read_bytes()
    def fail(*args):
        raise OSError('injected disk failure')
    monkeypatch.setattr(module.os, failure, fail)
    with pytest.raises(OSError):
        run_store.record_stage('speech', 'running')
    assert path.read_bytes() == before
    assert run_store.snapshot()['stages']['speech']['status'] == 'pending'
    assert list(run_store.run_dir.glob('manifest.*.tmp'))
    assert not (run_store.run_dir / '.manifest.lock').exists()


def test_existing_lock_is_not_claimed_or_removed(run_store):
    from video_ai.runtime.manifest import ManifestBusyError
    lock = run_store.run_dir / '.manifest.lock'
    lock.write_text('external owner', encoding='utf-8')
    with pytest.raises(ManifestBusyError):
        run_store.record_stage('speech', 'running')
    assert lock.read_text() == 'external owner'


@pytest.mark.parametrize('change', [
    lambda d: d.update(schema_version=True),
    lambda d: d.update(run_id='../escape'),
    lambda d: d['stages']['speech'].update(status='invented'),
    lambda d: d['stages']['speech'].update(artifacts=[{'path':'C:/escape.wav','category':'run','bytes':0,'sha256':None,'verified_at':None}]),
    lambda d: d['units']['shot'].update({'../bad': {'status':'pending'}}),
    lambda d: d['models'].update({'x':{'path':'relative','bytes':None,'mtime_ns':None,'sha256':None,'verified_at':None}}),
])
def test_open_rejects_corrupt_record(run_store, change):
    from video_ai.runtime.manifest import ManifestStore
    data = run_store.snapshot()
    change(data)
    (run_store.run_dir / 'manifest.json').write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError):
        ManifestStore.open(run_store.run_dir)


@pytest.mark.parametrize('kind,unit', [('shot','shot_0000'),('speech','a/b'),('frame','shot_0001:frame_000000'),('frame','bad:frame_000001')])
def test_invalid_unit_ids_rejected(run_store, kind, unit):
    with pytest.raises(ValueError):
        run_store.record_unit(kind, unit, 'running')


def test_update_reloads_latest_cross_store_state(run_store):
    from video_ai.runtime.manifest import ManifestStore
    other = ManifestStore.open(run_store.run_dir)
    run_store.record_stage('speech', 'running')
    other.record_stage('timeline', 'running')
    assert run_store.snapshot()['stages']['speech']['status'] == 'running'
    assert run_store.snapshot()['stages']['timeline']['status'] == 'running'


@pytest.mark.parametrize('change',[
    lambda d:d['config_snapshot']['resolved'].update(output_root='C:/escape'),
    lambda d:d['services'].update(comfyui={'name':'comfyui','url':'http://127.0.0.1:8188','owned':'yes','pid':'bad','started_at':None,'status':'healthy','updated_at':d['updated_at'],'stdout_path':'C:/escape'}),
    lambda d:d['resources'].update(latest={'status':'verified','external_pids':['bad']}),
    lambda d:d['events'].append({'time':d['updated_at'],'stage':'speech','unit_id':None,'action':'bad','evidence_paths':'not-a-list'}),
])
def test_open_rejects_nested_service_resource_and_config_corruption(run_store,change):
    from video_ai.runtime.manifest import ManifestStore
    data=run_store.snapshot()
    change(data)
    (run_store.run_dir/'manifest.json').write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError):ManifestStore.open(run_store.run_dir)


def test_writer_does_not_delete_replaced_lock(run_store):
    from video_ai.runtime.manifest import ManifestBusyError
    lock=run_store.run_dir/'.manifest.lock'
    def replace_owner(data):
        lock.write_text('{"token":"other"}',encoding='utf-8')
    try:
        with pytest.raises(ManifestBusyError):run_store.update(replace_owner)
        assert lock.read_text()=='{"token":"other"}'
    finally:lock.unlink()


def test_false_traceback_path_is_still_invalid(run_store):
    from video_ai.runtime.manifest import ManifestStore
    data=run_store.snapshot()
    data['stages']['speech']['error']={'kind':'failed','message':'bad','traceback_path':False,'evidence_paths':[]}
    (run_store.run_dir/'manifest.json').write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError):ManifestStore.open(run_store.run_dir)


def test_saved_submission_cannot_be_cleared_for_repost(run_store):
    from uuid import uuid4
    request=run_store.run_dir/'request.json'
    request.write_text('{}',encoding='utf-8')
    record={'attempt_id':str(uuid4()),'client_id':str(uuid4()),'state':'intent','request_path':str(request),'response_path':None,'prompt_id':None,'number':None,'submitted_at':run_store.snapshot()['created_at'],'last_seen_at':None}
    run_store.record_unit('shot','shot_0001','running',submission=record)
    with pytest.raises(ValueError):
        run_store.update(lambda data:data['units']['shot']['shot_0001'].update(submission=None))


def test_manifest_update_always_preserves_event_history(run_store):
    before=run_store.snapshot()
    run_store.update(lambda data:data['resources'].update(latest={'status':'unverified','external_pids':[]}))
    after=run_store.snapshot()
    assert len(after['events'])==len(before['events'])+1
    assert after['events'][-1]['action']=='manifest_update'
def test_old_media_snapshot_preserved_when_timeline_updates(run_store):
    import json
    from video_ai.runtime.manifest import ManifestStore
    path=run_store.run_dir/'manifest.json'
    data=run_store.snapshot()
    data['config_snapshot']['resolved']['media'].pop('timeline',None)
    path.write_text(json.dumps(data),encoding='utf-8')
    old=data['config_snapshot']
    store=ManifestStore.open(run_store.run_dir)
    store.record_stage('timeline','running')
    assert store.snapshot()['config_snapshot']==old


def test_unknown_media_snapshot_rejected(run_store):
    import json
    from video_ai.runtime.manifest import ManifestStore
    path=run_store.run_dir/'manifest.json'
    data=run_store.snapshot()
    data['config_snapshot']['resolved']['media']['unknown']=1
    path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError):ManifestStore.open(run_store.run_dir)
