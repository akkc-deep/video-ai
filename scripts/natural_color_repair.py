"""Explicit local natural research candidate commands; no production admission."""
import argparse
import json
from video_ai.runtime import production_natural_repair as r


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('propose');c.add_argument('--request',required=True)
    for name in ('review','status','assess'):
        c=sub.add_parser(name);c.add_argument('--run-dir',required=True)
        if name!='assess': c.add_argument('--candidate-id',required=True)
        if name=='review': c.add_argument('--observation',required=True)
        if name=='assess': c.add_argument('--observations',nargs='*',default=[]);c.add_argument('--natural-profile')
    a=p.parse_args(argv)
    try:
        if a.command=='propose': value=r.propose(a.request)
        elif a.command=='review': value=r.review(a.run_dir,a.candidate_id,a.observation)
        elif a.command=='status': value=r.status(a.run_dir,a.candidate_id)
        else: value=r.assess(a.run_dir,observations=a.observations,natural_profile=a.natural_profile)
        print(json.dumps(value,ensure_ascii=False,allow_nan=False))
        return 3 if value['status'].startswith('awaiting_') else 0
    except (ValueError,RuntimeError,OSError,KeyError,TypeError,ImportError) as e:
        print(json.dumps(dict(status='refused',error=dict(kind=type(e).__name__,message=str(e))),ensure_ascii=False));return 2
    except KeyboardInterrupt: print(json.dumps(dict(status='interrupted',ready_for_propose=False)));return 130


if __name__=='__main__': raise SystemExit(main())
