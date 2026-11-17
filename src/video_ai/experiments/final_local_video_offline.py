"""Real tiny CPU media through the actual LVA-06 coordinator, fake Comfy only."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4
import wave

from .final_local_video_benchmark import (SOURCE,PROFILE,TRIALS,FinalBenchmarkPlan,
    FinalBenchmarkSession,artifact,read,write_once,digest)
from .final_local_video_execution import RealFinalBackend,run_batch
from .upscale_offline import OfflineTransport
from ..runtime.paths import RUNTIME_ROOT


class NativeTransport:
    def __init__(self,root,video):self.root,self.video=Path(root),Path(video);self.history={}
    def __call__(self,method,route,payload=None):
        if method=='POST':
            if set(payload)!={'prompt','client_id'}:raise ValueError('sidecar data leaked into Comfy POST')
            graph=payload['prompt'];pid=str(uuid4());name=pid+'.mp4'
            target=self.root/'output'/name;target.parent.mkdir(exist_ok=True);shutil.copyfile(self.video,target)
            self.history[pid]=dict(prompt=[0,pid,graph,dict(client_id=payload['client_id'])],
                status=dict(completed=True,status_str='success'),
                outputs={'108':{'images':[dict(filename=name,subfolder='',type='output')]}})
            return dict(prompt_id=pid,node_errors={})
        if route=='/history':return self.history
        if route=='/queue':return dict(queue_running=[],queue_pending=[])
        pid=route.split('/')[-1];return {pid:self.history[pid]} if pid in self.history else {}


class OfflineBackend(RealFinalBackend):
    def __init__(self,plan,sha,video):super().__init__(plan,sha);self.video=video;self.transports={}
    @contextmanager
    def owned(self,root,initialize):
        if not root.exists():
            root.mkdir(parents=True)
            write_once(root/'frozen/final-plan.json',self.plan)
            write_once(root/'experiment.json',dict(kind='LVA-06',port=8189,profile_sha256=self.sha))
            initialize()
        yield
    def transport_for(self,root):
        if root not in self.transports:
            self.transports[root]=OfflineTransport(root) if root.name=='upscale' else NativeTransport(root,self.video)
        return self.transports[root]
    def telemetry(self,root,rows):return dict(scope='CPU offline only; no GPU/model/service',physical_model_load_count=None)


def run_offline():
    from ..config import load_config
    from ..runtime.production_state import ArtifactStamp
    from ..planning.production_scenes import canonical_digest
    config=load_config(SOURCE/'config/production.example.json')
    root=RUNTIME_ROOT/'scratch/benchmarks'/('LVA-06-offline-'+uuid4().hex[:12]);root.mkdir(parents=True)
    before=time.perf_counter();ffmpeg=config.tools['ffmpeg']
    video=root/'synthetic-source.mp4'
    subprocess.run([str(ffmpeg),'-nostdin','-n','-v','error','-f','lavfi','-i','color=c=blue:s=32x32:r=16',
        '-frames:v','3','-c:v','libx264','-crf','18','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True,timeout=30)
    image=root/'synthetic-source.png'
    subprocess.run([str(ffmpeg),'-nostdin','-n','-v','error','-i',str(video),'-frames:v','1',str(image)],check=True,capture_output=True,timeout=30)
    audio=root/'synthetic.wav'
    with wave.open(str(audio),'wb') as out:
        out.setparams((1,2,48000,0,'NONE',''));out.writeframes(b'\0'*(18000*2))
    timeline=root/'timeline.json'
    write_once(timeline,dict(clips=[dict(unit_id='offline',text='CPU offline',start_sample=0,end_sample=18000,
        samples=18000,pcm=dict(stamp=ArtifactStamp.read(audio).to_dict()))],
        subtitles=[dict(start_sample=0,end_sample=18000,text='CPU offline')]))
    font=Path('C:/Windows/Fonts/msyh.ttc')
    assets={k:artifact(config.tools[k]).identity_dict() for k in ('ffmpeg','ffprobe')}
    assets['pcm']=artifact(audio).identity_dict()
    assets['upscale_workflow']=artifact(SOURCE/'workflows/upscale_api.json').identity_dict()
    native={}
    for key in ('low','high','parent','child'):
        child=key=='child';label={'low':'low_motion','high':'high_motion','parent':'parent_child','child':'parent_child'}[key]
        graph={'97':{'inputs':{'image':'start.png'}},'108':{'inputs':{'filename_prefix':'native'}}}
        budget=dict(clip_id=key,parent_clip_id='parent' if child else None,start_frame=3 if child else 0,
                    end_frame=6 if child else 3,generated_frames=3,retained_frames=3,
                    retained_source_start=0,retained_source_end=3)
        p=dict(steps=40,cfg=3.5,lora_enabled=False,width=32,height=32,fps=16)
        request=dict(clip_id=key,parent=dict(offline=True) if child else None,
                     parameters=p,budget=budget,graph_sha256=canonical_digest(graph),narration_bindings=[])
        folder=root/'sources'/key;folder.mkdir(parents=True)
        request_path=folder/'request.json';graph_path=folder/'graph.json'
        write_once(request_path,request);write_once(graph_path,graph)
        fixture=dict(schema_version=1,fixture_id=label,source_clip_id=key,requires_new_parent=child,
            parameters=p,budget=budget,source_graph_sha256=canonical_digest(graph),
            input_relative=label+'/start.png',input_sha256=artifact(image).sha256)
        if child:fixture['graph_file']='child-original-graph.json'
        native[key]=dict(fixture=fixture,request=artifact(request_path).identity_dict(),graph=artifact(graph_path).identity_dict(),
            requires_new_parent=child,input=artifact(image).identity_dict(),timeline=artifact(timeline).identity_dict(),font=artifact(font).identity_dict())
    fixtures={k:dict(root=str(root/k),native={part:native[part] for part in parts})
              for k,parts in [('low',['low']),('high',['high']),('chain',['parent','child'])]}
    plan=FinalBenchmarkPlan(1,'LVA-06',PROFILE,assets,fixtures,TRIALS);sha=plan.digest();path=root/'plan.json'
    write_once(path,dict(plan=plan.identity_dict(),plan_sha256=sha))
    backend=OfflineBackend(plan.identity_dict(),sha,video);states=[];counts=None
    for key in ('low','high','chain'):
        state=run_batch(path,key,backend=backend,allowed_root=root)
        while state['pending_review']:
            folder=Path(state['root']);session=FinalBenchmarkSession(folder,sha);pending=session.snapshot()['open_reviews'][0]
            decision=folder/(pending['review_kind']+'-offline-decision.json')
            write_once(decision,dict(task_id='LVA-06',kind=pending['review_kind'],decision='accepted',
                media_artifacts=pending['media_artifacts'],user_evidence='SIMULATED OFFLINE DECISION ONLY; not actual human quality'))
            session.finish_review(artifact(decision).identity_dict())
            state=run_batch(path,key,backend=backend,allowed_root=root)
        states.append(state)
    counts=dict(backend.counters)
    for key in ('low','high','chain'):run_batch(path,key,backend=backend,allowed_root=root)
    delta={k:backend.counters[k]-counts[k] for k in counts}
    if any(delta.values()):raise AssertionError('completed offline replay repeated work')
    return dict(schema_version=1,task_id='LVA-06',status='offline_passed',root=str(root),gpu_executed=False,
        real_model_loaded=False,network_calls=0,quality='simulated_offline_decisions_not_real_acceptance',
        scope='Three CPU synthetic fixtures, cold1/warm3 protocol identities; 3 frames/part; not original GPU budgets or timings',
        native_requests=16,upscale_requests=48,compositions=12,counters=counts,completed_replay_delta=delta,
        fixture_summaries=[s['summary'] for s in states],elapsed_seconds=time.perf_counter()-before,
        production_resumed=False)
