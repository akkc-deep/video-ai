"""Byte-bound candidate, full playback and current-epoch checks; never writes."""
from copy import deepcopy
from datetime import datetime,timezone
from fractions import Fraction
from pathlib import Path

from .production_state import ProductionRefused,object_fields,integer
from ._scene_continuity_io import Reader,artifact,verify,uid,nonempty,run_for
from . import scene_color_repair_records as r


def resolve_context(frozen,units=None,timeline=None,*,paths=None,lock=None):
    if units is None:
        from ._scene_revision_origins import common
        from ..planning.production_timeline import ProductionTimeline
        prefix=common(frozen);units=prefix['units'];timeline=ProductionTimeline.from_dict(prefix['timeline'])
    from .scene_clip_records import scene_context,collect_progress
    context=scene_context(frozen,units,timeline,paths=paths,lock=lock)
    _,source=collect_progress(context)
    return context,source


def current_assessment(frozen,context,source,clip_id,*,reader):
    from . import scene_continuity_records as continuity
    ids=[row['budget']['clip_id'] for row in context['rows']]
    epochs,pending=continuity._epochs(frozen,ids,reader)
    if not epochs or pending:raise ProductionRefused('repair requires a current complete continuity epoch')
    head=epochs[-1];matches=[]
    for path in sorted((run_for(frozen)/'production/scene-continuity/jobs').glob('*/assessment.json')):
        value=reader.read(path)
        if value.get('epoch')==head['artifact'] and value.get('clip_id')==clip_id:matches.append(path)
    if len(matches)!=1:raise ProductionRefused('repair requires exactly one current clip assessment')
    path=matches[0];value=continuity._assessment(path,head,context,source,reader)
    return value,artifact(path),head,epochs


def require_color_only_history(record,observation_refs,video_expected,*,reader):
    """A new precheck cannot clear another retained original process defect."""
    from .scene_clip_observations import validate_scene_clip_observation
    from .manifest import now
    refs=list(observation_refs);rejected=record.get('rejected')
    if rejected is not None:refs.append(rejected['observation'])
    seen=set();latest=None
    for ref in refs:
        key=(ref['path'],ref['sha256'])
        if key in seen:continue
        seen.add(key);reader.check()
        video=validate_scene_clip_observation(reader.read(ref),video_expected,now=now())
        at=r.timestamp(video['viewed_at']);latest=max(latest,at) if latest else at
        if (any(state=='failed' for name,state in video['checks'].items() if name not in ('color_clothing','time_lighting')) or
                any(issue['check'] not in ('color_clothing','time_lighting') for issue in video['issues'])):
            raise ProductionRefused('retained original non-color motion/structure defect forbids color repair')
    return latest


