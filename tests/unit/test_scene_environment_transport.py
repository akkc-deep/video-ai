"""Scene-local environment evidence and explicit backward reuse are lossless."""
from copy import deepcopy

import pytest

from unit.test_production_scenes import scene_inputs
from video_ai.adapters.ollama import ollama_body
from video_ai.config import ScenePlanningSettings
from video_ai.planning.production_scenes import make_scene_schema
from video_ai.planning.storyboard import _schema_check
from video_ai.runtime.production_scene_plan import _prompt

TEXT = '湖面很静。\n\n白鸟停在石上。\n\n它望向远处。'


def environment_input():
    script, units, timeline = scene_inputs(TEXT, samples=[48000] * 3)
    settings = ScenePlanningSettings(target_scenes_per_paragraph=1)
    schema = make_scene_schema(script, units, timeline, settings)
    prompt = _prompt(script, units, timeline, settings)
    return prompt, schema, script, units, timeline


def environment_wire():
    group = dict(label='湖畔', environment='湖面与岸边石头', time='清晨', lighting='柔光',
                 spatial_relations=[], source_facts=[dict(name='environment', value='湖面', sources=['speech_0001'])],
                 creative_choices=[], change_sources=[])
    def scene(environment):
        return dict(summary='湖边白鸟', image_prompt='白鸟在湖边', motion_prompt='白鸟轻轻转头',
                    entity_ids=[], variant_ids=[], change_sources=[], _environment=environment)
    return dict(global_style=dict(description='自然摄影', source_facts=[], creative_choices=[]),
                entities=[], appearance_variants=[], scenes={
                    'scene_0001': scene({'new': group}),
                    'scene_0002': scene({'reuse': 'scene_0001'}),
                    'scene_0003': scene({'reuse': 'scene_0002'})})


def test_known_single_unit_paragraphs_bind_each_scene_slot():
    prompt, schema, *_ = environment_input()
    body = ollama_body(prompt, schema, scene_planning=True, model='qwen3:14b')
    scenes = body['format']['properties']['scenes']
    assert scenes['type'] == 'object'
    assert scenes['required'] == ['scene_0001', 'scene_0002', 'scene_0003']
    assert TEXT.replace('\n', '\\n') in body['prompt']
    _schema_check(environment_wire(), body['format'])


@pytest.mark.parametrize('change', ['future_source', 'forward_reuse', 'missing_scene'])
def test_wire_rejects_future_environment_or_incomplete_slots(change):
    prompt, schema, *_ = environment_input()
    body = ollama_body(prompt, schema, scene_planning=True)
    wire = environment_wire()
    if change == 'future_source':
        wire['scenes']['scene_0001']['_environment']['new']['source_facts'][0]['sources'] = ['speech_0003']
    elif change == 'forward_reuse':
        wire['scenes']['scene_0002']['_environment'] = {'reuse': 'scene_0003'}
    else:
        del wire['scenes']['scene_0002']
    with pytest.raises(ValueError):
        _schema_check(wire, body['format'])


def test_environment_reuse_and_source_ids_restore_exact_canonical_proposal():
    from video_ai.adapters.ollama_scenes import restore_scene_content
    from video_ai.planning.production_scenes import build_scene_plan
    prompt, schema, script, units, timeline = environment_input()
    wire = environment_wire()
    before = deepcopy(wire)
    restored = restore_scene_content(wire, prompt)
    assert wire == before
    assert [s['unit_ids'] for s in restored['scenes']] == [['speech_0001'], ['speech_0002'], ['speech_0003']]
    assert len(restored['scene_groups']) == 1
    assert len({s['scene_group_id'] for s in restored['scenes']}) == 1
    assert restored['scene_groups'][0]['source_facts'][0]['sources'] == [
        dict(unit_id='speech_0001', text_start=0, text_end=5, quote='湖面很静。')]
    bible, plan = build_scene_plan(script, units, timeline, restored, settings=ScenePlanningSettings(target_scenes_per_paragraph=1))
    assert plan['total_frames'] == timeline.total_frames
    assert len(bible['scene_groups']) == 1


def test_multiple_units_per_paragraph_keep_original_wire():
    script, units, timeline = scene_inputs('湖面很静。白鸟停在石上。', samples=[48000] * 2)
    settings = ScenePlanningSettings()
    schema = make_scene_schema(script, units, timeline, settings)
    body = ollama_body(_prompt(script, units, timeline, settings), schema, scene_planning=True)
    assert body['format']['properties']['scenes']['type'] == 'array'
    assert 'scene_groups' in body['format']['properties']
