"""Fixed natural-qualification diagnostics; these statistics grant no repair authority."""
import hashlib
import json
import math

import numpy as np

from .natural_color_repair import ALGORITHM

_DIRECTIONS = {'exposure': [1., 1., 1.], 'wb_r': [1., -.5, -.5], 'wb_g': [-.5, 1., -.5]}


def _integer(value, minimum=0, maximum=65536):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('bounded non-Boolean integer required')
    return value


def _coordinates(rows, count):
    if type(rows) is not list or len(rows) != count:
        raise ValueError('complete fixed coordinate support required')
    seen = set()
    for row in rows:
        if type(row) is not dict or set(row) != {'region_id', 'reference', 'current'}:
            raise ValueError('exact sampled coordinate fields required')
        if type(row['region_id']) is not str or not row['region_id'].strip():
            raise ValueError('declared region ID required')
        for name in ('reference', 'current'):
            if type(row[name]) is not list or len(row[name]) != 2:
                raise ValueError('integer pixel coordinate pair required')
            for value in row[name]:
                _integer(value, maximum=2**31-1)
        key = (row['region_id'], *row['reference'], *row['current'])
        if key in seen:
            raise ValueError('duplicate support point')
        seen.add(key)
    data = json.dumps(rows, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def _role(row, direction):
    if type(row) is not dict or row.get('role') not in ('background', 'subject'):
        raise ValueError('declared ordinary subject/background role required')
    count = _integer(row.get('pairs'), 1, 1024)
    digest = _coordinates(row.get('coordinates'), count)
    logs = row.get('log2_ratios')
    if type(logs) is not list or len(logs) != count:
        raise ValueError('complete point log ratios required')
    for triple in logs:
        if (type(triple) is not list or len(triple) != 3 or any(
                type(v) not in (int, float) or not math.isfinite(v) for v in triple)):
            raise ValueError('finite non-Boolean three-channel log ratios required')
    try:
        with np.errstate(all='raise'):
            q = np.asarray(logs, dtype=np.float64)
            projection = (q @ direction) / float(direction @ direction)
            residual = np.linalg.norm(q - projection[:, None] * direction, axis=1)
            bias = float(np.median(projection))
            off_axis = float(np.quantile(residual, .9))
    except (ArithmeticError, OverflowError) as exc:
        raise ValueError('unrepresentable natural statistics') from exc
    if not math.isfinite(bias) or not math.isfinite(off_axis):
        raise ValueError('nonfinite natural statistics')
    return dict(role=row['role'], pairs=count, coordinate_sha256=digest,
                bias=bias, off_axis_residual=off_axis)


def natural_bias_statistics(frames, *, operation):
    """Compute equal frame/role b and o from every saved 9x9 support item.

    Saved median summaries are not trusted. No amplitude, threshold, label,
    production eligibility or qualified decision is estimated here.
    """
    if type(operation) is not str or operation not in _DIRECTIONS:
        raise ValueError('operation has no conditional qualified direction')
    if type(frames) is not list or not 1 <= len(frames) <= 4096:
        raise ValueError('complete bounded frame sequence required')
    direction = np.asarray(_DIRECTIONS[operation], dtype=np.float64)
    results, expected_roles = [], None
    for index, frame in enumerate(frames):
        if (type(frame) is not dict or type(frame.get('source_frame_index')) is not int
                or frame['source_frame_index'] != index or frame.get('status') != 'measured'):
            raise ValueError('complete ordered measured frames required')
        feature = frame.get('features')
        if (type(feature) is not dict or type(feature.get('schema_version')) is not int
                or feature['schema_version'] != 1 or feature.get('algorithm') != ALGORITHM
                or type(feature.get('patch_size')) is not int or feature['patch_size'] != 9
                or feature.get('status') != 'measured' or feature.get('qualified') is not False
                or feature.get('ready_for_propose') is not False):
            raise ValueError('unaltered unqualified natural feature schema required')
        roles = feature.get('roles')
        if type(roles) is not list or not 1 <= len(roles) <= 2:
            raise ValueError('complete declared roles required')
        measured = [_role(row, direction) for row in roles]
        names = [r['role'] for r in measured]
        if names != sorted(set(names)):
            raise ValueError('ordered unique roles required')
        if expected_roles is None:
            expected_roles = names
        if names != expected_roles:
            raise ValueError('role coverage changes between frames')
        count = _integer(feature.get('valid_pairs'), 81)
        supplied = _integer(feature.get('input_pairs'), count)
        excluded = sum(_integer(feature.get(key)) for key in ('excluded_edge', 'excluded_extreme'))
        if count != sum(r['pairs'] for r in measured) or count + excluded > supplied:
            raise ValueError('natural support counts differ')
        results.append(dict(source_frame_index=index, roles=measured))
    values = [abs(row['bias']) for frame in results for row in frame['roles']]
    mean = math.fsum(value / len(values) for value in values)
    return dict(schema_version=1, algorithm=ALGORITHM, kind='unqualified_bias_statistics_v1',
        operation=operation, frame_count=len(results), role_count=len(expected_roles), frames=results,
        bias_mean_absolute=mean, bias_max_absolute=max(values),
        off_axis_maximum=max(row['off_axis_residual'] for f in results for row in f['roles']),
        ready_for_propose=False)


def compare_natural_bias(before, after, *, operation):
    """Compare the exact same frame/role/coordinate support; preserve signed maxima."""
    left = natural_bias_statistics(before, operation=operation)
    right = natural_bias_statistics(after, operation=operation)
    if (left['frame_count'], left['role_count']) != (right['frame_count'], right['role_count']):
        raise ValueError('before/after complete coverage differs')
    regressions, temporal = [], []
    for index, (bf, af) in enumerate(zip(left['frames'], right['frames'])):
        for role_index, (b, a) in enumerate(zip(bf['roles'], af['roles'])):
            if any(b[key] != a[key] for key in ('role', 'pairs', 'coordinate_sha256')):
                raise ValueError('before/after fixed support differs')
            regressions.append(abs(a['bias']) - abs(b['bias']))
            if index:
                previous_b = left['frames'][index-1]['roles'][role_index]['bias']
                previous_a = right['frames'][index-1]['roles'][role_index]['bias']
                temporal.append(abs(a['bias']-previous_a) - abs(b['bias']-previous_b))
    return dict(schema_version=1, algorithm=ALGORITHM, before=left, after=right,
        improvement=left['bias_mean_absolute']-right['bias_mean_absolute'],
        maximum_frame_bias_regression=max(regressions),
        maximum_off_axis_residual=max(left['off_axis_maximum'], right['off_axis_maximum']),
        maximum_temporal_bias_increase=max(temporal) if temporal else 0., ready_for_propose=False)