def _continuity_color_only_history(context,source,binding,epochs,*,reader,seen=None):
    """Preserve confirmed non-color risks across epochs and imported origins."""
    from . import scene_continuity_records as continuity
    from .manifest import now
    run=context['store'].run_dir;seen=set() if seen is None else seen
    if str(run) in seen:raise ProductionRefused('repair history origin cycle')
    seen.add(str(run));candidate=continuity._candidate(binding)
    by_epoch={e['artifact']['path']:e for e in epochs}
    for path in sorted((run/'production/scene-continuity/reviews').glob('*.json')):
        ref=artifact(path);value=reader.read(ref)
        if path.stem!=ref['sha256']:raise ProductionRefused('original continuity review archive name differs')
        historical=reader.read(value['assessment'])
        if historical['binding']['scene_id']!=binding['scene_id']:continue
        old=continuity._candidate(historical['binding'])
        if old!=candidate[:len(old)]:continue
        epoch=by_epoch.get(historical['epoch']['path'])
        if epoch is None or epoch['artifact']!=historical['epoch']:raise ProductionRefused('repair risk history lacks verified epoch')
        assessed=continuity._assessment(Path(value['assessment']['path']),epoch,context,source,reader,historical=True)
        expected=continuity._review_expected(context,source,assessed,Path(value['assessment']['path']),reader)
        continuity.validate_continuity_review(value,expected,now=now())
        concerns={c['concern_id']:c for c in assessed['concerns']}
        if any(row['disposition']=='confirmed_issue' and concerns[row['concern_id']]['detector_id'] not in r.COLOR_DETECTORS for row in value['responses']):
            raise ProductionRefused('retained confirmed non-color continuity issue forbids repair')
        require_color_only_history(source[assessed['clip_id']],[value['video_observation']],expected['video_expected'],reader=reader)
        if value['prefix_observation']!=value['video_observation']:
            prefix=continuity._read_prefix_original(value['prefix_observation'],run,reader)
            if any(state=='failed' for name,state in prefix['checks'].items() if name not in ('color_lighting','cumulative_color')):
                raise ProductionRefused('retained non-color prefix defect forbids repair')
    frozen=context['frozen'];cid=binding['clip_id']
    if 'scene_revision' in getattr(frozen,'options',{}):
        from .scene_revision_records import require_scene_revision
        proof=require_scene_revision(frozen)
        if 'clip:'+cid in proof['imports']:
            from .production_inputs import load_frozen_inputs
            original=load_frozen_inputs(proof['source_run']);old_context,old_source=resolve_context(original)
            old_binding=continuity._binding(old_context,old_source,cid)
            ids=[row['budget']['clip_id'] for row in old_context['rows']]
            old_epochs,_=continuity._epochs(original,ids,reader,current=False)
            _continuity_color_only_history(old_context,old_source,old_binding,old_epochs,reader=reader,seen=seen)


def capture_binding(frozen,context,source,request,profile_closure,*,reader):
    from . import scene_continuity_records as continuity
    from .scene_clip_observations import validate_scene_clip_observation
    from .manifest import now
    assessment,ref,head,epochs=current_assessment(frozen,context,source,request['clip_id'],reader=reader)
    if ref!=request['assessment']:raise ProductionRefused('repair assessment is stale')
    original=assessment['binding']['clips'][-1]
    if original['clip_record']!=request['source_clip']:raise ProductionRefused('repair raw clip differs')
    video_expected=continuity._review_expected(context,source,assessment,Path(ref['path']),reader)['video_expected']
    precheck=r.validate_precheck(reader.read(request['context']['review']),request,assessment,video_expected,reader=reader)
    observations=[artifact(path) for path in sorted((Path(original['clip_record']['path']).parent/'observations').glob('*.json'))]
    latest=require_color_only_history(source[request['clip_id']],observations,video_expected,reader=reader)
    if latest is not None and r.timestamp(precheck['reviewed_at'])<latest:
        raise ProductionRefused('repair precheck predates retained original playback evidence')
    _continuity_color_only_history(context,source,assessment['binding'],epochs,reader=reader)
    parents=[]
    for row in assessment['binding']['clips'][:-1]:
        record=source[row['clip_id']]
        accepted=record.get('accepted')
        if not accepted:raise ProductionRefused('repair prefix lacks historical actual playback')
        observation=accepted['observation']
        video=validate_scene_clip_observation(reader.read(observation),
            {'template':record['template'],'created_at':record['clip']['created_at']},now=now())
        if video['reviewer']!=precheck['reviewer'] or video['verdict']!='passed':
            raise ProductionRefused('repair prefix requires same author complete passed playback')
        r.timestamp(precheck['reviewed_at'],after=video['viewed_at'])
        parents.append(dict(clip_id=row['clip_id'],clip=row['clip_record'],mapping=row['mapping'],
            last_frame=row['last_frame'],video_observation=observation))
    manifest=reader.read(request['manifest'])
    before_manifest=reader.read(assessment['manifest'])
    if before_manifest['context'] is not None:
        declarations=reader.read({k:before_manifest['context'][k] for k in ('path','bytes','sha256')})
        ids={f['frame_id'] for c in before_manifest['clips'] if c['clip_id']==request['clip_id'] for f in c['frames']}
        if any(e['kind']=='lighting' and ids.intersection(e['frame_ids']) for e in declarations['events']):
            raise ProductionRefused('frozen intentional lighting conflicts with repair')
    return dict(source_clip=original['clip_record'],source=original['source'],mapping=original['mapping'],
        last_frame=original['last_frame'],selected_image={k:assessment['binding']['selected_image'][k] for k in ('path','bytes','sha256')},
        parent_chain=parents,epoch=head['artifact'],assessment=ref,manifest=request['manifest'],
        precheck=request['context']['review'],profile=request['profile'],profile_closure=profile_closure,revision_of=request['revision_of'])


