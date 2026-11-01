"""Offline, read-only continuity measurements; never production acceptance."""
from copy import deepcopy
from fractions import Fraction
import json
import math
from time import monotonic

from ._continuity_schema import (ALGORITHM, PARAMETERS, DETECTORS, GENRES, KINDS,
    validate_continuity_manifest, validate_regions, validate_context, stable, identity, domain, array, identifier, rect, timebase)
from ._continuity_geometry import (numerical, CV_LOCK, lab_luma as _lab_luma, color_metrics as _color_metrics,
    frame_arrays, register, empty_region, affine_fit, apply_affine, transform_box, camera_parts,FeatureCache)
from ._continuity_scores import scores, seconds
from .colorimetry import _object, _int
from ..planning.production_scenes import canonical_digest


def _check_deadline(deadline):
    if deadline is not None and monotonic()>=deadline:raise TimeoutError('continuity budget expired')


def _validate_plan(plan):
    _object(plan,'schema_version algorithm purpose domain frames clips references regions comparisons context provenance'.split(),'ResolvedPlan')
    if type(plan['schema_version']) is not int or plan['schema_version']!=1 or plan['algorithm']!=ALGORITHM:raise ValueError('invalid plan version')
    if plan['purpose'] not in ('ordinary','benchmark_control'):raise ValueError('invalid plan purpose')
    domain(plan['domain']);frames=array(plan['frames'],nonempty=True)
    if len(frames)>4096 or len(plan['comparisons'])>65536:raise ValueError('resource_limit: plan')
    ids=set()
    for f in frames:
        _object(f,'frame_id source_record source_clip_id source_frame_index source_pts source_time_base display_pts display_time_base output_frame_index'.split(),'resolved frame')
        identifier(f['frame_id']);identity(f['source_record']);_int(f['source_frame_index'],'source frame')
        if f['frame_id'] in ids:raise ValueError('duplicate resolved frame')
        ids.add(f['frame_id'])
        for p,t in (('source_pts','source_time_base'),('display_pts','display_time_base')):
            if (f[p] is None)!=(f[t] is None):raise ValueError('time coordinate incomplete')
            if f[p] is not None:_int(f[p],p,-(2**63));timebase(f[t])
        if f['output_frame_index'] is not None:_int(f['output_frame_index'],'output frame')
    regionids=set()
    for r in array(plan['regions'],nonempty=True):
        _object(r,'region_id role identity_note anchors'.split(),'resolved region');identifier(r['region_id'])
        if r['region_id'] in regionids or r['role'] not in ('subject','background'):raise ValueError('invalid resolved region')
        regionids.add(r['region_id'])
        for a in r['anchors']:
            _object(a,('frame_id','rect'),'resolved anchor');rect(a['rect'])
            if a['frame_id'] not in ids:raise ValueError('unknown anchor')
    seen=set()
    for c in plan['comparisons']:
        _object(c,'comparison_id kind left right region_ids'.split(),'resolved comparison');identifier(c['comparison_id'])
        if c['comparison_id'] in seen or c['kind'] not in KINDS or c['left'] not in ids or c['right'] not in ids:raise ValueError('invalid resolved comparison')
        seen.add(c['comparison_id'])
        if any(r not in regionids for r in c['region_ids']):raise ValueError('unknown comparison region')
    _object(plan['provenance'],'kind input_sha256 source_files control_case'.split(),'provenance')
    if plan['provenance']['kind'] != ('verified_source' if plan['purpose']=='ordinary' else 'benchmark_control'):
        raise ValueError('control provenance differs')
    return plan


def _sample(frame,box,confidence=0.):
    center=[(box[0]+box[2])/2,(box[1]+box[3])/2] if box else None
    return dict(frame_id=frame['frame_id'],timestamp=dict(pts=frame['display_pts'],time_base=frame['display_time_base']),
        center=center,box=box,image_plane_velocity=None,camera_compensated_velocity=None,flow_direction=None,
        direction_delta=None,camera_translation=None,camera_rotation=None,camera_log_scale=None,
        edge_margin=min(box[0],box[1],1-box[2],1-box[3]) if box else None,
        status='anchored' if box else 'tracking_lost',confidence=float(confidence))


