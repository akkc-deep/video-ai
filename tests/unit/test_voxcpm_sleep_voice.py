import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def experiment():
    path = Path(__file__).resolve().parents[2]/'scripts/experiments/voxcpm2_sleep_voice.py'
    spec = importlib.util.spec_from_file_location('sleep_voice_experiment', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('stop_error', [False, True])
def test_shutdown_failure_preserves_preference_and_writes_failed_report(experiment, tmp_path, stop_error):
    preference = tmp_path/'preference.json'; preference.write_text('{"previous": true}', encoding='utf-8')
    class Owner:
        def stop(self):
            if stop_error: raise OSError('shutdown failed')
            return 1
    report = {'status': 'generated_pending_listening'}
    failure = experiment.finalize_sample(report, Owner(), preference, {'new':True}, tmp_path)
    assert isinstance(failure, Exception)
    assert json.loads(preference.read_text(encoding='utf-8')) == {'previous':True}
    saved = json.loads((tmp_path/'result.json').read_text(encoding='utf-8'))
    assert saved['status'] == 'failed' and 'shutdown_error' in saved


def test_primary_failure_survives_shutdown_error(experiment, tmp_path):
    class Owner:
        def stop(self): raise OSError('shutdown failed')
    original = RuntimeError('synthesis failed')
    report = {'status':'failed','error':'synthesis failed'}
    failure = experiment.finalize_sample(report, Owner(), tmp_path/'preference.json', {}, tmp_path, original)
    assert failure is original
    assert not (tmp_path/'preference.json').exists()
    assert json.loads((tmp_path/'result.json').read_text(encoding='utf-8'))['error'] == 'synthesis failed'


def test_preference_commits_after_successful_shutdown(experiment, tmp_path):
    preference = tmp_path/'preference.json'
    class Owner:
        def stop(self):
            assert not preference.exists()
            return 0
    report = {'status':'running'}
    assert experiment.finalize_sample(report, Owner(), preference, {'new':True}, tmp_path) is None
    assert json.loads(preference.read_text(encoding='utf-8')) == {'new':True}
    assert report['status'] == 'generated_pending_listening'


def test_design_source_must_match_recorded_revision(experiment, tmp_path, monkeypatch):
    monkeypatch.setattr(experiment.subprocess, 'check_output', lambda *a,**kw:'different-commit\n')
    with pytest.raises(RuntimeError, match='source'):
        experiment.verify_design_source(tmp_path, {'source_revision':'frozen-commit'})
