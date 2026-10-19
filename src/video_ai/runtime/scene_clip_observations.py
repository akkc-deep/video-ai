"""Read-only scene clip playback observation templates and strict admission.

Templates describe required evidence; they never claim that playback occurred.
The caller validates technical records before building an expected template and
passes ``{'template': template, 'created_at': clip_record['created_at']}`` to
``validate_scene_clip_observation``. Neither function writes files or uses a
model or service. Acceptance receipts belong to the caller's locked transaction.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
from pathlib import Path
import re
import stat

from ..adapters.common import strict_json
from ..jimeng_config import STRATEGY
from ..planning.production_scenes import canonical_digest
from .manifest import validate_run_dir
from .paths import PROJECT_ROOT
from .production_state import ProductionRefused, integer, object_fields, run_path


OBSERVATION_FIELDS = ('schema_version production_strategy run_id scope scene_id clip_id clip_sha256 '
    'request_sha256 visual_bible_sha256 selected_image comparison_images generated source last_frame parent '
    'playback review_method reviewer viewed_at start_observation process_observation end_observation '
    'quality_observation continuity_observation checks verdict issues reason').split()
CHECK_FIELDS = ('subject_identity appearance_structure color_clothing environment_space time_lighting '
    'style motion_process end_frame_stability input_alignment parent_join').split()
AUTHORED_FIELDS = ('start_observation process_observation end_observation quality_observation '
    'continuity_observation reason').split()
IDENTITY_FIELDS = ('schema_version production_strategy run_id scope scene_id clip_id clip_sha256 '
    'request_sha256 visual_bible_sha256 selected_image comparison_images generated source last_frame parent').split()
STATES = ('passed', 'failed', 'unverified')


def _equal(left, right, label):
    try:
        if canonical_digest(left) == canonical_digest(right):
            return
    except (TypeError, ValueError):
        pass
    raise ProductionRefused(label+' identity differs')


def _nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ProductionRefused(label+': expected nonempty string')


def _sha(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ProductionRefused('expected lowercase SHA256')


def _time(value, label):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError()
        return parsed
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProductionRefused(label+': expected timezone-aware timestamp') from exc


def _artifact(value, run):
    object_fields(value, ('path', 'bytes', 'sha256'), 'scene observation artifact')
    integer(value['bytes'], 'artifact bytes', 1)
    _sha(value['sha256'])
    if not isinstance(value['path'], str):
        raise ProductionRefused('artifact path must be a string')
    try:
        lexical = Path(value['path'])
        for entry in (lexical, *lexical.parents):
            if entry.is_symlink() or (entry.exists() and getattr(entry.lstat(), 'st_file_attributes', 0)
                                     & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ProductionRefused('redirected observation artifact forbidden')
        path = run_path(run, value['path'])
        digest = hashlib.sha256()
        size = 0
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(1024*1024), b''):
                size += len(chunk)
                digest.update(chunk)
    except (OSError, ValueError) as exc:
        raise ProductionRefused('scene observation artifact unavailable') from exc
    if size != value['bytes'] or digest.hexdigest() != value['sha256']:
        raise ProductionRefused('scene observation artifact bytes differ')


def _media_identities(template):
    try:
        run = validate_run_dir(PROJECT_ROOT/'runs'/template['run_id'])
    except (TypeError, ValueError) as exc:
        raise ProductionRefused('invalid observation run identity') from exc
    for field in ('generated', 'source', 'last_frame'):
        _artifact(template[field], run)
    if template['parent'] is not None:
        parent = template['parent']
        object_fields(parent, ('clip_id', 'clip_sha256', 'generated', 'source', 'last_frame_sha256',
                               'last_frame', 'observation_acceptance_sha256'), 'observation parent')
        for field in ('clip_sha256', 'last_frame_sha256', 'observation_acceptance_sha256'):
            _sha(parent[field])
        for field in ('generated', 'source', 'last_frame'):
            _artifact(parent[field], run)
    selected = template['selected_image']
    if not isinstance(selected, dict) or not all(key in selected for key in ('path', 'bytes', 'sha256')):
        raise ProductionRefused('observation selected image identity missing')
    _artifact({key: selected[key] for key in ('path', 'bytes', 'sha256')}, run)
    if not isinstance(template['comparison_images'], list):
        raise ProductionRefused('comparison images must be an array')
    for row in template['comparison_images']:
        object_fields(row, ('kind', 'id', 'scene_id', 'candidate_id', 'image'), 'comparison image')
        for key in ('kind', 'id', 'scene_id', 'candidate_id'):
            _nonempty(row[key], 'comparison image '+key)
        _artifact(row['image'], run)


def _interval(value, end, label):
    if not isinstance(value, list) or len(value) != 2:
        raise ProductionRefused(label+': expected half-open frame interval')
    for index in value:
        integer(index, label)
    if not 0 <= value[0] < value[1] <= end:
        raise ProductionRefused(label+': invalid source frame interval')


def build_observation_template(frozen, clip_record, request, mapping, last_frame, parent_records):
    """Bind trusted technical records to an intentionally unauthored template.

    ``parent_records`` is None, or a dict containing clip/mapping/last_frame/
    accepted records already validated by the caller. Inputs remain immutable.
    """
    try:
        run = validate_run_dir(Path(frozen.options['script_path']).parent.parent)
        _equal(frozen.options['run_id'], run.name, 'frozen observation run')
        path = run_path(run, run/'production/scene-clips/inputs.json')
        inputs = strict_json(path.read_bytes())
        _equal(canonical_digest(inputs), request['inputs_sha256'], 'observation inputs')
        _sha(inputs['visual_bible_sha256'])
        _equal(clip_record['request_sha256'], canonical_digest(request), 'observation request')
        for field, expected in (('schema_version', 2), ('production_strategy', STRATEGY),
                                ('run_id', run.name), ('scene_id', request['scene_id']),
                                ('clip_id', request['clip_id'])):
            _equal(clip_record[field], expected, 'technical clip '+field)
        integer(mapping['retained_frames'], 'clip retained frames', 1)
        parent_frames = None
        if request['parent'] is None:
            if parent_records is not None:
                raise ProductionRefused('first clip cannot bind parent records')
        else:
            object_fields(parent_records, ('clip', 'mapping', 'last_frame', 'accepted'), 'parent records')
            integer(parent_records['mapping']['retained_frames'], 'parent retained frames', 1)
            parent = parent_records['clip']
            _equal(request['parent'], dict(clip_id=parent['clip_id'], clip_sha256=canonical_digest(parent),
                generated=parent['generated'], source=parent['source'],
                last_frame_sha256=canonical_digest(parent_records['last_frame']),
                last_frame=parent_records['last_frame']['image'],
                observation_acceptance_sha256=canonical_digest(parent_records['accepted'])),
                'observation parent')
            for artifact in (parent['generated'], parent['source'], parent_records['last_frame']['image']):
                _artifact(artifact, run)
            parent_frames = [0, parent_records['mapping']['retained_frames']]
        value = dict(schema_version=2, production_strategy=STRATEGY, run_id=run.name,
            scope='scene_clip_process', scene_id=request['scene_id'], clip_id=request['clip_id'],
            clip_sha256=canonical_digest(clip_record), request_sha256=canonical_digest(request),
            visual_bible_sha256=inputs['visual_bible_sha256'], selected_image=deepcopy(request['selected_image']),
            comparison_images=deepcopy(request['comparison_images']), generated=deepcopy(clip_record['generated']),
            source=deepcopy(clip_record['source']), last_frame=deepcopy(last_frame['image']),
            parent=deepcopy(request['parent']), playback=dict(clip_source_frames=[0, mapping['retained_frames']],
                parent_source_frames=parent_frames), review_method=None, reviewer=None, viewed_at=None,
            checks={key: (None if key == 'parent_join' and request['parent'] is None else 'unverified')
                    for key in CHECK_FIELDS}, verdict='unverified', issues=[],
            **{key: '' for key in AUTHORED_FIELDS})
        _time(clip_record['created_at'], 'clip created_at')
        _media_identities(value)
        return value
    except (KeyError, TypeError, OSError, ValueError) as exc:
        if isinstance(exc, ProductionRefused):
            raise
        raise ProductionRefused('invalid scene clip observation inputs') from exc


def validate_scene_clip_observation(value, expected, *, now):
    """Return a copy of a valid observation, including failed/unverified verdicts.

    ``expected`` has exact fields template/created_at. Its template is built
    from freshly verified technical records; created_at is clip.created_at.
    A template itself is deliberately ineligible for admission. ``now`` is a
    timezone-aware datetime or ISO timestamp; accepted replay uses accepted_at.
    """
    object_fields(expected, ('template', 'created_at'), 'observation expected context')
    template = expected['template']
    object_fields(template, OBSERVATION_FIELDS, 'observation template')
    object_fields(value, OBSERVATION_FIELDS, 'scene clip observation')
    for field in IDENTITY_FIELDS:
        _equal(value[field], template[field], 'observation '+field)
    _media_identities(template)
    object_fields(value['playback'], ('clip_source_frames', 'parent_source_frames'), 'playback')
    _equal(value['playback'], template['playback'], 'complete playback')
    end = template['playback']['clip_source_frames'][1]
    _interval(value['playback']['clip_source_frames'], end, 'clip playback')
    parent_end = template['playback']['parent_source_frames']
    if parent_end is not None:
        _interval(value['playback']['parent_source_frames'], parent_end[1], 'parent playback')
    if value['review_method'] not in ('human_video', 'agent_video'):
        raise ProductionRefused('actual human_video or agent_video playback review required')
    _nonempty(value['reviewer'], 'reviewer')
    if not isinstance(value['viewed_at'], str):
        raise ProductionRefused('viewed_at must be an ISO timestamp string')
    viewed = _time(value['viewed_at'], 'viewed_at')
    if not _time(expected['created_at'], 'clip created_at') <= viewed <= _time(now, 'now'):
        raise ProductionRefused('observation viewed_at outside technical clip review period')
    for field in AUTHORED_FIELDS:
        _nonempty(value[field], field)
    object_fields(value['checks'], CHECK_FIELDS, 'observation checks')
    applicable = CHECK_FIELDS if template['parent'] is not None else CHECK_FIELDS[:-1]
    if template['parent'] is None and value['checks']['parent_join'] is not None:
        raise ProductionRefused('first clip parent_join must be null')
    for key in applicable:
        if value['checks'][key] not in STATES:
            raise ProductionRefused('invalid observation check state: '+key)
    if not isinstance(value['issues'], list):
        raise ProductionRefused('issues must be an array')
    for issue in value['issues']:
        object_fields(issue, ('check', 'frames', 'description'), 'observation issue')
        if issue['check'] not in applicable:
            raise ProductionRefused('issue check is not applicable')
        _interval(issue['frames'], end, 'issue frames')
        _nonempty(issue['description'], 'issue description')
    states = [value['checks'][key] for key in applicable]
    verdict = value['verdict']
    valid = ((verdict == 'passed' and all(status == 'passed' for status in states) and not value['issues'])
             or (verdict == 'failed' and 'failed' in states and bool(value['issues']))
             or (verdict == 'unverified' and 'failed' not in states and 'unverified' in states))
    if not valid:
        raise ProductionRefused('observation verdict contradicts checks or issues')
    return deepcopy(value)