def measure_continuity(plan, frame_provider, *, deadline=None):
    """Compute raw measures only. This result has no persisted audit authority."""
    _check_deadline(deadline);_validate_plan(plan);np,cv=numerical()
    with CV_LOCK:
        threads=cv.getNumThreads();cv.setNumThreads(1)
        try:
            return _measure(plan,frame_provider,deadline)
        except cv.error as exc:
            raise RuntimeError(f'OpenCV continuity operation failed: {exc}') from exc
        finally:cv.setNumThreads(threads)


def _measure(plan,provider,deadline):
    np,cv=numerical();frames={f['frame_id']:f for f in plan['frames']};regions={r['region_id']:r for r in plan['regions']}
    boxes={r['region_id']:{a['frame_id']:list(a['rect']) for a in r['anchors']} for r in plan['regions']}
    trajectories={r['region_id']:{} for r in plan['regions']}
    results={};ready=set();cache=FeatureCache();metadata_bytes=0
    # Tracking precedes fixed-reference comparisons; output retains caller order.
    ordered=sorted(enumerate(plan['comparisons']),key=lambda p:(p[1]['kind']=='reference',p[0]))
    for _,pair in ordered:
        _check_deadline(deadline);left_id,right_id=pair['left'],pair['right'];raw={}
        try:
            for f in dict.fromkeys((left_id,right_id)):
                raw[f]=frame_arrays(provider.get(f));_check_deadline(deadline)
                if raw[f] is not None:ready.add(f)
            rs=[];newboxes={};pair_bytes=0
            for rid in pair['region_ids']:
                _check_deadline(deadline);box=boxes[rid].get(left_id);rbox=boxes[rid].get(right_id)
                if raw[left_id] is None or raw[right_id] is None:
                    r=empty_region(rid,'unknown_color','unverified')
                elif box is None:
                    r=empty_region(rid,'identity_unverified','unverified')
                elif plan['purpose']=='ordinary' and pair['kind']!='same_frame' and (
                    frames[left_id]['source_clip_id'] is None or frames[right_id]['source_clip_id'] is None or
                    seconds(frames[left_id]) is None or seconds(frames[right_id]) is None or
                    (pair['kind']=='parent_join' and (frames[left_id]['output_frame_index'] is None or frames[right_id]['output_frame_index'] is None or
                     frames[right_id]['output_frame_index']!=frames[left_id]['output_frame_index']+1))):
                    r=empty_region(rid,'unverified_mapping','unverified')
                else:
                    same=(pair['kind']=='same_frame' and frames[left_id]['source_record']['sha256']==frames[right_id]['source_record']['sha256'] and
                          frames[left_id]['source_frame_index']==frames[right_id]['source_frame_index'])
                    r,newbox=register(raw[left_id],raw[right_id],box,rbox,rid,same_source=same,cache=cache,cache_keys=(left_id,right_id),
                        metadata_budget=67108864-metadata_bytes-pair_bytes,deadline=deadline)
                    if newbox is not None:newboxes[rid]=newbox
                pair_bytes+=len(json.dumps(r,allow_nan=False,separators=(',',':')).encode())
                if metadata_bytes+pair_bytes>67108864:raise ValueError('resource_limit: region metadata')
                rs.append(r)
            background=[];worksize=None
            for r in rs:
                if regions[r['region_id']]['role']=='background' and r['comparability']=='comparable':
                    background.extend(r['geometry']['vectors']);worksize=r['geometry']['working_size']
            camera=None
            if background:
                from ._continuity_geometry import _grid
                l=np.array([v['left'] for v in background]);rr=np.array([v['right'] for v in background])
                fit=affine_fit(l,rr,worksize)
                if fit is not None and _grid(l,[0,0,1,1])>=4 and np.count_nonzero(fit[1]<=2)>=12:camera=fit[0]
            if camera is not None:
                for r in rs:
                    for v in r['geometry']['vectors']:
                        v['residual']=(np.array(v['right'])-apply_affine([v['left']],camera)[0]).tolist()
            if pair['kind'] in ('adjacent','parent_join'):
                for r in rs:
                    rid=r['region_id'];lt,rt=seconds(frames[left_id]),seconds(frames[right_id]);box=boxes[rid].get(left_id)
                    trajectories[rid].setdefault(left_id,_sample(frames[left_id],box,1. if box else 0.))
                    if r['comparability']=='comparable':boxes[rid].setdefault(right_id,newboxes.get(rid))
                    rightbox=boxes[rid].get(right_id) if r['comparability']=='comparable' else None
                    sample=_sample(frames[right_id],rightbox,r['confidence'])
                    if rightbox is not None and box is not None and lt is not None and rt is not None and rt>lt:
                        dt=float(rt-lt);lc=np.array([(box[0]+box[2])/2,(box[1]+box[3])/2])
                        # Clip-start anchors relocate the sampling/tracking box;
                        # motion must come from this pair's pixel correspondence.
                        rc=apply_affine([lc],np.array(r['geometry']['affine']))[0]
                        velocity=(rc-lc)/dt;sample['image_plane_velocity']=velocity.tolist();sample['status']='tracked'
                        if camera is not None:
                            prediction=apply_affine([lc],camera)[0]-lc
                            sample['camera_compensated_velocity']=((rc-lc-prediction)/dt).tolist()
                            trans,rot,scale=camera_parts(camera)
                            sample.update(camera_translation=trans,camera_rotation=rot,camera_log_scale=scale,
                                _camera_velocity=[trans[0]/dt,trans[1]/dt,rot/dt,scale/dt])
                        speed=sample['camera_compensated_velocity']
                        if speed is not None and math.hypot(*speed)>1e-12:
                            sample['flow_direction']=math.atan2(speed[1],speed[0])
                            previous=trajectories[rid][left_id]['flow_direction']
                            if previous is not None:sample['direction_delta']=(sample['flow_direction']-previous+math.pi)%(2*math.pi)-math.pi
                    trajectories[rid][right_id]=sample
            pair_result=dict(comparison_id=pair['comparison_id'],kind=pair['kind'],left=left_id,right=right_id,regions=rs)
            metadata_bytes+=len(json.dumps(pair_result,allow_nan=False,separators=(',',':')).encode())
            if metadata_bytes>67108864:raise ValueError('resource_limit: result metadata')
            results[pair['comparison_id']]=pair_result
        finally:
            raw.clear()
            for f in dict.fromkeys((left_id,right_id)):provider.release(f)
    comparisons=[results[p['comparison_id']] for p in plan['comparisons']]
    trajectory_list=[dict(region_id=rid,samples=sorted(samples.values(),key=lambda s: seconds(frames[s['frame_id']]) or Fraction(0))) for rid,samples in trajectories.items()]
    detectors=scores(plan,comparisons,trajectory_list,deadline=deadline)
    for t in trajectory_list:
        for s in t['samples']:s.pop('_camera_velocity',None)
    fr=[]
    for f in plan['frames']:
        fr.append(dict(frame_id=f['frame_id'],record=f['source_record'],source=None,source_frame_index=f['source_frame_index'],
            pts=f['source_pts'],time_base=f['source_time_base'],output_frame_index=f['output_frame_index'],
            timeline_seconds=float(seconds(f)) if f['output_frame_index'] is not None and seconds(f) is not None else None,
            status='ready' if f['frame_id'] in ready else 'unverified',risks=[]))
    counts={s:0 for s in ('comparable','not_comparable','unverified')}
    for p in comparisons:
        statuses=[r['comparability'] for r in p['regions']]
        status='comparable' if 'comparable' in statuses else ('unverified' if 'unverified' in statuses else 'not_comparable')
        counts[status]+=1
    result=dict(frame_results=fr,comparisons=comparisons,trajectories=trajectory_list,detectors=detectors,
        coverage=dict(requested_frames=len(plan['frames']),ready_frames=len(ready),requested_pairs=len(comparisons),
            comparable_pairs=counts['comparable'],not_comparable_pairs=counts['not_comparable'],unverified_pairs=counts['unverified']))
    if len(json.dumps(result,allow_nan=False,separators=(',',':')).encode())>67108864:raise ValueError('resource_limit: result metadata')
    _check_deadline(deadline)
    return result


