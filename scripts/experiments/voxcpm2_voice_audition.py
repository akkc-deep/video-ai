"""Two alternative male timbres with the same low-stimulation narration recipe."""
import argparse
from datetime import datetime
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

SOURCE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SOURCE/'src'))
from video_ai.config import read_json
from video_ai.media.narration import assemble_narration
from video_ai.runtime.storage import VideoStorage
from video_ai.runtime.storage_files import write_record
from voxcpm2_sleep_voice import verify_design_source
from voxcpm2_soft_narration import REFERENCE, PARAGRAPHS


VARIANTS=(
    ('A-clear-gentle','清润男声方向',142,'清澈温润的青年男声，声音柔软干净，轻声放松，语调平稳，像安静的睡前陪伴'),
    ('B-warm-natural','温和圆润男声方向',242,'温和清爽的成年男声，声线圆润，像自然交谈，轻声柔和，放松平稳'),
)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe',type=Path,help='Explicit alternate voice directions and listening text')
    args=parser.parse_args()
    recipe=read_json(args.recipe) if args.recipe else {}
    root=VideoStorage().runtime_root
    tag=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    task_id=recipe.get('task_id','TTS-VOX-06-bright-natural') if args.recipe else 'TTS-VOX-06-voice-audition'
    from video_ai.voxcpm.contracts import valid_id
    valid_id(task_id)
    output=root/'scratch/benchmarks'/task_id/tag
    output.mkdir(parents=True)
    report=dict(task_id=task_id,status='running',output=str(output),
        user_feedback=recipe.get('user_feedback','感觉快对了，这个音色不好'),
        preserve_direction=recipe.get('preserve_direction','Low stimulation, gentle male narration; change only the voice candidate'),
        listening_status='voice_selection_pending',variants=[])
    try:
        os.environ['HF_HUB_OFFLINE']=os.environ['TRANSFORMERS_OFFLINE']='1'
        spec=read_json(SOURCE/'config/voxcpm2-deployment.json')
        actual_source=verify_design_source(root,spec)
        prior=read_json(SOURCE/'docs/research/TTS-VOX-06-soft-narration-result.json')
        choices=dict(prior['production_choices'],**recipe.get('production_choices',{}))
        parameters=dict(prior['parameters'])
        reference_text=recipe.get('reference_text',REFERENCE)
        paragraphs=tuple(recipe.get('paragraphs',PARAGRAPHS))
        variants=tuple((v['name'],v['label'],v['seed'],v['direction']) for v in recipe['variants']) if recipe else VARIANTS
        report.update(model_revision=spec['model_revision'],source_revision=actual_source,
            production_choices=choices,narration_parameters=parameters,
            reference_text=reference_text,paragraphs=list(paragraphs),background_audio=False,pitch_shift=0,
            recipe=str(args.recipe) if args.recipe else None)
        import numpy as np
        import soundfile as sf
        import torch
        from voxcpm import VoxCPM
        if not torch.cuda.is_available(): raise RuntimeError('voice audition requires CUDA')
        model=VoxCPM.from_pretrained(str(root/'shared/models/VoxCPM2'),local_files_only=True,
            load_denoiser=spec['load_denoiser'],optimize=spec['optimize'],device=spec['device'])
        ffmpeg=read_json(root/'shared/config/production.json')['tools']['ffmpeg']
        def generate(path,text,*,seed=42,pitch_diagnostic=False,design_cfg=None,**conditioning):
            started=time.monotonic()
            generation=dict(parameters,seed=seed)
            if design_cfg is not None: generation['cfg_value']=design_cfg
            with torch.inference_mode():
                samples=model.generate(text=text,**conditioning,**generation)
            torch.cuda.synchronize()
            if (samples.ndim!=1 or not samples.size or not np.isfinite(samples).all()
                    or float(np.max(np.abs(samples)))<=32/32768):
                raise ValueError('invalid or silent voice audition sample')
            sf.write(str(path),samples,model.tts_model.sample_rate,subtype='PCM_16')
            metrics=dict(generation_seconds=time.monotonic()-started,sample_count=int(samples.size))
            if pitch_diagnostic:
                import librosa
                signal=librosa.resample(samples,orig_sr=model.tts_model.sample_rate,target_sr=16000)
                f0,voiced,prob=librosa.pyin(signal,fmin=70,fmax=500,sr=16000,frame_length=2048,hop_length=320)
                values=f0[voiced & (prob>=.1)]
                metrics['pitch_diagnostic']=dict(confident_frames=len(values),
                    median_hz=float(np.median(values)) if len(values) else None,
                    note='Coarse voiced-pitch diagnostic only; not a quality, gender or sleep-efficacy verdict')
                print('Reference pitch diagnostic: '+str(metrics['pitch_diagnostic']),flush=True)
            return metrics
        for name,label,design_seed,direction in variants:
            from video_ai.voxcpm.contracts import valid_id
            valid_id(name)
            folder=output/name
            folder.mkdir()
            (folder/'raw').mkdir(); (folder/'segments').mkdir()
            variant=dict(name=name,label=label,direction=direction,design_seed=design_seed,samples=[])
            report['variants'].append(variant)
            reference=folder/'reference.wav'
            reuse_reference=recipe.get('reuse_reference')
            external_reference=recipe.get('external_reference')
            if external_reference:
                from video_ai.runtime.storage_files import safe_path
                from video_ai.voxcpm.contracts import wav_metadata
                provided_path=safe_path(Path(external_reference['path']).absolute(),root)
                reference.write_bytes(provided_path.read_bytes())
                metadata=wav_metadata(reference)
                variant['reference']=dict(method='user-provided-video-vocal-estimate',source=str(provided_path),
                    sample_count=metadata['sample_count'],transcript_source=external_reference['transcript_source'])
                print('Using provided vocal reference for '+name,flush=True)
            elif reuse_reference:
                from video_ai.runtime.storage_files import safe_path
                previous_path=safe_path(Path(reuse_reference['result']).absolute(),root)
                previous=read_json(previous_path)
                selected=next(v for v in previous['variants'] if v['name']==reuse_reference['candidate'])
                if (previous['reference_text']!=reference_text or previous['model_revision']!=spec['model_revision']
                        or previous['source_revision']!=actual_source or selected['direction']!=direction
                        or selected['design_seed']!=design_seed):
                    raise ValueError('reused reference differs from recorded design')
                old_reference=safe_path(Path(previous['output'])/selected['name']/'reference.wav',root)
                reference.write_bytes(old_reference.read_bytes())
                variant['reference']=dict(selected['reference'],reused_from=str(old_reference))
                print('Reusing selected reference '+name,flush=True)
            else:
                print('Designing '+name,flush=True)
                variant['reference']=generate(reference,f'({direction}){reference_text}',seed=design_seed,
                    pitch_diagnostic=recipe.get('pitch_diagnostic',False),design_cfg=recipe.get('reference_cfg_value'))
            floor=recipe.get('minimum_reference_median_hz')
            if floor is not None:
                diagnostic=variant['reference'].get('pitch_diagnostic',{})
                median=diagnostic.get('median_hz')
                if median is None or median<floor or diagnostic.get('confident_frames',0)<30:
                    variant.update(status='reference_not_selected',reason='Offline pitch screen: still low or insufficient voiced confidence')
                    write_record(output/'result.json',report)
                    continue
            reference_data=reference.read_bytes()
            digest=hashlib.sha256(reference_data).hexdigest()
            voice_id=recipe.get('voice_id',('male-bright-audition-' if recipe else 'male-soft-audition-')+name[0].lower())
            asset_dir=root/'shared/assets/voices'/(voice_id+'-'+tag)
            asset_dir.mkdir(parents=True)
            (asset_dir/'reference.wav').write_bytes(reference_data)
            asset=dict(schema_version=1,voice_id=voice_id,reference_audio='reference.wav',reference_sha256=digest,
                base_style=recipe.get('base_style','低刺激、轻声柔和、平稳放松的男声旁白'),intended_gender='male',listening_status='pending_user',
                provenance=dict(method='user-provided-video-vocal-reference' if external_reference else 'voxcpm2-voice-design',
                    source=external_reference,design_direction=None if external_reference else direction,reference_text=reference_text,
                    model_revision=spec['model_revision'],source_revision=actual_source,
                    generation=None if external_reference else dict(parameters,seed=design_seed,cfg_value=recipe.get('reference_cfg_value',parameters['cfg_value'])),
                    reused_reference=variant['reference'].get('reused_from'),transcript_verification='intended generated text only'))
            write_record(asset_dir/'voice.json',asset)
            voice=dict(voice_id=voice_id,voice_profile=str(asset_dir/'voice.json'),reference_sha256=digest,
                model_revision=spec['model_revision'],reference_text=reference_text,conditioning_mode='reference-prompt',
                parameters=parameters,speech_rate=choices['speech_rate'],paragraph_pause_ms=choices['paragraph_pause_ms'])
            paths,units,cursor={},[],0
            source='\n\n'.join(paragraphs)
            for i,paragraph in enumerate(paragraphs,1):
                identity=f'speech_{i:04d}'
                original=paragraph+('\n\n' if i<len(paragraphs) else '')
                print(f'Generating {name} paragraph {i}/{len(paragraphs)}',flush=True)
                raw=folder/'raw'/(identity+'.wav')
                metrics=generate(raw,paragraph,seed=parameters['seed'],reference_wav_path=str(reference),
                    prompt_wav_path=str(reference),prompt_text=reference_text)
                target=folder/'segments'/(identity+'.wav')
                command=[ffmpeg,'-nostdin','-v','error','-n','-i',str(raw),'-af',choices['postprocess'],
                    '-ar','48000','-ac','1','-c:a','pcm_s16le',str(target)]
                with (folder/(identity+'.log')).open('xb') as log:
                    subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                paths[identity]=target
                units.append(dict(unit_id=identity,start=cursor,end=cursor+len(original),original_text=original,
                    synthesis_text=original,voice_id=voice_id,seed=parameters['seed'],
                    pause_after_ms=choices['paragraph_pause_ms'] if i<len(paragraphs) else 0))
                cursor+=len(original)
                variant['samples'].append(dict(unit_id=identity,text=paragraph,raw_path=str(raw),**metrics))
                write_record(output/'result.json',report)
            plan=dict(schema_version=1,source_text=source,source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                alignment='independent-tts-paragraphs-after-processing',voice=voice,units=units,skips=[])
            result=assemble_narration(plan,paths,folder/'narration.wav',target_rms_db=choices['target_rms_db'])
            write_record(folder/'speech-plan.json',plan)
            write_record(folder/'tts-result.json',result)
            preset=read_json(Path(prior['output'])/'candidate-preset.json')
            preset.update(voice_profile=str((asset_dir/'voice.json').relative_to(root)),voice_id=voice_id,
                reference_sha256=digest,prompt_text=reference_text,postprocess_filters=choices['postprocess'],
                speech_rate=choices['speech_rate'],paragraph_pause_ms=choices['paragraph_pause_ms'],
                target_rms_db=choices['target_rms_db'],
                sample=str(folder/'narration.wav'),listening_status='voice_selection_pending')
            if recipe.get('analysis_basis'): preset['analysis_basis']=recipe['analysis_basis']
            write_record(folder/'candidate-preset.json',preset)
            variant.update(status='generated_pending_listening',audio_path=str(folder/'narration.wav'),
                duration_seconds=result['total_samples']/48000,total_samples=result['total_samples'],
                result_path=str(folder/'tts-result.json'),candidate_preset=str(folder/'candidate-preset.json'),
                asset_profile=str(asset_dir/'voice.json'))
            write_record(output/'result.json',report)
            if recipe.get('max_audition_outputs')==1:
                break
        completed=[v for v in report['variants'] if v.get('status')=='generated_pending_listening']
        if not completed:
            raise RuntimeError('No reference met this limited higher-register audition screen; do not present low references as brighter voices')
        report.update(status='generated_pending_listening',selected_voice_updated=False,feedback_record_updated=True,
            notes=['Same source, reference transcript, body seed/cfg/steps, postprocessing and global level for A/B',
                'Only candidate reference design descriptors and design seeds differ',
                'Exact generated prosody can still differ between reference voices; this is a listening audition',
                'No background sound, pitch shifting, extra frequency effect, ASR or full-video generation'])
        if recipe.get('external_reference'):
            report['notes']=['Provided video vocal estimate used as one fixed reference and prompt across target paragraphs',
                'Reference transcript from local ASR; not manually certified and separation artifacts can remain',
                'Fresh target narration generated with no speaker-identity claim',
                'Natural articulation with only mild uniform tempo and paragraph pause adjustment; no pitch shifting or background']
        current_path=root/'shared/config/tts/male-sleep-documentary.json'
        current=read_json(current_path)
        current.update(listening_status='voice_replacement_pending',user_feedback=report['user_feedback'],
            preserved_direction=report['preserve_direction'],
            audition_candidates=[v['candidate_preset'] for v in completed])
        write_record(current_path,current)
    except BaseException:
        report.update(status='failed',error=traceback.format_exc())
        raise
    finally:
        write_record(output/'result.json',report)
        print(str(output),flush=True)


if __name__=='__main__': main()
