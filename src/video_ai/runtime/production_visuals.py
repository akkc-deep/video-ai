"""Serial owned SDXL/Wan production with immutable technical checkpoints."""
from contextlib import contextmanager
from pathlib import Path
import os
import shutil
import sys
from uuid import uuid4

from ..adapters.common import AdapterError,HttpClient
from ..adapters.comfyui import ComfyClient
from ..config import read_json
from ..media.images import validate_start_png
from ..media.video import inspect_production_video,trim_production_video
from ..planning.start_images import image_parameters
from ..planning.production_visual_plan import plan_production_source_clips,production_frame_mapping
from .manifest import thaw
from .execution_limits import production_execution
from .production_inputs import check_stage_space,_verify_identity
from .production_state import ArtifactStamp,ProductionRefused,run_path,sync_file
from .production_support import (read_report,recover_checkpoint,commit_checkpoint,stamps,sync_manifest_stage,
                                 mark_request_error)
from .production_comfy import reconcile,request,evidence,submission_payload,same
from .workflows import WorkflowTemplate
from .service_specs import build_service_specs
from .services import ServiceManager,ServiceConflictError,port_listening
from .owned_cleanup import stop_owned_preserving_exception
from .production_visual_templates import validate_fixed_visual_template,validate_production_model_paths
from .production_visual_storyboard import model_visual_run
from .production_visual_review import require_image_review


def _copy(run,original,target):
    before=ArtifactStamp.read(original);target=run_path(run,target);target.parent.mkdir(parents=True,exist_ok=True)
    with Path(original).open('rb') as src,target.open('xb') as dst:
        shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
    before.verify();after=ArtifactStamp.read(target)
    if before.bytes!=after.bytes:raise OSError('incomplete production copy')
    return after


def _frozen(frozen,role):
    records=frozen.options['execution_policy']['input_identities']
    for key in (role,role+'_mapping'):_verify_identity(records['workflow/'+key])
    for stamp in frozen.options['model_stamps'].values():ArtifactStamp.from_dict(stamp).verify()