def _resolve_manifest(manifest,reader,window):
    entries={x['record_identity']['path']:x for x in reader.frames}
    sidecars=reader.sidecars
    input_frames=[f for c in manifest['clips'] for f in c['frames']]+manifest['references']
    bypath={f['record']['path']:f for f in input_frames}
    regions=validate_regions(window.read_json(manifest['regions']),bypath)
    frameids={f['frame_id'] for f in input_frames};regionids={r['region_id'] for r in regions}
    context=validate_context(window.read_json(manifest['context']) if manifest['context'] else None,frameids,regionids)
    if context:
        for e in context['events']:
            for ref in e['references']:window.check(ref)
    for r in regions:
        for a in r['anchors']:window.check(bypath[next(p for p,f in bypath.items() if f['frame_id']==a['frame_id'])]['record'])
    frames=[];records={};clipof={f['frame_id']:c['clip_id'] for c in manifest['clips'] for f in c['frames']}
    fps=Fraction(manifest['timeline']['fps_num'],manifest['timeline']['fps_den'])
    for f in input_frames:
        value=entries[f['record']['path']]
        if stable(value['record_identity'])!=stable(f['record']):raise OSError('manifest frame identity differs')
        record=value['record'];mapping=record['mapping'];records[f['frame_id']]=record
        verified=mapping is not None and not any(r['code']=='unverified_mapping' for r in record['risks'])
        clip=mapping['clip_id'] if verified else None
        if clip is not None and f['frame_id'] in clipof and clip!=clipof[f['frame_id']]:raise ValueError('frame does not belong to declared clip')
        output=mapping['output_frame_index'] if verified else None
        pts,tb=record['pts'],record['time_base']
        display_pts,display_tb=(output*fps.denominator,f'1/{fps.numerator}') if output is not None else (pts,tb)
        frames.append(dict(frame_id=f['frame_id'],source_record=f['record'],source_clip_id=clip,
            source_frame_index=record['frame_index'],source_pts=pts,source_time_base=tb,display_pts=display_pts,
            display_time_base=display_tb,output_frame_index=output))
        side=sidecars.get(record['sidecar']['path'],{})
        video=side.get('probe',{}).get('video',{})
        native=video.get('frames',[])
        if output is not None and video.get('time_base') is not None and len(native)>1:
            ticks=[row.get('pts',row.get('best_effort_timestamp')) for row in native]
            if any(type(t) is not int for t in ticks):raise ValueError('unproved output time')
            if any(Fraction(b-a)*Fraction(video['time_base'])!=1/fps for a,b in zip(ticks,ticks[1:])):
                raise ValueError('manifest fps/time differs from original native mapping evidence')
    fm={f['frame_id']:f for f in frames}
    clips=[dict(clip_id=c['clip_id'],frames=[f['frame_id'] for f in c['frames']]) for c in manifest['clips']]
    for c in clips:
        seq=[fm[i] for i in c['frames']]
        if any(b['source_frame_index']<=a['source_frame_index'] for a,b in zip(seq,seq[1:])):raise ValueError('clip frames must follow actual source order')
        for r in regions:
            anchors=[a for a in r['anchors'] if a['frame_id'] in c['frames']]
            if len(anchors)!=1 or anchors[0]['frame_id']!=c['frames'][0]:raise ValueError('each clip needs exactly one initial region anchor; future truth cannot be used')
        mapped=[f for f in seq if f['output_frame_index'] is not None and f['source_pts'] is not None]
        for a,b in zip(mapped,mapped[1:]):
            source_dt=Fraction(b['source_pts'])*Fraction(b['source_time_base'])-Fraction(a['source_pts'])*Fraction(a['source_time_base'])
            output_dt=Fraction(b['output_frame_index']-a['output_frame_index'])/fps
            if source_dt!=output_dt:raise ValueError('manifest fps/time differs from proved output mapping')
    for p in manifest['comparisons']:
        if any(r not in regionids for r in p['region_ids']):raise ValueError('unknown comparison region')
        l,r=fm[p['left']],fm[p['right']];lr,rr=records[p['left']],records[p['right']]
        if p['kind']=='same_frame':
            same=(lr['source']['sha256']==rr['source']['sha256'] and lr['frame_index']==rr['frame_index'])
            lm,rm=lr['mapping'],rr['mapping']
            same |= bool(lm and rm and l['source_clip_id'] is not None and r['source_clip_id'] is not None and
                lm['clip_id']==rm['clip_id'] and lm['generated_frame_index'] is not None and lm['generated_frame_index']==rm['generated_frame_index'])
            if not same:raise ValueError('same_frame lacks original content proof')
        elif p['kind']=='adjacent':
            if clipof.get(p['left'])!=clipof.get(p['right']) or r['source_frame_index']!=l['source_frame_index']+1:
                raise ValueError('adjacent requires consecutive actual frames in one clip')
            if l['source_pts'] is not None and r['source_pts'] is not None and Fraction(r['source_pts'])*Fraction(r['source_time_base'])<=Fraction(l['source_pts'])*Fraction(l['source_time_base']):
                raise ValueError('adjacent PTS must increase')
        elif p['kind']=='parent_join':
            leftclip=next((i for i,c in enumerate(clips) if p['left'] in c['frames']),None)
            rightclip=next((i for i,c in enumerate(clips) if p['right'] in c['frames']),None)
            if leftclip is None or rightclip!=leftclip+1 or clips[leftclip]['frames'][-1]!=p['left'] or clips[rightclip]['frames'][0]!=p['right']:
                raise ValueError('parent_join requires adjacent clip retained endpoints')
            if l['output_frame_index'] is not None and r['output_frame_index'] is not None and r['output_frame_index']!=l['output_frame_index']+1:
                raise ValueError('parent_join output indices are not adjacent')
            for f,rec,last in ((l,lr,True),(r,rr,False)):
                side=sidecars[rec['sidecar']['path']]
                kept=[row for row in side['mapping']['rows'] if row['retained_frame_index'] is not None]
                if not kept:
                    f['source_clip_id']=None
                if kept and rec['frame_index'] != (max if last else min)(row['asset_frame_index'] for row in kept):
                    raise ValueError('parent_join may not use discarded or interior frames')
        elif p['kind']=='reference' and p['left'] not in {f['frame_id'] for f in manifest['references']}:
            raise ValueError('reference comparison requires a declared fixed reference')
    return dict(schema_version=1,algorithm=ALGORITHM,purpose='ordinary',domain=manifest['domain'],frames=frames,clips=clips,
        references=[f['frame_id'] for f in manifest['references']],regions=regions,comparisons=manifest['comparisons'],context=context,
        provenance=dict(kind='verified_source',input_sha256=canonical_digest(stable(manifest)),source_files=reader.identities,control_case=None)),records


