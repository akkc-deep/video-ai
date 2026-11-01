"""Exact natural candidate contracts and original visual declarations."""
from pathlib import Path

from ._scene_continuity_io import uid,local
from .natural_study_records import StudyReader,fields,text,timestamp,bind_manifest,read_author_observations
from .production_state import ProductionRefused

REQUEST=('schema_version run_id candidate_id policy material epoch assessment pair_manifest conditional_profile '
    'natural_profile precheck operation operator_basis revision_of requested_at reason')
PRECHECK=('schema_version source_kind run_id material epoch assessment source pair_manifest observations review_method '
    'reviewer viewed_at playback_ranges color_issue operation correction_direction operator_basis '
    'target_reference_confirmed subject_structure_intact motion_intact intentional_lighting_change responses')
VISUAL_CHECKS=('subject_identity','appearance_structure','color_improvement','material_preservation',
    'motion_process','camera_path','no_new_flicker','native_timing')
REVIEW=('schema_version kind candidate_id source candidate playback before_report after_report review_method reviewer viewed_at '
    'playback_ranges start_observation process_observation end_observation quality_observation checks responses issues verdict')


def schema(value,names):
    fields(value,names)
    if type(value['schema_version']) is not int or value['schema_version']!=1: raise ProductionRefused('natural candidate schema1 required')
    return value


def _risk_once(risk,expected,seen):
    # JSON object key order is not identity. Use the actual expected item so
    # reordered copies cannot fill two slots and hide an unanswered concern.
    try: index=expected.index(risk)
    except ValueError as error: raise ProductionRefused('foreign natural observation risk') from error
    if index in seen: raise ProductionRefused('repeated natural observation risk')
    seen.add(index)


def validate_visual_review(value,expected,*,identity):
    schema(value,REVIEW)
    if value['kind']!='natural_repair_visual_review_v1' or value['candidate_id']!=identity:
        raise ProductionRefused('natural actual review producer differs')
    r=StudyReader()
    for k in ('source','candidate','playback','before_report','after_report'):
        if value[k]!=expected[k]: raise ProductionRefused('natural review media/report differs:'+k)
        r.cap(value[k])
    if value['review_method'] not in ('human_video','agent_video'): raise ProductionRefused('actual complete native video playback required')
    text(value['reviewer'])
    if timestamp(value['viewed_at'])<timestamp(expected['created_at']): raise ProductionRefused('review predates completed candidate')
    ranges=[dict(media=m,start_frame=0,end_frame=expected['frames'],fps='16/1') for m in (expected['source'],expected['playback'])]
    if value['playback_ranges']!=ranges: raise ProductionRefused('actual complete source/playback range required')
    for k in ('start_observation','process_observation','end_observation','quality_observation'): text(value[k])
    fields(value['checks'],VISUAL_CHECKS)
    if any(s not in ('passed','failed','unverified') for s in value['checks'].values()): raise ProductionRefused('explicit visual check states required')
    risks=expected['risks'];responses=value['responses']
    if type(responses) is not list or len(responses)!=len(risks): raise ProductionRefused('all before/after risks need actual responses')
    states=list(value['checks'].values());seen=set()
    for row in responses:
        fields(row,'risk disposition reason references');text(row['reason'])
        _risk_once(row['risk'],risks,seen)
        if type(row['references']) is not list: raise ProductionRefused('actual evidence array required')
        for ref in row['references']: r.cap(ref)
        if row['disposition']=='confirmed_issue': states.append('failed')
        elif row['disposition']=='unverified': states.append('unverified')
        elif row['disposition']=='not_observed_in_full_playback':
            if any(s!='passed' for s in value['checks'].values()): raise ProductionRefused('not-observed requires complete passed checks')
        elif row['disposition']=='resolved_color':
            risk=row['risk']
            if (risk.get('phase')!='before' or risk.get('detector_id') not in ('seam_color','local_color','color_drift','cumulative_color')
                    or expected['after_report'] not in row['references'] or value['checks']['color_improvement']!='passed'):
                raise ProductionRefused('resolved color requires actual after evidence and original color risk')
        else: raise ProductionRefused('unsupported natural risk disposition')
    verdict='failed' if 'failed' in states else 'unverified' if 'unverified' in states else 'passed'
    if value['verdict']!=verdict: raise ProductionRefused('visual verdict hides a failed/unknown check')
    if type(value['issues']) is not list or (verdict=='passed' and value['issues']) or (verdict=='failed' and not value['issues']):
        raise ProductionRefused('visual issues contradict verdict')
    for issue in value['issues']:
        fields(issue,'check media frames description');text(issue['description'])
        span=issue['frames']
        if (issue['check'] not in VISUAL_CHECKS or issue['media'] not in (expected['source'],expected['playback'])
                or type(span) is not list or len(span)!=2 or any(type(x) is not int for x in span)
                or not 0<=span[0]<span[1]<=expected['frames']): raise ProductionRefused('visual issue media/range differs')
    r.verify_all();return verdict


def read_review_receipt(path,expected,*,identity):
    """The retained original bytes, hash directory and receipt must all agree."""
    path=Path(path);r=StudyReader();receipt=r.any(path)
    schema(receipt,'schema_version observation verdict created_at')
    original=r.cap(receipt['observation']);raw=r.cap(path.parent/'raw.json')
    if (path.name!='receipt.json' or path.parent.name!=original['sha256']
            or path.parent.parent.name!='reviews' or path.parent.parent.parent.name!=identity
            or (raw['bytes'],raw['sha256'])!=(original['bytes'],original['sha256'])):
        raise ProductionRefused('review receipt differs from retained original observation bytes')
    row=r.any(raw);verdict=validate_visual_review(row,expected,identity=identity)
    if verdict=='unverified' or receipt['verdict']!=verdict or timestamp(receipt['created_at'])<timestamp(row['viewed_at']):
        raise ProductionRefused('review receipt verdict/time differs from original bytes')
    r.verify_all();return verdict,row


