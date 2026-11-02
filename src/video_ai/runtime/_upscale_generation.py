"""Owned, serial once-only frame inference with durable execution policy."""
from datetime import datetime
from pathlib import Path
import time

from ..adapters.common import AdapterError,FailureKind,HttpClient
from ..adapters.comfyui import ComfyClient
from ..media.frames import extract_video_frames,encode_video_frames
from ..media.images import validate_start_png
from ..planning.upscale import clip_deadline_seconds
from .component_checks import output_path
from .manifest import FileIdentity,hash_file,thaw
from .paths import RuntimePaths
from .services import ServiceManager,ServiceConflictError
from .owned_cleanup import stop_owned_preserving_exception
from .service_specs import build_service_specs
from .timeline_checks import _local,_again,_artifact
from ._source_clip_generation import copy
from ._upscale_inputs import fresh,same,graph,evidence,before_post,validate_remote
from .execution_limits import execution_deadline,unlimited_execution
from ._legacy_execution_policy import unlimited_policy


def remaining(end):
    if end is None:return None
    value=end-time.monotonic()
    if value<=0:raise TimeoutError('upscale absolute deadline exhausted; no retry')
    return value


class DeadlineHttp(HttpClient):
    def set_deadlines(self,clip_end,frame_end):
        self.end=None if unlimited_execution() else frame_end if clip_end is None else min(clip_end,frame_end)
    def remaining(self):
        if self.end is None:return None
        value=self.end-time.monotonic()
        if hasattr(self,'wall_end'):value=min(value,self.wall_end-time.time())
        if value<=0:raise AdapterError(FailureKind.ambiguous,'upscale frame/clip deadline exhausted; no repost')
        return value
    def request(self,*args,**kwargs):
        # Apply the recording reserve to legacy monotonic-only frames too:
        # coarse Windows ticks can overstate the durable wall-clock remainder.
        left=self.remaining()
        budget=min(kwargs.get('timeout') or self.timeout,self.timeout)
        if left is not None:budget=min(budget,left-.1)
        if budget<=0:raise AdapterError(FailureKind.ambiguous,'upscale deadline recording reserve exhausted before HTTP; no repost')
        if self.end is not None and hasattr(self,'wall_end'):
            # Windows monotonic may be coarser than durable wall timestamps. Reserve
            # recording time conservatively; replay still enforces exact bounds.
            budget=min(budget,self.wall_end-time.time()-.1)
            if budget<=0:raise AdapterError(FailureKind.ambiguous,'upscale frame wall deadline exhausted before HTTP; no repost')
        kwargs['timeout']=budget
        if kwargs.get('stage') is None:kwargs['stage']='upscale'
        if kwargs.get('unit_id') is None:kwargs['unit_id']=self.unit_id
        try:
            response=super().request(*args,**kwargs)
        except AdapterError as exc:
            self.paths.extend(exc.evidence_paths);raise
        # Every request's evidence is indexed at creation, never by scanning other frames.
        body=response.evidence_path;stem=body.with_suffix('')
        self.paths.extend((stem.with_suffix('.request.json'),stem.with_suffix('.response.json'),body))
        self.remaining()
        if len(args)>1 and args[1]=='/object_info':validate_remote(self.template,self.parse_json(response))
        return response


