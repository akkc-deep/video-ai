"""Independent LVA-05 encoder capability/CPU fixture and authorized NVENC pair."""
import argparse
import json
from pathlib import Path
import shutil
import sys
from uuid import uuid4
import wave

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE/'src'))
from video_ai.experiments.scene_encoding_experiment import (encoder_capability,encode_once,inspect_encoded,compare_evidence)
from video_ai.experiments.upscale_experiment import baseline_api,read
from video_ai.experiments.wan_fast_profiles import Artifact,artifact,digest


def evidence_once(path,output,*,config,count):
    identity=dict(output=artifact(path).identity_dict(),ffmpeg=artifact(config.tools['ffmpeg']).identity_dict(),
        ffprobe=artifact(config.tools['ffprobe']).identity_dict(),frames=count)
    if output.exists():
        result=read(output)
        if result['identity']!=identity:raise ValueError('encoding evidence content/tool drift')
        return result['evidence']
    evidence=inspect_encoded(path,ffmpeg=config.tools['ffmpeg'],ffprobe=config.tools['ffprobe'],expected_frames=count)
    baseline_api().write_once(output,dict(identity=identity,evidence=evidence));return evidence


def offline(output):
    from video_ai.config import load_config
    from video_ai.runtime.paths import RUNTIME_ROOT
    from video_ai.experiments.upscale_offline import write_png
    config=load_config(SOURCE/'config/production.example.json')
    output=Path(output).resolve();folder=output.parent/('LVA-05-encoding-offline-'+uuid4().hex[:10]);folder.mkdir(parents=True)
    for index in range(1,4):write_png(folder/'frames'/f'frame_{index:06d}.png',1920,1080,(index*32,96,192))
    with wave.open(str(folder/'narration.wav'),'wb') as audio:
        audio.setparams((1,2,48000,0,'NONE',''));audio.writeframes(bytes(9000*2))
    font=load_config(RUNTIME_ROOT/'shared/config/production.json').media.font_file
    (folder/'fonts').mkdir();shutil.copyfile(font,folder/'fonts/font.ttc')
    (folder/'subtitles.ass').write_text('[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n'
        '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
        'Style: Default,Microsoft YaHei,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,80,80,60,1\n'
        '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
        'Dialogue: 0,0:00:00.00,0:00:00.19,Default,,0,0,0,,LVA-05 offline\n',encoding='utf-8')
    capability=encoder_capability(config.tools['ffmpeg'])
    encoded=encode_once(folder,folder/'baseline.mp4',ffmpeg=config.tools['ffmpeg'],encoder='libx264')
    evidence=evidence_once(folder/'baseline.mp4',folder/'baseline.evidence.json',config=config,count=3)
    # Completed command and decoded evidence both replay without new producers.
    again=encode_once(folder,folder/'baseline.mp4',ffmpeg=config.tools['ffmpeg'],encoder='libx264')
    if encoded!=again:raise AssertionError('encoding replay differs')
    report=dict(task_id='LVA-05',status='offline_passed',gpu_executed=False,capability=capability,
        software=encoded,evidence=evidence,root=str(folder),nvenc=dict(status='not_run_awaiting_authorization'),
        default_encoder='libx264',scope='Synthetic CPU-only full 1080P/16fps fixture; no NVENC quality/performance claim.')
    baseline_api().write_once(output,report);return report


