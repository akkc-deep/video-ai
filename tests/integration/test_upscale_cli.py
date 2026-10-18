"""TEST ONLY CLI boundary results; no Comfy service or model inference."""
import json
from pathlib import Path

import pytest

from video_ai.cli import main
from video_ai.config import load_config
from video_ai.runtime import upscale_checks as upscale


SOURCE = Path(__file__).resolve().parents[2]
CONFIG = SOURCE / 'config/production.example.json'
COMMANDS = ('prepare-upscaled-clips', 'resume-upscaled-clips', 'finalize-upscaled-clips')
REQUIRED_ARGUMENTS = [
    ('prepare-upscaled-clips', '--config'),
    ('prepare-upscaled-clips', '--run-dir'),
    ('resume-upscaled-clips', '--config'),
    ('resume-upscaled-clips', '--run-dir'),
    ('finalize-upscaled-clips', '--config'),
    ('finalize-upscaled-clips', '--run-dir'),
    ('finalize-upscaled-clips', '--review'),
]


def arguments(command, run, *, config=CONFIG, review=None, json_output=True):
    values = [command, '--config', str(config), '--run-dir', str(run)]
    if command == 'finalize-upscaled-clips':
        values += ['--review', str(review or run / 'logs/upscale/semantic-review.json')]
    if json_output:
        values.append('--json')
    return values


def install_result(monkeypatch, command, status):
    """Only replace the inference boundary; config/path/serialization stay real."""
    def result(config, *, run_dir, **kwargs):
        assert config.config_file == CONFIG.resolve()
        assert 'upscale_mapping' not in config.workflows
        if command != 'finalize-upscaled-clips':
            assert kwargs == {}
        else:
            assert kwargs == {'review_path': run_dir / 'logs/upscale/semantic-review.json'}
        completed = status == 'completed'
        return upscale.UpscaledClipsResult(
            completed, run_dir, run_dir / 'upscaled-clips-draft.json',
            run_dir / 'upscaled-clips.json', 7, completed, status,
        )
    monkeypatch.setattr(upscale, command.replace('-', '_'), result)


@pytest.mark.parametrize('command', COMMANDS)
@pytest.mark.parametrize('status,want', [('review_required', 1), ('failed', 1), ('completed', 0)])
def test_json_result_and_exit_mapping(tmp_path, monkeypatch, capsys, command, status, want):
    install_result(monkeypatch, command, status)
    assert main(arguments(command, tmp_path)) == want
    captured = capsys.readouterr()
    assert captured.err == ''
    assert json.loads(captured.out) == {
        'passed': status == 'completed',
        'run_dir': str(tmp_path),
        'draft_path': str(tmp_path / 'upscaled-clips-draft.json'),
        'clips_path': str(tmp_path / 'upscaled-clips.json'),
        'clip_count': 7,
        'ready_for_composition': status == 'completed',
        'status': status,
    }


@pytest.mark.parametrize('command', COMMANDS)
@pytest.mark.parametrize('status,want', [('review_required', 1), ('failed', 1), ('completed', 0)])
def test_plain_result_reports_composition_readiness(tmp_path, monkeypatch, capsys, command, status, want):
    install_result(monkeypatch, command, status)
    assert main(arguments(command, tmp_path, json_output=False)) == want
    text = capsys.readouterr().out
    assert text.startswith(f'{status}: clips=7; ready_for_composition={str(status == "completed").lower()}; ')
    assert str(tmp_path / 'upscaled-clips.json') in text
    assert 'ready_for_upscale' not in text


@pytest.mark.parametrize('command', COMMANDS)
@pytest.mark.parametrize('exception,want', [
    (upscale.UpscaleRefusal('TEST ONLY stage refusal'), 2),
    (ValueError('TEST ONLY path refusal'), 2),
    (OSError('TEST ONLY runtime I/O failure'), 1),
    (KeyboardInterrupt(), 130),
])
def test_runtime_error_exit_mapping(tmp_path, monkeypatch, capsys, command, exception, want):
    def fail(*args, **kwargs):
        raise exception
    monkeypatch.setattr(upscale, command.replace('-', '_'), fail)
    assert main(arguments(command, tmp_path)) == want
    captured = capsys.readouterr()
    assert captured.out == ''
    assert captured.err


@pytest.mark.parametrize('command,missing', REQUIRED_ARGUMENTS)
def test_missing_required_arguments_refused(tmp_path, monkeypatch, command, missing):
    def forbidden(*args, **kwargs):
        pytest.fail('missing arguments reached inference')
    monkeypatch.setattr(upscale, command.replace('-', '_'), forbidden)
    args = arguments(command, tmp_path)
    index = args.index(missing)
    del args[index:index + 2]
    assert main(args) == 2


