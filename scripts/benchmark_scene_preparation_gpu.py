"""Authorized LVA-03 phases: original quality, one owned GPU, review gates."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

import benchmark_local_gpu as gpu
from summarize_local_gpu import summarize
from video_ai.runtime.paths import RUNTIME_ROOT
from video_ai.runtime.scene_stage_preparation import PreparationJob,ScenePreparationPool,ScenePhaseMetrics

TRIALS=('cold_1','warm_1','warm_2','warm_3')
SOURCE=Path(__file__).resolve().parents[1]


def persist_diagnostic(path,value,*,original=None):
    try:gpu.write_once(path,value)
    except Exception as exc:
        if original is None:raise
        original.add_note('diagnostic persistence failed: '+type(exc).__name__)


@contextmanager
def observe_gpu_calls():
    """Experiment-local direct counters; no additional HTTP or media calls."""
    original_client,original_media=gpu.ExperimentClient,gpu.media_command
    counts=dict(post=0,get=0,media_commands=0,media_producers=0)
    class CountedClient(original_client):
        def http(self,method,route,payload=None):
            key=method.lower()
            if key in counts:counts[key]+=1
            return super().http(method,route,payload)
    def media(*args,**kwargs):
        counts['media_commands']+=1
        counts['media_producers']+=int(kwargs.get('output') is not None)
        return original_media(*args,**kwargs)
    gpu.ExperimentClient,gpu.media_command=CountedClient,media
    try:yield counts
    finally:gpu.ExperimentClient,gpu.media_command=original_client,original_media


def sampled_idle_evidence(root):
    """Observed device-wide low-util spans, not exact CUDA/kernel idle time."""
    samples=[]
    for line in (Path(root)/'node-metrics.jsonl').read_text(encoding='utf-8').splitlines():
        try:value=json.loads(line)
        except ValueError:continue
        if value.get('kind')=='gpu':
            samples.append((value['offset_seconds'],max(v['utilization_percent'] for v in value['devices'])))
    intervals=[];start=end=None;count=0
    def finish():
        if start is not None:intervals.append(dict(start_seconds=start,end_seconds=end,samples=count))
    for offset,util in samples:
        if util<=5:
            if start is not None and offset-end>6:finish();start=end=None;count=0
            if start is None:start=offset
            end=offset;count+=1
        else:finish();start=end=None;count=0
    finish()
    return dict(threshold_percent=5,max_sample_gap_seconds=6,intervals=intervals,
        observed_idle_span_seconds=sum(v['end_seconds']-v['start_seconds'] for v in intervals),
        physical_model_load_count='未测得物理装载次数',
        scope='Whole phase device samples including startup/technical processing; desktop included. '
              'Only observed spans between adjacent low-util samples, not exact GPU idle or transfer count.')


def job_for(root,fixture,index):
    image=root/'input'/fixture['input_relative']
    raw=(root/'frozen/original-graph.json').read_bytes()
    # Independent repeats are distinct first-clip namespaces; the original
    # production clip ID remains in fixture.json, never rewritten in evidence.
    return PreparationJob(clip_id=f'scene_{index+1:04d}_clip_0001',
        source=dict(path=str(image),bytes=image.stat().st_size,sha256=fixture['input_sha256']),
        parameters_sha256=gpu.digest(fixture['parameters']),
        workflow_sha256=fixture['source_graph_sha256'],graph_bytes=raw,parent_required=False)


def run_independent_trials(root,*,candidate,port=8189):
    root=Path(root);fixture=gpu.read(root/'fixture.json')
    pool=ScenePreparationPool(enabled=candidate); metrics=ScenePhaseMetrics(); results=[]
    metrics.event('phase_enter'); started=time.perf_counter(); error=None
    try:
        for index,trial in enumerate(TRIALS):
            prepared=None
            if candidate and index:
                job=job_for(root,fixture,index)
                value=pool.take(job)
                if value is not None and value.error is None:
                    # run_trial still verifies source SHA and frozen graph digest.
                    prepared=deepcopy(json.loads(value.graph_bytes))
                    metrics.event('prepare_consumed',clip_id=job.clip_id,seconds=value.read_seconds)
                else:
                    pool.discard(); metrics.event('prepare_discarded',clip_id=job.clip_id)
                del value  # Release the full consumed source before the next job.
            if candidate and index+1<len(TRIALS):
                job=job_for(root,fixture,index+1)
                if pool.submit(job):metrics.event('prepare_queued',clip_id=job.clip_id)
            metrics.event('tracking_enter')
            before=time.perf_counter()
            result=gpu.run_trial(root,trial,port=port,prepared_original_graph=prepared)
            metrics.event('tracking_exit',seconds=time.perf_counter()-before)
            results.append(result)
    except BaseException as exc:
        error=type(exc).__name__;raise
    finally:
        pool.close();metrics.event('phase_exit')
        report=dict(candidate=candidate,wall_seconds=time.perf_counter()-started,
                    metrics=metrics.report(),preparation=pool.report(),exception_type=error,
                    completed_trials=[v.get('trial_id') for v in results],
                    scope='Repeated independent first clips; adapted LVA-01 input pre-read, no media receipt reuse.')
        persist_diagnostic(root/'preparation-phase.json',report,original=sys.exception())
    return report


def port_open(port):
    with socket.socket() as connection:
        connection.settimeout(.5)
        return connection.connect_ex(('127.0.0.1',port))==0


def request_stop(root):
    owner=gpu.read(root/'service-owner.json')
    gpu.write_once(root/'stop.request.json',dict(pid=owner['pid']))


def close_owned_service(service,root,*,original=None):
    failures=[]
    try:request_stop(root)
    except Exception as exc:failures.append(('stop request',exc))
    try:
        try:service.wait(timeout=20)
        except subprocess.TimeoutExpired:
            from video_ai.runtime.production_state import process_started_at
            import os,signal
            owner=gpu.read(root/'service-owner.json')
            if process_started_at(owner['pid'])==owner['process_started_at']:
                os.kill(owner['pid'],signal.SIGTERM)
            service.wait(timeout=20)
    except Exception as exc:failures.append(('owned shutdown',exc))
    if failures:
        target=original or failures[0][1]
        for stage,exc in failures:target.add_note(stage+' failed: '+type(exc).__name__)
        if original is None:raise target


def require_parent_reviews(parent_root):
    parent_root=Path(parent_root)
    for trial in TRIALS:
        directory=parent_root/'trials'/trial
        approval=directory/'observation-accepted.json'
        if not approval.is_file():raise ValueError('new parent human acceptance required before child service')
        accepted=gpu.read(approval);result=gpu.read(directory/'technical-complete.json')
        if (accepted.get('decision')!='accepted' or any(accepted.get(k+'_sha256')!=result[k+'_sha256']
                for k in ('generated','retained','last_frame'))):
            raise ValueError('new parent human acceptance binding differs')


def prepare_phase_inputs(root,source_folder,fixture_id,*,parent_root=None):
    if parent_root is None:return gpu.prepare(root,source_folder,fixture_id)
    # The established child runner consumes the sealed child definition from
    # parent_root, then admits it into its fresh service root itself. Preserve
    # the parent's original fixture and avoid an incompatible prefilled root.
    return gpu.prepare_child(parent_root,source_folder)


def recover_completed_trials(root,*,parent_root=None,port=8189):
    for trial in TRIALS:
        if parent_root is None:gpu.run_trial(root,trial,port=port)
        else:gpu.run_child_trial(root,trial,port=port,parent_root=parent_root)


def run_phase(root,source_folder,fixture_id,*,candidate,port=8189,parent_root=None):
    root=Path(root).resolve()
    if not root.name.startswith('LVA-03-') or not root.is_relative_to((RUNTIME_ROOT/'scratch/benchmarks').resolve()):
        raise ValueError('new LVA-03 scratch experiment required')
    if root.exists() or port_open(port) or port_open(8188):
        raise ValueError('new root and no existing Comfy listener required')
    if parent_root is not None:
        parent_root=Path(parent_root).resolve()
        if not parent_root.is_relative_to((RUNTIME_ROOT/'scratch/benchmarks').resolve()):
            raise ValueError('parent must be a new scratch experiment')
        require_parent_reviews(parent_root)
        prepare_phase_inputs(root,source_folder,fixture_id,parent_root=parent_root)
    output=root.parent/(root.name+'.launcher.log')
    started=time.perf_counter();service=None;failure=None;trial_report=None
    command=[sys.executable,'-X','utf8',str(SOURCE/'scripts/observe_local_comfy.py'),
             '--experiment-root',str(root),'--port',str(port),'--max-seconds','3600']
    with output.open('xb') as logs,observe_gpu_calls() as counts:
        service=subprocess.Popen(command,cwd=SOURCE,stdout=logs,stderr=subprocess.STDOUT,
                                 creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            until=time.monotonic()+180
            while time.monotonic()<until:
                if service.poll() is not None:raise RuntimeError('owned launcher exited during startup')
                if (root/'service-owner.json').exists() and port_open(port):
                    try:
                        client=gpu.ExperimentClient(root,port=port)
                        stats=client._http('GET','/system_stats');client.assert_owned_service()
                        gpu.write_once(root/'system-stats.json',stats);break
                    except OSError:pass
                time.sleep(1)
            else:raise TimeoutError('owned service startup timed out')
            gpu.write_once(root/'LVA-03-authorization.json',dict(task_id='LVA-03',candidate=candidate,
                authorization='User explicitly authorized this local GPU comparison; old production remains paused.'))
            if parent_root is None:prepare_phase_inputs(root,source_folder,fixture_id)
            before_counts=dict(counts)
            if parent_root is None:
                trial_report=run_independent_trials(root,candidate=candidate,port=port)
            else:
                before=time.perf_counter();results=[]
                for trial in TRIALS:results.append(gpu.run_child_trial(root,trial,port=port,parent_root=parent_root))
                trial_report=dict(candidate=candidate,wall_seconds=time.perf_counter()-before,
                    completed_trials=[v['trial_id'] for v in results],
                    preparation=dict(submitted=0,consumed=0,peak_jobs=0),
                    scope='Child chain serial; no parent/tail prefetch and no service retained through review.')
                gpu.write_once(root/'preparation-phase.json',trial_report)
            normal_counts={k:counts[k]-before_counts[k] for k in counts}
            before_counts=dict(counts);recovery_started=time.perf_counter()
            # Child recovery keeps the accepted-parent binding, while completed
            # media returns before constructing a client or media producer.
            recover_completed_trials(root,parent_root=parent_root,port=port)
            recovery_counts={k:counts[k]-before_counts[k] for k in counts}
            if any(recovery_counts.values()):raise RuntimeError('completed recovery repeated HTTP/media work')
            gpu.write_once(root/'LVA-03-direct-counts.json',dict(normal=normal_counts,recovery=recovery_counts,
                recovery_wall_seconds=time.perf_counter()-recovery_started,
                basis='Direct experiment-local method interception, no added HTTP/media calls.'))
        except BaseException as exc:
            failure=type(exc).__name__;raise
        finally:
            original=sys.exception();cleanup=None
            try:close_owned_service(service,root,original=original)
            except Exception as exc:cleanup=exc
            persist_diagnostic(root/'LVA-03-service-phase.json',dict(start_count=1,
                close_count=int(service.poll() is not None),
                launcher_exit_code=service.returncode,wall_seconds=time.perf_counter()-started,
                exception_type=failure,closed_before_review=service.poll() is not None,trial_report=trial_report),
                original=original or cleanup)
            if cleanup is not None:raise cleanup
    gpu.write_once(root/'summary.json',summarize(root))
    gpu.write_once(root/'LVA-03-idle-evidence.json',sampled_idle_evidence(root))
    return root


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--source-folder',type=Path,required=True)
    parser.add_argument('--fixture-id',choices=('low_motion','high_motion','parent_child'),required=True)
    parser.add_argument('--candidate',action='store_true')
    parser.add_argument('--parent-root',type=Path)
    args=parser.parse_args(argv)
    print(run_phase(args.root,args.source_folder,args.fixture_id,candidate=args.candidate,
                    parent_root=args.parent_root),flush=True)


if __name__=='__main__':main()
