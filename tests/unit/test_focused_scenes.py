from copy import deepcopy
import json

import pytest

from unit.test_production_scenes import scene_inputs
from video_ai.config import ScenePlanningSettings
from video_ai.planning.production_scenes import make_scene_schema
from unit.test_production_inputs import production_config


def test_explicit_source_bound_transport_is_a_valid_project_setting(production_config,tmp_path):
    from unit.test_jimeng_config import configured
    from video_ai.config import ConfigError
    config=configured(production_config,tmp_path,scene_planner_transport='focused_v1')
    assert config.raw['scene_planner_transport']=='focused_v1'
    with pytest.raises(ConfigError):configured(production_config,tmp_path,scene_planner_transport='unknown')


def inputs():
    script, units, timeline = scene_inputs('木星。\n土星。', samples=[48000, 48000])
    settings = ScenePlanningSettings(target_scenes_per_paragraph=3)
    schema = make_scene_schema(script, units, timeline, settings)
    return script, units, schema, settings


def wire_value(value):
    value=deepcopy(value)
    groups={g['key']:g for g in value.pop('scene_groups')}
    entities={e['key']:e for e in value.pop('entities')}
    variants={v['key']:v for v in value.pop('appearance_variants')}
    previous=None
    for index,(key,row) in enumerate(value['scenes'].items()):
        group_key=row.pop('scene_group_id')
        if group_key in groups:
            group=deepcopy(groups.pop(group_key));group.pop('key')
            row['environment']={'new':group}
        else:row['environment']={'reuse_previous':True} if index else {'reuse':'focus_environment_scene_0001'}
        ids=row.pop('entity_ids');vids=row.pop('variant_ids')
        if index and previous==(ids,vids):row['subjects']={'reuse_previous':True}
        else:
            row['subjects']=[]
            for eid in ids:
                if eid in entities:
                    entity=deepcopy(entities.pop(eid));entity.pop('key')
                    subject={'new':entity}
                else:subject={'reuse':'focus_subject_scene_0001_01'}
                appearance={'unchanged':True}
                if vids:
                    variant=deepcopy(variants[vids[0]]);variant.pop('key');variant.pop('entity_key')
                    appearance={'new':variant}
                subject['appearance']=appearance;row['subjects'].append(subject)
        previous=(ids,vids)
    return value


def test_focused_scenes_fix_sources_before_descriptions_and_show_literal_text():
    from video_ai.planning.focused_scenes import source_slices, focus_request
    script, units, schema, settings = inputs()
    slices = source_slices(script, settings)
    assert [r['unit_ids'] for r in slices] == [['speech_0001'], ['speech_0002']]
    assert [r['source_text'] for r in slices] == ['木星。', '土星。']
    prompt, wire = focus_request(script, units, schema, slices[:1], None)
    assert '木星。' in prompt
    row = wire['properties']['scenes']['properties']['scene_0001']
    assert next(iter(row['properties'])) == 'source_text'
    assert row['properties']['source_text'] == dict(type='string', const='木星。')
    assert set(wire['properties']['scenes']['properties']) == {'scene_0001'}
    assert 'speech_0002' not in json.dumps(wire)


def test_visual_schema_bounds_every_generated_string_and_array_without_truncating_source():
    from video_ai.planning.focused_scenes import source_slices,focus_request
    script,units,schema,settings=inputs()
    prompt,wire=focus_request(script,units,schema,source_slices(script,settings)[:1],None)
    def check(node):
        if not isinstance(node,dict):return
        if node.get('type')=='string' and 'const' not in node and 'enum' not in node:
            assert 0<node.get('maxLength',0)<=320
        if node.get('type')=='array':assert 0<node.get('maxItems',0)<=8
        for value in node.values():
            if isinstance(value,dict):
                check(value)
                for child in value.values():check(child)
            elif isinstance(value,list):
                for child in value:check(child)
    check(wire)
    image=wire['properties']['scenes']['properties']['scene_0001']['properties']['image_prompt']
    assert 'pattern' in image
    assert 'plain Chinese prose' in prompt


def test_visual_bounds_never_weaken_an_existing_limit():
    from video_ai.planning.focused_scenes import _bounded_visual_schema
    assert _bounded_visual_schema(dict(type='string',maxLength=5))['maxLength']==5
    assert _bounded_visual_schema(dict(type='array',items=dict(type='string'),maxItems=1))['maxItems']==1


def test_focused_visual_request_has_a_finite_backend_output_budget():
    from video_ai.adapters.ollama import ollama_body
    from video_ai.runtime.ollama_direct import completion_request
    body=ollama_body('small visual request',dict(type='object',properties={},required=[]),
        scene_planning=True,scene_local_repair=True,scene_output_limit=16384)
    assert body['options']['num_predict']==16384
    assert completion_request(body,[1,2,3])['n_predict']==16384


