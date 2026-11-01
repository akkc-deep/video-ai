"""Conditional, non-production photometric calibration over existing evidence."""
import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import numpy as np

from video_ai.experiments.whole_scene_case import (identity,now,read_json,verify_identity,
                                                 write_bytes,write_json)

ALGORITHM='AI_conditional_constant_color_repair_v1'
LEVELS=(1/64,1/32,1/16,1/8,1/4,1/2,1.)
OPERATIONS=('exposure','wb_r','wb_g','wb_b','chroma')
GENRES={'people','animals','transport','outdoor','indoor','animation'}
INPUT=Path('D:/VideoSi/projects/video-ai/continuity-benchmark/AI-experimental-calibration-20261025/experiment-inputs.FROZEN.json')
PROTOCOL=dict(algorithm=ALGORITHM,levels=list(LEVELS),operations=list(OPERATIONS),
    samples_per_role=1024,maximum_fit_pairs=16384,minimum_pairs=81,
    p99_error_codes=2,maximum_error_codes=4,minimum_sources=6,required_genres=sorted(GENRES),
    temporal_policy='one constant parameter for the complete source interval',
    correspondence='oracle_same_pixel',operator_selection='oracle_known_family_and_axis',
    scope='conditional arithmetic only; not real matching, automatic selection or semantic safety',
    production_eligible=False,pixel_working_budget_bytes=134217728)


def _rgb(value):
    if not isinstance(value,np.ndarray) or value.dtype!=np.uint8 or value.ndim<2 or value.shape[-1]!=3 or not value.size:
        raise ValueError('nonempty uint8 RGB required')
    return value


def _linear(rgb):
    u=rgb.astype(np.float64)/255
    return np.where(u<=.04045,u/12.92,((u+.055)/1.055)**2.4)


def _encode(x):
    x=np.clip(x,0,1)
    u=np.where(x<=.0031308,x*12.92,1.055*x**(1/2.4)-.055)
    return np.rint(np.clip(u,0,1)*255).astype(np.uint8)


def _direction(operation):
    if operation=='exposure':return np.ones(3)
    if operation in OPERATIONS[1:4]:
        d=np.full(3,-.5);d[OPERATIONS.index(operation)-1]=1.;return d
    raise ValueError('known diagonal operation required')


def transform(rgb,operation,amplitude):
    _rgb(rgb)
    if operation not in OPERATIONS or not isinstance(amplitude,(int,float)) or not math.isfinite(amplitude) or abs(amplitude)>8:
        raise ValueError('known operation and bounded finite amplitude required')
    if amplitude==0:return rgb.copy()
    x=_linear(rgb)
    if operation=='chroma':
        y=x@np.array([.2126,.7152,.0722]);out=y[...,None]+2**amplitude*(x-y[...,None])
    else:out=x*np.exp2(amplitude*_direction(operation))
    return _encode(out)


def estimate(reference,current,operation,context):
    _rgb(reference);_rgb(current)
    if reference.shape!=current.shape or operation not in OPERATIONS:raise ValueError('same RGB shape and known operation required')
    fields={'comparable','intentional_lighting_change','confirmed_motion_defect'}
    if (type(context) is not dict or set(context)!=fields or any(type(v) is not bool for v in context.values())
            or not context['comparable'] or context['intentional_lighting_change'] or context['confirmed_motion_defect']):
        return dict(status='abstained',amplitude=None,reason='context_gate')
    if np.array_equal(reference,current):return dict(status='noop',amplitude=0.,reason='identical_pixels')
    a=reference.reshape(-1,3);b=current.reshape(-1,3)
    valid=((a>=2)&(a<=253)&(b>=2)&(b<=253)).all(axis=1)
    inds=np.flatnonzero(valid)
    if len(inds)<81:return dict(status='abstained',amplitude=None,reason='insufficient_informative_pairs')
    if len(inds)>16384:inds=inds[np.linspace(0,len(inds)-1,16384,dtype=int)]
    a=_linear(a[inds]);b=_linear(b[inds])
    if operation=='chroma':
        y=b@np.array([.2126,.7152,.0722]);z=b-y[:,None];den=float(np.sum(z*z))
        if den<=1e-12:return dict(status='abstained',amplitude=None,reason='degenerate_chroma')
        scale=float(np.sum(z*(a-y[:,None]))/den)
        if not math.isfinite(scale) or scale<=0:return dict(status='abstained',amplitude=None,reason='nonpositive_chroma')
        amplitude=math.log2(scale)
    else:
        logs=np.median(np.log2(a/b),axis=0);direction=_direction(operation)
        amplitude=float(logs@direction/(direction@direction))
    if not math.isfinite(amplitude) or abs(amplitude)>8:return dict(status='abstained',amplitude=None,reason='numerical_domain')
    return dict(status='estimated',amplitude=amplitude,fit_pairs=len(inds),reason=None)


