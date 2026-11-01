"""Finite, memory-only loopback HTTP for independent scene transactions.

The optional transport has ``request(method, route, *, body, timeout,
ownership_check)``. It must obey the same no-replay and send-guard contract.
No transport thread may persist evidence or log events.
"""
from http.client import HTTPConnection
from contextvars import copy_context
import json
from queue import Queue, Empty
import socket
from threading import Event, Thread
import time
from urllib.parse import urlsplit
from uuid import UUID

from .common import JSON_LIMIT, positive_timeout, validate_base_url


def prompt_payload(graph, client_id):
    if not isinstance(graph, dict): raise ValueError('graph must be object')
    if not isinstance(client_id, str) or str(UUID(client_id)) != client_id:
        raise ValueError('client_id must be canonical UUID')
    body = json.dumps(dict(prompt=graph, client_id=client_id), ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(body) > JSON_LIMIT: raise ValueError('JSON request exceeds 32MiB')
    return body


class SceneComfyClient:
    def __init__(self, base_url, *, request_timeout, ownership_check, http=None, send_checks_only=False):
        self.base_url = validate_base_url(base_url)
        self.request_timeout = positive_timeout(request_timeout)
        if not callable(ownership_check): raise ValueError('ownership_check must be callable')
        if type(send_checks_only) is not bool: raise ValueError('send_checks_only must be bool')
        if send_checks_only and http is not None: raise ValueError('send checks require concrete HTTP transport')
        self.send_checks_only = send_checks_only
        self.ownership_check = ownership_check
        self.http = http

    def object_info(self, *, timeout): return self._request('GET', '/object_info', timeout=timeout)
    def system_stats(self, *, timeout): return self._request('GET', '/system_stats', timeout=timeout)
    def queue(self, *, timeout): return self._request('GET', '/queue', timeout=timeout)
    def history(self, prompt_id=None, *, timeout):
        if prompt_id is not None and (not isinstance(prompt_id, str) or str(UUID(prompt_id)) != prompt_id):
            raise ValueError('prompt_id must be canonical UUID')
        return self._request('GET', '/history' + ('/' + prompt_id if prompt_id else ''), timeout=timeout)
    def submit(self, graph, *, client_id, timeout):
        return self._request('POST', '/prompt', body=prompt_payload(graph, client_id), timeout=timeout)

    def _request(self, method, route, *, timeout, body=None):
        budget = min(self.request_timeout, positive_timeout(timeout)); end = time.monotonic() + budget
        cancelled = Event(); result = Queue(maxsize=1); connections = []
        def deadline():
            if cancelled.is_set() or time.monotonic() >= end: raise TimeoutError('scene HTTP deadline exceeded')
        def guard():
            deadline()
            self.ownership_check()
            deadline()
        # Explicit whole-scene media writers recheck before persisting any raw
        # evidence. Their concrete transport still runs the complete proof at
        # EVERY socket write; waiting/reading only needs cancellation/deadlines.
        # A returned memory response is not a media acceptance or write permit.
        phase_guard = deadline if self.send_checks_only else guard
        def close():
            for connection in connections:
                sock = connection.sock
                if sock is not None:
                    try: sock.shutdown(socket.SHUT_RDWR)
                    except OSError: pass
                connection.close()
        class Connection(HTTPConnection):
            def connect(self):
                phase_guard(); super().connect()
                try: phase_guard()
                except BaseException:
                    self.close(); raise
            def send(self, data):
                phase_guard()
                if self.sock is None: self.connect()
                guard()
                self.sock.settimeout(max(.001, end-time.monotonic()))
                super().send(data)
        def work():
            try:
                phase_guard()
                if self.http is not None:
                    value = self.http.request(method, route, body=body, timeout=budget, ownership_check=guard)
                else:
                    parts = urlsplit(self.base_url)
                    connection = Connection(parts.hostname, parts.port, timeout=budget); connections.append(connection)
                    connection.request(method, route, body=body, headers={'Accept':'application/json', **({'Content-Type':'application/json'} if body is not None else {})})
                    response = connection.getresponse(); chunks=[]; size=0
                    while True:
                        phase_guard()
                        if connection.sock is not None: connection.sock.settimeout(max(.001,end-time.monotonic()))
                        chunk = response.read1(min(65536, JSON_LIMIT+1-size))
                        if not chunk: break
                        chunks.append(chunk); size += len(chunk)
                        if size > JSON_LIMIT: raise ValueError('scene HTTP response exceeds 32MiB')
                    raw=b''.join(chunks)
                    length=response.getheader('Content-Length')
                    if length is not None and int(length)!=len(raw): raise ValueError('incomplete HTTP response')
                    value=dict(status=response.status, headers=dict(response.getheaders()), body=raw)
                phase_guard()
                if (not isinstance(value,dict) or set(value)!={'status','headers','body'} or type(value['status']) is not int
                    or not 100<=value['status']<=599 or not isinstance(value['headers'],dict) or not isinstance(value['body'],bytes)
                    or len(value['body'])>JSON_LIMIT): raise ValueError('invalid scene HTTP response')
                result.put((True,value))
            except BaseException as exc: result.put((False,exc))
            finally: close()
        phase_guard(); context=copy_context()
        thread=Thread(target=context.run,args=(work,),daemon=True,name='scene-comfy-io');thread.start()
        try:
            try: ok,value=result.get(timeout=max(.001,end-time.monotonic()))
            except Empty as exc: raise TimeoutError('scene HTTP deadline exceeded') from exc
            phase_guard()
            if not ok: raise value
            return value
        finally:
            cancelled.set(); close()
