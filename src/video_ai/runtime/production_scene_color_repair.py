"""Explicit locked local research color-repair transactions; no model clients."""
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path

from .manifest import now,thaw,hash_file
from .production_state import ProductionRefused,RunLock,run_path
from ._scene_continuity_io import Reader,ContinuityStore,artifact,verify,run_for,uid,local
from . import scene_color_repair_records as records
from . import _scene_color_repair_validation as checks
from .execution_limits import production_execution


def boundary(point):
    """Synchronous durable boundary for interruption tests."""


@dataclass(frozen=True)
class SceneColorRepairResult:
    schema_version:int=1
    run_id:str|None=None
    candidate_id:str|None=None
    status:str='blocked'
    intent:dict|None=None
    terminal:dict|None=None
    review_template:dict|None=None
    error:dict|None=None

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version!=1 or self.status not in (
                'abstained','noop','awaiting_review','reviewed','blocked','failed','interrupted'):
            raise ValueError('invalid color repair result')

    @property
    def exit_code(self):return dict(abstained=0,noop=0,awaiting_review=3,reviewed=0,blocked=2,failed=1,interrupted=130)[self.status]

    def to_dict(self):return thaw(self)


class RepairStore(ContinuityStore):
    def __init__(self,frozen,lock):
        super().__init__(frozen,lock);self.frozen=frozen;self.reader=None;self.root=run_path(self.run_dir,self.run_dir/'production/scene-color-repair')

    def write_bytes(self,relative,raw):
        target=run_path(self.run_dir,self.root/relative)
        if not target.is_relative_to(self.root):raise ProductionRefused('repair write escapes root')
        local(target,exists=False)
        if target.exists():
            local(target)
            if target.stat().st_size!=len(raw):raise ProductionRefused('immutable repair byte count differs')
        if Path(relative).suffix=='.json':
            if len(raw)>16777216:raise ProductionRefused('resource_limit: repair JSON')
            if self.reader is not None:self.reader.charge(target,len(raw))
        return super().write_bytes(relative,raw)

    def write(self,relative,value):
        target=run_path(self.run_dir,self.root/relative)
        if self.reader is not None and target.exists():
            self.owned()
            if not target.is_relative_to(self.root) or self.reader.read(target)!=value:raise ProductionRefused('immutable repair record differs')
            self.owned();return target
        return super().write(relative,value)


def _error(exc,folder=None):
    evidence=[str(p) for p in sorted(folder.rglob('*')) if p.is_file()] if folder and folder.exists() else []
    return dict(kind=type(exc).__name__,message=str(exc) or type(exc).__name__,evidence_paths=evidence)


def _result(frozen,status,*,folder=None,candidate_id=None,error=None):
    def ref(name):return artifact(folder/name) if folder is not None and (folder/name).is_file() else None
    return SceneColorRepairResult(run_id=run_for(frozen).name,candidate_id=candidate_id,status=status,
        intent=ref('intent.json'),terminal=ref('terminal.json'),review_template=ref('review-template.json'),error=error)


