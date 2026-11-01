"""Explicit offline natural qualification stages; never invokes a model."""
import argparse
import json
from video_ai.runtime import natural_study as s
from video_ai.runtime.natural_study_records import StudyReader,check_inputs


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for name in ('check-inputs','freeze','measure','seal','evaluate','finalize','status'):
        c=sub.add_parser(name)
        if name in ('check-inputs','freeze'): c.add_argument('--request',required=True)
        if name!='check-inputs': c.add_argument('--root',required=name!='freeze')
        if name=='finalize': c.add_argument('--observations')
    a=p.parse_args(argv)
    try:
        if a.command=='check-inputs': result=check_inputs(StudyReader().any(a.request),require_complete=False)
        elif a.command=='freeze': result=s.freeze(a.request,root=a.root)
        elif a.command=='finalize': result=s.finalize(a.root,observations=a.observations)
        else: result=getattr(s,a.command)(a.root)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return 3 if result.get('status')=='unqualified' else 0
    except (ValueError,OSError,RuntimeError,KeyError,TypeError,ImportError) as e:
        print(json.dumps(dict(status='refused',error=dict(kind=type(e).__name__,message=str(e))),ensure_ascii=False));return 2
    except KeyboardInterrupt: print(json.dumps(dict(status='interrupted',ready_for_propose=False)));return 130


if __name__=='__main__': raise SystemExit(main())
