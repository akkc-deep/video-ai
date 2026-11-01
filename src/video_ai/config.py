"""Strict versioned JSON configuration; loading performs no writes or inference."""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlsplit

from .runtime.paths import (CACHE_ROOT, OUTPUT_ROOT, PROJECT_ROOT, RUNTIME_ROOT,
                            resolve_config_path)


class ConfigError(ValueError):
    pass


def _error(file: Path, field: str, reason: str):
    raise ConfigError(f'{file}: {field}: {reason}')


def read_json(file: Path) -> dict:
    """Shared strict reader for versioned config and workflow mapping JSON."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _error(file, key, 'duplicate JSON key')
            result[key] = value
        return result

    def constant(value):
        _error(file, 'JSON', f'non-finite number {value}')

    try:
        value = json.loads(file.read_text(encoding='utf-8-sig'), object_pairs_hook=pairs, parse_constant=constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _error(file, 'JSON', str(exc))
    if not isinstance(value, dict):
        _error(file, 'JSON', 'expected object')
    return value


def _object(value, file, field, required, optional=()):
    if not isinstance(value, dict):
        _error(file, field, 'expected object')
    for name in value:
        if name not in required and name not in optional:
            _error(file, f'{field}.{name}', 'unknown field')
    for name in required:
        if name not in value or value[name] is None:
            _error(file, f'{field}.{name}', 'required non-null field')
    return value


def _str(value, file, field):
    if not isinstance(value, str) or not value.strip():
        _error(file, field, 'expected non-empty string')
    return value


def _number(value, file, field, *, integer=False, positive=True):
    if isinstance(value, bool) or not isinstance(value, int if integer else (int, float)):
        _error(file, field, 'expected integer' if integer else 'expected number')
    try:
        finite = math.isfinite(value)
    except OverflowError:
        _error(file, field, 'number exceeds the supported numeric range')
    if not finite or (positive and value <= 0):
        _error(file, field, 'must be finite and positive')
    return value


def _exact(value, expected, file, field):
    if type(value) is not type(expected) or value != expected:
        _error(file, field, f'must equal {expected!r}')
    return value


def _path(value, file, field):
    try:
        return resolve_config_path(_str(value, file, field), file)
    except ValueError as exc:
        _error(file, field, str(exc))


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def _scene_clip_limit(value: int | float) -> int:
    """Largest native16 Wan length allowed by a finite duration cap."""
    if type(value) not in (int, float):
        raise ConfigError('max_clip_seconds: expected number')
    try:
        if not math.isfinite(value):
            raise ConfigError('max_clip_seconds: must be finite')
        frames = math.floor(value * 16)
    except (ValueError, OverflowError) as exc:
        raise ConfigError('max_clip_seconds: must be finite within supported numeric range') from exc
    if value <= 0 or frames < 5:
        raise ConfigError('max_clip_seconds: must be positive and allow at least 5 native frames')
    return 1 + 4 * ((frames - 1) // 4)


@dataclass(frozen=True)
class ScenePlanningSettings:
    target_scenes_per_paragraph: int = 3
    max_clip_seconds: int | float = 6

    def __post_init__(self):
        if type(self.target_scenes_per_paragraph) is not int or self.target_scenes_per_paragraph <= 0:
            raise ConfigError('target_scenes_per_paragraph: expected positive integer')
        _scene_clip_limit(self.max_clip_seconds)


def parse_scene_planning(value) -> ScenePlanningSettings:
    """Parse explicit settings from live or frozen raw configuration."""
    if value is None:
        return ScenePlanningSettings()
    if not isinstance(value, Mapping):
        raise ConfigError('scene_planning: expected object')
    unknown = set(value) - set(ScenePlanningSettings.__dataclass_fields__)
    if unknown:
        raise ConfigError(f'scene_planning: unknown field {next(iter(unknown))!r}')
    try:
        return ScenePlanningSettings(**value)
    except ConfigError as exc:
        raise ConfigError(f'scene_planning: {exc}') from exc


def parse_scene_planner_model(value='qwen3:8b') -> str:
    """Only verified Qwen3 models share the existing scene token budget."""
    if type(value) is not str or value not in ('qwen3:8b', 'qwen3:14b'):
        raise ConfigError('scene_planner_model: expected qwen3:8b or qwen3:14b')
    return value


def parse_scene_continuity(value) -> dict:
    """Parse an explicit policy without introducing defaults for older runs."""
    if not isinstance(value, Mapping) or set(value) != {'schema_version', 'policy'}:
        raise ConfigError('scene_continuity: expected exact fields schema_version and policy')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ConfigError('scene_continuity.schema_version: expected integer 1')
    if type(value['policy']) is not str or value['policy'] != 'advisory_v1':
        raise ConfigError('scene_continuity.policy: expected advisory_v1')
    return dict(schema_version=1, policy='advisory_v1')


@dataclass(frozen=True)
class Profile:
    name: str
    width: int
    height: int
    native_fps: int = 16


@dataclass(frozen=True)
class TimelineSettings:
    sentence_pause_seconds: float = .8
    paragraph_pause_seconds: float = 2
    opening_seconds: float = 2
    closing_seconds: float = 3

    def __post_init__(self):
        for value in vars(self).values(): timeline_sample_count(value)


def timeline_sample_count(value: int | float) -> int:
    if type(value) not in (int, float): raise ConfigError('timeline seconds must be a number')
    try:
        with localcontext() as context:
            context.prec = 40
            number = Decimal(str(value))
            if not number.is_finite() or number < 0: raise ConfigError('timeline seconds must be finite and nonnegative')
            samples = (number * 48000).to_integral_value(rounding=ROUND_HALF_UP)
            if samples > 2**63-1: raise ConfigError('timeline sample count exceeds supported integer range')
            return int(samples)
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise ConfigError(f'invalid timeline seconds: {exc}') from exc


def parse_timeline_settings(value, file: Path) -> TimelineSettings:
    names = tuple(TimelineSettings.__dataclass_fields__)
    _object(value, file, 'media.timeline', (), names)
    try: return TimelineSettings(**value)
    except ConfigError as exc: _error(file, 'media.timeline', str(exc))


@dataclass(frozen=True)
class MediaConfig:
    profile: Profile
    fps: int
    final_width: int
    final_height: int
    transition: str
    transition_seconds: float
    burn_subtitles: bool
    music: Path | None
    font_file: Path
    timeline: TimelineSettings = field(default_factory=TimelineSettings)

    @property
    def frame_rate_conversion(self) -> bool:
        return self.fps != self.profile.native_fps


@dataclass(frozen=True)
class VoiceConfig:
    schema_version: int
    gpt_weights: Path
    sovits_weights: Path
    bert_root: Path
    hubert_root: Path
    reference_audio: Path
    reference_sha256: str
    reference_text: str
    text_language: str
    prompt_language: str
    speed_factor: float
    device: str
    is_half: bool
    inference: Mapping[str, Any]
    config_file: Path
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class ProjectConfig:
    schema_version: int
    runtime_root: Path
    project_root: Path
    output_root: Path
    cache_root: Path
    voice_config: Path
    tools: Mapping[str, Path]
    services: Mapping[str, str]
    workflows: Mapping[str, Path]
    models: Mapping[str, Path]
    media: MediaConfig
    timeouts: Mapping[str, float]
    voice: VoiceConfig
    config_file: Path
    raw: Mapping[str, Any]
    production_strategy: str = 'legacy'
    image_generation: Any = None


TOOL_FIELDS = ('ffmpeg', 'ffprobe', 'comfy_python', 'comfy_root', 'tts_python', 'tts_root', 'ollama_executable')
WORKFLOW_FIELDS = ('sdxl', 'wan', 'wan_mapping', 'upscale')
MODEL_FIELDS = ('sdxl', 'wan_high', 'wan_low', 'text_encoder', 'vae', 'upscale')
TIMEOUT_DEFAULTS = dict(ollama_request=120, tts_request=300, comfy_request=600,
                        service_start=300, wan=7200, upscale_frame=180, upscale_clip=1200)


def load_voice_config(path: Path, *, raw: dict | None = None) -> VoiceConfig:
    path = path.resolve()
    data = read_json(path) if raw is None else raw
    fields = ('schema_version', 'gpt_weights', 'sovits_weights', 'bert_root', 'hubert_root',
              'reference_audio', 'reference_sha256', 'reference_text', 'text_language',
              'prompt_language', 'speed_factor', 'device', 'is_half', 'inference')
    _object(data, path, 'voice', fields)
    _exact(data['schema_version'], 1, path, 'schema_version')
    values = {name: _path(data[name], path, name) for name in fields[1:6]}
    sha = _str(data['reference_sha256'], path, 'reference_sha256')
    if not re.fullmatch('[0-9a-f]{64}', sha):
        _error(path, 'reference_sha256', 'expected 64 lowercase hexadecimal characters')
    text = _str(data['reference_text'], path, 'reference_text')
    languages = {'zh', 'en', 'ja', 'yue', 'ko', 'auto', 'auto_yue', 'all_zh', 'all_ja', 'all_yue', 'all_ko'}
    for name in ('text_language', 'prompt_language'):
        if _str(data[name], path, name) not in languages:
            _error(path, name, 'unsupported language')
    speed = _number(data['speed_factor'], path, 'speed_factor')
    device = _str(data['device'], path, 'device')
    if not re.fullmatch(r'cpu|cuda(?::[0-9]+)?', device):
        _error(path, 'device', 'expected cpu, cuda or cuda:<nonnegative index>')
    half = data['is_half']
    if not isinstance(half, bool) or (device == 'cpu' and half):
        _error(path, 'is_half', 'expected bool, false on CPU')
    infer = _object(data['inference'], path, 'inference',
                    ('top_k', 'top_p', 'temperature', 'text_split_method', 'batch_size',
                     'media_type', 'streaming_mode', 'sample_steps'))
    for name in ('top_k', 'sample_steps'):
        _number(infer[name], path, 'inference.' + name, integer=True)
    top_p = _number(infer['top_p'], path, 'inference.top_p')
    if top_p > 1:
        _error(path, 'inference.top_p', 'must be <= 1')
    _number(infer['temperature'], path, 'inference.temperature')
    if _str(infer['text_split_method'], path, 'inference.text_split_method') not in {'cut0', 'cut1', 'cut2', 'cut3', 'cut4', 'cut5'}:
        _error(path, 'inference.text_split_method', 'unsupported split method')
    for name, expected in [('batch_size', 1), ('media_type', 'wav'), ('streaming_mode', False)]:
        _exact(infer[name], expected, path, 'inference.' + name)
    return VoiceConfig(1, **values, reference_sha256=sha, reference_text=text,
                       text_language=data['text_language'], prompt_language=data['prompt_language'],
                       speed_factor=speed, device=device, is_half=half,
                       inference=_freeze(infer), config_file=path, raw=_freeze(data))


def load_config(path: Path, *, raw: dict | None = None, voice: VoiceConfig | None = None) -> ProjectConfig:
    path = path.resolve()
    data = read_json(path) if raw is None else raw
    _object(data, path, 'project', ('schema_version', 'runtime_root', 'project_root', 'output_root',
                                  'cache_root', 'voice_config', 'tools', 'services', 'workflows',
                                  'models', 'media'), ('timeouts', 'production_strategy', 'image_generation', 'scene_planning', 'selection_email',
                                                       'reference_generation', 'reference_capabilities', 'reference_storage', 'scene_planner_model', 'scene_rendering', 'scene_continuity'))
    _exact(data['schema_version'], 1, path, 'schema_version')
    from .jimeng_config import STRATEGY, parse_image_generation
    strategy = data.get('production_strategy', 'legacy')
    if strategy not in ('legacy', STRATEGY): _error(path, 'production_strategy', 'unsupported strategy')
    if 'scene_continuity' in data:
        if strategy != STRATEGY: _error(path, 'scene_continuity', 'requires paragraph_jimeng_v1 strategy')
        try: parse_scene_continuity(data['scene_continuity'])
        except ConfigError as exc: _error(path, 'scene_continuity', str(exc))
    if 'scene_rendering' in data:
        if strategy != STRATEGY: _error(path, 'scene_rendering', 'requires paragraph_jimeng_v1 strategy')
        from .planning.scene_video_prompts import parse_scene_rendering
        try:
            rendering = parse_scene_rendering(data['scene_rendering'])
            if rendering.get('mode') == 'whole_scene_v1':
                if data.get('scene_continuity') != dict(schema_version=1, policy='advisory_v1'):
                    raise ValueError('whole_scene_v1 requires explicit scene_continuity advisory_v1')
                if not isinstance(data.get('media'), Mapping) or data['media'].get('profile') != 'fast':
                    raise ValueError('whole_scene_v1 requires the admitted fast profile')
        except ValueError as exc: _error(path, 'scene_rendering', str(exc))
    image = parse_image_generation(data.get('image_generation'), path) if strategy == STRATEGY else None
    if strategy == 'legacy' and 'image_generation' in data:
        _error(path, 'image_generation', 'requires paragraph_jimeng_v1 strategy')
    if strategy == 'legacy' and any(key in data for key in ('reference_generation', 'reference_capabilities', 'reference_storage')):
        _error(path, 'reference_generation', 'requires paragraph_jimeng_v1 strategy')
    if strategy == STRATEGY:
        # Reject unrecognized credential fields before raw configuration can be frozen.
        if data.get('reference_generation') is not None:
            parse_image_generation(data['reference_generation'], path)
        if data.get('reference_storage') is not None:
            from .reference_config import STORAGE_REQUIRED, STORAGE_DEFAULTS
            _object(data['reference_storage'], path, 'reference_storage', (), tuple(STORAGE_REQUIRED)+tuple(STORAGE_DEFAULTS))
    if strategy == 'legacy' and 'scene_planning' in data:
        _error(path, 'scene_planning', 'requires paragraph_jimeng_v1 strategy')
    if 'scene_planner_model' in data:
        if strategy != STRATEGY:
            _error(path, 'scene_planner_model', 'requires paragraph_jimeng_v1 strategy')
        parse_scene_planner_model(data['scene_planner_model'])
    if strategy == 'legacy' and 'selection_email' in data:
        _error(path, 'selection_email', 'requires paragraph_jimeng_v1 strategy')
    if strategy == STRATEGY:
        from .selection_config import parse_selection_email
        parse_selection_email(data.get('selection_email'))
        try:
            parse_scene_planning(data.get('scene_planning'))
        except ConfigError as exc:
            _error(path, 'scene_planning', str(exc))
    roots = {}
    for name, expected in [('runtime_root', RUNTIME_ROOT), ('project_root', PROJECT_ROOT),
                           ('output_root', OUTPUT_ROOT), ('cache_root', CACHE_ROOT)]:
        roots[name] = _path(data[name], path, name)
        # Compare against un-resolved canonical roots to reject redirected roots.
        if roots[name] != expected:
            _error(path, name, f'must resolve to {expected}')
    groups = {}
    for name, fields in [('tools', TOOL_FIELDS), ('models', MODEL_FIELDS), ('workflows', WORKFLOW_FIELDS)]:
        optional = ('sdxl',) if strategy == STRATEGY and name in ('models', 'workflows') else ()
        group = _object(data[name], path, name, tuple(k for k in fields if k not in optional), optional)
        groups[name] = MappingProxyType({k: _path(v, path, f'{name}.{k}') for k, v in group.items()})
    services = _object(data['services'], path, 'services', ('ollama', 'comfyui', 'tts'))
    for name, value in services.items():
        _str(value, path, f'services.{name}')
        try:
            url = urlsplit(value)
            good = (value == value.strip() and not any(ord(c) <= 32 for c in value)
                    and url.scheme == 'http' and url.hostname in {'localhost', '127.0.0.1', '::1'}
                    and url.port is not None and 0 < url.port < 65536 and url.username is None
                    and url.password is None and not url.query and not url.fragment and url.path in ('', '/'))
        except ValueError:
            good = False
        if not good:
            _error(path, f'services.{name}', 'expected local http URL with explicit port and no credentials/query/fragment')
    media = _object(data['media'], path, 'media', ('profile', 'font_file'),
                    ('fps', 'final_width', 'final_height', 'transition', 'transition_seconds', 'burn_subtitles', 'music', 'timeline'))
    for name in ('fps', 'final_width', 'final_height', 'transition', 'transition_seconds', 'burn_subtitles'):
        if name in media and media[name] is None:
            _error(path, 'media.' + name, 'must not be null')
    profile = media['profile']
    if profile not in ('fast', 'quality'):
        _error(path, 'media.profile', 'expected fast or quality')
    fps = _number(media.get('fps', 16), path, 'media.fps', integer=True)
    if fps not in (16, 24):
        _error(path, 'media.fps', 'must be 16 or 24')
    width = _exact(media.get('final_width', 1920), 1920, path, 'media.final_width')
    height = _exact(media.get('final_height', 1080), 1080, path, 'media.final_height')
    transition = media.get('transition', 'cut')
    seconds = _number(media.get('transition_seconds', 0), path, 'media.transition_seconds', positive=False)
    if transition not in ('cut', 'fade') or (transition == 'cut' and seconds != 0) or (transition == 'fade' and seconds <= 0):
        _error(path, 'media.transition_seconds', 'cut requires 0; fade requires a positive duration')
    burned = _exact(media.get('burn_subtitles', True), True, path, 'media.burn_subtitles')
    music = _path(media['music'], path, 'media.music') if media.get('music') is not None else None
    profile_object = Profile(profile, *( (768, 432) if profile == 'fast' else (1280, 720)))
    media_config = MediaConfig(profile_object, fps, width, height, transition, seconds, burned,
                               music, _path(media['font_file'], path, 'media.font_file'),
                               parse_timeline_settings(media.get('timeline', {}), path))
    timeouts = _object(data.get('timeouts', {}), path, 'timeouts', (), tuple(TIMEOUT_DEFAULTS))
    timeouts = {**TIMEOUT_DEFAULTS, **timeouts}
    for name, value in timeouts.items():
        _number(value, path, f'timeouts.{name}')
    if data.get('scene_rendering',{}).get('mode') == 'whole_scene_v1':
        if timeouts['wan']>7200 or timeouts['service_start']>300:
            _error(path,'timeouts','whole_scene_v1 requires Wan <=7200 and service_start <=300 seconds')
    voice_path = _path(data['voice_config'], path, 'voice_config')
    if voice is None:
        voice = load_voice_config(voice_path)
    elif voice.config_file != voice_path:
        _error(path, 'voice_config', 'supplied frozen voice path differs')
    return ProjectConfig(1, **roots, voice_config=voice_path, **groups,
                         services=_freeze(services), media=media_config,
                         timeouts=_freeze(timeouts), voice=voice, config_file=path, raw=_freeze(data),
                         production_strategy=strategy, image_generation=image)