class _Stage:
    def __init__(self,frozen,stage,*,state,manifest,paths,logger):
        self.frozen,self.stage,self.state,self.manifest,self.paths,self.logger=frozen,stage,state,manifest,paths,logger
        self.manager=ServiceManager(paths,manifest,logger);self.handle=None;self.validated=False
        self.complete=state.snapshot()['stages'][stage]['status']=='completed'
        self.report=read_report(state,stage)
        if self.complete and self.report is None:raise ProductionRefused('completed visual cursor has no report')
        if not self.complete:state.start_stage(stage)
        role='sdxl' if stage=='start_images' else 'wan';self.role=role
        validate_production_model_paths(frozen.config)
        _frozen(frozen,role)
        self.template=WorkflowTemplate.load(Path(frozen.options['workflow_snapshots'][role]['path']),
            Path(frozen.options['workflow_snapshots'][role+'_mapping']['path']),frozen.config.models)
        validate_fixed_visual_template(self.template,role)
        self.client=ComfyClient(HttpClient(frozen.config.services['comfyui'],frozen.config.timeouts['comfy_request'],logger),manifest,logger)
        self.client._production_deadline=frozen.config.timeouts['wan'] if role=='wan' else frozen.config.timeouts['comfy_request']
        for name in ('input','output','temp','user'):run_path(state.run_dir,state.run_dir/'comfy'/name).mkdir(parents=True,exist_ok=True)

    def ensure(self):
        if self.handle is not None:return
        url=self.frozen.config.services['comfyui']
        try:
            if port_listening(url,3):raise ProductionRefused(f'external Comfy service listening at {url}')
            self.handle=self.manager.ensure(build_service_specs(self.frozen.config,self.state.run_dir,production=True,frozen=self.frozen,store=self.manifest)['comfyui'])
        except ServiceConflictError as exc:raise ProductionRefused(str(exc)) from exc
        if not self.handle.owned:raise ProductionRefused(f'external Comfy service at {url}')

    def model(self,uid,graph,prefix,*,checkpoint=False):
        kind='image' if self.stage=='start_images' else 'shot_attempt'
        mid=uid if kind=='image' else uid+':attempt_0001';extension='.png' if kind=='image' else '.mp4'
        kwargs=dict(stage=self.stage,kind=kind,unit_id=mid,state=self.state,production_uid=uid,logger=self.logger,prefix=prefix,extension=extension)
        try:
            found=reconcile(self.client,self.template,graph,allow_get=False,**kwargs)
            if found=='needs_get':
                if checkpoint:raise ProductionRefused('completed checkpoint has no durable matching original history')
                self.ensure();found=reconcile(self.client,self.template,graph,allow_get=True,**kwargs)
            if found is None:
                if checkpoint or self.complete:raise ProductionRefused('completed visual lacks original Comfy submission')
                local=self.state.snapshot()['units'].get(self.stage,{}).get(uid)
                if local and local['request'] is not None:raise ProductionRefused('production intent has no corresponding manifest truth')
                self.ensure();_frozen(self.frozen,self.role)
                if not self.validated:self.client.validate_template(self.template);self.validated=True
                print(f'[make-video] {self.stage} {uid}: ComfyUI',file=sys.stderr,flush=True)
                def on_intent(path,sub):
                    self.state.record_unit(self.stage,uid,status='running',request=request(sub,[]))
                sub=self.client.submit_once(graph,stage=self.stage,kind=kind,unit_id=mid,on_intent=on_intent)
                saved=self.manifest.snapshot()['units'][kind][mid]['submission']
                self.state.record_unit(self.stage,uid,status='running',request=request(saved,evidence(self.logger,mid)))
                self.client.wait_for(sub,deadline_seconds=self.client._production_deadline)
                found=reconcile(self.client,self.template,graph,allow_get=False,**kwargs)
            if not isinstance(found,tuple):raise ProductionRefused('original history is not recoverable')
            target,saved=found
            payload=submission_payload(saved,self.logger,mid)
            return target,saved,payload,request(saved,payload['response_paths']),mid
        except AdapterError as exc:mark_request_error(self.state,self.stage,uid,exc)

    def finish(self,payload,inputs):
        if self.report and (not same(self.report['payload'],payload) or self.report['input_records']!=inputs):raise ProductionRefused('immutable visual report differs from checkpoints')
        if not self.report:self.state.write_report(self.stage,payload,input_records=inputs)
        if not self.complete:self.state.complete_stage(self.stage)
        name='images' if self.stage=='start_images' else 'source-clips'
        sync_manifest_stage(self.manifest,self.stage,self.state.run_dir/f'production/{name}.json')
        return payload


@contextmanager
def _stage(frozen,stage,**kwargs):
    task=_Stage(frozen,stage,**kwargs)
    try:yield task
    finally:stop_owned_preserving_exception(task.manager,task.handle,task.logger,stage)


def _failed(task,uid,req,exc):
    paths=[str(p) for p in getattr(exc,'evidence_paths',())]
    task.state.record_unit(task.stage,uid,status='failed',request=dict(req,state='failed'),
                          error=dict(kind=type(exc).__name__,message=str(exc),evidence_paths=paths))
    raise RuntimeError(f'{task.stage}/{uid}: invalid model media: {exc}') from exc


def _check_submission(cp,submission,req):
    if cp['request']!=dict(req,state='completed'):raise ProductionRefused('checkpoint request differs from original submission')
    if not same(submission,cp['payload'].get('submission',cp['payload'].get('clip',{}).get('submission'))):
        raise ProductionRefused('checkpoint submission differs from original Comfy evidence')


