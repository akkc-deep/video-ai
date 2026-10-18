"""Pure paragraph scenes, grounded shared design and complete PCM coverage."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import re

from ..config import ScenePlanningSettings, parse_scene_planning
from .production_timeline import validate_production_timeline
from .production_visual_plan import plan_scene_clips
from .segments import SegmentedScript, TextSpan, validate_segments
from .storyboard import _array, _object, _schema_check
from .timeline import sample_to_frame
from .visual_consistency import derive_reference_graph, validate_reference_graph


def canonical_digest(value):
    """SHA256 of canonical UTF-8 JSON, never an object representation."""
    return hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def _settings(settings):
    if not isinstance(settings,ScenePlanningSettings):
        raise ValueError('ScenePlanningSettings required')
    return asdict(parse_scene_planning(asdict(settings)))


def paragraphs_from_script(script: SegmentedScript) -> list[dict]:
    """Cover every original character, including CRLF and empty lines."""
    if not isinstance(script,SegmentedScript) or type(script.text) is not str or type(script.has_bom) is not bool:
        raise ValueError('original SegmentedScript required')
    validate_segments(script.text,script.spans)
    result, start = [], 0
    ends = [match.end() for match in re.finditer(r'\r\n|\r|\n',script.text)]
    if not ends or ends[-1] != len(script.text): ends.append(len(script.text))
    for end in ends:
        result.append(dict(paragraph_id=f'paragraph_{len(result)+1:04d}',text_start=start,text_end=end,unit_ids=[]))
        start = end
    for span in script.spans:
        if span.kind != 'speech': continue
        owners = [row for row in result if row['text_start'] <= span.start < span.end <= row['text_end']]
        if len(owners) != 1: raise ValueError('speech unit crosses paragraph boundary')
        owners[0]['unit_ids'].append(span.unit_id)
    return result


def _inputs(script, units, timeline):
    validate_production_timeline(timeline)
    paragraphs = paragraphs_from_script(script)
    if type(units) is not dict or type(units.get('spans')) is not list:
        raise ValueError('finalized units payload required')
    try:
        spans = tuple(TextSpan(**row) for row in units['spans'])
        validate_segments(script.text,spans)
    except (TypeError,KeyError) as exc:
        raise ValueError('invalid finalized unit source spans') from exc
    if (units.get('decoded_text') != script.text or type(units.get('has_bom')) is not bool
            or units['has_bom'] != script.has_bom or spans != script.spans
            or timeline.original_text != script.text or timeline.has_bom != script.has_bom
            or timeline.source_spans != script.spans):
        raise ValueError('script, units and timeline original text/spans differ')
    catalog = {s.unit_id:s for s in spans if s.kind == 'speech'}
    if type(units.get('semantic_specs')) is not dict or set(units['semantic_specs']) != set(catalog):
        raise ValueError('finalized semantic unit coverage differs')
    run_id = units.get('run_id','')
    source_sha = units.get('source_sha256')
    if type(run_id) is not str:
        raise ValueError('run_id must be string')
    if 'source_sha256' not in units:
        source_sha = hashlib.sha256((b'\xef\xbb\xbf' if script.has_bom else b'')+script.text.encode('utf-8')).hexdigest()
    if type(source_sha) is not str or re.fullmatch('[0-9a-f]{64}',source_sha) is None:
        raise ValueError('source_sha256 must be SHA256')
    identity = dict(schema_version=2,production_strategy='paragraph_jimeng_v1',run_id=run_id,
                    algorithm='scene_planning_v1',source_sha256=source_sha,
                    units_sha256=canonical_digest({k:v for k,v in units.items() if k not in ('run_id','source_sha256')}),
                    timeline_sha256=canonical_digest(timeline.as_dict()))
    return paragraphs, catalog, identity


def make_scene_schema(script, units, timeline, settings) -> dict:
    """Exact proposal keys; frame math, stable IDs and identity are program-owned."""
    paragraphs, catalog, _ = _inputs(script,units,timeline)
    effective = _settings(settings)
    string = dict(type='string',minLength=1)
    strings = _array(string,uniqueItems=True)
    source = _object(dict(unit_id=dict(type='string',enum=list(catalog)),text_start=dict(type='integer',minimum=0),
                          text_end=dict(type='integer',minimum=1),quote=string))
    facts = _array(_object(dict(name=string,value=string,sources=_array(source,minItems=1))))
    choices = _array(_object(dict(name=string,value=string,reason=string)))
    grounded = dict(source_facts=facts,creative_choices=choices)
    entity = _object(dict(key=string,label=string,fixed_attributes=_array(string),**grounded))
    variant = _object(dict(key=string,entity_key=string,attributes=_array(string),**grounded,change_sources=_array(source)))
    group = _object(dict(key=string,label=string,environment=string,time=string,lighting=string,
                         spatial_relations=_array(string),**grounded,change_sources=_array(source)))
    scene = _object(dict(paragraph_id=dict(type='string',enum=[p['paragraph_id'] for p in paragraphs if p['unit_ids']]),
                         unit_ids=_array(dict(type='string',enum=list(catalog)),minItems=1,uniqueItems=True),
                         summary=string,image_prompt=string,motion_prompt=string,entity_ids=strings,variant_ids=strings,
                         scene_group_id=string,change_sources=_array(source)))
    return _object(dict(global_style=_object(dict(description=string,**grounded)),entities=_array(entity),
                        appearance_variants=_array(variant),scene_groups=_array(group,minItems=1),
                        scenes=_array(scene,minItems=sum(bool(p['unit_ids']) for p in paragraphs),
                                      maxItems=sum(min(effective['target_scenes_per_paragraph'],len(p['unit_ids'])) for p in paragraphs))))


def _source(source, script, catalog, *, latest=None):
    unit = catalog[source['unit_id']]
    start,end = source['text_start'],source['text_end']
    if (not unit.start <= start < end <= unit.end or source['quote'] != script.text[start:end]
            or (latest is not None and end > latest)):
        raise ValueError('inexact or future source span/quote')


def _grounding(row, script, catalog, *, latest=None):
    for fact in row.get('source_facts',[]):
        for source in fact['sources']: _source(source,script,catalog,latest=latest)
    for source in row.get('change_sources',[]): _source(source,script,catalog,latest=latest)
    for choice in row.get('creative_choices',[]):
        if re.search(r'用户已选|用户已确认|人工已验收|user\s+(?:has\s+)?selected|human[_ ]approved|consistency[_ ]passed',
                     ' '.join(choice.values()),re.IGNORECASE):
            raise ValueError('creative suggestion cannot claim user selection or acceptance')


def _nonempty_strings(value):
    if type(value) is str and not value.strip(): raise ValueError('nonempty visible description required')
    if type(value) is dict:
        for item in value.values(): _nonempty_strings(item)
    elif type(value) is list:
        for item in value: _nonempty_strings(item)


def _catalog(rows):
    result = {}
    for row in rows:
        if row['key'] in result: raise ValueError('duplicate proposal key')
        result[row['key']] = row
    return result


def build_scene_plan(script, units, timeline, proposal: dict, *, settings: ScenePlanningSettings) -> tuple[dict,dict]:
    """Build deterministic scene math and shared references from a visual proposal."""
    try:
        return _build_scene_plan(script,units,timeline,proposal,settings=settings)
    except (TypeError,KeyError,AttributeError,OverflowError) as exc:
        raise ValueError('invalid scene planning input or proposal') from exc


def _build_scene_plan(script,units,timeline,proposal,*,settings):
    effective = _settings(settings)
    paragraphs,catalog,identity = _inputs(script,units,timeline)
    _schema_check(proposal,make_scene_schema(script,units,timeline,settings))
    _nonempty_strings(proposal)
    entities,variants,groups = [_catalog(proposal[name]) for name in ('entities','appearance_variants','scene_groups')]
    for variant in variants.values():
        if variant['entity_key'] not in entities: raise ValueError('unknown variant entity key')
    for row in [proposal['global_style'],*entities.values(),*variants.values(),*groups.values()]:
        _grounding(row,script,catalog)
    expected_units = list(catalog)
    if [uid for s in proposal['scenes'] for uid in s['unit_ids']] != expected_units:
        raise ValueError('scene unit partition must cover all speech exactly once in source order')
    paragraph_by_id = {p['paragraph_id']:p for p in paragraphs}
    counts = {key:0 for key in paragraph_by_id}
    for row in proposal['scenes']:
        paragraph = paragraph_by_id[row['paragraph_id']]
        if any(uid not in paragraph['unit_ids'] for uid in row['unit_ids']):
            raise ValueError('scene cannot merge across paragraphs')
        counts[row['paragraph_id']] += 1
    for paragraph in paragraphs:
        count = counts[paragraph['paragraph_id']]
        if paragraph['unit_ids'] and not 1 <= count <= min(effective['target_scenes_per_paragraph'],len(paragraph['unit_ids'])):
            raise ValueError('scene target exceeded; adjust scene planning configuration')
    mappings = [{},{},{}]
    output_rows = [[],[],[]]
    scenes = []
    previous_group = None
    previous_variants = {}
    for index,row in enumerate(proposal['scenes'],1):
        first,last = catalog[row['unit_ids'][0]],catalog[row['unit_ids'][-1]]
        latest = last.end
        for source in row['change_sources']: _source(source,script,catalog,latest=latest)
        if any(key not in entities for key in row['entity_ids']) or any(key not in variants for key in row['variant_ids']) or row['scene_group_id'] not in groups:
            raise ValueError('unknown scene entity/variant/group key')
        if any(variants[key]['entity_key'] not in row['entity_ids'] for key in row['variant_ids']):
            raise ValueError('variant entity must appear in scene entity_ids')
        current_by_entity = {}
        for key in row['variant_ids']:
            variant = variants[key]; owner = variant['entity_key']
            current_by_entity.setdefault(owner,set()).add(key)
            _grounding(variant,script,catalog,latest=latest)
        for owner,keys in current_by_entity.items():
            if owner in previous_variants and previous_variants[owner] != keys:
                evidence = row['change_sources'] + [source for key in keys for source in variants[key]['change_sources']]
                if not evidence: raise ValueError('appearance change requires source evidence')
            previous_variants[owner] = keys
        group = groups[row['scene_group_id']]
        _grounding(group,script,catalog,latest=latest)
        if previous_group is not None and previous_group != row['scene_group_id']:
            if not group['change_sources'] and not row['change_sources']:
                raise ValueError('scene group change requires source evidence')
        previous_group = row['scene_group_id']
        for category,keys,items,prefix,id_field in (
                (0,row['entity_ids'],entities,'entity','entity_id'),
                (1,row['variant_ids'],variants,'variant','variant_id'),
                (2,[row['scene_group_id']],groups,'group','group_id')):
            for key in keys:
                if key in mappings[category]: continue
                stable = f'{prefix}_{len(mappings[category])+1:04d}'
                mappings[category][key] = stable
                result = {k:deepcopy(v) for k,v in items[key].items() if k not in ('key','entity_key')}
                result[id_field] = stable
                if category == 1: result['entity_id'] = mappings[0][items[key]['entity_key']]
                output_rows[category].append(result)
        scene = deepcopy(row)
        scene.update(scene_id=f'scene_{index:04d}',text_start=first.start,text_end=last.end,
                     entity_ids=[mappings[0][key] for key in row['entity_ids']],
                     variant_ids=[mappings[1][key] for key in row['variant_ids']],scene_group_id=mappings[2][row['scene_group_id']])
        scenes.append(scene)
    if any(len(mapping)!=len(items) for mapping,items in zip(mappings,(entities,variants,groups))):
        raise ValueError('unused proposal visual entry')
    clips_by_unit = {clip.unit_id:clip for clip in timeline.clips}
    edges = [0]+[sample_to_frame(clips_by_unit[s['unit_ids'][0]].start_sample,16) for s in scenes[1:]]+[timeline.total_frames]
    if any(a >= b for a,b in zip(edges,edges[1:])):
        raise ValueError('nonpositive scene frame coverage; merge too-short scene groups')
    for scene,start,end in zip(scenes,edges,edges[1:]):
        scene.update(start_frame=start,end_frame=end,bindings=[])
        for clip in timeline.clips:
            a,b = max(start*3000,clip.start_sample),min(end*3000,timeline.total_samples,clip.end_sample)
            if a < b:
                scene['bindings'].append(dict(unit_id=clip.unit_id,text_start=clip.text_start,text_end=clip.text_end,text=clip.text,
                                              semantic_member=clip.unit_id in scene['unit_ids'],start_sample=a,end_sample=b))
    for clip in timeline.clips:
        intervals = [(b['start_sample'],b['end_sample']) for scene in scenes for b in scene['bindings'] if b['unit_id']==clip.unit_id]
        if (not intervals or intervals[0][0]!=clip.start_sample or intervals[-1][1]!=clip.end_sample
                or any(a[1]!=b[0] for a,b in zip(intervals,intervals[1:]))):
            raise ValueError('scene bindings must cover complete PCM exactly once')
    bible = dict(identity,settings=effective,global_style=deepcopy(proposal['global_style']),
                 entities=output_rows[0],appearance_variants=output_rows[1],scene_groups=output_rows[2])
    baselines,bindings,dependencies,batches = derive_reference_graph(scenes,bible)
    bible['baselines'] = baselines
    for scene,binding,dependency in zip(scenes,bindings,dependencies):
        scene.update(reference_bindings=binding,dependencies=dependency)
    validate_reference_graph(scenes,bible)
    plan = dict(identity,settings=deepcopy(effective),visual_bible_sha256=canonical_digest(bible),
                total_samples=timeline.total_samples,total_frames=timeline.total_frames,
                paragraphs=paragraphs,scenes=scenes,batches=batches)
    plan['clips'] = plan_scene_clips(plan,max_clip_seconds=effective['max_clip_seconds'])
    return bible,plan


def validate_scene_plan(script, units, timeline, visual_bible, scene_plan, *, settings) -> None:
    """Rebuild all derived fields, comparing strict JSON to reject bool forgeries."""
    try:
        proposal = dict(global_style=deepcopy(visual_bible['global_style']),entities=[],appearance_variants=[],scene_groups=[],scenes=[])
        for row in visual_bible['entities']:
            proposal['entities'].append(dict(key=row['entity_id'],**{k:deepcopy(v) for k,v in row.items() if k!='entity_id'}))
        for row in visual_bible['appearance_variants']:
            proposal['appearance_variants'].append(dict(key=row['variant_id'],entity_key=row['entity_id'],**{k:deepcopy(v) for k,v in row.items() if k not in ('variant_id','entity_id')}))
        for row in visual_bible['scene_groups']:
            proposal['scene_groups'].append(dict(key=row['group_id'],**{k:deepcopy(v) for k,v in row.items() if k!='group_id'}))
        fields = ('paragraph_id','unit_ids','summary','image_prompt','motion_prompt','entity_ids','variant_ids','scene_group_id','change_sources')
        for row in scene_plan['scenes']:
            proposal['scenes'].append({field:deepcopy(row[field]) for field in fields})
        expected_bible,expected_plan = build_scene_plan(script,units,timeline,proposal,settings=settings)
        if _canonical(visual_bible)!=_canonical(expected_bible) or _canonical(scene_plan)!=_canonical(expected_plan):
            raise ValueError('scene plan differs from canonical source, settings, coverage or reference graph')
        if validate_reference_graph(scene_plan['scenes'],visual_bible) != scene_plan['batches']:
            raise ValueError('forged scene dependency batches')
    except (TypeError,KeyError,AttributeError,OverflowError) as exc:
        raise ValueError('invalid stored scene plan structure') from exc
