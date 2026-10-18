import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

SOURCE = Path(__file__).resolve().parents[2]


def test_bootstrap_streams_both_native_channels_and_preserves_failure(tmp_path):
    helper = tmp_path / 'native failure.py'
    helper.write_text("import sys\nprint('out中文', flush=True)\nprint('err中文', file=sys.stderr, flush=True)\nsys.exit(7)\n", encoding='utf-8')
    harness = tmp_path / 'probe.ps1'
    harness.write_text(". 'D:/code/py/video-ai/scripts/bootstrap.ps1'\nInitialize-VideoAiEnvironment 'test-stream'\nInvoke-VideoAiNative $env:VAI_TEST_PYTHON @('-B', $env:VAI_TEST_SCRIPT)\n[Console]::Error.WriteLine('probe-log=' + $script:VideoAiLog)\nexit $script:VideoAiExitCode\n", encoding='utf-8-sig')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(harness)],
                            env={**os.environ, 'VAI_TEST_PYTHON': sys.executable, 'VAI_TEST_SCRIPT': str(helper)},
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
    assert result.returncode == 7
    assert 'out中文' in result.stdout and 'err中文' in result.stderr
    log = Path(next(line.split('=', 1)[1] for line in result.stderr.splitlines() if line.startswith('probe-log=')))
    text = log.read_text(encoding='utf-8')
    assert 'out中文' in text and 'err中文' in text and 'exit_code=7' in text


def test_bootstrap_refuses_junction_before_runtime_write(tmp_path):
    junction = tmp_path / 'escape'
    harness = tmp_path / 'junction.ps1'
    harness.write_text("$ErrorActionPreference='Stop'\n. 'D:/code/py/video-ai/scripts/bootstrap.ps1'\nNew-Item -ItemType Junction -Path $env:VAI_TEST_JUNCTION -Target 'D:/code/py/video-ai' | Out-Null\ntry { New-VideoAiDirectory ($env:VAI_TEST_JUNCTION + '/forbidden') } catch { exit 7 } finally { [IO.Directory]::Delete($env:VAI_TEST_JUNCTION) }\nexit 0\n", encoding='utf-8-sig')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(harness)],
                            env={**os.environ, 'VAI_TEST_JUNCTION': str(junction)}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 7
    assert not (SOURCE / 'forbidden').exists()


def test_installer_rejects_interpreter_with_wrong_version(tmp_path):
    # A readable existing exe, not a Python3.12 interpreter. Cannot create an env.
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                             str(SOURCE / 'scripts/install_windows.ps1'), '-Python',
                             'C:/Windows/System32/whoami.exe'], capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert 'Python 3.12' in result.stderr


def test_existing_env_junction_rejected_before_python_execution(tmp_path):
    junction = tmp_path / 'env-junction'
    harness = tmp_path / 'env-check.ps1'
    harness.write_text("$ErrorActionPreference='Stop'\n. 'D:/code/py/video-ai/scripts/bootstrap.ps1'\nInitialize-VideoAiEnvironment 'test-env-junction'\nNew-Item -ItemType Junction -Path $env:VAI_TEST_JUNCTION -Target $env:VAI_TEST_BASE | Out-Null\n$VideoAiEnvRoot=$env:VAI_TEST_JUNCTION\n$VideoAiPython=Join-Path $VideoAiEnvRoot 'python.exe'\ntry { Assert-VideoAiPython $VideoAiPython } catch { exit 7 } finally { [IO.Directory]::Delete($env:VAI_TEST_JUNCTION) }\nexit 0\n", encoding='utf-8-sig')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(harness)],
                            env={**os.environ, 'VAI_TEST_JUNCTION': str(junction), 'VAI_TEST_BASE': sys.base_prefix},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 7
    assert '3.12.10' not in result.stdout


@pytest.mark.parametrize('arguments', [
    ['--basetemp=SHARED'], ['--basetemp', 'SHARED'],
    ['-o', 'cache_dir=SHARED'], ['--override-ini=cache_dir=SHARED'],
])
def test_test_script_refuses_user_cache_and_temp_overrides(arguments, tmp_path):
    shared = str(tmp_path / 'must-not-create')
    arguments = [value.replace('SHARED', shared) for value in arguments]
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                             str(SOURCE / 'scripts/test_windows.ps1'), *arguments,
                             'tests/unit/test_environment.py', '-q'], capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert not Path(shared).exists()
