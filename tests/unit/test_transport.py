import json
import pytest
from http_helpers import Response, ScriptedTransport


def client_for(runtime_run, handler):
    from video_ai.adapters.common import HttpClient
    from video_ai.runtime.logging import RunLogger
    transport = ScriptedTransport(handler)
    return HttpClient('http://127.0.0.1:8188', 1, RunLogger(runtime_run[0]), transport=transport), transport


@pytest.mark.parametrize('status,body,kind', [(400, {'error':'bad graph'},'explicit'),(500,{'error':'crash'},'ambiguous'),(400,b'not json','ambiguous'),(302,{},'ambiguous')])
def test_post_error_classification_preserves_raw_body(runtime_run, status, body, kind):
    from video_ai.adapters.common import AdapterError
    client, transport = client_for(runtime_run, lambda r,t: Response(body,status))
    with pytest.raises(AdapterError) as caught:
        client.request('POST','/prompt',json_body={'prompt':{}},max_bytes=1024)
    assert caught.value.kind.value == kind
    assert len(transport.calls) == 1
    raw = body if isinstance(body,bytes) else json.dumps(body).encode()
    assert any(p.read_bytes() == raw for p in caught.value.evidence_paths)


@pytest.mark.parametrize('method,kind', [('GET','unavailable'),('POST','ambiguous')])
def test_disconnect_does_not_retry(runtime_run, method, kind):
    from video_ai.adapters.common import AdapterError
    def disconnect(r,t):
        raise ConnectionResetError('lost response')
    client, transport = client_for(runtime_run, disconnect)
    with pytest.raises(AdapterError) as caught:
        client.request(method,'/prompt',max_bytes=10)
    assert caught.value.kind.value == kind
    assert len(transport.calls) == 1
    assert any('lost response' in p.read_text(errors='replace') for p in caught.value.evidence_paths)


@pytest.mark.parametrize('body', [b'\xff',b'{bad',b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e999}'])
def test_strict_json_keeps_unparseable_body(runtime_run, body):
    from video_ai.adapters.common import AdapterError
    client, _ = client_for(runtime_run, lambda r,t:Response(body))
    with pytest.raises(AdapterError):
        client.get_json('/queue',max_bytes=100)
    assert any(p.read_bytes() == body for p in (runtime_run[0]/'logs/http').glob('*.body'))


def test_oversize_stream_is_truncated_and_never_parsed(runtime_run):
    from video_ai.adapters.common import AdapterError
    client, _ = client_for(runtime_run, lambda r,t:Response(b'x'*100))
    with pytest.raises(AdapterError) as caught:
        client.request('POST','/prompt',max_bytes=10)
    assert caught.value.kind.value == 'ambiguous'
    assert any(p.read_bytes() == b'x'*11 for p in caught.value.evidence_paths)


def test_partial_read_failure_preserves_bytes(runtime_run):
    from video_ai.adapters.common import AdapterError
    class Partial(Response):
        def read(self, size):
            if self.tell():
                raise TimeoutError('body timeout')
            return super().read(4)
    client, _ = client_for(runtime_run, lambda r,t:Partial(b'first chunk'))
    with pytest.raises(AdapterError) as caught:
        client.request('POST','/prompt',max_bytes=100)
    assert any(p.read_bytes() == b'firs' for p in caught.value.evidence_paths)


@pytest.mark.parametrize('path', ['http://other/prompt','//other/prompt','/../prompt','/prompt#fragment'])
def test_request_path_cannot_escape_base_origin(runtime_run, path):
    client, transport = client_for(runtime_run, lambda r,t:Response({}))
    with pytest.raises(ValueError):
        client.request('GET',path,max_bytes=100)
    assert not transport.calls


def test_redirect_final_origin_and_media_type_rejected(runtime_run):
    from video_ai.adapters.common import AdapterError
    client, _ = client_for(runtime_run, lambda r,t:Response({},url='http://other:80/queue'))
    with pytest.raises(AdapterError):
        client.get_json('/queue',max_bytes=100)
    client, _ = client_for(runtime_run, lambda r,t:Response({},headers={'Content-Type':'text/html'}))
    with pytest.raises(AdapterError):
        client.get_json('/queue',max_bytes=100)


def test_transport_receives_payload_and_remaining_timeout(runtime_run):
    client, transport = client_for(runtime_run, lambda r,t:Response({'ok':True}))
    response = client.request('POST','/prompt',json_body={'client_id':'abc'},max_bytes=100,timeout=.25,stage='source_clips',unit_id='shot_0001')
    assert response.status == 200
    assert json.loads(transport.calls[0][2]) == {'client_id':'abc'}
    assert transport.calls[0][3] <= .25
    assert response.evidence_path.exists()


def test_incomplete_read_exception_keeps_its_partial_bytes(runtime_run):
    from http.client import IncompleteRead
    from video_ai.adapters.common import AdapterError
    class Truncated(Response):
        def read(self,size):
            raise IncompleteRead(b'partial acceptance',100)
    client,_=client_for(runtime_run,lambda r,t:Truncated())
    with pytest.raises(AdapterError) as caught:
        client.request('POST','/prompt',max_bytes=100)
    assert any(p.read_bytes()==b'partial acceptance' for p in caught.value.evidence_paths)
