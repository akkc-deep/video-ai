"""TEST ONLY upstream receipts and Comfy transport; real tiny FFmpeg media."""
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from http_helpers import Response, ScriptedTransport
from image_helpers import write_png
from source_clip_helpers import write
from unit.test_upscale import source_input


def setup(runtime_run, monkeypatch, mode='success', profile='fast', frames=2, clip_counts=None, clip_timeout=None,request_timeout=None,frame_timeout=None):
    from video_ai.runtime import upscale_checks as uc, _upscale_inputs as ui, _upscale_generation as ug
    from video_ai.config import load_config
    from video_ai.runtime.manifest import create_manifest, hash_file, thaw
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.workflows import WorkflowTemplate
    from unit.test_video import make_video
    run, original, paths = runtime_run
    actual=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    raw=thaw(original.raw);raw['voice_config']=str(original.voice.config_file)
    raw['workflows']={k:str(v) for k,v in original.workflows.items()}
    raw['services']['ollama']='http://127.0.0.1:11435'
    for name in ('ffmpeg','ffprobe'):raw['tools'][name]=str(actual.tools[name])
    raw['media']['profile']=profile
    if clip_timeout is not None:raw.setdefault('timeouts',{})['upscale_clip']=clip_timeout
    if request_timeout is not None:raw.setdefault('timeouts',{})['comfy_request']=request_timeout
    if frame_timeout is not None:raw.setdefault('timeouts',{})['upscale_frame']=frame_timeout
    model=run/'fixture-models/RealESRGAN_x4plus.pth';model.parent.mkdir();model.write_bytes(b'TEST ONLY upscale model; never loaded')
    raw['models']['upscale']=str(model)
    config=load_config(write(run/'fixture-config.json',raw));logger=RunLogger(run)
    store=create_manifest(run,config,inputs={'config':hash_file(config.config_file)},models={},workflows={})
    source=source_input(profile=profile);source['run_id']=run.name
    clip=source['clips'][0];source['clips']=[clip];mapped=source['frame_mappings'][0];source['frame_mappings']=[mapped]
    n=frames;generated=1+4*((n+2)//4)
    b=clip['budget'];b.update(core_start_frame=0,core_end_frame=n,coverage_start_frame=0,coverage_end_frame=n,
        incoming_overlap_frames=0,outgoing_overlap_frames=0,required_output_frames=n,required_native_frames=n,
        wan_frames=generated,native_trim_frames=generated-n)
    clip.update(source_frames=n,generated_frames=generated)
    mapped.update(core_start_frame=0,core_end_frame=n,coverage_start_frame=0,coverage_end_frame=n,
        source_frames=n,generated_frames=generated,generated_to_source=list(range(n))+[None]*(generated-n),output_to_source=list(range(n)))
    shot=run/'shots/shot_0001';shot.mkdir(parents=True)
    path=make_video((run,dict(config=config,paths=paths,logger=logger,unit_id='TEST ONLY')),
        frames=n,width=clip['width'],height=clip['height'],name='shots/shot_0001/source.mp4')
    clip['source_identity']=mapped['source_identity']=thaw(hash_file(path))
    review=write(run/'logs/source-clips/semantic-review.json',dict(review_method='user_acceptance',fixture='TEST ONLY'))
    source['review_identity']=thaw(hash_file(review))
    source['requirement_clips']=[dict(shot_id='shot_0001',requirement_index=0,clip_shot_id='shot_0001',
        role='primary',text='TEST ONLY full continuous action',actual_artifact=clip['source_identity'],
        local_frames=dict(start=0,end=n),output_frames=dict(start=0,end=n),source_samples=dict(start=0,end=n*3000))]
    if clip_counts is not None:
        from copy import deepcopy
        assert clip_counts[0]==frames
        offset=frames
        for ordinal,count in enumerate(clip_counts[1:],2):
            uid=f'shot_{ordinal:04d}';other=deepcopy(clip);association=deepcopy(mapped)
            generated=1+4*((count+2)//4)
            other.update(shot_id=uid,source_frames=count,generated_frames=generated)
            other['budget'].update(shot_id=uid,core_start_frame=offset,core_end_frame=offset+count,
                coverage_start_frame=offset,coverage_end_frame=offset+count,required_output_frames=count,
                required_native_frames=count,wan_frames=generated,native_trim_frames=generated-count)
            association.update(shot_id=uid,core_start_frame=offset,core_end_frame=offset+count,
                coverage_start_frame=offset,coverage_end_frame=offset+count,source_frames=count,generated_frames=generated,
                generated_to_source=list(range(count))+[None]*(generated-count),output_to_source=list(range(count)))
            (run/'shots'/uid).mkdir()
            target=make_video((run,dict(config=config,paths=paths,logger=logger,unit_id='TEST ONLY')),
                frames=count,width=other['width'],height=other['height'],name=f'shots/{uid}/source.mp4')
            other['source_identity']=association['source_identity']=thaw(hash_file(target))
            source['clips'].append(other);source['frame_mappings'].append(association)
            source['requirement_clips'].append(dict(shot_id=uid,requirement_index=ordinal-1,clip_shot_id=uid,
                role='primary',text='TEST ONLY full continuous action',actual_artifact=other['source_identity'],
                local_frames=dict(start=0,end=count),output_frames=dict(start=offset,end=offset+count),source_samples=dict(start=offset*3000,end=(offset+count)*3000)))
            offset+=count
    write(run/'source-clips.json',source)
    for stage in ('speech','timeline','storyboard','start_images','source_clips'):
        store.record_stage(stage,'running');store.record_stage(stage,'completed')
    store.record_unit('shot','shot_0001','running');store.record_unit('shot','shot_0001','completed')
    calls=[]
    def consumer(r):calls.append('source');return json.loads((r/'source-clips.json').read_text(encoding='utf-8'))
    monkeypatch.setattr(ui,'load_committed_source_clips',consumer)
    inv=write(run/'fixture-inventory.json',{str(p.resolve()):thaw(hash_file(p)) for p in
        (config.workflows['upscale'],config.workflows['upscale'].with_suffix('.mapping.json'),model)})
    acceptance=write(run/'fixture-acceptance.json',dict(components=dict(upscale=dict(passed=True)),
        provenance=dict(upscale=dict(before=thaw(hash_file(inv))))))
    monkeypatch.setattr(ui,'TASK4_ACCEPTANCE',acceptance)
    monkeypatch.setattr(ui,'MODEL_PATH',model)
    monkeypatch.setattr(ui,'MODEL_SHA',hash_file(model).sha256)
    actions=[];process=SimpleNamespace(stopped=False);process.poll=lambda:0 if process.stopped else None
    class Manager:
        def __init__(self,*a,**kw):pass
        def ensure(self,spec):
            actions.append('start');return SimpleNamespace(owned=mode!='external',process=process)
        def stop(self,handle):
            actions.append('stop')
            if mode!='stop_failure':process.stopped=True
        def release_comfy_models(self,*a):raise AssertionError('TEST ONLY: free forbidden')
    monkeypatch.setattr(ug,'ServiceManager',Manager)
    template=WorkflowTemplate.load(config.workflows['upscale'],config.workflows['upscale'].with_suffix('.mapping.json'),config.models)
    remote={node['class_type']:dict(input=dict(required={k:['STRING',{}] for k in node['inputs']},optional={}),output_node=node['class_type']=='SaveImage') for node in template.graph.values()}
    if mode=='remote_missing':del remote['ImageScale']['input']['required']['crop']
    pending={};requests=[]
    def route(request,timeout):
        assert 0<timeout<=config.timeouts['comfy_request']
        if request.full_url.endswith('/object_info'):return Response(remote)
        if request.method=='POST':
            graph=json.loads(request.data)['prompt'];requests.append(graph)
            if mode=='lost' or mode=='later_fail' and len(requests)==2:raise ConnectionResetError('TEST ONLY accepted response lost')
            prefix=graph['5']['inputs']['filename_prefix'];target=run/'comfy/output'/(prefix+'_00001_.png')
            target.parent.mkdir(parents=True,exist_ok=True)
            write_png(target,1920 if mode!='size' else 128,1080 if mode!='size' else 72)
            if mode=='corrupt':target.write_bytes(b'TEST ONLY corrupt PNG')
            if mode=='stale':
                import os
                os.utime(target,(0,0))
            output=dict(filename=target.name,subfolder=target.parent.relative_to(run/'comfy/output').as_posix(),type='output')
            if mode=='prefix':output['filename']='wrong.png'
            if mode=='url':output['filename']='http://bad/frame.png'
            outputs=[output,output] if mode=='two' else [output]
            token=str(uuid4());pending[token]=dict(status=dict(completed=True,status_str='success'),outputs={'5':{'images':outputs}})
            return Response(dict(prompt_id=token,number=0,node_errors={}))
        if '/history/' in request.full_url:
            token=request.full_url.rsplit('/',1)[-1];return Response({token:pending[token]} if token in pending else {})
        if request.full_url.endswith('/history'):return Response(pending)
        return Response(dict(queue_running=[],queue_pending=[]))
    transport=ScriptedTransport(route);base=ug.DeadlineHttp.__init__
    monkeypatch.setattr(ug.DeadlineHttp,'__init__',lambda self,*a,**kw:base(self,*a,transport=transport,**kw))
    return SimpleNamespace(uc=uc,ui=ui,ug=ug,run=run,config=config,store=store,requests=requests,
        actions=actions,source=source,calls=calls,process=process,transport=transport)


def review(run):
    from video_ai.runtime.manifest import hash_file,thaw,now
    draft=json.loads((run/'upscaled-clips-draft.json').read_text(encoding='utf-8'));identity=thaw(hash_file(run/'upscaled-clips-draft.json'))
    observations=[dict(row,source_playback_frames=row['local_frames'],upscaled_playback_frames=row['local_frames'],
        start_observation='TEST ONLY start viewed',process_observation='TEST ONLY continuous action viewed',
        end_observation='TEST ONLY end viewed',comparison_observation='TEST ONLY source and new video agree',
        quality_observation='TEST ONLY no new color noise seams flicker texture jumps deformation') for row in draft['requirement_clips']]
    for row in observations:
        if row['role']=='primary' and row['clip_shot_id'] in ('shot_0004','shot_0006'):
            before='shot_0003' if row['clip_shot_id']=='shot_0004' else 'shot_0005'
            row['quality_observation']=f"[continuity:{before}->{row['clip_shot_id']}:passed] TEST ONLY continuous endpoint/start comparison agrees"
    note=write(run/'logs/upscale/test-observation.json',dict(schema_version=1,run_id=run.name,draft_identity=identity,
        review_method='human_video',reviewer='TEST ONLY',viewed_at=now(),entries=observations))
    data=dict(schema_version=1,run_id=run.name,draft_identity=identity,source_clips_identity=draft['source_clips_identity'],
        review_method='human_video',reviewer='TEST ONLY',reviewed_at=now(),global_verdict='passed',reason='TEST ONLY continuous comparison',
        entries=[dict(row,evidence_identity=thaw(hash_file(note)),verdict='passed',reason='TEST ONLY actual video comparison') for row in draft['requirement_clips']])
    return write(run/'logs/upscale/semantic-review.json',data),data


def reseal_technical(f,draft):
    """TEST ONLY refresh every receipt so tests reach semantic validation, not hashes."""
    from video_ai.runtime.manifest import hash_file,thaw
    from video_ai.runtime.timeline_checks import _artifact
    def refresh(value):
        if isinstance(value,dict):
            if set(value)=={'path','bytes','mtime_ns','sha256','verified_at'}:
                actual=thaw(hash_file(Path(value['path'])))
                return value if all(value[k]==actual[k] for k in ('path','bytes','mtime_ns','sha256')) else actual
            return {key:refresh(item) for key,item in value.items()}
        if isinstance(value,list):return [refresh(item) for item in value]
        return value
    # Preserve identity references exactly across frames/top-level before refreshing.
    draft=refresh(draft)
    for clip in draft['clips']:
        for frame in clip['frames']:
            for key in ('source_identity','parameters'):frame[key]=clip[key]
            for key in ('model_identity','workflow_identity','mapping_identity'):frame[key]=draft[key]
            checkpoint=Path(frame['checkpoint_identity']['path'])
            write(checkpoint,{k:v for k,v in frame.items() if k!='checkpoint_identity'})
            frame['checkpoint_identity']=thaw(hash_file(checkpoint))
        write(f.run/'logs/upscale'/f"clip-{clip['shot_id']}.json",clip)
    draft['request_evidence']={name:thaw(hash_file(f.run/name)) for name in draft['request_evidence']}
    snapshot=f.store.snapshot()
    for clip in draft['clips']:
        for frame in clip['frames']:
            uid=f"{clip['shot_id']}:frame_{frame['frame_index']:06d}"
            snapshot['workflows'][frame['submission']['attempt_id']]=frame['submission']['intent_identity']
            snapshot['units']['frame'][uid]['artifacts']=[_artifact(hash_file(Path(frame[k]['path']))) for k in ('checkpoint_identity','input_identity','upscaled_frame_identity')]
    return draft,snapshot
