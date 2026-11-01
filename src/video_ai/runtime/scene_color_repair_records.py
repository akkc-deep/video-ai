"""Read-only admission of independent, non-production color repair candidates."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from .production_state import ProductionRefused, object_fields, integer
from ._scene_continuity_io import Reader, artifact, verify, uid, instant, nonempty, local, run_for

REQUEST = 'schema_version run_id candidate_id policy clip_id source_clip assessment profile manifest operation context revision_of requested_at reason'
CONTEXT = 'comparable intentional_lighting_change confirmed_motion_defect subject_structure_intact operator_basis review'
PRECHECK = 'schema_version run_id clip_id assessment source_clip video_observation reviewer reviewed_at color_issue operation operator_basis subject_structure_intact motion_intact intentional_lighting_change responses'
BINDING = 'source_clip source mapping last_frame selected_image parent_chain epoch assessment manifest precheck profile profile_closure revision_of'
INTENT = 'schema_version run_id candidate_id request binding engine created_at'
TERMINAL = 'schema_version run_id candidate_id intent status fit media pair_report before_report after_report closure failure finished_at'
REVIEW = 'schema_version run_id candidate_id terminal source candidate playback parent_chain before_report after_report review_method reviewer viewed_at playback_ranges start_observation process_observation end_observation quality_observation checks responses verdict issues'
CHECKS = 'subject_identity appearance_structure color_improvement material_preservation motion_process camera_path parent_join no_new_flicker native_timing'
COLOR_DETECTORS = {'seam_color','local_color','color_drift','cumulative_color'}


def schema(value, fields, *, run_id=None):
    object_fields(value, fields.split(), 'color repair record')
    if type(value.get('schema_version')) is not int or value['schema_version'] != 1:
        raise ProductionRefused('unsupported color repair schema')
    if run_id is not None and value.get('run_id') != run_id:
        raise ProductionRefused('color repair run differs')
    return value


def timestamp(value, *, after=None):
    at=instant(value)
    if at>datetime.now(timezone.utc) or (after is not None and at<instant(after)):
        raise ProductionRefused('repair timestamp outside evidence window')
    return at


def closure(refs):
    result={}
    for ref in refs:
        verify(ref,runtime=False,empty=ref['bytes']==0)
        if ref['path'] in result and result[ref['path']]!=ref:
            raise ProductionRefused('conflicting repair artifact identity')
        result[ref['path']]=ref
    return [result[p] for p in sorted(result)]


def validate_repair_request(value, expected):
    schema(value,REQUEST,run_id=expected['run_id']);uid(value['candidate_id'])
    nonempty(value['clip_id']);nonempty(value['reason']);timestamp(value['requested_at'])
    if value['policy']!='research_candidate_v1' or value['operation'] not in ('exposure','wb_r','wb_g','wb_b'):
        raise ProductionRefused('unsupported research repair policy or operation')
    ctx=value['context'];object_fields(ctx,CONTEXT.split(),'repair context')
    for name,want in [('comparable',True),('intentional_lighting_change',False),
                      ('confirmed_motion_defect',False),('subject_structure_intact',True)]:
        if type(ctx[name]) is not bool or ctx[name] is not want:
            raise ProductionRefused('repair context gate: '+name)
    nonempty(ctx['operator_basis']);verify(ctx['review'])
    for key in ('source_clip','assessment','profile','manifest'):verify(value[key])
    if value['revision_of'] is not None:verify(value['revision_of'])
    for key in ('candidate_id','clip_id','source_clip','assessment'):
        if key in expected and value[key]!=expected[key]:raise ProductionRefused('repair request binding differs: '+key)
    return deepcopy(value)


def require_production_repair_origin(value):
    """Every production boundary calls this before accepting a media origin."""
    if isinstance(value,(str,Path)):
        spelling=str(value).replace('\\','/').lower()
        if '/scene-color-repair/' in spelling or spelling.endswith('/scene-color-repair'):
            raise ProductionRefused('research color repair candidate has no production eligibility')
    elif isinstance(value,dict):
        if (value.get('policy')=='research_candidate_v1' or value.get('kind')=='adopt_color_repair'
                or value.get('state')=='research_candidate_reviewed'
                or value.get('algorithm') in ('constant_color_repair_v1','AI_conditional_constant_color_repair_v1')
                or ('candidate_id' in value and value.get('production_eligible') is False)):
            raise ProductionRefused('research color repair origin cannot enter production')
        for item in value.values():require_production_repair_origin(item)
    elif isinstance(value,(list,tuple)):
        for item in value:require_production_repair_origin(item)


def load_repair_profile(path, *, reader):
    from ._scene_color_repair_profile import load_profile
    return load_profile(path,reader=reader)


def validate_precheck(value, request, assessment, video_expected, *, reader):
    schema(value,PRECHECK,run_id=request['run_id'])
    for key in ('clip_id','assessment','source_clip','operation'):
        if value[key]!=request[key]:raise ProductionRefused('precheck binding differs: '+key)
    if value['operator_basis']!=request['context']['operator_basis']:
        raise ProductionRefused('precheck operator basis differs')
    for name,want in [('subject_structure_intact',True),('motion_intact',True),('intentional_lighting_change',False)]:
        if type(value[name]) is not bool or value[name] is not want:raise ProductionRefused('precheck motion/structure/lighting gate')
    nonempty(value['color_issue']);nonempty(value['reviewer'])
    from .scene_clip_observations import validate_scene_clip_observation
    from .manifest import now
    video=validate_scene_clip_observation(reader.read(value['video_observation']),video_expected,now=now())
    if video['review_method'] not in ('human_video','agent_video') or video['reviewer']!=value['reviewer']:
        raise ProductionRefused('precheck requires same author actual full playback')
    for name,state in video['checks'].items():
        if name not in ('color_clothing','time_lighting') and state not in ('passed',None):
            raise ProductionRefused('repair cannot conceal non-color playback defect')
    timestamp(value['reviewed_at'],after=max(instant(video['viewed_at']),instant(assessment['created_at'])))
    concerns={c['concern_id']:c for c in assessment['concerns']}
    if type(value['responses']) is not list or len(value['responses'])!=len(concerns):
        raise ProductionRefused('precheck concerns incomplete')
    seen=set()
    for row in value['responses']:
        object_fields(row,'concern_id disposition reason references'.split(),'precheck response')
        key=row['concern_id']
        if key not in concerns or key in seen:raise ProductionRefused('precheck concern unknown or repeated')
        seen.add(key);nonempty(row['reason'])
        if type(row['references']) is not list:raise ProductionRefused('precheck references must be list')
        for ref in row['references']:verify(ref)
        disposition=row['disposition'];color=concerns[key]['detector_id'] in COLOR_DETECTORS
        if disposition=='confirmed_issue' and color:continue
        if disposition=='not_observed_in_full_playback':continue
        if disposition=='explained_change':
            from .scene_continuity_records import _explanation
            _explanation(row,concerns[key],assessment,reader);continue
        raise ProductionRefused('precheck confirms non-color defect or lacks full risk response')
    return value


def validate_revision(request, *, run, reader):
    previous=request['revision_of'];seen={request['candidate_id']}
    while previous is not None:
        p=verify(previous);value=reader.read(previous)
        if p.name=='terminal.json':
            schema(value,TERMINAL,run_id=run.name)
            if p!=run/'production/scene-color-repair/candidates'/uid(value['candidate_id'])/'terminal.json':
                raise ProductionRefused('repair revision terminal path differs')
            previous=value['intent'];p=verify(previous);value=reader.read(previous)
        schema(value,INTENT,run_id=run.name);cid=uid(value['candidate_id'])
        if p!=run/'production/scene-color-repair/candidates'/cid/'intent.json' or cid in seen:
            raise ProductionRefused('repair revision cycle or foreign intent')
        seen.add(cid);old=reader.read(value['request'])
        if old['clip_id']!=request['clip_id'] or old['source_clip']!=request['source_clip']:
            raise ProductionRefused('repair revision raw source or clip differs')
        previous=old['revision_of']


def load_scene_color_repair_progress(frozen, *, candidate_id=None):
    run=run_for(frozen);root=run/'production/scene-color-repair/candidates';reader=Reader()
    if candidate_id is not None:uid(candidate_id)
    result=dict(schema_version=1,run_id=run.name,candidates=[],production_ready=False)
    for folder in sorted(root.iterdir()) if root.exists() else []:
        cid=uid(folder.name)
        if not folder.is_dir():raise ProductionRefused('unexpected repair candidate entry')
        if candidate_id is not None and cid!=candidate_id:continue
        row=dict(candidate_id=cid,intent=None,terminal=None,review=None,state='awaiting_precheck',reasons=[],revision_of=None)
        try:
            if not (folder/'intent.json').exists():
                if (folder/'request.json').exists():
                    req=reader.read(folder/'request.json');validate_repair_request(req,{'run_id':run.name,'candidate_id':cid})
                    row['revision_of']=req['revision_of']
                result['candidates'].append(row);continue
            intent=reader.read(folder/'intent.json');schema(intent,INTENT,run_id=run.name)
            if intent['candidate_id']!=cid:raise ProductionRefused('repair intent ID differs')
            row['intent']=artifact(folder/'intent.json');req=reader.read(intent['request'])
            validate_repair_request(req,{'run_id':run.name,'candidate_id':cid});validate_revision(req,run=run,reader=reader)
            row['revision_of']=req['revision_of']
            for key,ref in intent['binding'].items():
                if key in ('parent_chain','profile_closure'):
                    for item in ref:
                        if key=='profile_closure':verify(item,runtime=False,empty=item['bytes']==0)
                        else:
                            for k in ('clip','mapping','last_frame','video_observation'):verify(item[k])
                elif ref is not None:verify(ref)
            from ._scene_color_repair_validation import validate_saved_candidate, current_binding
            current_binding(frozen,intent,reader=reader)
            if not (folder/'terminal.json').exists():row['state']='interrupted'
            else:
                terminal=validate_saved_candidate(frozen,folder,reader=reader)
                row.update(terminal=artifact(folder/'terminal.json'),state=terminal['status'])
                if terminal['status']=='awaiting_review':
                    from ._scene_color_repair_validation import review_state
                    row['state'],row['review']=review_state(frozen,folder,reader=reader)
        except (ValueError,OSError,RuntimeError,KeyError,TypeError) as exc:
            row.update(state='stale',reasons=[str(exc)])
        result['candidates'].append(row)
    return result
