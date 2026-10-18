"""Canonical sample positions and source coverage budgets, without inference."""
from dataclasses import dataclass, fields
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import re
from typing import Mapping, Sequence

from ..config import TimelineSettings, timeline_sample_count
from ..media.audio import AudioInfo
from ..runtime.manifest import thaw
from .segments import SegmentedScript, TextSpan, segment_text, validate_segments


def seconds_to_samples(seconds: int | float) -> int:
    return timeline_sample_count(seconds)


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum: raise ValueError(f'{name}: expected integer >= {minimum}')


def _fps(value):
    _integer(value,'fps')
    if value not in (16,24): raise ValueError('fps must be 16 or 24')


def sample_to_frame(sample: int, fps: int) -> int:
    _integer(sample,'sample')
    _fps(fps)
    return (2*sample*fps+48000)//96000


@dataclass(frozen=True)
class NarrationClip:
    unit_id: str
    span_index: int
    text_start: int
    text_end: int
    text: str
    pcm: AudioInfo
    samples: int
    start_sample: int
    end_sample: int
    pause_kind: str
    pause_samples: int
    pause_end_sample: int
    start_frame: int
    end_frame: int


@dataclass(frozen=True)
class SubtitleEvent:
    unit_id: str
    text_start: int
    text_end: int
    text: str
    start_sample: int
    end_sample: int
    start_frame: int
    end_frame: int


@dataclass(frozen=True)
class SilenceInterval:
    kind: str
    start_sample: int
    end_sample: int
    after_unit_id: str | None
    start_frame: int
    end_frame: int


@dataclass(frozen=True)
class SemanticBoundary:
    pause_end_sample: int
    frame: int
    unit_id: str
    boundary: str
    pause_kind: str


@dataclass(frozen=True)
class SettingSamples:
    sentence_pause_seconds: int
    paragraph_pause_seconds: int
    opening_seconds: int
    closing_seconds: int


@dataclass(frozen=True)
class Timeline:
    schema_version: int
    sample_rate: int
    channels: int
    sample_width: int
    native_fps: int
    output_fps: int
    frame_rate_conversion: bool
    effective_settings: TimelineSettings
    setting_samples: SettingSamples
    original_text: str
    has_bom: bool
    source_spans: tuple[TextSpan, ...]
    clips: tuple[NarrationClip, ...]
    subtitles: tuple[SubtitleEvent, ...]
    silences: tuple[SilenceInterval, ...]
    total_speech_samples: int
    total_silence_samples: int
    total_samples: int
    total_frames: int
    video_padding_samples: int
    semantic_boundaries: tuple[SemanticBoundary, ...]

    def as_dict(self): return thaw(self)

    @classmethod
    def from_dict(cls, data):
        try:
            d=dict(data)
            d['effective_settings']=TimelineSettings(**d['effective_settings'])
            d['setting_samples']=SettingSamples(**d['setting_samples'])
            for name,kind in [('source_spans',TextSpan),('subtitles',SubtitleEvent),
                              ('silences',SilenceInterval),('semantic_boundaries',SemanticBoundary)]:
                d[name]=tuple(kind(**item) for item in d[name])
            clips=[]
            for item in d['clips']:
                c=dict(item)
                pcm=dict(c['pcm']); pcm['path']=Path(pcm['path'])
                c['pcm']=AudioInfo(**pcm)
                clips.append(NarrationClip(**c))
            d['clips']=tuple(clips)
            result=cls(**d)
            validate_timeline(result)
            return result
        except (TypeError,KeyError,AttributeError) as exc: raise ValueError('invalid timeline structure') from exc


