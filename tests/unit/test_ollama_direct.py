"""The local llama interface reads complete results without Ollama's SSE cap."""
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread

import pytest


def test_direct_request_preserves_complete_prompt_and_has_no_generation_cap():
    from video_ai.runtime.ollama_direct import chat_prompt,completion_request
    body=dict(model='qwen3:8b',prompt='全文'*100000,think=False,format={'type':'object'},options={'temperature':0,'num_predict':-1})
    assert body['prompt'] in chat_prompt(body)
    request=completion_request(body,[10,20,30])
    assert request['prompt']==[10,20,30]
    assert request['n_keep']==3 and request['n_predict']==-1
    assert request['json_schema']==body['format']
    assert request['stream'] is False


def test_direct_backend_accepts_event_metadata_larger_than_eight_mib():
    from video_ai.runtime.ollama_direct import backend_json,completion_response
    raw=json.dumps(dict(content='{"ok":true}',stop=True,stop_type='eos',
        generation_settings={'grammar':'x'*(8*1024*1024+1)},tokens_predicted=5,tokens_evaluated=7)).encode()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(200);self.send_header('Content-Length',str(len(raw)))
            self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        original=backend_json(f'http://127.0.0.1:{server.server_port}/completion',{})
        result=completion_response('qwen3:8b',original)
    finally:server.shutdown();server.server_close();thread.join(2)
    assert result['response']=='{"ok":true}' and result['done'] is True
    assert result['model']=='qwen3:8b' and result['eval_count']==5 and result['prompt_eval_count']==7
    assert 'generation_settings' not in result


def test_direct_backend_truncation_cannot_be_reported_as_a_normal_completion():
    from video_ai.runtime.ollama_direct import completion_response
    result=completion_response('qwen3:8b',dict(content='{}',stop=True,stop_type='limit'))
    assert result['done_reason']=='length'
    with pytest.raises(ValueError):completion_response('qwen3:8b',{'error':'backend failed'})


@pytest.mark.parametrize('think',[False,True])
def test_literal_thinking_tag_inside_valid_json_is_preserved(think):
    from video_ai.runtime.ollama_direct import completion_response
    content='{"quote":"literal </think> in original text"}'
    assert completion_response('qwen3:8b',dict(content=content,stop=True),think=think)['response']==content


def test_direct_backend_must_evaluate_the_complete_tokenized_input():
    from video_ai.runtime.ollama_direct import completion_response
    with pytest.raises(ValueError,match='complete prompt'):
        completion_response('qwen3:8b',dict(content='{}',stop=True,tokens_evaluated=2),expected_prompt_tokens=3)


def test_model_blob_is_resolved_from_the_existing_ollama_manifest(tmp_path):
    from video_ai.runtime.ollama_direct import model_blob
    manifest=tmp_path/'manifests/registry.ollama.ai/library/qwen3/8b'
    manifest.parent.mkdir(parents=True)
    digest='a'*64;blob=tmp_path/'blobs'/('sha256-'+digest);blob.parent.mkdir();blob.write_bytes(b'existing model')
    manifest.write_text(json.dumps(dict(layers=[dict(mediaType='application/vnd.ollama.image.model',digest='sha256:'+digest)])))
    assert model_blob(tmp_path,'qwen3:8b')==blob
    with pytest.raises(ValueError):model_blob(tmp_path,'../../elsewhere')


def test_cuda_backend_environment_names_the_dll_without_mutating_parent(tmp_path):
    from video_ai.runtime.ollama_direct import backend_environment
    executable=tmp_path/'llama-server.exe';library=tmp_path/'cuda_v13/ggml-cuda.dll'
    library.parent.mkdir();library.write_bytes(b'installed library fixture')
    before=os.environ.get('GGML_BACKEND_PATH')
    env=backend_environment(executable)
    assert env['GGML_BACKEND_PATH']==str(library)
    assert str(library.parent) in env['PATH']
    assert os.environ.get('GGML_BACKEND_PATH')==before


@pytest.mark.skipif(os.name!='nt',reason='Windows process ownership')
def test_closing_backend_ownership_terminates_its_actual_child():
    from video_ai.runtime.ollama_direct import WindowsJob
    child=subprocess.Popen([sys.executable,'-B','-c','import time; time.sleep(60)'],
        creationflags=subprocess.CREATE_NO_WINDOW)
    job=None
    try:
        job=WindowsJob(child);job.close()
        assert child.wait(timeout=5) is not None
    finally:
        if job is not None:job.close()
        if child.poll() is None:child.terminate();child.wait(timeout=5)


def test_direct_attempt_is_not_repeated_without_explicit_retirement(tmp_path):
    from video_ai.runtime.production_scene_plan import direct_attempt
    from video_ai.planning.production_scenes import canonical_digest
    folder=tmp_path/'compact-v4';folder.mkdir()
    body={'model':'qwen3:8b'}
    (folder/'initial.intent.json').write_text(json.dumps(dict(request_id='scene_plan_direct_initial',body=body)))
    logger=SimpleNamespace(path=lambda name:tmp_path/'http')
    assert direct_attempt(folder,logger)==(folder,'scene_plan_direct_')
    (folder/'retired.json').write_text(json.dumps(dict(request_id='scene_plan_direct_initial',
        body_sha256=canonical_digest(body),reason='owned failed backend stopped for CUDA loader fix')))
    assert direct_attempt(folder,logger)==(folder/'attempt_0001','scene_plan_direct_attempt_0001_')


def test_direct_retirement_cannot_discard_a_completed_proposal(tmp_path):
    from video_ai.runtime.production_scene_plan import direct_attempt
    from video_ai.planning.production_scenes import canonical_digest
    body={};(tmp_path/'initial.intent.json').write_text(json.dumps(dict(request_id='scene_plan_direct_initial',body=body)))
    (tmp_path/'retired.json').write_text(json.dumps(dict(request_id='scene_plan_direct_initial',body_sha256=canonical_digest(body),reason='retry')))
    (tmp_path/'proposal.json').write_text('{}')
    with pytest.raises(ValueError,match='completed'):direct_attempt(tmp_path,SimpleNamespace(path=lambda name:tmp_path/'http'))
