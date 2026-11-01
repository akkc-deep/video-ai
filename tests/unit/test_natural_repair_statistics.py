"""Independent statistical examples; fixture features do not establish natural quality."""
from copy import deepcopy
import math

import pytest


def frame(index, roles):
    feature_roles = []
    for role, logs in sorted(roles.items()):
        coordinates = [dict(region_id=role, reference=[8+i, 8], current=[8+i, 8])
                       for i in range(len(logs))]
        feature_roles.append(dict(role=role, pairs=len(logs), coordinates=coordinates,
            log2_ratios=logs, median_log2_ratio=[0., 0., 0.],
            raw_rgb=dict(mae=0., p99_error=0., max_error=0)))
    count = sum(r['pairs'] for r in feature_roles)
    return dict(source_frame_index=index, status='measured', reasons=[],
        features=dict(schema_version=1, algorithm='natural_constant_color_repair_v1',
            patch_size=9, status='measured', input_pairs=count, valid_pairs=count,
            excluded_edge=0, excluded_extreme=0, roles=feature_roles,
            qualified=False, ready_for_propose=False))


def constant(index, value, *, role='subject', count=81):
    return frame(index, {role: [[value]*3 for _ in range(count)]})


def test_frame_and_role_means_have_equal_weight_despite_unequal_pair_counts():
    from video_ai.media.natural_repair_statistics import natural_bias_statistics
    rows = [frame(0, {'background': [[.1]*3]*81, 'subject': [[.3]*3]*162}),
            frame(1, {'background': [[.5]*3]*162, 'subject': [[.7]*3]*81})]
    result = natural_bias_statistics(rows, operation='exposure')
    assert result['bias_mean_absolute'] == pytest.approx(.4)
    assert result['bias_max_absolute'] == pytest.approx(.7)
    assert result['off_axis_maximum'] == pytest.approx(0)
    assert result['frame_count'] == 2 and result['role_count'] == 2


def test_off_axis_is_p90_of_per_point_orthogonal_l2_then_row_maximum():
    from video_ai.media.natural_repair_statistics import natural_bias_statistics
    rows = [frame(0, {'subject': [[0., 0., 0.]]*90 + [[1., -1., 0.]]*10})]
    result = natural_bias_statistics(rows, operation='exposure')
    assert result['bias_mean_absolute'] == 0
    assert result['off_axis_maximum'] == pytest.approx(math.sqrt(2)*.1)


@pytest.mark.parametrize('operation,vector', [('exposure', [1,1,1]),
    ('wb_r', [1,-.5,-.5]), ('wb_g', [-.5,1,-.5])])
def test_projection_uses_declared_direction_and_its_squared_norm(operation, vector):
    from video_ai.media.natural_repair_statistics import natural_bias_statistics
    rows = [frame(0, {'subject': [[v*.02 for v in vector]]*81})]
    result = natural_bias_statistics(rows, operation=operation)
    assert result['frames'][0]['roles'][0]['bias'] == pytest.approx(.02)
    assert result['off_axis_maximum'] == pytest.approx(0)


def test_signed_frame_regression_and_temporal_increase_are_not_clamped():
    from video_ai.media.natural_repair_statistics import compare_natural_bias
    result = compare_natural_bias([constant(0, 1.), constant(1, 3.)],
        [constant(0, .5), constant(1, 1.)], operation='exposure')
    assert result['improvement'] == pytest.approx(1.25)
    assert result['maximum_frame_bias_regression'] == pytest.approx(-.5)
    assert result['maximum_temporal_bias_increase'] == pytest.approx(-1.5)


def test_single_frame_has_zero_temporal_increase():
    from video_ai.media.natural_repair_statistics import compare_natural_bias
    result = compare_natural_bias([constant(0, .03)], [constant(0, .01)], operation='exposure')
    assert result['maximum_temporal_bias_increase'] == 0


@pytest.mark.parametrize('change', ['drop_frame','reorder_frame','drop_role','change_coordinate','drop_point'])
def test_before_after_cannot_select_different_frames_roles_or_support(change):
    from video_ai.media.natural_repair_statistics import compare_natural_bias
    original = [frame(i, {'background': [[.01]*3]*81, 'subject': [[.02]*3]*81}) for i in range(2)]
    altered = deepcopy(original)
    if change == 'drop_frame': altered.pop()
    elif change == 'reorder_frame': altered.reverse()
    elif change == 'drop_role': altered[1]['features']['roles'].pop()
    elif change == 'change_coordinate': altered[0]['features']['roles'][0]['coordinates'][0]['current'][0] += 1
    else:
        row = altered[0]['features']['roles'][0]
        row['pairs'] -= 1; row['coordinates'].pop(); row['log2_ratios'].pop()
        altered[0]['features']['valid_pairs'] -= 1
    with pytest.raises(ValueError): compare_natural_bias(original, altered, operation='exposure')


@pytest.mark.parametrize('change', ['nan','infinity','bool_value','bool_index','unsupported',
    'incomplete','false_count','duplicate','empty','bad_role','too_many_pairs','missing_feature'])
def test_invalid_or_incomplete_evidence_cannot_become_a_statistic(change):
    from video_ai.media.natural_repair_statistics import natural_bias_statistics
    rows = [constant(0, .01)]
    role = rows[0]['features']['roles'][0]
    operation = 'exposure'
    if change == 'nan': role['log2_ratios'][0][0] = float('nan')
    elif change == 'infinity': role['log2_ratios'][0][0] = float('inf')
    elif change == 'bool_value': role['log2_ratios'][0][0] = True
    elif change == 'bool_index': rows[0]['source_frame_index'] = False
    elif change == 'unsupported': operation = 'wb_b'
    elif change == 'incomplete': rows[0]['status'] = 'not_comparable'
    elif change == 'false_count': rows[0]['features']['valid_pairs'] += 1
    elif change == 'duplicate': role['coordinates'][1] = deepcopy(role['coordinates'][0])
    elif change == 'empty': rows = []
    elif change == 'bad_role': role['role'] = 'unverified'
    elif change == 'too_many_pairs': rows = [constant(0, .01, count=1025)]
    else: rows[0]['features'] = None
    with pytest.raises(ValueError): natural_bias_statistics(rows, operation=operation)
