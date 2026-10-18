"""Immutable Wan source budgets and continuous review associations, without I/O."""
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, fields
import json
import re
from types import MappingProxyType

from ..runtime.manifest import _identity, thaw
from .start_images import validate_dimensions
from .timeline import Timeline, SlotRange, budget_slots

# Exact negative text from the fixed Wan graph. Runtime must verify the graph
# against this literal as part of its full workflow validation.
WAN_NEGATIVE = '色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走'


def _freeze(value):
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise ValueError('plan mapping keys must be strings')
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(v) for v in value)
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise ValueError('unsupported nested plan value')


@dataclass(frozen=True)
class SourceClipPlan:
    shot_id: str
    primary_unit_id: str
    budget: Mapping[str, object]
    parameters: Mapping[str, object]
    start_image_identity: Mapping[str, object]

    def __post_init__(self):
        for key in ('budget', 'parameters', 'start_image_identity'):
            value = getattr(self, key)
            if not isinstance(value, Mapping):
                raise ValueError('plan fields must be mappings')
            object.__setattr__(self, key, _freeze(value))


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name}: expected integer >= {minimum}')
    return value


def _same(left, right):
    return json.dumps(thaw(left), sort_keys=True, allow_nan=False) == json.dumps(thaw(right), sort_keys=True, allow_nan=False)


def _complete_identity(value):
    _identity(value)
    if any(value[k] is None for k in value):
        raise ValueError('complete verified file identity required')
    if any(part in ('.', '..') for part in re.split(r'[/\\]', value['path'])):
        raise ValueError('file identity path aliases forbidden')
    return deepcopy(value)


def _fps(value):
    if type(value) is not int or value not in (16, 24):
        raise ValueError('output fps must be 16 or 24')
    return value


