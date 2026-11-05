"""Pure native temporal budgets and visual requests; no model or filesystem I/O."""
from collections.abc import Mapping
from copy import deepcopy
import re

from ..runtime.manifest import thaw
from .scene_clip_continuation import BUDGET_FIELDS, _artifact, _fields, _narration, _budgets
from .source_clips import _integer
from .visual_consistency import KINDS, validate_reference_graph

MODE = 'temporal_extension_v1'
PROTOCOL = 'longcat_native16_v1'
CLOCK_POLICY = 'predeclared_deployment_clock_16_no_model_fps_condition_v1'
NEGATIVE = ('Bright tones, overexposed, static, blurred details, subtitles, style, works, paintings, '
            'images, static, overall gray, worst quality, low quality, JPEG compression residue, ugly, '
            'incomplete, extra fingers, poorly drawn hands, poorly drawn faces, deformed, disfigured, '
            'misshapen limbs, fused fingers, still picture, messy background, three legs, many people '
            'in the background, walking backwards')


def validate_temporal_clip(clip) -> dict:
    _fields(clip, BUDGET_FIELDS+['protocol'], 'temporal clip budget')
    if clip['protocol'] != PROTOCOL:
        raise ValueError('unknown temporal protocol')
    for key in set(BUDGET_FIELDS)-{'clip_id', 'scene_id', 'parent_clip_id', 'input_kind'}:
        _integer(clip[key], key, 1 if key in {'ordinal', 'retained_frames', 'generated_frames', 'end_frame', 'retained_source_end'} else 0)
    sid, ordinal = clip['scene_id'], clip['ordinal']
    if (not isinstance(sid, str) or re.fullmatch(r'scene_[0-9]{4,}', sid) is None
            or int(sid[6:]) < 1 or clip['clip_id'] != f'{sid}_clip_{ordinal:04d}'):
        raise ValueError('exact temporal clip identity required')
    parent = None if ordinal == 1 else f'{sid}_clip_{ordinal-1:04d}'
    head = 0 if parent is None else 13
    retained = clip['retained_frames']
    if (clip['parent_clip_id'] != parent
            or clip['input_kind'] != ('selected_scene_image' if parent is None else 'parent_native_tail_13')
            or clip['generated_frames'] != 93 or retained > 93-head
            or clip['discard_head_frames'] != head or clip['retained_source_start'] != head
            or clip['retained_source_end'] != head+retained
            or clip['end_frame']-clip['start_frame'] != retained
            or clip['trim_tail_frames'] != 93-head-retained):
        raise ValueError('temporal history/retention budget differs')
    return deepcopy(thaw(clip))


def derive_temporal_clips(plan, timeline) -> list[dict]:
    from .scene_execution import _frames
    if not isinstance(plan, Mapping): raise ValueError('scene plan required')
    total = _frames(timeline)
    if _integer(plan.get('total_frames'), 'plan.total_frames', 1) != total:
        raise ValueError('scene plan differs from timeline')
    scenes = plan.get('scenes')
    if not isinstance(scenes, (list, tuple)) or not scenes:
        raise ValueError('ordered nonempty scenes required')
    result, seen, cursor = [], set(), 0
    for scene in scenes:
        if not isinstance(scene, Mapping): raise ValueError('scene mapping required')
        sid = scene.get('scene_id')
        if (not isinstance(sid, str) or re.fullmatch(r'scene_[0-9]{4,}', sid) is None
                or int(sid[6:]) < 1 or sid in seen):
            raise ValueError('unique exact scene identity required')
        seen.add(sid)
        start = _integer(scene.get('start_frame'), 'start_frame')
        end = _integer(scene.get('end_frame'), 'end_frame', 1)
        if start != cursor or end <= start:
            raise ValueError('scene frames must cover continuously from zero')
        ordinal = 1
        while cursor < end:
            head = 0 if ordinal == 1 else 13
            retained = min(93-head, end-cursor)
            result.append(validate_temporal_clip(dict(
                clip_id=f'{sid}_clip_{ordinal:04d}', scene_id=sid, ordinal=ordinal,
                parent_clip_id=None if ordinal == 1 else f'{sid}_clip_{ordinal-1:04d}',
                input_kind='selected_scene_image' if ordinal == 1 else 'parent_native_tail_13',
                start_frame=cursor, end_frame=cursor+retained, retained_frames=retained,
                generated_frames=93, discard_head_frames=head, trim_tail_frames=93-head-retained,
                retained_source_start=head, retained_source_end=head+retained, protocol=PROTOCOL)))
            cursor += retained
            ordinal += 1
    if cursor != total: raise ValueError('scene coverage differs from full timeline')
    return result


