"""Real local HTTP models with recorded payloads; service ownership is simulated."""
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import threading
import wave


def wav_bytes(samples=4800, silent=False):
    buffer = BytesIO()
    with wave.open(buffer, 'wb') as file:
        file.setparams((1, 2, 48000, 0, 'NONE', ''))
        file.writeframes((b'\0\0' if silent else b'\x40\x01') * samples)
    return buffer.getvalue()


def proposal_for(body):
    # The prompt is application data; tests return one lossless piece per fixed candidate.
    prompt = body['prompt']
    data = json.loads(prompt.split('\nINPUT_JSON\n', 1)[1].split('\nCORRECTION\n', 1)[0])
    facts = dict(subject=None, action_or_state=None, setting=None, quantity=None,
                 negation=None, relation_or_order=None, context_sources=[], resolved_references=[])
    return {s['unit_id']: [dict(text_end=s['end'], semantic_reason='单一原文画面', facts=facts)]
            for s in data['candidates']}


@contextmanager
def model_server(handler=None):
    posts = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            posts.append((self.path, body))
            status, media, response = handler(self.path, body, len(posts)) if handler else (
                (200, 'application/json', json.dumps(dict(model='qwen3:8b', done=True,
                    response=json.dumps(proposal_for(body), ensure_ascii=False))).encode())
                if self.path == '/api/generate' else (200, 'audio/wav', wav_bytes()))
            self.send_response(status); self.send_header('Content-Type', media)
            self.send_header('Content-Length', str(len(response))); self.end_headers()
            try: self.wfile.write(response)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}', posts
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def config_for_server(config, url, run):
    from video_ai.config import load_config
    from video_ai.runtime.manifest import thaw
    data = thaw(config.raw)
    data['services'].update(ollama=url, tts=url)
    actual = load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    for name in ('ffmpeg', 'ffprobe'):
        data['tools'][name] = str(actual.tools[name])
    file = run/'http-production-config.json'
    file.write_text(json.dumps(data), encoding='utf-8')
    return load_config(file)


def install_owned_services(monkeypatch):
    from video_ai.runtime.services import ServiceHandle
    class OwnedManager:
        stopped = []
        def __init__(self, *args, **kwargs): pass
        def ensure(self, spec): return ServiceHandle(spec.name, spec.url, True, None, None, None)
        def stop(self, handle): self.stopped.append(handle.name)
    # Simulates Popen ownership only; all inference still goes through a real HTTP server.
    import video_ai.runtime.production_storyboard as units
    import video_ai.runtime.production_speech as speech
    monkeypatch.setattr(units, 'ServiceManager', OwnedManager)
    monkeypatch.setattr(speech, 'ServiceManager', OwnedManager)
    monkeypatch.setattr(units, 'port_listening', lambda *args: False)
    monkeypatch.setattr(speech, 'port_listening', lambda *args: False)
    monkeypatch.setattr(speech, 'validate_production_voice_startup', lambda *args, **kwargs: None)
    return OwnedManager
