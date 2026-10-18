from pathlib import Path
import pytest

from video_ai.runtime.pipeline_inventory import config_projection


def configuration(workflow, mapping=None):
    workflows = {'upscale': str(workflow)}
    if mapping is not None: workflows['sdxl_mapping'] = str(mapping)
    return dict(models={}, tools={}, workflows=workflows, media={}, voice={})


def test_implicit_and_explicit_mapping_capture_same_identity(tmp_path):
    workflow = tmp_path/'upscale.json'; workflow.write_bytes(b'{}')
    mapping = tmp_path/'upscale.mapping.json'; mapping.write_bytes(b'{"version":1}')
    identities = {}
    projection = config_projection(configuration(workflow, mapping), identities)
    assert str(mapping.resolve()) in identities
    assert 'derived_workflows' in projection, 'implicit upscale mapping is absent from config dependencies'
    assert projection['derived_workflows']['upscale_mapping']['sha256'] == projection['workflows']['sdxl_mapping']['sha256']


def test_missing_implicit_mapping_refuses_before_execution(tmp_path):
    workflow = tmp_path/'upscale.json'; workflow.write_bytes(b'{}')
    with pytest.raises(OSError):
        config_projection(configuration(workflow), {})


def test_captured_mapping_content_drift_rejected_even_with_same_mtime(tmp_path):
    import os
    workflow = tmp_path/'upscale.json'; workflow.write_bytes(b'{}')
    mapping = tmp_path/'upscale.mapping.json'; mapping.write_bytes(b'{"version":1}')
    identities = {}; config_projection(configuration(workflow), identities)
    old = mapping.stat(); mapping.write_bytes(b'{"version":2}')
    os.utime(mapping, ns=(old.st_atime_ns, old.st_mtime_ns))
    with pytest.raises((OSError, ValueError), match='drift|changed'):
        config_projection(configuration(workflow), identities)


def test_new_derived_import_contains_implicit_mapping_and_refuses_drift(runtime_run):
    from dataclasses import replace
    from video_ai.runtime.manifest import create_manifest
    from video_ai.runtime.pipeline_import import derive_completed_stages, load_pipeline_import
    run, config, _ = runtime_run
    workflow=run/'TEST-ONLY-upscale.json';workflow.write_bytes(b'{}')
    mapping=workflow.with_suffix('.mapping.json');mapping.write_bytes(b'{"version":1}')
    config=replace(config,workflows=dict(config.workflows,upscale=workflow))
    create_manifest(run,config,inputs={},models={},workflows={})
    child = derive_completed_stages(config,parent_run_dir=run,stages=(),reason='TEST ONLY mapping closure')
    mapping = config.workflows['upscale'].with_suffix('.mapping.json')
    assert str(mapping.resolve()) in load_pipeline_import(child)['source_identities']
    mapping.write_bytes(b'{"version":2}')
    with pytest.raises(ValueError,match='drift'):
        load_pipeline_import(child)


def test_historical_closure_without_mapping_still_refuses_revision(runtime_run):
    import json
    from video_ai.runtime.paths import create_run,RuntimePaths
    from video_ai.runtime.manifest import create_manifest,hash_file,thaw,now
    from video_ai.runtime.pipeline_import import create_pipeline_import
    from video_ai.runtime._pipeline_model_admission import revised_files
    run,config,_=runtime_run
    create_manifest(run,config,inputs={},models={},workflows={})
    child=create_run(RuntimePaths.from_config(config))
    create_manifest(child,config,inputs={},models={},workflows={})
    snapshot=run/'base.json';snapshot.write_bytes((run/'manifest.json').read_bytes())
    changes=run/'changes.json'
    changes.write_text(json.dumps(dict(schema_version=1,base_run_id=run.name,
        base_manifest_snapshot_identity=thaw(hash_file(snapshot)),created_at=now(),reason='TEST ONLY old closure',
        script_identity=None,unit_review_identity=None,config_identity=thaw(hash_file(config.config_file)),shot_changes=[])),encoding='utf-8')
    create_pipeline_import(config,run_dir=child,parent_run_dir=run,reason='TEST ONLY old closure',
        source_identities={},copies=[],changes_identity=hash_file(changes))
    with pytest.raises(ValueError,match='mapping'):
        revised_files(config,child,{'mapping':config.workflows['upscale'].with_suffix('.mapping.json')})
