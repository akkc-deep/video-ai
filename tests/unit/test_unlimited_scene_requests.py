"""Long production requests reach Ollama intact without application size caps."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import time

from http_helpers import Response, ScriptedTransport
from video_ai.adapters.common import HttpClient, JSON_LIMIT
from video_ai.adapters.ollama import OllamaPlanner, ollama_body
from video_ai.runtime.logging import RunLogger


def test_scene_context_grows_for_complete_long_input_without_output_cap():
    prompt = '完整原文' * 10000
    body = ollama_body(prompt, {'type': 'object'}, scene_planning=True)
    assert body['prompt'] == prompt
    assert body['options']['num_ctx'] > len(prompt.encode('utf-8')) + 2048
    assert body['options']['num_predict'] == -1


def test_local_json_can_send_and_receive_more_than_default_byte_budget(runtime_run):
    payload = {'complete': 'x' * (JSON_LIMIT + 1)}
    raw = json.dumps(payload).encode()
    transport = ScriptedTransport(lambda request, timeout: Response(raw))
    client = HttpClient('http://127.0.0.1:11435', 1, RunLogger(runtime_run[0]), transport=transport)
    response = client.request('POST', '/api/generate', json_body=payload, max_bytes=None,
                              unlimited=True)
    assert response.body == raw
    assert json.loads(transport.calls[0][2]) == payload
    assert transport.calls[0][3] is None


def test_scene_planner_waits_for_owned_local_generation_without_timeout(runtime_run):
    transport = ScriptedTransport(lambda request, timeout: Response(
        dict(model='qwen3:8b', done=True, done_reason='stop', response='{}')))
    client = HttpClient('http://127.0.0.1:11435', 0.01, RunLogger(runtime_run[0]), transport=transport)
    planner = OllamaPlanner(client)
    assert planner.generate('entire input', schema={}, request_id='scene_plan_initial') == {}
    assert transport.calls[0][3] is None


def test_real_local_scene_response_survives_the_former_network_deadline(runtime_run):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            time.sleep(0.1)
            raw=json.dumps(dict(model='qwen3:8b', done=True, response='{}')).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        client=HttpClient(f'http://127.0.0.1:{server.server_port}',0.01,RunLogger(runtime_run[0]))
        assert OllamaPlanner(client).generate('input',schema={},request_id='scene_plan_initial')=={}
    finally:
        server.shutdown();server.server_close();thread.join(2)


def test_compact_scene_request_keeps_complete_source_facts_and_sample_mapping():
    from unit.test_production_scenes import scene_inputs
    from video_ai.config import ScenePlanningSettings
    from video_ai.planning.production_scenes import make_scene_schema
    from video_ai.runtime.production_scene_plan import _prompt
    script,units,timeline=scene_inputs('湖面静。\n白鸟飞。',samples=[48000,48000])
    units['planner']={'evidence':'audit'*10000}
    settings=ScenePlanningSettings()
    body=ollama_body(_prompt(script,units,timeline,settings),
        make_scene_schema(script,units,timeline,settings),scene_planning=True,scene_compact=True)
    payload=json.JSONDecoder().raw_decode(body['prompt'].split('\nSCENE_COMPACT_INPUT_JSON\n')[1])[0]
    assert payload['decoded_text']==script.text
    assert [row[0] for row in payload['units']]==['speech_0001','speech_0002']
    assert [row[1:3] for row in payload['units']]==[[0,4],[5,9]]
    assert [row[3:5] for row in payload['units']]==[
        [timeline.clips[0].start_sample,timeline.clips[0].end_sample],
        [timeline.clips[1].start_sample,timeline.clips[1].end_sample]]
    assert [row[5] for row in payload['units']]==[
        {k:v for k,v in units['semantic_specs'][uid]['facts'].items() if v not in (None,[])}
        for uid in ['speech_0001','speech_0002']]
    assert len(body['prompt'].encode())<len(units['planner']['evidence'])
    assert body['options']['num_predict']==-1


def test_truncated_service_prompt_cannot_be_used_as_a_scene_plan(tmp_path):
    from video_ai.runtime.production_scene_plan import check_scene_context_log
    import pytest
    path=tmp_path/'ollama.stderr'
    path.write_text('msg="truncating input prompt" limit=20482 prompt=176748\n',encoding='utf-8')
    with pytest.raises(ValueError,match='truncat'):
        check_scene_context_log(path)
