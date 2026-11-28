"""The approved spoken-guide separator, measured in actual post-tempo PCM."""
from array import array
from collections.abc import Mapping
import sys
from types import MappingProxyType


APPROVED_ONSET_GUARD = MappingProxyType(dict(
    schema_version=1, text='下面继续讲述。', search_start_ms=1000,
    search_end_ms=2600, min_silence_ms=150, retained_silence_ms=50,
    silence_peak=32, boundary='longest-quiet-run', zero_quiet_edges=True))


def approved_onset_guard(value):
    return (isinstance(value, Mapping) and set(value) == set(APPROVED_ONSET_GUARD)
            and all(value[k] == v and type(value[k]) is type(v)
                    for k, v in APPROVED_ONSET_GUARD.items()))


def remove_spoken_guard(pcm, profile):
    if not approved_onset_guard(profile):
        raise ValueError('unapproved narration onset guard')
    if not pcm or len(pcm) % 2:
        raise ValueError('guard removal requires complete mono PCM16 samples')
    samples = array('h'); samples.frombytes(pcm)
    if sys.byteorder != 'little': samples.byteswap()
    window = 480  # 10ms at the production 48kHz rate.
    start = profile['search_start_ms']//10
    stop = min(profile['search_end_ms']//10, len(samples)//window)
    minimum = profile['min_silence_ms']//10
    runs, all_runs, first = [], [], None
    for i in range(start, stop+1):
        quiet = i < stop and max(abs(v) for v in samples[i*window:(i+1)*window]) <= profile['silence_peak']
        if quiet and first is None: first = i
        if not quiet and first is not None:
            all_runs.append((first, i))
            if i-first >= minimum: runs.append((first, i))
            first = None
    if not runs:
        raise ValueError('no safe acoustic guide/body separator; retain cached synthesis')
    a, b = max(runs, key=lambda pair: pair[1]-pair[0])
    # Retain short gaps as ambiguity evidence. The approved material sometimes
    # has a 10ms quiet blip within 30ms of the real separator; only such adjacent
    # micro-gaps may precede it. A short genuine separator followed by a body
    # phrase must not disappear from consideration merely for being <150ms.
    earlier = [(x,y) for x,y in all_runs if x < a]
    if (a, b) != runs[0] or any(y-x > 2 or a-y > 3 for x,y in earlier):
        raise ValueError('ambiguous acoustic guide/body separators; retain cached synthesis')
    cut = b*window-profile['retained_silence_ms']*48
    body = samples[cut:]
    leading = 0
    while leading < len(body) and abs(body[leading]) <= profile['silence_peak']:
        leading += 1
    if leading == len(body): raise ValueError('no original speech after guide/body separator')
    trailing = 0
    while trailing < len(body) and abs(body[-trailing-1]) <= profile['silence_peak']:
        trailing += 1
    for i in range(leading): body[i] = 0
    for i in range(trailing): body[-i-1] = 0
    if sys.byteorder != 'little': body.byteswap()
    return body.tobytes(), dict(cut_samples=cut, silent_separator_ms=[a*10,b*10],
        retained_quiet_guard_ms=profile['retained_silence_ms'],
        leading_zeroed_samples=leading, trailing_zeroed_samples=trailing,
        samples=len(body))
