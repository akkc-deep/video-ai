"""Opt-in concrete HTTP checks every wire write without rescanning reads."""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from uuid import uuid4

import pytest


@pytest.fixture
def wire_server():
    seen=[];responded=threading.Event()
    controls={}
    body=json.dumps({'padding':'x'*(2*1024*1024),
        'Save':{'input':{'required':{'filename_prefix':['STRING']}},'output_node':True}}).encode()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            seen.append(('GET',self.path))
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)+controls.get('extra_length',0)))
            self.end_headers();responded.set()
            try:
                if 'release_read' in controls:
                    self.wfile.write(body[:65536]);self.wfile.flush()
                    controls['read_started'].set();controls['release_read'].wait(2)
                    self.wfile.write(body[65536:])
                else:self.wfile.write(body)
            except OSError:pass
        def do_POST(self):
            expected=int(self.headers['Content-Length']);raw=self.rfile.read(expected)
            if len(raw)==expected:
                seen.append(('POST',json.loads(raw)))
                if 'on_post' in controls:controls['on_post']()
            try:
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.end_headers();self.wfile.write(b'{}')
            except OSError:pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    yield dict(url=f'http://127.0.0.1:{server.server_port}',seen=seen,body=body,responded=responded,controls=controls)
    server.shutdown();server.server_close();thread.join(timeout=2)


def client(server,guard):
    from video_ai.adapters.scene_comfy import SceneComfyClient
    return SceneComfyClient(server['url'],request_timeout=180,ownership_check=guard,send_checks_only=True)


def test_large_response_cost_is_independent_of_read_chunks(wire_server,monkeypatch):
    import video_ai.adapters.scene_comfy as module
    clock=[0.];calls=[]
    def guard():calls.append(threading.get_ident());clock[0]+=4.406
    monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    response=client(wire_server,guard).object_info(timeout=180)
    assert response['body']==wire_server['body']
    assert clock[0]<10 and len(calls)==1
    assert wire_server['seen']==[('GET','/object_info')]


def test_post_headers_and_body_each_check_ownership(wire_server):
    calls=[]
    def guard():
        calls.append(1)
        if len(calls)==2:raise RuntimeError('ownership lost before body')
    with pytest.raises(RuntimeError,match='before body'):
        client(wire_server,guard).submit({'5':{}},client_id=str(uuid4()),timeout=1)
    assert len(calls)==2
    assert not any(row[0]=='POST' for row in wire_server['seen'])


def test_connect_time_ownership_loss_still_prevents_all_writes(wire_server,monkeypatch):
    original=socket.create_connection;owned=[True]
    def connect(*args,**kwargs):
        result=original(*args,**kwargs);owned[0]=False;return result
    monkeypatch.setattr(socket,'create_connection',connect)
    def guard():
        if not owned[0]:raise RuntimeError('lost after connect')
    with pytest.raises(RuntimeError,match='after connect'):
        client(wire_server,guard).submit({},client_id=str(uuid4()),timeout=1)
    assert wire_server['seen']==[]


def test_callback_cannot_spend_last_budget_then_write(wire_server,monkeypatch):
    import video_ai.adapters.scene_comfy as module
    clock=[0.]
    def guard():clock[0]+=181
    monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    with pytest.raises(TimeoutError):client(wire_server,guard).queue(timeout=180)
    assert wire_server['seen']==[]


def test_late_dns_is_cancelled_before_write(wire_server,monkeypatch):
    original=socket.getaddrinfo;entered=threading.Event();release=threading.Event()
    def delayed(*args,**kwargs):
        entered.set();release.wait(1);return original(*args,**kwargs)
    monkeypatch.setattr(socket,'getaddrinfo',delayed)
    try:
        with pytest.raises(TimeoutError):client(wire_server,lambda:None).queue(timeout=.05)
        assert entered.is_set()
    finally:release.set()
    time.sleep(.1);assert wire_server['seen']==[]


