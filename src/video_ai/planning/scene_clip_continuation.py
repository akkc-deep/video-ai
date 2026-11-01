"""Pure native16 scene continuation requests and exact retained-frame mappings."""
from collections.abc import Mapping
from copy import deepcopy
import re

from ..adapters.jimeng import encode_body
from ..runtime.manifest import thaw
from .production_visual_plan import plan_scene_clips
from .source_clips import WAN_NEGATIVE, _integer, _same, _wan_frames
from .visual_consistency import KINDS, validate_reference_graph


BUDGET_FIELDS = ('clip_id scene_id ordinal parent_clip_id input_kind start_frame end_frame '
                 'retained_frames generated_frames discard_head_frames trim_tail_frames '
                 'retained_source_start retained_source_end').split()
BINDING_FIELDS = 'unit_id text_start text_end text semantic_member start_sample end_sample'.split()


def _fields(value, names, label):
    if not isinstance(value, Mapping) or set(value) != set(names):
        raise ValueError(f'{label}: exact fields required')


def _clip(clip):
    _fields(clip, BUDGET_FIELDS, 'scene clip budget')
    for key in set(BUDGET_FIELDS) - {'clip_id', 'scene_id', 'parent_clip_id', 'input_kind'}:
        _integer(clip[key], key, 1 if key in {'ordinal', 'retained_frames', 'generated_frames', 'end_frame', 'retained_source_end'} else 0)
    sid = clip['scene_id']; ordinal = clip['ordinal']
    if (not isinstance(sid, str) or re.fullmatch(r'scene_[0-9]{4,}', sid) is None
            or int(sid[6:]) < 1 or clip['clip_id'] != f'{sid}_clip_{ordinal:04d}'):
        raise ValueError('exact scene clip identity required')
    parent = None if ordinal == 1 else f'{sid}_clip_{ordinal-1:04d}'
    head = int(parent is not None)
    retained = clip['retained_frames']
    if (clip['parent_clip_id'] != parent
            or clip['input_kind'] != ('selected_scene_image' if parent is None else 'parent_retained_last_frame')
            or clip['end_frame'] - clip['start_frame'] != retained
            or clip['discard_head_frames'] != head or clip['retained_source_start'] != head
            or clip['retained_source_end'] != head + retained
            or clip['generated_frames'] != _wan_frames(head + retained)
            or clip['trim_tail_frames'] != clip['generated_frames'] - head - retained):
        raise ValueError('scene continuation retention budget differs')
    return clip


def scene_clip_frame_mapping(clip, *, actual_generated_frames):
    """Map every generated frame, explicitly discarding continuation head/tail."""
    clip = _clip(clip)
    _integer(actual_generated_frames, 'actual_generated_frames', 1)
    if actual_generated_frames != clip['generated_frames']:
        raise ValueError('generated frame count must exactly equal budget')
    a, b = clip['retained_source_start'], clip['retained_source_end']
    return dict(clip_id=clip['clip_id'], scene_id=clip['scene_id'], native_fps=16,
        output_fps=16, generated_frames=actual_generated_frames,
        retained_frames=clip['retained_frames'], start_frame=clip['start_frame'], end_frame=clip['end_frame'],
        generated_to_retained=[j-a if a <= j < b else None for j in range(actual_generated_frames)],
        retained_to_generated=list(range(a, b)),
        output_to_generated=[dict(output_frame=clip['start_frame']+k, generated_frame=j)
                             for k, j in enumerate(range(a, b))])


def _budgets(plan, timeline, *, execution=None):
    if execution is not None:
        from .scene_execution import EXPECTED_FIELDS, validate_scene_execution_budget
        if not isinstance(execution, Mapping): raise ValueError('scene execution budget required')
        expected = {key: execution.get(key) for key in EXPECTED_FIELDS}
        return validate_scene_execution_budget(execution, plan, timeline, expected=expected)['clips']
    if not isinstance(plan, Mapping):
        raise ValueError('scene plan required')
    total = _integer(timeline.total_frames, 'timeline.total_frames', 1)
    if _integer(plan.get('total_frames'), 'plan.total_frames', 1) != total:
        raise ValueError('scene plan differs from timeline frame count')
    settings = plan.get('settings', {})
    expected = plan_scene_clips(plan, max_clip_seconds=settings.get('max_clip_seconds', 6))
    if not _same(plan.get('clips'), expected):
        raise ValueError('scene clip budgets differ from committed scene plan')
    for clip in expected:
        _clip(clip)
        if clip['generated_frames'] > 96:
            raise ValueError('Wan scene clips must stay within the six second (96 frame) limit')
    return expected


