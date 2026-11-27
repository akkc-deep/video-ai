"""Three slower paragraphs with one fixed male reference and prompt transcript.

Dedicated VoxCPM2 interpreter; no production timeline or backend changes.
"""
import argparse
from datetime import datetime
import hashlib
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE/'src'))
from video_ai.config import read_json
from video_ai.media.narration import assemble_narration
from video_ai.runtime.storage import VideoStorage
from video_ai.runtime.storage_files import write_record
from video_ai.voxcpm.voices import load_voice_asset
from voxcpm2_sleep_voice import verify_design_source


PARAGRAPHS = (
    '当夜幕落下，白天的喧嚣渐渐远去，森林开始显露出另一种安静的模样。'
    '月光越过山脊，落在缓缓流动的河面上，像一层柔和的银色薄纱。',
    '沿着河岸望去，远处的山峦只留下一道淡淡的轮廓。风穿过树梢，'
    '又轻轻落下。那些细微的声响，让这片安静的夜晚，显得更加悠长。',
    '再把目光移向天空，星光已经穿过漫长的岁月，才来到我们的眼前。'
    '此刻，不必急着寻找答案。让呼吸慢下来，随着这段平静的旅程，一点一点放松。',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--speed', type=float, default=.8, help='Pitch-preserving tempo, .65..1.0')
    parser.add_argument('--reuse-from', type=Path, help='Reuse this experiment raw WAVs for a tempo-only revision')
    parser.add_argument('--bass-db', type=float, default=0., help='Uniform low shelf, -6..0 dB')
    parser.add_argument('--pitch-semitones', type=float, default=0., help='Small formant-preserving lift, 0..1.5 semitones')
    args = parser.parse_args()
    if not .65 <= args.speed <= 1.:
        parser.error('--speed must be .65..1.0')
    if not -6 <= args.bass_db <= 0 or not 0 <= args.pitch_semitones <= 1.5:
        parser.error('--bass-db must be -6..0 and --pitch-semitones 0..1.5')
    root = VideoStorage().runtime_root
    tag = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output = root/'scratch/benchmarks/TTS-VOX-06-consistent-voice'/tag
    output.mkdir(parents=True)
    report = dict(task_id='TTS-VOX-06-consistent-voice', status='running', output=str(output),
        requirement='语速更慢，多段之间保持同一男声', speed=args.speed,
        listening_status='pending_user', paragraphs=[], reused_raw=args.reuse_from is not None)
    try:
        spec = read_json(SOURCE/'config/voxcpm2-deployment.json')
        source_revision = verify_design_source(root, spec)
        audition = read_json(SOURCE/'docs/research/TTS-VOX-06-natural-voice-result.json')
        profile_path = Path(audition['candidate_voice_profile'])
        asset = load_voice_asset(profile_path, root)
        profile = read_json(profile_path)
        reference_data = asset.reference_audio.read_bytes()
        if hashlib.sha256(reference_data).hexdigest() != asset.reference_sha256:
            raise ValueError('fixed male reference identity differs')
        reference_text = profile['provenance']['reference_text']
        parameters = dict(spec['generation'], inference_timesteps=20)
        frozen = dict(voice_id=asset.voice_id, reference_sha256=asset.reference_sha256,
            voice_profile=str(profile_path), model_revision=spec['model_revision'], source_revision=source_revision,
            mode='reference-prompt', reference_text=reference_text, parameters=parameters,
            speed=args.speed, paragraph_pause_ms=650,
            bass_db=args.bass_db,pitch_semitones=args.pitch_semitones)
        report['frozen_voice'] = frozen
        ffmpeg = Path(read_json(root/'shared/config/production.json')['tools']['ffmpeg'])
        reuse = None
        if args.reuse_from is not None:
            from video_ai.runtime.storage_files import safe_path
            reuse_dir = safe_path(args.reuse_from.absolute(), root/'scratch/benchmarks/TTS-VOX-06-consistent-voice')
            reuse = read_json(reuse_dir/'result.json')
            # Reuse synthesis only when all generation/conditioning inputs match;
            # these explicit uniform postprocessing controls can change.
            old_voice = dict(reuse['frozen_voice'])
            current_voice = dict(frozen)
            for name in ('speed','bass_db','pitch_semitones'):
                old_voice.pop(name,None); current_voice.pop(name,None)
            if old_voice != current_voice or [p['text'] for p in reuse['paragraphs']] != list(PARAGRAPHS):
                raise ValueError('postprocessing reuse requires identical voice, parameters and paragraphs')
        else:
            os.environ['HF_HUB_OFFLINE'] = os.environ['TRANSFORMERS_OFFLINE'] = '1'
            import numpy as np
            import soundfile as sf
            import torch
            from voxcpm import VoxCPM
            if not torch.cuda.is_available():
                raise RuntimeError('fixed-voice sample requires CUDA')
            model = VoxCPM.from_pretrained(str(root/'shared/models/VoxCPM2'), local_files_only=True,
                load_denoiser=spec['load_denoiser'], optimize=spec['optimize'], device=spec['device'])
        (output/'raw').mkdir()
        (output/'segments').mkdir()
        source, cursor, units, paths = '\n\n'.join(PARAGRAPHS), 0, [], {}
        for i, paragraph in enumerate(PARAGRAPHS, 1):
            identity = f'speech_{i:04d}'
            original = paragraph+('\n\n' if i < len(PARAGRAPHS) else '')
            raw = output/'raw'/(identity+'.wav')
            if reuse is not None:
                prior = reuse['paragraphs'][i-1]
                raw.write_bytes(Path(prior['raw_path']).read_bytes())
                metrics = dict(generation_seconds=prior['generation_seconds'], generation_reused=True)
            else:
                print(f'Generating paragraph {i}/{len(PARAGRAPHS)} with the same reference and prompt', flush=True)
                started = time.monotonic()
                with torch.inference_mode():
                    samples = model.generate(text=paragraph, reference_wav_path=str(asset.reference_audio),
                        prompt_wav_path=str(asset.reference_audio), prompt_text=reference_text, **parameters)
                torch.cuda.synchronize()
                metrics = dict(generation_seconds=time.monotonic()-started, generation_reused=False)
                if (samples.ndim != 1 or not samples.size or not np.isfinite(samples).all()
                        or float(np.max(np.abs(samples))) <= 32/32768):
                    raise ValueError('invalid or silent paragraph: '+identity)
                sf.write(str(raw), samples, model.tts_model.sample_rate, subtype='PCM_16')
            target = output/'segments'/(identity+'.wav')
            filters = [f'atempo={args.speed}']
            if args.pitch_semitones:
                ratio = math.pow(2,args.pitch_semitones/12)
                filters.append(f'rubberband=pitch={ratio:.12f}:formant=preserved:pitchq=quality')
            if args.bass_db:
                filters.append(f'bass=g={args.bass_db}:f=180:t=q:w=0.707')
            # Identical processing on every paragraph; actual timing is measured
            # after both tempo and pitch processing, never copied from an old run.
            expression = ','.join(filters)
            command = [str(ffmpeg),'-nostdin','-v','error','-n','-i',str(raw),
                '-af',expression,'-ar','48000','-ac','1','-c:a','pcm_s16le',str(target)]
            with (output/(identity+'-tempo.log')).open('xb') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            units.append(dict(unit_id=identity, start=cursor, end=cursor+len(original),
                original_text=original, synthesis_text=original, voice_id=asset.voice_id,
                seed=parameters['seed'], pause_after_ms=650 if i < len(PARAGRAPHS) else 0))
            cursor += len(original)
            paths[identity] = target
            report['paragraphs'].append(dict(unit_id=identity,text=paragraph,raw_path=str(raw),
                processed_path=str(target),tempo_command=command,**metrics))
            write_record(output/'result.json', report)
        plan = dict(schema_version=1,source_text=source,source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            alignment='independent-tts-paragraphs-after-tempo',voice=frozen,units=units,skips=[])
        result = assemble_narration(plan,paths,output/'narration.wav')
        write_record(output/'speech-plan.json',plan)
        write_record(output/'tts-result.json',result)
        report.update(status='generated_pending_listening',audio_path=result['audio_path'],
            duration_seconds=result['total_samples']/48000,total_samples=result['total_samples'],
            result_path=str(output/'tts-result.json'),
            notes=['Same fixed reference and prompt transcript for every paragraph; no rolling generated reference',
                'Same seed/cfg/steps and identical postprocessing controls across paragraphs',
                'Actual timing measured after tempo processing; no fabricated sentence timestamps',
                'Reference transcript is intended generated text, not independently transcribed',
                'No automatic perceptual consistency or naturalness claim'])
        preference = dict(schema_version=1,engine='voxcpm2',voice_profile=str(profile_path.relative_to(root)),
            voice_id=asset.voice_id,reference_sha256=asset.reference_sha256,
            purpose='male_documentary_sleep_narration',conditioning_mode='reference-prompt',
            prompt_text=reference_text,seed=parameters['seed'],cfg_value=parameters['cfg_value'],
            inference_timesteps=parameters['inference_timesteps'],speech_rate=args.speed,
            paragraph_pause_ms=650,voice_consistency='fixed-reference-and-prompt-for-all-paragraphs',
            emotion_policy='fixed-reference-delivery',per_segment_instructions=False,
            tone_filter=(f'bass=g={args.bass_db}:f=180:t=q:w=0.707' if args.bass_db else None),
            pitch_shift_semitones=args.pitch_semitones,
            postprocess_filters=expression,
            postprocess_source='raw-tts; this chain already includes speech_rate, do not apply tempo twice',
            listening_status='pending_user',sample=str(output/'narration.wav'),
            production_note='07 must implement the same conditioning/tempo before alignment; legacy reference-only service does not reproduce this preset')
        write_record(output/'candidate-preset.json',preference)
        # Keep this audition pending; record concrete requirements without claiming acceptance.
        current_path = root/'shared/config/tts/male-sleep-documentary.json'
        current = read_json(current_path)
        current.update(preference)
        current.update(listening_status='needs_revision',
            user_feedback='声音还是有点重，并且语速略快了点' if args.bass_db or args.pitch_semitones else '语速快了，多段之间的声音需要保持一致',
            requested_speech_rate=args.speed,requested_voice_consistency='fixed-reference-and-prompt-for-all-paragraphs',
            requested_bass_db=args.bass_db,requested_pitch_shift_semitones=args.pitch_semitones,
            accepted_dimensions=['male narration direction','naturalness','cross-paragraph consistency'],
            candidate_preset=str(output/'candidate-preset.json'))
        write_record(current_path,current)
    except BaseException:
        report.update(status='failed',error=traceback.format_exc())
        raise
    finally:
        write_record(output/'result.json',report)
        print(str(output),flush=True)


if __name__ == '__main__':
    main()
