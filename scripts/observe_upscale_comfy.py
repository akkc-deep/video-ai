"""One bounded LVA-05 owned Comfy, native model cache, no graph submission."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from time import perf_counter
from types import SimpleNamespace

SOURCE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(SOURCE/'src'),str(SOURCE/'scripts')]
from video_ai.experiments.upscale_experiment import read,baseline_api
from video_ai.experiments.wan_fast_profiles import Artifact,digest
from video_ai.runtime.paths import RUNTIME_ROOT
from video_ai.experiments.upscale_manifest import pinned_tools


class KillOnCloseJob:
    """Windows kernel kills the owned child even if this observer is terminated."""
    def __init__(self,process):
        class Basic(ctypes.Structure):
            _fields_=[('PerProcessUserTimeLimit',ctypes.c_int64),('PerJobUserTimeLimit',ctypes.c_int64),
                ('LimitFlags',wintypes.DWORD),('MinimumWorkingSetSize',ctypes.c_size_t),
                ('MaximumWorkingSetSize',ctypes.c_size_t),('ActiveProcessLimit',wintypes.DWORD),
                ('Affinity',ctypes.c_size_t),('PriorityClass',wintypes.DWORD),('SchedulingClass',wintypes.DWORD)]
        class Io(ctypes.Structure):
            _fields_=[(name,ctypes.c_uint64) for name in ('ReadOperationCount','WriteOperationCount','OtherOperationCount',
                'ReadTransferCount','WriteTransferCount','OtherTransferCount')]
        class Extended(ctypes.Structure):
            _fields_=[('BasicLimitInformation',Basic),('IoInfo',Io),('ProcessMemoryLimit',ctypes.c_size_t),
                ('JobMemoryLimit',ctypes.c_size_t),('PeakProcessMemoryUsed',ctypes.c_size_t),('PeakJobMemoryUsed',ctypes.c_size_t)]
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype=wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        self.handle=self.kernel.CreateJobObjectW(None,None)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        value=Extended();value.BasicLimitInformation.LimitFlags=0x2000
        try:
            if not self.kernel.SetInformationJobObject(self.handle,9,ctypes.byref(value),ctypes.sizeof(value)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.kernel.AssignProcessToJobObject(self.handle,int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:self.close();raise

    def close(self):
        if self.handle:
            handle,self.handle=self.handle,None;self.kernel.CloseHandle(handle)


def validate_launch(root,profile,port):
    manifest=read(root/'frozen/manifest.json');launch=read(root/'frozen/service-launch.json')
    marker=read(root/'experiment.json')
    if (digest(manifest)!=profile or manifest.get('task_id')!='LVA-05'
            or launch.get('profile_sha256')!=profile or launch.get('port')!=port
            or marker.get('profile_sha256')!=profile or marker.get('port')!=port
            or launch.get('environment')!=manifest.get('environment')):
        raise ValueError('reviewed LVA-05 launch profile differs')
    for item in manifest['artifacts'].values():Artifact(**item).verify()
    return manifest


def _port_open(port):
    with socket.socket() as sock:
        sock.settimeout(.3);return sock.connect_ex(('127.0.0.1',port))==0


def _memory(pid):
    """Windows observed process RSS and native peak; not a payload budget."""
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),
            *[(k,ctypes.c_size_t) for k in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage',
                'QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    handle=kernel.OpenProcess(0x0400|0x0010,False,pid)
    if not handle:return None
    try:
        value=Counters();value.cb=ctypes.sizeof(value)
        if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(value),value.cb):return None
        return dict(rss_bytes=value.WorkingSetSize,peak_rss_bytes=value.PeakWorkingSetSize)
    finally:kernel.CloseHandle(handle)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment-root',required=True,type=Path)
    parser.add_argument('--profile-sha256',required=True);parser.add_argument('--port',type=int,default=8189)
    parser.add_argument('--max-seconds',type=int,default=14400);parser.add_argument('--worker',action='store_true')
    args=parser.parse_args(argv);root=args.experiment_root.resolve()
    if (not root.is_relative_to((RUNTIME_ROOT/'scratch/benchmarks').resolve()) or not root.name.startswith('LVA-05-')
            or not 30<=args.max_seconds<=14400 or args.port!=8189):parser.error('reviewed LVA-05 root/port/runtime required')
    from video_ai.config import load_config
    manifest=validate_launch(root,args.profile_sha256,args.port)
    tools=pinned_tools(manifest)
    config=launch_configuration(manifest)
    if args.worker:
        import observe_local_comfy
        return observe_local_comfy.worker(SimpleNamespace(experiment_root=root,
            comfy_root=tools['comfy_root'],port=args.port))
    if _port_open(8188) or _port_open(args.port) or (root/'service-owner.json').exists():
        raise ValueError('new owned phase required; no replacement of an existing service')
    for name in ('input','output','temp','user'):(root/name).mkdir(exist_ok=True)
    command=[str(tools['comfy_python']),'-B','-s',str(Path(__file__).resolve()),'--worker',
        '--experiment-root',str(root),'--profile-sha256',args.profile_sha256,'--port',str(args.port)]
    started=perf_counter();peak=0;samples=0;timed_out=False;code=None
    with (root/'comfy.stdout').open('xb') as stdout,(root/'comfy.stderr').open('xb') as stderr:
        from video_ai.runtime.environment import build_child_env
        from video_ai.runtime.paths import RuntimePaths
        environment=build_child_env(RuntimePaths.from_config(config))
        process=subprocess.Popen(command,cwd=tools['comfy_root'],env=environment,stdout=stdout,stderr=stderr,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        job=None
        try:
            job=KillOnCloseJob(process)
            from video_ai.runtime.production_state import process_started_at
            owner=dict(pid=process.pid,process_started_at=process_started_at(process.pid),experiment_root=str(root),
                port=args.port,parent_pid=os.getpid(),profile_sha256=args.profile_sha256,
                launch_sha256=digest(read(root/'frozen/service-launch.json')))
            baseline_api().write_once(root/'service-owner.json',owner)
            while process.poll() is None:
                memory=_memory(process.pid)
                if memory:peak=max(peak,memory['peak_rss_bytes']);samples+=1
                if perf_counter()-started>args.max_seconds:
                    timed_out=True;process.terminate();break
                try:process.wait(timeout=1)
                except subprocess.TimeoutExpired:pass
            code=process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            if job is not None:job.close()
    finalized=False
    if (root/'node-metrics.jsonl').exists():
        lines=(root/'node-metrics.jsonl').read_text('utf-8').splitlines()
        try:finalized=read_json_line(lines[-1]).get('finalized') is True
        except (ValueError,IndexError):pass
    result=dict(returncode=code,timed_out=timed_out,metrics_finalized=finalized,
        wall_seconds=perf_counter()-started,observed_peak_process_rss_bytes=peak if samples else None,
        rss_samples=samples,physical_model_load_count=None)
    baseline_api().write_once(root/'service-result.json',result)
    return 124 if timed_out else code


def read_json_line(line):return json.loads(line)


def launch_configuration(manifest):
    from video_ai.config import load_config
    return load_config(Path(manifest['artifacts']['configuration']['path']))


if __name__=='__main__':raise SystemExit(main())
