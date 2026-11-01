"""Conditional constant sRGB arithmetic; no media or calibration authority.

Pair inputs are (N, 3), (F, N, 3), or a list/tuple of (N_f, 3)
uint8 arrays. Their order is the complete native source frame order. The
caller verifies correspondence, coordinates, per-role sampling and evidence.
"""
from contextlib import contextmanager
from copy import deepcopy
import math
from pathlib import PureWindowsPath
import re

from ._continuity_geometry import CV_LOCK, numerical


_OPERATIONS = ('exposure', 'wb_r', 'wb_g', 'wb_b')
_MAX_RGB = 32 * 1024 * 1024
_MAX_WORK = 128 * 1024 * 1024
_CHUNK = 65536


@contextmanager
def _numerical_context():
    np, cv = numerical()
    with CV_LOCK:
        previous = cv.getNumThreads()
        try:
            cv.setNumThreads(1)
            with np.errstate(divide='raise', invalid='raise', over='raise'):
                yield np
        finally:
            cv.setNumThreads(previous)


def _rgb(value, np):
    if (not isinstance(value, np.ndarray) or value.dtype != np.uint8 or
            value.ndim < 2 or value.shape[-1] != 3 or not value.size):
        raise ValueError('nonempty uint8 RGB required')
    if value.nbytes > _MAX_RGB:
        raise ValueError('resource_limit: RGB frame')
    return value


def _operation(operation):
    if type(operation) is not str or operation not in _OPERATIONS:
        raise ValueError('known diagonal operation required')


def _direction(operation, np):
    if operation == 'exposure':
        return np.ones(3)
    result = np.full(3, -.5)
    result[_OPERATIONS.index(operation) - 1] = 1.
    return result


def _linear(rgb, np):
    u = rgb.astype(np.float64) / 255
    return np.where(u <= .04045, u / 12.92, ((u + .055) / 1.055) ** 2.4)


def _apply(rgb, operation, amplitude, np):
    out = rgb.copy()
    if amplitude == 0:
        return out
    source = rgb.reshape(-1, 3)
    target = out.reshape(-1, 3)
    gain = np.exp2(amplitude * _direction(operation, np))
    for start in range(0, len(source), _CHUNK):
        linear = np.clip(_linear(source[start:start + _CHUNK], np) * gain, 0, 1)
        u = np.where(linear <= .0031308, linear * 12.92,
                     1.055 * linear ** (1 / 2.4) - .055)
        target[start:start + _CHUNK] = np.rint(np.clip(u, 0, 1) * 255).astype(np.uint8)
    return out


def apply_constant_repair(rgb, *, operation, amplitude):
    """Apply one finite constant diagonal transform, returning fresh uint8 RGB.

    This arithmetic primitive allows |a| <= 8; candidate authority comes only
    from estimate_constant_repair and the caller's verified sealed profile.
    """
    with _numerical_context() as np:
        _rgb(rgb, np); _operation(operation)
        if type(amplitude) not in (int, float) or not math.isfinite(amplitude) or abs(amplitude) > 8:
            raise ValueError('bounded finite canonical amplitude required')
        return _apply(rgb, operation, amplitude, np)


def _frames(value, np):
    if isinstance(value, np.ndarray):
        if value.ndim == 2:
            frames = [value]
        elif value.ndim == 3:
            if not 1 <= value.shape[0] <= 4096:
                raise ValueError('resource_limit: nonempty frames <=4096 required')
            frames = list(value)
        else:
            raise ValueError('pair arrays require (N,3) or (F,N,3)')
    elif type(value) in (list, tuple):
        if not 1 <= len(value) <= 4096:
            raise ValueError('resource_limit: nonempty frames <=4096 required')
        frames = list(value)
    else:
        raise ValueError('RGB pair frames required')
    if not frames or len(frames) > 4096:
        raise ValueError('resource_limit: nonempty frames <=4096 required')
    for frame in frames:
        _rgb(frame, np)
        if frame.ndim != 2:
            raise ValueError('each pair frame requires (N,3)')
    return frames


