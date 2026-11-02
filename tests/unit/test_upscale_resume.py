"""TEST ONLY receipt-bound resume, with real tiny FFmpeg media."""
import json
import pytest
from upscale_helpers import setup, review


def stopped(runtime_run, monkeypatch, frames=2,post_remote_check=False, **kwargs):
    from video_ai.adapters.common import AdapterError, FailureKind
    f = setup(runtime_run, monkeypatch, frames=frames, **kwargs)
    # unit_id is assigned after set_deadlines; intercept validation instead.
    original_validate = f.ug.ComfyClient.validate_template
    def validate(client, template):
        if client.http.unit_id.endswith('000002'):
            if post_remote_check:original_validate(client,template)
            raise AdapterError(FailureKind.ambiguous, 'TEST ONLY local pre-POST timeout',client.http.paths)
        return original_validate(client, template)
    monkeypatch.setattr(f.ug.ComfyClient, 'validate_template', validate)
    result = f.uc.prepare_upscaled_clips(f.config, run_dir=f.run)
    assert result.status == 'failed' and len(f.requests) == 1
    monkeypatch.setattr(f.ug.ComfyClient, 'validate_template', original_validate)
    return f


def test_resume_reuses_completed_checkpoint_and_first_submits_tail(runtime_run, monkeypatch):
    f = stopped(runtime_run, monkeypatch)
    before = f.store.snapshot()
    preserved = {p: p.read_bytes() for p in (f.run/'logs/upscale').glob('frame-*.json')}
    assert callable(getattr(f.uc, 'resume_upscaled_clips', None)), 'resume API is required'
    result = f.uc.resume_upscaled_clips(f.config, run_dir=f.run)
    assert result.status == 'review_required' and len(f.requests) == 2, f.store.snapshot()['stages']['upscale']['error']
    current = f.store.snapshot()
    assert current['units']['frame']['shot_0001:frame_000001'] == before['units']['frame']['shot_0001:frame_000001']
    assert current['events'][:len(before['events'])] == before['events']
    assert all(p.read_bytes() == content for p, content in preserved.items())
    draft = json.loads(result.draft_path.read_text(encoding='utf-8'))
    assert draft['schema_version'] == 2
    assert draft['execution_policy']['total_timeout_seconds'] is None
    path, _ = review(f.run)
    assert f.uc.finalize_upscaled_clips(f.config, run_dir=f.run, review_path=path).passed
    assert f.uc.load_committed_upscaled_clips(f.run)['schema_version'] == 2
    f.store.record_stage('composition','running')
    f.store.record_stage('composition','completed')
    assert f.uc.load_committed_upscaled_clips(f.run)['schema_version'] == 2


