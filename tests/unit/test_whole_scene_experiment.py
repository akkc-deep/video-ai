"""A lost acceptance must never turn a diagnostic experiment into two jobs."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
from pathlib import Path
from threading import Thread
from uuid import uuid4

import pytest


def module():
    return importlib.import_module('video_ai.experiments.whole_scene_case')


@pytest.fixture
def case(tmp_path):
    m = module()
    source = tmp_path/'original'; source.mkdir()
    picture = source/'start.png'; picture.write_bytes(b'original image')
    model = source/'model'; model.write_bytes(b'original weights')
    graph = json.loads(Path('workflows/wan22_i2v_14b_api.json').read_text(encoding='utf-8'))
    graph['129:98']['inputs'].update(width=768, height=432, length=321)
    graph['97']['inputs']['image'] = 'start.png'
    graph['108']['inputs']['filename_prefix'] = 'candidate'
    graph['129:93']['inputs']['text'] = 'Reviewed visual prompt'
    root = tmp_path/'experiment'
    m.freeze_case(root, source_run=source, graph=graph,
                  dependencies={'start': picture, 'model': model},
                  runtime={'wan_seconds': 7200, 'service_start_seconds': 300})
    return root, source


def test_native_budget_has_no_overlap_or_missing_retained_frame():
    value = module().native_budget()
    assert value == {'requested_frames': 321, 'retained_frames': 320,
                     'source_start': 0, 'source_end': 320, 'fps': 16,
                     'duration_seconds': 20}


@pytest.mark.parametrize('name', ['start.png', 'model'])
def test_source_identity_drift_rejected_before_any_submission(case, name):
    root, source = case
    (source/name).write_bytes(b'changed')
    with pytest.raises(ValueError, match='identity|changed'):
        module().verify_case(root)
    assert not (root/'intent.json').exists()


def test_graph_drift_rejected(case):
    root, _ = case
    (root/'graph.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='identity|changed'):
        module().verify_case(root)


@pytest.mark.parametrize('node,field,value', [
    ('129:98', 'length', 317), ('129:98', 'width', 640),
    ('129:162', 'value', 24), ('129:128', 'value', 20),
    ('129:126', 'value', 1.0), ('129:131', 'value', True),
    ('129:86', 'sampler_name', 'heun'), ('129:127', 'value', 21)])
def test_experiment_never_silently_lowers_fixed_settings(case, tmp_path, node, field, value):
    root, source = case
    graph = json.loads((root/'graph.json').read_text(encoding='utf-8'))
    graph[node]['inputs'][field] = value
    with pytest.raises(ValueError):
        module().freeze_case(tmp_path/'bad', source_run=source, graph=graph,
                             dependencies={'start': source/'start.png'}, runtime={})


def test_source_cannot_be_used_as_experiment_directory(case):
    root, source = case
    graph = json.loads((root/'graph.json').read_text(encoding='utf-8'))
    with pytest.raises(ValueError, match='overlap|source'):
        module().freeze_case(source/'experiment', source_run=source, graph=graph,
                             dependencies={}, runtime={})
    assert sorted(p.name for p in source.iterdir()) == ['model', 'start.png']


@pytest.fixture
def server():
    state = {'posts': 0, 'graph': None, 'client': None, 'lose_response': False,
             'pid': str(uuid4()), 'fail': False, 'conflict': False}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def reply(self, value):
            body = json.dumps(value).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        def do_POST(self):
            value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state.update(posts=state['posts']+1, graph=value['prompt'], client=value['client_id'])
            if state['lose_response']:
                self.connection.close(); return
            self.reply({'prompt_id': state['pid'], 'number': 1, 'node_errors': {}})
        def do_GET(self):
            if self.path == '/queue': self.reply({'queue_running': [], 'queue_pending': []}); return
            prompt = [1, state['pid'], state['graph'], {'client_id': state['client']}, ['108']]
            if state['conflict']: prompt[3] = {'client_id': str(uuid4())}
            status = {'completed': True, 'status_str': 'error' if state['fail'] else 'success', 'messages': []}
            self.reply({state['pid']: {'prompt': prompt, 'status': status,
                'outputs': {'108': {'images': [{'filename': 'candidate_00001_.mp4', 'subfolder': '', 'type': 'output'}]}}}})
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=httpd.serve_forever, daemon=True); thread.start()
    yield f'http://127.0.0.1:{httpd.server_port}', state
    httpd.shutdown(); httpd.server_close(); thread.join()


def track(root, url):
    runner = importlib.import_module('video_ai.experiments.whole_scene_runner')
    from video_ai.adapters.common import HttpClient
    return runner.submit_or_recover(root, HttpClient(url, 3, module().Evidence(root)), poll_seconds=.01)


@pytest.mark.parametrize('lost', [False, True])
def test_reenter_after_acceptance_or_lost_http_never_posts_twice(case, server, lost):
    root, source = case; url, state = server; state['lose_response'] = lost
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    result = track(root, url)
    assert result['status'] == 'completed'
    assert result['prompt_id'] == state['pid']
    assert track(root, url)['status'] == 'completed'
    assert state['posts'] == 1
    assert before == {p.name: p.read_bytes() for p in source.iterdir()}
    assert len(list((root/'http').glob('*.request.json'))) >= 3


def test_oom_is_terminal_and_does_not_retry(case, server):
    root, _ = case; url, state = server; state['fail'] = True
    assert track(root, url)['status'] == 'failed'
    assert track(root, url)['status'] == 'failed'
    assert state['posts'] == 1


def test_original_history_identity_must_match(case, server):
    root, _ = case; url, state = server; state['conflict'] = True
    with pytest.raises(ValueError, match='identity|conflict'):
        track(root, url)
    assert state['posts'] == 1


def test_existing_intent_without_known_task_is_query_only(case, server):
    root, _ = case; url, state = server
    m = module(); m.write_json(root/'intent.json', {
        'case_sha256': m.identity(root/'case.json')['sha256'],
        'graph_sha256': m.identity(root/'graph.json')['sha256'],
        'client_id': str(uuid4()), 'deadline_unix': 0})
    assert track(root, url)['status'] == 'unknown'
    assert state['posts'] == 0


def test_second_process_cannot_enter_locked_case(case):
    from video_ai.experiments.whole_scene_runner import case_lock
    root, _ = case
    with case_lock(root):
        with pytest.raises(FileExistsError):
            with case_lock(root): pass


def test_post_guard_can_refuse_a_replaced_service_without_creating_intent(case, server):
    from video_ai.experiments.whole_scene_runner import submit_or_recover
    from video_ai.adapters.common import HttpClient
    root,_=case;url,state=server
    def refuse(): raise RuntimeError('service ownership changed')
    with pytest.raises(RuntimeError,match='ownership'):
        submit_or_recover(root,HttpClient(url,3,module().Evidence(root)),before_post=refuse)
    assert state['posts']==0
    assert not (root/'intent.json').exists()


def test_model_paths_must_match_actual_service_search_order(tmp_path):
    from video_ai.experiments.whole_scene_case import validate_model_loading
    model_root=tmp_path/'models';comfy=tmp_path/'comfy';comfy.mkdir()
    roles={'wan_high':('diffusion_models','high'), 'wan_low':('diffusion_models','low'),
           'text_encoder':('text_encoders','text'), 'vae':('vae','vae')}
    models={}
    for name,(folder,file) in roles.items():
        path=model_root/folder/file;path.parent.mkdir(exist_ok=True,parents=True);path.write_bytes(b'weight');models[name]=path
    validate_model_loading(models,model_root,comfy)
    outside=tmp_path/'high';outside.write_bytes(b'other')
    with pytest.raises(ValueError): validate_model_loading(dict(models,wan_high=outside),model_root,comfy)
    (model_root/'unet').mkdir();(model_root/'unet/high').write_bytes(b'shadow')
    with pytest.raises(ValueError): validate_model_loading(models,model_root,comfy)
    (model_root/'unet/high').unlink()
    (comfy/'extra_model_paths.yaml').write_text('other: {}',encoding='utf-8')
    with pytest.raises(ValueError): validate_model_loading(models,model_root,comfy)


def test_windows_desktop_gpu_contexts_are_recorded_without_killing_them():
    from video_ai.experiments.whole_scene_runner import validate_gpu_processes
    assert validate_gpu_processes([{'Id':1,'ProcessName':'dwm'}, {'Id':2,'ProcessName':'msedgewebview2'}]) == [1,2]
    with pytest.raises(RuntimeError):
        validate_gpu_processes([{'Id':3,'ProcessName':'python'}])
    with pytest.raises(RuntimeError):
        validate_gpu_processes([{'Id':4,'ProcessName':'unidentified-compute'}])


def test_dead_owned_service_stops_tracking_without_waiting_or_retry(case,server):
    from video_ai.experiments.whole_scene_runner import submit_or_recover
    from video_ai.adapters.common import HttpClient
    root,_=case;url,state=server
    def died(): raise RuntimeError('owned process exited')
    with pytest.raises(RuntimeError,match='exited'):
        submit_or_recover(root,HttpClient(url,3,module().Evidence(root)),service_alive=died)
    assert state['posts']==1
    assert (root/'intent.json').is_file()
    assert not (root/'submission-result.json').exists()


def test_experiment_respects_existing_global_gpu_lease(tmp_path):
    from video_ai.experiments.whole_scene_runner import gpu_slot
    lock=tmp_path/'gpu.lock'
    with gpu_slot(lock,tmp_path/'case'):
        with pytest.raises(FileExistsError):
            with gpu_slot(lock,tmp_path/'other'): pass
    assert not lock.exists()
