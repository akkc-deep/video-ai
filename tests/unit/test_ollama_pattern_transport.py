"""Keep generated JSON safe without weakening the canonical grounded contract."""
from copy import deepcopy
import json
import re

import pytest

from unit.test_ollama import client_for
from unit.test_storyboard_contract import setup_contract, grounded_model


def grounded_wire(storyboard_run):
    from video_ai.planning.storyboard import primary_model_slots, make_model_schema
    slots,specs,model,data,path = setup_contract(storyboard_run)
    slots = primary_model_slots(slots)
    uid = slots[0].primary_unit_id
    specs[uid]['subject'] = 'TEST ONLY a literal (probe) [x]+? with "windows"'
    for shot in model['shots']:
        for requirement in shot['visual_requirements']:
            if requirement['unit_id'] == uid:
                requirement['subject'] = specs[uid]['subject']
    model = grounded_model(model,slots,specs)
    schema = make_model_schema(slots,semantic_specs=specs,depiction_policy='grounded_prompts_v1')
    wire = deepcopy(model)
    wire['shots'] = {shot['shot_id']:dict(shot,visual_requirements={r['unit_id']:r for r in shot['visual_requirements']}) for shot in wire['shots']}
    from video_ai.planning.storyboard import depiction_anchor
    for slot in slots:
        shot=wire['shots'][slot.shot_id];prefix=depiction_anchor(specs[slot.primary_unit_id]);presentations={}
        for name in ('composition','action_start','action_end','image_prompt','video_prompt'):
            text=shot.pop(name);assert text.startswith(prefix)
            if name=='video_prompt':
                suffix=' Camera path: '+shot['camera_motion']+'.';assert text.endswith(suffix);text=text[:-len(suffix)]
            presentations[name]=text[len(prefix):]
        shot['_grounded_visual']=dict(fact_prefix=prefix,presentations=presentations)
    return slots,specs,model,schema,wire


def string_patterns(schema):
    if isinstance(schema,list):
        return [p for value in schema for p in string_patterns(value)]
    if not isinstance(schema,dict):return []
    found = [schema['pattern']] if schema.get('type')=='string' and 'pattern' in schema else []
    return found+[p for key,value in schema.items() if key not in ('const','enum') for p in string_patterns(value)]


def test_actual_http_transport_uses_json_strings_and_retains_canonical_constraints(storyboard_run):
    from video_ai.planning.storyboard import validate_model_content
    slots,specs,model,schema,wire = grounded_wire(storyboard_run)
    before = deepcopy(schema)
    planner,transport = client_for(storyboard_run,dict(model='qwen3:8b',done=True,response=json.dumps(wire,ensure_ascii=False)))
    normalized = planner.generate('TEST ONLY grounded source contract',schema=schema,request_id='initial')
    body = json.loads(transport.calls[0][2])
    assert string_patterns(schema) and schema == before
    patterns=string_patterns(body['format'])
    assert len(patterns)==len(string_patterns(schema))
    first=body['format']['properties']['shots']['properties'][slots[0].shot_id]['properties']
    group=first['_grounded_visual']['properties']
    assert group['fact_prefix']['const']==wire['shots'][slots[0].shot_id]['_grounded_visual']['fact_prefix']
    for field in ('composition','action_start','action_end','image_prompt','video_prompt'):
        payload=json.dumps(wire['shots'][slots[0].shot_id]['_grounded_visual']['presentations'][field],ensure_ascii=False)[1:-1]
        assert re.fullmatch(group['presentations']['properties'][field]['pattern'],payload)
        assert not re.fullmatch(group['presentations']['properties'][field]['pattern'],'Invalid " unescaped payload')
    assert normalized == model
    validate_model_content(normalized,slots,semantic_specs=specs,depiction_policy='grounded_prompts_v1')
    bad = deepcopy(normalized)
    bad['shots'][0]['image_prompt'] = 'Unrelated scene omitting the required source'
    with pytest.raises(ValueError):validate_model_content(bad,slots,semantic_specs=specs,depiction_policy='grounded_prompts_v1')
    assert len(transport.calls)==1


@pytest.mark.parametrize('bad',['anchor','camera','frozen_fact'])
def test_payload_wire_cannot_bypass_full_grounded_validation_or_correction_budget(storyboard_run,bad):
    from video_ai.adapters.ollama import OllamaFormatError
    from video_ai.runtime.storyboard_checks import _request_content
    from video_ai.runtime.logging import RunLogger
    slots,specs,model,schema,wire = grounded_wire(storyboard_run)
    first = wire['shots'][slots[0].shot_id]
    if bad=='anchor':first['_grounded_visual']['fact_prefix']='Unrelated source. '
    elif bad=='camera':first['camera_motion']='invalid orbit'
    else:first['visual_requirements'][slots[0].primary_unit_id]['subject']='Wrong source subject'
    planner,transport = client_for(storyboard_run,dict(model='qwen3:8b',done=True,response=json.dumps(wire,ensure_ascii=False)))
    with pytest.raises(OllamaFormatError):
        _request_content(planner,slots,RunLogger(storyboard_run[0]),semantic_specs=specs,depiction_policy='grounded_prompts_v1')
    assert len(transport.calls)==2
    assert all(string_patterns(json.loads(call[2])['format']) for call in transport.calls)
    assert not (storyboard_run[0]/'logs/storyboard/primary-content.json').exists()


@pytest.mark.parametrize('property_name',['pattern','const','enum'])
def test_pattern_transport_preserves_literal_data_and_property_names(property_name):
    from video_ai.adapters.ollama import ollama_schema
    literal = dict(type='string',pattern='THIS IS SOURCE DATA')
    schema = dict(type='object',properties={property_name:dict(type='string',pattern='^.*$',const=literal)})
    original = deepcopy(schema)
    transported = ollama_schema(schema)
    assert property_name in transported['properties']
    assert transported['properties'][property_name]['const'] == literal
    assert 'pattern' not in transported['properties'][property_name]
    assert schema == original


def test_observed_concat_fragment_remains_a_strict_format_error(storyboard_run):
    from video_ai.adapters.ollama import OllamaFormatError
    # A small TEST ONLY reproduction of the actual initial invalid JSON syntax.
    body = '{"composition":"TEST ONLY source anchor. " + "Camera path: static camera."}'
    planner,transport = client_for(storyboard_run,dict(model='qwen3:8b',done=True,done_reason='length',response=body))
    with pytest.raises(OllamaFormatError):planner.generate('TEST ONLY observed failure',schema={'type':'object'},request_id='initial')
    assert len(transport.calls)==1