@pytest.mark.parametrize('change',['checkpoint','raw_http','input_copy','future_copy','extra_output','extra_frame','extra_media','duplicate_media','extra_prefix','model','config','submission','busy','existing_draft'])
def test_resume_admission_refuses_drift_without_new_post(runtime_run,monkeypatch,change):
    f=stopped(runtime_run,monkeypatch);before=f.store.snapshot()
    if change=='checkpoint':(f.run/'logs/upscale/frame-shot_0001-000001.json').write_bytes(b'{}')
    elif change=='raw_http':next((f.run/'logs/http').glob('*.body')).write_bytes(b'TEST ONLY drift')
    elif change=='input_copy':(f.run/'comfy/input'/f.run.name/'upscale/shot_0001/frame_000002.png').write_bytes(b'TEST ONLY drift')
    elif change=='future_copy':
        import os,time
        target=f.run/'comfy/input'/f.run.name/'upscale/shot_0001/frame_000002.png'
        value=time.time()+1000;os.utime(target,(value,value))
    elif change=='extra_output':(f.run/'comfy/output'/f.run.name/'upscale/shot_0001/frame_000002_orphan.png').write_bytes(b'TEST ONLY orphan')
    elif change=='extra_frame':(f.run/'shots/shot_0001/frames/frame_000003.png').write_bytes(b'TEST ONLY orphan')
    elif change=='extra_media':(f.run/'logs/upscale/media-orphan.json').write_text('{}',encoding='utf-8')
    elif change=='duplicate_media':
        target=next(p for p in (f.run/'logs/upscale').glob('media-*.json') if json.loads(p.read_text(encoding='utf-8'))['info']['identity']['path'].endswith('frames\\frame_000001.png'))
        (f.run/'logs/upscale/media-shot_0001-orphan.json').write_bytes(target.read_bytes())
    elif change=='extra_prefix':(f.run/'comfy/output'/f.run.name/'upscale/orphan').mkdir()
    elif change=='model':f.config.models['upscale'].write_bytes(b'TEST ONLY drift')
    elif change=='config':f.config.config_file.write_bytes(b'{}')
    elif change=='submission':
        # TEST ONLY construct a valid non-null historical intent without POST.
        from video_ai.runtime.manifest import now
        from uuid import uuid4
        uid='shot_0001:frame_000002';graph=f.run/'logs/upscale/test-intent.json';graph.write_text('{}',encoding='utf-8')
        before['units']['frame'][uid]['submission']=dict(state='intent',attempt_id=str(uuid4()),client_id=str(uuid4()),prompt_id=None,number=None,
            request_path=str(graph),response_path=None,submitted_at=now(),last_seen_at=None)
        f.store._write(before)
    elif change=='busy':(f.run/'.upscale.lock').write_text('TEST ONLY busy',encoding='utf-8')
    else:(f.run/'upscaled-clips-draft.json').write_text('{}',encoding='utf-8')
    original=(f.run/'manifest.json').read_bytes()
    with pytest.raises(f.uc.UpscaleRefusal):f.uc.resume_upscaled_clips(f.config,run_dir=f.run)
    assert len(f.requests)==1 and (f.run/'manifest.json').read_bytes()==original


@pytest.mark.parametrize('mode',['external','transaction_failure'])
def test_owned_admission_and_transaction_refusal_preserve_manifest(runtime_run,monkeypatch,mode):
    from types import SimpleNamespace
    f=stopped(runtime_run,monkeypatch);original=(f.run/'manifest.json').read_bytes()
    class Manager:
        def __init__(self,paths,store,logger):self.store=store
        def ensure(self,spec):
            f.actions.append('resume_start')
            self.store.update(lambda data:data['services'].update({}))
            return SimpleNamespace(owned=mode!='external',process=f.process)
        def stop(self,handle):f.actions.append('resume_stop');f.process.stopped=True
    monkeypatch.setattr(f.ug,'ServiceManager',Manager)
    if mode=='transaction_failure':
        write=f.store.__class__._write
        def refuse_write(store,data):
            if 'upscale_resume' in data['workflows']:raise OSError('TEST ONLY atomic write failure')
            return write(store,data)
        monkeypatch.setattr(f.store.__class__,'_write',refuse_write)
    with pytest.raises(f.uc.UpscaleRefusal):f.uc.resume_upscaled_clips(f.config,run_dir=f.run)
    assert len(f.requests)==1 and (f.run/'manifest.json').read_bytes()==original
    assert ('resume_stop' in f.actions)==(mode=='transaction_failure')


def test_default_terminal_and_resume_receipt_replacement_remain_forbidden(runtime_run,monkeypatch):
    f=stopped(runtime_run,monkeypatch)
    with pytest.raises(ValueError):f.store.record_stage('upscale','running')
    with pytest.raises(ValueError):f.store.record_unit('frame','shot_0001:frame_000002','running')
    result=f.uc.resume_upscaled_clips(f.config,run_dir=f.run)
    assert result.status=='review_required'
    with pytest.raises(ValueError):f.store.update(lambda data:data['workflows'].pop('upscale_resume'))
    with pytest.raises(f.uc.UpscaleRefusal):f.uc.resume_upscaled_clips(f.config,run_dir=f.run)


@pytest.mark.parametrize('value',[True,False,0,-1,float('inf'),float('nan'),None])
def test_resume_policy_keeps_finite_operation_deadlines(value):
    from video_ai.runtime._upscale_resume import check_policy
    with pytest.raises(ValueError):check_policy(dict(total_timeout_seconds=None,frame_timeout_seconds=value,media_command_timeout_seconds=300,request_timeout_seconds=30))


