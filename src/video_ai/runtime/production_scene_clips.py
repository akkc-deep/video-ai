"""Prepared-run Wan chains, immutable native media and explicit playback gates."""
from dataclasses import dataclass,field
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4

from ..config import read_json
from ..jimeng_config import STRATEGY
from ..planning.production_scenes import canonical_digest
from .manifest import ManifestStore,create_manifest,hash_file,now,thaw,validate_run_dir
from .production_state import ProductionRefused,RunLock,object_fields,run_path
from .scene_clip_records import (scene_context,graph_for,expected_request,validate_clip,collect_progress,
    complete_value,validate_media_receipt,technical_recipes,equal)
from .scene_execution_records import verified_scene_execution_write


def boundary(point):
    """Durable caller-thread boundary for interruption tests."""


class InvalidGeneratedMedia(ProductionRefused):
    """Confirmed invalid decoded model output, rather than a local conversion failure."""


@dataclass(frozen=True)
class SceneClipResult:
    schema_version:int=2
    production_strategy:str=STRATEGY
    run_id:str|None=None
    run_dir:Path|None=None
    status:str='blocked'
    active_stage:str='source_clips'
    scenes:list=field(default_factory=list)
    observation_templates:list=field(default_factory=list)
    source_clips:Path|None=None
    log_dir:Path|None=None
    error:dict|None=None

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version!=2 or self.production_strategy!=STRATEGY:
            raise ValueError('invalid scene clip result schema')
        if self.status not in ('awaiting_continuity_review','source_clips_ready','blocked','failed','interrupted'):
            raise ValueError('invalid scene clip result status')
        if self.active_stage!='source_clips': raise ValueError('invalid scene clip result stage')
        if self.run_dir is not None:
            run=validate_run_dir(Path(self.run_dir)); object.__setattr__(self,'run_dir',run)
            if self.run_id!=run.name: raise ValueError('scene clip result run differs')
            for key in ('source_clips','log_dir'):
                value=getattr(self,key)
                if value is not None: object.__setattr__(self,key,run_path(run,value))
            for path in self.observation_templates: run_path(run,path)
        elif any(x is not None for x in (self.run_id,self.source_clips,self.log_dir)) or self.scenes or self.observation_templates:
            raise ValueError('scene clip result requires known run')
        if self.status=='source_clips_ready':
            if self.source_clips is None or not self.source_clips.is_file(): raise ValueError('ready requires complete admission')
        elif self.source_clips is not None: raise ValueError('source clips require ready status')
        if self.error is not None: object_fields(self.error,('kind','message','evidence_paths'),'scene clip error')
        for row in self.scenes:
            object_fields(row,'scene_id status completed_clip_ids accepted_clip_ids waiting_clip_id error'.split(),'scene result')
        json.dumps(self.to_dict(),allow_nan=False)

    def to_dict(self): return thaw(self)

    @property
    def exit_code(self):
        return dict(awaiting_continuity_review=3,source_clips_ready=0,blocked=2,failed=1,interrupted=130)[self.status]


def _error(exc,paths=()):
    message=str(exc) or type(exc).__name__
    for note in getattr(exc,'__notes__',()): message+='; '+note
    return dict(kind=type(exc).__name__,message=message,
                evidence_paths=[str(p) for p in paths])


def _result(run,status,*,scenes=None,templates=None,error=None):
    return SceneClipResult(run_id=run.name if run else None,run_dir=run,status=status,scenes=scenes or [],
        observation_templates=templates or [],source_clips=run/'production/scene-clips/complete.json' if status=='source_clips_ready' else None,
        log_dir=run/'logs/production' if run else None,error=error)


