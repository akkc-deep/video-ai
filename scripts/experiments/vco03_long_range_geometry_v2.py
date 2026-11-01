"""Isolated encoded-luma geometry experiment; no production profile support."""
import math
import hashlib
from collections import OrderedDict
from fractions import Fraction
from time import monotonic
import cv2
import numpy as np

ALGORITHM='AI_luma_SIFT_join_geometry_stable_overlap_v2'
PARAMETERS=dict(maximum_feature_edge=512,maximum_features=800,descriptor_ratio=.75,
    minimum_inliers=12,minimum_grid_cells=4,minimum_inlier_fraction=.5,
    maximum_residual_work_pixels=2.,minimum_patch_ncc=.85,minimum_overlap=.35,
    minimum_affine_determinant=.5,maximum_affine_determinant=2.,work_edge=256,
    camera_background='whole_frame_excluding_current_subject_boxes',subject_jump_fraction=.08)
VARIANTS=('unchanged','allowed_camera','occlusion','motion_reset','camera_jump','subject_jump')

def _box(box):
    a=np.asarray(box,dtype=np.float64)
    if a.shape!=(4,) or not np.isfinite(a).all() or a[2]<=a[0] or a[3]<=a[1]:raise ValueError('invalid ROI')
    return a

def _mask(shape,box):
    h,w=shape;x0,y0,x1,y1=_box(box);y,x=np.indices(shape)
    return ((x+.5)/w>=x0)&((x+.5)/w<x1)&((y+.5)/h>=y0)&((y+.5)/h<y1)

def background_mask(shape,subject_boxes):
    result=np.ones(shape,dtype=bool)
    for box in subject_boxes:result&=~_mask(shape,box)
    return result

def source_index(variant,index,n):
    if variant not in VARIANTS or not 0<=index<n:raise ValueError('invalid control coordinate')
    return index-n//2 if variant=='motion_reset' and index>=n//2 else index

