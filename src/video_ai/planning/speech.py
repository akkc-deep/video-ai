"""Frozen voice and lossless, bounded units with independently measurable timing."""
from dataclasses import dataclass
import hashlib
import re
from types import MappingProxyType

from .emotion import BASE_STYLE, TONES
from .segments import CLOSERS, segment_text, speakable
from ..voxcpm.contracts import fingerprint, freeze_request


@dataclass(frozen=True)
class FrozenVoice:
    voice_id: str
    model_revision: str
    reference_sha256: str
    base_style: str
    parameters: object

    def as_dict(self):
        value = dict(voice_id=self.voice_id, model_revision=self.model_revision,
                     reference_sha256=self.reference_sha256, base_style=self.base_style,
                     parameters=dict(self.parameters))
        return dict(value, identity=fingerprint(value))


def freeze_voice(config, *, base_style=None, voice_profile=None):
    if config.tts.engine != 'voxcpm2':
        raise ValueError('long-form voice requires explicit voxcpm2 settings')
    parameters = dict(config.tts.parameters)
    reference_sha256 = config.voice.reference_sha256
    default_style = parameters['instruction'] or BASE_STYLE
    if voice_profile is not None:
        from ..voxcpm.voices import load_voice_asset
        asset = load_voice_asset(voice_profile, config.runtime_root)
        parameters['voice_id'] = asset.voice_id
        reference_sha256, default_style = asset.reference_sha256, asset.base_style
    style = base_style if base_style is not None else default_style
    if not isinstance(style, str) or not style.strip() or len(style) > 280:
        raise ValueError('base style must contain 1–280 characters')
    return FrozenVoice(parameters['voice_id'], config.tts.model_revision,
                       reference_sha256, style, MappingProxyType(parameters))


def _checked_spans(plan, voice):
    text = plan['source_text']
    if not isinstance(text, str) or not speakable(text):
        raise ValueError('speech plan requires speakable source text')
    if (plan['source_sha256'] != hashlib.sha256(text.encode('utf-8')).hexdigest()
            or plan['base_style'] != voice.base_style):
        raise ValueError('source or base style differs from frozen plan')
    position = 0
    for row in plan['spans']:
        a, b = row['start'], row['end']
        if (type(a) is not int or type(b) is not int or a != position or not a < b <= len(text)
                or row['original_text'] != text[a:b] or row['synthesis_text'] != text[a:b]):
            raise ValueError('invalid original-text coverage or rewritten synthesis text')
        pause = row['pause_after_ms']
        if type(pause) is not int or not 0 <= pause <= 650 or row['tone'] not in TONES:
            raise ValueError('invalid pause or tone')
        freeze_request(dict(voice.parameters, request_id='plan', text='验证',
                            emotion=row['emotion'], emotion_intensity=row['emotion_intensity']),
                       dict(voice_id=voice.voice_id))
        position = b
    if position != len(text):
        raise ValueError('incomplete original-text coverage')
    return text, plan['spans']


def _style(row):
    return row['emotion'], row['emotion_intensity'], row['tone']


def _sentence_ends(text, blocks):
    """Keep legacy source tokens, but don't promote internal English dots to sentences."""
    result = set()
    for block in blocks:
        if block.boundary != 'sentence':
            continue
        mark = block.end-1
        while mark >= block.start and text[mark] in CLOSERS:
            mark -= 1
        if mark >= block.start and text[mark] == '.':
            if (0 < mark < len(text)-1 and text[mark-1].isascii() and text[mark-1].isalnum()
                    and text[mark+1].isascii() and text[mark+1].isalnum()):
                continue  # domain, internal initialism dot, or version number
            token = re.search(r'[A-Za-z.]+$', text[:mark+1])
            token = token.group() if token else ''
            rest = text[mark+1:].lstrip()
            if rest and token.lower() in {'dr.', 'mr.', 'mrs.', 'ms.', 'prof.', 'sr.', 'jr.', 'st.'}:
                continue
            if rest and re.fullmatch(r'(?:[A-Za-z]\.){2,}', token) and not rest[0].isupper():
                continue
        result.add(block.end)
    return result


def _spoken_bounds(text, row):
    start, end = row['start'], row['end']
    while start < end and not speakable(text[start]):
        start += 1
    while end > start and not speakable(text[end-1]):
        end -= 1
    return start, end


