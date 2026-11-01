"""Unqualified natural-video diagnostic features; no candidate rendering authority."""
import math

import numpy as np

from ..runtime.production_state import ProductionRefused

ALGORITHM = 'natural_constant_color_repair_v1'


def _image(value):
    if (not isinstance(value, np.ndarray) or value.dtype != np.uint8 or value.ndim != 3
            or value.shape[2] != 3 or value.nbytes > 32 * 1024 ** 2 or min(value.shape[:2]) < 1):
        raise ValueError('bounded RGB8 image required')
    return value


def _linear(value):
    rgb = value.astype(np.float64) / 255
    return np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)


def _patch(image, coordinate, box):
    if (type(coordinate) not in (list, tuple) or len(coordinate) != 2
            or any(type(v) is not int for v in coordinate)):
        raise ValueError('original integer sampled-pair coordinates required')
    if (type(box) not in (list, tuple) or len(box) != 4
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in box)
            or not box[0] < box[2] or not box[1] < box[3]):
        raise ValueError('explicit bounded declared region required')
    x, y = coordinate
    h, w = image.shape[:2]
    # Ordinary propagation can extend the declared region beyond the image.
    # Use its actual intersection; never invent padding or change coordinates.
    if (x - 4 < max(0, box[0]) * w or x + 5 > min(1, box[2]) * w
            or y - 4 < max(0, box[1]) * h or y + 5 > min(1, box[3]) * h):
        return None
    return image[y-4:y+5, x-4:x+5]


def natural_patch_features(reference, current, coordinates, regions):
    """Measure fixed 9x9 neighborhoods; preserve actual support failures and raw error."""
    reference, current = _image(reference), _image(current)
    if type(coordinates) is not list or len(coordinates) > 65536 or type(regions) is not dict:
        raise ValueError('bounded coordinate list and declared region mapping required')
    grouped = {}
    excluded_edge = excluded_extreme = 0
    seen = set()
    for row in coordinates:
        rid = row['region_id']
        region = regions[rid]
        key = (rid, *row['reference'], *row['current'])
        if key in seen:
            continue
        seen.add(key)
        left = _patch(reference, row['reference'], region['reference_rect'])
        right = _patch(current, row['current'], region['current_rect'])
        if left is None or right is None:
            excluded_edge += 1
            continue
        code_l = np.median(left.reshape(-1, 3), axis=0)
        code_r = np.median(right.reshape(-1, 3), axis=0)
        if ((code_l < 2) | (code_l > 253) | (code_r < 2) | (code_r > 253)).any():
            excluded_extreme += 1
            continue
        med_l = np.median(_linear(left).reshape(-1, 3), axis=0)
        med_r = np.median(_linear(right).reshape(-1, 3), axis=0)
        x1, y1 = row['reference']
        x2, y2 = row['current']
        raw = reference[y1, x1].astype(np.int16) - current[y2, x2].astype(np.int16)
        grouped.setdefault(region['role'], []).append((key, row, np.log2(med_l / med_r), np.abs(raw)))
    roles = []
    for role in sorted(grouped):
        rows = sorted(grouped[role], key=lambda v: v[0])
        if len(rows) > 1024:
            rows = [rows[i] for i in np.linspace(0, len(rows)-1, 1024, dtype=int)]
        logs = np.array([row[2] for row in rows])
        errors = np.array([row[3] for row in rows])
        roles.append(dict(role=role, pairs=len(rows), coordinates=[row[1] for row in rows],
            log2_ratios=logs.tolist(), median_log2_ratio=np.median(logs, axis=0).tolist(),
            raw_rgb=dict(mae=float(errors.mean()), p99_error=float(np.quantile(errors.max(axis=1), .99)),
                         max_error=int(errors.max()))))
    count = sum(row['pairs'] for row in roles)
    return dict(schema_version=1, algorithm=ALGORITHM, patch_size=9,
        status='measured' if count >= 81 else 'insufficient_support',
        input_pairs=len(coordinates), valid_pairs=count, excluded_edge=excluded_edge,
        excluded_extreme=excluded_extreme, roles=roles,
        qualified=False, ready_for_propose=False)


def estimate_natural_repair(features, *, operation, context, conditional_profile, natural_profile):
    """Only the mandated waiting branch exists until a qualified loader/study exists.

    Caller dictionaries cannot supply a qualification, threshold default, fit or
    rendering permission. This function deliberately has no fitting branch yet.
    """
    return dict(status='awaiting_qualification', algorithm=ALGORITHM, operation=operation,
        amplitude=None, reasons=['independent_natural_qualification_not_available'],
        production_eligible=False, ready_for_propose=False)
