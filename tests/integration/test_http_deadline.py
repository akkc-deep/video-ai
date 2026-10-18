import socket
import threading
import time
import pytest


def test_dripping_response_headers_cannot_extend_absolute_deadline(runtime_run):
    from video_ai.adapters.common import HttpClient,AdapterError
    from video_ai.runtime.logging import RunLogger
    listener=socket.socket()
    listener.bind(('127.0.0.1',0))
    listener.listen(1)
    listener.settimeout(2)
    port=listener.getsockname()[1]
    stopped=threading.Event()
    def serve():
        try:
            connection,_=listener.accept()
            with connection:
                connection.recv(4096)
                for char in b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}':
                    if stopped.wait(.015):break
                    connection.send(bytes([char]))
        except OSError:
            pass
    thread=threading.Thread(target=serve,daemon=True)
    thread.start()
    started=time.monotonic()
    try:
        client=HttpClient(f'http://127.0.0.1:{port}',.12,RunLogger(runtime_run[0]))
        with pytest.raises(AdapterError):client.get_json('/queue',max_bytes=100)
        assert time.monotonic()-started<.5
    finally:
        stopped.set()
        listener.close()
        thread.join(timeout=2)
