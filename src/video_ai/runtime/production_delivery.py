"""Exclusive automatic delivery, with recoverable no-overwrite publication."""
from contextlib import contextmanager
from copy import deepcopy
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4

from ..config import read_json
from .manifest import now
from .production_state import (ArtifactStamp, ProductionRefused, json_bytes, run_path,
    write_exclusive, process_started_at)
from .production_delivery_records import (ROLES, output_path, validate_targets, validate_owner,
    file_identity, sources_for, media_for, validate_delivery_transaction, validate_delivery_receipt)

BLOCK = 1024*1024


def boundary(event, role):
    """Durability boundary; also used for deterministic crash injection."""


class OutputLock:
    def __init__(self, run, movie, *, run_lock_owner=None):
        self.run=run;self.movie=output_path(movie)
        self.path=self.movie.with_name('.'+self.movie.stem+'.make-video.lock')
        self.owner=dict(schema_version=1,execution_mode='automatic',run_id=run.name,
            pid=os.getpid(),process_started_at=process_started_at(os.getpid()),token=uuid4().hex,target_movie=str(self.movie))
        self.intent_path=run_path(run,run/f'logs/production/delivery/locks/{self.owner["token"]}.json')
        run_lock=run_path(run,run/'.make-video.lock')
        self.run_owner=deepcopy(run_lock_owner) if run_lock_owner is not None else read_json(run_lock) if run_lock.exists() else None

    @property
    def record(self):return dict(owner=deepcopy(self.owner),intent_path=str(self.intent_path),lock_path=str(self.path))

    def check(self):
        if read_json(output_path(self.path))!=self.owner:raise ProductionRefused('output lock owner changed; retained')
        run_lock=run_path(self.run,self.run/'.make-video.lock')
        if self.run_owner is not None:
            if not run_lock.is_file() or read_json(run_lock)!=self.run_owner:
                raise ProductionRefused('run lock ownership changed')

    @contextmanager
    def guard(self):
        path=output_path(self.path.with_name('.'+self.movie.stem+'.make-video-reclaim.lock'))
        try:write_exclusive(path,self.owner)
        except FileExistsError as exc:raise ProductionRefused('output reclaim is already guarded') from exc
        try:yield
        finally:
            has_error=sys.exc_info()[0] is not None
            try:
                if read_json(output_path(path))!=self.owner:raise ProductionRefused('output reclaim guard changed')
                path.unlink()
            except (OSError,ValueError):
                if not has_error:raise

    def __enter__(self):
        output_path(self.path);self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists():
            with self.guard():
                owner=read_json(output_path(self.path));validate_owner(owner,self.run,self.movie)
                intent_path=run_path(self.run,self.run/f'logs/production/delivery/locks/{owner["token"]}.json')
                intent=read_json(intent_path)
                from .production_state import object_fields,timestamp
                object_fields(intent,('owner','lock_path','created_at'),'output lock intent');timestamp(intent['created_at'])
                if intent['owner']!=owner or intent['lock_path']!=str(self.path):raise ProductionRefused('foreign output lock intent')
                if process_started_at(owner['pid']) is not None:raise ProductionRefused('live or reused PID output lock')
                audit=run_path(self.run,self.run/f'logs/production/delivery/reclaims/{uuid4().hex}.json')
                write_exclusive(audit,dict(owner=owner,lock_path=str(self.path),checked_at=now(),action='archive_ended_owner'))
                if read_json(output_path(self.path))!=owner:raise ProductionRefused('output lock changed during reclaim')
                archive=output_path(self.path.with_name(self.path.name+'.'+uuid4().hex+'.archive'))
                os.rename(output_path(self.path),archive)
        write_exclusive(self.intent_path,dict(owner=self.owner,lock_path=str(self.path),created_at=now()))
        try:write_exclusive(output_path(self.path),self.owner)
        except FileExistsError as exc:raise ProductionRefused('output already locked') from exc
        self.check();return self

    def __exit__(self,kind,exc,tb):
        try:self.check();output_path(self.path).unlink()
        except (OSError,ValueError):
            if exc is None:raise
        return False


def temporary(targets,run,transaction_id,role):
    movie=Path(targets['movie'])
    return str(output_path(movie.with_name(f'.{movie.stem}.{run.name}.{transaction_id}.{role}.{uuid4().hex}.tmp')))


