"""Staged LVA-06 coordinator and original quality media adapters.

All evidence and HTTP run synchronously on the coordinator. Owned service
contexts always close before a review can be created.
"""
from contextlib import contextmanager,nullcontext
from copy import deepcopy
from functools import lru_cache
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from .final_local_video_benchmark import (PROFILE, TRIALS, SOURCE, Artifact, artifact,
    digest, read, write_once, verify_final_plan, FinalBenchmarkSession,
    FinalExperimentClient, FinalMediaCommands, summarize_final_results, batch_lock)
from .upscale_experiment import baseline_api
from ..runtime.paths import RUNTIME_ROOT
from ..runtime.verification import whole_input_protection,writable_validation_session


@lru_cache(maxsize=1)
def post_api():
    from .upscale_manifest import _module
    return _module('_lva06_postprocess', SOURCE/'scripts/postprocess_local_gpu.py')


def _all_artifacts(root):
    """Capture original protocol/command receipts as well as media, once."""
    return [artifact(p).identity_dict() for p in sorted(Path(root).rglob('*'))
            if p.is_file() and p.suffix.lower() in ('.json', '.png', '.mp4', '.ass', '.wav', '.ttc')
            and p.name not in ('service-result.json', 'stop.request.json')]


def _verify_result(result):
    for a in result['artifacts']: Artifact(**a).verify()


def _subjects(result):
    return [artifact(row[k]).identity_dict() for row in result['trials']
            for k in ('generated', 'retained', 'last_frame')]


def _publish_native_approval(root, result, decision):
    for row in result['trials']:
        write_once(root/'trials'/row['trial_id']/'observation-accepted.json', dict(
            decision='accepted', **{k+'_sha256':row[k+'_sha256'] for k in ('generated','retained','last_frame')},
            actual_user_decision=decision['decision_artifact']))


