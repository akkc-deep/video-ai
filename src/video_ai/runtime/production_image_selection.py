"""Prepared image batches: durable notifications, explicit choices and safe waits."""
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from ..adapters.selection_email import (build_messages, SmtpSender, EmailPreconditionError,
                                         EmailRejected, EmailDeliveryUnknown)
from ..config import read_json
from ..jimeng_config import STRATEGY
from ..media.selection_sheet import prepare_email_media
from ..planning.production_scenes import canonical_digest
from ..planning.production_timeline import ProductionTimeline
from ..selection_config import parse_selection_email
from . import image_selection_records as records
from .manifest import hash_file, now, thaw, validate_run_dir
from .production_inputs import load_frozen_inputs, _same_json
from .execution_limits import production_execution
from .production_state import ProductionRefused, RunLock, object_fields, run_path, timestamp


def boundary(point):
    """Fault-injection boundary after a durable transaction step."""


@dataclass(frozen=True)
class ImageSelectionResult:
    schema_version: int = 2
    production_strategy: str = STRATEGY
    run_id: str | None = None
    run_dir: Path | None = None
    status: str = 'blocked'
    active_stage: str = 'start_images'
    batch_id: str | None = None
    selection_template: Path | None = None
    all_images_accepted: bool = False
    log_dir: Path | None = None
    error: dict | None = None

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 2 or self.production_strategy != STRATEGY:
            raise ValueError('invalid image selection result schema')
        if self.status not in ('awaiting_image_selection','email_delivery_unknown','image_batch_accepted','blocked','failed','interrupted'):
            raise ValueError('invalid image selection result status')
        if self.active_stage != 'start_images' or type(self.all_images_accepted) is not bool:
            raise ValueError('invalid image selection result stage/acceptance')
        if self.run_dir is not None:
            run=validate_run_dir(Path(self.run_dir)); object.__setattr__(self,'run_dir',run)
            if self.run_id != run.name: raise ValueError('image result run identity differs')
            for key in ('selection_template','log_dir'):
                value=getattr(self,key)
                if value is not None: object.__setattr__(self,key,run_path(run,value))
        elif any(v is not None for v in (self.run_id,self.selection_template,self.log_dir)):
            raise ValueError('image result requires run identity')
        if self.status in ('awaiting_image_selection','email_delivery_unknown','image_batch_accepted'):
            if not self.batch_id or self.selection_template is None or not self.selection_template.is_file():
                raise ValueError('waiting/accepted result requires a prepared batch')
        if self.all_images_accepted and self.status != 'image_batch_accepted':
            raise ValueError('complete acceptance requires accepted status')
        if self.error is not None: object_fields(self.error,('kind','message','evidence_paths'),'image result error')
        json.dumps(self.to_dict(),allow_nan=False)

    def to_dict(self): return thaw(self)

    @property
    def exit_code(self):
        return dict(awaiting_image_selection=3,email_delivery_unknown=3,image_batch_accepted=0,
                    blocked=2,failed=1,interrupted=130)[self.status]