def plan_speech(emotion_plan, voice, *, target_chars=180, max_chars=250):
    if (type(target_chars) is not int or type(max_chars) is not int
            or not 1 <= target_chars <= max_chars <= 250):
        raise ValueError('expected 1 <= target_chars <= max_chars <= 250')
    text, emotions = _checked_spans(emotion_plan, voice)
    blocks = segment_text(text)
    sentences = _sentence_ends(text, blocks)
    paragraphs = {s.end for s in blocks if s.kind == 'skip' and ('\n' in s.text or '\r' in s.text)}
    cuts = {0, len(text), *sentences, *paragraphs}
    last_style = None
    for row in emotions:
        if speakable(row['original_text']):
            if last_style is not None and _style(row) != last_style:
                left = max(p for p in cuts if p <= row['start'])
                right = min(p for p in cuts if p >= row['start'])
                # Keep complete short sentences, but avoid isolated interjections
                # at a model's fine-grained emotion transition inside a sentence.
                if (row['start'] in cuts or
                        (sum(speakable(c) for c in text[left:row['start']]) >= 8
                         and sum(speakable(c) for c in text[row['start']:right]) >= 8)):
                    cuts.add(row['start'])
            last_style = _style(row)
    # Only use real punctuation/space ends when reducing a long semantic group.
    soft = sorted({s.end for s in blocks if s.boundary != 'sentence' or s.end in sentences})
    ranges = []
    ordered = sorted(cuts)
    for start, end in zip(ordered, ordered[1:]):
        while end - start > max_chars:
            candidates = [p for p in soft if start < p <= start + target_chars]
            if not candidates:
                candidates = [p for p in soft if start < p <= start + max_chars]
            stop = candidates[-1] if candidates else start + target_chars
            ranges.append([start, stop])
            start = stop
        if start < end:
            # A final 181–250 char group may stay intact to avoid a tiny tail.
            ranges.append([start, end])
    # Attach ordinary skip ranges to neighboring speech without exceeding the cap.
    joined = []
    for start, end in ranges:
        if (joined and not speakable(text[start:end])
                and end - joined[-1][0] <= max_chars):
            joined[-1][1] = end
        elif (joined and not speakable(text[joined[-1][0]:joined[-1][1]])
              and end - joined[-1][0] <= max_chars):
            joined[-1][1] = end
        else:
            joined.append([start, end])
    units, skips = [], []
    for start, end in joined:
        original = text[start:end]
        if not speakable(original):
            skips.append(dict(start=start, end=end, original_text=original, kind='skip'))
            continue
        overlap = [r for r in emotions if r['start'] < end and r['end'] > start]
        weights = {}
        for row in overlap:
            weights[_style(row)] = weights.get(_style(row), 0) + sum(
                speakable(c) for c in text[max(start,row['start']):min(end,row['end'])])
        dominant = max(weights, key=weights.get)
        direction = next(r for r in overlap if _style(r) == dominant)
        units.append(dict(unit_id=f'speech_{len(units)+1:04d}', start=start, end=end,
            original_text=original, synthesis_text=original, voice_id=voice.voice_id,
            seed=voice.parameters['seed'], emotion=direction['emotion'],
            emotion_intensity=direction['emotion_intensity'],
            instruction=f'{voice.base_style}，语气{direction["tone"]}',
            emotion_span_ids=[r['span_id'] for r in overlap], pause_after_ms=0))
    for unit, following in zip(units, units[1:]):
        # Leading whitespace belongs to its source range, not the pause after it.
        a, b = _spoken_bounds(text, unit)[1], _spoken_bounds(text, following)[0]
        paragraph = any(a < p <= b for p in paragraphs)
        sentence = any(a < p <= b for p in sentences)
        hints = [r['pause_after_ms'] for r in emotions if a <= r['end'] <= b]
        hint = max(hints, default=0)
        unit['pause_after_ms'] = (min(650, max(350, hint or 450)) if paragraph else
                                  min(300, max(150, hint or 220)) if sentence else min(300, hint))
    return dict(schema_version=1, source_text=text, source_sha256=emotion_plan['source_sha256'],
                voice=voice.as_dict(), alignment='independent-tts-units',
                segmentation=dict(target_chars=target_chars, max_chars=max_chars),
                units=units, skips=skips)


def validate_speech_plan(plan, voice):
    """One preflight at the synthesis boundary, before spending GPU work."""
    if (plan.get('alignment') != 'independent-tts-units'
            or plan['voice'] != voice.as_dict() or not plan['units']):
        raise ValueError('speech plan differs from frozen voice or has no units')
    text = plan['source_text']
    if plan['source_sha256'] != hashlib.sha256(text.encode('utf-8')).hexdigest():
        raise ValueError('speech source identity differs')
    position = 0
    for row in sorted([*plan['units'], *plan['skips']], key=lambda x:x['start']):
        a, b = row['start'], row['end']
        if (type(a) is not int or type(b) is not int or a != position or not a < b <= len(text)
                or row['original_text'] != text[a:b]):
            raise ValueError('invalid speech source coverage')
        position = b
    if position != len(text):
        raise ValueError('incomplete speech source coverage')
    if any(speakable(row['original_text']) for row in plan['skips']):
        raise ValueError('speakable original text cannot be skipped')
    previous_end = 0
    for i, row in enumerate(plan['units'], 1):
        if (row['unit_id'] != f'speech_{i:04d}' or row['voice_id'] != voice.voice_id
                or row['start'] < previous_end
                or row['seed'] != voice.parameters['seed']
                or row['instruction'] not in {f'{voice.base_style}，语气{tone}' for tone in TONES}
                or row['synthesis_text'] != row['original_text'] or not speakable(row['synthesis_text'])
                or type(row['pause_after_ms']) is not int or not 0 <= row['pause_after_ms'] <= 650):
            raise ValueError('speech unit differs from frozen identity or original text')
        previous_end = row['end']
        freeze_request(dict(voice.parameters, request_id='plan', text=row['synthesis_text'],
            emotion=row['emotion'], emotion_intensity=row['emotion_intensity'], instruction=row['instruction']),
            dict(voice_id=voice.voice_id))
