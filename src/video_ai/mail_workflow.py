"""Durable email waits around the existing, independently locked producer."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from email import policy
from email.message import EmailMessage
import hashlib
import json
import os
from pathlib import Path
import re
import time
from uuid import uuid4

from .adapters.selection_email import SmtpSender
from .config import read_json
from .mail_replies import ImapReplyReader,MailboxError
from .mail_workflow_context import mail_reply_context
from .selection_config import parse_selection_email
from .runtime.manifest import now

DEFAULT_REFERENCE_SETTINGS=Path(__file__).resolve().parents[2]/'config/reference.local.json'


def _bytes(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def _digest(value):return hashlib.sha256(_bytes(value)).hexdigest()


def _write_bytes(path,raw,*,replace=False):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and not replace:
        if path.read_bytes()!=raw:raise ValueError('email workflow immutable record differs')
        return
    temporary=path.with_name('.'+uuid4().hex[:12]+'.tmp')
    with temporary.open('xb') as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
    if replace:os.replace(temporary,path)
    else:temporary.rename(path)


def _write(path,value,*,replace=False):
    _write_bytes(path,_bytes(value),replace=replace)


def _invalidate(root,folder,reason):
    _write(folder/'invalidated.json',dict(reason=reason,at=now()),replace=True)
    (root/'pending.json').unlink(missing_ok=True)


def _plain_result(value):return value if isinstance(value,dict) else value.to_dict()


def _settings(run):
    options=run/'production/options.json'
    if options.exists():
        data=read_json(options)
        snapshot=data.get('config_snapshot',{})
        if isinstance(snapshot.get('raw'),dict):
            return parse_selection_email(snapshot['raw'].get('selection_email'))
        if snapshot.get('path'):
            return parse_selection_email(read_json(snapshot['path']).get('selection_email'))
    return parse_selection_email(None)


def _reference_supplement(config,run,explicit):
    """Use the existing local supplement only to fill missing stage settings."""
    if explicit is not None:return Path(explicit).absolute()
    if run is not None:
        if (run/'production/reference-images/settings.json').exists():return None
        options=run/'production/options.json'
        if not options.exists():return None
        raw=read_json(options).get('config_snapshot',{}).get('raw',{})
    elif hasattr(config,'raw'):
        raw=config.raw
    else:
        from .runtime.production_inputs import DEFAULT_CONFIG
        raw=read_json(config or DEFAULT_CONFIG)
    local=DEFAULT_REFERENCE_SETTINGS
    if not local.is_file():return None
    supplement=read_json(local)
    fields=('reference_generation','reference_capabilities','reference_storage')
    if set(supplement)!=set(fields):raise ValueError('config/reference.local.json must contain the three reference configuration fields')
    if raw.get('reference_capabilities') and raw.get('reference_storage'):
        return None  # The task already supplies its own reference configuration.
    for key in fields:
        frozen=raw.get(key)
        missing=frozen is None or key=='reference_capabilities' and frozen=={}
        if not missing and frozen!=supplement[key]:return None
    return local


@contextmanager
def _workflow_lock(run):
    # OS ownership is released on process exit. Unlike RunLock this does not
    # acquire the runtime-wide storage lease during a potentially long wait.
    handle=(run/'.mail-video.lock').open('a+b');locked=False
    try:
        if handle.seek(0,os.SEEK_END)==0:handle.write(b'\0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            locked=True
        except OSError:
            raise ValueError('该视频已有邮件等待程序正在运行，请使用原窗口') from None
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        handle.close()


def parse_image_reply(request,text):
    confirmations=re.findall(r'(?:^|\s)确认\s*[=＝]\s*(\S+)',text)
    if any(value!='提交' for value in confirmations) or re.search(r'(?m)^\s*(?:不要提交|暂不提交|先不提交|仅暂存|取消提交)[。！!\s]*$',text):
        raise ValueError('该回复未提交选择；请在准备好后回复完整选择')
    # QQ can flatten edited HTML lines into one plain-text line. Exact,
    # complete scene choices remain explicit selection instructions; preview
    # filename extensions are presentation details, not candidate identities.
    pattern=r'(?<![A-Za-z0-9_])(scene_[0-9]+)\s*[=＝]\s*([A-Za-z0-9_]+)(?:\.(?:png|jpe?g|webp))?(?![A-Za-z0-9_.])'
    matches=list(re.finditer(pattern,text,re.I))
    assignments=re.findall(r'(?<![A-Za-z0-9_])scene_[0-9]+\s*[=＝]',text,re.I)
    if not matches or len(matches)!=len(assignments):raise ValueError('场景选择格式应为 scene_0001=request_02_image_01，可带图片后缀')
    found={}
    for match in matches:
        sid,cid=match.groups()
        sid=sid.lower()
        if sid in found:raise ValueError('同一场景只能选择一次')
        found[sid]=cid
    scenes=request['batch']['scenes']
    if set(found)!={s['scene_id'] for s in scenes}:raise ValueError('请为当前批次的每个场景恰好选择一张图片')
    value=deepcopy(request['templates'][0]);value['intent']='accept';value['selections']=[]
    for scene in scenes:
        candidate=next((c for c in scene['candidates'] if c['candidate_id']==found[scene['scene_id']]),None)
        if candidate is None:raise ValueError('候选编号不属于当前批次，请使用邮件列出的编号')
        value['selections'].append(dict(scene_id=scene['scene_id'],candidate_id=candidate['candidate_id'],sha256=candidate['sha256']))
    return value


def _image_request(result):
    run=Path(result['run_dir'])
    template=Path(result.get('selection_template') or result.get('selection_result',{}).get('selection_template',''))
    if not template.is_file() or not template.is_relative_to(run):raise ValueError('current image selection template unavailable')
    batch=read_json(template.parent/'batch.json')
    notification=read_json(template.parent/'mail/notification.json')
    return dict(kind='image_selection',binding=_digest(batch),subject='候选图选择',
        body_template='确认=提交\n'+'\n'.join(s['scene_id']+'=填写候选编号' for s in batch['scenes']),
        templates=[read_json(template)],batch=batch,action='image_selection',attachments=[],
        message_ids=[part['message_id'] for part in notification['parts']])


def _message(request,settings,message_id,*,error=None):
    message=EmailMessage(policy=policy.SMTP)
    message['From']=settings.sender;message['To']=settings.recipient
    message['Date']=datetime.now().astimezone()
    message['Message-ID']=message_id
    message['X-Video-AI-Request-ID']=message_id
    message['Subject']=request['subject']+' [VideoAI '+request['binding'][:16]+']'
    intro='请直接回复本邮件，将下面模板填写完整；程序收到有效回复后自动继续。\n'
    if error:intro='上次回复尚未录入：'+error+'\n'+intro
    files=[Path(p) for p in request.get('attachments',[]) if Path(p).is_file()]
    intro+='需要查看的文件：\n'+'\n'.join(str(p) for p in files)+'\n\n' if files else ''
    message.set_content('Request-ID: '+message_id+'\n'+intro+request['body_template']+'\n')
    # Keep the exact files; large videos are opened from their local path.
    # The mail explicitly lists them even when the SMTP limit precludes an attachment.
    for path in files:
        if path.stat().st_size*4//3+len(message.as_bytes())>settings.max_mime_bytes-4096:continue
        kind,subtype=('video','mp4') if path.suffix.lower()=='.mp4' else ('image','jpeg') if path.suffix.lower() in ('.jpg','.jpeg') else ('image','png') if path.suffix.lower()=='.png' else ('application','octet-stream')
        message.add_attachment(path.read_bytes(),maintype=kind,subtype=subtype,filename=path.name)
    raw=message.as_bytes()
    if len(raw)>settings.max_mime_bytes:raise ValueError('confirmation email exceeds SMTP size limit')
    return raw


def _send(folder,request,settings,sender_factory,*,error=None):
    folder.mkdir(parents=True,exist_ok=True)
    receipt=folder/'receipt.json'
    if receipt.exists():return read_json(receipt)['message_id']
    # An interrupted DATA is intentionally not resent on restart.
    if (folder/'intent.json').exists():raise ValueError('email delivery outcome unknown; inspect the pending SMTP attempt before retrying')
    path=folder/'message.eml'
    if path.exists():
        from email.parser import BytesParser
        raw=path.read_bytes();message_id=BytesParser(policy=policy.default).parsebytes(raw)['Message-ID']
    else:
        message_id='<'+request['binding']+'.'+uuid4().hex+'@video-ai.local>'
        raw=_message(request,settings,message_id,error=error)
        _write_bytes(path,raw)
    sender=sender_factory(settings)
    result=sender.send(raw,before_data=lambda:_write(folder/'intent.json',dict(message_id=message_id,created_at=now())))
    _write(receipt,dict(message_id=message_id,smtp_code=result['smtp_code'],accepted_at=now()))
    return message_id


def _existing_run(video,run_dir):
    if run_dir is not None:return Path(run_dir).absolute()
    if video is not None:
        from .runtime.storage import VideoStorage
        storage=VideoStorage();return storage.current_run(storage.find(video))
    return None


def _current_revision(run):
    from .runtime.storage import VideoStorage,managed_location
    location=managed_location(run)
    if location is not None:
        storage=VideoStorage(location[0])
        if storage.current_run(storage.find(location[1].name))!=run:
            raise ValueError('视频已有新的修订；旧邮件不会用于新修订，请使用视频编号重新启动')


def _exit(result):
    status=result.get('status')
    if status=='delivered':return 0
    if status=='interrupted':return 130
    if status in ('failed','final_review_failed'):return 1
    return 2


def run_mail_workflow(config=None,*,video=None,title=None,script=None,text=None,run_dir=None,
                      wan_mode='fast',once=False,producer=None,reader=None,sender_factory=None,
                      sleep=None,review_builder=None,output=None,cpu_planner=None,image_model=None,
                      reference_settings=None):
    """Run until delivery, a genuine error, or Ctrl+C; --once permits one poll."""
    from .managed_production import make_managed_video
    from .mail_review_requests import build_review_request,parse_review_reply,encode_submission
    producer=producer or make_managed_video
    sender_factory=sender_factory or SmtpSender;sleep=sleep or time.sleep
    review_builder=review_builder or build_review_request
    initial=dict(config=config,video=video,title=title,script=script,text=text,run_dir=run_dir,
                 wan_mode=wan_mode,output_path=output,cpu_planner=cpu_planner,image_model=image_model)
    initial={k:v for k,v in initial.items() if v is not None}
    result=None;run=None;announced=None;mail_error=None
    try:
        run=_existing_run(video,run_dir)
        # Resume a durable mail wait directly; do not rerun historical admission
        # and producer work merely because another poll or restart occurred.
        if run is None or not (run/'production/mail-workflow/pending.json').exists():
            supplement=_reference_supplement(config,run,reference_settings)
            if supplement is not None:initial['reference_settings']=supplement
            with mail_reply_context():result=_plain_result(producer(**initial))
            if not result.get('run_dir'):
                print(result.get('error') or result.get('status'));return _exit(result)
            run=Path(result['run_dir'])
        root=run/'production/mail-workflow';root.mkdir(parents=True,exist_ok=True)
        with _workflow_lock(run):
            # Every pending reply belongs to this exact revision, including
            # publish=True, which otherwise has no observation identity payload.
            resume=dict(run_dir=run,wan_mode=wan_mode)
            def advance(**actions):
                _current_revision(run)
                args=dict(resume,**actions)
                if not actions:
                    supplement=_reference_supplement(config,run,reference_settings)
                    if supplement is not None:args['reference_settings']=supplement
                with mail_reply_context():return _plain_result(producer(**args))
            settings=_settings(run)
            reader=reader or ImapReplyReader(credential_name=settings.smtp_password_env)
            while True:
                pointer=root/'pending.json'
                pending=read_json(pointer) if pointer.exists() else None
                if pending is not None:
                    folder=root/'requests'/pending['request_id']
                    request=read_json(folder/'request.json')
                    result=read_json(folder/'result.json')
                    if (folder/'completed.json').exists():
                        pointer.unlink();pending=None
                        result=advance()
                if pending is None:
                    if result is None:
                        result=advance()
                    print('Video '+str(result.get('video_number') or video or run.name)+': '+result['status'],flush=True)
                    if result['status']=='delivered':
                        _write(root/'delivered.json',result,replace=True);return 0
                    request=_image_request(result) if result['status']=='awaiting_image_selection' else review_builder(result)
                    if request is None:
                        if result['status'] in ('image_batch_accepted','source_clips_ready','images_ready','upscale_ready'):
                            result=advance()
                            continue
                        if result.get('error'):print(result['error'].get('message','Production stopped'),flush=True)
                        return _exit(result)
                    request_id=request['kind']+'-'+str(request['binding'])[:24]
                    folder=root/'requests'/request_id
                    if not (folder/'request.json').exists():_write(folder/'request.json',request)
                    else:request=read_json(folder/'request.json')
                    if not (folder/'result.json').exists():_write(folder/'result.json',result)
                    if request['kind']!='image_selection':
                        message_id=_send(folder/'mail',request,settings,sender_factory)
                        request=dict(request,message_ids=[message_id])
                    _write(folder/'thread.json',dict(message_ids=request['message_ids']))
                    _write(pointer,dict(request_id=request_id),replace=True)
                ids=read_json(folder/'thread.json')['message_ids']
                for receipt in sorted((folder/'corrections').glob('*/receipt.json')):
                    mid=read_json(receipt)['message_id']
                    if mid not in ids:ids.append(mid)
                if announced!=str(folder):
                    print('正在等待邮件回复；请保持本程序运行，Ctrl+C 可暂停。',flush=True)
                    announced=str(folder)
                try:
                    replies=reader.poll(ids)
                    if mail_error:print('邮件收信连接已恢复。',flush=True)
                    mail_error=None
                except MailboxError as exc:
                    if str(exc) in ('authentication_failed','credentials_unavailable','mailbox_unavailable','invalid_settings','invalid_request'):
                        print('IMAP 收信未就绪：请在 QQ 邮箱启用 IMAP/SMTP 服务，并确认本地 SMTP 授权码有效。进度已保存，重新运行同一视频即可恢复。',flush=True)
                        return 2
                    if mail_error!=str(exc):print('邮件收信连接暂时不可用，稍后自动重试。',flush=True)
                    mail_error=str(exc)
                    if once:return 3
                    sleep(min(getattr(getattr(reader,'settings',None),'poll_seconds',30),60))
                    continue
                advanced=False
                for reply in replies:
                    key=hashlib.sha256(reply.key.encode('utf-8')).hexdigest()[:24]
                    reply_folder=folder/'replies'/key
                    if (reply_folder/'seen.json').exists():continue
                    evidence=dict(key=reply.key,message_id=reply.message_id,sender=reply.sender,text=reply.text)
                    if (reply_folder/'reply.json').exists():
                        stored=read_json(reply_folder/'reply.json')
                        if any(stored.get(k)!=v for k,v in evidence.items()):raise ValueError('stored reply identity differs')
                    else:
                        stored=dict(evidence,received_at=now());_write(reply_folder/'reply.json',stored)
                    active_request=request
                    if request.get('submission_paths'):
                        active_request=dict(request,submission_paths=[str(Path(p).parent/key/Path(p).name)
                                                                      for p in request['submission_paths']])
                    try:
                        values=[parse_image_reply(request,reply.text)] if request['kind']=='image_selection' else parse_review_reply(active_request,reply.text,reviewer=reply.sender,viewed_at=stored['received_at'])
                    except ValueError:
                        # Never echo arbitrary mailbox contents into outbound mail.
                        hint=('请为当前批次每个场景恰选一张，使用邮件中的完整候选编号。'
                              if request['kind']=='image_selection' else '请填写完整模板，保留确认行，并只使用当前邮件中的编号和字段。')
                        _send(folder/'corrections'/key,request,settings,sender_factory,error=hint)
                        _write(reply_folder/'seen.json',dict(status='rejected',at=now()))
                        continue
                    paths=active_request.get('submission_paths')
                    if paths is not None and len(paths)!=len(values):raise ValueError('review submission path count differs')
                    submitted=[]
                    for index,value in enumerate(values):
                        path=Path(paths[index]) if paths else reply_folder/f'submission_{index+1:04d}.json'
                        if not path.absolute().is_relative_to(run):raise ValueError('review submission path escapes current run')
                        path.parent.mkdir(parents=True,exist_ok=True)
                        raw=encode_submission(value)
                        if path.exists():
                            if path.read_bytes()!=raw:raise ValueError('reply submission bytes differ')
                        else:_write_bytes(path,raw)
                        submitted.append(path)
                    action=request['action']
                    # Recheck only the small request source records once a
                    # response arrives, never rehash media while merely polling.
                    fresh=_image_request(result) if request['kind']=='image_selection' else review_builder(result)
                    active=run/'production/image-selection/active-batch.json'
                    batch_changed=(request['kind']=='image_selection' and active.is_file()
                                   and read_json(active).get('batch_id')!=request['batch']['batch_id'])
                    if batch_changed or fresh is None or fresh['binding']!=request['binding']:
                        _invalidate(root,folder,'current confirmation source changed')
                        raise ValueError('当前确认对象已经改变；旧邮件回复已保留，请重新启动当前视频获取新模板')
                    indexes=range(len(values)) if action=='clip_observation' else [len(values)-1]
                    for index in indexes:
                        applied=reply_folder/f'applied_{index+1:04d}.json'
                        if applied.exists():result=read_json(applied);continue
                        result=advance(**{action:True if action=='publish' else submitted[index]})
                        if result['status'] in ('blocked','failed','interrupted','final_review_failed'):
                            _invalidate(root,folder,'production consumer stopped; refresh current state on restart')
                            print((result.get('error') or {}).get('message',result['status']),flush=True)
                            return _exit(result)
                        _write(applied,result)
                    # A successful action only consumes evidence. The subsequent
                    # ordinary resume performs generation through its usual path.
                    if result['status'] not in ('image_batch_accepted','delivered'):
                        result=advance()
                    followup=_image_request(result) if result['status']=='awaiting_image_selection' else review_builder(result)
                    if followup is not None and followup['binding']==request['binding']:
                        # An explicit unverified judgment is recorded, but this
                        # same gate remains open for a further human reply.
                        _write(reply_folder/'seen.json',dict(status='accepted',at=now()))
                        continue
                    _write(folder/'completed.json',dict(reply_key=key,at=now()))
                    _write(reply_folder/'seen.json',dict(status='accepted',at=now()))
                    pointer.unlink();advanced=True
                    break
                if advanced:continue
                if once:return 3
                interval=getattr(getattr(reader,'settings',None),'poll_seconds',30)
                sleep(min(interval,60))
    except KeyboardInterrupt:
        print('已暂停；使用同一视频编号重新启动即可恢复邮件等待。',flush=True);return 130
    except (ValueError,OSError) as exc:
        print(str(exc),flush=True);return 2