@pytest.mark.parametrize('command', COMMANDS)
@pytest.mark.parametrize('kind,want', [('missing', 1), ('directory', 1), ('invalid_json', 2), ('invalid_schema', 2), ('unknown_mapping', 2)])
def test_actual_config_validation_before_runtime(tmp_path, monkeypatch, capsys, command, kind, want):
    path = tmp_path / 'TEST-ONLY-config.json'
    if kind == 'directory':
        path.mkdir()
    if kind == 'invalid_json':
        path.write_text('{', encoding='utf-8')
    if kind == 'invalid_schema':
        data = json.loads(CONFIG.read_text(encoding='utf-8'))
        data['schema_version'] = True
        path.write_text(json.dumps(data), encoding='utf-8')
    if kind == 'unknown_mapping':
        data = json.loads(CONFIG.read_text(encoding='utf-8'))
        data['workflows']['upscale_mapping'] = 'upscale_api.mapping.json'
        path.write_text(json.dumps(data), encoding='utf-8')
    def forbidden(*args, **kwargs):
        pytest.fail('invalid configuration reached inference')
    monkeypatch.setattr(upscale, command.replace('-', '_'), forbidden)
    assert main(arguments(command, tmp_path, config=path)) == want
    text = capsys.readouterr().err
    assert text
    if kind == 'invalid_schema':
        assert 'schema_version' in text
    if kind == 'unknown_mapping':
        assert 'upscale_mapping' in text


@pytest.mark.parametrize('command,field', REQUIRED_ARGUMENTS)
@pytest.mark.parametrize('bad', ['', ' ', 'D:relative', '//server/share', 'D:/VideoSi/name:stream', 'D:/VideoSi/CON', 'D:/VideoSi/trailing.'])
def test_windows_aliases_refused_before_runtime(tmp_path, monkeypatch, command, field, bad):
    def forbidden(*args, **kwargs):
        pytest.fail('invalid path reached inference')
    monkeypatch.setattr(upscale, command.replace('-', '_'), forbidden)
    args = arguments(command, tmp_path)
    args[args.index(field) + 1] = bad
    assert main(args) == 2


@pytest.mark.parametrize('command', COMMANDS)
def test_relative_paths_use_captured_cwd_and_keep_lexical_run_review(tmp_path, monkeypatch, capsys, command):
    import video_ai.cli as cli
    invocation = tmp_path / 'invocation'
    changed = tmp_path / 'changed'
    invocation.mkdir()
    changed.mkdir()
    monkeypatch.chdir(invocation)
    expected_run = invocation / 'alias' / '..' / 'run'
    expected_review = invocation / 'alias' / '..' / 'review.json'
    config_copy = invocation / 'TEST-ONLY-config.json'
    data = json.loads(CONFIG.read_text(encoding='utf-8'))
    data['voice_config'] = str(SOURCE / 'config/voice.example.json')
    config_copy.write_text(json.dumps(data), encoding='utf-8')

    def load_then_change_cwd(path):
        assert path == config_copy
        config = load_config(path)
        monkeypatch.chdir(changed)
        return config

    def result(config, *, run_dir, **kwargs):
        assert config.config_file == config_copy
        assert run_dir == expected_run
        assert kwargs == ({'review_path': expected_review} if command == 'finalize-upscaled-clips' else {})
        return upscale.UpscaledClipsResult(False, run_dir, run_dir / 'upscaled-clips-draft.json',
                                         run_dir / 'upscaled-clips.json', 7, False, 'review_required')

    monkeypatch.setattr(cli, 'load_config', load_then_change_cwd)
    monkeypatch.setattr(upscale, command.replace('-', '_'), result)
    assert main(arguments(command, Path('alias/../run'), config='TEST-ONLY-config.json',
                          review='alias/../review.json')) == 1
    assert json.loads(capsys.readouterr().out)['run_dir'] == str(expected_run)


@pytest.mark.parametrize('command', COMMANDS)
def test_actual_runtime_missing_manifest_is_stage_refusal(runtime_run, capsys, command):
    # Existing runtime refuses before service admission; never starts Comfy.
    run, _, _ = runtime_run
    assert main(arguments(command, run)) == 2
    assert 'manifest.json' in capsys.readouterr().err


def test_prepare_rejects_review_argument(tmp_path):
    assert main(arguments('prepare-upscaled-clips', tmp_path) + ['--review', 'review.json']) == 2