def run_batch(plan_path, fixture, *, backend=None, allowed_root=None):
    report = read(plan_path); plan, sha = report['plan'], report['plan_sha256']
    if digest(plan)!=sha or plan.get('profile')!=PROFILE:raise ValueError('final plan identity drift')
    if fixture not in ('low', 'high', 'chain'): raise ValueError('unknown fixture')
    selected = plan['fixtures'][fixture]; root = Path(selected['root']).resolve()
    allowed = Path(allowed_root or RUNTIME_ROOT/'scratch/benchmarks').resolve()
    if not root.is_relative_to(allowed): raise ValueError('batch root outside admitted scratch')
    if backend is None:
        if not root.name.startswith('LVA-06-'): raise ValueError('new LVA-06 root required')
        backend = RealFinalBackend(plan, sha)
        # Real batches are measured serially in predefined order.
        previous = ('low', 'high', 'chain')[:('low', 'high', 'chain').index(fixture)]
        for key in previous:
            prior_root = Path(plan['fixtures'][key]['root']); session = FinalBenchmarkSession(prior_root, sha)
            final = [r for r in session.snapshot()['reviews'] if r['kind']=='final']
            if len(final)!=1 or final[0]['decision']!='accepted':
                raise ValueError('previous real batch must be closed and quality accepted')
    sealed=tuple(Path(a['path']) for a in plan['assets'].values())
    with batch_lock(root), whole_input_protection(immutable_roots=sealed),writable_validation_session(root):
        verify_final_plan(plan, sha)
        s = FinalBenchmarkSession(root, sha)
        if not s.events: s.record_selection_handoff()
        else: s.resume_original()
        write_once(root/'frozen/final-plan.json', plan)
        results = {}; local = []; stage_records={}

        def stage(name, operation, trial=None):
            path = root/'stage-results'/(name+('_'+trial if trial else '')+'.json')
            prior = next((v for v in s.snapshot()['stages'] if v['name']==name and v['trial']==trial), None)
            if path.exists():
                value = read(path)
                if value['plan_sha256'] != sha: raise ValueError('stage plan identity differs')
                _verify_result(value['result'])
                if prior:
                    if prior['evidence']['receipt'] != artifact(path).identity_dict(): raise ValueError('stage receipt drift')
                else:
                    s.finish_phase(name, trial, recovered=True, receipt=artifact(path).identity_dict())
                stage_records[(name,trial)]=value
                return value['result']
            if prior: raise ValueError('completed phase lost receipt')
            opened = s.snapshot()['open_phases']
            recovering = bool(opened)
            if opened:
                if len(opened)!=1 or (opened[0]['name'],opened[0]['trial'])!=(name,trial):
                    raise ValueError('different original phase remains incomplete')
            else: s.enter_phase(name, trial)
            before=dict(getattr(backend,'counters',{}))
            try:
                with backend.measure() if hasattr(backend,'measure') else nullcontext():
                    value = operation()
            except BaseException as exc:
                try:s._event('stage_failure',name=name,trial=trial,exception_type=type(exc).__name__,
                    invocation_counter_delta={k:v-before.get(k,0) for k,v in getattr(backend,'counters',{}).items()})
                except Exception as diagnostic:exc.add_note('failure diagnostic failed: '+type(diagnostic).__name__)
                raise
            _verify_result(value)
            delta={k:v-before.get(k,0) for k,v in getattr(backend,'counters',{}).items()}
            is_recovery=recovering or value.get('mode')=='recovery' or any(
                r.get('mode')=='recovery' or ('wall_seconds' in r and r['wall_seconds'] is None)
                for r in value.get('trials',[]))
            saved=dict(plan_sha256=sha,result=value,counters=delta,counters_complete=not recovering,
                       mode='recovery' if is_recovery else 'normal')
            write_once(path,saved);stage_records[(name,trial)]=saved
            s.finish_phase(name, trial, recovered=recovering, receipt=artifact(path).identity_dict())
            return value

        def review(kind, subjects):
            snapshot = s.snapshot()
            done = next((v for v in snapshot['reviews'] if v['kind']==kind), None)
            if done:
                Artifact(**done['decision_artifact']).verify()
                decision = read(done['decision_artifact']['path'])
                if (done['media_artifacts'] != subjects or decision['media_artifacts'] != subjects
                        or decision['decision'] != done['decision']): raise ValueError('review decision identity drift')
                for a in subjects: Artifact(**a).verify()
                return done
            if snapshot['open_reviews']:
                pending = snapshot['open_reviews'][0]
                if pending['review_kind'] != kind or pending['media_artifacts'] != subjects:
                    raise ValueError('pending review differs')
            else: s.begin_review(kind, subjects)
            return None

        def state(kind, decision=None, summary=None):
            status = 'awaiting_human_review' if decision is None else 'quality_'+decision['decision']
            return dict(task_id='LVA-06', fixture=fixture, root=str(root), plan_sha256=sha,
                        status=status, pending_review=kind if decision is None else None,
                        review=s.snapshot()['open_reviews'], summary=summary,
                        invocation_counters=dict(getattr(backend,'counters',{})),
                        production_resumed=False)

        native_keys = ('parent','child') if fixture=='chain' else (fixture,)
        for key in native_keys:
            native_root = root/('native_'+key)
            parent_root = root/'native_parent' if key=='child' else None
            value = stage('native_'+key, lambda k=key,r=native_root,p=parent_root:
                          backend.native(r,k,selected['native'][k],parent_root=p))
            results[key] = value
            kind = ('child_continuity' if key=='child' else 'parent') if fixture=='chain' else 'native'
            subjects = _subjects(value)
            if key=='child':
                # Preview is independently receipted, never remade just to review.
                previews = stage('continuity_preview', lambda: dict(artifacts=backend.continuity(root,root/'native_parent',native_root)))
                subjects += previews['artifacts']
            decision = review(kind, subjects)
            if decision is None or decision['decision']!='accepted': return state(kind,decision)
            _publish_native_approval(native_root, value, decision)
            for i,row in enumerate(value['trials']):
                local.append(dict(stage='native_'+key, temperature='process_cold' if i==0 else 'warm_process',
                                  mode='recovery' if row.get('wall_seconds') is None else 'normal', seconds=row.get('wall_seconds')))
        sources = [(k, root/('native_'+k)) for k in native_keys]
        upscale = stage('upscale_'+fixture, lambda: backend.upscale(root/'upscale',sources))
        for i,row in enumerate(upscale.get('trials',[])):
            local.append(dict(stage='upscale_'+fixture,temperature='process_cold' if i==0 else 'warm_process',
                              mode=row.get('mode','normal'),seconds=row.get('submit_and_tracking_seconds')))
        finals = []
        for trial in TRIALS:
            value = stage('composition', lambda t=trial: backend.compose(root/'upscale',fixture,t,sources),trial)
            phase = next(v for v in s.snapshot()['stages'] if v['name']=='composition' and v['trial']==trial)
            finals.append(dict(trial=trial, completed_at=phase['end'], contribution_frames=value['technical']['frames'],
                               quality_accepted=False,candidate=value['candidate'],candidate_sha256=value['candidate_sha256']))
        end = s.finish_batch(); snapshot = s.snapshot()
        totals={k:sum(v['counters'].get(k,0) for v in stage_records.values())
                for k in {key for v in stage_records.values() for key in v['counters']}}
        failures=[e for e in s.events if e['kind']=='stage_failure']
        for event in failures:
            for k,v in event['invocation_counter_delta'].items():totals[k]=totals.get(k,0)+v
        resources={name:result.get('resources',{}) for name,result in results.items()}
        resources['upscale']=upscale.get('resources',{})
        measurement = dict(batch_id=fixture, profile=PROFILE,
            mode='recovery' if any(v['mode']=='recovery' for v in stage_records.values()) else 'normal',fps=16,
            t0=snapshot['t0'], tend=end['utc'], reviews=snapshot['reviews'], stages=snapshot['stages'],
            local_samples=local, trials=finals, resources=resources,
            counters=totals,counters_complete=all(v['counters_complete'] for v in stage_records.values()),
            counters_scope='Direct coordinator invocation deltas, accumulated once per completed stage; interrupted invocation missing counts explicit.',
            failed=len(failures),redone=0)
        # The technical boundary persists before the final review begins.
        technical = root/'batch-measurement.json'
        if not technical.exists(): write_once(technical,measurement)
        else: measurement=read(technical)
        bindings=[e for e in s.events if e['kind']=='measurement_complete']
        if not bindings:s._event('measurement_complete',measurement=artifact(technical).identity_dict())
        elif bindings[0]['measurement']!=artifact(technical).identity_dict():raise ValueError('measurement content drift')
        subjects = [artifact(t['candidate']).identity_dict() for t in finals]
        decision = review('final',subjects)
        if decision and decision['decision']=='accepted':
            for t in measurement['trials']: t['quality_accepted']=True
        measurement['quality_decisions']=s.snapshot()['reviews']
        return state('final',decision,summarize_final_results([measurement]))


