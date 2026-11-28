"""Performance decisions must not hide incomplete or acoustically changed trials."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('vox_performance',
    Path(__file__).resolve().parents[2]/'scripts/experiments/voxcpm2_performance.py')
experiment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(experiment)


def rows():
    return [dict(round=r, case=c, variant=v, generation_seconds=t,
                 raw_seconds=d, body_seconds=d-1, pipeline_seconds=t+.1,
                 pcm_sha256=c, body_pcm_sha256=c)
            for r in (0, 1) for c, d in (('long', 10), ('short', 3))
            for v, t in (('baseline', d), ('prompt-cache', d*.8))]


def test_weighted_rtf_excludes_cold_and_reports_cache_cost():
    trials = rows()+[dict(round=-1, case='cold', variant='cold', generation_seconds=999)]
    result = experiment.summarize(trials, {(r,c) for r in (0,1) for c in ('long','short')}, .5)
    assert result['baseline']['raw_rtf'] == 1
    assert result['prompt-cache']['raw_rtf'] == pytest.approx(.8)
    assert result['baseline']['body_rtf'] == pytest.approx(26/22)
    assert result['generation_reduction'] == pytest.approx(.2)
    assert result['cache_build_seconds'] == .5
    assert result['objective_gate_passed'] is True
    assert result['production_enabled'] is False


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'crossed'])
def test_incomplete_or_crossed_comparisons_are_rejected(mutation):
    trials = rows()
    if mutation == 'missing': trials.pop()
    if mutation == 'duplicate': trials.append(dict(trials[0]))
    if mutation == 'crossed': trials[0]['case'] = 'unknown'
    with pytest.raises(ValueError, match='pair'):
        experiment.summarize(trials, {(r,c) for r in (0,1) for c in ('long','short')}, .5)


def test_changed_pcm_blocks_objective_gate():
    trials = rows(); trials[-1]['pcm_sha256'] = 'different'
    result = experiment.summarize(trials, {(r,c) for r in (0,1) for c in ('long','short')}, .5)
    assert result['pcm_identical'] is False
    assert result['objective_gate_passed'] is False


def test_one_regressing_round_blocks_speed_gate():
    trials = rows()
    for row in trials:
        if row['round'] == 1 and row['variant'] == 'prompt-cache': row['generation_seconds'] *= 1.3
    result = experiment.summarize(trials, {(r,c) for r in (0,1) for c in ('long','short')}, .5)
    assert result['performance_gate_passed'] is False
