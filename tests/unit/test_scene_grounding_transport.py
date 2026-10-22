"""Scene wire grammar must reject invented source offsets before generation."""
import pytest

from unit.test_production_scenes import scene_inputs
from video_ai.adapters.ollama import ollama_body
from video_ai.config import ScenePlanningSettings
from video_ai.planning.production_scenes import make_scene_schema
from video_ai.planning.storyboard import _schema_check
from video_ai.runtime.production_scene_plan import _prompt


def source_schema():
    script, units, timeline = scene_inputs('白鹭在湖边。\n它张开翅膀。', samples=[48000, 48000])
    settings = ScenePlanningSettings()
    schema = make_scene_schema(script, units, timeline, settings)
    body = ollama_body(_prompt(script, units, timeline, settings), schema, scene_planning=True, scene_environment_constraints=False)
    source = body['format']['properties']['entities']['items']['properties']['source_facts']['items']['properties']['sources']['items']
    return body, source


@pytest.mark.parametrize('change', [
    {'unit_id': 'speech_0002'}, {'text_start': 1}, {'text_end': 5}, {'quote': '白鹭在湖边'},
])
def test_scene_wire_rejects_invented_or_mismatched_original_references(change):
    _, schema = source_schema()
    reference = dict(unit_id='speech_0001', text_start=0, text_end=6, quote='白鹭在湖边。')
    _schema_check(reference, schema)
    reference.update(change)
    with pytest.raises(ValueError):
        _schema_check(reference, schema)


def test_scene_wire_keeps_later_original_units_available_and_full_input_intact():
    body, schema = source_schema()
    _schema_check(dict(unit_id='speech_0002', text_start=7, text_end=13, quote='它张开翅膀。'), schema)
    assert '白鹭在湖边。\\n它张开翅膀。' in body['prompt']
    assert body['options']['num_ctx'] == 32768


def test_scene_planning_uses_reasoning_with_the_same_bounded_output_budget():
    body, _ = source_schema()
    assert body['think'] is True
    assert body['options']['num_predict'] == 8192
    assert body['options']['num_ctx'] == 32768
    assert ollama_body('unchanged ordinary request', {'type': 'object'})['think'] is False


@pytest.mark.parametrize('location', ['entity_key', 'group_key', 'entity_reference', 'group_reference'])
def test_scene_wire_identifiers_reject_explanatory_text(location):
    body, _ = source_schema()
    properties = body['format']['properties']
    schema = {
        'entity_key': properties['entities']['items']['properties']['key'],
        'group_key': properties['scene_groups']['items']['properties']['key'],
        'entity_reference': properties['scenes']['items']['properties']['entity_ids']['items'],
        'group_reference': properties['scenes']['items']['properties']['scene_group_id'],
    }[location]
    _schema_check('entity_0001', schema)
    with pytest.raises(ValueError):
        _schema_check('entity_00意图: ', schema)


def test_three_scene_citations_fit_budget_without_dropping_original_evidence():
    text = ('清晨的湖岸泛着柔和的金光一只白鹭沿着芦苇旁的浅水缓缓向前行走。\n\n'
            '微风中的白鹭正轻轻展开一双映着晨光的洁白翅膀。\n\n'
            '随后这只白鹭振翅掠过平静的湖面飞向远处被晨光照亮的树林。\n')
    script, units, timeline = scene_inputs(text, samples=[48000, 48000, 48000])
    units['planner'] = {'original_evidence': 'x' * 3000}
    settings = ScenePlanningSettings()
    schema = make_scene_schema(script, units, timeline, settings)
    body = ollama_body(_prompt(script, units, timeline, settings), schema, scene_planning=True)
    assert 'x' * 3000 in body['prompt']
    assert '清晨的湖岸泛着柔和的金光' in body['prompt']
    assert '飞向远处被晨光照亮的树林。' in body['prompt']