def new_transaction(frozen,run,lock):
    targets=dict(frozen.options['output_paths']);validate_targets(targets,run,frozen=frozen)
    transaction_id=uuid4().hex;stamp=now()
    return dict(schema_version=1,execution_mode='automatic',run_id=run.name,created_at=stamp,updated_at=stamp,
        transaction_id=transaction_id,status='publishing',lock_record=lock.record,source_records=sources_for(run),output_paths=targets,
        operations={r:dict(status='pending',temp_path=temporary(targets,run,transaction_id,r),file_id=None,
            temp_stamp=None,output_stamp=None,archives=[]) for r in ROLES},receipt=None)


def save_transaction(run,data,lock,*,initial=False):
    lock.check();validate_delivery_transaction(data,run)
    path=run_path(run,run/'production/delivery.json')
    if initial:write_exclusive(path,data)
    else:
        existing=read_json(path)
        if existing['status']=='completed':
            if existing!=data:raise ProductionRefused('completed delivery transaction is frozen')
            return
        data['updated_at']=now();validate_delivery_transaction(data,run)
        temporary_path=run_path(run,path.with_name('delivery.'+uuid4().hex+'.tmp'))
        write_exclusive(temporary_path,data);lock.check();os.replace(temporary_path,path)
    if read_json(path)!=data:raise OSError('delivery transaction readback differs')


def verify_source(stamp):
    stamp=ArtifactStamp.from_dict(stamp);stamp.verify();return stamp


def source_stat_matches(stat,stamp):
    if (stat.st_size,stat.st_mtime_ns)!=(stamp.bytes,stamp.mtime_ns):
        raise ProductionRefused('source changed through open file handle')


def copy_media(source,target_file):
    """No media transforms: bounded copy with before/after source observations."""
    stamp=verify_source(source);count=0
    with Path(stamp.path).open('rb') as original:
        source_stat_matches(os.fstat(original.fileno()),stamp)
        while block:=original.read(BLOCK):
            target_file.write(block);count+=len(block)
        source_stat_matches(os.fstat(original.fileno()),stamp)
    if count!=stamp.bytes:raise ProductionRefused('copied source byte count differs')
    stamp.verify()


def compare_media(source,target):
    stamp=verify_source(source);target=output_path(target);count=0
    with Path(stamp.path).open('rb') as original,target.open('rb') as copy:
        source_stat_matches(os.fstat(original.fileno()),stamp)
        while block:=original.read(BLOCK):
            if copy.read(len(block))!=block:raise ProductionRefused('delivery copied bytes differ')
            count+=len(block)
        if copy.read(1) or count!=stamp.bytes:raise ProductionRefused('delivery copied length differs')
        source_stat_matches(os.fstat(original.fileno()),stamp)
    stamp.verify()


def compare_output(tx,role,path):
    if role=='receipt':
        if output_path(path).read_bytes()!=json_bytes(tx['receipt']) or read_json(path)!=tx['receipt']:
            raise ProductionRefused('delivery receipt bytes differ')
    else:compare_media(tx['source_records']['candidate' if role=='movie' else 'subtitle'],path)


def check_owned(path,op,stamp=None):
    path=output_path(path)
    if not path.is_file() or file_identity(path)!=op['file_id']:raise ProductionRefused('delivery file ownership differs')
    if stamp is not None:
        actual=ArtifactStamp.read(path)
        if (actual.bytes,actual.mtime_ns)!=(stamp['bytes'],stamp['mtime_ns']):raise ProductionRefused('delivery file stamp changed')


def admit_targets(tx,lock):
    lock.check();targets=validate_targets(tx['output_paths'],lock.run)
    marker=output_path(targets['movie'].with_suffix('.publication.json'))
    if marker.exists():raise ProductionRefused('foreign publication marker occupies delivery stem')
    for role,target in targets.items():
        op=tx['operations'][role];temp=output_path(op['temp_path'])
        if op['status']=='published':
            check_owned(target,op,op['output_stamp']);compare_output(tx,role,target)
            if temp.exists():raise ProductionRefused('published temporary unexpectedly exists')
        elif target.exists():
            if op['status']!='copied' or temp.exists():raise ProductionRefused('foreign output already exists')
            check_owned(target,op,op['temp_stamp']);compare_output(tx,role,target)


