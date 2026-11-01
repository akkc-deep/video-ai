"""Pilot planning tests do not create model or human-viewing evidence."""
import copy
import hashlib
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def pilot(tmp_path, resource_config, monkeypatch):
    from video_ai.experiments import natural_pilot as module
    monkeypatch.setattr(module, 'PILOT_ROOT', tmp_path)
    monkeypatch.setattr(module, 'load_config', lambda path: resource_config)
    (resource_config.tools['comfy_root']/'main.py').write_bytes(b'# fixture Comfy entry, never executed')
    root = tmp_path/'new-pilot'
    module.freeze_pilot(root, Path(__file__).parents[2]/'config/jimeng.example.json')
    return module, root


def test_four_new_references_are_deterministic_declared_srgb(tmp_path):
    from video_ai.experiments.natural_pilot import render_pilot_reference
    from video_ai.experiments.natural_acquisition import encode_reference
    from video_ai.media.colorimetry import _png_metadata
    hashes = set()
    for i in range(4):
        rgb = render_pilot_reference(i)
        assert rgb.shape == (432,768,3) and rgb.dtype == np.uint8
        assert np.array_equal(rgb,render_pilot_reference(i))
        hashes.add(hashlib.sha256(rgb.tobytes()).hexdigest())
        path = tmp_path/f'{i}.png';path.write_bytes(encode_reference(rgb))
        meta, conflicts = _png_metadata(path)
        assert meta['srgb_intent'] == 0 and not conflicts
    assert len(hashes) == 4


@pytest.mark.parametrize('index',[-1,4,True,.5])
def test_pilot_renderer_refuses_extra_sources(index):
    from video_ai.experiments.natural_pilot import render_pilot_reference
    with pytest.raises(ValueError): render_pilot_reference(index)


def test_pilot_budget_is_exactly_four_development_only_requests(pilot):
    module, root = pilot
    plan = module.load_pilot(root)
    assert plan['max_requests'] == 4 and len(plan['cases']) == 4
    assert all(c['split'] == 'development' and c['natural_label'] == 'unverified' for c in plan['cases'])
    assert len({c['seed_high'] for c in plan['cases']}) == 4
    assert all(c['frames'] == 49 and c['fps'] == '16/1' for c in plan['cases'])
    assert plan['expected_motion'] == 'stationary_camera_and_objects'
    assert not (root/'inputs.FROZEN.json').exists()
    assert plan['production_eligible'] is False


@pytest.mark.parametrize('problem',['extra_case','holdout','seed','prompt','label','budget','motion'])
def test_pilot_schema_refuses_changed_budget_or_scientific_intent(pilot, problem):
    module, root = pilot
    plan = copy.deepcopy(module.load_pilot(root))
    if problem == 'extra_case': plan['cases'].append(plan['cases'][0])
    elif problem == 'holdout': plan['cases'][0]['split'] = 'holdout'
    elif problem == 'seed': plan['cases'][0]['seed_high'] += 1
    elif problem == 'prompt': plan['cases'][0]['positive_prompt'] += ' warmer'
    elif problem == 'label': plan['cases'][0]['natural_label'] = 'mild_color_bias'
    elif problem == 'budget': plan['max_requests'] = 24
    elif problem == 'motion': plan['expected_motion'] = 'complex_actor_action'
    with pytest.raises(ValueError): module.validate_pilot(plan)


def test_new_pilot_is_never_accepted_as_old_twenty_four_collection(pilot):
    from video_ai.experiments.natural_acquisition import validate_collection
    module, root = pilot
    with pytest.raises(ValueError): validate_collection(module.load_pilot(root))


def test_pilot_freeze_cannot_overwrite_or_escape(pilot):
    module, root = pilot
    raw = (root/'pilot.FROZEN.json').read_bytes()
    with pytest.raises(FileExistsError): module.freeze_pilot(root,Path('not-used'))
    assert (root/'pilot.FROZEN.json').read_bytes() == raw
    with pytest.raises(ValueError): module.freeze_pilot(root.parent.parent/'outside',Path('not-used'))


@pytest.mark.parametrize('item',['reference','conversion','config','frozen_json','renderer_archive','comfy_entry','executable'])
def test_pilot_load_rejects_any_frozen_input_drift(pilot,item):
    module, root = pilot
    plan = module.load_pilot(root)
    paths = dict(reference=Path(plan['cases'][0]['reference']['path']),conversion=Path(plan['cases'][0]['conversion']['path']),
        config=Path(plan['config']['path']),frozen_json=root/'pilot.FROZEN.json',renderer_archive=root/'reference-renderer.py',
        comfy_entry=module.load_config(Path(plan['config']['path'])).tools['comfy_root']/'main.py',
        executable=module.load_config(Path(plan['config']['path'])).tools['comfy_python'])
    path = paths[item];path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError,match='identity'): module.load_pilot(root)


def test_frozen_pilot_includes_actual_request_service_and_freeze_dependencies(pilot):
    module,root=pilot
    plan=module.load_pilot(root)
    files={Path(p['path']).as_posix() for p in plan['software']+plan['dependencies']}
    base=Path(module.__file__).parents[1]
    for relative in ('adapters/comfyui.py','runtime/services.py','runtime/production_inputs.py','runtime/workflows.py'):
        assert (base/relative).as_posix() in files


def test_case_selection_is_frozen_before_any_side_effect(pilot):
    module, root = pilot
    before = sorted(str(p) for p in root.rglob('*'))
    with pytest.raises(ValueError): module.pilot_case(root,'../outside')
    assert sorted(str(p) for p in root.rglob('*')) == before
