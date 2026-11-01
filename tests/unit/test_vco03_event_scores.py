"""Physical/scoping regressions for the isolated v3 experimental scorer."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import pytest

def module():
    path=Path(__file__).resolve().parents[2]/'scripts/experiments/vco03_event_scores.py'
    assert path.exists(),'experimental event scorer is missing'
    spec=importlib.util.spec_from_file_location('vco03_event_scores',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def fixture(joins=(6,),role='background',steps=None):
    steps=steps or [40]*12;t=0;samples=[]
    for i,dt in enumerate(steps):
        t+=dt
        samples.append(dict(frame_id=f'display_{i}',timestamp=dict(pts=t,time_base='1/1000'),camera_translation=[0.,0.],camera_rotation=0.,camera_log_scale=0.,camera_compensated_velocity=[0.,0.]))
    points=dict(trajectories=[dict(region_id='roi',samples=samples)])
    control=dict(anchors=[dict(region_id='roi',role=role)],comparisons=[dict(kind='parent_join',left=f'display_{j-1}',right=f'display_{j}',region_ids=['roi']) for j in joins],context=None)
    return points,control,samples

def score(points,control,detector='camera_jump',interval=(0,12)):
    return module().event_case(points,control,1920,1080,'roi',detector,interval)

def test_stationary_camera_tiny_noise_and_declared_jump():
    p,c,s=fixture();s[6]['camera_translation']=[.08,0.]
    result=score(p,c)
    assert result['state']=='comparable' and result['score']==pytest.approx(20.48)
    assert result['events'][0]['frame_id']=='display_6'
    s[6]['camera_translation']=[1e-7,-1e-7];s[6]['camera_rotation']=1e-7
    assert score(p,c)['score']<.001

@pytest.mark.parametrize('kind',['translation','rotation','scale'])
def test_constant_camera_motion_is_not_a_jump(kind):
    p,c,s=fixture()
    for sample in s:
        if kind=='translation':sample['camera_translation']=[.01,0.]
        elif kind=='rotation':sample['camera_rotation']=.01
        else:sample['camera_log_scale']=.01
    assert score(p,c)['score']==pytest.approx(0.,abs=1e-10)

def test_native_unequal_time_steps_preserve_constant_velocity():
    p,c,s=fixture(steps=[30,40,50]*4)
    for i,sample in enumerate(s):sample['camera_translation']=[.2*([30,40,50][i%3]/1000),0.]
    assert score(p,c)['score']==pytest.approx(0.,abs=1e-10)

def test_subject_velocity_jump_and_constant_motion():
    p,c,s=fixture(role='subject')
    for sample in s:sample['camera_compensated_velocity']=[.2,0.]
    assert score(p,c,'motion_reset')['score']==pytest.approx(0.)
    s[6]['camera_compensated_velocity']=[1.2,0.]
    assert score(p,c,'motion_reset')['score']==pytest.approx(10.24)

def test_non_join_peak_cannot_create_a_join_alarm():
    p,c,s=fixture(joins=(8,));s[4]['camera_translation']=[.2,0.]
    assert score(p,c)['score']==pytest.approx(0.)

@pytest.mark.parametrize('missing',[3,5,6])
def test_missing_current_or_recent_support_abstains(missing):
    p,c,s=fixture();s[missing]['camera_translation']=None
    result=score(p,c)
    assert result['state']=='unverified' and result['score'] is None
    assert result['valid_events']==0

def test_partial_multi_join_case_does_not_become_comparable():
    p,c,s=fixture(joins=(5,9));s[5]['camera_translation']=[.08,0.];s[9]['camera_translation']=None
    r=score(p,c)
    assert r['score'] is None and r['valid_events']==1 and r['expected_events']==2
    assert r['events'][0]['score']>0

def test_declared_change_and_interval_are_explicit():
    p,c,s=fixture(joins=(5,9))
    c['context']=dict(events=[dict(detector_ids=['camera_jump'],region_ids=['roi'],frame_ids=['display_5'])])
    assert score(p,c,interval=(0,6))['state']=='not_comparable'
    assert score(p,c,interval=(6,12))['expected_events']==1
    assert score(p,c,interval=(10,12))['state']=='not_comparable'

def test_declared_history_cannot_be_used_as_normal_baseline():
    p,c,s=fixture()
    c['context']=dict(events=[dict(detector_ids=['camera_jump'],region_ids=['roi'],frame_ids=['display_4','display_5'])])
    r=score(p,c)
    assert r['score'] is None and r['state']=='unverified'

@pytest.mark.parametrize('role,detector',[('subject','camera_jump'),('background','motion_reset')])
def test_role_mismatch_is_not_normal(role,detector):
    p,c,s=fixture(role=role)
    assert score(p,c,detector)['state']=='not_comparable'

@pytest.mark.parametrize('bad',['nan','duplicate','order','dimensions'])
def test_invalid_input_rejected(bad):
    p,c,s=fixture()
    if bad=='nan':s[6]['camera_rotation']=float('nan')
    elif bad=='duplicate':s[7]['frame_id']=s[6]['frame_id']
    elif bad=='order':s[7]['timestamp']['pts']=s[6]['timestamp']['pts']
    if bad=='dimensions':
        with pytest.raises(ValueError):module().event_case(p,c,0,1080,'roi','camera_jump',(0,12))
    else:
        with pytest.raises(ValueError):score(p,c)

def test_inputs_not_mutated_or_dependent_on_recipe_or_truth():
    p,c,s=fixture();before=deepcopy((p,c));r=score(p,c)
    assert (p,c)==before
    c.update(variant='arbitrary',recipe={'intent':'anomaly'},truth={'future_boxes':'forbidden'})
    assert score(p,c)==r
