"""Finite external HTTPS, without raw request/response logging or POST replay."""
from dataclasses import dataclass
from http.client import HTTPSConnection
import ipaddress
from queue import Queue, Empty
from threading import Thread, Event
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPSHandler

from .common import AdapterError, FailureKind, positive_timeout, _Redirects, _DeadlineConnection


def validate_https_url(url):
    try:
        parts = urlsplit(url)
        good = (isinstance(url, str) and url == url.strip() and not any(ord(c) <= 32 for c in url)
                and '\\' not in url and parts.scheme == 'https' and parts.hostname
                and parts.username is None and parts.password is None and not parts.fragment
                and parts.port in (None, 443) and parts.hostname != 'localhost'
                and not parts.hostname.endswith(('.localhost', '.local')))
        if good:
            try: good = ipaddress.ip_address(parts.hostname).is_global
            except ValueError: good = '.' in parts.hostname
        if not good: raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('expected public HTTPS URL without credentials or fragment') from None
    return url


class _DeadlineHTTPSConnection(_DeadlineConnection, HTTPSConnection):
    pass


class _HTTPSHandler(HTTPSHandler):
    def https_open(self, request):
        connections = []
        def factory(host, **kwargs):
            connection = _DeadlineHTTPSConnection(host, **kwargs)
            connections.append(connection)
            return connection
        try:
            response = self.do_open(factory, request, context=self._context)
        except BaseException:
            for connection in connections:
                connection.timer.cancel(); connection.expire()
            raise
        response._deadline_connection = connections[0]
        return response


@dataclass(frozen=True)
class ExternalResponse:
    status: int
    body: bytes


class ExternalHttpsClient:
    def __init__(self, *, transport=None):
        opener = build_opener(ProxyHandler({}), _Redirects(), _HTTPSHandler())
        self.transport = transport or opener.open

    def request(self, method, url, *, body=None, headers=None, timeout=60, max_bytes=32*1024*1024):
        validate_https_url(url)
        if method not in ('GET', 'POST'): raise ValueError('unsupported HTTPS method')
        budget = positive_timeout(timeout)
        if type(max_bytes) is not int or max_bytes < 1: raise ValueError('positive byte limit required')
        request = Request(url, data=body, headers=headers or {}, method=method)
        # Socket timeouts cannot bound DNS resolution. The caller always regains
        # control at the total deadline, even if the OS resolver is still blocked.
        # A late connection checks its own expired deadline before sending HTTP.
        end = time.monotonic()+budget
        cancelled = Event()
        result = Queue(maxsize=1)
        def perform():
            try:
                result.put((self._perform(request, method, url, end, max_bytes, cancelled), None))
            except BaseException as exc:
                result.put((None, exc))
        Thread(target=perform, name='video-ai-https', daemon=True).start()
        try:
            response, error = result.get(timeout=max(.000001, end-time.monotonic()))
        except Empty:
            cancelled.set()
            raise AdapterError(FailureKind.unavailable if method == 'GET' else FailureKind.ambiguous,
                               'external HTTPS total deadline expired; no automatic retry') from None
        if error is not None: raise error
        return response

    def _perform(self, request, method, url, end, max_bytes, cancelled):
        response = None
        try:
            if cancelled.is_set() or time.monotonic() >= end: raise TimeoutError()
            try: response = self.transport(request, timeout=end-time.monotonic())
            except HTTPError as exc: response = exc
            status = response.status if hasattr(response, 'status') else response.code
            final = response.geturl() or url
            # No redirects are followed, including signed downloads.
            if urlsplit(final).hostname != urlsplit(url).hostname: raise ValueError('redirect refused')
            chunks = []; size = 0
            while True:
                if cancelled.is_set() or time.monotonic() >= end: raise TimeoutError()
                chunk = getattr(response, 'read1', response.read)(min(65536, max_bytes+1-size))
                if not chunk: break
                chunks.append(chunk); size += len(chunk)
                if size > max_bytes: raise ValueError('byte budget exceeded')
            length = response.headers.get('Content-Length')
            if length is not None and int(length) != size: raise ValueError('incomplete response')
            if type(status) is not int or not 200 <= status < 300:
                raise AdapterError(FailureKind.unavailable if method == 'GET' else FailureKind.ambiguous,
                                   f'external HTTPS status {status}')
            return ExternalResponse(status, b''.join(chunks))
        except AdapterError:
            raise
        except Exception:
            raise AdapterError(FailureKind.unavailable if method == 'GET' else FailureKind.ambiguous,
                               'external HTTPS request failed; sensitive transport details withheld') from None
        finally:
            if response is not None:
                connection = getattr(response, '_deadline_connection', None)
                if connection is not None: connection.timer.cancel(); connection.expire()
                try: response.close()
                except Exception: pass
