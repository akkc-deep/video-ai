"""Durable guide removal before any alignment of delivered original speech."""
from io import BytesIO
from pathlib import Path
import wave

from ..media.narration_guard import remove_spoken_guard
from ..voxcpm.contracts import fingerprint
from .manifest import thaw
from .production_support import stamps
from .storage_files import write_record


def prepare_guarded_bodies(frozen, plan, outputs, *, logger):
    from .production_vox_speech import _receipt, _atomic_audio
    profile = thaw(frozen.config.tts.narration)['onset_guard']
    result = {}
    for paragraph in plan:
        uid = paragraph['unit_id']; directory = logger.run_dir/'production/vox'/uid
        identity = fingerprint(dict(paragraph=paragraph, guard=profile,
                                    input=stamps(dict(processed=outputs[uid]))))
        receipt = _receipt(directory/'body.json', identity)
        if receipt is None:
            with wave.open(str(outputs[uid]), 'rb') as source:
                if source.getparams()[:3] != (1,2,48000):
                    raise ValueError('guard removal requires 48kHz mono PCM16')
                original = source.readframes(source.getnframes())
            try:
                pcm, metadata = remove_spoken_guard(original, profile)
            except ValueError as exc:
                raise ValueError(f'{uid}: {exc}') from exc
            buffer = BytesIO()
            with wave.open(buffer, 'wb') as destination:
                destination.setparams((1,2,48000,0,'NONE','')); destination.writeframes(pcm)
            target = directory/'body.wav'
            _atomic_audio(target, buffer.getvalue())
            receipt = dict(identity=identity, outputs=stamps(dict(pcm=target)), metadata=metadata)
            write_record(directory/'body.json', receipt)
        result[uid] = Path(receipt['outputs']['pcm']['path'])
    return result