class _Records:
    def __init__(self,run,lock): self.run,self.lock=run,lock;self.revision_guard=None
    def owned(self):
        if (not isinstance(self.lock,RunLock) or self.lock.run_dir != self.run
                or not self.lock.path.is_file() or read_json(self.lock.path) != self.lock.owner):
            raise ProductionRefused('image selection lost held run lock')
        if self.revision_guard is not None:self.revision_guard.verify_captured_bytes()
    def bytes(self,path,raw,*,replace=False):
        self.owned(); path=run_path(self.run,path)
        if path.exists() and not replace:
            if path.read_bytes()!=raw: raise ProductionRefused('immutable image selection record differs: '+path.name)
            return path
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=run_path(self.run,path.with_name(path.name+'.'+uuid4().hex+'.tmp'))
        with temp.open('xb') as file:
            file.write(raw); file.flush(); os.fsync(file.fileno())
        self.owned()
        if replace: os.replace(temp,path)
        else: os.rename(temp,path)
        return path
    def save(self,path,value,*,replace=False):
        raw=(json.dumps(thaw(value),sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
        return self.bytes(path,raw,replace=replace)


def _result(run,status,batch=None,*,complete=False,error=None):
    return ImageSelectionResult(run_id=run.name,run_dir=run,status=status,
        batch_id=batch['batch_id'] if batch else None,
        selection_template=_folder(run,batch['batch_id'])/'selection-template.json' if batch else None,
        all_images_accepted=complete,log_dir=run/'logs/production',error=error)


def _folder(run,batch_id):
    if not isinstance(batch_id,str) or not re.fullmatch(r'image_batch_[0-9]{4}',batch_id):
        raise ProductionRefused('invalid image batch ID')
    return run_path(run,run/'production/image-selection'/batch_id)


from .scene_revision_records import revision_validation


@production_execution
@revision_validation
def _invoke(frozen,logger,lock,operation):
    run=None
    try:
        run=validate_run_dir(Path(frozen.options['script_path']).parent.parent)
        if lock is None:
            with RunLock(run) as held: return _invoke(frozen,logger,held,operation)
        store=_Records(run,lock); store.owned()
        if frozen.config.production_strategy!=STRATEGY or not _same_json(load_frozen_inputs(run),frozen):
            raise ProductionRefused('image selection frozen input/run identity differs')
        if 'scene_revision' in frozen.options:
            from .scene_revision_records import require_scene_revision
            store.revision_guard=require_scene_revision(frozen)['guard']
        if logger.run_dir!=run or not logger.production: raise ProductionRefused('matching production logger required')
        return operation(store)
    except (Exception,KeyboardInterrupt) as exc:
        status=('interrupted' if isinstance(exc,KeyboardInterrupt) else
                'blocked' if isinstance(exc,(ValueError,EmailPreconditionError,EmailRejected)) else 'failed')
        # SMTP adapters publish only safe categories; unexpected exception text is never copied.
        message=(str(exc) if isinstance(exc,(ProductionRefused,EmailPreconditionError,EmailRejected))
                 else 'Image selection '+status+' ('+type(exc).__name__+').')
        error=dict(kind=type(exc).__name__,message=message or status,evidence_paths=[])
        return ImageSelectionResult(run_id=run.name if run else None,run_dir=run,status=status,
            log_dir=run/'logs/production' if run else None,error=error)


def _transport_settings(frozen,batch,override):
    settings=parse_selection_email(thaw(frozen.config.raw.get('selection_email')) if override is None else thaw(override))
    if any(getattr(settings,k)!=batch['delivery'][k] for k in ('sender','recipient','max_mime_bytes')):
        raise ProductionRefused('email repair cannot change frozen addresses or MIME layout')
    return settings


def _activation_value(store,frozen,units,timeline,batch):
    run=store.run; root=run/'production/image-selection'; path=root/'active-batch.json'
    value=dict(schema_version=2,run_id=run.name,batch_id=batch['batch_id'],batch_sha256=canonical_digest(batch))
    bible,plan=records.load_committed_plan(frozen,units,timeline)
    accepted=records._load_accepted(frozen,units,timeline,bible,plan,before=batch['batch_index'])
    accepted_ids={row['batch_id'] for row in accepted}
    inherited_ids={bid for bid in accepted_ids if not (_folder(run,bid)/'accepted.json').exists()}
    if path.exists():
        previous=read_json(path)
        object_fields(previous,('schema_version','run_id','batch_id','batch_sha256'),'active image batch')
        if type(previous['schema_version']) is not int or previous['schema_version']!=2 or previous['run_id']!=run.name:
            raise ProductionRefused('active image batch schema/run differs')
        old=read_json(_folder(run,previous['batch_id'])/'batch.json')
        if previous['batch_sha256']!=canonical_digest(old): raise ProductionRefused('active batch SHA256 differs')
        if previous==value:return value
        required={f'image_batch_{i:04d}' for i in range(old['batch_index'],batch['batch_index'])}
        skipped=required-{old['batch_id']}
        if old['batch_index']>=batch['batch_index'] or not required<=accepted_ids or not skipped<=inherited_ids:
            raise ProductionRefused('active image batch cannot regress or skip unaccepted batches')
    elif batch['batch_index']!=1:
        required={f'image_batch_{i:04d}' for i in range(1,batch['batch_index'])}
        if not required<=inherited_ids:raise ProductionRefused('first image batch must be batch 1')
    return value


def _activate(store,frozen,units,timeline,batch):
    value=_activation_value(store,frozen,units,timeline,batch)
    root=store.run/'production/image-selection';path=root/'active-batch.json'
    if path.exists() and read_json(path)==value:return
    store.save(root/f"active-batch-{batch['batch_index']:04d}.json",value)
    store.save(path,value,replace=True); boundary('active-batch')


def _verify_file(run,row):
    path=run_path(run,row['path']); fresh=hash_file(path)
    if type(row['bytes']) is not int or (fresh.bytes,fresh.sha256)!=(row['bytes'],row['sha256']):
        raise ProductionRefused('notification backing bytes/SHA256 differs')
    return path.read_bytes()


def validate_notification(run,batch):
    """Read-only backing validation, also consumed by complete-acceptance checks."""
    folder=_folder(run,batch['batch_id']); mail=folder/'mail'; path=mail/'notification.json'
    value=read_json(path)
    object_fields(value,('schema_version','run_id','batch_id','scene_manifest_sha256','created_at','parts'),'image notification')
    if (type(value['schema_version']) is not int or value['schema_version']!=2 or value['run_id']!=run.name
            or value['batch_id']!=batch['batch_id'] or value['scene_manifest_sha256']!=canonical_digest(batch)):
        raise ProductionRefused('notification identity differs')
    timestamp(value['created_at'])
    if not isinstance(value['parts'],list) or not value['parts']: raise ProductionRefused('notification has no parts')
    attachments=[]
    for i,row in enumerate(value['parts'],1):
        object_fields(row,('part','total','message_id','path','bytes','sha256','attachments'),'notification part')
        if (type(row['part']) is not int or type(row['total']) is not int
                or row['part']!=i or row['total']!=len(value['parts'])
                or row['path']!=str(mail/f'part_{i:04d}/attempt_0001/message.eml')):
            raise ProductionRefused('notification page/path differs')
        raw=_verify_file(run,row)
        if len(raw)>batch['delivery']['max_mime_bytes']: raise ProductionRefused('notification exceeds MIME limit')
        parsed=BytesParser(policy=policy.SMTP).parsebytes(raw)
        if parsed['Message-ID']!=row['message_id']: raise ProductionRefused('notification Message-ID differs')
        if not isinstance(row['attachments'],list): raise ProductionRefused('invalid notification attachments')
        for att in row['attachments']:
            object_fields(att,('scene_id','candidate_id','original_sha256','attachment_sha256'),'notification attachment')
        payload_hashes={hashlib.sha256(p.get_payload(decode=True)).hexdigest() for p in parsed.walk()
                        if p.get_content_maintype()=='image' and not p.is_multipart()}
        if any(a['attachment_sha256'] not in payload_hashes for a in row['attachments']):
            raise ProductionRefused('notification actual attachment digest differs')
        attachments+=row['attachments']
    expected=[(s['scene_id'],c['candidate_id'],c['sha256']) for s in batch['scenes'] for c in s['candidates']]
    observed=[(a['scene_id'],a['candidate_id'],a['original_sha256']) for a in attachments]
    if observed!=expected: raise ProductionRefused('notification candidate coverage differs')
    return value


def _notification(store,frozen,batch,*,paths,logger):
    folder=_folder(store.run,batch['batch_id']); mail=folder/'mail'
    store.owned()
    media=prepare_email_media(batch,config=frozen.config,paths=paths,logger=logger)
    store.owned()
    stamp_path=mail/'created-at.json'
    if stamp_path.exists():
        stamp=read_json(stamp_path); object_fields(stamp,('created_at',),'notification creation')
    else:
        stamp=dict(created_at=now()); store.save(stamp_path,stamp)
    from ._scene_revision_origins import inherited
    imported=inherited(frozen,'plan','all')
    bible=imported['bible'] if imported is not None else read_json(store.run/'production/visual-bible.json')
    messages=build_messages(batch,media,created_at=stamp['created_at'],baseline_roles=bible['baselines'],**batch['delivery'])
    parts=[]
    for row in messages:
        raw=row['mime_bytes']; path=mail/f"part_{row['part']:04d}/attempt_0001/message.eml"
        store.bytes(path,raw)
        parts.append(dict(part=row['part'],total=row['total'],message_id=row['message_id'],path=str(path),
            bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),attachments=row['attachment_bindings']))
    value=dict(schema_version=2,run_id=store.run.name,batch_id=batch['batch_id'],scene_manifest_sha256=canonical_digest(batch),
               created_at=stamp['created_at'],parts=parts)
    store.save(mail/'notification.json',value); boundary('notification')
    return validate_notification(store.run,batch)


def _attempts(run,batch,row):
    folder=_folder(run,batch['batch_id'])/'mail'/f"part_{row['part']:04d}"
    dirs=sorted(p for p in folder.glob('attempt_*') if p.is_dir())
    if any(p.name!=f'attempt_{i:04d}' for i,p in enumerate(dirs,1)):
        raise ProductionRefused('noncontiguous SMTP attempts')
    return dirs


def _attempt_state(run,batch,row,folder):
    """Return accepted/unknown/rejected/unsent after validating attempt evidence."""
    intent_path=folder/'intent.json'
    if not intent_path.exists():
        if (folder/'receipt.json').exists() or (folder/'rejected.json').exists():
            raise ProductionRefused('SMTP outcome lacks intent')
        return 'unsent',None
    intent=read_json(intent_path)
    keys=('schema_version','run_id','batch_id','part','attempt','message_id','mime_sha256','transport','created_at')
    object_fields(intent,keys,'SMTP intent')
    attempt=int(folder.name.split('_')[1]); raw=(folder/'message.eml').read_bytes()
    expected_id=f"<{run.name}.{batch['batch_id']}.part_{row['part']:04d}.attempt_{attempt:04d}@video-ai.local>"
    if (type(intent['schema_version']) is not int or intent['schema_version']!=2 or intent['run_id']!=run.name
            or intent['batch_id']!=batch['batch_id'] or type(intent['part']) is not int or intent['part']!=row['part']
            or type(intent['attempt']) is not int or intent['attempt']!=attempt
            or intent['message_id']!=expected_id or intent['mime_sha256']!=hashlib.sha256(raw).hexdigest()):
        raise ProductionRefused('SMTP attempt identity differs')
    settings=parse_selection_email(intent['transport'])
    if thaw(settings)!=intent['transport'] or any(getattr(settings,k)!=batch['delivery'][k] for k in batch['delivery']):
        raise ProductionRefused('SMTP attempt transport differs')
    timestamp(intent['created_at'])
    parsed=BytesParser(policy=policy.SMTP).parsebytes(raw)
    if parsed['Message-ID']!=expected_id or len(raw)>batch['delivery']['max_mime_bytes']:
        raise ProductionRefused('SMTP attempt MIME identity differs')
    # Later attempts may change only delivery identity and MIME boundaries.
    original=BytesParser(policy=policy.SMTP).parsebytes(run_path(run,row['path']).read_bytes())
    def contents(message):
        return [(p.get_content_type(),p.get_filename(),p.get_payload(decode=True)) for p in message.walk() if not p.is_multipart()]
    if contents(parsed)!=contents(original) or any(parsed[k]!=original[k] for k in ('From','To','Subject')):
        raise ProductionRefused('SMTP retry changed notification contents')
    found=[]
    for name,extra,status in [('receipt.json',('accepted_at','smtp_code'),'accepted'),
                              ('rejected.json',('rejected_at','smtp_code'),'rejected')]:
        path=folder/name
        if not path.exists(): continue
        outcome=read_json(path); object_fields(outcome,keys+extra,'SMTP outcome')
        if canonical_digest({k:outcome[k] for k in keys})!=canonical_digest(intent):
            raise ProductionRefused('SMTP receipt differs from intent')
        code=outcome['smtp_code']
        if type(code) is not int or (status=='accepted' and not 200<=code<300) or (status=='rejected' and not 400<=code<600):
            raise ProductionRefused('invalid SMTP result code')
        timestamp(outcome[extra[0]]); found.append(status)
    if len(found)>1: raise ProductionRefused('conflicting SMTP outcomes')
    return (found[0] if found else 'unknown'),intent


def notification_delivery_state(run,batch):
    notification=validate_notification(run,batch); statuses=[]
    for row in notification['parts']:
        states=[_attempt_state(run,batch,row,p)[0] for p in _attempts(run,batch,row)]
        if 'accepted' in states:
            if states.index('accepted')!=len(states)-1: raise ProductionRefused('SMTP accepted page has later attempt')
            statuses.append('accepted')
        else: statuses.append(states[-1] if states else 'unsent')
    if 'unknown' in statuses: return 'unknown'
    if 'rejected' in statuses: return 'rejected'
    return 'accepted' if all(s=='accepted' for s in statuses) else 'unsent'


def _send_page(store,batch,row,folder,settings,smtp_factory):
    raw=run_path(store.run,folder/'message.eml').read_bytes()
    attempt=int(folder.name.split('_')[1]); message=BytesParser(policy=policy.SMTP).parsebytes(raw)
    if attempt==1 and (len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']):
        raise ProductionRefused('captured SMTP MIME differs from notification')
    intent=dict(schema_version=2,run_id=store.run.name,batch_id=batch['batch_id'],part=row['part'],attempt=attempt,
        message_id=message['Message-ID'],mime_sha256=hashlib.sha256(raw).hexdigest(),transport=thaw(settings),created_at=now())
    def before_data():
        store.owned(); store.save(folder/'intent.json',intent); boundary('intent'); store.owned()
    store.owned()
    try:
        response=SmtpSender(settings,smtp_factory=smtp_factory,ownership_check=store.owned).send(raw,before_data=before_data)
    except EmailDeliveryUnknown:
        return 'unknown'
    except EmailRejected as exc:
        store.owned()
        if (folder/'intent.json').exists():
            code=getattr(exc,'smtp_code',getattr(exc,'code',550))
            store.save(folder/'rejected.json',dict(intent,rejected_at=now(),smtp_code=code))
        return 'rejected'
    store.owned(); boundary('data-accepted'); store.owned()
    store.save(folder/'receipt.json',dict(intent,accepted_at=now(),smtp_code=response['smtp_code']))
    boundary('receipt')
    return 'accepted'


def _deliver(store,frozen,batch,notification,*,email_settings,smtp_factory):
    settings=_transport_settings(frozen,batch,email_settings)
    for row in notification['parts']:
        attempts=_attempts(store.run,batch,row)
        if not attempts: raise ProductionRefused('notification missing initial MIME')
        outcomes=[_attempt_state(store.run,batch,row,p)[0] for p in attempts]
        if 'accepted' in outcomes:
            if outcomes[-1]!='accepted': raise ProductionRefused('accepted SMTP page has later attempt')
            continue
        if outcomes[-1] in ('unknown','rejected'): return outcomes[-1]
        state=_send_page(store,batch,row,attempts[-1],settings,smtp_factory)
        if state!='accepted': return state
    return 'accepted'


def _load_batch(frozen,units,timeline,batch_id):
    bible,plan=records.load_committed_plan(frozen,units,timeline)
    batch=read_json(records.batch_directory(frozen,batch_id)/'batch.json')
    records.validate_batch(frozen,units,timeline,bible,plan,batch)
    return bible,plan,batch


def _accepted_result(store,frozen,units,timeline,batch):
    bible,plan=records.load_committed_plan(frozen,units,timeline)
    accepted=records.load_accepted_batches(frozen,units,timeline,bible,plan)
    if not any(a['batch_id']==batch['batch_id'] for a in accepted):
        return _result(store.run,'awaiting_image_selection',batch)
    complete_path=store.run/'production/image-selection/complete-acceptance.json'
    if complete_path.exists():
        records.require_complete_image_acceptance(frozen,units,timeline)
        return _result(store.run,'image_batch_accepted',batch,complete=True)
    covered={r['scene_id'] for a in accepted for r in a['selections']}
    status='awaiting_image_selection' if len(covered)==len(plan['scenes']) else 'image_batch_accepted'
    return _result(store.run,status,batch)


def prepare_image_batch(frozen,units,timeline,candidate_manifests,*,batch_index,paths,logger,
                        email_settings=None,smtp_factory=None,lock=None):
    def operation(store):
        batch=records.build_batch(frozen,units,timeline,candidate_manifests,batch_index=batch_index)
        folder=_folder(store.run,batch['batch_id'])
        # Validate forward movement before exposing any new batch records.
        _activation_value(store,frozen,units,timeline,batch)
        store.save(folder/'batch.json',batch); boundary('batch')
        store.save(folder/'selection-template.json',records.selection_template(batch)); boundary('selection-template')
        _activate(store,frozen,units,timeline,batch)
        notification=_notification(store,frozen,batch,paths=paths,logger=logger)
        state=_deliver(store,frozen,batch,notification,email_settings=email_settings,smtp_factory=smtp_factory)
        if state=='unknown': return _result(store.run,'email_delivery_unknown',batch,error=dict(
            kind='EmailDeliveryUnknown',message='SMTP DATA outcome unknown; explicit retry required.',evidence_paths=[]))
        if state=='rejected': raise ProductionRefused('SMTP DATA explicitly rejected; explicit retry required')
        return _accepted_result(store,frozen,units,timeline,batch)
    return _invoke(frozen,logger,lock,operation)


def _stable_submission(path):
    path=Path(path)
    with path.open('rb') as file:
        before=os.fstat(file.fileno()); raw=file.read(); after=os.fstat(file.fileno())
    current=path.stat()
    fields=lambda st:(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)
    if fields(before)!=fields(after) or fields(after)!=fields(current):
        raise ProductionRefused('image selection file changed while reading')
    from ..adapters.common import strict_json
    value=strict_json(raw)
    return raw,value


def consume_image_selection(frozen,units,timeline,selection_path,*,paths,logger,lock=None):
    def operation(store):
        raw,value=_stable_submission(selection_path)
        if not isinstance(value,dict): raise ProductionRefused('selection must be an object')
        bible,plan,batch=_load_batch(frozen,units,timeline,value.get('batch_id'))
        active=read_json(store.run/'production/image-selection/active-batch.json')
        object_fields(active,('schema_version','run_id','batch_id','batch_sha256'),'active image batch')
        if (type(active['schema_version']) is not int or active['schema_version']!=2 or active['run_id']!=store.run.name
                or active['batch_id']!=batch['batch_id'] or active['batch_sha256']!=canonical_digest(batch)):
            raise ProductionRefused('selection must target current active batch')
        notification=validate_notification(store.run,batch)
        state=notification_delivery_state(store.run,batch)
        if state=='unknown': return _result(store.run,'email_delivery_unknown',batch,error=dict(
            kind='EmailDeliveryUnknown',message='SMTP DATA outcome unknown; explicit retry required.',evidence_paths=[]))
        if state!='accepted': raise ProductionRefused('all notification pages need valid SMTP acceptance receipts')
        accepted=records.load_accepted_batches(frozen,units,timeline,bible,plan)
        normalized=records.validate_selection(frozen,bible,plan,batch,value,accepted_batches=accepted)
        folder=_folder(store.run,batch['batch_id']); digest=hashlib.sha256(raw).hexdigest()
        store.bytes(folder/'submissions'/f'{digest}.json',raw); boundary('submission')
        if value['intent']=='draft': return _result(store.run,'awaiting_image_selection',batch)
        proposed=records.build_accepted(batch,normalized,source_submission_sha256=digest,bible=bible,accepted_batches=accepted)
        target=folder/'accepted.json'
        if target.exists():
            old=read_json(target)
            # New observations can keep the immutable first accepted source.
            if old['selections']!=proposed['selections'] or old['baseline_bindings']!=proposed['baseline_bindings']:
                raise ProductionRefused('accepted image choices cannot change; create a revision run')
        else:
            store.save(target,proposed); boundary('accepted')
        accepted=records.load_accepted_batches(frozen,units,timeline,bible,plan)
        covered={r['scene_id'] for a in accepted for r in a['selections']}
        obs=normalized['observation']
        if (len(covered)==len(plan['scenes']) and obs is not None and obs['scope']=='all_selected_images'
                and obs['verdict']=='passed'):
            complete=records.build_complete_acceptance(frozen,bible,plan,accepted,obs,observation_submission_sha256=digest)
            target=store.run/'production/image-selection/complete-acceptance.json'
            if target.exists(): records.require_complete_image_acceptance(frozen,units,timeline)
            else: store.save(target,complete); boundary('complete-acceptance')
        return _accepted_result(store,frozen,units,timeline,batch)
    return _invoke(frozen,logger,lock,operation)


def load_prepared_inputs(frozen):
    if 'scene_revision' in frozen.options:
        from .scene_revision_records import require_scene_revision,require_revision_import
        proof=require_scene_revision(frozen)
        if 'common:all' in proof['imports']:
            view=require_revision_import(frozen,'common','all',context=proof)
            timeline=ProductionTimeline.from_dict(view['timeline'])
            records.load_committed_plan(frozen,view['units'],timeline)
            return view['units'],timeline
    run=validate_run_dir(Path(frozen.options['script_path']).parent.parent)
    payloads=[]
    for stage in ('units','timeline'):
        path=run_path(run,run/f'production/{stage}.json')
        if not path.exists(): raise ProductionRefused('prepared image selection requires units/timeline reports')
        report=read_json(path)
        object_fields(report,('schema_version','execution_mode','run_id','stage','created_at','status','input_records','payload'),'prepared report')
        if (type(report['schema_version']) is not int or report['schema_version']!=1
                or report['execution_mode']!='automatic' or report['run_id']!=run.name
                or report['stage']!=stage or report['status']!='completed'):
            raise ProductionRefused('prepared units/timeline report identity differs')
        timestamp(report['created_at']); payloads.append(report['payload'])
    units=payloads[0]; timeline=ProductionTimeline.from_dict(payloads[1])
    records.load_committed_plan(frozen,units,timeline)
    return units,timeline


def resume_image_selection(frozen,*,paths,logger,selection_path=None,lock=None,smtp_factory=None,email_settings=None):
    def operation(store):
        units,timeline=load_prepared_inputs(frozen)
        if selection_path is not None:
            return consume_image_selection(frozen,units,timeline,selection_path,paths=paths,logger=logger,lock=store.lock)
        active=read_json(store.run/'production/image-selection/active-batch.json')
        object_fields(active,('schema_version','run_id','batch_id','batch_sha256'),'active image batch')
        bible,plan,batch=_load_batch(frozen,units,timeline,active['batch_id'])
        if (type(active['schema_version']) is not int or active['schema_version']!=2 or active['run_id']!=store.run.name
                or active['batch_sha256']!=canonical_digest(batch)):
            raise ProductionRefused('active image batch identity differs')
        return prepare_image_batch(frozen,units,timeline,[s['candidate_manifest']['path'] for s in batch['scenes']],
            batch_index=batch['batch_index'],paths=paths,logger=logger,email_settings=email_settings,
            smtp_factory=smtp_factory,lock=store.lock)
    return _invoke(frozen,logger,lock,operation)


def retry_notification(frozen,batch_id,part,*,expected_attempt_sha256,email_settings=None,paths,logger,smtp_factory=None,lock=None):
    def operation(store):
        if type(part) is not int or part<1: raise ProductionRefused('invalid retry part')
        units,timeline=load_prepared_inputs(frozen)
        bible,plan,batch=_load_batch(frozen,units,timeline,batch_id)
        notification=validate_notification(store.run,batch)
        if part>len(notification['parts']): raise ProductionRefused('unknown notification part')
        row=notification['parts'][part-1]; attempts=_attempts(store.run,batch,row)
        state,intent=_attempt_state(store.run,batch,row,attempts[-1])
        if state not in ('unknown','rejected'): raise ProductionRefused('only failed/unknown SMTP intents can be retried')
        if hashlib.sha256((attempts[-1]/'intent.json').read_bytes()).hexdigest()!=expected_attempt_sha256:
            raise ProductionRefused('retry intent SHA256 differs')
        settings=_transport_settings(frozen,batch,email_settings)
        attempt=len(attempts)+1; folder=attempts[-1].parent/f'attempt_{attempt:04d}'
        parsed=BytesParser(policy=policy.SMTP).parsebytes((attempts[-1]/'message.eml').read_bytes())
        parsed.replace_header('Message-ID',f'<{store.run.name}.{batch_id}.part_{part:04d}.attempt_{attempt:04d}@video-ai.local>')
        from email.utils import format_datetime
        from datetime import datetime
        parsed.replace_header('Date',format_datetime(datetime.now().astimezone()))
        for i,p in enumerate(parsed.walk()):
            if p.is_multipart(): p.set_boundary(f'video-ai-{batch_id}-{part}-{attempt}-{i}')
        raw=parsed.as_bytes()
        if len(raw)>batch['delivery']['max_mime_bytes']: raise ProductionRefused('retried MIME exceeds frozen limit')
        store.bytes(folder/'message.eml',raw)
        state=_send_page(store,batch,row,folder,settings,smtp_factory)
        if state=='unknown': return _result(store.run,'email_delivery_unknown',batch,error=dict(
            kind='EmailDeliveryUnknown',message='Explicit SMTP retry outcome unknown.',evidence_paths=[]))
        if state=='rejected': raise ProductionRefused('explicit SMTP retry rejected')
        state=_deliver(store,frozen,batch,notification,email_settings=email_settings,smtp_factory=smtp_factory)
        if state=='unknown': return _result(store.run,'email_delivery_unknown',batch,error=dict(
            kind='EmailDeliveryUnknown',message='SMTP DATA outcome unknown.',evidence_paths=[]))
        if state=='rejected': raise ProductionRefused('another SMTP page needs explicit retry')
        return _accepted_result(store,frozen,units,timeline,batch)
    return _invoke(frozen,logger,lock,operation)
