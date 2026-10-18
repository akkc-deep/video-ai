"""Lossless, bounded-memory PCM materialization for the production timeline."""
import os
from pathlib import Path
import wave

from ..planning.production_timeline import validate_production_timeline
from ..runtime.production_state import ArtifactStamp

BLOCK_SAMPLES = 65536


def write_production_narration(timeline, target):
    """Copy every original PCM sample and insert only canonical timeline silence."""
    validate_production_timeline(timeline)
    target = Path(target)
    for clip in timeline.clips:
        clip.pcm.stamp.verify()
    samples = timeline.total_frames * 3000
    clips = []
    silence_block = bytes(BLOCK_SAMPLES * 2)
    with target.open('xb') as raw:
        with wave.open(raw, 'wb') as output:
            output.setparams((1, 2, 48000, 0, 'NONE', ''))
            cursor = 0
            def silence(count):
                while count:
                    size = min(BLOCK_SAMPLES, count)
                    output.writeframesraw(silence_block[:size * 2]); count -= size
            for clip in timeline.clips:
                clip.pcm.stamp.verify()
                silence(clip.start_sample - cursor)
                with wave.open(str(clip.pcm.path), 'rb') as source:
                    if (source.getframerate(), source.getnchannels(), source.getsampwidth(), source.getcomptype()) != (48000, 1, 2, 'NONE'):
                        raise ValueError('expected original 48kHz mono PCM16')
                    if source.getnframes() != clip.samples:
                        raise ValueError('original PCM sample count differs')
                    remaining = clip.samples
                    while remaining:
                        size = min(BLOCK_SAMPLES, remaining)
                        block = source.readframes(size)
                        if len(block) != size * 2:
                            raise ValueError('original PCM is truncated')
                        output.writeframesraw(block); remaining -= size
                    if source.readframes(1): raise ValueError('original PCM has extra samples')
                clip.pcm.stamp.verify()
                clips.append(dict(unit_id=clip.unit_id, start_sample=clip.start_sample,
                    end_sample=clip.end_sample, samples=clip.samples, pcm=clip.pcm.stamp.to_dict()))
                cursor = clip.end_sample
            silence(samples - cursor)
        raw.flush(); os.fsync(raw.fileno())
    for clip in timeline.clips:
        clip.pcm.stamp.verify()
    return dict(stamp=ArtifactStamp.read(target).to_dict(), samples=samples,
        speech_samples=timeline.total_speech_samples, silence_samples=timeline.total_silence_samples,
        padding_samples=timeline.video_padding_samples, clips=clips)