def current_binding(frozen,intent,*,reader,context=None,source=None):
    if context is None:context,source=resolve_context(frozen)
    req=reader.read(intent['request'])
    expected=capture_binding(frozen,context,source,req,intent['binding']['profile_closure'],reader=reader)
    if expected!=intent['binding']:raise ProductionRefused('repair binding or epoch changed')
    for ref in intent['engine']['implementation']:verify(ref,runtime=False)
    for ref in intent['binding']['profile_closure']:verify(ref,runtime=False,empty=ref['bytes']==0)
    from ._scene_color_repair_engine import verify_engine
    folder=Path(intent['request']['path']).parent
    if (folder/'engine/manifest.json').exists():verify_engine(folder,intent,reader=reader)
    else:
        from ._scene_color_repair_engine import capture_engine
        if capture_engine()['engine']!=intent['engine']:raise ProductionRefused('partial repair engine changed')
    return expected


def validate_pair_manifest(manifest,request,binding,assessment,*,config,reader):
    from ..media._continuity_schema import validate_continuity_manifest
    from ..media.colorimetry import load_color_analysis_set
    manifest=validate_continuity_manifest(manifest)
    cid=request['clip_id'];mapping=reader.read(binding['mapping']);count=mapping['retained_frames']
    if (manifest['scope']!='clip' or manifest['scene_id']!=assessment['binding']['scene_id'] or
            manifest['domain']!=dict(genre=reader.read(assessment['manifest'])['domain']['genre'],source_kind='generated') or
            manifest['timeline']!=dict(fps_num=16,fps_den=1) or manifest['profile'] is not None or
            len(manifest['clips'])!=1 or manifest['clips'][0]['clip_id']!=cid or
            len(manifest['clips'][0]['frames'])!=count or len(manifest['references'])!=1 or
            manifest['references'][0]['frame_id']!='repair_clean_reference'):
        raise ProductionRefused('repair pair manifest scope or complete coverage differs')
    target=manifest['clips'][0]['frames'];reference=manifest['references'][0]
    original=reader.read(assessment['manifest'])
    old=next(c for c in original['clips'] if c['clip_id']==cid)['frames']
    if target!=old:raise ProductionRefused('repair frames differ from original complete assessment')
    regions=reader.read({k:manifest['regions'][k] for k in ('path','bytes','sha256')})
    region_ids=sorted(reg['region_id'] for reg in regions['regions'])
    if not region_ids:raise ProductionRefused('repair needs explicit stable regions')
    required=[dict(comparison_id=f'repair_adj_{i:06d}',kind='adjacent',left=target[i-1]['frame_id'],right=target[i]['frame_id'],region_ids=region_ids)
              for i in range(1,count)]
    required += [dict(comparison_id=f'repair_ref_{i:06d}',kind='reference',left=reference['frame_id'],right=f['frame_id'],region_ids=region_ids)
                 for i,f in enumerate(target)]
    if manifest['comparisons']!=required:raise ProductionRefused('repair reference/adjacent coverage or order differs')
    anchors={target[0]['record']['path'],reference['record']['path']}
    for reg in regions['regions']:
        if not anchors.issubset({a['frame']['path'] for a in reg['anchors']}):
            raise ProductionRefused('repair requires independent reference and first frame region anchors')
    refs=[f['record']['path'] for f in target]+[reference['record']['path']]
    with load_color_analysis_set(refs,config=config,timeout=remaining(reader)) as colors:
        data=colors.frames
        for i,item in enumerate(data[:-1]):
            rec=item['record'];row=rec['mapping']
            if rec['status']!='ready' or {k:rec['source'][k] for k in ('path','bytes','sha256')}!=binding['source']:
                raise ProductionRefused('repair source requires proven sRGB')
            if (row is None or row['asset_frame_index']!=i or row['retained_frame_index']!=i or row['clip_id']!=cid or
                    row['generated_frame_index']!=mapping['retained_to_generated'][i] or row['output_frame_index']!=mapping['start_frame']+i):
                raise ProductionRefused('repair source native mapping differs')
        ref=data[-1]['record']
        if ref['status']!='ready' or ref['source']['sha256']==binding['source']['sha256']:
            raise ProductionRefused('repair requires independent selected image sRGB reference')
        verify_reference_source(ref,binding)
        video=next(iter(colors.sidecars.values()))['probe']['video']
        validate_native(video,count)
        from ._scene_color_repair_media import dimensions
        ref_video=colors.sidecars[ref['sidecar']['path']]['probe']['video']
        dimensions(video,count,run=Path(binding['source']['path']).parent,reference_bytes=ref_video['width']*ref_video['height']*3)
        side=next(iter(colors.sidecars.values()))
        probe=reader.read({k:side['probe']['raw_probe'][k] for k in ('path','bytes','sha256')})
        if any(s.get('codec_type')!='video' for s in probe['streams']):raise ProductionRefused('repair source must have no audio or auxiliary tracks')
    return manifest


