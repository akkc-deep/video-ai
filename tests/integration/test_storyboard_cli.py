import json
import pytest
from storyboard_helpers import mock_generation,review_for,write_review


def argv(command,config,run,path):
    flag='--timing-review' if command=='plan-storyboard' else '--review'
    return [command,'--config',str(config.config_file),'--run-dir',str(run),flag,str(path),'--json']


def test_plan_and_finalize_exit_codes(storyboard_run,monkeypatch,capsys):
    from video_ai.cli import main
    run,config,store,timing,path=storyboard_run;mock_generation(monkeypatch)
    assert main(argv('plan-storyboard',config,run,path))==1
    data=json.loads(capsys.readouterr().out);assert data['status']=='review_required' and data['ready_for_images'] is False
    review=write_review(run,review_for(run));assert main(argv('finalize-storyboard',config,run,review))==0
    assert json.loads(capsys.readouterr().out)['ready_for_images'] is True
    assert main(argv('plan-storyboard',config,run,path))==2
    assert main(argv('finalize-storyboard',config,run,review))==2


def test_missing_timing_is_runtime_failure(storyboard_run,capsys):
    from video_ai.cli import main
    run,config,store,timing,path=storyboard_run;path.unlink()
    assert main(argv('plan-storyboard',config,run,path))==1
    assert json.loads(capsys.readouterr().out)['passed'] is False


@pytest.mark.parametrize('kind',['escape','source','C','relative','config_io','interrupt'])
def test_review_paths_and_cli_errors(storyboard_run,monkeypatch,capsys,kind):
    from video_ai.cli import main
    from video_ai.runtime import storyboard_checks as sc
    run,config,store,timing,path=storyboard_run;mock_generation(monkeypatch);args=argv('plan-storyboard',config,run,path)
    if kind=='escape':args[-2]=str(run/'timing-review.json')
    if kind=='source':args[-2]='D:/code/py/video-ai/timing-review.json'
    if kind=='C':args[-2]='C:/timing-review.json'
    if kind=='relative':
        monkeypatch.chdir(run);args[args.index('--run-dir')+1]='.';args[-2]='logs/storyboard/timing-review.json'
    if kind=='config_io':args[args.index('--config')+1]=str(run/'missing-config.json')
    if kind=='interrupt':
        def interrupted(*args,**kwargs):raise KeyboardInterrupt()
        monkeypatch.setattr(sc,'plan_storyboard',interrupted)
    expected=1 if kind in ('relative','config_io') else 130 if kind=='interrupt' else 2
    assert main(args)==expected


def test_cpu_planner_flag_reaches_runtime(storyboard_run,monkeypatch):
    from video_ai.cli import main
    from video_ai.runtime import storyboard_checks as sc
    from storyboard_helpers import content_for
    run,config,store,timing,path=storyboard_run;observed=[]
    def generate(config,run,store,logger,slots,*,cpu_only=False,semantic_reasons=None,semantic_specs=None,depiction_policy=None):
        observed.append(cpu_only);return content_for(slots),{}
    monkeypatch.setattr(sc,'_generate_owned',generate)
    assert main(argv('plan-storyboard',config,run,path)+['--cpu-planner'])==1
    assert observed==[True] and (run/'storyboard-draft.json').exists()
