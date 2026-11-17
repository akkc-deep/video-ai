"""Exercise the complete staged coordinator without any GPU/network model."""
from pathlib import Path

import pytest

from video_ai.experiments.wan_fast_profiles import artifact, write_once, digest
from video_ai.experiments.final_local_video_benchmark import PROFILE, TRIALS, FinalBenchmarkPlan


class FakeBackend:
    def __init__(self): self.calls = []; self.closed = True
    def native(self, root, name, source, parent_root=None):
        assert self.closed
        self.calls.append(name)
        if name == 'child':
            assert all((parent_root/'trials'/t/'observation-accepted.json').is_file() for t in TRIALS)
        rows = []
        for t in TRIALS:
            actual = t+'_child' if name == 'child' else t
            folder = root/'trials'/actual; folder.mkdir(parents=True, exist_ok=True)
            paths = {}
            for role in ('generated', 'retained', 'last_frame'):
                p = folder/role; p.write_bytes((name+t+role).encode()); a = artifact(p)
                paths[role] = a.path; paths[role+'_sha256'] = a.sha256
            row = dict(trial_id=actual, wall_seconds=1., **paths)
            write_once(folder/'technical-complete.json', row); rows.append(row)
        return dict(trials=rows, artifacts=[artifact(r[k]).identity_dict() for r in rows for k in ('generated', 'retained', 'last_frame')])
    def upscale(self, root, sources):
        assert self.closed
        self.calls.append('upscale')
        return dict(artifacts=[], trials=[])
    def compose(self, root, name, trial, sources):
        self.calls.append('compose_'+trial)
        root.mkdir(parents=True, exist_ok=True); p = root/(trial+'.mp4'); p.write_bytes(trial.encode())
        return dict(candidate=str(p), candidate_sha256=artifact(p).sha256,
                    artifacts=[artifact(p).identity_dict()], technical=dict(frames=170 if name=='chain' else 93))
    def continuity(self, root, parent, child): return []


def make_plan(tmp_path, fixture):
    native = {'parent': {}, 'child': {}} if fixture == 'chain' else {fixture: {}}
    fixtures = {k: dict(root=str(tmp_path/k), native=native if k==fixture else {}) for k in ('low','high','chain')}
    plan = FinalBenchmarkPlan(1, 'LVA-06', PROFILE, {}, fixtures, TRIALS)
    path = tmp_path/'plan.json'
    write_once(path, dict(plan=plan.identity_dict(), plan_sha256=plan.digest(), limits=dict(wan=16,upscale=1424,compositions=12)))
    return path


def decide(root, state, decision='accepted'):
    from video_ai.experiments.final_local_video_benchmark import FinalBenchmarkSession
    s = FinalBenchmarkSession(root, state['plan_sha256'])
    pending = s.snapshot()['open_reviews'][0]
    p = root/(pending['review_kind']+'-decision.json')
    write_once(p, dict(task_id='LVA-06', kind=pending['review_kind'], decision=decision,
                       media_artifacts=pending['media_artifacts'], user_evidence='offline fake-user decision, not real quality'))
    s.finish_review(artifact(p).identity_dict())


def test_full_chain_gates_new_parent_and_final_cost_and_completed_replay(tmp_path, monkeypatch):
    from video_ai.experiments.final_local_video_execution import run_batch
    path = make_plan(tmp_path, 'chain'); backend = FakeBackend()
    state = run_batch(path, 'chain', backend=backend, allowed_root=tmp_path)
    assert state['pending_review'] == 'parent'; assert backend.calls == ['parent']
    root = tmp_path/'chain'; decide(root, state)
    state = run_batch(path, 'chain', backend=backend, allowed_root=tmp_path)
    assert state['pending_review'] == 'child_continuity'; assert backend.calls == ['parent','child']
    decide(root, state)
    state = run_batch(path, 'chain', backend=backend, allowed_root=tmp_path)
    assert state['pending_review'] == 'final'
    assert state['summary']['batches'][0]['cost_per_usable_video_second'] is None
    assert backend.calls == ['parent','child','upscale', *['compose_'+t for t in TRIALS]]
    pending_replay=run_batch(path,'chain',backend=backend,allowed_root=tmp_path)
    assert pending_replay['pending_review']=='final'
    decide(root, state)
    before = list(backend.calls)
    state = run_batch(path, 'chain', backend=backend, allowed_root=tmp_path)
    assert state['status'] == 'quality_accepted'
    assert state['summary']['batches'][0]['accepted_video_seconds'] == 680/16
    assert backend.calls == before
    from video_ai.experiments.final_local_video_benchmark import load_final_measurement, summarize_final_results
    saved=load_final_measurement(root/'batch-measurement.json')
    assert all(t['quality_accepted'] for t in saved['trials'])
    assert summarize_final_results([saved])['batches'][0]['cost_per_usable_video_second'] is not None


