"""Explicit offline corpus validation, controls, fitting and one holdout audit."""
from copy import deepcopy
from fractions import Fraction
import json
import math
from pathlib import Path
from time import monotonic

from ._continuity_schema import (ALGORITHM,PARAMETERS,DETECTORS,GENRES,identity,identifier,text,array,
    timebase,stable,domain,rect,finite,validate_regions,validate_context)
from .colorimetry import _object,_int
from ..planning.production_scenes import canonical_digest
from ..runtime.manifest import _timestamp,now

VARIANTS=('unchanged','allowed_lighting','allowed_camera','occlusion','seam_color','local_color',
          'gradual_drift','cumulative_drift','motion_reset','camera_jump')
LABELS=('anomaly','normal','not_comparable','unverified')


def validate_calibration_catalog(catalog,labels=None):
    _object(catalog,'schema_version corpus_id corpus_kind sources split created_at'.split(),'catalog')
    if type(catalog['schema_version']) is not int or catalog['schema_version']!=1:raise ValueError('invalid corpus version')
    identifier(catalog['corpus_id']);_timestamp(catalog['created_at'])
    if catalog['corpus_kind'] not in ('real_benchmark','fixture_only'):raise ValueError('invalid corpus purpose')
    _object(catalog['split'],('calibration_groups','holdout_groups'),'split')
    split=catalog['split'];cal=array(split['calibration_groups'],nonempty=True);hold=array(split['holdout_groups'],nonempty=True)
    if len(set(cal))!=len(cal) or len(set(hold))!=len(hold) or set(cal)&set(hold):raise ValueError('split groups overlap/duplicate')
    for g in (*cal,*hold):identifier(g)
    sourceids=set();groups=set();sha_groups={};cases={}
    for source in array(catalog['sources'],nonempty=True):
        fields='source_id genre source_kind scene_group media frame_records interval rights_note regions truth context'.split()
        _object(source,fields+(['control_targets'] if type(source) is dict and 'control_targets' in source else []),'source')
        _validate_control_targets(source.get('control_targets',{}))
        identifier(source['source_id']);identifier(source['scene_group']);text(source['rights_note']);domain({k:source[k] for k in ('genre','source_kind')},unspecified=False)
        if source['source_id'] in sourceids:raise ValueError('duplicate source ID')
        sourceids.add(source['source_id']);group=source['scene_group'];groups.add(group)
        for k in ('media','regions','truth'):identity(source[k])
        if source['context'] is not None:identity(source['context'])
        records=array(source['frame_records'],nonempty=True)
        if len(records)>4096:raise ValueError('resource_limit: source frames')
        if len({r['path'] for r in records})!=len(records):raise ValueError('duplicate source record')
        for r in records:identity(r)
        for digest in [source['media']['sha256'],*[r['sha256'] for r in records]]:
            prior=sha_groups.setdefault(digest,group)
            if prior!=group:raise ValueError('same media/derivative belongs to multiple scene groups')
        _object(source['interval'],('start_pts','end_pts','time_base'),'interval');interval=source['interval']
        start=_int(interval['start_pts'],'start_pts',-(2**63));end=_int(interval['end_pts'],'end_pts',-(2**63));tb=timebase(interval['time_base'])
        if end<=start or (end-start)*tb<4:raise ValueError('source interval must cover at least four seconds')
        for variant in VARIANTS:cases[f'{source["source_id"]}_{variant}']=source
    if groups!=set(cal)|set(hold):raise ValueError('split must cover exact source scene groups')
    if labels is not None:_validate_labels(catalog,labels,cases)
    return deepcopy(catalog)


def _validate_control_targets(targets):
    if type(targets) is not dict or not set(targets)<= {'occlusion','local_color'}:
        raise ValueError('control targets only support occlusion/local_color')
    for target in targets.values():
        _object(target,('region_ids','authorization'),'control target')
        ids=array(target['region_ids'],nonempty=True)
        for rid in ids:identifier(rid)
        if len(set(ids))!=len(ids):raise ValueError('duplicate control target')
        identity(target['authorization'])


def _source_recipe(source,variant,n,subject_ids):
    targets=source.get('control_targets',{});_validate_control_targets(targets)
    for target in targets.values():
        if not set(target['region_ids'])<=set(subject_ids):raise ValueError('control target must name declared subject regions')
    selected=targets.get(variant)
    return _recipe(variant,n,selected['region_ids'] if selected is not None else subject_ids)


def _source_timing(source,records,sidecars):
    """Verify every native frame and the evidenced half-open end boundary."""
    if not records:raise ValueError('complete native source interval required')
    interval=source['interval'];tb=Fraction(interval['time_base']);side=records[0]['sidecar']['path']
    video=sidecars[side]['probe']['video'];native=video['frames']
    indices=[r['frame_index'] for r in records]
    if (indices!=list(range(indices[0],indices[0]+len(indices))) or
        indices[0]<0 or indices[-1]>=len(native) or Fraction(video['time_base'])!=tb):
        raise ValueError('complete consecutive native source interval required')
    ticks=[]
    for record in records:
        f=native[record['frame_index']];pts=f.get('pts',f.get('best_effort_timestamp'))
        if (type(pts) is not int or record['pts']!=pts or record['time_base'] is None or
            Fraction(record['time_base'])!=tb or record['sidecar']['path']!=side):
            raise ValueError('catalog original PTS/time base differs from native source')
        ticks.append(pts)
    deltas=[(b-a)*tb for a,b in zip(ticks,ticks[1:])]
    if not deltas or min(deltas)<=0 or ticks[0]!=interval['start_pts']:
        raise ValueError('ordered native source interval start required')
    last=indices[-1]
    if last+1<len(native):
        boundary=native[last+1].get('pts',native[last+1].get('best_effort_timestamp'))
    else:
        durations=[native[last][k] for k in ('duration','pkt_duration') if k in native[last]]
        if not durations or any(type(d) is not int or d<=0 for d in durations) or len(set(durations))!=1:
            raise ValueError('explicit last-frame duration required for native interval boundary')
        boundary=ticks[-1]+durations[0]
    if type(boundary) is not int or boundary<=ticks[-1] or boundary!=interval['end_pts']:
        raise ValueError('native source interval end boundary differs')
    return {(rate.numerator,rate.denominator) for rate in (1/d for d in deltas)}


