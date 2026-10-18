"""Real single-frame production upscale with durable, stamp-based recovery."""
from pathlib import Path
import sys
from uuid import uuid4

from ..adapters.common import AdapterError,HttpClient
from ..adapters.comfyui import ComfyClient
from ..config import read_json
from ..media.images import validate_start_png
from ..planning.production_visual_plan import plan_production_upscale,production_upscale_frame_mapping
from .environment import build_child_env
from .manifest import thaw
from .owned_cleanup import stop_owned_preserving_exception
from .processes import run_logged
from .production_comfy import HttpEvidenceIndex,reconcile,request,submission_payload,same
from .production_inputs import check_stage_space
from .production_state import ArtifactStamp,ProductionRefused,run_path,sync_file
from .production_support import (checkpoint_path,read_report,recover_checkpoint,commit_checkpoint,stamps,
                                 sync_manifest_stage,mark_request_error)
from .production_visuals import _copy,_frozen,_failed,_check_submission
from .production_visual_templates import validate_fixed_visual_template,validate_production_model_paths
from .service_specs import build_service_specs
from .services import ServiceManager,ServiceConflictError,port_listening
from .workflows import WorkflowTemplate


class _Upscale:
    stage='upscale'

    def __init__(self,frozen,*,state,manifest,paths,logger):
        self.frozen,self.state,self.manifest,self.paths,self.logger=frozen,state,manifest,paths,logger
        self.manager=ServiceManager(paths,manifest,logger);self.handle=None;self.validated=False
        self.complete=state.snapshot()['stages']['upscale']['status']=='completed'
        self.report=read_report(state,'upscale')
        if self.complete and self.report is None:raise ProductionRefused('completed upscale has no report')
        if not self.complete:state.start_stage('upscale')
        validate_production_model_paths(frozen.config);_frozen(frozen,'upscale')
        if frozen.config.models['upscale'].name!='RealESRGAN_x4plus.pth':raise ProductionRefused('fixed RealESRGAN model required')
        expected=frozen.options['model_stamps']['upscale']
        if ArtifactStamp.read(frozen.config.models['upscale']).to_dict()!=expected:raise ProductionRefused('actual upscale model differs from frozen stamp')
        self.template=WorkflowTemplate.load(Path(frozen.options['workflow_snapshots']['upscale']['path']),
            Path(frozen.options['workflow_snapshots']['upscale_mapping']['path']),frozen.config.models)
        validate_fixed_visual_template(self.template,'upscale')
        self.http=HttpEvidenceIndex(logger)
        self.client=ComfyClient(HttpClient(frozen.config.services['comfyui'],min(frozen.config.timeouts['comfy_request'],frozen.config.timeouts['upscale_frame']),self.http),manifest,logger)
        self.client._production_deadline=frozen.config.timeouts['upscale_frame']
        for name in ('input','output','temp','user'):run_path(state.run_dir,state.run_dir/'comfy'/name).mkdir(parents=True,exist_ok=True)

    def ensure(self):
        if self.handle is not None:return
        url=self.frozen.config.services['comfyui']
        try:
            if port_listening(url,3):raise ProductionRefused(f'external Comfy service listening at {url}')
            handle=self.manager.ensure(build_service_specs(self.frozen.config,self.state.run_dir,production=True,frozen=self.frozen,store=self.manifest)['comfyui'])
        except ServiceConflictError as exc:raise ProductionRefused(str(exc)) from exc
        if not handle.owned:raise ProductionRefused(f'external Comfy service at {url}')
        self.handle=handle

    def model(self,uid,graph,prefix,*,checkpoint,input_stamps):
        evidence=self.http.paths(uid)
        kwargs=dict(stage='upscale',kind='frame',unit_id=uid,state=self.state,production_uid=uid,logger=self.logger,
                    prefix=prefix,extension='.png',evidence_paths=evidence)
        try:
            found=reconcile(self.client,self.template,graph,allow_get=False,**kwargs)
            if found=='needs_get':
                if checkpoint:raise ProductionRefused('completed frame lacks durable matching original history')
                self.ensure();found=reconcile(self.client,self.template,graph,allow_get=True,**kwargs)
            if found is None:
                if checkpoint or self.complete:raise ProductionRefused('completed frame has no original submission')
                local=self.state.snapshot()['units'].get('upscale',{}).get(uid)
                if local and local['request'] is not None:raise ProductionRefused('production intent lacks manifest submission')
                self.ensure();validate_fixed_visual_template(self.template,'upscale')
                if not self.validated:self.client.validate_template(self.template);self.validated=True
                _frozen(self.frozen,'upscale')
                for stamp in input_stamps:stamp.verify()
                print(f'[make-video] upscale {uid}: ComfyUI',file=sys.stderr,flush=True)
                def on_intent(path,sub):
                    self.state.record_unit('upscale',uid,status='running',request=request(sub,[]))
                    _frozen(self.frozen,'upscale')
                    for stamp in input_stamps:stamp.verify()
                sub=self.client.submit_once(graph,stage='upscale',kind='frame',unit_id=uid,on_intent=on_intent)
                saved=self.manifest.snapshot()['units']['frame'][uid]['submission']
                self.state.record_unit('upscale',uid,status='running',request=request(saved,list(evidence)))
                self.client.wait_for(sub,deadline_seconds=self.client._production_deadline)
                found=reconcile(self.client,self.template,graph,allow_get=False,**kwargs)
            if not isinstance(found,tuple):raise ProductionRefused('original frame history is not recoverable')
            _frozen(self.frozen,'upscale')
            for stamp in input_stamps:stamp.verify()
            target,saved=found;sub=submission_payload(saved,self.logger,uid,evidence_paths=evidence)
            return target,sub,request(saved,sub['response_paths'])
        except AdapterError as exc:mark_request_error(self.state,'upscale',uid,exc)


