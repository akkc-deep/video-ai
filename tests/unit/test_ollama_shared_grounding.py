"""Missing semantic values must never be supplied by the shared-prefix codec."""
from copy import deepcopy
import json
import re

import pytest

from unit.test_ollama import client_for
from video_ai.adapters.ollama import ollama_schema, ollama_content, OllamaFormatError
from video_ai.planning.storyboard import _anchored_string, _schema_check

FIELDS=('composition','action_start','action_end','image_prompt','video_prompt')
CAMERAS=['static camera','slow forward dolly','slow backward dolly','slow left pan',
         'slow right pan','slow upward tilt','slow downward tilt']


def shot_schema(subject='TEST ONLY craft',shot_id='shot_0001'):
    facts=dict(subject=subject,action_or_state=None,setting=None,quantity=None,negation=None,relation_or_order=None)
    props=dict(shot_id=dict(type='string',const=shot_id),camera_motion=dict(type='string',enum=CAMERAS),
        visual_expression=_anchored_string(facts),source_quote=dict(type='string',const='TEST ONLY original quote'))
    props.update({field:_anchored_string(facts,video=field=='video_prompt') for field in FIELDS})
    return dict(type='object',properties=props,required=list(props),additionalProperties=False)


def emitted(prefix='TEST ONLY craft. ',camera='static camera',shot_id='shot_0001'):
    return dict(shot_id=shot_id,camera_motion=camera,source_quote='TEST ONLY original quote',
        visual_expression=prefix+'The craft stays visible.',_grounded_visual=dict(fact_prefix=prefix,presentations=dict(
            composition='The craft occupies the center.',action_start='The craft begins at the left.',
            action_end='The craft continues toward the right.',image_prompt='A clear view of the craft.',
            video_prompt='The craft advances steadily.')))


def test_shared_wire_emits_one_prefix_and_preserves_unfactored_requirement():
    schema=shot_schema();before=deepcopy(schema);wire=ollama_schema(schema)
    assert set(wire['properties'])=={'shot_id','camera_motion','source_quote','visual_expression','_grounded_visual'}
    group=wire['properties']['_grounded_visual']
    assert group['properties']['fact_prefix']==dict(type='string',const='TEST ONLY craft. ')
    assert set(group['properties']['presentations']['properties'])==set(FIELDS)
    assert set(wire['required'])==set(wire['properties'])
    assert re.fullmatch(wire['properties']['visual_expression']['pattern'],'TEST ONLY craft. The craft stays visible.')
    assert not re.fullmatch(wire['properties']['visual_expression']['pattern'],'The craft stays visible.')
    assert schema==before


@pytest.mark.parametrize('camera',CAMERAS)
def test_restores_every_emitted_value_and_camera_without_mutation(camera):
    schema=shot_schema();value=emitted(camera=camera);before=deepcopy(value)
    result=ollama_content(value,schema)
    assert result==dict(shot_id='shot_0001',camera_motion=camera,source_quote='TEST ONLY original quote',
        visual_expression='TEST ONLY craft. The craft stays visible.',
        composition='TEST ONLY craft. The craft occupies the center.',
        action_start='TEST ONLY craft. The craft begins at the left.',
        action_end='TEST ONLY craft. The craft continues toward the right.',
        image_prompt='TEST ONLY craft. A clear view of the craft.',
        video_prompt='TEST ONLY craft. The craft advances steadily. Camera path: '+camera+'.')
    _schema_check(result,schema)
    assert value==before


def test_long_escaped_prefix_and_description_whitespace_are_lossless():
    subject='TEST ONLY '+('long source '*40)+'银白 (probe) [x]+? "windows" C:\\bay\nsecond\tline'
    prefix=subject+'. ';schema=shot_schema(subject);value=emitted(prefix)
    value['_grounded_visual']['presentations']['image_prompt']='Visible "probe" at C:\\bay.\t银白  '
    result=ollama_content(value,schema)
    assert result['image_prompt']==prefix+'Visible "probe" at C:\\bay.\t银白  '
    assert result['video_prompt']==prefix+'The craft advances steadily. Camera path: static camera.'
    assert ollama_schema(schema)['properties']['_grounded_visual']['properties']['fact_prefix']['const']==prefix
    _schema_check(result,schema)


def test_canonical_newline_in_description_remains_rejected_without_trimming():
    value=emitted();value['_grounded_visual']['presentations']['image_prompt']='Visible craft.\nSecond line.'
    before=deepcopy(value)
    with pytest.raises(ValueError):ollama_content(value,shot_schema())
    assert value==before


