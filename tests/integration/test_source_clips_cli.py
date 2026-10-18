import json
import pytest
from source_clip_helpers import setup,review


def argv(command,f,extra=()):
    return [command,'--config',str(f.config.config_file),'--run-dir',str(f.run),*extra,'--json']


def test_source_cli_1_review_required_0_completed_2_refusal(runtime_run,monkeypatch,capsys):
    from video_ai.cli import main
    f=setup(runtime_run,monkeypatch)
    assert main(argv('prepare-source-clips',f))==1
    assert json.loads(capsys.readouterr().out)['clip_count']==7
    path,_=review(f.run)
    assert main(argv('finalize-source-clips',f,['--review',str(path)]))==0
    assert json.loads(capsys.readouterr().out)['ready_for_upscale']
    assert main(argv('prepare-source-clips',f))==2


def test_source_cli_interrupt130(runtime_run,monkeypatch):
    from video_ai.cli import main
    f=setup(runtime_run,monkeypatch)
    def interrupted(*a,**kw):raise KeyboardInterrupt()
    monkeypatch.setattr(f.sc,'prepare_source_clips',interrupted)
    assert main(argv('prepare-source-clips',f))==130


@pytest.mark.parametrize('bad',['missing','malformed','lock_path'])
def test_source_cli_pre_run_refusals_exit2_without_post(runtime_run,monkeypatch,bad):
    from video_ai.cli import main
    from pathlib import Path
    f=setup(runtime_run,monkeypatch)
    if bad=='missing':(f.run/'manifest.json').unlink()
    if bad=='malformed':(f.run/'manifest.json').write_text('{}')
    if bad=='lock_path':
        base=f.sc._local
        def invalid(run,path):
            if Path(path).name=='.source-clips.lock':raise OSError('redirected lock path')
            return base(run,path)
        monkeypatch.setattr(f.sc,'_local',invalid)
    assert main(argv('prepare-source-clips',f))==2
    assert f.requests==[] and f.actions==[]


def test_source_cli_running_failure_still_exit1(runtime_run,monkeypatch):
    from video_ai.cli import main
    f=setup(runtime_run,monkeypatch,mode='lost')
    assert main(argv('prepare-source-clips',f))==1
    assert f.requests==[69]
    assert f.store.snapshot()['stages']['source_clips']['status']=='ambiguous'