def _validate_labels(catalog,labels,cases):
    _object(labels,'schema_version corpus_sha256 annotators adjudicator entries reviewed_at'.split(),'labels')
    if type(labels['schema_version']) is not int or labels['schema_version']!=1 or labels['corpus_sha256']!=canonical_digest(stable(catalog)):
        raise ValueError('labels corpus/version mismatch')
    authors=array(labels['annotators']);adjudicator=text(labels['adjudicator'])
    if len(authors)!=2 or any(type(a) is not str or not a.strip() for a in authors) or len(set(authors))!=2 or adjudicator in authors:
        raise ValueError('two different annotators and an independent adjudicator required')
    _timestamp(labels['reviewed_at']);seen=set()
    def interval(value,n):
        if type(value) is not list or len(value)!=2:raise ValueError('half-open interval required')
        a,b=(_int(v,'display index') for v in value)
        if not 0<=a<b<=n:raise ValueError('invalid display interval')
    for entry in array(labels['entries']):
        _object(entry,'case_id region_id frame_interval detector_id labels final_label rationale evidence adjudication'.split(),'label entry')
        case=entry['case_id']
        if case not in cases or entry['detector_id'] not in DETECTORS:raise ValueError('unknown case/detector')
        identifier(entry['region_id']);n=len(cases[case]['frame_records']);interval(entry['frame_interval'],n)
        key=(case,entry['region_id'],entry['detector_id'],*entry['frame_interval'])
        if key in seen:raise ValueError('duplicate label entry')
        seen.add(key);text(entry['rationale'])
        observations=array(entry['labels'])
        if len(observations)!=2 or {r.get('author') for r in observations}!=set(authors):raise ValueError('two independent observations required')
        for observation in observations:
            _object(observation,'author label viewed_interval viewed_at'.split(),'observation')
            if observation['label'] not in LABELS:raise ValueError('invalid observer label')
            if observation['viewed_interval']!=[0,n]:raise ValueError('complete actual playback interval required')
            _timestamp(observation['viewed_at'])
        if entry['final_label'] not in LABELS:raise ValueError('invalid final label')
        for ref in array(entry['evidence'],nonempty=True):identity(ref)
        adjudication=entry['adjudication'];observed={r['label'] for r in observations}
        if len(observed)>1 or entry['final_label'] not in observed:
            if adjudication is None:raise ValueError('independent adjudication required for disagreement')
        if adjudication is not None:
            _object(adjudication,'author adjudicated_at reason evidence'.split(),'adjudication')
            if adjudication['author']!=adjudicator:raise ValueError('adjudicator identity differs')
            _timestamp(adjudication['adjudicated_at']);text(adjudication['reason'])
            for ref in array(adjudication['evidence'],nonempty=True):identity(ref)


def build_annotation_template(catalog):
    validate_calibration_catalog(catalog)
    # No fabricated region names, signatures or observations. Operators fill
    # entries against the explicit ROI files and actual complete playback.
    return dict(schema_version=1,corpus_sha256=canonical_digest(stable(catalog)),
        annotators=['annotator_a','annotator_b'],adjudicator='adjudicator',entries=[],reviewed_at=now())


def _fit_threshold(rows):
    rows=[(float(s),label) for s,label in rows if s is not None and math.isfinite(s) and label in ('normal','anomaly')]
    positive=[s for s,l in rows if l=='anomaly'];negative=[s for s,l in rows if l=='normal']
    values=sorted(set(s for s,_ in rows))
    if not positive or not negative or len(values)<2:return None
    candidates=[math.nextafter(values[0],-math.inf),*(a+(b-a)/2 for a,b in zip(values,values[1:])),math.nextafter(values[-1],math.inf)]
    candidates=[c for c in candidates if math.isfinite(c)]
    def error(t):return (sum(s>t for s in negative)/len(negative)+sum(s<=t for s in positive)/len(positive))/2
    threshold=min(candidates,key=lambda t:(error(t),-t))
    return threshold if error(threshold)<.5 else None


def _wilson(k,n):
    if not n:return None
    z=1.959963984540054;p=k/n;den=1+z*z/n
    center=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [max(0.,center-half),min(1.,center+half)]


