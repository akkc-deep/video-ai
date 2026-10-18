import json
from pathlib import Path
import pytest


def test_real_stage_cli_relative_paths(timeline_run,monkeypatch,capsys):
    from video_ai.cli import main
    run,config,store,data=timeline_run
    monkeypatch.chdir(run.parent)
    assert main(['plan-timeline','--config',str(config.config_file),'--run-dir',run.name,'--json'])==0
    result=json.loads(capsys.readouterr().out)
    assert result['passed'] and result['total_samples']==350400 and result['total_frames']==117
    assert result['listening_accepted'] is False
    assert main(['plan-timeline','--config',str(config.config_file),'--run-dir',run.name])==2


@pytest.mark.parametrize('run_path',['C:/bad','D:/code/py/video-ai','D:/VideoSi/projects/video-ai/runs/not-a-run'])
def test_cli_invalid_run_argument(timeline_run,run_path):
    from video_ai.cli import main
    assert main(['plan-timeline','--config',str(timeline_run[1].config_file),'--run-dir',run_path])==2


def test_cli_bad_pcm_is_runtime_failure(timeline_run,capsys):
    from video_ai.cli import main
    run,config,store,data=timeline_run
    Path(data['spans'][0]['pcm']['path']).write_bytes(b'bad media')
    assert main(['plan-timeline','--config',str(config.config_file),'--run-dir',str(run),'--json'])==1
    assert json.loads(capsys.readouterr().out)['passed'] is False


def test_cli_interrupt(timeline_run,monkeypatch):
    from video_ai.cli import main
    from video_ai.runtime import timeline_checks as tc
    def interrupt(*a,**k):raise KeyboardInterrupt()
    monkeypatch.setattr(tc,'build_timeline',interrupt)
    run,config,store,data=timeline_run
    assert main(['plan-timeline','--config',str(config.config_file),'--run-dir',str(run)])==130
    assert store.snapshot()['stages']['timeline']['status']=='interrupted'


def test_cli_help(capsys):
    from video_ai.cli import main
    assert main(['plan-timeline','--help'])==0
    assert '--run-dir' in capsys.readouterr().out


def test_manifest_input_io_failure_exit_one(timeline_run,monkeypatch):
    from video_ai.cli import main
    run,config,store,data=timeline_run
    original=Path.read_text
    def unavailable(path,*a,**kw):
        if path==run/'manifest.json':raise FileNotFoundError('manifest read failed')
        return original(path,*a,**kw)
    monkeypatch.setattr(Path,'read_text',unavailable)
    assert main(['plan-timeline','--config',str(config.config_file),'--run-dir',str(run)])==1


def test_missing_manifest_is_input_failure(timeline_run):
    from video_ai.cli import main
    from video_ai.runtime.paths import RuntimePaths,create_run
    run,config,store,data=timeline_run
    empty=create_run(RuntimePaths.from_config(config))
    assert main(['plan-timeline','--config',str(config.config_file),'--run-dir',str(empty),'--json'])==1


def test_missing_config_is_io_failure(timeline_run):
    from video_ai.cli import main
    run,config,store,data=timeline_run
    assert main(['plan-timeline','--config',str(run/'missing-config.json'),'--run-dir',str(run)])==1
