"""Revision proofs bind bytes, ownership and scope; readers never repair them."""
from types import SimpleNamespace
from pathlib import Path

import pytest


def test_revision_guard_rejects_changed_origin_bytes_even_with_restored_stat(runtime_run):
    import os
    from video_ai.runtime.scene_revision_records import RevisionGuard, artifact
    run, _, _ = runtime_run
    source = run/'original.json'; source.write_bytes(b'{"value":1}')
    stamp = source.stat()
    frozen = SimpleNamespace(options={'script_path':str(run/'production/script.txt'), 'model_stamps':{}})
    guard = RevisionGuard(frozen)
    guard.capture(source, root=run)
    guard.verify_captured_bytes()
    source.write_bytes(b'{"value":2}')
    os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    with pytest.raises(ValueError, match='changed|differs'): guard.verify_captured_bytes()


@pytest.mark.parametrize('mutation', ['empty_log','inventory','absent','local_copy'])
def test_revision_guard_rechecks_empty_logs_inventories_absence_and_local_copy(runtime_run, mutation):
    from video_ai.runtime.scene_revision_records import RevisionGuard
    run, _, _ = runtime_run
    folder = run/'origin'; folder.mkdir()
    log = folder/'command.log'; log.write_bytes(b'')
    local = run/'local.png'; local.write_bytes(b'original bytes')
    absent = folder/'observation-rejected.json'
    frozen = SimpleNamespace(options={'script_path':str(run/'production/script.txt'), 'model_stamps':{}})
    guard = RevisionGuard(frozen)
    guard.capture(log, root=run, allow_empty=True)
    guard.capture(local, root=run)
    guard.capture_directory(folder, root=run)
    guard.capture_absent(absent, root=run)
    guard.verify_captured_bytes()
    if mutation=='empty_log': log.write_bytes(b'later output')
    elif mutation=='inventory': (folder/'new.json').write_text('{}')
    elif mutation=='absent': absent.write_text('{}')
    else: local.write_bytes(b'changed bytes')
    with pytest.raises(ValueError): guard.verify_captured_bytes()


def test_unregistered_external_view_is_not_inherited(runtime_run):
    from video_ai.runtime.scene_revision_records import RevisionGuard
    run, _, _ = runtime_run
    frozen = SimpleNamespace(options={'script_path':str(run/'production/script.txt'), 'model_stamps':{}})
    guard = RevisionGuard(frozen)
    assert not guard.is_registered({'path':'D:/VideoSi/unrelated.png','bytes':1,'sha256':'a'*64})


def test_unfrozen_sidecar_cannot_enable_import(runtime_run):
    from video_ai.runtime.scene_revision_records import require_scene_revision
    run, _, _ = runtime_run
    folder = run/'production/scene-revision/imports'; folder.mkdir(parents=True)
    (folder/'fake.json').write_text('{}')
    frozen = SimpleNamespace(options={'script_path':str(run/'production/script.txt')})
    with pytest.raises(ValueError, match='frozen|revision'): require_scene_revision(frozen)


def test_guard_registration_compares_the_full_view_and_not_external_path_prefix(runtime_run):
    from video_ai.runtime.scene_revision_records import RevisionGuard
    run, _, _ = runtime_run
    frozen = SimpleNamespace(options={'script_path':str(run/'production/script.txt'), 'model_stamps':{}})
    guard = RevisionGuard(frozen)
    view = {'clip_id':'scene_0001_clip_0001','media':{'path':'D:/VideoSi/source.mp4','sha256':'a'*64}}
    guard.register('clip:scene_0001_clip_0001', view)
    assert guard.is_registered(view)
    assert not guard.is_registered(dict(view,clip_id='scene_0001_clip_0002'))


def test_registered_aliases_share_only_the_same_proven_import(runtime_run):
    from video_ai.runtime.scene_revision_records import RevisionGuard
    run,_,_=runtime_run
    guard=RevisionGuard(SimpleNamespace(options={'script_path':str(run/'production/script.txt')}))
    view={'original':'same immutable subtree'}
    guard.register('clip:scene_0001_clip_0001#request',view)
    guard.register('clip:scene_0001_clip_0001#comparison',view)
    assert guard.is_registered(view)
    with pytest.raises(ValueError,match='ambiguous'):
        guard.register('clip:scene_0002_clip_0001#comparison',view)