def _metrics(rows,threshold, *, group):
    result=dict(group=group,tp=0,fp=0,tn=0,fn=0,abstained_positive=0,abstained_negative=0,not_comparable=0,unverified=0)
    denominator=0
    for r in rows:
        if r['label'] not in ('normal','anomaly'):continue
        denominator+=1;positive=r['label']=='anomaly'
        if r['score'] is None or threshold is None or r['state']!='comparable':
            result['abstained_positive' if positive else 'abstained_negative']+=1
            result['not_comparable' if r['state']=='not_comparable' else 'unverified']+=1
        else:
            candidate=r['score']>threshold
            result['tp' if positive and candidate else 'fn' if positive else 'fp' if candidate else 'tn']+=1
    tp,fp,tn,fn=(result[k] for k in ('tp','fp','tn','fn'));covered=tp+fp+tn+fn
    def ratio(k,n):return k/n if n else None
    result.update(fpr=ratio(fp,fp+tn),fnr=ratio(fn,fn+tp),precision=ratio(tp,tp+fp),recall=ratio(tp,tp+fn),
        end_to_end_recall=ratio(tp,tp+fn+result['abstained_positive']),coverage=ratio(covered,denominator),
        wilson=dict(fpr=_wilson(fp,fp+tn),fnr=_wilson(fn,fn+tp),precision=_wilson(tp,tp+fp),recall=_wilson(tp,tp+fn),coverage=_wilson(covered,denominator)))
    return result