def score(reference,current,repaired):
    _rgb(reference);_rgb(current);_rgb(repaired)
    if reference.shape!=current.shape or reference.shape!=repaired.shape:raise ValueError('same scoring shape required')
    ref=reference.reshape(-1,3);cur=current.reshape(-1,3);out=repaired.reshape(-1,3)
    before=np.abs(cur.astype(np.int16)-ref);error=np.abs(out.astype(np.int16)-ref)
    p99=float(np.quantile(error.max(axis=1),.99));maximum=int(error.max())
    interior=(ref>=3)&(ref<=252)
    def clipped(v):return int(np.count_nonzero(interior&((v==0)|(v==255))))
    clipping_before,clipping_after=clipped(cur),clipped(out)
    from video_ai.media._continuity_geometry import lab_luma
    a,_=lab_luma(ref);b,_=lab_luma(out)
    return dict(before_mae=float(before.mean()),after_mae=float(error.mean()),p99_error=p99,max_error=maximum,
        delta_e76_p90=float(np.quantile(np.linalg.norm(a-b,axis=1),.9)),
        new_clip_before=clipping_before,new_clip_after=clipping_after,
        mean_signed_error=(out.astype(float)-ref).mean(axis=0).tolist(),
        passed=bool(p99<=2 and maximum<=4 and clipping_after<=clipping_before))


def _coverage(sources,split):
    if any(s['split']!=split for s in sources):raise ValueError(split+' sources required')
    eligible=[s for s in sources if s['eligible']]
    valid=(len(eligible)>=6 and len({s['scene_group'] for s in eligible})>=6
           and {s['genre'] for s in eligible}==GENRES)
    if len({s['source_id'] for s in sources})!=len(sources):raise ValueError('duplicate source')
    return eligible,valid


def _rows(rows,split):
    result={}
    for row in rows:
        if row['split']!=split:raise ValueError(split+' rows required; split leakage refused')
        if row['operation'] not in OPERATIONS:continue
        key=(row['source_id'],row['operation'],row['injection_direction'],row['level'])
        if key in result:raise ValueError('duplicate control result')
        result[key]=row
    return result


def _correct_direction(row,injection_direction):
    a=row['estimated_amplitude']
    return type(a) in (float,int) and math.isfinite(a) and a*injection_direction<=1e-12


def fit_bounds(rows,sources):
    eligible,coverage=_coverage(sources,'calibration');lookup=_rows(rows,'calibration');out=[]
    for op in OPERATIONS:
        for sign in (-1,1):
            bound=None;amplitudes=[]
            if coverage:
                for level in LEVELS:
                    at=[lookup.get((s['source_id'],op,sign,level)) for s in eligible]
                    if any(r is None or r['passed'] is not True or not _correct_direction(r,sign) for r in at):break
                    bound=level;amplitudes.extend(abs(r['estimated_amplitude']) for r in at if r['estimated_amplitude'] is not None)
            out.append(dict(operation=op,injection_direction=sign,max_injection_level=bound,
                correction_direction=-sign,correction_amplitude_ceiling=max(amplitudes) if bound is not None and amplitudes else None,
                eligible_sources=[s['source_id'] for s in eligible],coverage_sufficient=coverage,
                reason=None if bound is not None else 'no_contiguous_pass' if coverage else 'insufficient_source_genre_coverage'))
    return out


