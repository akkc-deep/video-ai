"""Dual backend contract; real HTTP/SQLite coverage lives alongside scripted fault cases."""
from dataclasses import replace
import json

import pytest
from http_helpers import Response, ScriptedTransport


def vox_config(config):
    from video_ai.config import load_config
    from video_ai.runtime.manifest import thaw
    raw = thaw(config.raw)
    raw['tts'] = dict(engine='voxcpm2', model_revision='model-1')
    raw['services']['tts'] = 'http://127.0.0.1:9881'
    return load_config(config.config_file, raw=raw, voice=config.voice)


def test_legacy_config_snapshot_roundtrip_unchanged(runtime_run):
    from video_ai.config import load_config
    from video_ai.runtime.manifest import create_manifest, thaw, ManifestStore
    from video_ai.adapters.tts import create_tts_client, TtsClient
    run, config, _ = runtime_run
    before = thaw(config)
    assert config.tts.engine == 'gpt-sovits'
    assert 'tts' not in before and 'tts' not in before['raw']
    store = create_manifest(run, config, inputs={}, models={}, workflows={})
    snapshot = store.snapshot()
    assert ManifestStore.open(run).snapshot() == snapshot
    loaded = load_config(config.config_file, raw=snapshot['config_snapshot']['raw'], voice=config.voice)
    assert thaw(loaded) == before
    assert isinstance(create_tts_client(loaded, None), TtsClient)


def test_explicit_backends_and_frozen_raw(runtime_run):
    from video_ai.config import load_config
    from video_ai.runtime.manifest import thaw
    config = vox_config(runtime_run[1])
    assert config.tts.engine == 'voxcpm2' and config.tts.parameters['seed'] == 42
    raw = thaw(config.raw)
    assert load_config(config.config_file, raw=raw, voice=config.voice).tts == config.tts
    raw['tts'] = dict(engine='gpt-sovits')
    assert load_config(config.config_file, raw=raw, voice=config.voice).tts.engine == 'gpt-sovits'


def test_vox_defaults_materialized_before_snapshot_and_never_drift(runtime_run, monkeypatch):
    from video_ai.config import load_config
    from video_ai.runtime.manifest import thaw, create_manifest, ManifestStore
    from video_ai.voxcpm.contracts import DEFAULTS
    config = vox_config(runtime_run[1])
    create_manifest(runtime_run[0], config, inputs={}, models={}, workflows={})
    snapshot = ManifestStore.open(runtime_run[0]).snapshot()
    assert snapshot['config_snapshot']['raw']['tts']['seed'] == 42
    monkeypatch.setitem(DEFAULTS, 'seed', 999)
    restored = load_config(config.config_file, raw=snapshot['config_snapshot']['raw'], voice=config.voice)
    assert restored.tts.parameters['seed'] == 42
    assert thaw(restored) == thaw(config)


@pytest.mark.parametrize('value', [None, {}, {'engine':'bad'}, {'engine':'voxcpm2'},
    {'engine':'gpt-sovits','seed':42}, {'engine':'voxcpm2','model_revision':'x','seed':True},
    {'engine':'voxcpm2','model_revision':'x','cfg_value':float('nan')},
    {'engine':'voxcpm2','model_revision':'x','inference_timesteps':0},
    {'engine':'voxcpm2','model_revision':'x','voice_id':'other'},
    {'engine':'voxcpm2','model_revision':'x','emotion':'other'},
    {'engine':'voxcpm2','model_revision':'x','extra':1}])
def test_bad_backend_configuration_rejected(runtime_run, value):
    from video_ai.config import ConfigError, load_config
    from video_ai.runtime.manifest import thaw
    raw = thaw(runtime_run[1].raw); raw['tts'] = value
    with pytest.raises(ConfigError, match='tts'):
        load_config(runtime_run[1].config_file, raw=raw, voice=runtime_run[1].voice)


def test_unwired_production_refuses_vox_instead_of_silent_gpt(runtime_run):
    from video_ai.runtime.production_inputs import validate_supported
    from video_ai.runtime.service_specs import build_service_specs
    config = vox_config(runtime_run[1])
    with pytest.raises(ValueError, match='TTS-VOX-07'):
        validate_supported(config)
    with pytest.raises(ValueError, match='VoxServiceProcess'):
        build_service_specs(config, runtime_run[0])


