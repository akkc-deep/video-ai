"""Pure, versioned execution budgets; semantic plans remain unchanged."""
from collections.abc import Mapping
from copy import deepcopy
from pathlib import PurePosixPath, PureWindowsPath
import re
from types import SimpleNamespace

from ..runtime.manifest import thaw
from .production_scenes import canonical_digest
from .scene_clip_continuation import _budgets, _clip, _fields
from .source_clips import _integer, _same, _wan_frames


ALGORITHM = 'scene_execution_v1'
MODES = ('segmented_v1', 'whole_scene_v1')
EXPECTED_FIELDS = 'run_id mode rendering_identity_sha256 admission'.split()
BUDGET_FIELDS = ('schema_version algorithm production_strategy run_id mode scene_plan_sha256 '
                 'timeline_sha256 rendering_identity_sha256 admission clips').split()


def _mode(mode):
    if not isinstance(mode, str) or mode not in MODES:
        raise ValueError('explicit segmented_v1 or whole_scene_v1 execution mode required')


def _frames(timeline):
    value = timeline.get('total_frames') if isinstance(timeline, Mapping) else getattr(timeline, 'total_frames', None)
    return _integer(value, 'timeline.total_frames', 1)


def _timeline_value(timeline):
    value = timeline if isinstance(timeline, Mapping) else (
        timeline.as_dict() if callable(getattr(timeline, 'as_dict', None)) else thaw(timeline))
    if not isinstance(value, Mapping) or _integer(value.get('total_frames'), 'timeline.total_frames', 1) != _frames(timeline):
        raise ValueError('complete serialized timeline required')
    return thaw(value)


def _sha(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('execution SHA256 required')


def _identity(value):
    _fields(value, EXPECTED_FIELDS, 'execution identity')
    _mode(value['mode'])
    if not isinstance(value['run_id'], str) or not value['run_id'].strip():
        raise ValueError('execution run_id required')
    _sha(value['rendering_identity_sha256'])
    admission = value['admission']
    if value['mode'] == 'segmented_v1':
        if admission is not None: raise ValueError('segmented execution admission must be null')
    else:
        _fields(admission, ('path', 'bytes', 'sha256'), 'whole scene admission Artifact')
        path = admission['path']
        if (not isinstance(path, str) or not path
                or not (PureWindowsPath(path).is_absolute() or PurePosixPath(path).is_absolute())
                or any(part in ('.', '..') for part in re.split(r'[/\\]', path))):
            raise ValueError('whole scene admission requires an absolute Artifact path')
        _integer(admission['bytes'], 'admission bytes', 1)
        _sha(admission['sha256'])


def derive_scene_execution_clips(plan, timeline, *, mode) -> list[dict]:
    """Derive complete native16 clips without rewriting the committed semantic plan."""
    _mode(mode)
    if not isinstance(plan, Mapping): raise ValueError('scene plan required')
    total = _frames(timeline)
    if _integer(plan.get('total_frames'), 'plan.total_frames', 1) != total:
        raise ValueError('scene plan differs from timeline frame count')
    if mode == 'segmented_v1':
        view = SimpleNamespace(total_frames=total) if isinstance(timeline, Mapping) else timeline
        return deepcopy(thaw(_budgets(plan, view)))
    scenes = plan.get('scenes')
    if not isinstance(scenes, (list, tuple)) or not scenes:
        raise ValueError('nonempty ordered scenes required')
    clips, seen, cursor = [], set(), 0
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
            raise ValueError('scene frames must be positive and continuous from zero')
        retained = end-start
        if retained > 320: raise ValueError('whole scene retained frames must be within 1..320')
        generated = _wan_frames(retained)
        clip = dict(clip_id=sid+'_clip_0001', scene_id=sid, ordinal=1, parent_clip_id=None,
            input_kind='selected_scene_image', start_frame=start, end_frame=end,
            retained_frames=retained, generated_frames=generated, discard_head_frames=0,
            trim_tail_frames=generated-retained, retained_source_start=0, retained_source_end=retained)
        clips.append(_clip(clip))
        cursor = end
    if cursor != total: raise ValueError('scene coverage differs from full timeline')
    return clips


def build_scene_execution_budget(plan, timeline, *, run_id, mode, rendering_identity_sha256, admission) -> dict:
    """Bind pure clips to the original plan, full timeline and frozen render identity."""
    identity = dict(run_id=run_id, mode=mode, rendering_identity_sha256=rendering_identity_sha256, admission=admission)
    _identity(identity)
    clips = derive_scene_execution_clips(plan, timeline, mode=mode)
    return dict(schema_version=1, algorithm=ALGORITHM, production_strategy='paragraph_jimeng_v1',
        run_id=run_id, mode=mode, scene_plan_sha256=canonical_digest(thaw(plan)),
        timeline_sha256=canonical_digest(_timeline_value(timeline)),
        rendering_identity_sha256=rendering_identity_sha256, admission=deepcopy(thaw(admission)), clips=clips)


def validate_scene_execution_budget(value, plan, timeline, *, expected) -> dict:
    """Rebuild every field using caller-supplied frozen identities; never trust flags."""
    _fields(value, BUDGET_FIELDS, 'scene execution budget')
    _identity(expected)
    rebuilt = build_scene_execution_budget(plan, timeline, **expected)
    if not _same(value, rebuilt): raise ValueError('scene execution budget differs from frozen inputs')
    return rebuilt
