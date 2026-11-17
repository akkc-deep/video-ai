"""LVA-05 isolated CPU/GPU benchmark. Real GPU requires a reviewed plan."""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE/'src'))
from video_ai.experiments.upscale_experiment import FACTORS, baseline_api, freeze_manifest, read, run_frames
from video_ai.experiments.wan_fast_profiles import Artifact, artifact, digest


def offline(output,repeats):
    from video_ai.experiments.upscale_offline import offline_manifest, OfflineTransport
    api=baseline_api();output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    scratch=output.parent/('LVA-05-offline-'+uuid4().hex[:10]);rows=[];reference=None
    for repeat in range(repeats):
        for factor in FACTORS:
            root=scratch/f'{repeat}-{factor}'
            manifest=offline_manifest(root,factor);profile=freeze_manifest(root,manifest)
            transport=OfflineTransport(root);result=run_frames(root,profile_sha256=profile,http=transport)
            posts=sum(method=='POST' for method,_ in transport.calls)
            transport.calls.clear()
            def no_decode(*a,**kw):raise AssertionError('completed replay decoded again')
            resumed=run_frames(root,profile_sha256=profile,http=transport,pixel_proof=no_decode)
            if transport.calls or resumed!=result or posts!=3:raise AssertionError('completed recovery contract')
            pixels=result['frame_rgb_sha256']
            if reference is None:reference=pixels
            if reference!=pixels:raise AssertionError('I/O factor changed full RGB pixels')
            rows.append(dict(repeat=repeat,factor=factor,wall_seconds=result['wall_seconds'],
                frame_count=result['frame_count'],frame_rgb_sha256=pixels,pipeline=result['pipeline'],
                normal_posts=posts,replay_http_calls=0,replay_decodes=0,root=str(root)))
    report=dict(task_id='LVA-05',status='offline_passed',gpu_executed=False,
        scope='Synthetic PNG/fake HTTP; complete real PNG/FFmpeg pixel proofs, not model speedup.',
        repeats=repeats,rows=rows,default_factor='serial',physical_model_loads=None)
    api.write_once(output,report);return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline',action='store_true');parser.add_argument('--output',type=Path)
    parser.add_argument('--repeats',type=int,default=4)
    parser.add_argument('--prepare-plan',type=Path)
    parser.add_argument('--plan',type=Path);parser.add_argument('--phase')
    parser.add_argument('--gpu-authorized',action='store_true')
    args=parser.parse_args(argv)
    if args.offline:
        if not args.output or not 1<=args.repeats<=4:parser.error('offline requires output and repeats 1..4')
        report=offline(args.output,args.repeats)
    elif args.prepare_plan:
        from video_ai.experiments.upscale_manifest import prepare_plan
        report=prepare_plan(args.prepare_plan)
    else:
        if not args.gpu_authorized or not args.plan or not args.phase:
            parser.error('real phase requires exact --plan --phase and explicit --gpu-authorized')
        from video_ai.experiments.upscale_manifest import run_phase
        report=run_phase(args.plan,args.phase)
    print(json.dumps(dict(status=report.get('status'),task_id='LVA-05',gpu_executed=report.get('gpu_executed',False)),ensure_ascii=False))


if __name__=='__main__':main()
