"""TEST ONLY SDXL revised admission retains complete fixed graph checks."""
from pathlib import Path
import pytest
from source_clip_helpers import write


@pytest.mark.parametrize('tamper',[None,'steps','link','extra'])
def test_author_bound_sdxl_revision_rechecks_complete_model_and_fixed_graph(runtime_run,monkeypatch,tamper):
    from video_ai.runtime import start_image_checks as s
    from video_ai.runtime._pipeline_model_admission import revised_files
    from video_ai.runtime.manifest import create_manifest,hash_file,thaw,now
    from video_ai.runtime.paths import create_run,RuntimePaths
    from video_ai.runtime.pipeline_import import create_pipeline_import
    from video_ai.config import load_config,read_json
    parent,original,_=runtime_run
    old_model=parent/original.models['sdxl'].name;old_model.write_bytes(b'TEST ONLY original SDXL')
    workflow=original.workflows['sdxl'];mapping=workflow.with_suffix('.mapping.json')
    inv=write(parent/'TEST-ONLY-inventory.json',{str(p):thaw(hash_file(p)) for p in (old_model,workflow,mapping)})
    accepted=write(parent/'TEST-ONLY-acceptance.json',dict(passed=True,components={'sdxl':{'passed':True}},
        provenance={'sdxl':{'before':thaw(hash_file(inv))}}))
    monkeypatch.setattr(s,'TASK4_ACCEPTANCE',accepted,raising=False)
    raw=thaw(original.raw);raw.update(voice_config=str(original.voice.config_file),workflows={k:str(v) for k,v in original.workflows.items()})
    raw['models']['sdxl']=str(old_model);config=load_config(write(parent/'TEST-ONLY-original.json',raw))
    store=create_manifest(parent,config,inputs={'config':hash_file(config.config_file)},models={},workflows={})
    new_model=parent/'revision'/old_model.name;new_model.parent.mkdir();new_model.write_bytes(b'TEST ONLY revised SDXL never loaded')
    graph=read_json(workflow);next(iter(graph.values()))['_meta']={'title':'TEST ONLY revised workflow'}
    if tamper=='steps':next(v for v in graph.values() if v['class_type']=='KSampler')['inputs']['steps']=26
    if tamper=='link':next(v for v in graph.values() if v['class_type']=='KSampler')['inputs']['positive']=['6',0]
    if tamper=='extra':graph['999']={'class_type':'UnapprovedNode','inputs':{}}
    new_workflow=write(parent/'revision'/workflow.name,graph)
    current_mapping=read_json(mapping);current_mapping['template_sha256']=hash_file(new_workflow).sha256
    if tamper=='extra':current_mapping['nodes']['999']='UnapprovedNode'
    new_mapping=write(new_workflow.with_suffix('.mapping.json'),current_mapping)
    raw['models']['sdxl']=str(new_model);raw['workflows']['sdxl']=str(new_workflow)
    current=load_config(write(parent/'revision/config.json',raw));child=create_run(RuntimePaths.from_config(current))
    create_manifest(child,current,inputs={'config':hash_file(current.config_file)},models={},workflows={})
    base=write(parent/'logs/pipeline/TEST-ONLY-base.json',store.snapshot())
    changes=write(parent/'logs/pipeline/TEST-ONLY-changes.json',dict(schema_version=1,base_run_id=parent.name,
        base_manifest_snapshot_identity=thaw(hash_file(base)),created_at=now(),reason='TEST ONLY SDXL explicit revision',
        script_identity=None,unit_review_identity=None,config_identity=thaw(hash_file(current.config_file)),shot_changes=[]))
    files=dict(model=new_model,workflow=new_workflow,mapping=new_mapping)
    create_pipeline_import(current,run_dir=child,parent_run_dir=parent,reason='TEST ONLY author-bound SDXL',
        changes_identity=hash_file(changes),copies=[],source_identities={str(p):thaw(hash_file(p)) for p in files.values()})
    with pytest.raises(ValueError):s._model(current)
    revision=revised_files(current,child,files)
    if tamper:
        with pytest.raises(ValueError):s._template(current,revision=revision)
    else:
        model,basis=s._model(current,revision=revision);template=s._template(current,revision=revision)
        assert model.sha256==hash_file(new_model).sha256 and template.graph==graph
        assert basis['revision_authorization']['sha256']==hash_file(changes).sha256
        new_model.write_bytes(b'TEST ONLY drift')
        with pytest.raises((ValueError,OSError)):revised_files(current,child,files)
