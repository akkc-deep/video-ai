"""Offline performance contracts retain complete media and protocol proofs."""
from pathlib import Path
import json
import pytest

from unit.test_frames import media_context, make_video
from unit.test_scene_upscale_transactions import transaction, Client


def test_default_extraction_has_no_per_png_media_processes(media_context, monkeypatch):
    import video_ai.media.frames as frames
    from video_ai.media.scene_upscale import extract_scene_frames, verify_scene_frame_pixels
    run, kwargs = media_context
    source = make_video(media_context, frames=3)
    def per_png(*a, **kw):
        pytest.fail('per-PNG probe/decode duplicates the complete batch proof')
    monkeypatch.setattr(frames, 'inspect_image', per_png)
    rows, evidence = extract_scene_frames(source, run/'batch', expected_frames=3,
        width=128, height=72, **kwargs)
    assert len(rows) == 3 and len(evidence) < 20
    verify_scene_frame_pixels(source, [r['path'] for r in rows], expected_frames=3,
        width=128, height=72, config=kwargs['config'])


def test_video_inspection_reuses_content_only_inside_explicit_scope(media_context, monkeypatch):
    import video_ai.media.video as video
    run, kwargs = media_context
    source = make_video(media_context, frames=3)
    original = video._command
    calls = []
    def command(*a, **kw):
        calls.append(a[0]); return original(*a, **kw)
    monkeypatch.setattr(video, '_command', command)
    with video.inspection_reuse():
        first, _ = video.inspect_video(source, width=128, height=72, **kwargs)
        copied = run/'same.mp4'; copied.write_bytes(source.read_bytes())
        second, _ = video.inspect_video(copied, width=128, height=72, **kwargs)
        assert first['frames'] == second['frames'] == 3
        assert second['identity']['path'] == str(copied)
        assert len(calls) == 3
    video.inspect_video(copied, width=128, height=72, **kwargs)
    assert len(calls) == 6


def test_capability_reuse_is_bound_to_live_owned_instance_and_template(transaction):
    import video_ai.runtime.scene_upscale_transactions as tx
    store, request, graph, template = transaction
    client = Client(store, request, graph)
    cache = {}; identity = ['owned-1']
    for _ in range(3):
        tx._remote_validate(store, client, template, None, 1,
            capability_cache=cache, service_identity=lambda:identity[0])
    assert client.info_calls == 1
    identity[0] = 'owned-2'
    tx._remote_validate(store, client, template, None, 1,
        capability_cache=cache, service_identity=lambda:identity[0])
    assert client.info_calls == 2
    template.graph['5']['inputs']['filename_prefix'] = 'another'
    tx._remote_validate(store, client, template, None, 1,
        capability_cache=cache, service_identity=lambda:identity[0])
    assert client.info_calls == 3


def test_response_source_drift_cannot_write_raw_protocol_evidence(transaction):
    import video_ai.runtime.scene_upscale_transactions as tx
    store, request, graph, template = transaction
    folder = store.frame_dir(request['frame_id'])
    drift = [False]
    def guard():
        if drift[0]: raise RuntimeError('source bytes changed while reading response')
    store.capture_guard = lambda *a:guard
    intent = dict(client_id='00000000-0000-0000-0000-000000000001')
    def response(timeout):
        drift[0] = True
        return dict(status=200, headers={}, body=b'{}')
    with pytest.raises(RuntimeError, match='source bytes changed'):
        tx._record_http(store, request, intent, 'GET', '/queue', response, 1, graph)
    assert len(list((folder/'http').glob('*.request.json'))) == 1
    assert not list((folder/'http').glob('*.body'))


