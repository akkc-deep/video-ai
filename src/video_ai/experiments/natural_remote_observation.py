"""Separate human remote-viewing declarations, never fabricated frame coverage.

The frozen v1 validator and its intake remain unchanged. Browser declarations and
an identified human report are evidence, not independent proof of visual quality.
"""
import hashlib
import math
from pathlib import Path
import re

from .natural_acquisition import identity, read_json
from .natural_acquisition_observation import _time
from .natural_acquisition_runtime import _case, _verified_result


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_remote_observation(row):
    keys = ('schema_version kind case_id collection video reference reviewer review_method reviewed_at playback '
        'natural_label operation correction_direction target_reference_confirmed subject_structure_intact '
        'motion_intact intentional_lighting_change description remote_playback').split()
    if (type(row) is not dict or set(row) != set(keys) or type(row['schema_version']) is not int
            or row['schema_version'] != 2 or row['kind'] != 'natural_material_observation_remote_v2'
            or row['review_method'] != 'human_remote_video'):
        raise ValueError('exact separate remote observation v2 schema required')
    if any(not isinstance(row[k], str) or not row[k].strip() for k in ('case_id', 'reviewer', 'description')):
        raise ValueError('actual case, human author and observation text required')
    for key in ('collection', 'video', 'reference'):
        a = row[key]
        if (type(a) is not dict or set(a) != {'path', 'bytes', 'sha256'}
                or not isinstance(a['path'], str) or not a['path'].strip()
                or type(a['bytes']) is not int or a['bytes'] <= 0
                or not isinstance(a['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', a['sha256'])):
            raise ValueError('exact media and collection identities required')
    reviewed = _time(row['reviewed_at'])
    label = row['natural_label']
    if label not in ('neutral', 'mild_color_bias', 'unsafe', 'not_comparable'):
        raise ValueError('explicit human natural observation label required')
    for key in ('target_reference_confirmed', 'subject_structure_intact', 'motion_intact', 'intentional_lighting_change'):
        if row[key] is not None and type(row[key]) is not bool:
            raise ValueError('explicit boolean or unknown semantic response required')
    if label in ('neutral', 'mild_color_bias') and (
            row['target_reference_confirmed'] is not True or row['subject_structure_intact'] is not True
            or row['motion_intact'] is not True or row['intentional_lighting_change'] is not False):
        raise ValueError('explicit target, structure, motion and illumination intent required')
    if label == 'mild_color_bias':
        if (row['operation'], row['correction_direction']) not in (
                ('exposure', 'negative'), ('wb_r', 'negative'), ('wb_g', 'positive'), ('wb_g', 'negative')):
            raise ValueError('known supported correction axis and direction required')
    elif row['operation'] is not None or row['correction_direction'] is not None:
        raise ValueError('only an observed mild color issue has a chosen correction axis')
    p = row['playback']
    if (type(p) is not dict or set(p) != set(('completed frames fps covered_frames frame_times started_at ended_at '
            'elapsed_seconds playback_rate visible interruptions').split())
            or p['completed'] is not False or type(p['frames']) is not int or p['frames'] != 49 or p['fps'] != '16/1'):
        raise ValueError('exact actual playback, without a false strict completion flag, required')
    indices, times = p['covered_frames'], p['frame_times']
    if (type(indices) is not list or type(times) is not list or len(indices) != len(times) or len(indices) > 49
            or any(type(i) is not int or not 0 <= i < 49 for i in indices)
            or any(a >= b for a, b in zip(indices, indices[1:]))
            or any(not _finite(t) or abs(t-i/16) > .01 for i, t in zip(indices, times))):
        raise ValueError('bounded ordered actual callback evidence required; missing frames must stay missing')
    start, end = _time(p['started_at']), _time(p['ended_at'])
    elapsed, wall = p['elapsed_seconds'], (end-start).total_seconds()
    if (not _finite(elapsed) or elapsed < 49/16-.03 or wall < 49/16-.03 or abs(elapsed-wall) > .25
            or end > reviewed or p['visible'] is not True or not _finite(p['playback_rate'])
            or p['playback_rate'] != 1 or type(p['interruptions']) is not list or len(p['interruptions']) > 512
            or any(event != 'stalled' for event in p['interruptions'])):
        raise ValueError('complete visible uninterrupted native elapsed playback required')
    # Network fetching may stall while the buffered presentation keeps playing.
    # Retain that notification; every actual pause/wait/seek/error still rejects.
    r = row['remote_playback']
    if (type(r) is not dict or set(r) != set(('ended_event media_duration end_media_time played_ranges '
            'video_sha256 viewer_confirmed_complete').split())
            or r['ended_event'] is not True or r['viewer_confirmed_complete'] is not True
            or r['video_sha256'] != row['video']['sha256']
            or not _finite(r['media_duration']) or abs(r['media_duration']-49/16) > .01
            or not _finite(r['end_media_time']) or abs(r['end_media_time']-49/16) > .01):
        raise ValueError('actual native ended event, matching media and explicit human confirmation required')
    ranges = r['played_ranges']
    if (type(ranges) is not list or len(ranges) != 1 or type(ranges[0]) is not list or len(ranges[0]) != 2
            or any(not _finite(t) for t in ranges[0]) or not 0 <= ranges[0][0] <= .01
            or not 49/16-.01 <= ranges[0][1] <= 49/16+.01):
        raise ValueError('actual single continuous full native played time range required')
    return 'remote_label_recorded'


def record_remote_observation(root, observation_path):
    from ..adapters.common import strict_json
    from ..runtime._scene_continuity_io import local
    path = local(observation_path, runtime=False)
    with path.open('rb') as stream:
        raw = stream.read(16*1024**2+1)
    if len(raw) > 16*1024**2:
        raise ValueError('observation input exceeds 16MiB')
    row = strict_json(raw)
    state = validate_remote_observation(row)
    _, case, folder = _case(root, row['case_id'])
    if case['split'] != 'development':
        raise ValueError('holdout observations require the separate sealed evaluation workflow')
    result = _verified_result(root, case, folder)
    collection = read_json(Path(root)/'collection-receipt.json')['collection']
    if (row['collection'] != collection or row['reference'] != case['reference'] or row['video'] != result['video']
            or _time(row['playback']['started_at']) < _time(result['finished_at'])):
        raise ValueError('observation media/collection/time identity differs')
    digest = hashlib.sha256(raw).hexdigest()
    target = Path(root)/'remote-observations'/case['case_id']/(digest+'.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open('xb') as stream:
            stream.write(raw)
    except FileExistsError:
        if target.read_bytes() != raw:
            raise ValueError('observation digest collision')
    return dict(status=state, observation=identity(target), case_id=case['case_id'], natural_label=row['natural_label'],
        ready_for_propose=False, production_eligible=False,
        limitation='Retained human report and browser timeline declarations, including actual incomplete frame callbacks; '
                   'not independent visual proof, a frozen-v1 observation, or a qualification/profile/candidate approval.')
