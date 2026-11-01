import importlib
from copy import deepcopy
import math
import pytest
from continuity_helpers import identity


def module():
    assert importlib.util.find_spec('video_ai.media.continuity_calibration') is not None,'calibration interface missing'
    return importlib.import_module('video_ai.media.continuity_calibration')


def catalog():
    sources=[]
    for i,group in enumerate(('group_a','group_b')):
        sources.append(dict(source_id=f'source_{i}',genre='animals',source_kind='captured',scene_group=group,
            media=identity('media',i),frame_records=[identity('frame',i*100+j) for j in range(8)],
            interval=dict(start_pts=0,end_pts=8,time_base='1/2'),rights_note='fixture only',
            regions=identity('regions',i),truth=identity('truth',i),context=None))
    return dict(schema_version=1,corpus_id='fixture_corpus',corpus_kind='fixture_only',sources=sources,
        split=dict(calibration_groups=['group_a'],holdout_groups=['group_b']),created_at='2026-10-24T00:00:00+00:00')


def test_catalog_split_leakage_and_pure_template():
    m=module();c=catalog();before=deepcopy(c)
    assert m.validate_calibration_catalog(c)==before and c==before
    template=m.build_annotation_template(c)
    assert template['corpus_sha256']
    assert template['entries']==[] # Regions are external files; pure builder must not invent IDs.
    assert template['annotators']==['annotator_a','annotator_b']
    assert template['adjudicator']=='adjudicator'
    for mutate in (lambda d:d['split']['holdout_groups'].append('group_a'),
        lambda d:d['sources'][1].update(media=deepcopy(d['sources'][0]['media'])),
        lambda d:d['sources'][0].update(genre='unknown'),lambda d:d.update(extra=True),
        lambda d:d['sources'].__setitem__(0,None)):
        bad=deepcopy(c);mutate(bad)
        with pytest.raises(ValueError):m.validate_calibration_catalog(bad)


def test_fit_threshold_uses_strict_greater_and_tie_high():
    m=module()
    assert m._fit_threshold([(0.,'normal'),(2.,'anomaly')])==1.
    assert m._fit_threshold([(1.,'normal'),(1.,'anomaly')]) is None
    assert m._fit_threshold([(0.,'normal')]) is None
    # Two equally good boundaries; the higher midpoint wins.
    assert m._fit_threshold([(0.,'normal'),(1.,'anomaly'),(2.,'normal'),(3.,'anomaly')])==2.5


def test_metrics_keep_abstentions_in_end_to_end_recall_and_zero_denominators():
    m=module()
    rows=[dict(label='anomaly',score=3.,state='comparable'),dict(label='anomaly',score=None,state='unverified'),
          dict(label='normal',score=1.,state='comparable'),dict(label='normal',score=None,state='not_comparable')]
    result=m._metrics(rows,2.,group='all')
    assert (result['tp'],result['fp'],result['tn'],result['fn'])==(1,0,1,0)
    assert result['recall']==1. and result['end_to_end_recall']==.5 and result['coverage']==.5
    assert result['abstained_positive']==result['abstained_negative']==1
    empty=m._metrics([],None,group='all')
    assert empty['fpr'] is empty['coverage'] is None
    assert m._wilson(0,1)==pytest.approx([0.,.7934506856],abs=1e-9)
    assert m._wilson(1,1)==pytest.approx([.2065493144,1.],abs=1e-9)


def test_human_labels_cannot_self_sign_or_skip_playback():
    m=module();c=catalog();labels=m.build_annotation_template(c)
    labels['annotators']=['same','same']
    with pytest.raises(ValueError):m.validate_calibration_catalog(c,labels)


def test_control_recipe_and_display_time_preserve_source_order_except_reset():
    m=module()
    recipe=m._recipe('cumulative_drift',12,['subject'])
    assert recipe['linear_r_factors']==[1.]*4+[1.1]*4+[1.2]*4
    assert recipe['linear_b_factors']==[1.]*4+[.95]*4+[.9]*4
    assert m._recipe('camera_jump',8,['subject'])['translation_x']==[0.]*4+[.08]*4
    assert callable(m.calibrate_continuity) and callable(m.build_control_case)


def test_profile_cannot_enable_detector_without_observed_metrics():
    m=module()
    from video_ai.media._continuity_schema import DETECTORS,PARAMETERS
    from video_ai.planning.production_scenes import canonical_digest
    profile=dict(schema_version=1,algorithm='continuity_cv_v1',parameters_sha256=canonical_digest(PARAMETERS),
        dependency_fingerprint='a'*64,corpus=identity('corpus'),labels=identity('labels'),split_sha256='b'*64,
        thresholds=identity('thresholds'),purpose='real_benchmark',status='ready',
        applicability=dict(genres=list(m.GENRES),source_kinds=['captured'],source_fps=[dict(num=16,den=1)],analysis_space='srgb_rgb24_v1',comparison_kinds=['adjacent']),
        detectors=[dict(detector_id=d,threshold=.1,enabled=True,calibration_groups=['cal'],holdout_groups=['hold'],reason=None) for d in DETECTORS],
        calibration_metrics=[],holdout_metrics=[],limitations=[],created_at='2026-10-24T00:00:00+00:00')
    with pytest.raises(ValueError,match='metrics|evidence|coverage'):m._validate_profile(profile)


