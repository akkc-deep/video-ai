from copy import deepcopy
from dataclasses import replace
import pytest
from composition_helpers import inputs
from video_ai.runtime.manifest import thaw

def module():
    from video_ai.planning import composition
    return composition

def plan(fps=16,transition='cut',seconds=0):
    c=module();data=inputs(fps,transition,seconds)
    return c.plan_composition(*data,settings=c.CompositionSettings()),data

def test_exact_frame_and_sample_coverage():
    p,data=plan()
    assert p.total_frames==48 and p.video_samples==144000 and p.padding_samples==0
    assert [r['output_frame'] for r in p.ordered_frame_map]==list(range(48))
    assert [r['contributors'][0]['native_frame_index'] for r in p.ordered_frame_map]==list(range(16))*3
    assert [b['candidate_frame_ranges'] for b in p.requirement_bindings]==[(dict(start=0,end=16),),(dict(start=16,end=32),),(dict(start=32,end=48),)]
    assert all(c['verdict']=='passed' for c in p.cue_checks)
    module().validate_composition_plan(p,timeline=data[0],storyboard=data[1],upscaled=data[2],timing=data[3])

def test_24fps_previous_native_sampling_is_explicit():
    p,_=plan(24)
    assert p.total_frames==72
    assert [r['contributors'][0]['native_frame_index'] for r in p.ordered_frame_map[:24]]==[i*16//24 for i in range(24)]
    assert p.ordered_shots[0]['rate_conversion']=='previous_native_frame'

@pytest.mark.parametrize('frames',[1,3,8])
def test_fade_preserves_duration_and_exact_rational_weights(frames):
    p,_=plan(16,'fade',frames/16)
    assert len(p.ordered_frame_map)==48
    t=p.transitions[0];rows=p.ordered_frame_map[t['start_frame']:t['end_frame']]
    for k,row in enumerate(rows):
        a,b=row['contributors']
        den=2 if frames==1 else frames-1
        assert (a['weight_numerator'],b['weight_numerator'],a['weight_denominator'],b['weight_denominator'])==(1 if frames==1 else den-k,1 if frames==1 else k,den,den)

@pytest.mark.parametrize('field,value',[('font_size',True),('margin',301),('outline',-1),('music_gain',float('nan')),('music_fade_seconds',-1),('font_name','bad{tag}'),('schema_version',True)])
def test_settings_reject_invalid_values(field,value):
    with pytest.raises(ValueError):module().CompositionSettings(**{field:value})

def test_settings_partial_defaults_and_unknown_field():
    c=module()
    assert c.CompositionSettings.from_dict({'font_size':60}).margin==64
    with pytest.raises(ValueError):c.CompositionSettings.from_dict({'other':1})

@pytest.mark.parametrize('change',['order','short','text','mapping','failed','bool'])
def test_reject_inconsistent_upstream(change):
    t,s,u,e=inputs()
    if change=='order':u['clips'].reverse()
    if change=='short':u['clips'][0]['frames'].pop()
    if change=='text':u['requirement_clips'][0]['source_quote']='飞船'
    if change=='mapping':u['frame_mappings'][0]['output_to_upscaled'][0]=1
    if change=='failed':u['validation']['motion_semantics_passed']=False
    if change=='bool':u['clips'][0]['frames'][0]['source_frame_index']=False
    with pytest.raises(ValueError):module().plan_composition(t,s,u,e,settings=module().CompositionSettings())

def test_plan_is_deeply_frozen_and_reconstructed():
    p,data=plan()
    with pytest.raises(TypeError):p.ordered_frame_map[0]['output_frame']=3
    bad=replace(p,total_frames=p.total_frames+1)
    with pytest.raises(ValueError):module().validate_composition_plan(bad,timeline=data[0],storyboard=data[1],upscaled=data[2],timing=data[3])

def test_cross_scene_fade_exceeding_cue_budget_rejected():
    t,s,u,e=inputs(16,'fade',0.5)
    s['shots'][1]['visual_requirements'][0]['setting']='unrelated scene'
    with pytest.raises(ValueError,match='cue|fade'):module().plan_composition(t,s,u,e,settings=module().CompositionSettings())

def test_same_subject_with_changed_action_cannot_hide_over_budget_fade():
    t,s,u,e=inputs(16,'fade',0.5)
    s['shots'][0]['visual_requirements'][0]['action_or_state']='standing'
    s['shots'][1]['visual_requirements'][0]['action_or_state']='running'
    with pytest.raises(ValueError,match='cue|fade'):module().plan_composition(t,s,u,e,settings=module().CompositionSettings())

def test_formal_storyboard_cue_records_include_verified_output_frame():
    t,s,u,e=inputs()
    for i,cue in enumerate(s['cues'],1):cue['frame']=16*i
    p=module().plan_composition(t,s,u,e,settings=module().CompositionSettings())
    assert [c['planned_change_frame'] for c in p.cue_checks]==[16,32]
    s['cues'][0]['frame']=17
    with pytest.raises(ValueError):module().plan_composition(t,s,u,e,settings=module().CompositionSettings())
