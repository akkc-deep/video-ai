"""TEST ONLY durable import provenance; no model or production input writes."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import pytest


def bind_fixture_upstream(run):
    """Give characterized upstream placeholders real TEST ONLY leaf identities."""
    from video_ai.config import read_json
    from video_ai.runtime.manifest import hash_file,thaw
    from source_clip_helpers import write
    sentinel=run/'fixture-upstream.bin';sentinel.write_bytes(b'TEST ONLY upstream');sentinel_id=thaw(hash_file(sentinel))
    def bound(value):
        if isinstance(value,dict):
            if set(value)=={'path','bytes','mtime_ns','sha256','verified_at'} and not Path(value['path']).is_file():return sentinel_id
            return {k:bound(v) for k,v in value.items()}
        if isinstance(value,list):return [bound(v) for v in value]
        return value
    write(run/'source-clips.json',bound(read_json(run/'source-clips.json')))


def test_import_api_exists():
    from video_ai.runtime import pipeline_import
    assert callable(pipeline_import.create_pipeline_import)
    assert callable(pipeline_import.load_pipeline_import)


def test_complete_images_derive_rebinds_native_requirements_and_preserves_author(storyboard_run,monkeypatch):
    from start_image_helpers import make_images_run,fake_media,image_review
    from video_ai.runtime.start_image_checks import prepare_start_images,finalize_start_images,load_committed_start_images
    from video_ai.runtime.pipeline_import import derive_completed_stages
    from video_ai.runtime.manifest import ManifestStore,thaw
    parent,config,store,inputs=make_images_run(storyboard_run,monkeypatch);fake_media(monkeypatch)
    assert prepare_start_images(config,run_dir=parent,image_inputs_path=inputs).status=='review_required'
    review,_=image_review(parent)
    assert finalize_start_images(config,run_dir=parent,review_path=review).passed
    original=thaw(load_committed_start_images(parent));before=store.snapshot()
    assert any(row['role']=='quantization_edge_preview' for row in original['requirement_images'])
    # The legacy schema-1 speech fixture has no human acceptance. Supply only
    # that external decision; native timeline/import/media consumers stay real.
    from video_ai.runtime import speech_checks
    consume_speech=speech_checks.load_committed_speech
    monkeypatch.setattr(speech_checks,'load_committed_speech',
        lambda run:dict(consume_speech(run),accepted=True))
    child=derive_completed_stages(config,parent_run_dir=parent,
        stages=('speech','storyboard','start_images'),reason='TEST ONLY complete native images import')
    imported=load_committed_start_images(child)
    assert len(imported['requirement_images'])==len(original['requirement_images'])
    for actual,wanted in zip(imported['requirement_images'],original['requirement_images']):
        assert {k:v for k,v in actual.items() if k!='image_identity'}=={k:v for k,v in wanted.items() if k!='image_identity'}
        assert Path(actual['image_identity']['path'])==child/'shots'/wanted['image_shot_id']/'start.png'
        assert actual['image_identity']['sha256']==wanted['image_identity']['sha256']
    assert imported['review_identity']==original['review_identity']
    assert store.snapshot()==before
    assert all(u['submission'] is None for u in ManifestStore.open(child).snapshot()['units']['image'].values())


@pytest.mark.parametrize('stage',['source_clips','upscale'])
def test_explicit_revision_admits_bound_model_content_and_complete_fixed_workflow(runtime_run,monkeypatch,stage):
    import shutil
    from source_clip_helpers import write
    from video_ai.config import load_config,read_json
    from video_ai.runtime.manifest import create_manifest,hash_file,thaw,now
    from video_ai.runtime.paths import create_run,RuntimePaths
    from video_ai.runtime.pipeline_import import create_pipeline_import
    from video_ai.runtime._pipeline_model_admission import revised_files
    if stage=='source_clips':
        from source_clip_helpers import setup
        f=setup(runtime_run,monkeypatch);owner=f.ci;model_key='wan_high';workflow_key='wan'
    else:
        from upscale_helpers import setup
        f=setup(runtime_run,monkeypatch,frames=1);owner=f.ui;model_key='upscale';workflow_key='upscale'
    raw=thaw(f.config.raw)
    raw['voice_config']=str(f.config.voice.config_file)
    raw['workflows']={k:str(v) for k,v in f.config.workflows.items()}
    target=f.run/'explicit-revision-models'/f.config.models[model_key].name
    target.parent.mkdir();target.write_bytes(b'TEST ONLY explicitly revised model content; never loaded')
    raw['models'][model_key]=str(target)
    graph=read_json(f.config.workflows[workflow_key]);next(iter(graph.values()))['_meta']={'title':'TEST ONLY explicit workflow revision'}
    workflow=write(f.run/'explicit-revision-workflows'/f.config.workflows[workflow_key].name,graph)
    mapping=read_json(f.config.workflows[workflow_key].with_suffix('.mapping.json'))
    mapping['template_sha256']=hash_file(workflow).sha256
    write(workflow.with_suffix('.mapping.json'),mapping)
    raw['workflows'][workflow_key]=str(workflow)
    if stage=='source_clips':raw['workflows']['wan_mapping']=str(workflow.with_suffix('.mapping.json'))
    config=load_config(write(f.run/'explicit-revision-config.json',raw))
    child=create_run(RuntimePaths.from_config(config));create_manifest(child,config,inputs={'config':hash_file(config.config_file)},models={},workflows={})
    base=write(f.run/'logs/pipeline/TEST-ONLY-base.json',f.store.snapshot())
    changes=write(f.run/'logs/pipeline/TEST-ONLY-changes.json',dict(schema_version=1,base_run_id=f.run.name,
        base_manifest_snapshot_identity=thaw(hash_file(base)),created_at=now(),reason='TEST ONLY explicit model/workflow revision',
        script_identity=None,unit_review_identity=None,config_identity=thaw(hash_file(config.config_file)),shot_changes=[]))
    files=({**{n:config.models[n] for n in owner.MODEL_NAMES},'workflow':workflow,'mapping':workflow.with_suffix('.mapping.json')}
        if stage=='source_clips' else dict(model=target,workflow=workflow,mapping=workflow.with_suffix('.mapping.json')))
    create_pipeline_import(config,run_dir=child,parent_run_dir=f.run,reason='TEST ONLY author-bound content',changes_identity=hash_file(changes),
        copies=[],source_identities={str(p):thaw(hash_file(p)) for p in files.values()})
    with pytest.raises(ValueError):owner.models(config)
    with pytest.raises(ValueError):owner.template(config)
    admitted=revised_files(config,child,files)
    ids=owner.models(config,revision=admitted);template=owner.template(config,revision=admitted)
    assert ids[model_key if stage=='source_clips' else 'model'].sha256==hash_file(target).sha256
    assert template.graph==graph
    target.write_bytes(b'TEST ONLY later revision drift')
    with pytest.raises((ValueError,OSError)):revised_files(config,child,files)


def test_storyboard_new_generation_never_samples_or_leases_gpu(runtime_run,monkeypatch):
    from video_ai.runtime import storyboard_checks as sc
    from video_ai.runtime.manifest import create_manifest
    from video_ai.runtime.logging import RunLogger
    from types import SimpleNamespace
    run,config,paths=runtime_run;store=create_manifest(run,config,inputs={},models={},workflows={})
    def forbidden(*args,**kwargs):pytest.fail('GPU management forbidden')
    monkeypatch.setattr(sc,'ResourceSampler',forbidden);monkeypatch.setattr(sc,'GpuLease',forbidden)
    monkeypatch.setattr(sc,'_model_files',lambda paths:{})
    monkeypatch.setattr(sc,'build_service_specs',lambda *args:{'ollama':object()})
    monkeypatch.setattr(sc.ServiceManager,'ensure',lambda *args:SimpleNamespace(owned=False))
    with pytest.raises(sc.ServiceConflictError):sc._generate_owned(config,run,store,RunLogger(run),())


def pair(runtime_run):
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.manifest import create_manifest, hash_file, thaw
    parent, config, paths = runtime_run
    old = create_manifest(parent, config, inputs={}, models={}, workflows={})
    source = parent / 'script.txt'; source.write_bytes(b'TEST ONLY original')
    child = create_run(paths)
    create_manifest(child, config, inputs={}, models={}, workflows={})
    return parent, child, config, old, thaw(hash_file(source))


def imported(runtime_run):
    from video_ai.runtime.pipeline_import import create_pipeline_import
    parent, child, config, old, source = pair(runtime_run)
    identity = create_pipeline_import(config, run_dir=child, parent_run_dir=parent,
        reason='TEST ONLY preserved original', source_identities={source['path']:source},
        copies=[dict(original_identity=source, copy_path=child/'script.txt', role='script', stage='speech', unit_id=None)])
    return parent, child, old, identity


def test_copy_and_leaf_revalidation(runtime_run):
    from video_ai.runtime.pipeline_import import load_pipeline_import, import_source_identities
    parent, child, old, identity = imported(runtime_run)
    receipt = load_pipeline_import(child)
    assert receipt['run_id'] == child.name
    assert (child/'script.txt').read_bytes() == (parent/'script.txt').read_bytes()
    assert str(parent/'script.txt') in import_source_identities(child)
    (parent/'script.txt').write_bytes(b'TEST ONLY mutation')
    with pytest.raises(ValueError, match='identity|changed|drift'):load_pipeline_import(child)


def test_parent_append_is_allowed_but_protected_prefix_is_not(runtime_run):
    from video_ai.runtime.pipeline_import import load_pipeline_import
    parent, child, old, identity = imported(runtime_run)
    old.record_stage('preflight', 'running')
    old.record_stage('preflight', 'completed')
    assert load_pipeline_import(child)['parent_run_id'] == parent.name
    from video_ai.runtime.manifest import thaw
    snapshot = old.snapshot(); snapshot['inputs']['unexpected'] = thaw(identity)
    old._write(snapshot)
    with pytest.raises(ValueError, match='parent|protected'):load_pipeline_import(child)


def test_copy_is_exclusive(runtime_run):
    from video_ai.runtime.pipeline_import import create_pipeline_import
    parent, child, config, old, source = pair(runtime_run)
    (child/'script.txt').write_bytes(b'TEST ONLY sentinel')
    with pytest.raises((ValueError, FileExistsError)):
        create_pipeline_import(config, run_dir=child, parent_run_dir=parent, reason='TEST ONLY',
            source_identities={source['path']:source},copies=[dict(original_identity=source,
                copy_path=child/'script.txt',role='script',stage='speech',unit_id=None)])
    assert (child/'script.txt').read_bytes() == b'TEST ONLY sentinel'


def test_failed_child_copy_retains_original_error_and_child_diagnostic(timeline_run,monkeypatch):
    from video_ai.runtime import pipeline_import as imports
    from video_ai.runtime import paths
    from video_ai.config import read_json
    parent,config,store,_=timeline_run
    created=[];create_run=paths.create_run
    def track_child(runtime_paths):
        child=create_run(runtime_paths);created.append(child);return child
    monkeypatch.setattr(paths,'create_run',track_child)
    failure=OSError('TEST ONLY copy storage failure')
    def fail(*args,**kwargs):raise failure
    monkeypatch.setattr(imports,'copy_exclusive',fail)
    with pytest.raises(OSError) as caught:
        imports.derive_completed_stages(config,parent_run_dir=parent,stages=('speech',),reason='TEST ONLY copy fault')
    assert caught.value is failure
    child,=created
    diagnostics=list((child/'logs/pipeline').glob('diagnostic-*.json'))
    assert len(diagnostics)==1
    report=read_json(diagnostics[0])
    assert report['error_type']=='OSError' and report['message']=='TEST ONLY copy storage failure'
    assert Path(report['traceback_identity']['path']).is_file()


def test_reuse_context_cannot_be_forged_or_mutated(runtime_run):
    from video_ai.runtime.pipeline_import import make_reuse_context, verify_reuse_context, ReuseContext
    parent, child, old, identity = imported(runtime_run)
    context = make_reuse_context(child,stage='speech',unit_ids=('unit_0001',),current_input_identities={})
    assert context.remaining_units == ('unit_0001',)
    with pytest.raises(FrozenInstanceError):context.stage = 'upscale'
    with pytest.raises(TypeError):context.verified_units['fake'] = {}
    forged = ReuseContext('speech',identity,{},(),{})
    with pytest.raises(ValueError, match='context|consumer'):
        verify_reuse_context(child,forged,stage='speech',unit_ids=('unit_0001',),current_input_identities={})


def test_native_upscale_schema3(runtime_run, monkeypatch):
    from upscale_helpers import setup, review
    f = setup(runtime_run,monkeypatch,frames=1)
    result = f.uc.prepare_upscaled_clips(f.config,run_dir=f.run,execution_policy='pipeline')
    assert result.status == 'review_required'
    from video_ai.config import read_json
    draft = read_json(result.draft_path)
    assert draft['schema_version'] == 3
    assert draft['execution_policy']['total_timeout_seconds'] is None
    assert draft['import_identity'] is None and draft['reused_units'] == {}
    path, _ = review(f.run)
    assert f.uc.finalize_upscaled_clips(f.config,run_dir=f.run,review_path=path).passed
    assert f.uc.load_committed_upscaled_clips(f.run)['schema_version'] == 3


def test_nested_import_flattens_actual_original_leaves(runtime_run):
    from video_ai.runtime.pipeline_import import create_pipeline_import,load_pipeline_import
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.manifest import create_manifest,hash_file,thaw
    parent,child,old,identity=imported(runtime_run)
    _,config,paths=runtime_run
    grandchild=create_run(paths);create_manifest(grandchild,config,inputs={},models={},workflows={})
    source=thaw(hash_file(child/'script.txt'))
    create_pipeline_import(config,run_dir=grandchild,parent_run_dir=child,reason='TEST ONLY second generation',
        source_identities={source['path']:source},copies=[dict(original_identity=source,copy_path=grandchild/'script.txt',role='script',stage='speech',unit_id=None)])
    receipt=load_pipeline_import(grandchild)
    assert str(parent/'script.txt') in receipt['source_identities']
    (parent/'script.txt').write_bytes(b'changed original')
    with pytest.raises(ValueError,match='identity|drift'):load_pipeline_import(grandchild)


def test_candidate_closure_contains_import_leaf(runtime_run):
    from video_ai.runtime._candidate_evidence import capture_bound_identities
    parent,child,old,identity=imported(runtime_run)
    leaves=capture_bound_identities({},run=child)
    assert str(parent/'script.txt') in {item.path for item in leaves.values()}


def test_partial_upscale_inventory_replays_prefix_without_manifest_reset(runtime_run,monkeypatch):
    from unit.test_upscale_resume import stopped
    from video_ai.runtime.pipeline_import import collect_partial_inventory
    f=stopped(runtime_run,monkeypatch)
    before=(f.run/'manifest.json').read_bytes()
    inventory=collect_partial_inventory(f.config,f.run,f.store.snapshot())
    assert tuple(inventory['upscale']['verified_units'])==('shot_0001:frame_000001',)
    assert inventory['upscale']['remaining_units']==('shot_0001:frame_000002',)
    assert before==(f.run/'manifest.json').read_bytes() and len(f.requests)==1


def test_native_pipeline_policy_survives_stopped_upscale_inventory(runtime_run,monkeypatch):
    from upscale_helpers import setup
    from video_ai.runtime.pipeline_import import collect_partial_inventory
    from video_ai.adapters.common import AdapterError,FailureKind
    f=setup(runtime_run,monkeypatch,frames=2)
    original=f.ug.ComfyClient.validate_template
    def stop(client,template):
        if f.requests:raise AdapterError(FailureKind.network,'TEST ONLY stopped before second frame')
        return original(client,template)
    monkeypatch.setattr(f.ug.ComfyClient,'validate_template',stop)
    assert f.uc.prepare_upscaled_clips(f.config,run_dir=f.run,execution_policy='pipeline').status=='failed'
    before=f.store.snapshot()
    inventory=collect_partial_inventory(f.config,f.run)
    assert tuple(inventory['upscale']['verified_units'])==('shot_0001:frame_000001',)
    policy=before['workflows']['upscale_execution_policy']
    assert policy['path'] in {row['path'] for row in inventory['upscale']['evidence_identities'].values()}
    assert f.store.snapshot()==before and len(f.requests)==1


def test_known_invalid_upscale_requires_exact_inactive_original_media_proof(runtime_run,monkeypatch):
    import json
    from upscale_helpers import setup
    from http_helpers import Response
    from video_ai.runtime import pipeline_recovery as recovery
    from video_ai.adapters.common import HttpClient
    from video_ai.runtime.pipeline_import import collect_partial_inventory
    f=setup(runtime_run,monkeypatch,frames=1,mode='corrupt');handler=f.transport.handler;bound={}
    def transport(request,timeout):
        response=handler(request,timeout);data=json.loads(response.getvalue())
        if request.method=='POST':
            payload=json.loads(request.data);token=data['prompt_id']
            bound[token]=[0,token,payload['prompt'],{'client_id':payload['client_id']},['5']]
        if '/history' in request.full_url:
            for token,entry in data.items():entry['prompt']=bound[token]
            return Response(data)
        return response
    f.transport.handler=transport
    monkeypatch.setattr(recovery,'HttpClient',lambda *args,**kwargs:HttpClient(*args,transport=f.transport,**kwargs))
    assert f.uc.prepare_upscaled_clips(f.config,run_dir=f.run,execution_policy='pipeline').status=='failed'
    before=f.store.snapshot();unit=before['units']['frame']['shot_0001:frame_000001']
    assert unit['status']=='failed' and unit['submission']['state']=='completed'
    inventory=collect_partial_inventory(f.config,f.run)['upscale']
    assert inventory['verified_units']=={} and inventory['unsent_verified'] is False
    assert tuple(inventory['known_failed_units'])==('shot_0001:frame_000001',)
    assert f.store.snapshot()==before and len(f.requests)==1


def test_unknown_source_cannot_become_a_retry_child(runtime_run,monkeypatch):
    from source_clip_helpers import setup
    from video_ai.runtime.pipeline_import import derive_completed_stages
    f=setup(runtime_run,monkeypatch,mode='lost')
    assert f.sc.prepare_source_clips(f.config,run_dir=f.run).status in ('failed','ambiguous')
    assert f.store.snapshot()['units']['shot_attempt']['shot_0001:attempt_0001']['submission']['state']=='ambiguous'
    before=f.store.snapshot();posts=sum(call[0]=='POST' for call in f.transport.calls)
    with pytest.raises(ValueError,match='partial stage'):
        derive_completed_stages(f.config,parent_run_dir=f.run,stages=(),partial_stages=('source_clips',),
            retry_targets={'source_clips':('shot_0001',)},reason='TEST ONLY must refuse unknown')
    assert f.store.snapshot()==before and sum(call[0]=='POST' for call in f.transport.calls)==posts==1


@pytest.mark.parametrize('complete_prefix',[False,True,'selected','nested'])
def test_partial_upscale_child_first_submits_only_remaining_frame(runtime_run,monkeypatch,complete_prefix):
    import json,shutil
    from unit.test_upscale_resume import stopped
    from upscale_helpers import review
    from source_clip_helpers import write
    from video_ai.runtime.pipeline_import import derive_partial_stage,derive_completed_stages,make_reuse_context
    from video_ai.runtime.manifest import hash_file,thaw,ManifestStore
    if complete_prefix:
        from upscale_helpers import setup
        from video_ai.adapters.common import AdapterError,FailureKind
        f=setup(runtime_run,monkeypatch,frames=1,clip_counts=[1,2])
        if complete_prefix=='selected':bind_fixture_upstream(f.run)
        original=f.ug.ComfyClient.validate_template
        def stop(client,template):
            if client.http.unit_id=='shot_0002:frame_000002':raise AdapterError(FailureKind.ambiguous,'TEST ONLY stopped frame')
            return original(client,template)
        if complete_prefix=='selected':
            assert f.uc.prepare_upscaled_clips(f.config,run_dir=f.run).status=='review_required'
            path,_=review(f.run)
            assert f.uc.finalize_upscaled_clips(f.config,run_dir=f.run,review_path=path).passed
        else:
            monkeypatch.setattr(f.ug.ComfyClient,'validate_template',stop)
            assert f.uc.prepare_upscaled_clips(f.config,run_dir=f.run).status=='failed'
            monkeypatch.setattr(f.ug.ComfyClient,'validate_template',original)
    else:f=stopped(runtime_run,monkeypatch)
    child=(derive_completed_stages(f.config,parent_run_dir=f.run,stages=(),partial_stages=('upscale',),
        selected_units={'upscale':('shot_0001',)},reason='TEST ONLY selective affected shot')
        if complete_prefix=='selected' else derive_partial_stage(f.config,parent_run_dir=f.run,stage='upscale'))
    source=thaw(f.source);source['run_id']=child.name
    for index,clip in enumerate(source['clips']):
        target=child/'shots'/clip['shot_id']/'source.mp4';target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(f.run/'shots'/clip['shot_id']/'source.mp4',target);source_id=thaw(hash_file(target))
        clip['source_identity']=source['frame_mappings'][index]['source_identity']=source['requirement_clips'][index]['actual_artifact']=source_id
    # Characterized source consumer keeps the real inherited review at origin.
    source['import_identity']=ManifestStore.open(child).snapshot()['workflows']['pipeline_import']
    source.update(schema_version=2,reused_units={'TEST ONLY':'characterized upstream boundary'})
    write(child/'source-clips.json',source)
    context=f.ui.inputs(f.config,child)
    units=tuple(f'{p.shot_id}:frame_{i:06d}' for p in context['plans'] for i in range(1,p.source_frames+1))
    reuse=make_reuse_context(child,stage='upscale',unit_ids=units,current_input_identities=context['identities'])
    handler=f.transport.handler
    def route(request,timeout):
        response=handler(request,timeout)
        if request.method=='POST':
            prefix=json.loads(request.data)['prompt']['5']['inputs']['filename_prefix']
            generated=f.run/'comfy/output'/(prefix+'_00001_.png');copied=child/'comfy/output'/(prefix+'_00001_.png')
            copied.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(generated,copied)
        return response
    f.transport.handler=route;before=f.store.snapshot()
    if complete_prefix=='nested':
        monkeypatch.setattr(f.ug.ComfyClient,'validate_template',stop)
    from video_ai.runtime.pipeline_stages import prepare
    result=prepare('upscale',f.config,child,options={},reviews={},store=ManifestStore.open(child))
    if complete_prefix=='nested':
        from video_ai.runtime.pipeline_import import collect_partial_inventory,load_pipeline_import
        assert result.status=='failed'
        child_before=ManifestStore.open(child).snapshot()
        inventory=collect_partial_inventory(f.config,child)['upscale']
        assert tuple(inventory['verified_units'])==('shot_0001:frame_000001','shot_0002:frame_000001')
        grandchild=derive_partial_stage(f.config,parent_run_dir=child,stage='upscale')
        assert (grandchild/'shots/shot_0001/upscaled.mp4').read_bytes()==(child/'shots/shot_0001/upscaled.mp4').read_bytes()
        assert {r['imported_record']['origin_run_id'] for r in load_pipeline_import(grandchild)['units']}=={f.run.name}
        assert ManifestStore.open(child).snapshot()==child_before and len(f.requests)==2
        return
    assert result.status=='review_required',ManifestStore.open(child).snapshot()['stages']['upscale']['error']
    assert len(f.requests)==(5 if complete_prefix=='selected' else 3 if complete_prefix else 2) and f.store.snapshot()==before
    if complete_prefix:assert (child/'shots/shot_0001/upscaled.mp4').read_bytes()==(f.run/'shots/shot_0001/upscaled.mp4').read_bytes()
    assert ManifestStore.open(child).snapshot()['units']['frame'][units[0]]['submission'] is None
    path,_=review(child)
    assert f.uc.finalize_upscaled_clips(f.config,run_dir=child,review_path=path).passed
    assert f.uc.load_committed_upscaled_clips(child)['schema_version']==3


def test_partial_source_inventory_replays_selected_attempt(runtime_run,monkeypatch):
    from source_clip_helpers import setup
    from video_ai.runtime.pipeline_import import collect_partial_inventory
    from video_ai.adapters.common import AdapterError,FailureKind
    f=setup(runtime_run,monkeypatch)
    original=f.cg.ComfyClient.validate_template
    def stop(client,template):
        if f.requests:raise AdapterError(FailureKind.network,'TEST ONLY interrupted before second POST')
        return original(client,template)
    monkeypatch.setattr(f.cg.ComfyClient,'validate_template',stop)
    assert f.sc.prepare_source_clips(f.config,run_dir=f.run).status=='failed'
    before=(f.run/'manifest.json').read_bytes()
    inventory=collect_partial_inventory(f.config,f.run,f.store.snapshot())
    assert tuple(inventory['source_clips']['verified_units'])==('shot_0001',)
    assert 'shot_0002' in inventory['source_clips']['remaining_units']
    assert before==(f.run/'manifest.json').read_bytes() and len(f.requests)==1


@pytest.mark.parametrize('parent_state',['partial','completed','failed_retry','nested'])
def test_partial_source_child_first_submits_only_remaining(runtime_run,monkeypatch,parent_state):
    import json,shutil
    from source_clip_helpers import setup,write,review
    from video_ai.runtime.pipeline_import import derive_partial_stage,derive_completed_stages,make_reuse_context
    from video_ai.runtime import source_clip_checks as sc
    from video_ai.runtime.manifest import hash_file,thaw,ManifestStore
    from video_ai.adapters.common import AdapterError,FailureKind
    f=setup(runtime_run,monkeypatch)
    original=f.cg.ComfyClient.validate_template
    def stop(client,template):
        if f.requests:raise AdapterError(FailureKind.ambiguous,'TEST ONLY before second POST')
        return original(client,template)
    if parent_state=='completed':
        assert sc.prepare_source_clips(f.config,run_dir=f.run).status=='review_required'
        path,_=review(f.run)
        assert sc.finalize_source_clips(f.config,run_dir=f.run,review_path=path).passed
        child=derive_completed_stages(f.config,parent_run_dir=f.run,stages=(),partial_stages=('source_clips',),
            selected_units={'source_clips':tuple(f'shot_{i:04d}' for i in range(1,7))},reason='TEST ONLY selected unchanged shots')
    elif parent_state=='failed_retry':
        from http_helpers import Response
        handler=f.transport.handler
        def reject_second(request,timeout):
            if request.method=='POST' and f.requests:
                return Response({'error':{'type':'TEST ONLY rejected graph'}},status=400)
            return handler(request,timeout)
        f.transport.handler=reject_second
        assert sc.prepare_source_clips(f.config,run_dir=f.run).status=='failed'
        child=derive_completed_stages(f.config,parent_run_dir=f.run,stages=(),partial_stages=('source_clips',),
            retry_targets={'source_clips':('shot_0002',)},reason='TEST ONLY explicit once-only retry')
        f.transport.handler=handler
    else:
        monkeypatch.setattr(f.cg.ComfyClient,'validate_template',stop)
        assert sc.prepare_source_clips(f.config,run_dir=f.run).status=='failed'
        monkeypatch.setattr(f.cg.ComfyClient,'validate_template',original)
        child=derive_partial_stage(f.config,parent_run_dir=f.run,stage='source_clips')
    before=f.store.snapshot();board=thaw(f.board);images=thaw(f.images)
    board['run_id']=images['run_id']=child.name
    if parent_state=='completed':board['shots'][-1]['video_prompt']+=' TEST ONLY: gentler camera movement.'
    for row in images['images']:
        target=child/'shots'/row['shot_id']/'start.png';target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(row['image_identity']['path'],target);row['image_identity']=thaw(hash_file(target))
    for report,names in ((board,('review_identity','timing_review_identity')),(images,('review_identity',))):
        for name in names:
            old=Path(report[name]['path']);target=child/old.relative_to(f.run);target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(old,target);report[name]=thaw(hash_file(target))
    for name,data in [('storyboard.json',board),('images.json',images),('timeline.json',f.timeline),('storyboard-draft.json',{'fixture':'TEST ONLY'}),('images-draft.json',{'fixture':'TEST ONLY'})]:write(child/name,data)
    context=f.ci.inputs(f.config,child)
    reuse=make_reuse_context(child,stage='source_clips',unit_ids=tuple(p.shot_id for p in context['plans']),current_input_identities=context['identities'])
    handler=f.transport.handler
    def route(request,timeout):
        if parent_state=='failed_retry' and request.method=='POST':
            from http_helpers import Response
            return Response({'error':{'type':'TEST ONLY child rejected again'}},status=400)
        response=handler(request,timeout)
        if request.method=='POST':
            prefix=json.loads(request.data)['prompt']['108']['inputs']['filename_prefix']
            source=f.run/'comfy/output'/(prefix+'_00001_.mp4');target=child/'comfy/output'/(prefix+'_00001_.mp4')
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        return response
    f.transport.handler=route
    before_posts=sum(call[0]=='POST' for call in f.transport.calls)
    if parent_state=='nested':
        monkeypatch.setattr(f.cg.ComfyClient,'validate_template',stop)
    from video_ai.runtime.pipeline_stages import prepare
    result=prepare('source_clips',f.config,child,options={},reviews={},store=ManifestStore.open(child))
    if parent_state=='nested':
        from video_ai.runtime.pipeline_import import collect_partial_inventory,load_pipeline_import
        assert result.status=='failed'
        child_before=ManifestStore.open(child).snapshot()
        inventory=collect_partial_inventory(f.config,child)['source_clips']
        assert tuple(inventory['verified_units'])==('shot_0001',)
        grandchild=derive_partial_stage(f.config,parent_run_dir=child,stage='source_clips')
        assert (grandchild/'shots/shot_0001/source.mp4').read_bytes()==(child/'shots/shot_0001/source.mp4').read_bytes()
        assert {r['imported_record']['origin_run_id'] for r in load_pipeline_import(grandchild)['units']}=={f.run.name}
        assert ManifestStore.open(child).snapshot()==child_before and len(f.requests)==1
        return
    if parent_state=='failed_retry':
        assert result.status=='failed'
        assert sum(call[0]=='POST' for call in f.transport.calls)==before_posts+1
        assert f.store.snapshot()==before
        assert len(ManifestStore.open(child).snapshot()['units']['shot_attempt'])==1
        return
    assert result.status=='review_required',ManifestStore.open(child).snapshot()['stages']['source_clips']['error']
    assert len(f.requests)==(8 if parent_state=='completed' else len(context['plans']))
    assert f.store.snapshot()==before
    assert ManifestStore.open(child).snapshot()['units']['shot']['shot_0001']['submission'] is None
    path,_=review(child)
    assert sc.finalize_source_clips(f.config,run_dir=child,review_path=path).passed
    assert sc.load_committed_source_clips(child)['schema_version']==2


def test_derive_run_reuses_complete_speech_with_legal_child_transactions(timeline_run,monkeypatch):
    from types import SimpleNamespace
    from video_ai.runtime.pipeline_import import derive_run
    from video_ai.runtime.speech_checks import load_committed_speech
    from video_ai.runtime.manifest import ManifestStore
    parent,config,store,data=timeline_run
    from video_ai.runtime import preflight as pf
    monkeypatch.setattr(pf,'preflight',lambda *args,**kwargs:pf.PreflightReport((pf.PreflightCheck('TEST ONLY',True,'fixture admission'),)))
    before=store.snapshot()
    plan=SimpleNamespace(reused=(SimpleNamespace(stage='speech',unit_id=None,signature='a'*64),),invalidated=(),input_identities={})
    child=derive_run(config,parent_run_dir=parent,plan=plan)
    loaded=load_committed_speech(child)
    assert loaded['report']['schema_version']==2
    assert loaded['report']['total_speech_samples']==data['total_speech_samples']
    assert store.snapshot()==before
    assert all(u['submission'] is None for u in ManifestStore.open(child).snapshot()['units']['speech'].values())


def test_derive_refuses_failed_fresh_preflight_before_creating_child(timeline_run,monkeypatch):
    from types import SimpleNamespace
    from video_ai.runtime import preflight as pf
    from video_ai.runtime.pipeline_import import derive_run
    parent,config,store,data=timeline_run
    monkeypatch.setattr(pf,'preflight',lambda *args,**kwargs:pf.PreflightReport((pf.PreflightCheck('TEST ONLY',False,'fixture refusal'),)))
    before=set(parent.parent.iterdir())
    with pytest.raises(ValueError,match='preflight'):
        derive_run(config,parent_run_dir=parent,plan=SimpleNamespace(reused=(),invalidated=(),input_identities={}))
    assert set(parent.parent.iterdir())==before


def test_imported_upscale_keeps_original_submissions_and_copied_bytes(runtime_run,monkeypatch):
    from upscale_helpers import setup,review
    from video_ai.runtime.pipeline_import import derive_completed_stages
    from video_ai.runtime.manifest import ManifestStore
    f=setup(runtime_run,monkeypatch,frames=1)
    # Upstream is a characterized test double; replace its synthetic missing
    # identities with explicitly TEST ONLY existing leaves for closure checks.
    from video_ai.config import read_json
    from video_ai.runtime.manifest import hash_file,thaw
    from source_clip_helpers import write
    bind_fixture_upstream(f.run)
    assert f.uc.prepare_upscaled_clips(f.config,run_dir=f.run).status=='review_required'
    path,_=review(f.run)
    assert f.uc.finalize_upscaled_clips(f.config,run_dir=f.run,review_path=path).passed
    original=f.store.snapshot()
    from video_ai.runtime import pipeline_import as imports
    serializer=imports.serialize_stage_import
    def with_upstream(stage,report,**kwargs):
        import shutil
        child=kwargs['run'];upstream=read_json(f.run/'source-clips.json');upstream['run_id']=child.name
        target=child/'shots/shot_0001/source.mp4'
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f.run/'shots/shot_0001/source.mp4',target)
        current=thaw(hash_file(target));upstream['clips'][0]['source_identity']=current
        upstream['frame_mappings'][0]['source_identity']=current;upstream['requirement_clips'][0]['actual_artifact']=current
        upstream['import_identity']=thaw(kwargs['import_identity'])
        upstream.update(schema_version=2,reused_units={'TEST ONLY':'characterized upstream boundary'})
        if not (child/'source-clips.json').exists():write(child/'source-clips.json',upstream)
        return serializer(stage,report,**kwargs)
    monkeypatch.setattr(imports,'serialize_stage_import',with_upstream)
    child=derive_completed_stages(f.config,parent_run_dir=f.run,stages=('upscale',),reason='TEST ONLY copy')
    report=f.uc.load_committed_upscaled_clips(child)
    assert report['schema_version']==3
    assert report['clips'][0]['frames'][0]['submission']==f.uc.load_committed_upscaled_clips(f.run)['clips'][0]['frames'][0]['submission']
    copied=Path(report['clips'][0]['upscaled_identity']['path'])
    assert copied.is_relative_to(child)
    assert copied.read_bytes()==(f.run/'shots/shot_0001/upscaled.mp4').read_bytes()
    assert all(u['submission'] is None for u in ManifestStore.open(child).snapshot()['units']['frame'].values())
    assert f.store.snapshot()==original and len(f.requests)==1
    current=read_json(child/'source-clips.json');current['clips'][0]['source_frames']+=1
    write(child/'source-clips.json',current)
    with pytest.raises((ValueError,OSError)):f.uc.load_committed_upscaled_clips(child)
    current['clips'][0]['source_frames']-=1;write(child/'source-clips.json',current)
    (f.run/'shots/shot_0001/upscaled-frames/frame_000001.png').write_bytes(b'TEST ONLY drift')
    with pytest.raises((ValueError,OSError)):f.uc.load_committed_upscaled_clips(child)
