"""Opt-in policy freezing; all inputs are local and no service is started."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from video_ai.config import ConfigError, load_config
from video_ai.runtime.manifest import hash_file, thaw
from video_ai.runtime.production_inputs import freeze_inputs, load_frozen_inputs
from unit.test_jimeng_config import image_settings
from unit.test_production_inputs import production_config


POLICY = {'schema_version': 1, 'policy': 'advisory_v1'}
ROLE = 'scene_continuity_policy'


def configured(base, run, *, policy=POLICY, modern=True, include=True):
    raw = thaw(base.raw)
    if modern:
        raw.update(production_strategy='paragraph_jimeng_v1', image_generation=image_settings())
    if include:
        raw['scene_continuity'] = deepcopy(policy)
    file = run/'continuity-config.json'
    file.write_text(json.dumps(raw), encoding='utf-8')
    return load_config(file)


def save_options(run, options):
    (run/'production/options.json').write_text(json.dumps(options), encoding='utf-8')


def test_explicit_advisory_policy_loads_without_changing_resolved_fields(production_config, runtime_run):
    run, _, _ = runtime_run
    config = configured(production_config, run)
    assert thaw(config.raw['scene_continuity']) == POLICY
    assert config.production_strategy == 'paragraph_jimeng_v1'
    assert 'scene_continuity' not in vars(config)


@pytest.mark.parametrize('value', [
    None, False, True, [], {}, {'schema_version': 1}, {'policy': 'advisory_v1'},
    {'schema_version': True, 'policy': 'advisory_v1'},
    {'schema_version': 1.0, 'policy': 'advisory_v1'},
    {'schema_version': 2, 'policy': 'advisory_v1'},
    {'schema_version': 1, 'policy': None},
    {'schema_version': 1, 'policy': 'automatic'},
    {'schema_version': 1, 'policy': 'advisory_v1', 'enabled': True},
])
def test_partial_unknown_null_and_boolean_policy_rejected(production_config, runtime_run, value):
    with pytest.raises(ConfigError, match='scene_continuity'):
        configured(production_config, runtime_run[0], policy=value)


def test_legacy_strategy_cannot_enable_scene_continuity(production_config, runtime_run):
    with pytest.raises(ConfigError, match='paragraph_jimeng_v1'):
        configured(production_config, runtime_run[0], modern=False)


def test_freeze_adds_only_nested_original_file_identity(production_config, runtime_run):
    run, _, _ = runtime_run
    config = configured(production_config, run)
    frozen = freeze_inputs(config, run, text='湖水。')
    path = run/'production/scene-continuity/policy.json'
    assert json.loads(path.read_bytes()) == POLICY
    assert frozen.options['schema_version'] == 2
    assert set(frozen.options) == {
        'schema_version', 'execution_mode', 'run_id', 'created_at', 'input_mode', 'input_source',
        'script_path', 'config_snapshot', 'voice_snapshot', 'tts_yaml_path', 'workflow_snapshots',
        'model_stamps', 'output_paths', 'cpu_planner', 'execution_policy', 'production_strategy',
        'image_model_override', 'image_generation',
    }
    identity = frozen.options['execution_policy']['input_identities'][ROLE]
    assert set(identity) == {'path', 'bytes', 'mtime_ns', 'sha256', 'verified_at'}
    assert identity['path'] == str(path)
    assert identity['bytes'] == len(path.read_bytes())
    assert identity['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    before = (run/'production/options.json').read_bytes()
    config.config_file.write_text('original is no longer needed', encoding='utf-8')
    assert thaw(load_frozen_inputs(run).config.raw['scene_continuity']) == POLICY
    assert (run/'production/options.json').read_bytes() == before


@pytest.mark.parametrize('fault', ['missing_role', 'wrong_path', 'extra_role', 'missing_file',
                                  'same_stat_sha_drift', 'meaning_with_fresh_sha', 'artifact_shape'])
def test_frozen_policy_binding_cannot_be_omitted_relocated_or_forged(production_config, runtime_run, fault):
    run, _, _ = runtime_run
    frozen = freeze_inputs(configured(production_config, run), run, text='湖水。')
    records = frozen.options['execution_policy']['input_identities']
    path = Path(records[ROLE]['path'])
    if fault == 'missing_role':
        records.pop(ROLE)
    elif fault == 'wrong_path':
        other = run/'production/another-policy.json'
        other.write_bytes(path.read_bytes())
        records[ROLE] = thaw(hash_file(other))
    elif fault == 'extra_role':
        records[ROLE+'/duplicate'] = deepcopy(records[ROLE])
    elif fault == 'missing_file':
        path.unlink()
    elif fault == 'same_stat_sha_drift':
        stamp = path.stat()
        raw = path.read_bytes()
        path.write_bytes(raw.replace(b'advisory_v1', b'advisory_v2'))
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        assert path.stat().st_size == stamp.st_size
    elif fault == 'meaning_with_fresh_sha':
        path.write_text('{"schema_version":1,"policy":"advisory_v2"}', encoding='utf-8')
        records[ROLE] = thaw(hash_file(path))
    else:
        records[ROLE] = {key: records[ROLE][key] for key in ('path', 'bytes', 'sha256')}
    save_options(run, frozen.options)
    with pytest.raises((ValueError, OSError)):
        load_frozen_inputs(run)


@pytest.mark.parametrize('modern', [False, True])
def test_absent_policy_preserves_options_and_stray_directory_does_not_enable(production_config, runtime_run, modern):
    run, _, _ = runtime_run
    frozen = freeze_inputs(configured(production_config, run, include=False, modern=modern), run, text='湖水。')
    records = frozen.options['execution_policy']['input_identities']
    assert ROLE not in records
    assert 'scene_continuity' not in frozen.options['config_snapshot']['raw']
    policy_dir = run/'production/scene-continuity'
    assert not policy_dir.exists()
    policy_dir.mkdir()
    (policy_dir/'policy.json').write_text(json.dumps(POLICY), encoding='utf-8')
    before = (run/'production/options.json').read_bytes()
    loaded = load_frozen_inputs(run)
    assert ROLE not in loaded.options['execution_policy']['input_identities']
    assert (run/'production/options.json').read_bytes() == before


@pytest.mark.parametrize('modern', [False, True])
def test_policy_identity_without_original_config_is_rejected(production_config, runtime_run, modern):
    run, _, _ = runtime_run
    frozen = freeze_inputs(configured(production_config, run, include=False, modern=modern), run, text='湖水。')
    path = run/'production/scene-continuity/policy.json'
    path.parent.mkdir()
    path.write_text(json.dumps(POLICY), encoding='utf-8')
    frozen.options['execution_policy']['input_identities'][ROLE] = thaw(hash_file(path))
    save_options(run, frozen.options)
    with pytest.raises(ValueError):
        load_frozen_inputs(run)
