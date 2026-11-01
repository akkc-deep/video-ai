"""Explicit local research repair; dot-source scripts/bootstrap.ps1 first."""
import argparse
import json
from pathlib import Path


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for name,option in [('propose','--request'),('review','--review'),('status','--candidate-id')]:
        p=sub.add_parser(name);p.add_argument('--run-dir',required=True);p.add_argument(option,required=name!='status')
    args=parser.parse_args(argv)
    from video_ai.runtime._scene_continuity_io import local
    from video_ai.runtime.manifest import validate_run_dir
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.production_scene_color_repair import propose_scene_color_repair,consume_scene_color_repair_review,SceneColorRepairResult
    from video_ai.runtime.scene_color_repair_records import load_scene_color_repair_progress
    from video_ai.runtime.paths import RuntimePaths
    try:
        run=local(args.run_dir,exists=False);frozen=load_frozen_inputs(validate_run_dir(run))
        if args.command=='status':
            value=load_scene_color_repair_progress(frozen,candidate_id=args.candidate_id)
            print(json.dumps(value,ensure_ascii=False,allow_nan=False));return 0
        paths=RuntimePaths.from_config(frozen.config)
        if args.command=='review':result=consume_scene_color_repair_review(frozen,local(args.review),paths=paths,logger=None)
        else:
            from video_ai.runtime._scene_revision_origins import common
            from video_ai.planning.production_timeline import ProductionTimeline
            prefix=common(frozen)
            result=propose_scene_color_repair(frozen,prefix['units'],ProductionTimeline.from_dict(prefix['timeline']),local(args.request),paths=paths,logger=None)
    except (ValueError,OSError,RuntimeError,KeyError,TypeError,ImportError) as exc:
        result=SceneColorRepairResult(error=dict(kind=type(exc).__name__,message=str(exc),evidence_paths=[]))
    print(json.dumps(result.to_dict(),ensure_ascii=False,allow_nan=False));return result.exit_code


if __name__=='__main__':raise SystemExit(main())
