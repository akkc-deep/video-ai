import json
from pathlib import Path

import pytest


def test_scene_clip_result_codes_and_exact_schema():
    from video_ai.runtime.production_scene_clips import SceneClipResult
    for status,code in [('awaiting_continuity_review',3),('source_clips_ready',0),('blocked',2),('failed',1),('interrupted',130)]:
        if status == 'source_clips_ready': continue
        result=SceneClipResult(status=status)
        assert result.exit_code==code
        assert set(result.to_dict())==set('schema_version production_strategy run_id run_dir status active_stage scenes observation_templates source_clips log_dir error'.split())
    with pytest.raises(ValueError): SceneClipResult(schema_version=True)
    with pytest.raises(ValueError): SceneClipResult(status='completed')
    with pytest.raises(ValueError): SceneClipResult(source_clips=Path('D:/unverified.json'))


def test_unaccepted_images_stop_before_any_service_or_wan(runtime_run,tmp_path):
    from integration.test_jimeng_reference_flow import prepared_baseline
    from video_ai.runtime.production_scene_clips import produce_scene_clips
    s=prepared_baseline(runtime_run,tmp_path,accept=False)
    def forbidden(*args,**kwargs): raise AssertionError('no service/client before global image admission')
    result=produce_scene_clips(s['frozen'],s['units'],s['timeline'],paths=s['paths'],logger=s['logger'],
                               client_factory=forbidden,service_factory=forbidden)
    assert result.status=='blocked',result.error
    assert result.source_clips is None
    assert not list((s['run']/'production/scene-clips').glob('*/intent.json'))
    assert not (s['run']/'.make-video.lock').exists()


def test_authentic_three_scene_first_clips_wait_then_complete_readonly(runtime_run,tmp_path,monkeypatch):
    from scene_clip_helpers import prepared_wan,OfflineWan,generate,admit_all
    from video_ai.runtime.scene_clip_records import require_scene_clip_acceptance
    s=prepared_wan(runtime_run,tmp_path,monkeypatch);backend=OfflineWan(s)
    first=generate(s,backend)
    assert first.status=='awaiting_continuity_review',first.error
    assert len(backend.posts)==3 and len(first.observation_templates)==3
    assert len({post['client_id'] for post in backend.posts})==3
    assert all(row['status']=='awaiting_continuity_review' for row in first.scenes)
    ready=admit_all(s,backend,result=first)
    assert ready.status=='source_clips_ready',ready.error
    complete=require_scene_clip_acceptance(s['frozen'],s['units'],s['timeline'])
    assert len(complete['clips'])==len(s['plan']['clips'])
    assert complete['total_frames']==s['timeline'].total_frames
    before=(len(backend.posts),len(backend.gets),backend.ensures,backend.closes,backend.factories)
    def forbidden(*args,**kwargs): raise AssertionError('complete replay must not encode or extract')
    monkeypatch.setattr('video_ai.media.video.trim_scene_video',forbidden)
    monkeypatch.setattr('video_ai.media.frames.extract_native_frame',forbidden)
    monkeypatch.setattr('video_ai.media.images.adapt_image',forbidden)
    assert generate(s,backend).status=='source_clips_ready'
    assert require_scene_clip_acceptance(s['frozen'],s['units'],s['timeline'])==complete
    assert before==(len(backend.posts),len(backend.gets),backend.ensures,backend.closes,backend.factories)
    assert not (s['run']/'.make-video.lock').exists()