class _ReaderProvider:
    def __init__(self,plan,records,reader):
        self.reader=reader;self.frames={f['frame_id']:f for f in plan['frames']};self.records=records
        self.sides=reader.sidecars
    def get(self,frame_id):
        frame=self.frames[frame_id];record=self.records[frame_id]
        raw=self.reader.read_rgb(frame['source_record']['path'])
        if raw is None:return None
        video=self.sides[record['sidecar']['path']]['probe']['video']
        return dict(width=video['width'],height=video['height'],rgb24=raw,valid_mask=None)
    def release(self,frame_id):pass


def _apply_profile(result,profile,manifest, *, dependency_fingerprint,source_fps=None):
    if profile['purpose']=='fixture_only':raise ValueError('fixture_only profile cannot produce ordinary decisions')
    from .continuity_calibration import _validate_profile
    _validate_profile(profile)
    matching=(profile['algorithm']==ALGORITHM and profile['parameters_sha256']==canonical_digest(PARAMETERS) and
              profile['dependency_fingerprint']==dependency_fingerprint)
    if not matching:raise OSError('profile_mismatch: algorithm/parameters/dependency fingerprint differs')
    applicability=profile['applicability'];d=manifest['domain']
    covered=(d['genre'] in applicability['genres'] and d['source_kind'] in applicability['source_kinds'] and
        bool(source_fps) and all(dict(num=fps.numerator,den=fps.denominator) in applicability['source_fps'] for fps in source_fps) and
        all(p['kind'] in applicability['comparison_kinds'] for p in manifest['comparisons']))
    detector_rows={d['detector_id']:d for d in profile['detectors']}
    for row in result['detectors']:
        info=detector_rows[row['detector_id']]
        if row['score'] is None or row['status']=='not_comparable':continue
        if not covered:row['reasons']=['out_of_calibration_scope']
        elif not info['enabled']:row['reasons']=['disabled_detector',info['reason']]
        else:
            row['threshold']=info['threshold'];row['status']='candidate' if row['score']>info['threshold'] else 'no_candidate';row['reasons']=[]
    return dict(identity=manifest['profile'],applicability=applicability,status=profile['status'],
        enabled_detectors=[d['detector_id'] for d in profile['detectors'] if d['enabled']],domain_match=covered,
        reasons=[] if covered else ['out_of_calibration_scope'])


