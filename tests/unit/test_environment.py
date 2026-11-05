import json
import os
from pathlib import Path
import subprocess
import sys


def test_child_env_redirects_writes_without_mutating_parent():
    from video_ai.runtime.environment import build_child_env
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.config import load_config
    before = dict(os.environ)
    paths = RuntimePaths.from_config(load_config(Path('config/production.example.json').resolve()))
    env = build_child_env(paths)
    assert dict(os.environ) == before
    for name in ('TEMP', 'TMP', 'TMPDIR', 'PYTHONPYCACHEPREFIX', 'HF_HOME', 'HF_HUB_CACHE',
                 'TRANSFORMERS_CACHE', 'TORCH_HOME', 'PIP_CACHE_DIR', 'UV_CACHE_DIR',
                 'UV_PYTHON_INSTALL_DIR', 'XDG_CACHE_HOME'):
        from video_ai.runtime.storage import _sandbox
        assert Path(env[name]).is_relative_to(_sandbox.get())
        assert Path(env[name]).is_dir()
    assert Path(env['OLLAMA_MODELS']) == _sandbox.get()/'shared/models/ollama'
    result = subprocess.run([sys.executable, '-B', '-c',
                             'import tempfile,sys,json; print(json.dumps([tempfile.gettempdir(),sys.pycache_prefix]))'],
                            cwd=str(paths.cache_root), env=env, capture_output=True, text=True, check=True)
    temp, pycache = json.loads(result.stdout)
    assert Path(temp) == _sandbox.get()/'scratch/tmp'
    assert Path(pycache) == _sandbox.get()/'scratch/cache/pycache'
    assert not Path(env['HF_HOME']).is_relative_to(_sandbox.get()/'disposable')
    assert not Path(env['UV_PYTHON_INSTALL_DIR']).is_relative_to(_sandbox.get()/'disposable')


def test_invalid_runtime_paths_rejected_before_mkdir(monkeypatch, tmp_path):
    from video_ai.runtime.environment import build_child_env
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.config import load_config
    from dataclasses import replace
    import pytest
    paths = RuntimePaths.from_config(load_config(Path('config/production.example.json').resolve()))
    paths = replace(paths, cache_root=Path('C:/forbidden-cache'))
    with pytest.raises(ValueError):
        build_child_env(paths)


def test_two_video_children_keep_temporary_bytes_in_their_own_bundles(runtime_run):
    from video_ai.runtime.environment import build_child_env
    run, _, paths = runtime_run
    second = run.parent / (run.name[:-1] + ('0' if run.name[-1] != '0' else '1'))
    second.mkdir()
    before = dict(os.environ)
    one = build_child_env(paths, run)
    two = build_child_env(paths, second)
    for key in ('TEMP', 'TMP', 'TMPDIR', 'PYTHONPYCACHEPREFIX', 'PIP_CACHE_DIR'):
        assert Path(one[key]).is_relative_to(run)
        assert Path(two[key]).is_relative_to(second)
        assert not Path(one[key]).is_relative_to(second)
    assert one['HF_HOME'] == two['HF_HOME']
    assert dict(os.environ) == before


def test_native_text_cache_is_run_owned(runtime_run, monkeypatch):
    from video_ai.runtime.environment import build_child_env
    from video_ai.runtime.temporal_native_worker import text_cache_root
    run, _, paths = runtime_run
    env = build_child_env(paths, run)
    monkeypatch.setenv('VIDEO_AI_TASK_RUN_DIR', env['VIDEO_AI_TASK_RUN_DIR'])
    assert text_cache_root() == run/'service-runtime/cache/temporal-text'
