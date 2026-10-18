"""Bounded real-model previews in a NEW run; never resume a source run.

Run via the orchestration Python after scripts/bootstrap.ps1 initialization.
Planning, image generation and video generation are separate invocations;
videos require actual observations of the exact images. Failed observations
remain failed and only admit this bounded experiment, never production.
All writes are exclusive.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil

from video_ai.config import load_config,read_json
from video_ai.adapters.common import HttpClient
from video_ai.adapters.ollama import OllamaPlanner
from video_ai.adapters.comfyui import ComfyClient
from video_ai.planning.storyboard import StoryboardSlot,Binding,primary_model_slots,validate_model_content,GROUNDED_POLICY
from video_ai.planning.model_visual_prompts import validate_english_content,render_model_prompt
from video_ai.planning.start_images import image_parameters
from video_ai.runtime.production_visual_storyboard import _visual_request
from video_ai.runtime.production_inputs import freeze_inputs,load_frozen_inputs
from video_ai.runtime.production_state import write_exclusive,RunLock,ProductionRefused
from video_ai.runtime.production_visual_review import require_preview_observation
from video_ai.runtime.production_visual_templates import validate_fixed_visual_template
from video_ai.runtime.manifest import create_manifest,ManifestStore,hash_file,thaw
from video_ai.runtime.paths import RuntimePaths,create_run,PathPolicy
from video_ai.runtime.logging import RunLogger
from video_ai.runtime.services import ServiceManager,port_listening
from video_ai.runtime.service_specs import build_service_specs
from video_ai.runtime.owned_cleanup import stop_owned_preserving_exception
from video_ai.runtime.workflows import WorkflowTemplate
from video_ai.runtime.production_comfy import output_from_history
from video_ai.media.images import validate_start_png
from video_ai.media.video import inspect_production_video


def owned_service(frozen,run,manifest,logger,name):
    url=frozen.config.services[name]
    if port_listening(url,3):raise ProductionRefused('external service listening at '+url)
    manager=ServiceManager(RuntimePaths.from_config(frozen.config),manifest,logger)
    handle=manager.ensure(build_service_specs(frozen.config,run,production=True,frozen=frozen,store=manifest)[name])
    if not handle.owned:raise ProductionRefused('preview requires its own service')
    return manager,handle


def plan(args):
    source=Path(args.source_run)
    original=read_json(source/'production/storyboard.json')['payload']
    ids=args.shot_ids.split(',')
    if not 3<=len(ids)<=5 or len(set(ids))!=len(ids):raise ValueError('select 3 to 5 distinct representative shots')
    selected=[next(s for s in original['shots'] if s['shot_id']==sid) for sid in ids]
    config=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    run=create_run(RuntimePaths.from_config(config));print('PREVIEW_RUN='+str(run),flush=True)
    frozen=freeze_inputs(config,run,script=source/'production/script.txt')
    config=frozen.config
    manifest=create_manifest(run,config,inputs=dict(script=thaw(hash_file(run/'production/script.txt'))),models={},workflows={},verify_integrity=False)
    logger=RunLogger(run,production=True)
    (run/'samples').mkdir()
    source_records={name:thaw(hash_file(source/'production'/name)) for name in ('script.txt','storyboard.json','units.json','production-state.json')}
    write_exclusive(run/'samples/source.json',dict(source_run=str(source),source_records=source_records,shot_ids=ids,
        policy='Preview only, no batch, no delivery, no source-run writes'))
    slots=tuple(StoryboardSlot(s['shot_id'],s['start_frame'],s['end_frame'],s['primary_unit_id'],
        tuple(Binding(**b) for b in s['bindings'])) for s in original['shots'])
    primary=primary_model_slots(slots);batch=tuple(s for s in primary if s.shot_id in ids)
    facts={uid:spec['facts'] for uid,spec in read_json(source/'production/units.json')['payload']['semantic_specs'].items()}
    schema,prompt=_visual_request(frozen,batch,primary,slots,facts,None,[],concise=True,model_visual=True)
    write_exclusive(run/'samples/request.json',dict(schema=schema,prompt=prompt))
    with RunLock(run):
        manager,handle=owned_service(frozen,run,manifest,logger,'ollama')
        try:
            planner=OllamaPlanner(HttpClient(config.services['ollama'],config.timeouts['ollama_request'],logger))
            content=planner.generate(prompt,schema=schema,request_id='initial')
            try:validate_english_content(content)
            except ValueError as exc:
                content=planner.generate(prompt+'\nCORRECTION\n'+str(exc),schema=schema,request_id='correction')
                validate_english_content(content)
            validate_model_content(content,batch,semantic_specs=facts,depiction_policy=GROUNDED_POLICY,source_slots=slots)
            rows=[]
            historical={}
            for original_shot in selected:
                visual=next(s for s in content['shots'] if s['shot_id']==original_shot['shot_id'])
                row=deepcopy(original_shot);row.update(visual)
                # Preview only evaluates primary scene; retain all historical
                # requirements separately, including quantization edge facts.
                rows.append(row)
                historical[original_shot['shot_id']]=deepcopy(original_shot['visual_requirements'])
            board=dict(global_visual=content['global_visual'],shots=rows,historical_requirements=historical)
            for s in rows:
                render_model_prompt(s,board['global_visual'],'image');render_model_prompt(s,board['global_visual'],'video')
            write_exclusive(run/'samples/storyboard.json',board)
        finally:stop_owned_preserving_exception(manager,handle,logger,'preview-plan')
    print('PLANNED='+str(run/'samples/storyboard.json'),flush=True)


def generate(args):
    run=Path(args.run_dir);frozen=load_frozen_inputs(run);config=frozen.config
    manifest=ManifestStore.open(run,verify_integrity=False);logger=RunLogger(run,production=True)
    paths=RuntimePaths.from_config(config);board=read_json(run/'samples/storyboard.json')
    if not 3<=len(board['shots'])<=5:raise ValueError('bounded preview requires 3 to 5 shots')
    video=args.phase=='videos'
    selected=board['shots']
    if args.shot_ids:
        ids=args.shot_ids.split(',');known={s['shot_id'] for s in selected}
        if not ids or len(set(ids))!=len(ids) or set(ids)-known:raise ValueError('known unique preview shots required')
        selected=[s for s in selected if s['shot_id'] in ids]
    images=read_json(run/'samples/images.json') if video else None
    revisions=run/'samples/images-revision.json'
    if video and revisions.exists():
        revised=read_json(revisions)['images'];ids=[r['shot_id'] for r in revised]
        if len(set(ids))!=len(ids) or set(ids)-{r['shot_id'] for r in images['images']}:raise ValueError('known unique revised images required')
        updates={r['shot_id']:r for r in revised};images=dict(images=[updates.get(r['shot_id'],r) for r in images['images']])
    if video:
        observation_path=require_preview_observation(run,board,images)
        print('PREVIEW ONLY: observed image findings remain unchanged; no production approval.',flush=True)
        observation=thaw(hash_file(observation_path))
        write_exclusive(run/'samples/video-admission.json',dict(scope='preview_only',
            image_observation=observation,production_approved=False,shot_count=len(selected)))
    role='wan' if video else 'sdxl'
    template=WorkflowTemplate.load(Path(frozen.options['workflow_snapshots'][role]['path']),
        Path(frozen.options['workflow_snapshots'][role+'_mapping']['path']),config.models)
    validate_fixed_visual_template(template,role)
    results=[]
    with RunLock(run):
        for name in ('input','output','temp','user'):(run/'comfy'/name).mkdir(parents=True,exist_ok=True)
        manager,handle=owned_service(frozen,run,manifest,logger,'comfyui')
        try:
            client=ComfyClient(HttpClient(config.services['comfyui'],config.timeouts['comfy_request'],logger),manifest,logger)
            client.validate_template(template)
            for shot in selected:
                sid=shot['shot_id'];destination=run/'samples'/sid;destination.mkdir(exist_ok=True)
                target=destination/('source.mp4' if video else 'start.png')
                if target.exists():raise FileExistsError('preview output exists; no overwrite or auto-resubmit: '+str(target))
                kind='shot_attempt' if video else 'image';uid=sid+':attempt_0001' if video else sid
                if manifest.snapshot()['units'].get(kind,{}).get(uid,{}).get('submission') is not None:
                    raise ProductionRefused('existing preview request; inspect original evidence, no auto-retry')
                prefix=f'{run.name}/preview/{sid}/'+role
                if video:
                    image=next(r for r in images['images'] if r['shot_id']==sid)
                    relative=f'{run.name}/preview/{sid}/start.png';input_path=run/'comfy/input'/relative;input_path.parent.mkdir(parents=True,exist_ok=True)
                    with Path(image['image']['path']).open('rb') as src,input_path.open('xb') as dst:shutil.copyfileobj(src,dst)
                    p=dict(positive=render_model_prompt(shot,board['global_visual'],'video'),length=49,width=768,height=432,fps=16,
                        seed_high=264244520398999+int(sid[5:])-1,seed_low=0)
                    graph=template.instantiate(dict(positive_prompt=p['positive'],start_image=relative,width=768,height=432,length=49,fps=16,
                        seed_high=p['seed_high'],seed_low=0),output_prefix=prefix)
                else:
                    p=image_parameters(shot,board['global_visual'],768,432,model_visual=True)
                    graph=template.instantiate(dict(positive_prompt=p['positive'],negative_prompt=p['negative'],seed=p['seed'],width=p['width'],height=p['height']),output_prefix=prefix)
                write_exclusive(destination/('wan-parameters.json' if video else 'sdxl-parameters.json'),p)
                print('GENERATING '+role+' '+sid,flush=True)
                submission=client.submit_once(graph,stage='source_clips' if video else 'start_images',kind=kind,unit_id=uid)
                history=client.wait_for(submission,deadline_seconds=config.timeouts['wan'] if video else config.timeouts['comfy_request'],poll_seconds=5)
                entry=client.http.get_json('/history/'+submission.prompt_id)[submission.prompt_id]
                saved=manifest.snapshot()['units'][kind][uid]['submission']
                output=output_from_history(entry,saved,graph,template,run,prefix,'.mp4' if video else '.png')
                with output.open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
                if video:inspect_production_video(target,width=768,height=432,config=config,paths=paths,logger=logger,unit_id=uid)
                else:validate_start_png(target,width=p['width'],height=p['height'],config=config,paths=paths,logger=logger,unit_id=uid,production=True)
                results.append(dict(shot_id=sid,image=thaw(hash_file(target))) if not video else dict(shot_id=sid,video=thaw(hash_file(target))))
                print('GENERATED '+str(target),flush=True)
        finally:stop_owned_preserving_exception(manager,handle,logger,'preview-'+role)
    report='videos.json' if video else 'images-revision.json' if args.shot_ids and (run/'samples/images.json').exists() else 'images.json'
    write_exclusive(run/'samples'/report,dict(clips=results) if video else dict(images=results))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=('plan','images','videos'),required=True)
    parser.add_argument('--source-run');parser.add_argument('--shot-ids');parser.add_argument('--run-dir')
    args=parser.parse_args()
    if args.phase=='plan':
        if not args.source_run or not args.shot_ids:parser.error('plan requires --source-run and --shot-ids')
        plan(args)
    else:
        if not args.run_dir:parser.error('images/videos require --run-dir')
        generate(args)