def _native_source_fps(sidecars):
    rates=set();clip_rates={}
    for side in sidecars.values():
        video=side['probe']['video']
        if video['codec_name']=='png':continue
        ticks=[f.get('pts',f.get('best_effort_timestamp')) for f in video['frames']]
        if len(ticks)<2 or any(type(t) is not int for t in ticks):return None
        intervals={Fraction(b-a)*Fraction(video['time_base']) for a,b in zip(ticks,ticks[1:])}
        if not intervals or min(intervals)<=0:return None
        observed={1/d for d in intervals};rates.update(observed)
        if not any(r['code']=='unverified_mapping' for r in side['risks']):
            for row in side['mapping']['rows']:
                if row['clip_id'] is not None:clip_rates.setdefault(row['clip_id'],set()).update(observed)
    for side in sidecars.values():
        if side['probe']['video']['codec_name']!='png':continue
        rows=side['mapping']['rows']
        if any(r['code']=='unverified_mapping' for r in side['risks']) or not rows or any(row['clip_id'] not in clip_rates for row in rows):return None
    return rates or None


def _metric_digest(metrics):
    value=deepcopy({k:metrics[k] for k in ('frame_results','comparisons','trajectories','detectors')})
    for pair in value['comparisons']:
        for region in pair['regions']:region['evidence']=[]
    for detector in value['detectors']:detector['evidence']=[]
    return canonical_digest(stable(value))


