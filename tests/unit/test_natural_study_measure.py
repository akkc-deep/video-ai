"""Quantized pixel oracles; constructed imagery is software evidence only."""
from copy import deepcopy
import numpy as np
import pytest


def pixels():
    a=np.full((128,128,3),120,dtype=np.uint8)
    coords=[dict(region_id='r',reference=[x,y],current=[x,y]) for y in range(12,115,10) for x in range(12,115,10)]
    regions=dict(r=dict(role='subject',reference_rect=[0,0,1,1],current_rect=[0,0,1,1]))
    return a,coords,regions


def test_quantized_measurement_keeps_raw_errors_and_fixed_support():
    from video_ai.runtime.natural_study_measure import transform,measure_pixels
    a,coords,regions=pixels()
    b=transform(a,dict(kind='constant',operation='exposure',amplitude=.02),0,2)
    f=measure_pixels(a,b,coords,regions,0)
    assert f['status']=='measured' and f['features']['valid_pairs']==121
    assert f['features']['roles'][0]['raw_rgb']['max_error']>0
    assert b.dtype==np.uint8 and not np.array_equal(a,b)


def test_controls_are_actual_quantized_copies_and_identity_is_exact():
    from video_ai.runtime.natural_study_measure import control_recipes,transform
    a,_,_=pixels();raw=a.tobytes()
    a[0,0]=220;raw=a.tobytes()
    recipes=control_recipes('exposure',.02)
    assert {'identity','wrong_direction','overcorrection','mixed_axis','local','temporal','clip','structural'}<=set(r['name'] for r in recipes)
    assert np.array_equal(a,transform(a,recipes[0],0,4))
    outputs=[transform(a,r,1,4) for r in recipes]
    assert any((o==255).any() for o in outputs)
    assert a.tobytes()==raw


def test_support_loss_is_refused_instead_of_resampled():
    from video_ai.runtime.natural_study_measure import measure_pixels,fixed_compare
    a,c,r=pixels();before=[measure_pixels(a,a,c,r,0)]
    bad=a.copy();bad[:]=255
    after=[measure_pixels(a,bad,c,r,0)]
    with pytest.raises(ValueError): fixed_compare(before,after,operation='exposure')


def test_unknown_or_noncolor_history_never_gets_dry_fit_authority():
    from video_ai.runtime.natural_study_measure import safe_author
    good=dict(natural_label='mild_color_bias',operation='exposure',correction_direction='negative',
        target_reference_confirmed=True,subject_structure_intact=True,motion_intact=True,
        intentional_lighting_change=False,unresolved=False,hard_noncolor_failure=False)
    assert safe_author(good)
    for key,value in [('unresolved',True),('hard_noncolor_failure',True),('motion_intact',None),('intentional_lighting_change',True),('operation',None)]:
        bad=deepcopy(good);bad[key]=value
        assert not safe_author(bad)


def test_replay_does_not_let_projection_relabel_unknown_author_as_refused_negative(tmp_path,monkeypatch):
    from video_ai.runtime import natural_study_measure as m
    from video_ai.media import research_pair_report as reports
    from natural_study_helpers import save
    manifest=save(tmp_path/'manifest.json',dict(fixture=True))
    case=dict(case_id='fixture',scene_group='g',domain='fixture',manifest=manifest)
    context=dict(commit=manifest,epoch=manifest)
    author=dict(natural_label='unverified',operation=None,correction_direction=None,unresolved=True,hard_noncolor_failure=False)
    monkeypatch.setattr(m,'case_context',lambda *a,**k:context)
    monkeypatch.setattr(m,'read_author_observations',lambda *a,**k:author)
    monkeypatch.setattr(reports,'validate_research_pair_report',lambda *a,**k:dict(report={}))
    result=dict(case=case,material=manifest,epoch=manifest,author=author,report=manifest,original=[],dry=[],fit=None,preview=None,
        controls={op+':'+d:[dict(recipe=r,status='refused',frames=[],reason='fixture') for r in m.control_recipes(op,.01 if d=='positive' else -.01)] for op,d in m.DIRECTIONS},
        projections=[dict(case_id='fixture',scene_group='g',domain='fixture',natural_label='unsafe',operation=None,correction_direction=None,
            projection_operation=op,projection_direction=d,status='refused',controls={}) for op,d in m.DIRECTIONS])
    with pytest.raises(ValueError,match='author'): m.replay_case(result,config=None,conditional_profile={})