def validate_scene_clip_frame_mappings(plan, timeline, mappings, *, execution=None):
    """Rebuild budgets and require exact once-only coverage of the full timeline."""
    clips = _budgets(plan, timeline, execution=execution)
    if not isinstance(mappings, (list, tuple)) or len(mappings) != len(clips):
        raise ValueError('ordered complete scene clip mappings required')
    cursor = 0
    for clip, actual in zip(clips, mappings):
        expected = scene_clip_frame_mapping(clip, actual_generated_frames=clip['generated_frames'])
        if not _same(actual, expected) or expected['start_frame'] != cursor:
            raise ValueError('scene clip frame mapping differs from exact native mapping')
        cursor = expected['end_frame']
    if cursor != timeline.total_frames:
        raise ValueError('scene mappings do not cover the timeline')


def _narration(plan, timeline):
    total = _integer(timeline.total_samples, 'total_samples', 1)
    if (timeline.total_frames != (total + 2999)//3000
            or _integer(plan.get('total_samples'), 'plan.total_samples', 1) != total):
        raise ValueError('timeline samples and native frames differ')
    catalog = {c.unit_id: c for c in timeline.clips}
    if len(catalog) != len(timeline.clips):
        raise ValueError('unique narration units required')
    coverage = {uid: [] for uid in catalog}
    for scene in plan['scenes']:
        bindings = scene['bindings']
        if not isinstance(bindings, (list, tuple)):
            raise ValueError('scene narration bindings required')
        expected = []
        for narration in timeline.clips:
            start = max(scene['start_frame']*3000, narration.start_sample)
            end = min(scene['end_frame']*3000, total, narration.end_sample)
            if start < end:
                expected.append(dict(unit_id=narration.unit_id, text_start=narration.text_start,
                    text_end=narration.text_end, text=narration.text,
                    semantic_member=narration.unit_id in scene['unit_ids'], start_sample=start, end_sample=end))
        if not _same(bindings, expected):
            raise ValueError('scene bindings differ from complete original PCM/text')
        for binding in bindings:
            _fields(binding, BINDING_FIELDS, 'narration binding')
            for key in ('text_start', 'text_end', 'start_sample', 'end_sample'):
                _integer(binding[key], key)
            coverage[binding['unit_id']].append((binding['start_sample'], binding['end_sample']))
    for uid, intervals in coverage.items():
        narration = catalog[uid]
        if (not intervals or intervals[0][0] != narration.start_sample or intervals[-1][1] != narration.end_sample
                or any(left[1] != right[0] for left, right in zip(intervals, intervals[1:]))):
            raise ValueError('scene bindings must cover each PCM exactly once')