def verify_reference_source(record,binding):
    """Permit a byte-identical PNG filename adaptation of a .original still."""
    ref={k:record['source'][k] for k in ('path','bytes','sha256')};verify(ref);verify(binding['selected_image'])
    if any(ref[k]!=binding['selected_image'][k] for k in ('bytes','sha256')):
        raise ProductionRefused('repair independent reference bytes differ from selected original')


def remaining(reader):
    return reader.remaining()


def validate_native(video,count):
    integer(count,'repair frame count',1)
    if count>4096:raise ProductionRefused('resource_limit: repair native frames')
    try:rate=Fraction(video['avg_frame_rate']);tb=Fraction(video['time_base'])
    except (ValueError,ZeroDivisionError,TypeError) as exc:raise ProductionRefused('repair native rational time is invalid') from exc
    if len(video['frames'])!=count or rate!=16 or tb<=0:
        raise ProductionRefused('repair requires complete native 16fps frames')
    pts=[]
    for i,row in enumerate(video['frames']):
        value=row.get('pts',row.get('best_effort_timestamp'))
        if type(value) is not int or value*tb!=Fraction(i,16):raise ProductionRefused('repair native frame PTS differs')
        pts.append(value)
    return pts


def validate_candidate_review(value,expected,*,reader):
    r.schema(value,r.REVIEW,run_id=expected['run_id']);uid(value['candidate_id'])
    for name in ('candidate_id','terminal','source','candidate','playback','parent_chain','before_report','after_report','playback_ranges'):
        if value[name]!=expected[name]:raise ProductionRefused('repair review identity or complete playback range differs: '+name)
    for name in ('terminal','source','candidate','playback','before_report','after_report'):verify(value[name])
    if value['review_method'] not in ('human_video','agent_video'):raise ProductionRefused('actual complete video playback required')
    nonempty(value['reviewer']);r.timestamp(value['viewed_at'],after=expected['created_at'])
    for name in ('start_observation','process_observation','end_observation','quality_observation'):nonempty(value[name])
    object_fields(value['checks'],r.CHECKS.split(),'repair review checks')
    states=list(value['checks'].values())
    if any(s not in ('passed','failed','unverified') for s in states):raise ProductionRefused('repair review check state invalid')
    concerns={}
    for report,items in [(expected['before_report'],expected['before_concerns']),(expected['after_report'],expected['after_concerns'])]:
        for c in items:concerns[(report['path'],c['concern_id'])]=(report,c)
    responses=value['responses']
    if type(responses) is not list or len(responses)!=len(concerns):raise ProductionRefused('repair review risks incomplete')
    seen=set()
    for row in responses:
        object_fields(row,'assessment concern_id disposition reason references'.split(),'repair review response')
        key=(row['assessment'].get('path'),row['concern_id'])
        if key in seen or key not in concerns or row['assessment']!=concerns[key][0]:raise ProductionRefused('repair response scope unknown or repeated')
        seen.add(key);nonempty(row['reason'])
        if type(row['references']) is not list:raise ProductionRefused('repair references must be list')
        for ref in row['references']:verify(ref)
        d=row['disposition']
        if (value['verdict']=='passed' and row['assessment']==expected['before_report'] and
                row['concern_id'] in expected['confirmed_colors'] and d!='resolved_in_candidate'):
            raise ProductionRefused('confirmed original color issue must remain and be resolved using candidate evidence')
        if d=='confirmed_issue':states.append('failed')
        elif d=='unverified':states.append('unverified')
        elif d=='resolved_in_candidate':
            if (row['assessment']!=expected['before_report'] or concerns[key][1]['detector_id'] not in r.COLOR_DETECTORS or
                    row['concern_id'] not in expected['confirmed_colors'] or value['checks']['color_improvement']!='passed' or
                    expected['after_report'] not in row['references'] or expected['fit'] not in row['references']):
                raise ProductionRefused('repair resolved response lacks confirmed before-color and after/fit evidence')
        elif d=='not_observed_in_full_playback':
            if any(v!='passed' for v in value['checks'].values()):raise ProductionRefused('not-observed response requires passed complete playback')
        elif d=='explained_change':
            report=reader.read(row['assessment'])
            context=report['inputs']['manifest']['context']
            if context is None:raise ProductionRefused('repair explained change lacks frozen context')
            ref={k:context[k] for k in ('path','bytes','sha256')}
            c=concerns[key][1]
            if ref not in row['references'] or not any(c['detector_id'] in e['detector_ids'] and c['region_id'] in e['region_ids'] and
                    set(c['frame_ids'])<=set(e['frame_ids']) for e in reader.read(ref)['events']):
                raise ProductionRefused('repair explanation does not cover risk')
        else:raise ProductionRefused('unsupported repair concern disposition')
    verdict='failed' if 'failed' in states else 'unverified' if 'unverified' in states else 'passed'
    if value['verdict']!=verdict:raise ProductionRefused('repair verdict hides failed or unverified checks/risks')
    if type(value['issues']) is not list:raise ProductionRefused('repair issues must be list')
    ranges={row['media']['path']:row['end_frame'] for row in expected['playback_ranges']}
    for issue in value['issues']:
        object_fields(issue,'check media frames description'.split(),'repair issue')
        if issue['check'] not in value['checks'] or issue['media'] not in [x['media'] for x in expected['playback_ranges']]:
            raise ProductionRefused('repair issue check/media invalid')
        span=issue['frames']
        if type(span) is not list or len(span)!=2 or any(type(v) is not int for v in span) or not 0<=span[0]<span[1]<=ranges[issue['media']['path']]:
            raise ProductionRefused('repair issue frame range invalid')
        nonempty(issue['description'])
    if (verdict=='passed' and value['issues']) or (verdict=='failed' and not value['issues']):raise ProductionRefused('repair issues contradict verdict')
    return deepcopy(value)