class RealFinalBackend:
    def __init__(self, plan, sha):
        self.plan, self.sha = plan, sha
        self.counters = ObservedCounters(post=0,get=0,producer=0,decode=0,probe=0,actual_sha_calls=0,actual_sha_bytes=0)

    @contextmanager
    def measure(self):
        """Count existing command/hash work; introduce no reads or media passes."""
        import hashlib
        from ..runtime import verification as verification
        old_run,old_hash,old_read=subprocess.run,hashlib.file_digest,verification._read_open_bytes
        def run(args,*a,**kw):
            argv=list(map(str,args))
            tool=Path(argv[0]).resolve() if argv else None
            if tool==Path(self.plan['assets']['ffprobe']['path']).resolve():self.counters['probe']+=1
            elif tool==Path(self.plan['assets']['ffmpeg']['path']).resolve():
                decoding=any(v in argv for v in ('framehash','rawvideo','null'))
                self.counters['decode' if decoding else 'producer']+=1
            return old_run(args,*a,**kw)
        def hash_file(stream,*a,**kw):
            start=stream.tell();result=old_hash(stream,*a,**kw)
            self.counters['actual_sha_calls']+=1;self.counters['actual_sha_bytes']+=stream.tell()-start
            return result
        def read_bytes(stream,path):
            result=old_read(stream,path)
            self.counters['actual_sha_calls']+=1;self.counters['actual_sha_bytes']+=len(result[0])
            return result
        self.counters.observed=True;subprocess.run=run;hashlib.file_digest=hash_file;verification._read_open_bytes=read_bytes
        try:yield
        finally:
            subprocess.run=old_run;hashlib.file_digest=old_hash;verification._read_open_bytes=old_read;self.counters.observed=False

    @contextmanager
    def owned(self, root, initialize):
        """Never launch a replacement for an existing phase/history."""
        from .upscale_manifest import stop_owner, _port_open
        from ..runtime.environment import build_child_env
        from ..runtime.paths import RuntimePaths
        from ..config import load_config
        fresh = not root.exists(); service=None; logs=[]; failure=None
        try:
            if fresh:
                root.mkdir(parents=True)
                write_once(root/'frozen/final-plan.json',self.plan)
                write_once(root/'experiment.json',dict(kind='LVA-06',port=8189,profile_sha256=self.sha))
                initialize()
                if _port_open(8188) or _port_open(8189): raise ValueError('another Comfy service is listening')
                argv=[self.plan['assets']['comfy_python']['path'],'-B','-s',str(SOURCE/'scripts/observe_final_comfy.py'),
                      '--experiment-root',str(root),'--profile-sha256',self.sha,'--port','8189','--max-seconds','14400']
                write_once(root/'frozen/service-launch.json',dict(args=argv,profile_sha256=self.sha,port=8189))
                logs=[(root/'launcher.stdout').open('xb'),(root/'launcher.stderr').open('xb')]
                config=load_config(Path(self.plan['assets']['configuration']['path']))
                service=subprocess.Popen(argv,stdout=logs[0],stderr=logs[1],cwd=SOURCE,
                    env=build_child_env(RuntimePaths.from_config(config)),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                until=time.monotonic()+300
                while time.monotonic()<until:
                    if service.poll() is not None: raise RuntimeError('owned observer exited during startup')
                    if (root/'service-owner.json').exists() and _port_open(8189):
                        client=FinalExperimentClient(root,plan_sha256=self.sha,counters=self.counters)
                        client.verify(); client.assert_owned_service(); break
                    time.sleep(.25)
                else: raise TimeoutError('owned final service startup timeout')
            yield
        except BaseException as exc: failure=exc; raise
        finally:
            try: stop_owner(root,self.sha,service,original=failure)
            finally:
                for stream in logs: stream.close()

    @contextmanager
    def adapters(self, root):
        """Scoped original helper bindings; production modules stay unchanged."""
        api, post=baseline_api(),post_api()
        old_client,old_post,old_command,old_post_command=api.ExperimentClient,post.ExperimentClient,api.media_command,post.media_command
        def factory(folder,**kw):
            if hasattr(self,'transport_for'):kw['http']=self.transport_for(Path(folder))
            return FinalExperimentClient(folder,plan_sha256=self.sha,counters=self.counters,**kw)
        def command(folder,name,argv,**kw):
            args=list(map(str,argv))
            if not self.counters.observed:
                if '-f' in args and any(x in args for x in ('null','rawvideo','framehash')):self.counters['decode']+=1
                elif 'probe' in name or 'frames'==name or 'pts' in name or 'aac' in name:self.counters['probe']+=1
                else:self.counters['producer']+=1
            return old_command(folder,name,argv,**kw)
        api.ExperimentClient=post.ExperimentClient=factory; api.media_command=post.media_command=command
        try: yield api,post
        finally:
            api.ExperimentClient,post.ExperimentClient=old_client,old_post
            api.media_command,post.media_command=old_command,old_post_command

    def _initialize_native(self, root, source):
        fixture=deepcopy(source['fixture']); graph=read(source['graph']['path']); request=read(source['request']['path'])
        write_once(root/'frozen/original-request.json',request)
        write_once(root/'frozen/original-graph.json',graph)
        if source['requires_new_parent']:
            write_once(root/'child-fixture.json',fixture)
            write_once(root/'frozen/child-original-request.json',request)
            write_once(root/'frozen/child-original-graph.json',graph)
        else:
            write_once(root/'fixture.json',fixture)
            target=root/'input'/fixture['input_relative'];target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source['input']['path'],target)
            Artifact(**dict(source['input'],path=str(target.resolve()))).verify()
        if not source['requires_new_parent']:
            post=post_api();post.bind_narration(root,source['timeline']['path']);post.bind_font(root,source['font'])

    def native(self, root, name, source, parent_root=None):
        rows=[]
        with self.owned(root,lambda:self._initialize_native(root,source)), self.adapters(root) as (api,post):
            if name=='child':
                # Original helper reads the child source definition from the parent.
                for fname in ('child-original-request.json','child-original-graph.json'):
                    write_once(parent_root/'frozen'/fname,read(root/'frozen'/fname))
                write_once(parent_root/'child-fixture.json',read(root/'child-fixture.json'))
            for trial in TRIALS:
                result=(api.run_child_trial(root,trial,parent_root=parent_root) if name=='child' else api.run_trial(root,trial))
                actual=trial+'_child' if name=='child' else trial
                result=dict(result,trial_id=actual)
                graph=read(root/'trials'/actual/'intent.json')['graph']
                client=factory_client(self,root)
                original,pid=client.completed(actual,graph)
                if str(original)!=result['generated'] or pid!=result['prompt_id']:raise ValueError('native completion original differs')
                rows.append(result)
        return dict(trials=rows,artifacts=_all_artifacts(root),resources=self.telemetry(root,rows))

    def upscale(self, root, sources):
        def initialize(): pass
        rows=[]
        with self.owned(root,initialize),self.adapters(root) as (api,post):
            # Trial order: the complete chain is one sample. The child portion
            # remains warm in this same upscale process.
            for trial in TRIALS:
                parts=[]
                for name,native in sources:
                    actual=trial+'_child' if name=='child' else trial
                    parts.append(post.upscale_trial(root,native,actual,port=8189))
                seconds=None if any(p['submit_and_tracking_seconds'] is None for p in parts) else sum(p['submit_and_tracking_seconds'] for p in parts)
                rows.append(dict(trial=trial,submit_and_tracking_seconds=seconds,
                                 mode='recovery' if any(p['mode']=='recovery' for p in parts) else 'normal'))
        return dict(trials=rows,artifacts=_all_artifacts(root),resources=self.telemetry(root,rows))

    def continuity(self, root, parent, child):
        videos=[]
        ffmpeg,ffprobe=(self.plan['assets'][k]['path'] for k in ('ffmpeg','ffprobe'))
        for trial in TRIALS:
            p=post_api().require_native_review(parent,trial)
            c=read(child/'trials'/(trial+'_child')/'technical-complete.json')
            baseline_api().validate_completed(c)
            binding=read(child/'trials'/(trial+'_child')/'parent-binding.json')
            if (binding['parent_last_frame_sha256']!=p['last_frame_sha256']
                    or binding['human_acceptance_sha256']!=artifact(parent/'trials'/trial/'observation-accepted.json').sha256):
                raise ValueError('continuity parent/approval binding differs')
            folder=child/'review'/trial;folder.mkdir(parents=True,exist_ok=True)
            listing=folder/'concat.txt'
            # MP4 format.duration can round half-frame milliseconds. Explicit
            # exact contribution durations preserve every native16 joint PTS.
            text=''.join("file '"+str(Path(r['retained']).resolve()).replace('\\','/').replace("'","'\\''")+"'\n"
                +f"duration {r['retained_frames']/16:.8f}\n" for r in (p,c))
            if listing.exists():
                if listing.read_text('utf-8')!=text:raise ValueError('continuity concat differs')
            else:listing.write_text(text,'utf-8')
            target=folder/'parent-child-native.mp4'
            runner=FinalMediaCommands(folder,self.sha,counters=self.counters)
            runner.produce('preview',[ffmpeg,'-nostdin','-n','-v','error','-f','concat','-safe','0','-i',listing,
                '-map','0:v:0','-c:v','copy','-an',target],[listing,p['retained'],c['retained']],target)
            proof=folder/'preview-proof.json'
            if not proof.exists():
                f=read(parent/'fixture.json')['parameters']
                with self.adapters(child):
                    info=baseline_api().inspect_media(child,target,width=f['width'],height=f['height'],
                        expected_frames=p['retained_frames']+c['retained_frames'],ffmpeg=ffmpeg,ffprobe=ffprobe)
                write_once(proof,dict(output=artifact(target).identity_dict(),technical=info))
            elif read(proof)['output']!=artifact(target).identity_dict():raise ValueError('preview proof source differs')
            videos.append(artifact(target).identity_dict())
        return videos

    def compose(self, root, name, trial, sources):
        return compose_final(root,name,trial,sources,self.plan,self.sha,self.counters)

    def telemetry(self, root, rows):
        from .upscale_manifest import summarize_phase
        pids=[dict(prompt_id=r['prompt_id']) for r in rows if 'prompt_id' in r]
        if not pids:
            pids=[dict(prompt_id=read(p)['prompt_id']) for p in (root/'trials').glob('*/accepted.json')]
        telemetry=summarize_phase(root,dict(frame_timings=pids))
        intervals=[];start=end=None;count=0
        path=root/'node-metrics.jsonl'
        events=path.read_text('utf-8').splitlines() if path.exists() else []
        for line in events:
            try:event=json.loads(line)
            except ValueError:continue
            if event.get('kind')!='gpu' or not event.get('devices'):continue
            offset=event['offset_seconds'];low=max(v['utilization_percent'] for v in event['devices'])<=5
            if start is not None and (not low or offset-end>6):
                intervals.append(dict(start_seconds=start,end_seconds=end,samples=count));start=end=None;count=0
            if low:
                if start is None:start=offset
                end=offset;count+=1
        if start is not None:intervals.append(dict(start_seconds=start,end_seconds=end,samples=count))
        telemetry['device_low_utilization']=dict(threshold_percent=5,max_sample_gap_seconds=6,intervals=intervals,
            observed_span_seconds=sum(v['end_seconds']-v['start_seconds'] for v in intervals),
            scope='Adjacent device-wide samples, including desktop/startup; not exclusive or kernel idle.')
        telemetry['service_result']=read(root/'service-result.json') if (root/'service-result.json').exists() else None
        sizes=[p.stat().st_size for p in root.rglob('*') if p.is_file()]
        telemetry['retained_logical_file_bytes']=sum(sizes)
        telemetry['peak_logical_file_bytes']=None
        telemetry['disk_scope']='Retained file lengths at phase end; filesystem/temp peak not sampled, no files deleted for benefit.'
        telemetry['physical_model_load_count']=None
        return telemetry


