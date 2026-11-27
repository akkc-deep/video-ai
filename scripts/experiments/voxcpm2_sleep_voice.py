"""Design a generic male voice, then render a short sleep-documentary sample."""
import argparse
from datetime import datetime
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE/'src'))
from video_ai.config import load_config, read_json
from video_ai.runtime.storage import VideoStorage
from video_ai.runtime.storage_files import safe_path, write_record


def verify_design_source(root, spec):
    actual = subprocess.check_output(['git','-C',str(root/'shared/tools/VoxCPM'),
                                     'rev-parse','HEAD'],text=True,timeout=15).strip()
    if actual != spec['source_revision']:
        raise RuntimeError('VoxCPM source differs from frozen voice-design specification')
    return actual


def finalize_sample(report, controller, preference_path, preference, output, failure=None):
    if controller is not None:
        try:
            code = controller.stop()
            report['owned_vox_exit_code'] = code
            if code != 0:
                raise RuntimeError(f'owned voice service did not exit cleanly: {code}')
        except BaseException as error:
            report['shutdown_error'] = traceback.format_exc()
            if failure is None: failure = error
    if failure is None:
        try:
            write_record(preference_path, preference)
        except BaseException as error:
            report['error'] = traceback.format_exc()
            failure = error
    report['status'] = 'failed' if failure is not None else 'generated_pending_listening'
    write_record(output/'result.json', report)
    return failure


