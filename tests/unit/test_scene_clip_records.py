from pathlib import Path
from types import SimpleNamespace

import pytest
from unit.test_scene_clip_observations import observation_context, authored, expected_context, NOW


def test_scene_store_immutable_atomic_and_exact_artifact(runtime_run):
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from video_ai.runtime.production_state import RunLock
    run, _, paths = runtime_run
    frozen = SimpleNamespace(options={'run_id': run.name})
    with RunLock(run) as held:
        store = SceneClipStore(frozen, run, paths=paths, lock=held)
        target = store.write_bytes('sample.bin', b'original')
        identity = store.artifact(target)
        assert store.validate_artifact(identity) == target
        assert set(identity) == {'path', 'bytes', 'sha256'}
        assert store.write('record.json', {'identity': identity}).exists()
        assert store.write('record.json', {'identity': identity}).exists()
        with pytest.raises(ValueError): store.write('record.json', {'identity': None})
        target.write_bytes(b'modified')
        with pytest.raises(ValueError): store.validate_artifact(identity)


def test_scene_store_refuses_path_escape_and_lost_lock(runtime_run):
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from video_ai.runtime.production_state import RunLock
    run, _, paths = runtime_run
    frozen = SimpleNamespace(options={'run_id': run.name})
    with RunLock(run) as held:
        store = SceneClipStore(frozen, run, paths=paths, lock=held)
        with pytest.raises(ValueError): store.write('../escape.json', {})
        with pytest.raises(ValueError): store.validate_artifact(dict(path=str(run/'x'), bytes=True, sha256='a'*64))
        held.path.write_text('{}', encoding='utf-8')
        with pytest.raises(ValueError): store.write('late.json', {})
        held.path.write_text(__import__('json').dumps(held.owner), encoding='utf-8')
    assert not (run/'production/scene-clips/late.json').exists()


def test_required_media_receipt_cannot_be_missing(runtime_run):
    from video_ai.runtime.scene_clip_records import SceneClipStore,validate_media_receipt
    run,_,paths=runtime_run
    store=SceneClipStore(SimpleNamespace(options={'run_id':run.name}),run,paths=paths,clip_ids=['scene_0001_clip_0001'])
    with pytest.raises(ValueError,match='receipt'):
        validate_media_receipt(store,store.clip_dir('scene_0001_clip_0001'),'generated',required=True)


@pytest.mark.parametrize('verdict',['failed','unverified'])
def test_accepted_observation_cannot_be_poisoned(verdict):
    from video_ai.runtime.production_scene_clips import _check_observation_replacement
    from video_ai.planning.production_scenes import canonical_digest
    original={'verdict':'passed','reason':'actual playback'}
    record={'rejected':None,'accepted':{'observation_sha256':canonical_digest(original)}}
    with pytest.raises(ValueError,match='accepted'):
        _check_observation_replacement(record,dict(original,verdict=verdict))


def test_stale_owned_service_reconciles_only_proven_dead_pid(monkeypatch):
    from video_ai.runtime.production_scene_clips import _reconcile_service_ownership
    state={'services':{'comfyui':dict(owned=True,status='healthy',pid=424242)}}
    manifest=SimpleNamespace(snapshot=lambda:state,update=lambda fn:fn(state))
    monkeypatch.setattr('video_ai.runtime.production_state.process_started_at',lambda pid:None)
    _reconcile_service_ownership(manifest,lambda:None)
    assert state['services']['comfyui']['status']=='stopped'
    state['services']['comfyui']['status']='healthy'
    monkeypatch.setattr('video_ai.runtime.production_state.process_started_at',lambda pid:'live-pid')
    with pytest.raises(ValueError,match='ownership'):
        _reconcile_service_ownership(manifest,lambda:None)
    assert state['services']['comfyui']['status']=='healthy'


def test_scene_conversion_can_retry_before_preparation_receipt(runtime_run):
    from video_ai.media.images import adapt_image
    from video_ai.runtime.logging import RunLogger
    from image_helpers import write_png
    run,config,paths=runtime_run
    source=write_png(run/'original.png',32,18)
    kwargs=dict(width=768,height=432,config=config,paths=paths,logger=RunLogger(run,production=True),
                unit_id='scene_0001_clip_0001',stage='source_clips')
    adapt_image(source,run/'first-staging.png',**kwargs)
    adapt_image(source,run/'second-staging.png',**kwargs)
    assert (run/'second-staging.png').exists()


