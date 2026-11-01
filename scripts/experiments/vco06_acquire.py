"""Preregister and acquire independent real native Wan inputs; bootstrap first."""
import argparse
import json
from pathlib import Path

from video_ai.experiments.natural_acquisition import freeze_collection, load_collection
from video_ai.experiments.natural_acquisition_runtime import acquire_case, prepare_case, collection_status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    for name in ('freeze','acquire','prepare','status','portal','observe'):
        command = commands.add_parser(name)
        command.add_argument('--root',type=Path,required=True)
        if name == 'freeze':
            command.add_argument('--config',type=Path,required=True)
        elif name == 'observe':
            command.add_argument('--observation',type=Path,required=True)
        elif name in ('acquire','prepare'):
            command.add_argument('--case',required=True,help='Exact frozen case ID or all (serial; stops on error)')
    args = parser.parse_args(argv)
    try:
        if args.command == 'freeze':
            plan = freeze_collection(args.root,args.config)
            result = dict(status='collection_plan_frozen',cases=len(plan['cases']),root=str(args.root),ready_for_propose=False)
        elif args.command == 'status':
            result = collection_status(args.root)
        elif args.command == 'portal':
            from video_ai.experiments.natural_acquisition_observation import export_portal
            result = export_portal(args.root)
        elif args.command == 'observe':
            from video_ai.experiments.natural_acquisition_observation import record_observation
            result = record_observation(args.root,args.observation)
        else:
            cases = load_collection(args.root)['cases']
            selected = [c['case_id'] for c in cases] if args.case == 'all' else [args.case]
            operation = acquire_case if args.command == 'acquire' else prepare_case
            completed = []
            for case_id in selected:
                print(json.dumps(dict(event='case_start',case_id=case_id,operation=args.command)),flush=True)
                row = operation(args.root,case_id)
                completed.append(case_id)
                print(json.dumps(dict(event='case_done',case_id=case_id,status=row['status'])),flush=True)
            result = dict(status='acquisition_complete' if args.command=='acquire' else 'technical_import_complete',
                cases=completed,ready_for_propose=False)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return 0
    except KeyboardInterrupt:
        print(json.dumps(dict(status='interrupted',ready_for_propose=False)))
        return 130
    except (ValueError,OSError,RuntimeError,KeyError,TypeError,ImportError) as exc:
        print(json.dumps(dict(status='blocked',ready_for_propose=False,
            error=dict(kind=type(exc).__name__,message=str(exc))),ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
