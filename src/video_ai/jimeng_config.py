"""Explicit image model settings; no credentials or inference during parsing."""
from dataclasses import dataclass, replace
import re
from typing import Mapping, Any

from .config import ConfigError, _object, _str, _number, _error, _freeze

STRATEGY = 'paragraph_jimeng_v1'
# Presets are per-model. In particular, force_single must never leak to 3.x.
MODEL_PRESETS = {
    'jimeng_t2i_v30': dict(width=1280, height=720),
    'jimeng_t2i_v31': dict(width=1280, height=720),
    'jimeng_t2i_v40': dict(width=2560, height=1440, force_single=True),
}
MANAGED = {'req_key', 'prompt', 'task_id', 'req_json', 'image_urls', 'image_url',
           'binary_data_base64', 'image_base64', 'authorization', 'access_key',
           'secret_key', 'ak', 'sk', 'token', 'security_token', 'signature', 'n'}
MANAGED |= {'api_key', 'access_key_id', 'secret_access_key', 'host', 'x-date',
            'x-content-sha256', 'x-security-token', 'action', 'version', 'region', 'service'}


@dataclass(frozen=True)
class ImageGenerationConfig:
    provider: str
    req_key: str
    access_key_env: str
    secret_key_env: str
    model_parameters: Mapping[str, Any]
    candidates_per_scene: int
    output_width: int
    output_height: int
    request_timeout_seconds: float = 60
    task_timeout_seconds: float = 600
    poll_interval_seconds: float = 2


def validate_parameters(value, file):
    def walk(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str) or key.lower() in MANAGED or any(
                        part in key.lower() for part in ('password', 'credential', 'secret', 'authorization', 'signature')):
                    _error(file, 'image_generation.model_parameters', 'managed or credential field refused')
                walk(child)
        elif isinstance(item, list):
            for child in item: walk(child)
        elif isinstance(item, str) and ('://' in item or '\r' in item or '\n' in item):
            _error(file, 'image_generation.model_parameters', 'URLs and multiline values refused')
    walk(value)


def parse_image_generation(value, file):
    required = ('provider', 'req_key', 'access_key_env', 'secret_key_env', 'model_parameters')
    optional = ('candidates_per_scene', 'output_width', 'output_height', 'request_timeout_seconds',
                'task_timeout_seconds', 'poll_interval_seconds')
    _object(value, file, 'image_generation', required, optional)
    if value['provider'] != 'volcengine_jimeng': _error(file, 'image_generation.provider', 'unsupported provider')
    key = _str(value['req_key'], file, 'image_generation.req_key')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', key): _error(file, 'image_generation.req_key', 'invalid model identifier')
    for name in ('access_key_env', 'secret_key_env'):
        if not isinstance(value[name], str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value[name]):
            _error(file, 'image_generation.'+name, 'expected environment variable name')
    parameters = value['model_parameters']
    if not isinstance(parameters, dict): _error(file, 'image_generation.model_parameters', 'expected object')
    validate_parameters(parameters, file)
    width = value.get('output_width', parameters.get('width'))
    height = value.get('output_height', parameters.get('height'))
    for name, number in [('output_width', width), ('output_height', height)]:
        _number(number, file, 'image_generation.'+name, integer=True)
    for name in ('width', 'height'):
        if name in parameters:
            _number(parameters[name], file, 'image_generation.model_parameters.'+name, integer=True)
            if parameters[name] != (width if name == 'width' else height):
                _error(file, 'image_generation.'+name, 'parameter and output dimension differ')
    if width*9 != height*16: _error(file, 'image_generation.output_width', 'requires landscape 16:9 dimensions')
    count = value.get('candidates_per_scene', 2)
    _number(count, file, 'image_generation.candidates_per_scene', integer=True)
    budgets = {name: value.get(name, default) for name, default in
               [('request_timeout_seconds', 60), ('task_timeout_seconds', 600), ('poll_interval_seconds', 2)]}
    for name, number in budgets.items(): _number(number, file, 'image_generation.'+name)
    return ImageGenerationConfig(value['provider'], key, value['access_key_env'], value['secret_key_env'],
                                 _freeze(parameters), count, width, height, **budgets)


def override_image_model(settings, req_key):
    if req_key is None or settings is not None and req_key == settings.req_key: return settings
    if settings is None: raise ConfigError('--image-model requires paragraph_jimeng_v1 configuration')
    if req_key not in MODEL_PRESETS:
        raise ConfigError('unknown image model: provide explicit model_parameters and output dimensions in a new configuration')
    preset = MODEL_PRESETS[req_key]
    return replace(settings, req_key=req_key, model_parameters=_freeze(preset),
                   output_width=preset['width'], output_height=preset['height'])


def active_models(config):
    return {k: v for k, v in config.models.items() if k != 'sdxl' or config.production_strategy != STRATEGY}


def active_workflows(config):
    return {k: v for k, v in config.workflows.items() if k != 'sdxl' or config.production_strategy != STRATEGY}
