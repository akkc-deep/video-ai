"""Explicit, evidence-backed reference configuration; no cloud calls."""
import copy
import hashlib
import json

import pytest

from unit.test_jimeng_config import configured, image_settings


def capability(req_key='jimeng_t2i_v40', **changes):
    value = dict(schema_version=1, req_key=req_key, input_field='image_urls', max_images=1,
                 max_image_bytes=10_000_000, min_width=16, min_height=9,
                 max_width=4096, max_height=4096, formats=['png', 'jpeg', 'webp'],
                 max_prompt_bytes=100_000, evidence=dict(
                     source_url='https://docs.volcengine.com/docs/test-reference-fixture',
                     source_sha256='a'*64, verified_by='offline-test-fixture',
                     verified_at='2026-10-18T00:00:00+00:00'))
    value.update(changes)
    return value


def storage_settings(**changes):
    value = dict(provider='volcengine_tos', bucket='test-bucket', region='cn-beijing',
                 endpoint='https://tos-cn-beijing.volces.com', access_key_env='TEST_TOS_AK',
                 secret_key_env='TEST_TOS_SK')
    value.update(changes)
    return value


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return path


def test_explicit_capability_and_storage_defaults():
    from video_ai.reference_config import parse_capability, parse_reference_storage
    parsed = parse_capability(capability(), req_key='jimeng_t2i_v40')
    assert parsed['max_images'] == 1 and parsed['evidence']['verified_by'] == 'offline-test-fixture'
    settings = parse_reference_storage(storage_settings())
    assert settings['url_ttl_seconds'] == 3600
    assert settings['key_prefix'] == 'video-ai-references'


@pytest.mark.parametrize('field,value', [
    ('schema_version', True), ('max_images', True), ('min_width', 0), ('max_image_bytes', -1),
    ('max_width', 1), ('formats', ['png', 'png']), ('formats', ['gif']),
    ('input_field', 'image_base64'), ('req_key', 'other'), ('extra', 1),
])
def test_capability_rejects_unknown_or_unverified_limits(field, value):
    from video_ai.reference_config import parse_capability
    with pytest.raises(ValueError):
        parse_capability(capability(**{field: value}), req_key='jimeng_t2i_v40')


@pytest.mark.parametrize('change', [
    {'source_url': 'https://evil.test/docs'}, {'source_url': 'https://user@docs.volcengine.com/x'},
    {'source_url': 'https://docs.volcengine.com/x#fragment'}, {'source_sha256': 'A'*64},
    {'verified_by': ''}, {'verified_at': '2026-10-18T00:00:00'}, {'extra': 1},
])
def test_capability_requires_explicit_official_evidence(change):
    from video_ai.reference_config import parse_capability
    value = capability(); value['evidence'].update(change)
    with pytest.raises(ValueError): parse_capability(value, req_key='jimeng_t2i_v40')


@pytest.mark.parametrize('change', [
    {'bucket': 'ABC'}, {'region': '../x'}, {'endpoint': 'https://tos-cn-beijing.volces.com/path'},
    {'endpoint': 'https://tos-cn-shanghai.volces.com'}, {'url_ttl_seconds': True},
    {'url_ttl_seconds': 604801}, {'download_margin_seconds': 0}, {'clock_skew_seconds': 0.5},
    {'request_timeout_seconds': float('inf')}, {'key_prefix': 'x/../y'}, {'key_prefix': 'x//y'},
    {'access_key_env': 'actual-secret-value!'}, {'extra': 'x'},
])
def test_storage_rejects_unsafe_or_invalid_settings(change):
    from video_ai.reference_config import parse_reference_storage
    with pytest.raises(ValueError): parse_reference_storage(storage_settings(**change))


def test_model_selection_prefers_chosen_model_and_never_guesses():
    from video_ai.jimeng_config import parse_image_generation
    from video_ai.reference_config import choose_reference_model, ReferenceConfigurationRequired
    image = parse_image_generation(image_settings(), 'fixture')
    fallback = dict(image_settings(), req_key='explicit_reference')
    selected, cap = choose_reference_model(image, fallback, {'jimeng_t2i_v40': capability()})
    assert selected.req_key == image.req_key
    selected, cap = choose_reference_model(image, fallback, {'explicit_reference': capability('explicit_reference')})
    assert selected.req_key == 'explicit_reference'
    with pytest.raises(ReferenceConfigurationRequired): choose_reference_model(image, None, {})


def test_raw_reference_settings_freeze_capability_bytes_without_changing_resolved(runtime_run, tmp_path):
    from video_ai.runtime.production_inputs import freeze_inputs, load_frozen_inputs
    from video_ai.runtime.manifest import thaw
    raw = json.dumps(capability(), indent=2).encode('utf-8')
    cap_path = tmp_path/'capability.json'; cap_path.write_bytes(raw)
    config = configured(runtime_run[1], tmp_path, reference_generation=None,
                        reference_capabilities={'jimeng_t2i_v40': str(cap_path)},
                        reference_storage=storage_settings())
    frozen = freeze_inputs(config, runtime_run[0], text='完整旁白。')
    target = runtime_run[0]/'production/reference-capabilities/jimeng_t2i_v40.json'
    assert target.read_bytes() == raw
    assert frozen.options['config_snapshot']['raw']['reference_storage']['bucket'] == 'test-bucket'
    assert 'reference_storage' not in frozen.options['config_snapshot']['resolved']
    cap_path.write_text('{}', encoding='utf-8')
    assert load_frozen_inputs(runtime_run[0]).config.production_strategy == 'paragraph_jimeng_v1'
    target.write_bytes(b'{}')
    with pytest.raises(ValueError, match='frozen input changed'): load_frozen_inputs(runtime_run[0])