def _artifact(image):
    result = {key: image[key] for key in ('path', 'bytes', 'sha256')}
    if not isinstance(result['path'], str) or not result['path']:
        raise ValueError('accepted original path required')
    _integer(result['bytes'], 'image bytes', 1)
    if not isinstance(result['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', result['sha256']):
        raise ValueError('accepted original SHA256 required')
    return result


def build_scene_wan_plan(frozen, bible, plan, timeline, wan_inputs, *, prompt_contract=None, prompt_binding_context=None,
                         execution=None):
    """Keep fixed shared visual context, original narration and every baseline use."""
    clips = _budgets(plan, timeline, execution=execution)
    whole = execution is not None and execution['mode'] == 'whole_scene_v1'
    raw = getattr(frozen.config, 'raw', {})
    rendering = raw.get('scene_rendering', {})
    mode = rendering.get('mode') if isinstance(rendering, Mapping) else None
    if ((execution is not None and mode != execution['mode'])
            or (mode is not None and execution is None)):
        raise ValueError('explicit rendering mode requires its matching execution budget')
    _narration(plan, timeline)
    validate_reference_graph(thaw(plan['scenes']), thaw(bible))
    from .scene_video_prompts import (parse_scene_rendering,
        validate_scene_video_prompt_contract, render_scene_video_prompt)
    visual = 'scene_rendering' in raw
    if visual:
        parse_scene_rendering(raw['scene_rendering'])
        binding = prompt_binding_context if prompt_binding_context is not None else dict(
            bible=bible,plan=plan,wan_inputs=wan_inputs,script=frozen.script)
        _fields(binding, ('bible','plan','wan_inputs','script'), 'prompt binding context')
        if isinstance(prompt_contract, Mapping) and prompt_contract.get('schema_version') != (2 if whole else 1):
            raise ValueError('prompt schema differs from scene execution mode')
        if whole:
            validate_scene_video_prompt_contract(prompt_contract, **binding, execution=execution)
        else:
            validate_scene_video_prompt_contract(prompt_contract, **binding)
        if [c['clip_id'] for c in prompt_contract['clips']] != [c['clip_id'] for c in clips]:
            raise ValueError('visual prompt coverage differs from target plan')
    elif prompt_contract is not None:
        raise ValueError('prompt contract requires explicit visual_v2 policy')
    profile = frozen.config.media.profile
    if (type(profile.native_fps) is not int or profile.native_fps != 16
            or {'fast': (768, 432), 'quality': (1280, 720)}.get(profile.name) != (profile.width, profile.height)
            or type(profile.width) is not int or type(profile.height) is not int
            or type(frozen.config.media.fps) is not int or frozen.config.media.fps != 16
            or frozen.config.media.transition != 'cut'):
        raise ValueError('fixed native16/cut profile required')
    if whole and (profile.name, profile.width, profile.height) != ('fast', 768, 432):
        raise ValueError('whole scene execution requires fast 768x432 profile')
    scenes = {s['scene_id']: s for s in plan['scenes']}
    rows = wan_inputs['scenes']
    if [r['scene_id'] for r in rows] != list(scenes):
        raise ValueError('accepted images must exactly follow scene plan')
    selected = {r['scene_id']: r for r in rows}
    contexts = {}; comparisons = {}
    for sid, scene in scenes.items():
        context = dict(global_style=deepcopy(thaw(bible['global_style'])))
        uses = set()
        for kind, name, field, scene_field in KINDS:
            ids = [scene[scene_field]] if kind == 'scene_group' else scene[scene_field]
            context[name] = [deepcopy(thaw(row)) for row in bible[name] if row[field] in ids]
            uses.update((kind, item) for item in ids)
        motion = scene['motion_prompt']
        if not isinstance(motion, str) or not motion.strip():
            raise ValueError('complete scene motion prompt required')
        contexts[sid] = motion+'\nVISUAL_BIBLE_JSON\n'+encode_body(context).decode('utf-8')
        comparisons[sid] = []
        for baseline in bible['baselines']:
            if (baseline['kind'], baseline['id']) in uses:
                image = selected[baseline['scene_id']]
                comparisons[sid].append(dict(kind=baseline['kind'], id=baseline['id'],
                    scene_id=baseline['scene_id'], candidate_id=image['candidate_id'], image=_artifact(image)))
        _artifact(selected[sid])
    seed_indices = {}
    if whole:
        original = plan_scene_clips(plan, max_clip_seconds=plan.get('settings', {}).get('max_clip_seconds', 6))
        if not _same(plan.get('clips'), original):
            raise ValueError('semantic clip budgets differ from committed scene plan')
        for index, clip in enumerate(original):
            _clip(clip)
            seed_indices.setdefault(clip['scene_id'], index)
    result = []
    for index, clip in enumerate(clips):
        sid = clip['scene_id']; scene = scenes[sid]
        positive = render_scene_video_prompt(prompt_contract, bible, scene, clip['clip_id']) if visual else contexts[sid]
        parameters = dict(positive=positive, negative=WAN_NEGATIVE,
            seed_high=264244520398999+(seed_indices[sid] if whole else index), seed_low=0,
            width=profile.width, height=profile.height,
            length=clip['generated_frames'], fps=16, batch=1, steps=40, cfg=3.5, sampler='euler',
            scheduler='simple', split_step=15, shift_high=5.000000000000001,
            shift_low=5.000000000000001, lora_enabled=False)
        bindings = []
        for original in scene['bindings']:
            start = max(clip['start_frame']*3000, original['start_sample'])
            end = min(clip['end_frame']*3000, timeline.total_samples, original['end_sample'])
            if start < end: bindings.append(dict(thaw(original), start_sample=start, end_sample=end))
        result.append(dict(budget=deepcopy(clip), parameters=parameters, narration_bindings=bindings,
                           comparison_images=deepcopy(comparisons[sid])))
    return result
