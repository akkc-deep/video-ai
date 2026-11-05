"""Lossless scene-local environment transport for fixed one-unit paragraphs."""
from copy import deepcopy
import json

MARKER = 'video_ai_scene_environment_v1'
GROUPED_MARKER = 'video_ai_scene_environment_v2'
SOURCE_SET_MARKER = 'video_ai_scene_environment_v3'


def compact_scene_prompt(prompt):
    """Send all source meaning once; keep file/audit identities in local intents."""
    marker='\nSCENE_INPUT_JSON\n'
    prefix,raw=prompt.split(marker,1)
    value,end=json.JSONDecoder().raw_decode(raw)
    units=value['finalized_units'];timeline=value['narration_timeline']
    clips={row['unit_id']:row for row in timeline['clips']}
    rows=[]
    for span in units['spans']:
        if span['kind']!='speech':continue
        uid=span['unit_id'];clip=clips[uid]
        if span['text']!=value['decoded_text'][span['start']:span['end']]:
            raise ValueError('compact scene source differs')
        facts={key:item for key,item in units['semantic_specs'][uid]['facts'].items()
               if item not in (None,[])}
        rows.append([uid,span['start'],span['end'],clip['start_sample'],clip['end_sample'],facts])
    payload=dict(decoded_text=value['decoded_text'],settings=value['settings'],
        paragraphs=[[row['paragraph_id'],row['text_start'],row['text_end'],row['unit_ids']]
                    for row in value['paragraphs'] if row['unit_ids']],
        unit_columns=['unit_id','text_start','text_end','start_sample','end_sample','facts'],units=rows,
        sample_rate=timeline['sample_rate'],total_samples=timeline['total_samples'])
    note=('\nCompact source transport: the ENTIRE original text is decoded_text. Paragraph rows are '
          '[paragraph_id,text_start,text_end,unit_ids]. Unit rows follow unit_columns; exact text '
          'and source quotes are decoded_text[text_start:text_end], using Python Unicode offsets. '
          'Omitted fact fields are null or empty. File paths, duplicate text and audit receipts stay '
          'in the original local reports and are not visual facts. Cover every paragraph/unit in '
          'order. Keep descriptions concise, one physical subject/setting/action per scene.\n')
    return prefix+note+'\nSCENE_COMPACT_INPUT_JSON\n'+json.dumps(payload,ensure_ascii=False,separators=(',',':'))+raw[end:]


def _input(prompt, *, grouped=False):
    marker = '\nSCENE_INPUT_JSON\n'
    if marker not in prompt:
        return None
    value, _ = json.JSONDecoder().raw_decode(prompt.split(marker, 1)[1])
    catalog = {}
    for row in value['finalized_units']['spans']:
        if row['kind'] != 'speech':
            continue
        start, end = row['start'], row['end']
        if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(value['decoded_text'])
                or row['text'] != value['decoded_text'][start:end] or row['unit_id'] in catalog):
            raise ValueError('scene transport source catalog differs')
        catalog[row['unit_id']] = dict(unit_id=row['unit_id'], text_start=start, text_end=end, quote=row['text'])
    paragraphs = [row for row in value['paragraphs'] if row['unit_ids']]
    if (not paragraphs or not grouped and any(len(row['unit_ids']) != 1 for row in paragraphs)
            or [uid for row in paragraphs for uid in row['unit_ids']] != list(catalog)):
        return None
    return paragraphs, catalog


def is_environment_transport(body):
    return body.get('format', {}).get('$comment') in (MARKER,GROUPED_MARKER,SOURCE_SET_MARKER)


