"""Approved LVA-07-06 matrix; original-ID recovery and explicit human gates."""
import argparse
import json
from pathlib import Path
import socket
import sys
import time

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE/'src'));sys.path.insert(0,str(SOURCE/'scripts'))
from video_ai.experiments import wan_wrapper_matrix as matrix
from video_ai.experiments.wan_wrapper_backend import WrapperExperimentClient,prepare
from video_ai.experiments.wan_fast_experiment import read
from video_ai.experiments.wan_fast_profiles import write_once


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['init','seal-child','start-group','stop-group','prepare','run','recover','review','review-final','request-review','report','postprocess','postprocess-worker'])
    parser.add_argument('--root',required=True,type=Path);parser.add_argument('--group',choices=matrix.GROUPS)
    parser.add_argument('--trial',choices=matrix.TRIALS,default='cold_1');parser.add_argument('--authorization',type=Path)
    parser.add_argument('--decision',choices=['accepted','rejected']);parser.add_argument('--evidence')
    parser.add_argument('--scope',choices=['native','final'],default='native');parser.add_argument('--epoch-directory',type=Path)
    args=parser.parse_args(argv);root=args.root.resolve();command=args.command
    if command=='postprocess-worker':
        from video_ai.experiments.wan_wrapper_matrix_observer import postprocess_worker
        return postprocess_worker(root,args.epoch_directory)
    if command=='init':result=matrix.init_matrix(root)
    elif command=='report':
        result=matrix.report(root)
        # A report is replaceable derived data, never an acceptance or intent.
        (root/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    else:
        if not args.group:raise ValueError('explicit group required')
        gr=root/'groups'/args.group
        if command=='seal-child':result=matrix.seal_child(root,args.group)
        elif command=='review':result=matrix.review(root,args.group,args.trial,args.decision,args.evidence or '')
        elif command=='review-final':result=matrix.review_final(root,args.group,args.trial,args.decision,args.evidence or '')
        elif command=='request-review':result=matrix.request_review(root,args.group,args.trial,args.scope)
        elif command=='stop-group':
            owner=read(gr/'service-owner.json');write_once(gr/'stop.request.json',dict(pid=owner['pid'],epoch=owner['epoch']))
            result=dict(stop_requested=True,group=args.group,epoch=owner['epoch'])
        else:
            # Validate actual matrix authorization before importing GPU controller or creating clients.
            authorization=args.authorization or root/'authorization.json'
            auth=read(authorization);marker=matrix.authorize_group(gr,auth)
            profile=matrix.group_profile(gr);prepare(gr,profile)
            if command=='start-group':
                for other in matrix.GROUPS:
                    other_root=root/'groups'/other
                    if (other_root/'service-owner.json').exists() and not (other_root/'service-result.json').exists():
                        raise ValueError('previous owned group must exit before starting another')
                    for path in (other_root/'reviews').glob('*.json'):
                        if read(path).get('decision')=='rejected':raise ValueError('quality rejection stops matrix')
                index=matrix.GROUPS.index(args.group)
                if index:
                    previous=root/'groups'/matrix.GROUPS[index-1]
                    exit_result=read(previous/'service-result.json')
                    if not exit_result.get('passed'):raise ValueError('previous group service failed; stop matrix')
                    for trial in matrix.TRIALS:
                        if not (previous/'trials'/trial/'technical-complete.json').exists():raise ValueError('previous matrix group incomplete')
                if marker['mode']=='fast':matrix.require_fast_review(gr)
                if args.group.startswith('child-'):matrix.require_parent(gr)
                from observe_wan_wrapper_comfy import controller
                return controller(gr,port=marker['port'],max_seconds=0,mode='gpu',authorization=authorization)
            if command=='postprocess':
                from video_ai.experiments.wan_wrapper_matrix_postprocess import postprocess
                result=postprocess(root,args.group,args.trial)
            else:
                graph=matrix.graph(profile,read(gr/'fixture.json'),args.trial)
                if command=='recover' and not (gr/'trials'/args.trial/'intent.json').exists():raise ValueError('original intent missing; no producer or POST')
                client=WrapperExperimentClient(gr,profile_digest=profile.digest(),port=marker['port'])
                try:
                    if command=='prepare':
                        # prepare_text needs control profile even in a fast-only service.
                        client.close();client=WrapperExperimentClient(gr,profile_digest=marker['profiles']['control'],port=marker['port'])
                        for action in ('prepare_text','admit_pair'):
                            if action=='admit_pair':
                                client.close();client=WrapperExperimentClient(gr,profile_digest=marker['profiles']['fast'],port=marker['port'])
                            while True:
                                if (gr/'service-result.json').exists():raise RuntimeError('owned service exited during preparation')
                                try:value=getattr(client,action)()
                                except (TimeoutError,ConnectionError,socket.timeout):value={'status':'unknown'}
                                if value.get('error'):raise RuntimeError(json.dumps(value))
                                if value.get('receipt'):break
                                time.sleep(3)
                        result=value
                    else:
                        start=time.perf_counter();at=matrix.utcnow()
                        if command=='recover':result=client.recover(args.trial,graph)
                        else:result=client.collect(args.trial,graph)
                        if isinstance(result,dict):
                            path=gr/'trials'/args.trial/'invocation.json'
                            if not path.exists():write_once(path,dict(started_at_utc=at,finished_at_utc=matrix.utcnow(),
                                invocation_seconds=time.perf_counter()-start,mode=command))
                            matrix.record_trial_timing(gr,args.trial,command)
                finally:client.close()
    print(json.dumps(result,ensure_ascii=False));return 0


if __name__=='__main__':raise SystemExit(main())
