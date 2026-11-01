"""Deterministic CPU registration and original-code-value color sampling."""
import math
from threading import RLock
from functools import lru_cache
from collections import OrderedDict
from time import monotonic

from ._continuity_schema import PARAMETERS

CV_LOCK=RLock()


@lru_cache(maxsize=1)
def numerical():
    try:
        import numpy as np
        import cv2
        from importlib.metadata import version, PackageNotFoundError
        if np.__version__!='2.2.6' or version('opencv-python-headless')!='4.12.0.88':
            raise RuntimeError('continuity requires numpy==2.2.6 and opencv-python-headless==4.12.0.88')
        try:version('opencv-python')
        except PackageNotFoundError:pass
        else:raise RuntimeError('remove opencv-python before using the headless continuity extra')
        return np,cv2
    except ImportError as exc:
        raise RuntimeError('Install video-ai[continuity] for CPU continuity diagnostics') from exc


def lab_luma(rgb):
    np,_=numerical();c=PARAMETERS['color'];u=np.asarray(rgb,dtype=np.float64)/255.
    linear=np.where(u<=c['srgb_cutoff'],u/c['srgb_divisor'],((u+c['srgb_offset'])/c['srgb_scale'])**c['srgb_gamma'])
    y=linear@np.array(c['flow_luma']);xyz=linear@np.array(c['xyz']).T/np.array(c['white'])
    d=c['lab_delta'];f=np.where(xyz>d**3,np.cbrt(xyz),xyz/(3*d*d)+4/29)
    lab=np.stack((116*f[...,1]-16,500*(f[...,0]-f[...,1]),200*(f[...,1]-f[...,2])),axis=-1)
    return lab,y


def color_metrics(left,right):
    np,_=numerical();ll,ly=lab_luma(left);rl,ry=lab_luma(right);delta=rl-ll
    lc=np.linalg.norm(ll[:,1:],axis=1);rc=np.linalg.norm(rl[:,1:],axis=1)
    def clipped(a):return {f'{c}_{kind}':float(np.mean(a[:,i]==code))
        for i,c in enumerate('rgb') for kind,code in (('low',0),('high',255))}
    lf,rf=clipped(left),clipped(right)
    return dict(delta_lab_median=np.median(delta,axis=0).tolist(),delta_e_median=float(np.median(np.linalg.norm(delta,axis=1))),
        delta_e_p90=float(np.quantile(np.linalg.norm(delta,axis=1),.9)),left_luma_median=float(np.median(ly)),
        right_luma_median=float(np.median(ry)),luma_log_ratio=float(np.median(np.log2((ry+1/65535)/(ly+1/65535)))),
        left_chroma_median=float(np.median(lc)),right_chroma_median=float(np.median(rc)),chroma_delta=float(np.median(rc-lc)),
        left_clipped_fractions=lf,right_clipped_fractions=rf,sampled_clipped_delta={k:rf[k]-lf[k] for k in lf})


def frame_arrays(value):
    np,_=numerical()
    if value is None:return None
    if type(value) is not dict or set(value)!=set(('width','height','rgb24','valid_mask')):raise ValueError('invalid FrameProvider result')
    w,h=value['width'],value['height']
    if type(w) is not int or type(h) is not int or min(w,h)<1:raise ValueError('invalid dimensions')
    if w*h*3>33554432:raise ValueError('resource_limit: raw RGB')
    if type(value['rgb24']) is not bytes or len(value['rgb24'])!=w*h*3:raise ValueError('RGB byte count differs')
    mask=value['valid_mask']
    if mask is not None and (not isinstance(mask,np.ndarray) or mask.dtype!=np.bool_ or mask.shape!=(h,w)):
        raise ValueError('padding mask must be a full-sized boolean array')
    return np.frombuffer(value['rgb24'],dtype=np.uint8).reshape(h,w,3),mask


