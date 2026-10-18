import json
import pytest
from http_helpers import Response, ScriptedTransport


def make_client(runtime_run, handler):
    from video_ai.adapters.common import HttpClient
    from video_ai.adapters.tts import TtsClient
    from video_ai.runtime.logging import RunLogger
    run, config, _ = runtime_run
    transport = ScriptedTransport(handler)
    return TtsClient(HttpClient(config.services['tts'], 1, RunLogger(run), transport=transport), config.voice), transport


def test_fixed_payload_verbatim(runtime_run):
    body = b'RIFFxxxxWAVEdata'
    client, transport = make_client(runtime_run, lambda r,t: Response(body, headers={'Content-Type':'Audio/Wav; charset=binary'}))
    assert client.synthesize(' 原文🙂，', unit_id='speech_0001').body == body
    method, url, raw, timeout = transport.calls[0]
    voice = runtime_run[1].voice
    expected = dict(voice.inference, text=' 原文🙂，', text_lang=voice.text_language,
                    ref_audio_path=str(voice.reference_audio), prompt_text=voice.reference_text,
                    prompt_lang=voice.prompt_language, speed_factor=voice.speed_factor)
    assert json.loads(raw) == expected and method == 'POST' and url.endswith('/tts')


@pytest.mark.parametrize('text', ['', ' \r\n', '，。！？'])
def test_skip_zero_posts(runtime_run, text):
    client, transport = make_client(runtime_run, lambda r,t: Response())
    with pytest.raises(ValueError): client.synthesize(text, unit_id='speech_0001')
    assert not transport.calls


@pytest.mark.parametrize('failure,kind', [('disconnect','ambiguous'), ('timeout','ambiguous'), ('500','ambiguous'), ('400','explicit'), ('html','invalid_result'), ('empty','invalid_result'), ('json','invalid_result')])
def test_once_with_failure_evidence(runtime_run, failure, kind):
    from video_ai.adapters.common import AdapterError
    def handler(r, t):
        if failure == 'disconnect': raise ConnectionResetError('lost')
        if failure == 'timeout': raise TimeoutError('deadline')
        if failure in ('400','500'): return Response({'error':'bad'}, int(failure))
        if failure == 'html': return Response(b'<html>', headers={'content-type':'text/html'})
        if failure == 'empty': return Response(b'', headers={'content-type':'audio/wav'})
        return Response(b'{}', headers={'content-type':'audio/wav'})
    client, transport = make_client(runtime_run, handler)
    with pytest.raises(AdapterError) as error: client.synthesize('原文。', unit_id='speech_0001')
    assert error.value.kind.value == kind and len(transport.calls) == 1
    assert error.value.evidence_paths and all(p.exists() for p in error.value.evidence_paths)
