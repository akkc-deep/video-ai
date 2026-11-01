"""Explicit human playback declarations; telemetry never supplies semantic labels."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from .natural_acquisition import read_json, identity, write_json
from .natural_acquisition_runtime import _case, _verified_result, collection_status


def _time(value):
    when = datetime.fromisoformat(value)
    if when.tzinfo is None or when > datetime.now(timezone.utc):
        raise ValueError('actual timezone-aware observation time required')
    return when


def validate_observation(row):
    keys = ('schema_version kind case_id collection video reference reviewer review_method reviewed_at playback '
        'natural_label operation correction_direction target_reference_confirmed subject_structure_intact '
        'motion_intact intentional_lighting_change description').split()
    if (type(row) is not dict or set(row) != set(keys) or type(row['schema_version']) is not int
            or row['schema_version'] != 1 or row['kind'] != 'natural_material_observation_v1'
            or row['review_method'] != 'human_video'):
        raise ValueError('exact research human observation schema required')
    if any(not isinstance(row[k],str) or not row[k].strip() for k in ('reviewer','description','case_id')):
        raise ValueError('actual author, case and observation text required')
    reviewed = _time(row['reviewed_at'])
    label = row['natural_label']
    if label not in ('unverified','neutral','mild_color_bias','unsafe','not_comparable'):
        raise ValueError('unknown natural label')
    for field in ('target_reference_confirmed','subject_structure_intact','motion_intact','intentional_lighting_change'):
        if row[field] is not None and type(row[field]) is not bool:
            raise ValueError('explicit boolean or unknown semantic response required')
    p = row['playback']
    if type(p) is not dict or set(p) != set(('completed frames fps covered_frames frame_times started_at ended_at '
            'elapsed_seconds playback_rate visible interruptions').split()):
        raise ValueError('exact full playback declaration required')
    if type(p['frames']) is not int or p['frames'] != 49 or p['fps'] != '16/1':
        raise ValueError('frozen complete native frame budget required')
    if (type(p['covered_frames']) is not list or type(p['frame_times']) is not list
            or len(p['frame_times']) > 512 or any(type(t) not in (int,float) or not math.isfinite(t) for t in p['frame_times'])
            or any(type(i) is not int for i in p['covered_frames'])):
        raise ValueError('bounded finite actual frame declarations required')
    if label == 'unverified':
        return 'unverified'
    start, end = _time(p['started_at']), _time(p['ended_at'])
    if (p['completed'] is not True or p['visible'] is not True or p['playback_rate'] != 1
            or type(p['playback_rate']) is bool or p['interruptions'] != []
            or p['covered_frames'] != list(range(49)) or len(p['frame_times']) != 49
            or any(abs(t-i/16) > .01 for i,t in enumerate(p['frame_times']))
            or type(p['elapsed_seconds']) not in (int,float) or not math.isfinite(p['elapsed_seconds'])
            or p['elapsed_seconds'] < 49/16-.03 or (end-start).total_seconds() < 49/16-.03
            or end > reviewed):
        raise ValueError('complete visible uninterrupted native playback required')
    if label in ('neutral','mild_color_bias'):
        if (row['target_reference_confirmed'] is not True or row['subject_structure_intact'] is not True
                or row['motion_intact'] is not True or row['intentional_lighting_change'] is not False):
            raise ValueError('explicit target, structure, motion and illumination intent required')
    if label == 'mild_color_bias':
        if (row['operation'],row['correction_direction']) not in (
                ('exposure','negative'),('wb_r','negative'),('wb_g','positive'),('wb_g','negative')):
            raise ValueError('known supported correction axis and direction required')
    elif row['operation'] is not None or row['correction_direction'] is not None:
        raise ValueError('only an observed mild color issue has a chosen correction axis')
    return 'label_recorded'


def record_observation(root, observation_path):
    from ..runtime._scene_continuity_io import local
    from ..adapters.common import strict_json
    path = local(observation_path,runtime=False)
    if path.stat().st_size > 16*1024**2:
        raise ValueError('observation input exceeds 16MiB')
    with path.open('rb') as stream:
        raw = stream.read(16*1024**2+1)
    if len(raw) > 16*1024**2:
        raise ValueError('observation input exceeds 16MiB')
    row = strict_json(raw)
    state = validate_observation(row)
    _, case, folder = _case(root,row['case_id'])
    result = _verified_result(root,case,folder)
    collection = read_json(Path(root)/'collection-receipt.json')['collection']
    if (row['collection'] != collection or row['reference'] != case['reference'] or row['video'] != result['video']
            or _time(row['reviewed_at']) < _time(result['finished_at'])
            or state == 'label_recorded' and _time(row['playback']['started_at']) < _time(result['finished_at'])):
        raise ValueError('observation media/collection/time identity differs')
    if case['split'] != 'development':
        raise ValueError('holdout observations require the separate sealed evaluation workflow')
    digest = hashlib.sha256(raw).hexdigest()
    target = Path(root)/'observations'/case['case_id']/(digest+'.json')
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:
            stream.write(raw)
    elif target.read_bytes() != raw:
        raise ValueError('observation digest collision')
    return dict(status=state,observation=identity(target),case_id=case['case_id'],
        natural_label=row['natural_label'],ready_for_propose=False,
        limitation='Retained author report and browser declarations; not independent proof of visual correctness or qualification.')


def export_portal(root):
    status = collection_status(root)
    collection = read_json(Path(root)/'collection-receipt.json')['collection']
    cases = []
    for row in status['cases']:
        if row['video'] is None or row['split'] != 'development':
            continue
        cases.append(dict(**row,video_url=Path(row['video']['path']).relative_to(root).as_posix(),
            reference_url=Path(row['reference']['path']).relative_to(root).as_posix()))
    template = Path(__file__).parents[3]/'scripts/experiments/vco06_observe.html'
    data = json.dumps(dict(collection=collection,cases=cases),ensure_ascii=False).replace('<','\\u003c')
    text = template.read_text(encoding='utf-8').replace('/*COLLECTION_DATA*/null',data)
    target = Path(root)/f'observe-{len(cases):02d}.html'
    raw = text.encode('utf-8')
    if target.exists():
        if target.read_bytes() != raw:
            raise FileExistsError('different portal snapshot already exists')
    else:
        with target.open('xb') as stream:
            stream.write(raw)
    return dict(status='observation_portal_ready',cases=len(cases),portal=identity(target),ready_for_propose=False)
