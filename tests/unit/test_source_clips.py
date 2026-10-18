from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from unit.test_timeline import make
from video_ai.planning.timeline import SlotRange, budget_slots
from video_ai.runtime.manifest import thaw


TEXT = '夜色渐渐安静下来，微风轻轻吹过树梢。\r\n远处的灯光映在水面上，随着细小的波纹轻轻摇动。\n我们沿着安静的小路慢慢前行，听见脚步声，也听见夜风穿过枝叶。\n'


def identity(name):
    return dict(path=f'D:/VideoSi/fixture/{name}', bytes=123, mtime_ns=456,
                sha256='a'*64, verified_at='2026-10-04T10:00:00+08:00')


def inputs(fps=16, transition='cut', profile='fast'):
    timeline = make(TEXT, [106560,39360,141120,156480,164160,81600,133440], fps)
    bounds = [0,68,113,160,244,299,326,419] if fps == 16 else [0,101,169,240,366,448,489,628]
    slots = [SlotRange(f'shot_{i:04d}', a, b) for i,(a,b) in enumerate(zip(bounds,bounds[1:]),1)]
    seconds = 0 if transition == 'cut' else .5
    budgets = budget_slots(timeline,slots,transition=transition,transition_seconds=seconds)
    width,height = (768,432) if profile == 'fast' else (1280,720)
    shots = []
    for i,(slot,budget) in enumerate(zip(slots,budgets.shots),1):
        unit=f'speech_{i:04d}'
        requirements=[dict(requirement_id='repeated',unit_id=unit,source_quote=f'quote {i}')]
        bindings=[]
        if i < 7:
            bindings=[dict(unit_id=f'speech_{i+1:04d}',quantization_edge=True)]
            requirements.append(dict(requirement_id='repeated',unit_id=f'speech_{i+1:04d}',source_quote=f'quote {i+1}'))
        shots.append(dict(shot_id=slot.shot_id,start_frame=slot.start_frame,end_frame=slot.end_frame,
            primary_unit_id=unit,budget=thaw(budget),video_prompt=f'Original video {i}.',entity_ids=['water'],
            bindings=bindings,visual_requirements=requirements))
    board=dict(run_id='test',effective_media=dict(fps=fps,native_fps=16,
        profile=dict(name=profile,width=width,height=height,native_fps=16),transition=transition,transition_seconds=seconds),
        global_visual=dict(style='cinematic',color_palette='blue',lighting='night',
            entities=[dict(entity_id='water',description='Original water description.')]),
        shots=shots,transitions=thaw(budgets.transitions))
    images=dict(run_id='test',images=[dict(shot_id=s['shot_id'],primary_unit_id=s['primary_unit_id'],
        image_identity=identity(s['shot_id']+'/start.png')) for s in shots])
    return board,timeline.as_dict(),images


def api():
    from video_ai.planning import source_clips
    return source_clips


def test_seven_exact_native_budgets_parameters_and_original_prompt():
    b,t,i=inputs()
    plans=api().plan_source_clips(b,t,i)
    assert isinstance(plans,tuple) and len(plans)==7
    assert [p.budget['required_native_frames'] for p in plans]==[68,45,47,84,55,27,93]
    assert [p.parameters['length'] for p in plans]==[69,45,49,85,57,29,93]
    assert [p.budget['native_trim_frames'] for p in plans]==[1,0,2,1,2,2,0]
    assert sum(p.parameters['length'] for p in plans)==427
    assert [thaw(p.budget) for p in plans]==[s['budget'] for s in b['shots']]
    assert plans[0].parameters['positive']=='Original video 1.\nstyle: cinematic\ncolor_palette: blue\nlighting: night\nentity water: Original water description.'
    params=thaw(plans[0].parameters)
    assert set(params)==set('positive negative seed_high seed_low width height length fps batch steps cfg sampler scheduler split_step shift_high shift_low lora_enabled'.split())
    assert {k:params[k] for k in ('seed_high','seed_low','width','height','fps','batch','steps','cfg','sampler','scheduler','split_step','shift_high','shift_low','lora_enabled')}==dict(seed_high=264244520398999,seed_low=0,width=768,height=432,fps=16,batch=1,steps=40,cfg=3.5,sampler='euler',scheduler='simple',split_step=15,shift_high=5.000000000000001,shift_low=5.000000000000001,lora_enabled=False)
    graph=json.loads((Path(__file__).parents[2]/'workflows/wan22_i2v_14b_api.json').read_text(encoding='utf-8'))
    assert params['negative']==graph['129:89']['inputs']['text']
    assert plans[-1].parameters['seed_high']==264244520399005


