"""TTS-VOX-04: one real GPU sample through the unified TTS factory."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import sys
from threading import RLock
import time
import traceback

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE/'src'))
from video_ai.adapters.common import HttpClient
from video_ai.adapters.tts import create_tts_client
from video_ai.config import load_config, read_json
from video_ai.runtime.logging import RunLogger
from video_ai.runtime.manifest import thaw
from video_ai.runtime.storage import VideoStorage
from video_ai.runtime.storage_files import safe_path, write_record
from video_ai.voxcpm.contracts import wav_metadata
from video_ai.voxcpm.process import VoxServiceProcess, request_json


class ExperimentLogger(RunLogger):
    """Use the existing evidence writer under this experiment's scratch directory."""
    def __init__(self, directory):
        self.root = directory/'logs'
        self.root.mkdir()
        self.production = False
        self.started_at = time.monotonic()
        self._lock = RLock()

    def path(self, relative_name):
        return safe_path(self.root/relative_name, self.root)


def main():
    root = VideoStorage().runtime_root
    output = root/'scratch/benchmarks/TTS-VOX-04'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output.mkdir(parents=True)
    report = dict(task_id='TTS-VOX-04', status='running', output=str(output))
    controller = None
    try:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        controller = VoxServiceProcess(root, output/'state', port=port)
        started = time.monotonic()
        report['health'] = controller.start()
        report['cold_service_ready_seconds'] = time.monotonic()-started
        source = root/'shared/config/production.json'
        config = load_config(source)
        raw = thaw(config.raw)
        spec = read_json(SOURCE/'config/voxcpm2-deployment.json')
        raw['tts'] = dict(engine='voxcpm2', model_revision=spec['model_revision'])
        raw['services']['tts'] = controller.url
        config = load_config(source, raw=raw, voice=config.voice)
        write_record(output/'effective-config.json', thaw(config))
        logger = ExperimentLogger(output)
        client = create_tts_client(config, HttpClient(config.services['tts'], 180, logger), request_scope=str(output))
        print('Unified adapter: generating one real sample', flush=True)
        started = time.monotonic()
        response = client.synthesize('旅行者二号正在遥远的星际空间航行。', unit_id='speech_0001')
        report['adapter_seconds'] = time.monotonic()-started
        audio = output/'adapter.wav'; audio.write_bytes(response.body)
        report['audio'] = dict(path=str(audio), sha256=hashlib.sha256(response.body).hexdigest(), **wav_metadata(audio))
        code, before = request_json(controller.url, '/tts/tasks/'+client.request_id('speech_0001'))
        assert code == 200 and before['status'] == 'completed'
        # A new client represents a caller reconstructed from its frozen configuration.
        again = create_tts_client(config, HttpClient(config.services['tts'], 30, logger), request_scope=str(output))
        reused = again.synthesize('旅行者二号正在遥远的星际空间航行。', unit_id='speech_0001')
        code, after = request_json(controller.url, '/tts/tasks/'+client.request_id('speech_0001'))
        assert code == 200 and before == after and reused.body == response.body
        report.update(completed_task=after, fresh_client_reused_unchanged_task=True, status='passed')
    except BaseException:
        report.update(status='failed', error=traceback.format_exc())
        raise
    finally:
        if controller is not None:
            report['owned_process_exit_code'] = controller.stop()
        write_record(output/'result.json', report)
        print(json.dumps(dict(status=report['status'], output=str(output),
                              process_exit_code=report.get('owned_process_exit_code')), ensure_ascii=False), flush=True)
    if report.get('owned_process_exit_code') != 0:
        raise RuntimeError('owned VoxCPM2 process did not exit cleanly')


if __name__ == '__main__':
    main()
