"""Local workflow coordination; no external mail, services or video generation."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from video_ai.mail_workflow import parse_image_reply, run_mail_workflow


def image_request(run):
    folder=run/'production/image-selection/image_batch_0001'
    folder.mkdir(parents=True,exist_ok=True)
    batch=dict(batch_id='image_batch_0001',scenes=[dict(scene_id='scene_0001',candidates=[
        dict(candidate_id='request_01_image_01',sha256='a'*64),
        dict(candidate_id='request_02_image_01',sha256='b'*64)])])
    template=dict(schema_version=2,run_id=run.name,batch_id=batch['batch_id'],intent='draft',selections=[],observation=None)
    for name,value in [('batch.json',batch),('selection-template.json',template),
                       ('mail/notification.json',dict(parts=[dict(message_id='<current@video-ai.local>')]))]:
        path=folder/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value),encoding='utf-8')
    result=dict(status='awaiting_image_selection',run_dir=str(run),batch_id=batch['batch_id'],
                selection_template=str(folder/'selection-template.json'))
    return result,dict(kind='image_selection',templates=[template],batch=batch)


def test_exact_scene_choices_accept_optional_png_and_keep_sha(tmp_path):
    _,request=image_request(tmp_path)
    selected=parse_image_reply(request,'确认=提交\nscene_0001=request_02_image_01.png')
    assert selected['intent']=='accept'
    assert selected['selections']==[dict(scene_id='scene_0001',candidate_id='request_02_image_01',sha256='b'*64)]
    assert request['templates'][0]['intent']=='draft'


@pytest.mark.parametrize('reply',[
    '确认=暂存\nscene_0001=request_02_image_01',
    '确认=提交\nscene_0001=填写候选编号',
    '确认=提交\nscene_0002=request_01_image_01',
    '确认=提交\nscene_0001=request_01_image_01\nscene_0001=request_02_image_01',
    '确认=提交',
])
def test_incomplete_ambiguous_or_explicit_draft_choices_cannot_advance(tmp_path,reply):
    _,request=image_request(tmp_path)
    with pytest.raises(ValueError):parse_image_reply(request,reply)


def test_complete_choices_in_qq_collapsed_plain_text_accept_jpeg_without_extra_confirmation(tmp_path):
    _,request=image_request(tmp_path)
    other=deepcopy(request['batch']['scenes'][0]);other['scene_id']='scene_0002'
    request['batch']['scenes'].append(other)
    text='scene_0001=request_02_image_01.jpeg scene_0002=request_01_image_01.jpg\n\n318575094\n318575094@qq.com'
    value=parse_image_reply(request,text)
    assert value['selections']==[
        dict(scene_id='scene_0001',candidate_id='request_02_image_01',sha256='b'*64),
        dict(scene_id='scene_0002',candidate_id='request_01_image_01',sha256='a'*64),
    ]
    assert value['observation'] is None


def test_complete_reply_remains_explicit_with_optional_confirmation_and_preview_suffix(tmp_path):
    _,request=image_request(tmp_path)
    assert parse_image_reply(request,'scene_0001=request_02_image_01.webp')['intent']=='accept'
    with pytest.raises(ValueError):parse_image_reply(request,'scene_0001=request_02_image_01.exe')


class Inbox:
    def __init__(self,replies=()):self.replies=list(replies);self.polls=[]
    def poll(self,ids):
        self.polls.append(ids)
        result=self.replies;self.replies=[]
        return result


def test_restarting_pending_wait_does_not_call_producer_again(runtime_run):
    run,_,_=runtime_run
    result,_=image_request(run)
    calls=[]
    def producer(**kwargs):calls.append(kwargs);return deepcopy(result)
    inbox=Inbox()
    assert run_mail_workflow(run_dir=run,once=True,producer=producer,reader=inbox)==3
    assert run_mail_workflow(run_dir=run,once=True,producer=producer,reader=inbox)==3
    assert len(calls)==1
    assert inbox.polls==[['<current@video-ai.local>'],['<current@video-ai.local>']]


def test_reply_is_submitted_then_production_advances_without_another_command(runtime_run):
    run,_,_=runtime_run
    result,_=image_request(run)
    calls=[]
    def producer(**kwargs):
        calls.append(kwargs)
        if kwargs.get('image_selection'):
            value=json.loads(kwargs['image_selection'].read_text(encoding='utf-8'))
            assert value['selections'][0]['candidate_id']=='request_02_image_01'
            return dict(result,status='image_batch_accepted')
        if len(calls)>1:return dict(status='delivered',run_dir=str(run))
        return deepcopy(result)
    reply=SimpleNamespace(key='91:2',message_id='<reply@qq.com>',sender='318575094@qq.com',
                          text='确认=提交\nscene_0001=request_02_image_01.png')
    assert run_mail_workflow(run_dir=run,once=True,producer=producer,reader=Inbox([reply]),
                             review_builder=lambda value:None)==0
    assert len(calls)==3
    assert not (run/'production/mail-workflow/pending.json').exists()


def test_failed_selection_consumer_does_not_resume_paid_work(runtime_run):
    run,_,_=runtime_run
    result,_=image_request(run)
    calls=[]
    def producer(**kwargs):
        calls.append(kwargs)
        return dict(result,status='blocked',error=dict(message='selection refused')) if kwargs.get('image_selection') else result
    reply=SimpleNamespace(key='91:2',message_id='<reply@qq.com>',sender='318575094@qq.com',
                          text='确认=提交\nscene_0001=request_02_image_01')
    assert run_mail_workflow(run_dir=run,once=True,producer=producer,reader=Inbox([reply]))==2
    assert len(calls)==2


class Outbox:
    def __init__(self,unknown=False):self.messages=[];self.unknown=unknown
    def __call__(self,settings):return self
    def send(self,raw,*,before_data):
        from video_ai.adapters.selection_email import EmailDeliveryUnknown
        before_data();self.messages.append(raw)
        if self.unknown:raise EmailDeliveryUnknown()
        return dict(smtp_code=250)


def publish_result(run):
    return dict(status='final_review_ready',run_dir=str(run),final_observation_template=dict(
        scope='scene_final_film',candidate=dict(path=str(run/'candidate.mp4'),bytes=1,sha256='a'*64),
        scene_observations=[],join_observations=[],narration_observations=[]))


def test_confirmation_email_is_sent_once_across_wait_restarts(runtime_run):
    run,_,_=runtime_run;calls=[];outbox=Outbox()
    def producer(**kwargs):
        calls.append(kwargs);return publish_result(run)
    for _ in range(2):
        assert run_mail_workflow(run_dir=run,once=True,producer=producer,reader=Inbox(),sender_factory=outbox)==3
    assert len(calls)==1 and len(outbox.messages)==1
    from email import policy
    from email.parser import BytesParser
    assert '"reviews": []' in BytesParser(policy=policy.default).parsebytes(outbox.messages[0]).get_body().get_content()


def test_publish_requires_explicit_reply_and_does_not_repeat_production_after_delivery(runtime_run):
    run,_,_=runtime_run;calls=[]
    def producer(**kwargs):
        calls.append(kwargs)
        return dict(status='delivered',run_dir=str(run)) if kwargs.get('publish') else publish_result(run)
    reply=SimpleNamespace(key='91:8',message_id='<published@qq.com>',sender='318575094@qq.com',
        text=json.dumps({'确认':'提交','完整查看':True,'发布':True,'reviews':[]}))
    assert run_mail_workflow(run_dir=run,once=True,producer=producer,reader=Inbox([reply]),sender_factory=Outbox())==0
    assert len(calls)==2 and calls[-1]['publish'] is True


def test_uncertain_smtp_attempt_is_not_resent_on_restart(runtime_run):
    run,_,_=runtime_run;outbox=Outbox(unknown=True)
    def producer(**kwargs):return publish_result(run)
    for _ in range(2):
        assert run_mail_workflow(run_dir=run,once=True,producer=producer,reader=Inbox(),sender_factory=outbox)==2
    assert len(outbox.messages)==1


def test_temporary_mail_connection_failure_retries_without_replaying_producer(runtime_run):
    from video_ai.mail_replies import MailboxError
    run,_,_=runtime_run;result,_=image_request(run);calls=[];waits=[]
    reply=SimpleNamespace(key='1:2',message_id='<reply@qq.com>',sender='318575094@qq.com',
                          text='确认=提交\nscene_0001=request_01_image_01')
    class FlakyInbox:
        def __init__(self):self.attempt=0
        def poll(self,ids):
            self.attempt+=1
            if self.attempt==1:raise MailboxError('connection_failed')
            return [reply]
    def producer(**kwargs):
        calls.append(kwargs)
        return dict(result,status='image_batch_accepted') if kwargs.get('image_selection') else result if len(calls)==1 else dict(status='delivered',run_dir=str(run))
    assert run_mail_workflow(run_dir=run,producer=producer,reader=FlakyInbox(),sleep=waits.append,
                             review_builder=lambda value:None)==0
    assert len(calls)==3 and waits==[30]


def test_imap_authentication_failure_explains_account_setup(runtime_run,capsys):
    from video_ai.mail_replies import MailboxError
    run,_,_=runtime_run;result,_=image_request(run)
    class NoLogin:
        def poll(self,ids):raise MailboxError('authentication_failed')
    assert run_mail_workflow(run_dir=run,once=True,producer=lambda **kw:result,reader=NoLogin())==2
    assert 'IMAP' in capsys.readouterr().out


def clip_wait_result(run):
    from video_ai.runtime.scene_clip_observations import AUTHORED_FIELDS
    template=dict(scope='scene_clip_process',scene_id='scene_0001',clip_id='clip_0001',
        checks=dict(motion_process='unverified'),verdict='unverified',issues=[],
        playback=dict(clip_source_frames=[0,12],parent_source_frames=None),
        **dict.fromkeys(AUTHORED_FIELDS,''))
    authored=dict(template,checks=dict(motion_process='passed'),verdict='passed',
                  **dict.fromkeys(AUTHORED_FIELDS,'人工已完整观看并检查该项。'))
    for key in ('scope','scene_id','clip_id','playback'):authored.pop(key)
    reply=SimpleNamespace(key='91:20',message_id='<clip-reply@qq.com>',sender='318575094@qq.com',
        text=json.dumps({'确认':'提交','完整查看':True,'reviews':[authored]}))
    return dict(status='awaiting_continuity_review',run_dir=str(run),observation_templates=[template]),reply


def test_interrupted_review_submission_reuses_durable_viewing_timestamp(runtime_run,monkeypatch):
    from video_ai import mail_workflow
    run,_,_=runtime_run;result,reply=clip_wait_result(run);stamps=[];clock=['2026-11-29T10:00:00+00:00']
    monkeypatch.setattr(mail_workflow,'now',lambda:clock[0])
    def producer(**kwargs):
        if kwargs.get('clip_observation'):
            stamps.append(json.loads(kwargs['clip_observation'].read_text(encoding='utf-8'))['viewed_at'])
            if len(stamps)==1:raise OSError('simulated loss after staging')
            return dict(status='source_clips_ready',run_dir=str(run))
        return result if not stamps else dict(status='delivered',run_dir=str(run))
    assert run_mail_workflow(run_dir=run,once=True,producer=producer,reader=Inbox([reply]),sender_factory=Outbox())==2
    clock[0]='2026-11-29T11:00:00+00:00'
    assert run_mail_workflow(run_dir=run,once=True,producer=producer,reader=Inbox([reply]),sender_factory=Outbox())==0
    assert stamps==['2026-11-29T10:00:00+00:00']*2


def test_wait_lock_does_not_hold_global_storage_lease(runtime_run,monkeypatch):
    from video_ai import mail_workflow
    from video_ai.runtime import storage
    run,_,_=runtime_run
    def lease_forbidden(*args):raise AssertionError('email wait must not acquire global lifecycle lease')
    monkeypatch.setattr(storage,'managed_lease',lease_forbidden)
    with mail_workflow._workflow_lock(run):
        with pytest.raises(ValueError):
            with mail_workflow._workflow_lock(run):pass
    with mail_workflow._workflow_lock(run):pass


def test_unverified_review_keeps_same_thread_open_for_later_confirmed_reply(runtime_run):
    run,_,_=runtime_run;result,passed=clip_wait_result(run);outbox=Outbox();accepted=[]
    data=json.loads(passed.text)
    data['reviews'][0].update(checks=dict(motion_process='unverified'),verdict='unverified')
    uncertain=SimpleNamespace(key='91:19',message_id='<unverified@qq.com>',sender=passed.sender,text=json.dumps(data))
    def producer(**kwargs):
        if kwargs.get('clip_observation'):
            accepted.append(json.loads(kwargs['clip_observation'].read_text(encoding='utf-8'))['verdict'])
            return dict(status='source_clips_ready',run_dir=str(run)) if accepted[-1]=='passed' else result
        return dict(status='delivered',run_dir=str(run)) if accepted and accepted[-1]=='passed' else result
    assert run_mail_workflow(run_dir=run,once=True,producer=producer,reader=Inbox([uncertain,passed]),sender_factory=outbox)==0
    assert accepted==['unverified','passed'] and len(outbox.messages)==1


def test_interrupted_request_initialization_recovers_missing_result_record(runtime_run,monkeypatch):
    from video_ai import mail_workflow
    run,_,_=runtime_run;result,_=image_request(run);original=mail_workflow._write;failed=[]
    def fail_once(path,value,**kwargs):
        if path.name=='result.json' and not failed:
            failed.append(True);raise OSError('simulated initialization interruption')
        return original(path,value,**kwargs)
    monkeypatch.setattr(mail_workflow,'_write',fail_once)
    assert run_mail_workflow(run_dir=run,once=True,producer=lambda **kw:result,reader=Inbox())==2
    assert run_mail_workflow(run_dir=run,once=True,producer=lambda **kw:result,reader=Inbox())==3
    assert len(list((run/'production/mail-workflow/requests').glob('*/result.json')))==1


def test_partial_byte_write_never_exposes_a_truncated_final_record(tmp_path,monkeypatch):
    from pathlib import Path
    from video_ai import mail_workflow
    original=Path.open;failures=[]
    class InterruptedWrite:
        def __init__(self,file):self.file=file
        def __enter__(self):return self
        def __exit__(self,*args):self.file.close()
        def write(self,raw):
            self.file.write(raw[:2]);self.file.flush();raise OSError('simulated partial write')
    def open_file(path,*args,**kwargs):
        file=original(path,*args,**kwargs)
        if path.suffix=='.tmp' and args==('xb',) and not failures:
            failures.append(True);return InterruptedWrite(file)
        return file
    monkeypatch.setattr(Path,'open',open_file)
    target=tmp_path/'submission.json'
    with pytest.raises(OSError):mail_workflow._write_bytes(target,b'{"confirmed":true}')
    assert not target.exists()
    mail_workflow._write_bytes(target,b'{"confirmed":true}')
    assert target.read_bytes()==b'{"confirmed":true}'


def test_obsolete_image_wait_is_invalidated_so_restart_can_refresh_current_batch(runtime_run):
    run,_,_=runtime_run;result,_=image_request(run);calls=[]
    def producer(**kwargs):calls.append(kwargs);return result
    assert run_mail_workflow(run_dir=run,once=True,producer=producer,reader=Inbox())==3
    (run/'production/image-selection/active-batch.json').write_text('{"batch_id":"image_batch_0002"}',encoding='utf-8')
    reply=SimpleNamespace(key='91:5',message_id='<old-reply@qq.com>',sender='318575094@qq.com',
                          text='确认=提交\nscene_0001=request_01_image_01')
    assert run_mail_workflow(run_dir=run,once=True,producer=producer,reader=Inbox([reply]))==2
    assert not (run/'production/mail-workflow/pending.json').exists()
    assert len(calls)==1


def reference_config(run,tmp_path,monkeypatch):
    from video_ai import mail_workflow
    local=tmp_path/'reference.local.json'
    local.write_text(json.dumps(dict(reference_generation=None,reference_capabilities={'model':'capability.json'},
                                     reference_storage={'bucket':'existing'})),encoding='utf-8')
    monkeypatch.setattr(mail_workflow,'DEFAULT_REFERENCE_SETTINGS',local,raising=False)
    options=run/'production/options.json';options.parent.mkdir(parents=True,exist_ok=True)
    options.write_text(json.dumps(dict(config_snapshot=dict(raw=dict(reference_generation=None,
        reference_capabilities={},reference_storage=None)))),encoding='utf-8')
    return local,options


def test_mail_entry_uses_existing_reference_supplement_without_editing_frozen_inputs(runtime_run,tmp_path,monkeypatch):
    run,_,_=runtime_run;result,_=image_request(run);calls=[]
    local,options=reference_config(run,tmp_path,monkeypatch);original=options.read_bytes()
    def producer(**kwargs):calls.append(kwargs);return result
    assert run_mail_workflow(run_dir=run,once=True,producer=producer,reader=Inbox())==3
    assert calls[0].get('reference_settings')==local
    assert options.read_bytes()==original


def test_reference_supplement_is_forwarded_only_for_generation_not_reply_consumption(runtime_run,tmp_path,monkeypatch):
    run,_,_=runtime_run;result,_=image_request(run);calls=[]
    local,_=reference_config(run,tmp_path,monkeypatch)
    def producer(**kwargs):
        calls.append(kwargs)
        return dict(result,status='image_batch_accepted') if kwargs.get('image_selection') else result if len(calls)==1 else dict(status='delivered',run_dir=str(run))
    reply=SimpleNamespace(key='1:7',message_id='<selection@qq.com>',sender='318575094@qq.com',text='确认=提交\nscene_0001=request_01_image_01')
    assert run_mail_workflow(run_dir=run,once=True,producer=producer,reader=Inbox([reply]),review_builder=lambda value:None)==0
    assert calls[0].get('reference_settings')==calls[2].get('reference_settings')==local
    assert 'reference_settings' not in calls[1]


@pytest.mark.parametrize('case',['already_bound','frozen_conflict'])
def test_reference_defaults_do_not_replace_preexisting_task_configuration(runtime_run,tmp_path,monkeypatch,case):
    run,_,_=runtime_run;result,_=image_request(run);calls=[]
    _,options=reference_config(run,tmp_path,monkeypatch)
    if case=='already_bound':
        marker=run/'production/reference-images/settings.json';marker.parent.mkdir(parents=True);marker.write_text('{}',encoding='utf-8')
    else:
        data=json.loads(options.read_text(encoding='utf-8'));data['config_snapshot']['raw']['reference_storage']={'bucket':'task-specific'}
        options.write_text(json.dumps(data),encoding='utf-8')
    def producer(**kwargs):calls.append(kwargs);return result
    assert run_mail_workflow(run_dir=run,once=True,producer=producer,reader=Inbox())==3
    assert 'reference_settings' not in calls[0]


def test_mail_settings_read_actual_frozen_raw_snapshot(runtime_run):
    from video_ai.mail_workflow import _settings
    run,_,_=runtime_run
    p=run/'production/options.json';p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(dict(config_snapshot=dict(raw=dict(selection_email=dict(smtp_password_env='TASK_SMTP'))))),encoding='utf-8')
    assert _settings(run).smtp_password_env=='TASK_SMTP'