def test_exact_200_frame_parent_chain_uses_original_retained_png_and_full_narration(runtime_run,tmp_path,monkeypatch):
    import hashlib
    from scene_clip_helpers import prepared_wan,OfflineWan,generate,observation,admit_all
    from video_ai.runtime.scene_clip_records import require_scene_clip_acceptance
    s=prepared_wan(runtime_run,tmp_path,monkeypatch,long_scene=True);backend=OfflineWan(s)
    first=generate(s,backend)
    assert first.status=='awaiting_continuity_review',first.error
    assert len(backend.posts)==3
    assert [Path(p).parent.name for p in first.observation_templates]==[
        'scene_0001_clip_0001','scene_0002_clip_0001','scene_0003_clip_0001']
    parent_folder=s['run']/'production/scene-clips/scene_0001_clip_0001'
    assert not (parent_folder.parent/'scene_0001_clip_0002/intent.json').exists()
    parent_png=parent_folder/'frame_000093.png'
    accepted,_,_=observation(s,first.observation_templates[0])
    assert accepted.status in ('awaiting_continuity_review','blocked'),accepted.error
    second=generate(s,backend)
    assert second.status=='awaiting_continuity_review',second.error
    assert len(backend.posts)==4
    child_folder=parent_folder.parent/'scene_0001_clip_0002'
    child_input=json.loads((child_folder/'input.json').read_text())
    assert Path(child_input['target']['path']).read_bytes()==parent_png.read_bytes()
    assert child_input['source']['sha256']==hashlib.sha256(parent_png.read_bytes()).hexdigest()
    assert child_input['rule']=='identity_png_copy_v1' and child_input['filter'] is None
    parent_request=json.loads((parent_folder/'request.json').read_text())
    child_request=json.loads((child_folder/'request.json').read_text())
    assert child_request['parameters']['positive']==parent_request['parameters']['positive']
    assert child_request['parent']['clip_id']=='scene_0001_clip_0001'
    assert backend.posts[-1]['prompt']['97']['inputs']['image']==f'{s["run"].name}/scene_clips/scene_0001_clip_0002/start.png'
    ready=admit_all(s,backend,result=second)
    assert ready.status=='source_clips_ready',ready.error
    complete=require_scene_clip_acceptance(s['frozen'],s['units'],s['timeline'])
    chain=[c for c in complete['clips'] if c['scene_id']=='scene_0001']
    assert [c['budget']['generated_frames'] for c in chain]==[93,93,17]
    assert [Path(c['last_frame']['image']['path']).name for c in chain]==[
        'frame_000093.png','frame_000093.png','frame_000016.png']
    assert [c['last_frame']['source_frame_index'] for c in chain]==[92,92,15]
    assert [r['output_frame'] for c in chain for r in c['frame_mapping']['output_to_generated']]==list(range(200))
    assert len(backend.posts)==len(s['plan']['clips'])==5
    for unit in s['timeline'].clips:
        rows=[b for c in complete['clips'] for b in c['narration_bindings'] if b['unit_id']==unit.unit_id]
        assert rows[0]['start_sample']==unit.start_sample and rows[-1]['end_sample']==unit.end_sample
        assert all(row['text']==unit.text for row in rows)
        assert sum(row['end_sample']-row['start_sample'] for row in rows)==unit.samples


@pytest.mark.parametrize('verdict', ['failed','unverified'])
def test_parent_process_gate_blocks_child_while_independent_scenes_finish(runtime_run,tmp_path,monkeypatch,verdict):
    from scene_clip_helpers import prepared_wan,OfflineWan,generate,observation
    s=prepared_wan(runtime_run,tmp_path,monkeypatch,long_scene=True);backend=OfflineWan(s)
    first=generate(s,backend)
    assert first.status=='awaiting_continuity_review',first.error
    result,_,_=observation(s,first.observation_templates[0],verdict=verdict)
    assert result.status==('blocked' if verdict=='failed' else 'awaiting_continuity_review'),result.error
    for template in first.observation_templates[1:]: observation(s,template)
    resumed=generate(s,backend)
    assert resumed.status==('blocked' if verdict=='failed' else 'awaiting_continuity_review'),resumed.error
    assert resumed.scenes[0]['status']==('continuity_failed' if verdict=='failed' else 'awaiting_continuity_review')
    assert all(row['status']=='ready' for row in resumed.scenes[1:])
    assert len(backend.posts)==3
    assert not (s['run']/'production/scene-clips/scene_0001_clip_0002/intent.json').exists()
    if verdict=='unverified':
        result,_,_=observation(s,first.observation_templates[0])
        assert result.status=='blocked',result.error  # Ready independent scenes, pending gated child.
        assert generate(s,backend).status=='awaiting_continuity_review'
        assert len(backend.posts)==4