def _pairs(np, *values):
    groups = [_frames(value, np) for value in values]
    expected = [frame.shape for frame in groups[0]]
    if any([frame.shape for frame in frames] != expected for frames in groups[1:]):
        raise ValueError('same scoring frame and pair shapes required')
    raw_bytes = sum(frame.nbytes for frames in groups for frame in frames)
    # Account conservatively for int16 differences, masks, indices and output,
    # before any numerical allocation (broadcast/strided inputs included).
    largest = max(frame.nbytes for frame in groups[0])
    if raw_bytes + 6 * largest > _MAX_WORK:
        raise ValueError('resource_limit: pair pixels')
    return groups


def _context_allowed(value):
    fields = {'comparable', 'intentional_lighting_change', 'confirmed_motion_defect',
              'subject_structure_intact', 'operator_basis', 'review'}
    if type(value) is not dict or set(value) != fields:
        return False
    flags = ('comparable', 'intentional_lighting_change', 'confirmed_motion_defect', 'subject_structure_intact')
    if any(type(value[k]) is not bool for k in flags):
        return False
    if [value[k] for k in flags] != [True, False, False, True]:
        return False
    if type(value['operator_basis']) is not str or not value['operator_basis'].strip():
        return False
    review = value['review']
    return (type(review) is dict and set(review) == {'path', 'bytes', 'sha256'} and
            type(review['path']) is str and PureWindowsPath(review['path']).is_absolute() and
            type(review['bytes']) is int and review['bytes'] > 0 and
            type(review['sha256']) is str and re.fullmatch('[0-9a-f]{64}', review['sha256']) is not None)


def _profile(profile):
    """Check arithmetic authority fields; runtime verifies the complete closure."""
    if (type(profile) is not dict or profile.get('purpose') != 'offline_AI_repair_calibration' or
            profile.get('algorithm') != 'AI_conditional_constant_color_repair_v1' or
            profile.get('production_eligible') is not False or profile.get('evidence_only') is not True):
        raise ValueError('validated evidence-only repair profile required')
    qualified, bounds = profile.get('qualified_directions'), profile.get('calibrated_bounds')
    if type(qualified) is not list or type(bounds) is not list:
        raise ValueError('sealed direction lists required')
    known = set(_OPERATIONS) | {'chroma'}
    keys = set()
    for row in qualified:
        if (type(row) is not dict or set(row) != {'operation', 'injection_direction'} or
                type(row['operation']) is not str or row['operation'] not in known or
                type(row['injection_direction']) is not int or row['injection_direction'] not in (-1, 1)):
            raise ValueError('invalid qualified direction')
        key = (row['operation'], row['injection_direction'])
        if key in keys:
            raise ValueError('duplicate qualified direction')
        keys.add(key)
    indexed = {}
    for row in bounds:
        if (type(row) is not dict or not {'operation', 'injection_direction', 'correction_direction',
                'correction_amplitude_ceiling'} <= set(row) or
                type(row['operation']) is not str or row['operation'] not in known or
                type(row['injection_direction']) is not int or row['injection_direction'] not in (-1, 1) or
                type(row['correction_direction']) is not int or row['correction_direction'] != -row['injection_direction']):
            raise ValueError('invalid sealed correction bound')
        key = (row['operation'], row['injection_direction'])
        ceiling = row['correction_amplitude_ceiling']
        if key in indexed or (ceiling is not None and (type(ceiling) not in (int, float) or
                not math.isfinite(ceiling) or not 0 < ceiling <= 8)):
            raise ValueError('invalid correction amplitude ceiling')
        indexed[key] = row
    if any(key not in indexed or indexed[key]['correction_amplitude_ceiling'] is None for key in keys):
        raise ValueError('qualified direction lacks sealed bound')
    return keys, indexed


def _frame_metrics(ref, value, index, np):
    maximums = np.empty(len(ref), np.uint8)
    total = 0
    clips = 0
    for start in range(0, len(ref), _CHUNK):
        r, v = ref[start:start + _CHUNK], value[start:start + _CHUNK]
        error = np.abs(v.astype(np.int16) - r)
        maximums[start:start + len(r)] = error.max(axis=1)
        total += int(error.sum())
        clips += int(np.count_nonzero((r >= 3) & (r <= 252) & ((v == 0) | (v == 255))))
    return dict(source_frame_index=index, mae=total / ref.size,
                p99_error=float(np.quantile(maximums, .99)),
                max_error=int(maximums.max()), new_clip=clips)


