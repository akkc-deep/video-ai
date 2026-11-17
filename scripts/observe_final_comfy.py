"""Bounded LVA-06-only owned Comfy supervisor; never submits a graph."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

SOURCE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(SOURCE/'src'),str(SOURCE/'scripts')]
from video_ai.experiments.final_local_video_benchmark import validate_final_launch, digest, read, write_once
from video_ai.experiments.upscale_manifest import _port_open
from video_ai.runtime.paths import RUNTIME_ROOT
from observe_upscale_comfy import KillOnCloseJob, _memory


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-root',type=Path,required=True)
    parser.add_argument('--profile-sha256',required=True);parser.add_argument('--port',type=int,default=8189)
    parser.add_argument('--max-seconds',type=int,default=14400);parser.add_argument('--worker',action='store_true')
    args=parser.parse_args(argv);root=args.experiment_root.resolve()
    if (not root.is_relative_to((RUNTIME_ROOT/'scratch/benchmarks').resolve())
            or not any(p.name.startswith('LVA-06-') for p in (root,*root.parents))
            or args.port!=8189 or not 30<=args.max_seconds<=14400):
        parser.error('admitted LVA-06 scratch root/port/runtime required')
    plan=validate_final_launch(root,args.profile_sha256,args.port);assets=plan['assets']
    python=Path(assets['comfy_python']['path']);comfy=Path(assets['comfy_main.py']['path']).parent
    if args.worker:
        from observe_local_comfy import worker
        return worker(SimpleNamespace(experiment_root=root,comfy_root=comfy,port=args.port))
    if _port_open(8188) or _port_open(args.port) or (root/'service-owner.json').exists():
        raise ValueError('never replace an existing service')
    for name in ('input','output','temp','user'):(root/name).mkdir(exist_ok=True)
    from video_ai.config import load_config
    from video_ai.runtime.environment import build_child_env
    from video_ai.runtime.paths import RuntimePaths
    config=load_config(Path(assets['configuration']['path']))
    command=[str(python),'-B','-s',str(Path(__file__).resolve()),'--worker','--experiment-root',str(root),
             '--profile-sha256',args.profile_sha256,'--port',str(args.port)]
    started=time.perf_counter();peak=0;samples=0;code=None;timed_out=False
    with (root/'comfy.stdout').open('xb') as stdout,(root/'comfy.stderr').open('xb') as stderr:
        process=subprocess.Popen(command,cwd=comfy,env=build_child_env(RuntimePaths.from_config(config)),
            stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        job=None
        try:
            job=KillOnCloseJob(process)
            from video_ai.runtime.production_state import process_started_at
            write_once(root/'service-owner.json',dict(pid=process.pid,process_started_at=process_started_at(process.pid),
                experiment_root=str(root),port=args.port,parent_pid=os.getpid(),profile_sha256=args.profile_sha256,
                launch_sha256=digest(read(root/'frozen/service-launch.json'))))
            while process.poll() is None:
                memory=_memory(process.pid)
                if memory:peak=max(peak,memory['peak_rss_bytes']);samples+=1
                if time.perf_counter()-started>args.max_seconds:
                    timed_out=True;process.terminate();break
                try:process.wait(timeout=1)
                except subprocess.TimeoutExpired:pass
            code=process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            if job is not None:job.close()
    finalized=False
    path=root/'node-metrics.jsonl'
    if path.exists():
        try:finalized=json.loads(path.read_text('utf-8').splitlines()[-1]).get('finalized') is True
        except (ValueError,IndexError):pass
    write_once(root/'service-result.json',dict(returncode=code,timed_out=timed_out,metrics_finalized=finalized,
        wall_seconds=time.perf_counter()-started,observed_peak_process_rss_bytes=peak if samples else None,
        rss_samples=samples,physical_model_load_count=None))
    return 124 if timed_out else code


if __name__=='__main__':raise SystemExit(main())