def test_readonly_rejects_tampered_authentic_records_receipts_and_media(runtime_run,tmp_path,monkeypatch):
    from scene_clip_helpers import prepared_wan,OfflineWan,admit_all,generate
    from video_ai.runtime.scene_clip_records import require_scene_clip_acceptance
    s=prepared_wan(runtime_run,tmp_path,monkeypatch);backend=OfflineWan(s);ready=admit_all(s,backend)
    root=s['run']/'production/scene-clips';folder=root/s['plan']['clips'][0]['clip_id']
    complete=require_scene_clip_acceptance(s['frozen'],s['units'],s['timeline'])
    before=(len(backend.posts),backend.ensures,backend.closes)
    changes=[(folder/'graph.json',lambda v:v['97']['inputs'].update(image='foreign/start.png')),
        (folder/'intent.json',lambda v:v.update(client_id='00000000-0000-0000-0000-000000000001')),
        (folder/'accepted.json',lambda v:v.update(number=True)),
        (folder/'submission.json',lambda v:v.update(prompt_id='00000000-0000-0000-0000-000000000001')),
        (folder/'input.json',lambda v:v.update(filter='scale=1:1')),
        (folder/'mapping.json',lambda v:v['generated_to_retained'].__setitem__(0,True)),
        (folder/'last-frame.json',lambda v:v.update(source_frame_index=0)),
        (folder/'observation-accepted.json',lambda v:v.update(observation_sha256='0'*64)),
        (folder/'media-ready/source.json',lambda v:v['recipe']['parameters'].update(start_frame=1)),
        (folder/'media-ready/last_frame.json',lambda v:v['recipe']['parameters'].update(source_frame_index=0)),
        (root/'complete.json',lambda v:v.update(total_frames=1))]
    for path,change in changes:
        original=path.read_bytes();value=json.loads(original);change(value)
        try:
            path.write_text(json.dumps(value),encoding='utf-8')
            with pytest.raises(ValueError): require_scene_clip_acceptance(s['frozen'],s['units'],s['timeline'])
        finally: path.write_bytes(original)
    for path in [folder/'media-ready/source.json',folder/'media-ready/last_frame.json']:
        original=path.read_bytes()
        try:
            path.unlink()
            with pytest.raises(ValueError): require_scene_clip_acceptance(s['frozen'],s['units'],s['timeline'])
        finally: path.write_bytes(original)
    acceptance=json.loads((folder/'observation-accepted.json').read_text())
    paths=[Path(complete['clips'][0]['generated']['path']),Path(complete['clips'][0]['source']['path']),
        Path(complete['clips'][0]['last_frame']['image']['path']),Path(acceptance['observation']['path'])]
    for path in paths:
        original=path.read_bytes()
        try:
            path.write_bytes(original+b'changed')
            with pytest.raises(ValueError): require_scene_clip_acceptance(s['frozen'],s['units'],s['timeline'])
        finally:path.write_bytes(original)
    assert generate(s,backend).status=='source_clips_ready'
    assert before==(len(backend.posts),backend.ensures,backend.closes)


def test_accepted_observation_cannot_be_poisoned_by_later_failed_review(runtime_run,tmp_path,monkeypatch):
    from scene_clip_helpers import prepared_wan,OfflineWan,generate,observation
    s=prepared_wan(runtime_run,tmp_path,monkeypatch);backend=OfflineWan(s);first=generate(s,backend)
    template=first.observation_templates[0]
    accepted,_,_=observation(s,template)
    folder=Path(template).parent;original=(folder/'observation-accepted.json').read_bytes()
    declined,_,_=observation(s,template,verdict='failed')
    assert declined.status=='blocked',declined.error
    assert (folder/'observation-accepted.json').read_bytes()==original
    assert not (folder/'observation-rejected.json').exists()
    resumed=generate(s,backend)
    assert resumed.scenes[0]['status']=='ready',resumed.error


def test_complete_outer_records_recover_without_regenerating_existing_media(runtime_run,tmp_path,monkeypatch):
    from scene_clip_helpers import prepared_wan,OfflineWan,admit_all,generate
    from video_ai.runtime.scene_clip_records import require_scene_clip_acceptance
    s=prepared_wan(runtime_run,tmp_path,monkeypatch);backend=OfflineWan(s);admit_all(s,backend)
    root=s['run']/'production/scene-clips';folder=root/s['plan']['clips'][0]['clip_id']
    complete=require_scene_clip_acceptance(s['frozen'],s['units'],s['timeline'])
    original={name:(folder/name).read_bytes() for name in ('mapping.json','last-frame.json','clip.json')}
    before=(len(backend.posts),backend.ensures,backend.closes)
    def forbidden(*args,**kwargs): raise AssertionError('valid receipt media must never be regenerated')
    monkeypatch.setattr('video_ai.media.video.trim_scene_video',forbidden)
    monkeypatch.setattr('video_ai.media.frames.extract_native_frame',forbidden)
    monkeypatch.setattr('video_ai.media.images.adapt_image',forbidden)
    for name in original: (folder/name).unlink()
    (root/'complete.json').unlink()
    repaired=generate(s,backend)
    assert repaired.status=='source_clips_ready',repaired.error
    assert require_scene_clip_acceptance(s['frozen'],s['units'],s['timeline'])==complete
    assert all((folder/name).read_bytes()==raw for name,raw in original.items())
    assert before==(len(backend.posts),backend.ensures,backend.closes)


