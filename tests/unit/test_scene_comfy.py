"""Scene HTTP transport: bounded memory, exact bytes, and actual send ownership."""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import pytest


@pytest.fixture
def server():
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((self.path, self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"ok":true}')
        def do_GET(self):
            seen.append((self.path, None))
            self.send_response(302); self.send_header('Location', '/prompt'); self.end_headers()
        def log_message(self, *args): pass
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    yield f'http://127.0.0.1:{http.server_port}', seen
    http.shutdown(); http.server_close(); thread.join()


def test_submit_preserves_client_identity_and_raw_response(server):
    from video_ai.adapters.scene_comfy import SceneComfyClient
    url, seen = server
    client_id = str(uuid4()); graph = {'97': {'inputs': {'image': 'original.png'}}}
    client = SceneComfyClient(url, request_timeout=1, ownership_check=lambda: None)
    response = client.submit(graph, client_id=client_id, timeout=1)
    assert set(response) == {'status', 'headers', 'body'}
    assert response['body'] == b'{"ok":true}'
    assert [(p, json.loads(b)) for p, b in seen] == [('/prompt', {'prompt': graph, 'client_id': client_id})]


def test_get_does_not_follow_redirect(server):
    from video_ai.adapters.scene_comfy import SceneComfyClient
    url, seen = server
    response = SceneComfyClient(url, request_timeout=1, ownership_check=lambda: None).queue(timeout=1)
    assert response['status'] == 302
    assert seen == [('/queue', None)]


def test_late_dns_cannot_send_after_deadline(server, monkeypatch):
    from video_ai.adapters.scene_comfy import SceneComfyClient
    url, seen = server; original = socket.getaddrinfo; entered = threading.Event(); release = threading.Event()
    def delayed(*args, **kwargs):
        entered.set(); release.wait(2); return original(*args, **kwargs)
    monkeypatch.setattr(socket, 'getaddrinfo', delayed)
    client = SceneComfyClient(url, request_timeout=.05, ownership_check=lambda: None)
    started = time.monotonic()
    with pytest.raises(TimeoutError): client.submit({}, client_id=str(uuid4()), timeout=.05)
    assert entered.is_set() and time.monotonic() - started < .5
    release.set(); time.sleep(.1)
    assert seen == []


def test_ownership_loss_after_connect_prevents_send(server, monkeypatch):
    from video_ai.adapters.scene_comfy import SceneComfyClient
    url, seen = server; original = socket.create_connection; owned = [True]
    def connect(*args, **kwargs):
        result = original(*args, **kwargs); owned[0] = False; return result
    monkeypatch.setattr(socket, 'create_connection', connect)
    def check():
        if not owned[0]: raise RuntimeError('lost lock')
    with pytest.raises(RuntimeError, match='lost lock'):
        SceneComfyClient(url, request_timeout=1, ownership_check=check).submit({}, client_id=str(uuid4()), timeout=1)
    assert seen == []


@pytest.mark.parametrize('url', ['https://127.0.0.1:80', 'http://example.com:80', 'http://127.0.0.1:80/extra'])
def test_only_loopback_origins(url):
    from video_ai.adapters.scene_comfy import SceneComfyClient
    with pytest.raises(ValueError): SceneComfyClient(url, request_timeout=1, ownership_check=lambda: None)


def test_history_rejects_path_injection(server):
    from video_ai.adapters.scene_comfy import SceneComfyClient
    url, seen = server
    with pytest.raises(ValueError):
        SceneComfyClient(url, request_timeout=1, ownership_check=lambda: None).history('../queue', timeout=1)
    assert seen == []


def test_slow_guard_cannot_send_after_caller_deadline(server):
    from video_ai.adapters.scene_comfy import SceneComfyClient
    url,seen=server; release=threading.Event(); caller=threading.get_ident()
    def check():
        if threading.get_ident()!=caller: release.wait(1)
    with pytest.raises(TimeoutError):
        SceneComfyClient(url,request_timeout=.05,ownership_check=check).submit({},client_id=str(uuid4()),timeout=.05)
    release.set(); time.sleep(.1)
    assert seen==[]