def evaluate(rows,sources,sealed):
    eligible,coverage=_coverage(sources,'holdout');lookup=_rows(rows,'holdout');out=[]
    for bound in sealed:
        limit=bound['max_injection_level'];cases=[]
        if limit is not None:
            for source in eligible:
                for level in LEVELS:
                    if level>limit:break
                    row=lookup.get((source['source_id'],bound['operation'],bound['injection_direction'],level))
                    inside=(row is not None and _correct_direction(row,bound['injection_direction'])
                            and abs(row['estimated_amplitude'])<=bound['correction_amplitude_ceiling']+1e-12)
                    cases.append(dict(source_id=source['source_id'],level=level,measured=row is not None,
                        passed=bool(row and row['passed'] and inside),within_fitted_parameter_domain=inside))
        out.append(dict(operation=bound['operation'],injection_direction=bound['injection_direction'],
            qualified=bool(coverage and cases and all(c['passed'] for c in cases)),coverage_sufficient=coverage,
            eligible_sources=[s['source_id'] for s in eligible],cases=cases,
            reason='no_calibrated_bound' if limit is None else None if coverage else 'insufficient_source_genre_coverage'))
    return out


def _software():
    import cv2
    from video_ai.runtime.paths import SOURCE_ROOT
    paths=[Path(__file__).resolve(),Path(sys.executable).resolve(),Path(np.__file__).resolve(),Path(cv2.__file__).resolve()]
    paths+=list(Path(np.__file__).parent.rglob('*.pyd'))+list(Path(cv2.__file__).parent.glob('*.pyd'))
    paths+=[SOURCE_ROOT/'src/video_ai'/p for p in ('media/colorimetry.py','media/_continuity_controls.py',
        'media/_continuity_schema.py','media/_continuity_geometry.py','runtime/manifest.py','runtime/paths.py',
        'adapters/common.py','experiments/whole_scene_case.py')]
    return [identity(p) for p in sorted(set(paths))]


def validate_root(root,index_path=INPUT):
    from video_ai.runtime.paths import PROJECT_ROOT,CACHE_ROOT
    root=Path(root).resolve();source=Path(index_path).resolve()
    if not any(root.is_relative_to(p) for p in (PROJECT_ROOT/'continuity-benchmark',CACHE_ROOT)):
        raise ValueError('dedicated local experiment output root required')
    if root.is_relative_to(source.parent) or source.is_relative_to(root):
        raise ValueError('experiment overlaps original source tree')
    return root


def prepare(root,*,index_path=INPUT):
    root=validate_root(root,index_path)
    # Project experiment directories are intentionally outside production runs.
    index=read_json(index_path);entries=index['sources']
    if len(entries)!=24:raise ValueError('original 24-source index required')
    ids=[e['source']['source_id'] for e in entries];groups=[e['source']['scene_group'] for e in entries]
    if len(set(ids))!=24 or len(set(groups))!=24:raise ValueError('unique source/group split required')
    for split in ('calibration','holdout'):
        selected=[e for e in entries if e['split']==split]
        if len(selected)!=12 or any(sum(e['source']['genre']==g for e in selected)!=2 for g in GENRES):
            raise ValueError('preserved 12/12 and six-genre split required')
    if not index_path.resolve().is_relative_to(Path('D:/VideoSi')):raise ValueError('source index must be local D:/VideoSi')
    root.mkdir(parents=True,exist_ok=False)
    write_json(root/'protocol.FROZEN.json',dict(PROTOCOL,created_at=now(),
        operator_details='sRGB transfer; linear x*2**(a*d) or Y+2**a*(x-Y); clip then np.rint to uint8',
        residual_rules='per-frame p99<=2, every channel maximum<=4; new interior clipping cannot increase',
        sampling='visible ROI only; 1024 per role; every native frame; oracle correspondence and family/axis',
        qualification='all baseline-eligible sources; minimum six sources/groups and six genres for each split',
        time_limit_seconds_per_source=265))
    software=_software()
    write_json(root/'inputs.FROZEN.json',dict(created_at=now(),authorization='同意，按这条路线走',
        index=identity(index_path),protocol=identity(root/'protocol.FROZEN.json'),software=software,
        versions=dict(python=sys.version,numpy=np.__version__,opencv=importlib.metadata.version('opencv-python-headless')),
        sources=entries,source_count=24,requested_controls_per_source=74,production_eligible=False,
        limitations=['Old AI split, not a fresh blind test','Known correspondence AND known operator family/axis',
                     'Sampled pixels, not full-resolution output qualification','Constant parameter only']))
    write_json(root/'inputs-identity.json',identity(root/'inputs.FROZEN.json'))
    write_bytes(root/'software/calibrator.py',Path(__file__).read_bytes())
    return dict(status='prepared',sources=24,controls=1776,production_eligible=False)


