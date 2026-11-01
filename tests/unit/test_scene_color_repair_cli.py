"""The explicit command refuses invalid paths and unknown bypass flags."""
import importlib.util
import json
from pathlib import Path

import pytest


def command():
    path=Path(__file__).parents[2]/'scripts/scene_color_repair.py'
    spec=importlib.util.spec_from_file_location('fixture_only_repair_cli',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.main


def test_cli_invalid_relative_run_returns_exact_blocked_result(capsys):
    assert command()(['propose','--run-dir','relative','--request','D:/VideoSi/missing.json'])==2
    result=json.loads(capsys.readouterr().out)
    assert set(result)==set('schema_version run_id candidate_id status intent terminal review_template error'.split())
    assert result['status']=='blocked' and result['intent'] is None and result['terminal'] is None
    assert set(result['error'])=={'kind','message','evidence_paths'}


def test_cli_has_no_force_or_production_adoption_switch():
    with pytest.raises(SystemExit) as exc:
        command()(['propose','--run-dir','D:/VideoSi/x','--request','D:/VideoSi/x.json','--force'])
    assert exc.value.code==2
