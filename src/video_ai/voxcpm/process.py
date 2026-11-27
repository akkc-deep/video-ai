"""Owned VoxCPM2 Popen lifecycle, without legacy service or GPU admission changes."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from ..runtime.processes import stop_process
from ..runtime.services import ServiceConflictError, ServiceStartError
from .store import state_directory


def request_json(url, path, body=None, *, timeout=10, token=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['X-Vox-Stop-Token'] = token
    request = Request(url+path, data=data, headers=headers)
    try:
        response = urlopen(request, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())


class VoxServiceProcess:
    def __init__(self, runtime_root, state_dir, *, port=9881, voice_profile=None):
        self.root = Path(runtime_root).absolute()
        self.directory = state_directory(state_dir, self.root)
        from .voices import resolve_voice_profile
        self.voice_profile = resolve_voice_profile(voice_profile, self.root) if voice_profile is not None else None
        self.port = port
        self.url = f'http://127.0.0.1:{port}'
        self.session_id = uuid4().hex
        self._token = secrets.token_urlsafe(32)
        self.process = None
        self._log = None

    def start(self, timeout=180):
        if self.process is not None:
            raise ValueError('this launcher already owns a process')
        try:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', self.port))
        except OSError as error:
            raise ServiceConflictError('VoxCPM2 port is occupied or unavailable; no process is owned') from error
        self.directory.mkdir(parents=True, exist_ok=True)
        self._log = (self.directory/f'service-{self.session_id}.log').open('xb')
        env = dict(os.environ)
        env.update(VIDEO_AI_RUNTIME_ROOT=str(self.root), VIDEO_AI_VOX_STOP_TOKEN=self._token,
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONUTF8='1')
        source = Path(__file__).resolve().parents[2]
        env['PYTHONPATH'] = str(source) + os.pathsep + env.get('PYTHONPATH', '')
        command = [str(self.root/'shared/envs/voxcpm2/Scripts/python.exe'), '-B', '-u',
            '-m', 'video_ai.voxcpm.server', '--state-dir', str(self.directory),
            '--port', str(self.port), '--session-id', self.session_id]
        if self.voice_profile is not None:
            command.extend(['--voice-profile', str(self.voice_profile)])
        try:
            self.process = subprocess.Popen(command, cwd=source.parent, env=env, stdout=self._log,
                stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise ServiceStartError('VoxCPM2 exited during startup; see service log')
                try:
                    status, health = request_json(self.url, '/health', timeout=1)
                except (OSError, ValueError):
                    time.sleep(.1)
                    continue
                if health.get('session_id') != self.session_id:
                    raise ServiceConflictError('occupied port belongs to another service session')
                if health.get('status') == 'failed':
                    raise ServiceStartError(health.get('error'))
                if status == 200 and health.get('service') == 'video-ai-voxcpm2':
                    return health
                time.sleep(.1)
            raise ServiceStartError('VoxCPM2 startup deadline exceeded')
        except BaseException:
            self.stop(grace_seconds=2)
            raise

    def stop(self, grace_seconds=120):
        if self.process is None:
            if self._log is not None:
                self._log.close()
                self._log = None
            return None
        try:
            if self.process.poll() is None:
                try:
                    request_json(self.url, '/shutdown', {}, timeout=2, token=self._token)
                    self.process.wait(timeout=grace_seconds)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    stop_process(self.process)
            return self.process.returncode
        finally:
            if self._log is not None:
                self._log.close()
                self._log = None
