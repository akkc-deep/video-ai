"""Exercise real signing/protocol/storage with an injected HTTP response boundary."""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import io
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from unit.test_jimeng_config import configured
from unit.test_production_inputs import production_config


class Response(io.BytesIO):
    status = 200
    headers = {}
    def __init__(self, content, url): super().__init__(content); self.url = url
    def geturl(self): return self.url


@pytest.fixture
def candidate_setup(production_config, runtime_run, tmp_path, monkeypatch):
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.adapters.jimeng import JimengClient
    from video_ai.adapters.external_https import ExternalHttpsClient
    config = configured(production_config, tmp_path)
    data = json.loads(config.config_file.read_text(encoding='utf-8'))
    data['image_generation']['candidates_per_scene'] = 1
    config.config_file.write_text(json.dumps(data), encoding='utf-8')
    from video_ai.config import load_config
    frozen = freeze_inputs(load_config(config.config_file), runtime_run[0], text='湖水。')
    monkeypatch.setenv('TEST_VOLC_AK', 'test-access')
    monkeypatch.setenv('TEST_VOLC_SK', 'test-secret')
    state = dict(submits=0, queries=0, downloads=[], statuses=[], failure=None, urls=2)
    def transport(request, **kwargs):
        if request.get_method() == 'GET':
            path = urlsplit(request.full_url).path
            state['downloads'].append(path)
            if state['failure'] == 'download' and path.endswith('/2'):
                raise OSError('signed URL https://cdn.example/2?sig=private')
            return Response(state.get('image_bytes', b'original-image-'+path.encode()), request.full_url)
        action = parse_qs(urlsplit(request.full_url).query)['Action'][0]
        payload = json.loads(request.data)
        assert payload['req_key'] == 'jimeng_t2i_v40'
        if action == 'CVSync2AsyncSubmitTask':
            state['submits'] += 1
            assert payload['prompt'] == '湖水上的鸟'
            if state['failure'] == 'submit': raise OSError('response lost after accepted')
            reply = dict(code=10000, data={'task_id': 'task_1'}, request_id='submit_req')
        else:
            state['queries'] += 1
            assert payload['task_id'] == 'task_1'
            if state['failure'] == 'query': raise TimeoutError('query timed out')
            status = state['statuses'].pop(0) if state['statuses'] else 'done'
            reply = dict(code=10000, data=dict(status=status,
                image_urls=[f'https://cdn.example/{i+1}?sig=private' for i in range(state['urls'])]), request_id='query_req')
        return Response(json.dumps(reply).encode(), request.full_url)
    client = JimengClient(frozen.config.image_generation, http=ExternalHttpsClient(transport=transport))
    return frozen, client, state, runtime_run[0]


def image_info(path):
    assert path.read_bytes().startswith(b'original-image-')
    return dict(width=2560, height=1440, format='png')


def generate(setup, **kwargs):
    from video_ai.runtime.jimeng_candidates import generate_candidates
    frozen, client, _, _ = setup
    return generate_candidates(frozen, 'scene_0001', '湖水上的鸟', client=client, inspect=image_info,
                               sleep=lambda seconds: None, **kwargs)


