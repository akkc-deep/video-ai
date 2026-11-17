"""LVA-06 offline, prepare, authorized staged run/recovery and read-only summary."""
import argparse
import json
from pathlib import Path
import sys

SOURCE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(SOURCE/'src'),str(SOURCE/'scripts')]
from video_ai.experiments.final_local_video_benchmark import (prepare_final_plan,run_final_batch,
    FinalBenchmarkSession,batch_lock,artifact,read,digest,render_final_markdown,summarize_final_results,load_final_measurement)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--offline',action='store_true');g.add_argument('--prepare-plan',type=Path)
    g.add_argument('--run-batch',choices=('low','high','chain'));g.add_argument('--recover',choices=('low','high','chain'))
    g.add_argument('--record-review',type=Path,metavar='DECISION_JSON');g.add_argument('--summarize',nargs='+',type=Path)
    p.add_argument('--plan',type=Path);p.add_argument('--root',type=Path)
    p.add_argument('--authorize-plan-sha256');p.add_argument('--output',type=Path)
    args=p.parse_args(argv)
    if args.offline:
        from video_ai.experiments.final_local_video_offline import run_offline
        result=run_offline()
    elif args.prepare_plan:result=prepare_final_plan(args.prepare_plan)
    elif args.run_batch or args.recover:
        if not args.plan:p.error('--plan required')
        reviewed=read(args.plan)
        if args.authorize_plan_sha256!=digest(reviewed):p.error('exact specifically authorized manifest SHA required')
        result=run_final_batch(args.plan,args.run_batch or args.recover)
    elif args.record_review:
        if not args.plan or not args.root:p.error('--plan and --root required')
        reviewed=read(args.plan);roots=[Path(v['root']).resolve() for v in reviewed['plan']['fixtures'].values()]
        if args.root.resolve() not in roots:p.error('review root differs from manifest')
        with batch_lock(args.root):
            s=FinalBenchmarkSession(args.root,reviewed['plan_sha256'])
            result=s.finish_review(artifact(args.record_review).identity_dict())
    else:
        # Reading reports has no service, producer or inference side effects.
        inputs=[]
        for path in args.summarize:
            value=read(path)
            if 'trials' in value:inputs.append(load_final_measurement(path))
            elif 'measurement' in value:inputs.append(value['measurement'])
            else:p.error('batch measurement JSON required')
        result=summarize_final_results(inputs)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
        args.output.with_suffix('.md').write_text(render_final_markdown(result),'utf-8')
    print(json.dumps(result,ensure_ascii=False,allow_nan=False),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
