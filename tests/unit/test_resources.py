from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import time
import pytest


def test_two_runs_compete_for_exclusive_gpu_lock(run_store,runtime_run,monkeypatch):
    import video_ai.runtime.resources as module
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.paths import create_run
    from video_ai.runtime.manifest import create_manifest
    run,config,paths=runtime_run
    other_run=create_run(paths)
    other_store=create_manifest(other_run,config,inputs={},models={},workflows={})
    monkeypatch.setattr(module,'gpu_guard',lambda *a,**k:{'status':'verified','external_pids':[]})
    one=module.GpuLease(paths,run_store,RunLogger(run))
    two=module.GpuLease(paths,other_store,RunLogger(other_run))
    one.acquire('source_clips','shot_0001')
    try:
        with pytest.raises(module.GpuBusyError):two.acquire('upscale','shot_0001')
        two.release()
        assert one.lock_path.exists()
    finally:one.release()
    two.acquire('upscale','shot_0001')
    two.release()
    assert not two.lock_path.exists()


@pytest.mark.parametrize('batch',[0,2,True,1.0])
def test_gpu_batch_must_be_integer_one(run_store,runtime_run,batch):
    from video_ai.runtime.resources import GpuLease
    from video_ai.runtime.logging import RunLogger
    with pytest.raises(ValueError):
        GpuLease(runtime_run[2],run_store,RunLogger(runtime_run[0])).acquire('upscale','shot_0001',batch_size=batch)


@pytest.mark.parametrize('sample',[{'status':'unverified','external_pids':[]},{'status':'verified','external_pids':[99999]}])
def test_unknown_or_external_gpu_task_refuses_lease(run_store,runtime_run,monkeypatch,sample):
    import video_ai.runtime.resources as module
    from video_ai.runtime.logging import RunLogger
    monkeypatch.setattr(module,'gpu_guard',lambda *a,**k:sample)
    lease=module.GpuLease(runtime_run[2],run_store,RunLogger(runtime_run[0]))
    with pytest.raises(module.GpuBusyError):lease.acquire('source_clips','shot_0001')
    assert not lease.lock_path.exists()
    assert run_store.snapshot()['resources']['latest']['status']==sample['status']


def test_stale_gpu_lock_never_removed_or_claimed(run_store,runtime_run,monkeypatch):
    import video_ai.runtime.resources as module
    from video_ai.runtime.logging import RunLogger
    monkeypatch.setattr(module,'gpu_guard',lambda *a,**k:{'status':'verified','external_pids':[]})
    lease=module.GpuLease(runtime_run[2],run_store,RunLogger(runtime_run[0]))
    lease.lock_path.parent.mkdir(parents=True,exist_ok=True)
    lease.lock_path.write_text('historical owner',encoding='utf-8')
    try:
        with pytest.raises(module.GpuBusyError):lease.acquire('upscale','shot_0001')
        lease.release()
        assert lease.lock_path.read_text()=='historical owner'
    finally:lease.lock_path.unlink()


def test_sampler_classifies_external_pids_and_computes_real_peaks(runtime_run,monkeypatch):
    import video_ai.runtime.resources as module
    used=[100,200]
    def run(args,**kwargs):
        assert Path(args[0]).is_absolute()
        assert kwargs['timeout']>0 and kwargs['shell'] is False
        data='123, 20\n999, 40\n' if any('compute-apps' in a for a in args) else f'24455, {used.pop(0)}, 8\n'
        return subprocess.CompletedProcess(args,0,data,'')
    monkeypatch.setattr(module,'find_nvidia_smi',lambda:Path('C:/Windows/System32/nvidia-smi.exe'))
    monkeypatch.setattr(module,'windows_memory',lambda pids:{'system_used_bytes':500,'process_rss_bytes':{'123':40}})
    sampler=module.ResourceSampler(runtime_run[0],{123},runner=run)
    first=sampler.sample()
    second=sampler.sample()
    assert first['external_pids']==[999]
    assert first['status']=='verified' and first['gpu_used_mib']==100
    assert second['gpu_used_mib']==200
    assert sampler.summary()['peak_gpu_used_mib']==200
    assert sampler.summary()['peak_system_used_bytes']==500
    rows=[json.loads(line) for line in (runtime_run[0]/'logs/resources.jsonl').read_text().splitlines()]
    assert len(rows)==2 and rows[0]['external_gpu_task'] is True


