"""Exclusive active-model namespaces for author-bound Comfy executions."""
import os
from pathlib import Path

from ..config import load_config,read_json
from .manifest import ManifestStore,hash_file,thaw,now
from .pipeline_import import fresh,same_identity,write_exclusive,keys,load_pipeline_import
from .timeline_checks import _run_path,_local

ROLES={'sdxl':('sdxl',),'wan':('wan_high','wan_low','text_encoder','vae'),'upscale':('upscale',)}
CATEGORIES={'sdxl':'checkpoints','wan_high':'diffusion_models','wan_low':'diffusion_models',
    'text_encoder':'text_encoders','vae':'vae','upscale':'upscale_models'}
STAGES={'sdxl':'start_images','wan':'source_clips','upscale':'upscale'}
KINDS={'sdxl':('image',),'wan':('shot','shot_attempt'),'upscale':('frame',)}


def _files(config,stage):
    workflow=config.workflows[stage]
    files={role:config.models[role] for role in ROLES[stage]}
    return dict(files,workflow=workflow,mapping=config.workflows['wan_mapping'] if stage=='wan' else workflow.with_suffix('.mapping.json'))


def _loader(config):
    root=config.tools['comfy_root']
    if any((root/name).exists() or (root/name).is_symlink() for name in ('extra_model_paths.yaml','extra_model_paths.yml')):
        raise ValueError('extra model paths would change the isolated loader namespace')
    return {name:hash_file(root/name) for name in ('folder_paths.py','main.py')}


def binding_identities(binding):
    """Expose every actual loader leaf to partial/full origin collectors."""
    identity=fresh(binding['identity']);proof=read_json(Path(identity.path))
    result={'model_loader_binding':identity,'model_loader_config':fresh(proof['config_identity']),
        'model_loader_authorization':fresh(proof['authorization_identity'])}
    result.update({'model_loader_code/'+name:fresh(value) for name,value in proof['loader_identities'].items()})
    for name,row in proof['models'].items():
        result['model_loader_source/'+name]=fresh(row['source_identity'])
        result['model_loader_link/'+name]=fresh(row['link_identity'])
    return result


def _imported_binding(config,run,stage,snapshot):
    """Wholly imported completed media retains its actual origin loader proof."""
    if snapshot['stages'][STAGES[stage]]['status']!='completed':return None
    receipt=load_pipeline_import(run)
    rows=[row for row in receipt['stages'] if row['id']==STAGES[stage]]
    if len(rows)!=1 or rows[0]['source_record']['status']!='completed':return None
    units=[unit for kind in KINDS[stage] for unit in snapshot['units'].get(kind,{}).values()]
    if not units or any(unit['submission'] is not None for unit in units):return None
    parent=run.parent/receipt['parent_run_id'];old=ManifestStore.open(parent).snapshot()
    original=load_config(Path(old['config_snapshot']['path']))
    binding=prepare_or_consume_model_binding(original,parent,stage)
    if binding is None:raise ValueError('imported revised model has no original loader binding')
    identity=binding['identity'];bound=receipt['source_identities'].get(identity.path)
    if bound is None or not same_identity(identity,fresh(bound)):raise ValueError('original loader proof absent from immutable import closure')
    proof=read_json(Path(identity.path))
    for role in ROLES[stage]:
        old=fresh(proof['models'][role]['source_identity']);current=hash_file(config.models[role])
        if (old.bytes,old.sha256)!=(current.bytes,current.sha256):raise ValueError('imported current model bytes differ from actual original loader')
    return binding


