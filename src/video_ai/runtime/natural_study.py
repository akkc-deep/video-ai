"""Immutable natural qualification stages, separate from real improvement acceptance."""
from pathlib import Path

from ..media.natural_repair_engine import DIRECTIONS,METRICS,THRESHOLDS,derive_natural_thresholds
from ._scene_continuity_io import artifact,uid
from .manifest import now
from .natural_study_records import (StudyReader,StudyLock,fields,text,timestamp,study_root,
    put_json,check_inputs,capture_software,verify_software,STUDY_ROOT)
from .natural_study_measure import measure_case,replay_case,control_recipes
from .production_state import ProductionRefused

ALGORITHM='natural_constant_color_repair_v1'
PROFILE_FIELDS=('schema_version algorithm purpose production_eligible evidence_only protocol inputs software '
    'conditional_profile thresholds evaluation qualified_domains qualified_directions limitations created_at')
LIMITATIONS=['Offline research only; no production eligibility.','Human declarations are retained evidence, not automated visual truth.',
    'Only registered domains and conditional r2 directions; no additional axes or amplitude authority.']


def dependencies(request):
    from ..config import load_config
    from ._scene_color_repair_profile import verified_profile
    r=StudyReader();config=load_config(Path(r.cap(request['config'])['path']))
    profile,closure=verified_profile(r.cap(request['conditional_profile'])['path'],reader=r)
    r.verify_all();return config,profile,closure


def protocol():
    return dict(schema_version=1,algorithm=ALGORITHM,phase_order=['freeze','measure','seal','evaluate','finalize'],
        minimum_split_sources=12,minimum_split_groups=4,minimum_direction_positive_groups=4,
        thresholds=list(THRESHOLDS),threshold_rule='strict_interval_midpoint_v1',
        controls={op+':'+d:control_recipes(op,.01 if d=='positive' else -.01) for op,d in DIRECTIONS},
        native_fps='16/1',maximum_native_frames=4096,minimum_support_per_frame=81,
        pixel_quantization='actual_RGB8_after_each_transform',holdout_policy='no_pixels_or_labels_before_seal_once_only',
        maximum_frame_bytes=32*1024**2,maximum_feature_window_bytes=64*1024**2,
        maximum_json_bytes=16*1024**2,maximum_cumulative_json_bytes=256*1024**2,
        source_operation_seconds=300,production_eligible=False)


def _identity(reader,root,name,ref):
    if reader.cap(root/name)!=ref: raise ProductionRefused('independent stage identity differs: '+name)
    return reader.any(ref)


def _frozen(root):
    root=study_root(root);r=StudyReader();freeze_ref=r.cap(root/'freeze-receipt.json');receipt=r.any(freeze_ref)
    fields(receipt,'schema_version study_id request protocol inputs software conditional_closure created_at')
    if receipt['schema_version']!=1 or uid(receipt['study_id'])!=root.name: raise ProductionRefused('study freeze producer differs')
    timestamp(receipt['created_at'])
    req=_identity(r,root,'inputs.FROZEN.json',receipt['inputs'])
    if r.any(receipt['request'])!=req: raise ProductionRefused('study original request differs')
    if _identity(r,root,'protocol.FROZEN.json',receipt['protocol'])!=protocol(): raise ProductionRefused('frozen natural protocol differs')
    config,conditional,closure=dependencies(req)
    if closure!=receipt['conditional_closure']: raise ProductionRefused('original conditional closure differs')
    r=StudyReader()
    verify_software(_identity(r,root,'software.FROZEN.json',receipt['software']),config)
    check_inputs(req)
    if timestamp(req['requested_at'])>timestamp(receipt['created_at']): raise ProductionRefused('freeze precedes request')
    # Each source owns its budget. Recheck the small independent anchors after
    # the multi-source validation, without extending any individual deadline.
    final=StudyReader()
    for ref in [freeze_ref,receipt['request'],receipt['inputs'],receipt['protocol'],receipt['software']]: final.cap(ref)
    final.verify_all();return root,receipt,req,config,conditional


