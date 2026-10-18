from dataclasses import replace
from pathlib import Path
import wave
import pytest


def media_config(runtime_run):
    run, config, paths = runtime_run
    tools = dict(config.tools, ffmpeg=Path('D:/VideoSi/tools/ffmpeg/bin/ffmpeg.exe'), ffprobe=Path('D:/VideoSi/tools/ffmpeg/bin/ffprobe.exe'))
    return run, replace(config, tools=tools), paths


def write_wav(path, *, rate=24000, channels=2, frames=6000):
    with wave.open(str(path), 'wb') as f:
        f.setparams((channels, 2, rate, 0, 'NONE', 'not compressed'))
        f.writeframes(b'\x12\x03' * channels * frames)


@pytest.mark.parametrize('rate,channels', [(24000,2),(44100,1),(48000,2)])
def test_real_standardization_preserves_duration(runtime_run, rate, channels):
    from video_ai.media.audio import standardize_wav, SpeechLimits
    from video_ai.runtime.logging import RunLogger
    run, config, paths = media_config(runtime_run)
    raw, pcm = run/'raw.wav', run/'pcm.wav'
    write_wav(raw, rate=rate, channels=channels, frames=rate//4)
    before = raw.read_bytes()
    info = standardize_wav(raw, pcm, config=config, paths=paths, logger=RunLogger(run), unit_id='speech_0001', limits=SpeechLimits())
    assert (info.samples, info.sample_rate, info.channels, info.sample_width) == (12000,48000,1,2)
    assert info.duration == .25 and raw.read_bytes() == before
    with pytest.raises(FileExistsError):
        standardize_wav(raw, pcm, config=config, paths=paths, logger=RunLogger(run), unit_id='speech_0001', limits=SpeechLimits())


@pytest.mark.parametrize('bad', ['empty','header','truncated','short','long'])
def test_bad_audio_never_accepted(runtime_run, bad):
    from video_ai.media.audio import standardize_wav, SpeechLimits
    from video_ai.runtime.logging import RunLogger
    run, config, paths = media_config(runtime_run)
    raw, pcm = run/'raw.wav', run/'pcm.wav'
    write_wav(raw, frames=10 if bad == 'short' else 6000)
    if bad == 'empty': raw.write_bytes(b'')
    if bad == 'header': raw.write_bytes(b'not wav')
    if bad == 'truncated': raw.write_bytes(raw.read_bytes()[:-1000])
    before = raw.read_bytes()
    with pytest.raises((ValueError, RuntimeError, OSError)):
        standardize_wav(raw, pcm, config=config, paths=paths, logger=RunLogger(run), unit_id='speech_0001', limits=SpeechLimits(max_seconds=.1 if bad=='long' else 120))
    assert raw.read_bytes() == before


@pytest.mark.parametrize('minimum,maximum', [(0,1),(1,0),(float('nan'),1),(1,float('inf')),(True,2)])
def test_limits_invalid(minimum, maximum):
    from video_ai.media.audio import SpeechLimits
    with pytest.raises(ValueError): SpeechLimits(minimum, maximum)