def test_resume_http_caps_wall_window_before_recording(runtime_run,monkeypatch):
    import time
    from video_ai.runtime.logging import RunLogger
    f=setup(runtime_run,monkeypatch)
    http=f.ug.DeadlineHttp(f.config.services['comfyui'],f.config.timeouts['comfy_request'],RunLogger(f.run))
    http.paths=[];http.unit_id='shot_0001:frame_000001';http.template=f.ui.template(f.config)
    http.set_deadlines(None,time.monotonic()+180);http.wall_end=time.time()+.5
    monkeypatch.setattr(http,'remaining',lambda:180)
    http.request('GET','/object_info')
    request=json.loads(next((f.run/'logs/http').glob('*.request.json')).read_text(encoding='utf-8'))
    assert request['timeout']<=.5


def test_resume_old_copy_is_not_new_frame_start_and_no_clip_budget(runtime_run,monkeypatch):
    import os,time
    f=stopped(runtime_run,monkeypatch)
    path=f.run/'comfy/input'/f.run.name/'upscale/shot_0001/frame_000002.png'
    old=time.time()-1000;os.utime(path,(old,old))
    identity=path.stat().st_mtime_ns
    monkeypatch.setattr(f.ug,'clip_deadline_seconds',lambda **kw:(_ for _ in ()).throw(AssertionError('resume has no clip budget')))
    result=f.uc.resume_upscaled_clips(f.config,run_dir=f.run)
    assert result.status=='review_required',f.store.snapshot()['stages']['upscale']['error']
    draft=json.loads(result.draft_path.read_text(encoding='utf-8'))
    assert draft['clips'][0]['frames'][1]['input_copy_identity']['mtime_ns']==identity
    assert len(f.requests)==2 and path.stat().st_mtime_ns==identity


def test_resume_three_encoded_clips_partial_fourth_and_unattempted_later(runtime_run,monkeypatch):
    from video_ai.adapters.common import AdapterError,FailureKind
    f=setup(runtime_run,monkeypatch,frames=1,clip_counts=[1,1,1,3,1,1,1])
    original=f.ug.ComfyClient.validate_template
    def validate(client,template):
        if client.http.unit_id=='shot_0004:frame_000002':raise AdapterError(FailureKind.ambiguous,'TEST ONLY local timeout')
        return original(client,template)
    monkeypatch.setattr(f.ug.ComfyClient,'validate_template',validate)
    assert f.uc.prepare_upscaled_clips(f.config,run_dir=f.run).status=='failed'
    assert len(f.requests)==4
    preserved={p:p.read_bytes() for uid in ('shot_0001','shot_0002','shot_0003') for p in [f.run/'shots'/uid/'upscaled.mp4',f.run/'logs/upscale'/f'clip-{uid}.json']}
    before=f.store.snapshot();extractions={p:p.read_bytes() for p in (f.run/'logs/upscale').glob('extract-*.json')}
    monkeypatch.setattr(f.ug.ComfyClient,'validate_template',original)
    extract,encode=f.ug.extract_video_frames,f.ug.encode_video_frames
    def bounded_extract(*args,**kwargs):
        assert kwargs['timeout']==300
        return extract(*args,**kwargs)
    def bounded_encode(*args,**kwargs):
        assert kwargs['timeout']==300
        return encode(*args,**kwargs)
    monkeypatch.setattr(f.ug,'extract_video_frames',bounded_extract)
    monkeypatch.setattr(f.ug,'encode_video_frames',bounded_encode)
    result=f.uc.resume_upscaled_clips(f.config,run_dir=f.run)
    assert result.status=='review_required' and result.clip_count==7,f.store.snapshot()['stages']['upscale']['error']
    assert len(f.requests)==9
    assert [g['5']['inputs']['filename_prefix'].split('/')[-2:] for g in f.requests[4:]]==[
        ['shot_0004','frame_000002'],['shot_0004','frame_000003'],['shot_0005','frame_000001'],['shot_0006','frame_000001'],['shot_0007','frame_000001']]
    assert all(p.read_bytes()==content for p,content in preserved.items())
    assert all(p.read_bytes()==content for p,content in extractions.items())
    assert all(f.store.snapshot()['units']['frame'][uid]==record for uid,record in before['units']['frame'].items() if record['status']=='completed')
    path,_=review(f.run)
    assert f.uc.finalize_upscaled_clips(f.config,run_dir=f.run,review_path=path).passed
    assert len(f.uc.load_committed_upscaled_clips(f.run)['clips'])==7


