"""Known-axis natural arithmetic and reductions, never media/qualification authority."""
import math

import numpy as np

from .color_repair import _profile
from .natural_repair_statistics import natural_bias_statistics,compare_natural_bias

DIRECTIONS=(('exposure','negative'),('wb_r','negative'),('wb_g','positive'),('wb_g','negative'))
THRESHOLDS=('noop_bias_ceiling','minimum_bias_improvement','maximum_frame_bias_regression',
            'maximum_off_axis_residual','maximum_temporal_bias_increase')
METRICS=('maximum_frame_bias_regression','maximum_off_axis_residual','maximum_temporal_bias_increase')
VECTORS={'exposure':(1.,1.,1.),'wb_r':(1.,-.5,-.5),'wb_g':(-.5,1.,-.5)}


def finite(value):
    if type(value) not in (int,float) or not math.isfinite(value): raise ValueError('finite non-Boolean scalar required')
    return value


def direction_key(operation,direction):
    if type(operation) is not str or type(direction) is not str or (operation,direction) not in DIRECTIONS:
        raise ValueError('one of four known conditional directions required')
    return operation+':'+direction


def validate_thresholds(value):
    if type(value) is not dict or set(value)!=set(THRESHOLDS): raise ValueError('five exact explicit natural thresholds required')
    for name in THRESHOLDS:
        v=finite(value[name])
        if name in ('noop_bias_ceiling','minimum_bias_improvement','maximum_off_axis_residual') and v<0:
            raise ValueError('nonnegative bias/improvement/residual threshold required')
    return value


def _result(status,*,operation,amplitude=None,reason=None,**values):
    return dict(status=status,operation=operation,amplitude=amplitude,
        correction_direction=None if amplitude in (None,0) else 'positive' if amplitude>0 else 'negative',
        reasons=[] if reason is None else [reason],ready_for_propose=False,**values)


def fit_natural_parameter(frames,*,operation,conditional_profile):
    """A bounded arithmetic primitive; callers must verify real authority separately."""
    if type(operation) is not str or operation not in VECTORS: raise ValueError('known natural axis required')
    qualified,bounds=_profile(conditional_profile)
    if type(frames) is not list or not 1<=len(frames)<=4096: raise ValueError('complete bounded frames required')
    if any(type(f) is dict and (f.get('status')!='measured' or
            type(f.get('features')) is dict and type(f['features'].get('valid_pairs')) is int and f['features']['valid_pairs']<81) for f in frames):
        return _result('abstained',operation=operation,reason='incomplete_full_frame_support',fit_pairs=0,frame_count=len(frames))
    natural_bias_statistics(frames,operation=operation) # Validate every frame/role, including unsampled rows.
    count=sum(r['pairs'] for f in frames for r in f['features']['roles'])
    selected=np.linspace(0,count-1,min(count,16384),dtype=np.int64)
    collected=[];offset=0
    for f in frames:
        for role in f['features']['roles']:
            local=selected[(selected>=offset)&(selected<offset+role['pairs'])]-offset
            collected.extend(role['log2_ratios'][int(i)] for i in local)
            offset+=role['pairs']
    vector=np.asarray(VECTORS[operation],dtype=np.float64)
    with np.errstate(all='raise'):
        logs=np.median(np.asarray(collected,dtype=np.float64),axis=0)
        amplitude=float(logs@vector/(vector@vector))
    if not math.isfinite(amplitude) or abs(amplitude)>8: raise ValueError('natural amplitude outside numerical domain')
    values=dict(fit_pairs=len(collected),frame_count=len(frames))
    if amplitude==0: return _result('noop',operation=operation,amplitude=0.,reason='zero_amplitude',**values)
    key=(operation,-1 if amplitude>0 else 1)
    if key not in qualified or (operation,'positive' if amplitude>0 else 'negative') not in DIRECTIONS:
        return _result('abstained',operation=operation,reason='unqualified_direction',**values)
    bound=bounds[key]
    if abs(amplitude)>bound['correction_amplitude_ceiling']:
        return _result('abstained',operation=operation,reason='correction_bound_exceeded',**values)
    return _result('estimated',operation=operation,amplitude=amplitude,correction_bound=dict(bound),**values)


