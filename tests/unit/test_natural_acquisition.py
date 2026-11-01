import hashlib
import json
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def collection(tmp_path, resource_config, monkeypatch):
    from video_ai.experiments import natural_acquisition as module
    monkeypatch.setattr(module, 'COLLECTION_ROOT', tmp_path)
    monkeypatch.setattr(module, 'load_config', lambda path: resource_config)
    root = tmp_path / 'new-study'
    module.freeze_collection(root, Path(__file__).parents[2]/'config/jimeng.example.json')
    return module, root


def test_references_are_authored_distinct_rgb8_with_supported_srgb():
    from video_ai.experiments.natural_acquisition import render_reference, encode_reference
    from video_ai.media.colorimetry import _png_metadata
    from video_ai.runtime.paths import CACHE_ROOT
    from uuid import uuid4
    hashes = set()
    for i in range(8):
        image = render_reference(i)
        assert image.shape == (432, 768, 3) and image.dtype == np.uint8
        assert np.array_equal(image, render_reference(i))
        hashes.add(hashlib.sha256(image.tobytes()).hexdigest())
        path = CACHE_ROOT / 'temp' / ('authored-reference-' + uuid4().hex + '.png')
        path.write_bytes(encode_reference(image))
        meta, conflicts = _png_metadata(path)
        assert meta['srgb_intent'] == 0 and meta['icc_sha256'] is None and not conflicts
    assert len(hashes) == 8


@pytest.mark.parametrize('index', [-1, 8, True, 1.5])
def test_renderer_rejects_unknown_scene(index):
    from video_ai.experiments.natural_acquisition import render_reference
    with pytest.raises(ValueError):
        render_reference(index)


def test_freeze_has_exact_split_group_and_request_budget(collection):
    module, root = collection
    plan = module.load_collection(root)
    assert plan['max_requests'] == 24
    assert plan['reference_domain'] == 'authored_srgb_still_life'
    assert len(plan['cases']) == 24
    for split in ('development', 'holdout'):
        cases = [c for c in plan['cases'] if c['split'] == split]
        assert len(cases) == 12
        assert len({c['scene_group'] for c in cases}) == 4
        assert all(c['frames'] == 49 and c['fps'] == '16/1' for c in cases)
        assert all(c['natural_label'] == 'unverified' for c in cases)
    assert len({(c['seed_high'], c['seed_low']) for c in plan['cases']}) == 24
    assert not (root / 'inputs.FROZEN.json').exists()
    assert not (root / 'natural-repair-profile.json').exists()


def test_freeze_refuses_overwrite(collection):
    module, root = collection
    before = (root / 'collection.FROZEN.json').read_bytes()
    with pytest.raises(FileExistsError):
        module.freeze_collection(root, Path(module.load_collection(root)['config']['path']))
    assert (root / 'collection.FROZEN.json').read_bytes() == before


def test_load_rejects_reference_drift(collection):
    module, root = collection
    plan = module.load_collection(root)
    path = Path(plan['scenes'][0]['reference']['path'])
    path.write_bytes(path.read_bytes()[:-1] + b'x')
    with pytest.raises(ValueError, match='identity'):
        module.load_collection(root)


@pytest.mark.parametrize('mutation', ['cross_split', 'duplicate_seed', 'missing_case', 'budget', 'label'])
def test_plan_validation_rejects_scientific_shortcuts(collection, mutation):
    module, root = collection
    plan = module.load_collection(root)
    if mutation == 'cross_split':
        plan['cases'][12]['scene_group'] = plan['cases'][0]['scene_group']
    elif mutation == 'duplicate_seed':
        plan['cases'][1]['seed_high'] = plan['cases'][0]['seed_high']
    elif mutation == 'missing_case':
        plan['cases'].pop()
    elif mutation == 'budget':
        plan['max_requests'] = 25
    else:
        plan['cases'][0]['natural_label'] = 'mild_color_bias'
    with pytest.raises(ValueError):
        module.validate_collection(plan)


def test_root_escape_refused_before_creating_files(tmp_path):
    from video_ai.experiments.natural_acquisition import freeze_collection
    with pytest.raises(ValueError):
        freeze_collection(Path('D:/VideoSi/output/invalid-acquisition'), Path('missing-config.json'))


def test_frozen_json_cannot_be_edited_and_resumed(collection):
    module, root = collection
    path = root / 'collection.FROZEN.json'
    plan = json.loads(path.read_bytes())
    plan['cases'][0]['positive_prompt'] += ' altered'
    path.write_text(json.dumps(plan), encoding='utf-8')
    with pytest.raises(ValueError, match='identity'):
        module.load_collection(root)


def test_authorship_receipt_source_can_be_consumed_by_official_reader(collection):
    from video_ai.runtime.research_material_records import ResearchReader
    module, root = collection
    plan = module.load_collection(root)
    reader = ResearchReader()
    conversion = reader.read(plan['scenes'][0]['conversion'])
    assert Path(conversion['source']['path']).is_relative_to(root)
    reader.capture(conversion['source'])
    reader.verify_all()


def test_relocated_config_retains_resolved_workflow_and_voice_paths(collection, resource_config):
    from video_ai.config import load_config
    module, root = collection
    plan = module.load_collection(root)
    loaded = load_config(Path(plan['config']['path']))
    assert loaded.workflows['wan'] == resource_config.workflows['wan']
    assert loaded.voice.config_file == resource_config.voice.config_file
