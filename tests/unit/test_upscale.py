"""Pure upscale plans preserve accepted source order, budgets and native frames."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import math
import pytest

from unit.test_source_clips import identity, inputs
from video_ai.planning.source_clips import plan_source_clips, frame_mapping
from video_ai.runtime.manifest import thaw


def source_input(fps=16, transition='cut', profile='fast'):
    board, timeline, images = inputs(fps, transition, profile)
    plans = plan_source_clips(board, timeline, images)
    clips, mappings = [], []
    for plan in plans:
        n = plan.budget['required_native_frames']
        generated = plan.budget['wan_frames']
        src, gen = identity(plan.shot_id+'/source.mp4'), identity(plan.shot_id+'/generated.mp4')
        clips.append(dict(shot_id=plan.shot_id, primary_unit_id=plan.primary_unit_id,
            budget=thaw(plan.budget), start_image_identity=identity('start.png'),
            input_copy_identity=identity('copy.png'), selected_attempt_id='attempt_0001', attempts=[],
            generated_identity=gen, source_identity=src, width=plan.parameters['width'],
            height=plan.parameters['height'], native_fps=16, generated_frames=generated,
            source_frames=n, parameters=thaw(plan.parameters), evidence_identities=[]))
        mappings.append(frame_mapping(plan, generated_identity=gen, source_identity=src,
                                      generated_frames=generated, output_fps=fps))
    return dict(schema_version=1, run_id='test', created_at='2026-10-04T10:00:00+08:00',
        status='completed', passed=True, images_identity=identity('images.json'),
        storyboard_identity=identity('storyboard.json'), timeline_identity=identity('timeline.json'),
        effective_media=dict(board['effective_media'], image_aspect_ratio='16:9',
            default_image_width=1280, default_image_height=720), clips=clips,
        requirement_clips=[], frame_mappings=mappings, model_identities={},
        workflow_identity=identity('workflow.json'), mapping_identity=identity('mapping.json'),
        provenance={}, validation=dict(structure_passed=True,media_passed=True,
            video_text_semantics_passed=False,motion_semantics_passed=False,ready_for_upscale=True,
            final_video_sync='unverified',full_film_acceptance='unverified'),
        request_evidence={},review_identity=identity('review.json'))


def api():
    from video_ai.planning import upscale
    return upscale


@pytest.mark.parametrize('profile', ['fast', 'quality'])
def test_plan_uses_retained_counts_and_exact_fixed_parameters(profile):
    source = source_input(profile=profile)
    plans = api().plan_upscale(source)
    assert [p.source_frames for p in plans] == [68,45,47,84,55,27,93]
    assert sum(p.source_frames for p in plans) == 419
    assert [p.shot_id for p in plans] == [f'shot_{i:04d}' for i in range(1,8)]
    assert all((p.width,p.height,p.native_fps)==(1920,1080,16) for p in plans)
    assert thaw(plans[0].parameters) == dict(model_name='RealESRGAN_x4plus.pth',
        model_scale=4,resize_method='lanczos',width=1920,height=1080,crop='disabled',native_fps=16,batch=1)
    assert thaw(plans[0].budget)==source['clips'][0]['budget']
    assert plans[0].primary_unit_id=='speech_0001'


def test_all_nested_plan_data_is_frozen_and_detached():
    source=source_input();p=api().plan_upscale(source)[0]
    with pytest.raises(FrozenInstanceError):p.width=1
    for action in (lambda:p.parameters.__setitem__('batch',2),
                   lambda:p.source_identity.__setitem__('bytes',4),
                   lambda:p.budget['associated_unit_ids'].__setitem__(0,'other')):
        with pytest.raises((TypeError,AttributeError)):action()
    source['clips'][0]['budget']['associated_unit_ids'][0]='other'
    source['clips'][0]['source_identity']['bytes']=999
    assert p.budget['associated_unit_ids'][0]=='speech_0001' and p.source_identity['bytes']==123


@pytest.mark.parametrize('fault', ['top_extra','clip_extra','bool_count','float_count','not_ready',
    'bool_fps','bad_dimensions','duplicate_shot','budget_drift','mapping_drift','incomplete_identity','nan'])
def test_plan_rejects_malformed_or_drifting_source(fault):
    s=source_input();c=s['clips'][0]
    if fault=='top_extra':s['unknown']=1
    elif fault=='clip_extra':c['unknown']=1
    elif fault=='bool_count':c['source_frames']=True
    elif fault=='float_count':c['source_frames']=68.0
    elif fault=='not_ready':s['validation']['ready_for_upscale']=1
    elif fault=='bool_fps':c['native_fps']=True
    elif fault=='bad_dimensions':c['width']=1280
    elif fault=='duplicate_shot':s['clips'][1]['shot_id']=c['shot_id']
    elif fault=='budget_drift':c['budget']['required_native_frames']=69
    elif fault=='mapping_drift':s['frame_mappings'][0]['source_frames']=69
    elif fault=='incomplete_identity':c['source_identity']['mtime_ns']=None
    else:c['parameters']['cfg']=math.nan
    with pytest.raises(ValueError):api().plan_upscale(s)


@pytest.mark.parametrize('n,want',[(68,1200),(45,1200),(47,1200),(84,1245),(55,1200),(27,1200),(93,1378),(81,1200)])
def test_clip_budget_scales_after_eighty_one_frames(n,want):
    assert api().clip_deadline_seconds(frame_count=n,base_seconds=1200)==want


@pytest.mark.parametrize('n,base',[(True,1200),(0,1200),(81.,1200),(81,True),(81,0),(81,-1),(81,math.inf),(81,math.nan)])
def test_clip_budget_rejects_nonpositive_nonfinite_and_bool(n,base):
    with pytest.raises(ValueError):api().clip_deadline_seconds(frame_count=n,base_seconds=base)


@pytest.mark.parametrize('fps,transition',[(16,'cut'),(24,'fade')])
def test_mapping_preserves_all_output_and_budget_coordinates(fps,transition):
    src=source_input(fps,transition)['frame_mappings'][0];before=deepcopy(src)
    result=api().upscale_frame_mapping(src,upscaled_identity=identity('upscaled.mp4'))
    assert set(result)==set('shot_id source_identity upscaled_identity source_frames upscaled_frames native_fps output_fps source_to_upscaled output_to_upscaled coverage_start_frame coverage_end_frame core_start_frame core_end_frame'.split())
    assert result['source_frames']==result['upscaled_frames']==src['source_frames']
    assert result['source_to_upscaled']==list(range(src['source_frames']))
    assert result['output_to_upscaled']==src['output_to_source']
    for k in ('source_identity','shot_id','native_fps','output_fps','coverage_start_frame','coverage_end_frame','core_start_frame','core_end_frame'):
        assert result[k]==src[k]
    result['output_to_upscaled'][0]=99
    assert src==before


@pytest.mark.parametrize('fault',['extra','bool','bad_output','missing_tail','bad_range'])
def test_mapping_rejects_invalid_source_associations(fault):
    src=source_input()['frame_mappings'][0]
    if fault=='extra':src['unknown']=1
    elif fault=='bool':src['source_frames']=True
    elif fault=='bad_output':src['output_to_source'][0]=1
    elif fault=='missing_tail':src['generated_to_source'].pop()
    else:src['core_end_frame']=100
    with pytest.raises(ValueError):api().upscale_frame_mapping(src,upscaled_identity=identity('upscaled.mp4'))
