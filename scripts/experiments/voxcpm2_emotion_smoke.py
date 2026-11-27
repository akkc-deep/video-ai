"""TTS-VOX-05: one real full-script Ollama plan and one directed GPU sample."""
from datetime import datetime
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE/'src'))
from video_ai.adapters.common import HttpClient
from video_ai.adapters.ollama_emotion import EmotionDirector
from video_ai.adapters.tts import create_tts_client
from video_ai.config import load_config, read_json
from video_ai.runtime.environment import build_child_env
from video_ai.runtime.manifest import thaw
from video_ai.runtime.paths import RuntimePaths
from video_ai.runtime.processes import stop_process
from video_ai.runtime.storage import VideoStorage
from video_ai.runtime.storage_files import write_record
from video_ai.voxcpm.contracts import wav_metadata
from video_ai.voxcpm.process import VoxServiceProcess, request_json
from voxcpm2_adapter_smoke import ExperimentLogger


TEXT = ('旅行者 2 号已经飞行了 47 年。NASA 的信号跨越数十亿 km，来到地球。\r\n'
        '看啊，星云在黑暗中绽放，宇宙竟然如此壮丽！\r\n'
        '可是，那颗熟悉的蓝色星球，早已远得无法看清。只有孤独的探测器继续前行。\r\n'
        '轻轻闭上眼睛，让思绪随星光慢慢安静下来。')


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def main():
    root = VideoStorage().runtime_root
    output = root/'scratch/benchmarks/TTS-VOX-05'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output.mkdir(parents=True)
    report = dict(task_id='TTS-VOX-05', status='running', output=str(output))
    logger = ExperimentLogger(output)
    source = root/'shared/config/production.json'
    config = load_config(source)
    ollama = controller = None
    try:
        url = f'http://127.0.0.1:{free_port()}'
        env = build_child_env(RuntimePaths.from_config(config))
        env['OLLAMA_HOST'] = url.removeprefix('http://')
        with (output/'ollama.log').open('xb') as stream:
            ollama = subprocess.Popen([str(config.tools['ollama_executable']), 'serve'],
                cwd=config.tools['ollama_executable'].parent, env=env, stdout=stream,
                stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            deadline = time.monotonic()+30
            while True:
                if ollama.poll() is not None:
                    raise RuntimeError('owned Ollama exited; see ollama.log')
                try:
                    status, version = request_json(url, '/api/version', timeout=1)
                    if status == 200 and version.get('version'):
                        report['ollama_version'] = version
                        break
                except (OSError, ValueError):
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError('owned Ollama startup timed out')
                time.sleep(.1)
            print('Ollama: planning the complete script once', flush=True)
            started = time.monotonic()
            plan = EmotionDirector(HttpClient(url, 240, logger)).plan(TEXT)
            report['planning_seconds'] = time.monotonic()-started
            report['plan'] = plan
            assert plan['status'] == 'planned', plan['fallback']
            assert ''.join(s['original_text'] for s in plan['spans']) == TEXT
            assert ''.join(s['synthesis_text'] for s in plan['spans']) == TEXT
            report['original_coverage_verified'] = True
            report['owned_ollama_exit_code'] = stop_process(ollama)
        # keep_alive=0 unloads the model after planning; only our server is stopped.
        controller = VoxServiceProcess(root, output/'state', port=free_port())
        report['health'] = controller.start()
        candidates = [s for s in plan['spans'] if s['synthesis_text'].strip() and len(s['synthesis_text']) <= 250]
        selected = max(candidates, key=lambda s:s['emotion_intensity'])
        report['selected_span'] = selected
        raw = thaw(config.raw)
        spec = read_json(SOURCE/'config/voxcpm2-deployment.json')
        raw['tts'] = dict(engine='voxcpm2', model_revision=spec['model_revision'],
            emotion=selected['emotion'], emotion_intensity=selected['emotion_intensity'],
            instruction=selected['instruction'])
        raw['services']['tts'] = controller.url
        directed = load_config(source, raw=raw, voice=config.voice)
        client = create_tts_client(directed, HttpClient(controller.url, 180, logger), request_scope=str(output))
        print('VoxCPM2: synthesizing one planned range', flush=True)
        started = time.monotonic()
        response = client.synthesize(selected['synthesis_text'], unit_id='speech_0001')
        report['synthesis_seconds'] = time.monotonic()-started
        audio = output/'directed.wav'
        audio.write_bytes(response.body)
        report['audio'] = dict(path=str(audio), **wav_metadata(audio))
        status, task = request_json(controller.url, '/tts/tasks/'+client.request_id('speech_0001'))
        assert status == 200 and task['status'] == 'completed'
        frozen = task['request']
        assert frozen['text'] == selected['original_text']
        for name in ('emotion', 'emotion_intensity', 'instruction'):
            assert frozen[name] == selected[name]
        assert selected['instruction'] in frozen['synthesis_text']
        report.update(completed_task=task, instruction_consumed=True, status='passed')
    except BaseException:
        report.update(status='failed', error=traceback.format_exc())
        raise
    finally:
        if ollama is not None and ollama.poll() is None:
            report['owned_ollama_exit_code'] = stop_process(ollama)
        if controller is not None:
            report['owned_vox_exit_code'] = controller.stop()
        write_record(output/'result.json', report)
        print(json.dumps(dict(status=report['status'], output=str(output)), ensure_ascii=False), flush=True)
    if report.get('owned_vox_exit_code') != 0:
        raise RuntimeError('owned VoxCPM2 process did not exit cleanly')


if __name__ == '__main__':
    main()
