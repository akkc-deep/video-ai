from dataclasses import FrozenInstanceError, fields
from types import MappingProxyType

import pytest

from video_ai import config
from video_ai.runtime.manifest import thaw


def test_scene_settings_defaults_are_immutable_and_parse_frozen_raw():
    settings = config.parse_scene_planning(None)
    assert settings == config.ScenePlanningSettings(3, 6)
    with pytest.raises(FrozenInstanceError):
        settings.max_clip_seconds = 10
    raw = MappingProxyType({'target_scenes_per_paragraph': 2, 'max_clip_seconds': .3125})
    assert config.parse_scene_planning(raw) == config.ScenePlanningSettings(2, .3125)
    assert config.parse_scene_planning({}) == settings


@pytest.mark.parametrize('value', [True, 0, -1, 2.0, '2', None])
def test_scene_target_requires_positive_nonbool_integer(value):
    with pytest.raises(config.ConfigError, match='target_scenes_per_paragraph'):
        config.ScenePlanningSettings(target_scenes_per_paragraph=value)


@pytest.mark.parametrize('value', [True, 0, -1, .312499999999, '6', None,
                                  float('nan'), float('inf'), 10**1000, 1e308])
def test_scene_duration_requires_finite_positive_five_frame_budget(value):
    with pytest.raises(config.ConfigError, match='max_clip_seconds'):
        config.ScenePlanningSettings(max_clip_seconds=value)


@pytest.mark.parametrize('value', [[], True, 3, {'extra': 1}, {'max_clip_seconds': None}])
def test_scene_parser_rejects_invalid_structure(value):
    with pytest.raises(config.ConfigError, match='scene_planning'):
        config.parse_scene_planning(value)


def test_new_strategy_freezes_explicit_scene_settings_without_dataclass_field(runtime_run, tmp_path):
    from test_jimeng_config import configured
    old = runtime_run[1]
    new = configured(old, tmp_path, scene_planning={'target_scenes_per_paragraph': 2, 'max_clip_seconds': 4})
    assert config.parse_scene_planning(new.raw['scene_planning']) == config.ScenePlanningSettings(2, 4)
    assert 'scene_planning' not in {f.name for f in fields(new)}
    with pytest.raises(TypeError):
        new.raw['scene_planning']['max_clip_seconds'] = 6
    assert 'scene_planning' not in thaw(old.raw)


@pytest.mark.parametrize('settings', [{}, None])
def test_legacy_rejects_scene_planning_root_field(runtime_run, settings):
    old = runtime_run[1]
    raw = thaw(old.raw)
    raw['scene_planning'] = settings
    with pytest.raises(config.ConfigError, match='scene_planning.*paragraph_jimeng_v1'):
        config.load_config(old.config_file, raw=raw, voice=old.voice)


def test_new_strategy_validates_scene_settings_with_config_location(runtime_run, tmp_path):
    from test_jimeng_config import configured
    with pytest.raises(config.ConfigError, match=r'jimeng.json: scene_planning.*max_clip_seconds'):
        configured(runtime_run[1], tmp_path, scene_planning={'max_clip_seconds': .1})