def _recipe(variant,n,subject_ids):
    if variant not in VARIANTS or n<6:raise ValueError('known control variant and at least six source frames required')
    r=dict(variant=variant,linear_r_factors=[1.]*n,linear_g_factors=[1.]*n,linear_b_factors=[1.]*n,
        translation_x=[0.]*n,scale=[1.]*n,occlusion_fraction=0.,occlusion_interval=None,local_region_ids=list(subject_ids))
    h=n//2
    for i in range(n):
        t=i/(n-1)
        if variant=='allowed_lighting':
            for c in 'rgb':r[f'linear_{c}_factors'][i]=1+.2*t
        if variant=='allowed_camera':r['translation_x'][i]=.05*t;r['scale'][i]=1+.05*t
        if variant in ('seam_color','local_color') and i>=h:r['linear_r_factors'][i]=1.2;r['linear_b_factors'][i]=.9
        if variant=='gradual_drift':r['linear_r_factors'][i]=1+.2*t;r['linear_b_factors'][i]=1-.1*t
        if variant=='cumulative_drift':
            part=0 if i<n//3 else 1 if i<2*n//3 else 2
            r['linear_r_factors'][i]=[1.,1.1,1.2][part];r['linear_b_factors'][i]=[1.,.95,.9][part]
        if variant=='camera_jump' and i>=h:r['translation_x'][i]=.08
    if variant=='occlusion':r.update(occlusion_fraction=.5,occlusion_interval=[3*n//8,math.ceil(5*n/8)])
    return r


def _validate_profile(profile):
    _object(profile,'schema_version algorithm parameters_sha256 dependency_fingerprint corpus labels split_sha256 thresholds purpose status applicability detectors calibration_metrics holdout_metrics limitations created_at'.split(),'profile')
    if type(profile['schema_version']) is not int or profile['schema_version']!=1 or profile['algorithm']!=ALGORITHM:raise ValueError('invalid profile algorithm/version')
    for k in ('parameters_sha256','dependency_fingerprint','split_sha256'):
        import re
        if type(profile[k]) is not str or not re.fullmatch('[0-9a-f]{64}',profile[k]):raise ValueError('invalid profile digest')
    if profile['purpose'] not in ('real_benchmark','fixture_only') or profile['status'] not in ('ready','partial','unverified'):raise ValueError('invalid profile status/purpose')
    for k in ('corpus','labels','thresholds'):identity(profile[k])
    _timestamp(profile['created_at'])
    _object(profile['applicability'],'genres source_kinds source_fps analysis_space comparison_kinds'.split(),'applicability')
    ap=profile['applicability']
    if ap['analysis_space']!='srgb_rgb24_v1' or any(g not in GENRES for g in ap['genres']) or any(k not in ('captured','generated','animation') for k in ap['source_kinds']):raise ValueError('invalid profile domain')
    for fps in ap['source_fps']:
        _object(fps,('num','den'),'fps');_int(fps['num'],'fps',1);_int(fps['den'],'fps',1)
    from ._continuity_schema import KINDS
    if any(k not in KINDS for k in ap['comparison_kinds']):raise ValueError('invalid profile comparisons')
    rows=array(profile['detectors'])
    if len(rows)!=6 or {r.get('detector_id') for r in rows}!=set(DETECTORS):raise ValueError('six unique detector rows required')
    for r in rows:
        _object(r,'detector_id threshold enabled calibration_groups holdout_groups reason'.split(),'profile detector')
        if type(r['enabled']) is not bool:raise ValueError('enabled must be bool')
        if r['threshold'] is not None:finite(r['threshold'])
        if r['enabled'] and r['threshold'] is None:raise ValueError('enabled detector needs a threshold')
        for g in [*array(r['calibration_groups']),*array(r['holdout_groups'])]:identifier(g)
        if set(r['calibration_groups'])&set(r['holdout_groups']):raise ValueError('profile split overlap')
    enabled=sum(r['enabled'] for r in rows)
    if profile['status']!=('ready' if enabled==6 else 'partial' if enabled else 'unverified'):raise ValueError('profile status contradicts detector readiness')
    for key in ('calibration_metrics','holdout_metrics'):
        metrics=array(profile[key])
        if len(metrics)!=6 or {m.get('detector_id') for m in metrics}!=set(DETECTORS):raise ValueError('six observed detector metrics required')
        for m in metrics:
            _object(m,('detector_id','overall','strata'),'detector metrics')
            for group in [m['overall'],*array(m['strata'])]:
                _object(group,'group tp fp tn fn abstained_positive abstained_negative not_comparable unverified fpr fnr precision recall end_to_end_recall coverage wilson'.split(),'metrics group')
                text(group['group'])
                for k in ('tp','fp','tn','fn','abstained_positive','abstained_negative','not_comparable','unverified'):_int(group[k],k)
                for k in ('fpr','fnr','precision','recall','end_to_end_recall','coverage'):
                    if group[k] is not None and not 0<=finite(group[k])<=1:raise ValueError('invalid metrics ratio')
                _object(group['wilson'],('fpr','fnr','precision','recall','coverage'),'Wilson metrics')
                for interval in group['wilson'].values():
                    if interval is not None and (type(interval) is not list or len(interval)!=2 or not 0<=finite(interval[0])<=finite(interval[1])<=1):raise ValueError('invalid Wilson interval')
            detector=next(r for r in rows if r['detector_id']==m['detector_id']);overall=m['overall']
            if detector['enabled'] and (overall['fpr'] is None or overall['fnr'] is None or (overall['fpr']+overall['fnr'])/2>=.5):
                raise ValueError('enabled detector lacks better-than-constant observed metrics')
    for limitation in array(profile['limitations']):text(limitation)
    return profile


# Control construction and calibration orchestration are below; both use the
# same measured core and keep future truth out of FrameProvider.get().
from ._continuity_controls import build_control_case


def calibrate_continuity(catalog,labels, *, config,paths,logger,timeout=600):
    return _calibrate(catalog,labels,config=config,paths=paths,logger=logger,timeout=timeout)


def _case_rows(source,control,result,labels):
    from ._continuity_geometry import numerical
    np,_=numerical();output=[]
    for entry in labels:
        selected=[];states=[]
        for detector in result['detectors']:
            if detector['detector_id']!=entry['detector_id'] or detector['region_id']!=entry['region_id']:continue
            indices=[int(f.removeprefix('display_')) for f in detector['frame_ids'] if f.startswith('display_')]
            if indices and not any(entry['frame_interval'][0]<=i<entry['frame_interval'][1] for i in indices):continue
            states.append(detector['status'])
            if detector['score'] is not None and detector['status']!='not_comparable':selected.append(detector['score'])
        score=float(np.quantile(selected,.9)) if selected else None
        output.append(dict(detector_id=entry['detector_id'],score=score,label=entry['final_label'],
            state='comparable' if score is not None else 'not_comparable' if 'not_comparable' in states else 'unverified',
            group=source['scene_group'],genre=source['genre'],source_kind=source['source_kind'],case_id=control['case_id']))
    return output


def _summaries(rows,thresholds):
    output=[]
    for detector in DETECTORS:
        values=[r for r in rows if r['detector_id']==detector];threshold=thresholds[detector]
        strata=[_metrics([r for r in values if r['genre']==g],threshold,group='genre:'+g) for g in GENRES]
        strata.extend(_metrics([r for r in values if r['group']==g],threshold,group='scene:'+g) for g in sorted({r['group'] for r in values}))
        output.append(dict(detector_id=detector,overall=_metrics(values,threshold,group='all'),strata=strata))
    return output


def _media_lineage(sidecar,reader):
    result={sidecar['source']['sha256']}
    for record in sidecar['processing']['command_records']:
        data=reader._json(Path(record['path']))
        origin=data.get('source',{}) if isinstance(data,dict) else {}
        if isinstance(origin,dict):origin=origin.get('identity',origin)
        if isinstance(origin,dict) and isinstance(origin.get('sha256'),str):result.add(origin['sha256'])
    # Only already verified media origins are used; tools and generic receipts
    # shared by multiple independent sources are not scene lineage.
    for value in sidecar.get('mapping',{}).get('evidence',[]):
        data=reader._json(Path(value['path']))
        if not isinstance(data,dict):continue
        for key in ('source','generated','image'):
            origin=data.get(key,{})
            if isinstance(origin,dict):origin=origin.get('identity',origin)
            if not isinstance(origin,dict):continue
            actual=getattr(reader,'frozen',{}).get(origin.get('path'))
            if actual is not None and actual['sha256']==origin.get('sha256'):result.add(actual['sha256'])
    return result


def _claim_lineage(hashes,group,owners):
    for sha in hashes:
        if sha in owners and owners[sha]!=group:raise ValueError('verified media lineage belongs to different scene groups')
        owners[sha]=group


def _sealed_predictions(detectors,thresholds):
    for detector in detectors:
        threshold=thresholds[detector['detector_id']]
        if threshold is not None and detector['score'] is not None and detector['status']!='not_comparable':
            detector.update(threshold=threshold,status='candidate' if detector['score']>threshold else 'no_candidate',reasons=[])


def _verify_profile_evidence(profile,profile_identity,window):
    """Re-derive a profile's claims from its sealed local benchmark artifacts."""
    baseline=window.json_bytes
    try:return _verify_profile_records(profile,profile_identity,window)
    finally:window.json_bytes=baseline


def _profile_source_evidence(source,window):
    """Read one source at a time; saved controls cannot define source facts."""
    records=[];sidecars={};side_refs={};bypath={}
    try:
        for i,ref in enumerate(source['frame_records']):
            record=window.read_json(ref)
            try:
                if (record['status']!='ready' or record['analysis_space']!='srgb_rgb24_v1' or
                    stable(record['source'])!=stable(source['media'])):
                    raise ValueError('profile native source record differs')
                side=record['sidecar']
                if side['path'] not in sidecars:
                    sidecars[side['path']]=window.read_json(side);side_refs[side['path']]=side
                records.append({k:deepcopy(record[k]) for k in ('frame_index','pts','time_base','sidecar')})
                bypath[ref['path']]=dict(frame_id=f'source_frame_{i}',record=ref)
            finally:window.release_json(ref)
        rates=_source_timing(source,records,sidecars)
        regions=window.read_json(source['regions'])
        try:regions=validate_regions(regions,bypath)
        finally:window.release_json(source['regions'])
        return dict(records=[dict(pts=r['pts'],time_base=r['time_base']) for r in records],rates=rates,
            regions=[{k:r[k] for k in ('region_id','role','identity_note')} for r in regions])
    finally:
        for side in sidecars:
            window.release_json(side_refs[side])


def _verify_profile_records(profile,profile_identity,window):
    _validate_profile(profile)
    if stable(window.read_json(profile_identity))!=stable(profile):raise ValueError('profile differs from persisted sealed record')
    catalog=window.read_json(profile['corpus']);labels=window.read_json(profile['labels'])
    validate_calibration_catalog(catalog,labels)
    if profile['purpose']!=catalog['corpus_kind']:raise ValueError('profile purpose contradicts corpus')
    split_digest=canonical_digest(stable(dict(split=catalog['split'],sources=[dict(scene_group=s['scene_group'],media=s['media']) for s in catalog['sources']])))
    if profile['split_sha256']!=split_digest:raise ValueError('profile split evidence differs')
    sealed=window.read_json(profile['thresholds'])
    _object(sealed,('schema_version','algorithm','calibration_groups','thresholds'),'sealed thresholds')
    if type(sealed['schema_version']) is not int or sealed['schema_version']!=1 or sealed['algorithm']!=ALGORITHM or sealed['calibration_groups']!=catalog['split']['calibration_groups']:
        raise ValueError('sealed threshold split/version differs')
    rows=array(sealed['thresholds'])
    if len(rows)!=6 or {r.get('detector_id') for r in rows}!=set(DETECTORS):raise ValueError('six sealed thresholds required')
    for row in rows:
        _object(row,('detector_id','threshold','reason'),'sealed threshold')
        if row['threshold'] is not None:finite(row['threshold'])
    thresholds={r['detector_id']:r['threshold'] for r in rows}
    if any(r['threshold']!=thresholds[r['detector_id']] for r in profile['detectors']):raise ValueError('profile thresholds differ from sealed evidence')
    parent=Path(profile_identity['path']).parent
    def sibling(name):
        value=window.freeze(parent/name)
        return value,window.read_json(value)
    case_identity,case_results=sibling('case-results.json')
    _,evaluation=sibling('evaluation.json')
    _object(case_results,'schema_version algorithm corpus_sha256 labels_sha256 cases'.split(),'case results')
    if case_results['schema_version']!=1 or case_results['algorithm']!=ALGORITHM or case_results['corpus_sha256']!=canonical_digest(stable(catalog)) or case_results['labels_sha256']!=canonical_digest(stable(labels)):
        raise ValueError('case results input identities differ')
    from .continuity_analysis import _metric_digest
    source_by_id={s['source_id']:s for s in catalog['sources']};expected={s['source_id']+'_'+v for s in catalog['sources'] for v in VARIANTS}
    source_evidence={sid:_profile_source_evidence(source,window) for sid,source in source_by_id.items()}
    seen=set();measures={'calibration':[],'holdout':[]};label_keys=set();fpses={'calibration':set(),'holdout':set()};kindsets={'calibration':set(),'holdout':set()}
    for case in array(case_results['cases']):
        window.check_time();_object(case,'case_id source_id scene_group split control metrics metric_digest labels detector_results'.split(),'case result')
        if case['case_id'] not in expected or case['case_id'] in seen or case['source_id'] not in source_by_id:raise ValueError('unknown/duplicate benchmark case')
        seen.add(case['case_id']);source=source_by_id[case['source_id']]
        split='calibration' if source['scene_group'] in catalog['split']['calibration_groups'] else 'holdout'
        if case['split']!=split or case['scene_group']!=source['scene_group']:raise ValueError('case scene/split differs')
        control=window.read_json(case['control']);metrics=window.read_json(case['metrics'])
        _object(control,'schema_version case_id source_id scene_group split variant base_input_sha256 recipe display_map clips references comparisons anchors context padding_masks truth created_at'.split(),'control case')
        if control['case_id']!=case['case_id'] or control['source_id']!=source['source_id'] or control['scene_group']!=source['scene_group'] or control['split']!=split:
            raise ValueError('control case identity differs')
        if control['truth']!=source['truth'] or control['variant'] not in VARIANTS:raise ValueError('control truth/variant differs')
        evidence=source_evidence[source['source_id']];original=evidence['records'];n=len(original)
        region_fields=('region_id','role','identity_note')
        if ([{k:r[k] for k in region_fields} for r in control['anchors']]!=
            [{k:r[k] for k in region_fields} for r in evidence['regions']]):raise ValueError('control region roles differ from source regions')
        if control['recipe']!=_source_recipe(source,control['variant'],n,[r['region_id'] for r in evidence['regions'] if r['role']=='subject']):raise ValueError('control recipe differs')
        expected_map=[dict(frame_id=f'display_{i}',source_frame_id=f'source_frame_{i if control["variant"]!="motion_reset" or i<n//2 else i-n//2}',
            display_index=i,display_pts=r['pts']-original[0]['pts'],display_time_base=r['time_base'],transform_index=i) for i,r in enumerate(original)]
        if control['display_map']!=expected_map:raise ValueError('control display map differs from native source timing')
        for target in source.get('control_targets',{}).values():window.check(target['authorization'])
        _object(metrics,'schema_version algorithm input_sha256 frame_results comparisons trajectories detectors'.split(),'case metrics')
        if metrics['schema_version']!=1 or metrics['algorithm']!=ALGORITHM or case['metric_digest']!=_metric_digest(metrics):raise ValueError('case metric content digest differs')
        expected_labels=[e for e in labels['entries'] if e['case_id']==case['case_id']]
        if case['labels']!=expected_labels:raise ValueError('case labels differ from frozen annotations')
        predictions=deepcopy(metrics['detectors']);_sealed_predictions(predictions,thresholds)
        if case['detector_results']!=predictions:raise ValueError('case predictions contradict sealed thresholds')
        measures[split].extend(_case_rows(source,control,dict(detectors=case['detector_results']),expected_labels))
        label_keys.update((e['case_id'],e['region_id'],e['detector_id']) for e in expected_labels)
        fpses[split].update(evidence['rates'])
        kindsets[split].update(p['kind'] for p in metrics['comparisons'] if any(r['comparability']=='comparable' for r in p['regions']))
        for mask in control['padding_masks']:
            if mask is not None:window.check(mask)
        # Keep only the compact score rows; full case geometries are sequential
        # inputs rather than a corpus-sized metadata cache.
        window.release_json(case['control']);window.release_json(case['metrics'])
    if seen!=expected:raise ValueError('benchmark case coverage incomplete')
    for d in DETECTORS:
        fitted=_fit_threshold([(r['score'],r['label']) for r in measures['calibration'] if r['detector_id']==d and r['state']=='comparable'])
        if fitted!=thresholds[d]:raise ValueError('sealed threshold contradicts calibration measurements')
    for split,key in (('calibration','calibration_metrics'),('holdout','holdout_metrics')):
        if profile[key]!=_summaries(measures[split],thresholds):raise ValueError('profile observed metrics contradict case evidence')
    for detector in profile['detectors']:
        if detector['calibration_groups']!=catalog['split']['calibration_groups'] or detector['holdout_groups']!=catalog['split']['holdout_groups']:
            raise ValueError('profile detector split differs')
        if not detector['enabled']:continue
        if profile['purpose']=='real_benchmark' and (len(catalog['sources'])!=24 or len(catalog['split']['calibration_groups'])!=12 or len(catalog['split']['holdout_groups'])!=12 or
            any(sum(s['genre']==g and s['scene_group'] in catalog['split'][key] for s in catalog['sources'])!=2 for g in GENRES for key in ('calibration_groups','holdout_groups'))):
            raise ValueError('enabled profile lacks real benchmark coverage')
        for case in case_results['cases']:
            regionids={d['region_id'] for d in case['detector_results'] if d['region_id'] is not None}
            if any((case['case_id'],r,d) not in label_keys for r in regionids for d in DETECTORS):raise ValueError('enabled profile lacks complete annotations')
        for split in ('calibration','holdout'):
            rows=[r for r in measures[split] if r['detector_id']==detector['detector_id'] and r['score'] is not None]
            if any(len({r['group'] for r in rows if r['label']==label})<6 for label in ('normal','anomaly')) or {r['genre'] for r in rows if r['label'] in ('normal','anomaly')}!=set(GENRES):
                raise ValueError('enabled profile lacks independent scene/genre coverage')
    ap=profile['applicability']
    for key,field in (('genres','genre'),('source_kinds','source_kind')):
        expected_values=sorted(set(r[field] for r in measures['calibration'] if r['score'] is not None and r['label'] in ('normal','anomaly'))&set(r[field] for r in measures['holdout'] if r['score'] is not None and r['label'] in ('normal','anomaly')))
        if sorted(ap[key])!=expected_values:raise ValueError('profile applicability contradicts observed domain')
    if ap['source_fps']!=[dict(num=n,den=d) for n,d in sorted(fpses['calibration']&fpses['holdout'])] or ap['comparison_kinds']!=sorted(kindsets['calibration']&kindsets['holdout']):
        raise ValueError('profile fps/comparison domain contradicts observed evidence')
    _object(evaluation,'schema_version algorithm profile_sha256 case_results calibration_metrics holdout_metrics domain_coverage limitations'.split(),'evaluation')
    if evaluation['profile_sha256']!=profile_identity['sha256'] or stable(evaluation['case_results'])!=stable(case_identity) or evaluation['calibration_metrics']!=profile['calibration_metrics'] or evaluation['holdout_metrics']!=profile['holdout_metrics'] or evaluation['domain_coverage']!=ap:
        raise ValueError('profile evaluation identity/metrics differ')
    return profile


def _calibrate(catalog,labels, *, config,paths,logger,timeout):
    from .images import _deadline
    from ._continuity_audit import AuditWindow,dependencies,png_bytes
    from .colorimetry import load_color_analysis_set
    from .continuity_analysis import measure_continuity,_save_measurement
    from ._continuity_geometry import numerical,frame_arrays
    from ..runtime.manifest import thaw,hash_file
    deadline=_deadline(timeout,monotonic());window=AuditWindow(paths,logger,deadline)
    if type(catalog) is dict and set(catalog)==set(('path','bytes','mtime_ns','sha256','verified_at')):
        catalog_identity=deepcopy(catalog);catalog=window.read_json(catalog)
    else:catalog_identity=None
    if type(labels) is dict and set(labels)==set(('path','bytes','mtime_ns','sha256','verified_at')):
        labels_identity=deepcopy(labels);labels=window.read_json(labels)
    else:labels_identity=None
    data=validate_calibration_catalog(catalog,labels)
    if not labels['entries']:raise ValueError('actual complete playback annotations required; template has no observations')
    deps=dependencies(window)
    catalog_identity=catalog_identity or window.save('calibration/catalog-input.json',data)
    labels_identity=labels_identity or window.save('calibration/labels-input.json',labels)
    window.save('calibration/catalog-snapshot.json',dict(schema_version=1,catalog_identity=catalog_identity,catalog=data))
    window.save('calibration/labels-snapshot.json',dict(schema_version=1,labels_identity=labels_identity,labels=labels))
    for e in labels['entries']:
        for ref in e['evidence']:window.check(ref)
        if e['adjudication']:
            for ref in e['adjudication']['evidence']:window.check(ref)
    all_rows={};cases=[];fps_by_split={};kinds_by_split={};input_groups={};thresholds={}
    # Establish ancestry ownership across BOTH splits before any threshold fit.
    # Each source has its own bounded read window and no raw pixels are loaded.
    for source in data['sources']:
        with load_color_analysis_set([r['path'] for r in source['frame_records']],config=config,timeout=max(.001,deadline-monotonic())) as reader:
            for side in reader.sidecars.values():_claim_lineage(_media_lineage(side,reader),source['scene_group'],input_groups)
    for split_name,group_key in (('calibration','calibration_groups'),('holdout','holdout_groups')):
        if split_name=='holdout':
            # The fitting function receives calibration rows only, before any
            # holdout measurement. The exclusive file seals this boundary.
            thresholds={detector:_fit_threshold([(r['score'],r['label']) for r in all_rows['calibration'] if r['detector_id']==detector and r['state']=='comparable']) for detector in DETECTORS}
            threshold_identity=window.save('calibration/thresholds.json',dict(schema_version=1,algorithm=ALGORITHM,
                calibration_groups=data['split']['calibration_groups'],thresholds=[dict(detector_id=d,threshold=thresholds[d],reason=None if thresholds[d] is not None else 'insufficient_or_inseparable_labels') for d in DETECTORS]))
            for case in cases:_sealed_predictions(case['detector_results'],thresholds)
        rows=[];fpsset=set();kindset=set()
        sources=[s for s in data['sources'] if s['scene_group'] in data['split'][group_key]]
        for source in sources:
            window.check_time();window.check(source['media'])
            truth=window.read_json(source['truth']);region_doc=window.read_json(source['regions'])
            allowed_regions={r['region_id'] for r in region_doc['regions']}
            for e in labels['entries']:
                if e['case_id'] in {source['source_id']+'_'+v for v in VARIANTS} and e['region_id'] not in allowed_regions:raise ValueError('label refers to undeclared source region')
            with load_color_analysis_set([r['path'] for r in source['frame_records']],config=config,timeout=max(.001,deadline-monotonic())) as reader:
                source_frames=reader.frames
                source_sha={f['record']['source']['sha256'] for f in source_frames}
                if source_sha!={source['media']['sha256']}:raise ValueError('source frame records do not bind declared media')
                for sha in source_sha:
                    prior=input_groups.setdefault(sha,source['scene_group'])
                    if prior!=source['scene_group']:raise ValueError('same original media in different scene groups')
                original=[f['record'] for f in source_frames]
                fpsset.update(_source_timing(source,original,reader.sidecars))
                for variant in VARIANTS:
                    window.check_time();control,provider=build_control_case(source,variant,reader=reader,truth=truth)
                    control['split']=split_name;caseid=control['case_id'];plan=provider.plan
                    if any(v!=0 for v in control['recipe']['translation_x']) or any(v!=1 for v in control['recipe']['scale']):
                        np,cv=numerical()
                        for i,d in enumerate(control['display_map']):
                            try:
                                value=provider.get(d['frame_id']);mask=value['valid_mask']
                                if mask is not None:
                                    ok,encoded=cv.imencode('.png',mask.astype(np.uint8)*255)
                                    if not ok:raise RuntimeError('padding mask PNG encoding failed')
                                    control['padding_masks'][i]=window.save_bytes(f'calibration/masks/{caseid}_{i:06d}.png',encoded.tobytes())
                            finally:provider.release(d['frame_id'])
                    control_identity=window.save(f'calibration/controls/{caseid}.json',control)
                    plan['provenance']['control_case']=control_identity
                    result=measure_continuity(plan,provider,deadline=deadline)
                    for frame in result['frame_results']:
                        rec=next(r['record'] for r in source_frames if r['record_identity']['path']==frame['record']['path']);frame['source']=rec['source']
                    case_labels=[e for e in labels['entries'] if e['case_id']==caseid]
                    case_rows=_case_rows(source,control,result,case_labels);rows.extend(case_rows)
                    kindset.update(p['kind'] for p in result['comparisons'] if any(r['comparability']=='comparable' for r in p['regions']))
                    # Predictions here reflect the sealed threshold, even if
                    # the final applicability gate later disables a detector.
                    if split_name=='holdout':
                        _sealed_predictions(result['detectors'],thresholds)
                    metric_id,metric_digest=_save_measurement(result,plan,provider,window,canonical_digest(stable(control)),prefix=f'calibration/cases/{caseid}/')
                    cases.append(dict(case_id=caseid,source_id=source['source_id'],scene_group=source['scene_group'],split=split_name,
                        control=control_identity,metrics=metric_id,metric_digest=metric_digest,labels=case_labels,detector_results=result['detectors']))
                for side in reader.sidecars.values():_claim_lineage(_media_lineage(side,reader),source['scene_group'],input_groups)
        all_rows[split_name]=rows;fps_by_split[split_name]=fpsset;kinds_by_split[split_name]=kindset
    cal_metrics=_summaries(all_rows['calibration'],thresholds);hold_metrics=_summaries(all_rows['holdout'],thresholds)
    detectors=[]
    real_complete=(data['corpus_kind']=='real_benchmark' and len(data['sources'])==24 and len(data['split']['calibration_groups'])==12 and len(data['split']['holdout_groups'])==12 and
        all(sum(s['genre']==g and s['scene_group'] in data['split'][key] for s in data['sources'])==2 for g in GENRES for key in ('calibration_groups','holdout_groups')))
    # Require every source/case/region/detector to have an explicit final human
    # observation, including not_comparable/unverified rather than omission.
    label_keys={(e['case_id'],e['region_id'],e['detector_id']) for e in labels['entries']}
    all_annotated=True
    for c in cases:
        rid={d['region_id'] for d in c['detector_results'] if d['region_id'] is not None}
        if any((c['case_id'],r,d) not in label_keys for r in rid for d in DETECTORS):all_annotated=False
    for detector in DETECTORS:
        enabled=thresholds[detector] is not None and all_annotated
        for split in ('calibration','holdout'):
            rows=[r for r in all_rows[split] if r['detector_id']==detector];metrics=_metrics(rows,thresholds[detector],group='all')
            enabled &= metrics['fpr'] is not None and metrics['fnr'] is not None and (metrics['fpr']+metrics['fnr'])/2<.5
            for label in ('normal','anomaly'):
                enabled &= len({r['group'] for r in rows if r['label']==label and r['score'] is not None})>=6
            enabled &= {r['genre'] for r in rows if r['score'] is not None and r['label'] in ('normal','anomaly')}==set(GENRES)
        enabled=bool(enabled and (real_complete or data['corpus_kind']=='fixture_only'))
        detectors.append(dict(detector_id=detector,threshold=thresholds[detector],enabled=enabled,
            calibration_groups=data['split']['calibration_groups'],holdout_groups=data['split']['holdout_groups'],reason=None if enabled else 'insufficient_annotated_coverage_or_not_better_than_constant'))
    genres=[];source_kinds=[]
    for key,values,target in (('genre',GENRES,genres),('source_kind',('captured','generated','animation'),source_kinds)):
        for value in values:
            if all(any(r[key]==value and r['score'] is not None and r['label'] in ('normal','anomaly') for r in all_rows[split]) for split in ('calibration','holdout')):target.append(value)
    applicability=dict(genres=genres,source_kinds=source_kinds,source_fps=[dict(num=n,den=d) for n,d in sorted(fps_by_split['calibration']&fps_by_split['holdout'])],
        analysis_space='srgb_rgb24_v1',comparison_kinds=sorted(kinds_by_split['calibration']&kinds_by_split['holdout']))
    limitations=['Controlled benchmark only; no production accuracy or complete-video approval.','Independent filming/lineage and actual human playback are operator attestations.']
    if not real_complete:limitations.append('Real 24-source six-genre 12/12 benchmark is incomplete.')
    if not all_annotated:limitations.append('Some source/case/region/detector labels are missing.')
    count=sum(d['enabled'] for d in detectors)
    profile=dict(schema_version=1,algorithm=ALGORITHM,parameters_sha256=canonical_digest(PARAMETERS),dependency_fingerprint=deps['fingerprint'],
        corpus=catalog_identity,labels=labels_identity,split_sha256=canonical_digest(stable(dict(split=data['split'],sources=[dict(scene_group=s['scene_group'],media=s['media']) for s in data['sources']]))),
        thresholds=threshold_identity,purpose=data['corpus_kind'],status='ready' if count==6 else 'partial' if count else 'unverified',applicability=applicability,
        detectors=detectors,calibration_metrics=cal_metrics,holdout_metrics=hold_metrics,limitations=limitations,created_at=now())
    _validate_profile(profile)
    case_identity=window.save('calibration/case-results.json',dict(schema_version=1,algorithm=ALGORITHM,corpus_sha256=canonical_digest(stable(data)),labels_sha256=canonical_digest(stable(labels)),cases=cases))
    window.verify();profile_identity=window.save('calibration/profile.json',profile)
    window.save('calibration/evaluation.json',dict(schema_version=1,algorithm=ALGORITHM,profile_sha256=profile_identity['sha256'],case_results=case_identity,
        calibration_metrics=cal_metrics,holdout_metrics=hold_metrics,domain_coverage=applicability,limitations=limitations))
    return profile,list(window.outputs)
