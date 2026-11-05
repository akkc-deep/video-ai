"""Strict image-only window screening and one complete native-chain review."""
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

from ..jimeng_config import STRATEGY
from ..planning.production_scenes import canonical_digest
from ..planning.scene_temporal import PROTOCOL, validate_temporal_clip
from .manifest import validate_run_dir
from .production_state import ProductionRefused, object_fields
from .scene_clip_observations import _artifact, _equal, _nonempty, _sha, _time

SCOPES = ('temporal_window_static', 'scene_temporal_chain_process')
CHECKS = ('subject', 'color', 'composition', 'camera', 'motion')
FIELDS = ('schema_version production_strategy run_id scope binding playback review_method reviewer viewed_at '
          'checks verdict reason allow_next_window').split()
IDENTITY = ('schema_version', 'production_strategy', 'run_id', 'scope', 'binding', 'playback')


def retained_temporal_observations(context, folder, template, created_at, now):
    """Original author bytes survive an interruption before receipt publication."""
    from ..adapters.common import strict_json, JSON_LIMIT
    rows = []
    for path in sorted((Path(folder)/'observations').glob('*.json')):
        raw = path.read_bytes()
        if len(raw)>JSON_LIMIT: raise ProductionRefused('retained native observation exceeds JSON limit')
        rows.append(validate_temporal_observation(strict_json(raw),dict(template=template,created_at=created_at),now))
    return rows


def _window(row):
    budget = validate_temporal_clip(row['budget'])
    return dict(clip_id=budget['clip_id'], source_frame_range=[budget['retained_source_start'], budget['retained_source_end']],
                chain_frame_range=[budget['start_frame'], budget['end_frame']], raw_frames=93,
                result=deepcopy(row['result']), raw_frames_artifact=deepcopy(row['raw_frames']))


def _artifacts(value, run, origins=None):
    origins={} if origins is None else origins
    if isinstance(value, Mapping):
        if set(value) == {'path', 'bytes', 'sha256'}:
            if not isinstance(value['path'],str):raise ProductionRefused('native observation Artifact path must be text')
            if Path(value['path']).is_relative_to(run):_artifact(value, run)
            else:
                if 'store' not in origins:
                    from types import SimpleNamespace
                    from .production_inputs import load_frozen_inputs
                    from .scene_revision_records import require_scene_revision
                    frozen=load_frozen_inputs(run)
                    if frozen.config.raw.get('scene_rendering',{}).get('mode')!='temporal_extension_v1' or 'scene_revision' not in frozen.options:
                        raise ProductionRefused('native observation Artifact outside current run has no origin')
                    origins['store']=SimpleNamespace(run_dir=run,execution_mode='temporal_extension_v1',revision_context=require_scene_revision(frozen))
                from .temporal_scene_origins import bound_temporal_artifact
                if bound_temporal_artifact(origins['store'],value['path'],dict(value)) is None:
                    raise ProductionRefused('native observation refers to an uncaptured original')
        else:
            for child in value.values(): _artifacts(child, run,origins)
    elif isinstance(value, (list, tuple)):
        for child in value: _artifacts(child, run,origins)


