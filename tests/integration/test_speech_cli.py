import json
from pathlib import Path
from types import SimpleNamespace
import pytest


@pytest.mark.parametrize('passed,code', [(True,0),(False,1)])
def test_speech_cli_paths_report(runtime_run, monkeypatch, tmp_path, capsys, passed, code):
    from video_ai import cli
    from video_ai.runtime import speech_checks
    seen = {}
    monkeypatch.chdir(tmp_path)
    def load(path): seen['config']=path; return runtime_run[1]
    def synth(config,script,*,run_dir):
        seen['script']=script
        return speech_checks.SpeechResult(passed,run_dir,run_dir/'segments.json',4800,False)
    monkeypatch.setattr(cli,'load_config',load)
    monkeypatch.setattr(speech_checks,'synthesize_script',synth)
    assert cli.main(['synthesize-speech','--config','main.json','--script','文案.txt','--json']) == code
    result=json.loads(capsys.readouterr().out)
    assert result['passed']==passed and result['listened'] is False
    assert seen == {'config':tmp_path/'main.json','script':tmp_path/'文案.txt'}


def test_speech_cli_help(capsys):
    from video_ai.cli import main
    assert main(['synthesize-speech','--help'])==0
    assert '--script' in capsys.readouterr().out
