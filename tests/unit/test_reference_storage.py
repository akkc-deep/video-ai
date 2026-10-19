"""TOS protocol vectors and storage recovery, with no cloud requests."""
from datetime import datetime, timezone
import hashlib
import hmac
import io
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest


def storage_settings(**changes):
    return dict(dict(provider='volcengine_tos', bucket='test-bucket', region='cn-beijing',
                    endpoint='https://tos-cn-beijing.volces.com', access_key_env='TEST_TOS_AK',
                    secret_key_env='TEST_TOS_SK', key_prefix='video-ai-references',
                    url_ttl_seconds=3600, download_margin_seconds=120,
                    clock_skew_seconds=60, request_timeout_seconds=1), **changes)


class Response(io.BytesIO):
    def __init__(self, request, *, status=200, body=b'', headers=None):
        super().__init__(body)
        self.status, self.headers, self.url = status, headers or {}, request.full_url
    def geturl(self): return self.url


def original(tmp_path):
    data = b'\x89PNG\r\n\x1a\noriginal fixture bytes'
    path = tmp_path / '\u56fa\u5b9a\u539f\u56fe.png'
    path.write_bytes(data)
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                width=1, height=1, format='png'), data


def storage(monkeypatch, transport, **kwargs):
    from video_ai.adapters.external_https import ExternalHttpsClient
    from video_ai.adapters.reference_storage import ReferenceStorage
    monkeypatch.setenv('TEST_TOS_AK', 'test-ak')
    monkeypatch.setenv('TEST_TOS_SK', 'test-sk')
    settings = kwargs.pop('settings', storage_settings())
    return ReferenceStorage(settings, http=ExternalHttpsClient(transport=transport),
                            clock=lambda: datetime(2026, 10, 18, tzinfo=timezone.utc), **kwargs)


def identity_headers(row):
    return {'Content-Length': str(row['bytes']), 'Content-Type': 'image/png',
            'X-Tos-Meta-Sha256': row['sha256'], 'ETag': '"server-etag"'}


def test_fixed_tos4_get_and_header_vectors(monkeypatch):
    # Independent oracle: canonical bytes are specified here, without calling
    # production canonicalization or signing helpers.
    from video_ai.adapters.reference_storage import ReferenceStorage

    monkeypatch.setenv('TEST_TOS_AK', 'test-ak')
    monkeypatch.setenv('TEST_TOS_SK', 'test-sk')
    settings = dict(provider='volcengine_tos', bucket='test-bucket', region='cn-beijing',
                    endpoint='https://tos-cn-beijing.volces.com', access_key_env='TEST_TOS_AK',
                    secret_key_env='TEST_TOS_SK', key_prefix='video-ai-references',
                    url_ttl_seconds=3600, download_margin_seconds=120,
                    clock_skew_seconds=60, request_timeout_seconds=60)
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    storage = ReferenceStorage(settings, clock=lambda: now)
    key = 'video-ai-references/fixture-run/' + 'a'*64 + '.original'
    record = dict(bucket='test-bucket', region='cn-beijing', endpoint=settings['endpoint'],
                  key=key, bytes=1, sha256='a'*64, content_type='image/png', etag='"fixture"')
    query = ('X-Tos-Algorithm=TOS4-HMAC-SHA256&'
             'X-Tos-Credential=test-ak%2F20261018%2Fcn-beijing%2Ftos%2Frequest&'
             'X-Tos-Date=20261018T000000Z&X-Tos-Expires=3600&X-Tos-SignedHeaders=host')
    host = 'test-bucket.tos-cn-beijing.volces.com'
    canonical = ('GET\n/' + key + '\n' + query + '\nhost:' + host + '\n\nhost\nUNSIGNED-PAYLOAD').encode()
    signing_key = b'test-sk'
    for value in ('20261018', 'cn-beijing', 'tos', 'request'):
        signing_key = hmac.new(signing_key, value.encode(), hashlib.sha256).digest()
    string_to_sign = ('TOS4-HMAC-SHA256\n20261018T000000Z\n20261018/cn-beijing/tos/request\n' +
                      hashlib.sha256(canonical).hexdigest()).encode()
    signature = hmac.new(signing_key, string_to_sign, hashlib.sha256).hexdigest()
    signed = storage.presign_get(record, expires_seconds=3600)
    assert signed == dict(url='https://' + host + '/' + key + '?' + query + '&X-Tos-Signature=' + signature,
                          issued_at='2026-10-18T00:00:00Z', expires_at='2026-10-18T01:00:00Z')
    assert parse_qs(urlsplit(signed['url']).query)['X-Tos-Signature'] == [signature]
    # Header authentication has a separate fixed canonical HEAD vector.
    canonical_head = (f'HEAD\n/{key}\n\nhost:{host}\nx-tos-content-sha256:UNSIGNED-PAYLOAD\n'
                      'x-tos-date:20261018T000000Z\n\nhost;x-tos-content-sha256;x-tos-date\nUNSIGNED-PAYLOAD')
    head_message = ('TOS4-HMAC-SHA256\n20261018T000000Z\n20261018/cn-beijing/tos/request\n'+
                    hashlib.sha256(canonical_head.encode()).hexdigest())
    head_signature = hmac.new(signing_key, head_message.encode(), hashlib.sha256).hexdigest()
    assert storage._headers('HEAD', record, 'test-ak', 'test-sk')['Authorization'] == (
        'TOS4-HMAC-SHA256 Credential=test-ak/20261018/cn-beijing/tos/request, '
        'SignedHeaders=host;x-tos-content-sha256;x-tos-date, Signature='+head_signature)