def _save_measurement(result,plan,provider,window,input_sha256, *, prefix=''):
    from ._continuity_storage import storage_needed
    window.packed_geometry=storage_needed(result)
    np,cv=numerical()
    for pi,pair in enumerate(result['comparisons']):
        for side in ('left','right'):
            frame_id=pair[side]
            try:
                image=frame_arrays(provider.get(frame_id))
                if image is None:continue
                rgb,_=image;h,w=rgb.shape[:2];scale=min(1.,256/max(w,h))
                thumbnail=cv.resize(rgb,(round(w*scale),round(h*scale)),interpolation=cv.INTER_AREA)
                from ._continuity_audit import png_bytes
                for ri,r in enumerate(pair['regions']):
                    identity_=window.save_bytes(f'{prefix}evidence/{pi:06d}_{side}_{ri:04d}.png',png_bytes(thumbnail))
                    r['evidence'].append(identity_)
            finally:provider.release(frame_id)
        records={f['frame_id']:f['source_record'] for f in plan['frames']}
        for r in pair['regions']:r['evidence']=[records[pair['left']],records[pair['right']],*r['evidence']]
        window.save(f'{prefix}pairs/{pi:06d}.json',dict(schema_version=1,algorithm=ALGORITHM,input_sha256=input_sha256,comparison=pair))
    metrics=dict(schema_version=1,algorithm=ALGORITHM,input_sha256=input_sha256,
        **{k:result[k] for k in ('frame_results','comparisons','trajectories','detectors')})
    return window.save(prefix+'metrics.json',metrics),_metric_digest(metrics)