def _reconcile_service_ownership(manifest,guard):
    from .production_state import process_started_at
    old=manifest.snapshot().get('services',{}).get('comfyui')
    if not old or not old.get('owned') or old.get('status') in ('stopped','failed'): return
    guard()
    if process_started_at(old.get('pid')) is not None:
        raise ProductionRefused('previous live Comfy ownership cannot be transferred to this invocation')
    guard()
    def reconcile(value):
        if value.get('services',{}).get('comfyui')!=old: raise ProductionRefused('Comfy ownership record changed during recovery')
        value['services']['comfyui']=dict(old,status='stopped',updated_at=now(),recovery_reason='prior owned PID proven absent')
    manifest.update(reconcile)
    guard()


class _GuardedLogger:
    """Media helpers retain their API while every persistent log write checks ownership."""
    def __init__(self,logger,guard):self.logger,self.guard=logger,guard
    def __getattr__(self,name):return getattr(self.logger,name)
    def _write(self,name,*args,**kwargs):
        self.guard();return getattr(self.logger,name)(*args,**kwargs)
    def open_exclusive(self,*args,**kwargs):return self._write('open_exclusive',*args,**kwargs)
    def save_bytes(self,*args,**kwargs):return self._write('save_bytes',*args,**kwargs)
    def save_json(self,*args,**kwargs):return self._write('save_json',*args,**kwargs)
    def event(self,*args,**kwargs):return self._write('event',*args,**kwargs)
    def exception(self,*args,**kwargs):return self._write('exception',*args,**kwargs)
    def progress(self,*args,**kwargs):return self._write('progress',*args,**kwargs)


def _prepare_comfy_directories(run,guard):
    from .paths import PathPolicy
    policy=PathPolicy()
    for name in ('input','output','temp','user'):
        guard()
        policy.validate_write(run/'comfy'/name,'run').mkdir(parents=True,exist_ok=True)
    guard()


class _OwnedService:
    def __init__(self,frozen,paths,logger,lock):
        self.frozen,self.paths,self.logger,self.lock=frozen,paths,logger,lock
        self.run=logger.run_dir; self.manager=None; self.handle=None
        self.lease=None; self.sampler=None; self.stage='source_clips'

    def _start_resources(self,manifest):
        if self.frozen.config.raw.get('scene_rendering',{}).get('mode') != 'whole_scene_v1': return
        if self.lease is not None: return
        from .resources import GpuLease, ResourceSampler
        from .gpu_desktop import desktop_policy
        self.lease=GpuLease(self.paths,manifest,self.logger,resource_policy=desktop_policy)
        self.lease.acquire(self.stage,'whole_scene_v1',batch_size=1)
        self.sampler=ResourceSampler(self.run,lambda: ({os.getpid()} |
            (self.manager.owned_pids if self.manager is not None else set())),interval_seconds=2)
        self.sampler.start()

    def ensure(self):
        if self.handle is not None: return
        from .services import ServiceManager,port_listening
        from .service_specs import build_service_specs
        from .logging import RunLogger
        from ..adapters.scene_comfy import SceneComfyClient
        from ..adapters.common import strict_json,AdapterError,FailureKind
        run=self.run; frozen=self.frozen
        def guard():
            if read_json(self.lock.path)!=self.lock.owner: raise ProductionRefused('service lost run lock')
        guard()
        if (run/'manifest.json').exists():
            manifest=ManifestStore.open(run,verify_integrity=False)
            snapshot=manifest.snapshot()
            resolved=thaw(frozen.config); voice=resolved.pop('voice'); resolved.pop('raw'); voice.pop('raw')
            if snapshot['run_id']!=run.name or snapshot['config_snapshot']['raw']!=thaw(frozen.config.raw) or snapshot['config_snapshot']['resolved']!=resolved:
                raise ProductionRefused('service manifest differs from frozen inputs')
            _reconcile_service_ownership(manifest,guard)
        else:
            manifest=create_manifest(run,frozen.config,inputs={'script':hash_file(Path(frozen.options['script_path']))},
                                     models={},workflows={},verify_integrity=False)
        # Keep health evidence under the held run lock. The caller's full model
        # admission guard remains outside the two-second HTTP probe budget.
        guard()
        health_logger=_GuardedLogger(RunLogger(run,production=True),guard)
        class Health:
            def __init__(inner,url,timeout,ignored_logger):
                inner.client=SceneComfyClient(url,request_timeout=timeout,ownership_check=guard)
            def get_json(inner,route,**kwargs):
                timeout=kwargs.get('timeout',2)
                try:
                    response=inner.client.system_stats(timeout=timeout) if route=='/system_stats' else inner.client.queue(timeout=timeout)
                except OSError as exc:
                    raise AdapterError(FailureKind.unavailable,'bounded Comfy health unavailable: '+str(exc)) from exc
                guard()
                token=uuid4().hex
                health_logger.save_json('scene-clips/service/'+token+'.json',dict(method='GET',route=route,status=response['status'],
                    headers=response['headers'],body=response['body'].decode('utf-8'),finished_at=now()))
                try:
                    if response['status']!=200: raise ValueError('health HTTP status differs')
                    return strict_json(response['body'])
                except ValueError as exc:
                    raise AdapterError(FailureKind.invalid_result,'invalid Comfy health response') from exc
        if port_listening(frozen.config.services['comfyui'],3): raise ProductionRefused('external Comfy service already listening')
        _prepare_comfy_directories(run,guard)
        self.manager=ServiceManager(self.paths,manifest,self.logger,http_factory=Health)
        guard()
        self._start_resources(manifest)
        self.handle=self.manager.ensure(build_service_specs(frozen.config,run,production=True,frozen=frozen,store=manifest)['comfyui'])
        if not self.handle.owned: raise ProductionRefused('Comfy service is not owned by this run')

    def close(self):
        try:
            if self.sampler is not None:
                self.sampler.stop()
                self.logger.save_json('scene-clips/resources/'+uuid4().hex+'.summary.json',self.sampler.summary())
                self.sampler=None
        finally:
            try:
                if self.manager is not None and self.handle is not None: self.manager.stop(self.handle)
            finally:
                if self.lease is not None:
                    self.lease.release(); self.lease=None


