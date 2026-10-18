"""Strict automatic delivery records; official paths have a dedicated policy."""
import math
import os
from pathlib import Path
import re

from ..config import read_json
from .paths import PathPolicy
from .production_state import (ArtifactStamp, ProductionRefused, absolute_path, object_fields,
    integer, timestamp, run_path, json_bytes, _header)
from .production_composition_records import TECHNICAL_CHECKS, validate_composition_report, validate_technical_checks

ROLES = ('movie', 'subtitle', 'receipt')
SOURCES = ('options', 'composition', 'technical_checks', 'candidate', 'subtitle')


def output_path(value):
    path = absolute_path(str(value))
    if '..' in path.parts or '.' in path.parts:
        raise ProductionRefused('output path alias is forbidden')
    for item in (path, *path.parents):
        if item.is_symlink() or item.is_junction():
            raise ProductionRefused(f'redirected output path: {item}')
    checked = PathPolicy().validate_write(path, 'output')
    if checked != path or (path.exists() and not path.is_file()):
        raise ProductionRefused(f'output path changed or is not a regular file: {path}')
    return checked


def validate_targets(data, run, *, frozen=None):
    object_fields(data, ROLES, 'output paths')
    targets = {key:output_path(value) for key,value in data.items()}
    movie = targets['movie']
    if movie.suffix.lower() != '.mp4' or targets['subtitle'] != movie.with_suffix('.srt') or targets['receipt'] != movie.with_suffix('.delivery.json'):
        raise ProductionRefused('output roles/stem differ')
    expected = frozen.options['output_paths'] if frozen is not None else read_json(run_path(run, run/'production/options.json'))['output_paths']
    if data != dict(expected): raise ProductionRefused('output differs from frozen targets')
    return targets


