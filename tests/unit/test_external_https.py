"""Additional controlled storage methods preserve the external HTTPS boundary."""
import io
import threading

import pytest

from video_ai.adapters.common import AdapterError
from video_ai.adapters.external_https import ExternalHttpsClient


class Response(io.BytesIO):
    status = 200
    headers = {'Content-Length': '999', 'ETag': '"object"'}
    def geturl(self): return 'https://store.example/object'


def test_head_returns_headers_without_reading_declared_object_body():
    result = ExternalHttpsClient(transport=lambda *a, **k: Response()).request('HEAD', 'https://store.example/object')
    assert result.body == b'' and result.headers['ETag'] == '"object"'


def test_only_explicit_head_allows_not_found():
    def transport(*a, **k):
        response = Response()
        response.status, response.headers = 404, {}
        return response
    client = ExternalHttpsClient(transport=transport)
    with pytest.raises(AdapterError): client.request('GET', 'https://store.example/object')
    with pytest.raises(AdapterError): client.request('HEAD', 'https://store.example/object')
    assert client.request('HEAD', 'https://store.example/object', allow_not_found=True).status == 404
    with pytest.raises(ValueError): client.request('GET', 'https://store.example/object', allow_not_found=True)


@pytest.mark.parametrize('reason', ['ownership', 'deadline'])
def test_real_connection_checks_guard_after_dns_before_transmitting(monkeypatch, reason):
    import video_ai.adapters.external_https as module
    from http.client import HTTPSConnection
    from threading import Event
    import time
    ready, release, finished = Event(), Event(), Event()
    transmitted, owned = [], [True]
    class Socket:
        def sendall(self, data): transmitted.append(data)
        def close(self): pass
        def shutdown(self, *args): pass
    def connect(connection):
        ready.set()
        release.wait(.5)
        connection.sock = Socket()
    monkeypatch.setattr(HTTPSConnection, 'connect', connect)
    def ownership():
        if not owned[0]: raise RuntimeError('lost')
    client = ExternalHttpsClient()
    errors = []
    def request():
        try: client.request('PUT', 'https://store.example/object', body=b'private',
                            timeout=.08, ownership_check=ownership)
        except AdapterError as exc: errors.append(exc)
        finally: finished.set()
    worker = threading.Thread(target=request)
    worker.start()
    try:
        assert ready.wait(.5)
        if reason == 'ownership': owned[0] = False
        else: assert finished.wait(.4)
    finally: release.set()
    worker.join(.5)
    time.sleep(.02)
    assert not transmitted and len(errors) == 1


def test_interrupted_caller_cancels_late_connection(monkeypatch):
    import video_ai.adapters.external_https as module
    from http.client import HTTPSConnection
    from queue import Queue
    import time
    ready, release, left_connect = threading.Event(), threading.Event(), threading.Event()
    transmitted = []
    class Socket:
        def sendall(self, data): transmitted.append(data)
        def close(self): pass
        def shutdown(self, *args): pass
    def connect(connection):
        ready.set()
        release.wait(.5)
        connection.sock = Socket()
        left_connect.set()
    class InterruptedQueue(Queue):
        def get(self, **kwargs):
            assert ready.wait(.5)
            raise KeyboardInterrupt()
    monkeypatch.setattr(HTTPSConnection, 'connect', connect)
    monkeypatch.setattr(module, 'Queue', InterruptedQueue)
    try:
        with pytest.raises(KeyboardInterrupt):
            ExternalHttpsClient().request('PUT', 'https://store.example/object', body=b'private')
    finally: release.set()
    assert left_connect.wait(.5)
    time.sleep(.02)
    assert not transmitted