def _extract(task,plan):
    state=task.state;uid=plan.shot_id+'_extract';source=plan.source_stamp;source.verify()
    profile=task.frozen.config.media.profile;width,height=profile.width,profile.height
    cp=recover_checkpoint(state,'upscale',uid)
    if cp:
        payload=cp['payload']
        if (payload['shot_id']!=plan.shot_id or payload['source']!=source.to_dict() or payload['source_frames']!=plan.source_frames
            or payload['width']!=width or payload['height']!=height):raise ProductionRefused('extraction checkpoint differs from source/profile')
        for row in payload['frames']:ArtifactStamp.from_dict(row['input']).verify()
        return payload
    if task.complete:raise ProductionRefused('completed upscale lacks extraction checkpoint')
    state.record_unit('upscale',uid,status='running')
    directory=run_path(state.run_dir,state.run_dir/f'production/upscale/{plan.shot_id}/{uuid4().hex}/input-frames')
    directory.mkdir(parents=True)
    command=run_logged(tuple(str(v) for v in (task.frozen.config.tools['ffmpeg'],'-nostdin','-n','-v','error','-xerror','-i',source.path,
        '-map','0:v:0','-vf','format=rgb24','-fps_mode','passthrough','-start_number','1',directory/'frame_%06d.png')),
        cwd=state.run_dir,env=build_child_env(task.paths),timeout=300,logger=task.logger,stage='upscale',unit_id=uid)
    if command.returncode!=0 or command.timed_out:raise RuntimeError(f'{uid}: extraction failed: {command.stderr_path}')
    expected=[directory/f'frame_{i:06d}.png' for i in range(1,plan.source_frames+1)]
    if {p.name for p in directory.iterdir()}!={p.name for p in expected}:raise ValueError('exact native PNG extraction sequence required')
    rows=[];media=[command.stdout_path,command.stderr_path]
    for i,path in enumerate(expected,1):
        if path.is_symlink() or not path.is_file():raise ProductionRefused('regular owned extracted PNG required')
        info,more=validate_start_png(path,width=width,height=height,config=task.frozen.config,paths=task.paths,logger=task.logger,
            unit_id=uid+f'_frame_{i:06d}',stage='upscale',production=True,timeout=300)
        stamp=ArtifactStamp.from_dict(info['stamp']);stamp.verify();sync_file(path);stamp.verify()
        rows.append(dict(frame_index=i,source_frame_index=i-1,input=stamp.to_dict()));media.extend(more)
    source.verify()
    payload=dict(shot_id=plan.shot_id,source=source.to_dict(),source_frames=plan.source_frames,width=width,height=height,frames=rows,command=thaw(command))
    outputs=stamps({f'evidence_{i}':p for i,p in enumerate(media)})
    for i,row in enumerate(rows):
        stamp=ArtifactStamp.from_dict(row['input']);stamp.verify();outputs[f'input_{i}']=stamp.to_dict()
    source.verify()
    commit_checkpoint(state,'upscale',uid,outputs=outputs,payload=payload)
    return payload


def _input_copy(task,uid,input_stamp,*,completed):
    state=task.state;sid,index=uid.split(':');target=run_path(state.run_dir,state.run_dir/f'comfy/input/{state.run_dir.name}/upscale/{sid}/{index}.png')
    record=task.logger.path(f'upscale/{sid}_{index}.input-copy.json')
    original=ArtifactStamp.from_dict(input_stamp);original.verify()
    if record.is_file():
        row=read_json(record)
        if set(row)!={'source','target'} or row['source']!=input_stamp:raise ProductionRefused('original upscale input copy differs')
        copy=ArtifactStamp.from_dict(row['target']);copy.verify()
        if copy.path!=str(target):raise ProductionRefused('upscale input copy path differs')
    elif completed or task.complete:raise ProductionRefused('completed frame lacks input copy evidence')
    else:
        if target.exists():
            saved=task.manifest.snapshot()['units'].get('frame',{}).get(uid,{}).get('submission')
            if saved is not None:raise ProductionRefused('submitted frame lacks original input copy evidence')
            target.rename(target.with_name('unregistered-'+uuid4().hex+'.png'))
        copy=_copy(state.run_dir,original.path,target)
        task.logger.save_json(f'upscale/{sid}_{index}.input-copy.json',dict(source=input_stamp,target=copy.to_dict()))
    return copy,record


