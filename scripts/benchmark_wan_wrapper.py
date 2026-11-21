"""LVA-07-04 offline tooling; real admission/run require separate LVA-07-05 authorization."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE/'src'))
from video_ai.experiments.wan_fast_profiles import artifact,digest,write_once
from video_ai.experiments.wan_fast_experiment import read
from video_ai.experiments.wan_wrapper_backend import WrapperExperimentClient,WrapperProfile,build_graph,freeze_comparison,prepare

SCRATCH=Path('E:/VideoAI/scratch/benchmarks')


def checked_root(root):
    root=root.resolve()
    if not root.is_relative_to(SCRATCH.resolve()) or root==SCRATCH.resolve():raise ValueError('new experiment under scratch/benchmarks required')
    return root


def init(root,fixture_path,*,port):
    from observe_wan_wrapper_comfy import make_profiles,verify_environment
    root=checked_root(root)
    if root.exists():raise ValueError('new comparison root required')
    fixture=read(fixture_path);image=Path(fixture.pop('input_path')).resolve(strict=True)
    identity=artifact(image)
    fixture.update(input_relative=image.name,input_sha256=identity.sha256,source_image=identity.identity_dict(),
                   source_fixture=artifact(fixture_path).identity_dict())
    profiles=make_profiles();verify_environment()
    root.mkdir(parents=True,exist_ok=False);(root/'input').mkdir()
    shutil.copyfile(image,root/'input'/image.name)
    if artifact(root/'input'/image.name).sha256!=identity.sha256:raise ValueError('input copy identity differs')
    marker=freeze_comparison(root,profiles,fixture,port=port)
    print(json.dumps(dict(root=str(root),comparison_sha256=marker['comparison_sha256'],profiles=marker['profiles'],model_payload_bytes_read=0)))
    return 0


def offline_selftest(root):
    root=checked_root(root);root.mkdir(parents=True,exist_ok=False)
    files=['tests/unit/test_wan_wrapper_backend.py','tests/unit/test_wan_wrapper_media.py',
        'tests/unit/test_wan_wrapper_cli.py','tests/integration/test_wan_wrapper_recovery.py','tests/integration/test_wan_wrapper_worker.py']
    command=[sys.executable,'-X','utf8','-m','pytest',*files,'-q','-p','no:cacheprovider']
    start=time.perf_counter()
    with (root/'pytest.log').open('xb') as output:
        result=subprocess.run(command,cwd=SOURCE,env=dict(os.environ,PYTHONPATH=str(SOURCE/'src')),stdout=output,stderr=subprocess.STDOUT,timeout=180)
    report=dict(task_id='LVA-07-04',passed=result.returncode==0,returncode=result.returncode,command=command,
        seconds=time.perf_counter()-start,source_root=str(SOURCE),graph_posts_to_real_comfy=0,
        full_model_verified=False,gpu_used=False,quality_accepted=False,production_ready=False)
    write_once(root/'results.json',report)
    print(json.dumps(report));return result.returncode


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['init','graph','probe-cpu','offline-selftest','recover','prepare-text','admit-pair','run'])
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--fixture',type=Path)
    parser.add_argument('--mode',choices=['control','fast'],default='control');parser.add_argument('--port',type=int,default=8297)
    parser.add_argument('--authorization',type=Path)
    args=parser.parse_args(argv);root=args.root.resolve();command=args.command
    # Fail before creating clients, importing torch, touching payloads or networking.
    if command in ('run','admit-pair','prepare-text'):
        if args.authorization is None:raise ValueError('separate LVA-07-05 authorization required')
        from video_ai.experiments.wan_wrapper_nodes import WorkerContext
        context=WorkerContext(root,mode='gpu',epoch='client',authorization=read(args.authorization));context.require_gpu()
    if command=='init':
        if not args.fixture:parser.error('init requires a canonical fixture JSON with input_path, positive, negative and fixed seeds')
        return init(root,args.fixture,port=args.port)
    if command=='probe-cpu':
        from observe_wan_wrapper_comfy import controller
        return controller(root,port=args.port)
    if command=='offline-selftest':return offline_selftest(root)
    profile=WrapperProfile.from_dict(read(root/f'frozen/profiles/{args.mode}.json')['profile'])
    prepare(root,profile);fixture=read(root/'fixture.json');graph=build_graph(profile,fixture);trial=args.mode+'_1'
    if command=='graph':
        write_once(root/f'graphs/{args.mode}.json',graph)
        print(json.dumps(dict(mode=args.mode,profile_sha256=profile.digest(),graph_sha256=digest(graph),output=str(root/f'graphs/{args.mode}.json'))));return 0
    if command=='recover' and not (root/'trials'/trial/'intent.json').exists():raise ValueError('original intent missing; unknown, no POST')
    if command=='recover' and profile.identity_dict()['kind']=='experiment':
        from video_ai.experiments.wan_wrapper_backend import read_v1_archive
        print(json.dumps(read_v1_archive(root,args.mode),ensure_ascii=False));return 0
    checked_root(root)
    if profile.identity_dict()['kind']!='experiment':raise ValueError('offline fixture profile forbidden on real network CLI')
    if command=='admit-pair' and args.mode!='fast':raise ValueError('admit-pair requires --mode fast')
    client=WrapperExperimentClient(root,profile_digest=profile.digest(),port=args.port)
    try:
        if command=='prepare-text':result=client.prepare_text()
        elif command=='admit-pair':result=client.admit_pair()
        elif command=='recover':result=client.recover(trial,graph)
        else:result=client.collect(trial,graph)
        print(json.dumps(result,ensure_ascii=False));return 0
    finally:client.close()


if __name__=='__main__':raise SystemExit(main())