def analyze_continuity(manifest, *, config,paths,logger,timeout=300):
    from .colorimetry import load_color_analysis_set
    from .images import _deadline
    from ._continuity_audit import AuditWindow,dependencies
    from ..runtime.manifest import now
    data=validate_continuity_manifest(manifest);deadline=_deadline(timeout,monotonic());window=AuditWindow(paths,logger,deadline)
    inputs=[f['record']['path'] for c in data['clips'] for f in c['frames']]+[f['record']['path'] for f in data['references']]
    deps=dependencies(window)
    with load_color_analysis_set(inputs,config=config,timeout=max(.001,deadline-monotonic())) as reader:
        plan,records=_resolve_manifest(data,reader,window);provider=_ReaderProvider(plan,records,reader)
        result=measure_continuity(plan,provider,deadline=deadline)
        for f in result['frame_results']:
            f['source']=records[f['frame_id']]['source'];f['risks']=records[f['frame_id']]['risks']
        profile=None
        if data['profile'] is not None:
            profile_data=window.read_json(data['profile'])
            from .continuity_calibration import _verify_profile_evidence
            _verify_profile_evidence(profile_data,data['profile'],window)
            source_fps=_native_source_fps(reader.sidecars)
            profile=_apply_profile(result,profile_data,data,dependency_fingerprint=deps['fingerprint'],source_fps=source_fps)
        files={**{i['path']:i for i in reader.identities},**window.frozen}
        inputs=dict(manifest=data,files=[files[p] for p in sorted(files)])
        digest=canonical_digest(dict(inputs=stable(inputs),algorithm=ALGORITHM,parameters=PARAMETERS,dependencies=deps['fingerprint']))
        _save_measurement(result,plan,provider,window,digest)
        window.verify()
        # Reader exit verifies original media/tools/raw evidence before report.
    risks=[]
    for pair in result['comparisons']:
        for r in pair['regions']:
            for code in r['reasons']:risks.append(dict(code=code,detail=f'{pair["comparison_id"]}/{r["region_id"]}',frame_ids=[pair['left'],pair['right']]))
    if profile is None:risks.append(dict(code='missing_profile',detail='Raw measurement only; no calibrated decision',frame_ids=[]))
    report=dict(schema_version=1,algorithm=ALGORITHM,parameters=deepcopy(PARAMETERS),parameters_sha256=canonical_digest(PARAMETERS),
        input_sha256=digest,inputs=inputs,dependencies=deps,scope=data['scope'],scene_id=data['scene_id'],domain=data['domain'],
        **result,profile=profile,risks=risks,created_at=now())
    window.save('report.json',report)
    return report,list(window.outputs)
