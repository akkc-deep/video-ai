"""Cross-stage orchestration retains genuine native media and explicit gates."""
from pathlib import Path

import pytest
from unit.test_production_inputs import production_config


@pytest.mark.parametrize('corruption',['intent','tts_body','large_tts_body'])
def test_new_original_text_uses_automatic_prefix_and_exact_baseline_prompts(production_config,runtime_run,tmp_path,monkeypatch,corruption):
    import json
    from copy import deepcopy
    from types import SimpleNamespace
    import video_ai.production as production
    import video_ai.runtime.production_scene_plan as scene_planning
    import video_ai.runtime.jimeng_candidates as candidates
    import video_ai.adapters.selection_email as email
    from video_ai.adapters.jimeng import JimengClient as RealImageClient,encode_body
    from video_ai.adapters.external_https import ExternalResponse
    from video_ai.config import load_config
    from video_ai.runtime.preflight import PreflightReport,PreflightCheck
    from production_helpers import model_server,proposal_for,wav_bytes,config_for_server,install_owned_services
    from unit.test_jimeng_config import image_settings
    from unit.test_production_scenes import scene_proposal
    from integration.test_image_selection_flow import SMTP,png
    original_text='湖面很静。白鸟停在石上。它望向远处。\r\n\r\n落日映着远山。'
    def model_reply(path,body,count):
        if path!='/api/generate':
            text=body['text'];samples=19501 if text.startswith(('湖面','白鸟停')) else 6001
            raw=wav_bytes(samples=samples)
            if corruption=='large_tts_body' and text.startswith('湖面'):
                junk=b'JUNK'+(1100000).to_bytes(4,'little')+b'\0'*1100000
                raw=raw[:4]+(len(raw)+len(junk)-8).to_bytes(4,'little')+raw[8:]+junk
            return 200,'audio/wav',raw
        if '\nSCENE_INPUT_JSON\n' in body['prompt']:
            data,_=json.JSONDecoder().raw_decode(body['prompt'].split('\nSCENE_INPUT_JSON\n',1)[1])
            proposal=deepcopy(scene_proposal())
            span=next(s for s in data['finalized_units']['spans'] if s['unit_id']=='speech_0004')
            source=[dict(unit_id=span['unit_id'],text_start=span['start'],text_end=span['end'],quote=original_text[span['start']:span['end']])]
            proposal['scene_groups'].append(dict(proposal['scene_groups'][0],key='mountains',label='远山',environment='落日和远山',change_sources=source))
            proposal['scenes'][-1].update(entity_ids=[],scene_group_id='mountains',summary='落日远山',image_prompt='落日映着远山',motion_prompt='落日光线缓缓移动',change_sources=source)
        else:proposal=proposal_for(body)
        return 200,'application/json',json.dumps(dict(model='qwen3:8b',done=True,done_reason='stop',response=json.dumps(proposal,ensure_ascii=False))).encode()
    official=[];smtp=SMTP();raw_image=png(1280,720)
    def official_http(method,url,**kwargs):
        if kwargs.get('ownership_check') is not None:kwargs['ownership_check']()
        if method=='GET':return ExternalResponse(200,raw_image)
        body=json.loads(kwargs['body']);official.append((url,body))
        if 'CVSync2AsyncSubmitTask' in url:data=dict(task_id='source-task-'+str(len(official)))
        else:data=dict(status='done',image_urls=['https://cdn.example.test/'+body['task_id']+'.png'])
        return ExternalResponse(200,encode_body(dict(code=10000,request_id='fixture-official',data=data)))
    class OfflineImageClient(RealImageClient):
        def __init__(self,settings):super().__init__(settings,http=SimpleNamespace(request=official_http))
    for name in ('TEST_VOLC_AK','TEST_VOLC_SK','VIDEO_AI_SMTP_AUTH_CODE'):monkeypatch.setenv(name,'synthetic-test-only')
    monkeypatch.setattr(candidates,'JimengClient',OfflineImageClient)
    monkeypatch.setattr(email.smtplib,'SMTP_SSL',smtp.factory)
    manager=install_owned_services(monkeypatch)
    monkeypatch.setattr(scene_planning,'ServiceManager',manager);monkeypatch.setattr(scene_planning,'port_listening',lambda *args:False)
    monkeypatch.setattr(production,'production_preflight',lambda *args:PreflightReport((PreflightCheck('fixture',True,'local services only'),)))
    run=runtime_run[0];monkeypatch.setattr(production,'create_run',lambda *args:run)
    with model_server(model_reply) as (url,posts):
        config=config_for_server(production_config,url,run)
        raw=json.loads(config.config_file.read_text(encoding='utf-8'))
        settings=image_settings();settings['model_parameters'].update(width=1280,height=720)
        raw.update(production_strategy='paragraph_jimeng_v1',image_generation=settings,scene_planning={'target_scenes_per_paragraph':3,'max_clip_seconds':0.5})
        raw['media']['timeline']=dict(sentence_pause_seconds=0,paragraph_pause_seconds=0,opening_seconds=0,closing_seconds=0)
        config.config_file.write_text(json.dumps(raw),encoding='utf-8');config=load_config(config.config_file)
        result=production.make_video(config,text=original_text)
        assert result.status=='awaiting_image_selection',result.error
        assert (run/'production/script.txt').read_bytes()==original_text.encode('utf-8')
        plan=json.loads((run/'production/scene-plan.json').read_text(encoding='utf-8'))
        assert plan['scenes'][0]['end_frame']==13
        assert [r['retained_frames'] for r in plan['clips'][:3]]==[5,4,4]
        submitted=[body for url,body in official if 'CVSync2AsyncSubmitTask' in url]
        assert [b['prompt'] for b in submitted]==[s['image_prompt'] for s in plan['scenes'] if s['scene_id'] in plan['batches'][0] for _ in range(2)]
        assert len(smtp.messages)==1
        before=(len(posts),len(official),len(smtp.messages))
        resumed=production.make_video(run_dir=run)
        assert resumed.status=='awaiting_image_selection',resumed.error
        assert (len(posts),len(official),len(smtp.messages))==before
        state=json.loads((run/'production/production-state.json').read_text(encoding='utf-8'))
        assert all(state['stages'][s]['status']=='completed' for s in ('units','speech','timeline'))
        assert all(state['stages'][s]['status']=='pending' for s in ('storyboard','start_images','source_clips','upscale','composition','delivery'))
        from video_ai.runtime.production_inputs import load_frozen_inputs
        from video_ai.runtime._scene_revision_origins import capture_origin
        captured=capture_origin(load_frozen_inputs(run),'common','all')
        paths={row['path'] for row in captured['snapshot']['files']+captured['raw_files']+[m for _,m in captured['media']]}
        assert str(run/'production/production-state.json') in paths
        assert str(run/'production/speech.json') in paths
        for stage in ('units','speech','timeline'):
            for record in state['units'][stage].values():
                assert record['checkpoint_path'] in paths
                assert all(row['path'] in paths for row in record['outputs'].values())
                if record['request'] is not None:
                    assert record['request']['intent_path'] in paths
                    assert all(p in paths for p in record['request']['response_paths'])
        from video_ai.runtime._scene_revision_origins import owned_common
        import os
        speech_record=state['units']['speech']['speech_0001']
        intent_path=Path(speech_record['request']['intent_path'])
        body_path=next(Path(p) for p in speech_record['request']['response_paths'] if p.endswith('.body'))
        for corrupted in ((intent_path,) if corruption=='intent' else (body_path,)):
            original=corrupted.read_bytes();stamp=corrupted.stat()
            changed=original.replace('湖面'.encode(),'海面'.encode()) if corrupted==intent_path else original[:100]+bytes([original[100]^1])+original[101:]
            assert changed!=original and len(changed)==len(original)
            try:
                corrupted.write_bytes(changed);os.utime(corrupted,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
                with pytest.raises(ValueError):owned_common(load_frozen_inputs(run))
            finally:
                corrupted.write_bytes(original);os.utime(corrupted,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        captured['guard'].verify_captured_bytes()
        selection=json.loads(Path(result.selection_template).read_text(encoding='utf-8'))
        batch=json.loads((Path(result.selection_template).parent/'batch.json').read_text(encoding='utf-8'))
        selection.update(intent='accept',selections=[{k:scene['candidates'][0][k] for k in ('candidate_id','sha256')}|{'scene_id':scene['scene_id']} for scene in batch['scenes']])
        authored=run/'synthetic-baseline-selection.json';authored.write_text(json.dumps(selection),encoding='utf-8')
        import video_ai.runtime.production_scene_pipeline as pipeline_module
        raised=[]
        def stop_image(point):
            if point=='image-accepted' and not raised:raised.append(point);raise KeyboardInterrupt(point)
        with monkeypatch.context() as patch:
            patch.setattr(pipeline_module,'boundary',stop_image)
            interrupted=production.make_video(run_dir=run,image_selection=authored)
            assert interrupted.status=='interrupted',interrupted.error
            recovered=production.make_video(run_dir=run,image_selection=authored)
            assert recovered.status=='image_batch_accepted',recovered.error
            assert raised==['image-accepted']
        assert (len(posts),len(official),len(smtp.messages))==before


def test_prepared_public_pipeline_waits_for_parent_and_never_posts_child_or_duplicate(runtime_run,tmp_path,monkeypatch):
    import video_ai.production as production
    import video_ai.runtime.production_scene_clips as clips_module
    import video_ai.adapters.scene_comfy as comfy
    from scene_pipeline_helpers import prepared_pipeline,write_clip_observation,write_final_observation
    from scene_clip_helpers import OfflineWan
    from video_ai.runtime.scene_pipeline_records import load_scene_pipeline_progress
    import video_ai.runtime.production_scene_pipeline as pipeline_module
    interruptions=[];seen=set()
    def stop_once(point):
        if point not in seen:
            seen.add(point);interruptions.append(point);raise KeyboardInterrupt('coordinator boundary '+point)
    monkeypatch.setattr(pipeline_module,'boundary',stop_once)
    def resume(**arguments):
        for _ in range(11):
            count=len(interruptions)
            value=production.make_video(**arguments)
            if value.status!='interrupted':return value
            assert len(interruptions)>count,value.error
        raise AssertionError('coordinator failed to recover its durable boundaries')
    setup=prepared_pipeline(runtime_run,tmp_path,monkeypatch)
    backend=OfflineWan(setup)
    monkeypatch.setattr(comfy,'SceneComfyClient',backend.factory)
    monkeypatch.setattr(clips_module,'_OwnedService',backend.service_factory)
    result=resume(run_dir=setup['run'])
    assert result.status=='awaiting_continuity_review',result.error
    assert len(backend.posts)==len(setup['plan']['scenes'])
    before=len(backend.posts)
    again=resume(run_dir=setup['run'])
    assert again.status=='awaiting_continuity_review',again.error
    assert len(backend.posts)==before
    assert len(result.observation_templates)==len(setup['plan']['scenes'])
    template=next(Path(p) for p in result.observation_templates if 'scene_0001' in p)
    authored=write_clip_observation(setup,template)
    consumed=resume(run_dir=setup['run'],clip_observation=authored)
    assert consumed.status=='blocked' and consumed.error is None  # original consumer: child is pending
    assert len(backend.posts)==before  # consume-only, no child inference
    resumed=resume(run_dir=setup['run'])
    assert resumed.status=='awaiting_continuity_review',resumed.error
    assert len(backend.posts)==before+1
    progress=load_scene_pipeline_progress(setup['frozen'])
    assert progress['common']['status']==progress['plan']['status']=='ready'
    assert progress['images']['status']=='images_ready'
    assert progress['clips'] is not None
    # Finish both continuation joins with the original public consume-only API.
    result=resumed
    for _ in range(len(setup['plan']['clips'])+1):
        for path in result.observation_templates:
            consumed=resume(run_dir=setup['run'],clip_observation=write_clip_observation(setup,path))
            assert consumed.error is None,consumed.error
        if consumed.status=='source_clips_ready':break
        result=resume(run_dir=setup['run'])
        assert result.status=='awaiting_continuity_review',result.error
    assert consumed.status=='source_clips_ready'
    assert len(backend.posts)==len(setup['plan']['clips'])
    # All retained frames are truly upscaled by a local HTTP substitute.
    from scene_media_helpers import OfflineUpscale
    import video_ai.runtime.production_scene_upscale as upscale_module
    import video_ai.runtime.production_scene_composition as composition_module
    upscale=OfflineUpscale(setup)
    monkeypatch.setattr(comfy,'SceneComfyClient',upscale.factory)
    monkeypatch.setattr(upscale_module,'_OwnedService',upscale.service_factory)
    candidate=resume(run_dir=setup['run'])
    assert candidate.status=='awaiting_final_review',candidate.error
    assert len(upscale.posts)==setup['timeline'].total_frames
    assert not Path(setup['frozen'].options['output_paths']['receipt']).exists()
    _verify_candidate_read_window(setup,monkeypatch)
    _verify_missing_outer_markers(setup,tmp_path,backend,upscale,monkeypatch)
    monkeypatch.setattr(composition_module,'run_logged',lambda *a,**kw:pytest.fail('candidate re-encoded'))
    accepted=resume(run_dir=setup['run'],final_observation=write_final_observation(setup,candidate.final_observation_template))
    assert accepted.status=='final_review_ready',accepted.error
    assert not Path(setup['frozen'].options['output_paths']['receipt']).exists()
    assert resume(run_dir=setup['run']).status=='final_review_ready'
    # Only a fully validated publishing prefix may re-enter the explicit writer.
    import video_ai.runtime.scene_delivery_files as delivery_files
    publication_stops=[]
    def interrupt_publication(point,role):
        if (point,role)==('renamed','movie') and not publication_stops:
            publication_stops.append((point,role));raise KeyboardInterrupt('durable rename before published cursor')
    with monkeypatch.context() as patch:
        patch.setattr(delivery_files,'boundary',interrupt_publication)
        partial=production.make_video(run_dir=setup['run'],publish=True)
    assert partial.status=='interrupted',partial.error
    assert publication_stops==[('renamed','movie')]
    from integration.test_scene_revision_flow import tree_identity
    partial_before=tree_identity(setup['run'])
    with monkeypatch.context() as patch:
        patch.setattr(production,'RunLock',lambda *a,**kw:pytest.fail('ordinary partial publish acquired a lock'))
        assert production.make_video(run_dir=setup['run']).status=='blocked'
    assert tree_identity(setup['run'])==partial_before
    delivered=resume(run_dir=setup['run'],publish=True)
    assert delivered.status=='delivered',delivered.error
    from integration.test_scene_revision_flow import tree_identity
    before=tree_identity(setup['run'])
    def output_identity():
        import hashlib
        result={}
        for role,path in setup['frozen'].options['output_paths'].items():
            path=Path(path);stamp=path.stat()
            result[role]=(stamp.st_dev,stamp.st_ino,stamp.st_mtime_ns,stamp.st_size,hashlib.sha256(path.read_bytes()).hexdigest())
        return result
    outputs_before=output_identity()
    def forbidden(*args,**kwargs):pytest.fail('completed replay performed a write/service action')
    monkeypatch.setattr(production,'RunLock',forbidden)
    import video_ai.runtime.logging as logging_module
    import video_ai.runtime.production_scene_pipeline as pipeline_module
    monkeypatch.setattr(logging_module,'RunLogger',forbidden)
    monkeypatch.setattr(pipeline_module,'record_invocation',forbidden)
    import video_ai.runtime.scene_delivery_files as delivery_files
    monkeypatch.setattr(delivery_files,'_copy',forbidden)
    monkeypatch.setattr(upscale_module,'_extract',forbidden)
    for arguments in ({},{},{'publish':True}):
        replay=production.make_video(run_dir=setup['run'],**arguments)
        assert replay.status=='delivered',replay.error
        assert replay.delivery_receipt==delivered.delivery_receipt
        assert tree_identity(setup['run'])==before
        assert output_identity()==outputs_before
    assert len(backend.posts)==len(setup['plan']['clips'])
    assert len(upscale.posts)==setup['timeline'].total_frames
    # A damaged final receipt is a read-only refusal, never generation fallback.
    receipt=delivered.delivery_receipt;original=receipt.read_bytes();receipt.write_bytes(b'{}')
    damaged=tree_identity(setup['run'])
    damaged_outputs=output_identity()
    assert production.make_video(run_dir=setup['run']).status=='blocked'
    assert tree_identity(setup['run'])==damaged
    assert output_identity()==damaged_outputs
    receipt.write_bytes(original)
    _verify_completed_transaction_corruption_read_only(setup,monkeypatch)
    assert seen=={'common-ready','pipeline-inputs','wan-inputs','clip-accepted','upscale-ready','candidate-ready',
                 'final-accepted','delivery-returned','invocation-written'}
    monkeypatch.undo()
    _verify_continuation_revision_inherits_original_media(setup)


def _verify_completed_transaction_corruption_read_only(setup,monkeypatch):
    import json
    import os
    import video_ai.production as production
    import video_ai.runtime.logging as logging_module
    import video_ai.runtime.production_scene_pipeline as pipeline
    from integration.test_scene_revision_flow import tree_identity
    path=setup['run']/'production/scene-delivery/transaction.json'
    original=path.read_bytes();stamp=path.stat();tx=json.loads(original)
    def forbidden(*args,**kwargs):pytest.fail('damaged completed transaction entered a writer')
    try:
        with monkeypatch.context() as patch:
            patch.setattr(production,'RunLock',forbidden)
            patch.setattr(logging_module,'RunLogger',forbidden)
            patch.setattr(pipeline,'record_invocation',forbidden)
            for damaged in ({},dict(tx,status='bogus'),dict(tx,status='publishing',composition_sha256='0'*64)):
                path.write_text(json.dumps(damaged),encoding='utf-8')
                before=tree_identity(setup['run'])
                for arguments in ({'publish':True},{}):
                    result=production.make_video(run_dir=setup['run'],**arguments)
                    assert result.status=='blocked',result.error
                    assert tree_identity(setup['run'])==before
    finally:
        path.write_bytes(original);os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))


