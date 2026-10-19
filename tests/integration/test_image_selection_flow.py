"""Prepared runs use real committed plans, original PNGs and local SMTP doubles."""
import hashlib
import json
from pathlib import Path
import struct
import zlib

import pytest

from integration.test_scene_planning import scene_setup, produce
from unit.test_production_inputs import production_config as stub_production_config


@pytest.fixture
def production_config(stub_production_config,runtime_run,request):
    from video_ai.config import load_config
    config=stub_production_config
    data=json.loads(config.config_file.read_text(encoding='utf-8'))
    for name in ('ffmpeg','ffprobe'): data['tools'][name]=str(runtime_run[1].tools[name])
    if hasattr(request,'param'):
        from unit.test_jimeng_config import image_settings
        data.update(production_strategy='paragraph_jimeng_v1',image_generation=image_settings(),
                    selection_email=dict(max_mime_bytes=request.param))
    config.config_file.write_text(json.dumps(data),encoding='utf-8')
    return load_config(config.config_file)


def png(width=2560, height=1440):
    def chunk(kind, data):
        return struct.pack('!I', len(data))+kind+data+struct.pack('!I', zlib.crc32(kind+data))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('!2I5B', width,height,8,2,0,0,0))
            +chunk(b'IDAT', zlib.compress((b'\0'+b'\x70\x90\xb0'*width)*height)) +chunk(b'IEND', b''))


class SMTP:
    def __init__(self):
        self.messages=[]; self.closed=0; self.fail=None; self.fail_on=None
    def factory(self, host, port, **kwargs):
        assert kwargs['context'].verify_mode != 0
        outer=self
        class Connection:
            def login(self, user, password):
                if outer.fail=='auth': raise OSError('AUTH test-secret')
                return 235,b'ok'
            def ehlo(self): return 250,b'ok'
            def mail(self, address): return 250,b'ok'
            def rcpt(self, address): return 250,b'ok'
            def data(self, raw):
                outer.messages.append(raw)
                if outer.fail=='unknown' and (outer.fail_on is None or len(outer.messages)==outer.fail_on):
                    raise TimeoutError('private reply lost')
                if outer.fail=='reject': return 550,b'private rejected text'
                return 250,b'ok'
            def quit(self): outer.closed+=1; return 221,b'bye'
            def close(self): outer.closed+=1
        return Connection()


@pytest.fixture
def selection_setup(scene_setup, monkeypatch):
    from video_ai.runtime.jimeng_candidates import generate_candidates
    from video_ai.runtime.manifest import now
    s=scene_setup
    s['bible'],s['plan']=produce(s)
    class Images:
        settings=s['frozen'].config.image_generation
        def submit(self, prompt): return dict(task_id='task_1',request_id='req',diagnostic={})
        def query(self, task_id, **kwargs): return dict(status='done',request_id='q',diagnostic={},image_urls=['https://cdn.example/img'])
        def download(self,url,**kwargs): return png()
    s['manifests']={}
    for scene in s['plan']['scenes']:
        sid=scene['scene_id']
        generate_candidates(s['frozen'],sid,scene['image_prompt'],client=Images(),
            inspect=lambda p:dict(width=2560,height=1440,format='png'),sleep=lambda _:None)
        s['manifests'][sid]=s['run']/f'production/jimeng/{sid}/candidates.json'
    for stage,payload in [('units',s['units']),('timeline',s['timeline'].as_dict())]:
        (s['run']/f'production/{stage}.json').write_text(json.dumps(dict(schema_version=1,
            execution_mode='automatic',run_id=s['run'].name,stage=stage,created_at=now(),
            status='completed',input_records={},payload=payload),ensure_ascii=False),encoding='utf-8')
    s['smtp']=SMTP()
    monkeypatch.setenv('VIDEO_AI_SMTP_AUTH_CODE','test-secret')
    return s


def prepare(s,index=1,**kwargs):
    from video_ai.runtime.production_image_selection import prepare_image_batch
    return prepare_image_batch(s['frozen'],s['units'],s['timeline'],
        [s['manifests'][sid] for sid in s['plan']['batches'][index-1]],batch_index=index,
        paths=s['paths'],logger=s['logger'],smtp_factory=s['smtp'].factory,**kwargs)


def consume(s,path,**kwargs):
    from video_ai.runtime.production_image_selection import consume_image_selection
    return consume_image_selection(s['frozen'],s['units'],s['timeline'],path,
        paths=s['paths'],logger=s['logger'],**kwargs)


