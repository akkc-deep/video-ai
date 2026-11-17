import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from video_ai.experiments import wan_fast_profiles as profiles
from video_ai.experiments.wan_fast_experiment import FastExperimentClient, build_trial_fixture, prepare_request


@pytest.fixture
def experiment(tmp_path, monkeypatch):
    roles = profiles.BASE_ROLES | {'lora_high', 'lora_low'}
    assets = {}
    for role in roles:
        path = tmp_path/(role+'.bin')
        path.write_bytes(role.encode())
        assets[role] = profiles.artifact(path)
    monkeypatch.setattr(profiles, 'LORA_PINS', {r: dict(filename=r+'.bin', bytes=len(r),
        sha256=hashlib.sha256(r.encode()).hexdigest()) for r in ('lora_high', 'lora_low')})
    p = profiles.load_profile('fast_experimental', factor='distill', assets=assets,
                              capabilities={'environment': {'python': 'fixture'}})
    profiles.freeze_profile(tmp_path, p)
    graph = {'97': {'inputs': {'image': 'start.png'}}, '108': {'inputs': {'filename_prefix': 'fixture/cold_1'}}}
    fixture = build_trial_fixture(dict(source_graph_sha256='a'*64, parameters={'seed_high': 17},
        budget={'generated_frames': 93}, source_clip_id='clip', source_request_sha256='b'*64,
        requires_new_parent=False), p, graph)
    prepare_request(tmp_path, p, fixture, graph)
    return tmp_path, p, graph


def test_lost_response_only_recovers_original_get(experiment):
    root, p, graph = experiment
    calls, pid = [], str(uuid4())
    def lost(method, route, payload=None):
        calls.append(method)
        if method == 'POST':
            raise TimeoutError('lost response')
        intent = json.loads((root/'trials/cold_1/intent.json').read_text())
        return {pid: {'prompt': [0, pid, graph, {'client_id': intent['client_id']}]}} if route == '/history' else {}
    client = FastExperimentClient(root, profile_digest=p.digest(), port=8189, http=lost)
    with pytest.raises(TimeoutError):
        client.submit('cold_1', graph)
    assert client.submit('cold_1', graph) == pid
    assert calls.count('POST') == 1
    binding = json.loads((root/'trials/cold_1/profile-binding.json').read_text())
    assert binding['profile_sha256'] == p.digest()


@pytest.mark.parametrize('drift', ['profile', 'node', 'request', 'graph', 'binding', 'service'])
def test_identity_drift_refused_before_any_http(experiment, drift):
    root, p, graph = experiment
    client = FastExperimentClient(root, profile_digest=p.digest(), port=8189,
        http=lambda *args: pytest.fail('drift must fail before HTTP'))
    if drift == 'profile':
        path = root/'frozen/profile.json'
        value = json.loads(path.read_text()); value['profile']['attention_backend'] = 'sage'
        path.write_text(json.dumps(value))
    elif drift == 'node':
        Path(dict(p.assets)['node_source'].path).write_bytes(b'changed')
    elif drift == 'request':
        path = root/'frozen/request.json'; path.write_text('{}')
    elif drift == 'graph':
        graph['97']['inputs']['image'] = 'other.png'
    elif drift == 'binding':
        folder = root/'trials/cold_1'; folder.mkdir(parents=True)
        (folder/'profile-binding.json').write_text('{}')
    else:
        (root/'service-owner.json').write_text(json.dumps({'profile_sha256': 'wrong'}))
    with pytest.raises((ValueError, OSError)):
        client.submit('cold_1', graph)


def test_completed_media_recovery_has_zero_producer_or_post(experiment):
    root, p, graph = experiment
    client = FastExperimentClient(root, profile_digest=p.digest(), port=8189,
        http=lambda *a: pytest.fail('completed recovery must not contact service'))
    result = {}
    for role in ('generated', 'retained', 'last_frame'):
        path = root/(role+'.bin'); path.write_bytes(role.encode())
        result[role] = str(path); result[role+'_sha256'] = hashlib.sha256(role.encode()).hexdigest()
    folder = root/'trials/cold_1'; folder.mkdir(parents=True)
    client.bind('cold_1', graph)
    pid = str(uuid4())
    intent = dict(client_id=str(uuid4()), graph_sha256=profiles.digest(graph), graph=graph)
    profiles.write_once(folder/'intent.json', intent)
    profiles.write_once(folder/'intent-binding.json', dict(profile_sha256=p.digest(), intent_sha256=profiles.digest(intent)))
    profiles.write_once(folder/'accepted.json', dict(prompt_id=pid, recovered=False))
    result.update(trial_id='cold_1', prompt_id=pid, graph_sha256=profiles.digest(graph), input_sha256=None)
    (folder/'technical-complete.json').write_text(json.dumps(result))
    assert client.completed('cold_1', graph) == result
    Path(result['retained']).write_bytes(b'replaced')
    with pytest.raises(ValueError):
        client.completed('cold_1', graph)


