"""Prompt-only child drafts with an explicit fresh original-meaning review."""
from pathlib import Path

from ..config import read_json
from ..planning.recovery import validate_changes
from ..planning.storyboard import plan_slots,validate_model_content
from .manifest import ManifestStore,hash_file,thaw
from .pipeline_evidence import write_exclusive
from .pipeline_import import (load_pipeline_import,serialize_stage_import,import_source_identities,
    fresh,same_identity)
from .timeline_checks import _run_path,_local,_again,_artifact,load_committed_timeline


def _timeline_content(timeline):
    value=thaw(timeline)
    for clip in value['clips']:
        pcm=clip['pcm']
        identity=hash_file(Path(pcm['path']))
        if identity.sha256!=pcm['sha256']:raise ValueError('revision PCM content differs')
        pcm.pop('path')
    return value


def _expected(config,run,identity, *, bindings=None):
    from . import storyboard_checks as owner
    from .visual_contracts import load_visual_contract,check_contract_presence
    receipt=load_pipeline_import(run,identity=identity)
    if receipt['changes_identity'] is None:raise ValueError('revision requires author changes identity')
    changes_id=fresh(receipt['changes_identity']);changes=read_json(Path(changes_id.path))
    parent=run.parent/receipt['parent_run_id'];origin=owner.load_committed_storyboard(parent)
    validate_changes(changes,run_id=parent.name,shot_ids=tuple(s['shot_id'] for s in origin['shots']))
    if not changes['shot_changes'] or changes['script_identity'] is not None or changes['unit_review_identity'] is not None:
        raise ValueError('prompt revision cannot change source speech')
    rows=[r for r in receipt['stages'] if r['id']=='storyboard']
    if len(rows)!=1 or not same_identity(hash_file(parent/'storyboard.json'),rows[0]['imported_record']['source_report_identity']):
        raise ValueError('revision source storyboard differs')
    child_timeline=load_committed_timeline(run);parent_timeline=load_committed_timeline(parent)
    if _timeline_content(child_timeline)!=_timeline_content(parent_timeline):raise ValueError('revision timeline differs from original samples')
    if owner._media(config)!=origin['effective_media']:raise ValueError('prompt revision media differs')
    expected=serialize_stage_import('storyboard',origin,run=run,import_identity=identity,receipt=receipt)
    expected.pop('review_identity')
    current={}
    for key,path in (('timeline_identity',run/'timeline.json'),('script_identity',run/'script.txt')):
        record=(bindings or {}).get(key)
        actual=fresh(record) if record is not None else hash_file(path)
        if Path(actual.path)!=path:raise ValueError('revision current input path differs')
        current[key]=thaw(record if record is not None else actual)
    expected.update(status='review_required',passed=False,validation=owner._validation(False),**current)
    by_id={s['shot_id']:s for s in expected['shots']}
    for row in changes['shot_changes']:
        for name in ('image_prompt','video_prompt'):
            if row[name] is not None:by_id[row['shot_id']][name]=row[name]
    source_inputs=origin['provenance']['inputs']
    source_script=fresh(source_inputs['script_copy'])
    source_run=_run_path(Path(source_script.path).parent)
    source_timeline=parent_timeline if source_run==parent else load_committed_timeline(source_run)
    if _timeline_content(source_timeline)!=_timeline_content(parent_timeline):raise ValueError('revision source author timeline differs from original samples')
    timing,ids=owner._timing(source_run,Path(origin['timing_review_identity']['path']),source_timeline)
    ids['script_copy']=source_script
    if 'visual_contract' in source_inputs:ids['visual_contract']=fresh(source_inputs['visual_contract'])
    slots=plan_slots(source_timeline,timing=timing)
    contract=load_visual_contract(source_run,slots,ids)
    content=dict(schema_version=1,global_visual=expected['global_visual'],shots=[])
    for shot in expected['shots']:
        row={k:shot[k] for k in owner.VISUAL_FIELDS};row['shot_id']=shot['shot_id']
        row['visual_requirements']=[{k:v for k,v in req.items() if k!='requirement_id'} for req in row['visual_requirements']]
        content['shots'].append(row)
    validate_model_content(content,slots,semantic_specs=contract.facts if contract else None,
        depiction_policy=contract.depiction_policy if contract else None)
    ids.update({'origin/'+p:i for p,i in import_source_identities(run).items()})
    ids.update(changes=changes_id,timeline=hash_file(run/'timeline.json'),script_copy=hash_file(run/'script.txt'))
    _again(ids)
    check_contract_presence(source_run,ids)
    return expected,ids


