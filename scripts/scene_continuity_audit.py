"""Explicit local scene continuity analysis/reassessment/status; bootstrap required."""
import argparse
import json
from pathlib import Path

from video_ai.runtime.paths import RuntimePaths
from video_ai.runtime.manifest import validate_run_dir
from video_ai.runtime.production_inputs import load_frozen_inputs
from video_ai.runtime.scene_continuity_records import load_scene_continuity_progress
from video_ai.runtime.production_scene_continuity import analyze_scene_continuity,reassess_scene_continuity
from video_ai.runtime._scene_revision_origins import common
from video_ai.planning.production_timeline import ProductionTimeline


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('analyze','reassess','status'):
        p=sub.add_parser(name);p.add_argument('--run-dir',required=True)
        if name!='status':p.add_argument('--request',required=True)
    args=parser.parse_args(argv)
    try:
        frozen=load_frozen_inputs(validate_run_dir(Path(args.run_dir)))
        prefix=common(frozen);units=prefix['units'];timeline=ProductionTimeline.from_dict(prefix['timeline'])
        if args.command=='status':
            result=load_scene_continuity_progress(frozen,units,timeline)
            print(json.dumps(result,ensure_ascii=False,allow_nan=False));return 0 if result['ready'] else 3
        operation=analyze_scene_continuity if args.command=='analyze' else reassess_scene_continuity
        result=operation(frozen,units,timeline,Path(args.request),paths=RuntimePaths.from_config(frozen.config),logger=None)
        print(json.dumps(result.to_dict(),ensure_ascii=False,allow_nan=False));return result.exit_code
    except (ValueError,OSError,RuntimeError,KeyError,ImportError) as exc:
        print(json.dumps(dict(status='blocked',error=str(exc)),ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
