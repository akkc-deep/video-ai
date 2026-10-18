import json
from pathlib import Path
from types import SimpleNamespace
import pytest


def test_help_exposes_run_and_resume_without_force(capsys):
    from video_ai.cli import main
    assert main(['--help']) == 0
    text = capsys.readouterr().out
    assert 'run' in text and 'resume' in text
    assert main(['run', '--help']) == 0
    text = capsys.readouterr().out
    assert '--unit-review' in text and '--publish' not in text and '--force' not in text


@pytest.mark.parametrize('status,expected', [('candidate_ready', 0), ('published', 0),
    ('awaiting_review', 3), ('awaiting_acceptance', 3), ('failed', 1), ('refused', 2), ('interrupted', 130)])
def test_cli_maps_pipeline_status_and_json(monkeypatch, capsys, status, expected):
    from video_ai import pipeline
    from video_ai.cli import main
    from video_ai.config import load_config
    monkeypatch.setattr(pipeline, 'resume_pipeline', lambda *args, **kwargs:
        pipeline.PipelineResult(Path('D:/VideoSi/projects/video-ai/runs/20261005-000000-111111111111'),
            None, status, 'validation', (), None, None, status=='published', None))
    assert main(['resume', '--config', 'config/production.example.json', '--run-dir',
        'D:/VideoSi/projects/video-ai/runs/20261005-000000-111111111111', '--json']) == expected
    result = json.loads(capsys.readouterr().out)
    assert result['schema_version'] == 1 and result['status'] == status
    assert result['published'] is (status == 'published')


def test_run_never_accepts_publish(capsys):
    from video_ai.cli import main
    assert main(['run', '--config', 'config/production.example.json', '--script', 'a.txt',
        '--unit-review', 'review.json', '--publish']) == 2


def test_refusal_exception_emits_complete_json_result(monkeypatch,capsys):
    from video_ai import pipeline
    from video_ai.cli import main
    def refuse(*a,**k):raise pipeline.PipelineRefusal('TEST ONLY stale source')
    monkeypatch.setattr(pipeline,'resume_pipeline',refuse)
    assert main(['resume','--config','config/production.example.json','--run-dir',
        'D:/VideoSi/projects/video-ai/runs/20261005-000000-111111111111','--json'])==2
    value=json.loads(capsys.readouterr().out)
    assert value['status']=='refused' and value['published'] is False
    assert {'run_dir','parent_run_dir','active_stage','waiting_for','candidate_path','subtitle_path','report_path'}<=set(value)
    assert value['validation']['full_film_acceptance']=='unverified'


@pytest.mark.parametrize('method',[[],{}])
def test_real_cli_malformed_author_method_refuses_json_before_any_run(runtime_run,capsys,monkeypatch,method):
    from pipeline_helpers import unit_review,write
    from video_ai.cli import main
    from video_ai import pipeline
    run,config,_=runtime_run
    script=run/'TEST-ONLY-original.txt';script.write_text('一只鸟。',encoding='utf-8')
    review=unit_review(script,run/'TEST-ONLY-author.json')
    data=json.loads(review.read_text(encoding='utf-8'));data['review_method']=method;write(review,data)
    monkeypatch.setattr(pipeline,'create_run',lambda *a:pytest.fail('malformed author created run'))
    assert main(['run','--config',str(config.config_file),'--script',str(script),'--unit-review',str(review),'--json'])==2
    value=json.loads(capsys.readouterr().out)
    assert value['status']=='refused' and value['published'] is False


def test_real_cli_missing_author_file_is_structured_admission_refusal(runtime_run,capsys):
    from video_ai.cli import main
    run,config,_=runtime_run
    script=run/'TEST-ONLY-original.txt';script.write_text('一只鸟。',encoding='utf-8')
    assert main(['run','--config',str(config.config_file),'--script',str(script),'--unit-review',str(run/'missing.json'),'--json'])==2
    value=json.loads(capsys.readouterr().out)
    assert value['status']=='refused' and value['published'] is False


def test_cli_execution_io_failure_emits_complete_failed_json(monkeypatch,capsys):
    from video_ai import pipeline
    from video_ai.cli import main
    def failed(*a,**kw):raise OSError('TEST ONLY execution disk failure')
    monkeypatch.setattr(pipeline,'run_pipeline',failed)
    assert main(['run','--config','config/production.example.json','--script','a.txt','--unit-review','review.json','--json'])==1
    assert json.loads(capsys.readouterr().out)['status']=='failed'


def test_cli_raw_interrupt_retains_130_and_complete_json(monkeypatch,capsys):
    from video_ai import pipeline
    from video_ai.cli import main
    def interrupted(*a,**kw):raise KeyboardInterrupt('TEST ONLY original interruption')
    monkeypatch.setattr(pipeline,'resume_pipeline',interrupted)
    assert main(['resume','--config','config/production.example.json','--run-dir',
        'D:/VideoSi/projects/video-ai/runs/20261005-000000-111111111111','--json'])==130
    value=json.loads(capsys.readouterr().out)
    assert value['status']=='interrupted' and not value['published']
    assert value['validation']['full_film_acceptance']=='unverified'