def test_known_prompt_waits_on_history_and_refreshes_queue_at_completion(transaction, monkeypatch):
    import video_ai.runtime.scene_upscale_transactions as tx
    store, request, graph, template = transaction
    client = Client(store, request, graph)
    original_history = client.history
    gets = []; sleeps = []
    def history(prompt_id=None, **kw):
        gets.append(('history',prompt_id))
        response = original_history(prompt_id, **kw)
        if sum(route=='history' for route,_ in gets) < 4:
            value = json.loads(response['body'])
            value[client.pid]['status'] = dict(status_str='running',completed=False,messages=[])
            value[client.pid]['outputs'] = {}
            response = client.response(value)
        return response
    def queue(**kw):
        gets.append(('queue',None))
        active = [] if sum(route=='history' for route,_ in gets)>=4 else [
            [1,client.pid,graph,dict(client_id=client.cid),['5']]]
        return client.response(dict(queue_running=active,queue_pending=[]))
    client.history=history;client.queue=queue
    monkeypatch.setattr(tx.time,'sleep',lambda seconds:sleeps.append(seconds))
    result=tx.recover_or_submit_scene_frame(store,request,graph,client=client,template=template,
        ensure_service=lambda:None,logger=None,timeout=10)
    assert result['prompt_id']==client.pid and client.posts==1
    assert [route for route,_ in gets].count('history')==4
    assert [route for route,_ in gets].count('queue')==2
    assert all(pid==client.pid for route,pid in gets if route=='history')
    assert sleeps[0] < 2


def test_history_tracker_parses_only_new_protocol_views(transaction,monkeypatch):
    import video_ai.runtime.scene_comfy_transactions as tx
    store,request,graph,template=transaction
    intent=dict(client_id='00000000-0000-0000-0000-000000000001')
    from video_ai.runtime.manifest import now
    rows=[];calls=[];parse=tx.strict_json
    def counting(raw):calls.append(raw);return parse(raw)
    monkeypatch.setattr(tx,'strict_json',counting)
    tracker=tx._HistoryTracker(intent,graph)
    for _ in range(20):
        rows.append(dict(request=dict(method='GET',route='/queue',started_at=now()),
            response=dict(status=200,error=None,headers={'Content-Type':'application/json'},finished_at=now()),
            raw=b'{"queue_running":[],"queue_pending":[]}',evidence={}))
        tracker.advance(rows,None)
    assert len(calls)==20


def test_capability_response_from_replaced_instance_is_refused(transaction):
    import video_ai.runtime.scene_upscale_transactions as tx
    from video_ai.runtime.production_state import ProductionRefused
    store,request,graph,template=transaction;client=Client(store,request,graph)
    identity=['owned-1'];original=client.object_info
    def replaced(**kwargs):
        result=original(**kwargs);identity[0]='owned-2';return result
    client.object_info=replaced
    with pytest.raises(ProductionRefused,match='service identity changed'):
        tx._remote_validate(store,client,template,None,1,capability_cache={},service_identity=lambda:identity[0])
    assert client.posts==0


def test_owned_service_cache_identity_rejects_pid_reuse(monkeypatch):
    from types import SimpleNamespace
    from video_ai.runtime.production_scene_clips import _OwnedService
    from video_ai.runtime.production_state import ProductionRefused
    service=object.__new__(_OwnedService)
    service.handle=SimpleNamespace(owned=True,pid=17,started_at='original',url='http://127.0.0.1:8188',
        process=SimpleNamespace(poll=lambda:None))
    monkeypatch.setattr('video_ai.runtime.production_state.process_started_at',lambda pid:'replacement')
    with pytest.raises(ProductionRefused,match='service identity changed'):service.capability_identity()


def test_batch_rejects_animation_even_when_first_pixels_match(media_context):
    import struct,zlib
    from video_ai.media.scene_upscale import extract_scene_frames,verify_scene_frame_pixels,InvalidScenePng
    run,kwargs=media_context;source=make_video(media_context,frames=3)
    rows,_=extract_scene_frames(source,run/'batch',expected_frames=3,width=128,height=72,**kwargs)
    path=Path(rows[0]['path']);raw=path.read_bytes();kind=b'acTL';data=struct.pack('>II',1,0)
    chunk=struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    path.write_bytes(raw[:33]+chunk+raw[33:])
    with pytest.raises(InvalidScenePng,match='animation'):
        verify_scene_frame_pixels(source,[r['path'] for r in rows],expected_frames=3,
            width=128,height=72,config=kwargs['config'])


