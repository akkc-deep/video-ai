"""AI-only join-event experiment; never an ordinary continuity profile.

Uses measured trajectories and declared joins, without control recipes, truth,
variant names or future boxes. Numerical parameters are versioned and fixed.
"""
from fractions import Fraction
import math
from statistics import median

ALGORITHM = 'AI_join_event_work_pixel_v3'
PARAMETERS = dict(history_seconds='1/2', minimum_history=3,
                  noise_floor_work_pixels=1.0, maximum_work_edge=256,
                  aggregation='max_of_all_declared_supported_joins',
                  missing_join='abstain_entire_case')


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('finite numeric measurement required')
    return float(value)


def _vector(value, length):
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError('invalid measured vector')
    return [_number(x) for x in value]


def _time(sample):
    stamp = sample['timestamp']
    if stamp['pts'] is None or stamp['time_base'] is None:
        return None
    if type(stamp['pts']) is not int:
        raise ValueError('integer PTS required')
    tb = Fraction(stamp['time_base'])
    if tb <= 0:
        raise ValueError('positive time base required')
    return stamp['pts'] * tb


def _field(sample, detector, size, dt):
    w, h = size
    if detector == 'motion_reset':
        v = _vector(sample.get('camera_compensated_velocity'), 2)
        return None if v is None else [v[0] * w, v[1] * h]
    translation = _vector(sample.get('camera_translation'), 2)
    rot, scale = sample.get('camera_rotation'), sample.get('camera_log_scale')
    if translation is None or rot is None or scale is None:
        return None
    rot, scale = _number(rot), _number(scale)
    try:
        a, b = math.exp(scale) * math.cos(rot), math.exp(scale) * math.sin(rot)
    except OverflowError as exc:
        raise ValueError('camera transform outside finite domain') from exc
    # Center translation and a similarity field at the four image corners.
    result = []
    for x, y in ((0., 0.), (-.5, -.5), (-.5, .5), (.5, -.5), (.5, .5)):
        result.extend((((a - 1) * x - b * y + translation[0]) * w / dt,
                       (b * x + (a - 1) * y + translation[1]) * h / dt))
    return [_number(x) for x in result]


def _length(field):
    return max(math.hypot(field[i], field[i + 1]) for i in range(0, len(field), 2))


def event_case(points, control, width, height, region_id, detector_id, frame_interval):
    """Return supported declared-event scores, leaving incomplete cases null.

    Scores are experimental work-pixel impulses relative to recent continuous
    motion. No detector decision or threshold is applied by this function.
    """
    if any(type(v) is not int or v < 1 for v in (width, height)):
        raise ValueError('positive integer source dimensions required')
    if detector_id not in ('motion_reset', 'camera_jump'):
        raise ValueError('event detector required')
    if (len(frame_interval) != 2 or any(type(x) is not int for x in frame_interval)
            or not 0 <= frame_interval[0] < frame_interval[1]):
        raise ValueError('valid half-open display interval required')
    edge = min(PARAMETERS['maximum_work_edge'], max(width, height))
    size = [round(width / max(width, height) * edge), round(height / max(width, height) * edge)]
    if min(size) < 32:
        raise ValueError('below existing minimum working image size')
    roles = {r['region_id']: r['role'] for r in control['anchors']}
    base = dict(algorithm=ALGORITHM, detector_id=detector_id, region_id=region_id,
                score=None, state='not_comparable', expected_events=0, valid_events=0,
                working_size=size, events=[])
    if roles.get(region_id) != ('subject' if detector_id == 'motion_reset' else 'background'):
        return dict(base, reason='inapplicable_region_role')
    joins = []
    for pair in control['comparisons']:
        if pair['kind'] != 'parent_join' or region_id not in pair['region_ids']:
            continue
        fid = pair['right']; index = int(fid.removeprefix('display_'))
        if frame_interval[0] <= index < frame_interval[1]:
            joins.append(fid)
    joins = list(dict.fromkeys(joins))
    if not joins:
        return dict(base, reason='no_declared_join_in_label_interval')
    declared = {fid for e in (control.get('context') or {}).get('events', [])
                if detector_id in e['detector_ids'] and region_id in e['region_ids']
                for fid in e['frame_ids']}
    active = [fid for fid in joins if fid not in declared]
    if not active:
        return dict(base, reason='all_relevant_joins_declared_not_comparable')
    trajectories = [t for t in points['trajectories'] if t['region_id'] == region_id]
    if len(trajectories) > 1:
        raise ValueError('duplicate region trajectory')
    samples = trajectories[0]['samples'] if trajectories else []
    if len(samples) > 4096:
        raise ValueError('resource_limit: event trajectory samples')
    byframe = {}; history = []; previous_t = None; previous_index = None; seen = set()
    for sample in samples:
        fid = sample['frame_id']; index = int(fid.removeprefix('display_'))
        if fid in seen or (previous_index is not None and index <= previous_index):
            raise ValueError('duplicate or unordered trajectory frames')
        seen.add(fid); t = _time(sample)
        if previous_t is not None and t is not None and t <= previous_t:
            raise ValueError('non-increasing trajectory timestamp')
        contiguous = previous_index is not None and index == previous_index + 1
        dt = float(t - previous_t) if t is not None and previous_t is not None and contiguous else None
        if dt is None or fid in declared:
            history = []; field = None
        else:
            field = _field(sample, detector_id, size, dt)
        byframe[fid] = dict(frame_id=fid, score=None, reason='missing_motion_or_camera_support')
        if field is None:
            history = []
        else:
            history = [(ht, hv) for ht, hv in history if 0 < t - ht <= Fraction(PARAMETERS['history_seconds'])]
            if len(history) >= PARAMETERS['minimum_history']:
                center = [median(v[j] for _, v in history) for j in range(len(field))]
                residual = _length([(a - b) * dt for a, b in zip(field, center)])
                deviations = [_length([(a - b) * dt for a, b in zip(v, center)]) for _, v in history]
                med = median(deviations); mad = median(abs(v - med) for v in deviations)
                normalizer = max(PARAMETERS['noise_floor_work_pixels'], mad)
                score = _number(residual / normalizer)
                byframe[fid] = dict(frame_id=fid, score=score, reason=None,
                                    residual_work_pixels=residual, normalizer_work_pixels=normalizer,
                                    history_samples=len(history), dt_seconds=dt)
            else:
                byframe[fid]['reason'] = 'insufficient_contiguous_history'
            history.append((t, field))
        previous_t, previous_index = t, index
    events = [dict(frame_id=fid, score=None, reason='declared_change') if fid in declared
              else byframe.get(fid, dict(frame_id=fid, score=None, reason='missing_trajectory_sample')) for fid in joins]
    scores = [e['score'] for e in events if e['frame_id'] in active and e['score'] is not None]
    complete = len(scores) == len(active)
    return dict(base, events=events, expected_events=len(active), valid_events=len(scores),
                state='comparable' if complete else 'unverified',
                score=max(scores) if complete else None,
                reason=None if complete else 'unsupported_declared_join')
