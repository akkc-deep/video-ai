"""Behavior tests for experimental displayed-pixel sequence replay."""
import importlib.util
from pathlib import Path
import cv2
import numpy as np
import pytest


def module():
    path=Path(__file__).resolve().parents[2]/'scripts/experiments/vco03_temporal_replay.py'
    assert path.exists(), 'temporal replay detector missing'
    spec=importlib.util.spec_from_file_location('replay',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def footage(n=120):
    rng=np.random.default_rng(374)
    base=cv2.GaussianBlur(rng.integers(30,210,(96,128),dtype=np.uint8),(5,5),1)
    result=[]
    for i in range(n):
        a=base.copy()
        cv2.circle(a,(12+i%100,40+round(20*np.sin(i/13))),11,230,-1)
        cv2.rectangle(a,(30,5+i%60),(50,15+i%60),25,-1)
        result.append(a)
    return result


def measure(images,pts=None,roi=(0,0,1,1),mask=None,join=60):
    m=module();requests=[]
    def provider(i):
        requests.append(i)
        return dict(image=images[i],valid_mask=np.ones_like(images[i],dtype=bool) if mask is None else mask)
    r=m.measure_replay(provider,pts or [i*40 for i in range(len(images))],'1/1000',join,roi)
    assert all(type(i) is int for i in requests)
    assert r['requested_frames']==len(set(requests))
    return r


@pytest.mark.parametrize('kind',['exact','jpeg','brightness'])
def test_dynamic_sequence_replay_has_strong_pixel_evidence(kind):
    a=footage();post=[]
    for f in a[:60]:
        if kind=='jpeg':
            ok,encoded=cv2.imencode('.jpg',f,[cv2.IMWRITE_JPEG_QUALITY,65]);assert ok
            f=cv2.imdecode(encoded,cv2.IMREAD_GRAYSCALE)
        if kind=='brightness':f=np.clip(f.astype(int)+12,0,255).astype(np.uint8)
        post.append(f)
    r=measure(a[:60]+post)
    assert r['state']=='comparable' and r['score']>.8
    assert r['best_start']==0 and r['latency_seconds']>=.36


def test_continuous_action_is_below_replay_evidence():
    r=measure(footage())
    assert r['state']=='comparable' and r['score']<.7


def test_static_textured_frames_abstain():
    r=measure([footage()[0]]*120)
    assert r['score'] is None and r['reason']=='insufficient_motion'


def test_established_periodic_motion_abstains():
    a=footage(20)
    r=measure([a[i%20] for i in range(120)])
    assert r['score'] is None and r['reason'] in ('ambiguous_periodicity','phase_continuous')


def test_matching_precursor_is_continuation_not_unexpected_replay():
    a=footage();a[55:75]=[x.copy() for x in a[15:35]]
    r=measure(a)
    assert r['score'] is None and r['reason']=='phase_continuous'


def test_invalid_or_occluded_support_abstains():
    r=measure(footage(),mask=np.zeros((96,128),dtype=bool))
    assert r['score'] is None and r['reason']=='invalid_support'


def test_fixed_roi_does_not_use_motion_outside_region():
    a=footage();r=measure(a[:60]+a[:60],roi=(.8,0,1,.2))
    assert r['score'] is None and r['reason']=='insufficient_motion'


def test_vfr_native_timing_is_checked_without_assuming_fps():
    a=footage();deltas=[35,45]*60;pts=np.cumsum([0]+deltas[:-1]).tolist()
    r=measure(a[:60]+a[:60],pts=pts)
    assert r['state']=='comparable' and r['score']>.9


def test_time_warped_match_does_not_certify_native_sequence_replay():
    a=footage();pts=list(range(0,2400,40))+list(range(2400,7200,80))
    r=measure(a[:60]+a[:60],pts=pts)
    assert r['score'] is None and r['reason']=='timing_mismatch'


def test_nonmonotonic_pts_rejected():
    with pytest.raises(ValueError,match='timestamp'):
        measure(footage(),pts=[0]*120)


@pytest.mark.parametrize('join',[2,118])
def test_missing_history_or_lookahead_abstains(join):
    r=measure(footage(),join=join)
    assert r['score'] is None
