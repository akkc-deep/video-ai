"""Strict original-character SRT validation against committed subtitle events."""
from copy import deepcopy
from pathlib import Path
import re

from .subtitles import quantize, srt_text


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name}: nonnegative integer required')
    return value


def _events(events, total_samples):
    _integer(total_samples, 'total_samples', 1)
    if not isinstance(events, (list, tuple)) or not events:
        raise ValueError('nonempty subtitle events required')
    last_sample = last_ms = last_text = 0
    units = set()
    for event in events:
        if not isinstance(event, dict): raise ValueError('subtitle event object required')
        unit = event['unit_id']
        if type(unit) is not str or not unit.strip() or unit in units:
            raise ValueError('unique subtitle unit required')
        units.add(unit)
        a, b = (_integer(event[k], k) for k in ('text_start', 'text_end'))
        text = event['text']
        if type(text) is not str or not text or any(ord(c) < 32 for c in text) or not last_text <= a < b or b-a != len(text):
            raise ValueError('invalid original subtitle text/span')
        start, end = (_integer(event[k], k) for k in ('start_sample', 'end_sample'))
        if not last_sample <= start < end <= total_samples:
            raise ValueError('subtitle samples overlap or exceed media')
        start_ms, end_ms = (_integer(event[k], k) for k in ('start_ms', 'end_ms'))
        if (start_ms, end_ms) != (quantize(start,1000), quantize(end,1000)) or not last_ms <= start_ms < end_ms:
            raise ValueError('subtitle millisecond mapping differs')
        for key in ('start_frame','end_frame','start_cs','end_cs'):
            _integer(event[key], key)
        if event['start_frame'] >= event['end_frame'] or (event['start_cs'],event['end_cs']) != (quantize(start,100),quantize(end,100)):
            raise ValueError('subtitle frame/centisecond range differs')
        layout = event['layout']
        if not isinstance(layout, dict) or set(layout) != {'lines','line_ranges','line_widths','available_width'}:
            raise ValueError('invalid subtitle layout')
        lines, ranges = layout['lines'], layout['line_ranges']
        if type(lines) is not list or type(ranges) is not list or not 1 <= len(lines) <= 2 or len(lines) != len(ranges):
            raise ValueError('one or two subtitle lines required')
        widths, available = layout['line_widths'], layout['available_width']
        if type(available) is not int or available<=0 or type(widths) is not list or len(widths)!=len(lines):
            raise ValueError('finite subtitle layout widths required')
        if any(type(w) is not int or not 0<w<=available for w in widths):
            raise ValueError('subtitle line exceeds available width')
        cursor = 0
        for line, span in zip(lines, ranges):
            if type(span) is not dict or set(span) != {'start','end'}:
                raise ValueError('invalid line range')
            x, y = (_integer(span[k], 'line '+k) for k in ('start','end'))
            if x != cursor or not x < y <= len(text) or line != text[x:y]:
                raise ValueError('layout fails to preserve original characters')
            cursor = y
        if cursor != len(text) or ''.join(lines) != text:
            raise ValueError('incomplete original subtitle span')
        last_sample, last_ms, last_text = end, end_ms, b


def validate_srt(path, events, *, total_samples):
    """Return the execution srt_check, or reject malformed/mismatching bytes."""
    try:
        _events(events,total_samples)
        payload = Path(path).read_bytes()
        text = payload.decode('utf-8', errors='strict')
        if text.startswith('\ufeff') or '\r' in text:
            raise ValueError('UTF-8 without BOM and LF required')
        if text != srt_text(events):
            raise ValueError('SRT original text, timing or serialization differs')
        # Exact serialization above rejects numbering, spacing and extra events;
        # parse the timestamps separately to reject invalid clock components.
        timestamps = re.findall(r'(?m)^([0-9]{2}:[0-9]{2}:[0-9]{2},[0-9]{3}) --> ([0-9]{2}:[0-9]{2}:[0-9]{2},[0-9]{3})$',text)
        if len(timestamps)!=len(events): raise ValueError('exact HH:MM:SS,mmm timestamps required')
        for timestamp in timestamps:
            for value in timestamp:
                if int(value[3:5]) >= 60 or int(value[6:8]) >= 60:
                    raise ValueError('invalid SRT clock')
        return dict(events=deepcopy(events),original_text_passed=True,timing_passed=True,serialization_passed=True)
    except (KeyError,TypeError,AttributeError,UnicodeError,OverflowError) as exc:
        raise ValueError('invalid SRT or subtitle event structure') from exc
