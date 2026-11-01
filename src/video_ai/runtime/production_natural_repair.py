"""Independent natural research candidates, no models and no production admission."""
from pathlib import Path

from ..media.natural_repair_engine import fit_natural_parameter,assess_natural_change
from ._scene_continuity_io import artifact,uid,local
from .manifest import now,validate_run_dir
from .natural_study_records import StudyReader,StudyLock,put_json,copy_original,capture_software,verify_software,read_author_observations,require_complete_observations,fields,timestamp
from .natural_candidate_records import validate_request,validate_precheck,validate_visual_review,source_registration,VISUAL_CHECKS,read_review_receipt,has_noncolor_failure
from .natural_candidate_media import render_media,validate_media
from .natural_repair_profile import load_natural_repair_profile,direction_thresholds
from .natural_study_measure import measure_variant,safe_author,replay_ordinary_report
from .production_state import ProductionRefused
from .research_material_records import load_research_material_context


def boundary(point):
    """Durable test interruption boundary; never an automatic retry hook."""


def _request_reader(request,request_ref):
    """A new operation boundary rechecks identities, never extends case work."""
    r=StudyReader();r.cap(request_ref)
    for key in ('material','epoch','assessment','pair_manifest','conditional_profile','natural_profile','precheck'):
        if request[key] is not None: r.cap(request[key])
    return r


def _prepare(request):
    from ..config import load_config
    from .paths import RuntimePaths
    r=StudyReader();run=validate_run_dir(Path(request['material']['path']).parents[2])
    context=load_research_material_context(run,reader=r)
    validate_request(request,run,context,r)
    options=r.any(run/'research/options.json');config=load_config(Path(r.cap(options['config'])['path']))
    manifest=r.any(request['pair_manifest']);report=r.any(r.any(request['assessment'])['report'])
    r.verify_all();return run,context,manifest,report,config,RuntimePaths.from_config(config)


def _result(folder):
    r=StudyReader();terminal=r.any(folder/'terminal.json')
    return dict(status=terminal['status'],candidate_id=folder.name,terminal=r.cap(folder/'terminal.json'),
        original_preserved=True,production_eligible=False,ready_for_propose=False,reasons=terminal['reasons'])


def _lineage(root,request):
    r=StudyReader();parents=[];all_intents=[]
    for p in root.glob('*/intent.json'):
        value=r.any(p);old=r.any(value['request'])
        if old['material']==request['material']:
            all_intents.append((p,value,old))
            # A revision cannot omit an adverse sibling by naming an earlier
            # ancestor. Every same-source submitted failure remains binding.
            for review in (p.parent/'reviews').glob('*/receipt.json'):
                terminal=r.any(p.parent/'terminal.json')
                if terminal['media'] is None: raise ProductionRefused('review receipt lacks original candidate media')
                expected=r.any(terminal['media'])
                _,observation=read_review_receipt(review,expected,identity=p.parent.name)
                if has_noncolor_failure(observation):
                    raise ProductionRefused('historical non-color candidate failure permanently blocks repair')
    if len(all_intents)>=3: raise ProductionRefused('natural source family has reached three attempts')
    parent=request['revision_of']
    if all_intents and parent is None: raise ProductionRefused('new natural attempt must name its actual revision parent')
    if parent is not None:
        path=Path(r.cap(parent)['path'])
        if path.name not in ('terminal.json','intent.json') or path.parent.parent!=root or path.parent.name==request['candidate_id']:
            raise ProductionRefused('natural revision must bind an actual same-source ancestor')
        if not any(p.parent==path.parent for p,_,_ in all_intents): raise ProductionRefused('natural revision source family differs')
        seen=set()
        while parent is not None:
            p=Path(r.cap(parent)['path']);cid=p.parent.name
            if cid in seen or len(seen)>=3: raise ProductionRefused('natural revision cycle')
            seen.add(cid);intent=r.any(p.parent/'intent.json');prior=r.any(intent['request'])
            if prior['material']!=request['material']: raise ProductionRefused('natural ancestor material differs')
            parents.append(r.cap(p))
            parent=prior['revision_of']
    return parents