@pytest.mark.parametrize('change',['receipt','snapshot','policy','completed_record','missing_policy','missing_receipt'])
def test_schema2_independent_replay_rejects_proof_drift(runtime_run,monkeypatch,change):
    from pathlib import Path
    from video_ai.config import read_json
    from video_ai.runtime._upscale_evidence import validate
    f=stopped(runtime_run,monkeypatch)
    result=f.uc.resume_upscaled_clips(f.config,run_dir=f.run)
    assert result.status=='review_required'
    draft=read_json(result.draft_path);snapshot=f.store.snapshot();context=f.ui.inputs(f.config,f.run)
    identity=draft['execution_policy']['resume_identity'];proof=read_json(Path(identity['path']))
    if change=='receipt':Path(identity['path']).write_text('{}',encoding='utf-8')
    elif change=='snapshot':Path(proof['manifest_identity']['path']).write_text('{}',encoding='utf-8')
    elif change=='policy':draft['execution_policy']['frame_timeout_seconds']=True
    elif change=='completed_record':snapshot['units']['frame']['shot_0001:frame_000001']['error']={'message':'TEST ONLY tamper'}
    elif change=='missing_policy':draft.pop('execution_policy')
    else:snapshot['workflows'].pop('upscale_resume')
    with pytest.raises((ValueError,OSError,KeyError)):validate(f.config,f.run,draft,context,snapshot)


def test_service_proxy_only_buffers_service_updates_and_flushes(runtime_run,monkeypatch):
    from video_ai.runtime._upscale_resume import StagedServiceStore
    from video_ai.runtime.manifest import now
    f=stopped(runtime_run,monkeypatch);before=f.store.snapshot();proxy=StagedServiceStore(f.store)
    with pytest.raises(ValueError):proxy.update(lambda data:data['resources'].update(TEST_ONLY=True))
    record=dict(name='comfyui',url=f.config.services['comfyui'],owned=True,pid=123,started_at=now(),status='healthy',updated_at=now())
    def mutate(data):data['services']['comfyui']=record
    proxy.update(mutate)
    assert f.store.snapshot()==before
    proxy.activate()
    assert proxy.active and proxy.pending==[] and f.store.snapshot()['services']=={'comfyui':record}


def test_resume_single_frame_deadline_failure_never_posts(runtime_run,monkeypatch):
    import time
    f=stopped(runtime_run,monkeypatch);base=f.ug.DeadlineHttp.set_deadlines
    monkeypatch.setattr(f.ug.DeadlineHttp,'set_deadlines',lambda self,c,e:base(self,c,time.monotonic()-.01))
    result=f.uc.resume_upscaled_clips.__wrapped__(f.config,run_dir=f.run)
    assert result.status=='failed' and len(f.requests)==1
    assert f.store.snapshot()['units']['frame']['shot_0001:frame_000002']['submission'] is None
    assert f.actions[-1]=='stop'


def test_post_commit_service_flush_failure_keeps_receipt_and_stops_owned(runtime_run,monkeypatch):
    from types import SimpleNamespace
    from video_ai.runtime.manifest import now
    f=stopped(runtime_run,monkeypatch);before=f.store.snapshot();f.process.stopped=False
    record=dict(name='comfyui',url=f.config.services['comfyui'],owned=True,pid=123,started_at=now(),status='healthy',updated_at=now())
    class Manager:
        def __init__(self,paths,store,logger):self.store=store
        def ensure(self,spec):
            self.store.update(lambda data:data['services'].update(comfyui=record))
            return SimpleNamespace(owned=True,process=f.process)
        def stop(self,handle):
            f.process.stopped=True;f.actions.append('resume_stop')
            self.store.update(lambda data:data['services'].update(comfyui=dict(record,status='stopped')))
    monkeypatch.setattr(f.ug,'ServiceManager',Manager)
    write=f.store.__class__._write
    failed=[]
    def fail_first_flush(store,data):
        if 'upscale_resume' in data['workflows'] and data['services'].get('comfyui',{}).get('status')=='healthy' and not failed:
            failed.append(True);raise OSError('TEST ONLY post-commit flush failure')
        return write(store,data)
    monkeypatch.setattr(f.store.__class__,'_write',fail_first_flush)
    result=f.uc.resume_upscaled_clips(f.config,run_dir=f.run)
    assert result.status=='failed' and len(f.requests)==1 and f.process.stopped
    current=f.store.snapshot()
    assert 'upscale_resume' in current['workflows'] and current['stages']['upscale']['status']=='failed'
    assert current['units']['frame']['shot_0001:frame_000001']==before['units']['frame']['shot_0001:frame_000001']
    assert current['events'][:len(before['events'])]==before['events']