def _wan_frames(required):
    return 1 + 4 * ((max(0, required-1) + 3)//4)


def _budget(value, shot_id, fps):
    names = set('shot_id core_start_frame core_end_frame coverage_start_frame coverage_end_frame incoming_overlap_frames outgoing_overlap_frames associated_unit_ids required_output_frames required_native_frames wan_frames native_trim_frames'.split())
    if not isinstance(value, Mapping) or set(value) != names or value['shot_id'] != shot_id:
        raise ValueError('invalid complete shot budget')
    for key in names - {'shot_id', 'associated_unit_ids'}:
        _integer(value[key], key)
    ids = value['associated_unit_ids']
    if not isinstance(ids, (list, tuple)) or not ids or any(not isinstance(uid, str) or not uid for uid in ids) or len(set(ids)) != len(ids):
        raise ValueError('invalid associated units')
    a, b = value['coverage_start_frame'], value['coverage_end_frame']
    c, d = value['core_start_frame'], value['core_end_frame']
    output, native = value['required_output_frames'], value['required_native_frames']
    if not a <= c < d <= b or output != b-a or native != (output*16+fps-1)//fps or value['wan_frames'] != _wan_frames(native) or value['native_trim_frames'] != value['wan_frames']-native:
        raise ValueError('invalid shot budget ranges/frame counts')
    return value


def plan_source_clips(storyboard: dict, timeline: dict, images: dict) -> tuple[SourceClipPlan, ...]:
    try:
        names = {f.name for f in fields(Timeline)}
        metadata = {'run_id', 'status', 'passed', 'created_at', 'provenance', 'validation'}
        if not isinstance(timeline, dict) or not names <= set(timeline) or set(timeline)-names-metadata:
            raise ValueError('invalid timeline fields')
        canonical = Timeline.from_dict({key: timeline[key] for key in names})
        run_id = storyboard['run_id']
        if images['run_id'] != run_id or ('run_id' in timeline and timeline['run_id'] != run_id):
            raise ValueError('input run identities differ')
        media = storyboard['effective_media']
        fps = _fps(media['fps'])
        if fps != canonical.output_fps or type(media['native_fps']) is not int or media['native_fps'] != 16:
            raise ValueError('timeline/media rate differs')
        profile = media['profile']
        if set(profile) != {'name', 'width', 'height', 'native_fps'}:
            raise ValueError('invalid media profile fields')
        dimensions = {'fast': (768, 432), 'quality': (1280, 720)}
        width, height = validate_dimensions(profile['width'], profile['height'])
        if dimensions.get(profile['name']) != (width, height) or type(profile['native_fps']) is not int or profile['native_fps'] != 16:
            raise ValueError('invalid source media profile')
        shots = storyboard['shots']
        if not isinstance(shots, list) or not shots:
            raise ValueError('shots required')
        budgets = budget_slots(canonical, [SlotRange(s['shot_id'], s['start_frame'], s['end_frame']) for s in shots],
            transition=media['transition'], transition_seconds=media['transition_seconds'])
        if not _same(storyboard['transitions'], budgets.transitions):
            raise ValueError('frozen transitions differ from timeline')
        image_rows = images['images']
        if not isinstance(image_rows, list) or [r['shot_id'] for r in image_rows] != [s['shot_id'] for s in shots]:
            raise ValueError('start images must match frozen shot order exactly')
        global_visual = storyboard['global_visual']
        entities = global_visual['entities']
        descriptions = {e['entity_id']: e['description'] for e in entities}
        if len(descriptions) != len(entities) or any(not isinstance(d, str) or not d.strip() for d in descriptions.values()):
            raise ValueError('invalid entity descriptions')
        if any(not isinstance(global_visual[k], str) or not global_visual[k].strip() for k in ('style', 'color_palette', 'lighting')):
            raise ValueError('global visual descriptions required')
        result = []
        for ordinal, (shot, budget, image) in enumerate(zip(shots, budgets.shots, image_rows), 1):
            if not _same(shot['budget'], budget):
                raise ValueError('frozen shot budget differs from timeline')
            _budget(shot['budget'], shot['shot_id'], fps)
            primary = shot['primary_unit_id']
            if primary not in shot['budget']['associated_unit_ids'] or image['primary_unit_id'] != primary:
                raise ValueError('primary unit/image association differs')
            original = shot['video_prompt']
            if not isinstance(original, str) or not original.strip():
                raise ValueError('original video prompt required')
            if not isinstance(shot['entity_ids'], list) or len(set(shot['entity_ids'])) != len(shot['entity_ids']):
                raise ValueError('invalid shot entity IDs')
            positive = original + '\n' + '\n'.join(f'{k}: {global_visual[k]}' for k in ('style', 'color_palette', 'lighting'))
            for eid in shot['entity_ids']:
                positive += f'\nentity {eid}: {descriptions[eid]}'
            seed = 264244520398999 + ordinal-1
            if not 0 <= seed < 2**64:
                raise ValueError('Wan seed outside uint64')
            parameters = dict(positive=positive, negative=WAN_NEGATIVE, seed_high=seed, seed_low=0,
                width=width, height=height, length=budget.wan_frames, fps=16, batch=1, steps=40,
                cfg=3.5, sampler='euler', scheduler='simple', split_step=15,
                shift_high=5.000000000000001, shift_low=5.000000000000001, lora_enabled=False)
            result.append(SourceClipPlan(shot['shot_id'], primary, shot['budget'], parameters, _complete_identity(image['image_identity'])))
        return tuple(result)
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError('invalid source clip planning input') from exc


def supplement_frames(*, requested_frames: int, required_native_frames: int, actual_frames: int) -> int:
    for name, value in (('requested_frames', requested_frames), ('required_native_frames', required_native_frames), ('actual_frames', actual_frames)):
        _integer(value, name, 1)
    if requested_frames != _wan_frames(required_native_frames) or not actual_frames < required_native_frames:
        raise ValueError('supplement requires a proven short first attempt')
    return requested_frames + 4*((required_native_frames-actual_frames+3)//4)


def _mapping(shot_id, budget, generated_identity, source_identity, generated_frames, output_fps):
    _fps(output_fps)
    _integer(generated_frames, 'generated_frames', 1)
    budget = _budget(budget, shot_id, output_fps)
    required = budget['required_native_frames']
    if generated_frames < required:
        raise ValueError('generated clip is short')
    return dict(shot_id=shot_id, generated_identity=_complete_identity(generated_identity), source_identity=_complete_identity(source_identity),
        generated_frames=generated_frames, source_frames=required,
        generated_to_source=list(range(required))+[None]*(generated_frames-required),
        coverage_start_frame=budget['coverage_start_frame'], coverage_end_frame=budget['coverage_end_frame'],
        core_start_frame=budget['core_start_frame'], core_end_frame=budget['core_end_frame'],
        output_fps=output_fps, native_fps=16,
        output_to_source=[j*16//output_fps for j in range(budget['required_output_frames'])])


def frame_mapping(plan: SourceClipPlan, *, generated_identity: dict, source_identity: dict, generated_frames: int, output_fps: int) -> dict:
    if not isinstance(plan, SourceClipPlan):
        raise ValueError('SourceClipPlan required')
    return _mapping(plan.shot_id, plan.budget, generated_identity, source_identity, generated_frames, output_fps)


def requirement_clips(storyboard: dict, *, source_identities: dict[str, dict], frame_mappings: dict[str, dict], total_samples: int) -> list[dict]:
    try:
        _integer(total_samples, 'total_samples', 1)
        fps = _fps(storyboard['effective_media']['fps'])
        shots = storyboard['shots']
        ids = [s['shot_id'] for s in shots]
        if not shots or len(set(ids)) != len(ids) or set(source_identities) != set(ids) or set(frame_mappings) != set(ids):
            raise ValueError('complete source/mapping associations required')
        for shot in shots:
            uid = shot['shot_id']; mapped = frame_mappings[uid]
            _integer(shot['start_frame'], 'start_frame')
            _integer(shot['end_frame'], 'end_frame', 1)
            if (shot['start_frame'] != shot['budget']['core_start_frame']
                    or shot['end_frame'] != shot['budget']['core_end_frame']):
                raise ValueError('shot coordinates differ from frozen core interval')
            expected = _mapping(uid, shot['budget'], mapped['generated_identity'], source_identities[uid], mapped['generated_frames'], fps)
            if not _same(mapped, expected):
                raise ValueError('frame mapping differs from frozen coverage/identity')
        result = []
        for shot in shots:
            for index, req in enumerate(shot['visual_requirements']):
                target = shot; role = 'primary'
                if req['unit_id'] != shot['primary_unit_id']:
                    if not any(b['unit_id'] == req['unit_id'] and b.get('quantization_edge') is True for b in shot['bindings']):
                        raise ValueError('foreign requirement is not a quantization edge')
                    candidates = [(i,s) for i,s in enumerate(shots) if s['primary_unit_id'] == req['unit_id']]
                    if not candidates:
                        raise ValueError('edge lacks corresponding primary source')
                    _, target = min(candidates, key=lambda item:(abs(item[1]['start_frame']-shot['start_frame']), item[0]))
                    role = 'quantization_edge_review'
                uid = target['shot_id']; mapped = frame_mappings[uid]
                start, end = mapped['coverage_start_frame'], mapped['coverage_end_frame']
                sample_start, sample_end = min(start*48000//fps, total_samples), min(end*48000//fps, total_samples)
                if sample_start >= sample_end:
                    raise ValueError('requirement source has empty sample range')
                if any(not isinstance(req[k], str) or not req[k].strip() for k in ('requirement_id','unit_id','source_quote')):
                    raise ValueError('requirement identity/text required')
                result.append(dict(shot_id=shot['shot_id'], requirement_id=req['requirement_id'], requirement_index=index,
                    unit_id=req['unit_id'], source_quote=req['source_quote'], clip_shot_id=uid, role=role,
                    actual_artifact=deepcopy(source_identities[uid]), local_frames=dict(start=0,end=mapped['source_frames']),
                    output_frames=dict(start=start,end=end), sample_range=dict(start=sample_start,end=sample_end)))
        return result
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError('invalid requirement clip association') from exc
