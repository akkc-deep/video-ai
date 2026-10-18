from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import pytest


def test_local_fixture_doctor_passes_and_keeps_inference_and_space_unverified(resource_config, capability_runner):
    from video_ai.runtime.preflight import preflight
    runs = resource_config.project_root / 'runs'
    before = set(runs.iterdir()) if runs.exists() else set()
    report = preflight(resource_config, runner=capability_runner)
    assert report.passed
    assert report.as_dict()['inference_verified'] is False
    assert report.as_dict()['full_run_space_checked'] is False
    assert report.as_dict()['fast_profile_verified'] is False
    assert set(runs.iterdir()) == before
    assert (report.log_dir / 'ffmpeg-filters.stdout.txt').read_text().startswith(' .. subtitles')


def test_missing_target_resources_reported_individually(resource_config,capability_runner):
    from video_ai.config import load_config
    from video_ai.runtime.preflight import preflight
    # Missing fixtures must stay missing even after the real migration completes.
    tools=dict(resource_config.tools,ffmpeg=resource_config.tools['ffmpeg'].with_name('missing.exe'))
    model=resource_config.models['wan_high']
    models=dict(resource_config.models,wan_high=model.parent/'missing'/model.name)
    voice=replace(resource_config.voice,reference_audio=resource_config.voice.reference_audio.with_name('missing.wav'))
    config=replace(resource_config,tools=tools,models=models,voice=voice,
                   media=replace(resource_config.media,font_file=resource_config.media.font_file.with_name('missing.ttc')))
    report = preflight(config,runner=capability_runner)
    failed = {check.name for check in report.checks if not check.passed}
    assert {'tools.ffmpeg', 'models.wan_high', 'font_file', 'voice.reference_audio'} <= failed
    assert not report.passed
    assert next(c for c in report.checks if c.name == 'workflow.wan').passed


def test_bad_output_stops_before_command_or_directory_creation(resource_config):
    from video_ai.runtime.preflight import preflight
    def forbidden_runner(*args, **kwargs):
        pytest.fail('unsafe path must stop before subprocess')
    report = preflight(resource_config, output=Path('C:/bad.mp4'), runner=forbidden_runner)
    assert not report.passed
    assert report.log_dir is None
    assert any(c.name == 'paths' and not c.passed for c in report.checks)


def test_reference_hash_mismatch_and_missing_utf8_script_fail(resource_config, capability_runner, tmp_path):
    from video_ai.runtime.preflight import preflight
    config = replace(resource_config, voice=replace(resource_config.voice, reference_sha256='0' * 64))
    report = preflight(config, script=tmp_path / 'absent.txt', runner=capability_runner)
    failed = {c.name for c in report.checks if not c.passed}
    assert {'voice.reference_sha256', 'script'} <= failed


def test_c_drive_readonly_utf8_script_is_allowed(resource_config, capability_runner):
    # Existing read-only Windows file suffices; no C: file is written by this test.
    from video_ai.runtime.preflight import preflight
    candidates = [Path('C:/Windows/win.ini'), Path('C:/Windows/System32/drivers/etc/hosts')]
    readable = next((p for p in candidates if p.exists()), None)
    if readable is None:
        pytest.skip('no existing read-only C: text fixture')
    report = preflight(resource_config, script=readable, runner=capability_runner)
    assert next(c for c in report.checks if c.name == 'script').passed


@pytest.mark.parametrize('flags', ['...', '..', 'T.C'])
def test_ffmpeg_capabilities_parse_columns_not_descriptions(flags):
    from video_ai.runtime.preflight import parse_capabilities
    data = f' {flags} subtitles V->V render\n {flags} scale V->V contains h264_nvenc in description\n'
    assert parse_capabilities(data, 'filters') == {'subtitles', 'scale'}
    assert parse_capabilities(' V....D libx264 H.264 mentions h264_nvenc\n', 'encoders') == {'libx264'}


@pytest.mark.parametrize('kind', ['exit', 'timeout'])
def test_command_failure_keeps_exit_and_timeout_evidence(resource_config, tmp_path, kind):
    from video_ai.runtime.preflight import preflight
    def run(args, **kwargs):
        kwargs['stderr'].write('underlying failure evidence\n')
        if kind == 'timeout':
            raise subprocess.TimeoutExpired(args, kwargs['timeout'])
        return subprocess.CompletedProcess(args, 7)
    report = preflight(resource_config, runner=run)
    assert not report.passed
    records = json.loads((report.log_dir / 'commands.json').read_text())
    assert records[0]['returncode'] == (None if kind == 'timeout' else 7)
    assert records[0]['timed_out'] is (kind == 'timeout')
    assert 'underlying failure' in (report.log_dir / 'ffmpeg-version.stderr.txt').read_text()


def test_disk_failure_is_visible(resource_config, capability_runner):
    from video_ai.runtime.preflight import preflight
    report = preflight(resource_config, runner=capability_runner,
                       disk_usage=lambda p: shutil._ntuple_diskusage(100, 100, 0))
    assert next(c for c in report.checks if c.name == 'disk').passed is False


def test_mapping_missing_input_reports_node_and_field(resource_config, capability_runner, tmp_path):
    from video_ai.runtime.preflight import preflight
    original = resource_config.workflows['wan']
    graph = json.loads(original.read_text(encoding='utf-8'))
    del graph['129:98']['inputs']['length']
    broken = tmp_path / original.name
    broken.write_text(json.dumps(graph), encoding='utf-8')
    mapping = tmp_path / resource_config.workflows['wan_mapping'].name
    mapping.write_bytes(resource_config.workflows['wan_mapping'].read_bytes())
    config = replace(resource_config, workflows={**resource_config.workflows, 'wan': broken, 'wan_mapping': mapping})
    report = preflight(config, runner=capability_runner)
    check = next(c for c in report.checks if c.name == 'workflow.wan')
    assert not check.passed and '129:98' in check.details and 'length' in check.details


def test_wrong_model_filename_is_rejected(resource_config, capability_runner, tmp_path):
    from video_ai.runtime.preflight import preflight
    config = replace(resource_config, models={**resource_config.models, 'wan_high': resource_config.models['wan_low']})
    check = next(c for c in preflight(config, runner=capability_runner).checks if c.name == 'workflow.wan')
    assert not check.passed and 'wan_high' in check.details