def test_guard_cannot_rebaseline_a_captured_path(runtime_run):
    from video_ai.runtime.scene_revision_records import RevisionGuard
    run, _, _ = runtime_run
    path = run/'origin.json'; path.write_text('{"v":1}')
    frozen = SimpleNamespace(options={'script_path':str(run/'production/script.txt'), 'model_stamps':{}})
    guard = RevisionGuard(frozen)
    guard.capture(path, root=run)
    path.write_text('{"v":2}')
    with pytest.raises(ValueError): guard.capture(path, root=run)


@pytest.mark.parametrize('point',['copy-intent','copy-staging','copy-ready','copy-promoted'])
def test_identity_copy_recovers_without_taking_unowned_staging(runtime_run,monkeypatch,point):
    import video_ai.runtime._scene_revision_copy as copying
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.scene_revision_records import RevisionGuard,artifact
    run,_,_ = runtime_run
    source = run/'original.png'; source.write_bytes(b'original media bytes')
    frozen = SimpleNamespace(options={'script_path':str(run/'production/script.txt'),'model_stamps':{}})
    guard = RevisionGuard(frozen); bound = guard.capture(source,root=run)
    with RunLock(run) as held:
        store = copying.RevisionStore(run,held)
        raised = []
        def interrupt(event):
            if event==point and not raised: raised.append(event); raise KeyboardInterrupt(event)
        monkeypatch.setattr(copying,'boundary',interrupt)
        with pytest.raises(KeyboardInterrupt):
            copying.copy_identity(store,'image:scene_0001','image','scene_0001','candidate_000001',bound,guard=guard)
        abandoned = set(store.root.glob('staging/*'))
        monkeypatch.setattr(copying,'boundary',lambda event:None)
        result = copying.copy_identity(store,'image:scene_0001','image','scene_0001','candidate_000001',bound,guard=guard)
        assert Path(result['path']).read_bytes()==source.read_bytes()
        if point=='copy-staging': assert all(p.exists() for p in abandoned)
        assert copying.copy_identity(store,'image:scene_0001','image','scene_0001','candidate_000001',bound,guard=guard)==result


def test_same_byte_replacement_cannot_take_owned_revision_target(runtime_run):
    from pathlib import Path
    from video_ai.runtime._scene_revision_copy import RevisionStore,copy_identity
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.scene_revision_records import RevisionGuard
    run,_,_ = runtime_run
    source = run/'original.png'; source.write_bytes(b'original bytes')
    guard = RevisionGuard(SimpleNamespace(options={'script_path':str(run/'production/script.txt'),'model_stamps':{}}))
    bound = guard.capture(source,root=run)
    with RunLock(run) as held:
        store = RevisionStore(run,held)
        result = copy_identity(store,'image:s1','image','s1','output',bound,guard=guard)
        path = Path(result['path']); path.rename(path.with_suffix('.old'))
        path.write_bytes(source.read_bytes())
        with pytest.raises(ValueError,match='ownership'):
            copy_identity(store,'image:s1','image','s1','output',bound,guard=guard)


def test_revision_store_refuses_writes_from_noncaller_thread(runtime_run):
    from concurrent.futures import ThreadPoolExecutor
    from video_ai.runtime._scene_revision_copy import RevisionStore
    from video_ai.runtime.production_state import RunLock
    run,_,_ = runtime_run
    with RunLock(run) as held:
        store = RevisionStore(run,held)
        with ThreadPoolExecutor(max_workers=1) as worker:
            with pytest.raises(ValueError,match='thread'):
                worker.submit(store.save,'late.json',{'late':True}).result()
    assert not (run/'production/scene-revision/late.json').exists()


