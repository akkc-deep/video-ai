"""Small visual requests whose source slices are fixed before generation."""
from copy import deepcopy
import json
from itertools import combinations

from .production_scenes import paragraphs_from_script, _grounding, _nonempty_strings
from .segments import TextSpan
from .storyboard import _schema_check
from .focused_subjects import subject_schema,restore_subjects


CATALOGS = ('entities', 'appearance_variants', 'scene_groups')


def _bounded_visual_schema(node, field=''):
    if not isinstance(node,dict):return deepcopy(node)
    result=deepcopy(node)
    if result.get('type')=='string' and 'const' not in result and 'enum' not in result:
        ceiling={'image_prompt':280,'motion_prompt':100,'summary':100,
            'key':64,'label':80,'name':64,'time':40,'lighting':80}.get(field,160)
        result['maxLength']=min(result.get('maxLength',ceiling),ceiling)
        if field=='image_prompt':result['pattern']=r'^[^{}\r\n]+$'
    if result.get('type')=='array':
        ceiling={'entities':4,'appearance_variants':3,'source_facts':3,
            'creative_choices':2,'sources':2,'change_sources':3}.get(field,6)
        result['maxItems']=min(result.get('maxItems',ceiling),ceiling)
    if 'properties' in result:
        result['properties']={key:_bounded_visual_schema(value,key) for key,value in result['properties'].items()}
    if 'items' in result:result['items']=_bounded_visual_schema(result['items'],field)
    for key in ('anyOf','oneOf','allOf'):
        if key in result:result[key]=[_bounded_visual_schema(value,field) for value in result[key]]
    return result


def partition_request(script, settings, paragraphs):
    catalog={s.unit_id:s for s in script.spans if s.kind=='speech'}
    slots={}
    targets=[]
    for paragraph in paragraphs:
        ids=paragraph['unit_ids']
        choices=[]
        for count in range(1,min(settings.target_scenes_per_paragraph,len(ids))+1):
            for cuts in combinations(range(1,len(ids)),count-1):
                choices.append([ids[end-1] for end in (*cuts,len(ids))])
        text=script.text[paragraph['text_start']:paragraph['text_end']]
        slots[paragraph['paragraph_id']]=dict(type='object',properties=dict(
            source_text=dict(type='string',const=text),
            end_units=dict(type='array',items=dict(type='string',enum=ids),enum=choices)),
            required=['source_text','end_units'],additionalProperties=False)
        targets.append(dict(paragraph_id=paragraph['paragraph_id'],source_text=text,
            units=[dict(unit_id=uid,text=catalog[uid].text) for uid in ids]))
    schema=dict(type='object',properties=slots,required=list(slots),additionalProperties=False)
    prompt=('Choose ONLY contiguous scene boundaries for the supplied paragraphs. Do not generate visual '
        'descriptions or a story summary. Keep related narration together; split at an actual change of '
        'visible subject, setting or action. Use 1 to the configured maximum scenes per paragraph, not '
        'automatically the maximum. end_units lists the last original unit of each scene in increasing '
        'order, ending with the paragraph final unit. Copy source_text first.\n'
        +json.dumps(dict(full_original_text=script.text,target=settings.target_scenes_per_paragraph,
                         paragraphs=targets),ensure_ascii=False,separators=(',',':')))
    return prompt,schema


def source_slices(script, settings, partitions=None):
    catalog = {s.unit_id: s for s in script.spans if s.kind == 'speech'}
    result = []
    for paragraph in paragraphs_from_script(script):
        ids = paragraph['unit_ids']
        if not ids: continue
        ends=partitions[paragraph['paragraph_id']] if partitions is not None else [ids[-1]]
        if not 1<=len(ends)<=min(settings.target_scenes_per_paragraph,len(ids)):
            raise ValueError('focused partition scene count differs')
        start=0
        for end_id in ends:
            if end_id not in ids:raise ValueError('focused partition foreign source')
            end=ids.index(end_id)+1
            if end<=start:raise ValueError('focused partition boundaries must increase')
            selected=ids[start:end]
            result.append(dict(scene_key=f'scene_{len(result)+1:04d}',
                paragraph_id=paragraph['paragraph_id'], unit_ids=selected,
                source_text=script.text[catalog[selected[0]].start:catalog[selected[-1]].end]))
            start=end
        if start!=len(ids):raise ValueError('focused partition lacks paragraph tail')
    return result