def _evidence(store,paths):
    # Empty stdout/stderr carry no media identity; command/probe JSON binds the invocation.
    return [store.artifact(p) for p in dict.fromkeys(str(x) for x in paths) if Path(p).stat().st_size>0]


def _media(context,row,operation,source,target,recipe,producer):
    store=context['store']; folder=store.clip_dir(row['budget']['clip_id']); store.assert_owned()
    old=validate_media_receipt(store,folder,operation,source=source,target=target,recipe=recipe,promote=True)
    if old is not None: return old['target'],old['evidence']
    if target.exists(): raise ProductionRefused('existing media lacks matching preparation receipt: '+str(target))
    store.validate_artifact(source)
    staging=folder/'staging'/uuid4().hex/target.name
    staging.parent.mkdir(parents=True,exist_ok=False)
    evidence=producer(staging)
    store.assert_owned(); store.validate_artifact(source)
    staged=store.artifact(staging); final=dict(staged,path=str(target))
    value=dict(schema_version=2,run_id=store.run_dir.name,clip_id=folder.name,operation=operation,source=source,
        staging=staged,target=final,recipe=recipe,evidence=_evidence(store,evidence),created_at=now())
    store.write(folder/'media-ready'/(operation+'.json'),value); boundary('media-'+operation+'-ready')
    validate_media_receipt(store,folder,operation,source=source,target=target,recipe=recipe,promote=True)
    boundary('media-'+operation+'-promoted')
    return final,value['evidence']


def _copy(store,source,target):
    store.validate_artifact(source)
    with Path(source['path']).open('rb') as src,target.open('xb') as dst:
        shutil.copyfileobj(src,dst); dst.flush(); os.fsync(dst.fileno())
    store.validate_artifact(source)
    if store.artifact(target)['sha256']!=source['sha256']: raise ProductionRefused('media copy bytes differ')
    return []