@pytest.mark.parametrize('module_name', ['jimeng_candidates','production_image_selection','production_reference_images'])
def test_image_writers_recheck_revision_guard_before_writing(runtime_run,module_name):
    import importlib
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.scene_revision_records import RevisionGuard
    run,_,_=runtime_run
    path=run/'origin.json';path.write_bytes(b'original')
    guard=RevisionGuard(SimpleNamespace(options={'script_path':str(run/'production/script.txt'),'model_stamps':{}}))
    guard.capture(path,root=run)
    with RunLock(run) as held:
        store=importlib.import_module('video_ai.runtime.'+module_name)._Records(run,held)
        store.revision_guard=guard
        path.write_bytes(b'changed!')
        with pytest.raises(ValueError):store.owned()


def test_image_decode_cache_is_one_invocation_and_rehashes_actual_bytes(runtime_run,monkeypatch):
    import json
    import os
    from types import SimpleNamespace
    import video_ai.runtime.image_selection_records as images
    from video_ai.runtime.scene_revision_records import revision_scope
    run,_,_=runtime_run
    path=run/'image.png';path.write_bytes(b'first image bytes')
    frozen=SimpleNamespace(config=SimpleNamespace(tools={'ffprobe':Path('D:/VideoSi/tools/ffmpeg/bin/ffprobe.exe'),
                                                        'ffmpeg':Path('D:/VideoSi/tools/ffmpeg/bin/ffmpeg.exe')}))
    calls=[]
    def command(args,**kwargs):
        calls.append(args)
        body=json.dumps({'streams':[dict(codec_type='video',nb_read_frames='1',codec_name='png',width=2,height=2)]}).encode() if args[0].endswith('ffprobe.exe') else b''
        return SimpleNamespace(returncode=0,stdout=body)
    monkeypatch.setattr(images.subprocess,'run',command)
    with revision_scope():
        images._inspect_original(frozen,path);images._inspect_original(frozen,path)
        assert len(calls)==2
        stamp=path.stat();path.write_bytes(b'other image bytes')
        os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        images._inspect_original(frozen,path)
        assert len(calls)==4
    with revision_scope():images._inspect_original(frozen,path)
    assert len(calls)==6


def test_target_reference_identity_uses_actual_target_storage_and_capability_bytes(tmp_path):
    import json
    from video_ai.runtime._scene_revision_reference import target_reference_digest
    from unit.test_reference_config import capability,storage_settings
    from unit.test_jimeng_config import image_settings
    from video_ai.jimeng_config import parse_image_generation
    from copy import deepcopy
    cap=capability();raw=json.dumps(cap).encode();storage=storage_settings()
    context=dict(values=dict(reference_generation=None,reference_capabilities={'jimeng_t2i_v40':'D:/deleted-cap.json'},reference_storage=storage),
        raws={'jimeng_t2i_v40':raw})
    config=SimpleNamespace(raw={},image_generation=parse_image_generation(image_settings(),'image_generation'))
    first=target_reference_digest(SimpleNamespace(config=config,options={}),context)
    assert first is not None
    changed=deepcopy(storage);changed['bucket']='another-test-bucket'
    config.raw={'reference_storage':changed}
    assert target_reference_digest(SimpleNamespace(config=config,options={}),context)!=first
    cap_path=tmp_path/'capability.json';cap_path.write_bytes(raw)
    config.raw={'reference_capabilities':{'jimeng_t2i_v40':str(cap_path)}}
    assert target_reference_digest(SimpleNamespace(config=config,options={}),context)==first
    cap['max_images']+=1;cap_path.write_text(json.dumps(cap),encoding='utf-8')
    assert target_reference_digest(SimpleNamespace(config=config,options={}),context)!=first


def test_reference_fallback_cannot_silently_keep_old_model_after_baseline_override():
    import json
    from video_ai.runtime._scene_revision_reference import target_reference_digest
    from unit.test_reference_config import capability,storage_settings
    from unit.test_jimeng_config import image_settings
    from video_ai.jimeng_config import parse_image_generation
    context=dict(values=dict(reference_generation=None,reference_capabilities={'jimeng_t2i_v40':'D:/deleted-cap.json'},reference_storage=storage_settings()),
        raws={'jimeng_t2i_v40':json.dumps(capability()).encode()})
    settings=image_settings();settings['req_key']='jimeng_t2i_v31'
    target=SimpleNamespace(config=SimpleNamespace(raw={},image_generation=parse_image_generation(settings,'image_generation')),options={})
    assert target_reference_digest(target,context) is None


