"""Explicit bounded four-request stationary pilot; bootstrap first."""
import argparse
import json
from pathlib import Path

from video_ai.experiments.natural_pilot import freeze_pilot, load_pilot
from video_ai.experiments.natural_pilot_runtime import (acquire_pilot_case,prepare_pilot_case,pilot_status,
    export_pilot_portal,record_pilot_observation)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    for name in ('freeze','acquire','prepare','status','portal','observe'):
        command=commands.add_parser(name);command.add_argument('--root',type=Path,required=True)
        if name=='freeze': command.add_argument('--config',type=Path,required=True)
        if name in ('acquire','prepare'): command.add_argument('--case',required=True)
        if name=='observe': command.add_argument('--observation',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='freeze':
            plan=freeze_pilot(args.root,args.config)
            result=dict(status='pilot_frozen',cases=len(plan['cases']),max_requests=4,ready_for_propose=False)
        elif args.command=='status': result=pilot_status(args.root)
        elif args.command=='portal': result=export_pilot_portal(args.root)
        elif args.command=='observe': result=record_pilot_observation(args.root,args.observation)
        else:
            plan=load_pilot(args.root);ids=[c['case_id'] for c in plan['cases']] if args.case=='all' else [args.case]
            operation=acquire_pilot_case if args.command=='acquire' else prepare_pilot_case
            completed=[]
            for cid in ids:
                row=operation(args.root,cid);completed.append(cid)
                print(json.dumps(dict(case_id=cid,status=row['status']),ensure_ascii=False),flush=True)
            result=dict(status='pilot_acquisition_complete' if args.command=='acquire' else 'pilot_technical_import_complete',
                cases=completed,ready_for_propose=False)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False));return 0
    except KeyboardInterrupt:
        print(json.dumps(dict(status='interrupted',ready_for_propose=False)));return 130
    except (ValueError,OSError,RuntimeError,KeyError,TypeError,ImportError) as error:
        print(json.dumps(dict(status='blocked',ready_for_propose=False,error=dict(kind=type(error).__name__,message=str(error))),ensure_ascii=False));return 2


if __name__=='__main__': raise SystemExit(main())
