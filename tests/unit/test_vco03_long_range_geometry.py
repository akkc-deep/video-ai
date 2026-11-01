"""Isolated experimental correspondence tests; no production profiles."""
import importlib.util
from pathlib import Path
from copy import deepcopy
import numpy as np
import cv2
import pytest

def module():
    path=Path(__file__).resolve().parents[2]/'scripts/experiments/vco03_long_range_geometry_v2.py'
    assert path.exists(),'long-range experimental matcher missing'
    spec=importlib.util.spec_from_file_location('long_range',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def texture():
    rng=np.random.default_rng(731)
    image=cv2.GaussianBlur(rng.integers(0,256,(288,512),dtype=np.uint8),(3,3),.6)
    for i in range(25):
        x,y=map(int,rng.integers([10,10],[500,276]));cv2.circle(image,(x,y),4+i%7,int(rng.integers(20,235)),1)
    return image

def test_large_translation_has_pixel_correspondence():
    m=module();left=texture();right=cv2.warpAffine(left,np.float32([[1,0,40],[0,1,0]]),(512,288))
    r=m.register_pair(left,right,[.08,.08,.9,.9],[.16,.08,.98,.9])
    assert r['affine'] is not None and r['inliers']>=12
    assert r['affine'][0][2]==pytest.approx(40/512,abs=.002)

def test_stationary_pixels_ignore_anchor_relocation():
    m=module();image=texture()
    r=m.register_pair(image,image,[.1,.1,.9,.9],[.18,.15,.98,.95])
    assert r['affine'] is not None
    assert r['affine'][0][2]==pytest.approx(0,abs=1e-5)
    v=m.pair_velocities(r['affine'],r['affine'],[.1,.1,.9,.9],.04)
    assert v['compensated']==pytest.approx([0,0],abs=1e-6)

def test_subject_motion_is_separate_from_camera():
    m=module();subject=[[1,0,.05],[0,1,.01]];camera=[[1,0,.02],[0,1,.01]]
    v=m.pair_velocities(subject,camera,[.1,.1,.4,.5],.05)
    assert v['image_plane']==pytest.approx([1.,.2])
    assert v['compensated']==pytest.approx([.6,0.])
    assert m.pair_velocities(subject,None,[.1,.1,.4,.5],.05)['compensated'] is None

def test_no_texture_or_no_mask_support_abstains():
    m=module();image=np.full((288,512),128,np.uint8)
    assert m.register_pair(image,image,[0,0,1,1])['affine'] is None
    rich=texture();mask=np.zeros_like(rich,dtype=bool)
    assert m.register_pair(rich,rich,[0,0,1,1],left_mask=mask,right_mask=mask)['affine'] is None

def test_occlusion_patch_is_not_reused_as_matching_support():
    m=module();image=texture();box=[.2,.2,.5,.8]
    result=m.transform_luma(image,'subject_jump',7,12,box)
    assert result['subject_rect'][0]>box[0]
    assert result['valid_mask'] is not None and not result['valid_mask'][60:220,103:140].any()
    occluded=m.transform_luma(image,'occlusion',6,12,box)
    assert not occluded['valid_mask'][60:140,110:250].any()

def test_background_excludes_subject_and_invalid_padding():
    m=module();mask=m.background_mask((288,512),[[.2,.2,.5,.8]])
    assert not mask[60:220,110:250].any() and mask[5,5]
    warp=m.transform_luma(texture(),'camera_jump',6,12,[.2,.2,.5,.8])
    assert not warp['valid_mask'][:,:40].any()

def test_control_source_mapping_and_original_pixels_are_preserved():
    m=module();image=texture();before=image.copy()
    assert m.source_index('motion_reset',7,12)==1
    assert m.source_index('unchanged',7,12)==7
    r=m.transform_luma(image,'unchanged',7,12,[.2,.2,.5,.8])
    assert np.array_equal(r['image'],before) and np.array_equal(image,before)

def test_invalid_shapes_and_times_reject():
    m=module();image=texture()
    with pytest.raises(ValueError):m.register_pair(image,image[:20],[0,0,1,1])
    with pytest.raises(ValueError):m.pair_velocities([[1,0,0],[0,1,0]],None,[0,0,1,1],0)
    with pytest.raises(ValueError):m.transform_luma(image,'unknown',1,12,[.2,.2,.5,.8])

def test_feature_residual_uses_exact_256_work_grid_units():
    m=module()
    assert m.residual_work_pixels(np.array([[2.,0.],[0.,4.]]),np.zeros((2,2)),(512,288)).tolist()==pytest.approx([1.,2.])

def sequence_plan(n=8):
    return dict(frames=[dict(frame_id=f'display_{i}',timestamp=dict(pts=i,time_base='1/25')) for i in range(n)],
        anchors=[dict(region_id='subject',role='subject',anchors=[dict(frame_id='display_0',rect=[.1,.1,.75,.9]),dict(frame_id='display_4',rect=[.18,.12,.83,.92])]),dict(region_id='background',role='background',anchors=[])],
        comparisons=[dict(kind='parent_join' if i==3 else 'adjacent',left=f'display_{i}',right=f'display_{i+1}',comparison_id=str(i),region_ids=['subject','background']) for i in range(n-1)],context=None)

def test_full_sequence_uses_pixels_at_changed_join_anchor():
    m=module();image=texture();seen=set()
    def provider(fid):
        seen.add(fid);return dict(image=image,valid_mask=np.ones_like(image,dtype=bool))
    result=m.measure_sequence(sequence_plan(),provider)
    assert len(seen)==8 and len(result['pairs'])==7
    sample=result['trajectories'][0]['samples'][4]
    assert sample['image_plane_velocity']==pytest.approx([0,0],abs=1e-5)

def test_lost_pair_does_not_invent_velocity():
    m=module();rich=texture();plain=np.full_like(rich,128)
    def provider(fid):
        return dict(image=plain if fid=='display_4' else rich,valid_mask=np.ones_like(rich,dtype=bool))
    result=m.measure_sequence(sequence_plan(),provider)
    sample=result['trajectories'][0]['samples'][4]
    assert sample['image_plane_velocity'] is None and sample['camera_compensated_velocity'] is None

def test_nearly_identical_affine_does_not_lose_overlap(monkeypatch):
    m=module();image=texture()
    matrix=np.float64([[.9999908631670751,-.0000017008965895110668,.004494357962587462],[.000000654453922507158,.9999993878589112,-.00021318866829942993]])
    monkeypatch.setattr(cv2,'estimateAffine2D',lambda left,right,**kwargs:(matrix,np.ones((len(left),1),np.uint8)))
    result=m.register_pair(image,image,[0,0,1,1],[0,0,1,1])
    assert result['affine'] is not None and result['overlap']>.999
