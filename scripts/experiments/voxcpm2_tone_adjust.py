"""Lighten the accepted narration's bass without regenerating or changing pace."""
import argparse
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import traceback
import wave

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE/'src'))
from video_ai.config import read_json
from video_ai.runtime.storage import VideoStorage
from video_ai.runtime.storage_files import safe_path, write_record


def pcm_shape(path):
    with wave.open(str(path), 'rb') as audio:
        return dict(sample_rate=audio.getframerate(),sample_count=audio.getnframes(),
                    channels=audio.getnchannels(),sample_width=audio.getsampwidth())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bass-db',type=float,default=-2.5)
    args = parser.parse_args()
    if not -6 <= args.bass_db <= 0:
        parser.error('--bass-db must be -6..0')
    root = VideoStorage().runtime_root
    prior = read_json(SOURCE/'docs/research/TTS-VOX-06-consistent-voice-result.json')
    source = safe_path(Path(prior['audio_path']),root)
    old_result = read_json(Path(prior['result_path']))
    source_dir = source.parent
    preset = read_json(source_dir/'candidate-preset.json')
    tag = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output = root/'scratch/benchmarks/TTS-VOX-06-tone-adjust'/tag
    output.mkdir(parents=True)
    target = output/'narration.wav'
    # A small low shelf reduces chest/bass weight. Fundamental pitch, timing,
    # articulation and the already accepted cross-paragraph delivery are retained.
    expression = f'bass=g={args.bass_db}:f=180:t=q:w=0.707'
    ffmpeg = read_json(root/'shared/config/production.json')['tools']['ffmpeg']
    command = [ffmpeg,'-nostdin','-v','error','-n','-i',str(source),'-af',expression,
               '-ar','48000','-ac','1','-c:a','pcm_s16le',str(target)]
    report = dict(task_id='TTS-VOX-06-tone-adjust',status='running',output=str(output),
        user_feedback='声音有点太低沉了，其他没问题',source=str(source),filter=expression,
        generation_reused=True,gpu_generation_performed=False,
        preserved=['speech rate 0.8','speaker reference and prompt','all three original paragraph performances',
                   'fundamental pitch','paragraph timing and silence','naturalness accepted by user'])
    try:
        with (output/'tone.log').open('xb') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=120,check=True,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        source_audio, target_audio = pcm_shape(source), pcm_shape(target)
        if source_audio != target_audio:
            raise ValueError('tone-only adjustment changed PCM format or sample count')
        result = old_result
        result['audio_path'] = str(target)
        result['postprocess']['tone_filter'] = expression
        result['postprocess']['tone_source'] = str(source)
        result['postprocess']['clip_sources'] = 'pre-tone segments; final tone filter applied once to entire narration'
        write_record(output/'tts-result.json',result)
        preset.update(tone_filter=expression,listening_status='tone_adjustment_pending',sample=str(target),
            accepted_dimensions=['male narration direction','speech rate','naturalness','cross-paragraph consistency'],
            user_feedback='声音有点太低沉了，其他没问题',
            production_note='07 must reproduce reference-prompt conditioning, speed 0.8 and final whole-narration tone filter')
        write_record(output/'candidate-preset.json',preset)
        report.update(status='generated_pending_listening',audio_path=str(target),audio=target_audio,
            duration_seconds=target_audio['sample_count']/target_audio['sample_rate'],
            result_path=str(output/'tts-result.json'),candidate_preset=str(output/'candidate-preset.json'),
            pitch_shift_semitones=0,sample_positions_preserved=True,
            listening='Only reduced bass weight is pending; other dimensions accepted in user feedback')
        write_record(root/'shared/config/tts/male-sleep-documentary.json',preset)
    except BaseException:
        report.update(status='failed',error=traceback.format_exc())
        raise
    finally:
        write_record(output/'result.json',report)
        print(str(output),flush=True)


if __name__ == '__main__':
    main()