@pytest.mark.parametrize('length',[1,160,161])
def test_video_wire_and_decoder_enforce_budget_outside_facts_and_camera(length):
    schema=shot_schema();wire=ollama_schema(schema)
    pattern=wire['properties']['_grounded_visual']['properties']['presentations']['properties']['video_prompt']['pattern']
    text='V'*length;value=emitted();value['_grounded_visual']['presentations']['video_prompt']=text
    assert bool(re.fullmatch(pattern,json.dumps(text)[1:-1]))==(length<=160)
    if length<=160:assert ollama_content(value,schema)['video_prompt']=='TEST ONLY craft. '+text+' Camera path: static camera.'
    else:
        with pytest.raises(ValueError):ollama_content(value,schema)


def test_video_json_escape_units_and_unbounded_nonvideo_presentation():
    schema=shot_schema();value=emitted()
    text='V'+('"\\\t银'*39)+'end'
    value['_grounded_visual']['presentations']['video_prompt']=text
    value['_grounded_visual']['presentations']['composition']='C'*2000
    result=ollama_content(value,schema)
    assert result['video_prompt']=='TEST ONLY craft. '+text+' Camera path: static camera.'
    assert result['composition']=='TEST ONLY craft. '+'C'*2000


def test_explicit_concise_budget_bounds_presentations_without_shortening_source_facts():
    prefix='TEST ONLY '+('original fact '*40)+'. '
    schema=shot_schema(prefix[:-2])
    for name in FIELDS:
        schema['properties'][name]['maxLength']=len(prefix)+160+(len(' Camera path: slow backward dolly.') if name=='video_prompt' else 0)
    value=emitted(prefix)
    wire=ollama_schema(schema)
    group=wire['properties'].get('_grounded_visual')
    assert group is not None, 'bounded fields must still share their complete source anchor'
    pattern=group['properties']['presentations']['properties']['composition']['pattern']
    assert not re.fullmatch(pattern,'Visible scene. '*30)
    assert re.fullmatch(pattern,json.dumps('Visible "probe" at C:\\bay. '+('银'*80),ensure_ascii=False)[1:-1])
    result=ollama_content(value,schema)
    assert result['image_prompt']==prefix+'A clear view of the craft.'
    value['_grounded_visual']['presentations']['composition']='Visible scene. '*30
    with pytest.raises(ValueError):ollama_content(value,schema)


def test_bounded_storyboard_reports_token_truncation_before_inner_json_error(runtime_run):
    schema=shot_schema()
    for name in FIELDS:
        schema['properties'][name]['maxLength']=240
    planner,_=client_for(runtime_run,dict(model='qwen3:8b',done=True,done_reason='length',eval_count=8192,response='{"unfinished": "'))
    with pytest.raises(OllamaFormatError,match='truncated.*8192'):
        planner.generate('TEST ONLY concise visual',schema=schema,request_id='initial')


@pytest.mark.parametrize('text',['Four tiles read OPEN OPEN OPEN OPEN.','An LED shows 2020202020202020.'])
def test_concise_visuals_allow_counted_labels_and_numeric_identifiers(text):
    from video_ai.adapters.ollama import parse_completed_response
    schema=shot_schema()
    for name in FIELDS:schema['properties'][name]['maxLength']=240
    value=emitted();value['_grounded_visual']['presentations']['composition']=text
    result=parse_completed_response(dict(model='qwen3:8b',done=True,response=json.dumps(value)),
        schema=schema,request_id='storyboard_batch_0001_initial',evidence_paths=[])
    assert result['composition']=='TEST ONLY craft. '+text


@pytest.mark.parametrize('fault',[
    'missing_group','old_full_shape','extra_shot','missing_id','wrong_id','missing_camera','wrong_camera','nonstring_camera',
    'missing_prefix','wrong_prefix','nonstring_prefix','extra_group','missing_presentations','extra_presentation',
    'missing_presentation','nonstring_description','empty_description','blank_description','space_first_description',
])
def test_refuses_missing_wrong_or_extra_model_values_before_reconstruction(fault):
    schema=shot_schema();value=emitted();group=value['_grounded_visual'];presentations=group['presentations']
    if fault=='missing_group':del value['_grounded_visual']
    elif fault=='old_full_shape':
        del value['_grounded_visual'];value.update({name:'TEST ONLY craft. Old complete description.' for name in FIELDS})
    elif fault=='extra_shot':value['unexpected']='extra'
    elif fault=='missing_id':del value['shot_id']
    elif fault=='wrong_id':value['shot_id']='shot_0002'
    elif fault=='missing_camera':del value['camera_motion']
    elif fault=='wrong_camera':value['camera_motion']='invalid orbit'
    elif fault=='nonstring_camera':value['camera_motion']=None
    elif fault=='missing_prefix':del group['fact_prefix']
    elif fault=='wrong_prefix':group['fact_prefix']='TEST ONLY wrong craft. '
    elif fault=='nonstring_prefix':group['fact_prefix']=None
    elif fault=='extra_group':group['unexpected']='extra'
    elif fault=='missing_presentations':del group['presentations']
    elif fault=='extra_presentation':presentations['unexpected']='extra'
    elif fault=='missing_presentation':del presentations['action_end']
    elif fault=='nonstring_description':presentations['action_end']=123
    elif fault=='empty_description':presentations['action_end']=''
    elif fault=='blank_description':presentations['action_end']=' \t\n'
    else:presentations['action_end']=' leading space'
    before=deepcopy(value)
    with pytest.raises(ValueError):ollama_content(value,schema)
    assert value==before


