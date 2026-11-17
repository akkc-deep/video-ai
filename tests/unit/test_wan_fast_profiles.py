import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from video_ai.experiments.wan_fast_profiles import (
    Artifact, load_profile, freeze_profile, verify_profile, UnsupportedProfile,
)

SOURCE = Path(__file__).parents[2]


@pytest.fixture(autouse=True)
def small_weight_pins(monkeypatch):
    import video_ai.experiments.wan_fast_profiles as module
    monkeypatch.setattr(module, 'LORA_PINS', {r: {'filename': r+'.bin', 'bytes': len(r),
        'sha256': hashlib.sha256(r.encode()).hexdigest()} for r in ('lora_high', 'lora_low')})


def assets_at(root):
    assets = {}
    for role in ('wan_high', 'wan_low', 'text_encoder', 'vae', 'lora_high', 'lora_low',
                 'workflow', 'mapping', 'provenance', 'node_source', 'media_source'):
        path = root / (role + '.bin')
        path.write_bytes(role.encode())
        assets[role] = Artifact(str(path.resolve()), len(role), hashlib.sha256(role.encode()).hexdigest())
    return assets


def profile_at(root, **kwargs):
    return load_profile('fast_experimental', factor='distill', assets=assets_at(root),
                        capabilities={'environment': {'python': 'fixture', 'comfy': 'fixture'}}, **kwargs)


def test_immutable_profile_recipe_and_digest(tmp_path):
    p = profile_at(tmp_path)
    assert (p.steps, p.cfg, p.split, p.shift) == (4, 1.0, 2, 5.0)
    assert p.sigma_points == (1, 15/16, 5/6, 5/8, 0)
    assert p.digest() == hashlib.sha256(json.dumps(p.identity_dict(), sort_keys=True,
        ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    with pytest.raises(FrozenInstanceError):
        p.steps = 3


@pytest.mark.parametrize('change', ['missing', 'sha', 'swap'])
def test_missing_corrupt_or_swapped_lora_refused(tmp_path, change):
    assets = assets_at(tmp_path)
    if change == 'missing':
        Path(assets['lora_low'].path).unlink()
    elif change == 'sha':
        Path(assets['lora_high'].path).write_bytes(b'x' * assets['lora_high'].bytes)
    else:
        assets['lora_high'], assets['lora_low'] = assets['lora_low'], assets['lora_high']
    with pytest.raises((ValueError, OSError)):
        load_profile('fast_experimental', factor='distill', assets=assets,
            capabilities={'environment': {'python': 'fixture'}})


def test_freeze_rejects_content_and_profile_drift(tmp_path):
    p = profile_at(tmp_path)
    freeze_profile(tmp_path, p)
    assert verify_profile(tmp_path, p.digest()) == p
    path = Path(dict(p.assets)['lora_high'].path)
    stamp = path.stat()
    path.write_bytes(b'x' * stamp.st_size)
    import os
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    with pytest.raises(ValueError, match='artifact'):
        verify_profile(tmp_path, p.digest())


def test_unknown_fields_and_backend_capabilities_refused(tmp_path):
    assets = assets_at(tmp_path)
    for factor in ('sage', 'cache', 'compile', 'combination', 'magic'):
        with pytest.raises((ValueError, UnsupportedProfile)):
            load_profile('fast_experimental', factor=factor, assets=assets,
                         capabilities={'environment': {'python': 'fixture'}})
    with pytest.raises(ValueError):
        load_profile('fast_experimental', factor='distill', assets={**assets, 'unknown': assets['vae']},
                     capabilities={'environment': {'python': 'fixture'}})


def test_original_quality_bytes_and_fast_graph_topology():
    original = SOURCE/'workflows/wan22_i2v_14b_api.json'
    assert hashlib.sha256(original.read_bytes()).hexdigest() == '5f3768f6e83bf6be21287457c7c15e811d8f6949b7b5c5ac5460c267c8f98666'
    graph = json.loads((SOURCE/'workflows/wan22_i2v_14b_fast_api.json').read_text(encoding='utf-8'))
    assert graph['lva04:lora_pair']['class_type'] == 'LVA04LoraPair'
    assert graph['129:104']['inputs']['model'] == ['lva04:lora_pair', 0]
    assert graph['129:103']['inputs']['model'] == ['lva04:lora_pair', 1]
    assert '129:131' not in graph
    for n in ('129:85', '129:86'):
        assert graph[n]['inputs']['steps'] == 4
        assert graph[n]['inputs']['cfg'] == 1


def test_empty_python_package_source_has_valid_content_identity(tmp_path):
    from video_ai.experiments.wan_fast_profiles import artifact
    path=tmp_path/'__init__.py';path.write_bytes(b'')
    value=artifact(path)
    assert value.bytes == 0
    value.verify()