def test_rejected_parent_never_prepares_child(tmp_path):
    from video_ai.experiments.final_local_video_execution import run_batch
    path = make_plan(tmp_path, 'chain'); backend = FakeBackend()
    state = run_batch(path, 'chain', backend=backend, allowed_root=tmp_path)
    decide(tmp_path/'chain', state, 'rejected')
    state = run_batch(path, 'chain', backend=backend, allowed_root=tmp_path)
    assert state['status'] == 'quality_rejected'
    assert backend.calls == ['parent']


def test_drift_completed_stage_rejected_without_reproduction(tmp_path):
    from video_ai.experiments.final_local_video_execution import run_batch
    path = make_plan(tmp_path, 'low'); backend = FakeBackend()
    state = run_batch(path, 'low', backend=backend, allowed_root=tmp_path)
    (tmp_path/'low/native_low/trials/cold_1/retained').write_bytes(b'drift')
    with pytest.raises(ValueError, match='drift'):
        run_batch(path, 'low', backend=backend, allowed_root=tmp_path)
    assert backend.calls == ['low']


def test_real_cpu_compose_checks_all_frames_and_replays_without_commands(tmp_path):
    import wave
    from video_ai.config import load_config
    from video_ai.experiments.upscale_offline import write_png
    from video_ai.experiments.final_local_video_execution import compose_final
    from video_ai.experiments.final_local_video_benchmark import SOURCE
    config=load_config(SOURCE/'config/production.example.json')
    native=tmp_path/'native'; native.mkdir()
    source=native/'source.wav'
    with wave.open(str(source),'wb') as audio:
        audio.setparams((1,2,48000,0,'NONE',''));audio.writeframes(b'\0'*(9000*2))
    from video_ai.runtime.production_state import ArtifactStamp
    timeline=tmp_path/'timeline.json'
    write_once(timeline,dict(clips=[dict(unit_id='u',text='Test',start_sample=0,end_sample=9000,
        samples=9000,pcm=dict(stamp=ArtifactStamp.read(source).to_dict()))],
        subtitles=[dict(start_sample=0,end_sample=9000,text='Test')]))
    write_once(native/'fixture.json',dict(fixture_id='low_motion',budget=dict(start_frame=0,retained_frames=3)))
    write_once(native/'narration-source.json',dict(path=str(timeline),sha256=artifact(timeline).sha256))
    font=Path('C:/Windows/Fonts/msyh.ttc')
    write_once(native/'render-font.json',dict(path=str(font),sha256=artifact(font).sha256))
    work=tmp_path/'work'; folder=work/'postprocess/low_motion_cold_1'; folder.mkdir(parents=True)
    frames=[]
    for i in range(1,4):
        p=folder/'frames'/f'frame_{i:06d}.png';write_png(p,1920,1080,(32*i,96,128))
        frames.append(dict(path=str(p),sha256=artifact(p).sha256))
    write_once(folder/'upscale-complete.json',dict(frames=frames,frame_count=3,width=1920,height=1080))
    plan=dict(assets={k:artifact(config.tools[k]).identity_dict() for k in ('ffmpeg','ffprobe')})
    counters=dict(producer=0,decode=0,probe=0)
    result=compose_final(work,'low','cold_1',[('low',native)],plan,'a'*64,counters)
    assert result['technical']['frames']==3
    assert len(result['frame_rgb_sha256'])==3 and result['pts']==['0','1/16','1/8']
    assert counters['decode']==1
    before=dict(counters)
    assert compose_final(work,'low','cold_1',[('low',native)],plan,'a'*64,counters)==result
    assert counters==before


