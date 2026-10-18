"""Task-4-only desktop exceptions explicitly approved by the user on 2026-10-04."""
import ctypes
from ctypes import wintypes
from fnmatch import fnmatchcase
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from uuid import uuid4

from .logging import RunLogger
from .resources import find_nvidia_smi

APPROVED_PATHS=(
    'c:/windows/explorer.exe',
    'c:/windows/system32/dwm.exe',
    'c:/windows/system32/applicationframehost.exe',
    'c:/windows/systemapps/microsoftwindows.client.cbs_*/crossdeviceresume.exe',
    'c:/windows/systemapps/microsoftwindows.client.cbs_*/searchhost.exe',
    'c:/windows/systemapps/microsoft.windows.startmenuexperiencehost_*/startmenuexperiencehost.exe',
    'c:/windows/systemapps/microsoft.windows.shellexperiencehost_*/shellexperiencehost.exe',
    'c:/windows/systemapps/microsoft.windows.lockapp_*/lockapp.exe',
    'c:/windows/systemapps/microsoft.lockapp_*/lockapp.exe',
    'c:/windows/systemapps/shellexperiencehost_*/shellexperiencehost.exe',
    'c:/windows/systemapps/microsoftwindows.client.cbs_*/textinputhost.exe',
    'c:/windows/system32/shellhost.exe',
    'c:/windows/immersivecontrolpanel/systemsettings.exe',
    'c:/program files/windowsapps/microsoft.yourphone_*/phoneexperiencehost.exe',
    'c:/program files/windowsapps/microsoftwindows.client.webexperience_*/dashboard/widgetboard.exe',
    'c:/program files/windowsapps/microsoftwindows.client.webexperience_*/widgetboard.exe',
    'c:/windows/system32/taskmgr.exe',
    'c:/program files (x86)/microsoft/edgewebview/application/*/msedgewebview2.exe',
    'c:/program files/nvidia corporation/nvidia app/cef/nvidia overlay.exe',
    'c:/users/qzw19/appdata/roaming/tencent/qqlive/cocosdanmu/*/magicdanmaku.exe',
    'd:/program files (x86)/tencent/qqlive/qqlive.exe',
    'd:/users/qzw19/appdata/local/programs/pixpin/pixpin.exe',
    'd:/program files/jetbrains/pycharm */bin/pycharm64.exe',
    'c:/users/qzw19/appdata/local/programs/microsoft vs code/code.exe',
    'd:/program files/microsoft vs code/code.exe',
    'c:/program files (x86)/msi/*/ledkeeper2.exe',
)
PROTECTED_DESKTOP_NAMES={'dwm.exe','applicationframehost.exe','msedgewebview2.exe','code.exe'}


def approved_desktop(path, process_type):
    spelling=str(path).replace('\\','/').casefold()
    if process_type not in ('G','C+G') or '..' in Path(spelling).parts:
        return False
    return any(fnmatchcase(spelling,pattern) for pattern in APPROVED_PATHS)


def process_image(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD)
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
    kernel.QueryFullProcessImageNameW.argtypes=(wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD))
    kernel.QueryFullProcessImageNameW.restype=wintypes.BOOL
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    try:
        text=ctypes.create_unicode_buffer(32768)
        size=wintypes.DWORD(len(text))
        if not kernel.QueryFullProcessImageNameW(handle,0,text,ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        return text.value
    finally:kernel.CloseHandle(handle)


def process_types(run):
    exe=find_nvidia_smi()
    if exe is None:raise OSError('nvidia-smi unavailable')
    args=(str(exe),'-q','-x')
    result=subprocess.run(args,cwd=run,timeout=10,shell=False,capture_output=True,text=True)
    RunLogger(run).save_json('resources/desktop-types-'+uuid4().hex+'.json',dict(args=args,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
    if result.returncode!=0:raise OSError('GPU process type query failed')
    types={}
    for info in ET.fromstring(result.stdout).findall('gpu/processes/process_info'):
        pid=int(info.findtext('pid'))
        kind=info.findtext('type')
        if pid<=0 or kind not in ('C','G','C+G'):raise ValueError('invalid GPU process type')
        types[pid]=kind
    return types


def process_names():
    class Entry(ctypes.Structure):
        _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('th32ProcessID',wintypes.DWORD),
                  ('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',wintypes.DWORD),('cntThreads',wintypes.DWORD),
                  ('th32ParentProcessID',wintypes.DWORD),('pcPriClassBase',wintypes.LONG),('dwFlags',wintypes.DWORD),
                  ('szExeFile',wintypes.WCHAR*260)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes=(wintypes.DWORD,wintypes.DWORD)
    kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    kernel.Process32FirstW.argtypes=(wintypes.HANDLE,ctypes.POINTER(Entry))
    kernel.Process32NextW.argtypes=(wintypes.HANDLE,ctypes.POINTER(Entry))
    kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
    handle=kernel.CreateToolhelp32Snapshot(2,0)
    if handle==wintypes.HANDLE(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    names={}
    try:
        entry=Entry()
        entry.dwSize=ctypes.sizeof(entry)
        valid=kernel.Process32FirstW(handle,ctypes.byref(entry))
        if not valid:raise ctypes.WinError(ctypes.get_last_error())
        while valid:
            names[entry.th32ProcessID]=entry.szExeFile.casefold()
            valid=kernel.Process32NextW(handle,ctypes.byref(entry))
        if ctypes.get_last_error()!=18:raise ctypes.WinError(ctypes.get_last_error())
    finally:kernel.CloseHandle(handle)
    return names


def desktop_policy(run, sample):
    sample=dict(sample)
    if sample.get('status')!='verified':return sample
    approved=[]
    evidence=[]
    try:
        types=process_types(run)
        for pid in sample.get('external_pids',[]):
            process_type=types.get(pid)
            name=None
            path=None
            try:
                path=process_image(pid)
                allowed=approved_desktop(path,process_type)
            except PermissionError:
                name=process_names().get(pid)
                allowed=name in PROTECTED_DESKTOP_NAMES and process_type in ('G','C+G')
            evidence.append(dict(pid=pid,path=path,protected_os_name=name,type=process_type,allowed=allowed))
            if allowed:approved.append(pid)
    except (OSError,ValueError,ET.ParseError) as exc:
        sample['status']='unverified'
        sample.setdefault('errors',[]).append('desktop identity query failed: '+str(exc))
        approved=[]
    sample['approved_desktop_pids']=approved
    sample['external_pids']=sorted(set(sample.get('external_pids',[]))-set(approved))
    sample['external_gpu_task']=bool(sample['external_pids'])
    sample['gpu_free_mib']=sample.get('gpu_total_mib',0)-sample.get('gpu_used_mib',0)
    RunLogger(run).save_json('resources/desktop-policy-'+uuid4().hex+'.json',dict(identities=evidence,result=sample,approval='User 2026-10-04: allow verified observed desktop applications'))
    return sample
