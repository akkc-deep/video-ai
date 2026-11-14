"""Lossless paragraph-local scene boundaries; original unit IDs are program-owned."""
from copy import deepcopy
import json
from itertools import combinations

MARKER = 'video_ai_scene_partition_v3'


def source(prompt):
    value, _ = json.JSONDecoder().raw_decode(prompt.split('\nSCENE_INPUT_JSON\n', 1)[1])
    return value


def project(prompt, schema, *, exact_sources=True, exact_boundaries=True):
    exact_boundaries=exact_boundaries and exact_sources
    data = source(prompt)
    maximum = data['settings']['target_scenes_per_paragraph']
    paragraphs = [p for p in data['paragraphs'] if p['unit_ids']]
    catalog={s['unit_id']:s for s in data['finalized_units']['spans'] if s['kind']=='speech'}
    def citations(node):
        if isinstance(node,list):return [citations(v) for v in node]
        if not isinstance(node,dict):return node
        if node.get('type')=='object' and set(node.get('properties',{}))=={'unit_id','text_start','text_end','quote'}:
            if exact_sources:return dict(type='string',enum=list(catalog))
            return dict(type='string',pattern='^speech_[0-9]{4,}$',maxLength=max(map(len,catalog)))
        return {key:citations(value) for key,value in node.items()}
    wire = citations(schema)
    slots = {}
    for paragraph in paragraphs:
        ids = paragraph['unit_ids']
        variants = []
        for count in range(1, min(maximum, len(ids)) + 1):
            cuts=combinations(range(1,len(ids)),count-1) if exact_boundaries else [None]
            for cut in cuts:
                ends=(*cut,len(ids)) if cut is not None else None
                properties = {}
                for index in range(count):
                    scene = deepcopy(wire['properties']['scenes']['items'])
                    for key in ('paragraph_id', 'unit_ids'):
                        scene['properties'].pop(key)
                        scene['required'].remove(key)
                    end=(dict(type='string',const=ids[ends[index]-1]) if ends is not None else
                         dict(type='string', const=ids[-1]) if index == count - 1 else dict(type='string', enum=ids[:-1]))
                    scene['properties']['end_unit'] = end
                    scene['required'].append('end_unit')
                    properties[f'scene_{index + 1:04d}'] = scene
                variants.append(dict(type='object', properties=properties, required=list(properties), additionalProperties=False))
        slots[paragraph['paragraph_id']] = dict(anyOf=variants)
    wire['properties']['scenes'] = dict(type='object', properties=slots, required=list(slots), additionalProperties=False)
    wire['$comment'] = MARKER if exact_boundaries else 'video_ai_scene_partition_v2' if exact_sources else 'video_ai_scene_partition_v1'
    note = ('\nSCENE_PARTITION_TRANSPORT\nFor each required paragraph emit between one and the configured maximum scenes. '
            'end_unit is the LAST original speech unit of that scene. End boundaries must increase in source order; '
            'the final boundary is fixed to the paragraph last unit. The decoder restores every original unit exactly once. '
            'Source citations in sources/change_sources are original speech unit IDs; the decoder restores their exact ranges and quotes. '
            'Do not repeat source text or unit lists. Preserve all original meaning and use concise visual descriptions.\n')
    return prompt + note, wire


def restore(content, prompt):
    data = source(prompt)
    paragraphs = [p for p in data['paragraphs'] if p['unit_ids']]
    slots = content['scenes']
    if not isinstance(slots, dict) or set(slots) != {p['paragraph_id'] for p in paragraphs}:
        raise ValueError('scene partition lacks exact paragraphs')
    result = deepcopy(content)
    scenes = []
    for paragraph in paragraphs:
        rows = slots[paragraph['paragraph_id']]
        ids = paragraph['unit_ids']
        if not isinstance(rows, dict) or not 1 <= len(rows) <= min(data['settings']['target_scenes_per_paragraph'], len(ids)):
            raise ValueError('scene partition count differs')
        keys = [f'scene_{i + 1:04d}' for i in range(len(rows))]
        if set(rows) != set(keys):
            raise ValueError('scene partition lacks ordered slots')
        start = 0
        for key in keys:
            scene = deepcopy(rows[key])
            end_id = scene.pop('end_unit')
            if end_id not in ids:
                raise ValueError('scene partition has foreign boundary')
            end = ids.index(end_id) + 1
            if end <= start:
                raise ValueError('scene partition boundaries must increase')
            scene.update(paragraph_id=paragraph['paragraph_id'], unit_ids=ids[start:end])
            scenes.append(scene)
            start = end
        if start != len(ids):
            raise ValueError('scene partition must cover paragraph tail')
    result['scenes'] = scenes
    catalog={s['unit_id']:dict(unit_id=s['unit_id'],text_start=s['start'],text_end=s['end'],quote=s['text'])
             for s in data['finalized_units']['spans'] if s['kind']=='speech'}
    def expand(node):
        if isinstance(node,list):return [expand(value) for value in node]
        if not isinstance(node,dict):return node
        output={}
        for key,value in node.items():
            if key in ('sources','change_sources'):
                if not isinstance(value,list) or any(not isinstance(uid,str) or uid not in catalog for uid in value):
                    raise ValueError('scene partition has unknown source')
                output[key]=[deepcopy(catalog[uid]) for uid in value]
            else:output[key]=expand(value)
        return output
    return expand(result)