def test_offline_cli_real_media_and_fake_http_only(tmp_path):
    import json
    import subprocess
    import sys
    from video_ai.experiments.final_local_video_benchmark import SOURCE
    target=tmp_path/'offline.json'
    result=subprocess.run([sys.executable,'-X','utf8',str(SOURCE/'scripts/benchmark_final_local_video.py'),
        '--offline','--output',str(target)],capture_output=True,timeout=120)
    assert result.returncode==0,result.stderr.decode('utf-8',errors='replace')
    report=json.loads(target.read_text('utf-8'))
    assert report['status']=='offline_passed'
    assert report['gpu_executed'] is False
    assert report['network_calls']==0
    assert all(v==0 for v in report['completed_replay_delta'].values())
    assert report['quality']=='simulated_offline_decisions_not_real_acceptance'


def test_batch_counts_persist_across_new_coordinator_instances(tmp_path):
    from video_ai.experiments.final_local_video_execution import run_batch
    class Counted(FakeBackend):
        def __init__(self):super().__init__();self.counters=dict(post=0,producer=0)
        def native(self,*a,**kw):self.counters['post']+=4;return super().native(*a,**kw)
        def upscale(self,*a,**kw):self.counters['post']+=372;return super().upscale(*a,**kw)
        def compose(self,*a,**kw):self.counters['producer']+=1;return super().compose(*a,**kw)
    path=make_plan(tmp_path,'low');state=run_batch(path,'low',backend=Counted(),allowed_root=tmp_path)
    decide(tmp_path/'low',state)
    state=run_batch(path,'low',backend=Counted(),allowed_root=tmp_path)
    assert state['summary']['batches'][0]['counters']==dict(post=376,producer=4)


def test_recovered_batch_preserves_mode_and_native_resources(tmp_path):
    from video_ai.experiments.final_local_video_execution import run_batch
    class Recovered(FakeBackend):
        def native(self,*a,**kw):
            result=super().native(*a,**kw)
            for row in result['trials']:row.update(mode='recovery',wall_seconds=None)
            result['resources']=dict(observed_peak_process_rss_bytes=123)
            return result
    path=make_plan(tmp_path,'low');backend=Recovered()
    state=run_batch(path,'low',backend=backend,allowed_root=tmp_path);decide(tmp_path/'low',state)
    state=run_batch(path,'low',backend=backend,allowed_root=tmp_path)
    batch=state['summary']['batches'][0]
    assert batch['mode']=='recovery'
    assert batch['resources']['low']['observed_peak_process_rss_bytes']==123


def test_real_adapter_validates_copied_native_fixture_before_post(tmp_path):
    from video_ai.experiments.final_local_video_benchmark import FinalExperimentClient
    from video_ai.experiments.final_local_video_execution import RealFinalBackend
    from unit.test_final_local_video_benchmark import client_root
    plan,_,_=client_root(tmp_path)
    root=tmp_path/'native_low';root.mkdir()
    request=tmp_path/'request.json';graph=tmp_path/'graph.json'
    write_once(request,dict(clip_id='low'))
    write_once(graph,{'97':{'inputs':{'image':'start.png'}}})
    expected=dict(input_relative='start.png',input_sha256='a'*64,parameters=dict(width=32))
    source=dict(fixture=expected,request=artifact(request).identity_dict(),graph=artifact(graph).identity_dict())
    plan['fixtures']=dict(low=dict(native=dict(low=source)),high=dict(native={}),chain=dict(native={}))
    sha=digest(plan);write_once(root/'frozen/final-plan.json',plan)
    write_once(root/'experiment.json',dict(port=8189))
    write_once(root/'fixture.json',dict(expected,parameters=dict(width=64)))
    calls=[];client=FinalExperimentClient(root,plan_sha256=sha,http=lambda *a:calls.append(a))
    with pytest.raises(ValueError,match='fixture'):client.submit('warm_1',read_graph(graph))
    assert calls==[]


def read_graph(path):
    import json
    return json.loads(path.read_text('utf-8'))
