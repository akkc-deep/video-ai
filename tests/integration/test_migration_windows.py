"""Exercise migration helpers against small fixtures, never the installed models."""
from pathlib import Path
import os
import shutil
import json
import subprocess
import sys

import pytest


SOURCE = Path(__file__).resolve().parents[2]
MIGRATION = SOURCE / 'scripts' / 'migrate_windows.ps1'


def run_ps(tmp_path, body, **environment):
    harness = tmp_path / 'migration probe.ps1'
    harness.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        ". $env:VAI_MIGRATION_SCRIPT\n" + body,
        encoding='utf-8-sig',
    )
    return subprocess.run(
        ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(harness)],
        env={**os.environ, 'VAI_MIGRATION_SCRIPT': str(MIGRATION),
             'VAI_FIXTURE': str(tmp_path), **environment},
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=40,
    )


def test_migration_script_is_available():
    assert MIGRATION.is_file()


@pytest.mark.skipif(not MIGRATION.exists(), reason='migration script not implemented yet')
def test_copy_handles_spaces_and_reports_missing_source(tmp_path):
    source = tmp_path / 'source space'
    source.mkdir()
    (source / 'weights.bin').write_bytes(b'tiny model fixture')
    result = run_ps(tmp_path, """
Copy-MigrationTree (Join-Path $env:VAI_FIXTURE 'source space') (Join-Path $env:VAI_FIXTURE 'target space')
try { Copy-MigrationTree (Join-Path $env:VAI_FIXTURE 'missing') (Join-Path $env:VAI_FIXTURE 'never') }
catch { exit 7 }
exit 0
""")
    assert result.returncode == 7, result.stdout + result.stderr
    assert (tmp_path / 'target space' / 'weights.bin').read_bytes() == b'tiny model fixture'


@pytest.mark.skipif(not MIGRATION.exists(), reason='migration script not implemented yet')
def test_venv_relocation_and_private_secret_loading(tmp_path):
    venv = tmp_path / 'orchestrator'
    venv.mkdir()
    (venv / 'pyvenv.cfg').write_text(
        'home = C:\\Users\\old-user\\Python312\nversion = 3.12.10\n'
        'executable = C:\\Users\\old-user\\Python312\\python.exe\n', encoding='utf-8')
    secret_file = tmp_path / 'secrets.local.json'
    secret_file.write_text('{"VIDEO_AI_TEST_SECRET": "private-fixture-value"}', encoding='utf-8')
    result = run_ps(tmp_path, """
Update-MigrationVenv (Join-Path $env:VAI_FIXTURE 'orchestrator') (Join-Path $env:VAI_FIXTURE 'base python')
Import-MigrationSecrets (Join-Path $env:VAI_FIXTURE 'secrets.local.json')
if ($env:VIDEO_AI_TEST_SECRET -ne 'private-fixture-value') { exit 8 }
""")
    assert result.returncode == 0, result.stdout + result.stderr
    config = (venv / 'pyvenv.cfg').read_text(encoding='utf-8-sig')
    assert 'old-user' not in config
    assert f'home = {tmp_path / "base python"}' in config
    assert 'version = 3.12.10' in config
    assert 'private-fixture-value' not in result.stdout + result.stderr


@pytest.mark.skipif(not MIGRATION.exists(), reason='migration script not implemented yet')
def test_restore_guard_and_nested_copy_guard(tmp_path):
    existing = tmp_path / 'existing'
    existing.mkdir()
    (existing / 'keep.txt').write_text('keep me', encoding='utf-8')
    result = run_ps(tmp_path, """
try { Assert-MigrationTarget (Join-Path $env:VAI_FIXTURE 'existing') $false }
catch {
    try { Copy-MigrationTree $env:VAI_FIXTURE (Join-Path $env:VAI_FIXTURE 'nested') }
    catch { exit 7 }
}
exit 0
""")
    assert result.returncode == 7, result.stdout + result.stderr
    assert (existing / 'keep.txt').read_text(encoding='utf-8') == 'keep me'
    assert not (tmp_path / 'nested').exists()


def test_orchestrator_startup_and_quoted_narration(tmp_path):
    narration = '他说："你好"。\n第二段，保留原文。'
    result = run_ps(tmp_path, """
Test-MigrationOrchestrator $env:VAI_TEST_PYTHON
$path = Save-MigrationNarration $env:VAI_NARRATION $env:VAI_FIXTURE
[Console]::WriteLine('narration-path=' + $path)
""", VAI_TEST_PYTHON=sys.executable, VAI_NARRATION=narration)
    assert result.returncode == 0, result.stdout + result.stderr
    path = Path(next(line.removeprefix('narration-path=') for line in result.stdout.splitlines()
                     if line.startswith('narration-path=')))
    assert path.read_text(encoding='utf-8') == narration