def _canonical(script, audio, *, settings, fps):
    if not isinstance(script,SegmentedScript) or type(script.has_bom) is not bool:
        raise ValueError('invalid script')
    validate_segments(script.text,script.spans)
    if script.spans != segment_text(script.text): raise ValueError('noncanonical original boundaries')
    _fps(fps)
    if not isinstance(settings,TimelineSettings): raise ValueError('invalid timeline settings')
    settings=TimelineSettings(**vars(settings))
    setting_samples=SettingSamples(**{k:seconds_to_samples(v) for k,v in vars(settings).items()})
    units=[(i,s) for i,s in enumerate(script.spans) if s.kind=='speech']
    if not units or set(audio)!={s.unit_id for _,s in units}: raise ValueError('speech audio must match every unit exactly')
    for info in audio.values():
        if not isinstance(info,AudioInfo): raise ValueError('invalid audio info')
        for name in ('sample_rate','channels','sample_width','samples','bytes'): _integer(getattr(info,name),name,1)
        if (info.sample_rate,info.channels,info.sample_width)!=(48000,1,2): raise ValueError('expected 48kHz mono PCM16')
        if not isinstance(info.path,Path) or not info.path.is_absolute() or not isinstance(info.sha256,str) or not re.fullmatch('[0-9a-f]{64}',info.sha256):
            raise ValueError('invalid PCM identity')
        if info.bytes < info.samples*2: raise ValueError('PCM identity too short')
    return _assemble_timeline(script,audio,settings=settings,fps=fps)