def _saved(folder,request,context,manifest,report,config):
    r=StudyReader();intent=r.any(folder/'intent.json')
    if request['candidate_id']!=folder.name: raise ProductionRefused('candidate UUID directory binding differs')
    if r.any(intent['request'])!=request: raise ProductionRefused('candidate UUID original request differs')
    registry=folder.parent.parent.parent.parent.parent/'natural-repair-candidates'/f"{folder.name}.json"
    if r.any(registry)!=dict(schema_version=1,candidate_id=folder.name,request=intent['request'],run=str(folder.parents[2])):
        raise ProductionRefused('candidate independent UUID registry differs')
    copied=r.cap(intent['request_copy'])
    if (copied['bytes'],copied['sha256'])!=(intent['request']['bytes'],intent['request']['sha256']):
        raise ProductionRefused('candidate original request byte copy differs')
    if intent['material']!=context['commit'] or intent['epoch']!=context['epoch'] or intent['source']!=context['source']:
        raise ProductionRefused('candidate current source/epoch differs')
    verify_software(r.any(intent['software']),config)
    if not (folder/'terminal.json').exists(): raise ProductionRefused('partial candidate retained; explicit new revision UUID required')
    t=r.any(folder/'terminal.json')
    fields(t,'schema_version intent request status reasons fit media finished_at')
    if t['status'] not in ('awaiting_qualification','noop','abstained','interrupted','awaiting_review'):
        raise ProductionRefused('candidate persisted terminal state is invalid')
    if timestamp(t['finished_at'])<timestamp(intent['created_at']): raise ProductionRefused('candidate terminal predates intent')
    if t['intent']!=r.cap(folder/'intent.json') or t['request']!=intent['request']: raise ProductionRefused('candidate terminal intent differs')
    if t['status']=='awaiting_review' and (t['media'] is None or t['fit'] is None or request['natural_profile'] is None):
        raise ProductionRefused('awaiting review requires qualified profile, measured fit and complete media')
    if t['status']=='awaiting_qualification' and (request['natural_profile'] is not None or t['fit'] is not None or t['media'] is not None):
        raise ProductionRefused('waiting terminal cannot claim fit/media authority')
    if t['media'] is not None and t['status']!='awaiting_review': raise ProductionRefused('terminal media status differs')
    if t['status']=='noop':
        if request['natural_profile'] is None or t['media'] is not None or t['fit'] is not None:
            raise ProductionRefused('noop requires actual qualified stable bias evidence')
        profile=load_natural_repair_profile(request['natural_profile']['path'])
        r=_request_reader(request,intent['request'])
        author=validate_precheck(r.any(request['precheck']),request,context,r)
        thresholds=direction_thresholds(profile,request['operation'],author['correction_direction'],domain=manifest['domain']['genre'])
        work=StudyReader();report=replay_ordinary_report(r.any(request['assessment'])['report'],manifest=manifest,config=config,reader=work)
        original=measure_variant(manifest,report,config=config,out=None,reader=work)
        if assess_natural_change(original['before'],original['before'],operation=request['operation'],thresholds=thresholds)['status']!='noop':
            raise ProductionRefused('saved noop differs from actual full-frame stable bias')
    if t['media'] is not None:
        profile=load_natural_repair_profile(request['natural_profile']['path'])
        r=_request_reader(request,intent['request'])
        pre=validate_precheck(r.any(request['precheck']),request,context,r)
        if profile['conditional_profile']!=request['conditional_profile']: raise ProductionRefused('natural conditional profile differs')
        from ._scene_color_repair_profile import verified_profile
        conditional,_=verified_profile(request['conditional_profile']['path'],reader=r)
        r=_request_reader(request,intent['request'])
        work=StudyReader();report=replay_ordinary_report(r.any(request['assessment'])['report'],manifest=manifest,config=config,reader=work)
        original=measure_variant(manifest,report,config=config,out=None,reader=work)
        fit=fit_natural_parameter(original['before'],operation=request['operation'],conditional_profile=conditional)
        if r.any(t['fit'])!=fit: raise ProductionRefused('candidate fit replay differs')
        media=r.any(t['media']);validate_media(media,manifest=manifest,report=report,fit=fit,config=config,reader=work)
        thresholds=direction_thresholds(profile,request['operation'],pre['correction_direction'],domain=manifest['domain']['genre'])
        measured=measure_variant(manifest,report,config=config,out=None,candidate_frames=media['master_frames'],reader=work)
        if assess_natural_change(measured['before'],measured['after'],operation=request['operation'],thresholds=thresholds)['status']!='estimated':
            raise ProductionRefused('actual decoded natural candidate no longer meets sealed gates')
    return t