def test_verified_png_identity_copies_share_one_decode_but_rehash_bytes(transaction,media_context,monkeypatch):
    import video_ai.runtime._scene_upscale_records as records
    from image_helpers import write_png
    from types import SimpleNamespace
    store,_,_,_=transaction;store.media_cache=set();store.verify_tools=lambda:None
    store.frozen=SimpleNamespace(config=media_context[1]['config'])
    source=store.run_dir/'original.png';write_png(source,128,72)
    paths=[source,store.run_dir/'staging.png',store.run_dir/'promoted.png']
    for p in paths[1:]:p.write_bytes(source.read_bytes())
    calls=[];verify=records.verify_png
    def observe(*a,**kw):calls.append(a[0]);return verify(*a,**kw)
    monkeypatch.setattr(records,'verify_png',observe)
    for path in paths:
        records.validate_png(store,store.artifact(path),width=128,height=72)
    assert len(calls)==1
    accepted=store.artifact(paths[-1]);paths[-1].write_bytes(b'changed despite cached content proof')
    with pytest.raises(AssertionError):records.validate_png(store,accepted,width=128,height=72)


def test_raw_body_write_cannot_authorize_metadata_after_source_drift(transaction):
    import video_ai.runtime.scene_upscale_transactions as tx
    store,request,graph,_=transaction;drift=[False];original=store.write_bytes
    def guard():
        if drift[0]:raise RuntimeError('source changed after raw body')
    store.capture_guard=lambda *a:guard
    def write(name,value):
        result=original(name,value)
        if str(name).endswith('.body'):drift[0]=True
        return result
    store.write_bytes=write
    with pytest.raises(RuntimeError,match='source changed after raw body'):
        tx._record_http(store,request,dict(client_id='00000000-0000-0000-0000-000000000001'),
            'GET','/queue',lambda _:dict(status=200,headers={},body=b'{}'),1,graph)
    folder=store.frame_dir(request['frame_id'])/'http'
    assert len(list(folder.glob('*.body')))==1 and not list(folder.glob('*.response.json'))


@pytest.mark.parametrize('fault',['last_crc','wrong_size','reordered','extra','missing'])
def test_default_batch_proves_every_png_and_numeric_position(media_context,fault):
    from image_helpers import write_png
    from video_ai.media.scene_upscale import extract_scene_frames,verify_scene_frame_pixels
    run,kwargs=media_context;source=make_video(media_context,frames=3)
    rows,_=extract_scene_frames(source,run/'batch',expected_frames=3,width=128,height=72,**kwargs)
    paths=[Path(r['path']) for r in rows];last=paths[-1]
    if fault=='last_crc':
        raw=bytearray(last.read_bytes());raw[-5]^=1;last.write_bytes(raw)
    elif fault=='wrong_size':write_png(last,64,72)
    elif fault=='reordered':last.write_bytes(paths[0].read_bytes())
    elif fault=='extra':(last.parent/'extra.png').write_bytes(paths[0].read_bytes())
    else:last.unlink()
    with pytest.raises((ValueError,OSError,RuntimeError)):
        verify_scene_frame_pixels(source,paths,expected_frames=3,width=128,height=72,config=kwargs['config'])


def test_batch_rejects_second_ihdr_before_decoding(media_context):
    from image_helpers import write_png
    from video_ai.media.scene_upscale import _check_png,InvalidScenePng
    path=media_context[0]/'duplicate-header.png';write_png(path,128,72)
    raw=path.read_bytes();path.write_bytes(raw[:33]+raw[8:33]+raw[33:])
    with pytest.raises(InvalidScenePng,match='IHDR'):_check_png(path,width=128,height=72)


def test_rgb_header_with_transparency_is_not_silently_converted_to_rgb24(media_context):
    import struct,zlib
    from image_helpers import write_png
    from video_ai.media.scene_upscale import _check_png,InvalidScenePng
    path=media_context[0]/'transparent-rgb.png';write_png(path,128,72)
    raw=path.read_bytes();kind=b'tRNS';data=b'\0'*6
    chunk=struct.pack('>I',6)+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    path.write_bytes(raw[:33]+chunk+raw[33:])
    with pytest.raises(InvalidScenePng,match='RGB24'):_check_png(path,width=128,height=72)


