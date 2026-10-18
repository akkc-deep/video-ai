from concurrent.futures import ThreadPoolExecutor
import json
import time
from uuid import uuid4
import pytest
from http_helpers import Response, ScriptedTransport


def test_attempt_submission_is_once_and_separate_from_main_shot(run_store,runtime_run):
    from video_ai.adapters.common import AdapterError
    client,transport,graph=setup_client(run_store,runtime_run,lambda r,t:Response({'prompt_id':str(uuid4()),'number':1,'node_errors':{}}))
    run_store.record_unit('shot','shot_0001','running')
    submission=client.submit_once(graph,stage='source_clips',kind='shot_attempt',unit_id='shot_0001:attempt_0001')
    assert submission.kind=='shot_attempt'
    assert run_store.snapshot()['units']['shot']['shot_0001']['submission'] is None
    saved=run_store.snapshot()['units']['shot_attempt']['shot_0001:attempt_0001']['submission']
    assert saved['state']=='accepted' and saved['prompt_id']==submission.prompt_id
    with pytest.raises(AdapterError):client.submit_once(graph,stage='source_clips',kind='shot_attempt',unit_id='shot_0001:attempt_0001')
    assert post_count(transport)==1


def test_attempt_stage_mismatch_posts_nothing(run_store,runtime_run):
    client,transport,graph=setup_client(run_store,runtime_run,lambda r,t:Response({'prompt_id':str(uuid4()),'number':1,'node_errors':{}}))
    for stage in ('start_images','upscale','preflight'):
        with pytest.raises(ValueError):client.submit_once(graph,stage=stage,kind='shot_attempt',unit_id='shot_0001:attempt_0001')
    assert post_count(transport)==0 and 'shot_attempt' not in run_store.snapshot()['units']


@pytest.mark.parametrize('lost',[False,True])
def test_attempt_tracking_preserves_completed_or_unknown_submission_without_repost(run_store,runtime_run,lost):
    from video_ai.adapters.common import AdapterError
    prompt_id=str(uuid4())
    def route(r,t):
        if r.method=='POST':
            if lost:raise ConnectionResetError('accepted reply lost')
            return Response({'prompt_id':prompt_id,'number':1,'node_errors':{}})
        if lost:return Response({})
        return Response({prompt_id:dict(status=dict(completed=True,status_str='success',messages=[]),outputs={'108':{'images':[dict(filename='clip.mp4',subfolder='run',type='output')]}})})
    client,transport,graph=setup_client(run_store,runtime_run,route)
    uid='shot_0001:attempt_0001'
    if lost:
        with pytest.raises(AdapterError):client.submit_once(graph,stage='source_clips',kind='shot_attempt',unit_id=uid)
    else:
        sub=client.submit_once(graph,stage='source_clips',kind='shot_attempt',unit_id=uid)
        client.wait_for(sub,deadline_seconds=.2,poll_seconds=.001)
        run_store.record_unit('shot_attempt',uid,'failed')
    saved=run_store.snapshot()['units']['shot_attempt'][uid]['submission']
    assert saved['state']==('ambiguous' if lost else 'completed')
    with pytest.raises(ValueError):run_store.update(lambda d:d['units']['shot_attempt'][uid].update(submission=None))
    with pytest.raises(AdapterError):client.submit_once(graph,stage='source_clips',kind='shot_attempt',unit_id=uid)
    assert post_count(transport)==1


def test_image_and_wan_same_shot_have_independent_once_submissions(run_store, runtime_run):
    from video_ai.adapters.common import AdapterError
    client, transport, graph = setup_client(run_store, runtime_run,
        lambda r,t: Response({'prompt_id':str(uuid4()),'number':1,'node_errors':{}}))
    image = client.submit_once(graph, stage='start_images', kind='image', unit_id='shot_0001')
    wan = submit(client, graph)
    assert image.prompt_id != wan.prompt_id
    assert set(run_store.snapshot()['units']['image']) == {'shot_0001'}
    with pytest.raises(AdapterError):
        client.submit_once(graph, stage='start_images', kind='image', unit_id='shot_0001')
    with pytest.raises(ValueError):
        client.submit_once(graph, stage='upscale', kind='image', unit_id='shot_0002')
    assert post_count(transport) == 2


