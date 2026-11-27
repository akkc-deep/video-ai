"""Small listening comparison for natural, stable male documentary narration.

Run with the dedicated VoxCPM2 interpreter after bootstrap. This experiment
does not change production segmentation, alignment or the selected voice.
"""
from datetime import datetime
import hashlib
import os
from pathlib import Path
import sys
import time
import traceback

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE/'src'))
from video_ai.config import read_json
from video_ai.runtime.storage import VideoStorage
from video_ai.runtime.storage_files import safe_path, write_record
from voxcpm2_sleep_voice import verify_design_source


def main():
    root = VideoStorage().runtime_root
    tag = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output = root/'scratch/benchmarks/TTS-VOX-06-natural-voice'/tag
    output.mkdir(parents=True)
    report = dict(task_id='TTS-VOX-06-natural-voice', status='running', output=str(output),
        feedback='声音不够稳，不够自然', listening_status='pending_user', samples={})
    try:
        os.environ['HF_HUB_OFFLINE'] = os.environ['TRANSFORMERS_OFFLINE'] = '1'
        spec = read_json(SOURCE/'config/voxcpm2-deployment.json')
        report['source_revision'] = verify_design_source(root, spec)
        report['model_revision'] = spec['model_revision']
        previous = read_json(root/'shared/config/tts/male-sleep-documentary.json')
        previous_profile = safe_path(root/previous['voice_profile'], root)
        previous_asset = read_json(previous_profile)
        reference = safe_path(previous_profile.parent/previous_asset['reference_audio'], root)
        if hashlib.sha256(reference.read_bytes()).hexdigest() != previous_asset['reference_sha256']:
            raise ValueError('previous voice reference identity differs')
        import numpy as np
        import soundfile as sf
        import torch
        from voxcpm import VoxCPM
        from video_ai.voxcpm.contracts import wav_metadata
        if not torch.cuda.is_available():
            raise RuntimeError('listening comparison requires the real CUDA model')
        model = VoxCPM.from_pretrained(str(root/'shared/models/VoxCPM2'), local_files_only=True,
            load_denoiser=spec['load_denoiser'], optimize=spec['optimize'], device=spec['device'])
        parameters = dict(spec['generation'], inference_timesteps=20)
        # The same source is one model call in A and B. No sentence-by-sentence
        # resampling, inserted gaps, pitch shifting or time stretching.
        text = ('当夜幕落下，白天的喧嚣渐渐远去，森林开始显露出另一种安静的模样。'
                '月光越过山脊，落在缓缓流动的河面上，像一层柔和的银色薄纱。'
                '在我们看不见的远方，星光已经穿过漫长的岁月，才来到这片夜空。')
        report.update(source_text=text, parameters=parameters,
            comparison_type='Listening alternatives, not a single-variable causal benchmark',
            alignment='whole-paragraph-only; no inferred sentence or word timestamps')

        def render(name, synthesis_text, **conditioning):
            print('Generating '+name, flush=True)
            started = time.monotonic()
            with torch.inference_mode():
                samples = model.generate(text=synthesis_text, **conditioning, **parameters)
            torch.cuda.synchronize()
            elapsed = time.monotonic()-started
            if (samples.ndim != 1 or not samples.size or not np.isfinite(samples).all()
                    or float(np.max(np.abs(samples))) <= 32/32768):
                raise ValueError('invalid or silent generated sample: '+name)
            path = output/(name+'.wav')
            sf.write(str(path), samples, model.tts_model.sample_rate, subtype='PCM_16')
            report['samples'][name] = dict(path=str(path), generation_seconds=elapsed,
                audio=wav_metadata(path), duration_seconds=len(samples)/model.tts_model.sample_rate,
                synthesis_text=synthesis_text, conditioning=conditioning)
            write_record(output/'result.json', report)
            return path

        render('A-simple-continuous', '(平静自然的男声旁白)'+text, reference_wav_path=str(reference))
        direction = '一位成年男性，普通话标准，音色平实温和，像专业纪录片旁白，自然连贯地讲述'
        reference_text = ('入夜之后，山林渐渐安静下来。河水沿着山谷缓缓流淌，'
                          '远处的灯光映在水面上。我们继续向前，听风吹过树梢，'
                          '看星光一点一点出现在天空。')
        new_reference = render('reference-v2', f'({direction}){reference_text}')
        # Official reference+prompt cloning preserves the reference's delivery.
        # prompt_text is the intended generated reference transcript; it has not
        # been independently transcribed or certified by this experiment.
        render('B-natural-continuation', text, reference_wav_path=str(new_reference),
               prompt_wav_path=str(new_reference), prompt_text=reference_text)
        asset_dir = root/'shared/assets/voices'/('male-natural-documentary-v2-'+tag)
        asset_dir.mkdir(parents=True, exist_ok=False)
        data = new_reference.read_bytes()
        (asset_dir/'reference.wav').write_bytes(data)
        profile = dict(schema_version=1, voice_id='male-natural-documentary-v2', reference_audio='reference.wav',
            reference_sha256=hashlib.sha256(data).hexdigest(), base_style='平静自然的男声纪录片旁白',
            intended_gender='male', purpose='male_documentary_sleep_narration', listening_status='pending_user',
            provenance=dict(method='voxcpm2-voice-design', design_direction=direction,
                reference_text=reference_text, transcript_verification='intended text only; not independently transcribed',
                model_revision=spec['model_revision'], source_revision=report['source_revision'], generation=parameters))
        write_record(asset_dir/'voice.json', profile)
        report.update(status='generated_pending_listening', candidate_voice_profile=str(asset_dir/'voice.json'),
            preference_updated=False, notes=['A reuses v1 timbre with a short instruction and one continuous paragraph',
                'B uses a newly designed plain male reference with reference+prompt continuation, no style prefix',
                '20 diffusion steps are an audition setting, not a new production default',
                'No subjective stability/naturalness result is inferred; no production alignment changes'])
    except BaseException:
        report.update(status='failed', error=traceback.format_exc())
        raise
    finally:
        write_record(output/'result.json', report)
        print(str(output), flush=True)


if __name__ == '__main__':
    main()