def test_twelve_frame_real_media_benchmark(media_context,monkeypatch):
    """Compare the previous extraction call chain with the aggregate checker."""
    import subprocess,time
    from video_ai.media.frames import extract_video_frames
    from video_ai.media.video import inspect_video
    from video_ai.media.scene_upscale import extract_scene_frames,_decode,verify_png
    from video_ai.runtime.manifest import hash_file
    run,kwargs=media_context;source=make_video(media_context,frames=12)
    popen=subprocess.Popen;commands=[]
    def count(*a,**kw):commands.append(a[0]);return popen(*a,**kw)
    monkeypatch.setattr(subprocess,'Popen',count)
    start=time.perf_counter()
    inspect_video(source,width=128,height=72,**kwargs)
    old,_=extract_video_frames(source,run/'previous',expected_frames=12,width=128,height=72,timeout=1200,**kwargs)
    raw=_decode(source,kwargs['config'],timeout=1200)
    for i in range(12):
        assert verify_png(run/'previous'/f'frame_{i+1:06d}.png',width=128,height=72,
            config=kwargs['config'])==raw[i*27648:(i+1)*27648]
    before=(time.perf_counter()-start,len(commands));commands.clear()
    start=time.perf_counter()
    current,_=extract_scene_frames(source,run/'current',expected_frames=12,width=128,height=72,**kwargs)
    after=(time.perf_counter()-start,len(commands))
    assert [r['identity']['sha256'] for r in old]==[r['sha256'] for r in current]
    assert before[1]==53 and after[1]==6
    print(f'\nNative 12x128x72 extraction: previous={before[0]:.4f}s/{before[1]} processes; current={after[0]:.4f}s/{after[1]} processes')


def test_concrete_transport_read_chunks_do_not_repeat_full_input_guard(monkeypatch):
    """Exercise the real transport state machine without sockets or a server."""
    import video_ai.adapters.scene_comfy as adapter
    body=b'x'*(2*1024*1024)
    class Socket:
        def settimeout(self,*a):pass
        def shutdown(self,*a):pass
    class Response:
        status=200
        def __init__(self):self.offset=0
        def read1(self,size):
            part=body[self.offset:self.offset+size];self.offset+=len(part);return part
        def getheader(self,name):return str(len(body))
        def getheaders(self):return [('Content-Type','application/json')]
    class Connection:
        def __init__(self,*a,**kw):self.sock=None
        def connect(self):self.sock=Socket()
        def send(self,data):pass
        def request(self,method,route,body=None,headers=None):
            self.send(b'GET /object_info HTTP/1.1\r\n\r\n')
            if body:self.send(body)
        def getresponse(self):return Response()
        def close(self):self.sock=None
    monkeypatch.setattr(adapter,'HTTPConnection',Connection)
    counts=[]
    for lightweight in (False,True):
        calls=[]
        client=adapter.SceneComfyClient('http://127.0.0.1:8188',request_timeout=1,
            ownership_check=lambda:calls.append(1),send_checks_only=lightweight)
        assert client.object_info(timeout=1)['body']==body
        counts.append(len(calls))
    assert counts[0]>32 and counts[1]==1
    print(f'\n2 MiB fake concrete GET full input guards: {counts[0]} -> {counts[1]}')


@pytest.mark.parametrize('closed',[False,True])
def test_copied_inspection_scope_cannot_reuse_after_close_or_in_foreign_thread(media_context,monkeypatch,closed):
    import video_ai.media.video as video
    from contextvars import copy_context
    from threading import Thread
    run,kwargs=media_context;source=make_video(media_context,frames=3)
    command=video._command;calls=[];failures=[]
    def count(*a,**kw):calls.append(1);return command(*a,**kw)
    monkeypatch.setattr(video,'_command',count)
    def inspect():
        try:video.inspect_video(source,width=128,height=72,**kwargs)
        except BaseException as exc:failures.append(exc)
    with video.inspection_reuse():
        inspect();copied=copy_context()
        if not closed:
            worker=Thread(target=lambda:copied.run(inspect));worker.start();worker.join()
    if closed:copied.run(inspect)
    assert not failures
    assert len(calls)==6


def test_png_batch_does_not_buffer_a_second_full_rgb_video(media_context,monkeypatch):
    import video_ai.media.scene_upscale as media
    run,kwargs=media_context;source=make_video(media_context,frames=3)
    execute=media.subprocess.run;sizes=[]
    def bounded(args,**kw):
        result=execute(args,**kw)
        if any('frame_%06d.png' in str(a) for a in args):sizes.append(len(result.stdout))
        return result
    monkeypatch.setattr(media.subprocess,'run',bounded)
    rows,_=media.extract_scene_frames(source,run/'batch',expected_frames=3,width=128,height=72,**kwargs)
    assert len(rows)==3 and len(sizes)==1
    assert sizes[0]<2048
