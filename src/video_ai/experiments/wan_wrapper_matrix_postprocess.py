"""Explicit reviewed Wrapper sources for the established full-frame 1080P pipeline."""
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import json
from uuid import uuid4

from .wan_fast_profiles import artifact,write_once
from .wan_fast_experiment import read
from . import wan_wrapper_matrix as matrix


def reviewed_source(root,trial):
    return matrix.require_review(root,trial)[0]


def fixture_source(root,trial):
    return read(Path(root)/'fixture.json')


def _state(path,value):
    """Replace only a derived current-owner pointer; immutable epoch archives remain."""
    path=Path(path);temporary=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temporary.replace(path)


def archive_previous_service(work):
    work=Path(work)
    if not (work/'service-owner.json').exists():return False
    owner=read(work/'service-owner.json');result=read(work/'service-result.json')
    if not result.get('exited') or not result.get('port_closed'):raise ValueError('previous postprocess owner must exit before recovery')
    folder=work/'service-epochs'/f'{owner["pid"]}-{owner["process_started_at"]}'
    write_once(folder/'service-owner.json',owner);write_once(folder/'service-result.json',result)
    return True


def copy_chain_frames(folder,rows,*,expected):
    folder=Path(folder);frames=folder/'frames';frames.mkdir(parents=True,exist_ok=True)
    if len(rows)!=expected:raise ValueError('complete contiguous parent/child sequence required')
    copied=[]
    for index,row in enumerate(rows,1):
        source=Path(row['path']);target=frames/f'frame_{index:06d}.png'
        if artifact(source).sha256!=row['sha256']:raise ValueError('parent/child upscale source differs')
        if target.exists():
            if artifact(target).sha256!=row['sha256']:raise ValueError('existing chain frame differs')
        else:shutil.copyfile(source,target)
        copied.append(dict(path=str(target),sha256=row['sha256']))
    write_once(folder/'upscale-complete.json',dict(kind='verified_wrapper_parent_child_sequence',frames=copied,
                                               frame_count=expected,width=1920,height=1080))
    return copied