@pytest.mark.parametrize('change',[
    'optional','extra_required','collision','unequal_prefix','unknown_pattern','nonvideo_pattern','field_constraint',
    'field_const','field_enum','unknown_camera','camera_constraint','shot_union','object_const',
])
def test_unrecognized_or_unsupported_schema_retains_prior_representation(change):
    schema=shot_schema()
    if change=='optional':schema['required'].remove('source_quote')
    elif change=='extra_required':schema['required'].append('unknown')
    elif change=='collision':schema['properties']['_grounded_visual']=dict(type='string');schema['required'].append('_grounded_visual')
    elif change=='unequal_prefix':schema['properties']['image_prompt']=shot_schema('TEST ONLY another')['properties']['image_prompt']
    elif change=='unknown_pattern':schema['properties']['image_prompt']['pattern']='^.*$'
    elif change=='nonvideo_pattern':schema['properties']['video_prompt']=deepcopy(schema['properties']['composition'])
    elif change=='field_constraint':schema['properties']['composition']['maxLength']=99
    elif change=='field_const':schema['properties']['composition']['const']='TEST ONLY craft. Fixed'
    elif change=='field_enum':schema['properties']['composition']['enum']=['TEST ONLY craft. Fixed']
    elif change=='unknown_camera':schema['properties']['camera_motion']['enum']=['invalid orbit']
    elif change=='camera_constraint':schema['properties']['camera_motion']['maxLength']=99
    elif change=='shot_union':schema['anyOf']=[dict(type='object')]
    else:schema['const']={'pattern':'opaque literal'}
    wire=ollama_schema(schema)
    assert all(name in wire['properties'] for name in FIELDS)
    if change=='object_const':assert wire['const']=={'pattern':'opaque literal'}


def test_fixed_tuple_restores_two_different_prefixes_in_source_order():
    first=shot_schema();second=shot_schema('TEST ONLY star','shot_0002')
    schema=dict(type='array',prefixItems=[first,second],items=False,minItems=2,maxItems=2)
    wire=ollama_schema(schema)
    assert list(wire['properties'])==['shot_0001','shot_0002']
    value={'shot_0002':emitted('TEST ONLY star. ','slow left pan','shot_0002'),'shot_0001':emitted()}
    result=ollama_content(value,schema)
    assert [shot['shot_id'] for shot in result]==['shot_0001','shot_0002']
    assert result[0]['video_prompt']=='TEST ONLY craft. The craft advances steadily. Camera path: static camera.'
    assert result[1]['video_prompt']=='TEST ONLY star. The craft advances steadily. Camera path: slow left pan.'
    _schema_check(result,schema)


@pytest.mark.parametrize('request_id',['initial','correction'])
def test_generate_declares_scoped_protocol_preserves_base_and_raw_evidence(runtime_run,request_id):
    schema=shot_schema();model=emitted();base='TEST ONLY base requires all complete anchored strings and original schema.'
    planner,transport=client_for(runtime_run,dict(model='qwen3:8b',done=True,response=json.dumps(model)))
    result=planner.generate(base,schema=schema,request_id=request_id)
    body=json.loads(transport.calls[0][2]);note=body['prompt'][len(base):]
    assert body['prompt'].startswith(base) and note.startswith('\n\nStructured transport protocol:')
    assert 'ONLY for composition, action_start, action_end, image_prompt and video_prompt' in note
    assert 'Unfactored visual_expression must still contain its complete exact anchor' in note
    assert 'both initial and correction requests' in note
    assert body['options']==dict(temperature=0,num_predict=8192)
    assert body['model']=='qwen3:8b' and body['think'] is False and body['stream'] is False and body['keep_alive']==0
    assert result['composition']=='TEST ONLY craft. The craft occupies the center.'
    run=runtime_run[0]
    assert json.loads((run/f'logs/storyboard/{request_id}.wire-content.json').read_text(encoding='utf-8'))==model
    assert json.loads((run/f'logs/storyboard/{request_id}.content.json').read_text(encoding='utf-8'))==result
    assert len(transport.calls)==1


