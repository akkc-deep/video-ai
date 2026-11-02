"""Isolated seven-shot upstream receipts; real FFmpeg, scripted Comfy transport.

Upstream stages are characterized elsewhere. This fixture replaces their consumers
only, while source stage identity, planner, transport, manifest and media are real.
It never starts Comfy or loads models and its reviews are explicitly test-only.
"""
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from http_helpers import Response, ScriptedTransport
from image_helpers import write_png
from unit.test_source_clips import inputs


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return path


def setup(runtime_run, monkeypatch, mode='success', profile='fast', fps=16, transition='cut', wan_timeout=None):
    from video_ai.runtime import source_clip_checks as sc
    from video_ai.runtime import _source_clip_inputs as ci
    from video_ai.runtime import _source_clip_generation as cg
    from video_ai.config import load_config
    from video_ai.runtime.manifest import create_manifest, hash_file, thaw
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.workflows import WorkflowTemplate
    from unit.test_workflows import remote_info
    from unit.test_video import make_video
    run, original, paths = runtime_run
    actual = load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    raw = thaw(original.raw)
    raw['voice_config'] = str(original.voice.config_file)
    raw['workflows'] = {k:str(v) for k,v in original.workflows.items()}
    raw['tools']['ffmpeg'] = str(actual.tools['ffmpeg'])
    raw['tools']['ffprobe'] = str(actual.tools['ffprobe'])
    raw['services']['ollama'] = 'http://127.0.0.1:11435'
    if wan_timeout is not None:raw.setdefault('timeouts',{})['wan']=wan_timeout
    raw['media'].update(profile=profile, fps=fps, transition=transition, transition_seconds=0 if transition=='cut' else .5)
    for name in ('wan_high','wan_low','text_encoder','vae'):
        model=run/'fixture-models'/Path(raw['models'][name]).name
        model.parent.mkdir(exist_ok=True)
        model.write_bytes(('TEST ONLY '+name).encode())
        raw['models'][name]=str(model)
    config=load_config(write(run/'fixture-config.json',raw))
    store=create_manifest(run,config,inputs={'config':hash_file(config.config_file)},models={},workflows={})
    board,timeline,images=inputs(fps,transition,profile)
    board['run_id']=images['run_id']=run.name
    for row in images['images']:
        (run/'shots'/row['shot_id']).mkdir(parents=True,exist_ok=True)
        png=write_png(run/'shots'/row['shot_id']/'start.png',1280,720)
        row['image_identity']=thaw(hash_file(png))
    for name in ('storyboard-draft.json','images-draft.json'):
        write(run/name,{'fixture':name})
    board_review=write(run/'logs/storyboard/semantic-review.json',{'fixture':'accepted upstream'})
    image_review=write(run/'logs/start-images/semantic-review.json',{'fixture':'accepted upstream'})
    timing=write(run/'logs/storyboard/timing-review.json',{'fixture':'accepted upstream'})
    board.update(review_identity=thaw(hash_file(board_review)),timing_review_identity=thaw(hash_file(timing)))
    images.update(review_identity=thaw(hash_file(image_review)))
    for name,data in [('storyboard.json',board),('timeline.json',timeline),('images.json',images)]:
        write(run/name,data)
    for stage in ('speech','timeline','storyboard','start_images'):
        store.record_stage(stage,'running');store.record_stage(stage,'completed')
    def consumer(name):
        return lambda r: json.loads((r/name).read_text(encoding='utf-8'))
    monkeypatch.setattr(ci,'load_committed_storyboard',consumer('storyboard.json'))
    monkeypatch.setattr(ci,'load_committed_timeline',consumer('timeline.json'))
    monkeypatch.setattr(ci,'load_committed_start_images',consumer('images.json'))
    inventory={str(p.resolve()):thaw(hash_file(p)) for p in [config.workflows['wan'],config.workflows['wan_mapping'],*[config.models[k] for k in ('wan_high','wan_low','text_encoder','vae')]]}
    inv=write(run/'fixture-inventory.json',inventory)
    baseline=write(run/'fixture-acceptance.json',dict(components=dict(wan=dict(passed=True)),provenance=dict(wan=dict(before=thaw(hash_file(inv))))))
    monkeypatch.setattr(ci,'TASK4_ACCEPTANCE',baseline)
    actions=[];process=SimpleNamespace(stopped=False)
    process.poll=lambda:0 if process.stopped else None
    class Manager:
        def __init__(self,*a,**kw):pass
        def ensure(self,spec):
            assert all((run/'comfy'/n).is_dir() for n in ('input','output','temp','user'))
            actions.append('start')
            return SimpleNamespace(owned=mode!='external',process=process)
        def stop(self,handle):
            actions.append('stop')
            if mode!='stop_failure':process.stopped=True
        def release_comfy_models(self,*a):raise AssertionError('free forbidden')
    monkeypatch.setattr(cg,'ServiceManager',Manager)
    template=WorkflowTemplate.load(config.workflows['wan'],config.workflows['wan_mapping'],config.models)
    pending={};requests=[];logger=RunLogger(run)
    def route(request,timeout):
        assert 0<timeout<=config.timeouts['comfy_request']
        if request.full_url.endswith('/object_info'):return Response(remote_info(template))
        if request.method=='POST':
            graph=json.loads(request.data)['prompt'];length=graph['129:98']['inputs']['length']
            prefix=graph['108']['inputs']['filename_prefix'];requests.append(length)
            token=str(uuid4());source=run/'comfy/output'/(prefix+'_00001_.mp4')
            count=65 if mode in ('short','twice_short') and len(requests)==1 else length
            if mode=='twice_short' and len(requests)==2:count=65
            if mode=='mismatch':count=length+4
            if mode=='later_fail' and len(requests)==2:raise ConnectionResetError('accepted but response lost')
            width,height=graph['129:98']['inputs']['width'],graph['129:98']['inputs']['height']
            source.parent.mkdir(parents=True,exist_ok=True)
            make_video((run,dict(config=config,paths=paths,logger=logger,unit_id=prefix.split('/')[-2]+':'+prefix.split('/')[-1])),frames=count,width=width,height=height,name=source.relative_to(run).as_posix())
            if mode=='stale':
                import os
                os.utime(source,(0,0))
            outputs=[dict(filename=source.name,subfolder=source.parent.relative_to(run/'comfy/output').as_posix(),type='output')]
            if mode=='two':outputs.append(dict(outputs[0]))
            if mode=='prefix':outputs[0]['subfolder']='wrong'
            if mode=='url':outputs[0]['filename']='http://bad/video.mp4'
            pending[token]=dict(status=dict(completed=True,status_str='success'),outputs={'108':{'images':outputs}})
            if mode=='lost':raise ConnectionResetError('accepted but response lost')
            return Response(dict(prompt_id=token,number=0,node_errors={}))
        if '/history/' in request.full_url:
            token=request.full_url.rsplit('/',1)[-1]
            return Response({token:pending[token]} if token in pending else {})
        if request.full_url.endswith('/history'):return Response(pending)
        return Response(dict(queue_running=[],queue_pending=[]))
    transport=ScriptedTransport(route);base=cg.DeadlineHttp.__init__
    monkeypatch.setattr(cg.DeadlineHttp,'__init__',lambda self,*a,**kw:base(self,*a,transport=transport,**kw))
    return SimpleNamespace(sc=sc,ci=ci,cg=cg,run=run,config=config,store=store,transport=transport,actions=actions,requests=requests,board=board,timeline=timeline,images=images,process=process)