def freeze(request_path,*,root=None):
    r=StudyReader();ref=r.cap(request_path);request=r.any(ref)
    checked=check_inputs(request);config,_,closure=dependencies(request)
    # Resolve the current records module constant, so a test can isolate roots.
    from . import natural_study_records as records
    root=study_root(root or records.STUDY_ROOT/request['study_id'],request['study_id'])
    with StudyLock(root):
        if (root/'freeze-receipt.json').exists():
            _,receipt,_,_,_=_frozen(root)
            if receipt['request']!=ref: raise ProductionRefused('study UUID already bound to another request')
        else:
            if any(p.name!='.natural-study.lock' for p in root.iterdir()):
                raise ProductionRefused('partial freeze retained; no automatic refreeze')
            p=put_json(root/'protocol.FROZEN.json',protocol())
            inputs=put_json(root/'inputs.FROZEN.json',request)
            software=put_json(root/'software.FROZEN.json',capture_software(config))
            records.holdout_reservations(request,checked['metadata'],reserve=True)
            put_json(root/'freeze-receipt.json',dict(schema_version=1,study_id=request['study_id'],request=ref,
                protocol=p,inputs=inputs,software=software,conditional_closure=closure,created_at=now()))
    return dict(status='frozen',root=str(root),ready_for_propose=False)


def _failed(case,error):
    return dict(schema_version=1,case=case,failed=True,error=dict(kind=type(error).__name__,message=str(error) or type(error).__name__),
        preview=None,projections=[dict(case_id=case['case_id'],scene_group=case['scene_group'],domain=case['domain'],
            natural_label='unverified',operation=None,correction_direction=None,projection_operation=op,
            projection_direction=d,status='failed',controls={}) for op,d in DIRECTIONS])


def _case_result(root,case,receipt,config,conditional,*,seal_ref=None):
    folder=root/case['split']/case['case_id'];r=StudyReader()
    intent=dict(schema_version=1,study_id=root.name,case=case,freeze=r.cap(root/'freeze-receipt.json'),seal=seal_ref)
    if (folder/'receipt.json').exists():
        return _read_case(root,case,receipt,config,conditional,seal_ref=seal_ref)[0]
    if folder.exists(): raise ProductionRefused('partial natural case retained; no automatic remeasure: '+case['case_id'])
    intent_ref=put_json(folder/'intent.json',dict(**intent,started_at=now()))
    try:
        value=measure_case(case,config=config,conditional_profile=conditional,out=folder/'evidence')
    except (ValueError,OSError,TimeoutError,RuntimeError) as error: value=_failed(case,error)
    result=put_json(folder/'result.json',value)
    saved=put_json(folder/'receipt.json',dict(schema_version=1,intent=intent_ref,result=result,finished_at=now()))
    return saved


def _read_case(root,case,receipt,config,conditional,*,seal_ref=None,replay=False):
    r=StudyReader();folder=root/case['split']/case['case_id'];ref=r.cap(folder/'receipt.json');row=r.any(ref)
    fields(row,'schema_version intent result finished_at')
    intent=_identity(r,folder,'intent.json',row['intent']);fields(intent,'schema_version study_id case freeze seal started_at')
    if (intent['study_id']!=root.name or intent['case']!=case or intent['seal']!=seal_ref
            or intent['freeze']!=r.cap(root/'freeze-receipt.json')): raise ProductionRefused('case original intent binding differs')
    start=timestamp(intent['started_at']);end=timestamp(row['finished_at'])
    if not timestamp(receipt['created_at'])<=start<=end: raise ProductionRefused('case stage time differs')
    if seal_ref is not None and start<timestamp(r.any(seal_ref)['created_at']): raise ProductionRefused('holdout before seal')
    result=_identity(r,folder,'result.json',row['result'])
    if result.get('failed') is True:
        fields(result,'schema_version case failed error preview projections','failed natural case')
        fields(result['error'],'kind message','failed natural error')
        text(result['error']['kind']);text(result['error']['message'])
        canonical=_failed(case,ValueError('canonical failure'))
        if result['preview'] is not None or result['projections']!=canonical['projections']:
            raise ProductionRefused('failed natural case cannot carry measured qualification evidence')
    elif 'failed' in result:
        raise ProductionRefused('failed natural case flag must use the canonical failure schema')
    else:
        fields(result,'schema_version case material epoch author report original dry fit preview controls projections reason ready_for_propose','measured natural case')
        if result['ready_for_propose'] is not False: raise ProductionRefused('study case cannot claim runtime repair authority')
    if result['case']!=case or [(p['projection_operation'],p['projection_direction']) for p in result['projections']]!=list(DIRECTIONS):
        raise ProductionRefused('case result inventory differs')
    for p in result['projections']:
        if any(p[k]!=case[k] for k in ('case_id','scene_group','domain')): raise ProductionRefused('case group/domain differs')
    if replay and result.get('failed') is not True: replay_case(result,config=config,conditional_profile=conditional)
    r.verify_all();return ref,result