def test_verified_shared_origin_cannot_cross_derivative_scene_groups():
    m=module();lineage=getattr(m,'_media_lineage',None);claim=getattr(m,'_claim_lineage',None)
    assert callable(lineage) and callable(claim),'verified derivative lineage checks missing'
    origin=identity('original_media');receipt=identity('processing_receipt')
    class Reader:
        def _json(self,path):return dict(source=origin)
    first=dict(source=identity('derivative_a'),processing=dict(command_records=[receipt]))
    second=dict(source=identity('derivative_b'),processing=dict(command_records=[receipt]))
    owners={};claim(lineage(first,Reader()),'group_a',owners)
    with pytest.raises(ValueError,match='lineage|scene group'):claim(lineage(second,Reader()),'group_b',owners)


def test_control_peak_image_budget_includes_packed_masks_and_warp_temporaries():
    module();import video_ai.media._continuity_controls as controls
    check=getattr(controls,'_control_image_budget',None);assert callable(check),'control peak allocation guard missing'
    check(64*36,0,camera=True,local=False)
    for camera,local in ((True,False),(False,True)):
        with pytest.raises(ValueError,match='resource_limit'):
            check(33554432//3,33554432,camera=camera,local=local)


def test_control_target_selection_is_bound_to_corpus_and_rejects_malformed_subsets():
    m=module();c=catalog()
    c['sources'][0]['control_targets']={'occlusion':dict(region_ids=['hand'],authorization=identity('permission'))}
    assert m.validate_calibration_catalog(c)==c
    labels=m.build_annotation_template(c)
    changed=deepcopy(c);changed['sources'][0]['control_targets']['occlusion']['region_ids']=['pen']
    with pytest.raises(ValueError,match='corpus'):m.validate_calibration_catalog(changed,labels)
    for targets in ({'unchanged':dict(region_ids=['hand'],authorization=identity())},
                    {'occlusion':dict(region_ids=[],authorization=identity())},
                    {'local_color':dict(region_ids=['pen','pen'],authorization=identity())},
                    {'occlusion':dict(region_ids=['hand'],authorization=None)},
                    {'occlusion':dict(region_ids=['hand'],authorization=identity(),extra=True)}):
        bad=deepcopy(c);bad['sources'][0]['control_targets']=targets
        with pytest.raises(ValueError):m.validate_calibration_catalog(bad)


def test_nonuniform_source_interval_uses_verified_native_boundaries():
    m=module();check=getattr(m,'_source_timing',None)
    assert callable(check),'native interval coverage validator missing'
    interval=dict(start_pts=0,end_pts=4500,time_base='1/1000')
    source=dict(interval=interval)
    ticks=[0,500,1125,1625,2250,2750,3375,3875,4500]
    native=[dict(pts=t,duration=500) for t in ticks]
    records=[dict(frame_index=i,pts=t,time_base='1/1000',sidecar=identity('side')) for i,t in enumerate(ticks[:-1])]
    sides={records[0]['sidecar']['path']:dict(probe=dict(video=dict(time_base='1/1000',frames=native)))}
    assert check(source,records,sides)=={(2,1),(8,5)}
    for mutate in (lambda s,r,v:s['interval'].update(end_pts=4375),
                   lambda s,r,v:r.pop(2),lambda s,r,v:r[2].update(pts=1126),
                   lambda s,r,v:r[2].update(time_base='1/8')):
        s,r,v=deepcopy((source,records,sides));mutate(s,r,v)
        with pytest.raises(ValueError):check(s,r,v)
    # At EOF, the explicit duration is evidence; extrapolation is forbidden.
    eof=deepcopy(sides);eof[records[0]['sidecar']['path']]['probe']['video']['frames'].pop()
    endsource=deepcopy(source);endsource['interval']['end_pts']=4375
    assert check(endsource,records,eof)=={(2,1),(8,5)}
    del eof[records[0]['sidecar']['path']]['probe']['video']['frames'][-1]['duration']
    with pytest.raises(ValueError,match='duration|boundary'):check(endsource,records,eof)


def test_profile_domain_retains_observed_nonuniform_time_steps():
    from video_ai.media.continuity_analysis import _native_source_fps
    from fractions import Fraction
    sides={'video':dict(probe=dict(video=dict(codec_name='h264',time_base='1/1000',frames=[dict(pts=t) for t in (0,500,1125,1625)])),
                        risks=[dict(code='unverified_mapping')],mapping=dict(rows=[]))}
    assert _native_source_fps(sides)=={Fraction(2),Fraction(8,5)}
