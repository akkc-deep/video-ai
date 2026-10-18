"""TEST ONLY active model bindings; installed folder_paths is loaded read-only."""
from pathlib import Path
import importlib.util
import sys
from types import ModuleType,SimpleNamespace

import pytest
from source_clip_helpers import write


def fixture(runtime_run,monkeypatch,stage):
    from video_ai.config import load_config
    from video_ai.runtime.manifest import create_manifest,hash_file,thaw,now
    from video_ai.runtime.paths import create_run,RuntimePaths
    from video_ai.runtime.pipeline_import import create_pipeline_import
    parent,original,_=runtime_run
    old=create_manifest(parent,original,inputs={},models={},workflows={})
    raw=thaw(original.raw);raw['voice_config']=str(original.voice.config_file)
    raw['workflows']={k:str(v) for k,v in original.workflows.items()}
    roles={'sdxl':('sdxl',),'wan':('wan_high','wan_low','text_encoder','vae'),'upscale':('upscale',)}[stage]
    for role in roles:
        target=parent/'explicit-models'/role/original.models[role].name
        target.parent.mkdir(parents=True);target.write_bytes(('TEST ONLY active revised '+role).encode())
        raw['models'][role]=str(target)
    config=load_config(write(parent/'revised-config.json',raw))
    child=create_run(RuntimePaths.from_config(config));create_manifest(child,config,inputs={'config':hash_file(config.config_file)},models={},workflows={})
    base=write(parent/'TEST-ONLY-base.json',old.snapshot())
    changes=write(parent/'TEST-ONLY-changes.json',dict(schema_version=1,base_run_id=parent.name,
        base_manifest_snapshot_identity=thaw(hash_file(base)),created_at=now(),reason='TEST ONLY active models',
        script_identity=None,unit_review_identity=None,config_identity=thaw(hash_file(config.config_file)),shot_changes=[]))
    workflow=config.workflows['wan' if stage=='wan' else stage]
    files=[*[config.models[role] for role in roles],workflow,workflow.with_suffix('.mapping.json')]
    create_pipeline_import(config,run_dir=child,parent_run_dir=parent,reason='TEST ONLY',changes_identity=hash_file(changes),
        copies=[],source_identities={str(p):thaw(hash_file(p)) for p in files})
    return config,child,roles


def installed_resolver(config,root,monkeypatch):
    # Import the actual installed resolver with only its CLI argument dependency
    # substituted. This starts no Comfy service and imports no model code.
    args=ModuleType('comfy.cli_args');args.args=SimpleNamespace(base_directory=None,models_directory=str(root))
    monkeypatch.setitem(sys.modules,'comfy.cli_args',args)
    path=config.tools['comfy_root']/'folder_paths.py'
    spec=importlib.util.spec_from_file_location('TEST_ONLY_installed_folder_paths',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('stage',['sdxl','wan','upscale'])
def test_bound_active_model_root_resolves_exact_admitted_bytes_with_installed_loader(runtime_run,monkeypatch,stage):
    from video_ai.runtime._pipeline_model_paths import prepare_or_consume_model_binding
    from video_ai.runtime.manifest import ManifestStore
    config,run,roles=fixture(runtime_run,monkeypatch,stage)
    with pytest.raises(ValueError,match='missing'):
        prepare_or_consume_model_binding(config,run,stage)
    result=prepare_or_consume_model_binding(config,run,stage,create=True)
    loader=installed_resolver(config,result['root'],monkeypatch)
    categories={'sdxl':'checkpoints','wan_high':'diffusion_models','wan_low':'diffusion_models','text_encoder':'text_encoders','vae':'vae','upscale':'upscale_models'}
    for role in roles:
        selected=Path(loader.get_full_path_or_raise(categories[role],config.models[role].name))
        assert selected.is_relative_to(result['root']) and selected.samefile(config.models[role])
        assert selected.read_bytes()==('TEST ONLY active revised '+role).encode()
    assert len([p for p in result['root'].rglob('*') if p.is_file()])==len(roles)
    before=ManifestStore.open(run).snapshot()
    assert prepare_or_consume_model_binding(config,run,stage)['root']==result['root']
    assert ManifestStore.open(run).snapshot()==before


@pytest.mark.parametrize('drift',['source','link_replacement','shadow','proof','missing_proof'])
def test_binding_rejects_model_link_mapping_or_shadow_drift_without_recreation(runtime_run,monkeypatch,drift):
    from video_ai.runtime._pipeline_model_paths import prepare_or_consume_model_binding
    config,run,_=fixture(runtime_run,monkeypatch,'upscale')
    result=prepare_or_consume_model_binding(config,run,'upscale',create=True)
    link=result['root']/'upscale_models'/config.models['upscale'].name
    if drift=='source':config.models['upscale'].write_bytes(b'TEST ONLY source drift')
    elif drift=='link_replacement':
        data=link.read_bytes();stamp=link.stat().st_mtime_ns;link.unlink();link.write_bytes(data)
        import os
        os.utime(link,ns=(stamp,stamp))
    elif drift=='shadow':(result['root']/'unet').mkdir()
    elif drift=='proof':Path(result['identity'].path).write_bytes(b'{}')
    else:Path(result['identity'].path).unlink()
    with pytest.raises((ValueError,OSError)):
        prepare_or_consume_model_binding(config,run,'upscale',create=True)