class Protocol:
    def __init__(self, config):
        self.config = config
        self.task = None
        self.posts = 0
        self.lose_post = False
        self.state = 'completed'
        self.binding = dict(voice_id='existing-reference', model_revision='model-1',
                            reference_sha256=config.voice.reference_sha256)

    def __call__(self, req, timeout):
        from video_ai.voxcpm.contracts import freeze_request
        path = req.full_url.removeprefix(self.config.services['tts'])
        if path == '/health':
            return Response(dict(service='video-ai-voxcpm2', status='ready', model_revision=self.binding['model_revision']))
        if path == '/voices':
            return Response(dict(voices=[self.binding]))
        if req.method == 'POST':
            self.posts += 1
            body = json.loads(req.data)
            self.task = dict(request_id=body['request_id'], engine='voxcpm2', status=self.state,
                             request=freeze_request(body, self.binding), result={}, error='test failure')
            if self.lose_post: raise ConnectionResetError('response lost after accepting')
            return Response(self.task, 202)
        if path.endswith('/audio'):
            return Response(b'RIFFxxxxWAVEdata', headers={'content-type':'audio/wav'})
        return Response(self.task) if self.task else Response({'error':'unknown task'}, 404)


def client_for(runtime_run, protocol=None, timeout=1, scope='revision_01'):
    from video_ai.adapters.tts import create_tts_client
    from video_ai.adapters.common import HttpClient
    from video_ai.runtime.logging import RunLogger
    config = vox_config(runtime_run[1])
    protocol = protocol or Protocol(config)
    transport = ScriptedTransport(protocol)
    client = create_tts_client(config, HttpClient(config.services['tts'], timeout, RunLogger(runtime_run[0]),
                                                transport=transport), request_scope=scope)
    return client, protocol, transport


def test_vox_returns_existing_wav_contract_and_reuses_completed(runtime_run):
    client, protocol, transport = client_for(runtime_run)
    text = ' 原文🙂，'
    response = client.synthesize(text, unit_id='speech_0001')
    assert response.body == b'RIFFxxxxWAVEdata' and response.evidence_path.is_file()
    request_id = protocol.task['request_id']
    assert protocol.task['request']['text'] == text
    assert client.synthesize(text, unit_id='speech_0001').body == response.body
    assert protocol.posts == 1 and protocol.task['request_id'] == request_id
    assert sum(url.endswith('/health') for _,url,_,_ in transport.calls) == 1
    other, _, _ = client_for(runtime_run, protocol, scope='revision_02')
    assert other.request_id('speech_0001') != request_id


def test_lost_post_response_queries_original_without_repost(runtime_run):
    client, protocol, _ = client_for(runtime_run)
    protocol.lose_post = True
    assert client.synthesize('原文。', unit_id='speech_0001').body[:4] == b'RIFF'
    assert protocol.posts == 1


def test_same_identity_changed_input_refused_without_post(runtime_run):
    from video_ai.adapters.common import AdapterError
    client, protocol, _ = client_for(runtime_run)
    client.synthesize('原文。', unit_id='speech_0001')
    with pytest.raises(AdapterError, match='frozen'):
        client.synthesize('改变。', unit_id='speech_0001')
    assert protocol.posts == 1


@pytest.mark.parametrize('state', ['failed','cancelled','cancel_requested'])
def test_vox_terminal_failure_never_downloads_or_retries(runtime_run, state):
    from video_ai.adapters.common import AdapterError
    client, protocol, transport = client_for(runtime_run)
    protocol.state = state
    with pytest.raises(AdapterError): client.synthesize('原文。', unit_id='speech_0001')
    assert protocol.posts == 1 and not any(url.endswith('/audio') for _,url,_,_ in transport.calls)


def test_vox_finite_deadline_does_not_cancel_or_repost(runtime_run):
    from video_ai.adapters.common import AdapterError, FailureKind
    client, protocol, transport = client_for(runtime_run, timeout=.04)
    protocol.state = 'running'
    with pytest.raises(AdapterError) as error: client.synthesize('原文。', unit_id='speech_0001')
    assert error.value.kind == FailureKind.ambiguous
    assert protocol.posts == 1 and not any(url.endswith('/cancel') for _,url,_,_ in transport.calls)


@pytest.mark.parametrize('field', ['model_revision','reference_sha256'])
def test_vox_wrong_startup_binding_rejected_before_post(runtime_run, field):
    from video_ai.adapters.common import AdapterError
    client, protocol, _ = client_for(runtime_run)
    protocol.binding[field] = 'wrong'
    with pytest.raises(AdapterError): client.synthesize('原文。', unit_id='speech_0001')
    assert protocol.posts == 0


@pytest.mark.parametrize('text', ['', '。！？', '字'*251])
def test_vox_invalid_text_no_network(runtime_run, text):
    client, _, transport = client_for(runtime_run)
    with pytest.raises(ValueError): client.synthesize(text, unit_id='speech_0001')
    assert not transport.calls