def _input(context,row,parent,*,paths,logger):
    from ..media.images import adapt_image,contain_filter
    store=context['store']; b=row['budget']; cid=b['clip_id']; folder=store.clip_dir(cid); p=row['parameters']
    selected=next(s for s in context['wan']['scenes'] if s['scene_id']==b['scene_id'])
    source={k:selected[k] for k in ('path','bytes','sha256')} if parent is None else parent['last_frame']['image']
    w,h=p['width'],p['height']; rule='contain_png_v1' if parent is None else 'identity_png_copy_v1'
    filter_value=contain_filter(w,h) if parent is None else None
    target=store.run_dir/'comfy/input'/store.run_dir.name/'scene_clips'/cid/'start.png'
    def produce(staging):
        if parent is not None: return _copy(store,source,staging)
        _,evidence=adapt_image(Path(source['path']),staging,width=w,height=h,config=context['frozen'].config,
            paths=paths,logger=logger,unit_id=cid,stage='source_clips',timeout=300)
        return evidence
    image,_=_media(context,row,'input',source,target,dict(algorithm=rule,
        parameters=dict(filter=filter_value,width=w,height=h) if parent is None else {}),produce)
    value=dict(schema_version=2,run_id=store.run_dir.name,clip_id=cid,kind=b['input_kind'],source=source,target=image,
        rule=rule,filter=filter_value,width=w,height=h,pixel_format='rgb24')
    store.write(folder/'input.json',value); boundary('input')
    return value


def _technical(context,row,submission,request,*,paths,logger):
    from ..media.video import inspect_video,trim_scene_video
    from ..media.frames import extract_native_frame
    from ..planning.scene_clip_continuation import scene_clip_frame_mapping
    store=context['store']; b=row['budget']; cid=b['clip_id']; folder=store.clip_dir(cid); p=row['parameters']
    kwargs=dict(config=context['frozen'].config,paths=paths,logger=logger,unit_id=cid,timeout=300)
    w,h=p['width'],p['height']
    def generated_producer(staging):
        _copy(store,submission['output'],staging)
        try:
            info,evidence=inspect_video(staging,width=w,height=h,**kwargs)
        except ValueError as exc:
            raise InvalidGeneratedMedia('model output violates decoded native video contract: '+str(exc)) from exc
        if info['frames']!=b['generated_frames']: raise InvalidGeneratedMedia('model output exact generated frame count differs')
        return evidence
    generated,ge=_media(context,row,'generated',submission['output'],folder/'generated.mp4',
        dict(algorithm='identity_copy_v1',parameters={}),generated_producer)
    a,z=b['retained_source_start'],b['retained_source_end']
    def source_producer(staging):
        info,_=inspect_video(Path(generated['path']),width=w,height=h,**kwargs)
        _,evidence=trim_scene_video(Path(generated['path']),staging,source_info=info,start_frame=a,end_frame=z,width=w,height=h,**kwargs)
        return evidence
    source,se=_media(context,row,'source',generated,folder/'source.mp4',dict(algorithm='trim_native16_v1',
        parameters=dict(start_frame=a,end_frame=z,filter=f'trim=start_frame={a}:end_frame={z},setpts=N/(16*TB)')),source_producer)
    def frame_producer(staging):
        _,evidence=extract_native_frame(Path(generated['path']),staging,source_frame_index=z-1,
            expected_frames=b['generated_frames'],width=w,height=h,**kwargs)
        return evidence
    image,le=_media(context,row,'last_frame',generated,folder/f'frame_{z:06d}.png',dict(algorithm='native_index_rgb24_v1',
        parameters=dict(source_frame_index=z-1,expected_frames=b['generated_frames'],width=w,height=h,
                        filter=f'select=eq(n\\,{z-1}),format=rgb24')),frame_producer)
    last=dict(schema_version=2,run_id=store.run_dir.name,clip_id=cid,generated=generated,source_frame_index=z-1,
        global_output_frame_index=b['end_frame']-1,image=image,extraction_rule='native_index_rgb24_v1',evidence=le)
    store.write(folder/'last-frame.json',last); boundary('last-frame')
    mapping=scene_clip_frame_mapping(b,actual_generated_frames=b['generated_frames'])
    store.write(folder/'mapping.json',mapping); boundary('mapping')
    old=store.read(folder/'clip.json')
    clip=dict(schema_version=2,production_strategy=STRATEGY,run_id=store.run_dir.name,scene_id=b['scene_id'],clip_id=cid,
        request_sha256=canonical_digest(request),submission_sha256=canonical_digest(submission),generated=generated,source=source,
        frame_mapping_sha256=canonical_digest(mapping),last_frame_sha256=canonical_digest(last),technical_evidence=ge+se+le,
        created_at=store.read(folder/'media-ready/last_frame.json')['created_at'])
    store.write(folder/'clip.json',clip); boundary('clip')


