from copy import deepcopy
import importlib
from time import monotonic

import pytest
from continuity_helpers import texture, Provider, plan, manifest


def module():
    assert importlib.util.find_spec('video_ai.media.continuity_analysis') is not None, 'continuity analyzer missing'
    return importlib.import_module('video_ai.media.continuity_analysis')


def test_manifest_strict_and_unchanged():
    m=module(); data=manifest(); before=deepcopy(data)
    result=m.validate_continuity_manifest(data)
    assert result==before and result is not data
    for mutate in (lambda d:d.update(extra=1),lambda d:d.update(schema_version=True),
        lambda d:d.pop('domain'),lambda d:d['timeline'].update(fps_num=True),
        lambda d:d['comparisons'][0].update(left='absent'),
        lambda d:d['clips'][0]['frames'].append(deepcopy(d['clips'][0]['frames'][0]))):
        bad=deepcopy(data);mutate(bad)
        with pytest.raises(ValueError):m.validate_continuity_manifest(bad)


def test_independent_srgb_lab_and_color_metrics():
    m=module(); import numpy as np
    lab,y=m._lab_luma(np.array([[0,0,0],[255,255,255],[128,128,128]],dtype=np.uint8))
    assert lab[0].tolist()==[0.,0.,0.]
    assert lab[1][0]==pytest.approx(100.,abs=1e-5)
    assert lab[1][1:]==pytest.approx([0.,0.],abs=2e-5)
    assert y.tolist()==pytest.approx([0.,1.,.21586050011389926],abs=1e-12)
    metrics=m._color_metrics(np.array([[0,0,0],[0,0,0]],dtype=np.uint8),
                            np.array([[255,255,255],[255,255,255]],dtype=np.uint8))
    assert metrics['delta_e_p90']==pytest.approx(100.,abs=1e-4)
    assert metrics['delta_lab_median'][0]==pytest.approx(100.,abs=1e-5)
    assert metrics['left_clipped_fractions']['r_low']==1.
    assert metrics['right_clipped_fractions']['r_high']==1.


def test_texture_identity_registration_and_no_default_decision():
    m=module(); img=texture(); images=dict(left=img,right=img.copy());provider=Provider(images)
    result=m.measure_continuity(plan(images),provider)
    for r in result['comparisons'][0]['regions']:
        assert r['comparability']=='comparable',r['reasons']
        assert r['metrics']['delta_e_p90']==0.
        assert r['geometry']['valid_points']>=12
        assert r['confidence_kind']=='match_support'
        assert len(r['geometry']['sampled_pairs'])>=81
    assert all(d['threshold'] is None and d['status']=='unverified' for d in result['detectors'])
    assert not provider.live and provider.peak<=2


def test_translation_keeps_subject_and_camera_distinct():
    m=module(); import cv2
    img=texture(); shifted=cv2.warpAffine(img, __import__('numpy').float32([[1,0,2],[0,1,1]]),(128,96))
    images=dict(left=img,right=shifted); result=m.measure_continuity(plan(images),Provider(images))
    region=result['comparisons'][0]['regions'][0]
    assert region['comparability']=='comparable',region['reasons']
    assert region['geometry']['affine'][0][2]==pytest.approx(2/128,abs=.003)
    assert region['geometry']['affine'][1][2]==pytest.approx(1/96,abs=.003)
    assert region['metrics']['delta_e_p90']<1.
    samples=result['trajectories'][0]['samples']
    assert samples[-1]['camera_compensated_velocity']==pytest.approx([0.,0.],abs=.03)


