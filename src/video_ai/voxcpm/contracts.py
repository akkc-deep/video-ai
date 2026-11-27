"""Finite requests, frozen synthesis inputs and small PCM metadata checks."""
import hashlib
import json
import math
import re
import wave


class ApiError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


EMOTIONS = dict(neutral='自然中性', narrative='沉稳叙述', mystery='神秘且带有悬念', awe='惊叹敬畏',
    excited='兴奋喜悦', sad='悲伤低落', lonely='孤独寂寥', gentle='温柔舒缓', tense='紧张急切',
    philosophical='沉思哲理', angry='愤怒有力', whisper='轻声耳语')
DEFAULTS = dict(voice_id='existing-reference', emotion='narrative', emotion_intensity=.3,
    instruction='', seed=42, cfg_value=2.0, inference_timesteps=10)


def valid_id(value):
    if not isinstance(value, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', value) is None:
        raise ApiError(400, 'invalid request_id')
    return value


def freeze_request(body, binding):
    if not isinstance(body, dict) or set(body) - (set(DEFAULTS) | {'request_id', 'text'}):
        raise ApiError(400, 'unknown request fields')
    value = dict(DEFAULTS, **body)
    valid_id(value.get('request_id'))
    text = value.get('text')
    if not isinstance(text, str) or not text.strip() or len(text) > 250:
        raise ApiError(400, 'text must contain 1–250 characters')
    if value['voice_id'] != binding['voice_id']:
        raise ApiError(400, 'unknown voice_id')
    if not isinstance(value['emotion'], str) or value['emotion'] not in EMOTIONS:
        raise ApiError(400, 'unknown emotion')
    if not isinstance(value['instruction'], str) or len(value['instruction']) > 300:
        raise ApiError(400, 'instruction must contain at most 300 characters')
    for name, low, high in [('cfg_value', .1, 10), ('emotion_intensity', 0, 1)]:
        number = value[name]
        if type(number) not in (int, float) or not math.isfinite(number) or not low <= number <= high:
            raise ApiError(400, f'invalid {name}')
        value[name] = float(number)
    for name, low, high in [('seed', 0, 2**63-1), ('inference_timesteps', 1, 50)]:
        if type(value[name]) is not int or not low <= value[name] <= high:
            raise ApiError(400, f'invalid {name}')
    strength = '轻微' if value['emotion_intensity'] < .34 else '适度' if value['emotion_intensity'] < .67 else '明显'
    direction = f'保持参考音色，吐字清晰，{strength}{EMOTIONS[value["emotion"]]}'
    if value['instruction']:
        direction += '，' + value['instruction']
    value['synthesis_text'] = f'({direction}){text}'
    value['binding'] = dict(binding)
    return value


def fingerprint(value):
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def wav_metadata(path):
    try:
        with wave.open(str(path), 'rb') as audio:
            result = dict(sample_rate=audio.getframerate(), sample_count=audio.getnframes(),
                          channels=audio.getnchannels(), sample_width=audio.getsampwidth())
    except wave.Error as error:
        raise ValueError(f'invalid WAV: {error}') from error
    if (result['channels'] != 1 or result['sample_width'] != 2 or result['sample_count'] <= 0
            or result['sample_rate'] != 48000 or path.stat().st_size < 44 + result['sample_count'] * 2):
        raise ValueError('expected complete mono 48000 Hz PCM16 WAV')
    return result
