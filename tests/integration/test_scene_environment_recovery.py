"""Real HTTP recovery of the scene-local transport preserves canonical records."""
from copy import deepcopy

import pytest

from integration.test_scene_planning import produce, scene_setup
from unit.test_production_inputs import production_config
from unit.test_scene_environment_transport import TEXT, environment_wire

pytestmark = pytest.mark.parametrize('scene_setup', [dict(model='qwen3:14b', text=TEXT)], indirect=True)


def test_environment_wire_commits_canonical_source_and_replays_without_http(scene_setup):
    s = scene_setup
    s['replies'].append(environment_wire())
    bible, plan = produce(s)
    assert len(plan['scenes']) == 3 and len(bible['scene_groups']) == 1
    assert [row['unit_ids'] for row in plan['scenes']] == [['speech_0001'], ['speech_0002'], ['speech_0003']]
    assert len({row['scene_group_id'] for row in plan['scenes']}) == 1
    assert s['received'][0]['model'] == 'qwen3:14b'
    assert s['received'][0]['format']['properties']['scenes']['type'] == 'object'
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in s['run'].rglob('*') if p.is_file()}
    assert produce(s) == (bible, plan)
    assert len(s['received']) == 1
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == value for p, value in before.items())


@pytest.mark.parametrize('valid_correction', [False, True])
def test_future_environment_citation_is_never_restored_as_accepted(scene_setup, valid_correction):
    s = scene_setup
    bad = environment_wire()
    bad['scenes']['scene_0001']['_environment']['new']['source_facts'][0]['sources'] = ['speech_0003']
    s['replies'].extend([bad, environment_wire() if valid_correction else deepcopy(bad)])
    if valid_correction:
        bible, _ = produce(s)
        assert bible['scene_groups'][0]['source_facts'][0]['sources'][0]['unit_id'] == 'speech_0001'
    else:
        with pytest.raises(ValueError):
            produce(s)
        with pytest.raises(ValueError):
            produce(s)
        assert not (s['run'] / 'production/scene-plan-commit.json').exists()
    assert len(s['received']) == 2


def test_scene_environment_saved_response_recovers_without_http(scene_setup, monkeypatch):
    import video_ai.runtime.production_scene_plan as module
    s = scene_setup
    s['replies'].append(environment_wire())
    def interrupt(where):
        if where == 'response':
            raise KeyboardInterrupt()
    with monkeypatch.context() as patch:
        patch.setattr(module, 'boundary', interrupt)
        with pytest.raises(KeyboardInterrupt):
            produce(s)
    intent = s['run'] / 'production/scene-planning/initial.intent.json'
    original = intent.read_bytes()
    assert len(produce(s)[1]['scenes']) == 3
    assert intent.read_bytes() == original
    assert len(s['received']) == 1


@pytest.mark.parametrize('point', ['completed', 'response'])
def test_eligible_old_array_wire_keeps_original_http_and_intent(scene_setup, monkeypatch, point):
    import video_ai.adapters.ollama as adapter
    import video_ai.runtime.production_scene_plan as module
    from video_ai.adapters.ollama_scenes import restore_scene_content
    from video_ai.config import parse_scene_planning
    s = scene_setup
    settings = parse_scene_planning(s['frozen'].config.raw.get('scene_planning'))
    prompt = module._prompt(s['frozen'].script, s['units'], s['timeline'], settings)
    s['replies'].append(restore_scene_content(environment_wire(), prompt))
    original_body = adapter.ollama_body
    def old_body(*args, **kwargs):
        return original_body(*args, **dict(kwargs, scene_environment_constraints=False))
    def interrupt(where):
        if where == 'response':
            raise KeyboardInterrupt()
    with monkeypatch.context() as patch:
        patch.setattr(adapter, 'ollama_body', old_body)
        patch.setattr(module, 'ollama_body', old_body)
        if point == 'response':
            patch.setattr(module, 'boundary', interrupt)
            with pytest.raises(KeyboardInterrupt):
                produce(s)
        else:
            produce(s)
    before = {p: p.read_bytes() for p in s['run'].rglob('*') if p.is_file()}
    assert len(produce(s)[1]['scenes']) == 3
    assert len(s['received']) == 1
    assert s['received'][0]['format']['properties']['scenes']['type'] == 'array'
    assert all(p.read_bytes() == value for p, value in before.items())