def propose(request_path):
    reader=StudyReader();request_ref=reader.cap(request_path);request=reader.any(request_ref)
    # Validate the exact envelope before creating any ledger or registry.
    from .natural_candidate_records import schema,REQUEST
    schema(request,REQUEST);uid(request['candidate_id'])
    run,context,manifest,report,config,paths=_prepare(request)
    root=run/'research/natural-color-repair';folder=root/request['candidate_id']
    with StudyLock(root):
        if folder.exists():
            _saved(folder,request,context,manifest,report,config);return _result(folder)
        parents=_lineage(root,request)
        registry=root.parent.parent.parent.parent/'natural-repair-candidates'/f"{request['candidate_id']}.json"
        put_json(registry,dict(schema_version=1,candidate_id=request['candidate_id'],request=request_ref,run=str(run)))
        copied=copy_original(request_ref,folder/'request.json')
        software=put_json(folder/'software.FROZEN.json',capture_software(config))
        intent=put_json(folder/'intent.json',dict(schema_version=1,request=request_ref,request_copy=copied,material=context['commit'],
            epoch=context['epoch'],source=context['source'],software=software,parent_chain=parents,created_at=now()))
        boundary('intent')
        status='awaiting_qualification';reasons=[];fit_ref=None;media_ref=None
        try:
            if request['natural_profile'] is None: reasons=['independent_natural_qualification_not_available']
            else:
                profile=load_natural_repair_profile(request['natural_profile']['path'])
                reader=_request_reader(request,request_ref)
                pre=validate_precheck(reader.any(request['precheck']),request,context,reader)
                if profile['conditional_profile']!=request['conditional_profile']: raise ProductionRefused('natural conditional profile differs')
                thresholds=direction_thresholds(profile,request['operation'],pre['correction_direction'],domain=manifest['domain']['genre'])
                from ._scene_color_repair_profile import verified_profile
                conditional,_=verified_profile(request['conditional_profile']['path'],reader=reader)
                reader=_request_reader(request,request_ref)
                verify_software(reader.any(software),config)
                work=StudyReader()
                report=replay_ordinary_report(reader.any(request['assessment'])['report'],manifest=manifest,config=config,reader=work)
                original=measure_variant(manifest,report,config=config,out=folder/'original',reader=work)
                neutral=assess_natural_change(original['before'],original['before'],operation=request['operation'],thresholds=thresholds)
                if neutral['status']=='noop': status='noop';reasons=neutral['reasons']
                else:
                    fit=fit_natural_parameter(original['before'],operation=request['operation'],conditional_profile=conditional)
                    fit_ref=put_json(folder/'fit.json',fit);boundary('fit')
                    if fit['status']!='estimated' or fit['correction_direction']!=pre['correction_direction']:
                        status='abstained';reasons=fit['reasons'] or ['fit_direction_differs_from_known_author_direction']
                    else:
                        media=render_media(manifest,report,fit,out=folder/'media',source=context['source'],
                            before_report=reader.any(request['assessment'])['report'],config=config,paths=paths,reader=work)
                        boundary('media')
                        decoded=measure_variant(manifest,report,config=config,out=None,candidate_frames=media['master_frames'],reader=work)
                        checked=assess_natural_change(decoded['before'],decoded['after'],operation=request['operation'],thresholds=thresholds)
                        put_json(folder/'natural-checks.json',checked)
                        if checked['status']!='estimated': status='abstained';reasons=checked['reasons']
                        else:
                            validate_media(media,manifest=manifest,report=report,fit=fit,config=config,reader=work)
                            media_ref=reader.cap(folder/'media/media.json');status='awaiting_review'
                # Revalidate the actual author/history and current source after work.
                run2,context2,_,_,_,_=_prepare(request)
                if context2!=context: raise ProductionRefused('research source changed during candidate operation')
                validate_precheck(reader.any(request['precheck']),request,context2,reader)
                verify_software(reader.any(software),config)
        except (ValueError,RuntimeError,OSError,TimeoutError) as error:
            status='abstained';reasons=[str(error)]
        except KeyboardInterrupt:
            put_json(folder/'terminal.json',dict(schema_version=1,intent=intent,request=request_ref,status='interrupted',
                reasons=['operation_interrupted_outputs_retained'],fit=fit_ref,media=None,finished_at=now()))
            raise
        reader.verify_all()
        put_json(folder/'terminal.json',dict(schema_version=1,intent=intent,request=request_ref,status=status,
            reasons=reasons,fit=fit_ref,media=media_ref,finished_at=now()))
        boundary('terminal')
    return _result(folder)


