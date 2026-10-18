"""Lossless Unicode spans; speech always comes directly from the input."""
from dataclasses import dataclass
from pathlib import Path
import unicodedata

SENTENCE = '。！？!?；;.'
PHRASE = '，,：:'
CLOSERS = '”’」』）》】"\''


def speakable(text: str) -> bool:
    return any(not c.isspace() and not unicodedata.category(c).startswith('P') for c in text)


@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int
    text: str
    kind: str
    boundary: str
    unit_id: str | None


@dataclass(frozen=True)
class SegmentedScript:
    text: str
    has_bom: bool
    spans: tuple[TextSpan, ...]

    @classmethod
    def read(cls, path: Path) -> 'SegmentedScript':
        raw = path.read_bytes()
        text = raw.decode('utf-8-sig', errors='strict')
        return cls(text, raw.startswith(b'\xef\xbb\xbf'), segment_text(text))


def _boundary(text, i):
    c = text[i]
    if c == '.' and 0 < i < len(text)-1 and text[i-1].isdigit() and text[i+1].isdigit():
        return None
    if c in SENTENCE: return 'sentence'
    if c in PHRASE: return 'phrase'
    return None


def segment_text(text: str) -> tuple[TextSpan, ...]:
    if not isinstance(text, str): raise ValueError('text must be a string')
    spans, i, number = [], 0, 0
    while i < len(text):
        start, boundary = i, 'end'
        if text[i].isspace():
            while i < len(text) and text[i].isspace(): i += 1
            boundary = 'newline' if any(c in '\r\n' for c in text[start:i]) else 'none'
        else:
            while i < len(text) and not text[i].isspace():
                found = _boundary(text, i)
                i += 1
                if found:
                    boundary = found
                    while i < len(text) and (_boundary(text, i) or text[i] in CLOSERS):
                        boundary = _boundary(text, i) or boundary
                        i += 1
                    break
            else:
                if i < len(text): boundary = 'newline' if text[i] in '\r\n' else 'none'
        part = text[start:i]
        kind = 'speech' if speakable(part) else 'skip'
        if kind == 'speech': number += 1
        spans.append(TextSpan(start, i, part, kind, boundary, f'speech_{number:04d}' if kind == 'speech' else None))
    result = tuple(spans)
    validate_segments(text, result)
    return result


def validate_segments(text, spans) -> None:
    position, number = 0, 0
    for span in spans:
        if (not isinstance(span, TextSpan) or type(span.start) is not int or type(span.end) is not int
                or span.start != position or not span.start < span.end <= len(text)
                or span.text != text[span.start:span.end]
                or span.boundary not in {'sentence', 'phrase', 'newline', 'end', 'none'}):
            raise ValueError('invalid original-text span/coverage')
        expected = 'speech' if speakable(span.text) else 'skip'
        if expected == 'speech': number += 1
        if span.kind != expected or span.unit_id != (f'speech_{number:04d}' if expected == 'speech' else None):
            raise ValueError('invalid speech/skip kind or sequential unit ID')
        position = span.end
    if position != len(text): raise ValueError('incomplete original-text coverage')