@production_execution
def produce_start_images(frozen,storyboard,*,state,manifest,paths,logger):
    check_stage_space(frozen.config,frames=sum(s['end_frame']-s['start_frame'] for s in storyboard['shots']))
    inputs=stamps({'options':state.run_dir/'production/options.json','storyboard':state.run_dir/'production/storyboard.json'})
    with _stage(frozen,'start_images',state=state,manifest=manifest,paths=paths,logger=logger) as task:
        rows=[];profile=frozen.config.media.profile
        for shot in storyboard['shots']:
            uid=shot['shot_id'];cp=recover_checkpoint(state,'start_images',uid)
            p=image_parameters(shot,storyboard['global_visual'],profile.width,profile.height,model_visual=model_visual_run(logger))
            prefix=f'{state.run_dir.name}/start_images/{uid}/attempt_0001'
            graph=task.template.instantiate(dict(positive_prompt=p['positive'],negative_prompt=p['negative'],seed=p['seed'],width=p['width'],height=p['height']),output_prefix=prefix)
            model_output,saved,sub,req,mid=task.model(uid,graph,prefix,checkpoint=cp is not None)
            if cp:
                _check_submission(cp,sub,req);row=cp['payload']
                if (row['shot_id']!=uid or row['primary_unit_id']!=shot['primary_unit_id'] or not same(row['parameters'],p)
                        or cp['outputs'].get('image')!=row['image'] or cp['outputs'].get('model_output')!=ArtifactStamp.read(model_output).to_dict()):
                    raise ProductionRefused('image checkpoint differs from fixed parameters/output')
            else:
                if task.complete:raise ProductionRefused('completed image stage missing checkpoint')
                try:validate_start_png(model_output,width=p['width'],height=p['height'],config=frozen.config,paths=paths,logger=logger,unit_id=uid,production=True)
                except (ValueError,RuntimeError) as exc:_failed(task,uid,req,exc)
                attempt=run_path(state.run_dir,state.run_dir/f'production/visuals/{uid}/{uuid4().hex}');image=_copy(state.run_dir,model_output,attempt/'start.png')
                row=dict(shot_id=uid,primary_unit_id=shot['primary_unit_id'],parameters=p,image=image.to_dict(),submission=sub)
                commit_checkpoint(state,'start_images',uid,request=req,outputs=stamps(dict(image=image.path,model_output=model_output,**{f'evidence_{i}':p for i,p in enumerate(sub['response_paths'])})),payload=row)
            rows.append(row)
        return task.finish(dict(images=rows),inputs)