def _verify_missing_outer_markers(setup,tmp_path,wan,upscale,monkeypatch):
    import video_ai.production as production
    import video_ai.runtime.production_scene_composition as composition
    import video_ai.runtime.production_scene_clips as clips
    import video_ai.runtime.production_scene_upscale as frames
    before=(len(wan.posts),len(upscale.posts))
    def forbidden(*args,**kwargs):pytest.fail('marker recovery regenerated media')
    with monkeypatch.context() as patch:
        patch.setattr(composition,'run_logged',forbidden)
        patch.setattr(clips,'_technical',forbidden)
        patch.setattr(frames,'_copy',forbidden)
        for i,relative in enumerate(('production/scene-clips/complete.json','production/scene-upscale/complete.json',
                                     'production/scene-composition/final-observation-template.json')):
            marker=setup['run']/relative;original=marker.read_bytes();backup=tmp_path/f'preserved-outer-{i}.json'
            marker.rename(backup)
            try:
                result=production.make_video(run_dir=setup['run'])
                assert result.status in ('awaiting_final_review','final_review_ready'),result.error
                assert marker.read_bytes()==original
                assert (len(wan.posts),len(upscale.posts))==before
            finally:
                if not marker.exists():backup.rename(marker)


def _verify_continuation_revision_inherits_original_media(source):
    """An explicit child redo keeps its accepted parent and independent scenes."""
    import json
    from scene_clip_helpers import OfflineWan,admit_all
    from scene_media_helpers import OfflineUpscale
    from integration.test_scene_revision_flow import revision_request,tree_identity
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import require_scene_revision,load_scene_common_prefix,revision_scope
    from video_ai.runtime.image_selection_records import load_committed_plan
    from video_ai.runtime.reference_image_records import build_reference_image_acceptance
    from video_ai.runtime._scene_revision_copy import RevisionStore
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.runtime.production_scene_upscale import produce_scene_upscaled_clips
    from video_ai.runtime.scene_media_records import require_scene_upscale_acceptance_record,scene_media_context
    from video_ai.runtime._scene_revision_origins import source_clip_record
    _verify_origin_media_scope(source)
    request,value=revision_request(source,kind='regenerate_clips')
    value.update(scene_ids=[],choices=[],clip_ids=[source['plan']['clips'][1]['clip_id']])
    request.write_text(json.dumps(value),encoding='utf-8')
    before=tree_identity(source['run'])
    revision=create_scene_revision(source['run'],request)
    assert revision.status=='revision_ready',revision.error
    frozen=load_frozen_inputs(revision.run_dir)
    with revision_scope():
        proof=require_scene_revision(frozen);units,timeline=load_scene_common_prefix(frozen)
        bible,plan=load_committed_plan(frozen,units,timeline)
        assert proof['invalidation']['dirty']['clips']==['scene_0001_clip_0002','scene_0001_clip_0003']
        assert len(proof['invalidation']['reusable']['upscale'])==10
        assert 'image_group:all' in proof['imports']
    target=dict(run=revision.run_dir,frozen=frozen,units=units,timeline=timeline,bible=bible,plan=plan,
        paths=RuntimePaths.from_config(frozen.config),logger=RunLogger(revision.run_dir,production=True))
    with RunLock(target['run']) as held,revision_scope():
        wan_inputs=build_reference_image_acceptance(frozen,units,timeline)
        RevisionStore(target['run'],held).save(target['run']/'production/reference-images/wan-inputs.json',wan_inputs)
    wan=OfflineWan(target);clips=admit_all(target,wan)
    assert clips.status=='source_clips_ready',clips.error
    assert len(wan.posts)==2
    for cid in ('scene_0001_clip_0001','scene_0002_clip_0001','scene_0003_clip_0001'):
        with revision_scope():
            old=source_clip_record(source['frozen'],cid);new=source_clip_record(frozen,cid)
            assert new['request']==old['request']
            assert new['accepted']==old['accepted']
            assert new['clip']['run_id']==source['run'].name
            assert new['clip']['source']['sha256']==old['clip']['source']['sha256']
    upscale=OfflineUpscale(target)
    result=produce_scene_upscaled_clips(frozen,units,timeline,paths=target['paths'],logger=target['logger'],**upscale.kwargs)
    assert result.status=='upscale_ready',result.error
    assert len(upscale.posts)==8
    with revision_scope():
        complete=require_scene_upscale_acceptance_record(scene_media_context(frozen,units,timeline))
        assert complete['total_frames']==18
    for cid in ('scene_0001_clip_0001','scene_0002_clip_0001','scene_0003_clip_0001'):
        assert not (target['run']/'production/scene-upscale'/cid).exists()
    assert tree_identity(source['run'])==before