@pytest.mark.parametrize('step_pixels',[0,2])
def test_clip_anchor_relocation_does_not_become_measured_motion(step_pixels):
    """An input box correction must not masquerade as pixel displacement."""
    m=module();import cv2
    import numpy as np
    base=texture();images={f'f_{i}':cv2.warpAffine(base,np.float32([[1,0,i*step_pixels],[0,1,0]]),(128,96)) for i in range(8)}
    p=plan(images,kinds={3:'parent_join'})
    p['clips']=[dict(clip_id='clip_a',frames=[f'f_{i}' for i in range(4)]),
                dict(clip_id='clip_b',frames=[f'f_{i}' for i in range(4,8)])]
    for f in p['frames'][4:]:f['source_clip_id']='clip_b'
    # Deliberately imperfect, but still overlapping the same textured object.
    p['regions'][0]['anchors'].append(dict(frame_id='f_4',rect=[.09,.05,.99,.95]))
    p['regions'][1]['anchors'].append(dict(frame_id='f_4',rect=[0.,0.,1.,1.]))
    original=deepcopy(p);provider=Provider(images)
    result=m.measure_continuity(p,provider)
    samples={s['frame_id']:s for s in result['trajectories'][0]['samples']}
    assert samples['f_4']['box']==[.09,.05,.99,.95]
    assert samples['f_4']['image_plane_velocity']==pytest.approx([step_pixels/8,0.],abs=.005)
    assert samples['f_4']['camera_compensated_velocity']==pytest.approx([0.,0.],abs=.005)
    assert samples['f_5']['camera_compensated_velocity']==pytest.approx([0.,0.],abs=.005)
    if step_pixels==0:
        boundary=[d['score'] for d in result['detectors'] if d['detector_id']=='motion_reset' and d['frame_ids'] in (['f_4'],['f_5'])]
        assert len(boundary)==2 and all(v is not None and v<1 for v in boundary)
    assert p==original and not provider.live and provider.peak<=2


def test_uniform_or_unrelated_images_abstain_and_missing_frames_unverified():
    m=module();import numpy as np
    for other in (np.zeros((96,128,3),dtype=np.uint8),None):
        images=dict(left=np.zeros((96,128,3),dtype=np.uint8),right=other)
        result=m.measure_continuity(plan(images),Provider(images))
        assert all(r['comparability'] in ('not_comparable','unverified') for r in result['comparisons'][0]['regions'])
        assert all(r['metrics'] is None for r in result['comparisons'][0]['regions'])


def test_context_scope_does_not_erase_unrelated_detector_or_region():
    m=module();images=dict(left=texture(),right=texture());p=plan(images)
    p['context']=dict(schema_version=1,author='fixture',reviewed_at='2026-10-24T00:00:00+00:00',events=[
        dict(event_id='sunset',kind='lighting',frame_ids=['right'],region_ids=['subject'],
             detector_ids=['local_color'],description='fixture declared change',references=[])])
    result=m.measure_continuity(p,Provider(images))
    local=[d for d in result['detectors'] if d['detector_id']=='local_color']
    assert next(d for d in local if d['region_id']=='subject')['status']=='not_comparable'
    assert next(d for d in local if d['region_id']=='background')['status']=='unverified'
    assert result['comparisons'][0]['regions'][0]['comparability']=='comparable'


def test_deadline_and_oversized_provider_release_frames():
    m=module();images=dict(left=texture(),right=texture());provider=Provider(images)
    with pytest.raises(TimeoutError):m.measure_continuity(plan(images),provider,deadline=monotonic()-1)
    class Oversized(Provider):
        def get(self,f):return dict(width=100000,height=100000,rgb24=b'',valid_mask=None)
    provider=Oversized(images)
    with pytest.raises(ValueError,match='resource_limit'):m.measure_continuity(plan(images),provider)
    assert not provider.live


def test_thread_settings_restored_even_when_provider_fails():
    m=module();import cv2
    images=dict(left=texture(),right=texture());before=cv2.getNumThreads()
    class Broken(Provider):
        def get(self,frame_id):raise RuntimeError('provider failure')
    with pytest.raises(RuntimeError,match='provider failure'):m.measure_continuity(plan(images),Broken(images))
    assert cv2.getNumThreads()==before


def test_profile_fixture_cannot_be_promoted_to_ordinary_decisions():
    m=module()
    apply=getattr(m,'_apply_profile',None)
    assert callable(apply),'profile application missing'
    with pytest.raises(ValueError,match='fixture_only'):
        apply({},dict(purpose='fixture_only'),manifest(),dependency_fingerprint='a'*64)


def test_audit_public_interface_exists():
    assert callable(getattr(module(),'analyze_continuity',None)),'audit interface missing'