def test_nested_plan_immutability_and_input_detachment():
    b,t,i=inputs();plan=api().plan_source_clips(b,t,i)[0]
    with pytest.raises(FrozenInstanceError):plan.shot_id='other'
    with pytest.raises(TypeError):plan.parameters['length']=5
    with pytest.raises(TypeError):plan.budget['associated_unit_ids'][0]='other'
    with pytest.raises(TypeError):plan.start_image_identity['sha256']='b'*64
    b['shots'][0]['budget']['associated_unit_ids'][0]='other';i['images'][0]['image_identity']['bytes']=999
    assert plan.budget['associated_unit_ids'][0]=='speech_0001' and plan.start_image_identity['bytes']==123


@pytest.mark.parametrize('field',['budget','parameters','start_image_identity'])
@pytest.mark.parametrize('mutable',[{1},bytearray(b'original'),SimpleNamespace(value=[])],ids=['set','bytearray','custom_object'])
def test_direct_plan_rejects_unsupported_nested_mutable_objects(field,mutable):
    values=dict(budget={},parameters={},start_image_identity={})
    values[field]={'nested':[{'value':mutable}]}
    with pytest.raises(ValueError):
        api().SourceClipPlan('shot_0001','speech_0001',**values)


@pytest.mark.parametrize('key',[1,('key',)])
def test_direct_plan_rejects_unsupported_nested_mapping_keys(key):
    with pytest.raises(ValueError):
        api().SourceClipPlan('shot_0001','speech_0001',{'nested':{key:'value'}},{},{})


def test_pure_functions_do_not_open_or_probe_files(monkeypatch):
    b,t,i=inputs()
    def forbidden(*args,**kwargs):raise AssertionError('pure planning performed file I/O')
    for name in ('open','read_text','read_bytes','stat','resolve'):
        monkeypatch.setattr(Path,name,forbidden)
    plans=api().plan_source_clips(b,t,i)
    identities={p.shot_id:identity(p.shot_id+'/source.mp4') for p in plans}
    mappings={p.shot_id:api().frame_mapping(p,generated_identity=identity(p.shot_id+'/g.mp4'),source_identity=identities[p.shot_id],generated_frames=p.parameters['length'],output_fps=16) for p in plans}
    assert len(api().requirement_clips(b,source_identities=identities,frame_mappings=mappings,total_samples=t['total_samples']))==13


def test_quality_profile_and_fade24_mapping_are_native16():
    b,t,i=inputs(24,'fade','quality');plan=api().plan_source_clips(b,t,i)[0]
    assert (plan.parameters['width'],plan.parameters['height'],plan.parameters['length'])==(1280,720,73)
    mapped=api().frame_mapping(plan,generated_identity=identity('generated.mp4'),source_identity=identity('source.mp4'),generated_frames=73,output_fps=24)
    assert (mapped['source_frames'],mapped['coverage_start_frame'],mapped['coverage_end_frame'])==(72,0,107)
    assert mapped['output_to_source'][:9]==[0,0,1,2,2,3,4,4,5]
    assert mapped['output_to_source'][-1]==70 and len(mapped['output_to_source'])==107
    assert mapped['generated_to_source'][-2:]==[71,None] and mapped['native_fps']==16