def assess_natural_change(before,after,*,operation,thresholds):
    thresholds=validate_thresholds(thresholds)
    metrics=compare_natural_bias(before,after,operation=operation)
    # An unchanged source has zero regression/increase. Negative midpoints for
    # nonzero repairs cannot require an already stable source to improve.
    if (metrics['before']['bias_max_absolute']<=thresholds['noop_bias_ceiling']
            and all(metrics[k]<=max(0.,thresholds[k]) for k in METRICS)):
        return _result('noop',operation=operation,amplitude=0.,reason='stable_natural_bias',metrics=metrics)
    reasons=[]
    if metrics['improvement']<=0 or metrics['improvement']<thresholds['minimum_bias_improvement']:
        reasons.append('insufficient_strict_bias_improvement')
    for key in METRICS:
        if metrics[key]>thresholds[key]: reasons.append(key)
    return dict(status='abstained' if reasons else 'estimated',metrics=metrics,reasons=reasons,
        operation=operation,ready_for_propose=False)


def derive_natural_thresholds(cases,*,operation,direction):
    """Strict interval midpoint reduction. This never creates a qualified profile."""
    direction_key(operation,direction)
    if type(cases) is not list or not 1<=len(cases)<=4096: raise ValueError('bounded complete development records required')
    ids=set();positives=[];neutrals=[];reasons=[]
    for row in cases:
        if type(row) is not dict or any(type(row.get(k)) is not str or not row[k].strip() for k in ('case_id','scene_group','domain')):
            raise ValueError('explicit case/group/domain required')
        if row['case_id'] in ids: raise ValueError('duplicate development case')
        ids.add(row['case_id'])
        if row.get('projection_operation')!=operation or row.get('projection_direction')!=direction:
            raise ValueError('projection differs from requested fixed direction')
        label=row.get('natural_label')
        if label not in ('neutral','mild_color_bias','unsafe','not_comparable','unverified'):
            raise ValueError('known original natural label required')
        if label=='unverified': reasons.append('unresolved_case:'+row['case_id']);continue
        target=(label=='mild_color_bias' and row.get('operation')==operation and row.get('correction_direction')==direction)
        if label in ('unsafe','not_comparable') or label=='mild_color_bias' and not target:
            if row.get('status')!='refused': reasons.append('negative_case_not_refused:'+row['case_id'])
            continue
        if row.get('status')!='measured': reasons.append('unmeasured_case:'+row['case_id']);continue
        for key in ('initial_bias','improvement',*METRICS): finite(row.get(key))
        if row['initial_bias']<0 or row['maximum_off_axis_residual']<0: raise ValueError('nonnegative absolute bias/residual required')
        if label=='neutral': neutrals.append(row)
        elif target: positives.append(row)
    groups={p['scene_group'] for p in positives}
    if len(positives)<4 or len(groups)<4: reasons.append('insufficient_four_group_natural_positives')
    if not neutrals: reasons.append('missing_neutral_cases')
    answer=dict(status='unqualified',thresholds=None,reasons=reasons,positive_cases=len(positives),
        positive_groups=len(groups),neutral_cases=len(neutrals),requested_cases=len(cases),ready_for_propose=False)
    if reasons: return answer
    if any(p['improvement']<=0 for p in positives):
        answer['reasons'].append('positive_has_no_strict_improvement');return answer
    ranges={
        'noop_bias_ceiling':(max(p['initial_bias'] for p in neutrals),min(p['initial_bias'] for p in positives)),
        'minimum_bias_improvement':(max(0.,max(p['improvement'] for p in neutrals)),min(p['improvement'] for p in positives)),
    }
    control_kinds={
        'maximum_frame_bias_regression':('wrong_direction','overcorrection'),
        'maximum_off_axis_residual':('mixed_axis','local'),
        'maximum_temporal_bias_increase':('temporal',),
    }
    for metric,kinds in control_kinds.items():
        values=[]
        for kind in kinds:
            controls=[]
            for row in positives+neutrals:
                if type(row.get('controls')) is not dict or type(row['controls'].get(kind)) is not list:
                    raise ValueError('explicit harmful control arrays required')
                controls.extend(row['controls'][kind])
            if not controls:
                answer['reasons'].append('missing_harmful_control:'+kind);continue
            values.extend(finite(c.get(metric)) for c in controls)
        if values: ranges[metric]=(max(p[metric] for p in positives),min(values))
    if answer['reasons']: return answer
    for name,(lo,hi) in ranges.items():
        if not lo<hi: answer['reasons'].append('no_strict_separation:'+name)
    if answer['reasons']: return answer
    derived={name:lo/2+hi/2 for name,(lo,hi) in ranges.items()}
    validate_thresholds(derived)
    answer.update(status='separated',thresholds=derived,separations={name:dict(lower=lo,upper=hi) for name,(lo,hi) in ranges.items()})
    return answer
