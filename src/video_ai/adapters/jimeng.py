"""Volcengine CV asynchronous image protocol and AK/SK signature v4."""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import re
from urllib.parse import urlencode

from .common import AdapterError, FailureKind, strict_json
from .external_https import ExternalHttpsClient, validate_https_url
from ..runtime.manifest import thaw

HOST = 'visual.volcengineapi.com'
VERSION = '2022-08-31'
SUBMIT = 'CVSync2AsyncSubmitTask'
QUERY = 'CVSync2AsyncGetResult'
STATES = {'in_queue', 'generating', 'done', 'expired', 'not_found', 'failed'}
SENSITIVE = {'authorization', 'access_key', 'secret_key', 'token', 'security_token',
             'signature', 'ak', 'sk', 'binary_data_base64', 'image_base64'}


def encode_body(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'), sort_keys=True).encode('utf-8')


def sign_request(body, action, access_key, secret_key, timestamp=None):
    if action not in (SUBMIT, QUERY): raise ValueError('unsupported official action')
    date = timestamp or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    if not re.fullmatch(r'\d{8}T\d{6}Z', date): raise ValueError('invalid signing date')
    digest = hashlib.sha256(body).hexdigest()
    names = 'content-type;host;x-content-sha256;x-date'
    query = urlencode(sorted(dict(Action=action, Version=VERSION).items()))
    canonical_headers = f'content-type:application/json\nhost:{HOST}\nx-content-sha256:{digest}\nx-date:{date}\n'
    canonical = '\n'.join(('POST', '/', query, canonical_headers, names, digest))
    scope = date[:8]+'/cn-north-1/cv/request'
    to_sign = '\n'.join(('HMAC-SHA256', date, scope, hashlib.sha256(canonical.encode()).hexdigest()))
    key = secret_key.encode()
    for component in (date[:8], 'cn-north-1', 'cv', 'request'):
        key = hmac.new(key, component.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return {'Content-Type': 'application/json', 'Host': HOST, 'X-Date': date, 'X-Content-Sha256': digest,
            'Authorization': f'HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={names}, Signature={signature}'}


def redact(value, secrets=()):
    if isinstance(value, dict):
        return {key: ('[redacted]' if key.lower() in SENSITIVE else redact(child, secrets))
                for key, child in value.items()}
    if isinstance(value, list): return [redact(child, secrets) for child in value]
    if isinstance(value, str):
        value = re.sub(r'https?://[^\s"<>]+', '[redacted-url]', value)
        for secret in secrets:
            if secret: value = value.replace(secret, '[redacted]')
    return value


def _identifier(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,256}', value):
        raise AdapterError(FailureKind.invalid_result, f'invalid official {label}')
    return value


class JimengClient:
    def __init__(self, settings, *, http=None, ownership_check=None):
        self.settings = settings
        self.http = http or ExternalHttpsClient()
        self.ownership_check = ownership_check

    def check_credentials(self):
        access = os.environ.get(self.settings.access_key_env)
        secret = os.environ.get(self.settings.secret_key_env)
        if not access or not secret:
            raise ValueError('missing Jimeng AK/SK environment variables')
        return access, secret

    def _request(self, action, payload, timeout=None):
        access, secret = self.check_credentials()
        body = encode_body(payload)
        headers = sign_request(body, action, access, secret)
        response = self.http.request('POST', 'https://'+HOST+'/?'+urlencode(dict(Action=action, Version=VERSION)),
                                     body=body, headers=headers,
                                     timeout=min(timeout, self.settings.request_timeout_seconds) if timeout is not None else self.settings.request_timeout_seconds,
                                     **({'ownership_check': self.ownership_check} if self.ownership_check is not None else {}))
        try:
            data = strict_json(response.body)
            if not isinstance(data, dict): raise ValueError()
        except (ValueError, UnicodeError):
            raise AdapterError(FailureKind.ambiguous if action == SUBMIT else FailureKind.invalid_result,
                               'malformed official JSON response') from None
        diagnostic = redact(data, (access, secret))
        code = data.get('code')
        request_id = data.get('request_id')
        if request_id is not None: request_id = _identifier(request_id, 'request_id')
        if type(code) is not int or code != 10000:
            error = AdapterError(FailureKind.explicit, f'Jimeng business error code={code if type(code) is int else "invalid"}; request_id={request_id}')
            error.diagnostic = diagnostic
            raise error
        content = data.get('data')
        if not isinstance(content, dict) or not content:
            error = AdapterError(FailureKind.ambiguous if action == SUBMIT else FailureKind.invalid_result,
                                 f'Jimeng empty data; request_id={request_id}')
            error.diagnostic = diagnostic
            raise error
        return content, request_id, diagnostic

    def submit(self, prompt, *, timeout=None, image_urls=None):
        if not isinstance(prompt, str) or not prompt.strip(): raise ValueError('nonempty image prompt required')
        parameters = thaw(self.settings.model_parameters)
        if any(key in parameters for key in ('prompt', 'req_key', 'image_urls')):
            raise ValueError('reserved Jimeng model parameter')
        payload = dict(parameters, req_key=self.settings.req_key, prompt=prompt)
        if image_urls is not None:
            if not isinstance(image_urls, list) or not image_urls:
                raise ValueError('reference image_urls must be a nonempty array')
            for url in image_urls: validate_https_url(url)
            payload['image_urls'] = list(image_urls)
        content, request_id, diagnostic = self._request(SUBMIT, payload, timeout)
        return dict(task_id=_identifier(content.get('task_id'), 'task_id'), request_id=request_id, diagnostic=diagnostic)

    def query(self, task_id, *, timeout=None):
        _identifier(task_id, 'task_id')
        content, request_id, diagnostic = self._request(QUERY, dict(req_key=self.settings.req_key,
            task_id=task_id, req_json=json.dumps({'return_url': True})), timeout)
        status = content.get('status')
        if status not in STATES: raise AdapterError(FailureKind.invalid_result, 'unknown official image task state')
        urls = content.get('image_urls', [])
        if status == 'done':
            if not isinstance(urls, list) or not urls: raise AdapterError(FailureKind.invalid_result, 'completed image task has no image URLs')
            try:
                for url in urls: validate_https_url(url)
            except ValueError:
                raise AdapterError(FailureKind.invalid_result, 'invalid image download URL') from None
        return dict(status=status, image_urls=urls, request_id=request_id, diagnostic=diagnostic)

    def download(self, url, *, timeout=None):
        return self.http.request('GET', url, timeout=min(timeout, self.settings.request_timeout_seconds)
            if timeout is not None else self.settings.request_timeout_seconds, max_bytes=64*1024*1024,
            **({'ownership_check': self.ownership_check} if self.ownership_check is not None else {})).body
