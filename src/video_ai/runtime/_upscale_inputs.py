"""Fresh source acceptance, fixed PyTorch graph and Task4 full-file inventory."""
from pathlib import Path
import shutil

from ..config import read_json
from ..planning.upscale import plan_upscale
from .manifest import ManifestStore,FileIdentity,hash_file,thaw
from .paths import SOURCE_ROOT
from .timeline_checks import _local,_again
from .source_clip_checks import load_committed_source_clips
from ._source_clip_inputs import fresh,same,evidence
from .workflows import WorkflowTemplate

TASK4_ACCEPTANCE=Path('D:/VideoSi/projects/video-ai/runs/20261004-040653-a0fcd961cc58/task4-acceptance.json')
MODEL_PATH=Path('D:/VideoSi/models/comfyui/upscale_models/RealESRGAN_x4plus.pth')
MODEL_SHA='4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1'
TEMPLATE_SHA='a647f05940ce6b59de9bde8d5d53b9300bfe6b5174d900b3324eb6cd01680533'
FIXED_GRAPH={
    '1':dict(class_type='LoadImage',inputs=dict(image='<inputName>')),
    '2':dict(class_type='UpscaleModelLoader',inputs=dict(model_name='RealESRGAN_x4plus.pth')),
    '3':dict(class_type='ImageUpscaleWithModel',inputs=dict(upscale_model=['2',0],image=['1',0])),
    '4':dict(class_type='ImageScale',inputs=dict(image=['3',0],upscale_method='lanczos',width=1920,height=1080,crop='disabled')),
    '5':dict(class_type='SaveImage',inputs=dict(images=['4',0],filename_prefix='<prefix>'))}


def template(config, *, revision=None):
    workflow=config.workflows['upscale'];mapping=workflow.with_suffix('.mapping.json')
    if revision is None and workflow!=SOURCE_ROOT/'workflows/upscale_api.json':raise ValueError('fixed upscale workflow required')
    t=WorkflowTemplate.load(workflow,mapping,config.models)
    if (revision is None and (hash_file(workflow).sha256!=TEMPLATE_SHA or not same(t.graph,FIXED_GRAPH))) or not same(t.graph,read_json(workflow)) or not same(t.mapping,read_json(mapping)):
        raise ValueError('complete fixed five-node upscale graph/mapping differs')
    if revision is not None:
        from ._pipeline_model_admission import fixed_graph
        fixed_graph(t,FIXED_GRAPH,read_json((SOURCE_ROOT/'workflows/upscale_api.json').with_suffix('.mapping.json')))
    if not same(t.mapping['inputs'],dict(image=dict(node_id='1',input='image'),output_prefix=dict(node_id='5',input='filename_prefix'))) or not same(t.mapping['models'],dict(upscale=dict(node_id='2',input='model_name'))) or not same(t.mapping['output'],dict(node_id='5',collection='images')):
        raise ValueError('fixed upscale mapping differs')
    return t


def validate_remote(t,info):
    t.validate_remote(info)
    for node in t.graph.values():
        remote=info[node['class_type']].get('input',{})
        fields=set(remote.get('required',{}))|set(remote.get('optional',{}))
        if not set(node['inputs'])<=fields:raise ValueError('remote complete upscale input fields missing: '+node['class_type'])


def models(config, *, revision=None):
    if revision is None and config.models['upscale']!=MODEL_PATH:raise ValueError('fixed real PyTorch model path required')
    acceptance_id=hash_file(TASK4_ACCEPTANCE);acceptance=read_json(TASK4_ACCEPTANCE)
    if acceptance.get('components',{}).get('upscale',{}).get('passed') is not True:raise ValueError('Task4 accepted upscale component required')
    inventory_id=fresh(acceptance['provenance']['upscale']['before']);inventory=read_json(Path(inventory_id.path))
    ids={}
    for name,path in [('model',config.models['upscale']),('workflow',config.workflows['upscale']),('mapping',config.workflows['upscale'].with_suffix('.mapping.json'))]:
        record=thaw(revision[name]) if revision is not None else inventory.get(str(path.resolve(strict=True)))
        if record is None:raise ValueError('upscale file absent from accepted Task4 full inventory')
        ids[name]=fresh(record,expected=path)
    if revision is None and (ids['model'].sha256!=MODEL_SHA or ids['workflow'].sha256!=TEMPLATE_SHA):raise ValueError('fixed accepted model/template bytes changed')
    if revision is not None:
        ids['revision_authorization']=revision['revision_authorization']
        ids.update(revision.get('model_loader_identities',{}))
    ids.update(task4_acceptance=acceptance_id,upscale_inventory=inventory_id);_again(ids)
    return ids


def required_capacity(source):
    return sum(c['source_frames']*(2*c['width']*c['height']*3+2*1920*1080*3+3*65536) for c in source['clips'])+2*1024**3