def archive_partial(tx,run,role,lock):
    """Persist intent before moving only this transaction's uncompleted file."""
    from .production_state import object_fields,timestamp
    op=tx['operations'][role];old=output_path(op['temp_path'])
    folder=run_path(run,run/'logs/production/delivery/archives');folder.mkdir(parents=True,exist_ok=True)
    matches=[]
    for p in folder.glob('*.json'):
        intent=read_json(p)
        if intent.get('old_path')==str(old):matches.append(intent)
    if len(matches)>1:raise ProductionRefused('ambiguous partial archive intents')
    if matches:
        intent=matches[0];object_fields(intent,('role','old_path','archive_path','file_id','created_at'),'archive intent');timestamp(intent['created_at'])
        if intent['role']!=role or intent['file_id']!=op['file_id']:raise ProductionRefused('archive intent identity differs')
        archive=output_path(intent['archive_path'])
        if archive.parent!=old.parent or not archive.name.startswith(old.name+'.') or archive.suffix!='.archive':raise ProductionRefused('archive intent path differs')
    else:
        check_owned(old,op)
        archive=output_path(old.with_name(old.name+'.'+uuid4().hex+'.archive'))
        intent=dict(role=role,old_path=str(old),archive_path=str(archive),file_id=op['file_id'],created_at=now())
        write_exclusive(folder/(uuid4().hex+'.json'),intent)
    lock.check()
    if old.exists():
        check_owned(old,op)
        if archive.exists():raise ProductionRefused('archive and partial both exist')
        os.rename(output_path(old),output_path(archive));boundary('archived',role)
    else:check_owned(archive,op)
    op['archives'].append(dict(path=str(archive),file_id=deepcopy(op['file_id']),stamp=ArtifactStamp.read(archive).to_dict()))
    op.update(status='pending',temp_path=temporary(tx['output_paths'],run,tx['transaction_id'],role),file_id=None,temp_stamp=None,output_stamp=None)
    save_transaction(run,tx,lock)


def publish_operation(tx,run,role,lock):
    op=tx['operations'][role];target=output_path(tx['output_paths'][role])
    if op['status']=='published':return
    if op['status']=='created':archive_partial(tx,run,role,lock)
    temp=output_path(op['temp_path'])
    if op['status']=='pending':
        boundary('pending',role);lock.check();admit_targets(tx,lock)
        if temp.exists():raise ProductionRefused('unregistered temporary retained; ownership unknown')
        try:file=temp.open('xb')
        except FileExistsError as exc:raise ProductionRefused('foreign temporary appeared') from exc
        with file:
            stat=os.fstat(file.fileno());op.update(status='created',file_id=dict(device=stat.st_dev,inode=stat.st_ino))
            save_transaction(run,tx,lock);boundary('created',role)
            if role=='receipt':file.write(json_bytes(tx['receipt']))
            else:copy_media(tx['source_records']['candidate' if role=='movie' else 'subtitle'],file)
            file.flush();os.fsync(file.fileno())
        compare_output(tx,role,temp);check_owned(temp,op)
        op.update(status='copied',temp_stamp=ArtifactStamp.read(temp).to_dict())
        save_transaction(run,tx,lock);boundary('copied',role)
    if op['status']=='copied':
        lock.check();validate_delivery_transaction(tx,run)
        if temp.exists():
            if target.exists():raise ProductionRefused('foreign target appeared before publication')
            check_owned(temp,op,op['temp_stamp']);compare_output(tx,role,temp);lock.check()
            try:os.rename(output_path(temp),output_path(target))
            except FileExistsError as exc:raise ProductionRefused('foreign target appeared during publication') from exc
            boundary('renamed',role)
        elif not target.exists():raise ProductionRefused('copied file and published target are missing')
        check_owned(target,op,op['temp_stamp']);compare_output(tx,role,target)
        op.update(status='published',output_stamp=ArtifactStamp.read(target).to_dict())
        save_transaction(run,tx,lock);boundary('published',role)


