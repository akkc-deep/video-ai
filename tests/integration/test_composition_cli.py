from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from video_ai.cli import main

@pytest.mark.parametrize('status,expected',[('completed',0),('failed',1),('refused',2),('interrupted',130)])
def test_cli_result_paths_staging_limits_and_exit_codes(monkeypatch,capsys,status,expected):
    from video_ai.runtime import composition_checks as cc
    from video_ai.config import load_config
    config=load_config(Path('D:/code/py/video-ai/config/production.example.json'))
    monkeypatch.setattr('video_ai.cli._load_cli_config',lambda *args:config)
    def compose(c,*,run_dir,settings_path):
        assert run_dir==Path.cwd()/'relative-run' and settings_path==Path.cwd()/'settings.json'
        if status=='refused':raise cc.CompositionRefusal('TEST ONLY refused')
        if status=='interrupted':raise KeyboardInterrupt()
        return cc.CompositionResult(status=='completed',run_dir,run_dir/'composition.json',run_dir/'staging/composition/candidate.mp4',run_dir/'staging/composition/subtitle.srt',48,144000,True,status)
    monkeypatch.setattr(cc,'compose_clips',compose)
    assert main(['compose-clips','--config','config.json','--run-dir','relative-run','--settings','settings.json','--json'])==expected
    if expected in (0,1):
        result=json.loads(capsys.readouterr().out);assert result['staging_only'] is True and result['status']==status
        assert all(result['validation'][k]=='unverified' for k in ('actual_final_video_semantics','actual_final_video_sync','full_film_acceptance'))
