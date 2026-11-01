"""Explicit isolated experiment commands; never runs on import."""
import argparse
import json
from pathlib import Path

from video_ai.experiments.whole_scene_case import prepare_case, read_json
from video_ai.experiments.whole_scene_runner import execute_case
from video_ai.experiments.whole_scene_media import audit_output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare')
    p.add_argument('--source-run',required=True,type=Path)
    p.add_argument('--scene-id',required=True)
    p.add_argument('--contract',required=True,type=Path)
    p.add_argument('--root',required=True,type=Path)
    for name in ('execute','audit','status'):
        p=sub.add_parser(name);p.add_argument('--root',required=True,type=Path)
    args=parser.parse_args()
    if args.command=='prepare':
        value=prepare_case(args.source_run,args.scene_id,args.contract,args.root)
        print(json.dumps(dict(status='prepared',root=str(args.root),budget=value['budget']),ensure_ascii=False))
    elif args.command=='execute':
        value=execute_case(args.root)
        print(json.dumps(value,ensure_ascii=False))
        return 0 if value['status']=='awaiting_video_observation' else 2
    elif args.command=='audit':
        value=audit_output(args.root,read_json(args.root/'submission-result.json')['output'])
        print(json.dumps(value,ensure_ascii=False))
    else:
        for name in ('result.json','submission-result.json','intent.json','prepared.json'):
            if (args.root/name).exists():
                print(json.dumps(read_json(args.root/name),ensure_ascii=False));break
    return 0


if __name__=='__main__': raise SystemExit(main())