def inputs(config,run):
    source=load_committed_source_clips(run);snapshot=ManifestStore.open(run).snapshot()
    resolved=thaw(config);resolved.pop('voice');resolved.pop('raw')
    if config.config_file!=Path(snapshot['config_snapshot']['path']) or not same(config.raw,snapshot['config_snapshot']['raw']) or not same(resolved,snapshot['config_snapshot']['resolved']):
        raise ValueError('upscale configuration differs from frozen run')
    planning_source=dict(source)
    if source.get('schema_version')==2:
        # The completed source consumer above validates import provenance. The
        # pure planner retains its original exact media schema unchanged.
        planning_source.pop('import_identity');planning_source.pop('reused_units');planning_source['schema_version']=1
    from ._pipeline_model_admission import revised_files
    revision=revised_files(config,run,dict(model=config.models['upscale'],workflow=config.workflows['upscale'],mapping=config.workflows['upscale'].with_suffix('.mapping.json')),model_stage='upscale')
    plans=plan_upscale(planning_source);ids=models(config,revision=revision);t=template(config,revision=revision)
    ids['config']=fresh(snapshot['inputs']['config'],expected=config.config_file)
    ids['source_clips']=hash_file(_local(run,run/'source-clips.json'))
    from .pipeline_import import fresh_origin_review
    ids['source_review']=fresh_origin_review(run,source,source['review_identity'])
    method=read_json(Path(ids['source_review'].path))['review_method']
    if method not in ('human_video','agent_video','user_acceptance'):raise ValueError('accepted source review method required')
    for name in ('ffmpeg','ffprobe'):ids[name]=hash_file(config.tools[name])
    for plan in plans:ids['source/'+plan.shot_id]=fresh(thaw(plan.source_identity),run=run,expected=run/'shots'/plan.shot_id/'source.mp4')
    _again(ids)
    provenance={name+'_identity':thaw(ids[name]) for name in ('config','ffmpeg','ffprobe','task4_acceptance','upscale_inventory')}
    if revision is not None:
        provenance['revision_authorization_identity']=thaw(revision['revision_authorization'])
        provenance['model_loader_binding_identity']=thaw(revision['model_loader_binding'])
    return dict(source=source,plans=plans,identities=ids,template=t,provenance=provenance,source_review_method=method,revision=revision)


def generated_inputs(config,run):
    """Use producer receipts without rechecking the upstream dependency tree.

    This explicit opt-out trusts existing generated inputs. Receipt hashes and
    timestamps stay as recorded; they are not reported as freshly verified.
    Newly generated outputs still receive their own identities.
    """
    source=read_json(_local(run,run/'source-clips.json'))
    planning_source=dict(source)
    if source.get('schema_version')==2:
        planning_source.pop('import_identity');planning_source.pop('reused_units')
        planning_source['schema_version']=1
    plans=plan_upscale(planning_source)
    acceptance=read_json(TASK4_ACCEPTANCE)
    inventory_record=acceptance['provenance']['upscale']['before']
    inventory=read_json(Path(inventory_record['path']))
    model_record=inventory[str(config.models['upscale'].resolve(strict=True))]
    ids=dict(model=FileIdentity(**model_record),
        workflow=hash_file(config.workflows['upscale']),
        mapping=hash_file(config.workflows['upscale'].with_suffix('.mapping.json')),
        config=hash_file(config.config_file),source_clips=hash_file(run/'source-clips.json'),
        source_review=FileIdentity(**source['review_identity']),
        task4_acceptance=hash_file(TASK4_ACCEPTANCE),upscale_inventory=FileIdentity(**inventory_record))
    for name in ('ffmpeg','ffprobe'):
        recorded=source.get('provenance',{}).get(name+'_identity')
        ids[name]=FileIdentity(**recorded) if recorded is not None else hash_file(config.tools[name])
    for plan in plans:ids['source/'+plan.shot_id]=FileIdentity(**thaw(plan.source_identity))
    method=read_json(Path(ids['source_review'].path))['review_method']
    provenance={name+'_identity':thaw(ids[name]) for name in ('config','ffmpeg','ffprobe','task4_acceptance','upscale_inventory')}
    return dict(source=source,plans=plans,identities=ids,template=template(config),
        provenance=provenance,source_review_method=method,revision=None,verify_integrity=False)


def graph(t,run,plan,index):
    frame=f'frame_{index:06d}'
    return t.instantiate(dict(image=f'{run.name}/upscale/{plan.shot_id}/{frame}.png'),
        output_prefix=f'{run.name}/upscale/{plan.shot_id}/{frame}')


def before_post(config,run,context,plan,input_row,copied,actual):
    if 'model_loader_binding' in context['identities']:
        from ._pipeline_model_paths import prepare_or_consume_model_binding
        prepare_or_consume_model_binding(config,run,'upscale')
    _again({k:context['identities'][k] for k in ('model','workflow','mapping','config','source/'+plan.shot_id)})
    fresh(input_row['identity'],run=run);fresh(thaw(copied),run=run)
    t=context['template'];current=template(config,revision=context.get('revision'))
    if not same(t.graph,current.graph) or not same(t.mapping,current.mapping) or not same(actual,graph(current,run,plan,input_row['index'])):
        raise ValueError('loaded or actual complete upscale graph differs before POST')