def selection(s,result,*,intent='accept',observation=None):
    folder=Path(result.selection_template).parent
    value=json.loads(Path(result.selection_template).read_text(encoding='utf-8'))
    batch=json.loads((folder/'batch.json').read_text(encoding='utf-8'))
    value.update(intent=intent,selections=[dict(scene_id=r['scene_id'],
        candidate_id=r['candidates'][0]['candidate_id'],sha256=r['candidates'][0]['sha256']) for r in batch['scenes']],
        observation=observation)
    path=s['run']/'selection.json'; path.write_text(json.dumps(value),encoding='utf-8')
    return path,value


def test_prepare_wait_and_resume_reuses_notification_and_releases_lock(selection_setup):
    s=selection_setup; result=prepare(s)
    assert result.status=='awaiting_image_selection' and result.exit_code==3, result.error
    assert not result.all_images_accepted
    assert len(s['smtp'].messages)==1 and s['smtp'].closed
    assert prepare(s).to_dict()==result.to_dict()
    assert len(s['smtp'].messages)==1
    assert not (s['run']/'.make-video.lock').exists()
    assert set(result.to_dict())==set('schema_version production_strategy run_id run_dir status active_stage batch_id selection_template all_images_accepted log_dir error'.split())


def test_unknown_delivery_never_automatically_retries_or_accepts(selection_setup):
    s=selection_setup; s['smtp'].fail='unknown'
    result=prepare(s)
    assert result.status=='email_delivery_unknown' and result.exit_code==3
    s['smtp'].fail=None
    assert prepare(s).status=='email_delivery_unknown'
    assert len(s['smtp'].messages)==1
    path,_=selection(s,result)
    assert consume(s,path).status=='email_delivery_unknown'
    assert not list((s['run']/'production/image-selection').rglob('accepted.json'))


def test_auth_fix_resumes_only_notification_and_redacts_credentials(selection_setup):
    s=selection_setup; s['smtp'].fail='auth'
    result=prepare(s)
    assert result.status=='blocked'
    assert not list((s['run']/'production/image-selection').rglob('intent.json'))
    s['smtp'].fail=None
    assert prepare(s).status=='awaiting_image_selection'
    text='\n'.join(p.read_text(encoding='utf-8',errors='replace') for p in (s['run']/'production/image-selection').rglob('*.json'))
    assert 'test-secret' not in text and 'private reply' not in text


def test_draft_and_number_selection_do_not_approve_whole_group(selection_setup):
    s=selection_setup; result=prepare(s)
    path,value=selection(s,result,intent='draft')
    value['selections']=[]; path.write_text(json.dumps(value),encoding='utf-8')
    assert consume(s,path).status=='awaiting_image_selection'
    path,_=selection(s,result)
    accepted=consume(s,path)
    assert accepted.status=='image_batch_accepted' and not accepted.all_images_accepted
    assert not (s['run']/'production/image-selection/complete-acceptance.json').exists()


def test_two_batches_require_explicit_whole_group_observation_and_original_revalidation(selection_setup):
    from video_ai.runtime.image_selection_records import require_complete_image_acceptance
    s=selection_setup
    first=prepare(s); path,_=selection(s,first); assert consume(s,path).status=='image_batch_accepted'
    second=prepare(s,2); path,value=selection(s,second)
    assert consume(s,path).status=='awaiting_image_selection'
    all_choices=[]
    for accepted in sorted((s['run']/'production/image-selection').glob('image_batch_*/accepted.json')):
        all_choices += [{k:r[k] for k in ('scene_id','candidate_id','sha256')} for r in json.loads(accepted.read_text())['selections']]
    value['observation']=dict(scope='all_selected_images',review_method='human_image',reviewer='fixture user',
        viewed_images=all_choices,subject_consistency='passed',style_consistency='passed',verdict='passed',issues=[],reason='fixture explicit observation')
    path.write_text(json.dumps(value),encoding='utf-8')
    result=consume(s,path)
    assert result.all_images_accepted and result.status=='image_batch_accepted'
    receipt=require_complete_image_acceptance(s['frozen'],s['units'],s['timeline'])
    assert len(receipt['selections'])==2
    Path(receipt['selections'][0]['path']).write_bytes(b'changed')
    with pytest.raises(ValueError): require_complete_image_acceptance(s['frozen'],s['units'],s['timeline'])


