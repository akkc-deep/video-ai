"""Shared owned-GPU exclusion, bounded device observations and native upscale bootstrap."""
import builtins
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

from .wan_fast_experiment import read
from .wan_fast_profiles import artifact
from .wan_wrapper_matrix import SCRATCH,utcnow,authorize_group


class GpuOwnership:
    def __init__(self,path=None):self.path=Path(path or SCRATCH/'.lva07-matrix-gpu.lock');self.file=None
    def __enter__(self):
        import msvcrt
        self.path.parent.mkdir(parents=True,exist_ok=True);self.file=self.path.open('a+b')
        if self.file.tell()==0:self.file.write(b'0');self.file.flush()
        self.file.seek(0)
        try:msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
        except BaseException:self.file.close();self.file=None;raise
        return self
    def __exit__(self,*exc):
        if self.file:
            import msvcrt
            self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1);self.file.close();self.file=None


def process_memory(pid):
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in
            ('peak_rss','rss','peak_paged','paged','peak_nonpaged','nonpaged','private_commit','peak_private_commit')]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    handle=kernel.OpenProcess(0x410,False,pid)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    try:
        counters=Counters();counters.cb=ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(counters),counters.cb):raise ctypes.WinError(ctypes.get_last_error())
        result={key:getattr(counters,key) for key in ('rss','peak_rss','private_commit','peak_private_commit')}
        class IO(ctypes.Structure):
            _fields_=[(n,ctypes.c_ulonglong) for n in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
        io=IO();kernel.GetProcessIoCounters.argtypes=[wintypes.HANDLE,ctypes.POINTER(IO)]
        if kernel.GetProcessIoCounters(handle,ctypes.byref(io)):result['io']={n:getattr(io,n) for n,_ in IO._fields_}
        clocks=[wintypes.FILETIME() for _ in range(4)]
        kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
        if kernel.GetProcessTimes(handle,*(ctypes.byref(value) for value in clocks)):
            for key,value in zip(('created','exit','kernel','user'),clocks):
                if key in ('kernel','user'):result['cpu_'+key+'_seconds']=((value.dwHighDateTime<<32)|value.dwLowDateTime)/10_000_000
        return result
    finally:kernel.CloseHandle(handle)


class DeviceSampler:
    def __init__(self,process,path,epoch,*,interval=10):
        self.process,self.path,self.epoch,self.interval=process,Path(path),epoch,interval
        self.stop_event=threading.Event();self.thread=None;self.quota_failure=None
    def sample(self):
        row=dict(at_utc=utcnow(),monotonic=time.monotonic(),pid=self.process.pid,epoch=self.epoch,
                 interval_seconds=self.interval,gpu_scope='device-wide including other applications; sampled, not exclusive kernel peak')
        try:
            row['process_memory']=process_memory(self.process.pid)
            if row['process_memory']['peak_rss']>24*1024**3:
                self.quota_failure='owned process RSS exceeded24GiB'
                if self.process.poll() is None:self.process.terminate()
            result=subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],
                                  capture_output=True,text=True,timeout=8,check=True)
            row['devices']=[dict(used_mib=int(parts[0]),utilization_percent=int(parts[1])) for line in result.stdout.splitlines()
                            if (parts:=[x.strip() for x in line.split(',')]) and len(parts)==2]
            row['status']='observed'
        except Exception as exc:row.update(status='unverified',error=repr(exc))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open('a',encoding='utf-8') as output:output.write(json.dumps(row,ensure_ascii=False)+'\n');output.flush()
    def start(self):
        def loop():
            while not self.stop_event.is_set():self.sample();self.stop_event.wait(self.interval)
        self.thread=threading.Thread(target=loop,name='lva07-device-observer',daemon=True);self.thread.start();return self
    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=10)
        if self.thread and self.thread.is_alive():raise TimeoutError('owned device observer did not stop')


def postprocess_worker(work,epoch_directory):
    from .wan_wrapper_backend import SOURCE,WrapperProfile
    from .wan_wrapper_runtime_support import SoftwareVerifier,InputLeases,SOFTWARE_SHA256
    work=Path(work).resolve();epoch=Path(epoch_directory).resolve()
    if not epoch.is_relative_to(work/'service-epochs'):raise ValueError('exact postprocess epoch directory required')
    import os
    deadline=time.monotonic()+10
    while True:
        if (work/'service-owner.json').exists() and read(work/'service-owner.json').get('pid')==os.getpid():break
        if time.monotonic()>deadline:raise TimeoutError('owned Job/identity handshake missing')
        time.sleep(.05)
    marker=read(work/'experiment.json');launch=read(epoch/'launch.json')
    authorize_group(Path(marker['matrix_root'])/'groups'/marker['group'],read(Path(marker['matrix_root'])/'authorization.json'))
    profile=WrapperProfile.from_dict(launch['profile']);common=profile.identity_dict()['common']
    for name in ('source','runtime','tool'):
        for item in common[name]['artifacts']:
            if artifact(item['path']).identity_dict()!=item:raise ValueError('postprocess runtime/source/tool differs')
    environment=SCRATCH/'LVA-07-04-environment'
    if Path(sys.executable).resolve()!=(environment/'python_embeded/python.exe').resolve():raise ValueError('isolated postprocess interpreter required')
    inventory=SOURCE/'docs/task-designs/LVA-07-04-software.json'
    if artifact(inventory).sha256!=SOFTWARE_SHA256:raise ValueError('original runtime inventory differs')
    rows=read(inventory)['files']+common['source']['artifacts']
    verifier=SoftwareVerifier(rows,[environment/'ComfyUI',environment/'python_embeded',SOURCE/'src',SOURCE/'scripts'])
    leases=InputLeases(common['source']['artifacts']);verifier.install()
    def nodes_ready(registry):
        import torch,folder_paths
        from .wan_fast_profiles import write_once
        torch.cuda.set_per_process_memory_fraction(20*1024**3/torch.cuda.get_device_properties(0).total_memory)
        if torch.cuda.mem_get_info()[0]<20*1024**3:raise ValueError('postprocess phase free VRAM below20GiB')
        workflow=read(launch['workflow']['path']);classes={row['class_type'] for row in workflow.values()}
        if not classes<=set(registry):raise ValueError('actual native upscale nodes missing')
        path=folder_paths.get_full_path('upscale_models',Path(launch['model']['path']).name)
        if path is None or Path(path).resolve()!=Path(launch['model']['path']).resolve():raise ValueError('actual upscale model search path differs')
        write_once(epoch/'worker-ready.json',dict(pid=os.getpid(),classes=sorted(classes),allocator_limit_bytes=20*1024**3,
            workflow=launch['workflow'],model=launch['model'],runtime_verifier_installed=True))
    sys.path.insert(0,str(SOURCE/'scripts'))
    try:
        import observe_local_comfy
        observe_local_comfy.worker(SimpleNamespace(experiment_root=work,comfy_root=environment/'ComfyUI',port=8189,
                                                  metrics_root=epoch,stop_root=epoch,on_nodes_ready=nodes_ready))
    finally:verifier.close();leases.close()
    return 0
