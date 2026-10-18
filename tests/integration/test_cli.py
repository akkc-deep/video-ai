import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

SOURCE = Path(__file__).resolve().parents[2]


def test_help_and_unknown_command_have_expected_exit_codes(capsys):
    from video_ai.cli import main
    assert main(['--help']) == 0
    assert 'doctor' in capsys.readouterr().out
    assert main(['run']) == 2


def test_cli_json_report_and_success_exit(resource_config, capability_runner, monkeypatch, capsys, tmp_path):
    from video_ai import cli
    from video_ai.runtime.preflight import preflight
    monkeypatch.setattr(cli, 'load_config', lambda p: resource_config)
    monkeypatch.setattr(cli, 'preflight', lambda c, **kw: preflight(c, runner=capability_runner, **kw))
    assert cli.main(['doctor', '--config', 'relative.json', '--json']) == 0
    data = json.loads(capsys.readouterr().out)
    assert data['schema_version'] == 1 and data['passed']
    assert data['inference_verified'] is False


def test_cli_resolves_all_relative_flags_from_invocation_cwd(monkeypatch, resource_config, capability_runner, tmp_path, capsys):
    from video_ai import cli
    from video_ai.runtime.preflight import preflight
    monkeypatch.chdir(tmp_path)
    captured = {}
    def load(path):
        captured['config'] = path
        return resource_config
    def check(config, **kwargs):
        captured.update(kwargs)
        return preflight(config, runner=capability_runner)
    monkeypatch.setattr(cli, 'load_config', load)
    monkeypatch.setattr(cli, 'preflight', check)
    assert cli.main(['doctor', '--config', '配置/main.json', '--script', './中文/a.txt', '--output', 'movie.mp4', '--json']) == 0
    assert captured == {'config': tmp_path / '配置/main.json', 'script': tmp_path / '中文/a.txt', 'output': tmp_path / 'movie.mp4'}
    assert Path.cwd() == tmp_path


def test_configuration_error_exit_two_and_interrupt_exit_130(monkeypatch, capsys, tmp_path):
    from video_ai import cli
    assert cli.main(['doctor', '--config', str(tmp_path / 'absent.json')]) == 2
    monkeypatch.setattr(cli, 'load_config', lambda p: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert cli.main(['doctor', '--config', 'unused']) == 130


def test_powershell_start_keeps_json_clean_and_paths_relative_to_call_site(tmp_path):
    # Missing resources must be a fixture, independent of real migration state.
    raw=json.loads((SOURCE/'config/production.example.json').read_text(encoding='utf-8'))
    raw['voice_config']=str(SOURCE/'config/voice.example.json')
    raw['tools']['ffmpeg']=str(tmp_path/'absent-ffmpeg.exe')
    for name in raw['workflows']:
        raw['workflows'][name]=str((SOURCE/'config'/raw['workflows'][name]).resolve())
    config_path=tmp_path/'missing-resources.json'
    config_path.write_text(json.dumps(raw),encoding='utf-8')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                             str(SOURCE / 'scripts/start_windows.ps1'), 'doctor', '--config',
                             os.path.relpath(config_path, tmp_path), '--json'],
                            cwd=str(tmp_path), capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert not data['passed'] and data['inference_verified'] is False
    assert 'Log:' in result.stderr