def test_media_preparation_resumes_only_bound_staging_and_recipe(runtime_run):
    from video_ai.runtime.scene_clip_records import SceneClipStore,validate_media_receipt
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.manifest import now
    run,_,paths=runtime_run;cid='scene_0001_clip_0001'
    with RunLock(run) as held:
        store=SceneClipStore(SimpleNamespace(options={'run_id':run.name}),run,paths=paths,lock=held,clip_ids=[cid])
        folder=store.clip_dir(cid)
        # identity_copy_v1 preserves the original bytes before promotion.
        source=store.artifact(store.write_bytes('original.bin',b'exact derived media'))
        staging=store.artifact(store.write_bytes(folder/'staging/unique/generated.mp4',b'exact derived media'))
        target=folder/'generated.mp4';recipe=dict(algorithm='identity_copy_v1',parameters={})
        receipt=dict(schema_version=2,run_id=run.name,clip_id=cid,operation='generated',source=source,staging=staging,
                     target=dict(staging,path=str(target)),recipe=recipe,evidence=[],created_at=now())
        store.write(folder/'media-ready/generated.json',receipt)
        with pytest.raises(ValueError,match='promotion'):
            validate_media_receipt(store,folder,'generated',source=source,target=target,recipe=recipe,required=True)
        validate_media_receipt(store,folder,'generated',source=source,target=target,recipe=recipe,required=True,promote=True)
        assert target.read_bytes()==b'exact derived media'
        assert not Path(staging['path']).exists()
        validate_media_receipt(store,folder,'generated',source=source,target=target,recipe=recipe,required=True,promote=True)
        with pytest.raises(ValueError,match='recipe'):
            validate_media_receipt(store,folder,'generated',recipe=dict(algorithm='other',parameters={}),required=True)
        target.write_bytes(b'changed')
        with pytest.raises(ValueError): validate_media_receipt(store,folder,'generated',required=True,promote=True)


def test_global_guard_rejects_changed_dependency_bytes_and_inventory(runtime_run):
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from video_ai.runtime.production_state import RunLock
    run,_,paths=runtime_run
    with RunLock(run) as held:
        store=SceneClipStore(SimpleNamespace(options={'model_stamps':{}}),run,paths=paths,lock=held)
        path=store.write('upstream/original.json',{'accepted':'original'})
        store.guard_paths[str(path)]=store.artifact(path)
        store.guard_directories[str(path.parent)]={str(path)}
        store.verify_global()
        original=path.read_bytes();path.write_text('{}',encoding='utf-8')
        with pytest.raises(ValueError):store.verify_global()
        path.write_bytes(original)
        store.write('upstream/added.json',{})
        with pytest.raises(ValueError,match='inventory'):store.verify_global()


def test_parent_observation_context_projects_exact_public_record_fields():
    from video_ai.runtime.scene_clip_records import observation_parent_records
    parent=dict(clip={'clip_id':'scene_0001_clip_0001'},mapping={'retained_frames':93},last_frame={},accepted={},
                request={},template={},rejected=None)
    assert observation_parent_records(parent)=={key:parent[key] for key in ('clip','mapping','last_frame','accepted')}
    assert observation_parent_records(None) is None


def test_observation_originals_retain_failed_conclusion_and_detect_tampering(observation_context,runtime_run):
    import hashlib
    import json
    from video_ai.runtime.scene_clip_records import SceneClipStore,scan_observation_sources
    from video_ai.runtime.production_state import RunLock
    frozen,clip,request,_,_=observation_context
    run,_,paths=runtime_run;cid=request['clip_id'];expected=expected_context(observation_context)
    value=authored(expected['template']);value['verdict']='failed';value['checks']['motion_process']='failed'
    value['issues']=[dict(check='motion_process',frames=[0,1],description='Observed motion failed')]
    raw=json.dumps(value,ensure_ascii=False).encode()
    with RunLock(run) as held:
        store=SceneClipStore(frozen,run,paths=paths,lock=held,clip_ids=[cid]);folder=store.clip_dir(cid)
        path=store.write_bytes(folder/'observations'/(hashlib.sha256(raw).hexdigest()+'.json'),raw)
        rows=scan_observation_sources(store,folder,expected['template'],clip['created_at'],now=NOW)
        assert len(rows)==1 and rows[0]['value']['verdict']=='failed'
        assert rows[0]['observation']==store.artifact(path)
        assert not (folder/'observation-rejected.json').exists()
        path.write_bytes(raw+b'changed')
        with pytest.raises(ValueError):scan_observation_sources(store,folder,expected['template'],clip['created_at'],now=NOW)


def test_actual_send_guard_checks_parent_observation_inventory(runtime_run):
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from video_ai.runtime.production_state import RunLock
    run,_,paths=runtime_run;parent='scene_0001_clip_0001';child='scene_0001_clip_0002'
    with RunLock(run) as held:
        store=SceneClipStore(SimpleNamespace(options={'model_stamps':{}}),run,paths=paths,lock=held,clip_ids=[parent,child])
        store.write('inputs.json',{})
        folder=store.clip_dir(child);pf=store.clip_dir(parent)
        request=dict(clip_id=child,parent={'clip_id':parent});graph={}
        store.write(folder/'request.json',request);store.write(folder/'graph.json',graph);store.write(folder/'input.json',{})
        store.write(pf/'clip.json',{});store.write(pf/'last-frame.json',{})
        original=store.write(pf/'observations/original.json',{})
        store.write(pf/'observation-accepted.json',{'observation':store.artifact(original)})
        guard=store.capture_guard(request,graph);guard()
        store.write(pf/'observations/new.json',{})
        with pytest.raises(ValueError,match='inventory'):guard()
