"""Offline displayed-pixel recurrence evidence. Isolated; no production profile.

This recognizes replay of a recorded segment, not semantic action identity.
The provider accepts display ordinal only and returns image + valid_mask.
No recipe, source mapping, original hashes, labels or tracking truth enter here.
"""
from fractions import Fraction
import hashlib
import math
import cv2
import numpy as np

ALGORITHM='AI_displayed_ROI_temporal_replay_v1'
PARAMETERS=dict(descriptor_edge=64,lookahead_seconds=.4,minimum_lag_seconds=.5,
    precursor_seconds=.2,minimum_frames=6,minimum_texture_std=3.,
    minimum_step_motion=.25,minimum_span_motion=1.,
    strong_match_absolute_error=1.,strong_match_span_fraction=.12,
    independent_lag_seconds=.2,timing_relative_tolerance=.1,timing_absolute_tolerance=.002)


def measure_replay(provider,pts,time_base,join,roi):
    """Measure one declared join with a fixed normalized clip-start ROI.

    All requested ROI pixels must be valid. Conservative abstentions remain
    null, never normal zero. Timing uses native PTS and is compared at every
    step; no assumed FPS, interpolation, source identity or future ROI truth.
    """
    p=PARAMETERS
    t=np.asarray([float(Fraction(int(x))*Fraction(time_base)) for x in pts])
    if len(t)<2 or not np.isfinite(t).all() or np.any(np.diff(t)<=0):
        raise ValueError('invalid timestamps')
    if type(join) is not int or not 0<join<len(t):raise ValueError('invalid join')
    box=np.asarray(roi,dtype=float)
    if box.shape!=(4,) or not np.isfinite(box).all() or not (0<=box[0]<box[2]<=1 and 0<=box[1]<box[3]<=1):
        raise ValueError('invalid ROI')
    result=dict(algorithm=ALGORITHM,state='unverified',score=None,reason=None,requested_frames=0,
                latency_seconds=None,query_interval=None,best_start=None,pixel_sha256={})
    def stop(reason):result['reason']=reason;return result
    end=int(np.searchsorted(t,t[join]+p['lookahead_seconds'],side='left'))
    if end>=len(t):return stop('insufficient_lookahead')
    q=end-join+1
    result.update(query_interval=[join,end+1],latency_seconds=float(t[end]-t[join]))
    if q<p['minimum_frames']:return stop('insufficient_lookahead')
    candidates=[k for k in range(join-q+1) if t[join]-t[k]>=p['minimum_lag_seconds']]
    if not candidates:return stop('insufficient_history')
    descriptors=[];shape=None;texture=[]
    # Bounded native frames: history through the actual post-join window only.
    for i in range(end+1):
        v=provider(i);image=np.asarray(v['image']);mask=np.asarray(v['valid_mask'])
        result['requested_frames']+=1
        if image.dtype!=np.uint8 or image.ndim!=2 or mask.shape!=image.shape or mask.dtype!=bool:
            raise ValueError('invalid image or mask')
        if shape is None:shape=image.shape
        if image.shape!=shape:raise ValueError('changing frame dimensions')
        h,w=shape;x0,y0,x1,y1=box
        bounds=(math.floor(x0*w),math.floor(y0*h),math.ceil(x1*w),math.ceil(y1*h))
        x0,y0,x1,y1=bounds
        if x1-x0<4 or y1-y0<4:return stop('invalid_support')
        if not mask[y0:y1,x0:x1].all():return stop('invalid_support')
        raw=image[y0:y1,x0:x1]
        result['pixel_sha256'][str(i)]=hashlib.sha256(raw.tobytes()).hexdigest()
        d=cv2.resize(raw,(p['descriptor_edge'],p['descriptor_edge']),interpolation=cv2.INTER_AREA).astype(np.float32)
        texture.append(float(d.std()));descriptors.append(d-d.mean())
    d=np.stack(descriptors);query=d[join:end+1]
    step=float(np.mean(np.abs(np.diff(query,axis=0))))
    span=float(np.max(np.mean(np.abs(query-query[0]),axis=(1,2))))
    result.update(step_motion=step,span_motion=span,query_texture=float(np.median(texture[join:end+1])))
    if result['query_texture']<p['minimum_texture_std']:return stop('insufficient_texture')
    if step<p['minimum_step_motion'] or span<p['minimum_span_motion']:return stop('insufficient_motion')
    qt=np.diff(t[join:end+1]);timed=[]
    for k in candidates:
        dt=np.diff(t[k:k+q]);tolerance=p['timing_absolute_tolerance']+p['timing_relative_tolerance']*qt
        if np.all(np.abs(dt-qt)<=tolerance):timed.append(k)
    if not timed:return stop('timing_mismatch')
    errors=[float(np.mean(np.abs(d[k:k+q]-query))) for k in timed]
    best=int(np.argmin(errors));k=timed[best];error=errors[best]
    result.update(best_start=k,best_error=error,candidates=len(timed),best_lag_seconds=float(t[join]-t[k]))
    strong=max(p['strong_match_absolute_error'],p['strong_match_span_fraction']*span)
    if error<=strong:
        # Separated equally good alignments are repeated cycles, not unique replay evidence.
        ambiguous=[a for a,e in zip(timed,errors) if abs(t[a]-t[k])>=p['independent_lag_seconds'] and e<=strong]
        if ambiguous:return stop('ambiguous_periodicity')
        count=int(np.searchsorted(t,t[join]-p['precursor_seconds'],side='left'))
        length=join-count
        if length>=2 and k>=length:
            dt=np.diff(t[k-length:k+1]);actual=np.diff(t[join-length:join+1])
            timing=np.all(np.abs(dt-actual)<=p['timing_absolute_tolerance']+p['timing_relative_tolerance']*actual)
            pre=float(np.mean(np.abs(d[k-length:k]-d[join-length:join])))
            result['precursor_error']=pre
            if timing and pre<=strong:return stop('phase_continuous')
    result.update(state='comparable',reason='measured',score=float(math.exp(-error/max(span,1.))))
    return result
