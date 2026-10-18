"""TEST ONLY sealed revisions, repeated stage dispatch and actual tiny media."""
from pathlib import Path
import json
import shutil

import pytest

from source_clip_helpers import write


def revised_config(f, *, operational=False,service_change=True):
    from video_ai.config import load_config,read_json
    from video_ai.runtime.manifest import hash_file,thaw
    raw=thaw(f.config.raw);raw['voice_config']=str(f.config.voice.config_file)
    raw['workflows']={k:str(v) for k,v in f.config.workflows.items()}
    if operational:
        if service_change:raw['services']['comfyui']='http://127.0.0.1:8190'
        raw.setdefault('timeouts',{})['comfy_request']=max(1,f.config.timeouts['comfy_request']//2)
        raw['timeouts']['upscale_frame']=max(1,f.config.timeouts['upscale_frame']//2)
    else:
        model=f.run/'revised-model'/f.config.models['upscale'].name
        model.parent.mkdir();model.write_bytes(b'TEST ONLY revised upscale model; never loaded')
        raw['models']['upscale']=str(model)
        graph=read_json(f.config.workflows['upscale'])
        next(iter(graph.values()))['_meta']={'title':'TEST ONLY revised workflow'}
        workflow=write(f.run/'revised-workflow'/f.config.workflows['upscale'].name,graph)
        mapping=read_json(f.config.workflows['upscale'].with_suffix('.mapping.json'))
        mapping['template_sha256']=hash_file(workflow).sha256
        write(workflow.with_suffix('.mapping.json'),mapping);raw['workflows']['upscale']=str(workflow)
    return load_config(write(f.run/('operational-config.json' if operational else 'revised-config.json'),raw))


def authorization(f,config):
    from video_ai.runtime.manifest import hash_file,thaw,now
    base=write(f.run/'logs/pipeline/TEST-ONLY-base.json',f.store.snapshot())
    return write(f.run/'logs/pipeline/TEST-ONLY-changes.json',dict(schema_version=1,base_run_id=f.run.name,
        base_manifest_snapshot_identity=thaw(hash_file(base)),created_at=now(),reason='TEST ONLY explicit revision',
        script_identity=None,unit_review_identity=None,config_identity=thaw(hash_file(config.config_file)),shot_changes=[]))


def current_files(config):
    return dict(model=config.models['upscale'],workflow=config.workflows['upscale'],mapping=config.workflows['upscale'].with_suffix('.mapping.json'))


def source_copy(f,run):
    from video_ai.runtime.manifest import hash_file,thaw,ManifestStore
    source=thaw(f.source);source['run_id']=run.name
    for index,clip in enumerate(source['clips']):
        target=run/'shots'/clip['shot_id']/'source.mp4';target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(f.run/'shots'/clip['shot_id']/'source.mp4',target);identity=thaw(hash_file(target))
        clip['source_identity']=source['frame_mappings'][index]['source_identity']=source['requirement_clips'][index]['actual_artifact']=identity
    source.update(schema_version=2,import_identity=ManifestStore.open(run).snapshot()['workflows']['pipeline_import'],
        reused_units={'TEST ONLY':'characterized upstream source consumer'})
    write(run/'source-clips.json',source)


def route_output(f,run):
    handler=f.transport.handler
    def route(request,timeout):
        response=handler(request,timeout)
        if request.method=='POST':
            graph=json.loads(request.data)['prompt']
            if hasattr(f,'active_model_root'):
                loader=next(row['inputs']['model_name'] for row in graph.values() if row['class_type']=='UpscaleModelLoader')
                actual=f.active_model_root/'upscale_models'/loader
                assert actual.samefile(f.active_model_source)
                assert actual.read_bytes()==f.active_model_source.read_bytes()
            prefix=graph['5']['inputs']['filename_prefix']
            generated=f.run/'comfy/output'/(prefix+'_00001_.png');copied=run/'comfy/output'/(prefix+'_00001_.png')
            copied.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(generated,copied)
        return response
    f.transport.handler=route


def check_service_model_root(f,monkeypatch,config):
    original=f.ug.ServiceManager.ensure
    def ensure(manager,spec):
        f.active_model_root=Path(spec.args[spec.args.index('--models-directory')+1])
        assert f.active_model_root.parent.name=='model-bindings' and f.active_model_root.name=='upscale'
        assert '--disable-all-custom-nodes' in spec.args
        f.active_model_source=config.models['upscale']
        return original(manager,spec)
    monkeypatch.setattr(f.ug.ServiceManager,'ensure',ensure)


@pytest.mark.parametrize('drift',[None,'authorization','model'])
def test_revised_upscale_interruption_then_ordinary_grandchild_dispatch(runtime_run,monkeypatch,drift):
    from upscale_helpers import setup,review
    from video_ai.adapters.common import AdapterError,FailureKind
    from video_ai.runtime.manifest import create_manifest,ManifestStore,hash_file,thaw
    from video_ai.runtime.paths import create_run,RuntimePaths
    from video_ai.runtime.pipeline_import import create_pipeline_import,derive_partial_stage,load_pipeline_import
    from video_ai.runtime.pipeline_stages import prepare
    f=setup(runtime_run,monkeypatch,frames=2);config=revised_config(f);changes=authorization(f,config)
    check_service_model_root(f,monkeypatch,config)
    child=create_run(RuntimePaths.from_config(config))
    create_manifest(child,config,inputs={'config':hash_file(config.config_file)},models={},workflows={})
    files={**current_files(config),'review':Path(f.source['review_identity']['path'])}
    create_pipeline_import(config,run_dir=child,parent_run_dir=f.run,reason='TEST ONLY revised model child',
        changes_identity=hash_file(changes),copies=[],source_identities={str(p):thaw(hash_file(p)) for p in files.values()})
    source_copy(f,child);route_output(f,child)
    native=f.ug.ComfyClient.validate_template
    def stop(client,template):
        if client.http.unit_id.endswith('000002'):raise AdapterError(FailureKind.ambiguous,'TEST ONLY before next POST')
        return native(client,template)
    monkeypatch.setattr(f.ug.ComfyClient,'validate_template',stop)
    result=prepare('upscale',config,child,options={},reviews={},store=ManifestStore.open(child))
    assert result.status=='failed' and len(f.requests)==1
    monkeypatch.setattr(f.ug.ComfyClient,'validate_template',native)
    before=ManifestStore.open(child).snapshot()
    grandchild=derive_partial_stage(config,parent_run_dir=child,stage='upscale')
    source_copy(f,grandchild);route_output(f,grandchild);f.process.stopped=False
    assert load_pipeline_import(grandchild)['changes_identity'] is None
    if drift:
        target=changes if drift=='authorization' else config.models['upscale']
        target.write_bytes(target.read_bytes()+b'TEST ONLY later drift')
        with pytest.raises((ValueError,OSError)):
            prepare('upscale',config,grandchild,options={},reviews={},store=ManifestStore.open(grandchild))
        assert len(f.requests)==1
    else:
        result=prepare('upscale',config,grandchild,options={},reviews={},store=ManifestStore.open(grandchild))
        assert result.status=='review_required',ManifestStore.open(grandchild).snapshot()['stages']['upscale']['error']
        assert len(f.requests)==2
        draft=json.loads((grandchild/'upscaled-clips-draft.json').read_text(encoding='utf-8'))
        assert draft['model_identity']['sha256']==hash_file(config.models['upscale']).sha256
        assert draft['provenance']['revision_authorization_identity']['path']==str(changes)
        assert ManifestStore.open(grandchild).snapshot()['units']['frame']['shot_0001:frame_000001']['submission'] is None
        path,_=review(grandchild)
        assert f.uc.finalize_upscaled_clips(config,run_dir=grandchild,review_path=path).passed
        assert f.uc.load_committed_upscaled_clips(grandchild)['schema_version']==3
    assert ManifestStore.open(child).snapshot()==before


@pytest.mark.parametrize('service_change',[False,True])
def test_operational_revision_replays_old_upscale_prefix_and_dispatches_new_policy(runtime_run,monkeypatch,service_change):
    from unit.test_upscale_resume import stopped
    from upscale_helpers import review
    from video_ai.runtime.manifest import ManifestStore,hash_file,thaw
    from video_ai.runtime.pipeline_import import derive_completed_stages
    from video_ai.runtime.pipeline_stages import prepare
    f=stopped(runtime_run,monkeypatch);config=revised_config(f,operational=True,service_change=service_change);changes=authorization(f,config)
    check_service_model_root(f,monkeypatch,config)
    before=f.store.snapshot();historical={p:p.read_bytes() for p in (f.run/'logs/http').glob('*') if p.is_file()}
    child=derive_completed_stages(config,parent_run_dir=f.run,stages=(),partial_stages=('upscale',),
        changes_identity=hash_file(changes),reason='TEST ONLY service and request timeout revision',
        extra_source_identities={str(p):thaw(hash_file(p)) for p in current_files(config).values()})
    source_copy(f,child);route_output(f,child);f.process.stopped=False
    result=prepare('upscale',config,child,options={},reviews={},store=ManifestStore.open(child))
    assert result.status=='review_required',ManifestStore.open(child).snapshot()['stages']['upscale']['error']
    assert len(f.requests)==2 and f.store.snapshot()==before
    assert all(p.read_bytes()==value for p,value in historical.items())
    draft=json.loads((child/'upscaled-clips-draft.json').read_text(encoding='utf-8'))
    assert draft['execution_policy']['request_timeout_seconds']==config.timeouts['comfy_request']
    requests=[json.loads(p.read_text(encoding='utf-8')) for p in (child/'logs/http').glob('*.request.json')]
    assert all(row['url'].startswith(config.services['comfyui']) for row in requests)
    path,_=review(child)
    assert f.uc.finalize_upscaled_clips(config,run_dir=child,review_path=path).passed
    assert f.uc.load_committed_upscaled_clips(child)['schema_version']==3
