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
        assert Path(env[name]).is_relative_to(Path('D:/VideoSi/cache/video-ai'))
        assert Path(env[name]).is_dir()
    assert Path(env['OLLAMA_MODELS']) == Path('D:/VideoSi/models/ollama')
    result = subprocess.run([sys.executable, '-B', '-c',
                             'import tempfile,sys,json; print(json.dumps([tempfile.gettempdir(),sys.pycache_prefix]))'],
                            cwd=str(paths.cache_root), env=env, capture_output=True, text=True, check=True)
    temp, pycache = json.loads(result.stdout)
    assert Path(temp) == Path('D:/VideoSi/cache/video-ai/temp')
    assert Path(pycache) == Path('D:/VideoSi/cache/video-ai/pycache')


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
