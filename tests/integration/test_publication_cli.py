"""CLI routing, lexical paths, scope of claims and stage exit codes."""
from pathlib import Path
from types import SimpleNamespace
import json
import pytest

from video_ai.cli import main


def test_help_exposes_candidate_and_publication_commands(capsys):
    assert main(['--help']) == 0
    help_text = capsys.readouterr().out
    assert 'validate-candidate' in help_text
    assert 'publish-candidate' in help_text


@pytest.mark.parametrize('command', ['validate-candidate', 'publish-candidate'])
@pytest.mark.parametrize('status,expected', [('completed', 0), ('failed', 1), ('refused', 2), ('interrupted', 130)])
def test_stage_routing_paths_limits_and_exit_codes(monkeypatch, capsys, command, status, expected):
    from video_ai.config import load_config
    from video_ai.runtime import candidate_checks, publication
    config = load_config(Path('D:/code/py/video-ai/config/production.example.json'))
    monkeypatch.setattr('video_ai.cli._load_cli_config', lambda *args: config)
    module = candidate_checks if command == 'validate-candidate' else publication
    refusal = module.CandidateRefusal if command == 'validate-candidate' else module.PublicationRefusal

    def action(c, *, run_dir, **kwargs):
        assert c is config
        assert run_dir == Path.cwd() / 'relative-run'
        if command == 'publish-candidate':
            assert kwargs == dict(review_path=Path.cwd()/'review.json', acceptance_path=Path.cwd()/'acceptance.json', output_path=Path.cwd()/'out.mp4')
        else:
            assert not kwargs
        if status == 'refused':
            raise refusal('TEST ONLY missing accepted review')
        if status == 'interrupted':
            raise KeyboardInterrupt()
        return SimpleNamespace(passed=status=='completed', status=status, run_dir=run_dir,
            report_path=run_dir/('candidate-validation.json' if command=='validate-candidate' else 'publication.json'),
            staging_only=command=='validate-candidate' or status!='completed',
            published=command=='publish-candidate' and status=='completed',
            ready_for_review=command=='validate-candidate' and status=='completed')

    # thaw handles dataclasses; using a dataclass-shaped real result also verifies JSON fields.
    from dataclasses import make_dataclass
    Result = make_dataclass('TestResult', [('passed', bool), ('status', str), ('run_dir', Path), ('report_path', Path), ('staging_only', bool), ('published', bool), ('ready_for_review', bool)], frozen=True)
    def wrapped(*args, **kwargs):
        return Result(**vars(action(*args, **kwargs)))
    monkeypatch.setattr(module, 'validate_candidate' if command=='validate-candidate' else 'publish_candidate', wrapped)
    args = [command, '--config', 'config.json', '--run-dir', 'relative-run', '--json']
    if command == 'publish-candidate':
        args += ['--review','review.json','--acceptance','acceptance.json','--output','out.mp4']
    assert main(args) == expected
    output = capsys.readouterr()
    if expected in (0, 1):
        result = json.loads(output.out)
        assert result['status'] == status
        assert result['staging_only'] == (command=='validate-candidate' or status!='completed')
        final = 'passed' if command=='publish-candidate' and status=='completed' else 'unverified'
        assert all(result['validation'][key] == final for key in ('actual_final_video_semantics','actual_final_video_sync','full_film_acceptance'))
        technical = {'media_passed','source_frame_mapping_passed','subtitle_text_timing_passed','narration_samples_passed','input_associations_passed'}
        assert technical <= set(result['validation'])
        assert all(result['validation'][key] == (True if status=='completed' else 'unverified') for key in technical)
        if status == 'failed':
            assert not any(value is True for key, value in result['validation'].items() if key.endswith('_passed'))


def test_publication_requires_explicit_review_and_acceptance():
    assert main(['publish-candidate','--config','config.json','--run-dir','run']) == 2
