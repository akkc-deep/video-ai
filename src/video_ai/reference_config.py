"""Explicit reference capability evidence and private TOS configuration.

No model capabilities are inferred from model names. This module performs no I/O.
"""
from copy import deepcopy
from datetime import datetime
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

from .jimeng_config import parse_image_generation

REFERENCE_FIELDS = ('reference_generation', 'reference_capabilities', 'reference_storage')
CAPABILITY_FIELDS = ('schema_version req_key input_field max_images max_image_bytes min_width min_height '
                     'max_width max_height formats max_prompt_bytes evidence').split()
STORAGE_REQUIRED = 'provider bucket region endpoint access_key_env secret_key_env'.split()
STORAGE_DEFAULTS = dict(key_prefix='video-ai-references', url_ttl_seconds=3600,
                        download_margin_seconds=120, clock_skew_seconds=60, request_timeout_seconds=60)


class ReferenceConfigurationRequired(ValueError):
    """A reference-stage local configuration must be supplied or corrected."""


def _require(condition, message):
    if not condition: raise ReferenceConfigurationRequired(message)


def _fields(value, required, optional=()):
    _require(isinstance(value, dict) and set(required) <= set(value)
             and not set(value)-set(required)-set(optional), 'invalid reference configuration fields')


def safe_req_key(value):
    _require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value),
             'reference capability requires safe explicit req_key')
    return value


def parse_capability(value, *, req_key):
    _fields(value, CAPABILITY_FIELDS)
    _require(type(value['schema_version']) is int and value['schema_version'] == 1, 'invalid reference capability schema')
    _require(safe_req_key(value['req_key']) == req_key, 'reference capability req_key differs')
    _require(value['input_field'] == 'image_urls', 'unsupported reference input field')
    for field in 'max_images max_image_bytes min_width min_height max_width max_height max_prompt_bytes'.split():
        _require(type(value[field]) is int and value[field] > 0, 'reference capability requires positive integer limits')
    _require(value['min_width'] <= value['max_width'] and value['min_height'] <= value['max_height'],
             'reference capability dimension range differs')
    formats = value['formats']
    _require(isinstance(formats, list) and formats and all(isinstance(f, str) for f in formats)
             and len(set(formats)) == len(formats) and set(formats) <= {'png', 'jpeg', 'webp'},
             'reference capability formats invalid')
    evidence = value['evidence']
    _fields(evidence, ('source_url', 'source_sha256', 'verified_by', 'verified_at'))
    try:
        parts = urlsplit(evidence['source_url'])
        valid_url = (parts.scheme == 'https' and parts.hostname in ('docs.volcengine.com', 'www.volcengine.com')
                     and not parts.username and not parts.password and not parts.fragment and parts.port in (None, 443)
                     and '\\' not in evidence['source_url'] and not any(ord(c) <= 32 for c in evidence['source_url']))
        date = datetime.fromisoformat(evidence['verified_at'])
        valid_date = date.tzinfo is not None and date.utcoffset() is not None
    except (TypeError, ValueError, AttributeError):
        raise ReferenceConfigurationRequired('reference capability evidence invalid') from None
    _require(valid_url and valid_date, 'reference capability needs official HTTPS evidence and zoned verification time')
    _require(isinstance(evidence['source_sha256'], str) and re.fullmatch('[0-9a-f]{64}', evidence['source_sha256']),
             'reference capability needs source byte SHA256')
    _require(isinstance(evidence['verified_by'], str) and evidence['verified_by'].strip(), 'reference capability needs verifier')
    return deepcopy(value)


def parse_capability_paths(value):
    _require(isinstance(value, dict), 'reference_capabilities must map req_key to absolute local file')
    for key, path in value.items():
        safe_req_key(key)
        _require(isinstance(path, str) and Path(path).is_absolute(), 'reference capability path must be absolute')
    return deepcopy(value)


def parse_reference_storage(value):
    _fields(value, STORAGE_REQUIRED, STORAGE_DEFAULTS)
    settings = dict(STORAGE_DEFAULTS, **value)
    _require(settings['provider'] == 'volcengine_tos', 'unsupported reference storage provider')
    bucket = settings['bucket']; region = settings['region']
    _require(isinstance(bucket, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]', bucket), 'invalid TOS bucket')
    _require(isinstance(region, str) and re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)+', region), 'invalid TOS region')
    _require(settings['endpoint'] == 'https://tos-'+region+'.volces.com', 'TOS endpoint must match region')
    for field in ('access_key_env', 'secret_key_env'):
        _require(isinstance(settings[field], str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', settings[field]),
                 'TOS credentials must use environment variable names')
    prefix = settings['key_prefix']
    _require(isinstance(prefix, str) and prefix and all(re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*', part)
             and part not in ('.', '..') for part in prefix.split('/')), 'invalid TOS key prefix')
    for field in ('url_ttl_seconds', 'download_margin_seconds', 'clock_skew_seconds', 'request_timeout_seconds'):
        number = settings[field]
        _require(type(number) in (int, float) and math.isfinite(number) and number > 0, 'TOS time budgets must be positive and finite')
        if field != 'request_timeout_seconds': _require(type(number) is int, 'TOS URL budgets must be integer seconds')
    _require(settings['url_ttl_seconds'] <= 604800, 'TOS URL TTL exceeds conservative upper limit')
    return settings


def choose_reference_model(image_generation, reference_generation, capabilities):
    reference = None
    if reference_generation is not None:
        try: reference = parse_image_generation(reference_generation, 'reference_generation')
        except ValueError:
            raise ReferenceConfigurationRequired('invalid explicit reference_generation configuration') from None
    for settings in (image_generation, reference):
        if settings is None: continue
        try:
            cap = parse_capability(capabilities.get(settings.req_key), req_key=settings.req_key)
        except ReferenceConfigurationRequired:
            continue
        return settings, cap
    raise ReferenceConfigurationRequired('awaiting_image_model_configuration: provide verified reference capability and explicit model')


def require_url_budget(model_settings, storage):
    needed = model_settings.task_timeout_seconds+storage['download_margin_seconds']+storage['clock_skew_seconds']
    _require(storage['url_ttl_seconds'] >= needed, 'reference URL TTL cannot cover task and download budget')
    return needed
