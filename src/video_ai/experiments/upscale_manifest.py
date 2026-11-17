"""Read-only admission of accepted LVA-01 sources and bounded LVA-05 phases."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

from .upscale_experiment import SOURCE, FACTORS, baseline_api, read, freeze_manifest, run_frames
from .wan_fast_profiles import Artifact, artifact, digest
from ..runtime.paths import RUNTIME_ROOT
from ..runtime.verification import whole_input_protection

TRIALS=('cold_1','warm_1','warm_2','warm_3')


def pinned_tools(manifest):
    assets=manifest['artifacts']
    python=Artifact(**assets['comfy_python']);main=Artifact(**assets['comfy_main.py'])
    python.verify();main.verify()
    return dict(comfy_python=Path(python.path),comfy_root=Path(main.path).parent)


def _port_open(port):
    with socket.socket() as connection:
        connection.settimeout(.3)
        return connection.connect_ex(('127.0.0.1',port))==0


def owned_service_ready(root,profile,port):
    from .upscale_experiment import PipelineExperimentClient
    if not (root/'service-owner.json').exists():return False
    client=PipelineExperimentClient(root,profile_sha256=profile,port=port)
    client.verify()
    # The owner is published immediately after spawn, before Comfy finishes
    # imports. Only assert listener PID after a listener actually exists.
    if not _port_open(port):return False
    client.delegate.assert_owned_service()
    return True


def _process_identity(pid):
    from ..runtime.production_state import process_started_at
    return process_started_at(pid)


def _wait_owner_exit(owner,timeout):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        current=_process_identity(owner['pid'])
        if current!=owner['process_started_at']:return True
        time.sleep(.2)
    return _process_identity(owner['pid'])!=owner['process_started_at']


def _terminate_owner(owner):
    import signal
    if _process_identity(owner['pid'])==owner['process_started_at']:
        os.kill(owner['pid'],signal.SIGTERM)


def stop_owner(root,profile,supervisor=None,*,original=None):
    """Stop the original bound child before touching its supervisor."""
    try:
        owner_path=root/'service-owner.json'
        if owner_path.exists():
            owner=read(owner_path)
            if owner.get('profile_sha256')!=profile:raise ValueError('cleanup owner profile differs')
            binding=root/'frozen/service-binding.json'
            if binding.exists() and read(binding)!=owner:raise ValueError('cleanup original owner differs')
            if _process_identity(owner['pid'])==owner['process_started_at']:
                baseline_api().write_once(root/'stop.request.json',dict(pid=owner['pid']))
                if not _wait_owner_exit(owner,30):
                    _terminate_owner(owner)
                    if not _wait_owner_exit(owner,10):raise RuntimeError('verified owned child did not stop')
        if supervisor is not None:
            try:supervisor.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Observer's kill-on-close job also guards the pre-owner startup
                # window. A verified child, when present, was reaped first.
                supervisor.terminate();supervisor.wait(timeout=10)
    except Exception as exc:
        if original is not None:original.add_note('owned cleanup failed: '+type(exc).__name__)
        else:raise


def select_native_case(cases,fixture):
    label={'low':'low_motion','high':'high_motion','parent':'parent_child','child':'parent_child'}[fixture]
    rows=[]
    for case in cases:
        if case['fixture_id']!=label:continue
        child=all(row['trial_id'].endswith('_child') for row in case['trials'])
        if child!=(fixture=='child'):continue
        value=read(Path(case['root'])/('child-fixture.json' if child else 'fixture.json'))
        if bool(value['requires_new_parent'])!=child or bool(value['budget']['parent_clip_id'])!=child:
            raise ValueError('native source parent/child identity differs')
        rows.append((case,value))
    if len(rows)!=1:raise ValueError('exactly one native source with matching clip/parent identity required')
    return rows[0]


def _module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module);return module


def _add(assets,role,path,expected=None):
    value=artifact(path).identity_dict()
    if expected and value['sha256']!=expected:raise ValueError('accepted artifact drift: '+role)
    assets[role]=value;return value


def source_manifest(results,fixture,common):
    case,identity=select_native_case(results['cases'],fixture)
    native=Path(case['root']).resolve();post=results['postprocess'][fixture];work=Path(post['root'])
    child=fixture=='child';assets=dict(common);frames=[];bindings=[]
    api=baseline_api();helper=_module('_lva05_post',SOURCE/'scripts/postprocess_local_gpu.py')
    _add(assets,'native_fixture',native/('child-fixture.json' if child else 'fixture.json'))
    for name in ('narration-source.json','render-font.json','frozen/original-request.json'):
        _add(assets,'native_'+name.replace('/','_'),native/name)
    font=read(native/'render-font.json');_add(assets,'font',font['path'],font['sha256'])
    narration=read(native/'narration-source.json');_add(assets,'narration_timeline',narration['path'],narration['sha256'])
    timeline=read(narration['path']);timeline=timeline.get('payload',timeline)
    for index,clip in enumerate(timeline['clips']):
        _add(assets,f'narration_pcm_{index}',clip['pcm']['stamp']['path'])
    template=read(SOURCE/'workflows/upscale_api.json')
    for trial in TRIALS:
        actual=trial+'_child' if child else trial
        result=helper.require_native_review(native,actual)
        folder=work/'postprocess'/(identity['fixture_id']+'_'+actual)
        extracted=read(folder/'extraction.json');complete=read(folder/'upscale-complete.json')
        if (result['retained_sha256']!=extracted['source_sha256'] or complete['native_source_sha256']!=result['retained_sha256']
                or len(extracted['frames'])!=result['retained_frames'] or complete['frame_count']!=result['retained_frames']
                or len(complete['frame_rgb_sha256'])!=result['retained_frames']):
            raise ValueError('accepted extraction/frame budget/source differs')
        _add(assets,actual+'_extraction',folder/'extraction.json')
        _add(assets,actual+'_upscale_complete',folder/'upscale-complete.json')
        for name in ('technical-complete.json','observation-accepted.json','intent.json','accepted.json','history.completed.json'):
            _add(assets,actual+'_'+name,native/'trials'/actual/name)
        for role in ('generated','retained','last_frame'):_add(assets,actual+'_'+role,result[role],result[role+'_sha256'])
        if child:
            binding=read(native/'trials'/actual/'parent-binding.json')
            parent=helper.require_native_review(Path(binding['parent_root']),binding['parent_trial'])
            if parent['last_frame_sha256']!=binding['parent_last_frame_sha256']:
                raise ValueError('accepted child source parent tail differs')
            _add(assets,actual+'_parent_binding',native/'trials'/actual/'parent-binding.json')
            _add(assets,actual+'_parent_approval',Path(binding['parent_root'])/'trials'/binding['parent_trial']/'observation-accepted.json',binding['human_acceptance_sha256'])
        start=len(frames)+1
        for row in extracted['frames']:
            source=artifact(row['path']).identity_dict()
            if source['sha256']!=row['sha256']:raise ValueError('proven extracted PNG drift')
            index=len(frames)+1;graph=deepcopy(template)
            graph['1']['inputs']['image']=f'frames/frame_{index:06d}.png'
            graph['5']['inputs']['filename_prefix']=f'upscale/frame_{index:06d}'
            frames.append(dict(frame_id=index,source=source,graph=graph,trial=trial,source_clip_id=identity['source_clip_id']))
        bindings.append(dict(trial=trial,native_trial=actual,native_root=str(native),source_clip_id=identity['source_clip_id'],
            requires_new_parent=child,retained_sha256=result['retained_sha256'],frame_start=start,
            frame_count=result['retained_frames'],expected_rgb_sha256=complete['frame_rgb_sha256'],
            original_upscale_complete=assets[actual+'_upscale_complete'],original_folder=str(folder)))
    return dict(schema_version=1,task_id='LVA-05',fixture=fixture,artifacts=assets,frames=frames,
        source_binding=bindings,parameters=dict(width=1920,height=1080,fps=16,
            model='RealESRGAN_x4plus.pth',resize='lanczos',factor=4))


def encoding_cases(results,common):
    rows=[]
    for fixture in ('low','high','chain'):
        group=results['postprocess']['child' if fixture=='chain' else fixture]
        label={'low':'low_motion','high':'high_motion','chain':'parent_child_chain'}[fixture]
        for trial in TRIALS:
            folder=Path(group['root'])/'postprocess'/(label+'_'+trial)
            complete=read(folder/'composition-complete.json');approval=read(folder/'observation-accepted.json')
            if approval.get('decision')!='accepted' or approval['candidate_sha256']!=complete['candidate_sha256']:
                raise ValueError('accepted complete materialized encoding input required')
            upscaled=read(folder/'upscale-complete.json');assets=dict(common)
            for name in ('composition-complete.json','observation-accepted.json','upscale-complete.json','subtitles.ass','narration.wav'):
                _add(assets,name,folder/name)
            for i,p in enumerate((folder/'fonts').iterdir()):_add(assets,'render_font_'+str(i),p)
            for i,row in enumerate(upscaled['frames']):_add(assets,'png_'+str(i),row['path'],row['sha256'])
            _add(assets,'accepted_video',complete['candidate'],complete['candidate_sha256'])
            name=fixture+'-'+trial
            rows.append(dict(case=name,folder=str(folder.resolve()),
                root=str((RUNTIME_ROOT/'scratch/benchmarks'/('LVA-05-20261116-01-encoding-'+name)).resolve()),
                frames=upscaled['frame_count'],artifacts=assets))
    return rows


def prepare_plan(output):
    """No inference/service/torch import: only accepted-content admission."""
    from ..config import load_config
    config=load_config(SOURCE/'config/production.example.json');output=Path(output).resolve()
    results=read(SOURCE/'docs/task-designs/LVA-01-gpu-results.json')
    expected_model=RUNTIME_ROOT/'shared/models/comfyui/upscale_models/RealESRGAN_x4plus.pth'
    if Path(config.models['upscale']).resolve()!=expected_model.resolve():
        raise ValueError('native loader model search path differs from admitted model')
    common={};phases=[]
    with whole_input_protection(immutable_roots=()):
        paths={'model':config.models['upscale'],'workflow':SOURCE/'workflows/upscale_api.json',
            'mapping':SOURCE/'workflows/upscale_api.mapping.json','ffmpeg':config.tools['ffmpeg'],
            'ffprobe':config.tools['ffprobe'],'comfy_python':config.tools['comfy_python'],
            'baseline_results':SOURCE/'docs/task-designs/LVA-01-gpu-results.json',
            'baseline_completion':SOURCE/'docs/task-designs/LVA-01-completion.json'}
        paths['configuration']=config.config_file
        for name in ('upscale_pipeline','upscale_experiment','upscale_manifest','scene_encoding_experiment'):
            paths['source_'+name]=SOURCE/f'src/video_ai/experiments/{name}.py'
        paths.update({f'script_{name}':SOURCE/f'scripts/{name}.py' for name in
            ('benchmark_upscale_pipeline','observe_upscale_comfy','benchmark_scene_encoding','benchmark_local_gpu','postprocess_local_gpu','observe_local_comfy')})
        for name in ('nodes.py','execution.py','main.py','comfyui_version.py','comfy_extras/nodes_upscale_model.py',
                     'comfy/model_management.py','comfy/utils.py','comfy/ops.py'):
            paths['comfy_'+name]=Path(config.tools['comfy_root'])/name
        for role,path in paths.items():_add(common,role,path)
        if common['workflow']['sha256']!='a647f05940ce6b59de9bde8d5d53b9300bfe6b5174d900b3324eb6cd01680533':
            raise ValueError('original upscale workflow changed')
        code='import sys,json,importlib.metadata as m;print(json.dumps(dict(python=sys.version,packages={k:m.version(k) for k in ("torch","numpy","comfy-aimdo","comfy-kitchen")})))'
        environment=json.loads(subprocess.check_output([str(config.tools['comfy_python']),'-B','-s','-c',code],timeout=30))
        # Version source read, no torch/CUDA initialization.
        torch_version=Path(config.tools['comfy_python']).parent/'Lib/site-packages/torch/version.py'
        _add(common,'torch_version',torch_version)
        environment['torch_version_source']=torch_version.read_text('utf-8')
        from ..runtime.resources import find_nvidia_smi
        smi=find_nvidia_smi()
        if smi:
            _add(common,'nvidia_smi',smi)
            environment['device_driver']=subprocess.check_output([str(smi),'--query-gpu=name,driver_version,memory.total','--format=csv,noheader'],timeout=30).decode().strip()
        from .scene_encoding_experiment import encoder_capability
        capability=encoder_capability(config.tools['ffmpeg'])
        for fixture in ('low','high','parent','child'):
            source=source_manifest(results,fixture,common)
            for factor in FACTORS:
                phase=fixture+'-'+factor
                root=RUNTIME_ROOT/'scratch/benchmarks'/('LVA-05-20261116-01-'+phase)
                manifest=dict(source,factor=factor,root=str(root.resolve()),environment=environment)
                phases.append(dict(phase=phase,root=str(root.resolve()),manifest=manifest,
                    profile_sha256=digest(dict(manifest,pipeline_config=__import__('dataclasses').asdict(FACTORS[factor]))),
                    requires_single_factor_acceptance=factor=='pipeline'))
        encodes=encoding_cases(results,common)
        report=dict(schema_version=1,task_id='LVA-05',status='prepared_awaiting_gpu_authorization',gpu_executed=False,
            phases=phases,encoding_capability=capability,max_owned_processes=16,
            max_upscale_requests=sum(len(p['manifest']['frames']) for p in phases),
            trials_per_phase=list(TRIALS),model_instances_per_phase=1,concurrent_gpu_requests=1,
            native_generations=0,downloads=0,production_resumed=False,
            sample_policy='Serial then prefetch/writeback; pipeline only after technical and genuine human acceptance. No gains implied by preparation.',
            encoding_cases=encodes,encoding_max_nvenc_requests=len(encodes),
            encoding_max_cpu_baselines=len(encodes),default_factor='serial',default_encoder='libx264')
        baseline_api().write_once(output,report)
    return report


def _verify_plan(plan):
    if (plan.get('task_id')!='LVA-05' or not 1<=plan.get('max_upscale_requests',0)<=5696
            or sum(len(p['manifest']['frames']) for p in plan['phases'])!=plan['max_upscale_requests']):
        raise ValueError('reviewed bounded LVA-05 plan required')
    return plan


def summarize_phase(root,result):
    """Aggregate existing node/CPU wall events; never equate calls to loads."""
    events=[];malformed=0
    path=Path(root)/'node-metrics.jsonl'
    if not path.exists():return dict(status='telemetry_missing',physical_model_load_count=None)
    for line in path.read_text('utf-8').splitlines():
        try:events.append(json.loads(line))
        except ValueError:malformed+=1
    pids={row['prompt_id'] for row in result.get('frame_timings',[])}
    nodes={};node_seconds={};models={};model_seconds={}
    for event in events:
        if event.get('prompt_id') not in pids:continue
        kind=event.get('kind');name=event.get('stage')
        if kind not in ('node','model'):continue
        counts,seconds=(nodes,node_seconds) if kind=='node' else (models,model_seconds)
        counts[name]=counts.get(name,0)+1;seconds[name]=seconds.get(name,0)+event['seconds']
    gpu=[device for event in events if event.get('kind')=='gpu' for device in event['devices']]
    return dict(node_calls=nodes,node_cpu_wall_seconds=node_seconds,model_method_calls=models,
        model_method_cpu_wall_seconds=model_seconds,physical_model_load_count=None,
        device_sampled_peak_vram_mib=max((v['used_mib'] for v in gpu),default=None),
        device_mean_gpu_utilization_percent=sum(v['utilization_percent'] for v in gpu)/len(gpu) if gpu else None,
        gpu_samples=len(gpu),malformed_events=malformed,
        backend='native Comfy ImageUpscaleWithModel / RealESRGAN',
        scope='Method/node CPU wall intervals and device-wide samples, not kernel time, physical transfers or exclusive-process peaks.')


def run_phase(plan_path, phase):
    """Caller must have already obtained authorization for this exact plan."""
    from .upscale_experiment import PipelineExperimentClient
    plan=_verify_plan(read(plan_path));matches=[p for p in plan['phases'] if p['phase']==phase]
    if len(matches)!=1:raise ValueError('unknown reviewed phase')
    selected=matches[0];manifest=selected['manifest'];root=Path(selected['root']).resolve()
    if not root.is_relative_to((RUNTIME_ROOT/'scratch/benchmarks').resolve()) or root!=Path(manifest['root']):
        raise ValueError('phase root differs from reviewed plan')
    if selected['requires_single_factor_acceptance']:
        for factor in ('prefetch','writeback'):
            predecessor=next(p for p in plan['phases'] if p['phase']==manifest['fixture']+'-'+factor)
            folder=Path(predecessor['root']);report=read(folder/'phase-results.json');approval=read(folder/'quality-accepted.json')
            if (report.get('status')!='awaiting_human_review' or report.get('accepted_baseline_pixels_equal') is not True
                    or approval.get('decision')!='accepted' or approval.get('report_sha256')!=digest(report)):
                raise ValueError('genuine single-factor quality acceptance required')
    # Existing roots are recovery only: never launch another process to replace
    # the original service, even if no receipt has yet been captured.
    fresh=not root.exists();profile=selected['profile_sha256'];api=baseline_api()
    service=None;error=None;result=None;logs=[]
    try:
        if fresh:
            root.mkdir(parents=True)
            if freeze_manifest(root,manifest)!=profile:raise ValueError('reviewed profile digest differs')
            api.write_once(root/'experiment.json',dict(kind='LVA-05',port=8189,profile_sha256=profile))
            tools=pinned_tools(manifest)
            argv=[str(tools['comfy_python']),'-B','-s',str(SOURCE/'scripts/observe_upscale_comfy.py'),
                '--experiment-root',str(root),'--profile-sha256',profile,'--port','8189','--max-seconds','14400']
            api.write_once(root/'frozen/service-launch.json',dict(args=argv,profile_sha256=profile,port=8189,environment=manifest['environment']))
            logs=[(root/'launcher.stdout').open('xb'),(root/'launcher.stderr').open('xb')]
            service=subprocess.Popen(argv,stdout=logs[0],stderr=logs[1],cwd=SOURCE,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            until=time.monotonic()+180
            while time.monotonic()<until:
                if service.poll() is not None:raise RuntimeError('owned upscale observer exited during startup')
                try:
                    if owned_service_ready(root,profile,8189):break
                except (OSError,api.OutcomeUnknown):pass
                time.sleep(.25)
            else:raise TimeoutError('owned upscale startup timeout')
        result=run_frames(root,profile_sha256=profile)
    except BaseException as exc:error=exc;raise
    finally:
        try:stop_owner(root,profile,service,original=error)
        finally:
            for stream in logs:stream.close()
    # No service survives the review gate. Compare every RGB frame to the
    # accepted original; differing pixels require a genuine new review.
    expected=[h for b in manifest['source_binding'] for h in b['expected_rgb_sha256']]
    result=dict(result,gpu_executed=True,status='awaiting_human_review' if result['frame_rgb_sha256']==expected else 'rejected_pixel_contract',
        accepted_baseline_pixels_equal=result['frame_rgb_sha256']==expected,
        telemetry=summarize_phase(root,result),
        physical_model_load_count=None,scope='Upscale phase only; composition and native inference separate.')
    api.write_once(root/'phase-results.json',result)
    return result
