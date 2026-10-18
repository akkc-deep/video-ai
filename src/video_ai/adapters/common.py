"""Local finite HTTP requests, raw evidence, and conservative failure classes."""
from dataclasses import dataclass
from enum import Enum
from http.client import IncompleteRead, HTTPConnection
import json
import math
from pathlib import Path
import time
import socket
from threading import Timer
from typing import Mapping
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler, HTTPHandler
from uuid import uuid4

from ..runtime.manifest import now

JSON_LIMIT = 32 * 1024 * 1024


class FailureKind(str, Enum):
    explicit = 'explicit'
    ambiguous = 'ambiguous'
    invalid_result = 'invalid_result'
    unavailable = 'unavailable'


class AdapterError(RuntimeError):
    def __init__(self, kind, message, evidence_paths=()):
        super().__init__(message)
        self.kind = FailureKind(kind)
        self.evidence_paths = tuple(Path(p) for p in evidence_paths)


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    evidence_path: Path


def positive_timeout(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError('timeout must be finite and positive')
    return float(value)


def origin(url):
    parts = urlsplit(url)
    return parts.scheme, parts.hostname, parts.port


def validate_base_url(url):
    parts = urlsplit(url)
    if (url != url.strip() or any(ord(c) <= 32 for c in url) or parts.scheme != 'http'
            or parts.hostname not in {'localhost', '127.0.0.1', '::1'}
            or parts.port is None or not 0 < parts.port < 65536 or parts.username is not None
            or parts.password is not None or parts.path not in ('', '/') or parts.query or parts.fragment):
        raise ValueError('expected local HTTP origin without credentials')
    return url.rstrip('/')


def strict_json(body):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError('non-finite JSON number')
        return parsed
    def constant(value):
        raise ValueError('non-finite JSON number')
    data = json.loads(body.decode('utf-8'), object_pairs_hook=pairs, parse_float=number, parse_constant=constant)
    if not isinstance(data, (dict, list)):
        raise ValueError('expected JSON object or list')
    return data


class _Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # No redirect can extend the deadline or cause an implicit POST replay.
        raise HTTPError(req.full_url, code, 'redirect refused', headers, fp)


class _DeadlineConnection(HTTPConnection):
    """Interrupt header parsing as well as body reads at the total deadline."""
    def __init__(self, host, **kwargs):
        super().__init__(host,**kwargs)
        self.end=time.monotonic()+self.timeout
        self._deadline_socket=None
        self.timer=Timer(self.timeout,self.expire)
        self.timer.daemon=True
        self.timer.start()

    def connect(self):
        super().connect()
        self._deadline_socket=self.sock
        if time.monotonic()>=self.end:
            self.expire()
            raise TimeoutError('HTTP connection deadline exceeded')

    def expire(self):
        sock=self._deadline_socket or self.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()


class _DeadlineHandler(HTTPHandler):
    def http_open(self,request):
        connections=[]
        def factory(host,**kwargs):
            connection=_DeadlineConnection(host,**kwargs)
            connections.append(connection)
            return connection
        try:
            response=self.do_open(factory,request)
        except BaseException:
            for connection in connections:
                connection.timer.cancel()
                connection.expire()
            raise
        response._deadline_connection=connections[0]
        return response


class HttpClient:
    def __init__(self, base_url, timeout, logger, *, transport=None):
        self.base_url = validate_base_url(base_url)
        self.timeout = positive_timeout(timeout)
        self.logger = logger
        self._opener = build_opener(ProxyHandler({}), _Redirects(), _DeadlineHandler())
        self.transport = transport or self._opener.open

    def request(self, method, path, *, json_body=None, max_bytes=JSON_LIMIT,
                timeout=None, stage=None, unit_id=None):
        method = method.upper()
        parts = urlsplit(path)
        if (method not in {'GET', 'POST'} or not path.startswith('/') or path.startswith('//')
                or parts.scheme or parts.netloc or parts.fragment or '\\' in path
                or '..' in unquote(parts.path).split('/') or any(ord(c) <= 32 for c in path)):
            raise ValueError('invalid method or request path')
        if type(max_bytes) is not int or max_bytes < 1:
            raise ValueError('max_bytes must be positive integer')
        budget = min(self.timeout, positive_timeout(timeout)) if timeout is not None else self.timeout
        body = None if json_body is None else json.dumps(json_body, allow_nan=False, ensure_ascii=False).encode('utf-8')
        if body is not None and len(body) > JSON_LIMIT:
            raise ValueError('JSON request exceeds 32MiB')
        headers = {'Accept':'application/json'}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        url = self.base_url + path
        request = Request(url, data=body, headers=headers, method=method)
        token = uuid4().hex
        request_path = self.logger.save_json(f'http/{token}.request.json',
                                             dict(method=method, url=url, headers=headers, json_body=json_body,
                                                  timeout=budget, stage=stage, unit_id=unit_id, started_at=now()))
        evidence = [request_path]
        response, status, response_headers, chunks, error, truncated = None, None, {}, [], None, False
        end = time.monotonic() + budget
        try:
            try:
                response = self.transport(request, timeout=budget)
            except HTTPError as exc:
                response = exc
            status = response.status if hasattr(response, 'status') else response.code
            response_headers = dict(response.headers.items())
            final_url = response.geturl() or url
            if origin(final_url) != origin(self.base_url):
                raise ValueError('redirect left configured origin')
            size = 0
            while True:
                if time.monotonic() >= end:
                    raise TimeoutError('HTTP response deadline exceeded')
                remaining = end - time.monotonic()
                stream = getattr(response, 'fp', None)
                if hasattr(stream, 'fp'):
                    stream = stream.fp
                sock = getattr(getattr(stream, 'raw', None), '_sock', None)
                if sock is not None:
                    sock.settimeout(remaining)
                read = getattr(response, 'read1', response.read)
                try:
                    chunk = read(min(65536, max_bytes + 1 - size))
                except IncompleteRead as exc:
                    partial = exc.partial[:max_bytes + 1 - size]
                    chunks.append(partial)
                    truncated = True
                    raise
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > max_bytes:
                    truncated = True
                    raise ValueError('response exceeds byte budget; truncated')
            content_length = next((v for k,v in response_headers.items() if k.lower() == 'content-length'), None)
            if content_length is not None and int(content_length) != size:
                raise ValueError('incomplete response Content-Length')
        except Exception as exc:
            error = exc
        finally:
            if response is not None:
                connection=getattr(response,'_deadline_connection',None) or getattr(getattr(response,'fp',None),'_deadline_connection',None)
                if connection is not None:
                    connection.timer.cancel()
                try:
                    response.close()
                except Exception as close_error:
                    error = error or close_error
        raw = b''.join(chunks)
        raw_path = self.logger.save_bytes(f'http/{token}.body', raw)
        evidence.append(raw_path)
        metadata = dict(method=method, url=url, stage=stage, unit_id=unit_id, status=status,
                        headers=response_headers, bytes=len(raw), truncated=truncated,
                        finished_at=now(), error=str(error) if error else None)
        metadata_path = self.logger.save_json(f'http/{token}.response.json', metadata)
        evidence.append(metadata_path)
        self.logger.event(stage, unit_id, 'http_response', dict(metadata, evidence_paths=[str(p) for p in evidence]))
        if error:
            evidence.append(self.logger.exception(stage, unit_id, error))
            raise AdapterError(FailureKind.unavailable if method == 'GET' else FailureKind.ambiguous,
                               str(error), evidence) from error
        if type(status) is not int or not 200 <= status < 300:
            kind = FailureKind.unavailable if method == 'GET' else FailureKind.ambiguous
            if method == 'POST' and type(status) is int and 400 <= status < 500:
                try:
                    strict_json(raw)
                except (ValueError, UnicodeError):
                    pass
                else:
                    kind = FailureKind.explicit
            raise AdapterError(kind, f'HTTP {status}', evidence)
        return HttpResponse(status, response_headers, raw, raw_path)

    def parse_json(self, response, *, method='GET', stage=None, unit_id=None):
        try:
            media = next((v for k,v in response.headers.items() if k.lower() == 'content-type'), '').split(';')[0].strip().lower()
            if media != 'application/json' and not media.endswith('+json'):
                raise ValueError('unexpected JSON media type')
            return strict_json(response.body)
        except (ValueError, UnicodeError) as exc:
            trace = self.logger.exception(stage, unit_id, exc)
            raise AdapterError(FailureKind.unavailable if method == 'GET' else FailureKind.ambiguous,
                               str(exc), (response.evidence_path, trace)) from exc

    def get_json(self, path, *, max_bytes=JSON_LIMIT, timeout=None, stage=None, unit_id=None):
        if max_bytes > JSON_LIMIT:
            raise ValueError('JSON responses limited to 32MiB')
        response = self.request('GET', path, max_bytes=max_bytes, timeout=timeout, stage=stage, unit_id=unit_id)
        return self.parse_json(response, stage=stage, unit_id=unit_id)
