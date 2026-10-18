"""Read-only bounded resource sampling and explicitly owned batch-one GPU leases."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
from threading import Event, RLock, Thread
from uuid import uuid4

from ..adapters.common import positive_timeout
from .logging import RunLogger
from .manifest import now, STAGES, validate_run_dir
from .paths import PathPolicy, CACHE_ROOT


class GpuBusyError(RuntimeError):
    pass


def find_nvidia_smi():
    path = shutil.which('nvidia-smi')
    if path:
        return Path(path).resolve(strict=True)
    fallback = Path('C:/Windows/System32/nvidia-smi.exe')
    return fallback if fallback.is_file() else None


def windows_memory(owned_pids):
    if os.name != 'nt':
        raise OSError('Windows memory APIs unavailable')
    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length',wintypes.DWORD),('load',wintypes.DWORD)] + [(name,ctypes.c_ulonglong) for name in
                  ('total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','avail_extended')]
    class ProcessCounters(ctypes.Structure):
        _fields_ = [('cb',wintypes.DWORD),('faults',wintypes.DWORD)] + [(name,ctypes.c_size_t) for name in
                   ('peak_working','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
    kernel, psapi = ctypes.WinDLL('kernel32',use_last_error=True), ctypes.WinDLL('psapi',use_last_error=True)
    kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
    kernel.GlobalMemoryStatusEx.restype = wintypes.BOOL
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not kernel.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ctypes.WinError(ctypes.get_last_error())
    kernel.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,ctypes.POINTER(ProcessCounters),wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    rss = {}
    for pid in owned_pids:
        handle = kernel.OpenProcess(0x410,False,pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            counters = ProcessCounters()
            counters.cb = ctypes.sizeof(counters)
            if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(counters),counters.cb):
                raise ctypes.WinError(ctypes.get_last_error())
            rss[str(pid)] = counters.working
        finally:
            kernel.CloseHandle(handle)
    return dict(system_used_bytes=status.total_phys-status.avail_phys, process_rss_bytes=rss)


class ResourceSampler:
    def __init__(self, run_dir, owned_pids, *, interval_seconds=1.0, runner=subprocess.run):
        self.run_dir = validate_run_dir(run_dir)
        self._owned_provider = owned_pids if callable(owned_pids) else None
        self.owned_pids = set(owned_pids() if self._owned_provider else owned_pids)
        if any(type(pid) is not int or pid <= 0 for pid in self.owned_pids):
            raise ValueError('owned_pids must be positive integers')
        self.interval = positive_timeout(interval_seconds)
        self.runner = runner
        self.logger = RunLogger(run_dir)
        self._stop = Event()
        self._thread = None
        self._lock = RLock()
        self._peaks = {'peak_gpu_used_mib':None,'peak_system_used_bytes':None,'peak_process_rss_bytes':{},'verified_samples':0}

    def sample(self):
        with self._lock:
            if self._owned_provider is not None:
                self.owned_pids=set(self._owned_provider())
                if any(type(pid) is not int or pid<=0 for pid in self.owned_pids):
                    raise ValueError('invalid dynamically owned PID')
            sample = dict(time=now(), status='unverified', gpu_total_mib=None,gpu_used_mib=None,
                          gpu_utilization_percent=None, compute_pids=[],external_pids=[],external_gpu_task=False,
                          system_used_bytes=None,process_rss_bytes={},errors=[],evidence_paths=[])
            try:
                sample.update(windows_memory(self.owned_pids))
            except Exception as exc:
                sample['errors'].append(str(exc))
            try:
                executable = find_nvidia_smi()
                if executable is None:
                    raise OSError('nvidia-smi unavailable')
                results = []
                for query in ('--query-gpu=memory.total,memory.used,utilization.gpu','--query-compute-apps=pid,used_gpu_memory'):
                    args = [str(executable),query,'--format=csv,noheader,nounits']
                    result = self.runner(args,cwd=self.run_dir,timeout=5,shell=False,capture_output=True,text=True)
                    path = self.logger.save_json(f'resources/{uuid4().hex}.json',dict(args=args,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
                    sample['evidence_paths'].append(str(path))
                    if result.returncode != 0:
                        raise OSError(f'nvidia-smi exit {result.returncode}: {result.stderr}')
                    results.append(result.stdout)
                rows = [[int(part.strip()) for part in row.split(',')] for row in results[0].splitlines() if row.strip()]
                if not rows or any(len(row)!=3 or any(value<0 for value in row) for row in rows):
                    raise ValueError('invalid GPU statistics')
                sample.update(gpu_total_mib=sum(row[0] for row in rows),gpu_used_mib=sum(row[1] for row in rows),gpu_utilization_percent=max(row[2] for row in rows))
                pids = []
                for row in results[1].splitlines():
                    if not row.strip():
                        continue
                    parts = row.split(',')
                    pid = int(parts[0].strip())
                    if len(parts)!=2 or pid <= 0:
                        raise ValueError('invalid compute-apps PID')
                    pids.append(pid)
                sample['compute_pids'] = sorted(set(pids))
                sample['external_pids'] = sorted(set(pids)-self.owned_pids)
                sample['external_gpu_task'] = bool(sample['external_pids'])
                sample['status'] = 'verified' if not sample['errors'] else 'unverified'
            except Exception as exc:
                sample['errors'].append(str(exc))
                sample['evidence_paths'].append(str(self.logger.exception(None,None,exc)))
            if sample['status']=='verified':
                self._peaks['verified_samples']+=1
                for field, peak in (('gpu_used_mib','peak_gpu_used_mib'),('system_used_bytes','peak_system_used_bytes')):
                    value = sample[field]
                    if value is not None:
                        self._peaks[peak] = max(value,self._peaks[peak] or 0)
                for pid,rss in sample['process_rss_bytes'].items():
                    self._peaks['peak_process_rss_bytes'][pid] = max(rss,self._peaks['peak_process_rss_bytes'].get(pid,0))
            with self.logger.path('resources.jsonl').open('a',encoding='utf-8',newline='\n') as file:
                file.write(json.dumps(sample,allow_nan=False)+'\n')
                file.flush()
            self.logger.event(None,None,'resource_sample',sample)
            return sample

    def summary(self):
        from copy import deepcopy
        with self._lock:
            return deepcopy(self._peaks)

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError('sampler already running')
        self._stop.clear()
        def loop():
            while not self._stop.is_set():
                try:
                    self.sample()
                except Exception as exc:
                    self.logger.exception(None,None,exc)
                self._stop.wait(self.interval)
        self._thread = Thread(target=loop,name='video-ai-resource-sampler',daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=12)
            if self._thread.is_alive():
                raise TimeoutError('resource sampler did not stop within bounded query deadline')

    def __enter__(self):
        return self.start()

    def __exit__(self,*exc):
        self.stop()


def gpu_guard(run_dir, owned_pids):
    return ResourceSampler(run_dir,owned_pids).sample()


_lease_mutex = RLock()


class GpuLease:
    def __init__(self, paths, manifest, logger, *, service_manager=None, resource_policy=None):
        self.paths,self.manifest,self.logger = paths,manifest,logger
        self.lock_path = paths.policy.validate_write(paths.cache_root/'locks/gpu.lock','cache')
        self._token = None
        self.service_manager = service_manager
        self.resource_policy = resource_policy

    def acquire(self, stage, unit_id, *, batch_size=1):
        if type(batch_size) is not int or batch_size != 1:
            raise ValueError('GPU batch_size must be integer 1')
        if stage not in STAGES:
            raise ValueError('unknown GPU stage')
        with _lease_mutex:
            if self._token:
                raise GpuBusyError('this lease is already held')
            path = self.paths.policy.validate_write(self.lock_path,'cache')
            path.parent.mkdir(parents=True,exist_ok=True)
            try:
                fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            except FileExistsError as exc:
                raise GpuBusyError('GPU lock exists; no stale-lock takeover') from exc
            token = uuid4().hex
            try:
                with os.fdopen(fd,'w',encoding='utf-8') as file:
                    json.dump(dict(token=token,run_id=self.manifest.run_dir.name,pid=os.getpid(),stage=stage,unit_id=unit_id),file)
                    file.flush()
                    os.fsync(file.fileno())
                self._token = token
                # Persistent service PIDs do not prove ownership in this process.
                owned_pids = {os.getpid()}
                if self.service_manager is not None:
                    owned_pids.update(self.service_manager.owned_pids)
                sample = gpu_guard(self.manifest.run_dir,owned_pids)
                if self.resource_policy is not None:
                    sample = self.resource_policy(self.manifest.run_dir,sample)
                self.manifest.update(lambda data:data['resources'].update(latest=sample))
                if sample.get('status')!='verified' or sample.get('external_pids'):
                    self.logger.event(stage,unit_id,'gpu_busy',sample)
                    raise GpuBusyError('GPU queries unverified or external compute task present')
                self.logger.event(stage,unit_id,'gpu_acquired',dict(token=token,batch_size=1))
                return self
            except BaseException:
                if self._token:
                    self.release()
                else:
                    path.unlink()
                raise

    def release(self):
        with _lease_mutex:
            if self._token is None:
                return
            path = self.paths.policy.validate_write(self.lock_path,'cache')
            try:
                owner = json.loads(path.read_text(encoding='utf-8'))
            except (OSError,ValueError) as exc:
                self._token = None
                raise GpuBusyError('lease ownership evidence missing; lock retained') from exc
            token,self._token = self._token,None
            if owner.get('token') != token:
                raise GpuBusyError('GPU lock belongs to another owner; retained')
            path.unlink()
            self.logger.event(None,None,'gpu_released',dict(token=token))

    def __enter__(self):
        if not self._token:
            raise GpuBusyError('acquire the GPU lease before entering context')
        return self

    def __exit__(self,*exc):
        self.release()
