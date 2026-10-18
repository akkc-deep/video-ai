"""Immutable sample/frame composition contracts. No media or filesystem I/O."""
from collections.abc import Mapping
from dataclasses import dataclass, fields
import math

from .timeline import Timeline, SlotRange, budget_slots, validate_timeline,sample_to_frame
from .storyboard import SpeechTimingEvidence, plan_slots, validate_timing
from .source_clips import _integer, _same, _complete_identity
from .upscale import _freeze
from ..runtime.manifest import thaw


@dataclass(frozen=True)
class CompositionSettings:
    schema_version: int = 1
    font_name: str = 'Microsoft YaHei'
    font_size: int = 54
    margin: int = 64
    outline: int = 2
    music_gain: float = 0.12
    music_fade_seconds: float = 0.5
    music_loop_crossfade_seconds: float = 0.05

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError('settings schema_version must be integer1')
        if type(self.font_name) is not str or not self.font_name.strip() or any(c in self.font_name for c in '\\{},\r\n\x00') or any(ord(c)<32 for c in self.font_name):
            raise ValueError('font_name contains ASS control characters')
        for key,low,high in [('font_size',16,120),('margin',0,300),('outline',0,10)]:
            value=getattr(self,key)
            if type(value) is not int or not low<=value<=high:raise ValueError(f'{key}: integer {low}..{high} required')
        for key in ('music_gain','music_fade_seconds','music_loop_crossfade_seconds'):
            value=getattr(self,key)
            if type(value) not in (float,int) or not math.isfinite(value) or value<0 or (key=='music_gain' and value>1):
                raise ValueError(f'{key}: invalid finite nonnegative number')

    @classmethod
    def from_dict(cls,data):
        if not isinstance(data,Mapping) or set(data)-{f.name for f in fields(cls)}:raise ValueError('unknown composition setting')
        return cls(**data)


@dataclass(frozen=True)
class CompositionPlan:
    output_fps: int
    native_fps: int
    total_frames: int
    total_samples: int
    video_samples: int
    padding_samples: int
    settings: CompositionSettings
    ordered_shots: tuple
    transitions: tuple
    ordered_frame_map: tuple
    subtitle_events: tuple
    requirement_bindings: tuple
    cue_checks: tuple

    def __post_init__(self):
        for name in ('ordered_shots','transitions','ordered_frame_map','subtitle_events','requirement_bindings','cue_checks'):
            object.__setattr__(self,name,_freeze(thaw(getattr(self,name))))

    def as_dict(self):return thaw(self)


def contiguous_ranges(values):
    result=[]
    for value in values:
        if result and result[-1]['end']==value:result[-1]['end']+=1
        else:result.append(dict(start=value,end=value+1))
    return result


def _ready(storyboard,upscaled):
    for report in (storyboard,upscaled):
        _freeze(report)
        if report.get('status')!='completed' or report.get('passed') is not True:raise ValueError('completed inputs required')
    checks=upscaled['validation']
    for key in ('ready_for_composition','video_text_semantics_passed','motion_semantics_passed'):
        if checks.get(key) is not True:raise ValueError('upscaled review not passed: '+key)
    if not _same(storyboard['effective_media'],upscaled['effective_media']):raise ValueError('effective media inputs differ')


