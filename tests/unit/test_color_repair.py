"""Frozen arithmetic and refusal gates for conditional research repair."""
import importlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


PROFILE = Path('D:/VideoSi/projects/video-ai/continuity-benchmark/AI-repair-calibration-20261027-r2/experimental-repair-profile.json')


def repair():
    name = 'video_ai.media.color_repair'
    assert importlib.util.find_spec(name) is not None, 'pure numerical repair is not implemented'
    return importlib.import_module(name)


def profile():
    return json.loads(PROFILE.read_text(encoding='utf-8'))


def context(**changes):
    value = dict(comparable=True, intentional_lighting_change=False,
                 confirmed_motion_defect=False, subject_structure_intact=True,
                 operator_basis='Known green axis from original observation',
                 review=dict(path='D:/VideoSi/precheck.json', bytes=10, sha256='a' * 64))
    value.update(changes)
    return value


def pixels(n=100):
    return np.tile(np.array([[220, 250, 220]], dtype=np.uint8), (n, 1))


def fit(ref, cur, operation='wb_g', **kwargs):
    return repair().estimate_constant_repair(ref, cur, operation=operation,
        context=kwargs.get('context', context()), profile=kwargs.get('profile', profile()))


def calibration():
    path = Path(__file__).resolve().parents[2] / 'scripts/experiments/vco06_repair_calibration.py'
    spec = importlib.util.spec_from_file_location('frozen_repair_arithmetic', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('operation', ['exposure', 'wb_r', 'wb_g', 'wb_b'])
@pytest.mark.parametrize('amplitude', [-.125, 0., .125])
def test_transform_matches_frozen_calibration_bytes(operation, amplitude):
    rgb = np.arange(256, dtype=np.uint8).repeat(3).reshape(16, 16, 3)
    original = rgb.copy()
    out = repair().apply_constant_repair(rgb, operation=operation, amplitude=amplitude)
    assert out.tobytes() == calibration().transform(rgb, operation, amplitude).tobytes()
    assert out.dtype == np.uint8 and out.shape == rgb.shape
    assert not np.shares_memory(out, rgb)
    assert np.array_equal(rgb, original)


def test_transform_uses_linear_light_and_even_rounding():
    rgb = np.array([[0, 1, 10], [32, 128, 255]], np.uint8)
    out = repair().apply_constant_repair(rgb, operation='exposure', amplitude=-1.)
    assert out.tolist() == [[0, 0, 5], [20, 92, 188]]


def test_transform_writes_noncontiguous_image_pixels():
    rgb = np.arange(180, dtype=np.uint8).reshape(4, 15, 3).transpose(1, 0, 2)
    out = repair().apply_constant_repair(rgb, operation='exposure', amplitude=-1.)
    assert out.tobytes() == calibration().transform(rgb, 'exposure', -1.).tobytes()


def test_estimation_preflights_pixel_work_before_allocating():
    one = np.array([[[220, 250, 220]]], np.uint8)
    frames = np.broadcast_to(one, (2, 5500000, 3))
    # Inputs are 66 MiB, but fitting/scores/output working arrays exceed 128 MiB.
    with pytest.raises(ValueError, match='resource_limit'):
        fit(frames, frames)


def test_frame_limit_is_checked_before_iterating_broadcast_views():
    class NoIteration(np.ndarray):
        def __iter__(self):
            raise AssertionError('oversized frame input was materialized before resource validation')
    frames=np.broadcast_to(np.array([[[100,100,100]]],np.uint8),(4097,1,3)).view(NoIteration)
    with pytest.raises(ValueError,match='resource_limit'):
        repair().score_repair_pairs(frames,frames,frames)


@pytest.mark.parametrize('amplitude', [True, np.float64(.1), float('nan'), float('inf'), 8.01, '0'])
def test_transform_rejects_nonfinite_or_noncanonical_amplitude(amplitude):
    with pytest.raises(ValueError):
        repair().apply_constant_repair(pixels(), operation='exposure', amplitude=amplitude)


@pytest.mark.parametrize('rgb', [np.zeros((0, 3), np.uint8), np.zeros((3,), np.uint8),
    np.zeros((10, 4), np.uint8), np.zeros((10, 3), float), [[1, 2, 3]]])
def test_transform_rejects_malformed_rgb(rgb):
    with pytest.raises(ValueError):
        repair().apply_constant_repair(rgb, operation='exposure', amplitude=.01)


def test_unknown_operator_is_rejected_even_at_zero():
    with pytest.raises(ValueError):
        repair().apply_constant_repair(pixels(), operation='chroma', amplitude=0.)


def test_qualified_fit_is_one_constant_with_exact_sealed_bound():
    ref = [pixels(100), pixels(120)]
    cur = [np.tile(np.array([[219, 253, 219]], np.uint8), (len(x), 1)) for x in ref]
    result = fit(ref, cur)
    assert set(result) == {'status', 'operation', 'amplitude', 'correction_bound', 'fit_pairs', 'reasons'}
    assert result['status'] == 'estimated'
    assert -.03628187114179243 <= result['amplitude'] < 0
    assert result['fit_pairs'] == 220 and result['reasons'] == []
    bound = next(b for b in profile()['calibrated_bounds'] if b['operation'] == 'wb_g' and b['injection_direction'] == 1)
    assert result['correction_bound'] == bound


@pytest.mark.parametrize('delta', [0, 1, 2])
def test_stable_matching_codes_are_noop(delta):
    ref = np.full((100, 3), 120, np.uint8)
    result = fit(ref, ref + delta)
    assert result['status'] == 'noop' and result['amplitude'] == 0.
    assert result['correction_bound'] is None


@pytest.mark.parametrize('operation,cur', [('exposure', 100), ('wb_b', 150)])
def test_unqualified_direction_cannot_use_existing_bound(operation, cur):
    ref = np.full((100, 3), 150, np.uint8)
    current = np.full_like(ref, cur)
    if operation == 'wb_b':
        current[:, 2] = 160
    result = fit(ref, current, operation)
    assert result['status'] == 'abstained' and result['amplitude'] is None
    assert 'unqualified_direction' in result['reasons']


def test_out_of_bound_fit_is_refused_without_clamping():
    ref = pixels()
    cur = np.tile(np.array([[210, 253, 210]], np.uint8), (100, 1))
    result = fit(ref, cur)
    assert result['status'] == 'abstained' and result['amplitude'] is None
    assert 'correction_bound_exceeded' in result['reasons']


def test_empty_qualified_list_refuses_every_nonzero_fit():
    p = profile(); p['qualified_directions'] = []
    result = fit(pixels(), np.tile(np.array([[219, 253, 219]], np.uint8), (100, 1)), profile=p)
    assert result['status'] == 'abstained'
    assert 'unqualified_direction' in result['reasons']


@pytest.mark.parametrize('changes', [dict(comparable=False), dict(intentional_lighting_change=True),
    dict(confirmed_motion_defect=True), dict(subject_structure_intact=False),
    dict(comparable=1), dict(operator_basis=''), dict(extra=True), dict(review=None)])
def test_unknown_or_unsafe_context_abstains(changes):
    result = fit(pixels(), pixels(), context=context(**changes))
    assert result['status'] == 'abstained'
    assert 'context_gate' in result['reasons']


def test_each_frame_needs_support_before_identity_noop():
    result = fit([pixels(), pixels(80)], [pixels(), pixels(80)])
    assert result['status'] == 'abstained'
    assert 'insufficient_frame_pairs' in result['reasons']


def test_nonidentity_requires_informative_pairs():
    ref = np.zeros((100, 3), np.uint8); cur = np.full_like(ref, 3)
    result = fit(ref, cur)
    assert result['status'] == 'abstained'
    assert 'insufficient_informative_pairs' in result['reasons']


def test_fit_caps_informative_population_deterministically():
    ref = pixels(20000); cur = np.tile(np.array([[219, 253, 219]], np.uint8), (20000, 1))
    result = fit(ref, cur)
    assert result['status'] == 'estimated' and result['fit_pairs'] == 16384
    assert result == fit(ref, cur)


def test_scoring_preserves_every_frame_and_weighted_aggregate():
    ref = [np.full((100, 3), 100, np.uint8), np.full((200, 3), 100, np.uint8)]
    cur = [x + 3 for x in ref]; out = [ref[0] + 1, ref[1].copy()]
    result = repair().score_repair_pairs(ref, cur, out)
    assert result['before_mae'] == 3 and result['after_mae'] == pytest.approx(1/3)
    assert result['passed'] is True and result['reasons'] == []
    assert result['after'] == [dict(source_frame_index=0, mae=1., p99_error=1., max_error=1, new_clip=0),
                               dict(source_frame_index=1, mae=0., p99_error=0., max_error=0, new_clip=0)]


def test_single_regressing_frame_blocks_improved_aggregate():
    ref = np.full((2, 100, 3), 100, np.uint8)
    cur = ref.copy(); cur[0] += 4
    out = ref.copy(); out[1] += 1
    result = repair().score_repair_pairs(ref, cur, out)
    assert result['after_mae'] < result['before_mae']
    assert result['passed'] is False and 'frame_mae_regression:1' in result['reasons']


def test_sparse_severe_error_cannot_hide_below_p99():
    ref = np.full((1000, 3), 100, np.uint8); cur = ref + 4; out = ref.copy(); out[0] = 105
    result = repair().score_repair_pairs(ref, cur, out)
    assert result['after'][0]['p99_error'] == 0.
    assert result['passed'] is False and 'frame_max_error:0' in result['reasons']


def test_reference_interior_clipping_is_counted_per_channel():
    ref = np.tile(np.array([[3, 252, 253]], np.uint8), (100, 1)); cur = ref + np.array([1, -1, 0], np.int16)
    out = ref.copy(); out[0] = [0, 255, 255]
    result = repair().score_repair_pairs(ref, cur.astype(np.uint8), out)
    assert result['before'][0]['new_clip'] == 0 and result['after'][0]['new_clip'] == 2
    assert result['passed'] is False and 'frame_new_clip:0' in result['reasons']


def test_no_strict_improvement_blocks_equal_scores():
    ref = pixels(); cur = ref - 1
    result = repair().score_repair_pairs(ref, cur, cur.copy())
    assert result['passed'] is False and 'no_strict_improvement' in result['reasons']


def test_fit_scores_all_frames_including_unfavorable_frame_zero():
    ref = [pixels(81), pixels(1000)]
    cur = [ref[0].copy(), np.tile(np.array([[219, 253, 219]], np.uint8), (1000, 1))]
    result = fit(ref, cur)
    assert result['status'] == 'abstained'
    assert 'frame_mae_regression:0' in result['reasons']


@pytest.mark.parametrize('which', ['estimate', 'score'])
def test_mismatched_pair_shapes_raise(which):
    m = repair()
    with pytest.raises(ValueError):
        if which == 'estimate':
            fit([pixels(), pixels()], [pixels()])
        else:
            m.score_repair_pairs(pixels(), pixels(81), pixels())


def test_malformed_profile_cannot_enable_arithmetic():
    p = profile(); p['production_eligible'] = True
    with pytest.raises(ValueError):
        fit(pixels(), pixels(), profile=p)


def test_numerical_thread_setting_restored_on_success_and_failure():
    import cv2
    m = repair(); original = cv2.getNumThreads()
    cv2.setNumThreads(3)
    try:
        m.apply_constant_repair(pixels(), operation='exposure', amplitude=0.)
        assert cv2.getNumThreads() == 3
        with pytest.raises(ValueError):
            m.apply_constant_repair(pixels().astype(float), operation='exposure', amplitude=.1)
        assert cv2.getNumThreads() == 3
    finally:
        cv2.setNumThreads(original)
