"""Sample-preserving PCM assembly; silence top-up and one whole-program gain."""
from array import array
import math
import os
from pathlib import Path
import sys
from uuid import uuid4
import wave


RATE = 48000
SILENCE_THRESHOLD = 32
FADE_SAMPLES = 144  # 3ms, applied exclusively inside detected edge silence.


def _pcm_bytes(samples):
    if sys.byteorder == 'little':
        return samples.tobytes()
    copy = array('h', samples)
    copy.byteswap()
    return copy.tobytes()


def _read_unit(path):
    try:
        with wave.open(str(path), 'rb') as audio:
            count = audio.getnframes()
            if (audio.getparams()[:3] != (1, 2, RATE) or audio.getcomptype() != 'NONE'
                    or count <= 0):
                raise ValueError('expected nonempty 48kHz mono PCM16 speech')
            data = audio.readframes(count+1)  # Also expose a data chunk ending mid-sample.
            if len(data) != count*2:
                raise ValueError('truncated PCM speech')
    except (wave.Error, EOFError) as error:
        raise ValueError(f'invalid PCM speech: {path}') from error
    samples = array('h')
    samples.frombytes(data)
    if sys.byteorder != 'little':
        samples.byteswap()
    if max(abs(s) for s in samples) <= SILENCE_THRESHOLD:
        raise ValueError(f'all-silent speech: {path}')
    leading = trailing = 0
    while leading < count and abs(samples[leading]) <= SILENCE_THRESHOLD:
        leading += 1
    while trailing < count and abs(samples[count-trailing-1]) <= SILENCE_THRESHOLD:
        trailing += 1
    # Never attenuate a non-silent tail or shorten the waveform.
    for i in range(min(FADE_SAMPLES, leading)):
        samples[i] = round(samples[i] * i / FADE_SAMPLES)
    for i in range(min(FADE_SAMPLES, trailing)):
        samples[count-1-i] = round(samples[count-1-i] * i / FADE_SAMPLES)
    return samples, leading, trailing


def _write_silence(audio, count):
    while count:
        step = min(count, 65536)
        audio.writeframesraw(b'\0\0'*step)
        count -= step


def assemble_narration(plan, audio_paths, target, *, target_rms_db=-20):
    units = plan['units']
    if not units or set(audio_paths) != {u['unit_id'] for u in units}:
        raise ValueError('audio must match every speech unit exactly')
    if target_rms_db is not None and (type(target_rms_db) not in (int,float)
            or not math.isfinite(target_rms_db) or not -60 <= target_rms_db <= 0):
        raise ValueError('target RMS must be None or finite -60..0 dBFS')
    target = Path(target).absolute()
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    spool = target.with_name(f'.{target.name}-{uuid4().hex}.tmp')
    final = target.with_name(f'.{target.name}-{uuid4().hex}.tmp')
    clips, cursor, energy, peak, added_total = [], 0, 0, 0, 0
    try:
        current = _read_unit(audio_paths[units[0]['unit_id']])
        with wave.open(str(spool), 'wb') as audio:
            audio.setparams((1,2,RATE,0,'NONE',''))
            for i, unit in enumerate(units):
                following = _read_unit(audio_paths[units[i+1]['unit_id']]) if i+1 < len(units) else None
                samples, leading, trailing = current
                count = len(samples)
                desired = unit['pause_after_ms']*RATE//1000 if following else 0
                added = max(0, desired-trailing-following[1]) if following else 0
                audio.writeframesraw(_pcm_bytes(samples))
                _write_silence(audio, added)
                energy += sum(s*s for s in samples)
                peak = max(peak, max(abs(s) for s in samples))
                clips.append(dict(unit, audio_path=str(Path(audio_paths[unit['unit_id']]).absolute()),
                    samples=count, start_sample=cursor, end_sample=cursor+count,
                    leading_silence_samples=leading, trailing_silence_samples=trailing,
                    added_pause_samples=added, pause_end_sample=cursor+count+added))
                cursor += count+added
                added_total += added
                current = following
        rms = math.sqrt(energy/cursor)
        gain = (min(10**(target_rms_db/20)*32768/rms, .95*32767/peak)
                if target_rms_db is not None else 1.)
        # This second pass is the required gain operation, not a second validation.
        with wave.open(str(spool), 'rb') as source, wave.open(str(final), 'wb') as output:
            output.setparams((1,2,RATE,0,'NONE',''))
            while data := source.readframes(65536):
                if gain == 1.:
                    output.writeframesraw(data)
                    continue
                samples = array('h'); samples.frombytes(data)
                if sys.byteorder != 'little': samples.byteswap()
                output.writeframesraw(_pcm_bytes(array('h', (round(s*gain) for s in samples))))
        with final.open('r+b') as file:
            os.fsync(file.fileno())
        result = dict(schema_version=1, status='completed', alignment=plan['alignment'],
            source_text=plan['source_text'], source_sha256=plan['source_sha256'], voice=plan['voice'],
            audio_path=str(target), sample_rate=RATE, channels=1, sample_width=2,
            total_samples=cursor, total_unit_samples=cursor-added_total,
            added_pause_samples=added_total, clips=clips, skips=plan['skips'],
            postprocess=dict(mode='whole-program-rms-gain' if target_rms_db is not None else 'none',
                target_rms_db=target_rms_db, input_rms_db=20*math.log10(rms/32768),
                gain=gain, peak_ceiling=.95, fade_ms=3, denoise=False, trimmed_samples=0))
        # Prepare metadata before publication, so errors cannot leave a completed WAV.
        # A hard link publishes atomically and fails if another writer won the name.
        os.link(final, target)
        return result
    finally:
        spool.unlink(missing_ok=True)
        final.unlink(missing_ok=True)