def test_resume_complete_prefix_without_unsubmitted_tail(runtime_run,monkeypatch):
    from video_ai.adapters.common import AdapterError,FailureKind
    f=setup(runtime_run,monkeypatch)
    stop=f.ug.ServiceManager.stop
    def fail_stop(manager,handle):
        stop(manager,handle)
        raise AdapterError(FailureKind.ambiguous,'TEST ONLY stopped after complete prefix')
    monkeypatch.setattr(f.ug.ServiceManager,'stop',fail_stop)
    assert f.uc.prepare_upscaled_clips(f.config,run_dir=f.run).status=='failed'
    before=f.store.snapshot();assert all(unit['status']=='completed' for unit in before['units']['frame'].values())
    monkeypatch.setattr(f.ug.ServiceManager,'stop',stop)
    result=f.uc.resume_upscaled_clips(f.config,run_dir=f.run)
    assert result.status=='review_required' and len(f.requests)==2
    assert f.store.snapshot()['units']['frame']==before['units']['frame']
    from video_ai.config import read_json
    proof=read_json(result.draft_path)['execution_policy']['resume_identity']
    from pathlib import Path
    assert read_json(Path(proof['path']))['unit_id'] is None


@pytest.mark.parametrize('state',['intent','accepted','ambiguous','rejected','failed','completed'])
def test_any_non_null_submission_tail_refuses_without_post(runtime_run,monkeypatch,state):
    from uuid import uuid4
    from video_ai.runtime.manifest import now
    f=stopped(runtime_run,monkeypatch);snapshot=f.store.snapshot();uid='shot_0001:frame_000002'
    path=f.run/'logs/upscale/test-intent.json';path.write_text('{}',encoding='utf-8')
    accepted=state in ('accepted','failed','completed')
    snapshot['units']['frame'][uid]['submission']=dict(state=state,attempt_id=str(uuid4()),client_id=str(uuid4()),prompt_id=str(uuid4()) if accepted else None,
        number=0 if accepted else None,request_path=str(path),response_path=str(path) if accepted else None,submitted_at=now(),last_seen_at=now() if accepted else None)
    f.store._write(snapshot)
    original=(f.run/'manifest.json').read_bytes()
    with pytest.raises(f.uc.UpscaleRefusal):f.uc.resume_upscaled_clips(f.config,run_dir=f.run)
    assert len(f.requests)==1 and (f.run/'manifest.json').read_bytes()==original


def test_resume_http_recording_reserve_exhaustion_fails_before_request(runtime_run,monkeypatch):
    import time
    from video_ai.runtime.logging import RunLogger
    from video_ai.adapters.common import AdapterError
    f=setup(runtime_run,monkeypatch)
    http=f.ug.DeadlineHttp(f.config.services['comfyui'],180,RunLogger(f.run))
    http.paths=[];http.unit_id='shot_0001:frame_000001';http.template=f.ui.template(f.config)
    http.set_deadlines(None,time.monotonic()+180);http.wall_end=time.time()+.05
    with pytest.raises(AdapterError):http.request('GET','/object_info')
    assert not f.requests and not list((f.run/'logs/http').glob('*.request.json'))