def review_expected(frozen,folder,*,reader):
    intent=reader.read(folder/'intent.json');terminal=reader.read(folder/'terminal.json');media=reader.read(terminal['media'])
    before=reader.read(terminal['before_report']);after=reader.read(terminal['after_report'])
    precheck=reader.read(intent['binding']['precheck']);parents=intent['binding']['parent_chain'];ranges=[]
    for row in parents:
        clip=reader.read(row['clip']);mapping=reader.read(row['mapping'])
        ranges.append(dict(media=clip['source'],start_frame=0,end_frame=mapping['retained_frames']))
    playback=next(ref for ref in media['evidence'] if Path(ref['path']).name=='playback.mp4')
    ranges += [dict(media=media['source'],start_frame=0,end_frame=media['frames']),dict(media=playback,start_frame=0,end_frame=media['frames'])]
    from .scene_continuity_records import derive_concerns
    return dict(run_id=run_for(frozen).name,candidate_id=intent['candidate_id'],terminal=artifact(folder/'terminal.json'),
        source=media['source'],candidate=media['candidate'],playback=playback,parent_chain=parents,
        before_report=terminal['before_report'],after_report=terminal['after_report'],fit=terminal['fit'],playback_ranges=ranges,
        before_concerns=derive_concerns(before),after_concerns=derive_concerns(after),created_at=terminal['finished_at'],
        confirmed_colors={row['concern_id'] for row in precheck['responses'] if row['disposition']=='confirmed_issue'})


