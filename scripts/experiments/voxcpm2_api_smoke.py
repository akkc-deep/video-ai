"""TTS-VOX-03 real local API evidence; two short inferences, no video generation."""
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import sys
import time
import traceback
from urllib.request import urlopen

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE/'src'))
from video_ai.runtime.storage import VideoStorage
from video_ai.runtime.storage_files import write_record
from video_ai.voxcpm.process import VoxServiceProcess, request_json


def main():
    root = VideoStorage().runtime_root
    output = root/'scratch/benchmarks/TTS-VOX-03'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output.mkdir(parents=True)
    with socket.socket() as socket_:
        socket_.bind(('127.0.0.1', 0))
        port = socket_.getsockname()[1]
    report = dict(task_id='TTS-VOX-03', status='running', output=str(output),
        started_at=datetime.now(timezone.utc).isoformat(), events=[], process_exit_codes=[])
    controller = None
    started = time.perf_counter()

    def observe(name, response, expected):
        status, value = response
        if status != expected:
            raise AssertionError(f'{name}: HTTP {status}: {value}')
        report['events'].append(dict(name=name, http_status=status, response=value))
        write_record(output/'result.json', report)
        return value

    def wait_task(request_id, statuses, timeout=180):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            code, task = request_json(controller.url, '/tts/tasks/'+request_id)
            if code != 200:
                raise AssertionError(f'query {request_id}: {code}: {task}')
            if task['status'] in statuses:
                return task
            if task['status'] in ('failed', 'cancelled', 'completed'):
                raise AssertionError(f'unexpected terminal status: {task}')
            time.sleep(.1)
        raise TimeoutError(f'{request_id} did not reach {statuses}')

    try:
        controller = VoxServiceProcess(root, output/'state', port=port)
        load_started = time.perf_counter()
        report['health'] = controller.start()
        report['cold_service_ready_seconds'] = time.perf_counter() - load_started
        print('Service ready', flush=True)
        observe('voices', request_json(controller.url, '/voices'), 200)
        body = dict(request_id='api_short', text='旅行者二号正在遥远的星际空间航行。')
        observe('submitted', request_json(controller.url, '/tts/generate', body), 202)
        wait_task('api_short', {'running'})
        observe('duplicate_running', request_json(controller.url, '/tts/generate', body), 200)
        observe('conflict', request_json(controller.url, '/tts/generate', dict(body, seed=9)), 409)
        observe('queued', request_json(controller.url, '/tts/generate', dict(body, request_id='cancel_queued')), 202)
        queued = observe('cancel_queued', request_json(controller.url, '/tts/tasks/cancel_queued/cancel', {}), 200)
        assert queued['status'] == 'cancelled'
        complete = wait_task('api_short', {'completed'})
        report['completed_task'] = complete
        with urlopen(controller.url+'/tts/tasks/api_short/audio', timeout=10) as response:
            audio = response.read()
        assert audio[:4] == b'RIFF' and audio[8:12] == b'WAVE'
        report['downloaded_audio_bytes'] = len(audio)
        assert complete['result']['sample_count'] > 0 and complete['result']['sample_rate'] == 48000
        print(f'Generated {complete["result"]["duration_ms"]/1000:.2f}s real audio', flush=True)
        observe('cancel_running_submit', request_json(controller.url, '/tts/generate',
            dict(body, request_id='cancel_running', text='这段语音用于验证正在运行任务的取消。')), 202)
        wait_task('cancel_running', {'running'})
        cancelling = observe('cancel_requested', request_json(controller.url, '/tts/tasks/cancel_running/cancel', {}), 200)
        assert cancelling['status'] == 'cancel_requested'
        report['cancelled_task'] = wait_task('cancel_running', {'cancelled'})
        observe('cancelled_audio_unavailable', request_json(controller.url, '/tts/tasks/cancel_running/audio'), 409)
        report['process_exit_codes'].append(controller.stop())
        assert report['process_exit_codes'][-1] == 0
        print('Owned service stopped; restarting same task store', flush=True)
        controller = VoxServiceProcess(root, output/'state', port=port)
        report['restart_health'] = controller.start()
        persisted = observe('duplicate_after_restart', request_json(controller.url, '/tts/generate', body), 200)
        assert persisted == complete
        report['completed_reused_after_restart'] = True
        report['process_exit_codes'].append(controller.stop())
        assert report['process_exit_codes'][-1] == 0
        report['status'] = 'completed'
        print('API generation, idempotency, conflict, queued/running cancel, restart and owned cleanup: OK', flush=True)
    except BaseException:
        report['status'] = 'failed'
        report['failure'] = traceback.format_exc()
        raise
    finally:
        if controller is not None and controller.process is not None and controller.process.poll() is None:
            report['process_exit_codes'].append(controller.stop())
        report['elapsed_seconds'] = time.perf_counter()-started
        write_record(output/'result.json', report)
        print(f'Evidence: {output}', flush=True)


if __name__ == '__main__':
    main()
