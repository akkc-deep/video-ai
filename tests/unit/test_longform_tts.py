import io
import json
from array import array
import wave

import pytest

from http_helpers import Response, ScriptedTransport
from test_tts_backends import Protocol, vox_config
from test_speech_plan import profile, plan_for


def client(runtime_run, protocol=None):
    from video_ai.adapters.common import HttpClient
    from video_ai.adapters.longform import LongFormSynthesizer
    from video_ai.runtime.logging import RunLogger
    config = vox_config(runtime_run[1])
    protocol = protocol or Protocol(config)
    original = protocol.__call__
    def request(req, timeout):
        if req.full_url.endswith('/audio'):
            out = io.BytesIO()
            with wave.open(out, 'wb') as f:
                f.setparams((1,2,48000,0,'NONE',''))
                f.writeframes(array('h', [1000]*4800).tobytes())
            return Response(out.getvalue(), headers={'content-type': 'audio/wav'})
        # This test protocol stores one task at a time; clear on a new unit GET.
        if '/tts/tasks/' in req.full_url and req.method == 'GET' and protocol.task:
            if not req.full_url.endswith(protocol.task['request_id']): protocol.task = None
        return original(req, timeout)
    transport = ScriptedTransport(request)
    http = HttpClient(config.services['tts'], 2, RunLogger(runtime_run[0]), transport=transport)
    return LongFormSynthesizer(http, profile(runtime_run), request_scope='revision-06'), protocol, transport


def test_serial_units_use_fixed_voice_seed_and_single_readiness_check(runtime_run, tmp_path):
    from video_ai.planning.speech import plan_speech
    from video_ai.planning.emotion import BASE_STYLE, make_plan
    synth, protocol, transport = client(runtime_run)
    text = '第一句。\r\n第二句。'
    rows = [dict(start=0,end=6,emotion='narrative',emotion_intensity=.3,tone='沉稳',pause_after_ms=450),
            dict(start=6,end=len(text),emotion='gentle',emotion_intensity=.5,tone='轻柔',pause_after_ms=0)]
    plan = plan_speech(make_plan(text, rows, BASE_STYLE), profile(runtime_run))
    result = synth.synthesize(plan, tmp_path/'audio')
    assert protocol.posts == 2
    assert sum(url.endswith('/health') for _,url,_,_ in transport.calls) == 1
    assert sum(url.endswith('/voices') for _,url,_,_ in transport.calls) == 1
    assert result['status'] == 'completed'
    assert len({c['request_id'] for c in result['clips']}) == 2
    payloads = [json.loads(body) for method,url,body,_ in transport.calls if method == 'POST']
    assert ''.join(p['text'] for p in payloads) == plan['source_text']
    assert all(p['seed'] == 42 and p['voice_id'] == 'existing-reference' for p in payloads)
    assert [p['emotion'] for p in payloads] == ['narrative', 'gentle']
    assert [p['emotion_intensity'] for p in payloads] == [.3,.5]
    assert payloads[-1]['instruction'] == profile(runtime_run).base_style+'，语气轻柔'
    assert json.loads((tmp_path/'audio/tts-result.json').read_text(encoding='utf-8')) == result
    with pytest.raises(FileExistsError): synth.synthesize(plan, tmp_path/'audio')


@pytest.mark.parametrize('damage', ['voice', 'seed', 'mapping', 'unit_id', 'order', 'spoken_skip', 'instruction', 'alignment'])
def test_plan_mutation_rejected_before_http(runtime_run, tmp_path, damage):
    from video_ai.planning.speech import plan_speech
    synth, _, transport = client(runtime_run)
    plan = plan_speech(plan_for('原文。第二句。'), profile(runtime_run))
    if damage == 'voice': plan['voice']['reference_sha256'] = 'bad'
    if damage == 'seed': plan['units'][0]['seed'] = 99
    if damage == 'mapping': plan['units'][0]['synthesis_text'] = '改写。'
    if damage == 'unit_id': plan['units'][0]['unit_id'] = '../bad'
    if damage == 'instruction': plan['units'][0]['instruction'] = 'new base style'
    if damage == 'alignment': plan.pop('alignment')
    if damage == 'order':
        plan['units'].reverse()
        for i, row in enumerate(plan['units'], 1): row['unit_id'] = f'speech_{i:04d}'
    if damage == 'spoken_skip':
        dropped = plan['units'].pop()
        plan['skips'].append(dict(start=dropped['start'], end=dropped['end'], original_text=dropped['original_text']))
    with pytest.raises(ValueError): synth.synthesize(plan, tmp_path/'audio')
    assert not transport.calls


def test_failed_request_does_not_publish_narration_or_success(runtime_run, tmp_path):
    from video_ai.adapters.common import AdapterError
    from video_ai.planning.speech import plan_speech
    protocol = Protocol(vox_config(runtime_run[1])); protocol.state = 'failed'
    synth, _, _ = client(runtime_run, protocol)
    plan = plan_speech(plan_for('原文。'), profile(runtime_run))
    with pytest.raises(AdapterError): synth.synthesize(plan, tmp_path/'audio')
    assert not (tmp_path/'audio/narration.wav').exists()
    assert not (tmp_path/'audio/tts-result.json').exists()
