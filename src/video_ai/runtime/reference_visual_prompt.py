"""Deterministic visual fields; complete citation evidence stays in the Bible."""
import json


def _literal(value):
    if not any(c in './=[]"\\\x85\u2028\u2029' or ord(c) < 32 for c in value):
        return value
    return (json.dumps(value, ensure_ascii=False).replace('\x85', '\\u0085')
            .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))


def compact_reference_prompt(scene, bible):
    """Keep every visual string and owner; factor only exactly equal values."""
    values = {}
    def add(label, value):
        values.setdefault(value, []).append(label)
    def grounded(label, row):
        for fact in row['source_facts']:
            add(label+'.F.'+_literal(fact['name']), fact['value'])
        for choice in row['creative_choices']:
            add(label+'.C.'+_literal(choice['name']), choice['value'])
            add(label+'.C.'+_literal(choice['name'])+'.R', choice['reason'])
    add('风格', bible['global_style']['description'])
    grounded('全局', bible['global_style'])
    for index, row in enumerate(bible['entities'], 1):
        if row['entity_id'] not in scene['entity_ids']:
            continue
        label = f'E{index}'
        add(label+'['+row['entity_id']+']', row['label'])
        for value in row['fixed_attributes']:
            add(label+'.固定', value)
        grounded(label, row)
    for index, row in enumerate(bible['appearance_variants'], 1):
        if row['variant_id'] not in scene['variant_ids']:
            continue
        label = f'V{index}'
        add(label+'['+row['variant_id']+'].主体', row['entity_id'])
        for value in row['attributes']:
            add(label+'.属性', value)
        grounded(label, row)
    for index, row in enumerate(bible['scene_groups'], 1):
        if row['group_id'] != scene['scene_group_id']:
            continue
        label = f'G{index}'
        add(label+'['+row['group_id']+'].环境名', row['label'])
        for field, name in (('environment', '环境'), ('time', '时间'), ('lighting', '光线')):
            add(label+'.'+name, row[field])
        for value in row['spatial_relations']:
            add(label+'.空间', value)
        grounded(label, row)
    return scene['image_prompt']+'\nVISUAL_FACTS_V1\n'+'\n'.join(
        '/'.join(labels)+'='+_literal(value) for value, labels in values.items())
