"""New test-generated runs and resources stay out of production storage."""
from pathlib import Path
import json
import os
import subprocess


def test_runtime_fixture_uses_disposable_instead_of_formal_runs(runtime_run):
    run,_,paths = runtime_run
    root = Path('D:/VideoSi/disposable/video-ai/tests')
    assert run.is_relative_to(root)
    assert paths.output_root.is_relative_to(root)
    assert paths.cache_root.is_relative_to(root)


def test_resource_fixture_does_not_pollute_public_models_or_tools(resource_config):
    root = Path('D:/VideoSi/disposable/video-ai/tests')
    assert all(path.is_relative_to(root) for path in resource_config.tools.values())
    assert all(path.is_relative_to(root) for path in resource_config.models.values())


def test_bootstrap_routes_rebuildable_caches_but_protects_model_dependencies(tmp_path):
    script = tmp_path/'environment.ps1'
    script.write_text(". 'D:/code/py/video-ai/scripts/bootstrap.ps1'\n"
        "Initialize-VideoAiEnvironment 'storage-test'\n"
        "@{TEMP=$env:TEMP;PIP=$env:PIP_CACHE_DIR;UV=$env:UV_CACHE_DIR;HF=$env:HF_HOME;PYTHON=$env:UV_PYTHON_INSTALL_DIR} | ConvertTo-Json -Compress\n",
        encoding='utf-8-sig')
    result = subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],
        capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert result.returncode == 0,result.stderr.decode('utf-8',errors='replace')
    env = json.loads(result.stdout.decode('utf-8-sig'))
    disposable = Path('D:/VideoSi/disposable/video-ai')
    assert Path(env['TEMP']).is_relative_to(disposable/'tmp')
    assert Path(env['PIP']).is_relative_to(disposable/'cache')
    assert Path(env['UV']).is_relative_to(disposable/'cache')
    assert not Path(env['HF']).is_relative_to(disposable)
    assert not Path(env['PYTHON']).is_relative_to(disposable)


def test_standard_test_launcher_uses_disposable_for_pytest_files():
    source=(Path(__file__).resolve().parents[2]/'scripts/test_windows.ps1').read_text(encoding='utf-8-sig')
    assert "Join-Path $VideoAiDisposableRoot 'tests'" in source
    assert "Join-Path $VideoAiCacheRoot 'pytest-tmp'" not in source