def review(run):
    from video_ai.runtime.manifest import hash_file,thaw,now
    draft=json.loads((run/'source-clips-draft.json').read_text(encoding='utf-8'))
    draft_id=thaw(hash_file(run/'source-clips-draft.json'))
    observations=[dict(row,playback_frames=row['local_frames'],start_observation='TEST ONLY: start inspected',
        process_observation='TEST ONLY: continuous branch wind, reflection ripple and forward walking',
        end_observation='TEST ONLY: endpoint inspected',quality_observation='TEST ONLY: no flicker or deformation') for row in draft['requirement_clips']]
    for row in observations:
        if row['role']=='primary' and row['clip_shot_id'] in ('shot_0004','shot_0006'):
            before='shot_0003' if row['clip_shot_id']=='shot_0004' else 'shot_0005'
            row['quality_observation']=f"[continuity:{before}->{row['clip_shot_id']}:passed] TEST ONLY: preceding endpoint/current start agree in reflected water or walking viewpoint; no flicker/deformation."
    note=write(run/'logs/source-clips/test-video-observation.json',dict(schema_version=1,run_id=run.name,
        draft_identity=draft_id,review_method='human_video',reviewer='TEST ONLY',viewed_at=now(),
        entries=observations))
    data=dict(schema_version=1,run_id=run.name,draft_identity=draft_id,
        **{key:draft[key] for key in ('images_identity','storyboard_identity','timeline_identity')},
        review_method='human_video',reviewer='TEST ONLY',reviewed_at=now(),global_verdict='passed',reason='TEST ONLY video fixture review',
        entries=[dict(row,evidence_identity=thaw(hash_file(note)),verdict='passed',reason='TEST ONLY requirement confirmed') for row in draft['requirement_clips']])
    return write(run/'logs/source-clips/semantic-review.json',data),data


def user_acceptance(run):
    from video_ai.runtime.manifest import hash_file,thaw,now
    draft=json.loads((run/'source-clips-draft.json').read_text(encoding='utf-8'))
    data=dict(schema_version=1,run_id=run.name,draft_identity=thaw(hash_file(run/'source-clips-draft.json')),
        **{key:draft[key] for key in ('images_identity','storyboard_identity','timeline_identity')},
        review_method='user_acceptance',reviewer='TEST ONLY user',reviewed_at=now(),accepted=True,
        acceptance_text='TEST ONLY: accept this candidate for continued development; refine later.',
        acceptance_scope='source_clips_for_upscale',
        unverified_checks=['video_text_semantics','motion_semantics','quality','cross_shot_continuity'],
        entries=draft['requirement_clips'])
    return write(run/'logs/source-clips/semantic-review.json',data),data