@production_execution
def produce_source_clips(frozen,storyboard,timeline,images,*,state,manifest,paths,logger):
    # This check occurs before starting the Wan stage, copying inputs or POSTing.
    # Legacy completed artifacts may be replayed; pending work always needs review.
    accepted_review=state.run_dir/'production/visual-review-accepted.json'
    if state.snapshot()['stages']['source_clips']['status']!='completed' or accepted_review.exists():
        require_image_review(state.run_dir,storyboard,images)
    plans=plan_production_source_clips(storyboard,timeline,images,model_visual=model_visual_run(logger));check_stage_space(frozen.config,frames=timeline.total_frames)
    inputs=stamps({'options':state.run_dir/'production/options.json','storyboard':state.run_dir/'production/storyboard.json',
                  'images':state.run_dir/'production/images.json','timeline':state.run_dir/'production/timeline.json',
                  'slots':state.run_dir/'logs/production/checkpoints/timeline/automatic-slots.json'})
    review_paths=dict(visual_review=state.run_dir/'production/visual-review.json',accepted_visual_review=accepted_review) if accepted_review.exists() else {}
    inputs.update(stamps(review_paths))
    with _stage(frozen,'source_clips',state=state,manifest=manifest,paths=paths,logger=logger) as task:
        clips=[];mappings=[]
        for plan in plans:
            uid=plan.shot_id;p=thaw(plan.parameters);cp=recover_checkpoint(state,'source_clips',uid)
            original=plan.start_image_stamp;original.verify()
            input_path=run_path(state.run_dir,state.run_dir/f'comfy/input/{state.run_dir.name}/source_clips/{uid}/start.png')
            input_record=logger.path(f'source-clips/{uid}.input-copy.json')
            if input_record.exists():
                saved_input=read_json(input_record)
                if saved_input.get('source')!=original.to_dict():raise ProductionRefused('original Wan input image changed')
                copied=ArtifactStamp.from_dict(saved_input['target']);copied.verify()
                if copied.path!=str(input_path):raise ProductionRefused('Wan input copy path changed')
            elif cp or task.complete:raise ProductionRefused('completed source clip missing original input copy')
            else:
                if input_path.exists():
                    # Only a pre-intent technical copy may be preserved and redone.
                    if manifest.snapshot()['units'].get('shot_attempt',{}).get(uid+':attempt_0001',{}).get('submission') is not None:raise ProductionRefused('submitted Wan has no durable input copy association')
                    archived=input_path.with_name('unregistered-'+uuid4().hex+'.png');input_path.rename(archived)
                copied=_copy(state.run_dir,original.path,input_path)
                logger.save_json(f'source-clips/{uid}.input-copy.json',dict(source=original.to_dict(),target=copied.to_dict()))
            prefix=f'{state.run_dir.name}/source_clips/{uid}/attempt_0001'
            graph=task.template.instantiate(dict(positive_prompt=p['positive'],start_image=f'{state.run_dir.name}/source_clips/{uid}/start.png',
                width=p['width'],height=p['height'],length=p['length'],fps=p['fps'],seed_high=p['seed_high'],seed_low=p['seed_low']),output_prefix=prefix)
            original.verify();copied.verify()
            model_output,saved,sub,req,mid=task.model(uid,graph,prefix,checkpoint=cp is not None)
            if cp:
                _check_submission(cp,sub,req);clip=cp['payload']['clip'];mapping=cp['payload']['frame_mapping']
                if (clip['shot_id']!=uid or clip['primary_unit_id']!=plan.primary_unit_id or not same(clip['parameters'],p) or not same(clip['budget'],thaw(plan.budget))
                    or clip['start_image']!=original.to_dict() or cp['payload']['input_copy']!=copied.to_dict()
                    or cp['outputs'].get('generated')!=clip['generated'] or cp['outputs'].get('source')!=clip['source']
                    or cp['outputs'].get('model_output')!=ArtifactStamp.read(model_output).to_dict()
                    or not same(mapping,production_frame_mapping(plan,generated_frames=clip['generated_frames']))):raise ProductionRefused('source checkpoint differs from original plan/output/mapping')
            else:
                if task.complete:raise ProductionRefused('completed source stage lacks checkpoint')
                attempt=run_path(state.run_dir,state.run_dir/f'production/visuals/{uid}/{uuid4().hex}');generated=_copy(state.run_dir,model_output,attempt/'generated.mp4')
                kwargs=dict(width=p['width'],height=p['height'],config=frozen.config,paths=paths,logger=logger,unit_id=mid)
                try:
                    info,media=inspect_production_video(Path(generated.path),**kwargs)
                    if info['frames']<plan.budget['required_native_frames']:raise ValueError('Wan source has insufficient frames; no second inference')
                    source,more=trim_production_video(Path(generated.path),attempt/'source.mp4',source_info=info,frames=plan.budget['required_native_frames'],**kwargs)
                except (ValueError,RuntimeError) as exc:_failed(task,uid,req,exc)
                clip=dict(shot_id=uid,primary_unit_id=plan.primary_unit_id,budget=thaw(plan.budget),parameters=p,start_image=original.to_dict(),
                          generated=generated.to_dict(),source=source['stamp'],native_fps=16,generated_frames=info['frames'],source_frames=source['frames'],submission=sub)
                mapping=production_frame_mapping(plan,generated_frames=info['frames'])
                media=[str(p) for p in (*media,*more)]
                outputs=stamps(dict(generated=generated.path,source=source['stamp']['path'],input_copy=copied.path,model_output=model_output,
                                    input_evidence=input_record,**review_paths,**{f'evidence_{i}':p for i,p in enumerate([*sub['response_paths'],*media])}))
                commit_checkpoint(state,'source_clips',uid,request=req,outputs=outputs,
                                  payload=dict(clip=clip,frame_mapping=mapping,input_copy=copied.to_dict(),media_evidence_paths=media))
            clips.append(clip);mappings.append(mapping)
        return task.finish(dict(clips=clips,frame_mappings=mappings),inputs)