def _assemble_timeline(script, audio, *, settings, fps, clip_type=NarrationClip, timeline_type=Timeline):
    """Shared sample arithmetic; callers independently validate their input contracts."""
    setting_samples=SettingSamples(**{k:seconds_to_samples(v) for k,v in vars(settings).items()})
    units=[(i,s) for i,s in enumerate(script.spans) if s.kind=='speech']
    clips,subtitles,silences,boundaries=[],[],[],[]
    def silence(kind,a,b,after):
        if b>a: silences.append(SilenceInterval(kind,a,b,after,sample_to_frame(a,fps),sample_to_frame(b,fps)))
    cursor=setting_samples.opening_seconds
    silence('opening',0,cursor,None)
    for pos,(i,span) in enumerate(units):
        info=audio[span.unit_id]
        start,end=cursor,cursor+info.samples
        kind='none'
        if pos<len(units)-1:
            middle=script.spans[i+1:units[pos+1][0]]
            if any('\r' in x.text or '\n' in x.text for x in middle): kind='paragraph'
            elif any(x.boundary=='sentence' for x in (span,*middle)): kind='sentence'
        pause=getattr(setting_samples,kind+'_pause_seconds') if kind!='none' else 0
        cursor=end+pause
        a,b=sample_to_frame(start,fps),sample_to_frame(end,fps)
        clips.append(clip_type(span.unit_id,i,span.start,span.end,span.text,info,info.samples,start,end,kind,pause,cursor,a,b))
        subtitles.append(SubtitleEvent(span.unit_id,span.start,span.end,span.text,start,end,a,b))
        silence(kind,end,cursor,span.unit_id)
        if pos<len(units)-1: boundaries.append(SemanticBoundary(cursor,sample_to_frame(cursor,fps),span.unit_id,span.boundary,kind))
    total=cursor+setting_samples.closing_seconds
    silence('closing',cursor,total,units[-1][1].unit_id)
    total_frames=(total*fps+47999)//48000
    speech=sum(c.samples for c in clips)
    return timeline_type(1,48000,1,2,16,fps,fps!=16,settings,setting_samples,script.text,script.has_bom,
        script.spans,tuple(clips),tuple(subtitles),tuple(silences),speech,total-speech,total,total_frames,
        total_frames*(48000//fps)-total,tuple(boundaries))


def build_timeline(script: SegmentedScript, audio: Mapping[str,AudioInfo], *, settings: TimelineSettings, fps: int) -> Timeline:
    return _canonical(script,audio,settings=settings,fps=fps)


def validate_timeline(timeline: Timeline) -> None:
    if not isinstance(timeline,Timeline): raise ValueError('expected Timeline')
    try:
        # Canonical reconstruction checks all positions, totals, text, silence and subtitle relationships.
        ids=[c.unit_id for c in timeline.clips]
        if len(set(ids))!=len(ids): raise ValueError('duplicate timeline clip')
        expected=_canonical(SegmentedScript(timeline.original_text,timeline.has_bom,timeline.source_spans),
            {c.unit_id:c.pcm for c in timeline.clips},settings=timeline.effective_settings,fps=timeline.output_fps)
        # JSON comparison also distinguishes bool from int (Python equality does not).
        if json.dumps(thaw(expected),sort_keys=True,allow_nan=False)!=json.dumps(thaw(timeline),sort_keys=True,allow_nan=False):
            raise ValueError('timeline differs from canonical sample coverage')
    except (TypeError,AttributeError,KeyError) as exc: raise ValueError('invalid timeline field') from exc


def associate_units(timeline: Timeline, start_frame: int, end_frame: int) -> tuple[str,...]:
    validate_timeline(timeline)
    _integer(start_frame,'start_frame'); _integer(end_frame,'end_frame',1)
    if not start_frame<end_frame<=timeline.total_frames: raise ValueError('slot range outside timeline')
    a=start_frame*(48000//timeline.output_fps)
    b=min(end_frame*(48000//timeline.output_fps),timeline.total_samples)
    return tuple(c.unit_id for c in timeline.clips if max(a,c.start_sample)<min(b,c.end_sample))


@dataclass(frozen=True)
class SlotRange:
    shot_id: str
    start_frame: int
    end_frame: int


@dataclass(frozen=True)
class ShotBudget:
    shot_id: str
    core_start_frame: int
    core_end_frame: int
    coverage_start_frame: int
    coverage_end_frame: int
    incoming_overlap_frames: int
    outgoing_overlap_frames: int
    associated_unit_ids: tuple[str,...]
    required_output_frames: int
    required_native_frames: int
    wan_frames: int
    native_trim_frames: int


@dataclass(frozen=True)
class TransitionBudget:
    left_shot_id: str
    right_shot_id: str
    boundary_frame: int
    requested_frames: int
    actual_frames: int
    start_frame: int
    end_frame: int
    limited_reason: str | None


@dataclass(frozen=True)
class VisualBudget:
    output_fps: int
    native_fps: int
    total_frames: int
    shots: tuple[ShotBudget,...]
    transitions: tuple[TransitionBudget,...]

    def as_dict(self): return thaw(self)


def budget_slots(timeline: Timeline, slots: Sequence[SlotRange], *, transition: str, transition_seconds: int | float) -> VisualBudget:
    validate_timeline(timeline)
    seconds_to_samples(transition_seconds)
    if transition not in ('cut','fade') or (transition=='cut' and transition_seconds!=0) or (transition=='fade' and transition_seconds<=0):
        raise ValueError('cut requires zero; fade requires positive seconds')
    requested=int((Decimal(str(transition_seconds))*timeline.output_fps).to_integral_value(rounding=ROUND_HALF_UP))
    if transition=='fade' and requested==0: raise ValueError('fade shorter than one frame')
    cursor=0
    for i,s in enumerate(slots,1):
        if not isinstance(s,SlotRange) or s.shot_id!=f'shot_{i:04d}': raise ValueError('nonsequential slot ID')
        _integer(s.start_frame,'start_frame'); _integer(s.end_frame,'end_frame',1)
        if s.start_frame!=cursor or s.end_frame<=cursor: raise ValueError('slot gap/overlap/order')
        cursor=s.end_frame
    if not slots or cursor!=timeline.total_frames: raise ValueError('slots must cover complete timeline')
    transitions=[]
    for left,right in zip(slots,slots[1:]):
        length=min(requested,left.end_frame-left.start_frame,right.end_frame-right.start_frame)
        b=left.end_frame
        transitions.append(TransitionBudget(left.shot_id,right.shot_id,b,requested,length,b-length//2,
            b+length-length//2,'short_adjacent_slot' if length<requested else None))
    if any(l.end_frame>r.start_frame for l,r in zip(transitions,transitions[1:])): raise ValueError('overlapping transition windows')
    shots=[]
    for i,s in enumerate(slots):
        incoming=transitions[i-1].actual_frames if i else 0
        outgoing=transitions[i].actual_frames if i<len(transitions) else 0
        a=s.start_frame-incoming//2; b=s.end_frame+outgoing-outgoing//2
        output=b-a
        native=(output*16+timeline.output_fps-1)//timeline.output_fps
        wan=1+4*((max(0,native-1)+3)//4)
        shots.append(ShotBudget(s.shot_id,s.start_frame,s.end_frame,a,b,incoming,outgoing,
            associate_units(timeline,s.start_frame,s.end_frame),output,native,wan,wan-native))
    if sum(s.required_output_frames for s in shots)-sum(t.actual_frames for t in transitions)!=timeline.total_frames:
        raise ValueError('visual coverage budget mismatch')
    return VisualBudget(timeline.output_fps,16,timeline.total_frames,tuple(shots),tuple(transitions))
