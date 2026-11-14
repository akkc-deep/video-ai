from copy import deepcopy

import pytest

from video_ai.planning.production_scenes import coalesce_unchanged_environments


def proposal():
    group=dict(environment='deep space',time='night',lighting='stars',spatial_relations=[],
               creative_choices=[],source_facts=[],change_sources=[])
    return dict(scene_groups=[dict(deepcopy(group),key='a'),dict(deepcopy(group),key='b')],
                scenes=[dict(scene_group_id=key,change_sources=[]) for key in ('a','b','unknown')])


@pytest.mark.parametrize('field,value',[
    ('environment','Earth'),('time','day'),('lighting','sunlight'),
    ('spatial_relations',['beside Earth']),('creative_choices',[dict(name='haze',value='blue',reason='mood')]),
])
def test_distinct_physical_or_creative_states_keep_unknown_reference_invalid(field,value):
    original=proposal();original['scene_groups'][1][field]=value
    normalized,aliases=coalesce_unchanged_environments(original)
    assert normalized==original and aliases==[]


def test_unique_environment_aliases_preserve_scene_descriptions_and_original_records():
    original=proposal();before=deepcopy(original)
    for scene in original['scenes']:scene['image_prompt']='original scene description'
    normalized,aliases=coalesce_unchanged_environments(original)
    assert [s['scene_group_id'] for s in normalized['scenes']]==['a','a','unknown']
    assert len(aliases)==1
    assert all(s['image_prompt']=='original scene description' for s in normalized['scenes'])
    assert [s['scene_group_id'] for s in original['scenes']]==[s['scene_group_id'] for s in before['scenes']]


def test_explicit_change_evidence_prevents_unknown_alias_resolution():
    original=proposal();original['scenes'][-1]['change_sources']=['explicit change']
    normalized,_=coalesce_unchanged_environments(original)
    assert normalized['scenes'][-1]['scene_group_id']=='unknown'
