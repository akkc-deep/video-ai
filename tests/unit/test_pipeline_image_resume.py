import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import pytest
from image_helpers import write_png
from http_helpers import Response,ScriptedTransport
from start_image_helpers import make_images_run,fake_media,image_review


def image_child(storyboard_run,monkeypatch,*,revision=False):
    from video_ai.runtime import start_image_checks as sc
    from video_ai.runtime.pipeline_import import create_pipeline_import,load_pipeline_import,serialize_stage_import,content_signature,collect_report_sources
    from video_ai.runtime.paths import create_run,RuntimePaths
    from video_ai.runtime.manifest import create_manifest,hash_file,thaw,now
    from video_ai.config import load_config
    parent,c,parent_store,inputs=make_images_run(storyboard_run,monkeypatch);fake_media(monkeypatch)
    assert sc.prepare_start_images(c,run_dir=parent,image_inputs_path=inputs).status=='review_required'
    review,_=image_review(parent);assert sc.finalize_start_images(c,run_dir=parent,review_path=review).passed
    child=create_run(RuntimePaths.from_config(c))
    model=child/c.models['sdxl'].name if revision else c.models['sdxl']
    if revision:model.write_bytes(b'TEST ONLY model not loaded')
    config,config_path=c,c.config_file
    if revision:
        from source_clip_helpers import write
        from video_ai.config import read_json
        raw=thaw(c.raw);raw.update(voice_config=str(c.voice.config_file),workflows=thaw(c.workflows))
        raw['models']['sdxl']=str(model)
        original=c.workflows['sdxl']
        graph=read_json(original);next(iter(graph.values()))['_meta']={'title':'TEST ONLY revised SDXL'}
        workflow=write(child/'fixture-workflows'/original.name,graph)
        mapping=read_json(original.with_suffix('.mapping.json'));mapping['template_sha256']=hash_file(workflow).sha256
        write(workflow.with_suffix('.mapping.json'),mapping);raw['workflows']['sdxl']=str(workflow)
        baseline_model=parent/c.models['sdxl'].name;baseline_model.write_bytes(b'TEST ONLY original SDXL acceptance')
        inv=write(parent/'TEST-ONLY-sdxl-inventory.json',{str(p):thaw(hash_file(p)) for p in
            (baseline_model,original,original.with_suffix('.mapping.json'))})
        acceptance=write(parent/'TEST-ONLY-sdxl-acceptance.json',dict(passed=True,components={'sdxl':{'passed':True}},
            provenance={'sdxl':{'before':thaw(hash_file(inv))}}))
        monkeypatch.setattr(sc,'TASK4_ACCEPTANCE',acceptance)
        raw['services']['ollama']='http://127.0.0.1:11435'
        config_path=child/'fixture-config.json';config_path.write_text(json.dumps(raw),encoding='utf-8');config=load_config(config_path)
    store=create_manifest(child,config,inputs={'config':hash_file(config_path)},models={},workflows={})
    inventory=sc.image_import_inventory(parent,child,unit_ids=('shot_0001',))
    board=sc.load_committed_storyboard(parent);board_id=hash_file(parent/'storyboard.json');snap=parent_store.snapshot()
    stage=dict(id='storyboard',source_record=snap['stages']['storyboard'],imported_record=dict(source_report_identity=thaw(board_id)),
        signature=content_signature(board),origin='reused_verified')
    rows=[dict(id=s['shot_id'],source_record=s,imported_record=dict(stage='storyboard',origin_run_id=parent.name,
        source_report_identity=thaw(board_id),source_unit_id=s['shot_id']),signature=content_signature(s),origin='reused_verified') for s in board['shots']]
    sources=dict(collect_report_sources(board,parent),**inventory['source_identities']);sources[board_id.path]=thaw(board_id)
    author=None
    if revision:
        base=write(parent/'logs/pipeline/TEST-ONLY-base.json',parent_store.snapshot())
        author=hash_file(write(parent/'logs/pipeline/TEST-ONLY-changes.json',dict(schema_version=1,base_run_id=parent.name,
            base_manifest_snapshot_identity=thaw(hash_file(base)),created_at=now(),reason='TEST ONLY SDXL model/workflow revision',
            script_identity=None,unit_review_identity=None,config_identity=thaw(hash_file(config_path)),shot_changes=[])))
        sources.update({str(p):thaw(hash_file(p)) for p in (model,workflow,workflow.with_suffix('.mapping.json'))})
    identity=create_pipeline_import(config,run_dir=child,parent_run_dir=parent,reason='TEST ONLY selective image reuse',
        changes_identity=author,source_identities=sources,copies=inventory['copies'],stages=[stage,inventory['stage']],units=rows+inventory['units'])
    receipt=load_pipeline_import(child);child_board=serialize_stage_import('storyboard',board,run=child,import_identity=identity,receipt=receipt)
    (child/'storyboard.json').write_text(json.dumps(child_board),encoding='utf-8')
    store.record_stage('storyboard','running');store.record_stage('storyboard','completed',artifacts=[sc._artifact(hash_file(child/'storyboard.json'))])
    store.update(lambda d:d['workflows'].update(storyboard_report=thaw(hash_file(child/'storyboard.json'))))
    store.record_unit('image','shot_0001','running');store.record_unit('image','shot_0001','completed',artifacts=[sc._artifact(hash_file(child/'shots/shot_0001/start.png'))])
    if not revision:
        # TEST ONLY admission boundary: read the configured model identity
        # without loading or executing it. Native path/freshness checks stay real.
        def fixture_model(cfg):
            identity=hash_file(cfg.models['sdxl'])
            return identity,dict(model=thaw(identity))
        monkeypatch.setattr(sc,'_model',fixture_model)
        # TEST ONLY: the ordinary child inherits the exact parent example
        # configuration, including Ollama 11434. Its fake ServiceManager does
        # not establish a real service binding. Revised cases retain the real
        # service-spec construction and model-loader binding checks.
        monkeypatch.setattr(sc,'build_service_specs',lambda *a:{'comfyui':SimpleNamespace(name='comfyui')})
    # The fixture imports a characterized storyboard without constructing a
    # child's complete speech/timeline. Keep that upstream consumer boundary
    # explicit; image admission, reuse, requests and commit remain real.
    monkeypatch.setattr(sc,'load_committed_storyboard',lambda run:json.loads((run/'storyboard.json').read_text(encoding='utf-8')))
    return sc,parent,child,config,store