def factory_client(backend,root):
    options=dict(plan_sha256=backend.sha,counters=backend.counters)
    if hasattr(backend,'transport_for'):options['http']=backend.transport_for(root)
    return FinalExperimentClient(root,**options)


class ObservedCounters(dict):
    observed=False


def compose_final(work, name, trial, sources, plan, sha, counters):
    """Original subtitle/audio/x264 command with durable success and one AV decode."""
    from fractions import Fraction
    from ..media.subtitles import ass_text, layout_text, quantize
    from ..media.font_metrics import PrivateFont
    from ..planning.composition import CompositionSettings
    from ..media.composition_video import validate_probe, validate_audio_packets
    work=Path(work).resolve(); native=sources[0][1]
    fixture=read(native/'fixture.json'); post=post_api()
    label='parent_child_chain' if name=='chain' else fixture['fixture_id']
    folder=work/'postprocess'/(label+'_'+trial)
    complete=folder/'composition-complete.json'
    if complete.exists():
        result=read(complete)
        if result['plan_sha256']!=sha:raise ValueError('composition plan drift')
        _verify_result(result); return result
    folder.mkdir(parents=True,exist_ok=True);frames=folder/'frames';frames.mkdir(exist_ok=True)
    if name=='chain':
        rows=[]
        for key,source in sources:
            actual=trial+'_child' if key=='child' else trial
            sf=read(source/('child-fixture.json' if key=='child' else 'fixture.json'))
            value=read(work/'postprocess'/(sf['fixture_id']+'_'+actual)/'upscale-complete.json')
            rows.extend(value['frames'])
        copied=[]
        for i,row in enumerate(rows,1):
            a=artifact(row['path'])
            if a.sha256!=row['sha256']:raise ValueError('chain source frame changed')
            target=frames/f'frame_{i:06d}.png'
            if not target.exists():
                with Path(row['path']).open('rb') as src,target.open('xb') as out:
                    shutil.copyfileobj(src,out);out.flush();os.fsync(out.fileno())
            b=artifact(target)
            if b.sha256!=a.sha256:raise ValueError('chain target frame changed')
            copied.append(dict(path=str(target),sha256=b.sha256))
        child=read(sources[1][1]/'child-fixture.json')
        if (fixture['budget']['end_frame']!=child['budget']['start_frame']
                or len(copied)!=fixture['budget']['retained_frames']+child['budget']['retained_frames']):
            raise ValueError('chain continuity/contribution frame budget differs')
        write_once(folder/'upscale-complete.json',dict(frames=copied,frame_count=len(copied),width=1920,height=1080))
    upscaled=read(folder/'upscale-complete.json'); count=upscaled['frame_count']
    if len(upscaled['frames'])!=count:raise ValueError('complete ordered upscale frame budget required')
    for i,row in enumerate(upscaled['frames'],1):
        if Path(row['path']).resolve()!=frames/f'frame_{i:06d}.png' or artifact(row['path']).sha256!=row['sha256']:
            raise ValueError('ordered composition frame/source differs')
    narration_source=read(native/'narration-source.json'); font_source=read(native/'render-font.json')
    if artifact(narration_source['path']).sha256!=narration_source['sha256']:raise ValueError('original timeline changed')
    if artifact(font_source['path']).sha256!=font_source['sha256']:raise ValueError('original font changed')
    timeline=read(narration_source['path']);timeline=timeline.get('payload',timeline)
    before=time.perf_counter()
    narration=post.slice_narration(timeline,start_frame=fixture['budget']['start_frame'],frames=count,target=folder/'narration.wav')
    settings=CompositionSettings();fontdir=folder/'fonts';fontdir.mkdir(exist_ok=True);font=fontdir/'font.ttc'
    if not font.exists():shutil.copyfile(font_source['path'],font)
    if artifact(font).sha256!=font_source['sha256']:raise ValueError('copied render font differs')
    start=fixture['budget']['start_frame']*3000;end=start+count*3000;events=[]
    with PrivateFont(font,settings.font_name,settings.font_size) as metrics:
        for event in timeline['subtitles']:
            a,b=max(start,event['start_sample']),min(end,event['end_sample'])
            if a<b:events.append(dict(start_cs=quantize(a-start,100),end_cs=quantize(b-start,100),
                layout=layout_text(event['text'],measure=metrics.measure,width=1920-2*(settings.margin+settings.outline))))
    text=ass_text(events,settings);subtitles=folder/'subtitles.ass'
    if subtitles.exists():
        if subtitles.read_text('utf-8')!=text:raise ValueError('subtitle content differs')
    else:subtitles.write_text(text,'utf-8')
    audio_seconds=time.perf_counter()-before
    ffmpeg,ffprobe=(plan['assets'][k]['path'] for k in ('ffmpeg','ffprobe'))
    candidate=folder/'candidate-1080p.mp4'
    args=[ffmpeg,'-nostdin','-n','-v','error','-xerror','-framerate','16','-start_number','1',
          '-i',frames/'frame_%06d.png','-i',folder/'narration.wav','-filter_complex',
          '[0:v:0]subtitles=filename=subtitles.ass:fontsdir=fonts[v]','-map','[v]','-map','1:a:0',
          '-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough',
          '-c:a','aac','-b:a','192k','-ar','48000','-ac','1','-movflags','+faststart',candidate]
    command=FinalMediaCommands(folder,sha,counters=counters)
    inputs=[*[Path(r['path']) for r in upscaled['frames']],folder/'narration.wav',subtitles,font]
    receipt=command.produce('composition',args,inputs,candidate,cwd=folder)
    # Technical proof has its own durable receipt: recovery after success never
    # launches the encoder; after validation it never launches a decoder either.
    proof=folder/'delivery-proof.json'
    proof_identity=dict(candidate=artifact(candidate).identity_dict(),ffmpeg=artifact(ffmpeg).identity_dict(),
                        ffprobe=artifact(ffprobe).identity_dict(),frames=count,plan_sha256=sha)
    if proof.exists():
        saved=read(proof)
        if saved['identity']!=proof_identity:raise ValueError('delivery proof/tool/source differs')
        technical=saved['technical'];pixels=saved['frame_rgb_sha256'];pts=saved['pts'];skip=saved['aac_priming_samples']
    else:
        def probe(name,options):
            if not getattr(counters,'observed',False):counters['probe']+=1
            return json.loads(baseline_api().media_command(work,name,[ffprobe,'-v','error',*options,'-of','json',candidate]))
        technical=validate_probe(probe('delivery-probe',['-count_frames','-show_streams','-show_format']),
            probe('delivery-pts',['-select_streams','v:0','-show_frames']),fps=16,total_frames=count,channels=1)
        skip=validate_audio_packets(probe('delivery-aac',['-select_streams','a:0','-show_packets'])['packets'],count*3000)
        if not getattr(counters,'observed',False):counters['decode']+=1
        raw=baseline_api().media_command(work,'delivery-full-av-rgb',[ffmpeg,'-nostdin','-v','error','-xerror','-copyts','-i',candidate,
            '-map','0:v:0','-vf','format=rgb24','-fps_mode','passthrough','-c:v','rawvideo','-pix_fmt','rgb24',
            '-enc_time_base:v','demux','-f','framehash','-hash','sha256','-',
            '-map','0:a:0','-f','null',os.devnull])
        pixels=[];pts=[];tb=None
        for line in raw.decode('ascii').splitlines():
            if line.startswith('#tb 0:'):tb=Fraction(line.split(':',1)[1].strip())
            if line.startswith('#'):continue
            fields=[v.strip() for v in line.split(',')]
            if len(fields)!=6 or fields[4]!=str(1920*1080*3) or len(fields[5])!=64 or tb is None:
                raise ValueError('complete final RGB proof missing')
            pixels.append(fields[5]);pts.append(str(Fraction(fields[2])*tb))
        if len(pixels)!=count or pts!=[str(Fraction(i,16)) for i in range(count)]:raise ValueError('full final frame/PTS budget differs')
        write_once(proof,dict(identity=proof_identity,technical=technical,frame_rgb_sha256=pixels,pts=pts,aac_priming_samples=skip))
    result=dict(plan_sha256=sha,candidate=str(candidate),candidate_sha256=artifact(candidate).sha256,
        technical=technical,frame_rgb_sha256=pixels,pts=pts,narration=narration,
        subtitles_sha256=artifact(subtitles).sha256,aac_priming_samples=skip,
        encode_seconds=receipt['seconds'],narration_subtitle_seconds=audio_seconds,
        quality_status='awaiting_final_human_review',artifacts=_all_artifacts(folder))
    write_once(complete,result);return result