def focus_request(script, units, schema, slices, prior):
    catalog = {s['unit_id']: s for s in units['spans'] if s['kind'] == 'speech'}
    latest = catalog[slices[-1]['unit_ids'][-1]]['end']
    eligible = [uid for uid, row in catalog.items() if row['end'] <= latest]

    def citations(value):
        if isinstance(value, list): return [citations(v) for v in value]
        if not isinstance(value, dict): return value
        if value.get('type') == 'object' and set(value.get('properties', {})) == {'unit_id','text_start','text_end','quote'}:
            return dict(type='string', enum=eligible)
        return {key: citations(v) for key, v in value.items()}

    wire = citations(deepcopy(schema))
    for category in CATALOGS:
        wire['properties'][category]['minItems'] = 0
    if prior is not None:
        def source_ids(value):
            if isinstance(value,list): return [source_ids(v) for v in value]
            if not isinstance(value,dict): return value
            return {key:[row['unit_id'] for row in item] if key in ('sources','change_sources')
                    else source_ids(item) for key,item in value.items()}
        wire['properties']['global_style']['const'] = source_ids(prior['global_style'])
    template = wire['properties']['scenes']['items']
    group_template=wire['properties'].pop('scene_groups')['items']
    wire['required'].remove('scene_groups')
    entity_template=wire['properties'].pop('entities')['items'];wire['required'].remove('entities')
    variant_template=wire['properties'].pop('appearance_variants')['items'];wire['required'].remove('appearance_variants')
    slots = {}
    for index,source in enumerate(slices):
        fields = {k: deepcopy(v) for k, v in template['properties'].items()
                  if k not in ('paragraph_id', 'unit_ids','scene_group_id','entity_ids','variant_ids')}
        new_group=deepcopy(group_template)
        new_group['properties'].pop('key');new_group['required'].remove('key')
        allowed=[uid for uid,row in catalog.items() if row['end']<=catalog[source['unit_ids'][-1]]['end']]
        def restrict(value):
            if isinstance(value,list):return [restrict(v) for v in value]
            if not isinstance(value,dict):return value
            if value.get('type')=='string' and value.get('enum')==eligible:return dict(value,enum=allowed)
            return {key:restrict(v) for key,v in value.items()}
        new_group=restrict(new_group)
        alternatives=[]
        if prior and prior['scene_groups']:
            alternatives.append(dict(type='object',properties=dict(reuse=dict(type='string',
                enum=[g['key'] for g in prior['scene_groups']])),required=['reuse'],additionalProperties=False))
        if index or prior and prior['scenes']:
            alternatives.append(dict(type='object',properties=dict(reuse_previous=dict(type='boolean',const=True)),
                required=['reuse_previous'],additionalProperties=False))
        alternatives.append(dict(type='object',properties=dict(new=new_group),required=['new'],additionalProperties=False))
        fields['environment']=dict(anyOf=alternatives)
        fields['subjects']=subject_schema(restrict(entity_template),restrict(variant_template),prior,
            previous_possible=bool(index or prior and prior['scenes']))
        fields = dict(source_text=dict(type='string', const=source['source_text']), **fields)
        slots[source['scene_key']] = dict(type='object', properties=fields,
            required=list(fields), additionalProperties=False)
    wire['properties']['scenes'] = dict(type='object', properties=slots,
        required=list(slots), additionalProperties=False)
    wire=_bounded_visual_schema(wire)
    context = dict(full_original_text=script.text, fixed_scenes=slices,
        scene_semantics={source['scene_key']:[dict(unit_id=uid,
            facts=deepcopy(units['semantic_specs'][uid].get('facts',{}))) for uid in source['unit_ids']] for source in slices},
        source_units=[dict(unit_id=uid, text=row['text']) for uid, row in catalog.items() if uid in eligible],
        existing_visuals={key: prior[key] if prior else [] for key in CATALOGS},
        previous_scene=prior['scenes'][-1] if prior and prior['scenes'] else None)
    prompt = (
        'Generate visual descriptions ONLY for fixed_scenes, in the exact given order. '
        'Their source_text and unit_ids have already been fixed by the program. Copy source_text first, '
        'then describe exactly that narration using the full original script only to resolve context. '
        'Prioritize the current scene_semantics subject over previous_scene or the existing entity catalog; '
        'a changed subject must change the actual picture. '
        'Never summarize the whole story into the first slots or fill remaining slots with a repeated generic shot. '
        'A scene about Jupiter must show Jupiter, not a later event, another planet or an unrelated spacecraft. '
        'Use concise Chinese descriptions of one visible scene. image_prompt must describe a film frame, '
        'image_prompt is plain Chinese prose, never JSON or an environment new/reuse object encoded as text. '
        'Only the environment FIELD uses the structured new/reuse choices. Do not put braces in image_prompt. '
        'not an infographic, collage, date caption, labelled diagram or a claim about absent objects. '
        'Do not ask for text, numbers, labels, watermarks or split screens in the image. '
        'When narration says there are no astronauts, show the unmanned exterior instead of astronauts. '
        'Maintain photorealistic scientific documentary style. '
        'Define depicted subjects inline in the subjects field. Use an array of {new: subject_definition, '
        'appearance: {unchanged:true}} for new subjects, or {reuse: existing_subject_key, appearance: '
        '{unchanged:true}} for existing subjects. subjects={reuse_previous:true} keeps the entire preceding '
        'scene subject set when the same physical subjects remain. Do not invent subject IDs or emit catalogs. '
        'An appearance change uses an inline new appearance with source evidence; unchanged preserves it. '
        'Define each scene environment inline: {"new": environment_definition}, '
        '{"reuse": existing_environment_key}, or {"reuse_previous":true} for the same place/time as the '
        'previous fixed scene. Do not emit a scene_groups catalog or invent environment references. '
        'Use source_facts only for claims supported by their cited original units; '
        'mark staging, camera and inferred visual details as creative_choices. '
        'References in sources/change_sources are original unit IDs, and must not cite future units '
        'relative to first use. A new environment or appearance needs explicit change_sources. '
        'For the same environment, reuse its key without redefining it. '
        'Keep global_style unchanged after the first batch. Never claim user approval or completed review. '
        'Output the supplied schema only.\nFOCUSED_SCENE_INPUT_JSON\n'
        + json.dumps(context, ensure_ascii=False, separators=(',', ':')))
    return prompt, wire


