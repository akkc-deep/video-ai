"""Durable, origin-preserving imports. Copies never become new submissions.

Every read rechecks original leaves and the protected parent manifest prefix.
The receipt is an index of consumed evidence, not a replacement for stage consumers.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import MappingProxyType
from uuid import uuid4

from ..config import read_json
from .manifest import ManifestStore, FileIdentity, hash_file, thaw, now, _identity, _timestamp, STAGES
from .timeline_checks import _run_path, _local, _again
from .paths import _validate_spelling
from .verification import verified_read

FIELDS = 'schema_version run_id parent_run_id created_at reason parent_snapshot_identity changes_identity source_identities copies stages units review_inheritance'
ROW_FIELDS = 'id source_record imported_record signature origin'
_CONSUMED = object()


def immutable(value):
    if isinstance(value, Mapping):return MappingProxyType({k:immutable(v) for k,v in value.items()})
    if isinstance(value,(list,tuple)):return tuple(immutable(v) for v in value)
    return value


def keys(value, expected, label):
    if not isinstance(value, Mapping) or set(value)!=set(expected.split()):raise ValueError(label+' fields differ')


def fresh(identity):
    record=thaw(identity);_identity(record)
    if any(v is None for v in record.values()):raise ValueError('complete import identity required')
    if datetime.fromisoformat(record['verified_at'])>datetime.now().astimezone():raise ValueError('future import identity timestamp')
    path=Path(_validate_spelling(record['path']))
    if not path.is_absolute() or path.resolve(strict=True)!=path:raise ValueError('noncanonical import identity path')
    current=hash_file(path)
    if any(getattr(current,k)!=record[k] for k in ('path','bytes','mtime_ns','sha256')):raise ValueError('import identity drift: '+str(path))
    return current


def same_identity(left,right):
    a,b=thaw(left),thaw(right)
    return all(a[k]==b[k] for k in ('path','bytes','mtime_ns','sha256'))


def write_exclusive(run,path,data):
    path=_local(run,path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='\n') as output:
        json.dump(thaw(data),output,ensure_ascii=False,allow_nan=False,indent=2);output.flush();os.fsync(output.fileno())
    return hash_file(path)


def copy_exclusive(run,original,target):
    before=fresh(original);source=Path(before.path);target=_local(run,Path(target))
    if target==source:raise ValueError('import requires independent copy')
    target.parent.mkdir(parents=True,exist_ok=True)
    with source.open('rb') as input_file,target.open('xb') as output:
        shutil.copyfileobj(input_file,output);output.flush();os.fsync(output.fileno())
    after=hash_file(_local(run,target));fresh(original)
    if (after.bytes,after.sha256)!=(before.bytes,before.sha256):raise ValueError('import copy bytes differ')
    return after


def merge_sources(destination,source):
    aliases={p.casefold():p for p in destination}
    for path,identity in source.items():
        current=fresh(identity)
        if path!=current.path:raise ValueError('source leaf path differs')
        alias=aliases.get(path.casefold())
        if alias is not None and (alias!=path or not same_identity(destination[alias],identity)):raise ValueError('conflicting import source identity')
        destination[path]=thaw(identity);aliases[path.casefold()]=path


def protected_parent(parent,snapshot,receipt):
    live=ManifestStore.open(parent).snapshot()
    for name in ('schema_version','run_id','created_at','config_snapshot','voice_snapshot','inputs','models'):
        if live[name]!=snapshot[name]:raise ValueError('parent protected '+name+' changed')
    if live['events'][:len(snapshot['events'])]!=snapshot['events']:raise ValueError('parent protected events prefix changed')
    for stage,record in snapshot['stages'].items():
        if record['status'] not in ('pending','running') and live['stages'][stage]!=record:raise ValueError('parent terminal stage changed')
    for kind,units in snapshot['units'].items():
        for uid,record in units.items():
            if record['status'] not in ('pending','running') and live['units'][kind].get(uid)!=record:raise ValueError('parent terminal unit changed')
    for row in receipt['units']:
        source_stage=row['imported_record'].get('stage')
        kind={'speech':'speech','start_images':'image','source_clips':'shot','upscale':'frame'}.get(source_stage)
        if row['origin']=='completed_saved_submission':kind=row['imported_record'].get('parent_kind',row['imported_record'].get('source_kind',kind))
        if kind:
            uid=row['imported_record'].get('parent_unit_id',row['imported_record']['source_unit_id']) if row['origin']=='completed_saved_submission' else row['id'];record=snapshot['units'][kind].get(uid)
            if record!=thaw(row['source_record']) or live['units'][kind].get(uid)!=record:raise ValueError('parent protected unit changed: '+uid)
    for row in receipt['stages']:
        stage=row['id']
        if stage not in STAGES or snapshot['stages'][stage]!=row['source_record'] or live['stages'][stage]!=row['source_record']:raise ValueError('parent protected source stage changed')
    for name,record in snapshot['workflows'].items():
        if live['workflows'].get(name)!=record:raise ValueError('parent protected workflow changed')


def create_pipeline_import(config, *, run_dir, parent_run_dir, reason, source_identities,
        copies, stages=(), units=(), review_inheritance=(), changes_identity=None):
    """Freeze a consumed parent into an existing fresh child; never alter the parent.

    ``copies`` has original_identity/copy_path/role/stage/unit_id fields. Stage
    callers supply explicitly rebuilt records, not rewritten parent JSON files.
    """
    run,parent=_run_path(run_dir),_run_path(parent_run_dir)
    if run==parent:raise ValueError('import cycle/self parent')
    if not isinstance(reason,str) or not reason.strip():raise ValueError('import reason required')
    store=ManifestStore.open(run);snapshot=ManifestStore.open(parent).snapshot()
    if 'pipeline_import' in store.snapshot()['workflows']:raise ValueError('child already has import receipt')
    sources={};merge_sources(sources,source_identities)
    if 'pipeline_import' in snapshot['workflows']:
        old=load_pipeline_import(parent)
        merge_sources(sources,old['source_identities'])
        merge_sources(sources,import_source_identities(parent))
    token=uuid4().hex
    parent_file=parent/'manifest.json';before=hash_file(parent_file)
    parent_copy=copy_exclusive(run,before,run/'logs/pipeline'/('parent-manifest-'+token+'.json'))
    if read_json(Path(parent_copy.path))!=snapshot:raise ValueError('parent manifest changed during snapshot')
    if changes_identity is not None:fresh(changes_identity)
    copied=[]
    for row in copies:
        keys(row,'original_identity copy_path role stage unit_id','copy request')
        original=thaw(row['original_identity']);merge_sources(sources,{original['path']:original})
        identity=copy_exclusive(run,original,row['copy_path'])
        copied.append(dict(original_identity=original,copy_identity=thaw(identity),role=row['role'],stage=row['stage'],unit_id=row['unit_id']))
    report=dict(schema_version=1,run_id=run.name,parent_run_id=parent.name,created_at=now(),reason=reason,
        parent_snapshot_identity=thaw(parent_copy),changes_identity=thaw(changes_identity),source_identities=sources,
        copies=copied,stages=thaw(stages),units=thaw(units),review_inheritance=thaw(review_inheritance))
    protected_parent(parent,snapshot,report);merge_sources({},sources)
    identity=write_exclusive(run,run/'logs/pipeline'/('import-'+token+'.json'),report)
    # Validate before exposing the receipt through the manifest.
    load_pipeline_import(run,identity=identity)
    def commit(data):
        if 'pipeline_import' in data['workflows']:raise ValueError('concurrent import receipt')
        data['workflows']['pipeline_import']=thaw(identity)
    store.update(commit)
    return identity


@verified_read
def load_pipeline_import(run_dir, *, identity=None, _ancestors=()):
    run=_run_path(run_dir)
    if run in _ancestors:raise ValueError('import origin cycle')
    snapshot=ManifestStore.open(run).snapshot()
    identity=identity if identity is not None else snapshot['workflows'].get('pipeline_import')
    if identity is None:raise ValueError('pipeline import receipt missing')
    actual=fresh(identity);path=Path(actual.path)
    if path.parent!=run/'logs/pipeline' or not path.name.startswith('import-') or path.suffix!='.json':raise ValueError('canonical import receipt required')
    report=read_json(path);keys(report,FIELDS,'import receipt')
    if type(report['schema_version']) is not int or report['schema_version']!=1 or report['run_id']!=run.name:raise ValueError('import schema/run differs')
    _timestamp(report['created_at'])
    if not isinstance(report['reason'],str) or not report['reason'].strip():raise ValueError('import reason missing')
    parent=_run_path(run.parent/report['parent_run_id'])
    if parent in (*_ancestors,run):raise ValueError('import origin cycle')
    saved=fresh(report['parent_snapshot_identity']);saved_path=Path(saved.path)
    if saved_path.parent!=run/'logs/pipeline' or not saved_path.name.startswith('parent-manifest-'):raise ValueError('canonical parent snapshot required')
    original=read_json(saved_path)
    if original['run_id']!=parent.name:raise ValueError('parent snapshot run differs')
    sources={};merge_sources(sources,report['source_identities'])
    parent_import=original['workflows'].get('pipeline_import')
    if parent_import is not None:
        nested=load_pipeline_import(parent,identity=parent_import,_ancestors=(*_ancestors,run))
        for name,value in nested['source_identities'].items():
            if name not in sources or not same_identity(value,sources[name]):raise ValueError('nested origin leaves not flattened')
    seen=set()
    for row in report['copies']:
        keys(row,'original_identity copy_identity role stage unit_id','import copy')
        a,b=fresh(row['original_identity']),fresh(row['copy_identity'])
        target=_local(run,Path(b.path))
        if target in seen or a.path==b.path or (a.bytes,a.sha256)!=(b.bytes,b.sha256):raise ValueError('duplicate/different import copy')
        if a.path not in sources or not same_identity(sources[a.path],a):raise ValueError('copy source absent from leaf index')
        if row['stage'] not in STAGES or not isinstance(row['role'],str) or not row['role']:raise ValueError('copy stage/role differs')
        seen.add(target)
    for name in ('stages','units'):
        if not isinstance(report[name],list):raise ValueError('import record list required')
        ids=set()
        for row in report[name]:
            keys(row,ROW_FIELDS,'import '+name)
            row_key=(row['imported_record'].get('stage'),row['id']) if name=='units' else row['id']
            if row_key in ids or row['origin'] not in ('reused_verified','completed_saved_submission'):raise ValueError('duplicate import unit/origin')
            if not isinstance(row['signature'],str) or len(row['signature'])!=64 or any(c not in '0123456789abcdef' for c in row['signature']):raise ValueError('import signature required')
            ids.add(row_key)
    for row in report['review_inheritance']:
        keys(row,'role source_identity applicable_signature reviewer reviewed_at','review inheritance')
        fresh(row['source_identity']);_timestamp(row['reviewed_at'])
    if report['changes_identity'] is not None:fresh(report['changes_identity'])
    protected_parent(parent,original,report);fresh(identity)
    return immutable(report)


def import_source_identities(run_dir):
    """Fresh flattened leaves for composition, candidate and publication closure."""
    run=_run_path(run_dir);identity=ManifestStore.open(run).snapshot()['workflows'].get('pipeline_import')
    if identity is None:return {}
    receipt=load_pipeline_import(run,identity=identity);result={}
    merge_sources(result,receipt['source_identities'])
    for value in (identity,receipt['parent_snapshot_identity'],receipt['changes_identity']):
        if value is not None:merge_sources(result,{thaw(value)['path']:value})
    for row in receipt['copies']:merge_sources(result,{row['copy_identity']['path']:row['copy_identity']})
    return {path:fresh(value) for path,value in result.items()}


@dataclass(frozen=True)
class ReuseContext:
    stage: str
    import_identity: FileIdentity
    verified_units: Mapping
    remaining_units: tuple
    current_input_identities: Mapping
    _seal: object = field(default=None,repr=False,compare=False)

    def __post_init__(self):
        object.__setattr__(self,'verified_units',immutable(self.verified_units))
        object.__setattr__(self,'remaining_units',tuple(self.remaining_units))
        object.__setattr__(self,'current_input_identities',immutable(self.current_input_identities))


def make_reuse_context(run_dir, *, stage, unit_ids, current_input_identities):
    run=_run_path(run_dir);report=load_pipeline_import(run)
    if stage not in STAGES or len(set(unit_ids))!=len(unit_ids):raise ValueError('reuse stage/unit order differs')
    registered=ManifestStore.open(run).snapshot()['workflows']['pipeline_import'];fresh(registered)
    identity=FileIdentity(**registered)
    verified={}
    for row in report['units']:
        imported=row['imported_record']
        if imported.get('stage')!=stage:continue
        uid=row['id']
        if uid not in unit_ids:raise ValueError('import unit outside current plan')
        verified[uid]=dict(origin_run_id=imported.get('origin_run_id',report['parent_run_id']),
            source_report_identity=imported['source_report_identity'],source_unit_id=imported.get('source_unit_id',uid),
            signature=row['signature'],import_identity=thaw(identity))
    parent_snapshot=ManifestStore.open(run.parent/report['parent_run_id']).snapshot()
    kind={'start_images':'image','source_clips':'shot_attempt','upscale':'frame','speech':'speech'}.get(stage)
    for uid,record in parent_snapshot['units'].get(kind,{}).items():
        submission=record['submission'];current_uid=uid.split(':attempt_',1)[0] if stage=='source_clips' else uid
        if submission is not None and submission['state'] in ('intent','accepted','ambiguous') and current_uid not in verified:
            raise ValueError('unknown original submission cannot become remaining unit')
    if verified:
        from ..config import load_config
        snapshot=ManifestStore.open(run).snapshot();config=load_config(Path(snapshot['config_snapshot']['path']))
        if stage=='source_clips':
            from ._source_clip_inputs import inputs
            context=inputs(config,run);reused_source_clips(run,verified,context)
        elif stage=='upscale':
            from ._upscale_inputs import inputs
            context=inputs(config,run);reused_upscale_frames(config,run,verified,context)
        elif stage=='start_images':
            from . import start_image_checks as owner
            board,identities=owner._input_files(config,run)
            owner._verified_reused_images(config,run,board,snapshot,identity,verified)
        elif stage=='speech':
            from .speech_checks import load_committed_speech,_load_partial_speech
            parent=run.parent/report['parent_run_id'];original=ManifestStore.open(parent).snapshot()
            if original['stages']['speech']['status']=='completed':load_committed_speech(parent)
            else:_load_partial_speech(parent)
        else:raise ValueError('stage has no completed import unit consumer')
    _again(current_input_identities)
    return ReuseContext(stage,identity,verified,tuple(uid for uid in unit_ids if uid not in verified),
        thaw(current_input_identities),_CONSUMED)


def imported_unit_map(run,stage):
    snapshot=ManifestStore.open(run).snapshot();identity=snapshot['workflows'].get('pipeline_import')
    if identity is None:return {},{}
    receipt=load_pipeline_import(run);rows={row['id']:row for row in receipt['units'] if row['imported_record'].get('stage')==stage}
    values={uid:dict(origin_run_id=row['imported_record']['origin_run_id'],source_report_identity=thaw(row['imported_record']['source_report_identity']),
        source_unit_id=row['imported_record']['source_unit_id'],signature=row['signature'],import_identity=thaw(identity)) for uid,row in rows.items()}
    return values,rows


def retained_unit_origin(parent,stage,uid,old):
    if old is None:return None
    _,rows=imported_unit_map(parent,stage);row=rows.get(uid)
    if row is None:raise ValueError('reused origin is absent from parent import')
    kind={'speech':'speech','start_images':'image','source_clips':'shot','upscale':'frame'}.get(stage)
    origin=thaw(row['imported_record'])
    if row['origin']=='completed_saved_submission':origin.update(parent_kind=kind,parent_unit_id=uid)
    return dict(origin_record=origin,origin_kind=row['origin'])


def verify_reuse_context(run_dir, reuse_context, *, stage, unit_ids, current_input_identities):
    if not isinstance(reuse_context,ReuseContext) or reuse_context._seal is not _CONSUMED:raise ValueError('reuse context must originate in import consumer')
    current=make_reuse_context(run_dir,stage=stage,unit_ids=unit_ids,current_input_identities=current_input_identities)
    if reuse_context.stage!=current.stage or not same_identity(reuse_context.import_identity,current.import_identity) or thaw(reuse_context.verified_units)!=thaw(current.verified_units) or reuse_context.remaining_units!=current.remaining_units:
        raise ValueError('reuse context changed')
    a,b=reuse_context.current_input_identities,current.current_input_identities
    if set(a)!=set(b) or any(not same_identity(a[k],b[k]) for k in a):raise ValueError('reuse context input identity differs')
    return current


STAGE_FILES={'speech':'segments.json','storyboard':'storyboard.json','start_images':'images.json','source_clips':'source-clips.json','upscale':'upscaled-clips.json'}
STAGE_WORKFLOWS={'speech':'speech_report','storyboard':'storyboard_report','start_images':'images_report','source_clips':'source_clips_report','upscale':'upscale_report'}
_SPEECH_RUNTIME_INPUTS=frozenset(('tts_runtime','tts_installed_data','tts_runtime_data','tts_serialization','tts_runtime_startup'))


def origin_run(run,report):
    """Return a freshly bound native origin for a fully reused stage report."""
    identity=report.get('import_identity')
    if identity is None:return run
    load_pipeline_import(run,identity=identity)
    units=report.get('reused_units')
    if not units:raise ValueError('import origin units required')
    origins={value['origin_run_id'] for value in units.values()}
    if len(origins)!=1:raise ValueError('stage-wide evidence requires one explicit origin')
    return _run_path(run.parent/next(iter(origins)))


def stage_draft_path(run,stage,report):
    filename=STAGE_FILES[stage].replace('.json','-draft.json')
    if stage=='storyboard' and 'storyboard_revision' in ManifestStore.open(run).snapshot()['workflows']:return run/filename
    return origin_run(run,report)/filename


def fresh_origin_review(run,report,identity):
    if report.get('import_identity') is None or Path(identity['path']).is_relative_to(run):
        from ._source_clip_inputs import fresh as local_fresh
        return local_fresh(identity,run=run)
    sources=import_source_identities(run)
    if identity['path'] not in sources or not same_identity(identity,sources[identity['path']]):raise ValueError('review outside consumed origin closure')
    return fresh(identity)


def stage_consumer(stage):
    if stage=='speech':
        from .speech_checks import load_committed_speech
        return lambda run:load_committed_speech(run)['report']
    if stage=='storyboard':
        from .storyboard_checks import load_committed_storyboard
        return load_committed_storyboard
    if stage=='start_images':
        from .start_image_checks import load_committed_start_images
        return load_committed_start_images
    if stage=='source_clips':
        from .source_clip_checks import load_committed_source_clips
        return load_committed_source_clips
    if stage=='upscale':
        from .upscale_checks import load_committed_upscaled_clips
        return load_committed_upscaled_clips
    raise ValueError('stage has no explicit import serializer: '+stage)


def collect_report_sources(report,run):
    """Collect identity-bound JSON leaves; never interpret arbitrary path strings."""
    from ._candidate_evidence import capture_bound_identities
    values=capture_bound_identities(report,run=run)
    return {identity.path:thaw(identity) for identity in values.values()}


def content_signature(value):
    def projection(node):
        if isinstance(node,Mapping):
            if set(node)=={'path','bytes','mtime_ns','sha256','verified_at'}:return {k:node[k] for k in ('bytes','sha256')}
            return {k:projection(v) for k,v in node.items()}
        if isinstance(node,(list,tuple)):return [projection(v) for v in node]
        return node
    return hashlib.sha256(json.dumps(projection(value),sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def stage_unit_ids(stage,report):
    if stage=='speech':return tuple(r['unit_id'] for r in [report.get('reference_replay'),*report['spans']] if r is not None and r.get('kind')!='skip')
    if stage=='storyboard':return tuple(row['shot_id'] for row in report['shots'])
    if stage=='start_images':return tuple(row['shot_id'] for row in report['images'])
    if stage=='source_clips':return tuple(row['shot_id'] for row in report['clips'])
    if stage=='upscale':return tuple(f"{clip['shot_id']}:frame_{frame['frame_index']:06d}" for clip in report['clips'] for frame in clip['frames'])
    raise ValueError('unsupported import unit stage')


def stage_media(stage,report):
    """Explicit media copy inventory; raw production evidence stays at origin."""
    result=[]
    if stage=='start_images':
        result.extend((r['shot_id'],'start_image',r['image_identity']) for r in report['images'])
    elif stage=='source_clips':
        for clip in report['clips']:
            for field in ('generated_identity','source_identity'):result.append((clip['shot_id'],field,clip[field]))
    elif stage=='upscale':
        for clip in report['clips']:
            result.append((clip['shot_id'],'upscaled_clip',clip['upscaled_identity']))
            for frame in clip['frames']:
                uid=f"{clip['shot_id']}:frame_{frame['frame_index']:06d}"
                for field in ('input_identity','upscaled_frame_identity'):result.append((uid,field,frame[field]))
    return result


def serialize_stage_import(stage,report, *, run,import_identity,receipt):
    """Stage-specific field serializers. Prompts, HTTP, argv and origins stay intact."""
    result=thaw(report)
    for key in ('import_identity','reused_units'):result.pop(key,None)
    result.update(schema_version=3 if stage=='upscale' else 2,run_id=run.name,import_identity=thaw(import_identity))
    copied={r['original_identity']['path']:thaw(r['copy_identity']) for r in receipt['copies']}
    for uid,role,identity in stage_media(stage,report):
        if identity['path'] not in copied:raise ValueError('required imported media copy missing: '+role+'/'+uid)
    def copy_id(identity):return copied.get(identity['path'],thaw(identity)) if identity is not None else None
    # Only documented artifact association fields are rebound. Production
    # graph, author review, model parameters and evidence are never rewritten.
    if stage=='storyboard':
        for name in ('timeline_identity','script_identity'):result[name]=copy_id(result[name])
    elif stage=='start_images':
        result['storyboard_identity']=copy_id(result['storyboard_identity'])
        for row in result['images']:row['image_identity']=copy_id(row['image_identity'])
        for row in result['references']:row['identity']=copy_id(row['identity'])
        for row in result['requirement_images']:row['image_identity']=copy_id(row['image_identity'])
    elif stage=='source_clips':
        for clip in result['clips']:
            for key in ('start_image_identity','generated_identity','source_identity'):clip[key]=copy_id(clip[key])
        for row in result['frame_mappings']:
            for key in ('generated_identity','source_identity'):row[key]=copy_id(row[key])
        for row in result['requirement_clips']:row['actual_artifact']=copy_id(row['actual_artifact'])
    elif stage=='upscale':
        for clip in result['clips']:
            for key in ('source_identity','upscaled_identity'):clip[key]=copy_id(clip[key])
            # Frame records remain their exact original durable production
            # checkpoints; their independent child copies live in import.
        for row in result['frame_mappings']:
            for key in ('source_identity','generated_identity','upscaled_identity'):
                if key in row:row[key]=copy_id(row[key])
        for row in result['requirement_clips']:
            for key in ('actual_artifact','source_actual_artifact'):row[key]=copy_id(row[key])
    elif stage!='speech':raise ValueError('explicit stage serializer required')
    units={r['id']:r for r in receipt['units'] if r['imported_record'].get('stage')==stage}
    result['reused_units']={}
    for uid in stage_unit_ids(stage,report):
        row=units.get(uid)
        if row is None:raise ValueError('full imported stage missing verified unit')
        origin=row['imported_record']
        result['reused_units'][uid]=dict(origin_run_id=origin['origin_run_id'],source_report_identity=thaw(origin['source_report_identity']),
            source_unit_id=origin['source_unit_id'],signature=row['signature'],import_identity=thaw(import_identity))
    if stage=='speech':
        from .speech_checks import serialize_imported_speech
        from ..config import load_config
        config=load_config(Path(ManifestStore.open(run).snapshot()['config_snapshot']['path']))
        return serialize_imported_speech(config,run,source_report=report,import_identity=import_identity,reused_units=result['reused_units'],copies=receipt['copies'])
    return result


@verified_read
def load_imported_stage(run_dir,stage,report=None):
    run=_run_path(run_dir);store=ManifestStore.open(run);snapshot=store.snapshot()
    report_path=run/STAGE_FILES[stage]
    report=read_json(report_path) if report is None else report
    if type(report.get('schema_version')) is not int or report['schema_version']!=(3 if stage=='upscale' else 2):raise ValueError('import stage version differs')
    identity=report.get('import_identity')
    if identity is None or not report.get('reused_units'):raise ValueError('import version requires bound nonempty origin units')
    registered=snapshot['workflows'].get('pipeline_import')
    if registered is None or not same_identity(registered,identity):raise ValueError('unregistered stage import')
    receipt=load_pipeline_import(run,identity=identity)
    rows=[r for r in receipt['stages'] if r['id']==stage]
    if len(rows)!=1:raise ValueError('import source stage missing')
    source_id=rows[0]['imported_record']['source_report_identity'];fresh(source_id)
    parent=run.parent/receipt['parent_run_id']
    origin=stage_consumer(stage)(parent)
    if not same_identity(hash_file(parent/STAGE_FILES[stage]),source_id):raise ValueError('origin formal report drift')
    expected=serialize_stage_import(stage,origin,run=run,import_identity=identity,receipt=receipt)
    if report!=expected:raise ValueError('imported report differs from fresh explicit origin serialization')
    record=snapshot['stages'][stage]
    if record['status']!='completed' or len(record['artifacts'])!=1 or Path(record['artifacts'][0]['path'])!=report_path:raise ValueError('imported completed stage artifact differs')
    from .timeline_checks import _fresh
    _fresh(record['artifacts'][0],run=run,expected=report_path)
    fresh(snapshot['workflows'][STAGE_WORKFLOWS[stage]])
    kind={'start_images':'image','source_clips':'shot','upscale':'frame'}.get(stage)
    if kind:
        for uid in report['reused_units']:
            unit=snapshot['units'][kind].get(uid)
            if unit is None or unit['status']!='completed' or unit['submission'] is not None:raise ValueError('import unit must not pretend to be new submission')
            for artifact in unit['artifacts']:_fresh(artifact,run=run)
    validate_imported_current_inputs(run,stage,report,parent)
    load_pipeline_import(run,identity=identity)
    if store.snapshot()['stages'][stage]!=record:raise ValueError('import stage changed during consume')
    return report


def validate_imported_current_inputs(run,stage,report,parent):
    """Replay current pure plans in addition to the immutable origin execution."""
    from ..config import load_config
    from .pipeline_inventory import _semantic
    config=load_config(Path(ManifestStore.open(run).snapshot()['config_snapshot']['path']))
    if stage=='storyboard':
        from . import storyboard_checks as owner
        from .timeline_checks import load_committed_timeline
        from ._pipeline_storyboard_revision import _timeline_content
        if owner._media(config)!=report['effective_media']:raise ValueError('imported storyboard current media differs')
        if _timeline_content(load_committed_timeline(run))!=_timeline_content(load_committed_timeline(parent)):
            raise ValueError('imported storyboard current actual timeline differs')
        original=fresh(report['script_identity']);current=hash_file(run/'script.txt')
        if (original.bytes,original.sha256)!=(current.bytes,current.sha256):raise ValueError('imported storyboard current script differs')
    elif stage=='start_images':
        from . import start_image_checks as owner
        board,identities=owner._input_files(config,run)
        images,origin_ids=owner._verified_reused_images(config,run,board,ManifestStore.open(run).snapshot(),report['import_identity'],report['reused_units'])
        if _semantic(report['images'])!=_semantic(list(images.values())):raise ValueError('imported images current plan differs')
        _again(identities);_again(origin_ids)
    elif stage=='source_clips':
        from ._source_clip_inputs import inputs,MODEL_NAMES
        from ..planning.source_clips import frame_mapping,requirement_clips
        context=inputs(config,run);plans=context['plans'];clips=report['clips']
        if [p.shot_id for p in plans]!=[c['shot_id'] for c in clips]:raise ValueError('imported source current coverage differs')
        for plan,clip in zip(plans,clips):
            params=thaw(plan.parameters);params['length']=clip['parameters']['length']
            if params!=clip['parameters'] or thaw(plan.budget)!=clip['budget'] or _semantic(thaw(plan.start_image_identity))!=_semantic(clip['start_image_identity']):
                raise ValueError('imported source current parameters or image differ')
        for name in (*MODEL_NAMES,'workflow','mapping'):
            prior=report['model_identities'][name] if name in MODEL_NAMES else report[name+'_identity']
            if _semantic(thaw(context['identities'][name]))!=_semantic(prior):raise ValueError('imported source current model/workflow differs')
        mappings={p.shot_id:frame_mapping(p,generated_identity=c['generated_identity'],source_identity=c['source_identity'],generated_frames=c['generated_frames'],output_fps=context['board']['effective_media']['fps']) for p,c in zip(plans,clips)}
        required=requirement_clips(context['board'],source_identities={c['shot_id']:c['source_identity'] for c in clips},frame_mappings=mappings,total_samples=context['timeline']['total_samples'])
        if _semantic(list(mappings.values()))!=_semantic(report['frame_mappings']) or _semantic(required)!=_semantic(report['requirement_clips']):
            raise ValueError('imported source current associations differ')
        _again(context['identities'])
    elif stage=='upscale':
        from ._upscale_inputs import inputs
        from ._upscale_evidence import requirements
        from ..planning.upscale import upscale_frame_mapping
        context=inputs(config,run);plans=context['plans'];clips=report['clips']
        if [p.shot_id for p in plans]!=[c['shot_id'] for c in clips]:raise ValueError('imported upscale current coverage differs')
        for plan,clip in zip(plans,clips):
            if thaw(plan.parameters)!=clip['parameters'] or thaw(plan.budget)!=clip['budget'] or _semantic(thaw(plan.source_identity))!=_semantic(clip['source_identity']):
                raise ValueError('imported upscale current source/parameters differ')
        for name in ('model','workflow','mapping'):
            if _semantic(thaw(context['identities'][name]))!=_semantic(report[name+'_identity']):raise ValueError('imported upscale current model/workflow differs')
        mapped=[upscale_frame_mapping(row,upscaled_identity=clip['upscaled_identity']) for row,clip in zip(context['source']['frame_mappings'],clips)]
        if _semantic(mapped)!=_semantic(report['frame_mappings']) or _semantic(requirements(context['source'],clips))!=_semantic(report['requirement_clips']):
            raise ValueError('imported upscale current associations differ')
        _again(context['identities'])


def derive_completed_stages(config, *, parent_run_dir, stages, reason, changes_identity=None, partial_stages=(),selected_units=None,changes=None,child_inputs=None,preflight_report=None,extra_source_identities=None,retry_targets=None):
    kwargs=locals();created=[]
    try:return _derive_completed_stages(**kwargs,_created=created)
    except BaseException as exc:
        if created:
            try:
                from .logging import RunLogger
                from .pipeline_evidence import save_record as diagnostic
                run=created[0];trace=RunLogger(run).exception('pipeline',None,exc)
                diagnostic(run,'diagnostic',dict(schema_version=1,run_id=run.name,operation='derive_import',
                    parent_run_id=Path(parent_run_dir).name,error_type=type(exc).__name__,message=str(exc),traceback_identity=thaw(hash_file(trace)),created_at=now()))
            except BaseException:pass
        raise


def _derive_completed_stages(config, *, parent_run_dir, stages, reason, changes_identity=None, partial_stages=(),selected_units=None,changes=None,child_inputs=None,preflight_report=None,extra_source_identities=None,retry_targets=None,_created):
    """Create a child from fully consumed stages using explicit serializers."""
    from .paths import RuntimePaths,create_run
    from .manifest import create_manifest
    from .timeline_checks import _artifact
    parent=_run_path(parent_run_dir);parent_snapshot=ManifestStore.open(parent).snapshot()
    ordered=tuple(s for s in STAGES if s in stages)
    if len(ordered)!=len(stages) or any(s not in STAGE_FILES for s in ordered):raise ValueError('unsupported complete import stage')
    reports={s:stage_consumer(s)(parent) for s in ordered}
    sources={};copies=[];stage_rows=[];unit_rows=[];targets=set();inherited=[]
    from .pipeline_inventory import derived_workflow_files
    for path in derived_workflow_files(config).values():
        entry=hash_file(path)
        merge_sources(sources,{entry.path:entry})
    if extra_source_identities:
        merge_sources(sources,{thaw(identity)['path']:identity for identity in extra_source_identities.values() if Path(thaw(identity)['path'])!=parent/'manifest.json'})
    run=create_run(RuntimePaths.from_config(config))
    _created.append(run)
    for stage,report in reports.items():
        if stage=='speech':
            from .speech_checks import speech_import_inventory
            inventory=speech_import_inventory(parent,run)
            merge_sources(sources,inventory['source_identities']);copies.extend(inventory['copies'])
            stage_rows.append(inventory['stage']);unit_rows.extend(inventory['units'])
            targets.update(row['copy_path'] for row in inventory['copies'])
            continue
        source_id=hash_file(parent/STAGE_FILES[stage]);merge_sources(sources,collect_report_sources(report,parent));sources[source_id.path]=thaw(source_id)
        if report.get('review_identity') is not None:
            author=read_json(Path(report['review_identity']['path']))
            if author.get('reviewer') and author.get('reviewed_at'):
                inherited.append(dict(role=stage,source_identity=report['review_identity'],applicable_signature=content_signature(report),reviewer=author['reviewer'],reviewed_at=author['reviewed_at']))
        stage_rows.append(dict(id=stage,source_record=parent_snapshot['stages'][stage],imported_record=dict(source_report_identity=thaw(source_id)),signature=content_signature(report),origin='reused_verified'))
        for uid in stage_unit_ids(stage,report):
            kind={'start_images':'image','source_clips':'shot','upscale':'frame'}.get(stage)
            source_record=parent_snapshot['units'][kind][uid] if kind else next(s for s in report['shots'] if s['shot_id']==uid)
            old=report.get('reused_units',{}).get(uid)
            retained=retained_unit_origin(parent,stage,uid,old)
            unit_rows.append(dict(id=uid,source_record=source_record,imported_record=retained['origin_record'] if retained else dict(stage=stage,
                origin_run_id=old['origin_run_id'] if old else parent.name,source_report_identity=old['source_report_identity'] if old else thaw(source_id),
                source_unit_id=old['source_unit_id'] if old else uid),signature=old['signature'] if old else content_signature(source_record),origin=retained['origin_kind'] if retained else 'reused_verified'))
        for uid,role,original in stage_media(stage,report):
            path=Path(original['path'])
            # Every output target is explicitly a stage media relative path.
            if role=='upscaled_clip':relative=Path('shots')/uid/'upscaled.mp4'
            elif role=='start_image':relative=Path('shots')/uid/'start.png'
            elif role in ('generated_identity','source_identity'):relative=Path('shots')/uid/('generated.mp4' if role=='generated_identity' else 'source.mp4')
            else:
                shot,frame=uid.split(':');relative=Path('shots')/shot/('frames' if role=='input_identity' else 'upscaled-frames')/(frame+'.png')
            target=run/relative
            if target not in targets:copies.append(dict(original_identity=original,copy_path=target,role=role,stage=stage,unit_id=uid));targets.add(target)
    selected_units=selected_units or {}
    from ..config import load_config
    original_config=load_config(Path(parent_snapshot['config_snapshot']['path'])) if partial_stages else None
    partial=dict(collect_partial_inventory(original_config,parent,parent_snapshot,stages=partial_stages)) if partial_stages else {}
    for stage in partial_stages:
        if stage=='speech':
            from .speech_checks import speech_import_inventory
            inventory=speech_import_inventory(parent,run,partial=True)
            merge_sources(sources,inventory['source_identities']);copies.extend(inventory['copies']);stage_rows.append(inventory['stage']);unit_rows.extend(inventory['units'])
            partial[stage]=dict(verified_units={r['id']:dict(record=r['source_record'],signature=r['signature']) for r in inventory['units']})
            continue
        if stage=='start_images':
            from .start_image_checks import image_import_inventory
            inventory=image_import_inventory(parent,run,unit_ids=selected_units.get(stage))
            merge_sources(sources,inventory['source_identities']);copies.extend(inventory['copies']);stage_rows.append(inventory['stage']);unit_rows.extend(inventory['units'])
            partial[stage]=dict(verified_units={r['id']:dict(record=r['source_record'],signature=r['signature']) for r in inventory['units']})
            continue
        if parent_snapshot['stages'][stage]['status']=='completed':partial[stage]=select_completed_inventory(parent,stage,selected_units.get(stage))
        if stage not in partial:raise ValueError('missing verified partial stage inventory: '+stage)
        inventory=partial[stage]
        merge_sources(sources,{value['path']:value for value in inventory['input_identities'].values()})
        merge_sources(sources,{value['path']:value for value in inventory['evidence_identities'].values()})
        stage_meta=dict(partial=True)
        if inventory.get('source_report_identity') is not None:stage_meta['source_report_identity']=thaw(inventory['source_report_identity'])
        stage_rows.append(dict(id=stage,source_record=parent_snapshot['stages'][stage],imported_record=stage_meta,signature=content_signature(inventory['input_identities']),origin='reused_verified'))
        for uid,item in inventory['verified_units'].items():
            origin=item.get('origin_record',dict(stage=stage,origin_run_id=parent.name,source_report_identity=item['checkpoint_identity'],source_unit_id=uid))
            unit_rows.append(dict(id=uid,source_record=item['record'],imported_record=thaw(origin),signature=item['signature'],origin=item.get('origin_kind','reused_verified')))
        if stage=='source_clips':media=stage_media(stage,{'clips':inventory['clips']})
        elif stage=='upscale':
            media=[]
            for uid,item in inventory['verified_units'].items():
                frame=thaw(item['frame']) if 'frame' in item else read_json(Path(item['checkpoint_identity']['path']))
                media.append((uid,'upscaled_frame_identity',frame['upscaled_frame_identity']))
            for clip in inventory['clips']:media.append((clip['shot_id'],'upscaled_clip',clip['upscaled_identity']))
        else:raise ValueError('partial stage serializer unavailable')
        for uid,role,original in media:
            if role in ('generated_identity','source_identity','upscaled_clip'):
                relative=Path('shots')/uid/({'generated_identity':'generated.mp4','source_identity':'source.mp4','upscaled_clip':'upscaled.mp4'}[role])
            else:
                shot,frame=uid.split(':');relative=Path('shots')/shot/('frames' if role=='input_identity' else 'upscaled-frames')/(frame+'.png')
            target=run/relative
            if target not in targets:copies.append(dict(original_identity=original,copy_path=target,role=role,stage=stage,unit_id=uid));targets.add(target)
    for stage,unit_ids in (retry_targets or {}).items():
        existing=next((row for row in stage_rows if row['id']==stage),None)
        if existing is None:
            existing=dict(id=stage,source_record=parent_snapshot['stages'][stage],imported_record={},signature=content_signature(parent_snapshot['stages'][stage]),origin='reused_verified');stage_rows.append(existing)
        existing['imported_record']['retry_failed_units']=list(unit_ids)
    child_inputs=dict(parent_snapshot['inputs'],config=thaw(hash_file(config.config_file))) if child_inputs is None else dict(child_inputs)
    if 'speech' in partial_stages:
        # The original startup remains bound by the import source closure;
        # this child will create and register its own startup evidence.
        child_inputs={key:value for key,value in child_inputs.items() if key not in _SPEECH_RUNTIME_INPUTS}
    child_models=parent_snapshot['models'] if 'speech' in stages or 'speech' in partial_stages else {}
    store=create_manifest(run,config,inputs=child_inputs,models=child_models,workflows={})
    if preflight_report is not None:
        preflight_id=write_exclusive(run,run/'logs/pipeline/preflight.json',preflight_report)
        store.record_stage('preflight','running');store.record_stage('preflight','completed',artifacts=[_artifact(preflight_id)])
    identity=create_pipeline_import(config,run_dir=run,parent_run_dir=parent,reason=reason,source_identities=sources,copies=copies,stages=stage_rows,units=unit_rows,review_inheritance=inherited,changes_identity=changes_identity)
    receipt=load_pipeline_import(run)
    for stage,origin in reports.items():
        if stage=='storyboard' and changes and changes.get('shot_changes'):
            from ._pipeline_storyboard_revision import prepare_storyboard_revision
            prepare_storyboard_revision(config,run,changes,identity)
            continue
        report=serialize_stage_import(stage,origin,run=run,import_identity=identity,receipt=receipt)
        report_id=write_exclusive(run,run/STAGE_FILES[stage],report)
        store.record_stage(stage,'running')
        kind={'speech':'speech','start_images':'image','source_clips':'shot','upscale':'frame'}.get(stage)
        if kind:
            for uid in report['reused_units']:
                artifacts=[_artifact(report_id)]+[_artifact(fresh(r['copy_identity'])) for r in receipt['copies'] if r['stage']==stage and r['unit_id']==uid]
                store.record_unit(kind,uid,'running');store.record_unit(kind,uid,'completed',artifacts=artifacts)
        store.update(lambda data,s=stage,i=report_id:data['workflows'].update({STAGE_WORKFLOWS[s]:thaw(i)}))
        store.record_stage(stage,'completed',artifacts=[_artifact(report_id)])
        if stage=='speech':stage_consumer(stage)(run)
        else:load_imported_stage(run,stage)
        if stage=='speech':
            from .speech_checks import load_committed_speech
            from .timeline_checks import plan_timeline
            if load_committed_speech(run)['accepted']:plan_timeline(config,run_dir=run)
    for stage in partial_stages:
        kind={'speech':'speech','start_images':'image','source_clips':'shot','upscale':'frame'}[stage]
        for uid in partial[stage]['verified_units']:
            artifacts=[_artifact(fresh(row['copy_identity'])) for row in receipt['copies'] if row['stage']==stage and row['unit_id']==uid]
            store.record_unit(kind,uid,'running');store.record_unit(kind,uid,'completed',artifacts=artifacts)
        if stage=='speech':
            from .speech_checks import serialize_imported_speech
            units={r['id']:dict(origin_run_id=r['imported_record']['origin_run_id'],source_report_identity=thaw(r['imported_record']['source_report_identity']),source_unit_id=r['imported_record']['source_unit_id'],signature=r['signature'],import_identity=thaw(identity)) for r in receipt['units'] if r['imported_record'].get('stage')==stage}
            report=serialize_imported_speech(config,run,source_report=read_json(parent/'segments.json'),import_identity=identity,reused_units=units,copies=receipt['copies'])
            write_exclusive(run,run/'segments.json',report)
    return run


def derive_partial_stage(config, *, parent_run_dir, stage, completed_stages=(), reason='Explicit partial stage recovery'):
    return derive_completed_stages(config,parent_run_dir=parent_run_dir,stages=completed_stages,reason=reason,partial_stages=(stage,))


def select_completed_inventory(parent,stage,unit_ids=None):
    report=stage_consumer(stage)(parent);snapshot=ManifestStore.open(parent).snapshot()
    source_id=hash_file(parent/STAGE_FILES[stage]);all_ids=stage_unit_ids(stage,report)
    requested=set(all_ids if unit_ids is None else unit_ids)
    # A planner may represent a whole unchanged upscale shot by its shot ID.
    selected=tuple(uid for uid in all_ids if uid in requested or stage=='upscale' and uid.split(':',1)[0] in requested)
    if not selected:raise ValueError('empty selective completed import')
    if requested-{*all_ids,*[uid.split(':',1)[0] for uid in all_ids]}:raise ValueError('selected import unit unknown')
    sources=collect_report_sources(report,parent);sources[source_id.path]=thaw(source_id)
    kind={'source_clips':'shot','upscale':'frame'}[stage]
    verified={uid:dict(record=snapshot['units'][kind][uid],checkpoint_identity=thaw(source_id),signature=report.get('reused_units',{}).get(uid,{}).get('signature',content_signature(snapshot['units'][kind][uid]))) for uid in selected}
    for uid,item in verified.items():
        retained=retained_unit_origin(parent,stage,uid,report.get('reused_units',{}).get(uid))
        if retained:item.update(retained)
    clips=[c for c in report['clips'] if c['shot_id'] in selected] if stage=='source_clips' else [c for c in report['clips'] if all(f"{c['shot_id']}:frame_{f['frame_index']:06d}" in selected for f in c['frames'])]
    if stage=='upscale':
        for clip in report['clips']:
            for frame in clip['frames']:
                uid=f"{clip['shot_id']}:frame_{frame['frame_index']:06d}"
                if uid in verified:verified[uid]['frame']=thaw(frame)
    return dict(verified_units=verified,remaining_units=tuple(uid for uid in all_ids if uid not in selected),input_identities={},evidence_identities=sources,clips=clips,source_report_identity=thaw(source_id))


def derive_run(config, *, parent_run_dir, plan, changes=None,changes_identity=None):
    """Execute only fresh reusable stages; the coordinator locks the child next."""
    def field(row,name):return row.get(name) if isinstance(row,Mapping) else getattr(row,name)
    stages=tuple(field(row,'stage') for row in plan.reused if field(row,'unit_id') is None and field(row,'stage') in STAGE_FILES)
    parent=_run_path(parent_run_dir);snapshot=ManifestStore.open(parent).snapshot()
    previous_options=parent/'logs/pipeline/pipeline-options.json'
    options=read_json(previous_options) if previous_options.is_file() else {}
    script_identity=(changes or {}).get('script_identity') or snapshot['inputs'].get('script')
    if script_identity is None:raise ValueError('derived run requires original/new script identity')
    script_identity=fresh(script_identity)
    from .preflight import preflight
    preflight_result=preflight(config,script=Path(script_identity.path),output=Path(options['output_path']) if options.get('output_path') else None)
    if not preflight_result.passed:raise ValueError('derived run fresh preflight failed')
    if changes is not None and changes_identity is None:
        if isinstance(changes,(str,Path)):changes_identity=hash_file(Path(changes))
        elif isinstance(changes,Mapping):changes_identity=changes.get('identity') or changes.get('changes_identity')
    if changes is not None and changes_identity is None:raise ValueError('explicit changes file identity required for derived provenance')
    retry_targets={}
    for row in plan.invalidated:
        reason=field(row,'reason');uid=field(row,'unit_id');stage=field(row,'stage')
        if uid is not None and isinstance(reason,str) and reason.startswith('explicit failed'):
            value=uid.split(':attempt_',1)[0] if stage=='source_clips' else uid
            if value not in retry_targets.setdefault(stage,[]):retry_targets[stage].append(value)
    partial=tuple(s for s in ('speech','start_images','source_clips','upscale') if s not in stages and (
        any(field(row,'stage')==s and field(row,'unit_id') is not None for row in plan.reused)
        or s=='speech' and bool(retry_targets.get('speech'))))
    selection={s:tuple(field(row,'unit_id') for row in plan.reused if field(row,'stage')==s and field(row,'unit_id') is not None) for s in partial}
    unit_review=(changes or {}).get('unit_review_identity') or options.get('unit_review_identity')
    if unit_review is not None:
        unit_review=fresh(unit_review)
        from .pipeline_reviews import load_unit_review
        load_unit_review(Path(unit_review.path),script_path=Path(script_identity.path))
    elif 'speech' not in stages and 'speech' not in partial:raise ValueError('new speech needs current unit review before deriving')
    inputs=dict(snapshot['inputs']) if 'speech' in stages or 'speech' in partial else {}
    if 'speech' in partial:inputs={key:value for key,value in inputs.items() if key not in _SPEECH_RUNTIME_INPUTS}
    inputs.update(script=thaw(script_identity),config=thaw(hash_file(config.config_file)),voice=thaw(hash_file(config.voice.config_file)))
    run=derive_completed_stages(config,parent_run_dir=parent_run_dir,stages=stages,reason='Explicit pipeline recovery or revision',changes_identity=changes_identity,partial_stages=partial,selected_units=selection,changes=changes,child_inputs=inputs,preflight_report=preflight_result.as_dict(),extra_source_identities=plan.input_identities,retry_targets=retry_targets)
    copied_review=copy_exclusive(run,unit_review,run/'logs/pipeline/unit-review.json') if unit_review is not None else None
    image_inputs=options.get('image_inputs_identity');settings=options.get('settings_identity')
    if image_inputs is not None:
        old=fresh(image_inputs);mapping=read_json(Path(old.path));keys(mapping,'schema_version run_id shots entities','image input map')
        image_inputs=write_exclusive(run,run/'logs/pipeline/image-inputs.json',dict(mapping,run_id=run.name))
    if settings is not None:settings=fresh(settings)
    write_exclusive(run,run/'logs/pipeline/pipeline-options.json',dict(schema_version=1,run_id=run.name,created_at=now(),input_identities=inputs,
        unit_review_identity=thaw(copied_review),image_inputs_identity=thaw(image_inputs),settings_identity=thaw(settings),output_path=options.get('output_path'),
        cpu_planner=options.get('cpu_planner',False),execution_policy=dict(gpu_management='disabled',total_timeout_seconds=None,media_command_timeout_seconds=300)))
    # Timeline has no imported schema: rebuild it from actual copied samples.
    if 'speech' in stages and any(field(row,'stage')=='timeline' and field(row,'unit_id') is None for row in plan.reused):
        from .speech_checks import load_committed_speech
        from .timeline_checks import plan_timeline
        if load_committed_speech(run)['accepted'] and ManifestStore.open(run).snapshot()['stages']['timeline']['status']=='pending':plan_timeline(config,run_dir=run)
    return run


def collect_partial_inventory(config,run_dir,snapshot=None, *, stages=None):
    """Reconstruct durable prefixes without reopening a terminal parent record."""
    run=_run_path(run_dir);snapshot=ManifestStore.open(run).snapshot() if snapshot is None else snapshot
    result={};selected=set(STAGES if stages is None else stages)
    def unknown(kinds):
        return any(unit.get('submission') is not None and unit['submission'].get('state') in ('intent','accepted','ambiguous') for kind in kinds for unit in snapshot['units'].get(kind,{}).values())
    stage=snapshot['stages']['upscale']
    if 'upscale' in selected and not unknown(('frame',)) and stage['status'] in ('running','failed','interrupted','ambiguous') and not stage['artifacts'] and snapshot['units']['frame']:
        from ._upscale_inputs import inputs
        from ._upscale_resume import reconstruct
        context=inputs(config,run)
        reuse,records,clips=reconstruct(config,run,snapshot,context,_pipeline=True)
        verified={}
        for plan in context['plans']:
            for index in range(1,plan.source_frames+1):
                uid=f'{plan.shot_id}:frame_{index:06d}'
                unit=snapshot['units']['frame'].get(uid)
                if unit is not None and unit['status']=='completed':
                    if uid in reuse.get('inherited_frames',{}):
                        row=reuse['origin_rows'][uid];origin=dict(thaw(row['imported_record']),parent_kind='frame',parent_unit_id=uid)
                        verified[uid]=dict(record=thaw(unit),checkpoint_identity=thaw(origin['source_report_identity']),signature=row['signature'],
                            frame=thaw(reuse['inherited_frames'][uid]),origin_record=origin,origin_kind=row['origin'])
                    else:verified[uid]=dict(record=thaw(unit),checkpoint_identity=thaw(hash_file(run/'logs/upscale'/f'frame-{plan.shot_id}-{index:06d}.json')),signature=content_signature(unit))
        all_units=tuple(f'{plan.shot_id}:frame_{index:06d}' for plan in context['plans'] for index in range(1,plan.source_frames+1))
        result['upscale']=dict(unsent_verified=not reuse.get('known_failed_units'),known_failed_units=reuse.get('known_failed_units',{}),verified_units=verified,remaining_units=tuple(uid for uid in all_units if uid not in verified),
            input_identities=thaw(context['identities']),evidence_identities={**records,**reuse.get('failure_source_identities',{})},reconstruction=reuse,clips=clips)
    stage=snapshot['stages']['source_clips']
    if 'source_clips' in selected and not unknown(('shot_attempt',)) and stage['status'] in ('running','failed','interrupted','ambiguous') and not stage['artifacts'] and snapshot['units']['shot']:
        result['source_clips']=reconstruct_source_prefix(config,run,snapshot)
    stage=snapshot['stages']['speech']
    from .pipeline_inventory import unknown_tts_intents
    if 'speech' in selected and not unknown(('speech',)) and not unknown_tts_intents(snapshot,run_dir=run) and stage['status'] in ('running','failed','interrupted') and (run/'segments.json').is_file():
        from .speech_checks import _load_partial_speech
        value=_load_partial_speech(run);report=value['report'];source_id=hash_file(run/'segments.json')
        items=[report.get('reference_replay'),*[item for item in report['spans'] if item['kind']=='speech']]
        verified={item['unit_id']:dict(record=snapshot['units']['speech'][item['unit_id']],checkpoint_identity=thaw(source_id),signature=content_signature(item)) for item in items if item is not None and item['status']=='completed'}
        failed=value.get('known_failed_units',{})
        failed_evidence={path:thaw(identity) for proof in failed.values() for path,identity in proof['evidence_identities'].items()}
        result['speech']=dict(unsent_verified=not failed,known_failed_units=failed,verified_units=verified,
            remaining_units=tuple(item['unit_id'] for item in items if item is not None and item['status']!='completed'),
            input_identities=thaw(value['input_identities']),evidence_identities=failed_evidence)
    if ManifestStore.open(run).snapshot()!=snapshot:raise ValueError('parent changed during partial inventory')
    return immutable(result)


def reconstruct_source_prefix(config,run,snapshot):
    from ._source_clip_inputs import inputs,evidence,MODEL_NAMES
    from ._source_clip_evidence import validate,validation
    from ..planning.source_clips import frame_mapping
    context=inputs(config,run);clips=[];records={};verified={};selected_attempts=set();mappings=[];failed={};failure_sources={}
    for plan in context['plans']:
        uid=plan.shot_id;path=run/'logs/source-clips'/f'clip-{uid}.json'
        if not path.exists():continue
        clip=read_json(_local(run,path))
        if clip.get('shot_id')!=uid:raise ValueError('source checkpoint unit differs')
        evidence(run,records,[run/name for name in clip['evidence_identities']]+[path])
        clips.append(clip)
        selected_attempts.update(a['unit_id'] for a in clip['attempts'])
        mappings.append(frame_mapping(plan,generated_identity=clip['generated_identity'],source_identity=clip['source_identity'],generated_frames=clip['generated_frames'],output_fps=context['board']['effective_media']['fps']))
        verified[uid]=dict(record=snapshot['units']['shot'][uid],checkpoint_identity=thaw(hash_file(path)),signature=content_signature(clip))
    for uid,unit in snapshot['units'].get('shot_attempt',{}).items():
        if uid not in selected_attempts and (unit['submission'] is not None or unit['artifacts']):
            submission=unit['submission']
            if submission is None or not (submission['state'] in ('failed','rejected') or unit['status']=='failed' and submission['state']=='completed'):
                raise ValueError('unknown/failed submitted source unit cannot become remaining')
            from .pipeline_recovery import validate_failed_submission
            proof=validate_failed_submission(run,'source_clips',uid,submission)
            evidence(run,records,[Path(identity.path) for identity in proof if Path(identity.path).is_relative_to(run)])
            failure_sources.update({identity.path:thaw(identity) for identity in proof if not Path(identity.path).is_relative_to(run)})
            failed[uid]=dict(record=thaw(unit),evidence_identities=thaw(proof))
    for path in (run/'logs/http').glob('*.request.json'):
        request=read_json(_local(run,path))
        if request.get('stage')=='source_clips' and request.get('method')=='POST' and path.relative_to(run).as_posix() not in records:raise ValueError('unassociated source POST cannot become remaining')
    if not clips and not failed and not imported_unit_map(run,'source_clips')[0]:raise ValueError('no independently verified source checkpoint')
    draft=dict(schema_version=1,run_id=run.name,created_at=now(),status='review_required',passed=False,
        **{k+'_identity':thaw(context['identities'][k]) for k in ('images','storyboard','timeline')},effective_media=context['board']['effective_media'],
        clips=clips,requirement_clips=[],frame_mappings=mappings,model_identities={n:thaw(context['identities'][n]) for n in MODEL_NAMES},
        workflow_identity=thaw(context['identities']['workflow']),mapping_identity=thaw(context['identities']['mapping']),
        provenance=context['provenance'],validation=validation(False),request_evidence=records)
    if clips:validate(config,run,draft,context,snapshot,_partial=True)
    imported,origin_rows=imported_unit_map(run,'source_clips')
    if imported:
        inherited=reused_source_clips(run,imported,context)
        if set(inherited)&set(verified):raise ValueError('imported source unexpectedly has new native checkpoint')
        for uid,clip in inherited.items():
            row=origin_rows[uid];unit=snapshot['units']['shot'].get(uid)
            if unit is None or unit['status']!='completed' or unit['submission'] is not None:raise ValueError('inherited source unit no longer completed')
            origin=dict(thaw(row['imported_record']),parent_kind='shot',parent_unit_id=uid)
            verified[uid]=dict(record=thaw(unit),checkpoint_identity=thaw(origin['source_report_identity']),signature=row['signature'],origin_record=origin,origin_kind=row['origin'])
        all_clips={**inherited,**{clip['shot_id']:clip for clip in clips}}
        clips=[all_clips[plan.shot_id] for plan in context['plans'] if plan.shot_id in all_clips]
        verified={plan.shot_id:verified[plan.shot_id] for plan in context['plans'] if plan.shot_id in verified}
        failure_sources.update({path:thaw(identity) for path,identity in import_source_identities(run).items()})
    _again(context['identities'])
    return dict(unsent_verified=not failed,known_failed_units=failed,verified_units=verified,remaining_units=tuple(p.shot_id for p in context['plans'] if p.shot_id not in verified),
        input_identities=thaw(context['identities']),evidence_identities={**records,**failure_sources},clips=clips)


def reused_source_clips(run,reused_units,context):
    """Revalidate original complete clips before rebinding documented copies."""
    receipt=load_pipeline_import(run);parent=_run_path(run.parent/receipt['parent_run_id'])
    snapshot=ManifestStore.open(parent).snapshot()
    rows={r['id']:r for r in receipt['units'] if r['imported_record'].get('stage')=='source_clips'}
    result={};origins={}
    for uid,reuse in reused_units.items():
        row=rows.get(uid)
        if row is None or reuse['signature']!=row['signature'] or not same_identity(reuse['import_identity'],ManifestStore.open(run).snapshot()['workflows']['pipeline_import']):raise ValueError('reused source unit provenance differs')
        source=row['imported_record']
        if any(thaw(reuse[k])!=thaw(source[k]) for k in ('origin_run_id','source_report_identity','source_unit_id')):raise ValueError('reused source origin differs')
        if row['origin']=='completed_saved_submission':
            from ._pipeline_saved_import import consume_reconciled_unit
            matches=[consume_reconciled_unit(parent,row)]
        else:
            native=run.parent/source['origin_run_id']
            if native not in origins:
                original_snapshot=ManifestStore.open(native).snapshot()
                if original_snapshot['stages']['source_clips']['status']=='completed':clips=stage_consumer('source_clips')(native)['clips']
                else:
                    from ..config import load_config
                    original_config=load_config(Path(original_snapshot['config_snapshot']['path']))
                    clips=reconstruct_source_prefix(original_config,native,original_snapshot)['clips']
                origins[native]=clips
            matches=[c for c in origins[native] if c['shot_id']==source['source_unit_id']]
        if len(matches)!=1:raise ValueError('source unit not independently reconstructed')
        value=thaw(matches[0])
        for name in ('generated_identity','source_identity'):
            value[name]=imported_media_copy(receipt,'source_clips',uid,name,value[name])
        # Start images are the current child input; their bytes must match origin.
        current_record=thaw(next(p.start_image_identity for p in context['plans'] if p.shot_id==uid))
        current=fresh(current_record)
        if (current.bytes,current.sha256)!=(value['start_image_identity']['bytes'],value['start_image_identity']['sha256']):raise ValueError('reused source current start image content differs')
        value['start_image_identity']=current_record
        plan=next(p for p in context['plans'] if p.shot_id==uid)
        parameters=thaw(plan.parameters);parameters['length']=value['parameters']['length']
        if parameters!=value['parameters'] or thaw(plan.budget)!=value['budget']:
            raise ValueError('reused source current parameters/budget differ before POST')
        from .pipeline_inventory import _semantic
        from ._source_clip_inputs import MODEL_NAMES
        resolved=snapshot['config_snapshot']['resolved']
        for name in (*MODEL_NAMES,'workflow','mapping'):
            path=resolved['models'][name] if name in MODEL_NAMES else resolved['workflows']['wan' if name=='workflow' else 'wan_mapping']
            old=hash_file(Path(path))
            if _semantic(thaw(old))!=_semantic(thaw(context['identities'][name])):raise ValueError('reused source current model/workflow differs')
        result[uid]=value
    return result


def imported_media_copy(receipt,stage,uid,role,original):
    rows=[r for r in receipt['copies'] if r['stage']==stage and r['unit_id']==uid and r['role']==role]
    if len(rows)!=1:raise ValueError('one exact imported media copy required')
    expected=fresh(original);source=fresh(rows[0]['original_identity']);target=fresh(rows[0]['copy_identity'])
    if (expected.bytes,expected.sha256)!=(source.bytes,source.sha256) or (source.bytes,source.sha256)!=(target.bytes,target.sha256):
        raise ValueError('imported media copy differs from actual native origin')
    return thaw(rows[0]['copy_identity'])


def validate_mixed_source(config,run,draft,context,snapshot):
    from ._source_clip_evidence import DRAFT_FIELDS,validate
    from ._source_clip_inputs import same
    from ..planning.source_clips import frame_mapping,requirement_clips
    keys(draft,DRAFT_FIELDS+' import_identity reused_units','imported source draft')
    if not draft['reused_units'] or draft['import_identity'] is None:raise ValueError('mixed source requires bound reused units')
    receipt=load_pipeline_import(run,identity=draft['import_identity'])
    originals=reused_source_clips(run,draft['reused_units'],context)
    native=thaw(draft);native.update(schema_version=1);native.pop('import_identity');native.pop('reused_units')
    native['clips']=[c for c in native['clips'] if c['shot_id'] not in originals]
    native['frame_mappings']=[m for m in native['frame_mappings'] if m['shot_id'] not in originals]
    ids=validate(config,run,native,context,snapshot,_partial=True) if native['clips'] else {}
    clips=draft['clips'];plans=context['plans']
    if [c['shot_id'] for c in clips]!=[p.shot_id for p in plans]:raise ValueError('mixed source exact order/coverage differs')
    mappings={};sources={}
    for clip,plan in zip(clips,plans):
        uid=clip['shot_id']
        if uid in originals:
            if not same(clip,originals[uid]):raise ValueError('mixed source clip differs from original and copies')
            params=thaw(plan.parameters);params['length']=clip['parameters']['length']
            if not same(params,clip['parameters']) or not same(plan.budget,clip['budget']):raise ValueError('reused source current parameters/budget differ')
            unit=snapshot['units']['shot'].get(uid)
            if unit is None or unit['status']!='completed' or unit['submission'] is not None:raise ValueError('reused source must have completed child unit and no POST')
        sources[uid]=clip['source_identity']
        mappings[uid]=frame_mapping(plan,generated_identity=clip['generated_identity'],source_identity=clip['source_identity'],generated_frames=clip['generated_frames'],output_fps=context['board']['effective_media']['fps'])
    if not same(draft['frame_mappings'],list(mappings.values())) or not same(draft['requirement_clips'],requirement_clips(context['board'],source_identities=sources,frame_mappings=mappings,total_samples=context['timeline']['total_samples'])):raise ValueError('mixed source full associations differ')
    if set(snapshot['units']['shot'])!=set(sources):raise ValueError('unexpected mixed source unit')
    expected_attempts={a['unit_id'] for c in native['clips'] for a in c['attempts']}
    if set(snapshot['units'].get('shot_attempt',{}))!=expected_attempts:raise ValueError('unexpected mixed source submitted unit')
    ids.update({'import/'+p:i for p,i in import_source_identities(run).items()});_again(ids)
    return ids


def reused_upscale_frames(config,run,reused_units,context):
    receipt=load_pipeline_import(run);parent=_run_path(run.parent/receipt['parent_run_id']);snapshot=ManifestStore.open(parent).snapshot()
    rows={r['id']:r for r in receipt['units'] if r['imported_record'].get('stage')=='upscale'}
    originals={};origins={};result={}
    for uid,reuse in reused_units.items():
        row=rows.get(uid)
        if row is not None and row['origin']=='completed_saved_submission':
            from ._pipeline_saved_import import consume_reconciled_unit
            originals[uid]=consume_reconciled_unit(parent,row)
        elif row is not None:
            source=row['imported_record'];native=run.parent/source['origin_run_id']
            if native not in origins:
                original_snapshot=ManifestStore.open(native).snapshot()
                if original_snapshot['stages']['upscale']['status']=='completed':
                    original=stage_consumer('upscale')(native)
                    frames={f"{c['shot_id']}:frame_{f['frame_index']:06d}":f for c in original['clips'] for f in c['frames']}
                else:
                    from ..config import load_config
                    original_config=load_config(Path(original_snapshot['config_snapshot']['path']))
                    inventory=collect_partial_inventory(original_config,native,original_snapshot)['upscale']
                    frames={name:dict(read_json(Path(item['checkpoint_identity']['path'])),checkpoint_identity=thaw(item['checkpoint_identity'])) for name,item in inventory['verified_units'].items()}
                origins[native]=frames
            originals[uid]=origins[native][source['source_unit_id']]
        if row is None or uid not in originals or reuse['signature']!=row['signature']:raise ValueError('upscale reused unit source/signature differs')
        source=row['imported_record']
        if any(thaw(reuse[k])!=thaw(source[k]) for k in ('origin_run_id','source_report_identity','source_unit_id')):raise ValueError('upscale reused origin differs')
        if not same_identity(reuse['import_identity'],ManifestStore.open(run).snapshot()['workflows']['pipeline_import']):raise ValueError('upscale reused import differs')
        frame=thaw(originals[uid])
        if row['origin']!='completed_saved_submission' and Path(source['source_report_identity']['path']).name.startswith('frame-'):
            frame['checkpoint_identity']=thaw(source['source_report_identity'])
        plan=next(p for p in context['plans'] if p.shot_id==frame['shot_id'])
        current=thaw(plan.source_identity)
        if (current['bytes'],current['sha256'])!=(frame['source_identity']['bytes'],frame['source_identity']['sha256']) or thaw(plan.parameters)!=frame['parameters']:raise ValueError('reused upscale current source/parameters differ')
        for name in ('model','workflow','mapping'):
            wanted=thaw(context['identities'][name]);original=frame[name+'_identity']
            if (wanted['bytes'],wanted['sha256'])!=(original['bytes'],original['sha256']):raise ValueError('reused upscale model/workflow content differs')
        frame['upscaled_frame_identity']=imported_media_copy(receipt,'upscale',uid,'upscaled_frame_identity',frame['upscaled_frame_identity'])
        frame['source_identity']=current
        result[uid]=frame
    # Arbitrary holes cannot be promoted into a prefix by sorting.
    for plan in context['plans']:
        indices=[f['frame_index'] for f in result.values() if f['shot_id']==plan.shot_id]
        if indices!=list(range(1,len(indices)+1)):raise ValueError('upscale reusable frames must be an ordered prefix')
    return result


def reused_upscale_clips(config,run,reused_units,context,frames):
    receipt=load_pipeline_import(run);parent=_run_path(run.parent/receipt['parent_run_id']);snapshot=ManifestStore.open(parent).snapshot()
    rows={r['id']:r for r in receipt['units'] if r['imported_record'].get('stage')=='upscale'}
    wanted={r['unit_id'] for r in receipt['copies'] if r['stage']=='upscale' and r['role']=='upscaled_clip'}
    clips=[];origins={}
    for shot in wanted:
        bound=[row for uid,row in rows.items() if uid.startswith(shot+':frame_')]
        if not bound:raise ValueError('encoded imported clip has no bound model frames')
        native=parent if (parent/'logs/upscale'/f'clip-{shot}.json').is_file() else run.parent/bound[0]['imported_record']['origin_run_id']
        if native not in origins:
            original_snapshot=ManifestStore.open(native).snapshot()
            if original_snapshot['stages']['upscale']['status']=='completed':original_clips=stage_consumer('upscale')(native)['clips']
            else:
                from ..config import load_config
                origin_config=load_config(Path(original_snapshot['config_snapshot']['path']))
                inventory=collect_partial_inventory(origin_config,native,original_snapshot,stages=('upscale',))
                original_clips=inventory.get('upscale',{}).get('clips',())
            origins[native]=original_clips
        selected=[clip for clip in origins[native] if clip['shot_id']==shot]
        if len(selected)!=1:raise ValueError('imported encoded clip original checkpoint unavailable')
        clips.extend(selected)
    result={}
    for clip in clips:
        uid=clip['shot_id'];unit_ids=tuple(f"{uid}:frame_{f['frame_index']:06d}" for f in clip['frames'])
        if not all(unit in reused_units for unit in unit_ids):raise ValueError('encoded imported clip lacks complete reused frame set')
        plan=next(p for p in context['plans'] if p.shot_id==uid)
        if thaw(plan.budget)!=thaw(clip['budget']) or thaw(plan.parameters)!=thaw(clip['parameters']):raise ValueError('reused encoded clip budget/parameters differ')
        value=thaw(clip);value['source_identity']=thaw(plan.source_identity)
        value['upscaled_identity']=imported_media_copy(receipt,'upscale',uid,'upscaled_clip',clip['upscaled_identity'])
        value['frames']=[frames[unit] for unit in unit_ids]
        result[uid]=value
    return result


def validate_mixed_upscale(config,run,draft,context,snapshot):
    from ._upscale_evidence import validate
    from ._upscale_inputs import same
    if not draft.get('reused_units') or draft.get('import_identity') is None:raise ValueError('mixed upscale import requires reused frames')
    load_pipeline_import(run,identity=draft['import_identity'])
    originals=reused_upscale_frames(config,run,draft['reused_units'],context)
    complete=reused_upscale_clips(config,run,draft['reused_units'],context,originals)
    expected={}
    for clip in draft['clips']:
        if clip['shot_id'] in complete:
            if not same(clip,complete[clip['shot_id']]):raise ValueError('reused encoded clip differs from original/copy')
            expected.update({uid:frame for uid,frame in originals.items() if frame['shot_id']==clip['shot_id']})
            continue
        extracts=[name for name in clip['evidence_identities'] if name.startswith('logs/upscale/extract-') and name.endswith('.json')]
        if len(extracts)!=1:raise ValueError('mixed upscale requires one new source extraction')
        rows=read_json(run/extracts[0])['frames']
        for frame in clip['frames']:
            uid=f"{clip['shot_id']}:frame_{frame['frame_index']:06d}"
            if uid not in originals:continue
            value=dict(originals[uid],input_identity=rows[frame['frame_index']-1]['identity'])
            if not same(frame,value):raise ValueError('imported model frame differs from origin/copy/extraction')
            unit=snapshot['units']['frame'].get(uid)
            if unit is None or unit['status']!='completed' or unit['submission'] is not None:raise ValueError('imported frame cannot have child POST')
            for identity in (frame['input_identity'],frame['upscaled_frame_identity']):fresh(identity)
            expected[uid]=value
    if set(expected)!=set(originals):raise ValueError('mixed upscale missing reused frame')
    ids=validate(config,run,draft,context,snapshot,_reused_frames=expected,_reused_clips=complete)
    ids.update({'import/'+p:i for p,i in import_source_identities(run).items()});_again(ids)
    return ids


def validate_pipeline_checkpoint(stage,config,run_dir,snapshot=None):
    """Consume a registered complete draft without generation or author verdicts."""
    run=_run_path(run_dir);snapshot=ManifestStore.open(run).snapshot() if snapshot is None else snapshot
    if stage not in ('storyboard','start_images','source_clips','upscale'):raise ValueError('unsupported pipeline checkpoint stage')
    path=run/STAGE_FILES[stage].replace('.json','-draft.json')
    record=snapshot['stages'][stage]
    if record['status']!='running' or len(record['artifacts'])!=1 or Path(record['artifacts'][0]['path'])!=path:raise ValueError('registered running draft required')
    from .timeline_checks import _fresh
    identity=_fresh(record['artifacts'][0],run=run,expected=path);draft=read_json(path)
    if stage=='source_clips':
        from ._source_clip_inputs import inputs
        from ._source_clip_evidence import validate
        ids=validate(config,run,draft,inputs(config,run),snapshot)
    elif stage=='upscale':
        from ._upscale_inputs import inputs
        from ._upscale_evidence import validate
        ids=validate(config,run,draft,inputs(config,run),snapshot)
    elif stage=='start_images':
        from .start_image_checks import _input_files,_validate_draft
        board,ids=_input_files(config,run);ids.update(_validate_draft(config,run,draft,board,snapshot))
    else:
        from .storyboard_checks import _verified_inputs,_timing,_validate_draft
        if draft.get('schema_version')==2 and draft.get('import_identity') is not None:
            from ._pipeline_storyboard_revision import validate_revision
            ids=validate_revision(config,run,draft)
        else:
            timeline,ids=_verified_inputs(config,run,snapshot)
            timing,more=_timing(run,Path(draft['timing_review_identity']['path']),timeline);ids.update(more)
            _validate_draft(config,run,draft,timeline,timing,ids)
    ids['draft']=identity;_again(ids)
    if ManifestStore.open(run).snapshot()!=snapshot:raise ValueError('checkpoint manifest drift')
    return dict(draft_complete=True,draft_identity=identity,identities=ids,report=draft)