def _finish(context,errors=None):
    store=context['store']; store.verify_global()
    progress,records=collect_progress(context); scenes=progress['scenes']; templates=[]
    for row in context['rows']:
        cid=row['budget']['clip_id']; record=records.get(cid)
        if record and not record['accepted'] and not record['rejected']:
            path=store.write(store.clip_dir(cid)/'observation-template.json',record['template'])
            templates.append(str(path))
    for scene in scenes:
        if errors and scene['scene_id'] in errors:
            status,error=errors[scene['scene_id']]; scene.update(status=status,error=error)
    if any(s['status']=='failed' for s in scenes): status='failed'
    elif any(s['status'] in ('blocked','continuity_failed','submit_unknown','pending') for s in scenes): status='blocked'
    elif any(s['status']=='awaiting_continuity_review' for s in scenes): status='awaiting_continuity_review'
    else:
        store.write('complete.json',complete_value(context,records)); boundary('complete'); status='source_clips_ready'
    error=next((s['error'] for s in scenes if s['error']),None)
    from .scene_continuity_records import load_continuity_policy,require_scene_continuity_acceptance,SceneContinuityPending
    if load_continuity_policy(context['frozen']) is not None:
        try:
            require_scene_continuity_acceptance(context['frozen'],context['units'],context['timeline'])
        except SceneContinuityPending as exc:
            if status!='failed':status='awaiting_continuity_review'
            error=error or _error(exc)
    return _result(store.run_dir,status,scenes=scenes,templates=templates,error=error)