def test_seam_baseline_and_three_clip_vector_slope_have_literal_scores():
    module()
    from video_ai.media._continuity_scores import scores
    images={f'f_{i}':texture(32,32) for i in range(12)};p=plan(images)
    p['clips']=[dict(clip_id=f'clip_{j}',frames=[f'f_{i}' for i in range(j*4,j*4+4)]) for j in range(3)]
    pairs=[]
    def r(de,lab):return dict(region_id='subject',metrics=dict(delta_e_p90=de,delta_e_median=de,delta_lab_median=lab),confidence=1.)
    for i in range(11):
        kind='parent_join' if i in (3,7) else 'adjacent'
        pairs.append(dict(comparison_id=f'join_{i}',kind=kind,left=f'f_{i}',right=f'f_{i+1}',regions=[r(12. if kind=='parent_join' else 2.,[0,0,0])]))
    for i in range(12):pairs.append(dict(comparison_id=f'ref_{i}',kind='reference',left='f_0',right=f'f_{i}',regions=[r(i,[i,0,0])]))
    ds=scores(p,pairs,[])
    seam=[d for d in ds if d['detector_id']=='seam_color']
    assert [d['score'] for d in seam]==[10.,10.]
    cumulative=next(d for d in ds if d['detector_id']=='cumulative_color' and d['region_id']=='subject')
    assert cumulative['score']==11.


def test_motion_and_camera_use_scalar_mad_of_historical_velocity_differences():
    module();from video_ai.media._continuity_scores import scores
    from video_ai.media.continuity_analysis import _sample
    images={f'f_{i}':texture(32,32) for i in range(5)};p=plan(images);samples=[]
    for i,f in enumerate(p['frames']):
        s=_sample(f,[0,0,1,1],1.);s['camera_compensated_velocity']=[10. if i==4 else 1.,0.]
        s['_camera_velocity']=[10. if i==4 else 1.,0.,0.,0.];samples.append(s)
    ds=scores(p,[],[dict(region_id='subject',samples=samples),dict(region_id='background',samples=samples)])
    assert next(d for d in ds if d['detector_id']=='motion_reset' and d['frame_ids']==['f_4'])['score']==9e6
    assert next(d for d in ds if d['detector_id']=='camera_jump' and d['frame_ids']==['f_4'])['score']==9e6


def test_subject_patch_local_change_survives_global_cancellation():
    m=module();import numpy as np
    left=texture();right=left.copy();right[:48]=np.clip(right[:48].astype(int)+10,0,255);right[48:]=np.clip(right[48:].astype(int)-10,0,255)
    assert abs(float(right.mean())-float(left.mean()))<.01
    p=plan(dict(left=left,right=right));p['regions'][0]['anchors'][0]['rect']=[.05,.05,.95,.45]
    result=m.measure_continuity(p,Provider(dict(left=left,right=right)))
    r=result['comparisons'][0]['regions'][0]
    assert r['comparability']=='comparable' and r['metrics']['delta_e_p90']>3.


def _resolve_case():
    from continuity_helpers import identity
    data=manifest();data['regions']=identity('regions')
    records=[];side=dict(mapping=dict(rows=[]))
    for i,f in enumerate(data['clips'][0]['frames']):
        mapping=dict(asset_frame_index=i,clip_id='clip_a',generated_frame_index=i,retained_frame_index=i,
            output_frame_index=i,pts=i,time_base='1/16')
        record=dict(source=identity('media'),frame_index=i,sidecar=identity('sidecar'),mapping=mapping,
            pts=i,time_base='1/16',status='ready',risks=[])
        records.append(dict(record_identity=f['record'],record=record));side['mapping']['rows'].append(mapping)
    region_doc=dict(schema_version=1,author='fixture',reviewed_at='2026-10-24T00:00:00+00:00',regions=[dict(
        region_id='subject',role='subject',identity_note='fixture identity',anchors=[dict(frame=data['clips'][0]['frames'][0]['record'],rect=[0,0,1,1])])])
    class Reader:
        frames=records;sidecars={identity('sidecar')['path']:side};identities=[]
    class Window:
        def read_json(self,ref):return region_doc
        def check(self,ref):pass
    return data,Reader(),Window(),region_doc


def test_ordinary_manifest_rejects_future_truth_anchors():
    m=module();data,reader,window,regions=_resolve_case()
    regions['regions'][0]['anchors'].append(dict(frame=data['clips'][0]['frames'][1]['record'],rect=[.1,.1,.9,.9]))
    with pytest.raises(ValueError,match='anchor'):m._resolve_manifest(data,reader,window)


