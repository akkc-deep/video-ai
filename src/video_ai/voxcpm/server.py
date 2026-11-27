"""Loopback-only HTTP surface for finite, persistent local speech tasks."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import shutil
import signal
import threading
from urllib.parse import unquote, urlsplit

from ..runtime.storage import VideoStorage
from .contracts import ApiError
from .service import JobService
from .store import JobStore


def make_server(service, host, port, stop_token):
    if host != '127.0.0.1':
        raise ValueError('only 127.0.0.1 is supported')

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, format, *args):
            pass  # Durable task evidence is in SQLite, not repetitive request logs.

        def _body(self):
            if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                raise ApiError(400, 'Content-Type must be application/json')
            if self.headers.get('Origin') or self.headers.get('Transfer-Encoding'):
                raise ApiError(400, 'browser origins and transfer encoding are not supported')
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 65536:
                    raise ValueError('body size must be 1–65536 bytes')
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise ValueError('incomplete request body')
                def invalid_constant(value):
                    raise ValueError('nonfinite JSON number')
                value = json.loads(raw.decode('utf-8'), parse_constant=invalid_constant)
                if not isinstance(value, dict):
                    raise ValueError('JSON object required')
                return value
            except (ValueError, UnicodeError) as error:
                raise ApiError(400, str(error)) from error

        def _send(self, status, value):
            if isinstance(value, Path):
                self.send_response(status)
                self.send_header('Content-Type', 'audio/wav')
                self.send_header('Content-Length', str(value.stat().st_size))
                self.end_headers()
                with value.open('rb') as file:
                    shutil.copyfileobj(file, self.wfile)
            else:
                data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        def _route(self):
            path = unquote(urlsplit(self.path).path)
            if self.command == 'GET' and path == '/health':
                return (200 if service.state == 'ready' else 503), service.health()
            if self.command == 'GET' and path == '/voices':
                return 200, dict(voices=[dict(voice_id=service.binding['voice_id'],
                    reference_sha256=service.binding['reference_sha256'])])
            if self.command == 'POST' and path == '/tts/generate':
                task, created = service.submit(self._body())
                return (202 if created else 200), task
            if self.command == 'POST' and path == '/shutdown':
                self._body()
                if not stop_token or not secrets.compare_digest(self.headers.get('X-Vox-Stop-Token', ''), stop_token):
                    raise ApiError(403, 'shutdown requires the owning launcher token')
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return 202, dict(status='shutdown_requested')
            parts = path.strip('/').split('/')
            if len(parts) in (3, 4) and parts[:2] == ['tts', 'tasks']:
                request_id = parts[2]
                if self.command == 'GET' and len(parts) == 3:
                    return 200, service.store.get(request_id)
                if self.command == 'POST' and len(parts) == 4 and parts[3] == 'cancel':
                    self._body()
                    return 200, service.cancel(request_id)
                if self.command == 'GET' and len(parts) == 4 and parts[3] == 'audio':
                    task = service.store.get(request_id)
                    if task['status'] != 'completed':
                        raise ApiError(409, 'audio is available only after completion')
                    artifact = service.store.output_path(request_id)
                    if not artifact.is_file():
                        raise ApiError(410, 'completed audio artifact is missing')
                    return 200, artifact
            raise ApiError(404, 'unknown endpoint')

        def _dispatch(self):
            try:
                status, value = self._route()
            except ApiError as error:
                status, value = error.status, dict(error=str(error))
            except Exception as error:
                status, value = 500, dict(error='internal service error', detail=type(error).__name__)
            try:
                self._send(status, value)
            except (BrokenPipeError, ConnectionError, TimeoutError):
                pass  # Response loss does not cancel or resubmit a durable task.

        do_GET = do_POST = _dispatch

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--listen', choices=['127.0.0.1'], default='127.0.0.1')
    parser.add_argument('--port', type=int, default=9881)
    parser.add_argument('--session-id', default='manual')
    parser.add_argument('--voice-profile', type=Path, help='Explicit Vox voice asset inside the runtime root')
    args = parser.parse_args()
    import os
    from .engine import load_assets
    root = VideoStorage().runtime_root
    with JobStore(args.state_dir, root) as store:
        binding, backend_factory = load_assets(root, store.directory, voice_profile=args.voice_profile)
        service = JobService(store, binding, backend_factory, session_id=args.session_id)
        server = make_server(service, args.listen, args.port, os.environ.get('VIDEO_AI_VOX_STOP_TOKEN', ''))
        service.start()
        def shutdown(*_):
            threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        try:
            server.serve_forever(poll_interval=.1)
        finally:
            server.server_close()
            service.close()


if __name__ == '__main__':
    main()