def _produce(context,*,paths,logger,client_factory,service_factory):
    from ..adapters.scene_comfy import SceneComfyClient
    from .scene_comfy_transactions import recover_or_submit_scene_clip,SceneSubmitUnknown
    from .production_inputs import check_stage_space
    store=context['store']; store.assert_owned()
    logger=_GuardedLogger(logger,store.assert_owned)
    check_stage_space(context['frozen'].config,frames=sum(r['budget']['generated_frames'] for r in context['rows']))
    # All graphs, all existing chains and originals are validated before the first ensure or POST.
    for row in context['rows']: graph_for(context,row)
    store.write('inputs.json',context['inputs']); boundary('inputs')
    _restore_outer(context,paths=paths,logger=logger)
    progress,_=collect_progress(context)
    whole = context.get('execution') is not None and context['execution']['mode']=='whole_scene_v1'
    if whole and any(row['status'] in ('failed','continuity_failed') for row in progress['scenes']):
        return _finish(context)
    from .scene_continuity_records import load_continuity_policy
    if load_continuity_policy(context['frozen']) is not None:
        from .production_scene_continuity import ensure_initial_epoch
        ensure_initial_epoch(context['frozen'],context['units'],context['timeline'],paths=paths,logger=logger,lock=store.lock)
    service=None; errors={}; result=None
    def ensure():
        nonlocal service
        store.assert_owned()
        if service is None: service=(service_factory or _OwnedService)(context['frozen'],paths,logger,store.lock)
        service.ensure(); store.assert_owned()
    try:
        for scene in context['plan']['scenes']:
            parent=None
            for row in [r for r in context['rows'] if r['budget']['scene_id']==scene['scene_id']]:
                b=row['budget']; cid=b['clip_id']; folder=store.clip_dir(cid)
                store.assert_owned()
                old=validate_clip(context,row,parent)
                if old:
                    if not old['accepted'] or old['rejected']: break
                    parent=old; continue
                try:
                    # Existing original intents only recover their own GET evidence.
                    # Admission is checked before allocating a new child request.
                    if parent is not None and load_continuity_policy(context['frozen']) is not None and store.read(folder/'intent.json') is None:
                        from .scene_continuity_records import require_scene_continuity_acceptance
                        require_scene_continuity_acceptance(context['frozen'],context['units'],context['timeline'],
                            clip_id=parent['clip']['clip_id'])
                    input_record=_input(context,row,parent,paths=paths,logger=logger)
                    graph=graph_for(context,row); request=expected_request(context,row,input_record,parent)
                    store.write(folder/'graph.json',graph); store.write(folder/'request.json',request); boundary('request')
                    factory=client_factory or SceneComfyClient
                    client=factory(context['frozen'].config.services['comfyui'],
                        request_timeout=context['frozen'].config.timeouts['comfy_request'],ownership_check=store.capture_guard(request,graph))
                    submission=recover_or_submit_scene_clip(store,request,graph,client=client,template=context['template'],
                        ensure_service=ensure,logger=logger,timeout=context['frozen'].config.timeouts['wan'],
                        request_timeout_seconds=context['frozen'].config.timeouts['comfy_request'])
                    try:
                        _technical(context,row,submission,request,paths=paths,logger=logger)
                    except InvalidGeneratedMedia as exc:
                        store.assert_owned()
                        intent=store.read(folder/'intent.json')
                        # Deterministic media rejection is terminal, retaining the original
                        # owned output. Interrupted or unavailable disk work is resumable.
                        store.write(folder/'terminal.json',dict(schema_version=2,run_id=store.run_dir.name,
                            clip_id=cid,intent_sha256=canonical_digest(intent),status='invalid_media',
                            evidence=[submission['output']],reason=str(exc) or type(exc).__name__))
                        raise RuntimeError('invalid original model media: '+str(exc)) from exc
                    new=validate_clip(context,row,parent)
                    store.write(folder/'observation-template.json',new['template']); boundary('observation-template')
                    break  # No process observation has been authored for this new technical clip.
                except KeyboardInterrupt: raise
                except Exception as exc:
                    store.assert_owned()
                    terminal=store.read(folder/'terminal.json')
                    from .scene_continuity_records import SceneContinuityPending
                    status=('awaiting_continuity_review' if isinstance(exc,SceneContinuityPending)
                            else 'failed' if terminal is not None else 'submit_unknown' if isinstance(exc,SceneSubmitUnknown)
                            else 'blocked' if isinstance(exc,ProductionRefused) else 'failed')
                    evidence=[str(p) for p in folder.rglob('*') if p.is_file()]
                    errors[scene['scene_id']]=(status,_error(exc,evidence))
                    break
            if whole and errors: break
        result=_finish(context,errors)
        return result
    finally:
        original=sys.exception()
        if service is not None:
            try: service.close()
            except Exception as cleanup:
                if original is not None:
                    original.add_note('service cleanup failed: '+str(cleanup))
                elif result is not None:
                    error=_error(cleanup)
                    if result.error:
                        error['message']=result.error['message']+'; service cleanup failed: '+error['message']
                        error['evidence_paths']=result.error['evidence_paths']
                    return _result(store.run_dir,'failed',scenes=result.scenes,templates=result.observation_templates,error=error)
                else: raise


