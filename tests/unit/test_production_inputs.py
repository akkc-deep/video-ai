from dataclasses import replace
import json
from pathlib import Path
import shutil

import pytest


@pytest.fixture
def production_config(resource_config, runtime_run):
    from video_ai.config import load_config
    from video_ai.runtime.manifest import thaw
    run, _, _ = runtime_run
    voice_file = run/'test-voice.json'
    voice = thaw(resource_config.voice.raw)
    for name in ('gpt_weights', 'sovits_weights', 'bert_root', 'hubert_root', 'reference_audio', 'reference_sha256'):
        voice[name] = thaw(getattr(resource_config.voice, name))
    voice_file.write_text(json.dumps(voice), encoding='utf-8')
    data = thaw(resource_config.raw)
    data.update(voice_config=str(voice_file), tools=thaw(resource_config.tools), models=thaw(resource_config.models),
                workflows=thaw(resource_config.workflows))
    data['media']['font_file'] = 'D:/VideoSi/projects/video-ai/inputs/fonts/msyh.ttc'
    config_file = run/'test-config.json'
    config_file.write_text(json.dumps(data), encoding='utf-8')
    return load_config(config_file)


def test_freeze_preserves_bytes_and_resume_ignores_original_change(production_config, runtime_run):
    from video_ai.runtime.production_inputs import freeze_inputs, load_frozen_inputs
    run, _, _ = runtime_run
    source = run/'original.txt'
    raw = b'\xef\xbb\xbf' + '  湖水。\r\n白鸟。\r\n'.encode('utf-8')
    source.write_bytes(raw)
    frozen = freeze_inputs(production_config, run, script=source, cpu_planner=True)
    assert (run/'production/script.txt').read_bytes() == raw
    assert frozen.script.text == '  湖水。\r\n白鸟。\r\n'
    assert frozen.options['cpu_planner'] is True
    assert frozen.options['execution_policy']['ollama_request_seconds'] >= 1800
    source.write_bytes(b'caller changed original')
    loaded = load_frozen_inputs(run)
    assert loaded.script.text == frozen.script.text
    assert loaded.config.media.profile.name == 'fast'
    assert all(Path(p).is_relative_to(run) for p in loaded.config.workflows.values())
    assert loaded.options['output_paths']['receipt'].endswith('.delivery.json')


@pytest.mark.parametrize('field,value', [('fps', 24), ('final_width', 1280), ('transition', 'xfade'), ('burn_subtitles', False), ('music', 'music.wav')])
def test_unsupported_configuration_rejected_before_freeze(production_config, runtime_run, field, value):
    from video_ai.runtime.production_inputs import freeze_inputs
    run, _, _ = runtime_run
    config = replace(production_config, media=replace(production_config.media, **{field: value}))
    with pytest.raises(ValueError, match=field): freeze_inputs(config, run, text='湖水。')
    assert not (run/'production/options.json').exists()


@pytest.mark.parametrize('text', ['', ' \r\n\t', '，。！？'])
def test_unspeakable_text_rejected(production_config, runtime_run, text):
    from video_ai.runtime.production_inputs import freeze_inputs
    run, _, _ = runtime_run
    with pytest.raises(ValueError): freeze_inputs(production_config, run, text=text)
    assert not (run/'production/options.json').exists()


@pytest.mark.parametrize('target', ['C:/escape.mp4', 'D:/VideoSi/output/video-ai/../../../escape.mp4'])
def test_output_escape_rejected(production_config, runtime_run, target):
    from video_ai.runtime.production_inputs import freeze_inputs
    run, _, _ = runtime_run
    with pytest.raises(ValueError): freeze_inputs(production_config, run, text='湖水。', output_path=Path(target))


@pytest.mark.parametrize('change', ['script', 'workflow', 'model', 'unknown_options', 'resolved_bool', 'cpu', 'config'])
def test_resume_rejects_frozen_or_explicit_changes(production_config, runtime_run, change):
    from video_ai.runtime.production_inputs import freeze_inputs, load_frozen_inputs
    run, _, _ = runtime_run
    frozen = freeze_inputs(production_config, run, text='湖水。')
    kwargs = {}
    if change == 'script': (run/'production/script.txt').write_bytes(b'changed')
    if change == 'workflow': Path(frozen.options['workflow_snapshots']['sdxl']['path']).write_bytes(b'changed')
    if change == 'model': production_config.models['sdxl'].write_bytes(b'changed')
    if change == 'unknown_options':
        data = dict(frozen.options, extra=1)
        (run/'production/options.json').write_text(json.dumps(data), encoding='utf-8')
    if change == 'resolved_bool':
        data = dict(frozen.options)
        data['config_snapshot']['resolved']['schema_version'] = True
        (run/'production/options.json').write_text(json.dumps(data), encoding='utf-8')
    if change == 'cpu': kwargs['cpu_planner'] = True
    if change == 'config': kwargs['config'] = replace(production_config, media=replace(production_config.media, fps=24))
    with pytest.raises(ValueError): load_frozen_inputs(run, **kwargs)