def project_scene_environment(prompt, schema, *, grouped=False,source_sets=False,source_nonempty=True):
    source = _input(prompt,grouped=grouped)
    if source is None:
        return prompt, schema
    paragraphs, catalog = source
    props = schema.get('properties', {})
    if set(props) != {'global_style', 'entities', 'appearance_variants', 'scene_groups', 'scenes'}:
        return prompt, schema
    if (props['scenes'].get('type') != 'array'
            or props['scenes'].get('minItems') != len(paragraphs)
            or props['scenes'].get('maxItems') != len(paragraphs)):
        return prompt, schema

    fields = {'unit_id', 'text_start', 'text_end', 'quote'}
    def source_set(eligible, *, nonempty=False):
        rest=dict(type='object',properties={uid:dict(type='boolean',const=True) for uid in eligible},
                  required=[],additionalProperties=False)
        if not nonempty:return rest
        return dict(type='object',properties=dict(first=dict(type='string',enum=eligible),more=rest),
                    required=['first','more'],additionalProperties=False)
    def citations(node, eligible):
        if isinstance(node, list):
            return [citations(item, eligible) for item in node]
        if not isinstance(node, dict):
            return node
        if (source_sets and node.get('type')=='array'
                and set(node.get('items',{}).get('properties',{}))==fields):
            return source_set(eligible,nonempty=source_nonempty and node.get('minItems',0)>0)
        if node.get('type') == 'object' and set(node.get('properties', {})) == fields:
            return dict(type='string', enum=eligible)
        return {key: citations(value, eligible) for key, value in node.items()}
    wire = citations(schema, list(catalog))
    group_schema = deepcopy(props['scene_groups']['items'])
    del group_schema['properties']['key']
    group_schema['required'].remove('key')
    slots = {}
    for index, paragraph in enumerate(paragraphs, 1):
        slot = f'scene_{index:04d}'
        latest = catalog[paragraph['unit_ids'][-1]]['text_end']
        eligible = [key for key, row in catalog.items() if row['text_end'] <= latest]
        scene = citations(props['scenes']['items'], eligible)
        for key in ('paragraph_id', 'unit_ids', 'scene_group_id'):
            del scene['properties'][key]
            scene['required'].remove(key)
        group = citations(group_schema, eligible)
        if index > 1:
            if source_sets and source_nonempty:group['properties']['change_sources']=source_set(eligible,nonempty=True)
            else:group['properties']['change_sources']['minItems'] = 1
        define = dict(type='object', properties={'new': group}, required=['new'], additionalProperties=False)
        if slots:
            reuse = dict(type='object', properties={'reuse': dict(type='string', enum=list(slots))},
                         required=['reuse'], additionalProperties=False)
            environment = dict(anyOf=[reuse, define])
        else:
            environment = define
        scene['properties']['_environment'] = environment
        scene['required'].append('_environment')
        slots[slot] = scene
    del wire['properties']['scene_groups']
    wire['required'].remove('scene_groups')
    wire['properties']['scenes'] = dict(type='object', properties=slots, required=list(slots), additionalProperties=False)
    wire['$comment'] = SOURCE_SET_MARKER if source_sets else GROUPED_MARKER if grouped else MARKER
    note = ('\nSCENE_ENVIRONMENT_TRANSPORT\nEmit scenes as the required keyed slots. The decoder restores '
            'paragraph_id and unit_ids from their frozen one-unit paragraphs. Source citations are unit_id '
            'strings, expanded to exact original ranges/quotes by the decoder. For _environment, define '
            'a persistent physical setting with new, or reuse a previous scene slot. Different actions at '
            'the same place/time reuse the same environment; action sequences belong in scene prompts. '
            'Environment fields are readable descriptions. Only actual environment changes define a new '
            'group with current/prior change_sources. Never reference a future scene or source.\n')
    if grouped:note=note.replace('frozen one-unit paragraphs','frozen complete paragraph memberships')
    if source_sets:
        explanation=('Optional source citations are true-valued unit_id keyed objects (for example {"speech_0001":true}). '
            'Required nonempty citations use {"first":"speech_0001","more":{}} with optional extra unit keys in more,'
            if source_nonempty else 'Source citations are true-valued unit_id keyed objects (for example {"speech_0001":true}),')
        note=note.replace('Source citations are unit_id strings,',explanation)
    return prompt + note, wire


def restore_scene_content(content, prompt):
    source = _input(prompt,grouped=True)
    if source is None:
        raise ValueError('scene environment transport lacks fixed paragraph source')
    paragraphs, catalog = source
    slots = content['scenes']
    expected = [f'scene_{i:04d}' for i in range(1, len(paragraphs) + 1)]
    if not isinstance(slots, dict) or set(slots) != set(expected):
        raise ValueError('scene environment transport lacks exact slots')
    groups = []; scenes = []; assigned = {}
    for slot, paragraph in zip(expected, paragraphs):
        scene = deepcopy(slots[slot])
        environment = scene.pop('_environment')
        if set(environment) == {'new'}:
            key = 'group_for_' + slot
            groups.append(dict(deepcopy(environment['new']), key=key))
        elif set(environment) == {'reuse'} and environment['reuse'] in assigned:
            key = assigned[environment['reuse']]
        else:
            raise ValueError('scene environment transport has invalid or future reuse')
        assigned[slot] = key
        scene.update(paragraph_id=paragraph['paragraph_id'], unit_ids=list(paragraph['unit_ids']), scene_group_id=key)
        scenes.append(scene)
    result = deepcopy(content)
    result.update(scenes=scenes, scene_groups=groups)
    def expand(node):
        if isinstance(node, list):
            return [expand(item) for item in node]
        if not isinstance(node, dict):
            return node
        out = {}
        for key, value in node.items():
            if key in ('sources', 'change_sources'):
                if isinstance(value,dict):
                    if set(value)=={'first','more'}:
                        first,more=value['first'],value['more']
                        if type(first) is not str or first not in catalog or not isinstance(more,dict):
                            raise ValueError('scene environment transport has invalid first source')
                        if any(uid not in catalog or selected is not True for uid,selected in more.items()):
                            raise ValueError('scene environment transport has invalid extra sources')
                        value={**more,first:True}
                    if any(uid not in catalog or selected is not True for uid,selected in value.items()):
                        raise ValueError('scene environment transport has invalid source set')
                    value=[uid for uid in catalog if uid in value]
                if not isinstance(value, list) or any(type(uid) is not str or uid not in catalog for uid in value):
                    raise ValueError('scene environment transport has unknown source')
                out[key] = [deepcopy(catalog[uid]) for uid in value]
            else:
                out[key] = expand(value)
        return out
    return expand(result)