def _restore_outer(context,*,paths,logger):
    """Restore indexes only from exact existing receipts; never perform media work."""
    from ..planning.scene_clip_continuation import scene_clip_frame_mapping
    store=context['store']
    parents={}
    for row in context['rows']:
        folder=store.clip_dir(row['budget']['clip_id']); clip=store.read(folder/'clip.json')
        b=row['budget']; recipes=technical_recipes(row)
        parent=parents.get(b['scene_id'])
        if b['parent_clip_id'] and (parent is None or not parent['accepted']): continue
        if clip is None:
            # A lost technical marker can be rebuilt using immutable media receipts and
            # a deterministic creation time (the final extraction receipt time).
            if not all(store.read(folder/'media-ready'/(op+'.json')) is not None for op in ('input','generated','source','last_frame')): continue
            from .scene_comfy_transactions import validate_scene_submission
            request=store.read(folder/'request.json'); graph=store.read(folder/'graph.json')
            if request is None or graph is None: raise ProductionRefused('prepared technical media lacks original request')
            submission=validate_scene_submission(store,request,graph)
            if submission is None: raise ProductionRefused('prepared technical media lacks original submission')
            _input(context,row,parent,paths=paths,logger=logger)
            _technical(context,row,submission,request,paths=paths,logger=logger)
            clip=store.read(folder/'clip.json')
        elif store.read(folder/'input.json') is None:
            if store.read(folder/'media-ready/input.json') is None: raise ProductionRefused('technical clip lacks input receipt')
            _input(context,row,parent,paths=paths,logger=logger)
        # Before any metadata restoration prove that all exact receipt-bound media exist.
        for operation,target in (('generated',folder/'generated.mp4'),('source',folder/'source.mp4'),
                                 ('last_frame',folder/f"frame_{b['retained_source_end']:06d}.png")):
            validate_media_receipt(store,folder,operation,target=target,recipe=recipes[operation],required=True,promote=True)
        mapping=scene_clip_frame_mapping(b,actual_generated_frames=b['generated_frames'])
        equal(canonical_digest(mapping),clip['frame_mapping_sha256'],'recover mapping')
        store.write(folder/'mapping.json',mapping)
        last_receipt=store.read(folder/'media-ready/last_frame.json')
        last=dict(schema_version=2,run_id=store.run_dir.name,clip_id=b['clip_id'],generated=clip['generated'],
            source_frame_index=b['retained_source_end']-1,global_output_frame_index=b['end_frame']-1,
            image=last_receipt['target'],extraction_rule='native_index_rgb24_v1',evidence=last_receipt['evidence'])
        equal(canonical_digest(last),clip['last_frame_sha256'],'recover last frame')
        store.write(folder/'last-frame.json',last)
        record=validate_clip(context,row,parent)
        if record['rejected'] and record['rejected'].get('_raw_only'):
            source=record['rejected']
            receipt=dict(schema_version=2,run_id=store.run_dir.name,clip_id=b['clip_id'],
                clip_sha256=canonical_digest(record['clip']),request_sha256=canonical_digest(record['request']),
                observation=source['observation'],observation_sha256=source['observation_sha256'],rejected_at=now())
            store.write(folder/'observation-rejected.json',receipt)
            record['rejected']=receipt
        parents[b['scene_id']]=record


def _check_observation_replacement(record,value):
    if record['rejected']:
        rejected=record['rejected']
        if not (rejected.get('_raw_only') and value.get('verdict')=='failed'
                and rejected['observation_sha256']==canonical_digest(value)):
            raise ProductionRefused('explicit failed clip requires a revision run')
    if record['accepted'] and (value.get('verdict')!='passed' or
            record['accepted']['observation_sha256']!=canonical_digest(value)):
        raise ProductionRefused('accepted observation cannot be replaced; use a revision run')