def setup_client(run_store, runtime_run, handler):
    from video_ai.adapters.common import HttpClient
    from video_ai.adapters.comfyui import ComfyClient
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.workflows import WorkflowTemplate
    from unit.test_workflows import remote_info
    config = runtime_run[1]
    template = WorkflowTemplate.load(config.workflows['wan'],config.workflows['wan_mapping'],config.models)
    def route(request, timeout):
        if request.full_url.endswith('/object_info'):
            return Response(remote_info(template))
        return handler(request, timeout)
    transport = ScriptedTransport(route)
    logger = RunLogger(run_store.run_dir)
    client = ComfyClient(HttpClient('http://127.0.0.1:8188',.1,logger,transport=transport),run_store,logger)
    client.validate_template(template)
    return client, transport, template.instantiate({'start_image':'start.png'},output_prefix='run/shot_0001')


def submit(client, graph):
    return client.submit_once(graph,stage='source_clips',kind='shot',unit_id='shot_0001')


def post_count(transport):
    return sum(c[0] == 'POST' for c in transport.calls)


@pytest.mark.parametrize('failure', ['lost','invalid','server','explicit'])
def test_submit_failure_never_reposts_and_keeps_queue_history(run_store,runtime_run,failure):
    from video_ai.adapters.common import AdapterError
    def route(r,t):
        if r.method == 'POST':
            if failure == 'lost':
                raise ConnectionResetError('server accepted, reply lost')
            if failure == 'invalid':
                return Response({'prompt_id':'not-uuid','number':True,'node_errors':{}})
            return Response({'error':'invalid graph'},400 if failure == 'explicit' else 500)
        return Response({'queue_running':[],'queue_pending':[]} if '/queue' in r.full_url else {})
    client, transport, graph = setup_client(run_store,runtime_run,route)
    with pytest.raises(AdapterError):
        submit(client,graph)
    sub = run_store.snapshot()['units']['shot']['shot_0001']['submission']
    assert sub['state'] == ('rejected' if failure == 'explicit' else 'ambiguous')
    assert sub['prompt_id'] is None
    assert PathExists(sub['request_path'])
    with pytest.raises(AdapterError):
        submit(client,graph)
    assert post_count(transport) == 1
    if failure != 'explicit':
        assert any('/queue' in c[1] for c in transport.calls)
        assert any('/history' in c[1] for c in transport.calls)


def PathExists(value):
    from pathlib import Path
    return Path(value).exists()


def test_accepted_is_durable_before_tracking_and_success_is_not_media_validation(run_store,runtime_run):
    prompt_id = str(uuid4())
    def route(r,t):
        if r.method == 'POST':
            return Response({'prompt_id':prompt_id,'number':1,'node_errors':{}})
        return Response({prompt_id:{'status':{'completed':True,'status_str':'success','messages':[]},
                                    'outputs':{'108':{'images':[{'filename':'clip.mp4','subfolder':'run','type':'output'}]}}}})
    client, transport, graph = setup_client(run_store,runtime_run,route)
    submission = submit(client,graph)
    sub = run_store.snapshot()['units']['shot']['shot_0001']['submission']
    assert sub['state'] == 'accepted' and sub['prompt_id'] == prompt_id
    result = client.wait_for(submission,deadline_seconds=.2,poll_seconds=.001)
    assert result.prompt_id == prompt_id
    assert result.outputs[0]['filename'] == 'clip.mp4'
    assert run_store.snapshot()['units']['shot']['shot_0001']['status'] == 'running'
    assert run_store.snapshot()['units']['shot']['shot_0001']['submission']['state'] == 'completed'
    assert post_count(transport) == 1
    assert all('/history/'+prompt_id in c[1] for c in transport.calls if '/history' in c[1])


