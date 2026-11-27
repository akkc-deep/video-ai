"""A serial stage facade; production persistence/recovery is owned by TTS-VOX-07."""
from pathlib import Path
from types import MappingProxyType

from .voxcpm import VoxTtsClient
from ..media.narration import assemble_narration
from ..planning.speech import validate_speech_plan
from ..runtime.storage_files import write_record
from ..tts_config import TtsSettings


class LongFormSynthesizer:
    def __init__(self, http, voice, *, request_scope):
        self.voice = voice
        self.client = VoxTtsClient(http, TtsSettings('voxcpm2', voice.model_revision, voice.parameters),
            reference_sha256=voice.reference_sha256, request_scope=request_scope)

    def synthesize(self, plan, output_dir):
        validate_speech_plan(plan, self.voice)
        output = Path(output_dir).absolute()
        output.mkdir(parents=True, exist_ok=False)
        write_record(output/'speech-plan.json', plan)
        segments = output/'segments'; segments.mkdir()
        requests = output/'requests'; requests.mkdir()
        audio_paths, identities = {}, {}
        for unit in plan['units']:
            parameters = dict(self.voice.parameters, emotion=unit['emotion'],
                emotion_intensity=unit['emotion_intensity'], instruction=unit['instruction'])
            # One serial client retains its once-per-stage model/reference check.
            self.client.settings = TtsSettings('voxcpm2', self.voice.model_revision, MappingProxyType(parameters))
            identity = self.client.request_id(unit['unit_id'])
            write_record(requests/(unit['unit_id']+'.json'), dict(request_id=identity, unit=unit,
                voice_identity=plan['voice']['identity']))
            response = self.client.synthesize(unit['synthesis_text'], unit_id=unit['unit_id'])
            path = segments/(unit['unit_id']+'.wav')
            with path.open('xb') as file:
                file.write(response.body)
            audio_paths[unit['unit_id']], identities[unit['unit_id']] = path, identity
        result = assemble_narration(plan, audio_paths, output/'narration.wav')
        for clip in result['clips']:
            clip['request_id'] = identities[clip['unit_id']]
        try:
            write_record(output/'tts-result.json', result)
        except BaseException:
            (output/'narration.wav').unlink(missing_ok=True)
            raise
        return result