def produce_upscaled_clips(frozen,source_clips,*,state,manifest,paths,logger):
    plans=plan_production_upscale(source_clips);check_stage_space(frozen.config,frames=sum(p.source_frames for p in plans))
    inputs=stamps({'options':state.run_dir/'production/options.json','source_clips':state.run_dir/'production/source-clips.json'})
    task=_Upscale(frozen,state=state,manifest=manifest,paths=paths,logger=logger)
    try:
        clips=[];mappings=[]
        total=sum(p.source_frames for p in plans);completed=0
        for plan,source_mapping in zip(plans,source_clips['frame_mappings']):
            extract=_extract(task,plan);inputs[plan.shot_id+'_extract']=ArtifactStamp.read(checkpoint_path(state,'upscale',plan.shot_id+'_extract')).to_dict()
            rows=[];p=thaw(plan.parameters)
            for frame in extract['frames']:
                completed+=1;task.logger.progress('upscale',plan.shot_id,frame=completed,total=total)
                i=frame['frame_index'];uid=f'{plan.shot_id}:frame_{i:06d}';cp=recover_checkpoint(state,'upscale',uid)
                copied,input_record=_input_copy(task,uid,frame['input'],completed=cp is not None)
                prefix=f'{state.run_dir.name}/upscale/{plan.shot_id}/frame_{i:06d}'
                graph=task.template.instantiate(dict(image=f'{prefix}.png'),output_prefix=prefix)
                plan.source_stamp.verify();ArtifactStamp.from_dict(frame['input']).verify();copied.verify()
                model_output,sub,req=task.model(uid,graph,prefix,checkpoint=cp is not None,
                    input_stamps=(plan.source_stamp,ArtifactStamp.from_dict(frame['input']),copied))
                if cp:
                    _check_submission(cp,sub,req);payload=cp['payload']
                    if (payload['shot_id']!=plan.shot_id or payload['frame_index']!=i or payload['source_frame_index']!=i-1
                        or payload['source']!=plan.source_stamp.to_dict() or not same(payload['parameters'],p)
                        or payload['input']!=frame['input'] or payload['input_copy']!=copied.to_dict()
                        or payload['model_output']!=ArtifactStamp.read(model_output).to_dict()
                        or any(cp['outputs'].get(k)!=payload[k] for k in ('input','input_copy','output','model_output'))):
                        raise ProductionRefused('frame checkpoint differs from original source/input/model')
                else:
                    try:
                        info,media=validate_start_png(model_output,width=1920,height=1080,config=frozen.config,paths=paths,logger=logger,
                            unit_id=uid,stage='upscale',production=True,timeout=frozen.config.timeouts['upscale_frame'])
                    except (ValueError,RuntimeError) as exc:_failed(task,uid,req,exc)
                    model_stamp=ArtifactStamp.from_dict(info['stamp']);model_stamp.verify()
                    directory=run_path(state.run_dir,state.run_dir/f'production/upscale/{plan.shot_id}/{uuid4().hex}/output-frames')
                    output=_copy(state.run_dir,model_output,directory/f'frame_{i:06d}.png')
                    model_stamp.verify()
                    media=[str(v) for v in media]
                    payload=dict(shot_id=plan.shot_id,frame_index=i,source_frame_index=i-1,source=plan.source_stamp.to_dict(),
                        parameters=p,input=frame['input'],input_copy=copied.to_dict(),output=output.to_dict(),model_output=model_stamp.to_dict(),submission=sub,media_evidence_paths=media)
                    outputs=stamps(dict(input_evidence=input_record,
                        **{f'evidence_{j}':v for j,v in enumerate([*sub['response_paths'],*media])}))
                    outputs.update({k:payload[k] for k in ('input','input_copy','output','model_output')})
                    _frozen(frozen,'upscale')
                    for stamp in (plan.source_stamp,ArtifactStamp.from_dict(frame['input']),copied,model_stamp,output):stamp.verify()
                    commit_checkpoint(state,'upscale',uid,request=req,outputs=outputs,payload=payload)
                rows.append({k:payload[k] for k in ('frame_index','source_frame_index','input','input_copy','output','submission')}|
                    dict(checkpoint_path=str(checkpoint_path(state,'upscale',uid))))
            clips.append(dict(shot_id=plan.shot_id,source=plan.source_stamp.to_dict(),upscaled_frames=plan.source_frames,frames=rows))
            mappings.append(production_upscale_frame_mapping(source_mapping,upscaled_frames=plan.source_frames))
        payload=dict(clips=clips,frame_mappings=mappings)
        if task.report and (not same(task.report['payload'],payload) or task.report['input_records']!=inputs):raise ProductionRefused('immutable upscale report differs')
        if not task.report:state.write_report('upscale',payload,input_records=inputs)
        if not task.complete:state.complete_stage('upscale')
        sync_manifest_stage(manifest,'upscale',state.run_dir/'production/upscaled-clips.json')
        return payload
    finally:stop_owned_preserving_exception(task.manager,task.handle,logger,'upscale')
