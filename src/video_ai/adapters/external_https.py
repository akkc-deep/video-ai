"""Finite external HTTPS, without raw request/response logging or POST replay."""
from dataclasses import dataclass, field
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
    def __init__(self, host, *, request_guard=None, **kwargs):
        self.request_guard = request_guard or (lambda: None)
        super().__init__(host, **kwargs)

    def connect(self):
        super().connect()
        self.request_guard()  # DNS/TLS may have outlived ownership or cancellation.

    def send(self, data):
        self.request_guard()
        # HTTPConnection.send connects lazily; the second guard in connect()
        # must pass before its first socket.sendall can transmit headers/body.
        return super().send(data)


class _HTTPSHandler(HTTPSHandler):
    def https_open(self, request):
        connections = []
        def factory(host, **kwargs):
            connection = _DeadlineHTTPSConnection(host, request_guard=getattr(request, '_request_guard', None), **kwargs)
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
    headers: dict = field(default_factory=dict)


class ExternalHttpsClient:
    def __init__(self, *, transport=None):
        opener = build_opener(ProxyHandler({}), _Redirects(), _HTTPSHandler())
        self.transport = transport or opener.open

    def request(self, method, url, *, body=None, headers=None, timeout=60, max_bytes=32*1024*1024,
                allow_not_found=False, ownership_check=None, strict_url=False):
        validate_https_url(url)
        if method not in ('GET', 'POST', 'PUT', 'HEAD'): raise ValueError('unsupported HTTPS method')
        if allow_not_found and method != 'HEAD': raise ValueError('only HEAD permits controlled not found')
        if method == 'HEAD' and body is not None: raise ValueError('HEAD cannot have request body')
        budget = positive_timeout(timeout)
        if type(max_bytes) is not int or max_bytes < 1: raise ValueError('positive byte limit required')
        request = Request(url, data=body, headers=headers or {}, method=method)
        # Socket timeouts cannot bound DNS resolution. The caller always regains
        # control at the total deadline, even if the OS resolver is still blocked.
        # A late connection checks its own expired deadline before sending HTTP.
        end = time.monotonic()+budget
        cancelled = Event()
        def guard():
            if cancelled.is_set() or time.monotonic() >= end: raise TimeoutError()
            if ownership_check is not None: ownership_check()
            if cancelled.is_set() or time.monotonic() >= end: raise TimeoutError()
        request._request_guard = guard
        request._strict_url = strict_url
        result = Queue(maxsize=1)
        def perform():
            try:
                result.put((self._perform(request, method, url, end, max_bytes, cancelled, allow_not_found), None))
            except BaseException as exc:
                result.put((None, exc))
        Thread(target=perform, name='video-ai-https', daemon=True).start()
        try:
            response, error = result.get(timeout=max(.000001, end-time.monotonic()))
        except Empty:
            cancelled.set()
            raise AdapterError(FailureKind.unavailable if method in ('GET', 'HEAD') else FailureKind.ambiguous,
                               'external HTTPS total deadline expired; no automatic retry') from None
        except BaseException:
            cancelled.set()
            raise
        if error is not None: raise error
        return response

    def _perform(self, request, method, url, end, max_bytes, cancelled, allow_not_found=False):
        response = None
        try:
            request._request_guard()
            try: response = self.transport(request, timeout=end-time.monotonic())
            except HTTPError as exc: response = exc
            status = response.status if hasattr(response, 'status') else response.code
            final = response.geturl() or url
            # No redirects are followed, including signed downloads.
            if (urlsplit(final).hostname != urlsplit(url).hostname
                    or (request._strict_url and final != url)): raise ValueError('redirect refused')
            chunks = []; size = 0
            while method != 'HEAD':
                request._request_guard()
                chunk = getattr(response, 'read1', response.read)(min(65536, max_bytes+1-size))
                if not chunk: break
                chunks.append(chunk); size += len(chunk)
                if size > max_bytes: raise ValueError('byte budget exceeded')
            length = response.headers.get('Content-Length')
            if method != 'HEAD' and length is not None and int(length) != size: raise ValueError('incomplete response')
            request._request_guard()
            if type(status) is not int or not (200 <= status < 300 or (allow_not_found and status == 404)):
                raise AdapterError(FailureKind.unavailable if method in ('GET', 'HEAD') else FailureKind.ambiguous,
                                   f'external HTTPS status {status}')
            return ExternalResponse(status, b''.join(chunks), dict(response.headers.items()))
        except AdapterError:
            raise
        except Exception:
            raise AdapterError(FailureKind.unavailable if method in ('GET', 'HEAD') else FailureKind.ambiguous,
                               'external HTTPS request failed; sensitive transport details withheld') from None
        finally:
            if response is not None:
                connection = getattr(response, '_deadline_connection', None)
                if connection is not None: connection.timer.cancel(); connection.expire()
                try: response.close()
                except Exception: pass
