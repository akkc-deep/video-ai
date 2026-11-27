"""TTS-VOX-01: offline CUDA load and one finite Chinese generation.

Run with the dedicated shared/envs/voxcpm2 interpreter after bootstrap.ps1.
This experiment does not participate in make-video or claim listening acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback
import wave

SOURCE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE_ROOT / 'src'))
from video_ai.runtime.storage import VideoStorage


def write_json(path, value):
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--text', default='旅行者一号从地球出发，飞向遥远的星际空间。即使相隔数百亿公里，它仍在向我们传回宇宙的消息。')
    parser.add_argument('--instruction', default='成年男性，沉稳自然，具有纪录片叙事感')
    parser.add_argument('--reference-audio', type=Path, help='Only use a reference you are authorized to use.')
    args = parser.parse_args()
    if not args.text.strip():
        parser.error('text must not be empty')
    if args.reference_audio and not args.reference_audio.is_file():
        parser.error('reference audio does not exist')

    storage = VideoStorage()
    root = storage.runtime_root
    output = root / 'scratch' / 'benchmarks' / 'TTS-VOX-01' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output.mkdir(parents=True, exist_ok=False)
    specification = json.loads((SOURCE_ROOT / 'config/voxcpm2-deployment.json').read_text(encoding='utf-8'))
    # All inference assets are local. Never download normalization or denoising models.
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    started = time.perf_counter()
    report = {
        'schema_version': 1, 'task_id': 'TTS-VOX-01', 'status': 'running',
        'started_at': datetime.now(timezone.utc).isoformat(),
        'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
        'runtime_root': str(root), 'specification': specification,
        'text': args.text, 'instruction': args.instruction,
        'reference_audio': str(args.reference_audio.resolve()) if args.reference_audio else None,
        'subjective_listening': 'unverified_TTS-VOX-02',
    }
    write_json(output / 'result.json', report)
    print(f'Evidence: {output}', flush=True)
    try:
        import numpy as np
        import soundfile as sf
        import torch
        from voxcpm import VoxCPM

        if not torch.cuda.is_available():
            raise RuntimeError('This experiment requires a real CUDA GPU; CPU fallback is disabled')
        if not torch.cuda.is_bf16_supported():
            raise RuntimeError('This experiment requires BF16 support')
        report['packages'] = {name: importlib.metadata.version(name) for name in
            ('voxcpm', 'torch', 'torchaudio', 'transformers', 'numpy', 'librosa', 'soundfile',
             'huggingface-hub', 'pydantic', 'einops', 'safetensors')}
        report['gpu'] = {
            'name': torch.cuda.get_device_name(0), 'capability': list(torch.cuda.get_device_capability(0)),
            'cuda': torch.version.cuda, 'bf16_supported': True,
            'total_memory_bytes': torch.cuda.get_device_properties(0).total_memory,
            'driver': subprocess.check_output(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'],
                                               text=True, timeout=15).strip(),
        }
        source = root / 'shared/tools/VoxCPM'
        report['source_revision_actual'] = subprocess.check_output(
            ['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True, timeout=15).strip()
        if report['source_revision_actual'] != specification['source_revision']:
            raise RuntimeError('Deployed source revision differs from the frozen specification')
        model_path = root / 'shared/models/VoxCPM2'
        torch.cuda.reset_peak_memory_stats()
        load_start = time.perf_counter()
        model = VoxCPM.from_pretrained(str(model_path), local_files_only=True,
            load_denoiser=specification['load_denoiser'], optimize=specification['optimize'],
            device=specification['device'])
        torch.cuda.synchronize()
        report['model_load_seconds'] = time.perf_counter() - load_start
        report['model_device'] = str(next(model.tts_model.parameters()).device)
        report['model_dtype'] = str(next(model.tts_model.base_lm.parameters()).dtype)
        if report['model_dtype'] != 'torch.bfloat16' or not report['model_device'].startswith('cuda:'):
            raise RuntimeError('Expected BF16 model on CUDA')
        print(f'Model loaded in {report["model_load_seconds"]:.2f}s', flush=True)
        generate_text = f'({args.instruction}){args.text}' if args.instruction else args.text
        report['synthesis_text'] = generate_text
        generation_start = time.perf_counter()
        with torch.inference_mode():
            wav = model.generate(text=generate_text,
                reference_wav_path=str(args.reference_audio.resolve()) if args.reference_audio else None,
                **specification['generation'])
        torch.cuda.synchronize()
        report['generation_seconds'] = time.perf_counter() - generation_start
        if wav.ndim != 1 or not wav.size or not np.isfinite(wav).all() or not np.any(wav):
            raise ValueError('Model returned invalid or silent audio')
        sample_rate = model.tts_model.sample_rate
        temporary = output / 'sample.partial.wav'
        sf.write(str(temporary), wav, sample_rate, subtype='PCM_16')
        # One header read verifies the written sample count and format, without decoding again.
        with wave.open(str(temporary), 'rb') as audio:
            audio_info = dict(sample_rate=audio.getframerate(), channels=audio.getnchannels(),
                              sample_count=audio.getnframes(), sample_width=audio.getsampwidth())
        if (audio_info['sample_count'] != wav.size or audio_info['channels'] != 1
                or audio_info['sample_width'] != 2 or audio_info['sample_rate'] != sample_rate):
            raise ValueError('Written PCM WAV differs from model output')
        temporary.replace(output / 'sample.wav')
        duration = wav.size / sample_rate
        report.update(status='completed', audio_path=str(output / 'sample.wav'), audio=audio_info,
            duration_seconds=duration, rtf=report['generation_seconds'] / duration,
            peak_allocated_bytes=torch.cuda.max_memory_allocated(),
            peak_reserved_bytes=torch.cuda.max_memory_reserved())
        # Freeze this environment once per experiment, not once per audio segment.
        frozen = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze', '--all'], text=True, timeout=60)
        (output / 'environment.freeze.txt').write_text(frozen, encoding='utf-8')
        report['environment_freeze'] = str(output / 'environment.freeze.txt')
        print(json.dumps({k: report[k] for k in ('status', 'audio_path', 'duration_seconds', 'generation_seconds', 'rtf')},
                         ensure_ascii=False), flush=True)
    except Exception as error:
        report.update(status='failed', error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        report['elapsed_seconds'] = time.perf_counter() - started
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(output / 'result.json', report)


if __name__ == '__main__':
    main()
