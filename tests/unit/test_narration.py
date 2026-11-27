from array import array
from pathlib import Path
import struct
import wave

import pytest


def wav(path, samples, *, rate=48000):
    with wave.open(str(path), 'wb') as f:
        f.setparams((1, 2, rate, 0, 'NONE', ''))
        f.writeframes(array('h', samples).tobytes())
    return path


def read_pcm(path):
    with wave.open(str(path), 'rb') as f:
        samples = array('h')
        samples.frombytes(f.readframes(f.getnframes()))
        return samples


def speech_plan(runtime_run, text='第一句。第二句。'):
    from test_speech_plan import profile, plan_for
    from video_ai.planning.speech import plan_speech
    return plan_speech(plan_for(text), profile(runtime_run))


def test_actual_samples_and_existing_silence_only_top_up(runtime_run, tmp_path):
    from video_ai.media.narration import assemble_narration
    plan = speech_plan(runtime_run)
    # 220ms target; 100ms trailing + 50ms leading => only 70ms added.
    first = [1000]*4800 + [0]*4800
    second = [0]*2400 + [-1000]*4800
    paths = dict(speech_0001=wav(tmp_path/'one.wav', first), speech_0002=wav(tmp_path/'two.wav', second))
    target = tmp_path/'narration.wav'
    result = assemble_narration(plan, paths, target, target_rms_db=None)
    assert result['total_samples'] == 9600+7200+3360
    assert len(read_pcm(target)) == result['total_samples']
    assert result['clips'][0]['added_pause_samples'] == 3360
    assert result['clips'][1]['start_sample'] == 12960
    assert result['clips'][1]['end_sample'] == 20160
    assert result['clips'][0]['original_text'] == '第一句。'
    assert result['clips'][0]['trailing_silence_samples'] == 4800
    assert result['clips'][1]['leading_silence_samples'] == 2400
    assert list(read_pcm(target)) == first + [0]*3360 + second


def test_no_extra_pause_when_model_silence_is_longer_and_tail_preserved(runtime_run, tmp_path):
    from video_ai.media.narration import assemble_narration
    plan = speech_plan(runtime_run)
    first = [1000]*4800+[0]*12000
    second = [1000]*4799+[1234]  # Last nonzero tail must survive, no unconditional fade.
    paths = dict(speech_0001=wav(tmp_path/'a.wav', first), speech_0002=wav(tmp_path/'b.wav', second))
    target = tmp_path/'result.wav'
    result = assemble_narration(plan, paths, target, target_rms_db=None)
    assert result['clips'][0]['added_pause_samples'] == 0
    assert list(read_pcm(target)) == first+second
    assert result['total_samples'] == len(first)+len(second)


def test_whole_program_gain_is_one_constant_and_peak_limited(runtime_run, tmp_path):
    from video_ai.media.narration import assemble_narration
    plan = speech_plan(runtime_run)
    paths = dict(speech_0001=wav(tmp_path/'a.wav', [1000,-1000]*2400),
                 speech_0002=wav(tmp_path/'b.wav', [10000,-10000]*2400))
    target = tmp_path/'result.wav'
    result = assemble_narration(plan, paths, target, target_rms_db=-5)
    data = read_pcm(target)
    assert data[0] == round(1000*result['postprocess']['gain'])
    assert data[-1] == round(-10000*result['postprocess']['gain'])
    assert max(abs(x) for x in data) <= round(32767*.95)
    assert result['postprocess']['mode'] == 'whole-program-rms-gain'
    assert len(data) == result['total_samples']


@pytest.mark.parametrize('damage', ['missing', 'extra', 'truncated', 'partial_sample', 'wrong_rate', 'silent', 'exists'])
def test_bad_or_incomplete_audio_never_publishes(runtime_run, tmp_path, damage):
    from video_ai.media.narration import assemble_narration
    plan = speech_plan(runtime_run)
    a, b = wav(tmp_path/'a.wav', [1000]*4800), wav(tmp_path/'b.wav', [1000]*4800)
    paths = dict(speech_0001=a, speech_0002=b)
    target = tmp_path/'result.wav'
    if damage == 'missing': paths.pop('speech_0002')
    if damage == 'extra': paths['speech_0003'] = b
    if damage == 'truncated': b.write_bytes(b.read_bytes()[:-10])
    if damage == 'partial_sample':
        body = (b'fmt '+struct.pack('<IHHIIHH',16,1,1,48000,96000,2,16)
                +b'data'+struct.pack('<I',5)+struct.pack('<hh',1000,2000)+b'\x7f\0')
        b.write_bytes(b'RIFF'+struct.pack('<I',4+len(body))+b'WAVE'+body)
    if damage == 'wrong_rate': wav(b, [1000]*4800, rate=24000)
    if damage == 'silent': wav(b, [0]*4800)
    if damage == 'exists': target.write_bytes(b'existing')
    with pytest.raises((ValueError, FileExistsError)):
        assemble_narration(plan, paths, target)
    assert target.read_bytes() == b'existing' if damage == 'exists' else not target.exists()
    assert not list(tmp_path.glob('*.tmp'))


def test_no_speech_in_plan_is_error(tmp_path):
    from video_ai.media.narration import assemble_narration
    with pytest.raises(ValueError): assemble_narration({'units': []}, {}, tmp_path/'empty.wav')


def test_missing_result_metadata_cannot_publish_audio(runtime_run, tmp_path):
    from video_ai.media.narration import assemble_narration
    plan = speech_plan(runtime_run)
    plan.pop('alignment')
    paths = dict(speech_0001=wav(tmp_path/'a.wav', [1000]*4800),
                 speech_0002=wav(tmp_path/'b.wav', [1000]*4800))
    target = tmp_path/'result.wav'
    with pytest.raises((KeyError, ValueError)): assemble_narration(plan, paths, target)
    assert not target.exists()
    assert not list(tmp_path.glob('*.tmp'))
