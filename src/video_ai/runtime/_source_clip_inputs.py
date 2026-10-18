"""Fresh input receipts and the accepted, complete fixed Wan graph."""
import json
from pathlib import Path

from ..config import read_json
from ..planning.source_clips import plan_source_clips, WAN_NEGATIVE
from ..planning.start_images import keys
from .manifest import hash_file, thaw, _identity
from .paths import SOURCE_ROOT
from .timeline_checks import _local, _fresh as artifact_fresh, _again
from .storyboard_checks import load_committed_storyboard
from .timeline_checks import load_committed_timeline
from .start_image_checks import load_committed_start_images
from .workflows import WorkflowTemplate

TASK4_ACCEPTANCE = Path('D:/VideoSi/projects/video-ai/runs/20261004-040653-a0fcd961cc58/task4-acceptance.json')
MODEL_NAMES = ('wan_high', 'wan_low', 'text_encoder', 'vae')


def same(a, b):
    return json.dumps(thaw(a), sort_keys=True, allow_nan=False) == json.dumps(thaw(b), sort_keys=True, allow_nan=False)


def fresh(record, *, run=None, expected=None):
    """New stage FileIdentity receipts require mtime as well as bytes and SHA."""
    _identity(record)
    if any(v is None for v in record.values()):
        raise ValueError('complete source clip identity required')
    identity = artifact_fresh(record, run=run, expected=expected)
    if identity.mtime_ns != record['mtime_ns']:
        raise OSError(f'source clip identity mtime changed: {identity.path}')
    if str(Path(record['path']).resolve(strict=True)) != record['path']:
        raise ValueError('identity path is not canonical')
    return identity


def template(config, *, revision=None):
    workflow, mapping = config.workflows['wan'], config.workflows['wan_mapping']
    if revision is None and (workflow != SOURCE_ROOT/'workflows/wan22_i2v_14b_api.json' or mapping != workflow.with_suffix('.mapping.json')):
        raise ValueError('fixed Wan workflow and corresponding mapping required')
    t = WorkflowTemplate.load(workflow, mapping, config.models)
    if not same(t.graph, read_json(workflow)) or not same(t.mapping, read_json(mapping)):
        raise ValueError('loaded Wan graph/mapping differs from actual files')
    if revision is None and hash_file(workflow).sha256 != '5f3768f6e83bf6be21287457c7c15e811d8f6949b7b5c5ac5460c267c8f98666':
        raise ValueError('fixed complete Wan graph changed')
    if revision is not None:
        from ._pipeline_model_admission import fixed_graph
        baseline=SOURCE_ROOT/'workflows/wan22_i2v_14b_api.json'
        fixed_graph(t,read_json(baseline),read_json(baseline.with_suffix('.mapping.json')))
    g = t.graph
    checks = [('129:131','value',False), ('129:128','value',40), ('129:127','value',15),
              ('129:126','value',3.5), ('129:104','shift',5.000000000000001),
              ('129:103','shift',5.000000000000001), ('129:98','batch_size',1),
              ('129:89','text',WAN_NEGATIVE), ('108','format','mp4'), ('108','format.codec','h264')]
    for node, field, value in checks:
        if not same(g[node]['inputs'].get(field), value):
            raise ValueError('fixed Wan sampling/output baseline changed')
    for node, noise, start, end, leftover in [('129:86','enable',0,['129:125',0],'enable'), ('129:85','disable',['129:125',0],['129:119',0],'disable')]:
        wanted=dict(add_noise=noise,start_at_step=start,end_at_step=end,return_with_leftover_noise=leftover,
                    sampler_name='euler',scheduler='simple')
        if any(not same(g[node]['inputs'].get(k),v) for k,v in wanted.items()):
            raise ValueError('fixed Wan high/low sampling baseline changed')
    return t


