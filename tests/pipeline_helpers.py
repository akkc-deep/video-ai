"""TEST ONLY author/service fixtures; never bind production acceptance."""
from contextlib import contextmanager
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import wave

from video_ai.runtime.manifest import hash_file, now, thaw
from video_ai.planning.segments import segment_text


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    return path


def unit_review(script, path):
    text=script.read_bytes().decode('utf-8-sig')
    return write(path,dict(schema_version=1,script_identity=thaw(hash_file(script)),review_method='agent_source',
        reviewer='TEST ONLY original author',reviewed_at=now(),verdict='passed',reason='TEST ONLY single meanings.',
        spans=[dict(unit_id=s.unit_id,kind=s.kind,text_start=s.start,text_end=s.end,text=s.text,
            single_visual_semantics=True if s.kind=='speech' else None,verdict='passed',reason='TEST ONLY original unit.',
            context_sources=[],resolved_references=[]) for s in segment_text(text)]))


def review_index(run, entries):
    return write(run/'logs/pipeline'/('reviews-'+__import__('uuid').uuid4().hex+'.json'),
        dict(schema_version=1,run_id=run.name,created_at=now(),entries={role:thaw(hash_file(path)) for role,path in entries.items()}))


@contextmanager
def tts_server():
    """Real finite local HTTP responses containing decodable mono PCM WAV."""
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as file:
        file.setparams((1,2,24000,0,'NONE',''));file.writeframes(b'\x00\x01'*12000)
    wav=buffer.getvalue(); requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            length=int(self.headers['Content-Length'])
            body=json.loads(self.rfile.read(length));requests.append(body)
            self.send_response(200);self.send_header('Content-Type','audio/wav')
            self.send_header('Content-Length',str(len(wav)));self.end_headers();self.wfile.write(wav)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield f'http://127.0.0.1:{server.server_port}',requests
    finally:server.shutdown();server.server_close();thread.join(timeout=5)


def patch_committed_upstream(monkeypatch, composition):
    """Reuse VAI-12's real candidate fixture; isolate model-stage algorithms."""
    from video_ai.runtime import pipeline_stages as stages
    from video_ai.runtime import pipeline_inventory
    def isolated_projection(config,identities):
        value=thaw(config);value.pop('raw');value['voice'].pop('raw');return value
    monkeypatch.setattr(pipeline_inventory,'config_projection',isolated_projection)
    from video_ai.runtime.manifest import ManifestStore
    from video_ai.runtime.timeline_checks import _artifact
    # The older publication fixture refreshes PCM identities after constructing
    # its mocked composition. Bind that TEST ONLY origin's final bytes once.
    run=Path(composition['candidate_identity']['path']).parents[2]
    store=ManifestStore.open(run);snapshot=store.snapshot();identity=hash_file(run/'composition.json')
    snapshot['stages']['composition']['artifacts']=[_artifact(identity)]
    snapshot['workflows']['composition_report']=thaw(identity)
    write(run/'manifest.json',snapshot)
    original=stages.consume
    def consume(name,config,run):
        if name in ('validation','publish'):return original(name,config,run)
        if name=='speech':return dict(accepted=True,input_identities=composition['input_identities'])
        if name=='composition':return composition
        return dict(status='completed')
    monkeypatch.setattr(stages,'consume',consume)