def _deadline(deadline):
    if deadline is not None and time.monotonic()>deadline:raise TimeoutError('source command deadline')


def phase_guard(root,split,deadline=None):
    root=Path(root).resolve(strict=True)
    try:verify_identity(read_json(root/'inputs-identity.json'))
    except (OSError,ValueError) as exc:raise ValueError('frozen input identity changed') from exc
    inputs=read_json(root/'inputs.FROZEN.json');_deadline(deadline)
    for item in [inputs['index'],inputs['protocol'],*inputs['software']]:
        _deadline(deadline)
        try:verify_identity(item)
        except (OSError,ValueError) as exc:raise ValueError('frozen identity changed: '+item['path']) from exc
        _deadline(deadline)
    if inputs['sources']!=read_json(inputs['index']['path'])['sources']:raise ValueError('copied source index changed')
    if split=='holdout':
        if not (root/'threshold-seal-identity.json').exists():raise ValueError('holdout requires frozen seal')
        verify_identity(read_json(root/'threshold-seal-identity.json'))
        try:verify_identity(read_json(root/'thresholds.SEALED.json')['inputs'])
        except (OSError,ValueError) as exc:raise ValueError('sealed input identity changed') from exc
    elif split=='calibration':
        if (root/'thresholds.SEALED.json').exists():raise ValueError('calibration closed by seal')
    else:raise ValueError('known phase required')
    return inputs


def pixel_budget(frames,width,height):
    if any(type(v) is not int or v<=0 for v in (frames,width,height)):raise ValueError('positive pixel dimensions required')
    raw=width*height*3;packed=frames*2048*(3+1+8)
    # Original RGB, a conservative three-channel mask-decode reserve, raw
    # decode temporaries, sample packs, and bounded numerical fit workspace.
    peak=3*raw+packed+16777216
    if raw>33554432 or peak>PROTOCOL['pixel_working_budget_bytes']:
        raise ValueError('resource_limit: pixel allocation budget')
    return peak


def _sample_frame(image,regions,roles,reader):
    import cv2
    h,w=image.shape[:2];selected=[];details=[]
    for role in ('subject','background'):
        points=[]
        for region in regions.values():
            if roles[region['region_id']]!=role or region['visibility']!='visible':continue
            x0,y0,x1,y1=region['box'];x0=max(0,math.floor(x0*w));x1=min(w,math.ceil(x1*w))
            y0=max(0,math.floor(y0*h));y1=min(h,math.ceil(y1*h))
            if x1<=x0 or y1<=y0:continue
            xx=np.linspace(x0,x1-1,min(32,x1-x0),dtype=int);yy=np.linspace(y0,y1-1,min(32,y1-y0),dtype=int)
            y,x=np.meshgrid(yy,xx,indexing='ij');p=np.column_stack((x.ravel(),y.ravel()))
            if region['mask'] is not None:
                reader.check(region['mask']);raw=Path(region['mask']['path']).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=region['mask']['sha256']:raise ValueError('ROI mask changed while reading')
                if (raw[:8]!=b'\x89PNG\r\n\x1a\n' or len(raw)<24
                        or (int.from_bytes(raw[16:20],'big'),int.from_bytes(raw[20:24],'big'))!=(w,h)):
                    raise ValueError('bounded native PNG mask required before decoding')
                mask=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_GRAYSCALE)
                if mask is None or mask.shape!=(h,w):raise ValueError('ROI mask dimensions differ')
                p=p[mask[p[:,1],p[:,0]]>0]
            details.append(dict(region_id=region['region_id'],role=role,points_before_role_cap=len(p)))
            points.extend(p.tolist())
        if points:
            points=np.unique(np.asarray(points,dtype=int),axis=0)
            if len(points)>1024:points=points[np.linspace(0,len(points)-1,1024,dtype=int)]
            selected.extend(points.tolist())
    points=np.unique(np.asarray(selected,dtype=int).reshape(-1,2),axis=0)
    return image[points[:,1],points[:,0]],points,details


