"""Finite in-memory HTTP streams with the same boundary as urllib responses."""
from io import BytesIO
import json


class Response(BytesIO):
    def __init__(self, body=b'{}', status=200, headers=None, url=None):
        super().__init__(body if isinstance(body, bytes) else json.dumps(body).encode('utf-8'))
        self.status = status
        self.headers = headers or {'Content-Type':'application/json'}
        self.url = url

    def geturl(self):
        return self.url

    def read1(self,size):
        return self.read(size)


class ScriptedTransport:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append((request.method, request.full_url, request.data, timeout))
        return self.handler(request, timeout)