def prepare_or_consume_model_binding(config,run,stage, *, create=False):
    """Return root/identity; only explicit producer calls may create a binding."""
    if stage not in ROLES or type(create) is not bool:raise ValueError('unsupported active model stage')
    from ._pipeline_model_admission import revised_files
    run=_run_path(run);store=ManifestStore.open(run);snapshot=store.snapshot()
    admitted=revised_files(config,run,_files(config,stage))
    if admitted is None:return None
    root=_local(run,run/'comfy/model-bindings'/stage)
    proof_path=_local(run,run/'logs/pipeline'/('model-binding-'+stage+'.json'))
    key='pipeline_model_binding_'+stage;registered=snapshot['workflows'].get(key)
    loaders=_loader(config)
    if registered is None:
        inherited=_imported_binding(config,run,stage,snapshot)
        if inherited is not None:return inherited
        if not create:raise ValueError('revised model loader binding missing')
        if snapshot['stages'][STAGES[stage]]['status'] not in ('pending','running'):
            raise ValueError('model binding creation requires a new producer')
        if any(unit['submission'] is not None for kind in KINDS[stage] for unit in snapshot['units'].get(kind,{}).values()):
            raise ValueError('submitted execution cannot mint missing model loader evidence')
        if root.exists() or root.is_symlink() or proof_path.exists() or proof_path.is_symlink():
            raise ValueError('orphan model binding must not be overwritten')
        expected={}
        for role in ROLES[stage]:
            source=fresh(admitted[role]);target=root/CATEGORIES[role]/Path(source.path).name
            folded=str(target).casefold()
            if folded in expected:raise ValueError('active model loader filename collision')
            expected[folded]=(role,source,target)
        root.mkdir(parents=True,exist_ok=False);models={}
        for role,source,target in expected.values():
            target=_local(run,target);target.parent.mkdir(parents=True,exist_ok=True)
            try:os.link(source.path,target)
            except OSError as exc:raise ValueError('active model projection requires an exclusive same-volume hardlink') from exc
            linked=hash_file(target);fresh(source)
            if not target.samefile(source.path) or (linked.bytes,linked.sha256,linked.mtime_ns)!=(source.bytes,source.sha256,source.mtime_ns):
                raise ValueError('active model hardlink identity differs')
            models[role]=dict(category=CATEGORIES[role],loader_name=target.name,source_identity=thaw(source),link_identity=thaw(linked))
        proof=dict(schema_version=1,run_id=run.name,stage=stage,created_at=now(),root=str(root),
            config_identity=thaw(hash_file(config.config_file)),authorization_identity=thaw(admitted['revision_authorization']),
            loader_identities=thaw(loaders),models=models)
        registered=write_exclusive(run,proof_path,proof)
        def register(data):
            if key in data['workflows']:raise ValueError('concurrent model loader registration')
            data['workflows'][key]=thaw(registered)
        store.update(register)
    identity=fresh(registered)
    if Path(identity.path)!=proof_path:raise ValueError('model loader proof must be canonical')
    proof=read_json(proof_path)
    keys(proof,'schema_version run_id stage created_at root config_identity authorization_identity loader_identities models','model loader proof')
    from .manifest import _timestamp
    _timestamp(proof['created_at'])
    if type(proof['schema_version']) is not int or proof['schema_version']!=1 or proof['run_id']!=run.name or proof['stage']!=stage or proof['root']!=str(root):
        raise ValueError('model loader proof scope differs')
    if not same_identity(hash_file(config.config_file),fresh(proof['config_identity'])) or not same_identity(admitted['revision_authorization'],fresh(proof['authorization_identity'])):
        raise ValueError('model loader current authorization/config differs')
    if set(proof['loader_identities'])!=set(loaders) or any(not same_identity(value,fresh(proof['loader_identities'][name])) for name,value in loaders.items()):
        raise ValueError('actual installed model loader changed')
    if set(proof['models'])!=set(ROLES[stage]):raise ValueError('active model loader coverage differs')
    expected_paths=set()
    for role,row in proof['models'].items():
        keys(row,'category loader_name source_identity link_identity','model loader entry')
        source=fresh(row['source_identity']);linked=fresh(row['link_identity'])
        target=_local(run,root/CATEGORIES[role]/config.models[role].name)
        if row['category']!=CATEGORIES[role] or row['loader_name']!=target.name or Path(linked.path)!=target or not same_identity(source,admitted[role]):
            raise ValueError('model loader role/path mapping differs')
        if not target.samefile(source.path) or (linked.bytes,linked.sha256,linked.mtime_ns)!=(source.bytes,source.sha256,source.mtime_ns):
            raise ValueError('model loader hardlink no longer binds original bytes')
        expected_paths.update((target,target.parent))
    actual={_local(run,path) for path in root.rglob('*')}
    if actual!=expected_paths:raise ValueError('extra model path or shadow alias in isolated loader namespace')
    fresh(identity)
    return dict(root=root,identity=identity)
