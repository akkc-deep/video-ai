"""Explicit actions validate before run allocation and preserve consume-only APIs."""
import pytest


@pytest.mark.parametrize('kwargs',[
    {'image_selection':'selection.json','clip_observation':'clip.json'},
    {'final_observation':'final.json','publish':True},
    {'revision':'revision.json','publish':True},
    {'publish':1},{'publish':'yes'},
    {'clip_observation':'clip.json'}, {'final_observation':'final.json'},
    {'retry_email':'retry.json'}, {'revision':'revision.json'}, {'publish':True},
])
def test_public_invalid_action_combinations_do_not_allocate_or_lock(monkeypatch,kwargs):
    import video_ai.production as production
    def forbidden(*args,**kwargs): pytest.fail('invalid action caused side effect')
    monkeypatch.setattr(production,'create_run',forbidden)
    monkeypatch.setattr(production,'RunLock',forbidden)
    result = production.make_video(text='原文。',**kwargs)
    assert result.status=='blocked' and result.exit_code==2
    assert result.run_dir is None


@pytest.mark.parametrize('actions',[
    ['--image-selection','a.json','--clip-observation','b.json'],
    ['--final-observation','a.json','--publish'],
    ['--revision','a.json','--publish'],
])
def test_cli_rejects_conflicting_actions_before_make_video(monkeypatch,actions):
    from video_ai.cli import main
    import video_ai.production as production
    monkeypatch.setattr(production,'make_video',lambda *a,**kw:pytest.fail('invalid CLI called make_video'))
    assert main(['make-video','--run-dir','D:/VideoSi/projects/video-ai/runs/missing',*actions])==2
