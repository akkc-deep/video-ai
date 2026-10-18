"""Serial, owned Wan generation with exactly one proven-short supplement."""
from datetime import datetime
from pathlib import Path
import os
import shutil
import time

from ..adapters.common import AdapterError,FailureKind,HttpClient
from ..adapters.comfyui import ComfyClient
from ..config import read_json
from ..media.video import inspect_video,trim_video
from ..planning.source_clips import supplement_frames
from .component_checks import output_path
from .manifest import hash_file,thaw
from .paths import RuntimePaths
from .services import ServiceManager,ServiceConflictError
from .owned_cleanup import stop_owned_preserving_exception
from .service_specs import build_service_specs
from .timeline_checks import _local,_again,_artifact
from ._source_clip_inputs import fresh,same,graph,evidence


class DeadlineHttp(HttpClient):
    def set_deadline(self,seconds):self.end=time.monotonic()+seconds
    def remaining(self):
        value=self.end-time.monotonic()
        if value<=0:raise AdapterError(FailureKind.ambiguous,'Wan attempt deadline exhausted; no repost')
        return value
    def request(self,*args,**kwargs):
        kwargs['timeout']=min(kwargs.get('timeout') or self.timeout,self.remaining())
        result=super().request(*args,**kwargs)
        self.remaining()
        return result


def copy(run,source,target):
    target=_local(run,target);target.parent.mkdir(parents=True,exist_ok=True)
    before=hash_file(source)
    with source.open('rb') as src,target.open('xb') as dst:
        shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
    after=hash_file(target);_again({'source':before})
    if (before.bytes,before.sha256)!=(after.bytes,after.sha256):raise OSError('source clip copy differs')
    return after