def reader_identity(stamp):
    """Adapt ColorAnalysisReader's five-field identity to experiment identity."""
    return {k:stamp[k] for k in ('path','bytes','sha256','mtime_ns')}


def pack_source(root,entry,deadline):
    from video_ai.media.colorimetry import ColorAnalysisReader
    from video_ai.media._continuity_controls import _truth
    from video_ai.media._continuity_schema import validate_regions
    source=entry['source'];sid=source['source_id']
    cfg=SimpleNamespace(tools={'ffmpeg':Path('D:/VideoSi/tools/ffmpeg/bin/ffmpeg.exe'),
                               'ffprobe':Path('D:/VideoSi/tools/ffmpeg/bin/ffprobe.exe')})
    for stamp in source['frame_records']:
        # Verify original declared frame identities before opening the evidence window.
        current=identity(stamp['path'])
        if any(current[k]!=stamp[k] for k in ('path','bytes','mtime_ns','sha256')):raise ValueError('source frame identity changed')
    with ColorAnalysisReader([p['path'] for p in source['frame_records']],config=cfg,
                             timeout=max(.001,deadline-time.monotonic())) as reader:
        reader.check(source['media']);reader.check(source['regions']);reader.check(source['truth'])
        frames=reader.frames;entries={r['record_identity']['path']:r for r in frames}
        bypath={p:dict(frame_id=f'frame_{i}',record=r['record_identity']) for i,(p,r) in enumerate(entries.items())}
        region_doc=read_json(source['regions']['path']);declared=validate_regions(region_doc,bypath)
        roles={r['region_id']:r['role'] for r in declared}
        truth=_truth(source,read_json(source['truth']['path']),reader,entries,set(roles))
        n=len(frames);sidecars=reader.sidecars
        peak=max(pixel_budget(n,s['probe']['video']['width'],s['probe']['video']['height']) for s in sidecars.values())
        rgb=np.zeros((n,2048,3),np.uint8);valid=np.zeros((n,2048),bool);coordinates=np.full((n,2048,2),-1,np.int32)
        timeline=[];counts=[];first_index=None;previous=None;informative=0
        for i,row in enumerate(frames):
            if time.monotonic()>deadline:raise TimeoutError('source packing deadline')
            rec=row['record'];video=sidecars[rec['sidecar']['path']]['probe']['video']
            if rec['status']!='ready' or rec['analysis_space']!='srgb_rgb24_v1':raise ValueError('resolved sRGB native frame required')
            index=rec['frame_index'];first_index=index if first_index is None else first_index
            if index!=first_index+i or rec['time_base']!=source['interval']['time_base']:raise ValueError('complete native frame sequence required')
            stamp=Fraction(rec['pts'])*Fraction(rec['time_base'])
            if previous is not None and stamp<=previous:raise ValueError('native PTS must increase')
            previous=stamp
            raw=reader.read_rgb(row['record_identity']['path']);image=np.frombuffer(raw,np.uint8).reshape(video['height'],video['width'],3)
            values,points,details=_sample_frame(image,truth[row['record_identity']['path']],roles,reader)
            k=len(values);rgb[i,:k]=values;valid[i,:k]=True;coordinates[i,:k]=points
            informative+=int(((values>=2)&(values<=253)).all(axis=1).sum())
            timeline.append(dict(frame_index=index,pts=rec['pts'],time_base=rec['time_base']))
            counts.append(dict(points=k,regions=details));del image,raw
        if timeline[0]['pts']!=source['interval']['start_pts']:raise ValueError('native interval start differs')
        last=frames[-1]['record'];video=sidecars[last['sidecar']['path']]['probe']['video'];native=video['frames']
        j=last['frame_index']
        if j+1<len(native):end=native[j+1].get('pts',native[j+1].get('best_effort_timestamp'))
        else:
            duration=native[j].get('duration',native[j].get('pkt_duration'))
            if not isinstance(duration,int) or duration<=0:raise ValueError('native end duration missing')
            end=last['pts']+duration
        if end!=source['interval']['end_pts']:raise ValueError('native interval end differs')
        reader.verify()
        identities=[reader_identity(stamp) for stamp in reader.identities]
    folder=Path(root)/'source-packs';folder.mkdir(exist_ok=True)
    path=folder/(sid+'.npz')
    with path.open('xb') as stream:np.savez_compressed(stream,rgb=rgb,valid=valid,coordinates=coordinates)
    meta=dict(source_id=sid,scene_group=source['scene_group'],genre=source['genre'],split=entry['split'],
        eligible=bool(min(c['points'] for c in counts)>=81 and informative>=81),
        eligibility_reason='all frames >=81 pairs and >=81 informative fitting pairs' if min(c['points'] for c in counts)>=81 and informative>=81 else 'insufficient_visible_informative_support',
        frames=n,timeline=timeline,interval=source['interval'],counts=counts,informative_pairs=informative,
        sampling='oracle paired coordinates; visible ROI; at most 1024 pixels per role',
        ROI_origin=entry.get('ROI_origin'),ROI_uncertainties=entry.get('ROI_uncertainties'),
        source_identities=identities,pack=identity(path),pixel_allocation_bound=peak)
    write_json(folder/(sid+'.json'),meta)
    return rgb,valid,meta