@pytest.mark.parametrize('field', ['graph_sha256','input_sha256','trial_id','prompt_id','intent'])
def test_completed_foreign_identity_refused_without_http(experiment, field):
    root, p, graph = experiment
    client = FastExperimentClient(root, profile_digest=p.digest(), port=8189,
        http=lambda *a: pytest.fail('completed drift must not contact service'))
    client.bind('cold_1', graph)
    folder = root/'trials/cold_1'
    pid = str(uuid4()); intent = dict(client_id=str(uuid4()), graph_sha256=profiles.digest(graph), graph=graph)
    profiles.write_once(folder/'intent.json', intent)
    profiles.write_once(folder/'intent-binding.json', dict(profile_sha256=p.digest(), intent_sha256=profiles.digest(intent)))
    profiles.write_once(folder/'accepted.json', dict(prompt_id=pid, recovered=False))
    result = dict(trial_id='cold_1', prompt_id=pid, graph_sha256=profiles.digest(graph), input_sha256=None)
    for role in ('generated','retained','last_frame'):
        path = root/(role+'.bin'); path.write_bytes(role.encode())
        result[role] = str(path); result[role+'_sha256'] = profiles.artifact(path).sha256
    if field == 'intent':
        (folder/'intent.json').unlink()
    else:
        result[field] = 'foreign'
    profiles.write_once(folder/'technical-complete.json', result)
    with pytest.raises((ValueError, OSError)):
        client.completed('cold_1', graph)


def test_fixture_retains_seed_budget_and_distinct_source_graph(experiment):
    root, p, graph = experiment
    fixture = json.loads((root/'fixture.json').read_text())
    assert fixture['source_quality_graph_sha256'] == 'a'*64
    assert fixture['source_graph_sha256'] == profiles.digest(graph)
    assert fixture['parameters']['seed_high'] == 17
    assert fixture['budget']['generated_frames'] == 93
    assert fixture['parameters']['steps'] == 4
    assert fixture['graph_file'] == 'profile-graph.json'


@pytest.mark.parametrize('gate', ['missing_review', 'wrong_profile', 'wrong_parent', 'changed_tail', 'running_service'])
def test_child_requires_stopped_accepted_same_profile_parent(experiment, gate):
    from video_ai.experiments.wan_fast_experiment import accepted_parent_binding
    root, p, graph = experiment
    folder = root/'trials/cold_1'; folder.mkdir(parents=True)
    result = {}
    for role in ('generated', 'retained', 'last_frame'):
        path = root/(role+'.bin'); path.write_bytes(role.encode())
        result[role] = str(path); result[role+'_sha256'] = profiles.artifact(path).sha256
    (folder/'technical-complete.json').write_text(json.dumps(result))
    if gate != 'missing_review':
        (folder/'observation-accepted.json').write_text(json.dumps(dict(decision='accepted',
            **{k+'_sha256':result[k+'_sha256'] for k in ('generated','retained','last_frame')})))
    if gate != 'running_service':
        (root/'service-result.json').write_text('{}')
    if gate == 'changed_tail':
        Path(result['last_frame']).write_bytes(b'different')
    child = {'budget': {'parent_clip_id': 'other' if gate == 'wrong_parent' else 'clip'}}
    expected_digest = '0'*64 if gate == 'wrong_profile' else p.digest()
    with pytest.raises((ValueError, OSError)):
        accepted_parent_binding(root, 'cold_1', expected_digest, child)


def test_parent_cannot_accept_a_foreign_completion(experiment):
    from video_ai.experiments.wan_fast_experiment import accepted_parent_binding
    root, p, graph = experiment
    folder = root/'trials/cold_1'; folder.mkdir(parents=True)
    result = {'trial_id': 'foreign'}
    for role in ('generated','retained','last_frame'):
        path=root/(role+'.bin'); path.write_bytes(role.encode())
        result[role]=str(path); result[role+'_sha256']=profiles.artifact(path).sha256
    profiles.write_once(folder/'technical-complete.json',result)
    profiles.write_once(folder/'observation-accepted.json',dict(decision='accepted',
        **{k+'_sha256':result[k+'_sha256'] for k in ('generated','retained','last_frame')}))
    profiles.write_once(root/'service-result.json',{})
    with pytest.raises((ValueError,OSError)):
        accepted_parent_binding(root,'cold_1',p.digest(),{'budget':{'parent_clip_id':'clip'}})
