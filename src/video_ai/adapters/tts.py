"""One finite GPT-SoVITS request with the run's fixed voice."""
from .common import AdapterError, FailureKind, HttpClient, HttpResponse
from ..config import VoiceConfig
from ..planning.segments import speakable
from ..runtime.manifest import validate_unit


class TtsClient:
    def __init__(self, http: HttpClient, voice: VoiceConfig):
        self.http, self.voice = http, voice

    def payload(self, text: str) -> dict:
        if not isinstance(text, str) or not speakable(text):
            raise ValueError('TTS requires original speech text')
        voice = self.voice
        payload = dict(voice.inference)
        if (payload.get('batch_size') != 1 or payload.get('streaming_mode') is not False
                or payload.get('media_type') != 'wav'):
            raise ValueError('TTS requires batch one, nonstreaming WAV')
        payload.update(text=text, text_lang=voice.text_language, ref_audio_path=str(voice.reference_audio),
                       prompt_text=voice.reference_text, prompt_lang=voice.prompt_language, speed_factor=voice.speed_factor)
        return payload

    def synthesize(self, text: str, *, unit_id: str) -> HttpResponse:
        validate_unit('speech', unit_id)
        response = self.http.request('POST', '/tts', json_body=self.payload(text), max_bytes=64*1024*1024,
                                     stage='speech', unit_id=unit_id)
        media = next((v for k,v in response.headers.items() if k.lower() == 'content-type'), '').split(';')[0].strip().lower()
        if (media not in {'', 'audio/wav', 'audio/x-wav', 'application/octet-stream'}
                or len(response.body) < 12 or response.body[:4] != b'RIFF' or response.body[8:12] != b'WAVE'):
            raise AdapterError(FailureKind.invalid_result, 'TTS response is not a WAV body', (response.evidence_path,))
        return response
