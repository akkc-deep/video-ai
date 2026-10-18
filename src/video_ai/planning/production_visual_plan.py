"""Native16/cut production budgets and stamp plans, without review or I/O."""
from collections.abc import Mapping
from dataclasses import dataclass
import re

from .production_timeline import validate_production_timeline
from .source_clips import _budget, _freeze, _integer, _same, _wan_frames, WAN_NEGATIVE
from .start_images import validate_dimensions
from .storyboard import StoryboardSlot
from .timeline import ShotBudget, VisualBudget
from ..runtime.manifest import thaw
from ..runtime.production_state import ArtifactStamp


def plan_scene_clips(scene_plan, *, max_clip_seconds) -> list[dict]:
    """Budget scene contributions and future continuation sources without I/O."""
    from ..config import _scene_clip_limit

    limit = _scene_clip_limit(max_clip_seconds)
    if not isinstance(scene_plan, Mapping):
        raise ValueError('scene plan mapping required')
    scenes = scene_plan.get('scenes')
    if not isinstance(scenes, (list, tuple)) or not scenes:
        raise ValueError('nonempty scene list required')
    clips = []
    cursor = 0
    seen = set()
    for scene in scenes:
        if not isinstance(scene, Mapping):
            raise ValueError('scene mapping required')
        scene_id = scene.get('scene_id')
        if not isinstance(scene_id, str) or not scene_id.strip() or scene_id in seen:
            raise ValueError('unique nonempty scene_id required')
        seen.add(scene_id)
        start = _integer(scene.get('start_frame'), 'start_frame')
        end = _integer(scene.get('end_frame'), 'end_frame', 1)
        if start != cursor or end <= start:
            raise ValueError('scene frames must be positive and continuous from zero')
        parent = None
        ordinal = 1
        while cursor < end:
            head = 0 if parent is None else 1
            retained = min(end - cursor, limit - head)
            generated = _wan_frames(retained + head)
            clip_id = f'{scene_id}_clip_{ordinal:04d}'
            clips.append(dict(
                clip_id=clip_id, scene_id=scene_id, ordinal=ordinal,
                parent_clip_id=parent,
                input_kind='selected_scene_image' if parent is None else 'parent_retained_last_frame',
                start_frame=cursor, end_frame=cursor + retained,
                retained_frames=retained, generated_frames=generated,
                discard_head_frames=head, trim_tail_frames=generated - head - retained,
                retained_source_start=head, retained_source_end=head + retained))
            cursor += retained
            parent = clip_id
            ordinal += 1
    if 'total_frames' in scene_plan:
        if _integer(scene_plan['total_frames'], 'total_frames', 1) != cursor:
            raise ValueError('scene coverage differs from total_frames')
    return clips


@dataclass(frozen=True)
class ProductionSourceClipPlan:
    shot_id: str
    primary_unit_id: str
    budget: Mapping
    parameters: Mapping
    start_image_stamp: ArtifactStamp

    def __post_init__(self):
        _budget(self.budget, self.shot_id, 16)
        if self.primary_unit_id not in self.budget['associated_unit_ids']:
            raise ValueError('primary unit outside source budget')
        if not isinstance(self.start_image_stamp, ArtifactStamp): raise ValueError('ArtifactStamp required')
        for key in ('budget','parameters'):
            if not isinstance(getattr(self,key),Mapping): raise ValueError('plan mapping required')
            object.__setattr__(self,key,_freeze(getattr(self,key)))


def build_production_budgets(timeline, slots):
    validate_production_timeline(timeline)
    if timeline.output_fps != 16: raise ValueError('production requires native16')
    cursor=0; budgets=[]; units={c.unit_id for c in timeline.clips}
    for i,s in enumerate(slots,1):
        if not isinstance(s,StoryboardSlot) or s.shot_id!=f'shot_{i:04d}': raise ValueError('fixed sequential shots required')
        _integer(s.start_frame,'start_frame'); _integer(s.end_frame,'end_frame',1)
        if s.start_frame!=cursor or not cursor<s.end_frame<=timeline.total_frames: raise ValueError('slot gap/overlap/range')
        associated=tuple(dict.fromkeys(b.unit_id for b in s.bindings))
        if not associated or set(associated)-units or s.primary_unit_id not in associated: raise ValueError('invalid slot bindings')
        required=s.end_frame-s.start_frame; wan=_wan_frames(required)
        budgets.append(ShotBudget(s.shot_id,s.start_frame,s.end_frame,s.start_frame,s.end_frame,
                                  0,0,associated,required,required,wan,wan-required))
        cursor=s.end_frame
    if not budgets or cursor!=timeline.total_frames: raise ValueError('slots must cover complete timeline')
    return VisualBudget(16,16,cursor,tuple(budgets),())