def _plan(timeline,storyboard,upscaled,timing,settings):
    validate_timeline(timeline);validate_timing(timeline,timing)
    if not isinstance(settings,CompositionSettings):raise ValueError('CompositionSettings required')
    _ready(storyboard,upscaled)
    slots=plan_slots(timeline,timing=timing)
    media=storyboard['effective_media']
    if type(media['fps']) is not int or media['fps']!=timeline.output_fps or type(media['native_fps']) is not int or media['native_fps']!=16:
        raise ValueError('timeline/media fps mismatch')
    budget=budget_slots(timeline,[SlotRange(s.shot_id,s.start_frame,s.end_frame) for s in slots],transition=media['transition'],transition_seconds=media['transition_seconds'])
    expected_cues=[dict(thaw(c),frame=sample_to_frame(c.absolute_sample,timeline.output_fps)) for c in timing.cues]
    if not _same(storyboard['transitions'],budget.transitions) or not _same(storyboard['cues'],expected_cues):raise ValueError('transition/cue evidence differs')
    if len(slots)!=len(storyboard['shots']) or len(slots)!=len(upscaled['clips']) or len(slots)!=len(upscaled['frame_mappings']):
        raise ValueError('shot coverage/order differs')
    shots=[];clip_by_id={};shot_by_id={}
    for slot,b,shot,clip,mapping in zip(slots,budget.shots,storyboard['shots'],upscaled['clips'],upscaled['frame_mappings']):
        for row in (shot,clip,mapping):
            if row['shot_id']!=slot.shot_id:raise ValueError('noncanonical shot order')
        if not _same(shot['bindings'],slot.bindings) or not _same(shot['budget'],b) or not _same(clip['budget'],b) or shot['primary_unit_id']!=slot.primary_unit_id or clip['primary_unit_id']!=slot.primary_unit_id or type(shot['start_frame']) is not int or type(shot['end_frame']) is not int or (shot['start_frame'],shot['end_frame'])!=(slot.start_frame,slot.end_frame):
            raise ValueError('storyboard text/binding/budget differs')
        n=b.required_native_frames
        for key,want in [('source_frames',n),('upscaled_frames',n),('width',1920),('height',1080),('native_fps',16)]:
            if type(clip[key]) is not int or clip[key]!=want:raise ValueError('invalid native frame count/dimensions')
        if len(clip['frames'])!=n:raise ValueError('missing native frame')
        _complete_identity(clip['upscaled_identity'])
        for i,frame in enumerate(clip['frames']):
            if type(frame['frame_index']) is not int or frame['frame_index']!=i+1 or type(frame['source_frame_index']) is not int or frame['source_frame_index']!=i:raise ValueError('frame order/source mapping differs')
            _complete_identity(frame['upscaled_frame_identity'])
        expected=dict(shot_id=slot.shot_id,source_frames=n,upscaled_frames=n,native_fps=16,output_fps=timeline.output_fps,
            coverage_start_frame=b.coverage_start_frame,coverage_end_frame=b.coverage_end_frame,
            core_start_frame=b.core_start_frame,core_end_frame=b.core_end_frame,source_to_upscaled=list(range(n)),
            output_to_upscaled=[i*16//timeline.output_fps for i in range(b.required_output_frames)],upscaled_identity=clip['upscaled_identity'])
        if not _same({k:mapping[k] for k in expected},expected):raise ValueError('upscaled frame mapping differs')
        shots.append(dict(shot_id=slot.shot_id,primary_unit_id=slot.primary_unit_id,core=dict(start=b.core_start_frame,end=b.core_end_frame),coverage=dict(start=b.coverage_start_frame,end=b.coverage_end_frame),crop=dict(start=0,end=n),rate_conversion='identity' if timeline.output_fps==16 else 'previous_native_frame'))
        clip_by_id[slot.shot_id]=clip;shot_by_id[slot.shot_id]=shot
    frame_map=[]
    for f in range(timeline.total_frames):
        window=next((t for t in budget.transitions if t.start_frame<=f<t.end_frame),None)
        contributors=[]
        for b in budget.shots:
            if not b.coverage_start_frame<=f<b.coverage_end_frame:continue
            num=den=1
            if window:
                L=window.actual_frames;k=f-window.start_frame
                den=2 if L==1 else L-1
                right=1 if L==1 else k
                num=right if b.shot_id==window.right_shot_id else den-right
            index=(f-b.coverage_start_frame)*16//timeline.output_fps
            clip=clip_by_id[b.shot_id]
            if index>=len(clip['frames']):raise ValueError('source frames insufficient')
            contributors.append(dict(shot_id=b.shot_id,native_frame_index=index,source_frame_index=index,frame_identity=clip['frames'][index]['upscaled_frame_identity'],weight_numerator=num,weight_denominator=den))
        if len(contributors)!=(2 if window else 1):raise ValueError('frame contributors incomplete')
        frame_map.append(dict(output_frame=f,contributors=contributors))
    requirements=[];expected_order=[]
    for shot in storyboard['shots']:
        expected_order.extend((shot['shot_id'],i,r) for i,r in enumerate(shot['visual_requirements']))
    if len(expected_order)!=len(upscaled['requirement_clips']):raise ValueError('requirement coverage differs')
    for (shot_id,i,req),row in zip(expected_order,upscaled['requirement_clips']):
        if row['shot_id']!=shot_id or type(row['requirement_index']) is not int or row['requirement_index']!=i or any(row[k]!=req[k] for k in ('requirement_id','unit_id','source_quote')):
            raise ValueError('requirement text/order differs')
        clip=clip_by_id[row['clip_shot_id']]
        expected_role='primary' if row['clip_shot_id']==shot_id else 'quantization_edge_review'
        if row['role']!=expected_role or row['unit_id']!=clip['primary_unit_id'] or not _same(row['actual_artifact'],clip['upscaled_identity']):raise ValueError('requirement clip role/identity differs')
        a=_integer(row['local_frames']['start'],'local start');b=_integer(row['local_frames']['end'],'local end',1)
        if not a<b<=clip['source_frames']:raise ValueError('requirement range outside source')
        visible=[f['output_frame'] for f in frame_map if any(c['shot_id']==row['clip_shot_id'] and c['weight_numerator']>0 and a<=c['native_frame_index']<b for c in f['contributors'])]
        requirements.append(dict(row,candidate_frame_ranges=contiguous_ranges(visible)))
    cues=[]
    for cue,unit in zip(timing.cues,timing.units[1:]):
        matching=next((t for t in budget.transitions if shot_by_id[t.left_shot_id]['primary_unit_id']==cue.from_unit_id and shot_by_id[t.right_shot_id]['primary_unit_id']==cue.to_unit_id),None)
        if matching is None:raise ValueError('cue shot transition absent')
        boundary=matching.boundary_frame
        positive_right=[r['output_frame'] for r in frame_map if any(c['shot_id']==matching.right_shot_id and c['weight_numerator']>0 for c in r['contributors'])]
        positive_left=[r['output_frame'] for r in frame_map if any(c['shot_id']==matching.left_shot_id and c['weight_numerator']>0 for c in r['contributors'])]
        first,last=min(positive_right),max(positive_left)
        measured=[boundary] if matching.actual_frames==0 else [first,last+1]
        worst=max(abs(f*48000-cue.absolute_sample*timeline.output_fps)+unit.boundary_uncertainty_samples*timeline.output_fps for f in measured)
        verdict='passed' if worst<=48000 else 'unverified'
        semantics=('subject','setting','quantity','negation','action_or_state','relation_or_order')
        def primary_semantics(shot):
            return [{k:r.get(k) for k in semantics} for r in shot['visual_requirements'] if r['unit_id']==shot['primary_unit_id']]
        compatible=_same(primary_semantics(shot_by_id[matching.left_shot_id]),primary_semantics(shot_by_id[matching.right_shot_id]))
        if worst>48000 and (not matching.actual_frames or not compatible):raise ValueError('fade/cue visible scene change exceeds one frame')
        cues.append(dict(cue_id=cue.cue_id,from_unit_id=cue.from_unit_id,to_unit_id=cue.to_unit_id,absolute_sample=cue.absolute_sample,boundary_uncertainty_samples=unit.boundary_uncertainty_samples,planned_change_frame=boundary,first_positive_contributor_frame=first,last_positive_contributor_frame=last,worst_case_error_numerator=worst,verdict=verdict,reason='Integer boundary calculation only; final visible synchronization remains unverified.' if verdict=='passed' else 'Compatible overlap requires actual final-video synchronization review.'))
    return CompositionPlan(timeline.output_fps,16,timeline.total_frames,timeline.total_samples,timeline.total_frames*(48000//timeline.output_fps),timeline.video_padding_samples,settings,tuple(shots),budget.transitions,tuple(frame_map),timeline.subtitles,tuple(requirements),tuple(cues))


def plan_composition(timeline:Timeline,storyboard:dict,upscaled:dict,timing:SpeechTimingEvidence,*,settings:CompositionSettings)->CompositionPlan:
    try:return _plan(timeline,storyboard,upscaled,timing,settings)
    except (KeyError,TypeError,AttributeError,OverflowError) as exc:raise ValueError('invalid composition inputs') from exc


def validate_composition_plan(plan:CompositionPlan,*,timeline,storyboard,upscaled,timing)->None:
    if not isinstance(plan,CompositionPlan):raise ValueError('CompositionPlan required')
    expected=plan_composition(timeline,storyboard,upscaled,timing,settings=plan.settings)
    if not _same(plan,expected):raise ValueError('composition plan differs from canonical reconstruction')