def test_failed_sampler_keeps_running_and_marks_unverified(runtime_run,monkeypatch):
    import video_ai.runtime.resources as module
    monkeypatch.setattr(module,'find_nvidia_smi',lambda:None)
    def denied(pids):raise OSError('memory query denied')
    monkeypatch.setattr(module,'windows_memory',denied)
    sampler=module.ResourceSampler(runtime_run[0],set(),interval_seconds=.01)
    sampler.start()
    time.sleep(.035)
    sampler.stop()
    rows=[json.loads(line) for line in (runtime_run[0]/'logs/resources.jsonl').read_text().splitlines()]
    assert len(rows)>=2 and all(r['status']=='unverified' for r in rows)
    assert all('memory query denied' in str(r['errors']) for r in rows)
    assert sampler.summary()['peak_gpu_used_mib'] is None


def test_sampler_tracks_new_live_owned_process_and_valid_sample_count(runtime_run,monkeypatch):
    import video_ai.runtime.resources as module
    owned={123}
    seen=[]
    def memory(pids):
        seen.append(set(pids))
        return {'system_used_bytes':500,'process_rss_bytes':{str(p):40 for p in pids}}
    monkeypatch.setattr(module,'windows_memory',memory)
    monkeypatch.setattr(module,'find_nvidia_smi',lambda:Path('C:/Windows/System32/nvidia-smi.exe'))
    def query(args,**kwargs):
        return subprocess.CompletedProcess(args,0,'123, 20\n' if any('compute-apps' in a for a in args) else '24455, 100, 8\n','')
    sampler=module.ResourceSampler(runtime_run[0],lambda:owned,runner=query)
    sampler.sample()
    owned.add(456)
    sampler.sample()
    assert seen==[{123},{123,456}]
    assert sampler.summary()['verified_samples']==2
    assert sampler.summary()['peak_process_rss_bytes']['456']==40


def test_replaced_lock_cannot_be_deleted_by_previous_lease(run_store,runtime_run,monkeypatch):
    import video_ai.runtime.resources as module
    from video_ai.runtime.logging import RunLogger
    monkeypatch.setattr(module,'gpu_guard',lambda *a,**k:{'status':'verified','external_pids':[]})
    lease=module.GpuLease(runtime_run[2],run_store,RunLogger(runtime_run[0]))
    lease.acquire('upscale','shot_0001')
    lease.lock_path.write_text('{"token":"other"}',encoding='utf-8')
    try:
        with pytest.raises(module.GpuBusyError):lease.release()
        assert lease.lock_path.exists()
    finally:lease.lock_path.unlink()


def test_lease_recognizes_current_managers_live_owned_service(run_store,runtime_run,monkeypatch):
    import video_ai.runtime.resources as module
    from video_ai.runtime.logging import RunLogger
    from test_services import manager, spec, healthy, Process
    import video_ai.runtime.services as services
    process=Process()
    started=False
    def route(r,t):
        if not started:raise ConnectionRefusedError('closed')
        return healthy(r,t)
    mgr,_=manager(run_store,runtime_run,route)
    monkeypatch.setattr(services,'port_listening',lambda *a,**k:False)
    def launch(*a,**k):
        nonlocal started
        started=True
        return process
    monkeypatch.setattr(services.subprocess,'Popen',launch)
    handle=mgr.ensure(spec(runtime_run,timeout=.2))
    observed=[]
    def guard(run,pids):
        observed.append(pids)
        return {'status':'verified','external_pids':[] if handle.pid in pids else [handle.pid]}
    monkeypatch.setattr(module,'gpu_guard',guard)
    lease=module.GpuLease(runtime_run[2],run_store,RunLogger(runtime_run[0]),service_manager=mgr)
    with lease.acquire('source_clips','shot_0001'):
        assert handle.pid in observed[-1]
    mgr.stop(handle)
    assert handle.pid not in mgr.owned_pids