def install_http(sc,child,config,monkeypatch):
    from video_ai.runtime.workflows import WorkflowTemplate
    from unit.test_workflows import remote_info
    template=WorkflowTemplate.load(config.workflows['sdxl'],config.workflows['sdxl'].with_suffix('.mapping.json'),config.models)
    actions=[];saved={}
    class Manager:
        def __init__(self,*a):pass
        def ensure(self,*a):actions.append('start');return SimpleNamespace(owned=True,process=SimpleNamespace(poll=lambda:0))
        def stop(self,*a):actions.append('stop')
    monkeypatch.setattr(sc,'ServiceManager',Manager)
    def route(request,timeout):
        if request.full_url.endswith('/object_info'):return Response(remote_info(template))
        if request.method=='POST':
            graph=json.loads(request.data)['prompt'];prefix=graph['7']['inputs']['filename_prefix']
            source=child/'comfy/output'/(prefix+'_00001_.png');source.parent.mkdir(parents=True,exist_ok=True);write_png(source,1280,720)
            pid=str(uuid4());saved[pid]=dict(status=dict(completed=True,status_str='success'),outputs={'7':{'images':[
                dict(filename=source.name,subfolder=source.parent.relative_to(child/'comfy/output').as_posix(),type='output')]}})
            return Response(dict(prompt_id=pid,number=0,node_errors={}))
        if '/history/' in request.full_url:
            pid=request.full_url.rsplit('/',1)[1];return Response({pid:saved[pid]})
        return Response(dict(queue_running=[],queue_pending=[]))
    transport=ScriptedTransport(route);original=sc._DeadlineHttp.__init__
    def http(self,*a,**k):original(self,*a,transport=transport,**k)
    monkeypatch.setattr(sc._DeadlineHttp,'__init__',http)
    return transport,actions