def _cases():
    for op in OPERATIONS:
        for sign in (-1,1):
            for level in LEVELS:
                yield dict(case_id=f'{op}_{"neg" if sign<0 else "pos"}_{level:g}',operation=op,
                           injection_direction=sign,level=level,context=dict(comparable=True,intentional_lighting_change=False,confirmed_motion_defect=False))
    for key in ('identity','allowed_lighting','not_comparable','motion_defect'):
        ctx=dict(comparable=True,intentional_lighting_change=False,confirmed_motion_defect=False)
        if key=='allowed_lighting':ctx['intentional_lighting_change']=True
        if key=='not_comparable':ctx['comparable']=False
        if key=='motion_defect':ctx['confirmed_motion_defect']=True
        yield dict(case_id=key,operation='identity' if key=='identity' else 'context_gate',
                   injection_direction=0,level=0.,context=ctx)


def measure_source(root,source_id):
    start=time.monotonic();deadline=start+265
    root=Path(root).resolve(strict=True);inputs=read_json(root/'inputs.FROZEN.json')
    entry=next(e for e in inputs['sources'] if e['source']['source_id']==source_id)
    phase_guard(root,entry['split'],deadline=deadline);target=root/'source-results'/(source_id+'.json')
    if target.exists():
        verify_identity(read_json(target.with_suffix('.identity.json')))
        old=read_json(target)
        return dict(status='retained' if old['status']=='completed' and old.get('closure_verified') else 'failed',
                    source_id=source_id,result=identity(target),reason='original result retained; no remeasurement')
    rows=[];meta=None;closure_verified=False
    try:
        rgb,valid,meta=pack_source(root,entry,deadline)
        fit_ref=rgb[valid]
        for case in _cases():
            if time.monotonic()>deadline:raise TimeoutError('source control deadline')
            base=dict(source_id=source_id,split=entry['split'],case_id=case['case_id'],operation=case['operation'],
                      injection_direction=case['injection_direction'],level=case['level'],estimated_amplitude=None,
                      conditional_operator_and_correspondence=True)
            if not meta['eligible']:
                rows.append(dict(base,passed=False,status='abstained',reason=meta['eligibility_reason'],frames=[]));continue
            if case['operation']=='context_gate':
                changed=transform(fit_ref,'exposure',.125)
                fit=estimate(fit_ref,changed,'exposure',case['context'])
                rows.append(dict(base,passed=fit['status']=='abstained',status='context_rejected',fit=fit,frames=[],
                    negative_construction='exposure +0.125 with explicit author context; tests gate, not semantic detector'));continue
            op='exposure' if case['operation']=='identity' else case['operation']
            a=case['injection_direction']*case['level'];current=np.empty_like(rgb)
            for i in range(len(rgb)):current[i]=transform(rgb[i],op,a)
            fit=estimate(fit_ref,current[valid],op,case['context'])
            base['estimated_amplitude']=fit['amplitude']
            if fit['status']=='abstained':
                rows.append(dict(base,passed=False,status='abstained',reason=fit['reason'],fit=fit,frames=[]));continue
            scores=[]
            for i in range(len(rgb)):
                if time.monotonic()>deadline:raise TimeoutError('source scoring deadline')
                ref=rgb[i,valid[i]];cur=current[i,valid[i]];out=transform(cur,op,fit['amplitude'])
                scores.append(dict(meta['timeline'][i],**score(ref,cur,out)))
            accepted=all(s['passed'] for s in scores)
            if case['operation']=='identity':accepted=accepted and fit['status']=='noop'
            rows.append(dict(base,passed=bool(accepted),status='measured',fit=fit,frames=scores,
                parameter_temporal_variation=0.,
                temporal_mean_error_differences=[float(np.linalg.norm(np.subtract(b['mean_signed_error'],a['mean_signed_error']))) for a,b in zip(scores,scores[1:])]))
        for stamp in [*meta['source_identities'],meta['pack']]:
            _deadline(deadline);verify_identity(stamp);_deadline(deadline)
        closure_verified=True
        result=dict(status='completed',closure_verified=True,source=meta,rows=rows,elapsed_seconds=time.monotonic()-start,finished_at=now())
    except Exception as exc:
        import traceback
        source=entry['source']
        meta=meta or dict(source_id=source_id,scene_group=source['scene_group'],genre=source['genre'],split=entry['split'],
                          eligible=False,eligibility_reason='input_or_resource_failure_before_baseline')
        result=dict(status='failed',closure_verified=closure_verified,source=meta,rows=rows,error=str(exc),traceback=traceback.format_exc(),
                    elapsed_seconds=time.monotonic()-start,finished_at=now())
    write_json(target,result)
    write_json(target.with_suffix('.identity.json'),identity(target))
    return dict(source_id=source_id,status=result['status'],eligible=meta['eligible'],
                rows=len(rows),passed=sum(r['passed'] for r in rows),elapsed_seconds=result['elapsed_seconds'],error=result.get('error'))