def test_legacy_http_recording_reserve_bounds_coarse_clock_budget(runtime_run,monkeypatch):
    """TEST ONLY coarse monotonic clock; real durable HTTP timestamps and logs."""
    import os,time
    from datetime import datetime
    from types import SimpleNamespace
    from http_helpers import Response,ScriptedTransport
    from video_ai.runtime import _upscale_generation as generation
    from video_ai.runtime.logging import RunLogger
    run,_,_=runtime_run
    # Model a 20ms clock discrepancy at the actual durable request boundary,
    # independent of machine scheduling. Keep raw HTTP timestamps unchanged.
    copied=run/'TEST-ONLY-clock-copy.bin';copied.write_bytes(b'TEST ONLY clock fixture')
    logger=RunLogger(run);save=logger.save_json
    def record(name,data):
        if name.endswith('.request.json'):
            origin=datetime.fromisoformat(data['started_at']).timestamp()-.02
            os.utime(copied,(origin,origin))
        return save(name,data)
    monkeypatch.setattr(logger,'save_json',record)
    monkeypatch.setattr(generation,'time',SimpleNamespace(monotonic=lambda:0.,time=time.time))
    transport=ScriptedTransport(lambda request,timeout:Response({'queue_running':[],'queue_pending':[]}))
    http=generation.DeadlineHttp('http://127.0.0.1:8188',600,logger,transport=transport)
    http.set_deadlines(None,180);http.paths=[];http.unit_id='shot_0001:frame_000001'
    assert not hasattr(http,'wall_end'),'exercise the legacy schema1 budget path'
    http.request('GET','/queue')
    request=json.loads(next((run/'logs/http').glob('*.request.json')).read_text(encoding='utf-8'))
    started=datetime.fromisoformat(request['started_at']).timestamp()
    assert 0<request['timeout']<=copied.stat().st_mtime_ns/1e9+180-started
    assert len(transport.calls)==1 and request['method']=='GET'


@pytest.mark.parametrize('window',[.05,.1])
def test_legacy_recording_reserve_exhaustion_stops_before_http(runtime_run,monkeypatch,window):
    """TEST ONLY zero/negative send budget must never create an HTTP intent."""
    import time
    from types import SimpleNamespace
    from http_helpers import Response,ScriptedTransport
    from video_ai.adapters.common import AdapterError,FailureKind
    from video_ai.runtime import _upscale_generation as generation
    from video_ai.runtime.logging import RunLogger
    run,_,_=runtime_run
    monkeypatch.setattr(generation,'time',SimpleNamespace(monotonic=lambda:0.,time=time.time))
    transport=ScriptedTransport(lambda request,timeout:Response({}))
    http=generation.DeadlineHttp('http://127.0.0.1:8188',600,RunLogger(run),transport=transport)
    http.set_deadlines(None,window)
    with pytest.raises(AdapterError) as error:
        http.request('POST','/prompt',json_body={'prompt':{},'client_id':'TEST ONLY'})
    assert error.value.kind==FailureKind.ambiguous
    assert not transport.calls and not list((run/'logs/http').glob('*.request.json'))


def test_active_service_proxy_checks_actual_manifest_not_admission_preview(runtime_run,monkeypatch):
    from video_ai.runtime._upscale_resume import StagedServiceStore
    from video_ai.runtime.manifest import now
    f=stopped(runtime_run,monkeypatch);proxy=StagedServiceStore(f.store);proxy.activate()
    record=dict(name='comfyui',url=f.config.services['comfyui'],owned=True,pid=123,started_at=now(),status='healthy',updated_at=now())
    f.store.update(lambda data:data['services'].update(comfyui=record))
    before=f.store.snapshot()
    def conditional(data):
        if data['services']:data['resources']['summary']={'TEST_ONLY':'illegal mutation'}
    with pytest.raises(ValueError):proxy.update(conditional)
    assert f.store.snapshot()==before


def test_resume_and_v2_replay_succeed_after_original_clip_deadline(runtime_run,monkeypatch):
    import time
    from datetime import datetime
    from video_ai.config import read_json
    f=stopped(runtime_run,monkeypatch,clip_timeout=5,request_timeout=1)
    extraction=read_json(next((f.run/'logs/upscale').glob('extract-*.json')))
    old_end=datetime.fromisoformat(extraction['command']['started_at']).timestamp()+5
    # Real elapsed time, real media and real raw HTTP timestamps: no validator mock.
    time.sleep(max(0,old_end+.2-time.time()))
    result=f.uc.resume_upscaled_clips(f.config,run_dir=f.run)
    assert result.status=='review_required',f.store.snapshot()['stages']['upscale']['error']
    unit=f.store.snapshot()['units']['frame']['shot_0001:frame_000002']
    assert datetime.fromisoformat(unit['started_at']).timestamp()>old_end
    path,_=review(f.run)
    assert f.uc.finalize_upscaled_clips(f.config,run_dir=f.run,review_path=path).passed
    assert f.uc.load_committed_upscaled_clips(f.run)['schema_version']==2