def affine_fit(left,right,size):
    np,_=numerical();w,h=size
    if len(left)<12:return None
    x=np.column_stack((left,np.ones(len(left))));y=right
    if np.linalg.cond(x)>1e6:return None
    weights=np.ones(len(left))
    for _ in range(5):
        root=np.sqrt(weights)[:,None]
        a=np.linalg.lstsq(x*root,y*root,rcond=None)[0].T
        residual=np.linalg.norm((x@a.T-y)*[w,h],axis=1)
        weights=np.minimum(1.,1.5/np.maximum(residual,1e-12))
    det=float(np.linalg.det(a[:,:2]))
    if not .5<=det<=2.:return None
    return a,residual


def apply_affine(points,a):
    np,_=numerical();return np.asarray(points)@a[:,:2].T+a[:,2]


def transform_box(box,a):
    np,_=numerical();x0,y0,x1,y1=box
    corners=apply_affine([[x0,y0],[x0,y1],[x1,y0],[x1,y1]],a)
    return [*corners.min(axis=0).tolist(),*corners.max(axis=0).tolist()]


def camera_parts(a):
    np,_=numerical();u,_,vt=np.linalg.svd(a[:,:2]);r=u@vt
    return ((apply_affine([[.5,.5]],a)[0]-[.5,.5]).tolist(),
            math.atan2(r[1,0],r[0,0]),math.log(math.sqrt(float(np.linalg.det(a[:,:2])))))


def _inside(points,box):
    np,_=numerical();p=np.asarray(points)
    return (p[:,0]>=box[0])&(p[:,0]<box[2])&(p[:,1]>=box[1])&(p[:,1]<box[3])


def _grid(points,box):
    np,_=numerical();p=np.asarray(points)
    q=np.floor((p-np.array(box[:2]))/(np.array(box[2:])-box[:2])*4).astype(int)
    q=np.clip(q,0,3)
    return len(set(map(tuple,q.tolist())))


def _nearest(work,original_size,work_size):
    np,_=numerical()
    return np.ceil((np.asarray(work)+.5)*np.array(original_size)/np.array(work_size)-1).astype(int)


def _overlap(box,rightbox,a):
    np,cv=numerical();x0,y0,x1,y1=box
    polygon=apply_affine([[x0,y0],[x1,y0],[x1,y1],[x0,y1]],a).astype(np.float32)
    bx0,by0,bx1,by1=rightbox
    clip=np.float32([[max(0,bx0),max(0,by0)],[min(1,bx1),max(0,by0)],
                     [min(1,bx1),min(1,by1)],[max(0,bx0),min(1,by1)]])
    if clip[0,0]>=clip[1,0] or clip[0,1]>=clip[2,1]:return 0.
    area,_=cv.intersectConvexConvex(polygon,clip)
    return max(0.,min(1.,float(area)/max(float(cv.contourArea(polygon)),1e-12)))


def empty_region(region_id,reason,status='not_comparable',size=None):
    return dict(region_id=region_id,comparability=status,reasons=[reason],geometry=dict(
        basis=None,working_size=size,candidate_points=0,valid_points=0,occupied_cells=0,overlap_fraction=0.,
        fb_error_p90=None,ncc_median=None,affine=None,vectors=[],sampled_pairs=[]),confidence=0.,
        confidence_kind='match_support',confidence_components=None,metrics=None,evidence=[])


class FeatureCache:
    """Call-local LRU; no full-resolution pixels or persistent tool hashes."""
    def __init__(self,budget=32*1024*1024):
        if type(budget) is not int or not 0<=budget<=134217728:raise ValueError('resource_limit: feature cache')
        self.budget=budget;self.nbytes=0;self.values=OrderedDict()
    def get(self,key,factory):
        if key in self.values:
            value=self.values.pop(key);self.values[key]=value;return value
        value=factory()
        if value.nbytes<=self.budget:
            while self.values and self.nbytes+value.nbytes>self.budget:
                _,old=self.values.popitem(last=False);self.nbytes-=old.nbytes
            self.values[key]=value;self.nbytes+=value.nbytes
        return value


