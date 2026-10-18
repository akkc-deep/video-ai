"""Immutable PCM coverage and human-reviewed cue mapping; no inference here."""
from dataclasses import dataclass
import json
import re
from typing import Sequence

from .timeline import Timeline, sample_to_frame, validate_timeline
from ..runtime.manifest import thaw


class UnsupportedSemanticTimingError(ValueError):
    """A new run with finer independently timed speech is needed."""


@dataclass(frozen=True)
class UnitTiming:
    unit_id: str
    spoken_start_sample: int
    spoken_end_sample: int
    boundary_uncertainty_samples: int
    verified_internal_silences: tuple[tuple[int, int], ...]
    verdict: str
    semantic_unit_verdict: str


@dataclass(frozen=True)
class SemanticCue:
    cue_id: str
    from_unit_id: str
    to_unit_id: str
    absolute_sample: int
    verdict: str


@dataclass(frozen=True)
class SpeechTimingEvidence:
    units: tuple[UnitTiming, ...]
    cues: tuple[SemanticCue, ...]
    review_method: str = 'human_audio'


@dataclass(frozen=True)
class Binding:
    unit_id: str
    text_start: int
    text_end: int
    text: str
    start_sample: int
    end_sample: int
    start_frame: int
    end_frame: int
    quantization_edge: bool
    silence_only: bool
    spoken_overlap_samples: int | None


@dataclass(frozen=True)
class StoryboardSlot:
    shot_id: str
    start_frame: int
    end_frame: int
    primary_unit_id: str
    bindings: tuple[Binding, ...]


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name}: expected integer >= {minimum}')


def validate_timing(timeline, timing):
    if not isinstance(timing, SpeechTimingEvidence): raise ValueError('invalid timing evidence')
    if timing.review_method not in ('human_audio','automated_audio'):raise ValueError('invalid timing review method')
    if tuple(u.unit_id for u in timing.units) != tuple(c.unit_id for c in timeline.clips):
        raise ValueError('timing unit coverage/order mismatch')
    for clip, unit in zip(timeline.clips, timing.units):
        if unit.verdict != 'passed' or unit.semantic_unit_verdict != 'passed':
            raise UnsupportedSemanticTimingError(f'{unit.unit_id}: unverified speech/semantic timing')
        a, b, u = unit.spoken_start_sample, unit.spoken_end_sample, unit.boundary_uncertainty_samples
        for name, value in [('onset', a), ('offset', b), ('uncertainty', u)]: integer(value, name)
        valid=(0<=a<b<=clip.samples) if timing.review_method=='automated_audio' else (0 <= a-u <= a < b <= b+u <= clip.samples)
        if not valid or u>clip.samples:
            raise ValueError('timing envelope/uncertainty outside PCM')
        cursor = a
        for interval in unit.verified_internal_silences:
            if len(interval) != 2: raise ValueError('invalid internal silence')
            x, y = interval
            integer(x,'silence start'); integer(y,'silence end')
            if not cursor <= x < y <= b: raise ValueError('invalid internal silence order/envelope')
            cursor = y
    if len(timing.cues) != len(timeline.clips)-1: raise ValueError('cue coverage mismatch')
    ids=set()
    for index, cue in enumerate(timing.cues):
        left, right = timeline.clips[index:index+2]
        lu, ru = timing.units[index:index+2]
        integer(cue.absolute_sample,'cue')
        if (not isinstance(cue.cue_id,str) or not cue.cue_id.strip() or cue.cue_id in ids
                or cue.from_unit_id != left.unit_id or cue.to_unit_id != right.unit_id or cue.verdict != 'passed'
                or cue.absolute_sample != right.start_sample+ru.spoken_start_sample
                or cue.absolute_sample < left.start_sample+lu.spoken_end_sample):
            raise ValueError('invalid cue identity/order/onset')
        ids.add(cue.cue_id)
        frame = sample_to_frame(cue.absolute_sample, timeline.output_fps)
        if abs(frame*48000-cue.absolute_sample*timeline.output_fps)+ru.boundary_uncertainty_samples*timeline.output_fps > 48000:
            raise ValueError('cue uncertainty and quantization exceed one frame')