def test_corrupt_later_incomplete_transaction_blocks_before_first_scene_post(runtime_run,tmp_path,monkeypatch):
    from scene_clip_helpers import prepared_wan,OfflineWan,generate
    from image_selection_helpers import save
    s=prepared_wan(runtime_run,tmp_path,monkeypatch);backend=OfflineWan(s)
    later=s['run']/'production/scene-clips/scene_0003_clip_0001'
    save(later/'intent.json',dict(schema_version=2,run_id=s['run'].name,clip_id=later.name))
    result=generate(s,backend)
    assert result.status=='blocked',result.error
    assert not backend.posts and backend.ensures==0
    assert not list((s['run']/'production/scene-clips/scene_0001_clip_0001').glob('intent.json'))


@pytest.mark.parametrize('point',['media-input-ready','media-input-promoted','media-generated-ready',
    'media-generated-promoted','media-source-ready','media-source-promoted','media-last_frame-ready',
    'media-last_frame-promoted','clip','observation-template'])
def test_durable_media_boundaries_resume_original_post_once(runtime_run,tmp_path,monkeypatch,point):
    from scene_clip_helpers import prepared_wan,OfflineWan,generate
    import video_ai.runtime.production_scene_clips as module
    s=prepared_wan(runtime_run,tmp_path,monkeypatch);backend=OfflineWan(s);fired=[]
    def interrupt(observed):
        if observed==point and not fired:
            fired.append(observed);raise KeyboardInterrupt('synthetic durable interruption')
    monkeypatch.setattr(module,'boundary',interrupt)
    result=generate(s,backend)
    assert result.status=='interrupted' and fired==[point],result.error
    assert len(backend.posts)==(0 if point.startswith('media-input-') else 1)
    assert not (s['run']/'.make-video.lock').exists()
    folder=s['run']/'production/scene-clips'/s['plan']['clips'][0]['clip_id']
    import video_ai.media.images as images
    import video_ai.media.video as video
    import video_ai.media.frames as frames
    for operation,owner,name in [('input',images,'adapt_image'),('source',video,'trim_scene_video'),
                                  ('last_frame',frames,'extract_native_frame')]:
        if (folder/'media-ready'/(operation+'.json')).exists():
            original=getattr(owner,name)
            def guard(source,target,*args,_original=original,_operation=operation,**kwargs):
                assert not Path(target).is_relative_to(folder),f'valid {_operation} bytes regenerated'
                return _original(source,target,*args,**kwargs)
            monkeypatch.setattr(owner,name,guard)
    resumed=generate(s,backend)
    assert resumed.status=='awaiting_continuity_review',resumed.error
    assert len(backend.posts)==3
    assert len({post['prompt']['108']['inputs']['filename_prefix'] for post in backend.posts})==3


def test_lost_post_response_recovers_original_uuid_graph_only_with_get(runtime_run,tmp_path,monkeypatch):
    from scene_clip_helpers import prepared_wan,OfflineWan,generate
    s=prepared_wan(runtime_run,tmp_path,monkeypatch);backend=OfflineWan(s);backend.mode='lost_response'
    result=generate(s,backend)
    assert result.status=='blocked',result.error
    assert len(backend.posts)==3
    original={post['client_id'] for post in backend.posts}
    backend.mode='normal'
    resumed=generate(s,backend)
    assert resumed.status=='awaiting_continuity_review',resumed.error
    assert len(backend.posts)==3 and {post['client_id'] for post in backend.posts}==original
    assert backend.gets.count('/history')==3


def test_remote_wan_template_rejection_precedes_intent_and_post(runtime_run,tmp_path,monkeypatch):
    from scene_clip_helpers import prepared_wan,OfflineWan,generate
    s=prepared_wan(runtime_run,tmp_path,monkeypatch);backend=OfflineWan(s);backend.remote_info={}
    result=generate(s,backend)
    assert result.status in ('blocked','failed'),result.error
    assert not backend.posts
    assert '/object_info' in backend.gets
    assert not list((s['run']/'production/scene-clips').glob('*/intent.json'))


def test_authentic_invalid_generated_count_is_terminal_without_reinference(runtime_run,tmp_path,monkeypatch):
    from scene_clip_helpers import prepared_wan,OfflineWan,generate
    s=prepared_wan(runtime_run,tmp_path,monkeypatch);backend=OfflineWan(s)
    cid=s['plan']['clips'][0]['clip_id'];output=backend.outputs[cid]
    assert s['plan']['clips'][0]['generated_frames']>1
    output.unlink();backend._create_video(output,1)
    result=generate(s,backend)
    assert result.status=='failed',result.error
    assert result.scenes[0]['status']=='failed'
    assert all(row['status']=='awaiting_continuity_review' for row in result.scenes[1:])
    terminal=json.loads((s['run']/'production/scene-clips'/cid/'terminal.json').read_text())
    assert terminal['status']=='invalid_media'
    assert len(backend.posts)==3
    resumed=generate(s,backend)
    assert resumed.status=='failed' and resumed.scenes[0]['status']=='failed'
    assert len(backend.posts)==3