def _collect(root,split):
    inputs=read_json(Path(root)/'inputs.FROZEN.json');sources=[];rows=[];artifacts=[]
    for entry in inputs['sources']:
        if entry['split']!=split:continue
        p=Path(root)/'source-results'/(entry['source']['source_id']+'.json')
        if not p.exists():raise ValueError('missing source result: '+str(p))
        data=read_json(p)
        if data['status']!='completed' or data.get('closure_verified') is not True:
            raise ValueError('source closure failed; sealing/qualification refused: '+str(p))
        verify_identity(read_json(p.with_suffix('.identity.json')))
        expected=dict(source_id=entry['source']['source_id'],scene_group=entry['source']['scene_group'],
                      genre=entry['source']['genre'],split=entry['split'])
        if any(data['source'][k]!=v for k,v in expected.items()):raise ValueError('source result differs from frozen index')
        for stamp in [*data['source']['source_identities'],data['source']['pack']]:verify_identity(stamp)
        declared={c['case_id']:c for c in _cases()}
        if len(data['rows'])!=74 or {r['case_id'] for r in data['rows']}!=set(declared):raise ValueError('complete fixed control coverage required')
        for row in data['rows']:
            c=declared[row['case_id']]
            if row['source_id']!=expected['source_id'] or row['split']!=split or any(row[k]!=c[k] for k in ('operation','injection_direction','level')):
                raise ValueError('control result provenance differs')
        sources.append({k:data['source'][k] for k in ('source_id','scene_group','genre','split','eligible')})
        rows.extend({k:r[k] for k in ('source_id','split','operation','injection_direction','level','passed','estimated_amplitude')} for r in data['rows'])
        artifacts.append(read_json(p.with_suffix('.identity.json')))
    return sources,rows,artifacts


