"""Independent numerical fixtures; no real natural label or qualification is asserted."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from test_natural_repair_statistics import constant,frame


def conditional():
    return json.loads(Path('D:/VideoSi/projects/video-ai/continuity-benchmark/AI-repair-calibration-20261027-r2/experimental-repair-profile.json').read_bytes())


def thresholds():
    return dict(noop_bias_ceiling=.002,minimum_bias_improvement=.005,maximum_frame_bias_regression=.001,
                maximum_off_axis_residual=.02,maximum_temporal_bias_increase=.001)


def test_known_axis_uses_channel_median_projection_and_one_constant_parameter():
    from video_ai.media.natural_repair_engine import fit_natural_parameter
    result=fit_natural_parameter([constant(0,-.01),constant(1,-.012)],operation='exposure',conditional_profile=conditional())
    assert result['status']=='estimated' and result['amplitude']==pytest.approx(-.011)
    assert result['correction_direction']=='negative' and result['fit_pairs']==162
    assert result['ready_for_propose'] is False


@pytest.mark.parametrize('operation,logs,want',[('wb_r',[-.01,.005,.005],-.01),('wb_g',[-.005,.01,-.005],.01)])
def test_white_balance_projection_respects_qualified_sign(operation,logs,want):
    from video_ai.media.natural_repair_engine import fit_natural_parameter
    out=fit_natural_parameter([frame(0,{'subject':[logs]*81})],operation=operation,conditional_profile=conditional())
    assert out['status']=='estimated' and out['amplitude']==pytest.approx(want)


@pytest.mark.parametrize('value,reason',[(.01,'unqualified_direction'),(-.1,'correction_bound_exceeded')])
def test_no_sign_switch_or_bound_clamp(value,reason):
    from video_ai.media.natural_repair_engine import fit_natural_parameter
    out=fit_natural_parameter([constant(0,value)],operation='exposure',conditional_profile=conditional())
    assert out['status']=='abstained' and out['amplitude'] is None and reason in out['reasons']


def test_zero_parameter_is_noop_and_all_frames_need_support():
    from video_ai.media.natural_repair_engine import fit_natural_parameter
    assert fit_natural_parameter([constant(0,0)],operation='exposure',conditional_profile=conditional())['status']=='noop'
    bad=constant(1,0,count=80)
    assert fit_natural_parameter([constant(0,-.01),bad],operation='exposure',conditional_profile=conditional())['status']=='abstained'


def test_fitting_support_is_deterministically_bounded_without_dropping_score_frames():
    from video_ai.media.natural_repair_engine import fit_natural_parameter
    rows=[constant(i,-.01,count=1024) for i in range(20)]
    out=fit_natural_parameter(rows,operation='exposure',conditional_profile=conditional())
    assert out['fit_pairs']==16384 and out['frame_count']==20 and out['amplitude']==pytest.approx(-.01)


@pytest.mark.parametrize('operation',['wb_b','chroma','auto',None])
def test_no_extra_axis_or_automatic_choice(operation):
    from video_ai.media.natural_repair_engine import fit_natural_parameter
    with pytest.raises(ValueError): fit_natural_parameter([constant(0,0)],operation=operation,conditional_profile=conditional())


def test_complete_fixed_support_positive_improvement_is_numerically_accepted():
    from video_ai.media.natural_repair_engine import assess_natural_change
    out=assess_natural_change([constant(0,.01),constant(1,.012)],[constant(0,.001),constant(1,.001)],operation='exposure',thresholds=thresholds())
    assert out['status']=='estimated' and out['metrics']['improvement']==pytest.approx(.01)
    assert out['metrics']['maximum_frame_bias_regression']==pytest.approx(-.009)
    assert out['ready_for_propose'] is False


def test_orthogonal_damage_cannot_be_hidden_by_zero_projected_bias_noop():
    from video_ai.media.natural_repair_engine import assess_natural_change
    rows=[frame(0,{'subject':[[.1,-.1,0.]]*81})]
    out=assess_natural_change(rows,rows,operation='exposure',thresholds=thresholds())
    assert out['status']=='abstained' and 'maximum_off_axis_residual' in out['reasons']


def test_unchanged_stable_source_is_noop_with_negative_nonzero_repair_regression_caps():
    from video_ai.media.natural_repair_engine import assess_natural_change
    bounds=thresholds();bounds.update(maximum_frame_bias_regression=-.001,maximum_temporal_bias_increase=-.001)
    frames=[constant(0,0),constant(1,0)]
    assert assess_natural_change(frames,frames,operation='exposure',thresholds=bounds)['status']=='noop'


def test_negative_regression_cap_remains_strict_for_nonzero_repairs():
    from video_ai.media.natural_repair_engine import assess_natural_change
    bounds=thresholds();bounds['maximum_frame_bias_regression']=-.02
    result=assess_natural_change([constant(0,-.02)],[constant(0,-.001)],operation='exposure',thresholds=bounds)
    assert result['status']=='abstained' and 'maximum_frame_bias_regression' in result['reasons']


@pytest.mark.parametrize('problem',['no_improvement','frame','off_axis','temporal','support'])
def test_global_improvement_cannot_hide_any_frame_role_or_support_failure(problem):
    from video_ai.media.natural_repair_engine import assess_natural_change
    before=[constant(0,.01),constant(1,.02)];after=[constant(0,.001),constant(1,.001)]
    if problem=='no_improvement': after=deepcopy(before)
    elif problem=='frame': after=[constant(0,.012),constant(1,0)]
    elif problem=='off_axis': after=[frame(i,{'subject':[[.05,-.05,0]]*81}) for i in range(2)]
    elif problem=='temporal': after=[constant(0,-.009),constant(1,.009)];before=[constant(0,.02),constant(1,.02)]
    else: after[1]['features']['roles'][0]['coordinates'][0]['current'][0]+=1
    if problem=='support':
        with pytest.raises(ValueError): assess_natural_change(before,after,operation='exposure',thresholds=thresholds())
    else:
        assert assess_natural_change(before,after,operation='exposure',thresholds=thresholds())['status']=='abstained'


@pytest.mark.parametrize('value',[None,{},dict(noop_bias_ceiling=True),{**thresholds(),'minimum_bias_improvement':float('nan')}])
def test_thresholds_must_be_explicit_exact_finite_values(value):
    from video_ai.media.natural_repair_engine import assess_natural_change
    with pytest.raises(ValueError): assess_natural_change([constant(0,.01)],[constant(0,0)],operation='exposure',thresholds=value)


def samples():
    controls={k:[dict(maximum_frame_bias_regression=f,maximum_off_axis_residual=o,maximum_temporal_bias_increase=t)]
              for k,f,o,t in [('wrong_direction',.02,.01,.001),('overcorrection',.03,.01,.001),
                  ('mixed_axis',.001,.04,.001),('local',.001,.05,.001),('temporal',.001,.01,.02)]}
    values=[]
    for i in range(4):
        values.append(dict(case_id=f'p{i}',scene_group=f'g{i}',domain='fixture',natural_label='mild_color_bias',
            operation='exposure',correction_direction='negative',projection_operation='exposure',projection_direction='negative',
            status='measured',initial_bias=.012+i*.001,improvement=.009+i*.001,
            maximum_frame_bias_regression=.001+i*.001,maximum_off_axis_residual=.01+i*.001,
            maximum_temporal_bias_increase=.001+i*.001,controls=deepcopy(controls)))
    values.append(dict(values[0],case_id='n',scene_group='neutral',natural_label='neutral',operation=None,correction_direction=None,
        initial_bias=.002,improvement=.001))
    return values


def test_strict_midpoints_are_derived_from_all_positive_and_harmful_bounds():
    from video_ai.media.natural_repair_engine import derive_natural_thresholds
    out=derive_natural_thresholds(samples(),operation='exposure',direction='negative')
    assert out['status']=='separated' and out['positive_groups']==4
    assert out['thresholds']==pytest.approx(dict(noop_bias_ceiling=.007,minimum_bias_improvement=.005,
        maximum_frame_bias_regression=.012,maximum_off_axis_residual=.0265,maximum_temporal_bias_increase=.012))
    assert out['ready_for_propose'] is False


@pytest.mark.parametrize('problem',['same_group','missing_positive','unknown','failed','overlap','no_neutral','missing_control','wrong_projection','duplicate'])
def test_no_qualification_from_missing_groups_labels_controls_or_nonseparation(problem):
    from video_ai.media.natural_repair_engine import derive_natural_thresholds
    rows=samples()
    if problem=='same_group': rows[3]['scene_group']='g0'
    elif problem=='missing_positive': rows.pop(3)
    elif problem=='unknown': rows[-1]['natural_label']='unverified'
    elif problem=='failed': rows[0]['status']='failed'
    elif problem=='overlap': rows[-1]['initial_bias']=.012
    elif problem=='no_neutral': rows.pop()
    elif problem=='missing_control':
        for row in rows: row['controls']['temporal']=[]
    elif problem=='wrong_projection': rows[0]['projection_operation']='wb_r'
    else: rows[1]['case_id']='p0'
    if problem in ('wrong_projection','duplicate'):
        with pytest.raises(ValueError): derive_natural_thresholds(rows,operation='exposure',direction='negative')
    else:
        out=derive_natural_thresholds(rows,operation='exposure',direction='negative')
        assert out['status']=='unqualified' and out['thresholds'] is None