def models(config, *, revision=None):
    acceptance_id=hash_file(TASK4_ACCEPTANCE);acceptance=read_json(TASK4_ACCEPTANCE)
    if acceptance.get('components',{}).get('wan',{}).get('passed') is not True:
        raise ValueError('accepted Task4 Wan component required')
    inventory_id=fresh(acceptance['provenance']['wan']['before'])
    inventory=read_json(Path(inventory_id.path));ids={}
    for name,path in [(n,config.models[n]) for n in MODEL_NAMES]+[('workflow',config.workflows['wan']),('mapping',config.workflows['wan_mapping'])]:
        record=thaw(revision[name]) if revision is not None else inventory.get(str(path.resolve(strict=True)))
        if record is None:raise ValueError(f'Wan {name} absent from accepted full inventory')
        ids[name]=fresh(record,expected=path)
    ids.update(task4_acceptance=acceptance_id,wan_inventory=inventory_id)
    if revision is not None:
        ids['revision_authorization']=revision['revision_authorization']
        ids.update(revision.get('model_loader_identities',{}))
    _again(ids)
    return ids


def inputs(config,run):
    from .manifest import ManifestStore
    from .pipeline_import import stage_draft_path,fresh_origin_review
    snapshot=ManifestStore.open(run).snapshot()
    resolved=thaw(config);resolved.pop('voice');resolved.pop('raw')
    if config.config_file!=Path(snapshot['config_snapshot']['path']) or not same(config.raw,snapshot['config_snapshot']['raw']) or not same(resolved,snapshot['config_snapshot']['resolved']):
        raise ValueError('source config differs from frozen run configuration')
    board=load_committed_storyboard(run);timeline=thaw(load_committed_timeline(run));images=load_committed_start_images(run)
    plans=plan_source_clips(board,timeline,images)
    from ._pipeline_model_admission import revised_files
    revision=revised_files(config,run,{**{n:config.models[n] for n in MODEL_NAMES},'workflow':config.workflows['wan'],'mapping':config.workflows['wan_mapping']},model_stage='wan')
    ids=models(config,revision=revision);t=template(config,revision=revision)
    ids['config']=fresh(snapshot['inputs']['config'],expected=config.config_file)
    for name in ('images','storyboard','timeline'):
        ids[name]=hash_file(_local(run,run/(name+'.json')))
    for name,path in [('ffmpeg',config.tools['ffmpeg']),('ffprobe',config.tools['ffprobe']),
        ('storyboard_draft',stage_draft_path(run,'storyboard',board)),('storyboard_review',Path(board['review_identity']['path'])),
        ('images_draft',stage_draft_path(run,'start_images',images)),('images_review',Path(images['review_identity']['path'])),
        ('timing_review',Path(board['timing_review_identity']['path']))]:
        ids[name]=hash_file(_local(run,path) if path.is_relative_to(run) else path)
    for name,record in [('storyboard_review',board['review_identity']),('images_review',images['review_identity']),('timing_review',board['timing_review_identity'])]:
        fresh_origin_review(run,images if name=='images_review' else board,record)
    contract=_local(run,run/'logs/storyboard/visual-contract.json')
    if contract.exists():ids['visual_contract']=hash_file(contract)
    for plan in plans:
        ids['start/'+plan.shot_id]=fresh(thaw(plan.start_image_identity),run=run,expected=run/'shots'/plan.shot_id/'start.png')
    _again(ids)
    provenance={n+'_identity':thaw(ids[n]) if n in ids else None for n in ('config','ffmpeg','ffprobe','storyboard_draft','storyboard_review','images_draft','images_review','timing_review','visual_contract','task4_acceptance','wan_inventory')}
    if revision is not None:
        provenance['revision_authorization_identity']=thaw(revision['revision_authorization'])
        provenance['model_loader_binding_identity']=thaw(revision['model_loader_binding'])
    return dict(board=board,timeline=timeline,images=images,plans=plans,identities=ids,template=t,provenance=provenance)


def graph(t,run,plan,requested,attempt):
    p=plan.parameters
    return t.instantiate(dict(positive_prompt=p['positive'],start_image=f'{run.name}/source_clips/{plan.shot_id}/start.png',
        width=p['width'],height=p['height'],length=requested,fps=p['fps'],seed_high=p['seed_high'],seed_low=p['seed_low']),
        output_prefix=f'{run.name}/source_clips/{plan.shot_id}/{attempt}')


def evidence(run,records,paths):
    names=[]
    for path in paths:
        path=_local(run,path);name=path.relative_to(run).as_posix()
        if name not in records:records[name]=thaw(hash_file(path))
        if name not in names:names.append(name)
    return names