def test_reviewed_image_prefix_has_only_remaining_posts_and_fresh_mixed_review(storyboard_run,monkeypatch):
    from video_ai.runtime.pipeline_import import make_reuse_context
    sc,parent,child,c,store=image_child(storyboard_run,monkeypatch)
    before=(parent/'images.json').read_bytes();transport,actions=install_http(sc,child,c,monkeypatch)
    _,identities=sc._input_files(c,child)
    context=make_reuse_context(child,stage='start_images',unit_ids=('shot_0001','shot_0002','shot_0003'),current_input_identities=identities)
    result=sc.resume_start_images(c,run_dir=child,reuse_context=context)
    assert result.status=='review_required' and result.image_count==3,store.snapshot()['stages']['start_images']['error']
    assert sum(method=='POST' for method,*_ in transport.calls)==2 and actions==['start','stop']
    assert store.snapshot()['units']['image']['shot_0001']['submission'] is None
    path,_=image_review(child);assert sc.finalize_start_images(c,run_dir=child,review_path=path).passed
    report=sc.load_committed_start_images(child)
    assert set(report['reused_units'])=={'shot_0001'} and report['schema_version']==2
    assert (parent/'images.json').read_bytes()==before
    (parent/'shots/shot_0001/start.png').write_bytes(b'late parent leaf')
    with pytest.raises((ValueError,OSError)):sc.load_committed_start_images(child)


def test_revised_sdxl_actual_generation_and_formal_consumer_wait_for_new_review(storyboard_run,monkeypatch):
    from video_ai.runtime.pipeline_import import make_reuse_context
    sc,parent,child,c,store=image_child(storyboard_run,monkeypatch,revision=True)
    transport,actions=install_http(sc,child,c,monkeypatch)
    _,identities=sc._input_files(c,child)
    context=make_reuse_context(child,stage='start_images',unit_ids=('shot_0001','shot_0002','shot_0003'),current_input_identities=identities)
    result=sc.resume_start_images(c,run_dir=child,reuse_context=context)
    assert result.status=='review_required',store.snapshot()['stages']['start_images']['error']
    assert sum(method=='POST' for method,*_ in transport.calls)==2 and actions==['start','stop']
    with pytest.raises(ValueError):sc.load_committed_start_images(child)
    path,_=image_review(child);assert sc.finalize_start_images(c,run_dir=child,review_path=path).passed
    assert sc.load_committed_start_images(child)['schema_version']==2


def test_unsealed_image_context_and_orphan_remaining_refused_without_post(storyboard_run,monkeypatch):
    from video_ai.runtime.pipeline_import import ReuseContext,make_reuse_context
    sc,parent,child,c,store=image_child(storyboard_run,monkeypatch);transport,actions=install_http(sc,child,c,monkeypatch)
    _,identities=sc._input_files(c,child)
    real=make_reuse_context(child,stage='start_images',unit_ids=('shot_0001','shot_0002','shot_0003'),current_input_identities=identities)
    forged=ReuseContext(real.stage,real.import_identity,real.verified_units,real.remaining_units,real.current_input_identities)
    with pytest.raises(ValueError):sc.resume_start_images(c,run_dir=child,reuse_context=forged)
    target=child/'shots/shot_0002/start.png';target.parent.mkdir(parents=True);target.write_bytes(b'foreign')
    with pytest.raises(ValueError):sc.resume_start_images(c,run_dir=child,reuse_context=real)
    assert not any(method=='POST' for method,*_ in transport.calls) and not actions