def register(left,right,box,rightbox,region_id, *, same_source=False,cache=None,cache_keys=None,metadata_budget=67108864,deadline=None):
    def check():
        if deadline is not None and monotonic()>=deadline:raise TimeoutError('continuity geometry budget expired')
    check()
    if metadata_budget<=0:raise ValueError('resource_limit: geometry metadata')
    np,cv=numerical();li,lmask=left;ri,rmask=right
    lh,lw=li.shape[:2];rh,rw=ri.shape[:2]
    if lw*rh!=rw*lh:return empty_region(region_id,'aspect_change'),None
    edge=min(256,max(lw,lh),max(rw,rh));w=round(lw/max(lw,lh)*edge);h=round(lh/max(lw,lh)*edge)
    if min(w,h)<32:return empty_region(region_id,'minimum_image_size','unverified',[w,h]),None
    size=[w,h]
    def gray(image):return np.rint(cv.resize(image,(w,h),interpolation=cv.INTER_AREA)@np.array([.2126,.7152,.0722])).astype(np.uint8)
    lg=cache.get((cache_keys[0],w,h),lambda:gray(li)) if cache else gray(li)
    rg=cache.get((cache_keys[1],w,h),lambda:gray(ri)) if cache else gray(ri)
    yy,xx=np.indices((h,w));centers=np.stack(((xx+.5)/w,(yy+.5)/h),axis=-1)
    roi=_inside(centers.reshape(-1,2),box).reshape(h,w)
    if lmask is not None:roi &= cv.resize(lmask.astype(np.uint8),(w,h),interpolation=cv.INTER_AREA)==1
    if not roi.any():return empty_region(region_id,'empty_visible_roi','not_comparable',size),None
    candidates=int(np.count_nonzero(roi)) if same_source else min(256,int(np.count_nonzero(roi)))
    # Conservative bound for coordinate/flow records plus unique pixel pairs.
    sample_bound=candidates if same_source else min(w*h,candidates*81)
    if candidates*512+sample_bound*128>metadata_budget:raise ValueError('resource_limit: geometry metadata preallocation')
    if same_source:
        lp=np.column_stack((xx[roi],yy[roi])).astype(float);rp=lp.copy();candidate=len(lp)
        fb=np.zeros(candidate);ncc=np.ones(candidate);a=np.float64([[1,0,0],[0,1,0]])
        residual=np.zeros(candidate);basis='same_source_mapping';rightbox=rightbox or box
    else:
        points=cv.goodFeaturesToTrack(lg,mask=roi.astype(np.uint8)*255,**PARAMETERS['geometry']['features'])
        if points is None:return empty_region(region_id,'insufficient_texture','not_comparable',size),None
        points=points.reshape(-1,2);points=points[np.lexsort((points[:,0],points[:,1]))].reshape(-1,1,2)
        opts=dict(PARAMETERS['geometry']['flow']);opts['winSize']=tuple(opts['winSize']);opts['criteria']=tuple(opts['criteria'])
        out,ok,_=cv.calcOpticalFlowPyrLK(lg,rg,points,None,**opts)
        if out is None:return empty_region(region_id,'registration_failed','not_comparable',size),None
        back,backok,_=cv.calcOpticalFlowPyrLK(rg,lg,out,None,**opts)
        if back is None:return empty_region(region_id,'registration_failed','not_comparable',size),None
        lp=points.reshape(-1,2).astype(float);rp=out.reshape(-1,2).astype(float);candidate=len(lp)
        fb=np.linalg.norm(lp-back.reshape(-1,2),axis=1);ncc=np.full(candidate,-1.)
        good=ok.ravel().astype(bool)&backok.ravel().astype(bool)&np.isfinite(rp).all(axis=1)&(fb<=1)
        for i in np.flatnonzero(good):
            check()
            x,y=np.rint(lp[i]).astype(int);u,v=np.rint(rp[i]).astype(int)
            if min(x,y,u,v)<4 or x+4>=w or u+4>=w or y+4>=h or v+4>=h:continue
            p=lg[y-4:y+5,x-4:x+5].astype(float).ravel();q=rg[v-4:v+5,u-4:u+5].astype(float).ravel()
            p-=p.mean();q-=q.mean();den=np.linalg.norm(p)*np.linalg.norm(q)
            if den>0:ncc[i]=float(p@q/den)
        good &= ncc>=.85
        good &= _inside((rp+.5)/[w,h],rightbox or [0,0,1,1])
        lp,rp,fb,ncc=lp[good],rp[good],fb[good],ncc[good]
        fit=affine_fit((lp+.5)/[w,h],(rp+.5)/[w,h],size)
        if fit is None:return empty_region(region_id,'registration_failed','not_comparable',size),None
        a,residual=fit;good=residual<=2
        lp,rp,fb,ncc,residual=lp[good],rp[good],fb[good],ncc[good],residual[good]
        if len(lp)<12 or _grid((lp+.5)/[w,h],box)<4:
            return empty_region(region_id,'insufficient_support','not_comparable',size),None
        basis='tracked_affine';rightbox=rightbox or transform_box(box,a)
    overlap=_overlap(box,rightbox,a)
    if overlap<.35:return empty_region(region_id,'insufficient_overlap','not_comparable',size),None
    pairs=set();accepted=[]
    offsets=np.array([(dx,dy) for dy in range(-4,5) for dx in range(-4,5)])
    for i,(p,q) in enumerate(zip(lp,rp)):
        check()
        # Integer work-grid offsets around each independently tracked center.
        pl=p+offsets;pr=q+offsets
        if not (_inside((pl+.5)/[w,h],box).all() and _inside((pr+.5)/[w,h],rightbox).all()):continue
        if (pl<0).any() or (pr<0).any() or (pl>=[w,h]).any() or (pr>=[w,h]).any():continue
        il=_nearest(pl,[lw,lh],size);ir=_nearest(pr,[rw,rh],size)
        if (il<0).any() or (ir<0).any() or (il>=[lw,lh]).any() or (ir>=[rw,rh]).any():continue
        if lmask is not None and not lmask[il[:,1],il[:,0]].all():continue
        if rmask is not None and not rmask[ir[:,1],ir[:,0]].all():continue
        pairs.update((int(x),int(y),int(u),int(v)) for (x,y),(u,v) in zip(il,ir));accepted.append(i)
    if len(pairs)<81:return empty_region(region_id,'insufficient_samples','unverified',size),None
    pairs=sorted(pairs);arr=np.array(pairs);metrics=color_metrics(li[arr[:,1],arr[:,0]],ri[arr[:,3],arr[:,2]])
    norml=(lp+.5)/[w,h];normr=(rp+.5)/[w,h];cells=_grid(norml,box)
    components=dict(tracked_fraction=len(lp)/max(candidate,1),grid_fraction=cells/16,overlap_fraction=overlap,
        fb_support=max(0.,1-float(np.quantile(fb,.9))),ncc_support=(float(np.median(ncc))+1)/2)
    confidence=1. if same_source else min(components.values())
    vectors=[dict(left=norml[i].tolist(),right=normr[i].tolist(),residual=None,fb_error=float(fb[i]),ncc=float(ncc[i])) for i in accepted]
    geometry=dict(basis=basis,working_size=size,candidate_points=candidate,valid_points=len(lp),occupied_cells=cells,
        overlap_fraction=overlap,fb_error_p90=float(np.quantile(fb,.9)),ncc_median=float(np.median(ncc)),affine=a.tolist(),
        vectors=vectors,sampled_pairs=[[[x,y],[u,v]] for x,y,u,v in pairs])
    return dict(region_id=region_id,comparability='comparable',reasons=[],geometry=geometry,confidence=float(confidence),
        confidence_kind='match_support',confidence_components=None if same_source else components,metrics=metrics,evidence=[]),rightbox