def build_temporal_observation_template(context, record, *, scope) -> dict:
    """Consume caller-validated technical records; never claim playback occurred."""
    try:
        if scope not in SCOPES: raise ProductionRefused('unknown temporal observation scope')
        run = validate_run_dir(Path(context['frozen'].options['script_path']).parent.parent)
        _equal(run.name, context['frozen'].options['run_id'], 'native observation run')
        if run != Path(context['store'].run_dir):
            raise ProductionRefused('native observation store identity differs')
        binding = dict(protocol=PROTOCOL, inputs_sha256=canonical_digest(context['inputs']),
                       result=deepcopy(record['result']), selected_image=deepcopy(record['selected_image']))
        if scope == 'temporal_window_static':
            budget = validate_temporal_clip(record['budget'])
            if type(record['terminal']) is not bool: raise ProductionRefused('explicit terminal-window flag required')
            _sha(record['request_sha256'])
            parent = record['parent']
            if budget['ordinal'] == 1:
                if parent is not None: raise ProductionRefused('first window cannot have a parent')
            else:
                object_fields(parent, ('result', 'raw_frames', 'condition_frames', 'source_frame_range'), 'native observation parent')
                if parent['source_frame_range'] != [80, 93]: raise ProductionRefused('actual parent raw13 range required')
            binding.update(scene_id=budget['scene_id'], clip_id=budget['clip_id'], window=_window(record),
                request_sha256=record['request_sha256'], contact_sheet=deepcopy(record['contact_sheet']),
                parent=deepcopy(parent), terminal=record['terminal'])
            playback = None
        else:
            windows = record['windows']
            if not isinstance(windows, (list, tuple)) or not windows:
                raise ProductionRefused('complete ordered chain windows required')
            compact = []
            start = cursor = windows[0]['budget']['start_frame']
            for ordinal, row in enumerate(windows, 1):
                budget = validate_temporal_clip(row['budget'])
                if (budget['scene_id'] != record['scene_id'] or budget['ordinal'] != ordinal
                        or budget['start_frame'] != cursor
                        or ordinal < len(windows) and budget['trim_tail_frames'] != 0):
                    raise ProductionRefused('complete native scene chain mapping required')
                compact.append(_window(row)); cursor = budget['end_frame']
            binding.update(scene_id=record['scene_id'], viewing=deepcopy(record['viewing']), windows=compact,
                frame_range=[start, cursor], boundary_frames=[row['chain_frame_range'][0] for row in compact[1:]], terminal=True)
            playback = [0, cursor-start]
        return dict(schema_version=1, production_strategy=STRATEGY, run_id=run.name, scope=scope,
            binding=binding, playback=playback, review_method=None, reviewer=None, viewed_at=None,
            checks={key: 'unverified' for key in CHECKS}, verdict='unverified', reason=None, allow_next_window=False)
    except (KeyError, TypeError, ValueError, OSError, AttributeError) as exc:
        if isinstance(exc, ProductionRefused): raise
        raise ProductionRefused('invalid native observation inputs') from exc


def validate_temporal_observation(value, expected, now) -> dict:
    object_fields(expected, ('template', 'created_at'), 'native observation expected context')
    template = expected['template']
    object_fields(template, FIELDS, 'native observation template')
    object_fields(value, FIELDS, 'native observation')
    for key in IDENTITY: _equal(value[key], template[key], 'native observation '+key)
    if type(value['schema_version']) is not int or value['schema_version'] != 1 or value['scope'] not in SCOPES:
        raise ProductionRefused('native observation schema/scope')
    static = value['scope'] == 'temporal_window_static'
    methods = ('human_image', 'agent_image') if static else ('human_video', 'agent_video')
    if value['review_method'] not in methods:
        raise ProductionRefused('actual image screening or complete video playback required for this scope')
    _nonempty(value['reviewer'], 'reviewer'); _nonempty(value['reason'], 'reason')
    if not isinstance(value['viewed_at'], str): raise ProductionRefused('viewed_at string required')
    if not _time(expected['created_at'], 'technical creation') <= _time(value['viewed_at'], 'viewed_at') <= _time(now, 'now'):
        raise ProductionRefused('native observation outside technical review period')
    object_fields(value['checks'], CHECKS, 'native continuity checks')
    states = ('acceptable', 'rejected', 'unverified') if static else ('passed', 'failed', 'unverified')
    if any(status not in states for status in value['checks'].values()):
        raise ProductionRefused('unknown native continuity check state')
    statuses = list(value['checks'].values())
    verdict = value['verdict']
    if static:
        valid = ((verdict == 'acceptable' and 'rejected' not in statuses
                  and all(value['checks'][key] == 'acceptable' for key in ('subject', 'color', 'composition')))
                 or (verdict == 'rejected' and 'rejected' in statuses)
                 or (verdict == 'unverified' and 'rejected' not in statuses and 'unverified' in statuses))
        allow = verdict == 'acceptable' and not template['binding']['terminal']
    else:
        valid = ((verdict == 'passed' and all(status == 'passed' for status in statuses))
                 or (verdict == 'failed' and 'failed' in statuses)
                 or (verdict == 'unverified' and 'failed' not in statuses and 'unverified' in statuses))
        allow = False
    if not valid or type(value['allow_next_window']) is not bool or value['allow_next_window'] != allow:
        raise ProductionRefused('native observation verdict/continuation contradicts checks')
    from .paths import PROJECT_ROOT
    run = validate_run_dir(PROJECT_ROOT/'runs'/template['run_id'])
    _artifacts(template['binding'], run)
    return deepcopy(value)
