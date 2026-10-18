"""Fixed baselines retain every use and determine stable dependency batches."""
from copy import deepcopy
import pytest


def graph():
    bible=dict(entities=[dict(entity_id='entity_0001')],appearance_variants=[dict(variant_id='variant_0001',entity_id='entity_0001')],scene_groups=[dict(group_id='group_0001')],baselines=[dict(kind='entity',id='entity_0001',scene_id='scene_0001'),dict(kind='appearance_variant',id='variant_0001',scene_id='scene_0001'),dict(kind='scene_group',id='group_0001',scene_id='scene_0001')])
    uses=[dict(kind='entity',id='entity_0001'),dict(kind='appearance_variant',id='variant_0001'),dict(kind='scene_group',id='group_0001')]
    scenes=[dict(scene_id=f'scene_{i:04d}',entity_ids=['entity_0001'],variant_ids=['variant_0001'],scene_group_id='group_0001',reference_bindings=[] if i==1 else [dict(source_scene_id='scene_0001',uses=deepcopy(uses))],dependencies=[] if i==1 else ['scene_0001']) for i in range(1,4)]
    return scenes,bible


def test_merged_image_uses_and_parallel_zero_indegree_batches():
    from video_ai.planning.visual_consistency import validate_reference_graph
    scenes,bible=graph()
    assert validate_reference_graph(scenes,bible)==[['scene_0001'],['scene_0002','scene_0003']]


@pytest.mark.parametrize('change',['self','cycle','unknown','wrong_baseline','omitted_entity','omitted_group','neighbor','duplicate_use','missing_dependency','unused','wrong_owner','extra_binding'])
def test_graph_rejects_forged_fixed_reference_contract(change):
    from video_ai.planning.visual_consistency import validate_reference_graph
    scenes,bible=graph()
    if change=='self': scenes[1]['reference_bindings'][0]['source_scene_id']='scene_0002'
    elif change=='cycle': scenes[0]['dependencies']=['scene_0003'];scenes[2]['dependencies']=['scene_0001']
    elif change=='unknown': scenes[1]['dependencies']=['unknown']
    elif change=='wrong_baseline': bible['baselines'][0]['scene_id']='scene_0002'
    elif change=='omitted_entity': scenes[1]['reference_bindings'][0]['uses'].pop(0)
    elif change=='omitted_group': scenes[1]['reference_bindings'][0]['uses'].pop()
    elif change=='neighbor': scenes[2]['reference_bindings'][0]['source_scene_id']='scene_0002';scenes[2]['dependencies']=['scene_0002']
    elif change=='duplicate_use': scenes[1]['reference_bindings'][0]['uses'].append(dict(kind='entity',id='entity_0001'))
    elif change=='missing_dependency': scenes[1]['dependencies']=[]
    elif change=='unused': bible['entities'].append(dict(entity_id='entity_0002'))
    elif change=='wrong_owner': bible['appearance_variants'][0]['entity_id']='entity_0002'
    else: scenes[1]['reference_bindings'][0]['passed']=True
    with pytest.raises(ValueError): validate_reference_graph(scenes,bible)
