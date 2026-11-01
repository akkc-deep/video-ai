import importlib.util
import json
from pathlib import Path
import pytest


def cli():
    spec = importlib.util.spec_from_file_location('research_cli', Path(__file__).parents[2]/'scripts/scene_research_material.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_import_request_returns_exact_error_contract(runtime_run, capsys):
    run, _, _ = runtime_run
    code = cli().main(['import', '--request', str(run/'missing.json')])
    result = json.loads(capsys.readouterr().out)
    assert code == 2
    assert set(result) == set('schema_version material_id run_dir status commit error'.split())
    assert result['status'] == 'blocked'


def test_import_interrupt_is_structured_130(runtime_run, monkeypatch, capsys):
    from video_ai.runtime.research_material_records import ResearchReader
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt()
    monkeypatch.setattr(ResearchReader, 'read', interrupted)
    run, _, _ = runtime_run
    code = cli().main(['import', '--request', str(run/'request.json')])
    result = json.loads(capsys.readouterr().out)
    assert code == 130
    assert result['status'] == 'interrupted'
    assert result['error']['kind'] == 'KeyboardInterrupt'