def test_upload_signs_headers_and_verifies_remote_bytes(monkeypatch, tmp_path):
    row, data = original(tmp_path)
    captured, callbacks = [], []
    caller = threading.get_ident()
    def transport(request, **kwargs):
        captured.append(request)
        method = request.get_method()
        if len(captured) == 1:
            return Response(request, status=404)
        if method == 'PUT':
            assert callbacks == [caller]
            assert request.data == data
            return Response(request)
        return Response(request, headers=identity_headers(row), body=data if method == 'GET' else b'')
    client = storage(monkeypatch, transport)
    result = client.ensure_original(row, run_id='fixture-run', before_put=lambda: callbacks.append(threading.get_ident()))
    assert [r.get_method() for r in captured] == ['HEAD', 'PUT', 'HEAD', 'GET']
    assert result == dict(bucket='test-bucket', region='cn-beijing', endpoint='https://tos-cn-beijing.volces.com',
                          key='video-ai-references/fixture-run/'+row['sha256']+'.original', bytes=len(data),
                          sha256=row['sha256'], content_type='image/png', etag='"server-etag"')
    put = dict((k.lower(), v) for k, v in captured[1].header_items())
    canonical_headers = (f'content-type:image/png\nhost:test-bucket.tos-cn-beijing.volces.com\n'
                         f'x-tos-content-sha256:{row["sha256"]}\nx-tos-date:20261018T000000Z\n'
                         f'x-tos-meta-sha256:{row["sha256"]}\n')
    names = 'content-type;host;x-tos-content-sha256;x-tos-date;x-tos-meta-sha256'
    canonical = f'PUT\n/{result["key"]}\n\n{canonical_headers}\n{names}\n{row["sha256"]}'
    key = b'test-sk'
    for part in ('20261018', 'cn-beijing', 'tos', 'request'):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    message = ('TOS4-HMAC-SHA256\n20261018T000000Z\n20261018/cn-beijing/tos/request\n'+
               hashlib.sha256(canonical.encode()).hexdigest())
    signature = hmac.new(key, message.encode(), hashlib.sha256).hexdigest()
    assert put['authorization'] == ('TOS4-HMAC-SHA256 Credential=test-ak/20261018/cn-beijing/tos/request, '
                                     f'SignedHeaders={names}, Signature={signature}')
    assert 'test-ak' not in str(result) and 'test-sk' not in str(result)


def test_existing_verified_object_writes_logical_intent_without_put(monkeypatch, tmp_path):
    row, data = original(tmp_path)
    calls, authorized = [], []
    def transport(request, **kwargs):
        calls.append(request.get_method())
        return Response(request, headers=identity_headers(row), body=data if request.get_method() == 'GET' else b'')
    client = storage(monkeypatch, transport)
    result = client.ensure_original(row, run_id='fixture-run', before_put=lambda: authorized.append(threading.get_ident()))
    assert calls == ['HEAD', 'GET'] and result['sha256'] == row['sha256']
    assert authorized == [threading.get_ident()]


@pytest.mark.parametrize('failure', ['metadata', 'bytes', 'length', 'type', 'etag', '403', 'redirect'])
def test_conflicting_or_unreadable_object_never_overwritten(monkeypatch, tmp_path, failure):
    from video_ai.adapters.common import AdapterError
    row, data = original(tmp_path)
    calls = []
    def transport(request, **kwargs):
        calls.append(request.get_method())
        headers = identity_headers(row)
        if failure == 'metadata': headers['X-Tos-Meta-Sha256'] = 'b'*64
        if failure == 'length': headers['Content-Length'] = '999'
        if failure == 'type': headers['Content-Type'] = 'image/jpeg'
        if failure == 'etag': headers.pop('ETag')
        payload = data if failure != 'bytes' else b'z'*len(data)
        response = Response(request, status=403 if failure == '403' else 200, headers=headers,
                            body=payload if request.get_method() == 'GET' else b'')
        if failure == 'redirect': response.url += '?unexpected=secret'
        return response
    with pytest.raises(AdapterError):
        storage(monkeypatch, transport).ensure_original(row, run_id='fixture-run', before_put=lambda: None)
    assert 'PUT' not in calls