def transform_luma(image,variant,index,n,subject_box):
    if variant not in VARIANTS or image.ndim!=2 or image.dtype!=np.uint8 or not 0<=index<n:raise ValueError('invalid luma control')
    h,w=image.shape;box=_box(subject_box).tolist();out=image.copy();valid=np.ones_like(image,dtype=bool)
    scale=1.;tx=0.
    if variant=='allowed_camera':scale=1+.05*index/(n-1);tx=.05*index/(n-1)
    if variant=='camera_jump' and index>=n//2:tx=.08
    if scale!=1 or tx!=0:
        a=np.float64([[scale,0,(1-scale)*(w-1)/2+tx*w],[0,scale,(1-scale)*(h-1)/2]])
        out=cv2.warpAffine(out,a,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        valid=cv2.warpAffine(valid.astype(np.float32),a,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)>=1-1e-6
        box=[scale*box[0]+(1-scale)/2+tx,scale*box[1]+(1-scale)/2,scale*box[2]+(1-scale)/2+tx,scale*box[3]+(1-scale)/2]
    if variant=='occlusion' and 3*n//8<=index<math.ceil(5*n/8):
        mask=_mask(image.shape,[box[0],box[1],box[2],(box[1]+box[3])/2]);out[mask]=128;valid[mask]=False
    if variant=='subject_jump' and index>=n//2:
        x0,y0,x1,y1=box;x0=max(0,math.floor(x0*w));x1=min(w,math.ceil(x1*w));y0=max(0,math.floor(y0*h));y1=min(h,math.ceil(y1*h))
        dx=max(0,min(round(PARAMETERS['subject_jump_fraction']*w),w-x1))
        if x1>x0 and y1>y0 and dx:
            erase=np.zeros_like(image);erase[y0:y1,x0:x1]=255
            out=cv2.inpaint(image,erase,3,cv2.INPAINT_TELEA);valid[erase>0]=False
            out[y0:y1,x0+dx:x1+dx]=image[y0:y1,x0:x1];valid[y0:y1,x0+dx:x1+dx]=True
            box=[box[0]+dx/w,box[1],box[2]+dx/w,box[3]]
    return dict(image=out,valid_mask=valid,subject_rect=box)

def features(image):
    if image.ndim!=2 or image.dtype!=np.uint8 or max(image.shape)>512:raise ValueError('bounded8-bit luma image required')
    keys,desc=cv2.SIFT_create(nfeatures=PARAMETERS['maximum_features']).detectAndCompute(image,None)
    return np.float32([k.pt for k in keys]).reshape(-1,2),desc

def _filtered_features(image,mask,provided):
    pts,desc=provided if provided is not None else features(image)
    if desc is None:return np.empty((0,2),np.float32),None
    p=np.rint(pts).astype(int);inside=(p[:,0]>=4)&(p[:,1]>=4)&(p[:,0]<image.shape[1]-4)&(p[:,1]<image.shape[0]-4)
    safe=np.zeros(len(p),dtype=bool)
    # Match patches, not just their centers, must be valid ROI support.
    eroded=cv2.erode(mask.astype(np.uint8),np.ones((9,9),np.uint8),borderType=cv2.BORDER_CONSTANT,borderValue=0)>0
    safe[inside]=eroded[p[inside,1],p[inside,0]]
    return pts[safe],desc[safe]

def _cells(points,box):
    box=_box(box);q=np.floor((points-box[:2])/(box[2:]-box[:2])*4).astype(int)
    return len(set(map(tuple,np.clip(q,0,3).tolist())))

def residual_work_pixels(predicted,observed,size):
    return np.linalg.norm((np.asarray(predicted)-np.asarray(observed))*(PARAMETERS['work_edge']/max(size)),axis=1)

def polygon_overlap(polygon,box):
    """Float64 rectangle clipping avoids near-coincident float32 edge loss."""
    p=np.asarray(polygon,dtype=np.float64);box=_box(box)
    def area(v):
        if len(v)<3:return 0.
        v=np.asarray(v);return abs(float(v[:,0]@np.roll(v[:,1],-1)-v[:,1]@np.roll(v[:,0],-1)))/2
    original=area(p)
    x0,y0,x1,y1=max(0,box[0]),max(0,box[1]),min(1,box[2]),min(1,box[3])
    if x0>=x1 or y0>=y1 or original<=1e-15:return 0.
    for axis,bound,lower in ((0,x0,True),(0,x1,False),(1,y0,True),(1,y1,False)):
        if not len(p):return 0.
        output=[];previous=p[-1];was=previous[axis]>=bound if lower else previous[axis]<=bound
        for current in p:
            inside=current[axis]>=bound if lower else current[axis]<=bound
            if inside!=was:
                fraction=(bound-previous[axis])/(current[axis]-previous[axis]);point=previous+fraction*(current-previous);point[axis]=bound;output.append(point)
            if inside:output.append(current)
            previous,was=current,inside
        p=np.asarray(output,dtype=np.float64).reshape(-1,2)
    return min(1.,max(0.,area(p)/original))

def register_pair(left,right,left_box,right_box=None,*,left_mask=None,right_mask=None,left_features=None,right_features=None):
    if left.shape!=right.shape or left.ndim!=2 or left.dtype!=np.uint8 or right.dtype!=np.uint8 or max(left.shape)>512:raise ValueError('same bounded8-bit luma dimensions required')
    h,w=left.shape;lb=_box(left_box);rb=_box(right_box) if right_box is not None else np.array([0.,0.,1.,1.])
    lm=_mask(left.shape,lb);rm=_mask(right.shape,rb)
    for mask,shape in ((left_mask,left.shape),(right_mask,right.shape)):
        if mask is not None and (mask.shape!=shape or mask.dtype!=np.bool_):raise ValueError('invalid support mask')
    if left_mask is not None:lm&=left_mask
    if right_mask is not None:rm&=right_mask
    result=dict(affine=None,reason='insufficient_descriptor_support',inliers=0,cells=0,matches=0)
    lp,ld=_filtered_features(left,lm,left_features);rp,rd=_filtered_features(right,rm,right_features)
    if ld is None or rd is None or min(len(ld),len(rd))<12:return result
    matcher=cv2.BFMatcher(cv2.NORM_L2)
    def choices(a,b):
        return {m.queryIdx:m.trainIdx for pair in matcher.knnMatch(a,b,k=2) if len(pair)==2 for m,n in [pair] if m.distance<PARAMETERS['descriptor_ratio']*n.distance}
    ab,ba=choices(ld,rd),choices(rd,ld);pairs=[(i,j) for i,j in ab.items() if ba.get(j)==i]
    result['matches']=len(pairs)
    if len(pairs)<12:return result
    xx=np.float32([lp[i] for i,j in pairs]);yy=np.float32([rp[j] for i,j in pairs]);ncc=[];keep=[]
    for i,(p,q) in enumerate(zip(xx,yy)):
        x,y=np.rint(p).astype(int);u,v=np.rint(q).astype(int)
        a=left[y-4:y+5,x-4:x+5].astype(float).ravel();b=right[v-4:v+5,u-4:u+5].astype(float).ravel();a-=a.mean();b-=b.mean();den=np.linalg.norm(a)*np.linalg.norm(b)
        corr=float(a@b/den) if den>0 else -1.
        if corr>=PARAMETERS['minimum_patch_ncc']:keep.append(i);ncc.append(corr)
    if len(keep)<12:return dict(result,reason='insufficient_patch_support')
    xx,yy=xx[keep],yy[keep];cv2.setRNGSeed(73031)
    matrix,inliers=cv2.estimateAffine2D(xx,yy,method=cv2.RANSAC,ransacReprojThreshold=2*max(w,h)/256,maxIters=1000,confidence=.99,refineIters=10)
    if matrix is None:return dict(result,reason='no_robust_affine')
    residual=residual_work_pixels(xx@matrix[:,:2].T+matrix[:,2],yy,(w,h))
    ok=(inliers.ravel()>0)&(residual<=PARAMETERS['maximum_residual_work_pixels'])
    count=int(ok.sum());fraction=count/len(xx);det=float(np.linalg.det(matrix[:,:2]));norm=(xx[ok]+.5)/[w,h];cells=_cells(norm,lb) if count else 0
    result.update(inliers=count,cells=cells,inlier_fraction=fraction)
    if count<12 or cells<4 or fraction<.5 or not .5<=det<=2:return dict(result,reason='insufficient_robust_support')
    a=matrix.copy();a[:,:2]=np.diag([1/w,1/h])@matrix[:,:2]@np.diag([w,h]);a[:,2]=(matrix[:,2]+.5-matrix[:,:2]@np.array([.5,.5]))/[w,h]
    corners=np.array([[lb[0],lb[1]],[lb[2],lb[1]],[lb[2],lb[3]],[lb[0],lb[3]]])@a[:,:2].T+a[:,2]
    target=rb.copy() if right_box is not None else np.r_[corners.min(axis=0),corners.max(axis=0)]
    overlap=polygon_overlap(corners,target)
    if overlap<PARAMETERS['minimum_overlap']:return dict(result,reason='insufficient_overlap')
    correspondence=np.stack((xx[ok],yy[ok]),axis=1).astype('<f4').tobytes()
    return dict(result,affine=a.tolist(),reason=None,overlap=overlap,ncc_median=float(np.median(ncc)),residual_work_p90=float(np.quantile(residual[ok],.9)),correspondence_sha256=hashlib.sha256(correspondence).hexdigest())

def pair_velocities(subject,camera,left_box,dt):
    if not isinstance(dt,(float,int)) or not math.isfinite(dt) or dt<=0:raise ValueError('positive finite native dt required')
    c=(_box(left_box)[:2]+_box(left_box)[2:])/2
    def displacement(a):
        a=np.asarray(a,float)
        if a.shape!=(2,3) or not np.isfinite(a).all():raise ValueError('finite affine required')
        return a[:,:2]@c+a[:,2]-c
    image=displacement(subject)/dt if subject is not None else None
    compensated=(image-displacement(camera)/dt).tolist() if image is not None and camera is not None else None
    return dict(image_plane=image.tolist() if image is not None else None,compensated=compensated)

def measure_sequence(plan,provider,*,deadline=None):
    """Measure every declared temporal pair, without access to recipes/truth."""
    from video_ai.media._continuity_geometry import camera_parts
    frames={f['frame_id']:f for f in plan['frames']}
    if len(frames)!=len(plan['frames']) or len(frames)>4096:raise ValueError('invalid bounded frame list')
    anchors={a['frame_id']:a['rect'] for r in plan['anchors'] if r['role']=='subject' for a in r['anchors']}
    boxes={fid:list(box) for fid,box in anchors.items()};cache=OrderedDict();hashes={};pairs=[]
    subject_samples={};camera_samples={};last_box=None
    def value(fid):
        if fid in cache:
            result=cache.pop(fid);cache[fid]=result;return result
        if len(cache)>=2:cache.popitem(last=False)
        v=provider(fid);f=features(v['image']);result=(v,f);cache[fid]=result
        hashes[fid]=hashlib.sha256(v['image'].tobytes()).hexdigest();return result
    def stamp(fid):
        ts=frames[fid]['timestamp'];return Fraction(ts['pts'])*Fraction(ts['time_base'])
    def sample(fid):
        return dict(frame_id=fid,timestamp=dict(frames[fid]['timestamp']),image_plane_velocity=None,camera_compensated_velocity=None,
                    camera_translation=None,camera_rotation=None,camera_log_scale=None,confidence=0.,status='tracking_lost')
    for pair in plan['comparisons']:
        if deadline is not None and monotonic()>deadline:raise TimeoutError('bounded luma geometry case budget')
        lf,rf=pair['left'],pair['right'];lv,lk=value(lf);rv,rk=value(rf);dt=float(stamp(rf)-stamp(lf))
        if not dt>0:raise ValueError('native temporal pair must advance')
        lb=boxes.get(lf);rb=anchors.get(rf)
        if lb is not None:last_box=lb
        exclusion_left=lb if lb is not None else last_box
        exclusion_right=rb if rb is not None else exclusion_left
        lm=background_mask(lv['image'].shape,[exclusion_left] if exclusion_left is not None else [])&lv['valid_mask']
        rm=background_mask(rv['image'].shape,[exclusion_right] if exclusion_right is not None else [])&rv['valid_mask']
        camera=register_pair(lv['image'],rv['image'],[0,0,1,1],[0,0,1,1],left_mask=lm,right_mask=rm,left_features=lk,right_features=rk)
        subject=register_pair(lv['image'],rv['image'],lb,rb,left_mask=lv['valid_mask'],right_mask=rv['valid_mask'],left_features=lk,right_features=rk) if lb is not None else dict(affine=None,reason='subject_tracking_lost',inliers=0,cells=0,matches=0)
        ca,sa=camera['affine'],subject['affine']
        subject_samples.setdefault(lf,sample(lf));camera_samples.setdefault(lf,sample(lf))
        ss,cs=sample(rf),sample(rf)
        if ca is not None:
            trans,rot,scale=camera_parts(np.array(ca));cs.update(camera_translation=trans,camera_rotation=rot,camera_log_scale=scale,
                status='tracked',confidence=min(camera['inlier_fraction'],camera['overlap']))
        if sa is not None:
            velocity=pair_velocities(sa,ca,lb,dt);ss.update(image_plane_velocity=velocity['image_plane'],camera_compensated_velocity=velocity['compensated'],
                status='tracked',confidence=min(subject['inlier_fraction'],subject['overlap']))
            corners=np.array([[lb[0],lb[1]],[lb[0],lb[3]],[lb[2],lb[1]],[lb[2],lb[3]]])@np.array(sa)[:,:2].T+np.array(sa)[:,2]
            if rb is None:boxes[rf]=np.r_[corners.min(axis=0),corners.max(axis=0)].tolist()
        # A provided clip-start anchor may restart sampling after a lost pair;
        # it never supplies a displacement or replaces missing pixel evidence.
        if rb is not None:boxes[rf]=list(rb)
        subject_samples[rf]=ss;camera_samples[rf]=cs
        pairs.append(dict(comparison_id=pair['comparison_id'],kind=pair['kind'],left=lf,right=rf,subject=subject,camera=camera,
                          background_exclusion_stale=lb is None,dt_seconds=dt))
    order={f:i for i,f in enumerate(frames)}
    return dict(algorithm=ALGORITHM,trajectories=[dict(region_id='subject',samples=sorted(subject_samples.values(),key=lambda s:order[s['frame_id']])),
        dict(region_id='background',samples=sorted(camera_samples.values(),key=lambda s:order[s['frame_id']]))],pairs=pairs,controlled_frame_sha256=hashes,
        coverage=dict(requested_frames=len(frames),measured_frames=len(hashes),requested_pairs=len(plan['comparisons']),measured_pairs=len(pairs),
                      subject_supported_pairs=sum(p['subject']['affine'] is not None for p in pairs),camera_supported_pairs=sum(p['camera']['affine'] is not None for p in pairs)))