def design(output, asset_dir, recipe, root):
    """Run only in the dedicated interpreter; exiting frees this design model."""
    os.environ['HF_HUB_OFFLINE'] = os.environ['TRANSFORMERS_OFFLINE'] = '1'
    spec = read_json(SOURCE/'config/voxcpm2-deployment.json')
    actual_source = verify_design_source(root, spec)
    import numpy as np
    import soundfile as sf
    import torch
    from voxcpm import VoxCPM
    from video_ai.voxcpm.contracts import wav_metadata
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError('male voice design requires CUDA BF16')
    model = VoxCPM.from_pretrained(str(root/'shared/models/VoxCPM2'), local_files_only=True,
        load_denoiser=spec['load_denoiser'], optimize=spec['optimize'], device=spec['device'])
    parameters = dict(spec['generation'], seed=recipe['seed'])
    started = time.monotonic()
    with torch.inference_mode():
        # Voice design: deliberately omit every previous reference/prompt audio.
        samples = model.generate(text=f'({recipe["design_direction"]}){recipe["reference_text"]}', **parameters)
    torch.cuda.synchronize()
    seconds = time.monotonic()-started
    if (samples.ndim != 1 or not samples.size or not np.isfinite(samples).all()
            or float(np.max(np.abs(samples))) <= 32/32768):
        raise ValueError('voice design returned silent or invalid speech')
    asset_dir.mkdir(parents=True, exist_ok=False)
    reference = asset_dir/'reference.wav'
    sf.write(str(reference), samples, model.tts_model.sample_rate, subtype='PCM_16')
    digest = hashlib.sha256(reference.read_bytes()).hexdigest()
    profile = dict(schema_version=1, voice_id=recipe['voice_id'], reference_audio='reference.wav',
        reference_sha256=digest, base_style=recipe['base_style'],
        intended_gender='male', purpose=recipe['purpose'], listening_status='pending_user',
        provenance=dict(method='voxcpm2-voice-design', reference_audio=None,
            design_direction=recipe['design_direction'], reference_text=recipe['reference_text'],
            model_revision=spec['model_revision'], source_revision=actual_source,
            generation=parameters, seconds=seconds))
    write_record(asset_dir/'voice.json', profile)
    write_record(output/'design-result.json', dict(profile=str(asset_dir/'voice.json'),
        reference=str(reference), audio=wav_metadata(reference), generation_seconds=seconds,
        source_reference=None, status='generated_pending_listening'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--design-only', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--asset-dir', type=Path)
    args = parser.parse_args()
    root = VideoStorage().runtime_root
    recipe = read_json(SOURCE/'config/voxcpm2-sleep-voice.json')
    if args.design_only:
        if args.output is None or args.asset_dir is None:
            parser.error('design phase requires --output and --asset-dir')
        design(safe_path(args.output.absolute(), root), safe_path(args.asset_dir.absolute(), root), recipe, root)
        return
    from video_ai.adapters.common import HttpClient
    from video_ai.adapters.longform import LongFormSynthesizer
    from video_ai.planning.emotion import make_plan
    from video_ai.planning.speech import freeze_voice, plan_speech
    from video_ai.runtime.manifest import thaw
    from video_ai.voxcpm.process import VoxServiceProcess
    from voxcpm2_adapter_smoke import ExperimentLogger
    tag = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output = root/'scratch/benchmarks/TTS-VOX-06-male-sleep'/tag
    output.mkdir(parents=True)
    asset_dir = root/'shared/assets/voices'/(recipe['voice_id']+'-'+tag)
    report = dict(task_id='TTS-VOX-06-male-sleep', status='running', output=str(output),
        requirement='纪录片旁白，用来助眠，需要男声', recipe=recipe)
    controller = None
    failure, preference = None, None
    preference_path = root/'shared/config/tts/male-sleep-documentary.json'
    try:
        print('Designing a new generic adult male voice without the old reference', flush=True)
        command = [str(root/'shared/envs/voxcpm2/Scripts/python.exe'), '-B','-u',str(Path(__file__).resolve()),
            '--design-only','--output',str(output),'--asset-dir',str(asset_dir)]
        with (output/'design.log').open('xb') as log:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if completed.returncode:
            raise RuntimeError('male voice design failed; see '+str(output/'design.log'))
        report['design'] = read_json(output/'design-result.json')
        profile_path = asset_dir/'voice.json'
        source = root/'shared/config/production.json'
        config = load_config(source)
        raw = thaw(config.raw)
        spec = read_json(SOURCE/'config/voxcpm2-deployment.json')
        raw['tts'] = dict(engine='voxcpm2', model_revision=spec['model_revision'], seed=recipe['seed'])
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0)); port = probe.getsockname()[1]
        controller = VoxServiceProcess(root, output/'state', port=port, voice_profile=profile_path)
        raw['services']['tts'] = controller.url
        config = load_config(source, raw=raw, voice=config.voice)
        voice = freeze_voice(config, voice_profile=profile_path)
        text = recipe['sample_text']
        rows = [dict(start=0,end=len(text),emotion=recipe['emotion'],
            emotion_intensity=recipe['emotion_intensity'],tone=recipe['tone'],pause_after_ms=0)]
        emotion = make_plan(text, rows, voice.base_style)
        plan = plan_speech(emotion, voice)
        write_record(output/'emotion-plan.json', emotion)
        write_record(output/'speech-plan.json', plan)
        print('Rendering a short calm documentary sample with the new male reference', flush=True)
        report['health'] = controller.start()
        result = LongFormSynthesizer(HttpClient(controller.url,300,ExperimentLogger(output)),voice,
            request_scope=str(output)).synthesize(plan, output/'audio')
        preference = dict(schema_version=1, engine='voxcpm2', purpose=recipe['purpose'],
            voice_profile=str(profile_path.relative_to(root)), reference_sha256=voice.reference_sha256,
            voice_id=voice.voice_id, base_style=voice.base_style, emotion=recipe['emotion'],
            emotion_intensity=recipe['emotion_intensity'], tone=recipe['tone'], seed=recipe['seed'],
            listening_status='pending_user')
        report.update(status='generated_pending_listening', voice=voice.as_dict(),
            voice_profile=str(profile_path), preference_path=str(preference_path),
            audio_path=result['audio_path'], duration_seconds=result['total_samples']/48000,
            total_samples=result['total_samples'], units=len(plan['units']),
            result_path=str(output/'audio/tts-result.json'),
            subjective_quality='User listening required; gender/timbre/style not automatically certified')
    except BaseException as error:
        failure = error
        report.update(status='failed', error=traceback.format_exc())
    failure = finalize_sample(report, controller, preference_path, preference, output, failure)
    print(str(output), flush=True)
    if failure is not None: raise failure
    print(report['audio_path'], flush=True)


if __name__ == '__main__':
    main()
