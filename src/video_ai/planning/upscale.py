"""Immutable per-shot upscale plans and native16 frame associations; no I/O."""
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
import json
import math
import re
from types import MappingProxyType

from .source_clips import _budget, _complete_identity, _fps, _integer, _same
from .start_images import keys
from ..runtime.manifest import thaw

SOURCE_FIELDS = 'schema_version run_id created_at status passed images_identity storyboard_identity timeline_identity effective_media clips requirement_clips frame_mappings model_identities workflow_identity mapping_identity provenance validation request_evidence review_identity'
CLIP_FIELDS = 'shot_id primary_unit_id budget start_image_identity input_copy_identity selected_attempt_id attempts generated_identity source_identity width height native_fps generated_frames source_frames parameters evidence_identities'
MAPPING_FIELDS = 'shot_id generated_identity source_identity generated_frames source_frames generated_to_source coverage_start_frame coverage_end_frame core_start_frame core_end_frame output_fps native_fps output_to_source'
PARAMETERS = dict(model_name='RealESRGAN_x4plus.pth', model_scale=4,
    resize_method='lanczos', width=1920, height=1080, crop='disabled', native_fps=16, batch=1)


def _freeze(value):
    if isinstance(value, Mapping):
        if any(type(k) is not str for k in value):
            raise ValueError('plan mapping keys must be strings')
        return MappingProxyType({k: _freeze(v) for k,v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError('unsupported or nonfinite nested plan value')


@dataclass(frozen=True)
class UpscalePlan:
    shot_id: str
    primary_unit_id: str
    source_identity: Mapping[str, object]
    source_frames: int
    width: int
    height: int
    native_fps: int
    budget: Mapping[str, object]
    parameters: Mapping[str, object]

    def __post_init__(self):
        for key in ('source_identity', 'budget', 'parameters'):
            value = getattr(self, key)
            if not isinstance(value, Mapping):
                raise ValueError('plan fields must be mappings')
            object.__setattr__(self, key, _freeze(value))


def clip_deadline_seconds(*, frame_count: int, base_seconds: float) -> int:
    _integer(frame_count, 'frame_count', 1)
    if type(base_seconds) not in (int, float) or not math.isfinite(base_seconds) or base_seconds <= 0:
        raise ValueError('base_seconds must be a positive finite number')
    try:
        return max(math.ceil(base_seconds), math.ceil(base_seconds*frame_count/81))
    except OverflowError as exc:
        raise ValueError('clip deadline is not finite') from exc


def _source_mapping(value):
    keys(value, MAPPING_FIELDS, 'source frame mapping')
    shot = value['shot_id']
    if not isinstance(shot, str) or not re.fullmatch(r'shot_[0-9]{4,}', shot) or int(shot[5:]) < 1:
        raise ValueError('valid source shot ID required')
    n = _integer(value['source_frames'], 'source_frames', 1)
    generated = _integer(value['generated_frames'], 'generated_frames', 1)
    if generated < n or type(value['native_fps']) is not int or value['native_fps'] != 16:
        raise ValueError('source native frames/rate differ')
    fps = _fps(value['output_fps'])
    for k in ('coverage_start_frame','coverage_end_frame','core_start_frame','core_end_frame'):
        _integer(value[k], k)
    a,b,c,d = (value[k] for k in ('coverage_start_frame','coverage_end_frame','core_start_frame','core_end_frame'))
    if not a <= c < d <= b or n != ((b-a)*16+fps-1)//fps:
        raise ValueError('source mapping coverage/core/native counts differ')
    for key,expected in (
        ('generated_to_source',list(range(n))+[None]*(generated-n)),
        ('output_to_source',[i*16//fps for i in range(b-a)])):
        actual=value[key]
        if not isinstance(actual,list) or len(actual)!=len(expected) or any(
            type(item) is not type(want) or item!=want for item,want in zip(actual,expected)):
            raise ValueError('source frame association differs')
    _complete_identity(value['generated_identity'])
    _complete_identity(value['source_identity'])
    return value


def upscale_frame_mapping(source_mapping: dict, *, upscaled_identity: dict) -> dict:
    try:
        source=_source_mapping(source_mapping)
        result={k:deepcopy(source[k]) for k in ('shot_id','source_identity','source_frames',
            'native_fps','output_fps','coverage_start_frame','coverage_end_frame','core_start_frame','core_end_frame')}
        result.update(upscaled_identity=_complete_identity(upscaled_identity),
            upscaled_frames=source['source_frames'],source_to_upscaled=list(range(source['source_frames'])),
            output_to_upscaled=deepcopy(source['output_to_source']))
        return result
    except (KeyError,TypeError,AttributeError,OverflowError) as exc:
        raise ValueError('invalid upscale frame mapping input') from exc


def plan_upscale(source_clips: dict) -> tuple[UpscalePlan, ...]:
    try:
        keys(source_clips, SOURCE_FIELDS, 'committed source clips')
        # Reject non-JSON/nonfinite nested values before copying into a plan.
        _freeze(source_clips)
        json.dumps(source_clips, allow_nan=False)
        if type(source_clips['schema_version']) is not int or source_clips['schema_version'] != 1 or source_clips['status'] != 'completed' or source_clips['passed'] is not True:
            raise ValueError('completed committed source clips required')
        validation=source_clips['validation']
        keys(validation,'structure_passed media_passed video_text_semantics_passed motion_semantics_passed ready_for_upscale final_video_sync full_film_acceptance','source validation')
        if any(type(validation[k]) is not bool for k in ('structure_passed','media_passed','video_text_semantics_passed','motion_semantics_passed','ready_for_upscale')) or any(validation[k] is not True for k in ('structure_passed','media_passed','ready_for_upscale')) or any(validation[k]!='unverified' for k in ('final_video_sync','full_film_acceptance')):
            raise ValueError('source readiness/validation differs')
        media=source_clips['effective_media']
        keys(media,'fps native_fps profile image_aspect_ratio default_image_width default_image_height transition transition_seconds','effective source media')
        fps=_fps(media['fps']);profile=media['profile']
        keys(profile,'name width height native_fps','source profile')
        dimensions={'fast':(768,432),'quality':(1280,720)}.get(profile['name'])
        if dimensions is None or any(type(profile[k]) is not int for k in ('width','height','native_fps')) or (profile['width'],profile['height'])!=dimensions or profile['native_fps']!=16 or type(media['native_fps']) is not int or media['native_fps']!=16 or media['image_aspect_ratio']!='16:9':
            raise ValueError('source media profile/rate differs')
        clips=source_clips['clips'];mappings=source_clips['frame_mappings']
        if not isinstance(clips,list) or not clips or not isinstance(mappings,list) or len(mappings)!=len(clips):
            raise ValueError('complete ordered source clips/mappings required')
        seen=set();result=[]
        for clip,mapped in zip(clips,mappings):
            keys(clip,CLIP_FIELDS,'source clip');_source_mapping(mapped)
            shot=clip['shot_id']
            if shot in seen or shot!=mapped['shot_id']:
                raise ValueError('unique ordered source/mapping shots required')
            seen.add(shot)
            budget=_budget(clip['budget'],shot,fps)
            primary=clip['primary_unit_id']
            if primary not in budget['associated_unit_ids']:
                raise ValueError('source primary unit differs from budget')
            for key,want in (('width',dimensions[0]),('height',dimensions[1]),('native_fps',16),
                             ('source_frames',budget['required_native_frames']),('generated_frames',mapped['generated_frames'])):
                if type(clip[key]) is not int or clip[key]!=want:
                    raise ValueError('source clip dimensions/count/rate differ')
            if mapped['source_frames']!=clip['source_frames'] or mapped['output_fps']!=fps or any(mapped[k]!=budget[k] for k in ('coverage_start_frame','coverage_end_frame','core_start_frame','core_end_frame')) or not _same(mapped['source_identity'],clip['source_identity']) or not _same(mapped['generated_identity'],clip['generated_identity']):
                raise ValueError('source mapping differs from clip/budget')
            result.append(UpscalePlan(shot,primary,_complete_identity(clip['source_identity']),
                clip['source_frames'],1920,1080,16,budget,PARAMETERS))
        return tuple(result)
    except (KeyError,TypeError,AttributeError,OverflowError) as exc:
        raise ValueError('invalid upscale planning input') from exc