def review_state(frozen,folder,*,reader):
    expected=review_expected(frozen,folder,reader=reader);root=folder.parents[1]/'reviews';submissions=[]
    for path in sorted(root.glob('*.json')):
        value=reader.read(path)
        if value.get('candidate_id')!=folder.name:continue
        if path.stem!=artifact(path)['sha256']:raise ProductionRefused('repair author archive name differs')
        validate_candidate_review(value,expected,reader=reader);submissions.append((value,artifact(path)))
    rejected=next((ref for value,ref in submissions if value['verdict']=='failed'),None)
    if rejected:return 'rejected',rejected
    receipt=folder/'review-receipt.json'
    if receipt.exists():
        value=reader.read(receipt);r.schema(value,'schema_version run_id candidate_id terminal review state created_at',run_id=run_for(frozen).name)
        if value['candidate_id']!=folder.name or value['terminal']!=expected['terminal']:raise ProductionRefused('repair receipt binding differs')
        r.timestamp(value['created_at'],after=expected['created_at'])
        review=reader.read(value['review']);validate_candidate_review(review,expected,reader=reader)
        if review['verdict']!='passed' or value['state']!='research_candidate_reviewed':raise ProductionRefused('repair receipt state differs')
        if value['review'] not in [ref for _,ref in submissions]:raise ProductionRefused('repair receipt lacks retained original author bytes')
        return 'research_candidate_reviewed',artifact(receipt)
    return 'awaiting_review',None