def generate(config,run,store,logger,context,records,clips, *, resume=None, before_generate=None):
    verify_integrity=context.get('verify_integrity',True)
    def receipt(record):
        return fresh(record,run=run) if verify_integrity else FileIdentity(**thaw(record))
    paths=RuntimePaths.from_config(config);manager=ServiceManager(paths,resume['service_store'] if resume is not None else store,logger);handle=None
    for name in ('input','output','temp','user'):_local(run,run/'comfy'/name).mkdir(parents=True,exist_ok=True)
    try:
        handle=manager.ensure(build_service_specs(config,run,**({'model_stage':'upscale'} if 'model_loader_binding' in context['identities'] else {}))['comfyui'])
        if not handle.owned:raise ServiceConflictError('external Comfy service; refuse takeover')
        if before_generate is not None:before_generate()
        for plan,source in zip(context['plans'],context['source']['clips']):
            uid=plan.shot_id
            if resume is not None and uid in resume['completed_clips']:continue
            clip_end=None if unlimited_execution() or resume is not None or context.get('no_total_timeout') else time.monotonic()+clip_deadline_seconds(frame_count=plan.source_frames,base_seconds=config.timeouts['upscale_clip'])
            original=Path(plan.source_identity['path'])
            if verify_integrity:fresh(thaw(plan.source_identity),run=run)
            reused=resume['partial'].get(uid) if resume is not None else None
            if reused is None:
                rows,logs=extract_video_frames(original,run/'shots'/uid/'frames',expected_frames=plan.source_frames,
                    width=source['width'],height=source['height'],config=config,paths=paths,logger=logger,unit_id=uid,timeout=300 if clip_end is None else remaining(clip_end))
                base=evidence(run,records,logs);frames=[]
                if context.get('imported_frames'):
                    frames=[dict(frame,input_identity=rows[frame['frame_index']-1]['identity']) for frame in context['imported_frames'].values() if frame['shot_id']==uid]
            else:rows,base,frames=reused['rows'],reused['base'],list(reused['frames'])
            destination=_local(run,run/'shots'/uid/'upscaled-frames')
            if reused is None:destination.mkdir(exist_ok=bool(frames))
            for row in rows:
                index=row['index'];unit_id=f'{uid}:frame_{index:06d}'
                if index<=len(frames):continue
                frame_end=execution_deadline(config.timeouts['upscale_frame'],time.monotonic())
                if clip_end is not None:frame_end=min(clip_end,frame_end)
                remaining(frame_end)
                store.record_unit('frame',unit_id,'running')
                source_png=Path(row['identity']['path'])
                if verify_integrity:fresh(row['identity'],run=run)
                copy_path=run/'comfy/input'/run.name/'upscale'/uid/f'frame_{index:06d}.png'
                if resume is not None and unit_id==resume['unit_id'] and resume['input_copy'] is not None:
                    copied=fresh(resume['input_copy'],run=run,expected=copy_path)
                    if copied.bytes!=row['identity']['bytes'] or copied.sha256!=row['identity']['sha256']:raise ValueError('reused input copy differs')
                else:copied=copy(run,source_png,copy_path)
                http=DeadlineHttp(config.services['comfyui'],config.timeouts['comfy_request'],logger)
                http.set_deadlines(clip_end,frame_end);http.paths=[];http.unit_id=unit_id;http.template=context['template']
                if not unlimited_execution() and (resume is not None or context.get('no_total_timeout')):
                    started=store.snapshot()['units']['frame'][unit_id]['started_at']
                    http.wall_end=max(datetime.fromisoformat(started).timestamp(),copied.mtime_ns/1e9)+config.timeouts['upscale_frame']
                client=ComfyClient(http,store,logger);client.validate_template(context['template'])
                actual=graph(context['template'],run,plan,index)
                if verify_integrity:before_post(config,run,context,plan,row,copied,actual)
                http.remaining()
                submission=client.submit_once(actual,stage='upscale',kind='frame',unit_id=unit_id)
                history=client.wait_for(submission,deadline_seconds=http.remaining());http.remaining()
                if len(history.outputs)!=1:raise ValueError('exactly one mapped PNG required')
                output=_local(run,output_path(run,history.outputs[0]));saved=store.snapshot()['units']['frame'][unit_id]['submission']
                prefix=f'frame_{index:06d}_'
                if output.parent!=run/'comfy/output'/run.name/'upscale'/uid or not output.name.startswith(prefix) or output.suffix.lower()!='.png':
                    raise ValueError('mapped PNG is not the exact frame output namespace/prefix')
                if output.stat().st_mtime_ns<int(datetime.fromisoformat(saved['submitted_at']).timestamp()*1e9):raise ValueError('mapped output predates submission')
                info,more=validate_start_png(output,width=1920,height=1080,config=config,paths=paths,logger=logger,
                    unit_id=unit_id,stage='upscale',timeout=remaining(frame_end))
                upscaled=copy(run,output,destination/f'frame_{index:06d}.png')
                if verify_integrity:fresh(info['identity'],run=run)
                names=evidence(run,records,[source_png,Path(copied.path),output,Path(upscaled.path),Path(saved['request_path']),history.evidence_path,*http.paths,*more])
                checkpoint=dict(schema_version=1,run_id=run.name,shot_id=uid,frame_index=index,source_frame_index=index-1,
                    source_identity=thaw(plan.source_identity),input_identity=row['identity'],input_copy_identity=thaw(copied),
                    workflow_identity=thaw(context['identities']['workflow']),mapping_identity=thaw(context['identities']['mapping']),
                    model_identity=thaw(context['identities']['model']),parameters=thaw(plan.parameters),
                    submission=dict(attempt_id=submission.attempt_id,prompt_id=submission.prompt_id,intent_identity=thaw(hash_file(Path(saved['request_path'])))),
                    output_identity=info['identity'],upscaled_frame_identity=thaw(upscaled),evidence_identities=names)
                if unlimited_execution():checkpoint['execution_policy']=unlimited_policy()
                path=logger.save_json(f'upscale/frame-{uid}-{index:06d}.json',checkpoint);checkpoint_id=hash_file(path)
                evidence(run,records,[path]);frames.append(dict(checkpoint,checkpoint_identity=thaw(checkpoint_id)))
                remaining(frame_end)
                store.record_unit('frame',unit_id,'completed',artifacts=[_artifact(checkpoint_id),_artifact(receipt(row['identity'])),_artifact(upscaled)])
                remaining(frame_end)
            info,more=encode_video_frames(destination,run/'shots'/uid/'upscaled.mp4',frames=plan.source_frames,
                config=config,paths=paths,logger=logger,unit_id=uid,timeout=300 if clip_end is None else remaining(clip_end))
            names=evidence(run,records,more)
            native_frames=[f for f in frames if f"{uid}:frame_{f['frame_index']:06d}" not in context.get('imported_frames',{})]
            clip=dict(shot_id=uid,primary_unit_id=plan.primary_unit_id,budget=thaw(plan.budget),source_identity=thaw(plan.source_identity),
                upscaled_identity=info['identity'],width=1920,height=1080,native_fps=16,source_frames=plan.source_frames,
                upscaled_frames=plan.source_frames,parameters=thaw(plan.parameters),frames=frames,
                evidence_identities=list(dict.fromkeys(base+[n for f in native_frames for n in f['evidence_identities']]+[Path(f['checkpoint_identity']['path']).relative_to(run).as_posix() for f in native_frames]+names)))
            if unlimited_execution():clip['execution_policy']=unlimited_policy()
            path=logger.save_json(f'upscale/clip-{uid}.json',clip);evidence(run,records,[path]);clips.append(clip)
            if clip_end is not None:remaining(clip_end)
    finally:
        stop_owned_preserving_exception(manager,handle,logger,'upscale',require_stopped=True)
    if verify_integrity:_again(context['identities'])
