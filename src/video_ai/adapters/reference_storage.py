"""Content-addressed private TOS originals and in-memory TOS4 GET URLs."""
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
from pathlib import Path
from queue import Queue, Empty
import re
from threading import Event, Lock, Thread
import time
from urllib.parse import quote, urlencode

from .common import AdapterError, FailureKind, positive_timeout
from .external_https import ExternalHttpsClient


def _safe_path(value):
    return (isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_./-]+', value) is not None
            and all(p and p not in ('.', '..') for p in value.split('/')))


def _stamp(value):
    return value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _signature(canonical, date, region, secret):
    key = secret.encode('utf-8')
    for part in (date[:8], region, 'tos', 'request'):
        key = hmac.new(key, part.encode('utf-8'), hashlib.sha256).digest()
    scope = f'{date[:8]}/{region}/tos/request'
    message = f'TOS4-HMAC-SHA256\n{date}\n{scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}'
    return hmac.new(key, message.encode(), hashlib.sha256).hexdigest()


class ReferenceStorage:
    def __init__(self, settings, *, http=None, clock=None, ownership_check=None):
        self.settings = asdict(settings) if is_dataclass(settings) else dict(settings)
        s = self.settings
        if (s.get('provider') != 'volcengine_tos'
                or not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]', s.get('bucket', ''))
                or not re.fullmatch(r'[a-z0-9-]+', s.get('region', ''))
                or s.get('endpoint') != f'https://tos-{s["region"]}.volces.com'
                or not _safe_path(s.get('key_prefix', ''))):
            raise ValueError('invalid TOS storage settings')
        self.timeout = positive_timeout(s['request_timeout_seconds'])
        self.http = http or ExternalHttpsClient()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.ownership_check = ownership_check or (lambda: None)

    def _credentials(self):
        s = self.settings
        access, secret = os.environ.get(s['access_key_env']), os.environ.get(s['secret_key_env'])
        if (not access or not secret or any(ord(c) <= 32 for c in access)
                or '\r' in secret or '\n' in secret):
            raise AdapterError(FailureKind.explicit, 'TOS credentials unavailable')
        return access, secret

    def check_credentials(self):
        """Validate environment credentials without returning or persisting them."""
        self._credentials()

    def _object(self, original, run_id):
        s = self.settings
        if (not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', run_id)
                or not re.fullmatch(r'[a-f0-9]{64}', original.get('sha256', ''))
                or type(original.get('bytes')) is not int or original['bytes'] <= 0
                or original.get('format') not in ('png', 'jpeg', 'webp')):
            raise AdapterError(FailureKind.explicit, 'invalid TOS original identity')
        return dict(bucket=s['bucket'], region=s['region'], endpoint=s['endpoint'],
                    key=f'{s["key_prefix"]}/{run_id}/{original["sha256"]}.original',
                    bytes=original['bytes'], sha256=original['sha256'],
                    content_type='image/'+original['format'])

    def _headers(self, method, record, access, secret):
        date = self.clock().astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        headers = {'host': f'{record["bucket"]}.tos-{record["region"]}.volces.com',
                   'x-tos-date': date,
                   'x-tos-content-sha256': record['sha256'] if method == 'PUT' else 'UNSIGNED-PAYLOAD'}
        if method == 'PUT':
            headers.update({'content-type': record['content_type'], 'x-tos-meta-sha256': record['sha256']})
        names = ';'.join(sorted(headers))
        canonical_headers = ''.join(f'{k}:{headers[k]}\n' for k in sorted(headers))
        canonical = f'{method}\n/{record["key"]}\n\n{canonical_headers}\n{names}\n{headers["x-tos-content-sha256"]}'
        signature = _signature(canonical, date, record['region'], secret)
        headers['Authorization'] = (f'TOS4-HMAC-SHA256 Credential={access}/{date[:8]}/{record["region"]}/tos/request, '
                                    f'SignedHeaders={names}, Signature={signature}')
        return headers

    def ensure_original(self, original, *, run_id, before_put):
        """Verify/recover one object; authorize logical intent on the caller thread.

        before_put() is called once, with no arguments, for both verified reuse
        and missing-object upload. It must commit the caller's public logical
        intent. No receipt or local file is written by this adapter.
        """
        record = self._object(original, run_id)
        access, secret = self._credentials()
        try:
            data = Path(original['path']).read_bytes()
        except (OSError, TypeError, KeyError):
            raise AdapterError(FailureKind.explicit, 'TOS original unavailable') from None
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise AdapterError(FailureKind.explicit, 'TOS original identity mismatch')
        end = time.monotonic() + self.timeout
        cancelled, permit = Event(), Event()
        transitions, results = Lock(), Queue()
        authorized, put_attempted = False, False

        def remaining():
            if cancelled.is_set() or time.monotonic() >= end: raise TimeoutError()
            return end - time.monotonic()

        def guard():
            remaining()
            self.ownership_check()
            remaining()

        def request(method):
            nonlocal put_attempted
            guard()
            if method == 'PUT':
                with transitions:
                    guard()
                    if not authorized: raise TimeoutError()
                    put_attempted = True
            url = f'https://{record["bucket"]}.tos-{record["region"]}.volces.com/{record["key"]}'
            response = self.http.request(method, url, body=data if method == 'PUT' else None,
                         headers=self._headers(method, record, access, secret), timeout=remaining(),
                         max_bytes=record['bytes'] if method == 'GET' else 1024*1024,
                         allow_not_found=method == 'HEAD', ownership_check=guard, strict_url=True)
            guard()
            return response

        def verify(head):
            headers = {k.lower(): v for k, v in head.headers.items()}
            if (head.status != 200 or headers.get('x-tos-meta-sha256') != record['sha256']
                    or headers.get('content-length') != str(record['bytes'])
                    or headers.get('content-type') != record['content_type']
                    or not isinstance(headers.get('etag'), str) or not headers['etag'].strip()):
                raise AdapterError(FailureKind.invalid_result, 'TOS object metadata conflict')
            downloaded = request('GET')
            if (len(downloaded.body) != record['bytes']
                    or hashlib.sha256(downloaded.body).hexdigest() != record['sha256']):
                raise AdapterError(FailureKind.invalid_result, 'TOS object byte identity conflict')
            return dict(record, etag=headers['etag'])

        def authorize():
            guard()
            results.put(('ready', None))
            if not permit.wait(remaining()): raise TimeoutError()
            with transitions:
                guard()
                if not authorized: raise TimeoutError()

        def worker():
            try:
                head = request('HEAD')
                if head.status == 404:
                    authorize()
                    request('PUT')
                    receipt = verify(request('HEAD'))
                else:
                    receipt = verify(head)
                    authorize()
                guard()
                results.put(('done', receipt))
            except BaseException as error:
                results.put(('error', error))

        Thread(target=worker, name='video-ai-tos', daemon=True).start()
        try:
            while True:
                stage, value = results.get(timeout=remaining())
                if stage == 'ready':
                    guard()
                    before_put()
                    with transitions:
                        guard()
                        authorized = True
                    permit.set()
                elif stage == 'done':
                    guard()
                    return value
                else:
                    if isinstance(value, AdapterError): raise value
                    raise AdapterError(FailureKind.ambiguous if put_attempted else FailureKind.unavailable,
                                       'TOS operation failed; sensitive details withheld') from None
        except AdapterError:
            raise
        except (Exception, Empty):
            raise AdapterError(FailureKind.ambiguous if put_attempted else FailureKind.unavailable,
                               'TOS operation cancelled or deadline expired; no automatic retry') from None
        finally:
            with transitions:
                cancelled.set()
            permit.set()

    def presign_get(self, object_record, *, expires_seconds):
        if type(expires_seconds) is not int or not 1 <= expires_seconds <= 604800:
            raise ValueError('invalid TOS URL expiry')
        s = self.settings
        if (any(object_record.get(k) != s[k] for k in ('bucket', 'region', 'endpoint'))
                or not _safe_path(object_record.get('key', ''))
                or not object_record['key'].startswith(s['key_prefix']+'/')):
            raise AdapterError(FailureKind.explicit, 'TOS object identity mismatch')
        access, secret = self._credentials()
        issued = self.clock()
        date = issued.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        scope = f'{date[:8]}/{s["region"]}/tos/request'
        host = f'{s["bucket"]}.tos-{s["region"]}.volces.com'
        path = '/' + quote(object_record['key'], safe='/~')
        query = urlencode(sorted(dict(**{'X-Tos-Algorithm': 'TOS4-HMAC-SHA256',
                        'X-Tos-Credential': f'{access}/{scope}', 'X-Tos-Date': date,
                        'X-Tos-Expires': str(expires_seconds), 'X-Tos-SignedHeaders': 'host'}).items()),
                          quote_via=quote, safe='~')
        canonical = f'GET\n{path}\n{query}\nhost:{host}\n\nhost\nUNSIGNED-PAYLOAD'
        signature = _signature(canonical, date, s['region'], secret)
        return dict(url=f'https://{host}{path}?{query}&X-Tos-Signature={signature}',
                    issued_at=_stamp(issued), expires_at=_stamp(issued+timedelta(seconds=expires_seconds)))