def test_vox_requires_persistent_scope(runtime_run):
    with pytest.raises(ValueError, match='scope'): client_for(runtime_run, scope=None)


def test_factory_rejects_http_origin_different_from_frozen_config(runtime_run):
    from video_ai.adapters.tts import create_tts_client
    from video_ai.adapters.common import HttpClient
    from video_ai.runtime.logging import RunLogger
    config = vox_config(runtime_run[1])
    with pytest.raises(ValueError, match='origin'):
        create_tts_client(config, HttpClient('http://127.0.0.1:9880', 1, RunLogger(runtime_run[0])), request_scope='r1')


@pytest.mark.parametrize('failure', ['disconnect', 'json'])
def test_unknown_query_never_becomes_new_post(runtime_run, failure):
    from video_ai.adapters.common import AdapterError, FailureKind
    config = vox_config(runtime_run[1]); protocol = Protocol(config)
    original = protocol.__call__
    def disconnect(req, timeout):
        if '/tts/tasks/' in req.full_url:
            if failure == 'json': return Response(b'broken JSON')
            raise ConnectionResetError('query unavailable')
        return original(req, timeout)
    client, _, transport = client_for(runtime_run, disconnect)
    with pytest.raises(AdapterError) as error: client.synthesize('原文。', unit_id='speech_0001')
    assert error.value.kind == FailureKind.ambiguous
    assert not any(method == 'POST' for method,_,_,_ in transport.calls)


@pytest.mark.parametrize('damage', ['identity', 'binding', 'status', 'wav', 'json'])
def test_mismatched_or_invalid_result_not_used(runtime_run, damage):
    from video_ai.adapters.common import AdapterError
    config = vox_config(runtime_run[1]); protocol = Protocol(config)
    first, _, _ = client_for(runtime_run, protocol)
    first.synthesize('原文。', unit_id='speech_0001')
    if damage == 'identity': protocol.task['request_id'] = 'wrong'
    if damage == 'binding': protocol.task['request']['binding']['reference_sha256'] = 'wrong'
    if damage == 'status': protocol.task['status'] = 'unknown'
    original = protocol.__call__
    def bad(req, timeout):
        if req.full_url.endswith('/audio') and damage == 'wav': return Response(b'no WAV')
        if '/tts/tasks/' in req.full_url and damage == 'json': return Response([])
        return original(req, timeout)
    client, _, _ = client_for(runtime_run, bad)
    with pytest.raises(AdapterError): client.synthesize('原文。', unit_id='speech_0001')
    assert protocol.posts == 1


def test_adapter_against_real_http_sqlite_and_completed_reuse(runtime_run, tmp_path):
    import threading
    import time
    import wave
    from video_ai.adapters.common import HttpClient
    from video_ai.adapters.tts import create_tts_client
    from video_ai.runtime.logging import RunLogger
    from video_ai.voxcpm.service import JobService
    from video_ai.voxcpm.store import JobStore
    from video_ai.voxcpm.server import make_server
    config = vox_config(runtime_run[1]); generated = []
    binding = dict(voice_id='existing-reference', model_revision='model-1',
                   reference_sha256=config.voice.reference_sha256)
    class Backend:
        def generate(self, request, temporary):
            generated.append(request['request_id'])
            time.sleep(.02)
            with wave.open(str(temporary), 'wb') as audio:
                audio.setparams((1,2,48000,0,'NONE',''))
                audio.writeframes(b'\x01\x00'*480)
            return dict(sample_count=480, sample_rate=48000, generation_time_ms=20)
    root = tmp_path/'runtime'
    with JobStore(root/'scratch/adapter', root) as store:
        service = JobService(store, binding, Backend)
        service.start()
        server = make_server(service, '127.0.0.1', 0, 'owner')
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            deadline = time.monotonic()+3
            while service.state == 'loading' and time.monotonic()<deadline: time.sleep(.01)
            config = replace(config, services=dict(config.services, tts=f'http://127.0.0.1:{server.server_port}'))
            logger = RunLogger(runtime_run[0])
            client = create_tts_client(config, HttpClient(config.services['tts'], 3, logger), request_scope='r1')
            response = client.synthesize('原文。', unit_id='speech_0001')
            frozen = store.get(client.request_id('speech_0001'))
            again = create_tts_client(config, HttpClient(config.services['tts'], 3, logger), request_scope='r1')
            assert again.synthesize('原文。', unit_id='speech_0001').body == response.body
            assert len(generated) == 1 and store.get(generated[0]) == frozen
            assert frozen['result']['sample_count'] == 480
        finally:
            server.shutdown(); thread.join(5); server.server_close(); service.close()
