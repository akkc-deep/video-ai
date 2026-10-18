import io
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from unit.test_jimeng_config import image_settings


class Response(io.BytesIO):
    status = 200
    headers = {'Content-Type': 'application/json'}
    def geturl(self): return 'https://visual.volcengineapi.com/'


def test_signature_fixed_utf8_vector():
    from video_ai.adapters.jimeng import sign_request
    body = '{"prompt":"湖水","req_key":"jimeng_t2i_v40"}'.encode()
    headers = sign_request(body, 'CVSync2AsyncSubmitTask', 'test-access', 'test-secret', '20260102T030405Z')
    assert headers['X-Content-Sha256'] == '2fe364ab8166e380f951f41f6fdcb5d3a48ec8f7ad11a0145e07e78b23c9b667'
    assert headers['Authorization'] == ('HMAC-SHA256 Credential=test-access/20260102/cn-north-1/cv/request, '
        'SignedHeaders=content-type;host;x-content-sha256;x-date, '
        'Signature=5190658c5ac5ea62e5a3e7649c38f65e45a7b16e4daa4d241d48d7efeb27dae9')


def client_with(monkeypatch, replies, captured=None):
    from video_ai.jimeng_config import parse_image_generation
    from video_ai.adapters.external_https import ExternalHttpsClient
    from video_ai.adapters.jimeng import JimengClient
    monkeypatch.setenv('TEST_VOLC_AK', 'test-access')
    monkeypatch.setenv('TEST_VOLC_SK', 'test-secret')
    def transport(request, **kwargs):
        if captured is not None: captured.append(request)
        value = replies.pop(0)
        if isinstance(value, BaseException): raise value
        return Response(json.dumps(value).encode())
    settings = parse_image_generation(image_settings(), 'test')
    return JimengClient(settings, http=ExternalHttpsClient(transport=transport))


def test_submit_and_query_use_frozen_model_and_distinct_actions(monkeypatch):
    captured = []
    client = client_with(monkeypatch, [dict(code=10000, data={'task_id': 'official_task_1'}, request_id='req1'),
        dict(code=10000, data={'status': 'done', 'image_urls': ['https://cdn.example/a?sig=secret']}, request_id='req2')], captured)
    submitted = client.submit('湖水')
    result = client.query(submitted['task_id'])
    assert result['status'] == 'done'
    assert json.loads(captured[0].data)['prompt'] == '湖水'
    assert json.loads(captured[1].data)['task_id'] == 'official_task_1'
    assert json.loads(captured[1].data)['req_key'] == 'jimeng_t2i_v40'
    assert json.loads(json.loads(captured[1].data)['req_json'])['return_url'] is True
    assert [parse_qs(urlsplit(r.full_url).query)['Action'][0] for r in captured] == [
        'CVSync2AsyncSubmitTask', 'CVSync2AsyncGetResult']
    assert 'sig=secret' not in json.dumps(result['diagnostic'])


@pytest.mark.parametrize('status', ['in_queue', 'generating', 'done', 'expired', 'not_found', 'failed'])
def test_each_official_state_is_preserved(monkeypatch, status):
    data = dict(status=status)
    if status == 'done': data['image_urls'] = ['https://cdn.example/a', 'https://cdn.example/b']
    client = client_with(monkeypatch, [dict(code=10000, data=data)])
    assert client.query('task_1')['status'] == status


@pytest.mark.parametrize('reply', [dict(code=50000, data={'task_id': 'must-not-accept'}),
    dict(code=10000, data=None), dict(code=10000, data={}), dict(code=True, data={'task_id': 'bad'})])
def test_business_error_and_empty_data_refused_before_reading_task(monkeypatch, reply):
    from video_ai.adapters.common import AdapterError
    client = client_with(monkeypatch, [reply])
    with pytest.raises(AdapterError): client.submit('湖水')


@pytest.mark.parametrize('status,data', [('unknown', {}), ('done', {}), ('done', {'image_urls': []}),
                                      ('done', {'image_urls': ['http://unsafe/image']})])
def test_invalid_results_are_not_completed(monkeypatch, status, data):
    from video_ai.adapters.common import AdapterError
    client = client_with(monkeypatch, [dict(code=10000, data=dict(status=status, **data))])
    with pytest.raises(AdapterError): client.query('task_1')


@pytest.mark.parametrize('url', ['http://host/a', 'https://user:pw@host/a', 'https://host/a#frag',
                               'https://localhost/a', 'https://127.0.0.1/a', 'https://host/a\n'])
def test_external_transport_refuses_invalid_urls(url):
    from video_ai.adapters.external_https import ExternalHttpsClient
    with pytest.raises(ValueError): ExternalHttpsClient().request('GET', url)


def test_transport_error_never_exposes_signed_url_or_credentials(monkeypatch):
    from video_ai.adapters.common import AdapterError
    client = client_with(monkeypatch, [OSError('https://cdn.example/?sig=private test-secret')])
    with pytest.raises(AdapterError) as error: client.submit('湖水')
    assert 'private' not in str(error.value)
    assert 'test-secret' not in str(error.value)
    assert error.value.kind.value == 'ambiguous'


def test_response_redaction_removes_credentials_and_nested_signed_urls(monkeypatch):
    client = client_with(monkeypatch, [dict(code=10000, request_id='req-safe', data={'task_id': 'task'},
        message='test-secret https://cdn.example/a?sig=private', extra={'Authorization': 'abc'})])
    result = client.submit('湖水')
    diagnostic = json.dumps(result['diagnostic'])
    assert all(secret not in diagnostic for secret in ('test-secret', 'sig=private', 'abc'))
    assert 'req-safe' in diagnostic


@pytest.mark.parametrize('failure', ['oversize', 'short', 'redirect', 'http'])
def test_https_response_failures_are_bounded_without_retry(failure):
    from video_ai.adapters.external_https import ExternalHttpsClient
    from video_ai.adapters.common import AdapterError
    calls = []
    def transport(request, **kwargs):
        calls.append(request)
        response = Response(b'12345')
        if failure == 'short': response.headers = {'Content-Length': '10'}
        if failure == 'redirect': response.geturl = lambda: 'https://other.example/a'
        if failure == 'http': response.status = 503
        return response
    with pytest.raises(AdapterError):
        ExternalHttpsClient(transport=transport).request('POST', 'https://visual.volcengineapi.com/',
            max_bytes=3 if failure == 'oversize' else 100)
    assert len(calls) == 1


def test_total_deadline_includes_blocking_transport_connection():
    from video_ai.adapters.external_https import ExternalHttpsClient
    from video_ai.adapters.common import AdapterError
    from threading import Event
    import time
    started = Event()
    finish = Event()
    def transport(request, **kwargs):
        started.set(); finish.wait(.6)
        return Response(b'{}')
    before = time.monotonic()
    try:
        with pytest.raises(AdapterError):
            ExternalHttpsClient(transport=transport).request('POST', 'https://visual.volcengineapi.com/', timeout=.03)
        assert time.monotonic()-before < .3
        assert started.is_set()
    finally:
        finish.set()