@pytest.mark.parametrize('change',['run','missing','duplicate','sha','unknown'])
def test_invalid_acceptance_is_refused(selection_setup,change):
    s=selection_setup; result=prepare(s); path,value=selection(s,result)
    if change=='run': value['run_id']='foreign'
    elif change=='missing': value['selections']=[]
    elif change=='duplicate': value['selections']*=2
    elif change=='sha': value['selections'][0]['sha256']='a'*64
    else: value['selections'][0]['candidate_id']='unknown'
    path.write_text(json.dumps(value),encoding='utf-8')
    assert consume(s,path).status=='blocked'
    assert not list((s['run']/'production/image-selection').rglob('accepted.json'))


def test_external_lock_is_retained_and_loss_blocks_data(selection_setup,monkeypatch):
    from video_ai.runtime.production_state import RunLock
    import video_ai.runtime.production_image_selection as module
    s=selection_setup
    with RunLock(s['run']) as lock:
        result=prepare(s,lock=lock)
        assert result.status=='awaiting_image_selection' and lock.path.exists()
    assert not lock.path.exists()


def test_explicit_retry_requires_exact_attempt_hash_and_new_message_identity(selection_setup):
    from video_ai.runtime.production_image_selection import retry_notification
    s=selection_setup; s['smtp'].fail='unknown'; result=prepare(s)
    intent=next((s['run']/'production/image-selection').rglob('intent.json'))
    s['smtp'].fail=None
    kwargs=dict(expected_attempt_sha256='a'*64,paths=s['paths'],logger=s['logger'],smtp_factory=s['smtp'].factory)
    assert retry_notification(s['frozen'],result.batch_id,1,**kwargs).status=='blocked'
    kwargs['expected_attempt_sha256']=hashlib.sha256(intent.read_bytes()).hexdigest()
    assert retry_notification(s['frozen'],result.batch_id,1,**kwargs).status=='awaiting_image_selection'
    assert len(s['smtp'].messages)==2
    from email.parser import BytesParser
    assert BytesParser().parsebytes(s['smtp'].messages[0])['Message-ID']!=BytesParser().parsebytes(s['smtp'].messages[1])['Message-ID']
    assert intent.exists() and len(list(intent.parents[2].rglob('intent.json')))==2


def test_prepared_cli_consumes_selection_without_models(selection_setup,capsys):
    from video_ai.cli import main
    s=selection_setup; result=prepare(s); path,_=selection(s,result)
    code=main(['make-video','--run-dir',str(s['run']),'--image-selection',str(path),'--json'])
    output=json.loads(capsys.readouterr().out)
    assert code==0 and output['schema_version']==2 and output['status']=='image_batch_accepted'
    assert 'movie' not in output


def test_cli_waiting_resume_has_version_two_result(selection_setup,capsys):
    from video_ai.cli import main
    s=selection_setup; prepare(s)
    assert main(['make-video','--run-dir',str(s['run']),'--json'])==3
    assert json.loads(capsys.readouterr().out)['status']=='awaiting_image_selection'


@pytest.mark.parametrize('field,value',[('schema_version',True),('run_id','foreign')])
def test_active_pointer_identity_is_required_when_consuming(selection_setup,field,value):
    s=selection_setup; result=prepare(s); path,_=selection(s,result)
    active=s['run']/'production/image-selection/active-batch.json'
    pointer=json.loads(active.read_text()); pointer[field]=value
    active.write_text(json.dumps(pointer))
    assert consume(s,path).status=='blocked'
    assert not list((s['run']/'production/image-selection').rglob('accepted.json'))


@pytest.mark.parametrize('point',['batch','intent','data-accepted'])
def test_durable_interruption_preserves_progress_and_prevents_duplicate_data(selection_setup,monkeypatch,point):
    import video_ai.runtime.production_image_selection as module
    s=selection_setup
    def interrupt(where):
        if where==point: raise KeyboardInterrupt()
    monkeypatch.setattr(module,'boundary',interrupt)
    assert prepare(s).status=='interrupted'
    assert not (s['run']/'.make-video.lock').exists()
    count=len(s['smtp'].messages)
    monkeypatch.setattr(module,'boundary',lambda _:None)
    resumed=prepare(s)
    if point=='batch': assert resumed.status=='awaiting_image_selection' and len(s['smtp'].messages)==1
    else: assert resumed.status=='email_delivery_unknown' and len(s['smtp'].messages)==count


def test_lock_loss_at_intent_never_permits_data(selection_setup,monkeypatch):
    import video_ai.runtime.production_image_selection as module
    s=selection_setup
    def lose_lock(where):
        if where=='intent':
            lock=s['run']/'.make-video.lock'; owner=json.loads(lock.read_text()); owner['token']='f'*32
            lock.write_text(json.dumps(owner))
    monkeypatch.setattr(module,'boundary',lose_lock)
    assert prepare(s).status=='blocked'
    assert not s['smtp'].messages