def structural_revision(runtime_run,*,domain='common',schema_record=None):
    """Hash-consistent records isolate loader checks from semantic admission."""
    from uuid import uuid4
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.scene_revision_records import artifact,token
    from video_ai.runtime.production_state import json_bytes
    from video_ai.planning.production_scenes import canonical_digest
    from unit.test_scene_revision import revision_fixture
    run,_,paths=runtime_run;source=create_run(paths);root=run/'production/scene-revision'
    def save(path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(json_bytes(value));return artifact(path)
    source_options=save(source/'production/options.json',{})
    from video_ai.planning.scene_revision import plan_scene_revision
    snapshot,request,identity=revision_fixture();rid=str(uuid4());created='2026-10-19T00:00:00+00:00'
    snapshot['source_options']['run_id']=source.name
    request.update(revision_id=rid,source_run_id=source.name,source_options_sha256=source_options['sha256'],requested_at=created)
    view={'units':{},'timeline':{}} if domain=='common' else {'bible':{},'scene_plan':{}}
    view_artifact=save(root/'views'/domain/(token(domain,'all')+'.json'),view)
    sidecar=dict(schema_version=2.0 if schema_record=='sidecar' else 2,production_strategy='paragraph_jimeng_v1',
        run_id=run.name,import_id=domain+':all',domain=domain,key='all',source_run_id=source.name,
        source_options_sha256=source_options['sha256'],source_identity_sha256=canonical_digest(view),
        dependency_import_ids=[],source_json_snapshot=dict(files=[],inventories=[],absent_paths=[]),
        raw_files=[],source_artifacts=[],local_artifacts=[],view=view,view_sha256=canonical_digest(view),view_artifact=view_artifact,created_at=created)
    imported=save(root/'imports'/(token(domain,'all')+'.json'),sidecar)
    index=save(root/'imports.json',dict(schema_version=2.0 if schema_record=='index' else 2,
        production_strategy='paragraph_jimeng_v1',run_id=run.name,revision_id=rid,imports=[imported]))
    invalidation=save(root/'invalidation.json',plan_scene_revision(snapshot,request,identity))
    commit=save(root/'commit.json',dict(schema_version=2,production_strategy='paragraph_jimeng_v1',run_id=run.name,revision_id=rid,
        source_run_id=source.name,source_run_dir=str(source),source_options=source_options,request=save(root/'request.json',request),
        target_identity=identity,invalidation=invalidation,imports=index,created_at=created))
    return dict(scene_revision=commit),run


@pytest.mark.parametrize('record',['index','sidecar'])
def test_hash_consistent_revision_rejects_float_schema_in_nested_records(runtime_run,record):
    from video_ai.runtime.scene_revision_records import validate_revision_structure
    options,run=structural_revision(runtime_run,schema_record=record)
    with pytest.raises(ValueError,match='schema|identity'):validate_revision_structure(options,run)


def test_hash_consistent_plan_import_cannot_omit_its_common_dependency(runtime_run):
    from video_ai.runtime.scene_revision_records import validate_revision_structure
    options,run=structural_revision(runtime_run,domain='plan')
    with pytest.raises(ValueError,match='dependency|ancestor|common'):validate_revision_structure(options,run)


def test_copy_refuses_orphan_ready_before_starting_another_role(runtime_run):
    from video_ai.runtime._scene_revision_copy import RevisionStore,copy_identity
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.scene_revision_records import RevisionGuard
    run,_,_=runtime_run;source=run/'original.png';source.write_bytes(b'original')
    guard=RevisionGuard(SimpleNamespace(options={'script_path':str(run/'production/script.txt'),'model_stamps':{}}))
    bound=guard.capture(source,root=run)
    orphan=run/'production/scene-revision/copy-ready/orphan/other.json';orphan.parent.mkdir(parents=True);orphan.write_text('{}')
    with RunLock(run) as held:
        with pytest.raises(ValueError):copy_identity(RevisionStore(run,held),'image:s1','image','s1','output',bound,guard=guard)
    assert not (run/'production/scene-revision/copy-intents').exists()


def test_native_decode_cache_shared_only_inside_invocation_and_rechecks_bytes(runtime_run,monkeypatch):
    import video_ai.runtime.scene_clip_records as clips
    from video_ai.runtime.scene_revision_records import revision_scope,artifact
    run,config,_=runtime_run
    generated=run/'generated.mp4';generated.write_bytes(b'original video')
    image=run/'last.png';image.write_bytes(b'original PNG')
    frozen=SimpleNamespace(options={'script_path':str(run/'production/script.txt')},config=config)
    calls=[]
    def decode(*args,**kwargs):calls.append(args);return SimpleNamespace(returncode=0,stdout=b'\0\0\0')
    monkeypatch.setattr(clips.subprocess,'run',decode)
    def validate():
        store=clips.SceneClipStore(frozen,run)
        clips._verify_native_pixels(store,artifact(generated),artifact(image),0,1,1)
    with revision_scope():
        validate();validate()
        assert len(calls)==2
        image.write_bytes(b'changed PNG');validate()
        assert len(calls)==4
    with revision_scope():validate()
    assert len(calls)==6


def test_origin_image_metadata_scope_never_claims_a_json_record_as_media(runtime_run):
    from video_ai.runtime.scene_revision_records import artifact
    from video_ai.runtime.scene_clip_records import SceneClipStore
    from video_ai.runtime._scene_revision_origin_images import origin_image_scope
    run,config,_=runtime_run
    path=run/'production/jimeng/scene_0001/request_01/accepted.json';path.parent.mkdir(parents=True);path.write_text('{}')
    frozen=SimpleNamespace(options={'script_path':str(run/'production/script.txt')},config=config)
    with origin_image_scope(frozen,['scene_0003']):
        assert SceneClipStore(frozen,run).validate_artifact(artifact(path))==path


def test_original_generated_identity_receipt_cannot_claim_different_model_bytes(runtime_run):
    from video_ai.runtime.scene_clip_records import SceneClipStore,validate_media_receipt
    from video_ai.runtime.scene_revision_records import artifact
    from video_ai.runtime.production_state import json_bytes
    from video_ai.runtime.manifest import now
    run,config,_=runtime_run;cid='scene_0001_clip_0001'
    folder=run/'production/scene-clips'/cid;folder.mkdir(parents=True)
    source=run/'comfy/output/model.mp4';source.parent.mkdir(parents=True);source.write_bytes(b'AAA')
    target=folder/'generated.mp4';target.write_bytes(b'BBB')
    staged=folder/'staging/attempt.mp4';value=artifact(target)
    ready=dict(schema_version=2,run_id=run.name,clip_id=cid,operation='generated',source=artifact(source),
        staging=dict(value,path=str(staged)),target=value,recipe=dict(algorithm='identity_copy_v1',parameters={}),evidence=[],created_at=now())
    path=folder/'media-ready/generated.json';path.parent.mkdir();path.write_bytes(json_bytes(ready))
    frozen=SimpleNamespace(options={'script_path':str(run/'production/script.txt')},config=config)
    with pytest.raises(ValueError,match='identity|copy|bytes'):
        validate_media_receipt(SceneClipStore(frozen,run,clip_ids=[cid]),folder,'generated',required=True)


def test_inherited_clip_reader_preserves_its_registered_import_identity(runtime_run,monkeypatch):
    from video_ai.runtime.scene_revision_records import RevisionGuard
    from video_ai.runtime._scene_revision_readers import inherited_clip_record
    import video_ai.runtime.production_inputs as inputs
    import video_ai.runtime._scene_revision_origins as origins
    run,_,_=runtime_run;cid='scene_0001_clip_0001'
    frozen=SimpleNamespace(options={'script_path':str(run/'production/script.txt'),'scene_revision':{}})
    guard=RevisionGuard(frozen);clip=dict(clip_id=cid,source={'sha256':'a'*64})
    guard.register('clip:'+cid,clip)
    sidecar=dict(view=clip,local_artifacts=[])
    proof=dict(guard=guard,source_run=run,imports={'clip:'+cid:(sidecar,{})})
    monkeypatch.setattr(inputs,'load_frozen_inputs',lambda path:frozen)
    monkeypatch.setattr(origins,'source_clip_record',lambda *args:dict(clip=clip,request={'request':'original'}))
    first=inherited_clip_record(frozen,cid,context=proof)
    assert first['clip']==clip and guard.is_registered(first['request'])
    assert inherited_clip_record(frozen,cid,context=proof)==first


def test_origin_media_context_reuse_rechecks_bytes_and_exact_ancestry(runtime_run,monkeypatch):
    import os
    from video_ai.runtime._scene_revision_origins import origin_media_context
    from video_ai.runtime.scene_revision_records import revision_scope,RevisionGuard
    import video_ai.runtime.scene_media_records as media
    run,_,_=runtime_run;path=run/'original-record.json';path.write_bytes(b'{"v":1}')
    frozen=SimpleNamespace(options={'script_path':str(run/'production/script.txt'),'model_stamps':{}},config=SimpleNamespace(raw={}))
    admissions=[]
    def admit(*args):
        guard=RevisionGuard(frozen);guard.capture(path,root=run)
        admissions.append(guard)
        return {'store':SimpleNamespace(verify_captured_bytes=guard.verify_captured_bytes,verify_tools=lambda:None)}
    monkeypatch.setattr(media,'scene_media_context',admit)
    def read(clips=('parent',)):
        return origin_media_context(frozen,{},None,scene_ids=('scene',),clip_ids=clips)
    with revision_scope():
        first=read();assert read() is first and len(admissions)==1
        assert read(('parent','child')) is not first and len(admissions)==2
        stamp=path.stat()
        path.write_bytes(b'{"v":2}');os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        with pytest.raises(ValueError):read()
        path.write_bytes(b'{"v":1}');os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    with revision_scope():read()
    assert len(admissions)==3


def test_inherited_frame_checks_one_complete_guard_per_lookup(runtime_run):
    from video_ai.runtime._scene_revision_readers import inherited_frame
    from video_ai.runtime.scene_revision_records import RevisionGuard
    run,_,_=runtime_run;fid='scene_0001_clip_0001:frame_000001';checks=[]
    frozen=SimpleNamespace(options={'scene_revision':{},'script_path':str(run/'production/script.txt')})
    row=dict(frame_id=fid,source={});value=dict(mapping={'frame_id':fid})
    guard=RevisionGuard(frozen);verify=guard.verify_captured_bytes
    def counted():checks.append(True);verify()
    guard.verify_captured_bytes=counted
    proof=dict(guard=guard,
        imports={'upscale:'+fid:({'view':value},{})})
    store=SimpleNamespace(frozen=frozen,revision_context=proof,frame_dir=lambda key:run/'no-owned-frame')
    assert inherited_frame({'store':store,'frozen':frozen},row)==value
    assert len(checks)==1


@pytest.mark.parametrize('reader',['revision','import'])
def test_cached_proof_is_bound_to_exact_frozen_options(runtime_run,reader):
    from video_ai.runtime.scene_revision_records import (RevisionGuard,revision_scope,_context,
        require_scene_revision,require_revision_import)
    run,_,_=runtime_run
    frozen=SimpleNamespace(options={'script_path':str(run/'production/script.txt'),'run_id':run.name,
        'scene_revision':{'sha256':'a'*64}})
    guard=RevisionGuard(frozen);view={'original':'registered image view'};guard.register('image:scene_0001',view)
    proof=dict(guard=guard,imports={'image:scene_0001':({'view':view},{})})
    changed=SimpleNamespace(options=dict(frozen.options,scene_revision={'sha256':'b'*64}))
    with revision_scope():
        _context.get()['validated'][str(run)]=proof
        with pytest.raises(ValueError):
            if reader=='revision':require_scene_revision(changed)
            else:require_revision_import(changed,'image','scene_0001',context=proof)
