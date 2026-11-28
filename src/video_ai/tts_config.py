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
    narration: Mapping | None = None


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
    if set(value) - (set(DEFAULTS) | {'engine', 'model_revision', 'narration'}):
        raise ConfigError('tts: unknown field')
    revision = value.get('model_revision')
    if not isinstance(revision, str) or not revision.strip() or revision != revision.strip():
        raise ConfigError('tts.model_revision: required nonempty frozen revision')
    parameters = dict(DEFAULTS, **{k:v for k,v in value.items() if k in DEFAULTS})
    narration = value.get('narration')
    if narration is not None:
        if not isinstance(narration, Mapping): raise ConfigError('tts.narration: expected inline frozen recipe')
        from .media.narration_guard import approved_onset_guard
        guarded = 'onset_guard' in narration
        if guarded and not approved_onset_guard(narration['onset_guard']):
            raise ConfigError('tts.narration: unapproved onset guard')
        expected = dict(engine='voxcpm2', conditioning_mode='reference-prompt', seed=42, cfg_value=2.,
            inference_timesteps=20, speech_rate=.95, pitch_shift_semitones=0, paragraph_pause_ms=500 if guarded else 850,
            target_rms_db=-23, background_audio=False, per_segment_instructions=False)
        if any(narration.get(k) != v for k,v in expected.items()) or narration.get('model_revision') != revision:
            raise ConfigError('tts.narration: approved recipe parameters differ')
        for key in ('voice_id','voice_profile','reference_sha256','prompt_text','source_revision','recipe_sha256'):
            if not isinstance(narration.get(key), str) or not narration[key].strip():
                raise ConfigError('tts.narration: missing '+key)
        parameters.update(voice_id=narration['voice_id'], seed=42, cfg_value=2., inference_timesteps=20,
                          instruction='', emotion='neutral', emotion_intensity=0.)
        narration = MappingProxyType(dict(narration))
    try:
        checked = freeze_request(dict(parameters, request_id='config', text='配置'),
                                 dict(voice_id=narration['voice_id'] if narration else 'existing-reference'))
    except ApiError as error:
        raise ConfigError(f'tts: {error}') from error
    parameters = {k:checked[k] for k in DEFAULTS}
    if narration:
        parameters.update(conditioning_mode='reference-prompt', prompt_text=narration['prompt_text'])
    return TtsSettings(engine, revision, MappingProxyType(parameters), narration)