def _index(root,receipt,req,config,conditional,split,*,seal_ref=None,replay=False):
    r=StudyReader();name='development-index.json' if split=='development' else 'holdout-index.json'
    ref=r.cap(root/name);index=r.any(ref);fields(index,'schema_version freeze seal cases created_at')
    cases=[c for c in req['cases'] if c['split']==split]
    if index['freeze']!=r.cap(root/'freeze-receipt.json') or index['seal']!=seal_ref or len(index['cases'])!=len(cases):
        raise ProductionRefused('stage index drops or changes registered denominator')
    results=[]
    for c,saved in zip(cases,index['cases']):
        actual,result=_read_case(root,c,receipt,config,conditional,seal_ref=seal_ref,replay=replay)
        if saved!=actual: raise ProductionRefused('stage case receipt identity differs')
        if timestamp(StudyReader().any(actual)['finished_at'])>timestamp(index['created_at']): raise ProductionRefused('index predates case')
        results.append(result)
    StudyReader().cap(ref)
    return ref,index,results


def measure(root):
    with StudyLock(study_root(root)):
        root,receipt,req,config,conditional=_frozen(root)
        if (root/'thresholds.SEALED.json').exists(): raise ProductionRefused('development cannot change after seal')
        if (root/'development-index.json').exists(): _index(root,receipt,req,config,conditional,'development')
        else:
            refs=[_case_result(root,c,receipt,config,conditional) for c in req['cases'] if c['split']=='development']
            put_json(root/'development-index.json',dict(schema_version=1,freeze=artifact(root/'freeze-receipt.json'),seal=None,cases=refs,created_at=now()))
    return dict(status='measured',root=str(root),ready_for_propose=False)


def reduce_development(results):
    return {op+':'+d:derive_natural_thresholds([next(p for p in row['projections']
        if (p['projection_operation'],p['projection_direction'])==(op,d)) for row in results],operation=op,direction=d) for op,d in DIRECTIONS}


def _seal(root,receipt,req,config,conditional,*,replay=False):
    r=StudyReader();seal_ref=r.any(root/'threshold-seal-identity.json')
    saved=_identity(r,root,'thresholds.SEALED.json',seal_ref)
    fields(saved,'schema_version freeze development directions created_at')
    dev,index,results=_index(root,receipt,req,config,conditional,'development',replay=replay)
    r=StudyReader()
    if r.any(root/'threshold-seal-identity.json')!=seal_ref: raise ProductionRefused('seal identity changed during replay')
    r.cap(seal_ref)
    if (saved['freeze']!=r.cap(root/'freeze-receipt.json') or saved['development']!=dev
            or saved['directions']!=reduce_development(results) or timestamp(saved['created_at'])<timestamp(index['created_at'])):
        raise ProductionRefused('sealed thresholds differ from original development reductions')
    return seal_ref,saved,results


def seal(root):
    with StudyLock(study_root(root)):
        root,receipt,req,config,conditional=_frozen(root)
        if (root/'threshold-seal-identity.json').exists(): ref,value,_=_seal(root,receipt,req,config,conditional)
        else:
            if (root/'thresholds.SEALED.json').exists(): raise ProductionRefused('partial seal retained')
            dev,index,results=_index(root,receipt,req,config,conditional,'development',replay=True)
            ref=put_json(root/'thresholds.SEALED.json',dict(schema_version=1,freeze=artifact(root/'freeze-receipt.json'),
                development=dev,directions=reduce_development(results),created_at=now()))
            put_json(root/'threshold-seal-identity.json',ref)
            value=StudyReader().any(ref)
    return dict(status='sealed',thresholds=ref,directions=value['directions'],ready_for_propose=False)