@pytest.mark.parametrize('change',[
    lambda b,t,i:b['effective_media']['profile'].update(width=True),
    lambda b,t,i:b['effective_media']['profile'].update(width=768.0),
    lambda b,t,i:b['effective_media']['profile'].update(width=1280,height=720),
    lambda b,t,i:b['effective_media']['profile'].update(height=431),
    lambda b,t,i:b['shots'][0]['budget'].update(wan_frames=True),
    lambda b,t,i:b['shots'][0]['budget'].update(unknown=1),
    lambda b,t,i:b['transitions'][0].update(actual_frames=True),
    lambda b,t,i:b['shots'][0].update(entity_ids=['unknown']),
    lambda b,t,i:b['shots'][0].update(video_prompt=''),
    lambda b,t,i:i.update(run_id='other'),
    lambda b,t,i:i['images'].append(deepcopy(i['images'][0])),
    lambda b,t,i:i['images'][0]['image_identity'].update(bytes=True),
    lambda b,t,i:i['images'][0]['image_identity'].update(unknown=1),
    lambda b,t,i:t.update(output_fps=True),
])
def test_planning_rejects_malformed_or_drifted_inputs(change):
    b,t,i=inputs();change(b,t,i)
    with pytest.raises(ValueError):api().plan_source_clips(b,t,i)


def test_supplement_known_short_frames_only():
    assert api().supplement_frames(requested_frames=69,required_native_frames=68,actual_frames=65)==73


@pytest.mark.parametrize('w,r,a',[(69,68,0),(69,68,68),(69,68,69),(68,68,65),(73,68,65),(69,True,1),(69,68,True),(69.0,68,65),(69,68,None),(0,1,1),(69,68,-1)])
def test_supplement_refuses_unknown_invalid_or_noninitial_request(w,r,a):
    with pytest.raises(ValueError):api().supplement_frames(requested_frames=w,required_native_frames=r,actual_frames=a)


def test_frame_mapping_exact_schema_trim_and_detachment():
    b,t,i=inputs();plan=api().plan_source_clips(b,t,i)[0];generated=identity('generated.mp4')
    result=api().frame_mapping(plan,generated_identity=generated,source_identity=identity('source.mp4'),generated_frames=73,output_fps=16)
    assert set(result)==set('shot_id generated_identity source_identity generated_frames source_frames generated_to_source coverage_start_frame coverage_end_frame core_start_frame core_end_frame output_fps native_fps output_to_source'.split())
    assert result['generated_to_source']==list(range(68))+[None]*5
    assert result['output_to_source']==list(range(68))
    generated['bytes']=999
    assert result['generated_identity']['bytes']==123


@pytest.mark.parametrize('a,fps',[(65,16),(True,16),(69.0,16),(69,True),(69,24),(69,30)])
def test_frame_mapping_rejects_short_noninteger_and_wrong_output_rate(a,fps):
    b,t,i=inputs();plan=api().plan_source_clips(b,t,i)[0]
    with pytest.raises(ValueError):api().frame_mapping(plan,generated_identity=identity('g.mp4'),source_identity=identity('s.mp4'),generated_frames=a,output_fps=fps)


def mapped_inputs():
    b,t,i=inputs();plans=api().plan_source_clips(b,t,i)
    identities={p.shot_id:identity(p.shot_id+'/source.mp4') for p in plans}
    mappings={p.shot_id:api().frame_mapping(p,generated_identity=identity(p.shot_id+'/generated.mp4'),source_identity=identities[p.shot_id],generated_frames=p.parameters['length'],output_fps=16) for p in plans}
    return b,t,identities,mappings