def has_noncolor_failure(row):
    colors={'seam_color','local_color','color_drift','cumulative_color'}
    return (any(v=='failed' for k,v in row['checks'].items() if k!='color_improvement')
        or any(i['check']!='color_improvement' for i in row['issues'])
        or any(r['disposition']=='confirmed_issue' and r['risk'].get('detector_id') not in colors for r in row['responses']))


def validate_request(value,run,context,reader):
    schema(value,REQUEST);uid(value['candidate_id']);timestamp(value['requested_at']);text(value['reason']);text(value['operator_basis'])
    if value['run_id']!=run.name or value['policy']!='research_candidate_natural_v1' or value['operation'] not in ('exposure','wb_r','wb_g'):
        raise ProductionRefused('explicit research natural source/policy/known axis required')
    for key in ('material','epoch','assessment'):
        expected=context['commit'] if key=='material' else context[key]
        if expected is None or value[key]!=expected: raise ProductionRefused('current research '+key+' differs')
        reader.cap(value[key])
    for key in ('pair_manifest','conditional_profile','precheck'): reader.cap(value[key])
    if value['natural_profile'] is not None: reader.cap(value['natural_profile'])
    if value['revision_of'] is not None: reader.cap(value['revision_of'])
    assessment=reader.any(context['assessment'])
    if assessment['manifest']!=value['pair_manifest']: raise ProductionRefused('candidate ordinary assessment manifest differs')
    case=dict(manifest=value['pair_manifest'])
    bind_manifest(case,context,reader)
    return value


def source_registration(context,reader):
    commit=reader.any(context['commit']);index_ref=commit['origin']['source_index'];index=reader.any(index_ref)
    result=reader.any(index['result'])
    cid=text(result.get('case_id'))
    # Generation result is independent of caller-supplied Precheck/case IDs.
    return cid,index_ref,result


def registered_history(context,reader,submitted):
    cid,index_ref,result=source_registration(context,reader)
    from .natural_study_records import require_complete_observations
    require_complete_observations(dict(case_id=cid,observations=submitted),context,reader)
    found={}
    for ref in submitted:
        row=reader.any(ref)
        if row.get('case_id')!=cid: raise ProductionRefused('original observation case differs')
        found[reader.cap(ref)['sha256']]=ref
    if len(found)>512: raise ProductionRefused('resource_limit: natural observation history')
    supplied={r['sha256'] for r in submitted}
    if not set(found)<=supplied: raise ProductionRefused('precheck omits registered original observation history')
    if not submitted: raise ProductionRefused('actual original observations required')
    return dict(case_id=cid,observations=submitted),result


def validate_precheck(value,request,context,reader):
    schema(value,PRECHECK)
    if value['source_kind']!='research_wan_material_v1' or value['run_id']!=request['run_id']:
        raise ProductionRefused('precheck must declare actual research source')
    for k in ('material','epoch','assessment','pair_manifest','operation','operator_basis'):
        if value[k]!=request[k]: raise ProductionRefused('precheck binding differs:'+k)
    if value['source']!=context['source'] or value['review_method'] not in ('human_video','agent_video','human_remote_video'):
        raise ProductionRefused('precheck actual source playback required')
    for k,want in [('target_reference_confirmed',True),('subject_structure_intact',True),('motion_intact',True),('intentional_lighting_change',False)]:
        if value[k] is not want: raise ProductionRefused('precheck semantic gate:'+k)
    if value['correction_direction'] not in ('positive','negative'): raise ProductionRefused('precheck known correction direction required')
    text(value['color_issue']);text(value['reviewer'])
    if timestamp(value['viewed_at'])<timestamp(reader.any(context['assessment'])['created_at']):
        raise ProductionRefused('precheck predates current assessment')
    if value['playback_ranges']!=[dict(media=context['source'],start_frame=0,end_frame=len(context['frames']),fps='16/1')]:
        raise ProductionRefused('precheck complete original playback required')
    if type(value['observations']) is not list: raise ProductionRefused('all original observations required')
    case,_=registered_history(context,reader,value['observations'])
    author=read_author_observations(case,context,reader)
    from .natural_study_measure import safe_author
    if not safe_author(author) or (author['operation'],author['correction_direction'])!=(request['operation'],value['correction_direction']):
        raise ProductionRefused('unknown or historical non-color failure cannot authorize a natural fit')
    from .scene_continuity_records import derive_concerns
    report=reader.any(reader.any(context['assessment'])['report']);risks=derive_concerns(report)
    expected=[dict(kind='observation',artifact=r) for r in value['observations']]+[dict(kind='ordinary',concern=c) for c in risks]
    responses=value['responses']
    if type(responses) is not list or len(responses)!=len(expected): raise ProductionRefused('precheck risk/history responses incomplete')
    seen=set()
    for response in responses:
        fields(response,'risk disposition reason references');text(response['reason'])
        risk=response['risk']
        _risk_once(risk,expected,seen)
        if response['disposition'] not in ('confirmed_color','not_observed_in_full_playback'):
            raise ProductionRefused('precheck unresolved risk cannot authorize repair')
        if response['disposition']=='confirmed_color' and risk['kind']=='ordinary' and risk['concern']['detector_id'] not in ('seam_color','local_color','color_drift','cumulative_color'):
            raise ProductionRefused('non-color ordinary risk cannot be called a color issue')
        for ref in response['references']: reader.cap(ref)
    return author