def run_pair(plan_path,case_name):
    from video_ai.config import load_config
    from video_ai.runtime.paths import RUNTIME_ROOT
    from video_ai.runtime.verification import whole_input_protection,writable_validation_session
    from types import SimpleNamespace
    plan=read(plan_path)
    if plan.get('task_id')!='LVA-05':raise ValueError('exact reviewed LVA-05 plan required')
    cases=[row for row in plan['encoding_cases'] if row['case']==case_name]
    if len(cases)!=1:raise ValueError('one reviewed materialized encoding case required')
    case=cases[0];folder=Path(case['folder']).resolve(strict=True);root=Path(case['root']).resolve()
    config=SimpleNamespace(tools={k:Path(case['artifacts'][k]['path']) for k in ('ffmpeg','ffprobe')})
    if not root.is_relative_to((RUNTIME_ROOT/'scratch/benchmarks').resolve()) or not root.name.startswith('LVA-05-'):
        raise ValueError('new LVA-05 scratch root required')
    root.mkdir(parents=True,exist_ok=True)
    with whole_input_protection(immutable_roots=()),writable_validation_session(root):
        for value in case['artifacts'].values():Artifact(**value).verify()
        completed=read(folder/'composition-complete.json');accepted=read(folder/'observation-accepted.json')
        if accepted.get('decision')!='accepted' or accepted['candidate_sha256']!=completed['candidate_sha256']:
            raise ValueError('accepted original materialized baseline required')
        baseline=Path(completed['candidate']);baseline_identity=artifact(baseline).identity_dict()
        if baseline_identity['sha256']!=completed['candidate_sha256']:raise ValueError('accepted encoding source drift')
        upscaled=read(folder/'upscale-complete.json');count=upscaled['frame_count']
        for row in upscaled['frames']:
            if artifact(row['path']).sha256!=row['sha256']:raise ValueError('complete materialized PNG source drift')
        sources=[folder/'composition-complete.json',folder/'observation-accepted.json',folder/'upscale-complete.json',
            folder/'narration.wav',folder/'subtitles.ass',*folder.glob('fonts/*'),
            *folder.glob('frames/*.png'),SOURCE/'scripts/benchmark_scene_encoding.py',
            SOURCE/'src/video_ai/experiments/scene_encoding_experiment.py',*map(Path,(config.tools['ffmpeg'],config.tools['ffprobe']))]
        request=dict(task_id='LVA-05',case_sha256=digest(case),accepted_baseline=baseline_identity,
            assets=[artifact(p).identity_dict() for p in sorted(sources)],frames=count,
            nvenc=dict(encoder='h264_nvenc',preset='p4',rc='constqp',qp=18),
            historical_encode_seconds=completed.get('encode_seconds'),timing_scope='New paired fixed-materialization libx264 and NVENC encoding; historical time separate.')
        baseline_api().write_once(root/'frozen/request.json',request)
        capability=encoder_capability(config.tools['ffmpeg'])
        if capability['status']=='unsupported':
            report=dict(task_id='LVA-05',status='unsupported',gpu_executed=False,capability=capability)
        else:
            software=encode_once(folder,root/'baseline.mp4',ffmpeg=config.tools['ffmpeg'],encoder='libx264')
            candidate=encode_once(folder,root/'nvenc.mp4',ffmpeg=config.tools['ffmpeg'],encoder='h264_nvenc')
            original=evidence_once(root/'baseline.mp4',root/'baseline.evidence.json',config=config,count=count)
            proposed=evidence_once(root/'nvenc.mp4',root/'nvenc.evidence.json',config=config,count=count)
            report=dict(task_id='LVA-05',gpu_executed=True,capability=capability,request_sha256=digest(request),
                software=software,candidate=candidate,baseline=original,proposed=proposed,**compare_evidence(original,proposed))
        baseline_api().write_once(root/'results.json',report);return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline',action='store_true');parser.add_argument('--output',type=Path)
    parser.add_argument('--folder',type=Path);parser.add_argument('--root',type=Path)
    parser.add_argument('--plan',type=Path);parser.add_argument('--case')
    parser.add_argument('--gpu-authorized',action='store_true')
    args=parser.parse_args(argv)
    if args.offline:
        if not args.output:parser.error('offline output required')
        report=offline(args.output)
    else:
        if not args.gpu_authorized or not args.plan or not args.case:parser.error('explicit GPU authorization, exact --plan and --case required')
        report=run_pair(args.plan,args.case)
    print(json.dumps(dict(status=report['status'],gpu_executed=report['gpu_executed'])))


if __name__=='__main__':main()
