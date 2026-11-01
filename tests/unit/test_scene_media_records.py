import pytest
from types import SimpleNamespace


def test_scene_media_result_protocol_fields_and_exit_codes():
    from video_ai.runtime.scene_media_records import SceneMediaResult
    assert set(SceneMediaResult().to_dict())==set('schema_version production_strategy run_id run_dir status active_stage upscaled_clips candidate final_observation_template delivery_receipt log_dir error'.split())
    for status,code in [('blocked',2),('failed',1),('interrupted',130)]:
        assert SceneMediaResult(status=status).exit_code==code
    for status in ('upscale_ready','awaiting_final_review','final_review_ready','final_review_failed','delivered'):
        with pytest.raises(ValueError): SceneMediaResult(status=status)


def test_unknown_run_has_no_identity_lock_or_log_side_effect(runtime_run):
    from uuid import uuid4
    from pathlib import Path
    from video_ai.runtime.production_scene_upscale import produce_scene_upscaled_clips
    unknown=Path('D:/VideoSi/projects/video-ai/runs')/('unknown-'+uuid4().hex)
    frozen=SimpleNamespace(options={'script_path':str(unknown/'inputs/script.txt')})
    result=produce_scene_upscaled_clips(frozen,[],None,paths=runtime_run[2],logger=None)
    assert result.status=='blocked' and result.run_id is None and result.run_dir is None and result.log_dir is None
    assert not unknown.exists()


