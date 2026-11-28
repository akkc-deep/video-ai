"""Paired, offline performance experiment for the approved VoxCPM2 narration."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import traceback
import wave

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE/'src'))
from video_ai.media.narration import assemble_narration
from video_ai.media.narration_guard import approved_onset_guard, remove_spoken_guard
from video_ai.runtime.storage import VideoStorage
from video_ai.runtime.storage_files import read_record, write_record
from video_ai.voxcpm.voices import load_voice_asset

CASES = {
    'opening': '在距离地球数百亿公里之外的宇宙深处，一艘来自上个世纪的探测器，正独自穿行在无尽的黑暗之中。',
    'middle': '在这片遥远的宇宙空间中，阳光已经极其微弱。',
    'ending': '而人类的探索，才刚刚开始。',
}


def summarize(rows, expected_pairs, cache_build_seconds):
    """Only complete paired warm trials can support the objective gate."""
    pairs = {}
    for row in rows:
        if row['variant'] == 'cold':
            continue
        key = (row['round'], row['case'])
        variant = row['variant']
        if key not in expected_pairs or variant not in ('baseline', 'prompt-cache'):
            raise ValueError('unexpected comparison pair')
        pair = pairs.setdefault(key, {})
        if variant in pair:
            raise ValueError('duplicate comparison pair')
        for name in ('generation_seconds', 'pipeline_seconds', 'raw_seconds', 'body_seconds'):
            if not math.isfinite(row[name]) or row[name] <= 0:
                raise ValueError('invalid comparison pair timing')
        pair[variant] = row
    if not expected_pairs or set(pairs) != expected_pairs or any(len(p) != 2 for p in pairs.values()):
        raise ValueError('incomplete comparison pairs')
    result = {}
    for variant in ('baseline', 'prompt-cache'):
        trials = [p[variant] for p in pairs.values()]
        generation = sum(r['generation_seconds'] for r in trials)
        raw = sum(r['raw_seconds'] for r in trials)
        body = sum(r['body_seconds'] for r in trials)
        result[variant] = dict(trials=len(trials), generation_seconds=generation,
            pipeline_seconds=sum(r['pipeline_seconds'] for r in trials), raw_seconds=raw,
            body_seconds=body, raw_rtf=generation/raw, body_rtf=generation/body)
    reduction = 1-result['prompt-cache']['generation_seconds']/result['baseline']['generation_seconds']
    per_round = {}
    for number in sorted({r for r,c in expected_pairs}):
        group = [p for (r,c),p in pairs.items() if r == number]
        per_round[str(number)] = 1-sum(p['prompt-cache']['generation_seconds'] for p in group)/sum(
            p['baseline']['generation_seconds'] for p in group)
    identical = all(p['baseline']['pcm_sha256'] == p['prompt-cache']['pcm_sha256']
                    and p['baseline']['body_pcm_sha256'] == p['prompt-cache']['body_pcm_sha256']
                    for p in pairs.values())
    performance = reduction >= .1 and all(v > 0 for v in per_round.values())
    pipeline_reduction = 1-result['prompt-cache']['pipeline_seconds']/result['baseline']['pipeline_seconds']
    result.update(generation_reduction=reduction, pipeline_reduction=pipeline_reduction,
        round_reductions=per_round, cache_build_seconds=cache_build_seconds,
        candidate_generation_with_cache_build_seconds=result['prompt-cache']['generation_seconds']+cache_build_seconds,
        pcm_identical=identical, performance_gate_passed=performance,
        objective_gate_passed=performance and identical,
        target_raw_rtf_met=result['prompt-cache']['raw_rtf'] <= .3,
        target_body_rtf_met=result['prompt-cache']['body_rtf'] <= .3,
        subjective_listening='not_performed', production_enabled=False,
        decision='retain-official-production-path',
        decision_reason='Requires >=10% gain with both rounds positive, identical paired PCM, and approved comparative listening; experiment never changes production.')
    return result


def postprocess(raw, target, recipe, ffmpeg):
    """Measure delivered body only, using the production acoustic separator."""
    tempo = target.with_name(target.stem+'-with-context.wav')
    subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-n', '-i', str(raw),
        '-af', recipe['postprocess_filters'], '-ar', '48000', '-ac', '1', '-c:a', 'pcm_s16le', str(tempo)],
        check=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    with wave.open(str(tempo), 'rb') as audio:
        if audio.getparams()[:3] != (1,2,48000):
            raise ValueError('postprocessing must produce 48kHz mono PCM16')
        pcm = audio.readframes(audio.getnframes())
    body, boundary = remove_spoken_guard(pcm, recipe['onset_guard'])
    with wave.open(str(target), 'wb') as audio:
        audio.setparams((1,2,48000,0,'NONE',''))
        audio.writeframes(body)
    return dict(body_seconds=len(body)/2/48000, body_samples=len(body)//2,
        body_pcm_sha256=hashlib.sha256(body).hexdigest(), acoustic_boundary=boundary,
        body_path=str(target))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rounds', type=int, default=2)
    args = parser.parse_args()
    if not 2 <= args.rounds <= 5:
        parser.error('--rounds must be 2..5')
    root = VideoStorage().runtime_root
    output = root/'scratch/benchmarks/TTS-VOX-09'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version=1, task_id='TTS-VOX-09', status='running', output=str(output),
        started_at=datetime.now(timezone.utc).isoformat(), platform=platform.platform(),
        python=sys.version, executable=sys.executable, cases=CASES, rounds=args.rounds, trials=[],
        production_enabled=False, subjective_listening='not_performed', retries=0,
        failures=0, sample_source='approved Voyager2 full redub: speech_0001/0069/0137',
        long_duration_benchmark='not_run; do not extrapolate 5/10/30 minute quality or RTF')
    write_record(output/'result.json', report)
    print('Evidence: '+str(output), flush=True)
    started = time.perf_counter()
    try:
        recipe = read_record(root/'shared/config/tts/default-narration.json')
        spec = read_record(SOURCE/'config/voxcpm2-deployment.json')
        if (recipe['voice_id'] != 'provided-reference-narration-v1'
                or recipe['conditioning_mode'] != 'reference-prompt'
                or not approved_onset_guard(recipe.get('onset_guard'))
                or (recipe['seed'], recipe['cfg_value'], recipe['inference_timesteps'],
                    recipe['speech_rate'], recipe['paragraph_pause_ms'], recipe['target_rms_db']) != (42,2,20,.95,500,-23)
                or recipe['postprocess_filters'] != 'atempo=0.95'
                or recipe['model_revision'] != spec['model_revision']
                or recipe['source_revision'] != spec['source_revision']):
            raise ValueError('experiment requires the current approved narration recipe')
        asset = load_voice_asset(recipe['voice_profile'], root)
        reference_data = asset.reference_audio.read_bytes()
        digest = hashlib.sha256(reference_data).hexdigest()
        if digest != recipe['reference_sha256'] or digest != asset.reference_sha256:
            raise ValueError('approved reference identity differs')
        reference = output/'reference.wav'
        reference.write_bytes(reference_data)
        revision = subprocess.check_output(['git','-C',str(root/'shared/tools/VoxCPM'),
            'rev-parse','HEAD'], text=True, timeout=15).strip()
        if revision != spec['source_revision']:
            raise ValueError('source revision differs from frozen deployment')
        write_record(output/'frozen-recipe.json', recipe)
        write_record(output/'frozen-deployment.json', spec)
        report.update(recipe=recipe, deployment=spec, reference_sha256=digest)
        ffmpeg = Path(read_record(root/'shared/config/production.json')['tools']['ffmpeg'])
        os.environ['HF_HUB_OFFLINE'] = os.environ['TRANSFORMERS_OFFLINE'] = '1'
        import_started = time.perf_counter()
        import numpy as np
        import soundfile as sf
        import torch
        from voxcpm import VoxCPM
        report['import_seconds'] = time.perf_counter()-import_started
        if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
            raise RuntimeError('real CUDA with BF16 is required')
        torch.cuda.synchronize()
        load_started = time.perf_counter()
        model = VoxCPM.from_pretrained(str(root/'shared/models/VoxCPM2'), local_files_only=True,
            load_denoiser=False, optimize=False, device=spec['device'])
        torch.cuda.synchronize()
        report.update(model_load_seconds=time.perf_counter()-load_started,
            torch_version=torch.__version__, cuda_runtime=torch.version.cuda,
            gpu=torch.cuda.get_device_name(), cpu_threads=torch.get_num_threads(),
            lm_dtype=str(model.tts_model.config.dtype), audio_vae_dtype=str(next(model.tts_model.audio_vae.parameters()).dtype))
        parameters = dict(spec['generation'])
        for name in ('seed','cfg_value','inference_timesteps'):
            parameters[name] = recipe[name]
        prompt = dict(prompt_text=recipe['prompt_text'], prompt_wav_path=str(reference),
                      reference_wav_path=str(reference))
        cache = None

        def trial(variant, number, case):
            text = recipe['onset_guard']['text']+CASES[case]
            text = re.sub(r'\s+', ' ', text.replace('\n',' '))
            label = f'{number+1:02d}-{case}-{variant}'
            print('Generating '+label, flush=True)
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
            pipeline_start = time.perf_counter()
            generation_start = time.perf_counter()
            with torch.inference_mode():
                if variant == 'prompt-cache':
                    options = {k:v for k,v in parameters.items() if k not in ('normalize','denoise')}
                    wav, _, _ = model.tts_model.generate_with_prompt_cache(
                        target_text=text, prompt_cache=cache, **options)
                    samples = wav.squeeze(0).cpu().numpy()
                else:
                    samples = model.generate(text=text, **prompt, **parameters)
            torch.cuda.synchronize()
            elapsed = time.perf_counter()-generation_start
            if samples.ndim != 1 or not samples.size or not np.isfinite(samples).all() or not np.any(samples):
                raise ValueError('invalid model audio: '+label)
            raw = output/(label+'-raw-internal.wav')
            sf.write(str(raw), samples, model.tts_model.sample_rate, subtype='PCM_16')
            with wave.open(str(raw), 'rb') as audio:
                pcm = audio.readframes(audio.getnframes())
            row = dict(round=number, case=case, variant=variant, generation_seconds=elapsed,
                raw_seconds=samples.size/model.tts_model.sample_rate,
                raw_samples=int(samples.size), sample_rate=model.tts_model.sample_rate,
                pcm_sha256=hashlib.sha256(pcm).hexdigest(), raw_path=str(raw),
                peak_allocated_gib=torch.cuda.max_memory_allocated()/2**30,
                peak_reserved_gib=torch.cuda.max_memory_reserved()/2**30, retries=0)
            row.update(postprocess(raw, output/(label+'-body.wav'), recipe, ffmpeg))
            row['pipeline_seconds'] = time.perf_counter()-pipeline_start
            report['trials'].append(row)
            write_record(output/'result.json', report)
            print(json.dumps(dict(trial=label, generation_seconds=elapsed,
                body_seconds=row['body_seconds']), ensure_ascii=False), flush=True)

        trial('cold', -1, 'opening')
        torch.cuda.synchronize()
        cache_started = time.perf_counter()
        with torch.inference_mode():
            cache = model.tts_model.build_prompt_cache(**prompt)
        torch.cuda.synchronize()
        report['cache_build_seconds'] = time.perf_counter()-cache_started
        report['cache_identity'] = dict(reference_sha256=digest, prompt_text=recipe['prompt_text'],
            mode=recipe['conditioning_mode'], model_revision=spec['model_revision'], source_revision=revision,
            scope='one immutable model instance and one frozen reference; no rolling merge or disk cache')
        for number in range(args.rounds):
            order = ('baseline','prompt-cache') if number%2 == 0 else ('prompt-cache','baseline')
            for case in CASES:
                for variant in order:
                    trial(variant, number, case)
        report['summary'] = summarize(report['trials'],
            {(r,c) for r in range(args.rounds) for c in CASES}, report['cache_build_seconds'])
        # Listening artifacts contain original text only, never the disposable context.
        for variant in ('baseline','prompt-cache'):
            selected = [r for r in report['trials'] if r['round'] == 0 and r['variant'] == variant]
            units = [dict(unit_id=r['case'], original_text=CASES[r['case']],
                          pause_after_ms=recipe['paragraph_pause_ms']) for r in selected]
            source_text = '\n\n'.join(CASES[r['case']] for r in selected)
            plan = dict(units=units, source_text=source_text,
                source_sha256=hashlib.sha256(source_text.encode()).hexdigest(), voice=recipe,
                alignment='actual-body-segment-samples; no sentence alignment', skips=[])
            assembled = assemble_narration(plan, {r['case']:Path(r['body_path']) for r in selected},
                output/(variant+'-listening.wav'), target_rms_db=recipe['target_rms_db'])
            write_record(output/(variant+'-assembly.json'), assembled)
        report.update(status='evaluated', end_to_end_seconds=time.perf_counter()-started)
    except BaseException:
        report.update(status='failed', failures=1, error=traceback.format_exc(),
                      end_to_end_seconds=time.perf_counter()-started)
        raise
    finally:
        write_record(output/'result.json', report)
        print('Report: '+str(output/'result.json'), flush=True)


if __name__ == '__main__':
    main()