def status(run,candidate_id):
    root=local(Path(run)/'research/natural-color-repair',exists=False);folder=root/uid(candidate_id)
    r=StudyReader();intent=r.any(folder/'intent.json');request=r.any(intent['request'])
    actual_run,context,manifest,report,config,_=_prepare(request)
    if actual_run!=Path(run): raise ProductionRefused('candidate status run differs')
    _saved(folder,request,context,manifest,report,config)
    result=_result(folder);verdicts=[]
    for path in sorted((folder/'reviews').glob('*/receipt.json')):
        media=r.any(r.any(folder/'terminal.json')['media'])
        verdict,_=read_review_receipt(path,media,identity=candidate_id)
        verdicts.append(verdict)
    if 'failed' in verdicts: result['status']='review_failed'
    elif 'passed' in verdicts: result['status']='research_candidate_reviewed'
    return result


def review(run,candidate_id,observation_path):
    root=Path(run)/'research/natural-color-repair';folder=root/uid(candidate_id)
    with StudyLock(root):
        current=status(run,candidate_id)
        if current['status'] not in ('awaiting_review','research_candidate_reviewed','review_failed'):
            raise ProductionRefused('natural candidate is not technically ready for actual review')
        r=StudyReader();ref=r.cap(observation_path);row=r.any(ref)
        media=r.any(r.any(folder/'terminal.json')['media'])
        verdict=validate_visual_review(row,media,identity=candidate_id)
        receipt_folder=folder/'reviews'/ref['sha256']
        copy_original(ref,receipt_folder/'raw.json')
        if current['status']=='review_failed' and verdict=='passed': raise ProductionRefused('failed visual review cannot be overwritten by passed')
        if verdict!='unverified':
            put_json(receipt_folder/'receipt.json',dict(schema_version=1,observation=ref,verdict=verdict,created_at=now()))
    return status(run,candidate_id)


def assess(run,*,observations=(),natural_profile=None):
    """Read-only existing-material disposition. Unknown is never a numerical noop."""
    r=StudyReader();context=load_research_material_context(Path(run),reader=r)
    status='awaiting_observation';reasons=[];author=None
    if observations:
        cid,_,_=source_registration(context,r)
        case=dict(case_id=cid,observations=list(observations))
        require_complete_observations(case,context,r)
        author=read_author_observations(case,context,r)
        if author['hard_noncolor_failure'] or author['natural_label'] in ('unsafe','not_comparable'):
            status='abstained';reasons=['known_noncolor_failure_or_incomparable_source']
        elif author['natural_label']=='neutral' and not author['unresolved']:
            status='original_acceptable';reasons=['actual_author_reports_no_color_issue']
        elif not safe_author(author): reasons=['unknown_color_axis_or_unresolved_original_observation']
        else: status='awaiting_qualification';reasons=['valid_current_precheck_and_independent_profile_required']
    else: reasons=['no_actual_original_observation_supplied']
    if natural_profile is not None: load_natural_repair_profile(natural_profile,reader=r)
    r.verify_all()
    return dict(schema_version=1,status=status,material=context['commit'],epoch=context['epoch'],source=context['source'],
        native_frames=len(context['frames']),author=author,reasons=reasons,original_preserved=True,
        model_requests=0,candidate_encoded=False,production_eligible=False,ready_for_propose=False)