def _consume(context,observation_path):
    from .scene_clip_observations import validate_scene_clip_observation
    from ..adapters.common import strict_json,JSON_LIMIT
    store=context['store']; store.assert_owned(); progress,records=collect_progress(context)
    raw=Path(observation_path).read_bytes()
    if len(raw)>JSON_LIMIT: raise ProductionRefused('observation exceeds JSON_LIMIT')
    value=strict_json(raw)
    cid=value.get('clip_id') if isinstance(value,dict) else None
    record=records.get(cid)
    if record is None: raise ProductionRefused('observation clip is not technically complete')
    _check_observation_replacement(record,value)
    current=datetime.now(timezone.utc)
    validate_scene_clip_observation(value,dict(template=record['template'],created_at=record['clip']['created_at']),now=current)
    folder=store.clip_dir(cid)
    original=store.write_bytes(folder/'observations'/(hashlib_sha(raw)+'.json'),raw)
    boundary('observation-original')
    # Reconstruct all immutable inputs/media after reading the source and before admission.
    # Every upstream record and original was fully admitted at entry. Exact raw
    # byte and inventory rechecks make that admission current without rerunning
    # the same decoders; this cache never crosses a public API invocation.
    store.verify_global()
    progress,records=collect_progress(context); record=records[cid]
    _check_observation_replacement(record,value)
    validate_scene_clip_observation(value,dict(template=record['template'],created_at=record['clip']['created_at']),now=current)
    if value['verdict'] in ('passed','failed'):
        filename='observation-accepted.json' if value['verdict']=='passed' else 'observation-rejected.json'
        time_key='accepted_at' if value['verdict']=='passed' else 'rejected_at'
        prior=store.read(folder/filename)
        if prior is None:
            store.write(folder/filename,dict(schema_version=2,run_id=store.run_dir.name,clip_id=cid,
                clip_sha256=canonical_digest(record['clip']),request_sha256=canonical_digest(record['request']),
                observation=store.artifact(original),observation_sha256=canonical_digest(value),**{time_key:current.isoformat()}))
        elif value['verdict']=='failed' or prior['observation_sha256']!=canonical_digest(value):
            raise ProductionRefused('accepted/rejected observation cannot be replaced')
        boundary('observation-receipt')
    return _finish(context)


def hashlib_sha(raw):
    import hashlib
    return hashlib.sha256(raw).hexdigest()


@verified_scene_execution_write
def _entry(frozen,units,timeline,*,paths,logger,lock,operation):
    run=None; acquired=None; result=None
    try:
        candidate=validate_run_dir(Path(frozen.options['script_path']).parent.parent)
        if (frozen.options['run_id']!=candidate.name or not candidate.is_dir()
                or not run_path(candidate,candidate/'production/options.json').is_file()):
            raise ProductionRefused('unknown prepared scene clip run')
        run=candidate
        if logger.run_dir!=run or not logger.production: raise ProductionRefused('scene clips require matching production logger')
        if lock is None:
            acquired=RunLock(run); acquired.__enter__(); lock=acquired
        context=scene_context(frozen,units,timeline,paths=paths,lock=lock); context['store'].assert_owned()
        result=operation(context)
    except KeyboardInterrupt as exc: result=_result(run,'interrupted',error=_error(exc))
    except ProductionRefused as exc: result=_result(run,'blocked',error=_error(exc))
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,AttributeError) as exc: result=_result(run,'failed',error=_error(exc))
    finally:
        if acquired is not None:
            try: acquired.__exit__(None,None,None)
            except Exception as exc:
                original=result.error if result else None
                error=_error(exc)
                if original: error['message']=original['message']+'; cleanup: '+error['message']
                result=_result(run,'failed',error=error)
    return result


from .scene_revision_records import revision_validation
from .execution_limits import production_execution


@production_execution
@revision_validation
def produce_scene_clips(frozen,units,timeline,*,paths,logger,client_factory=None,service_factory=None,lock=None):
    return _entry(frozen,units,timeline,paths=paths,logger=logger,lock=lock,
        operation=lambda context:_produce(context,paths=paths,logger=logger,client_factory=client_factory,service_factory=service_factory))


@production_execution
@revision_validation
def consume_scene_clip_observation(frozen,units,timeline,observation_path,*,paths,logger,lock=None):
    return _entry(frozen,units,timeline,paths=paths,logger=logger,lock=lock,
        operation=lambda context:_consume(context,observation_path))