def validate_saved_candidate(frozen,folder,*,reader,_terminal_value=None):
    intent=reader.read(folder/'intent.json');terminal=reader.read(folder/'terminal.json') if _terminal_value is None else _terminal_value
    r.schema(intent,r.INTENT,run_id=run_for(frozen).name)
    r.schema(terminal,r.TERMINAL,run_id=run_for(frozen).name)
    if terminal['candidate_id']!=folder.name or terminal['intent']!=artifact(folder/'intent.json'):
        raise ProductionRefused('repair terminal producer differs')
    r.timestamp(terminal['finished_at'],after=intent['created_at'])
    if terminal['status'] not in ('abstained','noop','awaiting_review','failed','interrupted'):raise ProductionRefused('invalid repair terminal status')
    if terminal['closure']!=r.closure(terminal['closure']):raise ProductionRefused('repair closure must be sorted unique')
    if intent['request']!=artifact(folder/'request.json'):raise ProductionRefused('repair archived request producer differs')
    object_fields(intent['binding'],r.BINDING.split(),'repair binding')
    mandatory=[intent['request'],terminal['intent']]
    if terminal['status'] not in ('failed','interrupted'):
        mandatory+=intent['binding']['profile_closure']
        for key,ref in intent['binding'].items():
            if key=='parent_chain':
                for row in ref:mandatory += [row[k] for k in ('clip','mapping','last_frame','video_observation')]
            elif key!='profile_closure' and ref is not None:mandatory.append(ref)
    for key in ('fit','media','pair_report','before_report','after_report'):
        ref=terminal[key]
        if ref is not None:
            verify(ref);mandatory.append(ref)
            if key in ('fit','media') and Path(ref['path'])!=folder/(key+'.json'):raise ProductionRefused('repair output borrows another candidate record')
        elif terminal['status']=='awaiting_review':raise ProductionRefused('repair review terminal has incomplete measured outputs')
    if any(ref not in terminal['closure'] for ref in mandatory):raise ProductionRefused('repair terminal closure missing evidence')
    if terminal['status'] in ('awaiting_review','noop','abstained'):
        if terminal['failure'] is not None:raise ProductionRefused('repair measured terminal claims a failure')
        if terminal['fit'] is None or terminal['pair_report'] is None or terminal['before_report'] is None:
            raise ProductionRefused('repair measured terminal lacks fit/pair/before evidence')
        request=reader.read(intent['request']);fit=reader.read(terminal['fit']);mapping=reader.read(intent['binding']['mapping']);count=mapping['retained_frames']
        r.schema(fit,'schema_version candidate_id status operation amplitude correction_bound fit_pairs frame_support before after reasons')
        if fit['candidate_id']!=folder.name or fit['operation']!=request['operation'] or fit['status'] not in ('estimated','noop','abstained'):
            raise ProductionRefused('repair fit binding or status differs')
        integer(fit['fit_pairs'],'repair informative fit pairs',0)
        if fit['fit_pairs']>16384 or type(fit['reasons']) is not list or any(type(v) is not str for v in fit['reasons']):
            raise ProductionRefused('repair fit support/reasons invalid')
        if fit['status']=='abstained':
            if fit['amplitude'] is not None or not fit['reasons']:raise ProductionRefused('repair abstention lacks reason or claims amplitude')
        else:
            import math
            if type(fit['amplitude']) not in (int,float) or not math.isfinite(fit['amplitude']):raise ProductionRefused('repair finite amplitude required')
            if fit['status']=='noop':
                if fit['amplitude']!=0 or fit['correction_bound'] is not None:raise ProductionRefused('repair noop has nonzero correction')
            else:
                profile=reader.read(intent['binding']['profile']);bound=fit['correction_bound'];amplitude=fit['amplitude']
                if (bound not in profile['calibrated_bounds'] or {'operation':fit['operation'],'injection_direction':bound['injection_direction']} not in profile['qualified_directions'] or
                        bound['operation']!=fit['operation'] or amplitude==0 or amplitude*bound['correction_direction']<=0 or abs(amplitude)>bound['correction_amplitude_ceiling']):
                    raise ProductionRefused('repair fit exceeds a qualified sealed direction')
        if fit['status']!='abstained' or fit['frame_support']:
            if type(fit['frame_support']) is not list or len(fit['frame_support'])!=count:raise ProductionRefused('repair fit native support incomplete')
            for i,row in enumerate(fit['frame_support']):
                object_fields(row,'source_frame_index pairs informative_pairs'.split(),'repair fit frame support')
                if type(row['source_frame_index']) is not int or row['source_frame_index']!=i:raise ProductionRefused('repair fit source frame order differs')
                integer(row['pairs'],'repair frame pairs',81);integer(row['informative_pairs'],'repair informative pairs',0)
                if row['pairs']>2048 or row['informative_pairs']>row['pairs']:raise ProductionRefused('repair fit frame support exceeds sampling domain')
        if (terminal['status']=='awaiting_review' and fit['status']!='estimated') or (terminal['status'] in ('noop','abstained') and terminal['status']!=fit['status']):
            raise ProductionRefused('repair fit and terminal state differ')
        if fit['status']!='abstained' and (len(fit['before'])!=count or len(fit['after'])!=count):raise ProductionRefused('repair frame scoring incomplete')
        before=reader.read(intent['binding']['assessment'])
        if terminal['before_report']!=before['report']:raise ProductionRefused('repair before report differs from bound assessment')
        from ..media.continuity_report import validate_continuity_report
        epoch=reader.read(intent['binding']['epoch']);engine=reader.read(epoch['intent'])['engine']
        for key,name in [('pair_report','pair'),('after_report','after')]:
            ref=terminal[key]
            if ref is None:continue
            producer_path=folder/(name+'-producer.json');producer=reader.read(producer_path)
            r.schema(producer,'schema_version candidate_id intent manifest audit_run_dir engine_epoch created_at')
            if producer['candidate_id']!=folder.name or producer['intent']!=terminal['intent'] or producer['engine_epoch']!=intent['binding']['epoch']:
                raise ProductionRefused('repair report producer does not own candidate intent/epoch')
            expected_manifest=intent['binding']['manifest'] if name=='pair' else artifact(folder/'after-manifest.json')
            expected_report=Path(producer['audit_run_dir'])/'logs/continuity/report.json'
            if producer['manifest']!=expected_manifest or ref['path']!=str(expected_report):raise ProductionRefused('repair report borrows foreign producer or manifest')
            r.timestamp(producer['created_at'],after=intent['created_at'])
            verified=validate_continuity_report(ref,manifest=expected_manifest,expected_engine=engine,expected_audit_run_dir=producer['audit_run_dir'],
                config=frozen.config,timeout=remaining(reader),_budget=reader)
            needed=verified['closure']+[expected_manifest,artifact(producer_path)]
            if any(ref not in terminal['closure'] for ref in needed):raise ProductionRefused('repair report producer closure incomplete')
    if terminal['status']=='awaiting_review':
        from ._scene_color_repair_media import validate_media
        media=reader.read(terminal['media']);validate_media(media,intent,config=frozen.config,reader=reader)
        if any(ref not in terminal['closure'] for ref in media['evidence']+media['encoding']['command_receipts']):raise ProductionRefused('repair media complete evidence closure missing')
        validate_after_manifest(folder,intent,media,reader=reader)
    return terminal


