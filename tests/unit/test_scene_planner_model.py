"""A chosen scene model binds configuration, requests and durable responses."""
import json

import pytest

from http_helpers import Response, ScriptedTransport
from unit.test_jimeng_config import configured
from video_ai.config import ConfigError, load_config
from video_ai.runtime.manifest import thaw


@pytest.mark.parametrize('model', ['qwen3:8b', 'qwen3:14b'])
def test_scene_model_is_explicit_and_survives_frozen_raw(runtime_run, tmp_path, model):
    config = configured(runtime_run[1], tmp_path, scene_planner_model=model)
    assert config.raw['scene_planner_model'] == model
    assert load_config(config.config_file, raw=thaw(config.raw)).raw['scene_planner_model'] == model


@pytest.mark.parametrize('model', [None, '', 'qwen3:32b', 'qwen3:14b ', True, [], {}])
def test_unverified_or_null_scene_model_refused(runtime_run, tmp_path, model):
    with pytest.raises(ConfigError, match='scene_planner_model'):
        configured(runtime_run[1], tmp_path, scene_planner_model=model)


def test_scene_model_is_not_accepted_by_legacy_strategy(runtime_run):
    config = runtime_run[1]
    raw = thaw(config.raw)
    raw['scene_planner_model'] = 'qwen3:14b'
    with pytest.raises(ConfigError, match='scene_planner_model'):
        load_config(config.config_file, raw=raw)


def test_scene_body_uses_chosen_model_and_ordinary_requests_keep_8b():
    from video_ai.adapters.ollama import ollama_body
    ordinary = ollama_body('ordinary', {'type': 'object'})
    body = ollama_body('complete input', {'type': 'object'}, scene_planning=True, model='qwen3:14b')
    assert body['model'] == 'qwen3:14b' and body['think'] is True
    assert body['options'] == dict(temperature=0, num_predict=8192, num_ctx=32768)
    assert ordinary['model'] == 'qwen3:8b' and ordinary['think'] is False
    with pytest.raises(ValueError):
        ollama_body('ordinary', {'type': 'object'}, model='qwen3:14b')


@pytest.mark.parametrize('response_model', ['qwen3:8b', 'qwen3:14b'])
def test_durable_scene_response_requires_exact_expected_model(response_model):
    from video_ai.adapters.common import AdapterError
    from video_ai.adapters.ollama import parse_completed_response
    outer = dict(model=response_model, done=True, response='{"ok":true}')
    args = dict(schema={'type': 'object'}, request_id='scene_plan_initial', evidence_paths=[], expected_model='qwen3:14b')
    if response_model == 'qwen3:14b':
        assert parse_completed_response(outer, **args) == {'ok': True}
    else:
        with pytest.raises(AdapterError):
            parse_completed_response(outer, **args)


def test_scene_planner_sends_and_validates_model_without_extra_http(runtime_run):
    from video_ai.adapters.common import HttpClient
    from video_ai.adapters.ollama import OllamaPlanner
    from video_ai.runtime.logging import RunLogger
    transport = ScriptedTransport(lambda r, t: Response(dict(model='qwen3:14b', done=True, response='{}')))
    planner = OllamaPlanner(HttpClient('http://127.0.0.1:11435', 1, RunLogger(runtime_run[0]), transport=transport), model='qwen3:14b')
    assert planner.generate('input', schema={}, request_id='scene_plan_initial') == {}
    assert len(transport.calls) == 1
    assert json.loads(transport.calls[0][2])['model'] == 'qwen3:14b'
    with pytest.raises(ValueError):
        planner.generate('ordinary input', schema={}, request_id='initial')
    assert len(transport.calls) == 1