def evaluate_rows(results,sealed):
    decisions={}
    for op,d in DIRECTIONS:
        key=op+':'+d;dev=sealed['directions'][key];reasons=[];positives=[];neutral=[]
        if dev['status']!='separated':
            decisions[key]=dict(status='unqualified',reasons=['development_unqualified'],positive_cases=0,positive_groups=0,domains=[]);continue
        t=dev['thresholds']
        for result in results:
            row=next(p for p in result['projections'] if (p['projection_operation'],p['projection_direction'])==(op,d))
            label=row['natural_label'];cid=row['case_id']
            if label not in ('neutral','mild_color_bias','unsafe','not_comparable','unverified'):
                raise ProductionRefused('unknown holdout natural label')
            if row['status'] not in ('measured','refused','failed'): raise ProductionRefused('unknown holdout measurement status')
            target=label=='mild_color_bias' and (row['operation'],row['correction_direction'])==(op,d)
            if label=='unverified': reasons.append('unresolved_case:'+cid)
            elif label in ('unsafe','not_comparable') or label=='mild_color_bias' and not target:
                if row['status']!='refused': reasons.append('negative_case_not_refused:'+cid)
            elif row['status']!='measured': reasons.append('unmeasured_case:'+cid)
            elif label=='neutral':
                neutral.append(row)
                if row['initial_bias']>t['noop_bias_ceiling'] or row['maximum_off_axis_residual']>t['maximum_off_axis_residual']:
                    reasons.append('neutral_not_noop:'+cid)
            elif target:
                positives.append(row)
                if (row['initial_bias']<=t['noop_bias_ceiling'] or row['improvement']<=0
                        or row['improvement']<t['minimum_bias_improvement'] or any(row[k]>t[k] for k in METRICS)):
                    reasons.append('positive_gate_failed:'+cid)
        groups={p['scene_group'] for p in positives}
        if len(positives)<4 or len(groups)<4: reasons.append('insufficient_four_group_holdout_positives')
        if not neutral: reasons.append('missing_holdout_neutrals')
        decisions[key]=dict(status='technically_passed' if not reasons else 'unqualified',reasons=reasons,
            positive_cases=len(positives),positive_groups=len(groups),domains=sorted({p['domain'] for p in positives}))
    return decisions


def _evaluation(root,receipt,req,config,conditional,*,replay=False):
    sr,sealed,_=_seal(root,receipt,req,config,conditional,replay=replay);r=StudyReader()
    ref=r.cap(root/'evaluation.json');value=r.any(ref)
    fields(value,'schema_version freeze seal holdout evaluation_status directions created_at')
    if value['freeze']!=r.cap(root/'freeze-receipt.json') or value['seal']!=sr or timestamp(value['created_at'])<timestamp(sealed['created_at']):
        raise ProductionRefused('evaluation seal/time binding differs')
    any_direction=any(v['status']=='separated' for v in sealed['directions'].values())
    if any_direction:
        href,hindex,rows=_index(root,receipt,req,config,conditional,'holdout',seal_ref=sr,replay=replay)
        if timestamp(value['created_at'])<timestamp(hindex['created_at']): raise ProductionRefused('evaluation predates holdout results')
        if value['holdout']!=href or value['evaluation_status']!='evaluated' or value['directions']!=evaluate_rows(rows,sealed):
            raise ProductionRefused('holdout evaluation reduction differs')
    else:
        rows=[]
        if value['holdout'] is not None or value['evaluation_status']!='skipped_no_qualified_direction' or value['directions']!={}: 
            raise ProductionRefused('unqualified development must not open holdout')
    StudyReader().cap(ref);return ref,value,rows,sealed


def evaluate(root):
    with StudyLock(study_root(root)):
        root,receipt,req,config,conditional=_frozen(root)
        sr,sealed,_=_seal(root,receipt,req,config,conditional,replay=True)
        if (root/'evaluation.json').exists(): _,value,_,_=_evaluation(root,receipt,req,config,conditional)
        else:
            eval_intent=root/'evaluation-intent.json'
            expected=dict(schema_version=1,freeze=artifact(root/'freeze-receipt.json'),seal=sr)
            if eval_intent.exists() and StudyReader().any(eval_intent)!=expected: raise ProductionRefused('one-shot evaluation intent differs')
            put_json(eval_intent,expected)
            href=None;rows=[];state='skipped_no_qualified_direction'
            if any(v['status']=='separated' for v in sealed['directions'].values()):
                state='evaluated'
                if not (root/'holdout-index.json').exists():
                    refs=[_case_result(root,c,receipt,config,conditional,seal_ref=sr) for c in req['cases'] if c['split']=='holdout']
                    put_json(root/'holdout-index.json',dict(schema_version=1,freeze=expected['freeze'],seal=sr,cases=refs,created_at=now()))
                href,_,rows=_index(root,receipt,req,config,conditional,'holdout',seal_ref=sr,replay=True)
            value=dict(schema_version=1,**{k:expected[k] for k in ('freeze','seal')},holdout=href,
                evaluation_status=state,directions=evaluate_rows(rows,sealed) if rows else {},created_at=now())
            put_json(root/'evaluation.json',value)
    return dict(status='evaluated',evaluation_status=value['evaluation_status'],directions=value['directions'],ready_for_propose=False)


