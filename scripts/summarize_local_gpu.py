"""Read-only LVA-01 native trial aggregation; no service, model or media calls."""
import argparse
import json
import math
from pathlib import Path

from video_ai.runtime.paths import RUNTIME_ROOT


def percentile(values,p):
    if not values:return None
    ordered=sorted(values);position=(len(ordered)-1)*p
    lo,hi=math.floor(position),math.ceil(position)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(position-lo)


def summarize(root):
    root=Path(root);fixture=json.loads((root/'fixture.json').read_text(encoding='utf-8'))
    events=[];errors=0;session=None
    with (root/'node-metrics.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            try:value=json.loads(line)
            except ValueError:errors+=1;continue
            if value.get('kind')=='session':session=value
            elif value.get('kind') in ('node','model','gpu'):events.append(value)
    trials=[]
    for path in sorted((root/'trials').glob('*/technical-complete.json')):
        result=json.loads(path.read_text(encoding='utf-8'))
        pid=result['prompt_id'];stage={};model_calls={}
        for event in events:
            if event.get('prompt_id')!=pid:continue
            if event['kind']=='node':stage[event['stage']]=stage.get(event['stage'],0)+event['seconds']
            elif event['kind']=='model':model_calls[event['stage']]=model_calls.get(event['stage'],0)+1
        gpu=[]
        if session and result.get('submit_to_output_seconds') is not None:
            begin=result['started_at_unix']-session['started_at_unix'];end=begin+result['submit_to_output_seconds']
            for event in events:
                if event['kind']=='gpu' and begin<=event['offset_seconds']<=end:gpu.extend(event['devices'])
        approval=path.parent/'observation-accepted.json';quality='unverified'
        if approval.exists():
            verdict=json.loads(approval.read_text(encoding='utf-8'))
            if verdict.get('decision')=='accepted' and all(verdict.get(k+'_sha256')==result[k+'_sha256'] for k in ('generated','retained','last_frame')):
                quality='accepted'
        if (path.parent/'observation-rejected.json').exists():quality='rejected'
        trials.append(dict(trial_id=result['trial_id'],prompt_id=pid,mode=result.get('mode','normal'),
            temperature=result['temperature'],frames=result['retained_frames'],
            submit_to_output_seconds=result.get('submit_to_output_seconds'),wall_seconds=result.get('wall_seconds'),
            technical_seconds=result['technical_seconds'],stage_wall_seconds=stage,model_method_calls=model_calls,
            device_sampled_peak_vram_mib=max((v['used_mib'] for v in gpu),default=None),
            device_mean_gpu_utilization_percent=sum(v['utilization_percent'] for v in gpu)/len(gpu) if gpu else None,
            gpu_samples=len(gpu),retained_sha256=result['retained_sha256'],
            retained=result['retained'],quality=quality,
            usable_video_seconds=result['retained_frames']/16 if quality=='accepted' else None))
    groups={}
    for temperature in sorted({t['temperature'] for t in trials}):
        rows=[t for t in trials if t['temperature']==temperature and t['mode']=='normal']
        times=[t['wall_seconds'] for t in rows if t['wall_seconds'] is not None]
        accepted=[t for t in rows if t['quality']=='accepted'];usable=sum(t['usable_video_seconds'] for t in accepted)
        groups[temperature]=dict(samples=len(rows),native_clip_p50_seconds=percentile(times,.5),
            native_clip_p95_seconds=percentile(times,.95),quality_accepted=len(accepted),
            native_seconds_per_usable_video_second=sum(times)/usable if usable and len(accepted)==len(rows) else None,
            quality_rejected=sum(t['quality']=='rejected' for t in rows),
            missing_quality=sum(t['quality']=='unverified' for t in rows))
    failures=list((root/'trials').glob('*/history.failed.json'))
    return dict(schema_version=1,task_id='LVA-01',scope='Native diagnostic fixture only; not final1080p/full-film speedup',
        fixture_id=fixture['fixture_id'],root=str(root),quality_parameters=fixture['parameters'],
        input_sha256=fixture['input_sha256'],selected_image_sha256=fixture['selected_image_sha256'],
        trials=trials,groups=groups,technical_execution_failures=len(failures),
        unique_retained_videos=len({t['retained_sha256'] for t in trials}),
        telemetry_parse_errors=errors,
        limitations=['Cold means new process, not OS disk-cache flush.',
            'Warm means repeated process with samplers invalidated; model residency is observed separately.',
            'GPU data are device-wide sampled values; node/model wall intervals are not synchronized CUDA kernel timings.',
            'No usable-video cost is published while quality is unverified; no 1080p end-to-end claim.'])


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',required=True,type=Path)
    args=parser.parse_args(argv);root=args.root.resolve()
    if not root.is_relative_to((RUNTIME_ROOT/'scratch/benchmarks').resolve()) or not (root/'experiment.json').is_file():
        parser.error('new experiment root required')
    report=summarize(root)
    (root/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# LVA-01 native GPU diagnostic summary','','Native clips only; quality acceptance and final1080p end-to-end remain separate.','',
        '| Trial | Generation/tracking s | Technical s | Peak device MiB | Quality |','| --- | ---: | ---: | ---: | --- |']
    for row in report['trials']:
        value=row['submit_to_output_seconds']
        lines.append(f'| {row["trial_id"]} | {value:.3f} | {row["technical_seconds"]:.3f} | {row["device_sampled_peak_vram_mib"]} | {row["quality"]} |' if value is not None else f'| {row["trial_id"]} | unknown (recovery) | {row["technical_seconds"]:.3f} | unknown | {row["quality"]} |')
    lines+=['',*report['limitations']]
    (root/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(fixture=report['fixture_id'],groups=report['groups'],completed=len(report['trials']),
                         unique_retained_videos=report['unique_retained_videos']),ensure_ascii=False))


if __name__=='__main__':main()