def test_next_send_rechecks_changed_dependencies(wire_server):
    owned=[True]
    def guard():
        if not owned[0]:raise RuntimeError('source changed')
    transport=client(wire_server,guard)
    assert transport.object_info(timeout=1)['body']==wire_server['body']
    owned[0]=False
    with pytest.raises(RuntimeError,match='source changed'):
        transport.submit({},client_id=str(uuid4()),timeout=1)
    assert not any(row[0]=='POST' for row in wire_server['seen'])


def test_opt_in_rejects_unknown_transport(wire_server):
    from video_ai.adapters.scene_comfy import SceneComfyClient
    with pytest.raises(ValueError,match='concrete'):
        SceneComfyClient(wire_server['url'],request_timeout=1,ownership_check=lambda:None,
                         http=object(),send_checks_only=True)


def test_wire_guard_keeps_authenticated_context(wire_server):
    from video_ai.runtime.scene_execution_records import _writer_admissions
    from video_ai.runtime.verification import validation_session,validation_memo
    admitted={'source':'caller'};token=_writer_admissions.set(admitted)
    try:
        with validation_session():
            expected=validation_memo('wire-budget-context');expected['proof']='original'
            def guard():
                assert _writer_admissions.get() is admitted
                assert validation_memo('wire-budget-context') is expected
            assert client(wire_server,guard).queue(timeout=1)['body']==wire_server['body']
    finally:_writer_admissions.reset(token)


def test_cancel_during_response_read_cannot_resume_request(wire_server):
    release=threading.Event();started=threading.Event();calls=[]
    wire_server['controls'].update(release_read=release,read_started=started)
    try:
        with pytest.raises(TimeoutError):client(wire_server,lambda:calls.append(1)).queue(timeout=.1)
        assert started.is_set()
    finally:release.set()
    time.sleep(.1)
    assert len(calls)==1 and wire_server['seen']==[('GET','/queue')]


def test_read_limits_and_complete_body_still_apply(wire_server,monkeypatch):
    import video_ai.adapters.scene_comfy as module
    monkeypatch.setattr(module,'JSON_LIMIT',1024)
    with pytest.raises(ValueError,match='exceeds'):
        client(wire_server,lambda:None).object_info(timeout=1)


def test_declared_body_length_must_match(wire_server):
    wire_server['controls']['extra_length']=1
    with pytest.raises(ValueError,match='incomplete'):
        client(wire_server,lambda:None).queue(timeout=1)


from test_scene_media_check_coverage import coverage_case,transaction


def test_post_response_drift_cannot_persist_raw_or_acceptance(wire_server,coverage_case,transaction):
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.production_scene_clips import _GuardedLogger
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.scene_upscale_transactions import recover_or_submit_scene_frame
    c=coverage_case();s=c['store'];_,request,graph,template=transaction
    wire_server['controls']['on_post']=lambda:c['budget'].write_text('{"budget":2}')
    with RunLock(c['run']) as lock:
        s.lock=lock;s._media_check_coverage=c['module'].capture_media_check_coverage(s,c['source'])
        s.write('inputs.json',{});folder=s.frame_dir(request['frame_id'])
        s.write(folder/'request.json',request);s.write(folder/'graph.json',graph)
        transport=client(wire_server,s.capture_guard(request,graph))
        with pytest.raises((ValueError,OSError)) as refused:
            recover_or_submit_scene_frame(s,request,graph,client=transport,template=template,
                ensure_service=lambda:None,logger=_GuardedLogger(RunLogger(s.run_dir,production=True),s.assert_write),timeout=2)
        assert len([row for row in wire_server['seen'] if row[0]=='POST'])==1,str(refused.value)
        assert len(list((folder/'http').glob('*.request.json')))==1
        assert not list((folder/'http').glob('*.body'))
        assert not (folder/'accepted.json').exists() and not (folder/'submission.json').exists()
