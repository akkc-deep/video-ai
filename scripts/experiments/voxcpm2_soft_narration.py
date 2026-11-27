"""Research-informed low-stimulation male audition, without background tones."""
from datetime import datetime
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SOURCE/'src'))
from video_ai.config import read_json
from video_ai.media.narration import assemble_narration
from video_ai.runtime.storage import VideoStorage
from video_ai.runtime.storage_files import write_record
from voxcpm2_sleep_voice import verify_design_source


DIRECTION = '成年男声，轻声柔和，嗓音放松，语调平缓，像在安静地讲睡前故事'
REFERENCE = ('夜色慢慢落下来，周围渐渐安静了。远处的山，像一幅淡淡的画。'
             '风从树梢轻轻经过，又慢慢停下来。你可以只是听着，'
             '让思绪像云一样，缓缓地飘远。')
PARAGRAPHS = (
    '夜色慢慢落在山谷里。河水安静地向前流着，月光在水面上，留下一层淡淡的银色。'
    '远处的风，穿过树梢，又慢慢停下来。',
    '在这片安静的夜空下，星光经过了很长的旅程，才来到我们的眼前。'
    '我们不必急着追赶什么，只是轻轻地听着，让这一刻，慢慢地过去。',
)


def main():
    root=VideoStorage().runtime_root
    tag=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output=root/'scratch/benchmarks/TTS-VOX-06-soft-narration'/tag
    output.mkdir(parents=True)
    report=dict(task_id='TTS-VOX-06-soft-narration',status='running',output=str(output),
        user_requirement='男声本身低刺激、平稳柔和，不加嗡鸣',
        research='docs/voxcpm2-low-stimulation-research.md',listening_status='pending_user',samples=[])
    try:
        os.environ['HF_HUB_OFFLINE']=os.environ['TRANSFORMERS_OFFLINE']='1'
        spec=read_json(SOURCE/'config/voxcpm2-deployment.json')
        actual_source=verify_design_source(root,spec)
        import numpy as np
        import soundfile as sf
        import torch
        from voxcpm import VoxCPM
        from video_ai.voxcpm.contracts import wav_metadata
        if not torch.cuda.is_available(): raise RuntimeError('soft male audition requires CUDA')
        model=VoxCPM.from_pretrained(str(root/'shared/models/VoxCPM2'),local_files_only=True,
            load_denoiser=spec['load_denoiser'],optimize=spec['optimize'],device=spec['device'])
        parameters=dict(spec['generation'],inference_timesteps=20)
        report.update(model_revision=spec['model_revision'],source_revision=actual_source,
            parameters=parameters,direction=DIRECTION,reference_text=REFERENCE,
            production_choices=dict(speech_rate=.75,paragraph_pause_ms=1200,target_rms_db=-25,
                postprocess='atempo=0.75,treble=g=-2:f=3500:t=q:w=0.707',pitch_shift=0,
                background_audio=False,therapeutic_frequency_target=None))
        def generate(path,text,**conditioning):
            started=time.monotonic()
            with torch.inference_mode(): samples=model.generate(text=text,**conditioning,**parameters)
            torch.cuda.synchronize()
            if (samples.ndim!=1 or not samples.size or not np.isfinite(samples).all()
                    or float(np.max(np.abs(samples)))<=32/32768):
                raise ValueError('invalid or silent soft-voice output')
            sf.write(str(path),samples,model.tts_model.sample_rate,subtype='PCM_16')
            return dict(path=str(path),generation_seconds=time.monotonic()-started,sample_count=int(samples.size))
        print('Designing a relaxed, soft-spoken male reference',flush=True)
        reference=output/'reference.wav'
        report['reference']=generate(reference,f'({DIRECTION}){REFERENCE}')
        asset_dir=root/'shared/assets/voices'/('male-soft-narration-v3-'+tag)
        asset_dir.mkdir(parents=True)
        reference_data=reference.read_bytes()
        (asset_dir/'reference.wav').write_bytes(reference_data)
        digest=hashlib.sha256(reference_data).hexdigest()
        profile=dict(schema_version=1,voice_id='male-soft-narration-v3',reference_audio='reference.wav',
            reference_sha256=digest,base_style='轻声柔和、放松平缓的男声旁白',
            purpose='male_documentary_sleep_narration',intended_gender='male',listening_status='pending_user',
            provenance=dict(method='voxcpm2-voice-design',design_direction=DIRECTION,reference_text=REFERENCE,
                transcript_verification='intended generated text, not independently transcribed',
                model_revision=spec['model_revision'],source_revision=actual_source,generation=parameters))
        write_record(asset_dir/'voice.json',profile)
        voice=dict(voice_id=profile['voice_id'],voice_profile=str(asset_dir/'voice.json'),
            reference_sha256=digest,model_revision=spec['model_revision'],reference_text=REFERENCE,
            conditioning_mode='reference-prompt',parameters=parameters,speech_rate=.75,
            pitch_shift_semitones=0,paragraph_pause_ms=1200)
        report['frozen_voice']=voice
        (output/'raw').mkdir(); (output/'segments').mkdir()
        ffmpeg=read_json(root/'shared/config/production.json')['tools']['ffmpeg']
        paths,units,cursor={},[],0
        source='\n\n'.join(PARAGRAPHS)
        for i,paragraph in enumerate(PARAGRAPHS,1):
            identity=f'speech_{i:04d}'
            original=paragraph+('\n\n' if i<len(PARAGRAPHS) else '')
            print(f'Generating soft paragraph {i}/{len(PARAGRAPHS)} with the same reference',flush=True)
            raw=output/'raw'/(identity+'.wav')
            sample=generate(raw,paragraph,reference_wav_path=str(reference),prompt_wav_path=str(reference),prompt_text=REFERENCE)
            target=output/'segments'/(identity+'.wav')
            command=[ffmpeg,'-nostdin','-v','error','-n','-i',str(raw),'-af',report['production_choices']['postprocess'],
                '-ar','48000','-ac','1','-c:a','pcm_s16le',str(target)]
            with (output/(identity+'.log')).open('xb') as log:
                subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            paths[identity]=target
            units.append(dict(unit_id=identity,start=cursor,end=cursor+len(original),
                original_text=original,synthesis_text=original,voice_id=voice['voice_id'],seed=parameters['seed'],
                pause_after_ms=1200 if i<len(PARAGRAPHS) else 0))
            cursor+=len(original)
            report['samples'].append(dict(sample,unit_id=identity,text=paragraph,processed_path=str(target)))
            write_record(output/'result.json',report)
        plan=dict(schema_version=1,source_text=source,source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            alignment='independent-tts-paragraphs-after-processing',voice=voice,units=units,skips=[])
        result=assemble_narration(plan,paths,output/'narration.wav',target_rms_db=-25)
        write_record(output/'speech-plan.json',plan)
        write_record(output/'tts-result.json',result)
        report.update(status='generated_pending_listening',audio_path=result['audio_path'],
            duration_seconds=result['total_samples']/48000,total_samples=result['total_samples'],
            result_path=str(output/'tts-result.json'),asset_profile=str(asset_dir/'voice.json'),
            signal_format=dict(sample_rate=48000,channels=1,sample_width=2),
            therapeutic_claim='None; research-informed artistic audition, not proof of sleep or hypnosis efficacy')
        preset=dict(schema_version=1,engine='voxcpm2',voice_profile=str((asset_dir/'voice.json').relative_to(root)),
            voice_id=voice['voice_id'],reference_sha256=digest,conditioning_mode='reference-prompt',prompt_text=REFERENCE,
            seed=parameters['seed'],cfg_value=parameters['cfg_value'],inference_timesteps=20,speech_rate=.75,
            pitch_shift_semitones=0,paragraph_pause_ms=1200,target_rms_db=-25,
            postprocess_filters=report['production_choices']['postprocess'],postprocess_source='raw-tts; tempo included once',
            background_audio=False,emotion_policy='fixed-reference-delivery',per_segment_instructions=False,
            listening_status='pending_user',sample=str(output/'narration.wav'),
            research='docs/voxcpm2-low-stimulation-research.md',
            production_note='07 must reproduce reference-prompt conditioning, then tempo/softening, actual-sample alignment and global gain')
        write_record(output/'candidate-preset.json',preset)
        write_record(root/'shared/config/tts/male-sleep-documentary.json',preset)
    except BaseException:
        report.update(status='failed',error=traceback.format_exc())
        raise
    finally:
        write_record(output/'result.json',report)
        print(str(output),flush=True)


if __name__=='__main__': main()
