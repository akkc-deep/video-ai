"""Original identity recovery, immutable raw HTTP evidence, and zero re-POST."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from video_ai.planning.production_scenes import canonical_digest


class Store:
    def __init__(self, root):
        self.run_dir = root; self.root = root / 'production/scene-clips'; self.root.mkdir(parents=True)
        self.frozen = SimpleNamespace(run_id='run'); self.paths = None; self.lock = None; self.threads = []
    def assert_owned(self): pass
    def clip_dir(self, clip_id): return self.root / clip_id
    def path(self, name): return name if isinstance(name, Path) and name.is_absolute() else self.root / name
    def read(self, name):
        path = self.path(name); return json.loads(path.read_bytes()) if path.exists() else None
    def write(self, name, value):
        return self.write_bytes(name, json.dumps(value, sort_keys=True, ensure_ascii=False).encode())
    def write_bytes(self, name, value):
        import threading
        self.threads.append(threading.get_ident()); path = self.path(name); path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists(): assert path.read_bytes() == value
        else: path.write_bytes(value)
        return path
    def artifact(self, path):
        path = self.path(path); raw = path.read_bytes()
        return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    def validate_artifact(self, value):
        assert self.artifact(Path(value['path'])) == value; return Path(value['path'])
    def capture_guard(self, request, graph): return self.assert_owned


@pytest.fixture
def transaction(runtime_run):
    store = Store(runtime_run[0]); clip = 'scene_0001_clip_0001'
    graph = {'108': {'class_type': 'Save', 'inputs': {'filename_prefix': f'run/scene_clips/{clip}/attempt_0001'}}}
    request = dict(schema_version=2, production_strategy='paragraph_jimeng_v1', run_id='run', scene_id='scene_0001',
        clip_id=clip, inputs_sha256='a'*64, budget={}, parameters={}, narration_bindings=[], comparison_images=[],
        selected_image={}, input_sha256='b'*64, parent=None, graph_sha256=canonical_digest(graph))
    from video_ai.runtime.workflows import WorkflowTemplate
    template = WorkflowTemplate(graph, dict(nodes={'108':'Save'},inputs={'output_prefix':dict(node_id='108',input='filename_prefix')},models={},output={'node_id': '108', 'collection': 'images'}))
    return store, request, graph, template


class Client:
    def __init__(self, store, request, graph, *, lose_response=False):
        self.store=store; self.request=request; self.graph=graph; self.pid=str(uuid4()); self.cid=None; self.posts=0; self.lose_response=lose_response; self.info_calls=0
        self.output=store.run_dir/'comfy/output/run/scene_clips'/request['clip_id']/'attempt_0001_00001.mp4'
        self.output.parent.mkdir(parents=True); self.output.write_bytes(b'owned model output')
    def response(self, value): return dict(status=200, headers={'Content-Type':'application/json'}, body=json.dumps(value).encode())
    def object_info(self, *, timeout):
        self.info_calls+=1
        return self.response({'Save':dict(input={'required':{'filename_prefix':['STRING']}},output_node=True)})
    def submit(self, graph, *, client_id, timeout):
        self.posts+=1; self.cid=client_id
        if self.lose_response: raise TimeoutError('response lost')
        return self.response(dict(prompt_id=self.pid, number=1.0, node_errors={}))
    def queue(self, *, timeout): return self.response(dict(queue_running=[], queue_pending=[]))
    def history(self, prompt_id=None, *, timeout):
        return self.response({self.pid:dict(prompt=[1,self.pid,self.graph,dict(client_id=self.cid),['108']],
            status=dict(status_str='success',completed=True,messages=[]), outputs={'108':{'images':[dict(filename=self.output.name,
            subfolder=f'run/scene_clips/{self.request["clip_id"]}',type='output')]}})})


def test_once_only_submission_and_readonly_reconstruction(transaction):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip, validate_scene_submission
    import threading
    store, request, graph, template=transaction; client=Client(store,request,graph)
    result=recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    assert result['output']==store.artifact(client.output) and result['prompt_id']==client.pid
    assert set(result)==set('schema_version run_id clip_id intent_sha256 accepted_sha256 prompt_id history_evidence output'.split())
    assert result==validate_scene_submission(store,request,graph)
    again=recover_or_submit_scene_clip(store,request,graph,client=None,template=template,ensure_service=lambda:pytest.fail('service restart'),logger=None,timeout=1)
    assert again==result and client.posts==1
    assert set(store.threads)=={threading.get_ident()}


def test_lost_post_response_recovers_original_identity_without_repost(transaction):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip, SceneSubmitUnknown
    store,request,graph,template=transaction; client=Client(store,request,graph,lose_response=True)
    with pytest.raises(SceneSubmitUnknown):
        recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    result=recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    assert result['prompt_id']==client.pid and client.posts==1 and client.info_calls==1


def test_raw_accepted_response_recovers_missing_accepted_index(transaction):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip
    store,request,graph,template=transaction; client=Client(store,request,graph)
    original=store.write
    def interrupted(name,value):
        if str(name).endswith('accepted.json'): raise KeyboardInterrupt()
        return original(name,value)
    store.write=interrupted
    with pytest.raises(KeyboardInterrupt):
        recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    store.write=original
    result=recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    assert result['prompt_id']==client.pid and client.posts==1


def test_same_prompt_conflict_is_durable(transaction):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip
    from video_ai.runtime.production_state import ProductionRefused
    store,request,graph,template=transaction; client=Client(store,request,graph)
    def conflict(*,timeout): return client.response(dict(queue_running=[[1,client.pid,{},dict(client_id=client.cid)]],queue_pending=[]))
    client.queue=conflict
    with pytest.raises(ProductionRefused, match='conflict'):
        recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    terminal=store.read(store.clip_dir(request['clip_id'])/'terminal.json')
    assert terminal['status']=='identity_conflict' and client.posts==1
    client.queue=lambda **kw:client.response(dict(queue_running=[],queue_pending=[]))
    with pytest.raises(ProductionRefused):
        recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:pytest.fail(),logger=None,timeout=1)


def test_completed_raw_history_recovers_missing_submission_without_service(transaction):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip
    store,request,graph,template=transaction; client=Client(store,request,graph); original=store.write
    def interrupted(name,value):
        if str(name).endswith('submission.json'): raise KeyboardInterrupt()
        return original(name,value)
    store.write=interrupted
    with pytest.raises(KeyboardInterrupt):
        recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    store.write=original
    result=recover_or_submit_scene_clip(store,request,graph,client=None,template=template,ensure_service=lambda:pytest.fail('GET or service on local replay'),logger=None,timeout=1)
    assert result['prompt_id']==client.pid and client.posts==1


@pytest.mark.parametrize('mutation', ['graph', 'accepted_number', 'http_body', 'output'])
def test_readonly_reconstruction_refuses_tampered_evidence(transaction,mutation):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip,validate_scene_submission
    from video_ai.runtime.production_state import ProductionRefused
    store,request,graph,template=transaction; client=Client(store,request,graph)
    recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    directory=store.clip_dir(request['clip_id'])
    if mutation=='graph': (directory/'graph.json').write_text('{}')
    elif mutation=='accepted_number':
        value=store.read(directory/'accepted.json'); value['number']=True
        (directory/'accepted.json').write_text(json.dumps(value))
    elif mutation=='http_body': next((directory/'http').glob('*.body')).write_bytes(b'{}')
    else: client.output.write_bytes(b'changed original output')
    with pytest.raises((ProductionRefused,AssertionError)):
        validate_scene_submission(store,request,graph)
    assert client.posts==1


def test_float_coercion_preserves_exact_graph_identity(transaction):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip
    from copy import deepcopy
    store,request,graph,template=transaction
    graph['108']['inputs']['fps']=16; request['graph_sha256']=canonical_digest(graph)
    client=Client(store,request,deepcopy(graph)); client.graph['108']['inputs']['fps']=16.0
    result=recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    assert result['prompt_id']==client.pid


def test_lossy_seed_float_is_identity_conflict(transaction):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip
    from video_ai.runtime.production_state import ProductionRefused
    from copy import deepcopy
    store,request,graph,template=transaction
    graph['108']['inputs']['seed']=9007199254740993; request['graph_sha256']=canonical_digest(graph)
    client=Client(store,request,deepcopy(graph)); client.graph['108']['inputs']['seed']=float(9007199254740993)
    with pytest.raises(ProductionRefused,match='conflict'):
        recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    assert client.posts==1


def test_raw_post_rejection_recovers_missing_terminal_without_get(transaction):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip
    from video_ai.runtime.production_state import ProductionRefused
    store,request,graph,template=transaction; client=Client(store,request,graph); original=store.write
    def rejected(graph,*,client_id,timeout):
        client.posts+=1
        return dict(status=400,headers={'Content-Type':'application/json'},body=b'{"error":"bad node"}')
    client.submit=rejected
    def interrupted(name,value):
        if str(name).endswith('terminal.json'): raise KeyboardInterrupt()
        return original(name,value)
    store.write=interrupted
    with pytest.raises(KeyboardInterrupt):
        recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    store.write=original
    with pytest.raises(ProductionRefused,match='rejected'):
        recover_or_submit_scene_clip(store,request,graph,client=None,template=template,ensure_service=lambda:pytest.fail('GET after rejection'),logger=None,timeout=1)
    assert client.posts==1


def test_remote_template_failure_precedes_intent_and_post(transaction):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip
    from video_ai.runtime.production_state import ProductionRefused
    store,request,graph,template=transaction; client=Client(store,request,graph)
    client.object_info=lambda **kw:client.response({})
    with pytest.raises(ProductionRefused,match='remote'):
        recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    assert store.read(store.clip_dir(request['clip_id'])/'intent.json') is None
    assert client.posts==0
    responses=list((store.run_dir/'logs/production/scene-clips/service').glob('*.response.json'))
    assert len(responses)==1 and json.loads(responses[0].read_bytes())['status']==200


def test_transient_get_failure_retries_within_original_tracking_budget(transaction):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip
    store,request,graph,template=transaction; client=Client(store,request,graph); original=client.queue; calls=[]
    def transient(*,timeout):
        calls.append(timeout)
        if len(calls)==1: raise TimeoutError('temporary GET connection failure')
        return original(timeout=timeout)
    client.queue=transient
    result=recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=3)
    assert result['prompt_id']==client.pid and client.posts==1 and len(calls)==2 and calls[1]<calls[0]


def test_terminal_is_readonly_validated_and_tampering_is_refused(transaction):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip,validate_scene_terminal
    from video_ai.runtime.production_state import ProductionRefused
    store,request,graph,template=transaction; client=Client(store,request,graph)
    client.queue=lambda **kw:client.response(dict(queue_running=[[1,client.pid,{},dict(client_id=client.cid)]],queue_pending=[]))
    with pytest.raises(ProductionRefused):
        recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    terminal=validate_scene_terminal(store,request,graph)
    assert terminal['status']=='identity_conflict' and client.posts==1
    path=store.clip_dir(request['clip_id'])/'terminal.json'; terminal['intent_sha256']='0'*64; path.write_text(json.dumps(terminal))
    with pytest.raises(ProductionRefused): validate_scene_terminal(store,request,graph)


def test_identity_terminal_requires_actual_original_conflict(transaction):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip,validate_scene_terminal
    from video_ai.runtime.production_state import ProductionRefused
    store,request,graph,template=transaction; client=Client(store,request,graph)
    result=recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    store.write(store.clip_dir(request['clip_id'])/'terminal.json',dict(schema_version=2,run_id='run',clip_id=request['clip_id'],
        intent_sha256=result['intent_sha256'],status='identity_conflict',evidence=[result['history_evidence']],reason='invented conflict'))
    with pytest.raises(ProductionRefused,match='lacks original'):
        validate_scene_terminal(store,request,graph)


@pytest.mark.parametrize('still_queued',[False,True])
def test_success_between_queue_and_history_requires_fresh_queue(transaction,still_queued):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip
    from video_ai.runtime.production_state import ProductionRefused
    store,request,graph,template=transaction; client=Client(store,request,graph); calls=[]
    def queue(*,timeout):
        calls.append(timeout)
        active=len(calls)==1 or still_queued
        return client.response(dict(queue_running=[[1,client.pid,graph,dict(client_id=client.cid)]] if active else [],queue_pending=[]))
    client.queue=queue
    if still_queued:
        with pytest.raises(ProductionRefused,match='completed history conflicts'):
            recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    else:
        result=recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
        assert result['prompt_id']==client.pid
    assert client.posts==1 and len(calls)==2


@pytest.mark.parametrize('first_failure',[True,False])
def test_retained_history_failure_or_different_output_cannot_be_erased(transaction,first_failure):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip,_record_http,validate_scene_terminal
    from video_ai.runtime.production_state import ProductionRefused
    store,request,graph,template=transaction; client=Client(store,request,graph); original=store.write; history=client.history
    if first_failure:
        def failed(prompt_id=None,*,timeout):
            value=json.loads(history(prompt_id,timeout=timeout)['body'])
            value[client.pid]['status']=dict(status_str='error',completed=False,messages=[['execution_error',{}]])
            return client.response(value)
        client.history=failed
    def interrupted(name,value):
        if str(name).endswith('terminal.json' if first_failure else 'submission.json'): raise KeyboardInterrupt()
        return original(name,value)
    store.write=interrupted
    with pytest.raises(KeyboardInterrupt):
        recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    store.write=original; client.history=history
    if not first_failure:
        client.output=client.output.with_name('attempt_0001_00002.mp4'); client.output.write_bytes(b'different owned output')
    intent=store.read(store.clip_dir(request['clip_id'])/'intent.json')
    _record_http(store,request,intent,'GET','/history/'+client.pid,lambda t:client.history(client.pid,timeout=t),1,graph)
    with pytest.raises(ProductionRefused,match='execution failed|outputs conflict'):
        recover_or_submit_scene_clip(store,request,graph,client=None,template=template,ensure_service=lambda:pytest.fail('service needed despite deterministic retained evidence'),logger=None,timeout=1)
    assert store.read(store.clip_dir(request['clip_id'])/'submission.json') is None
    assert validate_scene_terminal(store,request,graph)['status']==('execution_failed' if first_failure else 'identity_conflict')
    assert client.posts==1


def test_orphan_queue_response_cannot_erase_original_proof(transaction):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip,validate_scene_submission
    from video_ai.runtime.production_state import ProductionRefused
    store,request,graph,template=transaction; client=Client(store,request,graph)
    recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    queue_request=next(p for p in (store.clip_dir(request['clip_id'])/'http').glob('*.request.json') if store.read(p)['route']=='/queue')
    queue_request.unlink()
    with pytest.raises(ProductionRefused,match='orphan'):
        validate_scene_submission(store,request,graph)


def test_raw_body_before_response_metadata_is_preserved_and_get_recovered(transaction):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip
    store,request,graph,template=transaction; client=Client(store,request,graph); original=store.write
    def interrupted(name,value):
        if str(name).endswith('.response.json'): raise KeyboardInterrupt()
        return original(name,value)
    store.write=interrupted
    with pytest.raises(KeyboardInterrupt):
        recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    raw_body=next((store.clip_dir(request['clip_id'])/'http').glob('*.body')); saved_bytes=raw_body.read_bytes()
    store.write=original
    result=recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    assert result['prompt_id']==client.pid and client.posts==1 and raw_body.read_bytes()==saved_bytes


def test_unknown_original_id_failure_creates_valid_terminal_without_repost(transaction):
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip,SceneSubmitUnknown,validate_scene_terminal
    from video_ai.runtime.production_state import ProductionRefused
    store,request,graph,template=transaction; client=Client(store,request,graph,lose_response=True)
    with pytest.raises(SceneSubmitUnknown):
        recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    original=client.history
    def failed(prompt_id=None,*,timeout):
        value=json.loads(original(prompt_id,timeout=timeout)['body'])
        value[client.pid]['status']=dict(status_str='error',completed=False,messages=[['execution_error',{}]])
        return client.response(value)
    client.history=failed
    with pytest.raises(ProductionRefused,match='execution failed'):
        recover_or_submit_scene_clip(store,request,graph,client=client,template=template,ensure_service=lambda:None,logger=None,timeout=1)
    assert validate_scene_terminal(store,request,graph)['status']=='execution_failed'
    assert store.read(store.clip_dir(request['clip_id'])/'accepted.json')['prompt_id']==client.pid
    assert client.posts==1