@pytest.mark.parametrize('changed',[None,'model','workflow','mapping'])
def test_mixed_sdxl_reuse_compares_current_content_independently(runtime_run,run_store,monkeypatch,changed):
    from dataclasses import replace
    from unit.test_start_image_generation import setup
    from video_ai.runtime import pipeline_import as pi
    from video_ai.runtime.paths import create_run,RuntimePaths
    from video_ai.runtime.manifest import create_manifest,hash_file,thaw
    sc,c,parent,parent_store,logger,board,shot,transport,actions=setup(run_store,runtime_run,monkeypatch,'success')
    shot['visual_requirements']=[]
    native=sc._generate_owned(c,parent,parent_store,logger,board,[shot],1280,720,{})['shot_0001']
    child=create_run(RuntimePaths.from_config(c));copied=sc._copy(child,Path(native['image_identity']['path']),child/'shots/shot_0001/start.png')
    # Independent paths with identical bytes are equivalent; a replacement
    # file with different content must never inherit original model results.
    model=child/c.models['sdxl'].name;model.write_bytes(Path(native['model_identity']['path']).read_bytes())
    workflow=child/'sdxl.json';workflow.write_bytes(c.workflows['sdxl'].read_bytes())
    mapping=workflow.with_suffix('.mapping.json');mapping.write_bytes(c.workflows['sdxl'].with_suffix('.mapping.json').read_bytes())
    target={'model':model,'workflow':workflow,'mapping':mapping}.get(changed)
    if target:target.write_bytes(target.read_bytes()+b' changed TEST ONLY content')
    current=replace(c,models=dict(c.models,sdxl=model),workflows=dict(c.workflows,sdxl=workflow))
    store=create_manifest(child,current,inputs={},models={},workflows={})
    doc=parent/'images.json';doc.write_text(json.dumps(dict(images=[native])),encoding='utf-8');source_id=thaw(hash_file(doc))
    receipt_path=child/'receipt.json';receipt_path.write_text('{}',encoding='utf-8');receipt_id=thaw(hash_file(receipt_path))
    origin=dict(stage='start_images',origin_run_id=parent.name,source_report_identity=source_id,source_unit_id='shot_0001')
    reused={'shot_0001':dict(origin_run_id=parent.name,source_report_identity=source_id,source_unit_id='shot_0001',signature='a'*64,import_identity=receipt_id)}
    receipt=dict(parent_run_id=parent.name,stages=[dict(id='start_images',origin='reused_verified',imported_record=dict(source_report_identity=source_id))],
        units=[dict(id='shot_0001',origin='reused_verified',imported_record=origin,signature='a'*64)],copies=[dict(stage='start_images',unit_id='shot_0001',role='start_image',
            original_identity=native['image_identity'],copy_identity=thaw(copied))])
    store.update(lambda d:d['workflows'].update(pipeline_import=receipt_id))
    store.record_unit('image','shot_0001','running');store.record_unit('image','shot_0001','completed',artifacts=[sc._artifact(copied)])
    monkeypatch.setattr(pi,'load_pipeline_import',lambda *a,**k:receipt)
    monkeypatch.setattr(pi,'import_source_identities',lambda *a:{})
    monkeypatch.setattr(sc,'load_committed_start_images',lambda *a:dict(images=[native]))
    monkeypatch.setattr(sc,'load_committed_storyboard',lambda *a:board)
    if changed is None:
        result,_=sc._verified_reused_images(current,child,board,store.snapshot(),receipt_id,reused)
        assert result['shot_0001']['image_identity']['sha256']==copied.sha256
    else:
        with pytest.raises(ValueError,match='current SDXL'):
            sc._verified_reused_images(current,child,board,store.snapshot(),receipt_id,reused)