def indexed_tail_post(f,error_owner,posted_unit='tail'):
    """TEST ONLY contradictory durable HTTP, while the tail submission stays null."""
    from uuid import uuid4
    uid='shot_0001:frame_000002'
    original=next(json.loads(path.read_text(encoding='utf-8')) for path in (f.run/'logs/http').glob('*.request.json')
        if json.loads(path.read_text(encoding='utf-8'))['method']=='POST')
    targets={'tail':uid,'future':'shot_0001:frame_000003','completed':'shot_0001:frame_000001'}
    request=dict(original,unit_id=targets[posted_unit])
    path=f.run/'logs/http'/f'{uuid4().hex}.request.json'
    path.write_text(json.dumps(request,allow_nan=False,indent=2),encoding='utf-8')
    snapshot=f.store.snapshot()
    record=snapshot['stages']['upscale'] if error_owner=='stage' else snapshot['units']['frame'][uid]
    record['error']['evidence_paths'].append(str(path))
    # Construct the durable contradiction directly; ordinary terminal update is
    # intentionally unchanged and would refuse modifying these stopped records.
    f.store._write(snapshot)
    assert snapshot['units']['frame'][uid]['submission'] is None
    assert snapshot['units']['frame'][uid]['artifacts']==[]
    return path,snapshot


@pytest.mark.parametrize('error_owner',['tail','stage'])
@pytest.mark.parametrize('posted_unit',['tail','future','completed'])
def test_indexed_historical_tail_post_refuses_before_resume_and_any_new_post(runtime_run,monkeypatch,error_owner,posted_unit):
    f=stopped(runtime_run,monkeypatch,frames=3);path,snapshot=indexed_tail_post(f,error_owner,posted_unit)
    original=(f.run/'manifest.json').read_bytes();posts=len(f.requests);actions=list(f.actions)
    refused=False
    try:f.uc.resume_upscaled_clips(f.config,run_dir=f.run)
    except f.uc.UpscaleRefusal as exc:
        refused=True
        assert 'historical' in str(exc)
    assert len(f.requests)==posts,'historical tail POST must prevent every new POST'
    assert refused and f.actions==actions
    assert (f.run/'manifest.json').read_bytes()==original
    assert f.store.snapshot()['units']['frame']==snapshot['units']['frame']
    assert path.read_bytes() and not list((f.run/'logs/upscale').glob('resume-*.json'))


@pytest.mark.parametrize('error_owner',['tail','stage'])
@pytest.mark.parametrize('posted_unit',['tail','future','completed'])
def test_locked_resume_transaction_rejects_indexed_historical_tail_post(runtime_run,monkeypatch,error_owner,posted_unit):
    from video_ai.runtime._upscale_resume import reconstruct,freeze
    from video_ai.runtime.manifest import hash_file,thaw
    f=stopped(runtime_run,monkeypatch,frames=3);context=f.ui.inputs(f.config,f.run)
    _,records,_=reconstruct(f.config,f.run,f.store.snapshot(),context)
    path,snapshot=indexed_tail_post(f,error_owner,posted_unit)
    records[path.relative_to(f.run).as_posix()]=thaw(hash_file(path))
    # A caller can supply a freshly sealed but contradictory receipt. The locked
    # transaction must reconstruct and reject it independently of the entrypoint.
    identity=freeze(f.run,snapshot,records,f.config,context)
    original=(f.run/'manifest.json').read_bytes();posts=len(f.requests)
    with pytest.raises(ValueError,match='historical'):
        f.store.resume_unsubmitted_upscale(identity,expected_snapshot=snapshot,unit_id='shot_0001:frame_000002')
    assert len(f.requests)==posts and (f.run/'manifest.json').read_bytes()==original
    assert f.store.snapshot()==snapshot and 'upscale_resume' not in f.store.snapshot()['workflows']


