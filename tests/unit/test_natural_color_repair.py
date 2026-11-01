"""Numerical research hypotheses; no synthetic sample is a natural success."""
import numpy as np
import pytest


def inputs():
    image = np.full((64, 64, 3), 128, np.uint8)
    points = [dict(region_id='subject', reference=[x,y], current=[x,y])
              for y in range(8, 56, 4) for x in range(8, 56, 4)]
    regions = dict(subject=dict(role='subject', reference_rect=[0,0,1,1], current_rect=[0,0,1,1]))
    return image, points, regions


def test_sparse_texture_and_constant_color_are_measured_separately():
    from video_ai.media.natural_color_repair import natural_patch_features
    image, points, regions = inputs()
    texture = image.copy()
    texture[::4, :, :] += 8
    measured = natural_patch_features(image, texture, points, regions)
    assert measured['status'] == 'measured'
    role = measured['roles'][0]
    assert role['raw_rgb']['max_error'] == 8
    assert np.max(np.abs(role['median_log2_ratio'])) == 0
    biased = natural_patch_features(image, image-4, points, regions)
    assert min(biased['roles'][0]['median_log2_ratio']) > 0


def test_boundary_support_cannot_be_invented():
    from video_ai.media.natural_color_repair import natural_patch_features
    image, _, regions = inputs()
    points = [dict(region_id='subject', reference=[0,0], current=[0,0])]
    measured = natural_patch_features(image, image, points, regions)
    assert measured['status'] == 'insufficient_support'
    assert measured['excluded_edge'] == 1
    assert measured['valid_pairs'] == 0


def test_absent_profile_never_enables_fitting_or_rendering():
    from video_ai.media.natural_color_repair import estimate_natural_repair
    result = estimate_natural_repair({}, operation='exposure', context={},
        conditional_profile=None, natural_profile=None)
    assert result['status'] == 'awaiting_qualification'
    assert result['amplitude'] is None
    assert result['ready_for_propose'] is False


def test_propagated_region_uses_only_its_intersection_with_actual_image():
    from video_ai.media.natural_color_repair import natural_patch_features
    image, points, regions = inputs()
    regions['subject']['current_rect'] = [-.01, -.01, 1.01, 1.01]
    measured = natural_patch_features(image, image, points, regions)
    assert measured['status'] == 'measured'
    assert measured['valid_pairs'] == len(points)