def _postprocess_owned(root,group,trial):
    from .wan_wrapper_backend import SOURCE
    root=Path(root).resolve();gr=root/'groups'/group
    if group not in matrix.GROUPS or trial not in matrix.TRIALS:raise ValueError('matrix postprocess selection')
    matrix.authorize_group(gr,read(root/'authorization.json'))
    matrix.require_all_native_accepted(root)
    result=reviewed_source(gr,trial)
    fixture=fixture_source(gr,trial);key=fixture['matrix_fixture']
    if key=='parent' and trial!='cold_1':raise ValueError('unconsumed parent warm frames must not be upscaled')
    for other in matrix.GROUPS:
        other_root=root/'groups'/other
        if (other_root/'service-owner.json').exists():
            stopped=read(other_root/'service-result.json')
            if not stopped.get('exited') or not stopped.get('port_closed'):raise ValueError('all Wan owned services must exit before upscale')
    work=root/'postprocess'/f'{group}-{trial}'
    if (work/'operation-complete.json').exists():
        done=read(work/'operation-complete.json')
        for item in done['artifacts']:
            if artifact(item['path']).sha256!=item['sha256']:raise ValueError('completed postprocess artifact differs')
        return done
    recovering=archive_previous_service(work) if work.exists() else False
    # These exact sources were bound to the original request during matrix init.
    narration=fixture['postprocess_sources']['narration'];font=fixture['postprocess_sources']['font']
    if artifact(narration['path']).sha256!=narration['sha256'] or artifact(font['path']).sha256!=font['sha256']:
        raise ValueError('original narration/font identity differs')
    write_once(gr/'narration-source.json',narration);write_once(gr/'render-font.json',font)
    sys.path.insert(0,str(SOURCE/'scripts'))
    import postprocess_local_gpu as native
    from observe_wan_wrapper_comfy import BoundedJob,stop_owned,host_available_commit_bytes,bootstrap_software
    from video_ai.runtime.production_state import process_started_at
    from .wan_wrapper_runtime_support import InputLeases
    profile=matrix.group_profile(gr);common=profile.identity_dict()['common']
    upscale=dict(path='E:/VideoAI/shared/models/comfyui/upscale_models/RealESRGAN_x4plus.pth',bytes=67040989,
                 sha256='4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1')
    # Resource observation happens outside the bounded child.
    import ctypes
    class Memory(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in
            ('total_phys','avail_phys','total_pagefile','avail_pagefile','total_virtual','avail_virtual','avail_extended')]
    memory=Memory();memory.length=ctypes.sizeof(memory)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):raise ctypes.WinError()
    if memory.avail_phys<14*1024**3 or host_available_commit_bytes()<26*1024**3:raise ValueError('postprocess host resources below approved minimum')
    smi=subprocess.run(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True)
    if int(smi.stdout.strip().splitlines()[0])<21*1024:raise ValueError('postprocess free VRAM below approved minimum')
    with socket.socket() as reserve:reserve.bind(('127.0.0.1',8189))
    work.mkdir(parents=True,exist_ok=True)
    for name in ('input','output','temp','user'):(work/name).mkdir(exist_ok=True)
    write_once(work/'experiment.json',dict(kind='LVA-07-06-explicit-upscale',port=8189,matrix_root=str(root),matrix_sha256=read(gr/'experiment.json')['matrix_sha256'],group=group,trial=trial))
    environment=matrix.SCRATCH/'LVA-07-04-environment'
    logs=work/'service-epochs'/uuid4().hex;logs.mkdir(parents=True)
    write_once(logs/'launch.json',dict(profile=profile.identity_dict(),matrix_root=str(root),group=group,trial=trial,
                                    workflow=artifact(SOURCE/'workflows/upscale_api.json').identity_dict(),model=upscale))
    command=[str(environment/'python_embeded/python.exe'),'-I','-B','-X','utf8',str(SOURCE/'scripts/benchmark_wan_wrapper_matrix.py'),
             'postprocess-worker','--root',str(work),'--epoch-directory',str(logs)]
    assets=[*common['source']['artifacts'],*common['tool']['artifacts'],upscale]
    for binding in (narration,font):
        path=Path(binding['path']).resolve(strict=True)
        assets.append(dict(path=str(path),bytes=path.stat().st_size,sha256=binding['sha256']))
    process=job=sampler=None;started=time.monotonic();exit_result={};done=None
    leases=InputLeases(assets);software=bootstrap_software()
    try:
        with (logs/'stdout.log').open('xb') as out,(logs/'stderr.log').open('xb') as err:
            process=subprocess.Popen(command,cwd=environment/'ComfyUI',stdout=out,stderr=err,
                                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),shell=False)
            job=BoundedJob(process,18*1024**3,cpu=False)
            owner=dict(pid=process.pid,process_started_at=process_started_at(process.pid),experiment_root=str(work),port=8189)
            _state(work/'service-owner.json',owner)
            from .wan_wrapper_matrix_observer import DeviceSampler
            sampler=DeviceSampler(process,logs/'resources.jsonl',logs.name).start()
            client=native.ExperimentClient(work,port=8189)
            while True:
                if process.poll() is not None:raise RuntimeError('owned upscale worker exited before readiness')
                try:
                    client.assert_owned_service()
                    if not (logs/'worker-ready.json').exists():raise ValueError('postprocess guards not ready')
                    break
                except (ValueError,OSError,RuntimeError):
                    if time.monotonic()-started>180:raise TimeoutError('upscale worker readiness')
                    time.sleep(.25)
            upscale_result=native.upscale_trial(work,gr,trial,port=8189,result_provider=reviewed_source,
                                                fixture_provider=fixture_source,source_frames=result['frames'],restarted=recovering)
            artifacts=[dict(path=row['path'],sha256=row['sha256']) for row in upscale_result['frames']]
            candidate=None
            if key not in ('parent','child'):
                candidate=native.compose_trial(work,gr,trial,narration['path'],fixture_provider=fixture_source)
            elif key=='child':
                parent_root=root/'groups'/('parent-'+read(gr/'experiment.json')['mode'])
                parent_fixture=fixture_source(parent_root,'cold_1')
                if parent_fixture['budget']['end_frame']!=fixture['budget']['start_frame']:raise ValueError('parent/child intervals differ')
                parent_work=root/'postprocess'/('parent-'+read(gr/'experiment.json')['mode']+'-cold_1')
                parent_upscale=bound_parent_upscale(root,read(gr/'experiment.json')['mode'])
                folder=work/'postprocess'/('parent_child_chain_'+trial)
                copy_chain_frames(folder,parent_upscale['frames']+upscale_result['frames'],expected=170)
                candidate=native.compose_trial(work,parent_root,'cold_1',narration['path'],folder_override=folder,fixture_provider=fixture_source)
            if candidate:artifacts.append(dict(path=candidate['candidate'],sha256=candidate['candidate_sha256']))
            done=dict(task_id='LVA-07-06',group=group,trial=trial,upscale=upscale_result,candidate=candidate,
                      artifacts=artifacts,quality='awaiting_final_human_review' if candidate else 'parent_frames_ready',
                      seconds=time.monotonic()-started,recovered_invocation=recovering,technical_ready_at_utc=matrix.utcnow())
            done['render_font_sha256']=font['sha256']
            done.update(profile_sha256=result['profile_sha256'],fixture_sha256=result['fixture_sha256'],
                        native_prompt_id=result['prompt_id'],native_retained_sha256=result['retained_sha256'],
                        parent_binding=fixture.get('parent_binding'))
    finally:
        if sampler:
            sampler.stop()
            if process.poll() is None:sampler.sample()
        if process is not None:exit_result=stop_owned(process,logs,'matrix-postprocess')
        if job:job.close()
        software.close();leases.close()
        with socket.socket() as check:exit_result['port_closed']=check.connect_ex(('127.0.0.1',8189))!=0
        _state(work/'service-result.json',exit_result)
        write_once(logs/'service-result.json',exit_result)
    if not exit_result.get('exited') or exit_result.get('exit_code')!=0 or not exit_result.get('port_closed'):
        raise ValueError('postprocess owned service exit failed')
    write_once(work/'operation-complete.json',done)
    return done


def bound_parent_upscale(root,mode):
    root=Path(root);parent=root/'groups'/('parent-'+mode)
    result,_=matrix.require_review(parent,'cold_1',validate_media=False)
    fixture=read(parent/'fixture.json');work=root/'postprocess'/('parent-'+mode+'-cold_1')
    operation=read(work/'operation-complete.json')
    value=read(work/'postprocess'/(fixture['fixture_id']+'_cold_1')/'upscale-complete.json')
    proof=read(Path(result['retained']).with_suffix('.media-proof.json'))
    if value!=operation['upscale'] or value['native_source_sha256']!=result['retained_sha256'] or result['frames']!=proof['frames']:
        raise ValueError('parent upscale does not bind the accepted original media')
    if [r['source_sha256'] for r in value['frames']]!=[r['sha256'] for r in proof['frames']]:
        raise ValueError('ordered parent upscale source frames differ')
    return value


def postprocess(root,group,trial):
    from .wan_wrapper_matrix_observer import GpuOwnership
    root=Path(root)
    if group.startswith('child-'):bound_parent_upscale(root,group.rsplit('-',1)[1])
    with GpuOwnership():return _postprocess_owned(root,group,trial)
