"""Profile guards around the existing LVA-01 durable experiment protocol."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re

from .wan_fast_profiles import digest, verify_profile, write_once

SOURCE = Path(__file__).resolve().parents[3]


def baseline_api():
    # A private module instance lets the harness inject its client/inspection
    # without changing the old script or other callers' global functions.
    spec = importlib.util.spec_from_file_location('_lva04_baseline', SOURCE/'scripts/benchmark_local_gpu.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def build_trial_fixture(source_fixture, profile, graph):
    result = deepcopy(source_fixture)
    result.update(schema_version=1, source_quality_graph_sha256=source_fixture['source_graph_sha256'],
        source_graph_sha256=digest(graph), graph_file='profile-graph.json', profile_sha256=profile.digest())
    result.setdefault('fixture_id', 'fixture')
    result['parameters'].update(steps=profile.steps, cfg=profile.cfg, split_step=profile.split,
        sampler=profile.sampler, scheduler=profile.scheduler, lora_enabled=profile.mode == 'fast_experimental')
    return result


def request_identity(profile, fixture, graph):
    return dict(schema_version=1, profile_sha256=profile.digest(), fixture_sha256=digest(fixture),
        graph_sha256=digest(graph), source_request_sha256=fixture['source_request_sha256'],
        source_clip_id=fixture['source_clip_id'], parameters=fixture['parameters'], budget=fixture['budget'],
        parent_binding=fixture.get('parent_binding'))


def prepare_request(root, profile, fixture, graph):
    root = Path(root)
    verify_profile(root, profile.digest())
    if fixture['profile_sha256'] != profile.digest() or fixture['source_graph_sha256'] != digest(graph):
        raise ValueError('fixture/profile graph differs')
    write_once(root/'fixture.json', fixture)
    write_once(root/'frozen/profile-graph.json', graph)
    write_once(root/'frozen/request.json', request_identity(profile, fixture, graph))


class FastExperimentClient:
    def __init__(self, root, *, profile_digest, port, http=None):
        self.root, self.profile_digest, self.port = Path(root), profile_digest, port
        self.api = baseline_api()
        self.delegate = self.api.ExperimentClient(root, port=port, http=self._http)
        self.transport = http or self.delegate.http
        self.injected = http is not None

    def _verify(self):
        profile = verify_profile(self.root, self.profile_digest)
        fixture = read(self.root/'fixture.json')
        graph = read(self.root/'frozen/profile-graph.json')
        request = read(self.root/'frozen/request.json')
        if (fixture.get('profile_sha256') != self.profile_digest or fixture['source_graph_sha256'] != digest(graph)
                or request != request_identity(profile, fixture, graph)):
            raise ValueError('frozen request/fixture/graph drift')
        if fixture.get('input_relative'):
            from .wan_fast_profiles import Artifact
            image = (self.root/'input'/fixture['input_relative']).resolve(strict=True)
            if not image.is_relative_to((self.root/'input').resolve()):
                raise ValueError('input escapes experiment root')
            # Read only the actual image, using the same invocation's native
            # lease when available; no large-model rehash here.
            Artifact(str(image), image.stat().st_size, fixture['input_sha256']).verify()
        verify_parent(fixture, self.profile_digest)
        owner_path = self.root/'service-owner.json'
        if owner_path.exists():
            owner = read(owner_path)
            launch = read(self.root/'frozen/service-launch.json') if (self.root/'frozen/service-launch.json').exists() else {}
            if (owner.get('profile_sha256') != self.profile_digest or owner.get('launch_sha256') != digest(launch)
                    or launch.get('profile_sha256') != self.profile_digest or launch.get('port') != self.port
                    or launch.get('environment') != json.loads(profile.environment_json)):
                raise ValueError('service profile/argv/environment drift')
        return profile, fixture, graph, request

    def _http(self, method, route, payload=None):
        self._verify()
        if not self.injected:
            self.delegate.assert_owned_service()
            attestation = read(self.root/'worker-attestation.json')
            owner = read(self.root/'service-owner.json')
            if (attestation.get('profile_sha256') != self.profile_digest or
                    attestation.get('pid') != owner['pid'] or
                    attestation.get('launch_sha256') != owner['launch_sha256']):
                raise ValueError('owned worker attestation differs')
        return self.transport(method, route, payload)

    def bind(self, trial_id, graph):
        if not isinstance(trial_id, str) or not re.fullmatch(r'(cold_1|warm_[123])(?:_child)?', trial_id):
            raise ValueError('fixed cold1/warm3 trial ID required')
        _, fixture, source_graph, request = self._verify()
        if fixture.get('requires_new_parent'):
            raise ValueError('new parent human acceptance and profile binding required')
        expected = self.api.rebind_graph(source_graph,
            fixture.get('input_relative', source_graph['97']['inputs']['image']), fixture['fixture_id']+'/'+trial_id)
        if graph != expected:
            raise ValueError('trial graph differs from frozen recipe/input/namespace')
        value = dict(schema_version=1, profile_sha256=self.profile_digest,
            request_sha256=digest(request), graph_sha256=digest(graph), fixture_sha256=digest(fixture),
            intent_file='intent.json', parent_binding=fixture.get('parent_binding'))
        write_once(self.root/'trials'/trial_id/'profile-binding.json', value)
        intent = self.root/'trials'/trial_id/'intent.json'
        bound = self.root/'trials'/trial_id/'intent-binding.json'
        if intent.exists() and bound.exists():
            if read(bound) != dict(profile_sha256=self.profile_digest, intent_sha256=digest(read(intent))):
                raise ValueError('intent/profile binding drift')
        return value

    def submit(self, trial_id, graph):
        self.bind(trial_id, graph)
        try:
            return self.delegate.submit(trial_id, graph)
        finally:
            intent = self.root/'trials'/trial_id/'intent.json'
            if intent.exists():
                self._verify()
                write_once(intent.with_name('intent-binding.json'),
                    dict(profile_sha256=self.profile_digest, intent_sha256=digest(read(intent))))

    def wait(self, trial_id, graph, **kwargs):
        self.submit(trial_id, graph)
        # delegate.wait repeats submit, but the accepted ID already exists; the
        # original protocol performs no second POST. Every GET is guarded above.
        return self.delegate.wait(trial_id, graph, **kwargs)

    def completed(self, trial_id, graph):
        complete = self.root/'trials'/trial_id/'technical-complete.json'
        folder = complete.parent
        if complete.exists() and not (folder/'profile-binding.json').exists():
            raise ValueError('completed media has no original profile binding')
        self.bind(trial_id, graph)
        if complete.exists():
            result = read(complete)
            intent = read(folder/'intent.json')
            binding = read(folder/'intent-binding.json')
            accepted = read(folder/'accepted.json')
            fixture = read(self.root/'fixture.json')
            from uuid import UUID
            pid = accepted['prompt_id']
            if (str(UUID(pid)) != pid or intent.get('graph') != graph or intent.get('graph_sha256') != digest(graph)
                    or binding != dict(profile_sha256=self.profile_digest, intent_sha256=digest(intent))
                    or result.get('graph_sha256') != digest(graph) or result.get('trial_id') != trial_id
                    or result.get('prompt_id') != pid or result.get('input_sha256') != fixture.get('input_sha256')):
                raise ValueError('completed media differs from original profile/request/accepted ID')
            if any(not Path(result[k]).resolve().is_relative_to(self.root.resolve())
                   for k in ('generated', 'retained', 'last_frame')):
                raise ValueError('completed media escapes original experiment root')
            from .wan_fast_profiles import Artifact
            for role in ('generated', 'retained', 'last_frame'):
                media = Path(result[role]).resolve(strict=True)
                Artifact(str(media), media.stat().st_size, result[role+'_sha256']).verify()
            return result
        return None


def profile_graph(source_graph, profile):
    """Transfer only original mapped inputs; no synthetic fast source identity."""
    if profile.mode == 'quality':
        return deepcopy(source_graph)
    assets = dict(profile.assets)
    graph = read(assets['workflow'].path)
    mapping = read(assets['mapping'].path)
    for ref in mapping['inputs'].values():
        node, field = ref['node_id'], ref['input']
        graph[node]['inputs'][field] = deepcopy(source_graph[node]['inputs'][field])
    return graph


def accepted_parent_binding(parent_root, parent_trial, profile_digest, child_fixture):
    parent_root = Path(parent_root).resolve(strict=True)
    verify_profile(parent_root, profile_digest)
    parent_fixture = read(parent_root/'fixture.json')
    if child_fixture['budget']['parent_clip_id'] != parent_fixture['source_clip_id']:
        raise ValueError('child does not continue this profile parent')
    folder = parent_root/'trials'/parent_trial
    approval = folder/'observation-accepted.json'
    if not approval.exists():
        raise ValueError('new parent human acceptance required')
    parent = read(folder/'technical-complete.json')
    accepted = read(approval)
    if (accepted.get('decision') != 'accepted' or any(accepted.get(k+'_sha256') != parent[k+'_sha256']
            for k in ('generated', 'retained', 'last_frame'))):
        raise ValueError('human acceptance must bind exact parent media')
    if not (parent_root/'service-result.json').exists():
        raise ValueError('parent owned service must stop before review/child preparation')
    # Human approval must bind an actual completion from the parent's original
    # intent/accepted ID, not merely three arbitrary content-valid files.
    port = read(parent_root/'experiment.json')['port'] if (parent_root/'experiment.json').exists() else 8189
    client = FastExperimentClient(parent_root, profile_digest=profile_digest, port=port)
    parent_graph = read(parent_root/'frozen/profile-graph.json')
    expected_graph = client.api.rebind_graph(parent_graph,
        parent_fixture.get('input_relative', parent_graph['97']['inputs']['image']),
        parent_fixture['fixture_id']+'/'+parent_trial)
    if client.completed(parent_trial, expected_graph) != parent:
        raise ValueError('parent completion differs from accepted original trial')
    from .wan_fast_profiles import artifact
    return dict(parent_root=str(parent_root), parent_trial=parent_trial,
        parent_profile_sha256=profile_digest, parent_generated_sha256=parent['generated_sha256'],
        parent_retained_sha256=parent['retained_sha256'], parent_last_frame_sha256=parent['last_frame_sha256'],
        human_acceptance=artifact(approval).identity_dict(), last_frame=parent['last_frame'])


def verify_parent(fixture, profile_digest):
    binding = fixture.get('parent_binding')
    if binding:
        current = accepted_parent_binding(binding['parent_root'], binding['parent_trial'], profile_digest, fixture)
        if current != binding:
            raise ValueError('parent/profile binding drift')


def run_trial(root, trial_id, *, profile_digest, port=8189):
    from video_ai.runtime.verification import whole_input_protection
    root = Path(root)
    with whole_input_protection(immutable_roots=()):
        client = FastExperimentClient(root, profile_digest=profile_digest, port=port)
        _, fixture, source_graph, _ = client._verify()
        graph = client.api.rebind_graph(source_graph, fixture['input_relative'], fixture['fixture_id']+'/'+trial_id)
        complete = client.completed(trial_id, graph)
        if complete is not None:
            return complete
        from .wan_fast_media import inspect_media
        api = client.api
        api.ExperimentClient = lambda *a, **kw: client
        api.inspect_media = inspect_media
        result = api.run_trial(root, trial_id)
        client._verify()
        return result