@pytest.mark.parametrize('mode',['unknown','unavailable','running','error','empty','escape'])
def test_tracking_ambiguous_failed_and_bad_outputs(run_store,runtime_run,mode):
    from video_ai.adapters.common import AdapterError
    prompt_id = str(uuid4())
    def route(r,t):
        if r.method == 'POST':
            return Response({'prompt_id':prompt_id,'number':0,'node_errors':{}})
        if '/queue' in r.full_url:
            return Response({'queue_running':[[0,prompt_id,{},{}]],'queue_pending':[]})
        if mode == 'unavailable':
            raise TimeoutError('GET unavailable')
        if mode in ('unknown','running'):
            return Response({})
        if mode == 'error':
            return Response({prompt_id:{'status':{'completed':False,'status_str':'error','messages':[['execution_error',{'node_id':'97','exception_message':'bad image'}]]},'outputs':{}}})
        outputs = [] if mode == 'empty' else [{'filename':'../escape.mp4','subfolder':'','type':'output'}]
        return Response({prompt_id:{'status':{'completed':True,'status_str':'success','messages':[]},'outputs':{'108':{'images':outputs}}}})
    client, transport, graph = setup_client(run_store,runtime_run,route)
    sub = submit(client,graph)
    started = time.monotonic()
    with pytest.raises(AdapterError) as caught:
        client.wait_for(sub,deadline_seconds=.035,poll_seconds=.005)
    assert time.monotonic() - started < 1
    assert caught.value.evidence_paths
    assert all(p.exists() for p in caught.value.evidence_paths)
    assert post_count(transport) == 1
    saved = run_store.snapshot()['units']['shot']['shot_0001']['submission']
    assert saved['state'] == ('failed' if mode in ('error','empty','escape') else 'ambiguous')
    assert saved['prompt_id'] == prompt_id


def test_accepted_write_failure_retains_intent_and_raw_reply(run_store,runtime_run,monkeypatch):
    from video_ai.adapters.common import AdapterError
    prompt_id = str(uuid4())
    client, transport, graph = setup_client(run_store,runtime_run,lambda r,t:Response({'prompt_id':prompt_id,'number':1,'node_errors':{}}) if r.method=='POST' else Response({}))
    original = run_store._write
    def fail_accepted(data):
        record = data['units']['shot'].get('shot_0001',{}).get('submission')
        if record and record['state'] in ('accepted','ambiguous'):
            raise OSError('disk full after acceptance')
        original(data)
    monkeypatch.setattr(run_store,'_write',fail_accepted)
    with pytest.raises(AdapterError):
        submit(client,graph)
    assert run_store.snapshot()['units']['shot']['shot_0001']['submission']['state'] == 'intent'
    assert any(prompt_id.encode() in p.read_bytes() for p in (run_store.run_dir/'logs/http').glob('*.body'))
    with pytest.raises(AdapterError):
        submit(client,graph)
    assert post_count(transport) == 1


def test_concurrent_same_unit_can_only_post_once(run_store,runtime_run):
    from video_ai.adapters.common import AdapterError
    client, transport, graph = setup_client(run_store,runtime_run,lambda r,t:Response({'prompt_id':str(uuid4()),'number':1,'node_errors':{}}))
    def attempt():
        try:
            return submit(client,graph)
        except AdapterError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _:attempt(),range(2)))
    assert sum(r is not None for r in results) == 1
    assert post_count(transport) == 1


@pytest.mark.parametrize('status',[None,[],{'messages':None},{'completed':True,'status_str':'success','messages':'bad'}])
def test_malformed_history_is_recorded_as_invalid_result(run_store,runtime_run,status):
    from video_ai.adapters.common import AdapterError
    prompt_id=str(uuid4())
    def route(r,t):
        if r.method=='POST':return Response({'prompt_id':prompt_id,'number':1,'node_errors':{}})
        return Response({prompt_id:{'status':status,'outputs':{}}})
    client,transport,graph=setup_client(run_store,runtime_run,route)
    submission=submit(client,graph)
    with pytest.raises(AdapterError) as caught:
        client.wait_for(submission,deadline_seconds=.3,poll_seconds=.01)
    assert caught.value.kind.value=='invalid_result'
    assert run_store.snapshot()['units']['shot']['shot_0001']['submission']['state']=='failed'
    assert post_count(transport)==1