def _terminal(store,relative,intent,*,status,fit=None,media=None,pair_report=None,before_report=None,after_report=None,refs=(),failure=None,reader=None):
    folder=store.root/relative
    required=[intent['request'],artifact(folder/'intent.json')]
    if status not in ('failed','interrupted'):
        required += intent['binding']['profile_closure']+[x for x in (fit,media,pair_report,before_report,after_report) if x is not None]+list(refs)
        for key,value in intent['binding'].items():
            if key not in ('parent_chain','profile_closure') and value is not None:required.append(value)
            if key=='parent_chain':
                for row in value:required += [row[k] for k in ('clip','mapping','last_frame','video_observation')]
    value=dict(schema_version=1,run_id=store.run_dir.name,candidate_id=intent['candidate_id'],intent=artifact(folder/'intent.json'),
        status=status,fit=fit,media=media,pair_report=pair_report,before_report=before_report,after_report=after_report,
        closure=records.closure(required),failure=failure,finished_at=now())
    if status in ('awaiting_review','noop','abstained'):
        budget=reader or store.reader or Reader()
        size=len((json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode('utf-8'))
        budget.charge(folder/'terminal.json',size)
        checks.validate_saved_candidate(store.frozen,folder,reader=budget,_terminal_value=value)
    return artifact(store.write(relative/'terminal.json',value))


def _template(store,relative,*,frozen,reader):
    folder=store.root/relative
    if (folder/'review-template.json').exists():return artifact(folder/'review-template.json')
    expected=checks.review_expected(frozen,folder,reader=reader)
    value=dict(schema_version=1,**{k:expected[k] for k in ('run_id','candidate_id','terminal','source','candidate','playback','parent_chain','before_report','after_report')},
        review_method='agent_video',reviewer='',viewed_at=None,playback_ranges=expected['playback_ranges'],
        start_observation='',process_observation='',end_observation='',quality_observation='',
        checks={k:'unverified' for k in records.CHECKS.split()},responses=[],verdict='unverified',issues=[])
    for report,concerns in [(expected['before_report'],expected['before_concerns']),(expected['after_report'],expected['after_concerns'])]:
        value['responses'] += [dict(assessment=report,concern_id=c['concern_id'],disposition='unverified',reason='',references=[]) for c in concerns]
    return artifact(store.write(relative/'review-template.json',value))


def _audit(store,relative,name,manifest_ref,intent,*,frozen,paths,reader):
    from .paths import create_run
    from .logging import RunLogger
    from ..media.continuity_analysis import analyze_continuity
    from ..media.continuity_report import validate_continuity_report
    folder=store.root/relative
    producer=folder/(name+'-producer.json')
    if producer.exists():raise ProductionRefused('partial repair audit retained; new candidate UUID required')
    audit=create_run(paths)
    value=dict(schema_version=1,candidate_id=intent['candidate_id'],intent=artifact(folder/'intent.json'),
        manifest=manifest_ref,audit_run_dir=str(audit),engine_epoch=intent['binding']['epoch'],created_at=now())
    store.write(relative/(name+'-producer.json'),value);boundary(name+'-producer')
    manifest=reader.read(manifest_ref)
    analyze_continuity(manifest,config=frozen.config,paths=paths,logger=RunLogger(audit),timeout=checks.remaining(reader))
    boundary(name+'-report')
    ref=artifact(audit/'logs/continuity/report.json')
    epoch=reader.read(intent['binding']['epoch']);engine=reader.read(epoch['intent'])['engine']
    verified=validate_continuity_report(ref,manifest=manifest_ref,expected_engine=engine,expected_audit_run_dir=audit,
        config=frozen.config,timeout=checks.remaining(reader),_budget=reader)
    return ref,verified


def _after_manifest(store,relative,intent,frames,*,reader):
    before=reader.read(intent['binding']['assessment']);original=reader.read(before['manifest']);result=deepcopy(original)
    cid=reader.read(intent['request'])['clip_id'];old=next(c['frames'] for c in original['clips'] if c['clip_id']==cid)
    replacement={a['record']['path']:b['record'] for a,b in zip(old,frames)}
    for row in result['clips']:
        if row['clip_id']==cid:row['frames']=[dict(frame_id=a['frame_id'],record=b['record']) for a,b in zip(old,frames)]
    regions=reader.read({k:original['regions'][k] for k in ('path','bytes','sha256')})
    for region in regions['regions']:
        for anchor in region['anchors']:
            if anchor['frame']['path'] in replacement:anchor['frame']=replacement[anchor['frame']['path']]
    regions_path=store.write(relative/'after-regions.json',regions);result['regions']=thaw(hash_file(regions_path))
    return artifact(store.write(relative/'after-manifest.json',result))


def _propose(store,context,source,reader,request_path,*,frozen,paths,logger):
    from ._scene_color_repair_profile import verified_profile
    from ._scene_color_repair_engine import capture_engine,archive_engine,verify_engine
    from ._scene_color_repair_media import pair_pixels,render_media
    from ..media.color_repair import estimate_constant_repair,apply_constant_repair,score_repair_pairs
    request_ref=artifact(request_path);request=reader.read(request_ref)
    records.validate_repair_request(request,{'run_id':store.run_dir.name});cid=request['candidate_id'];relative=Path('candidates')/cid;folder=store.root/relative
    records.validate_revision(request,run=store.run_dir,reader=reader)
    if (folder/'request.json').exists() and (folder/'request.json').read_bytes()!=Path(request_path).read_bytes():
        raise ProductionRefused('same repair UUID has different request bytes')
    profile,profile_closure=verified_profile(request['profile']['path'],reader=reader)
    binding=checks.capture_binding(frozen,context,source,request,profile_closure,reader=reader)
    assessment=reader.read(binding['assessment']);manifest=checks.validate_pair_manifest(reader.read(request['manifest']),request,binding,assessment,config=frozen.config,reader=reader)
    if (folder/'intent.json').exists():
        intent=reader.read(folder/'intent.json');records.schema(intent,records.INTENT,run_id=store.run_dir.name)
        if intent['binding']!=binding or intent['request']!=artifact(folder/'request.json'):raise ProductionRefused('repair intent binding drift')
        if (folder/'terminal.json').exists():
            terminal=checks.validate_saved_candidate(frozen,folder,reader=reader)
            if terminal['status'] not in ('interrupted','failed'):verify_engine(folder,intent,reader=reader)
            if terminal['status']=='awaiting_review':_template(store,relative,frozen=frozen,reader=reader)
            return _result(frozen,terminal['status'],folder=folder,candidate_id=cid,error=terminal['failure'])
        if (folder/'engine/manifest.json').exists():verify_engine(folder,intent,reader=reader)
        # Only a complete measured media/after-report closure can finish without
        # re-running any operation. Every other partial attempt is immutable.
        if all((folder/name).exists() for name in ('fit.json','media.json','pair-producer.json','after-producer.json')):
            return _finish_recovered(store,relative,intent,frozen=frozen,reader=reader)
        _terminal(store,relative,intent,status='interrupted',failure=_error(InterruptedError('partial repair retained; new UUID and revision_of required'),folder))
        return _result(frozen,'interrupted',folder=folder,candidate_id=cid,error=_error(InterruptedError('explicit new candidate required'),folder))
    attempts=0;capture=capture_engine()
    for path in sorted((store.root/'candidates').glob('*/intent.json')):
        prior=reader.read(path);old=reader.read(prior['request'])
        records.schema(prior,records.INTENT,run_id=store.run_dir.name)
        records.schema(old,records.REQUEST,run_id=store.run_dir.name)
        if (uid(prior['candidate_id'])!=path.parent.name or old['candidate_id']!=prior['candidate_id'] or
                prior['request']['path']!=str(path.parent/'request.json')):
            raise ProductionRefused('historical repair attempt producer differs')
        if (old['source_clip']==request['source_clip'] and old['operation']==request['operation'] and
                all(old['profile'][k]==request['profile'][k] for k in ('bytes','sha256')) and prior['engine']==capture['engine']):
            attempts+=1
    if attempts>=3:raise ProductionRefused('repair three-attempt limit reached for raw/operation/profile')
    verify(request_ref)
    store.write_bytes(relative/'request.json',Path(request_path).read_bytes())
    if reader.read(folder/'request.json')!=request or artifact(request_path)!=request_ref:
        raise ProductionRefused('repair author request changed during capture')
    boundary('request')
    intent=dict(schema_version=1,run_id=store.run_dir.name,candidate_id=cid,request=artifact(folder/'request.json'),binding=binding,engine=capture['engine'],created_at=now())
    store.write(relative/'intent.json',intent);boundary('intent')
    archive_ref=archive_engine(store,relative,capture,reader=reader);boundary('engine')
    checks.current_binding(frozen,intent,reader=reader,context=context,source=source)
    pair_ref,verified=_audit(store,relative,'pair',request['manifest'],intent,frozen=frozen,paths=paths,reader=reader)
    pairs,reasons=pair_pixels(manifest,verified['report'],config=frozen.config,reader=reader)
    if pairs is None:
        fit=dict(status='abstained',operation=request['operation'],amplitude=None,correction_bound=None,fit_pairs=0,reasons=reasons)
        support=[];scores=dict(before=[],after=[])
    else:
        fit=estimate_constant_repair(pairs['reference'],pairs['current'],operation=request['operation'],context=request['context'],profile=profile)
        support=pairs['frame_support'];scores=dict(before=[],after=[])
        if fit['status'] in ('estimated','noop'):
            repaired=[apply_constant_repair(row,operation=request['operation'],amplitude=fit['amplitude']) for row in pairs['current']]
            scores=score_repair_pairs(pairs['reference'],pairs['current'],repaired)
            del repaired
    fit=dict(schema_version=1,candidate_id=cid,**fit,frame_support=support,before=scores['before'],after=scores['after'])
    fit_ref=artifact(store.write(relative/'fit.json',fit));boundary('fit')
    if fit['status'] in ('noop','abstained'):
        checks.current_binding(frozen,intent,reader=reader,context=context,source=source)
        _terminal(store,relative,intent,status=fit['status'],fit=fit_ref,pair_report=pair_ref,before_report=assessment['report'],
            refs=verified['closure']+[archive_ref,artifact(folder/'pair-producer.json')],reader=reader)
        boundary('terminal');return _result(frozen,fit['status'],folder=folder,candidate_id=cid)
    media,frames=render_media(store,relative,intent,fit,manifest,pairs,config=frozen.config,paths=paths,logger=logger,reader=reader,boundary=boundary)
    media_ref=artifact(store.write(relative/'media.json',media));boundary('media')
    after_manifest=_after_manifest(store,relative,intent,frames,reader=reader)
    after_ref,after=_audit(store,relative,'after',after_manifest,intent,frozen=frozen,paths=paths,reader=reader)
    checks.current_binding(frozen,intent,reader=reader,context=context,source=source);verify_engine(folder,intent,reader=reader)
    refs=verified['closure']+after['closure']+media['evidence']+media['encoding']['command_receipts']+[archive_ref,
        artifact(folder/'pair-producer.json'),artifact(folder/'after-producer.json'),after_manifest]
    _terminal(store,relative,intent,status='awaiting_review',fit=fit_ref,media=media_ref,pair_report=pair_ref,before_report=assessment['report'],after_report=after_ref,refs=refs,reader=reader)
    boundary('terminal')
    _template(store,relative,frozen=frozen,reader=reader);boundary('review-template')
    return _result(frozen,'awaiting_review',folder=folder,candidate_id=cid)


def _finish_recovered(store,relative,intent,*,frozen,reader):
    from ..media.continuity_report import validate_continuity_report
    folder=store.root/relative;reports=[];refs=[]
    for name in ('pair','after'):
        producer=reader.read(folder/(name+'-producer.json'))
        if producer['candidate_id']!=intent['candidate_id'] or producer['intent']!=artifact(folder/'intent.json'):
            raise ProductionRefused('repair recovered report producer differs')
        ref=artifact(Path(producer['audit_run_dir'])/'logs/continuity/report.json')
        valid=validate_continuity_report(ref,manifest=producer['manifest'],expected_audit_run_dir=producer['audit_run_dir'],
            config=frozen.config,timeout=checks.remaining(reader),_budget=reader)
        reports.append(ref);refs+=valid['closure']+[producer['manifest'],artifact(folder/(name+'-producer.json'))]
    media=reader.read(folder/'media.json')
    from ._scene_color_repair_media import validate_media
    validate_media(media,intent,config=frozen.config,reader=reader)
    refs+=media['evidence']+media['encoding']['command_receipts']+[artifact(folder/'engine/manifest.json')]
    _terminal(store,relative,intent,status='awaiting_review',fit=artifact(folder/'fit.json'),media=artifact(folder/'media.json'),
        pair_report=reports[0],before_report=reader.read(intent['binding']['assessment'])['report'],after_report=reports[1],refs=refs,reader=reader)
    _template(store,relative,frozen=frozen,reader=reader)
    return _result(frozen,'awaiting_review',folder=folder,candidate_id=intent['candidate_id'])


@production_execution
def propose_scene_color_repair(frozen,units,timeline,request_path,*,paths,logger,lock=None,timeout=300):
    acquired=None;store=None;candidate=None;folder=None
    try:
        reader=Reader(timeout)
        if lock is None:acquired=RunLock(run_for(frozen));acquired.__enter__();lock=acquired
        store=RepairStore(frozen,lock);store.reader=reader;store.owned()
        req=reader.read(request_path);candidate=uid(req['candidate_id']);folder=store.root/'candidates'/candidate
        context,source=checks.resolve_context(frozen,units,timeline,paths=paths,lock=lock)
        if logger is None:
            from .logging import RunLogger
            logger=RunLogger(run_for(frozen),production=True)
        return _propose(store,context,source,reader,request_path,frozen=frozen,paths=paths,logger=logger)
    except (KeyboardInterrupt,ValueError,OSError,RuntimeError,KeyError,TypeError,ImportError,TimeoutError) as exc:
        status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed' if isinstance(exc,(RuntimeError,TimeoutError,ImportError)) else 'blocked'
        if logger is not None:logger.exception('scene_color_repair',candidate,exc)
        error=_error(exc,folder)
        complete=(folder is not None and all((folder/name).exists() for name in ('fit.json','media.json','pair-producer.json','after-producer.json')))
        if complete:
            try:
                producer=Reader().read(folder/'after-producer.json')
                complete=(Path(producer['audit_run_dir'])/'logs/continuity/report.json').exists()
            except (ValueError,OSError,KeyError,TypeError):complete=False
        if store is not None and folder is not None and (folder/'intent.json').exists() and not (folder/'terminal.json').exists() and not (isinstance(exc,KeyboardInterrupt) and complete):
            try:
                store.reader=Reader()
                intent=Reader().read(folder/'intent.json')
                _terminal(store,folder.relative_to(store.root),intent,status='interrupted' if status=='interrupted' else 'failed',failure=error)
            except (ValueError,OSError,RuntimeError,KeyError,TypeError):pass
        return _result(frozen,status,folder=folder,candidate_id=candidate,error=error)
    finally:
        if acquired is not None:acquired.__exit__(None,None,None)


@production_execution
def consume_scene_color_repair_review(frozen,review_path,*,paths,logger,lock=None):
    acquired=None;folder=None;cid=None
    try:
        if lock is None:acquired=RunLock(run_for(frozen));acquired.__enter__();lock=acquired
        store=RepairStore(frozen,lock);store.owned();reader=Reader();store.reader=reader;original=artifact(review_path);review=reader.read(original)
        cid=uid(review['candidate_id']);relative=Path('candidates')/cid;folder=store.root/relative
        intent=reader.read(folder/'intent.json');checks.current_binding(frozen,intent,reader=reader)
        from ._scene_color_repair_engine import verify_engine
        verify_engine(folder,intent,reader=reader)
        terminal=checks.validate_saved_candidate(frozen,folder,reader=reader)
        if terminal['status']!='awaiting_review':raise ProductionRefused('repair candidate has no complete measured media for review')
        expected=checks.review_expected(frozen,folder,reader=reader);checks.validate_candidate_review(review,expected,reader=reader)
        retained=store.write_bytes(Path('reviews')/(original['sha256']+'.json'),Path(review_path).read_bytes());boundary('review-original')
        state,prior=checks.review_state(frozen,folder,reader=reader)
        if state=='rejected':
            if not (folder/'review-receipt.json').exists():
                value=dict(schema_version=1,run_id=store.run_dir.name,candidate_id=cid,terminal=artifact(folder/'terminal.json'),
                    review=prior,state='rejected',created_at=now())
                store.write(relative/'review-receipt.json',value);boundary('review-receipt')
            return _result(frozen,'blocked',folder=folder,candidate_id=cid,error=_error(ProductionRefused('retained failed review permanently rejects candidate')))
        if review['verdict']=='unverified':return _result(frozen,'awaiting_review',folder=folder,candidate_id=cid)
        if review['verdict']!='passed':raise ProductionRefused('repair review failed')
        receipt=folder/'review-receipt.json'
        if receipt.exists():
            checks.review_state(frozen,folder,reader=reader)
        else:
            checks.current_binding(frozen,intent,reader=reader)
            value=dict(schema_version=1,run_id=store.run_dir.name,candidate_id=cid,terminal=artifact(folder/'terminal.json'),
                review=artifact(retained),state='research_candidate_reviewed',created_at=now())
            store.write(relative/'review-receipt.json',value);boundary('review-receipt')
        return _result(frozen,'reviewed',folder=folder,candidate_id=cid)
    except (KeyboardInterrupt,ValueError,OSError,RuntimeError,KeyError,TypeError,ImportError,TimeoutError) as exc:
        status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'blocked'
        return _result(frozen,status,folder=folder,candidate_id=cid,error=_error(exc,folder))
    finally:
        if acquired is not None:acquired.__exit__(None,None,None)
