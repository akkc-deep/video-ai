from pathlib import Path
import pytest
from video_ai.runtime.paths import PathPolicy, SOURCE_ROOT

def test_checkout_source_root():
    assert SOURCE_ROOT == Path(__file__).resolve().parents[2]

def test_configurable_categories(tmp_path):
    root = tmp_path / "Runtime with spaces"
    policy = PathPolicy(root)
    assert policy.validate_write(root / "work/video/audio.wav", "run") == root / "work/video/audio.wav"
    with pytest.raises(ValueError):
        policy.validate_write(root / "shared/models/out.mp4", "output")
    with pytest.raises(ValueError):
        policy.validate_write(root / "work/../../escape", "run")


def test_environment_root_relocates_config_and_voice(tmp_path):
    import json
    import os
    import subprocess
    import sys
    root = tmp_path / 'Other drive style root with spaces'
    code = "from pathlib import Path; from video_ai.config import load_config; from video_ai.runtime.paths import RUNTIME_ROOT; c=load_config(Path('config/production.example.json')); assert c.runtime_root==RUNTIME_ROOT; assert c.tools['ffmpeg'].is_relative_to(RUNTIME_ROOT/'shared/tools'); assert c.voice.gpt_weights.is_relative_to(RUNTIME_ROOT/'shared/models')"
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', code], env={**os.environ, 'VIDEO_AI_RUNTIME_ROOT': str(root)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not root.exists()