def merge_focus(prior, value, slices, wire, script, units):
    _schema_check(value, wire)
    _nonempty_strings(value)
    spans = {s['unit_id']: TextSpan(**s) for s in units['spans'] if s['kind'] == 'speech'}
    catalog = {uid: dict(unit_id=uid, text_start=s.start, text_end=s.end, quote=s.text)
               for uid, s in spans.items()}
    result = deepcopy(prior) if prior else dict(global_style=None, entities=[], appearance_variants=[], scene_groups=[], scenes=[])

    def expand(node):
        if isinstance(node, list): return [expand(v) for v in node]
        if not isinstance(node, dict): return node
        return {key: [deepcopy(catalog[uid]) for uid in item] if key in ('sources','change_sources')
                else expand(item) for key, item in node.items()}

    restored = expand(value)
    restore_subjects(restored,prior,slices)
    restored['scene_groups']=[]
    previous_key=prior['scenes'][-1]['scene_group_id'] if prior and prior['scenes'] else None
    for source in slices:
        scene=restored['scenes'][source['scene_key']]
        environment=scene.pop('environment')
        if 'new' in environment:
            key='focus_environment_'+source['scene_key']
            restored['scene_groups'].append(dict(environment['new'],key=key))
        elif 'reuse' in environment:key=environment['reuse']
        else:key=previous_key
        scene['scene_group_id']=key
        previous_key=key
    if prior is None: result['global_style'] = restored['global_style']
    maps = {}
    added = {}
    for category in CATALOGS:
        maps[category] = {row['key']: row for row in result[category]}
        added[category] = set()
        for row in restored[category]:
            key = row['key']
            if key in maps[category]:
                if maps[category][key] != row: raise ValueError('immutable focused visual definition differs')
                continue
            result[category].append(row); maps[category][key] = row; added[category].add(key)
    used = {key: set() for key in CATALOGS}
    previous = result['scenes'][-1] if result['scenes'] else None
    previous_variants={}
    for old in result['scenes']:
        current={}
        for key in old['variant_ids']:
            owner=maps['appearance_variants'][key]['entity_key']
            current.setdefault(owner,set()).add(key)
        previous_variants.update(current)
    for source in slices:
        scene = deepcopy(restored['scenes'][source['scene_key']])
        scene.pop('source_text')
        scene.update(paragraph_id=source['paragraph_id'], unit_ids=source['unit_ids'])
        latest = spans[scene['unit_ids'][-1]].end
        _grounding(scene, script, spans, latest=latest)
        refs = dict(entities=scene['entity_ids'], appearance_variants=scene['variant_ids'], scene_groups=[scene['scene_group_id']])
        for category, keys in refs.items():
            for key in keys:
                if key not in maps[category]: raise ValueError('unknown focused visual reference')
                row = maps[category][key]
                _grounding(row, script, spans, latest=None if category=='entities' else latest)
                used[category].add(key)
                if category == 'appearance_variants' and row['entity_key'] not in scene['entity_ids']:
                    raise ValueError('focused variant entity absent from scene')
        group = maps['scene_groups'][scene['scene_group_id']]
        if previous and previous['scene_group_id'] != scene['scene_group_id'] and not (scene['change_sources'] or group['change_sources']):
            raise ValueError('focused environment change requires original-source evidence')
        current_variants={}
        for key in scene['variant_ids']:
            owner=maps['appearance_variants'][key]['entity_key']
            current_variants.setdefault(owner,set()).add(key)
        for owner,keys in current_variants.items():
            if owner in previous_variants and previous_variants[owner]!=keys:
                if not (scene['change_sources'] or any(maps['appearance_variants'][key]['change_sources'] for key in keys)):
                    raise ValueError('focused appearance change requires original-source evidence')
            previous_variants[owner]=keys
        result['scenes'].append(scene); previous = scene
    if any(added[key] - used[key] for key in CATALOGS): raise ValueError('unused focused visual definition')
    _grounding(result['global_style'], script, spans, latest=spans[result['scenes'][0]['unit_ids'][-1]].end)
    return result