def token(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{32}',value):
        raise ProductionRefused('expected 32 digit hex token')


def validate_owner(owner, run, movie):
    object_fields(owner,('schema_version','execution_mode','run_id','pid','process_started_at','token','target_movie'),'output lock owner')
    if type(owner['schema_version']) is not int or owner['schema_version'] != 1 or owner['execution_mode'] != 'automatic' or owner['run_id'] != run.name:
        raise ProductionRefused('foreign output lock identity')
    integer(owner['pid'],'lock pid',1); token(owner['token'])
    if not isinstance(owner['process_started_at'],str) or not re.fullmatch('[0-9]+',owner['process_started_at']):
        raise ProductionRefused('invalid process start time')
    if output_path(owner['target_movie']) != movie: raise ProductionRefused('output lock target differs')


def file_identity(path):
    with output_path(path).open('rb') as file:
        stat = os.fstat(file.fileno())
    return dict(device=stat.st_dev, inode=stat.st_ino)


def validate_file_id(value):
    object_fields(value,('device','inode'),'file identity')
    integer(value['device'],'device');integer(value['inode'],'inode',1)


def sources_for(run):
    composition_path=run_path(run,run/'production/composition.json')
    composition=read_json(composition_path)
    validate_composition_report(composition['payload'],run)
    technical_path=run_path(run,run/'production/technical-checks.json')
    validate_technical_checks(read_json(technical_path),run)
    return dict(options=ArtifactStamp.read(run_path(run,run/'production/options.json')).to_dict(),
        composition=ArtifactStamp.read(composition_path).to_dict(),technical_checks=ArtifactStamp.read(technical_path).to_dict(),
        candidate=composition['payload']['candidate'],subtitle=composition['payload']['subtitle'])


def media_for(run):
    p=read_json(run_path(run,run/'production/composition.json'))['payload']
    validate_composition_report(p,run)
    return dict(width=1920,height=1080,fps=16,frames=p['frames'],duration_seconds=p['frames']/16,
        video_codec='h264',pix_fmt='yuv420p',audio_codec='aac',audio_sample_rate=48000)


def validate_delivery_receipt(data, run, *, frozen=None):
    object_fields(data,('schema_version','execution_mode','run_id','delivered_at','movie','subtitle','media','technical_checks',
        'human_review','actual_video_semantics','actual_action_sync','production_report'),'delivery receipt')
    if type(data['schema_version']) is not int or data['schema_version'] != 1 or data['execution_mode'] != 'automatic' or data['run_id'] != run.name:
        raise ProductionRefused('receipt identity differs')
    timestamp(data['delivered_at'])
    targets=validate_targets(dict(frozen.options['output_paths']) if frozen is not None else read_json(run/'production/options.json')['output_paths'],run,frozen=frozen)
    for role in ('movie','subtitle'):
        stamp=ArtifactStamp.from_dict(data[role])
        if output_path(stamp.path)!=targets[role]:raise ProductionRefused('receipt target differs')
        stamp.verify()
    expected=media_for(run);object_fields(data['media'],expected,'receipt media')
    for key in ('width','height','fps','frames','audio_sample_rate'):integer(data['media'][key],key,1)
    duration=data['media']['duration_seconds']
    if type(duration) not in (int,float) or not math.isfinite(duration) or data['media']!=expected:
        raise ProductionRefused('receipt media differs from original probe')
    object_fields(data['technical_checks'],TECHNICAL_CHECKS,'receipt technical checks')
    if any(v!='passed' for v in data['technical_checks'].values()):raise ProductionRefused('delivery requires five passed checks')
    if any(data[key]!='unverified' for key in ('human_review','actual_video_semantics','actual_action_sync')):
        raise ProductionRefused('automatic receipt cannot claim human acceptance')
    if run_path(run,data['production_report'])!=run/'production/composition.json':raise ProductionRefused('receipt report differs')
    json_bytes(data)


def validate_delivery_transaction(data, run, *, frozen=None):
    object_fields(data,('schema_version','execution_mode','run_id','created_at','updated_at','transaction_id','status','lock_record',
        'source_records','output_paths','operations','receipt'),'delivery transaction')
    _header(data,run);timestamp(data['updated_at']);token(data['transaction_id'])
    if data['status'] not in ('publishing','completed'):raise ProductionRefused('invalid transaction status')
    targets=validate_targets(data['output_paths'],run,frozen=frozen)
    lock=data['lock_record'];object_fields(lock,('owner','intent_path','lock_path'),'transaction lock')
    validate_owner(lock['owner'],run,targets['movie'])
    expected_lock=targets['movie'].with_name('.'+targets['movie'].stem+'.make-video.lock')
    if output_path(lock['lock_path'])!=expected_lock:raise ProductionRefused('lock path differs')
    intent_path=run_path(run,lock['intent_path'])
    if intent_path!=run/f'logs/production/delivery/locks/{lock["owner"]["token"]}.json':raise ProductionRefused('lock intent path differs')
    intent=read_json(intent_path);object_fields(intent,('owner','lock_path','created_at'),'output lock intent');timestamp(intent['created_at'])
    if intent['owner']!=lock['owner'] or intent['lock_path']!=lock['lock_path']:raise ProductionRefused('lock intent identity differs')
    object_fields(data['source_records'],SOURCES,'delivery sources')
    for value in data['source_records'].values():
        stamp=ArtifactStamp.from_dict(value);run_path(run,stamp.path);stamp.verify()
    if data['source_records']!=sources_for(run):raise ProductionRefused('original delivery sources differ')
    object_fields(data['operations'],ROLES,'delivery operations')
    used=set();prior=True
    for role in ROLES:
        op=data['operations'][role]
        object_fields(op,('status','temp_path','file_id','temp_stamp','output_stamp','archives'),'delivery operation')
        if op['status'] not in ('pending','created','copied','published'):raise ProductionRefused('invalid operation status')
        if not prior and (role=='receipt' and op['status']!='pending' or op['status']=='published'):
            raise ProductionRefused('delivery operation order differs')
        prior=prior and op['status']=='published'
        temp=output_path(op['temp_path'])
        pattern=rf'\.{re.escape(targets["movie"].stem)}\.{re.escape(run.name)}\.{data["transaction_id"]}\.{role}\.[0-9a-f]{{32}}\.tmp'
        if temp.parent!=targets[role].parent or not re.fullmatch(pattern,temp.name) or temp in used:
            raise ProductionRefused('transaction temporary path differs')
        used.add(temp)
        if op['status']=='pending':
            if any(op[k] is not None for k in ('file_id','temp_stamp','output_stamp')):raise ProductionRefused('pending operation has completed identity')
        else:
            validate_file_id(op['file_id'])
            if op['status']=='created' and (op['temp_stamp'] is not None or op['output_stamp'] is not None):raise ProductionRefused('created cursor ahead')
            if op['status'] in ('copied','published'):
                s=ArtifactStamp.from_dict(op['temp_stamp'])
                if output_path(s.path)!=temp:raise ProductionRefused('temporary stamp role differs')
            if op['status']=='copied' and op['output_stamp'] is not None:raise ProductionRefused('copied cursor ahead')
            if op['status']=='published':
                s=ArtifactStamp.from_dict(op['output_stamp'])
                if output_path(s.path)!=targets[role] or (s.bytes,s.mtime_ns)!=(op['temp_stamp']['bytes'],op['temp_stamp']['mtime_ns']):raise ProductionRefused('published stamp differs')
                s.verify()
                if file_identity(targets[role])!=op['file_id']:raise ProductionRefused('published file identity changed')
        if not isinstance(op['archives'],list):raise ProductionRefused('archives must be list')
        for archive in op['archives']:
            object_fields(archive,('path','file_id','stamp'),'archive');validate_file_id(archive['file_id'])
            path=output_path(archive['path']);stamp=ArtifactStamp.from_dict(archive['stamp'])
            if path.parent!=temp.parent or not path.name.startswith('.'+targets['movie'].stem+'.'+run.name+'.'+data['transaction_id']+'.'+role+'.') or path.suffix!='.archive' or path in used or stamp.path!=str(path):raise ProductionRefused('archive path differs')
            used.add(path);stamp.verify()
            if file_identity(path)!=archive['file_id']:raise ProductionRefused('archive identity changed')
    if data['receipt'] is not None:
        if any(data['operations'][r]['status']!='published' for r in ('movie','subtitle')):raise ProductionRefused('receipt cursor ahead of media')
        validate_delivery_receipt(data['receipt'],run,frozen=frozen)
        if any(data['receipt'][r]!=data['operations'][r]['output_stamp'] for r in ('movie','subtitle')):raise ProductionRefused('receipt media stamps differ')
    if data['operations']['receipt']['status']!='pending' and data['receipt'] is None:raise ProductionRefused('receipt intent missing')
    if data['status']=='completed' and (not prior or data['receipt'] is None):raise ProductionRefused('completed transaction missing delivery')
    json_bytes(data)


def validate_delivery_checkpoint(data, run):
    if data['unit_id']!='final' or data['request'] is not None:raise ProductionRefused('delivery final has no model request')
    payload=data['payload'];object_fields(payload,('transaction','receipt','receipt_stamp'),'delivery checkpoint')
    transaction=ArtifactStamp.from_dict(payload['transaction']);transaction.verify()
    if run_path(run,transaction.path)!=run/'production/delivery.json':raise ProductionRefused('delivery transaction path differs')
    tx=read_json(Path(transaction.path));validate_delivery_transaction(tx,run)
    if tx['status']!='completed' or tx['receipt']!=payload['receipt']:raise ProductionRefused('delivery checkpoint receipt differs')
    receipt_stamp=ArtifactStamp.from_dict(payload['receipt_stamp']);receipt_stamp.verify()
    if output_path(receipt_stamp.path)!=output_path(tx['output_paths']['receipt']) or read_json(Path(receipt_stamp.path))!=payload['receipt']:
        raise ProductionRefused('official receipt differs')
    expected=dict(transaction=payload['transaction'],composition=tx['source_records']['composition'],
        technical_checks=tx['source_records']['technical_checks'],receipt_record=ArtifactStamp.read(run/'logs/production/delivery/receipt.json').to_dict())
    if data['outputs']!=expected or read_json(Path(expected['receipt_record']['path']))!=payload['receipt']:
        raise ProductionRefused('delivery checkpoint outputs differ')