def prepare_storyboard_revision(config,run,changes,import_identity):
    run=_run_path(run);store=ManifestStore.open(run);snapshot=store.snapshot()
    if snapshot['stages']['storyboard']['status']!='pending' or any((run/p).exists() for p in ('storyboard.json','storyboard-draft.json')):
        raise ValueError('revision needs independent pending storyboard')
    expected,ids=_expected(config,run,import_identity)
    receipt=load_pipeline_import(run,identity=import_identity)
    if read_json(Path(receipt['changes_identity']['path']))!=thaw(changes):raise ValueError('revision author changes differ')
    identity=write_exclusive(run,run/'storyboard-draft.json',expected)
    _local(run,run/'logs/storyboard').mkdir(parents=True,exist_ok=True)
    _again(ids)
    store.update(lambda data:data['workflows'].update(storyboard_revision=thaw(identity)))
    store.record_stage('storyboard','running',artifacts=[_artifact(identity)])
    return identity


def validate_revision(config,run,draft):
    run=_run_path(run);snapshot=ManifestStore.open(run).snapshot()
    registered=snapshot['workflows'].get('storyboard_revision')
    if registered is None:raise ValueError('unregistered storyboard revision')
    identity=fresh(registered)
    if Path(identity.path)!=run/'storyboard-draft.json' or read_json(Path(identity.path))!=thaw(draft):
        raise ValueError('revision draft differs from registered origin')
    expected,ids=_expected(config,run,draft['import_identity'],bindings=draft)
    if thaw(draft)!=expected:raise ValueError('revision differs from allowed prompt-only origin')
    ids['draft']=identity;_again(ids)
    return ids


def finalize_revision(config,run,review_path):
    from . import storyboard_checks as owner
    run=_run_path(run);path=owner._review_path(run,review_path);store=ManifestStore.open(run)
    with owner._exclusive(run) as lock:
        snapshot=store.snapshot();stage=snapshot['stages']['storyboard']
        if stage['status']!='running' or (run/'storyboard.json').exists():raise ValueError('running revision draft required')
        draft=read_json(run/'storyboard-draft.json');ids=validate_revision(config,run,draft)
        ids['review']=owner._review(run,path,draft,ids['draft'],origin_report=draft)
        report=dict(draft,status='completed',passed=True,validation=owner._validation(True),review_identity=thaw(ids['review']))
        _again(ids);owner._check_lock(run,lock)
        if store.snapshot()!=snapshot:raise ValueError('revision manifest changed before commit')
        identity=write_exclusive(run,run/'storyboard.json',report)
        _again(ids);owner._check_lock(run,lock)
        store.update(lambda data:data['workflows'].update(storyboard_report=thaw(identity)))
        store.record_stage('storyboard','completed',artifacts=[_artifact(identity)])
        return owner._result(run,'completed',len(report['shots']))


def load_revision(run):
    from ..config import load_config
    from . import storyboard_checks as owner
    run=_run_path(run);store=ManifestStore.open(run);snapshot=store.snapshot();stage=snapshot['stages']['storyboard']
    if stage['status']!='completed':raise ValueError('revision storyboard not completed')
    config=load_config(Path(snapshot['config_snapshot']['path']))
    draft=read_json(run/'storyboard-draft.json');ids=validate_revision(config,run,draft)
    report=read_json(run/'storyboard.json');path=owner._review_path(run,Path(report['review_identity']['path']))
    ids['review']=owner._review(run,path,draft,ids['draft'],origin_report=draft)
    if not same_identity(ids['review'],report['review_identity']):raise ValueError('revision author review changed')
    expected=dict(draft,status='completed',passed=True,validation=owner._validation(True),review_identity=report['review_identity'])
    if report!=expected:raise ValueError('revision formal report differs from reviewed draft')
    if len(stage['artifacts'])!=1:raise ValueError('revision stage artifact coverage differs')
    ids['report']=owner._fresh(stage['artifacts'][0],run=run,expected=run/'storyboard.json')
    if not same_identity(ids['report'],snapshot['workflows']['storyboard_report']):raise ValueError('revision report workflow differs')
    _again(ids)
    if store.snapshot()!=snapshot:raise ValueError('revision manifest changed during consumption')
    return report