@pytest.mark.parametrize('posted_unit',['tail','future','completed'])
def test_formal_consumer_rejects_resealed_historical_tail_post(runtime_run,monkeypatch,posted_unit):
    from pathlib import Path
    from video_ai.runtime.manifest import hash_file,thaw
    from video_ai.runtime.timeline_checks import _artifact
    from video_ai.config import read_json
    f=stopped(runtime_run,monkeypatch,frames=3)
    result=f.uc.resume_upscaled_clips(f.config,run_dir=f.run)
    assert result.status=='review_required'
    path,_=review(f.run)
    assert f.uc.finalize_upscaled_clips(f.config,run_dir=f.run,review_path=path).passed
    assert f.uc.load_committed_upscaled_clips(f.run)['schema_version']==2
    draft=read_json(result.draft_path);snapshot=f.store.snapshot()
    receipt_path=Path(draft['execution_policy']['resume_identity']['path']);proof=read_json(receipt_path)
    target='shot_0001:frame_000003' if posted_unit=='future' else 'shot_0001:frame_000002'
    post=next(path for path in (f.run/'logs/http').glob('*.request.json')
        if read_json(path)['method']=='POST' and read_json(path)['unit_id']==target)
    if posted_unit=='completed':
        from uuid import uuid4
        original=next(read_json(path) for path in (f.run/'logs/http').glob('*.request.json')
            if read_json(path)['method']=='POST' and read_json(path)['unit_id']=='shot_0001:frame_000001')
        post=f.run/'logs/http'/f'{uuid4().hex}.request.json'
        post.write_text(json.dumps(original,allow_nan=False,indent=2),encoding='utf-8')
    # TEST ONLY refresh all technical publication identities, deliberately claiming
    # the real new tail POST was historical. This reaches semantics, not hash drift.
    proof['reused_identities'][post.relative_to(f.run).as_posix()]=thaw(hash_file(post))
    receipt_path.write_text(json.dumps(proof,allow_nan=False,indent=2),encoding='utf-8')
    identity=thaw(hash_file(receipt_path));draft['execution_policy']['resume_identity']=identity
    result.draft_path.write_text(json.dumps(draft,allow_nan=False,indent=2),encoding='utf-8')
    path,_=review(f.run)
    report=dict(draft,status='completed',passed=True,validation=f.uc.validation(True),review_identity=thaw(hash_file(path)))
    result.clips_path.write_text(json.dumps(report,allow_nan=False,indent=2),encoding='utf-8')
    report_id=hash_file(result.clips_path)
    snapshot['workflows']['upscale_resume']=identity;snapshot['workflows']['upscale_report']=thaw(report_id)
    snapshot['stages']['upscale']['artifacts']=[_artifact(report_id)]
    f.store._write(snapshot)
    with pytest.raises(ValueError,match='historical'):f.uc.load_committed_upscaled_clips(f.run)


def test_resume_retains_error_indexed_legal_tail_get_evidence(runtime_run,monkeypatch):
    from pathlib import Path
    from video_ai.config import read_json
    f=stopped(runtime_run,monkeypatch,post_remote_check=True)
    old=f.store.snapshot();uid='shot_0001:frame_000002'
    paths=[Path(path) for path in old['units']['frame'][uid]['error']['evidence_paths']]
    requests=[path for path in paths if path.name.endswith('.request.json')]
    assert len(requests)==1 and read_json(requests[0])['method']=='GET'
    assert read_json(requests[0])['unit_id']==uid and len(f.requests)==1
    preserved={path:path.read_bytes() for path in paths}
    result=f.uc.resume_upscaled_clips(f.config,run_dir=f.run)
    assert result.status=='review_required' and len(f.requests)==2
    draft=read_json(result.draft_path);proof=read_json(Path(draft['execution_policy']['resume_identity']['path']))
    assert all(path.relative_to(f.run).as_posix() in proof['reused_identities'] for path in paths)
    assert all(path.read_bytes()==content for path,content in preserved.items())
    assert f.store.snapshot()['units']['frame']['shot_0001:frame_000001']==old['units']['frame']['shot_0001:frame_000001']
    path,_=review(f.run)
    assert f.uc.finalize_upscaled_clips(f.config,run_dir=f.run,review_path=path).passed
    assert f.uc.load_committed_upscaled_clips(f.run)['schema_version']==2
