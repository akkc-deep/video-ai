import json
import pytest
from start_image_helpers import make_images_run,fake_media,image_review


def argv(command,config,run,extra=()):
    return [command,'--config',str(config.config_file),'--run-dir',str(run),*extra,'--json']


def test_image_cli_prepare_finalize_and_refusal(storyboard_run,monkeypatch,capsys):
    from video_ai.cli import main
    run,config,store,inputs=make_images_run(storyboard_run,monkeypatch);fake_media(monkeypatch)
    args=argv('prepare-start-images',config,run,['--image-inputs',str(inputs)])
    assert main(args)==1
    assert json.loads(capsys.readouterr().out)['status']=='review_required'
    review,_=image_review(run)
    assert main(argv('finalize-start-images',config,run,['--review',str(review)]))==0
    assert json.loads(capsys.readouterr().out)['ready_for_source_clips'] is True
    assert main(args)==2


@pytest.mark.parametrize('bad',['dimensions','review_path','missing_config','interrupt'])
def test_image_cli_error_codes(storyboard_run,monkeypatch,bad):
    from video_ai.cli import main
    from video_ai.runtime import start_image_checks as sc
    run,config,store,inputs=make_images_run(storyboard_run,monkeypatch)
    args=argv('prepare-start-images',config,run)
    if bad=='dimensions':args+=['--image-width','1024','--image-height','1024']
    if bad=='review_path':args=argv('finalize-start-images',config,run,['--review','C:/review.json'])
    if bad=='missing_config':args[args.index('--config')+1]=str(run/'missing.json')
    if bad=='interrupt':
        def interrupted(*a,**kw):raise KeyboardInterrupt()
        monkeypatch.setattr(sc,'prepare_start_images',interrupted)
    assert main(args)==(130 if bad=='interrupt' else 1 if bad=='missing_config' else 2)