def validate_after_manifest(folder,intent,media,*,reader):
    from ..media._continuity_schema import stable
    from ._scene_color_repair_media import master_frames
    assessment=reader.read(intent['binding']['assessment']);before=reader.read(assessment['manifest']);after=reader.read(folder/'after-manifest.json')
    cid=reader.read(intent['request'])['clip_id'];frames=master_frames(media,reader=reader);expected=deepcopy(before)
    original=next(row['frames'] for row in before['clips'] if row['clip_id']==cid)
    replacements={old['record']['path']:new['record'] for old,new in zip(original,frames)}
    for clip in expected['clips']:
        if clip['clip_id']==cid:clip['frames']=[dict(frame_id=old['frame_id'],record=new['record']) for old,new in zip(original,frames)]
    regions=reader.read({k:before['regions'][k] for k in ('path','bytes','sha256')})
    for region in regions['regions']:
        for anchor in region['anchors']:
            if anchor['frame']['path'] in replacements:anchor['frame']=replacements[anchor['frame']['path']]
    path=folder/'after-regions.json'
    if stable(reader.read(path))!=stable(regions):raise ProductionRefused('repair after ROI differs from original geometry')
    from .manifest import thaw,hash_file
    expected['regions']=thaw(hash_file(path))
    if stable(after)!=stable(expected):raise ProductionRefused('repair after manifest changed context/reference/prefix or omitted candidate frames')
