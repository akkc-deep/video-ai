"""Measure only the offline admission fixture, in independent Python processes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    if not 1<=args.repeats<=5: parser.error('repeats must be 1..5')
    repo=Path(__file__).resolve().parents[1]
    baseline=args.baseline_dir.resolve(strict=True);output=args.output.resolve()
    if output.is_relative_to(Path('E:/VideoAI/work')): parser.error('report must be outside production work')
    output.parent.mkdir(parents=True,exist_ok=True)
    report={'fixture':'six pending synthetic clips, two accepted clips, three source layers and shared ancestor DAG',
            'scope':'Only test runtime writes. No network, model service, video inference or decoding/rendering.',
            'metric_notes':'Both versions share the same whole_input_protection window, matching the existing public review API. Cold preparation includes protection/batch entry and starts at progress/source admission, after synthetic fixture assembly (application admission cold, not OS cache cold); first receive and warm batch include synchronous raw/receipt persistence; final_boundary includes batch exit proof checks and protection cleanup. Leaf media/plan semantics are stubbed. hash_reads/hashed_input_bytes count application SHA input reads, not physical disk I/O. Timings are not production projections.',
            'baseline_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(baseline.glob('*.py'))},
            'optimized_sha256':{str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (repo/'src/video_ai/runtime'/name for name in
                    ('_continuity_byte_guard.py','scene_revision_records.py','image_selection_records.py',
                     '_scene_revision_readers.py','_scene_revision_origins.py','reference_image_records.py',
                     'scene_clip_records.py','scene_comfy_transactions.py','production_scene_clips.py',
                     '_scene_review_batch.py','scene_review_control.py'))},
            'runs':{},'summary':{}}
    for mode in ('baseline','optimized'):
        runs=[]
        for i in range(args.repeats):
            raw=output.with_name(output.stem+f'-{mode}-{i+1}.json')
            env=dict(os.environ,PYTHONPATH=os.pathsep.join((str(repo/'src'),str(repo/'tests'))),
                     REVIEW_ADMISSION_BENCHMARK=str(raw))
            env.pop('REVIEW_ADMISSION_BASELINE_DIR',None)
            if mode=='baseline': env['REVIEW_ADMISSION_BASELINE_DIR']=str(baseline)
            command=[sys.executable,'-m','pytest','tests/unit/test_review_admission_optimization.py::test_fixture_measurement',
                     '-q','-p','no:cacheprovider']
            result=subprocess.run(command,cwd=repo,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            if result.returncode:
                print(result.stdout)
                raise SystemExit(result.returncode)
            runs.append(json.loads(raw.read_text(encoding='utf-8')))
        report['runs'][mode]=runs
        report['summary'][mode]={}
        for stage in runs[0]['stages']:
            values=[run['stages'][stage] for run in runs]
            calls=values[0]['calls']
            if any(row['calls']!=calls for row in values): raise RuntimeError('fixture call counts varied')
            seconds=[row['seconds'] for row in values]
            report['summary'][mode][stage]=dict(median_seconds=statistics.median(seconds),
                min_seconds=min(seconds),max_seconds=max(seconds),calls=calls)
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report['summary'],indent=2))


if __name__=='__main__': main()