def _verify_origin_media_scope(source):
    import os
    from video_ai.runtime._scene_revision_origins import capture_origin
    from video_ai.runtime.scene_media_records import scene_media_context
    cases=[('scene_0001_clip_0001','scene_0003_clip_0001:frame_000001',True),
           ('scene_0003_clip_0001','scene_0003_clip_0001:frame_000001',False),
           ('scene_0001_clip_0001','scene_0001_clip_0002:frame_000001',False)]
    for cid,key,admit in cases:
        path=source['run']/'production/scene-clips'/cid/'source.mp4'
        original=path.read_bytes();stamp=path.stat();captured=None
        try:
            path.write_bytes(b'synthetic unrelated or required media fault')
            if admit:
                captured=capture_origin(source['frozen'],'upscale',key)
                assert captured['value']['frame_id']==key
                with pytest.raises(ValueError):scene_media_context(source['frozen'],source['units'],source['timeline'])
            else:
                with pytest.raises(ValueError):capture_origin(source['frozen'],'upscale',key)
        finally:
            path.write_bytes(original);os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        if captured is not None:captured['guard'].verify_captured_bytes()
    _verify_damaged_parent_can_be_explicitly_regenerated(source)


def _verify_damaged_parent_can_be_explicitly_regenerated(source):
    import json
    import os
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import require_scene_revision
    from integration.test_scene_revision_flow import revision_request
    request,value=revision_request(source,kind='regenerate_clips')
    value.update(scene_ids=[],choices=[],clip_ids=['scene_0001_clip_0002'])
    request.write_text(json.dumps(value),encoding='utf-8')
    path=source['run']/'production/scene-clips/scene_0001_clip_0002/source.mp4'
    frame=source['run']/'production/scene-upscale/scene_0001_clip_0002/frame_000001/frame.json'
    output=frame.parent/'output.png';output_raw=output.read_bytes();output_stamp=output.stat()
    original=path.read_bytes();stamp=path.stat();frame_raw=frame.read_bytes();frame_stamp=frame.stat()
    try:
        path.write_bytes(b'damaged explicitly dirty parent; original transaction remains finished')
        output.write_bytes(b'damaged dirty upscale that must not be imported')
        # A completed frame cursor cannot be inferred from an accepted request.
        frame.unlink()
        blocked=create_scene_revision(source['run'],request)
        assert blocked.status=='blocked' and blocked.run_dir is None,blocked.error
        terminal=frame.parent/'terminal.json';assert not terminal.exists()
        try:
            terminal.write_text('{}',encoding='utf-8')
            from video_ai.runtime.production_scene_revision import _snapshot,configuration_identity
            with pytest.raises(ValueError):
                _snapshot(source['frozen'],target_config=source['frozen'].config,request=value,
                    target_identity=configuration_identity(source['frozen'].config))
        finally:terminal.unlink()
        frame.write_bytes(frame_raw);os.utime(frame,ns=(frame_stamp.st_atime_ns,frame_stamp.st_mtime_ns))
        revision=create_scene_revision(source['run'],request)
        assert revision.status=='revision_ready',revision.error
        proof=require_scene_revision(load_frozen_inputs(revision.run_dir))
        assert proof['invalidation']['dirty']['clips']==['scene_0001_clip_0002','scene_0001_clip_0003']
        assert len(proof['invalidation']['reusable']['upscale'])==10
    finally:
        path.write_bytes(original);os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        if not frame.exists():frame.write_bytes(frame_raw)
        os.utime(frame,ns=(frame_stamp.st_atime_ns,frame_stamp.st_mtime_ns))
        output.write_bytes(output_raw);os.utime(output,ns=(output_stamp.st_atime_ns,output_stamp.st_mtime_ns))


def _verify_candidate_read_window(setup,monkeypatch):
    import os
    from video_ai.runtime.scene_media_records import scene_media_context
    import video_ai.runtime.production_scene_composition as composition
    original_commit=composition._commit;calls=[]
    def counted(*args,**kwargs):calls.append(True);return original_commit(*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(composition,'_commit',counted)
        context=scene_media_context(setup['frozen'],setup['units'],setup['timeline'])
        first=composition.require_scene_composition_record(context)
        assert composition.require_scene_composition_record(context)==first and len(calls)==1
        path=setup['run']/'production/scene-composition/materialized.json'
        original=path.read_bytes();stamp=path.stat();changed=original.replace(b'"schema_version": 2',b'"schema_version": 3',1)
        assert changed!=original and len(changed)==len(original)
        try:
            path.write_bytes(changed);os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            with pytest.raises(ValueError):composition.require_scene_composition_record(context)
        finally:
            path.write_bytes(original);os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        fresh=scene_media_context(setup['frozen'],setup['units'],setup['timeline'])
        assert composition.require_scene_composition_record(fresh)==first and len(calls)==2
