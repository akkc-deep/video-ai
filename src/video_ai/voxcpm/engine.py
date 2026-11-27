"""Locked offline CUDA backend. Imported only in the dedicated inference thread."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from ..runtime.storage_files import safe_path


def load_assets(runtime_root, state_dir, *, voice_profile=None):
    root = Path(runtime_root)
    if voice_profile is not None:
        from .voices import load_voice_asset
        asset = load_voice_asset(voice_profile, root)
        reference, expected_digest, voice_id = asset.reference_audio, asset.reference_sha256, asset.voice_id
    else:
        config = json.loads((root/'shared/config/production.json').read_text(encoding='utf-8-sig'))
        voice = json.loads(Path(config['voice_config']).read_text(encoding='utf-8-sig'))
        reference = safe_path(Path(voice['reference_audio']).absolute(), root)
        expected_digest, voice_id = voice['reference_sha256'], 'existing-reference'
    data = reference.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_digest:
        raise ValueError('configured reference audio identity differs')
    reference_copy = safe_path(Path(state_dir)/'inputs'/f'{digest}.wav', Path(state_dir))
    reference_copy.parent.mkdir(parents=True, exist_ok=True)
    reference_copy.write_bytes(data)
    spec_path = Path(__file__).resolve().parents[3]/'config/voxcpm2-deployment.json'
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    binding = dict(voice_id=voice_id, reference_sha256=digest,
        model_revision=spec['model_revision'], source_revision=spec['source_revision'],
        generation=spec['generation'], device=spec['device'], optimize=spec['optimize'],
        load_denoiser=spec['load_denoiser'])
    return binding, lambda: VoxBackend(root, reference_copy, spec)


class VoxBackend:
    def __init__(self, root, reference, spec):
        os.environ['HF_HUB_OFFLINE'] = os.environ['TRANSFORMERS_OFFLINE'] = '1'
        import torch
        from voxcpm import VoxCPM
        if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
            raise RuntimeError('VoxCPM2 requires real CUDA with BF16')
        actual = subprocess.check_output(['git', '-C', str(root/'shared/tools/VoxCPM'),
                                         'rev-parse', 'HEAD'], text=True, timeout=15).strip()
        if actual != spec['source_revision']:
            raise RuntimeError('VoxCPM source differs from frozen deployment')
        self.reference, self.spec = reference, spec
        self.model = VoxCPM.from_pretrained(str(root/'shared/models/VoxCPM2'), local_files_only=True,
            load_denoiser=spec['load_denoiser'], optimize=spec['optimize'], device=spec['device'])

    def generate(self, request, temporary):
        import numpy as np
        import soundfile as sf
        import torch
        parameters = dict(self.spec['generation'])
        for key in ('seed', 'cfg_value', 'inference_timesteps'):
            parameters[key] = request[key]
        started = time.perf_counter()
        with torch.inference_mode():
            samples = self.model.generate(text=request['synthesis_text'],
                reference_wav_path=str(self.reference), **parameters)
        torch.cuda.synchronize()
        elapsed = (time.perf_counter() - started) * 1000
        if samples.ndim != 1 or not samples.size or not np.isfinite(samples).all() or not np.any(samples):
            raise ValueError('model returned invalid or silent audio')
        sf.write(str(temporary), samples, self.model.tts_model.sample_rate, subtype='PCM_16')
        with temporary.open('r+b') as file:
            os.fsync(file.fileno())
        return dict(generation_time_ms=elapsed, sample_count=int(samples.size),
                    sample_rate=self.model.tts_model.sample_rate)