@pytest.mark.parametrize('production_config',[45000],indirect=True)
def test_partial_multipart_delivery_reuses_successful_pages(selection_setup):
    s=selection_setup; s['smtp'].fail='unknown'; s['smtp'].fail_on=2
    result=prepare(s)
    notification=json.loads((Path(result.selection_template).parent/'mail/notification.json').read_text())
    assert len(notification['parts'])>=2
    assert result.status=='email_delivery_unknown' and len(s['smtp'].messages)==2
    s['smtp'].fail=None
    assert prepare(s).status=='email_delivery_unknown' and len(s['smtp'].messages)==2


def test_repeated_accept_keeps_original_submission_and_refuses_changed_choice(selection_setup):
    s=selection_setup; result=prepare(s); path,value=selection(s,result)
    assert consume(s,path).status=='image_batch_accepted'
    target=Path(result.selection_template).parent/'accepted.json'; before=target.read_bytes()
    value['observation']=dict(scope='current_batch',review_method='human_image',reviewer='fixture',
        viewed_images=value['selections'],subject_consistency='unverified',style_consistency='unverified',
        verdict='unverified',issues=[],reason='fixture explicit observation')
    path.write_text(json.dumps(value)+'\n')
    assert consume(s,path).status=='image_batch_accepted' and target.read_bytes()==before
    batch=json.loads(target.with_name('batch.json').read_text()); choice=batch['scenes'][0]['candidates'][1]
    value['selections'][0]['candidate_id']=choice['candidate_id']; value['selections'][0]['sha256']=choice['sha256']; value['observation']=None
    path.write_text(json.dumps(value))
    assert consume(s,path).status=='blocked' and target.read_bytes()==before


def test_smtp_receipt_rejects_boolean_identity(selection_setup):
    from video_ai.runtime.production_image_selection import notification_delivery_state
    s=selection_setup; result=prepare(s)
    folder=Path(result.selection_template).parent
    receipt=next((folder/'mail').rglob('receipt.json')); value=json.loads(receipt.read_text())
    value['part']=True; receipt.write_text(json.dumps(value))
    batch=json.loads((folder/'batch.json').read_text())
    with pytest.raises(ValueError): notification_delivery_state(s['run'],batch)


def test_lock_loss_in_smtp_worker_prevents_data_after_intent(selection_setup,monkeypatch):
    import video_ai.adapters.selection_email as module
    s=selection_setup
    def lose_lock(where):
        if where=='before_data_transition':
            lock=s['run']/'.make-video.lock'; owner=json.loads(lock.read_text()); owner['token']='e'*32
            lock.write_text(json.dumps(owner))
    monkeypatch.setattr(module,'_smtp_boundary',lose_lock)
    assert prepare(s).status=='blocked'
    assert not s['smtp'].messages


def test_prepared_cli_finalization_after_lock_loss_keeps_schema2_without_error_writes(selection_setup,monkeypatch):
    import video_ai.runtime.production_image_selection as module
    from video_ai.production import make_video
    s=selection_setup; prepare(s)
    original=module.resume_image_selection
    def lose_after_result(*args,**kwargs):
        result=original(*args,**kwargs)
        lock=kwargs['lock']; owner=json.loads(lock.path.read_text()); owner['token']='d'*32
        lock.path.write_text(json.dumps(owner)); return result
    monkeypatch.setattr(module,'resume_image_selection',lose_after_result)
    before=set((s['run']/'logs/production').rglob('*'))
    result=make_video(run_dir=s['run'])
    assert result.schema_version==2 and result.status=='blocked'
    assert not set((s['run']/'logs/production/errors').glob('*'))-before
    assert not list((s['run']/'logs/production/invocations').glob('*'))


@pytest.mark.parametrize('failure',['owner','unlink'])
def test_prepared_cli_lock_exit_failure_returns_schema2_instead_of_attribute_error(selection_setup,monkeypatch,failure):
    from video_ai.runtime.production_state import RunLock
    from video_ai.production import make_video
    s=selection_setup; prepare(s)
    original=RunLock.__exit__
    def lose_on_exit(self,*args):
        if failure=='unlink': raise OSError('simulated lock unlink failure')
        owner=json.loads(self.path.read_text()); owner['token']='c'*32; self.path.write_text(json.dumps(owner))
        return original(self,*args)
    monkeypatch.setattr(RunLock,'__exit__',lose_on_exit)
    result=make_video(run_dir=s['run'])
    assert result.schema_version==2 and result.status==('failed' if failure=='unlink' else 'blocked')
