import json

from production_helpers import model_server
from unit.test_production_storyboard import wire_value
from test_production_timing import timeline,estimate
from video_ai.planning.production_timing import build_automatic_slots
from video_ai.runtime.production_visual_storyboard import _visual_request
from video_ai.adapters.ollama import ollama_schema,parse_completed_response,_has_shared_grounding


def schema():
    t=timeline([6000],text='旅行者一号飞掠木星。')
    slots=build_automatic_slots(t,{'speech_0001':estimate(6000)}).slots
    facts={'speech_0001':dict(subject='旅行者一号',action_or_state='飞掠木星',setting=None,
        quantity=None,negation=None,relation_or_order=None,context_sources=[],resolved_references=[])}
    return _visual_request(None,slots,slots,slots,facts,None,[],concise=True,model_visual=True)


def test_new_transport_generates_only_english_scene_without_echoing_source_facts():
    original,prompt=schema();wire=ollama_schema(original)
    props=wire['properties']['shots']['properties']['shot_0001']['properties']
    assert '_grounded_visual' not in props and 'visual_requirements' not in props
    assert not _has_shared_grounding(original)
    assert 'original_source_catalog' in prompt
    assert '旅行者' not in json.dumps(props,ensure_ascii=False)
    value=wire_value(wire);shot=value['shots']['shot_0001']
    shot['image_prompt']='Voyager 1 passes above striped Jupiter, black space background.'
    shot['video_prompt']='Voyager 1 slowly coasts past striped Jupiter.'
    result=parse_completed_response(dict(model='qwen3:8b',done=True,response=json.dumps(value)),
        schema=original,request_id='storyboard_batch_0001_initial',evidence_paths=[])
    row=result['shots'][0]
    assert row['image_prompt'].startswith('旅行者一号; 飞掠木星. Voyager 1')
    assert row['visual_requirements'][0]['source_quote']=='旅行者一号飞掠木星。'
    assert row['video_prompt'].count('Camera path:')==1


def test_new_transport_rejects_missing_or_invented_shot():
    import pytest
    from video_ai.adapters.ollama import OllamaFormatError
    original,_=schema();value=wire_value(ollama_schema(original));value['shots']['shot_9999']=value['shots'].pop('shot_0001')
    with pytest.raises(OllamaFormatError):
        parse_completed_response(dict(model='qwen3:8b',done=True,response=json.dumps(value)),
            schema=original,request_id='storyboard_batch_0001_initial',evidence_paths=[])