def test_robocopy_failure_is_propagated(tmp_path):
    (tmp_path / 'source').mkdir()
    result = run_ps(tmp_path, """
function robocopy.exe { $global:LASTEXITCODE = 16 }
try { Copy-MigrationTree (Join-Path $env:VAI_FIXTURE 'source') (Join-Path $env:VAI_FIXTURE 'target') }
catch { if ($_.ToString().Contains('Robocopy failed (16)')) { exit 7 }; throw }
exit 0
""")
    assert result.returncode == 7, result.stdout + result.stderr


def test_relocated_venv_really_starts_with_bundled_base(tmp_path):
    base = tmp_path / 'bundled python'
    base.mkdir()
    # Only the interpreter and encoding bootstrap are needed for this probe.
    # Do not copy installed packages or models into a test.
    for source in Path(sys.base_prefix).iterdir():
        if source.is_file() and source.suffix.lower() in ('.exe', '.dll'):
            shutil.copy2(source, base / source.name)
    shutil.copytree(Path(sys.base_prefix) / 'Lib' / 'encodings', base / 'Lib' / 'encodings')
    # CPython uses Lib/os.py as the landmark for locating its standard library.
    shutil.copy2(Path(sys.base_prefix) / 'Lib' / 'os.py', base / 'Lib' / 'os.py')
    env_root = tmp_path / 'relocated venv'
    (env_root / 'Scripts').mkdir(parents=True)
    shutil.copy2(sys.executable, env_root / 'Scripts' / 'python.exe')
    (env_root / 'pyvenv.cfg').write_text('home = C:\\missing-old-user\\Python312\n', encoding='utf-8')
    result = run_ps(tmp_path, """
Update-MigrationVenv (Join-Path $env:VAI_FIXTURE 'relocated venv') (Join-Path $env:VAI_FIXTURE 'bundled python')
& (Join-Path $env:VAI_FIXTURE 'relocated venv\\Scripts\\python.exe') -B -S -c 'import sys; print(sys.base_prefix)'
exit $LASTEXITCODE
""")
    assert result.returncode == 0, result.stdout + result.stderr
    assert str(base) in result.stdout


def test_reexport_preserves_previously_migrated_credentials(tmp_path):
    config = tmp_path / 'config'
    config.mkdir()
    (config / 'production.json').write_text(
        '{"image_generation":{"access_key_env":"VIDEO_AI_MIGRATED_TEST"}}', encoding='utf-8')
    (config / 'migration-secrets.local.json').write_text(
        '{"VIDEO_AI_MIGRATED_TEST":"migrated-private-value"}', encoding='utf-8')
    result = run_ps(tmp_path, """
Export-MigrationSecrets (Join-Path $env:VAI_FIXTURE 'config') (Join-Path $env:VAI_FIXTURE 'exported.local.json')
""")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads((tmp_path / 'exported.local.json').read_text())['VIDEO_AI_MIGRATED_TEST'] == 'migrated-private-value'
    assert 'migrated-private-value' not in result.stdout + result.stderr


def test_required_evidence_is_retained_without_ordinary_history(tmp_path):
    runtime = tmp_path / 'runtime'
    pinned = runtime / 'cache/video-ai/logs/vco05-20261027-native321'
    pinned.mkdir(parents=True)
    component = runtime / 'projects/video-ai/runs/20261004-040653-a0fcd961cc58'
    component.mkdir(parents=True)
    source_run = runtime / 'projects/video-ai/runs/required-source-run'
    source_run.mkdir()
    prompt = runtime / 'cache/video-ai/logs/required-inputs'
    prompt.mkdir()
    (prompt / 'prompt.json').write_text('{}')
    (pinned / 'case.json').write_text(json.dumps({
        'source_run': str(source_run), 'dependency': {'path': str(prompt / 'prompt.json')},
    }))
    (component / 'task4-acceptance.json').write_text('{}')
    result = run_ps(tmp_path, """
Get-MigrationEvidenceDirectories (Join-Path $env:VAI_FIXTURE 'runtime') | ForEach-Object { [Console]::WriteLine('evidence=' + $_) }
""")
    assert result.returncode == 0, result.stdout + result.stderr
    roots = {line.removeprefix('evidence=') for line in result.stdout.splitlines() if line.startswith('evidence=')}
    assert {str(pinned), str(component), str(source_run), str(prompt)} <= roots