def generate(config,run,store,logger,context,records,clips):
    from .pipeline_import import load_pipeline_import
    retry_units=set()
    if 'pipeline_import' in store.snapshot()['workflows']:
        receipt=load_pipeline_import(run)
        for row in receipt['stages']:
            if row['id']=='source_clips':retry_units.update(row['imported_record'].get('retry_failed_units',()))
    paths=RuntimePaths.from_config(config);manager=ServiceManager(paths,store,logger);handle=None
    for name in ('input','output','temp','user'):_local(run,run/'comfy'/name).mkdir(parents=True,exist_ok=True)
    try:
        handle=manager.ensure(build_service_specs(config,run,**({'model_stage':'wan'} if 'model_loader_binding' in context['identities'] else {}))['comfyui'])
        if not handle.owned:raise ServiceConflictError('external 8188; refuse takeover')
        for plan in context['plans']:
            uid=plan.shot_id;p=thaw(plan.parameters);required=plan.budget['required_native_frames']
            store.record_unit('shot',uid,'running')
            original=Path(plan.start_image_identity['path']);fresh(thaw(plan.start_image_identity),run=run,expected=original)
            copied=copy(run,original,run/'comfy/input'/run.name/'source_clips'/uid/'start.png')
            image_logs=logger.save_json(f'source-clips/input-{uid}.json',dict(source=thaw(plan.start_image_identity),target=thaw(copied)))
            base_names=evidence(run,records,[original,Path(copied.path),image_logs]);attempts=[];requested=p['length']
            for ordinal in ((1,) if uid in retry_units else (1,2)):
                local=f'attempt_{ordinal:04d}';unit_id=uid+':'+local
                store.record_unit('shot_attempt',unit_id,'running')
                http=DeadlineHttp(config.services['comfyui'],config.timeouts['comfy_request'],logger)
                http.set_deadline(config.timeouts['wan']);client=ComfyClient(http,store,logger)
                directory=run/'logs/http';before=set(directory.glob('*')) if directory.exists() else set()
                client.validate_template(context['template'])
                actual_graph=graph(context['template'],run,plan,requested,local)
                _again(context['identities']);fresh(thaw(copied),run=run)
                if 'model_loader_binding' in context['identities']:
                    from ._pipeline_model_paths import prepare_or_consume_model_binding
                    prepare_or_consume_model_binding(config,run,'wan')
                if not same(context['template'].graph,read_json(config.workflows['wan'])) or not same(context['template'].mapping,read_json(config.workflows['wan_mapping'])):
                    raise ValueError('loaded graph changed before POST')
                submission=client.submit_once(actual_graph,stage='source_clips',kind='shot_attempt',unit_id=unit_id)
                history=client.wait_for(submission,deadline_seconds=http.remaining());http.remaining()
                if len(history.outputs)!=1:raise ValueError('expected exactly one mapped MP4')
                source=_local(run,output_path(run,history.outputs[0]))
                expected=run/'comfy/output'/run.name/'source_clips'/uid
                if source.parent!=expected or not source.name.startswith(local+'_') or source.suffix.lower()!='.mp4':
                    raise ValueError('Wan output path/prefix is not this run and attempt')
                saved=store.snapshot()['units']['shot_attempt'][unit_id]['submission']
                if source.stat().st_mtime_ns<int(datetime.fromisoformat(saved['submitted_at']).timestamp()*1_000_000_000):
                    raise ValueError('output predates this submission')
                kwargs=dict(width=p['width'],height=p['height'],config=config,paths=paths,logger=logger,unit_id=unit_id)
                info,logs=inspect_video(source,**kwargs)
                actual=info['frames'];names=evidence(run,records,[Path(saved['request_path']),history.evidence_path,*sorted(set(directory.glob('*'))-before),*logs])
                item=dict(attempt_id=local,ordinal=ordinal,unit_id=unit_id,requested_frames=requested,status='short' if actual<required else 'selected',
                    submission=dict(attempt_id=submission.attempt_id,prompt_id=submission.prompt_id,intent_identity=thaw(hash_file(Path(saved['request_path'])))),
                    output_identity=info['identity'],actual_frames=actual,evidence_identities=names)
                attempts.append(item)
                if actual<required:
                    error=dict(kind='known_short',message=f'decoded {actual} < required {required}',traceback_path=None,evidence_paths=[str(path) for path in logs])
                    store.record_unit('shot_attempt',unit_id,'failed',artifacts=[_artifact(hash_file(source))],error=error)
                    if ordinal==2 or uid in retry_units:raise ValueError('authorized independent attempt still short; no further attempt')
                    requested=supplement_frames(requested_frames=requested,required_native_frames=required,actual_frames=actual)
                    continue
                if actual!=requested:raise ValueError('decoded sufficient output must equal requested frame count')
                generated=copy(run,source,run/'shots'/uid/'generated.mp4')
                target,target_logs=trim_video(Path(generated.path),run/'shots'/uid/'source.mp4',frames=required,**kwargs)
                names=evidence(run,records,target_logs)
                p['length']=requested
                clip=dict(shot_id=uid,primary_unit_id=plan.primary_unit_id,budget=thaw(plan.budget),start_image_identity=thaw(plan.start_image_identity),
                    input_copy_identity=thaw(copied),selected_attempt_id=local,attempts=attempts,generated_identity=thaw(generated),source_identity=target['identity'],
                    width=p['width'],height=p['height'],native_fps=16,generated_frames=actual,source_frames=required,parameters=p,
                    evidence_identities=list(dict.fromkeys(base_names+[n for a in attempts for n in a['evidence_identities']]+names)))
                checkpoint=logger.save_json(f'source-clips/clip-{uid}.json',clip)
                clips.append(clip)
                store.record_unit('shot_attempt',unit_id,'completed',artifacts=[_artifact(hash_file(checkpoint)),_artifact(generated),_artifact(hash_file(Path(target['identity']['path'])))])
                break
    finally:
        stop_owned_preserving_exception(manager,handle,logger,'source_clips',require_stopped=True)
    _again(context['identities'])