def _score(reference, current, repaired, np):
    before, after, reasons = [], [], []
    before_total = after_total = channels = 0
    for i, (ref, cur, out) in enumerate(zip(reference, current, repaired)):
        b, a = _frame_metrics(ref, cur, i, np), _frame_metrics(ref, out, i, np)
        before.append(b); after.append(a)
        before_total += round(b['mae'] * ref.size)
        after_total += round(a['mae'] * ref.size)
        channels += ref.size
        for condition, reason in ((a['p99_error'] > 2, 'frame_p99_error'),
                (a['max_error'] > 4, 'frame_max_error'),
                (a['new_clip'] > b['new_clip'], 'frame_new_clip'),
                (a['mae'] > b['mae'], 'frame_mae_regression')):
            if condition:
                reasons.append(f'{reason}:{i}')
    if after_total >= before_total:
        reasons.append('no_strict_improvement')
    return dict(before=before, after=after, before_mae=before_total / channels,
                after_mae=after_total / channels, passed=not reasons, reasons=reasons)


def score_repair_pairs(reference, current, repaired):
    """Score every frame; clipping is per reference-interior [3,252] channel.

    Returns before/after rows {source_frame_index,mae,p99_error,max_error,
    new_clip}, pair-weighted before_mae/after_mae, passed and reasons.
    """
    with _numerical_context() as np:
        return _score(*_pairs(np, reference, current, repaired), np)


def estimate_constant_repair(reference, current, *, operation, context, profile):
    """Fit one constant parameter, refusing unqualified or regressing repairs.

    The six output fields follow fit.json's pure-estimator contract. No bound
    is clamped, no alternate operation is attempted and no frame is dropped.
    """
    with _numerical_context() as np:
        _operation(operation)
        qualified, bounds = _profile(profile)
        ref, cur = _pairs(np, reference, current)

        def result(status, amplitude=None, bound=None, pairs=0, reasons=()):
            return dict(status=status, operation=operation, amplitude=amplitude,
                        correction_bound=deepcopy(bound), fit_pairs=pairs, reasons=list(reasons))

        if not _context_allowed(context):
            return result('abstained', reasons=['context_gate'])
        if any(len(frame) < 81 for frame in ref):
            return result('abstained', reasons=['insufficient_frame_pairs'])
        # The two-code engineering no-operation gate precedes informative fit.
        if all(np.max(np.abs(r.astype(np.int16) - c)) <= 2 for r, c in zip(ref, cur)):
            return result('noop', 0., reasons=['stable_matching_codes'])
        counts = []
        for r, c in zip(ref, cur):
            counts.append(int(np.count_nonzero(((r >= 2) & (r <= 253) & (c >= 2) & (c <= 253)).all(axis=1))))
        informative = sum(counts)
        if informative < 81:
            return result('abstained', reasons=['insufficient_informative_pairs'])
        count = min(informative, 16384)
        chosen = np.linspace(0, informative - 1, count, dtype=int)
        selected_ref, selected_cur = [], []
        offset = 0
        for r, c, n in zip(ref, cur, counts):
            local = chosen[(chosen >= offset) & (chosen < offset + n)] - offset
            if len(local):
                valid = np.flatnonzero(((r >= 2) & (r <= 253) & (c >= 2) & (c <= 253)).all(axis=1))
                indices = valid[local]
                selected_ref.append(r[indices]); selected_cur.append(c[indices])
            offset += n
        r, c = np.concatenate(selected_ref), np.concatenate(selected_cur)
        direction = _direction(operation, np)
        logs = np.median(np.log2(_linear(r, np) / _linear(c, np)), axis=0)
        amplitude = float(logs @ direction / (direction @ direction))
        if not math.isfinite(amplitude) or abs(amplitude) > 8:
            return result('abstained', pairs=count, reasons=['numerical_domain'])
        if amplitude == 0:
            return result('noop', 0., pairs=count, reasons=['zero_amplitude'])
        key = (operation, -1 if amplitude > 0 else 1)
        if key not in qualified:
            return result('abstained', pairs=count, reasons=['unqualified_direction'])
        bound = bounds[key]
        if abs(amplitude) > bound['correction_amplitude_ceiling']:
            return result('abstained', bound=bound, pairs=count, reasons=['correction_bound_exceeded'])
        repaired = (_apply(c, operation, amplitude, np) for c in cur)
        scores = _score(ref, cur, repaired, np)
        if not scores['passed']:
            return result('abstained', bound=bound, pairs=count, reasons=scores['reasons'])
        return result('estimated', amplitude, bound, count)
