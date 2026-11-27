"""TTS-VOX-02 isolated listening/RTF experiment; never imports production orchestration."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import random
import shutil
import socket
import subprocess
import sys
import time
import traceback
import urllib.request
import wave

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE / 'src'))
from video_ai.runtime.storage import VideoStorage
from video_ai.planning.segments import segment_text
from voxcpm2_smoke import write_json

EMOTIONS = {
    'narrative': '平静沉稳，以自然的纪录片叙述语气讲述',
    'gentle': '温柔舒缓，带着安慰和关怀，放慢语速',
    'mystery': '神秘好奇，带着悬念，吸引听众继续探索',
    'excited': '明显兴奋喜悦，充满活力和惊喜',
    'sad': '明显悲伤低落，带着失落和惋惜',
    'angry': '明显愤怒，语气坚定有力，但不要尖叫',
    'whisper': '轻声耳语，贴近听众，保持吐字清楚',
}
EMOTION_TEXT = '我们终于收到了远方传来的消息。请听我慢慢说，这段漫长的旅程即将迎来新的篇章。'
SHORT = '1977年8月20日，旅行者2号升空。NASA记录的速度约为每秒15.4公里。银行的行长重新核对数据，确认这艘满载仪器的飞船仍在运行。'
LONG = ('旅行者二号正在穿越遥远的星际空间。它携带着来自地球的问候，也保存着人类探索未知的勇气。'
        '当我们仰望夜空时，看到的是很久以前出发的光；当科学家等待探测器的信号时，等待的则是一段跨越漫长距离的回答。'
        '信号十分微弱，却能告诉我们那里还有怎样的粒子、磁场和变化。探测器的能源正在减少，部分仪器已经关闭，'
        '但每一份传回的数据仍然珍贵。我们无法亲自走到它的身旁，只能通过这些细小的变化，理解太阳影响之外的世界。'
        '这场旅程没有预先写好的结局。无论下一次消息何时到来，地球上的人们都会继续倾听。')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def info(path):
    # One header read per freshly written artifact, no ASR or repeated decode.
    with wave.open(str(path), 'rb') as audio:
        result = dict(sample_rate=audio.getframerate(), sample_count=audio.getnframes(),
                      channels=audio.getnchannels(), sample_width=audio.getsampwidth())
    if result['sample_count'] <= 0 or result['channels'] != 1 or result['sample_width'] != 2:
        raise ValueError(f'Expected nonempty mono PCM16: {path}')
    return result


def prepare(args):
    root = VideoStorage().runtime_root
    output = root / 'scratch/benchmarks/TTS-VOX-02' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output.mkdir(parents=True)
    config = read_json(root / 'shared/config/production.json')
    voice = read_json(config['voice_config'])
    reference = Path(voice['reference_audio'])
    digest = hashlib.sha256(reference.read_bytes()).hexdigest()
    if digest != voice['reference_sha256']:
        raise ValueError('Configured reference audio identity changed')
    shutil.copyfile(reference, output / 'reference.wav')
    write_json(output / 'voice.json', voice)
    shutil.copyfile(root / 'shared/config/tts-api.yaml', output / 'tts-runtime.yaml')
    script = args.long_text.read_text(encoding='utf-8-sig')
    (output / 'long-source.txt').write_text(script, encoding='utf-8')
    # Reuse existing lossless spans; merge only at their original boundaries.
    chunks, start = [], 0
    for span in segment_text(script):
        if span.end - start >= 120:
            chunks.append(dict(start=start, end=span.end, text=script[start:span.end]))
            start = span.end
    if start < len(script):
        chunks.append(dict(start=start, end=len(script), text=script[start:]))
    assert ''.join(c['text'] for c in chunks) == script
    cases = [dict(id='short', text=SHORT, emotion='narrative')]
    cases += [dict(id=f'emotion-{key}', text=EMOTION_TEXT, emotion=key) for key in EMOTIONS]
    cases += [dict(id='long-paragraph', text=LONG, emotion='narrative')]
    report = dict(schema_version=1, task_id='TTS-VOX-02', status='prepared',
        started_at=datetime.now(timezone.utc).isoformat(), runtime_root=str(root),
        output=str(output), configuration=config, voice=voice,
        reference=dict(path='reference.wav', source=str(reference), sha256=digest,
                       provenance='Existing configured production reference; no new external voice asset'),
        specification=read_json(SOURCE / 'config/voxcpm2-deployment.json'),
        long_source=dict(path=str(args.long_text.resolve()), sha256=hashlib.sha256(script.encode()).hexdigest(),
                         characters=len(script), chunks=chunks, target_seconds=args.long_seconds),
        cases=cases, baseline=[], voxcpm=[], long_segments=[], checkpoints=[],
        subjective_listening='pending_human_blind_listening',
        decision='HOLD: human listening required before TTS-VOX-03')
    write_json(output / 'result.json', report)
    print(output, flush=True)


def save_audio(output, relative, samples, rate):
    import numpy as np
    import soundfile as sf
    if samples.ndim != 1 or not samples.size or not np.isfinite(samples).all() or not np.any(samples):
        raise ValueError('Invalid or silent output')
    path = output / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.partial.wav')
    sf.write(str(temp), samples, rate, subtype='PCM_16')
    metadata = info(temp)
    if metadata['sample_count'] != samples.size or metadata['sample_rate'] != rate:
        raise ValueError('Written samples differ from model output')
    temp.replace(path)
    return metadata


def record(relative, metadata, seconds, **extra):
    duration = metadata['sample_count'] / metadata['sample_rate']
    return dict(audio_path=relative, audio=metadata, duration_seconds=duration,
                generation_seconds=seconds, rtf=seconds / duration, **extra)


def baseline(output, report):
    if report['baseline']:
        raise ValueError('Baseline already recorded; create a fresh experiment to rerun')
    config, voice = report['configuration'], report['voice']
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    command = [config['tools']['tts_python'], '-B', '-u',
        str(Path(config['tools']['tts_root']) / 'api_v2.py'), '-a', '127.0.0.1',
        '-p', str(port), '-c', str(output / 'tts-runtime.yaml')]
    report['baseline_command'] = command
    write_json(output / 'result.json', report)
    started = time.perf_counter()
    with (output / 'gpt-sovits.log').open('wb') as log:
        process = subprocess.Popen(command, cwd=config['tools']['tts_root'], stdout=log,
                                   stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        report['baseline_owned_pid'] = process.pid
        try:
            url = f'http://127.0.0.1:{port}'
            while True:
                if process.poll() is not None:
                    raise RuntimeError('GPT-SoVITS exited; see gpt-sovits.log')
                try:
                    with urllib.request.urlopen(url + '/openapi.json', timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    if time.perf_counter() - started > 180:
                        raise TimeoutError('GPT-SoVITS startup exceeded 180s')
                    time.sleep(1)
            report['baseline_load_seconds'] = time.perf_counter() - started
            print(f'GPT-SoVITS ready: {report["baseline_load_seconds"]:.2f}s', flush=True)
            seen = {}
            for case in report['cases']:
                if case['text'] in seen:
                    report['baseline'].append(dict(seen[case['text']], id=case['id'], reused=True))
                    continue
                payload = dict(voice['inference'], text=case['text'], text_lang=voice['text_language'],
                    ref_audio_path=str(output / 'reference.wav'), prompt_text=voice['reference_text'],
                    prompt_lang=voice['prompt_language'], speed_factor=voice['speed_factor'], seed=42)
                request = urllib.request.Request(url + '/tts', data=json.dumps(payload).encode(),
                    headers={'Content-Type': 'application/json'})
                generate_start = time.perf_counter()
                with urllib.request.urlopen(request, timeout=900) as response:
                    data = response.read()
                seconds = time.perf_counter() - generate_start
                relative = f'gpt-sovits/{case["id"]}.wav'
                path = output / relative
                path.parent.mkdir(exist_ok=True)
                temp = path.with_suffix('.partial.wav')
                temp.write_bytes(data)
                metadata = info(temp)
                temp.replace(path)
                result = record(relative, metadata, seconds, id=case['id'], payload=payload,
                                reused=False, cold_generation=not seen)
                report['baseline'].append(result)
                seen[case['text']] = result
                write_json(output / 'result.json', report)
                print(f'GPT {case["id"]}: {result["duration_seconds"]:.2f}s, RTF {result["rtf"]:.3f}', flush=True)
        finally:
            # Only this Popen child is stopped; never stop an existing production service.
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=20)
            report['baseline_process_exit_code'] = process.returncode
            write_json(output / 'result.json', report)


def voxcpm(output, report):
    import importlib.metadata
    import torch
    from voxcpm import VoxCPM
    if report['voxcpm'] or report['long_segments']:
        raise ValueError('Vox generation already started; use a fresh experiment, no implicit rerun')
    if not torch.cuda.is_available():
        raise RuntimeError('Real CUDA required')
    spec = report['specification']
    root = Path(report['runtime_root'])
    actual_revision = subprocess.check_output(['git', '-C', str(root / 'shared/tools/VoxCPM'),
                                               'rev-parse', 'HEAD'], text=True).strip()
    if actual_revision != spec['source_revision']:
        raise ValueError('VoxCPM source differs from task 01 freeze')
    report['voxcpm_source_revision'] = actual_revision
    report['packages'] = {p: importlib.metadata.version(p) for p in ('torch', 'voxcpm', 'soundfile')}
    (output / 'voxcpm-environment.freeze.txt').write_text(subprocess.check_output(
        [sys.executable, '-m', 'pip', 'freeze', '--all'], text=True, timeout=60), encoding='utf-8')
    report['gpu'] = torch.cuda.get_device_name(0)
    torch.cuda.reset_peak_memory_stats()
    load_start = time.perf_counter()
    model = VoxCPM.from_pretrained(str(root / 'shared/models/VoxCPM2'), local_files_only=True,
        load_denoiser=spec['load_denoiser'], optimize=spec['optimize'], device=spec['device'])
    torch.cuda.synchronize()
    report['voxcpm_load_seconds'] = time.perf_counter() - load_start
    print(f'VoxCPM2 ready: {report["voxcpm_load_seconds"]:.2f}s', flush=True)

    def generate(text, emotion, relative, **extra):
        instruction = '保持参考音色，吐字清晰，' + EMOTIONS[emotion]
        synthesis = f'({instruction}){text}'
        started = time.perf_counter()
        with torch.inference_mode():
            samples = model.generate(text=synthesis, reference_wav_path=str(output / 'reference.wav'),
                                     **spec['generation'])
        torch.cuda.synchronize()
        seconds = time.perf_counter() - started
        metadata = save_audio(output, relative, samples, model.tts_model.sample_rate)
        result = record(relative, metadata, seconds, instruction=instruction, synthesis_text=synthesis, **extra)
        print(f'VOX {relative}: {result["duration_seconds"]:.2f}s, RTF {result["rtf"]:.3f}', flush=True)
        return result

    report['warmup'] = generate('我们正在等待来自远方的消息。', 'narrative', 'voxcpm2/warmup.wav')
    for case in report['cases']:
        report['voxcpm'].append(generate(case['text'], case['emotion'], f'voxcpm2/{case["id"]}.wav', id=case['id']))
        write_json(output / 'result.json', report)
    report['status'] = 'comparisons_ready_long_running'
    write_json(output / 'result.json', report)
    package(output, report)
    total_audio = total_generation = 0.0
    source = report['long_source']
    for index in range(300):  # Bounded stress test, never an unbounded generation loop.
        chunk = source['chunks'][index % len(source['chunks'])]
        item = generate(chunk['text'], 'narrative', f'long/{index + 1:04d}.wav',
            id=f'long-{index + 1:04d}', source_start=chunk['start'], source_end=chunk['end'],
            source_cycle=index // len(source['chunks']) + 1,
            start_sample=round(total_audio * model.tts_model.sample_rate))
        total_audio += item['duration_seconds']
        total_generation += item['generation_seconds']
        item['end_sample'] = item['start_sample'] + item['audio']['sample_count']
        report['long_segments'].append(item)
        for target in (300, 600, 1800):
            if total_audio >= target and not any(c['target_seconds'] == target for c in report['checkpoints']):
                report['checkpoints'].append(dict(target_seconds=target, actual_seconds=total_audio,
                    generation_seconds=total_generation, rtf=total_generation / total_audio,
                    segment_count=len(report['long_segments'])))
        write_json(output / 'result.json', report)
        if total_audio >= source['target_seconds']:
            break
    else:
        raise RuntimeError('Long experiment hit 300 segment bound before target')
    # Same content at the end: listener can assess fixed-reference voice drift.
    report['fixed_voice_end'] = generate(EMOTION_TEXT, 'narrative', 'voxcpm2/fixed-voice-end.wav')
    merge_start = time.perf_counter()
    with wave.open(str(output / 'long-narration.wav'), 'wb') as merged:
        merged.setparams((1, 2, model.tts_model.sample_rate, 0, 'NONE', 'not compressed'))
        for item in report['long_segments']:
            with wave.open(str(output / item['audio_path']), 'rb') as part:
                merged.writeframesraw(part.readframes(part.getnframes()))
    report['long_audio'] = dict(path='long-narration.wav', **info(output / 'long-narration.wav'))
    if report['long_audio']['sample_count'] != sum(s['audio']['sample_count'] for s in report['long_segments']):
        raise ValueError('Merged sample count differs')
    report['postprocess_seconds'] = time.perf_counter() - merge_start
    report['peak_allocated_bytes'] = torch.cuda.max_memory_allocated()
    report['peak_reserved_bytes'] = torch.cuda.max_memory_reserved()
    report['status'] = 'generated_pending_listening'
    write_json(output / 'result.json', report)
    package(output, report)


def package(output, report):
    if len(report['baseline']) != len(report['cases']) or len(report['voxcpm']) != len(report['cases']):
        raise ValueError('Both engines must complete the comparison corpus')
    blind = output / 'blind'
    blind.mkdir(exist_ok=True)
    key_path = output / 'blind-key.json'
    key = read_json(key_path) if key_path.exists() else {}
    if not key:
        cases = list(report['cases'])
        random.SystemRandom().shuffle(cases)
        for number, case in enumerate(cases, 1):
            engines = ['baseline', 'voxcpm']
            random.SystemRandom().shuffle(engines)
            key[f'P{number:02d}'] = dict(case_id=case['id'], emotion=case['emotion'], A=engines[0], B=engines[1])
        write_json(key_path, key)
    public = []
    for pair_id, mapping in key.items():
        case = next(c for c in report['cases'] if c['id'] == mapping['case_id'])
        for label in ('A', 'B'):
            item = next(r for r in report[mapping[label]] if r['id'] == case['id'])
            target = blind / f'{pair_id}-{label}.wav'
            if not target.exists():
                shutil.copyfile(output / item['audio_path'], target)
        public.append(dict(id=pair_id, text=case['text'], emotion_test=case['id'].startswith('emotion-')))
    write_json(blind / 'pairs.json', public)
    rows = []
    for pair in public:
        players = ''.join(f'<label>{label} <audio controls preload="none" src="{pair["id"]}-{label}.wav"></audio></label>' for label in ('A', 'B'))
        options = ''.join(f'<option>{e}</option>' for e in EMOTIONS)
        rows.append(f'<section data-id="{pair["id"]}"><h2>{pair["id"]}</h2><p>{html.escape(pair["text"])}</p>{players}'
            '<p>整体偏好 <select class="preference"><option value="">请选择</option><option>A</option><option>B</option><option>相当</option></select></p>'
            + ''.join(f'<p>{label} 听到的情绪 <select class="emotion{label}"><option value="">未评</option>{options}</select></p>' for label in ('A', 'B'))
            + '<textarea placeholder="记录漏读、重复、发音、自然度、尾音和音色问题；请注明 A/B"></textarea></section>')
    drift = ''
    if report.get('fixed_voice_end'):
        for name, path in [('voice-start.wav', 'voxcpm2/emotion-narrative.wav'),
                           ('voice-end.wav', 'voxcpm2/fixed-voice-end.wav')]:
            if not (blind / name).exists():
                shutil.copyfile(output / path, blind / name)
        drift = '<h2>长文案音色一致性（非盲测）</h2><p>同文案起点 / 终点</p><audio controls src="voice-start.wav"></audio><audio controls src="voice-end.wav"></audio><p><a href="../long-narration.wav">完整长音频</a></p><textarea id="drift" placeholder="记录前中后音色、尾音与拼接情况"></textarea>'
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>TTS-VOX-02 盲听</title>
<style>body{max-width:900px;margin:36px auto;font:17px/1.6 system-ui;background:#f5f6f8;color:#182332}section{background:white;padding:24px;margin:20px 0;border-radius:12px}audio{display:block;width:100%;margin:10px 0}textarea{width:95%;min-height:80px}button{padding:12px 24px}label{display:block}</style>
<h1>TTS-VOX-02 匿名 A/B 试听</h1><p>请先听再评分，避免查看上级目录的答案。所有配对为同文案、同参考音频；七组情绪题文案相同，请独立判断每段听到的情绪。音频保持原始响度。先提交记录再揭晓引擎；未填项目不代表通过。</p>
<p>试听人 <input id="listener"> <button onclick="save()">导出试听记录</button></p>'''
    page += ''.join(rows) + drift + '''<script>
function save(){const rows=[...document.querySelectorAll('section')].map(s=>({pair:s.dataset.id,preference:s.querySelector('.preference').value,emotionA:s.querySelector('.emotionA').value,emotionB:s.querySelector('.emotionB').value,notes:s.querySelector('textarea').value}));const value={task_id:'TTS-VOX-02',listener:document.querySelector('#listener').value,recorded_at:new Date().toISOString(),pairs:rows,fixed_voice_notes:document.querySelector('#drift')?.value||'',acceptance:'requires_review'};let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));a.download='TTS-VOX-02-listening.json';a.click();}
</script></html>'''
    (blind / 'index.html').write_text(page, encoding='utf-8')
    print(f'Blind listening: {blind / "index.html"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare', 'baseline', 'voxcpm', 'package'])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--long-text', type=Path)
    parser.add_argument('--long-seconds', type=float, default=1800)
    args = parser.parse_args()
    os.environ['HF_HUB_OFFLINE'] = os.environ['TRANSFORMERS_OFFLINE'] = '1'
    if args.phase == 'prepare':
        if args.long_text is None or args.long_seconds <= 0:
            parser.error('prepare requires --long-text and positive --long-seconds')
        prepare(args)
        return
    if args.output is None:
        parser.error('--output is required')
    output = args.output.resolve()
    report = read_json(output / 'result.json')
    started = time.perf_counter()
    try:
        globals()[args.phase](output, report)
    except Exception:
        report['status'] = 'failed'
        report['failure'] = traceback.format_exc()
        raise
    finally:
        report[f'{args.phase}_elapsed_seconds'] = time.perf_counter() - started
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        write_json(output / 'result.json', report)


if __name__ == '__main__':
    main()
