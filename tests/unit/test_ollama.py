import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import pytest
from http_helpers import Response, ScriptedTransport


def client_for(runtime_run,body):
    from video_ai.adapters.common import HttpClient
    from video_ai.adapters.ollama import OllamaPlanner
    from video_ai.runtime.logging import RunLogger
    transport=ScriptedTransport(lambda r,t:Response(body))
    return OllamaPlanner(HttpClient('http://127.0.0.1:11435',1,RunLogger(runtime_run[0]),transport=transport)),transport


def test_single_structured_request_records_raw_evidence(runtime_run):
    from video_ai.adapters.common import HttpClient
    from video_ai.adapters.ollama import OllamaPlanner
    from video_ai.runtime.logging import RunLogger
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            body=json.dumps(dict(model='qwen3:8b',done=True,response='{"schema_version":1}')).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler); thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        planner=OllamaPlanner(HttpClient(f'http://127.0.0.1:{server.server_port}',2,RunLogger(runtime_run[0])))
        assert planner.generate('原文',schema={'type':'object'},request_id='initial')=={'schema_version':1}
    finally:server.shutdown();server.server_close();thread.join(2)
    assert len(requests)==1 and requests[0][0]=='/api/generate'
    body=requests[0][1]
    assert body==dict(model='qwen3:8b',prompt='原文',stream=False,format={'type':'object'},keep_alive=0,think=False,options=dict(temperature=0,num_predict=8192))
    run=runtime_run[0];assert (run/'logs/storyboard/initial.intent.json').exists()
    assert list((run/'logs/http').glob('*.body'))
    with pytest.raises(Exception):planner.generate('原文',schema={'type':'object'},request_id='initial')
    assert len(requests)==1


@pytest.mark.parametrize('inner',['{bad','{"x":1,"x":2}','{"x":NaN}','{"x":1e999}','[]'])
def test_only_done_invalid_inner_is_format_error(runtime_run,inner):
    from video_ai.adapters.ollama import OllamaFormatError
    p,t=client_for(runtime_run,dict(model='qwen3:8b',done=True,response=inner))
    with pytest.raises(OllamaFormatError):p.generate('prompt',schema={},request_id='initial')
    assert len(t.calls)==1


@pytest.mark.parametrize('bad',[dict(model='wrong',done=True,response='{}'),dict(model='qwen3:8b',done=False,response='{}'),{'error':'lost'},b'{bad'])
def test_unconfirmed_outer_never_qualifies_for_correction(runtime_run,bad):
    from video_ai.adapters.common import AdapterError
    p,t=client_for(runtime_run,bad)
    with pytest.raises(AdapterError) as exc:p.generate('prompt',schema={},request_id='initial')
    assert exc.value.kind.value=='ambiguous' and len(t.calls)==1


@pytest.mark.parametrize('failure',['disconnect','500','intent','response_evidence','wire_evidence_value'])
def test_lost_response_is_ambiguous_not_invalid_format(runtime_run,monkeypatch,failure):
    from video_ai.adapters.common import AdapterError
    from video_ai.runtime.logging import RunLogger
    p,t=client_for(runtime_run,dict(model='qwen3:8b',done=True,response='{}'))
    if failure=='disconnect':t.handler=lambda r,t:(_ for _ in ()).throw(ConnectionResetError('lost'))
    if failure=='500':t.handler=lambda r,t:Response({'error':'crash'},500)
    if failure in ('intent','response_evidence','wire_evidence_value'):
        original=RunLogger.save_json
        def fail(self,name,data):
            if name.endswith('.wire-content.json') and failure=='wire_evidence_value':raise ValueError('unconfirmed evidence persistence')
            if name.endswith('.intent.json') and failure=='intent' or name.endswith('.outer.json') and failure=='response_evidence':raise OSError('disk failure')
            return original(self,name,data)
        monkeypatch.setattr(RunLogger,'save_json',fail)
    with pytest.raises(AdapterError) as exc:p.generate('prompt',schema={},request_id='initial')
    assert exc.value.kind.value=='ambiguous' and len(t.calls)==(0 if failure=='intent' else 1)


def test_cpu_request_explicitly_disables_gpu_offload(runtime_run):
    from video_ai.adapters.ollama import OllamaPlanner
    p,t=client_for(runtime_run,dict(model='qwen3:8b',done=True,response='{}'))
    OllamaPlanner(p.http,cpu_only=True).generate('prompt',schema={},request_id='initial')
    body=json.loads(t.calls[0][2]);assert body['options']['num_gpu']==0
    assert body['keep_alive']==0 and len(t.calls)==1
def test_ollama_wire_schema_uses_fixed_keys_and_keeps_tuple_validation(tmp_path):
    from video_ai.adapters.ollama import ollama_schema,ollama_content
    schema={'type':'array','prefixItems':[{'type':'object','properties':{'shot_id':{'const':'a'}}},{'type':'object','properties':{'shot_id':{'const':'b'}}}], 'items':False,'minItems':2,'maxItems':2}
    wire=ollama_schema(schema)
    assert wire=={'type':'object','properties':dict(zip(['a','b'],schema['prefixItems'])),'required':['a','b'],'additionalProperties':False}
    assert schema['items'] is False and 'prefixItems' in schema
    assert ollama_content({'b':{'shot_id':'b'},'a':{'shot_id':'a'}},schema)==[{'shot_id':'a'},{'shot_id':'b'}]
    with pytest.raises(ValueError):ollama_content({'a':{'shot_id':'a'},'extra':{}},schema)


def test_real_wire_objects_roundtrip_exact_binding_requirements():
    from test_storyboard import real_timeline
    from storyboard_helpers import content_for
    from video_ai.planning.storyboard import plan_slots,make_model_schema,validate_model_content
    from video_ai.adapters.ollama import ollama_content
    slots=plan_slots(real_timeline());content=content_for(slots);schema=make_model_schema(slots)
    wire=json.loads(json.dumps(content))
    wire['shots']={s['shot_id']:dict(s,visual_requirements={r['unit_id']:r for r in s['visual_requirements']}) for s in wire['shots']}
    normalized=ollama_content(wire,schema)
    assert normalized==content
    validate_model_content(normalized,slots)