def test_focus_merge_preserves_binding_and_rejects_foreign_or_future_sources():
    from video_ai.planning.focused_scenes import source_slices, focus_request, merge_focus
    script, units, schema, settings = inputs()
    slices = source_slices(script, settings)
    _, wire = focus_request(script, units, schema, slices[:1], None)
    style = dict(description='写实科学纪录片', source_facts=[], creative_choices=[])
    group = dict(key='space',label='太空',environment='太空',time='白天',lighting='阳光',
                 spatial_relations=[],source_facts=[],creative_choices=[],change_sources=[])
    scene = dict(source_text='木星。',summary='木星',image_prompt='木星云带',motion_prompt='云带缓慢移动',
                 entity_ids=[],variant_ids=[],scene_group_id='space',change_sources=[])
    value = dict(global_style=style,entities=[],appearance_variants=[],scene_groups=[group],scenes={'scene_0001':scene})
    merged = merge_focus(None, wire_value(value), slices[:1], wire, script, units)
    assert merged['scenes'][0]['unit_ids'] == ['speech_0001']
    assert merged['scenes'][0]['paragraph_id'] == 'paragraph_0001'
    assert 'source_text' not in merged['scenes'][0]
    bad = deepcopy(value);bad['scenes']['scene_0001']['source_text']='土星。'
    with pytest.raises(ValueError): merge_focus(None,wire_value(bad),slices[:1],wire,script,units)
    bad=deepcopy(value);bad['scene_groups'][0]['change_sources']=['speech_0002']
    with pytest.raises(ValueError): merge_focus(None,wire_value(bad),slices[:1],wire,script,units)
    _, wire2=focus_request(script,units,schema,slices[1:],merged)
    second=dict(global_style=style,entities=[],appearance_variants=[],scene_groups=[],scenes={
        'scene_0002':dict(scene,source_text='土星。',summary='土星',image_prompt='土星光环')})
    updated=merge_focus(merged,wire_value(second),slices[1:],wire2,script,units)
    assert [r['summary'] for r in updated['scenes']]==['木星','土星']
    assert len(updated['scene_groups'])==1
    changed=deepcopy(second);changed['global_style']['description']='changed'
    with pytest.raises(ValueError,match='const'):
        merge_focus(merged,wire_value(changed),slices[1:],wire2,script,units)


def test_balanced_slices_keep_every_original_unit_and_paragraph_boundary():
    from video_ai.planning.focused_scenes import source_slices
    script,_,_=scene_inputs('一。二。三。四。\n五。',samples=[48000]*5)
    slices=source_slices(script,ScenePlanningSettings(target_scenes_per_paragraph=3),
        {'paragraph_0001':['speech_0001','speech_0002','speech_0004'],'paragraph_0002':['speech_0005']})
    assert len(slices)==4
    assert [uid for s in slices for uid in s['unit_ids']]==[f'speech_{i:04d}' for i in range(1,6)]
    assert slices[-1]['source_text']=='五。'


def test_boundaries_allow_one_two_or_three_scenes_before_visual_generation():
    from video_ai.planning.focused_scenes import partition_request
    from video_ai.planning.production_scenes import paragraphs_from_script
    script,_,_=scene_inputs('一。二。三。',samples=[48000]*3)
    prompt,wire=partition_request(script,ScenePlanningSettings(),paragraphs_from_script(script))
    choices=wire['properties']['paragraph_0001']['properties']['end_units']['enum']
    assert ['speech_0003'] in choices
    assert ['speech_0001','speech_0003'] in choices
    assert ['speech_0001','speech_0002','speech_0003'] in choices
    assert '一。' in prompt and '二。' in prompt and '三。' in prompt


def test_appearance_change_is_rejected_in_the_current_batch():
    from video_ai.planning.focused_scenes import source_slices,focus_request,merge_focus
    script,units,schema,settings=inputs()
    slices=source_slices(script,settings)
    style=dict(description='纪录片',source_facts=[],creative_choices=[])
    entity=dict(key='probe',label='探测器',fixed_attributes=[],source_facts=[],creative_choices=[])
    def variant(key):
        return dict(key=key,entity_key='probe',attributes=[key],source_facts=[],creative_choices=[],change_sources=[])
    group=dict(key='space',label='太空',environment='太空',time='白天',lighting='阳光',
               spatial_relations=[],source_facts=[],creative_choices=[],change_sources=[])
    def scene(text,key):
        return dict(source_text=text,summary=text,image_prompt=text,motion_prompt='漂浮',
                    entity_ids=['probe'],variant_ids=[key],scene_group_id='space',change_sources=[])
    _,wire=focus_request(script,units,schema,slices[:1],None)
    first=dict(global_style=style,entities=[entity],appearance_variants=[variant('a')],scene_groups=[group],
               scenes={'scene_0001':scene('木星。','a')})
    prior=merge_focus(None,wire_value(first),slices[:1],wire,script,units)
    _,wire2=focus_request(script,units,schema,slices[1:],prior)
    second=dict(global_style=style,entities=[],appearance_variants=[variant('b')],scene_groups=[],
                scenes={'scene_0002':scene('土星。','b')})
    with pytest.raises(ValueError,match='appearance change'):
        merge_focus(prior,wire_value(second),slices[1:],wire2,script,units)
    second['scenes']['scene_0002']['change_sources']=['speech_0002']
    assert merge_focus(prior,wire_value(second),slices[1:],wire2,script,units)['scenes'][-1]['variant_ids']==['focus_variant_scene_0002_01']