def test_legacy_prepared_run_can_bind_missing_settings_once(runtime_run, tmp_path):
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.reference_settings import bind_reference_settings, load_reference_settings
    from video_ai.runtime.jimeng_candidates import _Records
    config = configured(runtime_run[1], tmp_path)
    frozen = freeze_inputs(config, runtime_run[0], text='完整旁白。')
    options_before = (runtime_run[0]/'production/options.json').read_bytes()
    cap_path = write_json(tmp_path/'cap.json', capability())
    source = write_json(tmp_path/'reference-settings.json', dict(reference_generation=None,
        reference_capabilities={'jimeng_t2i_v40': str(cap_path)}, reference_storage=storage_settings()))
    with RunLock(runtime_run[0]) as held:
        settings = bind_reference_settings(frozen, reference_settings_path=source, store=_Records(runtime_run[0], held))
    assert settings['model_settings']['req_key'] == 'jimeng_t2i_v40'
    assert settings['config_source_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    source.unlink(); cap_path.unlink()
    assert load_reference_settings(frozen) == settings
    assert (runtime_run[0]/'production/options.json').read_bytes() == options_before


def test_missing_settings_and_insufficient_ttl_write_no_marker(runtime_run, tmp_path):
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.reference_settings import bind_reference_settings
    from video_ai.reference_config import ReferenceConfigurationRequired
    from video_ai.runtime.jimeng_candidates import _Records
    frozen = freeze_inputs(configured(runtime_run[1], tmp_path), runtime_run[0], text='完整旁白。')
    cap_path = write_json(tmp_path/'cap.json', capability())
    source = write_json(tmp_path/'settings.json', dict(reference_generation=None,
        reference_capabilities={'jimeng_t2i_v40': str(cap_path)}, reference_storage=storage_settings(url_ttl_seconds=100)))
    with RunLock(runtime_run[0]) as held:
        store = _Records(runtime_run[0], held)
        with pytest.raises(ReferenceConfigurationRequired): bind_reference_settings(frozen, store=store)
        with pytest.raises(ReferenceConfigurationRequired): bind_reference_settings(frozen, store=store, reference_settings_path=source)
    assert not (runtime_run[0]/'production/reference-images/settings.json').exists()


def test_bound_source_and_capability_cannot_change(runtime_run, tmp_path):
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.reference_settings import bind_reference_settings, load_reference_settings
    from video_ai.runtime.jimeng_candidates import _Records
    frozen = freeze_inputs(configured(runtime_run[1], tmp_path), runtime_run[0], text='完整旁白。')
    cap_path = write_json(tmp_path/'cap.json', capability())
    source = write_json(tmp_path/'settings.json', dict(reference_generation=None,
        reference_capabilities={'jimeng_t2i_v40': str(cap_path)}, reference_storage=storage_settings()))
    with RunLock(runtime_run[0]) as held:
        store = _Records(runtime_run[0], held)
        bind_reference_settings(frozen, store=store, reference_settings_path=source)
        changed = json.loads(source.read_text(encoding='utf-8')); changed['reference_storage']['bucket'] = 'other-bucket'
        write_json(source, changed)
        with pytest.raises(ValueError): bind_reference_settings(frozen, store=store, reference_settings_path=source)
    target = runtime_run[0]/'production/reference-images/capability.json'
    target.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError): load_reference_settings(frozen)


def test_unused_reference_model_cannot_smuggle_credentials(runtime_run, tmp_path):
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.reference_settings import bind_reference_settings
    from video_ai.runtime.jimeng_candidates import _Records
    frozen = freeze_inputs(configured(runtime_run[1], tmp_path), runtime_run[0], text='完整旁白。')
    cap_path = write_json(tmp_path/'cap.json', capability())
    fallback = dict(image_settings(), secret_key='SYNTHETIC_REVIEW_SECRET')
    source = write_json(tmp_path/'settings.json', dict(reference_generation=fallback,
        reference_capabilities={'jimeng_t2i_v40': str(cap_path)}, reference_storage=storage_settings()))
    with RunLock(runtime_run[0]) as held:
        with pytest.raises(ValueError):
            bind_reference_settings(frozen, store=_Records(runtime_run[0], held), reference_settings_path=source)
    assert not (runtime_run[0]/'production/reference-images/config-source.json').exists()


@pytest.mark.parametrize('field,value', [
    ('reference_generation', dict(image_settings(), secret_key='SYNTHETIC_REVIEW_SECRET')),
    ('reference_storage', storage_settings(secret_key='SYNTHETIC_REVIEW_SECRET')),
])
def test_live_reference_config_rejects_credential_fields_before_freezing(runtime_run, tmp_path, field, value):
    with pytest.raises(ValueError): configured(runtime_run[1], tmp_path, **{field: value})


def test_capability_validation_binds_same_bytes_that_are_copied(runtime_run, tmp_path, monkeypatch):
    import video_ai.runtime.production_inputs as inputs
    cap_path = write_json(tmp_path/'cap.json', capability())
    config = configured(runtime_run[1], tmp_path, reference_capabilities={'jimeng_t2i_v40': str(cap_path)})
    original_copy = inputs._copy_small
    def change_before_copy(source, destination, **kwargs):
        if Path(source) == cap_path:
            write_json(cap_path, dict(capability(), secret_key='SYNTHETIC_REVIEW_SECRET'))
        return original_copy(source, destination, **kwargs)
    from pathlib import Path
    monkeypatch.setattr(inputs, '_copy_small', change_before_copy)
    with pytest.raises(ValueError): inputs.freeze_inputs(config, runtime_run[0], text='完整旁白。')
    assert not (runtime_run[0]/'production/reference-capabilities/jimeng_t2i_v40.json').exists()