def publish_delivery(frozen,run,lock):
    path=run_path(run,run/'production/delivery.json')
    if path.exists():
        tx=read_json(path);validate_delivery_transaction(tx,run,frozen=frozen)
    else:
        tx=new_transaction(frozen,run,lock);admit_targets(tx,lock)
        needed=tx['source_records']['candidate']['bytes']+tx['source_records']['subtitle']['bytes']+64*1024*1024
        if shutil.disk_usage(Path(tx['output_paths']['movie']).parent).free<needed:raise OSError('insufficient delivery disk space')
        save_transaction(run,tx,lock,initial=True)
    admit_targets(tx,lock)
    if tx['status']=='completed':return tx['receipt']
    for role in ROLES:
        if role=='receipt' and tx['receipt'] is None:
            checks=read_json(run/'production/technical-checks.json')['technical_checks']
            tx['receipt']=dict(schema_version=1,execution_mode='automatic',run_id=run.name,delivered_at=now(),
                movie=tx['operations']['movie']['output_stamp'],subtitle=tx['operations']['subtitle']['output_stamp'],
                media=media_for(run),technical_checks=checks,human_review='unverified',actual_video_semantics='unverified',
                actual_action_sync='unverified',production_report=str(run/'production/composition.json'))
            validate_delivery_receipt(tx['receipt'],run,frozen=frozen);save_transaction(run,tx,lock)
        publish_operation(tx,run,role,lock)
    admit_targets(tx,lock);tx['status']='completed';save_transaction(run,tx,lock);boundary('completed','receipt')
    return tx['receipt']


def produce_delivery(frozen,*,state,manifest,paths,logger):
    from .production_support import stamps,commit_checkpoint,recover_checkpoint,read_report,checkpoint_path
    run=state.run_dir;snapshot=state.snapshot()
    if snapshot['stages']['composition']['status']!='completed':raise ProductionRefused('delivery requires completed composition')
    composition=read_report(state,'composition')
    final=read_json(checkpoint_path(state,'composition','final'))
    if final['payload']!=composition['payload']:raise ProductionRefused('composition final differs')
    if snapshot['stages']['delivery']['status']!='completed':state.start_stage('delivery')
    logger.progress('delivery')
    owner=getattr(state,'_run_lock_owner',None)
    if owner is None:raise ProductionRefused('delivery requires the held run lock identity')
    with OutputLock(run,frozen.options['output_paths']['movie'],run_lock_owner=owner) as lock:
        receipt=publish_delivery(frozen,run,lock)
        state.set_delivery(run/'production/delivery.json')
        copy=run_path(run,run/'logs/production/delivery/receipt.json')
        if copy.exists():
            if read_json(copy)!=receipt:raise ProductionRefused('receipt record changed')
        else:write_exclusive(copy,receipt)
        boundary('receipt_record','receipt')
        checkpoint=recover_checkpoint(state,'delivery','final')
        expected_payload=dict(transaction=ArtifactStamp.read(run/'production/delivery.json').to_dict(),receipt=receipt,
            receipt_stamp=ArtifactStamp.read(frozen.options['output_paths']['receipt']).to_dict())
        outputs=stamps(dict(transaction=run/'production/delivery.json',composition=run/'production/composition.json',
            technical_checks=run/'production/technical-checks.json',receipt_record=copy))
        if checkpoint is None:
            state.record_unit('delivery','final',status='running')
            commit_checkpoint(state,'delivery','final',outputs=outputs,payload=expected_payload)
        elif checkpoint['payload']!=expected_payload or checkpoint['outputs']!=outputs:
            raise ProductionRefused('delivery final checkpoint changed')
        boundary('final_checkpoint','receipt')
        report=read_report(state,'delivery')
        inputs=stamps(dict(options=run/'production/options.json',composition=run/'production/composition.json',
            technical_checks=run/'production/technical-checks.json',transaction=run/'production/delivery.json',
            final_checkpoint=checkpoint_path(state,'delivery','final')))
        if report is None:state.write_report('delivery',receipt,input_records=inputs)
        elif report['payload']!=receipt or report['input_records']!=inputs:raise ProductionRefused('delivery report differs')
        boundary('delivery_report','receipt')
        lock.check()
        if state.snapshot()['stages']['delivery']['status']!='completed':state.complete_stage('delivery')
        state.set_invocation('delivered')
        boundary('delivery_state','receipt')
        snapshot=state.snapshot()
        if snapshot['active_stage'] is not None or snapshot['invocation_status']!='delivered':raise ProductionRefused('delivery state was not committed')
    return receipt
