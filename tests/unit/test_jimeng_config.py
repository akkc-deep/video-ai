import json

import pytest

from video_ai.config import load_config, ConfigError
from video_ai.runtime.manifest import thaw


def image_settings(**changes):
    return dict(provider='volcengine_jimeng', req_key='jimeng_t2i_v40',
                access_key_env='TEST_VOLC_AK', secret_key_env='TEST_VOLC_SK',
                model_parameters=dict(width=2560, height=1440, force_single=True), **changes)


def configured(config, tmp_path, **changes):
    data = thaw(config.raw)
    data['voice_config'] = str(config.voice.config_file)
    data['workflows'] = thaw(config.workflows)
    data.update(production_strategy='paragraph_jimeng_v1', image_generation=image_settings())
    data.update(changes)
    path = tmp_path/'jimeng.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return load_config(path)


def test_defaults_preserve_legacy_and_explicit_strategy_loads(runtime_run, tmp_path):
    old = runtime_run[1]
    assert old.production_strategy == 'legacy'
    assert old.image_generation is None
    new = configured(old, tmp_path)
    assert new.image_generation.req_key == 'jimeng_t2i_v40'
    assert new.image_generation.candidates_per_scene == 2
    assert new.image_generation.output_width == 2560


@pytest.mark.parametrize('field', ['req_key', 'prompt', 'task_id', 'image_urls', 'binary_data_base64',
                                 'Authorization', 'secret_key', 'access_key', 'req_json',
                                 'api_key', 'access_key_id', 'Host', 'X-Date', 'Action', 'Version'])
def test_parameters_cannot_override_managed_fields(runtime_run, tmp_path, field):
    value = image_settings()
    value['model_parameters'][field] = 'forbidden'
    with pytest.raises(ConfigError):
        configured(runtime_run[1], tmp_path, image_generation=value)


@pytest.mark.parametrize('change', [dict(width=1280, height=721), dict(width=True), dict(height=0),
                                  dict(width=2560, height=1440, nested={'token': 'secret'}),
                                  dict(width=2560, height=1440, nested='https://host/image?sig=secret')])
def test_invalid_dimensions_and_nested_secrets_refused(runtime_run, tmp_path, change):
    value = image_settings()
    value['model_parameters'].update(change)
    with pytest.raises(ConfigError):
        configured(runtime_run[1], tmp_path, image_generation=value)


def test_unknown_model_explicit_parameters_are_preserved(runtime_run, tmp_path):
    value = image_settings()
    value.update(req_key='future_model', model_parameters={'size': 123, 'custom': ['a', 1]},
                 output_width=1600, output_height=900)
    loaded = configured(runtime_run[1], tmp_path, image_generation=value)
    assert thaw(loaded.image_generation.model_parameters) == {'size': 123, 'custom': ['a', 1]}


def test_model_override_uses_own_preset_and_unknown_requires_explicit_config(runtime_run, tmp_path):
    from video_ai.jimeng_config import override_image_model
    value = configured(runtime_run[1], tmp_path)
    changed = override_image_model(value.image_generation, 'jimeng_t2i_v31')
    assert changed.req_key == 'jimeng_t2i_v31'
    assert 'force_single' not in changed.model_parameters
    assert value.image_generation.req_key == 'jimeng_t2i_v40'
    with pytest.raises(ConfigError, match='explicit'):
        override_image_model(value.image_generation, 'future_model')
