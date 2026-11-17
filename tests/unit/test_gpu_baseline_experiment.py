import json
from uuid import uuid4

import pytest


def api():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('gpu_baseline_experiment', Path(__file__).parents[2]/'scripts/benchmark_local_gpu.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_graph_rebinding_changes_only_namespace_and_image():
    module = api()
    graph = {'97': {'inputs': {'image': 'old.png'}}, '108': {'inputs': {'filename_prefix': 'old'}},
             'sampler': {'inputs': {'seed': 17, 'steps': 40, 'cfg': 3.5}}}
    result = module.rebind_graph(graph, 'frozen/start.png', 'warm1')
    assert result['sampler'] == graph['sampler']
    assert graph['97']['inputs']['image'] == 'old.png'
    assert result['97']['inputs']['image'] == 'frozen/start.png'


def test_prepared_original_graph_is_copied_and_verified(tmp_path):
    module=api()
    from video_ai.planning.production_scenes import canonical_digest
    graph={'n':{'inputs':{'seed':17}}}; fixture={'source_graph_sha256':canonical_digest(graph)}
    copied=module.original_quality_graph(tmp_path,fixture,graph)
    copied['n']['inputs']['seed']=18
    assert graph['n']['inputs']['seed']==17
    with pytest.raises(ValueError,match='quality graph drift'):
        module.original_quality_graph(tmp_path,fixture,copied)


def test_unknown_durable_intent_never_posts_again(tmp_path):
    module = api()
    trial = tmp_path/'trials/first'; trial.mkdir(parents=True)
    graph = {'n': {'inputs': {}}}
    intent = dict(client_id=str(uuid4()), graph_sha256=module.digest(graph), graph=graph)
    (trial/'intent.json').write_text(json.dumps(intent))
    calls = []
    def http(method, route, payload=None):
        calls.append(method)
        return {} if route.startswith('/history') else dict(queue_running=[], queue_pending=[])
    client = module.ExperimentClient(tmp_path, http=http)
    with pytest.raises(module.OutcomeUnknown):
        client.submit('first', graph)
    assert 'POST' not in calls


def test_raw_post_acceptance_recovers_original_id_without_new_post(tmp_path):
    module = api()
    graph = {'n': {'inputs': {}}}; pid = str(uuid4())
    trial = tmp_path/'trials/first'; trial.mkdir(parents=True)
    (trial/'intent.json').write_text(json.dumps(dict(client_id=str(uuid4()), graph_sha256=module.digest(graph), graph=graph)))
    (trial/'post.response.json').write_text(json.dumps(dict(prompt_id=pid, number=1, node_errors={})))
    client = module.ExperimentClient(tmp_path, http=lambda *args: pytest.fail('must not contact service'))
    assert client.submit('first', graph) == pid
    assert json.loads((trial/'accepted.json').read_text())['prompt_id'] == pid


def test_experiment_port_cannot_be_redirected_to_production(tmp_path):
    module = api()
    (tmp_path/'experiment.json').write_text(json.dumps(dict(port=8189)))
    with pytest.raises(ValueError, match='port'):
        module.ExperimentClient(tmp_path, port=8188)


def test_completed_resume_authenticates_all_three_media_files(tmp_path):
    module = api()
    value = {}
    for key in ('generated', 'retained', 'last_frame'):
        file = tmp_path/(key+'.bin'); file.write_bytes(key.encode())
        value[key] = str(file); value[key+'_sha256'] = module.file_sha(file)
    module.validate_completed(value)
    (tmp_path/'last_frame.bin').write_bytes(b'replaced')
    with pytest.raises(ValueError):
        module.validate_completed(value)


def test_child_never_submits_before_new_parent_human_acceptance(tmp_path, monkeypatch):
    module = api()
    folder = tmp_path/'trials/cold_1'; folder.mkdir(parents=True)
    (folder/'technical-complete.json').write_text('{}')
    monkeypatch.setattr(module, 'ExperimentClient', lambda *a, **kw: pytest.fail('child service must not be touched'))
    with pytest.raises(ValueError, match='human acceptance'):
        module.run_child_trial(tmp_path,'cold_1')


def test_fresh_child_service_uses_sealed_child_and_real_accepted_parent_tail(tmp_path,monkeypatch):
    module=api();parent=tmp_path/'parent';root=tmp_path/'fresh-child';source=tmp_path/'original-child'
    for path in (parent/'frozen',parent/'trials/cold_1',source):path.mkdir(parents=True)
    root.mkdir()
    original_parent={'source_clip_id':'parent_clip'}
    module.write_once(parent/'fixture.json',original_parent)
    module.write_once(parent/'frozen/original-request.json',{'kind':'original parent request'})
    module.write_once(parent/'frozen/original-graph.json',{'kind':'original parent graph'})
    media={}
    for key in ('generated','retained','last_frame'):
        path=parent/(key+'.bin');path.write_bytes(('actual-'+key).encode())
        media[key]=str(path);media[key+'_sha256']=module.file_sha(path)
    module.write_once(parent/'trials/cold_1/technical-complete.json',media)
    module.write_once(parent/'trials/cold_1/observation-accepted.json',dict(decision='accepted',
        **{k:media[k] for k in ('generated_sha256','retained_sha256','last_frame_sha256')}))
    graph={'node':{'inputs':{'steps':40}}}
    from video_ai.planning.production_scenes import canonical_digest
    request=dict(parent={'clip_id':'parent_clip'},clip_id='child_clip',graph_sha256=canonical_digest(graph),
        parameters=dict(steps=40,cfg=3.5,lora_enabled=False),budget=dict(parent_clip_id='parent_clip'),
        selected_image={'sha256':'original selected image'})
    module.write_once(source/'request.json',request);module.write_once(source/'graph.json',graph)
    module.prepare_child(parent,source)
    seen=[]
    def run(root,trial,**kwargs):
        fixture=kwargs['fixture_override'];seen.append(fixture)
        assert module.file_sha(root/'input'/fixture['input_relative'])==media['last_frame_sha256']
        assert fixture['requires_new_parent'] is False
        return {'trial_id':trial}
    monkeypatch.setattr(module,'run_trial',run)
    assert module.run_child_trial(root,'cold_1',parent_root=parent)=={'trial_id':'cold_1_child'}
    assert module.read(parent/'fixture.json')==original_parent
    assert module.read(root/'frozen/child-original-graph.json')==graph
    assert module.read(root/'fixture.json')['requires_new_parent'] is True
    assert seen[0]['parent_binding']['parent_last_frame_sha256']==media['last_frame_sha256']
