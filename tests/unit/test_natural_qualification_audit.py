"""Fixture-only audit isolation; source/pixel replay is exercised on the actual delivery separately."""
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

import pytest

from video_ai.runtime._scene_continuity_io import artifact
from scene_continuity_helpers import save
from test_natural_repair_statistics import constant


@pytest.fixture
def audit_input(runtime_run, monkeypatch):
    run = runtime_run[0]
    ctx = dict(run_id=run.name, run_dir=str(run), material_id=str(uuid4()),
        status='research_input_ready', source_kind='research_wan_material_v1')
    for name in ('source','selected_image','commit','epoch','frame_map'):
        ctx[name] = artifact(save(run/'fixture-only'/f'{name}.json', {'fixture_only': name}))
    report = artifact(save(run/'fixture-only/report.json', {'fixture_only': 'report'}))
    ctx['assessment'] = artifact(save(run/'research/continuity/assessment.json',
        dict(manifest=artifact(save(run/'fixture-only/manifest.json', {'fixture_only': True})), report=report)))
    save(run/'research/options.json', dict(config=artifact(save(run/'fixture-only/config.json', {'fixture_only': True}))))
    expected = dict(schema_version=1, algorithm='natural_constant_color_repair_v1',
        kind='unqualified_natural_diagnostic_v1', report=report, implementation=[],
        frames=[constant(0,.01), constant(1,.02)], all_frames_supported=True,
        operation=None, thresholds=None, qualification='awaiting_qualification',
        full_video_observation='unverified', production_eligible=False, ready_for_propose=False)
    stored = deepcopy(expected); stored.update(commit=ctx['commit'], assessment=ctx['assessment'])
    baseline = save(run/'research/continuity/natural-baseline.json', stored)
    baseline.write_bytes((json.dumps(stored,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8'))
    delivery = dict(schema_version=1, task_id='VCO-06', status='research_input_ready',
        run_dir=str(run), source_kind=ctx['source_kind'], material_id=ctx['material_id'],
        **{k:ctx[k] for k in ('source','selected_image','commit','epoch','assessment','frame_map')},
        report=report, natural_baseline=artifact(baseline), native=dict(frames=2),
        qualification='awaiting_qualification', full_video_observation='unverified',
        operation=None, natural_profile=None, ready_for_propose=False,
        production_eligible=False, production_ready=False)
    path = save(run/'fixture-only/delivery.json', delivery)
    # Isolate existing expensive formal source/pixel dependencies; all new file
    # reads, hashes, byte replay comparisons, statistics and output writes are real.
    def load_module():
        import video_ai.runtime.natural_qualification_audit as module
        monkeypatch.setattr(module, 'load_research_material_context', lambda path, reader: deepcopy(ctx))
        monkeypatch.setattr(module, 'load_config', lambda path: object())
        monkeypatch.setattr(module, 'validate_research_pair_report', lambda *a, **kw: dict(closure=[report]))
        monkeypatch.setattr(module, 'measure_natural_manifest', lambda *a, **kw: deepcopy(expected))
        return module
    return dict(run=run, context=ctx, expected=expected, stored=stored,
                baseline=baseline, delivery=delivery, path=path, load_module=load_module)


def test_validated_replay_is_diagnostic_and_does_not_create_a_profile(audit_input):
    result = audit_input['load_module']().audit_natural_qualification(audit_input['path'])
    assert result['status'] == 'awaiting_qualification'
    assert result['native_frames'] == 2
    assert result['baseline_replayed'] is True
    assert result['qualified_directions'] == []
    assert all(v is None for v in result['thresholds'].values())
    assert result['natural_positive_cases'] == result['new_holdout_cases'] == 0
    assert result['candidate_generated'] is False and result['ready_for_propose'] is False
    assert result['statistics']['exposure']['bias_mean_absolute'] == pytest.approx(.015)


@pytest.mark.parametrize('change', ['source','commit','epoch','assessment','material_id','run_dir',
    'report','native','qualified','profile','operation','observation'])
def test_foreign_or_qualified_input_claims_are_not_accepted(audit_input, change):
    case = audit_input
    module = case['load_module']()
    value = deepcopy(case['delivery'])
    if change in ('source','commit','epoch','assessment','report'):
        value[change] = artifact(save(case['run']/f'foreign-{change}.json', {'foreign': change}))
    elif change == 'material_id': value['material_id'] = str(uuid4())
    elif change == 'run_dir': value['run_dir'] = str(case['run']/'other')
    elif change == 'native': value['native']['frames'] = 1
    elif change == 'qualified': value['ready_for_propose'] = True
    elif change == 'profile': value['natural_profile'] = value['commit']
    elif change == 'operation': value['operation'] = 'exposure'
    else: value['full_video_observation'] = 'passed'
    save(case['path'], value)
    with pytest.raises((ValueError,OSError)): module.audit_natural_qualification(case['path'])


def test_refreshed_hash_cannot_hide_forged_baseline_measurements(audit_input):
    case = audit_input
    module = case['load_module']()
    changed = deepcopy(case['stored'])
    changed['frames'][0]['features']['roles'][0]['log2_ratios'][0][0] = .5
    save(case['baseline'], changed)
    case['delivery']['natural_baseline'] = artifact(case['baseline'])
    save(case['path'], case['delivery'])
    with pytest.raises(ValueError, match='replay'):
        module.audit_natural_qualification(case['path'])


def test_same_size_restored_mtime_baseline_drift_is_rejected(audit_input):
    import os
    case = audit_input; stamp = case['baseline'].stat(); original = case['baseline'].read_bytes()
    module = case['load_module']()
    changed = original.replace(b'0.01', b'0.02', 1)
    assert changed != original and len(changed) == len(original)
    case['baseline'].write_bytes(changed)
    os.utime(case['baseline'], ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    with pytest.raises((ValueError,OSError)):
        module.audit_natural_qualification(case['path'])


def test_report_change_after_pixel_replay_is_caught_before_audit(audit_input, monkeypatch):
    case = audit_input; module = case['load_module']()
    original = module.measure_natural_manifest
    def replay_then_change(*args, **kwargs):
        measured = original(*args, **kwargs)
        Path(case['delivery']['report']['path']).write_bytes(b'{"changed_after_replay":true}')
        return measured
    monkeypatch.setattr(module, 'measure_natural_manifest', replay_then_change)
    with pytest.raises((ValueError, OSError)):
        module.audit_natural_qualification(case['path'])


def test_shard_change_after_replay_is_caught_in_the_same_read_window(audit_input, monkeypatch):
    case = audit_input; module = case['load_module']()
    shard = save(case['run']/'fixture-only/shard.json', {'fixture_only':'shard'})
    shard_ref = artifact(shard)
    monkeypatch.setattr(module, 'validate_research_pair_report',
        lambda *a, **kw: dict(closure=[case['delivery']['report'], shard_ref]))
    original = module.measure_natural_manifest
    def replay_then_change(*args, **kwargs):
        measured = original(*args, **kwargs)
        shard.write_bytes(b'{"changed_after_replay":true}')
        return measured
    monkeypatch.setattr(module, 'measure_natural_manifest', replay_then_change)
    with pytest.raises((ValueError, OSError)):
        module.audit_natural_qualification(case['path'])


def test_output_is_exclusive_and_separate_from_delivered_inputs(audit_input, monkeypatch):
    case = audit_input; module = case['load_module']()
    output = module.AUDIT_ROOT/uuid4().hex/'qualification-audit.json'
    result = module.write_qualification_audit(case['path'], output)
    assert result['status'] == 'awaiting_qualification'
    before = output.read_bytes(), output.stat().st_mtime_ns
    with pytest.raises(FileExistsError): module.write_qualification_audit(case['path'],output)
    assert (output.read_bytes(),output.stat().st_mtime_ns) == before
    with pytest.raises(ValueError):
        module.write_qualification_audit(case['path'],case['run']/'qualification-audit.json')


def test_cli_reports_waiting_and_preserves_failure_exit_contract(audit_input):
    from importlib.util import module_from_spec,spec_from_file_location
    module = audit_input['load_module']()
    spec = spec_from_file_location('fixture_qualification_cli',
        Path(__file__).parents[2]/'scripts/experiments/vco06_natural_qualification.py')
    cli = module_from_spec(spec); spec.loader.exec_module(cli)
    output = module.AUDIT_ROOT/uuid4().hex/'audit.json'
    arguments = ['audit','--delivery',str(audit_input['path']),'--output',str(output)]
    assert cli.main(arguments) == 3
    assert json.loads(output.read_text(encoding='utf-8'))['ready_for_propose'] is False
    assert cli.main(arguments) == 2


def test_independent_root_cannot_be_used_to_write_inside_a_delivered_bundle(audit_input):
    case = audit_input; module = case['load_module']()
    bundle = module.AUDIT_ROOT/uuid4().hex/'inputs'
    bundle.mkdir(parents=True)
    copied_delivery = bundle/'delivery.json'
    copied_delivery.write_bytes(case['path'].read_bytes())
    output = bundle/'qualification-audit.json'
    with pytest.raises(ValueError, match='bundle'):
        module.write_qualification_audit(copied_delivery, output)
    assert not output.exists()