def _spoken_overlap(clip, unit, a, b):
    # Only confirmed silence is removed. The uncertainty bands remain speech.
    x=max(a,clip.start_sample+unit.spoken_start_sample-unit.boundary_uncertainty_samples)
    y=min(b,clip.start_sample+unit.spoken_end_sample+unit.boundary_uncertainty_samples)
    total=max(0,y-x)
    for sa,sb in unit.verified_internal_silences:
        total-=max(0,min(y,clip.start_sample+sb)-max(x,clip.start_sample+sa))
    return total


def plan_slots(timeline: Timeline, *, timing: SpeechTimingEvidence | None = None) -> tuple[StoryboardSlot, ...]:
    validate_timeline(timeline)
    if timing is not None: validate_timing(timeline,timing)
    fps=timeline.output_fps; frame_samples=48000//fps
    cuts=[0]+[sample_to_frame(c.absolute_sample,fps) for c in timing.cues]+[timeline.total_frames] if timing is not None else [0]+[sample_to_frame(c.pause_end_sample,fps) for c in timeline.clips[:-1]]+[timeline.total_frames]
    units={u.unit_id:u for u in timing.units} if timing is not None else {}
    return _assemble_slots(timeline,cuts,units)


def _assemble_slots(timeline, cuts, units):
    """Shared integer subdivision and PCM intersections, after caller validation."""
    fps=timeline.output_fps; frame_samples=48000//fps
    slots=[]
    for clip, a, b in zip(timeline.clips,cuts,cuts[1:]):
        length=b-a
        if length<=0: raise UnsupportedSemanticTimingError(f'{clip.unit_id}: cell has no positive frame coverage')
        n=1 if length<=6*fps else max(2,(length+6*fps-1)//(6*fps),(2*length+5*fps)//(10*fps))
        edges=[a+(i*length)//n for i in range(n+1)]
        for start,end in zip(edges,edges[1:]):
            bindings=[]
            for other in timeline.clips:
                sa=max(start*frame_samples,other.start_sample)
                sb=min(end*frame_samples,other.end_sample,timeline.total_samples)
                if sa>=sb: continue
                overlap=_spoken_overlap(other,units[other.unit_id],sa,sb) if units else None
                active=sb-sa if overlap is None else overlap
                edge=other.unit_id!=clip.unit_id and active>0
                if edge and active>frame_samples:
                    raise UnsupportedSemanticTimingError(f'{other.unit_id}: foreign speech overlaps more than one frame')
                bindings.append(Binding(other.unit_id,other.text_start,other.text_end,other.text,sa,sb,
                    sample_to_frame(sa,fps),sample_to_frame(sb,fps),edge,overlap==0,overlap))
            slots.append(StoryboardSlot(f'shot_{len(slots)+1:04d}',start,end,clip.unit_id,tuple(bindings)))
    # All PCM coverage, including silence and rounding edges, is retained.
    for clip in timeline.clips:
        intervals=[(b.start_sample,b.end_sample) for s in slots for b in s.bindings if b.unit_id==clip.unit_id]
        if (not intervals or intervals[0][0]!=clip.start_sample or intervals[-1][1]!=clip.end_sample
                or any(x[1]!=y[0] for x,y in zip(intervals,intervals[1:]))):
            raise ValueError('binding coverage differs from complete PCM')
    return tuple(slots)


def validate_slots(timeline: Timeline, slots: Sequence[StoryboardSlot], *, timing=None) -> None:
    expected=plan_slots(timeline,timing=timing)
    if json.dumps(thaw(slots),sort_keys=True)!=json.dumps(thaw(expected),sort_keys=True):
        raise ValueError('slots differ from canonical PCM/cue coverage')


def _object(properties):
    return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)


def _array(items, **constraints):
    return dict(type='array',items=items,**constraints)


def source_catalog(slots):
    catalog={}
    for slot in slots:
        for binding in slot.bindings:
            source=dict(unit_id=binding.unit_id,text_start=binding.text_start,text_end=binding.text_end,text=binding.text)
            if binding.unit_id in catalog and catalog[binding.unit_id]!=source:
                raise ValueError('inconsistent frozen source catalog')
            catalog[binding.unit_id]=source
    return catalog


def primary_model_slots(slots: Sequence[StoryboardSlot]) -> tuple[StoryboardSlot, ...]:
    """Keep actual slots immutable while presenting one scene per model shot."""
    from dataclasses import replace
    result=[]
    for slot in slots:
        primary=tuple(b for b in slot.bindings if b.unit_id==slot.primary_unit_id)
        if len(primary)!=1:
            raise ValueError('one primary binding required')
        result.append(replace(slot,bindings=primary))
    return tuple(result)


def expand_boundary_requirements(content, slots, *, semantic_specs=None, depiction_policy=None):
    """Copy validated next/previous primary requirements; never edit model text."""
    from copy import deepcopy
    projected=primary_model_slots(slots)
    validate_model_content(content,projected,semantic_specs=semantic_specs,depiction_policy=depiction_policy,source_slots=slots)
    expanded=deepcopy(content);associations=[]
    for target_index,slot in enumerate(slots):
        requirements=[]
        for binding in slot.bindings:
            if binding.silence_only:continue
            primary=binding.unit_id==slot.primary_unit_id
            if not primary and not binding.quantization_edge:
                raise ValueError('foreign non-silent binding must be a quantization edge')
            candidates=[i for i,s in enumerate(projected) if s.primary_unit_id==binding.unit_id and
                len(content['shots'][i]['visual_requirements'])==1]
            if not candidates:raise ValueError('missing primary source for boundary binding')
            source_index=target_index if primary else min(candidates,key=lambda i:(abs(i-target_index),i))
            source=content['shots'][source_index]['visual_requirements'][0]
            requirements.append(deepcopy(source))
            associations.append(dict(target_shot_index=target_index,target_shot_id=slot.shot_id,
                target_requirement_index=len(requirements)-1,unit_id=binding.unit_id,
                source_shot_index=source_index,source_shot_id=projected[source_index].shot_id,
                source_requirement_index=0,scope='primary' if primary else 'leading_edge' if source_index<target_index else 'trailing_edge'))
        expanded['shots'][target_index]['visual_requirements']=requirements
    validate_model_content(expanded,slots,semantic_specs=semantic_specs,depiction_policy=depiction_policy)
    return expanded,associations


SOURCE_FACT_FIELDS=('subject','action_or_state','setting','quantity','negation','relation_or_order','context_sources','resolved_references')
GROUNDED_POLICY='grounded_prompts_v1'
CAMERA_PATHS=('static camera','slow forward dolly','slow backward dolly','slow left pan','slow right pan','slow upward tilt','slow downward tilt')


def depiction_anchor(facts, *, source_quote=None):
    values=[facts[k] for k in SOURCE_FACT_FIELDS[:6] if facts[k] is not None]
    # Lossless units may contain narration with no extracted visual facts.
    # Keep their frozen quote as grounding without inventing or editing facts.
    if not values and isinstance(source_quote,str) and source_quote.strip():values=[source_quote]
    if not values:raise ValueError('grounded depiction requires source facts')
    return '; '.join(values)+'. '


def _anchored_string(facts, *, video=False, source_quote=None):
    # llama.cpp rejects Python re.escape's unnecessary escapes for spaces,
    # hyphens and #. Escape only regex operators outside character classes.
    literal=lambda value:''.join('\\'+c if c in r'\.^$|?*+(){}[]' else {'\n':r'\n','\r':r'\r','\t':r'\t'}.get(c,c) for c in value)
    pattern='^'+literal(depiction_anchor(facts,source_quote=source_quote))+'[^ \\t\\r\\n].*'
    if video:pattern+=' Camera path: ('+'|'.join(literal(p) for p in CAMERA_PATHS)+')\\.'
    return dict(type='string',pattern=pattern+'$',minLength=1)


def _source_properties(catalog):
    string=dict(type='string',minLength=1)
    nullable=dict(type=['string','null'],minLength=1)
    context=dict(anyOf=[_object({key:dict(type='integer' if type(value) is int else 'string',const=value) for key,value in
        dict(unit_id=source['unit_id'],text_start=source['text_start'],text_end=source['text_end'],source_quote=source['text']).items()}) for source in catalog.values()])
    resolved=_object(dict(reference_quote=string,resolved_subject=string,
        context_source_indices=_array(dict(type='integer',minimum=0),minItems=1,uniqueItems=True)))
    return dict(subject=nullable,action_or_state=nullable,setting=nullable,quantity=nullable,negation=nullable,
        relation_or_order=nullable,context_sources=_array(context),resolved_references=_array(resolved))


def _source_references(requirement,text,catalog):
    for support in requirement['context_sources']:
        source=catalog[support['unit_id']];a,b=support['text_start'],support['text_end']
        if not source['text_start']<=a<b<=source['text_end'] or source['text'][a-source['text_start']:b-source['text_start']]!=support['source_quote']:
            raise ValueError('invalid context source span/quote')
    for reference in requirement['resolved_references']:
        if reference['reference_quote'] not in text:raise ValueError('reference outside binding')
        if any(i>=len(requirement['context_sources']) for i in reference['context_source_indices']):raise ValueError('context source index out of range')


def validate_semantic_specs(specs,slots):
    """Validate coverage/types/references, not the truth of agent interpretations."""
    catalog=source_catalog(slots);properties=_source_properties(catalog)
    if not isinstance(specs,dict) or set(specs)!=set(catalog):raise ValueError('source contract unit coverage')
    for uid,facts in specs.items():
        _schema_check(facts,_object(properties),f'contract.{uid}')
        _source_references(facts,catalog[uid]['text'],catalog)


def _model_sources(slots, source_slots):
    if source_slots is None: return slots
    by_id={s.shot_id:s for s in source_slots}
    if len(by_id)!=len(source_slots): raise ValueError('duplicate source slots')
    projected={s.shot_id:s for s in primary_model_slots(source_slots)}
    if any(s.shot_id not in by_id or s not in (by_id[s.shot_id],projected[s.shot_id]) for s in slots):
        raise ValueError('batch slot differs from fixed full source projection')
    return source_slots


def make_model_schema(slots: Sequence[StoryboardSlot], *, semantic_specs=None,depiction_policy=None,source_slots=None) -> dict:
    if not slots: raise ValueError('empty storyboard slots')
    from copy import deepcopy
    sources=_model_sources(slots,source_slots)
    catalog=source_catalog(sources);source_properties=_source_properties(catalog)
    if semantic_specs is not None:validate_semantic_specs(semantic_specs,sources)
    if depiction_policy is not None and (depiction_policy!=GROUNDED_POLICY or semantic_specs is None):
        raise ValueError('unknown or ungrounded depiction policy')
    string=dict(type='string',minLength=1)
    shot_schemas=[]
    for slot in slots:
        requirements=[_object(dict(unit_id=dict(type='string',const=b.unit_id),
            source_quote=dict(type='string',const=b.text),**deepcopy(source_properties),visual_expression=string,
            needs_finer_audio=dict(type='boolean'))) for b in slot.bindings if not b.silence_only]
        if semantic_specs is not None:
            for r in requirements:
                for key,value in semantic_specs[r['properties']['unit_id']['const']].items():
                    r['properties'][key]=dict(r['properties'][key],const=deepcopy(value))
        shot_schema=_object(dict(shot_id=dict(type='string',const=slot.shot_id),entity_ids=_array(string,uniqueItems=True),
            composition=string,camera_motion=string,action_start=string,action_end=string,image_prompt=string,
            video_prompt=string,visual_requirements=dict(type='array',prefixItems=requirements,items=False,minItems=len(requirements),maxItems=len(requirements))))
        if depiction_policy is not None:
            props=shot_schema['properties'];facts=semantic_specs[slot.primary_unit_id]
            for key in ('composition','action_start','action_end','image_prompt','video_prompt'):
                props[key]=_anchored_string(facts,video=key=='video_prompt',source_quote=catalog[slot.primary_unit_id]['text'])
            props['camera_motion']=dict(type='string',enum=list(CAMERA_PATHS))
            for r in requirements:
                uid=r['properties']['unit_id']['const']
                r['properties']['visual_expression']=_anchored_string(semantic_specs[uid],source_quote=catalog[uid]['text'])
        shot_schemas.append(shot_schema)
    entity=_object(dict(entity_id=string,description=string,source_quotes=_array(string,minItems=1)))
    global_schema=_object(dict(style=string,color_palette=string,lighting=string,entities=_array(entity)))
    return _object(dict(schema_version=dict(type='integer',const=1),global_visual=global_schema,
        shots=dict(type='array',prefixItems=shot_schemas,items=False,minItems=len(slots),maxItems=len(slots))))


def _schema_check(value,schema,path='content'):
    """Explicit validation of the exact standard JSON Schema subset we emit."""
    if schema is False: raise ValueError(f'{path}: extra array item')
    if 'anyOf' in schema:
        for alternative in schema['anyOf']:
            try:_schema_check(value,alternative,path);return
            except ValueError:pass
        raise ValueError(f'{path}: no supported original context source')
    types=schema.get('type'); types=[types] if isinstance(types,str) else types
    actual=('null' if value is None else 'boolean' if type(value) is bool else 'integer' if type(value) is int
            else 'string' if isinstance(value,str) else 'array' if isinstance(value,list) else 'object' if isinstance(value,dict) else 'unknown')
    if actual not in types: raise ValueError(f'{path}: invalid type {actual}')
    if 'const' in schema and value!=schema['const']: raise ValueError(f'{path}: wrong const')
    if 'enum' in schema and value not in schema['enum']: raise ValueError(f'{path}: value not in enum')
    if actual=='string' and ('minLength' in schema and len(value.strip())<schema['minLength']): raise ValueError(f'{path}: empty string')
    if actual=='string' and 'pattern' in schema and re.search(schema['pattern'],value) is None:raise ValueError(f'{path}: grounded instruction pattern missing')
    if actual=='integer' and value<schema.get('minimum',value): raise ValueError(f'{path}: integer out of range')
    if actual=='object':
        if set(value)!=set(schema['properties']): raise ValueError(f'{path}: missing/unknown fields')
        for key,item in value.items(): _schema_check(item,schema['properties'][key],f'{path}.{key}')
    if actual=='array':
        if not schema.get('minItems',0)<=len(value)<=schema.get('maxItems',len(value)): raise ValueError(f'{path}: array count')
        if schema.get('uniqueItems') and len({json.dumps(x,sort_keys=True) for x in value})!=len(value): raise ValueError(f'{path}: duplicate item')
        prefix=schema.get('prefixItems',[])
        for i,item in enumerate(value): _schema_check(item,prefix[i] if i<len(prefix) else schema['items'],f'{path}[{i}]')


def validate_model_content(content: dict, slots: Sequence[StoryboardSlot], *, semantic_specs=None,depiction_policy=None,source_slots=None) -> None:
    _schema_check(content,make_model_schema(slots,semantic_specs=semantic_specs,depiction_policy=depiction_policy,source_slots=source_slots))
    catalog=source_catalog(_model_sources(slots,source_slots))
    entities=content['global_visual']['entities']; entity_ids=[e['entity_id'] for e in entities]
    if len(set(entity_ids))!=len(entity_ids): raise ValueError('duplicate entity identity')
    for entity in entities:
        if any(not any(q in source['text'] for source in catalog.values()) for q in entity['source_quotes']):
            raise ValueError('entity quote outside original source')
    for slot,shot in zip(slots,content['shots']):
        if depiction_policy is not None and not shot['video_prompt'].endswith(' Camera path: '+shot['camera_motion']+'.'):
            raise ValueError('video camera path differs from camera_motion')
        if depiction_policy is not None:
            anchor=depiction_anchor(semantic_specs[slot.primary_unit_id],source_quote=catalog[slot.primary_unit_id]['text'])
            for key in ('composition','action_start','action_end','image_prompt','video_prompt'):
                suffix=shot[key][len(anchor):]
                if key=='video_prompt':suffix=suffix[:-len(' Camera path: '+shot['camera_motion']+'.')]
                if not suffix.strip():raise ValueError('nonblank model presentation required')
        if set(shot['entity_ids'])-set(entity_ids): raise ValueError('unknown entity identity')
        bindings={b.unit_id:b for b in slot.bindings}; covered=set()
        for requirement in shot['visual_requirements']:
            uid=requirement['unit_id']; binding=bindings[uid]
            if depiction_policy is not None and not requirement['visual_expression'][len(depiction_anchor(semantic_specs[uid],source_quote=catalog[uid]['text'])):].strip():
                raise ValueError('nonblank model visual expression required')
            if requirement['source_quote'] not in binding.text: raise ValueError('requirement quote outside binding')
            covered.add(uid)
            _source_references(requirement,binding.text,catalog)
            if requirement['needs_finer_audio']:
                raise UnsupportedSemanticTimingError(f'{uid}: needs_finer_audio; use a new run')
        if any(not b.silence_only and b.unit_id not in covered for b in slot.bindings):
            raise ValueError('missing visual requirement for speech binding')