def test_internal_reparse_component_refused_for_records_artifacts_and_roots(runtime_run,monkeypatch):
    from pathlib import Path
    import stat
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_state import ProductionRefused
    store=SceneMediaStore(SimpleNamespace(),runtime_run[0]); redirected=store.root/'redirected'
    original=Path.lstat
    def reparse(path,*args,**kwargs):
        if path==redirected: return SimpleNamespace(st_mode=stat.S_IFDIR,st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',reparse)
    for operation in (lambda:store.path(redirected/'record.json'),lambda:store.artifact(redirected/'media.png'),
                      lambda:store.for_root('production/scene-upscale/redirected')):
        with pytest.raises(ProductionRefused,match='redirected'): operation()


def test_media_store_rejects_network_thread_write_even_with_actual_held_lock(runtime_run):
    from threading import Thread
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    run=runtime_run[0]; failures=[]
    with RunLock(run) as lock:
        store=SceneMediaStore(SimpleNamespace(),run,lock=lock)
        def write():
            try: store.write('illegal.json',{})
            except BaseException as exc: failures.append(exc)
        worker=Thread(target=write); worker.start(); worker.join()
        assert len(failures)==1 and isinstance(failures[0],ProductionRefused)
        assert not (store.root/'illegal.json').exists()


@pytest.mark.parametrize('fault',['input_copy','http_body','empty_http_body'])
def test_captured_upstream_request_media_and_raw_http_mutation_blocks_send_guard(runtime_run,fault):
    from pathlib import Path
    import hashlib
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    run=runtime_run[0]
    input_copy=run/'comfy/input/upstream/start.png'; input_copy.parent.mkdir(parents=True); input_copy.write_bytes(b'original converted source pixels')
    http=run/'production/scene-clips/scene_0001_clip_0001/http'; http.mkdir(parents=True)
    body=http/'11111111-1111-4111-8111-111111111111.body'; body.write_bytes(b'original response')
    empty=http/'22222222-2222-4222-8222-222222222222.body'; empty.write_bytes(b'')
    with RunLock(run) as lock:
        store=SceneMediaStore(SimpleNamespace(options={'model_stamps':{}}),run,lock=lock)
        store.capture_admitted(dict(request=dict(input_copy=store.artifact(input_copy)),http_response=dict(body=store.artifact(body)),
            zero_response=dict(body=dict(path=str(empty),bytes=0,sha256=hashlib.sha256(b'').hexdigest()))))
        store.verify_global()
        dict(input_copy=input_copy,http_body=body,empty_http_body=empty)[fault].write_bytes(b'late mutation')
        with pytest.raises(ProductionRefused): store.verify_global()


def test_json_fsync_before_rename_crash_preserves_temp_and_can_recommit(runtime_run,monkeypatch):
    import os
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime._scene_upscale_records import _store_temporary
    with RunLock(runtime_run[0]) as lock:
        store=SceneMediaStore(SimpleNamespace(),runtime_run[0],lock=lock)
        rename=os.rename
        def crash(*args,**kwargs): raise KeyboardInterrupt()
        monkeypatch.setattr(os,'rename',crash)
        with pytest.raises(KeyboardInterrupt): store.write('inputs.json',{'immutable':'value'})
        leftovers=list(store.root.iterdir())
        assert len(leftovers)==1 and _store_temporary(store,leftovers[0]) and store.read('inputs.json') is None
        original=leftovers[0].read_bytes(); monkeypatch.setattr(os,'rename',rename)
        store.write('inputs.json',{'immutable':'value'})
        assert store.read('inputs.json')=={'immutable':'value'} and leftovers[0].read_bytes()==original


def test_capture_admitted_json_inventory_accepts_string_paths(runtime_run):
    import json
    from video_ai.runtime.scene_media_records import SceneMediaStore
    store=SceneMediaStore(SimpleNamespace(),runtime_run[0])
    image=runtime_run[0]/'upstream.png'; image.write_bytes(b'accepted original bytes')
    record=runtime_run[0]/'admitted-request.json'
    artifact=store.artifact(image)
    record.write_text(json.dumps(dict(input_copy=artifact)),encoding='utf-8')
    store.capture_admitted_inventory({str(record)})
    assert store.guard_paths[str(image)]==artifact


def test_network_thread_cannot_rebase_writer_ownership_via_for_root(runtime_run):
    from threading import Thread
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    run=runtime_run[0]; failures=[]
    with RunLock(run) as lock:
        store=SceneMediaStore(SimpleNamespace(),run,lock=lock)
        def write():
            try: store.for_root('production/scene-composition').write('illegal.json',{})
            except BaseException as exc: failures.append(exc)
        worker=Thread(target=write); worker.start(); worker.join()
        assert len(failures)==1 and isinstance(failures[0],ProductionRefused)
        assert not (run/'production/scene-composition/illegal.json').exists()


def test_capture_promoted_media_receipt_binds_target_and_absent_original_staging(runtime_run):
    from pathlib import Path
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    run=runtime_run[0]
    with RunLock(run) as lock:
        store=SceneMediaStore(SimpleNamespace(options={'model_stamps':{}}),run,lock=lock)
        source=run/'source.png'; source.write_bytes(b'accepted source bytes')
        target=run/'target.png'; target.write_bytes(source.read_bytes()); staging=run/'staging.png'
        artifact=store.artifact(target)
        store.capture_admitted(dict(schema_version=2,run_id=run.name,clip_id='scene_0001_clip_0001',operation='input',
            source=store.artifact(source),staging=dict(artifact,path=str(staging)),target=artifact,
            recipe=dict(algorithm='identity_copy_v1',parameters={}),evidence=[],created_at='2026-10-19T00:00:00+00:00'))
        store.verify_global()
        staging.write_bytes(b'late conflicting staging bytes')
        with pytest.raises(ProductionRefused): store.verify_global()


@pytest.mark.parametrize('role',['stdout','stderr'])
def test_capture_admitted_extraction_json_binds_original_command_bytes(runtime_run,role):
    import json
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    run=runtime_run[0]; logs=run/'logs/production/processes'; logs.mkdir(parents=True,exist_ok=True)
    stdout=logs/'command.stdout'; stdout.write_bytes(b'accepted raw probe stdout')
    stderr=logs/'command.stderr'; stderr.write_bytes(b'')
    record=logs.parent/'extraction.json'
    record.write_text(json.dumps(dict(original_info=dict(identity=dict(path=str(run/'renamed-original-staging.png'),bytes=100,sha256='a'*64,mtime_ns=123)),command=dict(args=['D:/VideoSi/tools/ffmpeg/bin/ffmpeg.exe'],cwd=str(run),returncode=0,
        timed_out=False,stdout_path=str(stdout),stderr_path=str(stderr),started_at='2026-10-19T00:00:00+00:00',finished_at='2026-10-19T00:00:01+00:00'))),encoding='utf-8')
    with RunLock(run) as lock:
        store=SceneMediaStore(SimpleNamespace(options={'model_stamps':{}}),run,lock=lock)
        store.capture_admitted(dict(evidence=[store.artifact(record)])); store.verify_global()
        dict(stdout=stdout,stderr=stderr)[role].write_bytes(b'late command evidence mutation')
        with pytest.raises(ProductionRefused): store.verify_global()


@pytest.mark.parametrize('fault',['new_failed_raw','changed_json','pcm_same_stat','empty_command_log'])
@pytest.mark.parametrize('phase',['clip_require','image_require'])
def test_source_admission_race_refused_before_upscale_pipeline(runtime_run,monkeypatch,fault,phase):
    """Isolate admission/capture sequencing; semantic gate bodies are controlled unit seams."""
    import json
    from video_ai.runtime import scene_clip_records,image_selection_records,production_scene_upscale
    from video_ai.runtime.workflows import WorkflowTemplate
    from video_ai.runtime import production_visual_templates
    from video_ai.runtime.scene_media_records import SceneMediaResult
    from video_ai.runtime.logging import RunLogger
    from unit.test_scene_media import retained_scene_fixture
    run,config,paths=runtime_run
    fixed=['production/options.json','production/scene-plan.json','production/visual-bible.json',
           'production/scene-plan-commit.json','production/reference-images/wan-inputs.json']
    for name in fixed:
        path=run/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('{}',encoding='utf-8')
    observations=run/'production/scene-clips/observations'; observations.mkdir(parents=True)
    existing=observations/'accepted.json'
    logs=run/'logs/production/processes'; logs.mkdir(parents=True,exist_ok=True)
    stdout=logs/'source-command.stdout'; stdout.write_bytes(b'original command output')
    stderr=logs/'source-command.stderr'; stderr.write_bytes(b'')
    command_record=logs.parent/'source-command.json'
    command_record.write_text(json.dumps(dict(command=dict(args=[str(config.tools['ffmpeg'])],cwd=str(run),returncode=0,
        timed_out=False,stdout_path=str(stdout),stderr_path=str(stderr),started_at='2026-10-19T00:00:00+00:00',finished_at='2026-10-19T00:00:01+00:00'))),encoding='utf-8')
    pcm=run/'audio/unit_0001/pcm.wav'; pcm.parent.mkdir(parents=True); pcm.write_bytes(b'\x01\x00'*100)
    source=run/'accepted-source.mp4'; source.write_bytes(b'controlled admitted source identity')
    from video_ai.runtime.manifest import hash_file
    command_identity=hash_file(command_record)
    existing.write_text(json.dumps(dict(verdict='passed',evidence=[{k:getattr(command_identity,k) for k in ('path','bytes','sha256')}])),encoding='utf-8')
    identity=hash_file(source); clips=retained_scene_fixture(1)
    clips['clips'][0]['source']={k:getattr(identity,k) for k in ('path','bytes','sha256')}
    workflow=run/'production/workflow.json'; workflow.write_text('{}',encoding='utf-8')
    from video_ai.runtime.production_state import ArtifactStamp
    frozen=SimpleNamespace(config=config,options=dict(script_path=str(run/'production/script.txt'),
        workflow_snapshots={k:{'path':str(workflow)} for k in ('upscale','upscale_mapping')},
        model_stamps={'upscale':ArtifactStamp.read(config.models['upscale']).to_dict()},execution_policy={'input_identities':{}}))
    timeline=SimpleNamespace(total_frames=1,clips=[SimpleNamespace(pcm=SimpleNamespace(path=pcm))],as_dict=lambda:{'total_frames':1})
    calls=[]
    def mutate():
        if fault=='new_failed_raw': (observations/'late-failed.json').write_text('{"verdict":"failed"}',encoding='utf-8')
        elif fault=='changed_json': existing.write_text('{"verdict":"failed"}',encoding='utf-8')
        elif fault=='pcm_same_stat':
            import os
            stamp=pcm.stat(); pcm.write_bytes(b'\x02\x00'*100); os.utime(pcm,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        else: stderr.write_bytes(b'late empty command evidence mutation')
    def clip_gate(*args):
        if phase=='clip_require': mutate()
        return clips
    def image_gate(*args):
        if phase=='image_require': mutate()
        return {}
    monkeypatch.setattr(image_selection_records,'_run',lambda frozen:run)
    monkeypatch.setattr(scene_clip_records,'_require_scene_clip_base_acceptance',clip_gate)
    monkeypatch.setattr(image_selection_records,'load_committed_plan',lambda *a:({},{}))
    monkeypatch.setattr(image_selection_records,'require_complete_image_acceptance',image_gate)
    monkeypatch.setattr(WorkflowTemplate,'load',lambda *a:SimpleNamespace())
    monkeypatch.setattr(production_visual_templates,'validate_fixed_visual_template',lambda *a:None)
    def paid_pipeline(*args):
        calls.append('pipeline-entered')
        return SceneMediaResult(status='blocked',error=dict(kind='TestPipeline',message='unexpected pipeline entry',evidence_paths=[]))
    monkeypatch.setattr(production_scene_upscale,'_produce',paid_pipeline)
    result=production_scene_upscale.produce_scene_upscaled_clips(frozen,[],timeline,paths=paths,logger=RunLogger(run,production=True))
    assert result.status=='blocked' and not calls
    assert 'inventory' in result.error['message'] or 'snapshot' in result.error['message']


@pytest.mark.parametrize('fault',['new_failed_raw','changed_json'])
def test_upscale_acceptance_does_not_bless_post_admission_json_race(runtime_run,monkeypatch,fault):
    import video_ai.runtime._scene_upscale_records as records
    from video_ai.runtime.scene_media_records import SceneMediaStore,require_scene_upscale_acceptance_record
    from video_ai.runtime.production_state import ProductionRefused
    store=SceneMediaStore(SimpleNamespace(),runtime_run[0]); store.root.mkdir(parents=True)
    existing=store.root/'complete.json'; existing.write_text('{"accepted":true}',encoding='utf-8')
    earlier=store.artifact(existing); store.guard_paths[str(existing)]=earlier
    def admitted(context):
        if fault=='new_failed_raw': (store.root/'late-terminal.json').write_text('{"status":"rejected"}',encoding='utf-8')
        else: existing.write_text('{"accepted":false}',encoding='utf-8')
        return {'frames':[]}
    monkeypatch.setattr(records,'require_upscale_record',admitted)
    with pytest.raises(ProductionRefused,match='inventory|snapshot'):
        require_scene_upscale_acceptance_record({'store':store})
    assert store.guard_paths[str(existing)]==earlier


@pytest.mark.parametrize('fault',['new_json','changed_json'])
def test_snapshot_adoption_rechecks_inventory_and_original_bytes_after_capture(runtime_run,monkeypatch,fault):
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_state import ProductionRefused
    store=SceneMediaStore(SimpleNamespace(),runtime_run[0]); store.root.mkdir(parents=True)
    path=store.root/'complete.json'; path.write_text('{"original":true}',encoding='utf-8')
    snapshot=store.snapshot_json(directories=(store.root,)); original=store.capture_admitted; changed=[]
    def capture(value):
        result=original(value)
        if not changed:
            changed.append(True)
            if fault=='new_json': (store.root/'late-failed.json').write_text('{"verdict":"failed"}',encoding='utf-8')
            else: path.write_text('{"original":false}',encoding='utf-8')
        return result
    monkeypatch.setattr(store,'capture_admitted',capture)
    with pytest.raises(ProductionRefused,match='inventory|snapshot'): store.adopt_json_snapshot(snapshot)
    assert store.guard_paths[str(path)]==snapshot['artifacts'][str(path)]


def test_extending_capture_cannot_replace_an_earlier_positive_byte_guard(runtime_run):
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_state import ProductionRefused
    store=SceneMediaStore(SimpleNamespace(),runtime_run[0]); path=runtime_run[0]/'accepted.png'; path.write_bytes(b'original')
    original=store.artifact(path); store.capture_admitted(original)
    path.write_bytes(b'new bytes after original admission')
    with pytest.raises(ProductionRefused): store.capture_admitted(store.artifact(path))
    assert store.guard_paths[str(path)]==original


def test_fixed_options_snapshot_binds_bytes_without_reinterpreting_external_source_identity(runtime_run):
    import json
    from video_ai.runtime.scene_media_records import SceneMediaStore
    run=runtime_run[0]; store=SceneMediaStore(SimpleNamespace(),run); options=run/'production/options.json'
    options.parent.mkdir(parents=True,exist_ok=True)
    options.write_text(json.dumps(dict(config_snapshot=dict(source_identity=dict(
        path='D:/VideoSi/cache/old-config-source.json',bytes=100,sha256='a'*64,mtime_ns=123)))),encoding='utf-8')
    snapshot=store.snapshot_json(files=(options,))
    store.adopt_json_snapshot(snapshot)
    assert set(store.guard_paths)=={str(options)}


@pytest.mark.parametrize('prefix',['submission','raw_success'])
@pytest.mark.parametrize('fault',['format','size','local_tool'])
def test_known_later_model_png_validated_before_earlier_paid_work(runtime_run,monkeypatch,prefix,fault):
    """Protocol/native admission are controlled seams; exercise actual PNG preflight."""
    import struct,zlib
    from pathlib import Path
    from video_ai.planning.scene_media import plan_scene_upscale
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    from video_ai.runtime.logging import RunLogger
    import video_ai.runtime.production_scene_upscale as production
    import video_ai.runtime._scene_upscale_records as records
    import video_ai.runtime.scene_upscale_transactions as transactions
    import video_ai.media.scene_upscale as media
    from unit.test_scene_media import retained_scene_fixture
    run,config,paths=runtime_run
    frozen=SimpleNamespace(config=config,options={'model_stamps':{}})
    def png(width,height):
        def chunk(kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
        return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\0'*(width*3))*height))+chunk(b'IEND',b'')
    source=run/'source.mp4'; source.write_bytes(b'controlled native admission source')
    native=run/'native.png'; native.write_bytes(b'controlled native extraction/input admission')
    owned=run/'comfy/output/owned-later.png'; owned.parent.mkdir(parents=True)
    owned.write_bytes(b'wrong format' if fault=='format' else png(768,432) if fault=='size' else png(1920,1080))
    paid=[]; services=[]
    with RunLock(run) as lock:
        store=SceneMediaStore(frozen,run,paths=paths,lock=lock,clip_ids=['scene_0001_clip_0001'])
        clips=retained_scene_fixture(2); clips['clips'][0]['source']=store.artifact(source)
        rows=plan_scene_upscale(clips); input_image=store.artifact(native); model=store.artifact(owned)
        extraction={'frames':[{'image':input_image},{'image':input_image}]}
        context=dict(frozen=frozen,store=store,rows=rows,scene_clips=clips,inputs={},template=SimpleNamespace(),timeline=SimpleNamespace(total_frames=2))
        later=store.frame_dir(rows[1]['frame_id'])
        store.write(later/'request.json',{'frame_id':rows[1]['frame_id']}); store.write(later/'graph.json',{})
        monkeypatch.setattr(records,'validate_extraction',lambda *a,**kw:extraction)
        monkeypatch.setattr(records,'graph_for',lambda *a:{})
        monkeypatch.setattr(records,'expected_request',lambda c,r,*a:{'frame_id':r['frame_id']})
        monkeypatch.setattr(records,'validate_png_receipt',lambda c,r,operation,**kw:{'target':input_image} if operation=='input_copy' else None)
        monkeypatch.setattr(transactions,'validate_scene_frame_submission',lambda *a,**kw:{'output':model} if prefix=='submission' else None)
        monkeypatch.setattr(transactions,'_pending_scene_frame_output',lambda *a,**kw:model,raising=False)
        monkeypatch.setattr(production,'graph_for',lambda *a:{})
        monkeypatch.setattr(production,'expected_request',lambda c,r,*a:{'frame_id':r['frame_id']})
        monkeypatch.setattr(production,'_extract',lambda *a:extraction)
        monkeypatch.setattr(production,'_copy',lambda *a:{'target':input_image})
        class Service:
            def ensure(self): services.append('started')
            def close(self): pass
        def submit(*args,ensure_service,**kwargs):
            ensure_service(); paid.append('earlier POST'); raise AssertionError('earlier paid frame reached before later known PNG validation')
        monkeypatch.setattr(transactions,'recover_or_submit_scene_frame',submit)
        if fault=='local_tool':
            def unavailable(*a,**kw): raise OSError('temporary local PNG tool unavailable')
            monkeypatch.setattr(media.subprocess,'run',unavailable)
        before={str(p):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
        with pytest.raises((ProductionRefused,OSError,RuntimeError)):
            production._produce(context,RunLogger(run,production=True),lambda *a,**kw:SimpleNamespace(),lambda *a:Service())
        assert not paid and not services and not list(store.root.rglob('terminal.json'))
        assert before=={str(p):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('width,height',[(768,432),(1280,720)])
def test_native_retained_extraction_exact_pixels_and_readonly_tamper(runtime_run,width,height):
    from pathlib import Path
    from video_ai.media.scene_upscale import extract_scene_frames,verify_scene_frame_pixels
    from video_ai.runtime.environment import build_child_env
    from video_ai.runtime.processes import run_logged
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.production_state import ProductionRefused
    run,config,paths=runtime_run; logger=RunLogger(run,production=True)
    source=run/'retained-source.mp4'
    result=run_logged(tuple(map(str,[config.tools['ffmpeg'],'-nostdin','-n','-v','error','-f','lavfi','-i',
        f'testsrc2=size={width}x{height}:rate=16','-frames:v','3','-an','-c:v','libx264','-pix_fmt','yuv420p',source])),
        cwd=run,env=build_child_env(paths),timeout=60,logger=logger,stage='test_fixture',unit_id='native')
    assert result.returncode==0
    rows,evidence=extract_scene_frames(source,run/'native-frames',expected_frames=3,width=width,height=height,
        config=config,paths=paths,logger=logger,unit_id='native')
    images=[Path(row['path']) for row in rows]
    assert [p.name for p in images]==['frame_000001.png','frame_000002.png','frame_000003.png']
    before={str(p):p.stat().st_mtime_ns for p in run.rglob('*') if p.is_file()}
    verify_scene_frame_pixels(source,images,expected_frames=3,width=width,height=height,config=config)
    assert before=={str(p):p.stat().st_mtime_ns for p in run.rglob('*') if p.is_file()}
    images[0].write_bytes(images[1].read_bytes())
    with pytest.raises(ProductionRefused,match='pixels differ'):
        verify_scene_frame_pixels(source,images,expected_frames=3,width=width,height=height,config=config)