def test_missing_emitted_prefix_is_format_error_without_accepted_content(runtime_run):
    value=emitted();del value['_grounded_visual']['fact_prefix']
    planner,transport=client_for(runtime_run,dict(model='qwen3:8b',done=True,response=json.dumps(value)))
    with pytest.raises(OllamaFormatError):planner.generate('TEST ONLY',schema=shot_schema(),request_id='initial')
    assert len(transport.calls)==1
    assert not (runtime_run[0]/'logs/storyboard/initial.content.json').exists()


def test_unfactored_generate_has_no_protocol_note(runtime_run):
    planner,transport=client_for(runtime_run,dict(model='qwen3:8b',done=True,response='{}'))
    planner.generate('TEST ONLY unchanged base',schema=dict(type='object'),request_id='initial')
    assert json.loads(transport.calls[0][2])['prompt']=='TEST ONLY unchanged base'


@pytest.mark.parametrize('keyword',['anyOf','oneOf','allOf'])
def test_union_wrapper_retains_full_string_wire_restoration_and_no_note(runtime_run,keyword):
    schema={keyword:[shot_schema()]};wire=ollama_schema(schema)
    assert 'composition' in wire[keyword][0]['properties']
    assert '_grounded_visual' not in wire[keyword][0]['properties']
    value=dict(shot_id='shot_0001',camera_motion='static camera',source_quote='TEST ONLY original quote',
        visual_expression='TEST ONLY craft. A visible craft.',composition='TEST ONLY craft. Centered craft.',
        action_start='TEST ONLY craft. Craft at left.',action_end='TEST ONLY craft. Craft at right.',
        image_prompt='TEST ONLY craft. Clear craft.',video_prompt='TEST ONLY craft. Moving craft. Camera path: static camera.')
    assert ollama_content(value,schema)==value
    if keyword=='anyOf':_schema_check(value,schema)
    planner,transport=client_for(runtime_run,dict(model='qwen3:8b',done=True,response=json.dumps(value)))
    assert planner.generate('TEST ONLY union base',schema=schema,request_id='initial')==value
    assert json.loads(transport.calls[0][2])['prompt']=='TEST ONLY union base'


@pytest.mark.parametrize('keyword',['definitions','$defs','contains','not'])
def test_unvisited_schema_descendant_retains_prior_wire_and_no_note(runtime_run,keyword):
    descendant={'named':shot_schema()} if keyword in ('definitions','$defs') else shot_schema()
    schema=dict(type='object',properties={},required=[],additionalProperties=False)
    schema[keyword]=descendant;wire=ollama_schema(schema)
    projected=wire[keyword]['named'] if keyword in ('definitions','$defs') else wire[keyword]
    assert 'composition' in projected['properties'] and '_grounded_visual' not in projected['properties']
    assert ollama_content({},schema)=={}
    planner,transport=client_for(runtime_run,dict(model='qwen3:8b',done=True,response='{}'))
    planner.generate('TEST ONLY fallback base',schema=schema,request_id='initial')
    assert json.loads(transport.calls[0][2])['prompt']=='TEST ONLY fallback base'


@pytest.mark.parametrize('property_name',['const','enum'])
def test_literal_property_name_gets_grouped_restore_and_declared_note(runtime_run,property_name):
    schema=dict(type='object',properties={property_name:shot_schema()},required=[property_name],additionalProperties=False)
    value={property_name:emitted()};wire=ollama_schema(schema)
    assert '_grounded_visual' in wire['properties'][property_name]['properties']
    assert ollama_content(value,schema)[property_name]['composition']=='TEST ONLY craft. The craft occupies the center.'
    planner,transport=client_for(runtime_run,dict(model='qwen3:8b',done=True,response=json.dumps(value)))
    restored=planner.generate('TEST ONLY named-property base',schema=schema,request_id='initial')
    assert restored[property_name]['video_prompt']=='TEST ONLY craft. The craft advances steadily. Camera path: static camera.'
    prompt=json.loads(transport.calls[0][2])['prompt']
    assert prompt.startswith('TEST ONLY named-property base\n\nStructured transport protocol:')
    assert prompt.count('Structured transport protocol:')==1
