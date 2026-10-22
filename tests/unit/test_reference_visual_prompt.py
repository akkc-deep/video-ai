"""Visual fields keep their complete strings and explicit owner in compact form."""
from copy import deepcopy


def test_all_visual_fields_and_same_value_owners_survive_exact_factoring():
    from video_ai.runtime.reference_visual_prompt import compact_reference_prompt
    bible = dict(
        global_style=dict(description='水墨', source_facts=[], creative_choices=[dict(name='风格选择', value='留白', reason='突出主体')]),
        entities=[
            dict(entity_id='entity_a', label='阿甲', fixed_attributes=['蓝发'],
                 source_facts=[dict(name='发色', value='蓝发', sources=[dict(quote='完整来源只留原证据')])], creative_choices=[]),
            dict(entity_id='entity_b', label='阿乙', fixed_attributes=['橙发'], source_facts=[], creative_choices=[]),
            dict(entity_id='unrelated', label='未引用主体', fixed_attributes=[], source_facts=[], creative_choices=[])],
        appearance_variants=[dict(variant_id='variant_a', entity_id='entity_a', attributes=['红衣'], source_facts=[], creative_choices=[])],
        scene_groups=[dict(group_id='group_a', label='湖边', environment='浅水', time='清晨', lighting='柔光',
                          spatial_relations=['芦苇在右'], source_facts=[dict(name='水域', value='浅水', sources=[])], creative_choices=[])])
    scene = dict(image_prompt='两人相望', entity_ids=['entity_a', 'entity_b'], variant_ids=['variant_a'], scene_group_id='group_a')
    before = deepcopy(bible)
    prompt = compact_reference_prompt(scene, bible)
    assert prompt.startswith('两人相望\nVISUAL_FACTS_V1\n风格=水墨\n')
    for line in ('全局.C.风格选择=留白', '全局.C.风格选择.R=突出主体',
                 'E1[entity_a]=阿甲', 'E1.固定/E1.F.发色=蓝发', 'E2[entity_b]=阿乙', 'E2.固定=橙发',
                 'V1[variant_a].主体=entity_a', 'V1.属性=红衣', 'G1[group_a].环境名=湖边',
                 'G1.环境/G1.F.水域=浅水', 'G1.时间=清晨', 'G1.光线=柔光', 'G1.空间=芦苇在右'):
        assert line in prompt.splitlines()
    assert '未引用主体' not in prompt and '完整来源只留原证据' not in prompt
    assert bible == before


def test_facts_and_creative_proposals_have_distinct_types():
    from video_ai.runtime.reference_visual_prompt import compact_reference_prompt
    from unit.test_production_scenes import build
    bible, plan = build()
    scene = plan['scenes'][0]
    facts = deepcopy(bible)
    facts['global_style']['source_facts'] = [dict(name='颜色', value='红', sources=[]), dict(name='颜色.理由', value='美观', sources=[])]
    choices = deepcopy(bible)
    choices['global_style']['creative_choices'] = [dict(name='颜色', value='红', reason='美观')]
    assert compact_reference_prompt(scene, facts) != compact_reference_prompt(scene, choices)


def test_literal_delimiters_cannot_create_another_owners_visual_field():
    from video_ai.runtime.reference_visual_prompt import compact_reference_prompt
    from unit.test_production_scenes import build
    bible, plan = build()
    bible['entities'][0]['source_facts'] = [dict(name='色/名=值', value='红\nE2.固定=蓝', sources=[])]
    prompt = compact_reference_prompt(plan['scenes'][0], bible)
    assert 'E2.固定=蓝' not in prompt.splitlines()
    assert '"色/名=值"="红\\nE2.固定=蓝"' in prompt
