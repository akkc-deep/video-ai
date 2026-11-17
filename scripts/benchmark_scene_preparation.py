"""LVA-03 offline serial/prefetch pairs: real FFmpeg, no GPU/network."""
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import platform
import socket
import subprocess
import sys
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from benchmark_scene_validation import production_pair, enrich_existing_evidence
from scene_validation_helpers import isolated_config
from video_ai.config import load_config
from video_ai.runtime.manifest import hash_file
from video_ai.runtime.paths import RUNTIME_ROOT, RuntimePaths
from video_ai.runtime.storage import test_runtime_scope
from video_ai.runtime.scene_stage_preparation import candidate_scene_preparation


def pair(paths,config,*,candidate,observed,repeat):
    with candidate_scene_preparation() if candidate else nullcontext():
        rows=production_pair(paths,config,reuse=False,observed=observed,repeat=repeat)
    run=Path(rows[0]['fixture_run'])
    reports=sorted((run/'logs/production/scene-clips/performance').glob('*.json'),
                   key=lambda p:p.stat().st_mtime_ns)
    if len(reports)!=2: raise RuntimeError('missing phase diagnostics')
    for row,path in zip(rows,reports):
        phase=json.loads(path.read_bytes()); row.update(candidate=candidate,phase=phase,phase_report=str(path))
        row['service_start_count']=phase['counts'].get('actual_start',0)
        row['service_close_count']=phase['counts'].get('close',0)
        if row['mode']=='recovery':
            if row['post_count'] or row['counts']['producer_invocations'] or row['service_start_count']:
                raise RuntimeError('completed recovery repeated work')
        elif row['service_start_count']!=1 or row['service_close_count']!=1:
            raise RuntimeError('phase did not start/close exactly once')
        if phase['preparation']['peak_jobs']>1 or phase['preparation']['peak_bytes']>96*1024*1024:
            raise RuntimeError('preparation exceeded resource budget')
    return rows


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repeats',type=int,default=4)
    args=parser.parse_args(argv); output=args.output.resolve()
    root=(RUNTIME_ROOT/'scratch/benchmarks').resolve()
    if (not output.is_relative_to(root) or not output.name.startswith('LVA-03-')
            or output.suffix!='.json' or args.repeats<1):
        parser.error('new scratch/benchmarks/LVA-03-*.json and positive repeats required')
    if output.exists() or output.with_suffix('.md').exists(): parser.error('report already exists')
    fixture=root/('LVA-03-'+uuid4().hex[:8]); fixture.mkdir(parents=True,exist_ok=False)
    base=load_config(Path(__file__).resolve().parents[1]/'config/production.example.json')
    results=[]
    with test_runtime_scope(fixture):
        config=isolated_config(base,fixture/'shared'); paths=RuntimePaths.from_config(config)
        allowed={p.resolve() for k,p in config.tools.items() if k in ('ffmpeg','ffprobe')}
        original=subprocess.Popen
        def media_only(command,*a,**kw):
            if Path(command[0]).resolve() not in allowed: raise RuntimeError('offline executable denied')
            return original(command,*a,**kw)
        def offline(*a,**kw): raise RuntimeError('offline network denied')
        with (patch.object(subprocess,'Popen',media_only),patch.object(socket.socket,'connect',offline),
              patch.object(socket.socket,'connect_ex',offline),patch.object(socket,'create_connection',offline)):
            for repeat in range(args.repeats):
                for candidate in ((False,True) if repeat%2==0 else (True,False)):
                    results.extend(pair(paths,config,candidate=candidate,observed=False,repeat=repeat))
                    print(f'wall pair {repeat+1}/{args.repeats} candidate={candidate}',flush=True)
            for candidate in (False,True):
                results.extend(pair(paths,config,candidate=candidate,observed=True,repeat=0))
                print(f'diagnostics candidate={candidate}',flush=True)
        tools={k:hash_file(config.tools[k]).sha256 for k in ('ffmpeg','ffprobe')}
    report=dict(schema_version=1,kind='offline_scene_preparation',fixture_root=str(fixture),
        environment=dict(python=platform.python_version(),tool_sha256=tools),results=results,
        summary={},gpu_runs=0,network_connections=0,original_production_runs_modified=0,
        limitations=['Source pre-read is CPU I/O, not GPU throughput or a media proof.',
            'OS cache and concurrent system load uncontrolled; full profiler sampled separately.',
            'LVA-02 helper/config reused with strict validation, candidate LVA-02 disabled.',
            'GPU and human quality acceptance are separate evidence.'])
    enrich_existing_evidence(report)
    for mode in ('normal','recovery'):
        report['summary'][mode]={}
        for candidate,label in ((False,'baseline'),(True,'candidate')):
            rows=[r for r in results if r['mode']==mode and r['candidate']==candidate and not r['observed']]
            report['summary'][mode][label]=dict(samples=len(rows),
                wall_mean_seconds=sum(r['wall_seconds'] for r in rows)/len(rows),
                producer_counts=[r['direct_producer_invocations'] for r in rows],
                post_counts=[r['post_count'] for r in rows])
    if len({tuple(v['source']['sha256'] for v in r['media']) for r in results})!=1:
        raise RuntimeError('paired source media differs')
    report['paired_media_sha_equal']=True
    with output.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    lines=['# LVA-03 Offline Preparation Benchmark','','| Mode | Baseline mean s | Candidate mean s |',
           '| --- | ---: | ---: |']
    for mode,p in report['summary'].items():
        lines.append(f'| {mode} | {p["baseline"]["wall_mean_seconds"]:.6f} | {p["candidate"]["wall_mean_seconds"]:.6f} |')
    output.with_suffix('.md').write_text('\n'.join(lines+['',*report['limitations']])+'\n',encoding='utf-8')
    print(output,flush=True)


if __name__=='__main__':main()