def test_preflight_uses_only_needed_capabilities_and_logs_under_run(production_config, runtime_run):
    production_config=replace(production_config,models=runtime_run[1].models)
    from video_ai.runtime.production_inputs import production_preflight
    import subprocess
    run, _, _ = runtime_run
    def runner(args, **kwargs):
        assert Path(kwargs['cwd']).is_relative_to(run)
        assert kwargs['timeout'] <= 300
        if args[-1] == '-encoders': text = ' V....D libx264 H264\n A..... aac AAC\n'
        elif args[-1] == '-filters': text = ' .. subtitles V->V render\n'
        elif '-c' in args: text = json.dumps({'custom': {'version': 'v2', 'device': 'cpu', 'is_half': False}})
        else: text = 'fixture version\n'
        kwargs['stdout'].write(text)
        return subprocess.CompletedProcess(args, 0)
    report = production_preflight(production_config, run, runner=runner, port_probe=lambda url, timeout: False)
    assert report.passed
    assert report.log_dir.is_relative_to(run/'logs/production')
    assert (report.log_dir/'commands.json').exists()


def test_foreign_port_and_space_insufficiency_rejected(production_config, runtime_run):
    production_config=replace(production_config,models=runtime_run[1].models)
    from video_ai.runtime.production_inputs import production_preflight, check_stage_space
    run, _, _ = runtime_run
    report = production_preflight(production_config, run, port_probe=lambda url, timeout: True)
    assert not report.passed
    assert all(production_config.services[name] in next(c.details for c in report.checks if c.name == 'ports.'+name)
               for name in production_config.services)
    with pytest.raises(OSError):
        check_stage_space(production_config, frames=10, disk_usage=lambda path: shutil._ntuple_diskusage(100, 100, 0))


def test_preflight_rejects_unsupported_installed_tts_route(production_config, runtime_run):
    production_config=replace(production_config,models=runtime_run[1].models)
    from video_ai.runtime.production_inputs import production_preflight
    import subprocess
    run, _, _ = runtime_run
    def runner(args, **kwargs):
        if '-c' in args: text = json.dumps({'custom': {'version': 'v1', 'device': 'cuda', 'is_half': True}})
        elif args[-1] == '-encoders': text = ' V....D libx264 H264\n A..... aac AAC\n'
        elif args[-1] == '-filters': text = ' .. subtitles V->V render\n'
        else: text = 'fixture version\n'
        kwargs['stdout'].write(text)
        return subprocess.CompletedProcess(args, 0)
    report = production_preflight(production_config, run, runner=runner, port_probe=lambda url, timeout: False)
    assert not report.passed
    check = next(c for c in report.checks if c.name == 'production.tts_yaml')
    assert not check.passed
    assert 'version' in check.details


def test_preflight_allows_windows_delayed_connection_refusal(production_config, runtime_run):
    production_config=replace(production_config,models=runtime_run[1].models)
    from video_ai.runtime.production_inputs import production_preflight
    from video_ai.runtime.services import ServiceConflictError
    import subprocess
    run, _, _ = runtime_run
    def port_probe(url, timeout):
        if timeout < 2: raise ServiceConflictError('Windows refusal still pending')
        return False
    def runner(args, **kwargs):
        if '-c' in args: text = json.dumps({'custom': {'version': 'v2', 'device': 'cpu', 'is_half': False}})
        elif args[-1] == '-encoders': text = ' V....D libx264 H264\n A..... aac AAC\n'
        elif args[-1] == '-filters': text = ' .. subtitles V->V render\n'
        else: text = 'fixture version\n'
        kwargs['stdout'].write(text)
        return subprocess.CompletedProcess(args, 0)
    report = production_preflight(production_config, run, runner=runner, port_probe=port_probe)
    assert report.passed