def test_unknown_put_is_not_replayed_and_next_call_verifies_existing_object(monkeypatch, tmp_path):
    from video_ai.adapters.common import AdapterError, FailureKind
    row, data = original(tmp_path)
    calls = []
    def transport(request, **kwargs):
        calls.append(request.get_method())
        if len(calls) == 1: return Response(request, status=404)
        if request.get_method() == 'PUT': raise OSError('secret test-sk signed?token=private')
        return Response(request, headers=identity_headers(row), body=data if request.get_method() == 'GET' else b'')
    client = storage(monkeypatch, transport)
    with pytest.raises(AdapterError) as error:
        client.ensure_original(row, run_id='fixture-run', before_put=lambda: None)
    assert error.value.kind == FailureKind.ambiguous
    assert all(s not in str(error.value) for s in ('test-sk', 'private', 'Authorization'))
    assert client.ensure_original(row, run_id='fixture-run', before_put=lambda: None)['sha256'] == row['sha256']
    assert calls == ['HEAD', 'PUT', 'HEAD', 'GET']


@pytest.mark.parametrize('cancel', ['raises', 'deadline', 'ownership'])
def test_cancelled_caller_callback_never_allows_late_put(monkeypatch, tmp_path, cancel):
    from video_ai.adapters.common import AdapterError
    row, _ = original(tmp_path)
    calls, owned = [], [True]
    def transport(request, **kwargs):
        calls.append(request.get_method())
        return Response(request, status=404)
    def ownership():
        if not owned[0]: raise RuntimeError('lock gone')
    def before_put():
        assert threading.current_thread() is threading.main_thread()
        if cancel == 'raises': raise RuntimeError('sensitive callback details')
        if cancel == 'deadline': time.sleep(.05)
        if cancel == 'ownership': owned[0] = False
    client = storage(monkeypatch, transport, ownership_check=ownership,
                     settings=storage_settings(request_timeout_seconds=.03))
    with pytest.raises(AdapterError):
        client.ensure_original(row, run_id='fixture-run', before_put=before_put)
    time.sleep(.04)
    assert calls == ['HEAD']


def test_late_head_cannot_request_put_after_deadline(monkeypatch, tmp_path):
    from video_ai.adapters.common import AdapterError
    row, _ = original(tmp_path)
    release, completed = threading.Event(), threading.Event()
    calls, authorized = [], []
    def transport(request, **kwargs):
        calls.append(request.get_method())
        release.wait(.4)
        completed.set()
        return Response(request, status=404)
    client = storage(monkeypatch, transport, settings=storage_settings(request_timeout_seconds=.03))
    try:
        with pytest.raises(AdapterError):
            client.ensure_original(row, run_id='fixture-run', before_put=lambda: authorized.append(True))
    finally: release.set()
    assert completed.wait(.5)
    assert calls == ['HEAD'] and not authorized


@pytest.mark.parametrize('change', ['bytes', 'sha256', 'run_id', 'format', 'credential'])
def test_invalid_local_identity_and_missing_credentials_send_nothing(monkeypatch, tmp_path, change):
    from video_ai.adapters.common import AdapterError
    row, _ = original(tmp_path)
    calls = []
    client = storage(monkeypatch, lambda request, **k: calls.append(request))
    run_id = 'fixture-run'
    if change == 'bytes': row['bytes'] += 1
    if change == 'sha256': row['sha256'] = 'f'*64
    if change == 'run_id': run_id = '../other'
    if change == 'format': row['format'] = 'png\nsecret'
    if change == 'credential': monkeypatch.delenv('TEST_TOS_SK')
    with pytest.raises(AdapterError):
        client.ensure_original(row, run_id=run_id, before_put=lambda: None)
    assert not calls


@pytest.mark.parametrize('expires', [True, 0, 604801, float('inf')])
def test_presign_rejects_invalid_ttl_without_network(monkeypatch, expires):
    client = storage(monkeypatch, lambda *a, **k: pytest.fail('presign must not request network'))
    with pytest.raises(ValueError): client.presign_get({}, expires_seconds=expires)


def test_credential_rotation_only_changes_live_signature(monkeypatch, tmp_path):
    row, _ = original(tmp_path)
    client = storage(monkeypatch, lambda *a, **k: pytest.fail('presign must not request network'))
    record = dict(client._object(row, 'fixture-run'), etag='"object"')
    first = client.presign_get(record, expires_seconds=3600)
    monkeypatch.setenv('TEST_TOS_SK', 'rotated-secret')
    second = client.presign_get(record, expires_seconds=3600)
    assert first['url'] != second['url']
    assert {k: v for k, v in first.items() if k != 'url'} == {k: v for k, v in second.items() if k != 'url'}
    assert all(secret not in str(record) for secret in ('test-ak', 'test-sk', 'rotated-secret'))