def qualification_reviews(root,rows,evaluation_ref,observations):
    """Actual full original/preview viewing, independently supplied after computation."""
    reviews={} if observations is None else StudyReader().any(observations)
    if observations is not None: fields(reviews,'schema_version evaluation cases')
    if reviews and (reviews['schema_version']!=1 or reviews['evaluation']!=evaluation_ref): raise ProductionRefused('qualification review evaluation differs')
    by_case={}
    for ref in reviews.get('cases',[]):
        r=StudyReader();review=r.any(ref);cid=review.get('candidate_id')
        if cid in by_case: raise ProductionRefused('duplicate qualification case observation')
        by_case[cid]=(ref,review)
    known={r['case']['case_id'] for r in rows}
    if set(by_case)-known: raise ProductionRefused('foreign qualification observation')
    passed=set();reasons=[]
    for result in rows:
        positive=[p for p in result['projections'] if p['natural_label']=='mild_color_bias' and
            (p['operation'],p['correction_direction'])==(p['projection_operation'],p['projection_direction'])]
        if not positive: continue
        cid=result['case']['case_id'];preview=result.get('preview')
        if preview is None or cid not in by_case: reasons.append('missing_actual_improvement_observation:'+cid);continue
        from .natural_candidate_records import validate_visual_review
        state=validate_visual_review(by_case[cid][1],preview,identity=cid)
        if state=='passed': passed.add(cid)
        else: reasons.append('unpassed_actual_improvement_observation:'+cid)
    return passed,reasons


def qualified_scope(dev,holdout,evaluation,passed):
    qualified=[];domain_sets=[]
    for op,d in DIRECTIONS:
        ev=evaluation['directions'].get(op+':'+d,{})
        positives=[p for r in dev+holdout for p in r['projections'] if p['natural_label']=='mild_color_bias'
            and (p['operation'],p['correction_direction'])==(op,d) and (p['projection_operation'],p['projection_direction'])==(op,d)]
        if ev.get('status')=='technically_passed' and positives and all(p['case_id'] in passed for p in positives):
            common={p['domain'] for r in dev for p in r['projections'] if p in positives}&set(ev['domains'])
            if common:
                qualified.append(dict(operation=op,correction_direction=d));domain_sets.append(common)
    # The profile schema authorizes a Cartesian product. Only its intersection
    # is evidenced for every retained direction; a union would expand scope.
    domains=set.intersection(*domain_sets) if domain_sets else set()
    return (sorted(qualified,key=lambda x:(x['operation'],x['correction_direction'])),sorted(domains)) if domains else ([],[])


def finalize(root,*,observations=None):
    with StudyLock(study_root(root)):
        root,receipt,req,config,conditional=_frozen(root)
        eref,evaluation,holdout,sealed=_evaluation(root,receipt,req,config,conditional,replay=True)
        dev_ref,_,dev=_index(root,receipt,req,config,conditional,'development')
        if dev_ref!=sealed['development']: raise ProductionRefused('development index changed during finalization')
        obsref=None if observations is None else StudyReader().cap(observations)
        passed,reasons=qualification_reviews(root,dev+holdout,eref,obsref)
        qualified,domains=qualified_scope(dev,holdout,evaluation,passed)
        result=dict(schema_version=1,status='qualified' if qualified and domains else 'unqualified',evaluation=eref,
            observations=obsref,qualified_directions=qualified if domains else [],qualified_domains=sorted(domains),
            reasons=reasons,profile=None,ready_for_propose=False,created_at=now())
        final_path=root/'finalization.json'
        if final_path.exists():
            old=StudyReader().any(final_path)
            if old['observations']!=obsref: raise ProductionRefused('finalization already bound; failed results retained')
            return old
        if result['status']=='qualified':
            profile=dict(schema_version=1,algorithm=ALGORITHM,purpose='offline_natural_repair_qualification',
                production_eligible=False,evidence_only=True,protocol=receipt['protocol'],inputs=receipt['inputs'],software=receipt['software'],
                conditional_profile=req['conditional_profile'],thresholds=artifact(root/'thresholds.SEALED.json'),evaluation=eref,
                qualified_domains=result['qualified_domains'],qualified_directions=result['qualified_directions'],
                limitations=LIMITATIONS,created_at=result['created_at'])
            result['profile']=put_json(root/'natural-repair-profile.json',profile)
        put_json(final_path,result)
    return result


def status(root):
    root,receipt,req,config,conditional=_frozen(root)
    stages=['frozen']
    if (root/'development-index.json').exists(): _index(root,receipt,req,config,conditional,'development');stages.append('measured')
    if (root/'threshold-seal-identity.json').exists(): _seal(root,receipt,req,config,conditional);stages.append('sealed')
    if (root/'evaluation.json').exists(): _evaluation(root,receipt,req,config,conditional);stages.append('evaluated')
    if (root/'finalization.json').exists(): stages.append(StudyReader().any(root/'finalization.json')['status'])
    return dict(status=stages[-1],stages=stages,ready_for_propose=False,root=str(root))