def test_original_multimage_outputs_are_durable_and_replay_has_no_http(candidate_setup):
    result = generate(candidate_setup)
    state = candidate_setup[2]
    assert result['schema_version'] == 2
    assert len(result['candidates']) == 2
    for item in result['candidates']:
        from pathlib import Path
        raw = Path(item['path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item['sha256']
        assert (item['width'], item['height']) == (2560, 1440)
        assert item['task_id'] == 'task_1'
    counts = (state['submits'], state['queries'], len(state['downloads']))
    assert generate(candidate_setup) == result
    assert (state['submits'], state['queries'], len(state['downloads'])) == counts
    persisted = '\n'.join(p.read_text(encoding='utf-8') for p in candidate_setup[3].rglob('*.json'))
    assert all(s not in persisted for s in ('test-secret', 'test-access', 'sig=private', 'Authorization'))
    assert not (candidate_setup[3]/'.make-video.lock').exists()


def test_accepted_then_interrupted_queries_original_task(candidate_setup, monkeypatch):
    import video_ai.runtime.jimeng_candidates as candidates
    def interrupt(point, identity):
        if point == 'accepted': raise KeyboardInterrupt()
    monkeypatch.setattr(candidates, 'boundary', interrupt)
    with pytest.raises(KeyboardInterrupt): generate(candidate_setup)
    monkeypatch.setattr(candidates, 'boundary', lambda *args: None)
    assert len(generate(candidate_setup)['candidates']) == 2
    assert candidate_setup[2]['submits'] == 1


def test_lost_submission_response_never_submits_again(candidate_setup):
    candidate_setup[2]['failure'] = 'submit'
    with pytest.raises(Exception): generate(candidate_setup)
    candidate_setup[2]['failure'] = None
    with pytest.raises(ValueError, match='submit_unknown'): generate(candidate_setup)
    assert candidate_setup[2]['submits'] == 1


@pytest.mark.parametrize('failure', ['query', 'download'])
def test_query_and_partial_download_resume_without_paid_resubmit(candidate_setup, failure):
    state = candidate_setup[2]
    state['failure'] = failure
    with pytest.raises(Exception): generate(candidate_setup)
    state['failure'] = None
    assert len(generate(candidate_setup)['candidates']) == 2
    assert state['submits'] == 1
    if failure == 'download': assert state['downloads'].count('/1') == 1


@pytest.mark.parametrize('status', ['expired', 'not_found', 'failed'])
def test_terminal_task_is_retained_and_never_resubmitted(candidate_setup, status):
    state = candidate_setup[2]
    state['statuses'] = [status]
    with pytest.raises(ValueError, match=status): generate(candidate_setup)
    with pytest.raises(ValueError, match=status): generate(candidate_setup)
    assert state['submits'] == 1
    assert state['queries'] == 1


def test_queue_and_generating_are_polled_until_done(candidate_setup):
    candidate_setup[2]['statuses'] = ['in_queue', 'generating', 'done']
    assert len(generate(candidate_setup)['candidates']) == 2
    assert candidate_setup[2]['queries'] == 3


@pytest.mark.parametrize('change', ['image', 'prompt', 'model', 'result_schema', 'run'])
def test_stale_or_tampered_identity_is_refused(candidate_setup, change):
    from pathlib import Path
    from video_ai.runtime.jimeng_candidates import generate_candidates
    frozen, client, state, run = candidate_setup
    result = generate(candidate_setup)
    prompt = '湖水上的鸟'
    if change == 'image': Path(result['candidates'][0]['path']).write_bytes(b'changed')
    if change == 'prompt': prompt = 'changed'
    if change == 'model': frozen = replace(frozen, config=replace(frozen.config,
        image_generation=replace(frozen.config.image_generation, req_key='modified')))
    if change in ('result_schema', 'run'):
        path = run/'production/jimeng/scene_0001/candidates.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['schema_version' if change == 'result_schema' else 'run_id'] = True if change == 'result_schema' else 'other_run'
        path.write_text(json.dumps(data), encoding='utf-8')
    counts = (state['submits'], state['queries'])
    with pytest.raises(ValueError):
        generate_candidates(frozen, 'scene_0001', prompt, client=client, inspect=image_info)
    assert (state['submits'], state['queries']) == counts


def test_wrong_model_dimensions_refused_without_cropping(candidate_setup):
    from video_ai.runtime.jimeng_candidates import generate_candidates
    frozen, client, state, run = candidate_setup
    with pytest.raises(ValueError, match='dimension'):
        generate_candidates(frozen, 'scene_0001', '湖水上的鸟', client=client,
                            inspect=lambda path: dict(width=1280, height=720, format='png'))
    assert state['submits'] == 1
    assert list((run/'production/jimeng').rglob('*.original'))


def test_credentials_can_rotate_without_changing_frozen_identity(candidate_setup, monkeypatch):
    generate(candidate_setup)
    monkeypatch.setenv('TEST_VOLC_AK', 'rotated-access')
    monkeypatch.setenv('TEST_VOLC_SK', 'rotated-secret')
    assert len(generate(candidate_setup)['candidates']) == 2
    assert candidate_setup[2]['submits'] == 1


def test_missing_credentials_do_not_poison_submission(candidate_setup, monkeypatch):
    monkeypatch.delenv('TEST_VOLC_SK')
    with pytest.raises(ValueError, match='AK/SK'): generate(candidate_setup)
    assert not list((candidate_setup[3]/'production/jimeng').rglob('intent.json'))
    monkeypatch.setenv('TEST_VOLC_SK', 'test-secret')
    assert len(generate(candidate_setup)['candidates']) == 2


def test_interrupted_after_original_download_reuses_original(candidate_setup, monkeypatch):
    import video_ai.runtime.jimeng_candidates as candidates
    fired = []
    def interrupt(point, identity):
        if point == 'downloaded' and not fired:
            fired.append(identity); raise KeyboardInterrupt()
    monkeypatch.setattr(candidates, 'boundary', interrupt)
    with pytest.raises(KeyboardInterrupt): generate(candidate_setup)
    assert len(generate(candidate_setup)['candidates']) == 2
    assert candidate_setup[2]['downloads'].count('/1') == 1
    assert candidate_setup[2]['submits'] == 1


def test_downloaded_original_changed_before_metadata_is_refused(candidate_setup, monkeypatch):
    import video_ai.runtime.jimeng_candidates as candidates
    def interrupt(point, identity):
        if point == 'downloaded': raise KeyboardInterrupt()
    monkeypatch.setattr(candidates, 'boundary', interrupt)
    with pytest.raises(KeyboardInterrupt): generate(candidate_setup)
    original = next((candidate_setup[3]/'production/jimeng').rglob('*.original'))
    original.write_bytes(b'original-image-replacement-with-valid-dimensions')
    monkeypatch.setattr(candidates, 'boundary', lambda *args: None)
    with pytest.raises(ValueError, match='SHA256'): generate(candidate_setup)
    assert candidate_setup[2]['submits'] == 1


def test_candidate_generation_refuses_live_foreign_run_lock(candidate_setup):
    from video_ai.runtime.production_state import RunLock
    with RunLock(candidate_setup[3]):
        with pytest.raises(ValueError, match='lock'): generate(candidate_setup)
    assert candidate_setup[2]['submits'] == 0


def refreeze(setup, runtime_run, changes=None):
    from video_ai.config import load_config
    from video_ai.runtime.paths import create_run, RuntimePaths
    from video_ai.runtime.production_inputs import freeze_inputs
    path = setup[0].config.config_file
    data = json.loads(path.read_text(encoding='utf-8'))
    for tool in ('ffmpeg', 'ffprobe'): data['tools'][tool] = str(runtime_run[1].tools[tool])
    if changes: data['image_generation'].update(changes)
    path.write_text(json.dumps(data), encoding='utf-8')
    config = load_config(path)
    return freeze_inputs(config, create_run(RuntimePaths.from_config(config)), text='湖水。')


@pytest.mark.parametrize('valid', [True, False])
def test_real_media_decoder_validates_original_bytes(candidate_setup, runtime_run, valid):
    import struct
    import zlib
    from video_ai.runtime.jimeng_candidates import generate_candidates
    def chunk(kind, raw):
        return struct.pack('>I', len(raw))+kind+raw+struct.pack('>I', zlib.crc32(kind+raw))
    png = (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', 2560, 1440, 8, 2, 0, 0, 0))
           +chunk(b'IDAT', zlib.compress((b'\0'+b'\x22\x88\xcc'*2560)*1440))+chunk(b'IEND', b''))
    candidate_setup[2]['image_bytes'] = png if valid else b'not a decodable image'
    frozen = refreeze(candidate_setup, runtime_run)
    if valid:
        result = generate_candidates(frozen, 'scene_0001', '湖水上的鸟', client=candidate_setup[1])
        assert result['candidates'][0]['sha256'] == hashlib.sha256(png).hexdigest()
        assert result['candidates'][0]['format'] == 'png'
    else:
        with pytest.raises((RuntimeError, ValueError)):
            generate_candidates(frozen, 'scene_0001', '湖水上的鸟', client=candidate_setup[1])


def test_poll_deadline_leaves_original_task_resumable(candidate_setup, runtime_run):
    from video_ai.adapters.jimeng import JimengClient
    from video_ai.runtime.jimeng_candidates import generate_candidates
    import time
    frozen = refreeze(candidate_setup, runtime_run, {'task_timeout_seconds': .05})
    client = JimengClient(frozen.config.image_generation, http=candidate_setup[1].http)
    candidate_setup[2]['statuses'] = ['in_queue']*100
    with pytest.raises(TimeoutError):
        generate_candidates(frozen, 'scene_0001', '湖水上的鸟', client=client, inspect=image_info,
                            sleep=lambda delay: time.sleep(.06))
    candidate_setup[2]['statuses'] = []
    assert len(generate_candidates(frozen, 'scene_0001', '湖水上的鸟', client=client, inspect=image_info)['candidates']) == 2
    assert candidate_setup[2]['submits'] == 1