def test_thirteen_requirements_preserve_repeated_ids_and_continuous_primary_edge_ranges():
    b,t,identities,mappings=mapped_inputs()
    rows=api().requirement_clips(b,source_identities=identities,frame_mappings=mappings,total_samples=t['total_samples'])
    assert len(rows)==13 and len({(r['shot_id'],r['requirement_index']) for r in rows})==13
    assert set(rows[0])==set('shot_id requirement_id requirement_index unit_id source_quote clip_shot_id role actual_artifact local_frames output_frames sample_range'.split())
    assert rows[0]['local_frames']==dict(start=0,end=68)
    assert rows[1]['role']=='quantization_edge_review' and rows[1]['clip_shot_id']=='shot_0002'
    assert rows[1]['local_frames']==dict(start=0,end=45)
    assert rows[1]['output_frames']==dict(start=68,end=113)
    assert rows[1]['sample_range']==dict(start=204000,end=339000)
    assert rows[-1]['sample_range']==dict(start=978000,end=1254720)


def test_edges_use_nearest_primary_by_start_frame_then_stable_shot_order():
    b,t,identities,mappings=mapped_inputs()
    # The same long speech unit can own several primary clips. Each edge
    # must use the closest original primary, rather than the first match.
    for shot in b['shots']:shot['visual_requirements']=[]
    b['shots'][3]['primary_unit_id']='speech_0002'
    b['shots'][4]['bindings']=[dict(unit_id='speech_0002',quantization_edge=True)]
    b['shots'][4]['visual_requirements']=[dict(requirement_id='edge',unit_id='speech_0002',source_quote='quote')]
    rows=api().requirement_clips(b,source_identities=identities,frame_mappings=mappings,total_samples=t['total_samples'])
    assert next(r for r in rows if r['requirement_id']=='edge')['clip_shot_id']=='shot_0004'


@pytest.mark.parametrize('coordinate,value',[
    ('start_frame',False),('start_frame',True),('start_frame',160.0),('start_frame',0),
    ('end_frame',False),('end_frame',True),('end_frame',244.0),('end_frame',245),
])
def test_requirement_clips_rejects_coordinates_that_disagree_with_frozen_core(coordinate,value):
    b,t,identities,mappings=mapped_inputs()
    for shot in b['shots']:shot['visual_requirements']=[]
    b['shots'][3]['primary_unit_id']='speech_0002'
    b['shots'][4]['bindings']=[dict(unit_id='speech_0002',quantization_edge=True)]
    b['shots'][4]['visual_requirements']=[dict(requirement_id='edge',unit_id='speech_0002',source_quote='quote')]
    rows=api().requirement_clips(b,source_identities=identities,frame_mappings=mappings,total_samples=t['total_samples'])
    assert rows[0]['clip_shot_id']=='shot_0004'
    # False/0 would change the selected repeated-unit primary to shot_0002,
    # despite the intact budget, mapping and identities for shot_0004.
    b['shots'][3][coordinate]=value
    with pytest.raises(ValueError):
        api().requirement_clips(b,source_identities=identities,frame_mappings=mappings,total_samples=t['total_samples'])


@pytest.mark.parametrize('change',[
    lambda b,t,i,m:b['shots'][0]['bindings'][0].update(quantization_edge=1),
    lambda b,t,i,m:i.pop('shot_0001'),
    lambda b,t,i,m:m['shot_0001'].update(source_frames=True),
    lambda b,t,i,m:m['shot_0001'].update(unknown=1),
    lambda b,t,i,m:m['shot_0001']['source_identity'].update(sha256='b'*64),
    lambda b,t,i,m:m['shot_0001']['output_to_source'].__setitem__(0,True),
    lambda b,t,i,m:t.update(total_samples=True),
])
def test_requirement_clips_refuses_invalid_bindings_mapping_identity_or_ranges(change):
    b,t,i,m=mapped_inputs();change(b,t,i,m)
    with pytest.raises(ValueError):api().requirement_clips(b,source_identities=i,frame_mappings=m,total_samples=t['total_samples'])
