"""TEST ONLY actual saved revised-SDXL graph/HTTP/PNG recovery without repost."""
import json
from pathlib import Path
from uuid import uuid4

import pytest
from http_helpers import Response,ScriptedTransport
from image_helpers import write_png
from source_clip_helpers import write


@pytest.mark.parametrize('missing_binding',[False,True])
@pytest.mark.parametrize('dimensions',[(768,432),(1280,720)])
def test_saved_revised_sdxl_consumes_existing_loader_authorization_without_post(runtime_run,monkeypatch,missing_binding,dimensions):
    from unit.test_pipeline_model_paths import fixture
    from unit.test_workflows import remote_info
    from video_ai.runtime import start_image_checks as owner,pipeline_recovery as recovery
    from video_ai.runtime._pipeline_model_paths import prepare_or_consume_model_binding,binding_identities
    from video_ai.runtime.manifest import ManifestStore,hash_file,thaw
    from video_ai.runtime.logging import RunLogger
    from video_ai.adapters.common import HttpClient
    from video_ai.adapters.comfyui import ComfyClient
    from video_ai.planning.start_images import image_parameters
    config,run,_=fixture(runtime_run,monkeypatch,'sdxl')
    old=run/'TEST-ONLY-original-model'/config.models['sdxl'].name
    old.parent.mkdir();old.write_bytes(b'TEST ONLY accepted old SDXL bytes')
    workflow=config.workflows['sdxl'];mapping=workflow.with_suffix('.mapping.json')
    inventory=write(run/'TEST-ONLY-baseline-inventory.json',{str(p):thaw(hash_file(p)) for p in (old,workflow,mapping)})
    acceptance=write(run/'TEST-ONLY-baseline-acceptance.json',dict(passed=True,components={'sdxl':{'passed':True}},
        provenance={'sdxl':{'before':thaw(hash_file(inventory))}}))
    monkeypatch.setattr(owner,'TASK4_ACCEPTANCE',acceptance)
    binding=prepare_or_consume_model_binding(config,run,'sdxl',create=True)
    expected_leaves={value.path for value in binding_identities(binding).values()}
    revision=owner._revision(config,run)
    template=owner._template(config,revision=revision)
    with pytest.raises(ValueError):owner._model(config)
    board=dict(global_visual=dict(style='TEST ONLY',color_palette='red',lighting='day',entities=[]),
        shots=[dict(shot_id='shot_0001',primary_unit_id='speech_0001',image_prompt='one red bird',entity_ids=[])])
    monkeypatch.setattr(owner,'_input_files',lambda *a:(board,{}))
    assert (config.media.profile.width,config.media.profile.height)==(768,432)
    width,height=dimensions
    params=image_parameters(board['shots'][0],board['global_visual'],width,height)
    graph=template.instantiate(dict(positive_prompt=params['positive'],negative_prompt=params['negative'],
        seed=params['seed'],width=width,height=height),output_prefix=f'{run.name}/start_images/shot_0001')
    prompt=str(uuid4());history={}
    def route(request,timeout):
        if request.method=='POST':return Response(dict(prompt_id=prompt,number=1,node_errors={}))
        if request.full_url.endswith('/object_info'):return Response(remote_info(template))
        if request.full_url.endswith('/queue'):return Response(dict(queue_running=[],queue_pending=[]))
        if '/history' in request.full_url:return Response(history)
        raise AssertionError('unexpected TEST ONLY request')
    transport=ScriptedTransport(route);store=ManifestStore.open(run);logger=RunLogger(run)
    store.record_stage('start_images','running');store.record_unit('image','shot_0001','running')
    client=ComfyClient(HttpClient(config.services['comfyui'],config.timeouts['comfy_request'],logger,transport=transport),store,logger)
    client.validate_template(template);client.submit_once(graph,stage='start_images',kind='image',unit_id='shot_0001')
    saved=store.snapshot()['units']['image']['shot_0001']['submission']
    output=run/'comfy/output'/run.name/'start_images/shot_0001_00001_.png';output.parent.mkdir(parents=True)
    write_png(output,width,height)
    output_node=template.mapping['output']['node_id']
    history[prompt]=dict(prompt=[1,prompt,graph,{'client_id':saved['client_id']},[output_node]],
        status=dict(completed=True,status_str='success'),outputs={output_node:{'images':[dict(filename=output.name,
        subfolder=f'{run.name}/start_images',type='output')]}})
    monkeypatch.setattr(recovery,'HttpClient',lambda *a:HttpClient(*a,transport=transport))
    if missing_binding:Path(binding['identity'].path).unlink()
    before=store.snapshot();original_posts=sum(call[0]=='POST' for call in transport.calls)
    result=recovery.reconcile_submission(run,'start_images','shot_0001')
    assert sum(call[0]=='POST' for call in transport.calls)==original_posts==1
    assert store.snapshot()==before
    if missing_binding:
        assert result.state=='unresolved'
        assert not Path(binding['identity'].path).exists()
    else:
        assert result.state=='completed',result.reason
        assert result.output_identities[0].sha256==hash_file(output).sha256
        assert expected_leaves<={identity.path for identity in result.evidence_identities}