def seal(root):
    root=Path(root);phase_guard(root,'calibration');sources,rows,artifacts=_collect(root,'calibration')
    value=dict(schema_version=1,algorithm=ALGORITHM,created_at=now(),purpose='offline_AI_repair_calibration',
        production_eligible=False,inputs=identity(root/'inputs.FROZEN.json'),
        calibration_results=artifacts,bounds=fit_bounds(rows,sources),sources=sources)
    phase_guard(root,'calibration')
    for item in artifacts:verify_identity(item)
    write_json(root/'thresholds.SEALED.json',value)
    write_json(root/'threshold-seal-identity.json',identity(root/'thresholds.SEALED.json'))
    return dict(status='sealed',bounds=value['bounds'])


def finalize(root):
    root=Path(root);phase_guard(root,'holdout');sealed=read_json(root/'thresholds.SEALED.json')
    for item in sealed['calibration_results']:verify_identity(item)
    sources,rows,artifacts=_collect(root,'holdout');checked=evaluate(rows,sources,sealed['bounds'])
    gate_counts={}
    for entry in read_json(root/'inputs.FROZEN.json')['sources']:
        data=read_json(root/'source-results'/(entry['source']['source_id']+'.json'))
        for row in data['rows']:
            if row['operation']=='context_gate':
                key=row['case_id'];counts=gate_counts.setdefault(key,dict(requested=24,refused=0,not_exercised=0))
                counts['refused']+=int(row['status']=='context_rejected' and row['passed'])
                counts['not_exercised']+=int(row['status']!='context_rejected')
    value=dict(schema_version=1,algorithm=ALGORITHM,created_at=now(),purpose='offline_AI_repair_calibration',
        production_eligible=False,inputs=identity(root/'inputs.FROZEN.json'),thresholds=identity(root/'thresholds.SEALED.json'),
        holdout_results=artifacts,checks=checked,context_gates=gate_counts,
        requested_sources=24,requested_controls=1776,source_groups_not_certified_independent=True,
        limitations=read_json(root/'inputs.FROZEN.json')['limitations'],
        qualified_directions=[dict(operation=c['operation'],injection_direction=c['injection_direction']) for c in checked if c['qualified']],
        temporal_policy=PROTOCOL['temporal_policy'],unsupported=['time-varying drift','local correction','unknown lighting intent',
            'unmatched pixels','automatic model/axis selection','combined parameter axes','arbitrary hue rotation'])
    phase_guard(root,'holdout')
    for item in [*sealed['calibration_results'],*artifacts]:verify_identity(item)
    write_json(root/'evaluation.json',value)
    write_json(root/'experimental-repair-profile.json',dict(value,evaluation=identity(root/'evaluation.json'),
        calibrated_bounds=sealed['bounds'],evidence_only=True))
    return dict(status='completed',qualified_directions=value['qualified_directions'],production_eligible=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('prepare','measure','seal','finalize'))
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--source-id');args=parser.parse_args()
    if args.command=='prepare':value=prepare(args.root)
    elif args.command=='measure':value=measure_source(args.root,args.source_id)
    elif args.command=='seal':value=seal(args.root)
    else:value=finalize(args.root)
    print(json.dumps(value,ensure_ascii=False))
    return 2 if value.get('status')=='failed' else 0


if __name__=='__main__':raise SystemExit(main())