def test_manifest_fps_must_agree_with_proved_output_mapping_time():
    m=module();data,reader,window,_=_resolve_case();data['timeline']['fps_num']=8
    with pytest.raises(ValueError,match='time|fps'):m._resolve_manifest(data,reader,window)


def test_parent_join_without_global_correspondence_cannot_be_comparable():
    m=module();images=dict(left=texture(),right=texture());p=plan(images,kinds={0:'parent_join'})
    p['clips']=[dict(clip_id='clip_a',frames=['left']),dict(clip_id='clip_b',frames=['right'])]
    p['frames'][1]['source_clip_id']='clip_b'
    for f in p['frames']:f['output_frame_index']=None
    for r in p['regions']:r['anchors'].append(dict(frame_id='right',rect=[.05,.05,.95,.95]))
    result=m.measure_continuity(p,Provider(images))
    assert all(r['comparability']=='unverified' for r in result['comparisons'][0]['regions'])


def test_score_aggregation_obeys_shared_deadline():
    module();from video_ai.media._continuity_scores import scores
    p=plan(dict(left=texture(),right=texture()))
    with pytest.raises(TimeoutError):scores(p,[],[],deadline=monotonic()-1)


def test_metric_digest_excludes_new_audit_evidence_paths():
    m=module();fn=getattr(m,'_metric_digest',None);assert callable(fn),'numerical digest missing'
    from continuity_helpers import identity
    a=dict(input_sha256='a'*64,frame_results=[],trajectories=[],detectors=[],comparisons=[dict(regions=[dict(metrics={'value':1.},evidence=[identity('audit_a')])])])
    b=deepcopy(a);b['input_sha256']='b'*64;b['comparisons'][0]['regions'][0]['evidence']=[identity('audit_b')]
    assert fn(a)==fn(b)


def test_dependency_inventory_cannot_be_silently_empty(monkeypatch):
    module();import video_ai.media._continuity_audit as audit
    audit.numerical()
    class EmptyDistribution:files=[]
    monkeypatch.setattr(audit.importlib.metadata,'distribution',lambda name:EmptyDistribution())
    class Window:
        def freeze(self,*args,**kwargs):raise AssertionError('empty RECORD must be rejected first')
    with pytest.raises(RuntimeError,match='RECORD|inventory'):audit.dependencies(Window())


def test_fractional_work_center_maps_once_to_original_pixel_with_low_ties():
    module();from video_ai.media._continuity_geometry import _nearest
    assert _nearest([[.49,0.],[.0,.0],[.5,.5]],[1024,1024],[256,256]).tolist()==[[3,1],[1,1],[3,3]]


def test_feature_lru_eviction_does_not_change_numerical_content(monkeypatch):
    m=module();import video_ai.media._continuity_geometry as g
    images=dict(left=texture(),right=texture());p=plan(images)
    first=m.measure_continuity(p,Provider(images));original=g.FeatureCache
    monkeypatch.setattr(m,'FeatureCache',lambda:original(0))
    second=m.measure_continuity(p,Provider(images))
    assert first==second


def test_registration_rejects_exhausted_metadata_budget_before_sampling():
    module();from video_ai.media._continuity_geometry import register
    image=texture(64,64)
    with pytest.raises(ValueError,match='resource_limit'):
        register((image,None),(image,None),[0,0,1,1],[0,0,1,1],'subject',same_source=True,metadata_budget=0)


def test_registration_obeys_deadline_inside_geometry_stage():
    module();from video_ai.media._continuity_geometry import register
    image=texture(64,64)
    with pytest.raises(TimeoutError):
        register((image,None),(image,None),[0,0,1,1],[0,0,1,1],'subject',deadline=monotonic()-1)


def test_profile_fps_comes_from_every_native_source_including_reference_provenance():
    m=module();fn=getattr(m,'_native_source_fps',None);assert callable(fn),'source fps proof helper missing'
    from fractions import Fraction
    sides={'video':dict(probe=dict(video=dict(codec_name='h264',frames=[dict(pts=0),dict(pts=1)],time_base='1/30')),
        mapping=dict(rows=[dict(clip_id='clip_a')]),risks=[])}
    assert fn(sides)=={Fraction(30)}
    sides['png']=dict(probe=dict(video=dict(codec_name='png')),mapping=dict(rows=[dict(clip_id='unrelated')]),risks=[])
    assert fn(sides) is None