def temporal_frame_mapping(clip, *, actual_generated_frames) -> dict:
    clip = validate_temporal_clip(clip)
    if _integer(actual_generated_frames, 'actual_generated_frames', 1) != 93:
        raise ValueError('temporal generated frame count must equal 93')
    a, b = clip['retained_source_start'], clip['retained_source_end']
    return dict(clip_id=clip['clip_id'], scene_id=clip['scene_id'], native_fps=16, output_fps=16,
        output_clock_policy=CLOCK_POLICY, generated_frames=93, retained_frames=clip['retained_frames'],
        start_frame=clip['start_frame'], end_frame=clip['end_frame'],
        generated_to_retained=[j-a if a <= j < b else None for j in range(93)],
        retained_to_generated=list(range(a, b)),
        output_to_generated=[dict(output_frame=clip['start_frame']+k, generated_frame=j)
                             for k, j in enumerate(range(a, b))])


def build_scene_temporal_plan(frozen, bible, plan, timeline, image_inputs, *, prompt_contract,
                              prompt_binding_context=None, execution) -> list[dict]:
    from .scene_video_prompts import parse_scene_rendering, validate_scene_video_prompt_contract, render_scene_video_prompt
    if not isinstance(execution, Mapping) or execution.get('mode') != MODE:
        raise ValueError('native temporal execution budget required')
    clips = _budgets(plan, timeline, execution=execution)
    settings = parse_scene_rendering(frozen.config.raw.get('scene_rendering'))
    if settings.get('mode') != MODE or prompt_contract.get('schema_version') != 3:
        raise ValueError('native mode and schema3 reviewed prompt required')
    profile = frozen.config.media.profile
    if (profile.name != 'fast' or (profile.width, profile.height, profile.native_fps) != (768, 432, 16)
            or any(type(v) is not int for v in (profile.width, profile.height, profile.native_fps, frozen.config.media.fps))
            or frozen.config.media.fps != 16 or frozen.config.media.transition != 'cut'):
        raise ValueError('temporal requires fast 768x432 native16/cut')
    _narration(plan, timeline)
    validate_reference_graph(thaw(plan['scenes']), thaw(bible))
    binding = prompt_binding_context if prompt_binding_context is not None else dict(
        bible=bible, plan=plan, wan_inputs=image_inputs, script=frozen.script)
    _fields(binding, ('bible', 'plan', 'wan_inputs', 'script'), 'prompt binding context')
    validate_scene_video_prompt_contract(prompt_contract, **binding, execution=execution)
    if [row['clip_id'] for row in prompt_contract['clips']] != [row['clip_id'] for row in clips]:
        raise ValueError('temporal visual prompt coverage differs')
    scenes = {row['scene_id']: row for row in plan['scenes']}
    selected = image_inputs['scenes']
    if [row['scene_id'] for row in selected] != list(scenes):
        raise ValueError('accepted images must follow complete scene plan')
    images = {row['scene_id']: row for row in selected}
    for row in selected: _artifact(row)
    comparisons = {}
    for sid, scene in scenes.items():
        uses = set()
        for kind, name, field, scene_field in KINDS:
            ids = [scene[scene_field]] if kind == 'scene_group' else scene[scene_field]
            uses.update((kind, item) for item in ids)
        comparisons[sid] = []
        for baseline in bible['baselines']:
            if (baseline['kind'], baseline['id']) in uses:
                image = images[baseline['scene_id']]
                comparisons[sid].append(dict(kind=baseline['kind'], id=baseline['id'],
                    scene_id=baseline['scene_id'], candidate_id=image['candidate_id'], image=_artifact(image)))
    seed_indices = {sid: index for index, sid in enumerate(scenes)}
    rows = []
    for clip in clips:
        sid = clip['scene_id']
        bindings = []
        for original in scenes[sid]['bindings']:
            start = max(clip['start_frame']*3000, original['start_sample'])
            end = min(clip['end_frame']*3000, timeline.total_samples, original['end_sample'])
            if start < end: bindings.append(dict(thaw(original), start_sample=start, end_sample=end))
        rows.append(dict(budget=deepcopy(clip),
            parameters=dict(positive=render_scene_video_prompt(prompt_contract, bible, scenes[sid], clip['clip_id']),
                negative=NEGATIVE, seed=264244520398999+seed_indices[sid], width=768, height=432,
                length=93, fps=16, output_clock_policy=CLOCK_POLICY, steps=50, cfg=4.0,
                resolution='432p-native16', num_cond_frames=1 if clip['ordinal'] == 1 else 13,
                use_kv_cache=True, offload_kv_cache=True, enhance_hf=False),
            narration_bindings=bindings, comparison_images=deepcopy(comparisons[sid])))
    return rows
