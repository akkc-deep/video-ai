"""Six raw, versioned scores. No implicit quality thresholds."""
from fractions import Fraction
import math
from time import monotonic

from ._continuity_schema import DETECTORS
from ._continuity_geometry import numerical


def seconds(frame):
    if frame['display_pts'] is None or frame['display_time_base'] is None:return None
    return Fraction(frame['display_pts'])*Fraction(frame['display_time_base'])


def _row(detector,region,frames,score,confidence=0.,reason=None):
    return dict(detector_id=detector,region_id=region,frame_ids=list(frames),score=score,threshold=None,
                status='unverified',reasons=[reason or ('missing_profile' if score is not None else 'missing_history')],
                confidence=float(confidence),evidence=[])


def _mad(values):
    np,_=numerical();a=np.array(values);return float(np.median(np.abs(a-np.median(a))))


def scores(plan,comparisons,trajectories, *, deadline=None):
    def check():
        if deadline is not None and monotonic()>=deadline:raise TimeoutError('continuity score budget expired')
    check()
    np,_=numerical();frames={f['frame_id']:f for f in plan['frames']};out=[]
    clipof={f:c['clip_id'] for c in plan['clips'] for f in c['frames']}
    for pair in comparisons:
        check()
        for region in pair['regions']:
            ids=[pair['left'],pair['right']];rid=region['region_id'];metrics=region['metrics']
            if metrics is None:
                row=_row('local_color',rid,ids,None,reason=region['reasons'][0]);row['status']=region['comparability'];out.append(row)
                continue
            out.append(_row('local_color',rid,ids,metrics['delta_e_p90'],region['confidence']))
            if pair['kind']=='reference':
                out.append(_row('color_drift',rid,ids,metrics['delta_e_p90'],region['confidence']))
            if pair['kind']=='parent_join':
                baselines=[]
                for edge in (pair['left'],pair['right']):
                    t=seconds(frames[edge]);values=[]
                    if t is not None:
                        for other in comparisons:
                            if other['kind']!='adjacent' or clipof.get(other['left'])!=clipof.get(edge):continue
                            ot=seconds(frames[other['right']]);lt=seconds(frames[other['left']])
                            if ot is None or lt is None or max(abs(ot-t),abs(lt-t))>Fraction(1,2):continue
                            r=next((r for r in other['regions'] if r['region_id']==rid and r['metrics'] is not None),None)
                            if r:values.append(r['metrics']['delta_e_median'])
                    if len(values)<3:break
                    baselines.append(float(np.median(values)))
                score=max(0.,metrics['delta_e_median']-max(baselines)) if len(baselines)==2 else None
                out.append(_row('seam_color',rid,ids,score,region['confidence']))
    for region in plan['regions']:
        check()
        rid=region['region_id'];groups={}
        for pair in comparisons:
            if pair['kind']!='reference':continue
            r=next((r for r in pair['regions'] if r['region_id']==rid and r['metrics'] is not None),None)
            if r is None:continue
            groups.setdefault(pair['left'],[]).append((pair,r))
        if not groups:
            out.append(_row('color_drift',rid,[],None,reason='missing_reference'))
            out.append(_row('cumulative_color',rid,[],None,reason='missing_reference'))
        for reference,items in groups.items():
            # A repeated declaration of one reference/frame is one observation.
            items=list({p['right']:(p,r) for p,r in items}.values())
            counts={c['clip_id']:0 for c in plan['clips']}
            for p,_ in items:
                if clipof.get(p['right']) in counts:counts[clipof[p['right']]]+=1
            eligible={cid for cid,n in counts.items() if n>=3};items=[(p,r) for p,r in items if clipof.get(p['right']) in eligible]
            items.sort(key=lambda v:seconds(frames[v[0]['right']]) or Fraction(0))
            score=None
            if len(eligible)>=3 and all(seconds(frames[p['right']]) is not None for p,_ in items):
                ts=[float(seconds(frames[p['right']])) for p,_ in items];ds=[r['metrics']['delta_lab_median'] for _,r in items]
                count=len(ts)*(len(ts)-1)//2
                # One float64 slope buffer (<=64MiB for <=4096 frames), reused
                # across components; no O(n²) Python-object lists.
                if count*8>67108864:raise ValueError('resource_limit: cumulative slopes')
                buffer=np.empty(count,dtype=np.float64);tt=np.asarray(ts);dd=np.asarray(ds);slopes=[]
                for k in range(3):
                    pos=0
                    for i in range(len(ts)-1):
                        check();dt=tt[i+1:]-tt[i];valid=dt>0;n=int(np.count_nonzero(valid))
                        buffer[pos:pos+n]=(dd[i+1:,k][valid]-dd[i,k])/dt[valid];pos+=n
                    if pos:slopes.append(float(np.median(buffer[:pos],overwrite_input=True)))
                del buffer
                if len(slopes)==3:score=float(np.linalg.norm(slopes)*(max(ts)-min(ts)))
            out.append(_row('cumulative_color',rid,[reference,*[p['right'] for p,_ in items]],score,
                            min((r['confidence'] for _,r in items),default=0.)))
    roles={r['region_id']:r['role'] for r in plan['regions']}
    for trajectory in trajectories:
        samples=trajectory['samples'];rid=trajectory['region_id'];history=[]
        for sample in samples:
            check()
            f=frames[sample['frame_id']];t=seconds(f)
            if t is None:continue
            old=[s for ot,s in history if 0<t-ot<=Fraction(1,2)]
            if roles[rid]=='subject':
                v=sample['camera_compensated_velocity'];valid=[s for s in old if s['camera_compensated_velocity'] is not None]
                score=None
                if v is not None and len(valid)>=3:
                    vs=[np.array(s['camera_compensated_velocity']) for s in valid]
                    diffs=[float(np.linalg.norm(b-a)) for a,b in zip(vs,vs[1:])]
                    score=float(np.linalg.norm(np.array(v)-vs[-1])/(_mad(diffs)+1e-6))
                out.append(_row('motion_reset',rid,[sample['frame_id']],score,sample['confidence']))
            else:
                def camera_velocity(s):
                    return s.get('_camera_velocity')
                current=camera_velocity(sample);valid=[s for s in old if camera_velocity(s) is not None];score=None
                if current is not None and len(valid)>=3:
                    cs=[np.array(camera_velocity(s)) for s in valid];v=np.array(current)
                    ds=[[float(np.linalg.norm(b[:2]-a[:2])),abs(float(b[2]-a[2])),abs(float(b[3]-a[3]))] for a,b in zip(cs,cs[1:])]
                    jump=[float(np.linalg.norm(v[:2]-cs[-1][:2])),abs(float(v[2]-cs[-1][2])),abs(float(v[3]-cs[-1][3]))]
                    score=max(jump[k]/(_mad([d[k] for d in ds])+1e-6) for k in range(3))
                out.append(_row('camera_jump',rid,[sample['frame_id']],score,sample['confidence']))
            history.append((t,sample))
    # A missing class still produces an explicit, non-decision row.
    present={d['detector_id'] for d in out}
    for d in DETECTORS:
        if d not in present:out.append(_row(d,None,[],None))
    for row in out:
        for event in (plan['context'] or {}).get('events',[]):
            if (row['detector_id'] in event['detector_ids'] and row['region_id'] in event['region_ids'] and
                set(row['frame_ids'])&set(event['frame_ids'])):
                row['status']='not_comparable';row['reasons']=['declared_change',event['event_id']]
    return out
