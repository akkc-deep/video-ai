"""Optional backend selection kept in raw snapshots for historical compatibility."""
from dataclasses import dataclass, field
from collections.abc import Mapping
from types import MappingProxyType

from .config import ConfigError
from .voxcpm.contracts import ApiError, DEFAULTS, freeze_request


@dataclass(frozen=True)
class TtsSettings:
    engine: str = 'gpt-sovits'
    model_revision: str | None = None
    parameters: Mapping = field(default_factory=lambda: MappingProxyType({}))


def parse_tts_settings(raw):
    if 'tts' not in raw:
        return TtsSettings()
    value = raw['tts']
    if not isinstance(value, Mapping):
        raise ConfigError('tts: expected object')
    engine = value.get('engine')
    if engine == 'gpt-sovits' and set(value) == {'engine'}:
        return TtsSettings()
    if engine != 'voxcpm2':
        raise ConfigError('tts.engine: expected gpt-sovits or voxcpm2 without unsupported fields')
    if set(value) - (set(DEFAULTS) | {'engine', 'model_revision'}):
        raise ConfigError('tts: unknown field')
    revision = value.get('model_revision')
    if not isinstance(revision, str) or not revision.strip() or revision != revision.strip():
        raise ConfigError('tts.model_revision: required nonempty frozen revision')
    parameters = dict(DEFAULTS, **{k:v for k,v in value.items() if k in DEFAULTS})
    try:
        checked = freeze_request(dict(parameters, request_id='config', text='配置'),
                                 dict(voice_id='existing-reference'))
    except ApiError as error:
        raise ConfigError(f'tts: {error}') from error
    return TtsSettings(engine, revision, MappingProxyType({k:checked[k] for k in DEFAULTS}))