def plan_production_source_clips(storyboard, timeline, images, *, model_visual=False):
    from .storyboard import Binding
    slots=tuple(StoryboardSlot(s['shot_id'],s['start_frame'],s['end_frame'],s['primary_unit_id'],
                               tuple(Binding(**b) for b in s['bindings'])) for s in storyboard['shots'])
    budgets=build_production_budgets(timeline,slots)
    media=storyboard['effective_media']; profile=media['profile']
    if media['fps']!=16 or type(media['fps']) is not int or media['native_fps']!=16 or media['transition']!='cut' or storyboard['transitions']!=[]:
        raise ValueError('only native16/cut supported')
    w,h=validate_dimensions(profile['width'],profile['height'])
    if {'fast':(768,432),'quality':(1280,720)}.get(profile['name'])!=(w,h): raise ValueError('invalid profile')
    rows=images['images']
    if [r['shot_id'] for r in rows]!=[s.shot_id for s in slots]: raise ValueError('image order/coverage differs')
    g=storyboard['global_visual']; entities={e['entity_id']:e['description'] for e in g['entities']}
    result=[]
    for i,(shot,budget,image) in enumerate(zip(storyboard['shots'],budgets.shots,rows),1):
        if not _same(shot['budget'],budget) or image['primary_unit_id']!=shot['primary_unit_id']: raise ValueError('image/budget association differs')
        positive=shot['video_prompt']+'\n'+'\n'.join(f'{k}: {g[k]}' for k in ('style','color_palette','lighting'))
        for eid in shot['entity_ids']: positive+=f'\nentity {eid}: {entities[eid]}'
        if model_visual:
            from .model_visual_prompts import render_model_prompt
            positive=render_model_prompt(shot,g,'video')
        p=dict(positive=positive,negative=WAN_NEGATIVE,seed_high=264244520398999+i-1,seed_low=0,
               width=w,height=h,length=budget.wan_frames,fps=16,batch=1,steps=40,cfg=3.5,
               sampler='euler',scheduler='simple',split_step=15,shift_high=5.000000000000001,
               shift_low=5.000000000000001,lora_enabled=False)
        result.append(ProductionSourceClipPlan(shot['shot_id'],shot['primary_unit_id'],thaw(budget),p,
                                               ArtifactStamp.from_dict(image['image'])))
    return tuple(result)


def production_frame_mapping(plan, *, generated_frames):
    if not isinstance(plan,ProductionSourceClipPlan): raise ValueError('production plan required')
    _integer(generated_frames,'generated_frames',1)
    b=plan.budget; required=b['required_native_frames']
    if generated_frames<required: raise ValueError('generated clip is short')
    return dict(shot_id=plan.shot_id,coverage_start_frame=b['coverage_start_frame'],coverage_end_frame=b['coverage_end_frame'],
                core_start_frame=b['core_start_frame'],core_end_frame=b['core_end_frame'],native_fps=16,output_fps=16,
                generated_frames=generated_frames,source_frames=required,
                generated_to_source=list(range(required))+[None]*(generated_frames-required),output_to_source=list(range(required)))


