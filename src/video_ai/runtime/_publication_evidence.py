"""Publication receipts, canonical evidence index and exact report reconstruction."""
from datetime import datetime
from pathlib import Path, PurePosixPath
import re

from ..config import read_json
from ..planning.start_images import keys
from .manifest import hash_file,thaw,_timestamp,_identity
from .timeline_checks import _local,_again
from .paths import PathPolicy
from ._publication_review import equal_identity,fresh

FIELDS='schema_version run_id created_at status passed published staging_only candidate_validation_identity composition_identity input_identities final_review_identity acceptance_identity review_collection_identities accepted_candidate_identity accepted_subtitle_identity output_video_identity output_subtitle_identity output_marker_identity validation provenance request_evidence'
MARKER_FIELDS='schema_version run_id created_at candidate_validation_identity final_review_identity acceptance_identity video_identity subtitle_identity'
COPY_FIELDS='schema_version run_id created_at source_identity target_identity copied_bytes payload_sha256'
GATE_FIELDS='schema_version run_id created_at candidate_validation_identity final_review_identity acceptance_identity review_collection_identities validation'


def same(a,b):
    if isinstance(a,dict) and isinstance(b,dict):
        if set(a)==set(b)==set('path bytes mtime_ns sha256 verified_at'.split()):return equal_identity(a,b)
        if set(a)==set(b)==set('path bytes category sha256 verified_at'.split()):
            _identity(a,artifact=True);_identity(b,artifact=True)
            if any(v is None for v in a.values()) or any(v is None for v in b.values()):raise ValueError('complete artifact required')
            return all(a[k]==b[k] for k in ('path','bytes','sha256','category'))
        return set(a)==set(b) and all(same(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    return type(a) is type(b) and a==b


def header(data,fields,run):
    keys(data,fields,'publication evidence')
    if type(data['schema_version']) is not int or data['schema_version']!=1 or data['run_id']!=run.name:raise ValueError('publication schema/run mismatch')
    _timestamp(data['created_at'])
    if datetime.fromisoformat(data['created_at'])>datetime.now().astimezone():raise ValueError('future publication timestamp')


def output_path(path):
    original=Path(path).absolute();actual=PathPolicy().validate_write(original,'output')
    if original!=actual:raise ValueError('redirected/noncanonical output path')
    return actual


def artifact(identity,category):
    record=thaw(identity);record.pop('mtime_ns');record['category']=category;return record


def index(run,paths):
    return {p.relative_to(run).as_posix():thaw(hash_file(_local(run,p))) for p in sorted(set(paths))}


def validate(run,report,gate):
    header(report,FIELDS,run)
    if report['status']!='completed' or report['passed'] is not True or report['published'] is not True or report['staging_only'] is not False:raise ValueError('publication completed flags required')
    candidate=gate['candidate']
    expected=dict(candidate_validation_identity=gate['candidate_identity'],composition_identity=candidate['composition_identity'],input_identities=candidate['input_identities'],final_review_identity=gate['review_identity'],acceptance_identity=gate['acceptance_identity'],review_collection_identities=gate['collection'],accepted_candidate_identity=candidate['candidate_identity'],accepted_subtitle_identity=candidate['subtitle_identity'],validation=gate['validation'],provenance=candidate['provenance'])
    for name,want in expected.items():
        if not same(report[name],want):raise ValueError('publication reconstructed field differs: '+name)
    ids={}
    video=output_path(report['output_video_identity']['path']);subtitle=output_path(report['output_subtitle_identity']['path']);marker=output_path(report['output_marker_identity']['path'])
    if video.suffix.lower()!='.mp4' or subtitle!=video.with_suffix('.srt') or marker!=video.with_suffix('.publication.json'):raise ValueError('publication output mapping differs')
    for name,path in [('output_video_identity',video),('output_subtitle_identity',subtitle),('output_marker_identity',marker)]:ids[name]=fresh(report[name],expected=path)
    for target,source in [('output_video_identity','accepted_candidate_identity'),('output_subtitle_identity','accepted_subtitle_identity')]:
        if any(report[target][k]!=report[source][k] for k in ('bytes','sha256')):raise ValueError('published bytes differ from accepted source')
        ids[source]=fresh(report[source],run=run)
    saved=read_json(marker);header(saved,MARKER_FIELDS,run)
    wanted=dict(schema_version=1,run_id=run.name,created_at=report['created_at'],candidate_validation_identity=gate['candidate_identity'],final_review_identity=gate['review_identity'],acceptance_identity=gate['acceptance_identity'],video_identity=report['output_video_identity'],subtitle_identity=report['output_subtitle_identity'])
    if not same(saved,wanted):raise ValueError('publication marker differs')
    evidence=report['request_evidence']
    if not isinstance(evidence,dict):raise ValueError('publication evidence index required')
    copies=[];gates=[];author=set(gate['collection'])|{Path(gate['acceptance_identity']['path']).relative_to(run).as_posix()}
    for name,record in evidence.items():
        if not isinstance(name,str) or PurePosixPath(name).as_posix()!=name or '..' in PurePosixPath(name).parts or PurePosixPath(name).is_absolute() or '\\' in name:raise ValueError('noncanonical publication evidence key')
        path=_local(run,run/name);ids[name]=fresh(record,run=run,expected=path)
        if name in author:continue
        if path.parent!=run/'logs/publication':raise ValueError('extra publication evidence')
        data=read_json(path)
        if re.fullmatch(r'copy-[0-9a-f]{32}\.json',path.name):
            header(data,COPY_FIELDS,run);copies.append(data)
        elif re.fullmatch(r'gate-[0-9a-f]{32}\.json',path.name):
            header(data,GATE_FIELDS,run);gates.append(data)
        else:raise ValueError('extra publication evidence')
    if set(evidence)!=author|{k for k in evidence if k.startswith('logs/publication/')} or len(copies)!=2 or len(gates)!=1:raise ValueError('missing/extra publication author or copy/gate evidence')
    remaining=list(copies)
    for source,target in [('accepted_candidate_identity','output_video_identity'),('accepted_subtitle_identity','output_subtitle_identity')]:
        matched=[c for c in remaining if same(c['source_identity'],report[source]) and same(c['target_identity'],report[target])]
        if len(matched)!=1:raise ValueError('copy evidence source/target mismatch')
        copy=matched[0];remaining.remove(copy)
        if type(copy['copied_bytes']) is not int or copy['copied_bytes']!=report[source]['bytes'] or copy['payload_sha256']!=report[source]['sha256']:raise ValueError('copy byte/hash evidence differs')
    recorded=gates[0]
    for name,want in dict(candidate_validation_identity=gate['candidate_identity'],final_review_identity=gate['review_identity'],acceptance_identity=gate['acceptance_identity'],review_collection_identities=gate['collection'],validation=gate['validation']).items():
        if not same(recorded[name],want):raise ValueError('gate evidence differs: '+name)
    _again(ids);_again(gate['identities'])
    return ids