def test_observation_raw_receipt_complete_boundaries_resume_exact_observation(runtime_run,tmp_path,monkeypatch):
    from scene_clip_helpers import prepared_wan,OfflineWan,generate,observation
    import video_ai.runtime.production_scene_clips as module
    from video_ai.runtime.scene_clip_records import require_scene_clip_acceptance
    s=prepared_wan(runtime_run,tmp_path,monkeypatch);backend=OfflineWan(s);first=generate(s,backend)
    assert first.status=='awaiting_continuity_review',first.error
    active={'point':'observation-original'};fired=[]
    def interrupt(point):
        if point==active['point']:
            fired.append(point);active['point']=None;raise KeyboardInterrupt('synthetic observation commit interruption')
    monkeypatch.setattr(module,'boundary',interrupt)
    interrupted,path,_=observation(s,first.observation_templates[0])
    assert interrupted.status=='interrupted' and fired==['observation-original']
    folder=Path(first.observation_templates[0]).parent
    assert len(list((folder/'observations').glob('*.json')))==1
    assert not (folder/'observation-accepted.json').exists()
    consume=lambda:module.consume_scene_clip_observation(s['frozen'],s['units'],s['timeline'],path,
        paths=s['paths'],logger=s['logger'])
    active['point']='observation-receipt'
    assert consume().status=='interrupted'
    receipt=(folder/'observation-accepted.json').read_bytes()
    assert consume().status=='awaiting_continuity_review'
    assert (folder/'observation-accepted.json').read_bytes()==receipt
    observation(s,first.observation_templates[1])
    active['point']='complete'
    interrupted,_,_=observation(s,first.observation_templates[2])
    assert interrupted.status=='interrupted' and fired[-1]=='complete'
    assert require_scene_clip_acceptance(s['frozen'],s['units'],s['timeline'])['total_frames']==s['timeline'].total_frames
    before=(len(backend.posts),backend.ensures)
    assert generate(s,backend).status=='source_clips_ready'
    assert before==(len(backend.posts),backend.ensures)


def test_upstream_mutation_after_observation_raw_copy_cannot_commit_acceptance(runtime_run,tmp_path,monkeypatch):
    from scene_clip_helpers import prepared_wan,OfflineWan,generate,observation
    import video_ai.runtime.production_scene_clips as module
    s=prepared_wan(runtime_run,tmp_path,monkeypatch);backend=OfflineWan(s);first=generate(s,backend)
    global_path=s['run']/'production/visual-bible.json';original=global_path.read_bytes()
    def change(point):
        if point=='observation-original':
            value=json.loads(original);value['global_style']['description']='changed after raw receipt'
            global_path.write_text(json.dumps(value),encoding='utf-8')
    monkeypatch.setattr(module,'boundary',change)
    try:
        result,_,_=observation(s,first.observation_templates[0])
        assert result.status=='blocked',result.error
        folder=Path(first.observation_templates[0]).parent
        assert not (folder/'observation-accepted.json').exists()
        assert len(list((folder/'observations').glob('*.json')))==1
    finally:global_path.write_bytes(original)


def test_post_acceptance_raw_response_recovers_missing_accepted_index_once(runtime_run,tmp_path,monkeypatch):
    from scene_clip_helpers import prepared_wan,OfflineWan,generate
    from video_ai.runtime.scene_clip_records import SceneClipStore
    s=prepared_wan(runtime_run,tmp_path,monkeypatch);backend=OfflineWan(s);original=SceneClipStore.write;fired=[]
    def interrupt(store,path,value):
        if Path(path).name=='accepted.json' and not fired:
            fired.append(str(path));raise KeyboardInterrupt('raw POST durable, accepted index absent')
        return original(store,path,value)
    monkeypatch.setattr(SceneClipStore,'write',interrupt)
    first=generate(s,backend)
    assert first.status=='interrupted' and len(backend.posts)==1,first.error
    first_folder=s['run']/'production/scene-clips'/s['plan']['clips'][0]['clip_id']
    assert not (first_folder/'accepted.json').exists()
    assert len(list((first_folder/'http').glob('*.response.json')))==1
    resumed=generate(s,backend)
    assert resumed.status=='awaiting_continuity_review',resumed.error
    assert len(backend.posts)==3
    assert len({p['client_id'] for p in backend.posts})==3