@dataclass(frozen=True)
class ProductionUpscalePlan:
    shot_id: str
    source_stamp: ArtifactStamp
    source_frames: int
    budget: Mapping
    parameters: Mapping

    def __post_init__(self):
        from .upscale import PARAMETERS
        if not isinstance(self.shot_id,str) or re.fullmatch(r'shot_[0-9]{4}',self.shot_id) is None or self.shot_id=='shot_0000':raise ValueError('production shot ID required')
        _integer(self.source_frames,'source_frames',1)
        b=_budget(self.budget,self.shot_id,16)
        if (not isinstance(self.source_stamp,ArtifactStamp) or self.source_frames!=b['required_native_frames']
            or b['incoming_overlap_frames'] or b['outgoing_overlap_frames']
            or b['coverage_start_frame']!=b['core_start_frame'] or b['coverage_end_frame']!=b['core_end_frame']
            or not _same(self.parameters,PARAMETERS)):
            raise ValueError('fixed native16/cut production upscale plan required')
        for key in ('budget','parameters'):object.__setattr__(self,key,_freeze(getattr(self,key)))


def production_upscale_frame_mapping(source_mapping, *, upscaled_frames):
    from .start_images import keys
    keys(source_mapping,'shot_id coverage_start_frame coverage_end_frame core_start_frame core_end_frame native_fps output_fps generated_frames source_frames generated_to_source output_to_source','production source mapping')
    m=source_mapping;n=_integer(m['source_frames'],'source_frames',1)
    if not isinstance(m['shot_id'],str) or re.fullmatch(r'shot_[0-9]{4}',m['shot_id']) is None or m['shot_id']=='shot_0000':raise ValueError('production shot ID required')
    _integer(upscaled_frames,'upscaled_frames',1);g=_integer(m['generated_frames'],'generated_frames',1)
    for key in ('coverage_start_frame','coverage_end_frame','core_start_frame','core_end_frame','native_fps','output_fps'):_integer(m[key],key)
    a,b=m['coverage_start_frame'],m['coverage_end_frame']
    if (upscaled_frames!=n or g<n or m['native_fps']!=16 or m['output_fps']!=16 or b-a!=n
        or m['core_start_frame']!=a or m['core_end_frame']!=b
        or not _same(m['generated_to_source'],list(range(n))+[None]*(g-n)) or not _same(m['output_to_source'],list(range(n)))):
        raise ValueError('source mapping must retain exact native16/cut prefix')
    result={key:m[key] for key in ('shot_id','coverage_start_frame','coverage_end_frame','core_start_frame','core_end_frame','native_fps','output_fps','source_frames')}
    return dict(result,upscaled_frames=n,source_to_upscaled=list(range(n)),output_to_upscaled=list(range(n)))


def plan_production_upscale(source_clips):
    from .start_images import keys
    from .upscale import PARAMETERS
    keys(source_clips,'clips frame_mappings','production source clips')
    clips,mappings=source_clips['clips'],source_clips['frame_mappings']
    if not isinstance(clips,list) or not clips or not isinstance(mappings,list) or len(clips)!=len(mappings):raise ValueError('ordered clips/mappings required')
    result=[];cursor=0
    for ordinal,(clip,mapping) in enumerate(zip(clips,mappings),1):
        keys(clip,'shot_id primary_unit_id budget parameters start_image generated source native_fps generated_frames source_frames submission','production source clip')
        sid=f'shot_{ordinal:04d}'
        if clip['shot_id']!=sid or mapping['shot_id']!=sid:raise ValueError('original clip order required')
        for key in ('source_frames','generated_frames','native_fps'):_integer(clip[key],key,1)
        mapped=production_upscale_frame_mapping(mapping,upscaled_frames=clip['source_frames'])
        b=_budget(clip['budget'],sid,16)
        if (clip['native_fps']!=16 or clip['generated_frames']!=mapping['generated_frames']
            or clip['primary_unit_id'] not in b['associated_unit_ids'] or b['coverage_start_frame']!=cursor
            or any(b[key]!=mapped[key] for key in ('coverage_start_frame','coverage_end_frame','core_start_frame','core_end_frame'))
            or (clip['parameters'].get('width'),clip['parameters'].get('height')) not in ((768,432),(1280,720))):
            raise ValueError('original source budget/profile/coverage differs')
        result.append(ProductionUpscalePlan(sid,ArtifactStamp.from_dict(clip['source']),clip['source_frames'],b,PARAMETERS))
        cursor=b['coverage_end_frame']
    return tuple(result)
