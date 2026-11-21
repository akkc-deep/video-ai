param([switch]$Run)
$ErrorActionPreference = 'Stop'
$environmentRoot = 'E:/VideoAI/scratch/benchmarks/LVA-07-04-environment'
$probeRoot = 'E:/VideoAI/scratch/benchmarks/LVA-07-04-node-probe'
$port = 8297
$classes = @('WanVideoModelLoader','WanVideoBlockSwap','WanVideoVAELoader','LoadWanVideoT5TextEncoder','WanVideoTextEncode','WanVideoImageToVideoEncode','WanVideoSampler','WanVideoDecode','WanVideoLoraSelect')
$arguments = @('-I','-B',"$environmentRoot/ComfyUI/main.py",'--cpu','--listen','127.0.0.1','--port',"$port",'--disable-auto-launch','--offline','--disable-all-custom-nodes','--whitelist-custom-nodes','ComfyUI-WanVideoWrapper-LVA07','--disable-assets','--cache-none','--models-directory','E:/VideoAI/shared/models/comfyui','--input-directory',"$probeRoot/input",'--output-directory',"$probeRoot/output",'--temp-directory',"$probeRoot/temp",'--user-directory',"$probeRoot/user",'--database-url',"sqlite:///$probeRoot/user/comfyui.db")
$plan = [ordered]@{ executable="$environmentRoot/python_embeded/python.exe"; argv=$arguments; probe_root=$probeRoot; private_commit_limit_bytes=4294967296; rss_stop_bytes=4294967296; max_seconds=180; cleanup_wait_seconds=10; http_timeout_seconds=2; disk_reserve_bytes=536870912; http_methods=@('GET'); nodes=$classes; graph_posts=0; actual_execution=[bool]$Run }
if (-not $Run) { $plan | ConvertTo-Json -Depth 8; return }

# Mutating path is intentionally separate from the default review/inspect path.
Get-Command Get-NetTCPConnection -ErrorAction Stop | Out-Null
if (Test-Path -LiteralPath $probeRoot) { throw 'New probe directory required; do not overwrite an earlier attempt' }
if (-not (Test-Path -LiteralPath "$environmentRoot/install.json")) { throw 'Completed approved installation required' }
if ((Get-Item -LiteralPath 'E:/').PSDrive.Free -lt 536870912) { throw '512 MiB free-space prerequisite failed' }
$reservation = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$port)
try { $reservation.Start() } finally { $reservation.Stop() }
$execution = Get-Content -Raw -LiteralPath 'E:/code/py/video-ai/docs/task-designs/LVA-07-03-preparation-execution.json' | ConvertFrom-Json
foreach ($stage in @('sources','runtime','wheels','install')) {
    $expectedMarker=$execution.stage_markers.PSObject.Properties[$stage].Value
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $expectedMarker.path).Hash.ToLowerInvariant() -ne $expectedMarker.sha256) { throw 'Executed environment marker identity changed' }
}
$sourceMarker = Get-Content -Raw -LiteralPath "$environmentRoot/sources.json" | ConvertFrom-Json
$wrapper = "$environmentRoot/ComfyUI/custom_nodes/ComfyUI-WanVideoWrapper-LVA07"
foreach ($entry in $sourceMarker.wrapper_files) {
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath "$wrapper/$($entry.path)").Hash.ToLowerInvariant() -ne $entry.sha256) { throw 'Pinned source changed before node probe' }
}
[IO.Directory]::CreateDirectory($probeRoot) | Out-Null
foreach ($name in @('input','output','temp','user','cache')) { [IO.Directory]::CreateDirectory("$probeRoot/$name") | Out-Null }
$utf8 = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText("$probeRoot/plan.json",($plan | ConvertTo-Json -Depth 8),$utf8)
$childEnv = @{ CUDA_VISIBLE_DEVICES=''; HF_HUB_OFFLINE='1'; TRANSFORMERS_OFFLINE='1'; HF_HOME="$probeRoot/cache"; TEMP="$probeRoot/temp"; TMP="$probeRoot/temp" }
$priorEnv = @{}
foreach ($name in $childEnv.Keys) { $priorEnv[$name]=[Environment]::GetEnvironmentVariable($name,'Process') }
$result = [ordered]@{ passed=$false; mode='cpu-only node registration/object_info'; port=$port; graph_posts=0; error=$null; pid=$null; process_start_utc=$null; exited=$false; port_closed=$false; peak_rss_observed_bytes=0; owned_pid_listener_verified=$false }
$owned = $null; $job = $null; $http = $null
try {
    foreach ($name in $childEnv.Keys) { [Environment]::SetEnvironmentVariable($name,$childEnv[$name],'Process') }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public sealed class Lva07ProbeJob : IDisposable {
  [StructLayout(LayoutKind.Sequential)] struct Basic { public long ProcessTime,JobTime; public uint Flags; public UIntPtr MinWS,MaxWS; public uint Active; public UIntPtr Affinity; public uint Priority,Scheduling; }
  [StructLayout(LayoutKind.Sequential)] struct IO { public ulong A,B,C,D,E,F; }
  [StructLayout(LayoutKind.Sequential)] struct Limits { public Basic Basic; public IO IO; public UIntPtr ProcessMemory,JobMemory,PeakProcess,PeakJob; }
  [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr a,string n);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(IntPtr h,int c,ref Limits p,uint l);
  [DllImport("kernel32.dll",SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr h,IntPtr p);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
  IntPtr handle;
  public Lva07ProbeJob() {
    handle=CreateJobObject(IntPtr.Zero,null);
    if(handle==IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
    Limits limits=new Limits(); limits.Basic.Flags=0x2000|0x100|0x8; limits.Basic.Active=1;
    limits.ProcessMemory=new UIntPtr(4294967296UL);
    if(!SetInformationJobObject(handle,9,ref limits,(uint)Marshal.SizeOf(typeof(Limits)))) {
      int error=Marshal.GetLastWin32Error(); Dispose(); throw new System.ComponentModel.Win32Exception(error);
    }
  }
  public void Assign(IntPtr process) { if(!AssignProcessToJobObject(handle,process)) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()); }
  public void Dispose() { if(handle!=IntPtr.Zero) { CloseHandle(handle); handle=IntPtr.Zero; } }
}
'@
    $job = [Lva07ProbeJob]::new()
    $owned = Start-Process -FilePath $plan.executable -ArgumentList $arguments -WorkingDirectory "$environmentRoot/ComfyUI" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$probeRoot/stdout.log" -RedirectStandardError "$probeRoot/stderr.log"
    $job.Assign($owned.Handle)
    $result.pid=$owned.Id; $result.process_start_utc=$owned.StartTime.ToUniversalTime().ToString('o')
    [IO.File]::WriteAllText("$probeRoot/owner.json",($result | ConvertTo-Json),$utf8)
    $deadline=[DateTime]::UtcNow.AddSeconds(180); $listening=$false
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($owned.HasExited) { throw "Owned probe exited before readiness (exit $($owned.ExitCode))" }
        $owned.Refresh(); $result.peak_rss_observed_bytes=[Math]::Max([long]$result.peak_rss_observed_bytes,$owned.WorkingSet64)
        if ($owned.WorkingSet64 -gt 4294967296) { throw 'RSS stop threshold exceeded' }
        foreach ($log in @('stdout.log','stderr.log')) { if ((Get-Item -LiteralPath "$probeRoot/$log").Length -gt 16777216) { throw 'Log size threshold exceeded' } }
        $listeners=@(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        if ($listeners.Count -gt 0) {
            if (@($listeners | Where-Object { $_.OwningProcess -ne $owned.Id -or $_.LocalAddress -ne '127.0.0.1' }).Count -gt 0) { throw 'Listener ownership/address mismatch' }
            $listening=$true; $result.owned_pid_listener_verified=$true; break
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $listening) { throw 'CPU probe readiness deadline exceeded' }
    Add-Type -AssemblyName System.Net.Http
    $handler=[Net.Http.HttpClientHandler]::new(); $handler.UseProxy=$false
    $http=[Net.Http.HttpClient]::new($handler); $http.Timeout=[TimeSpan]::FromSeconds(2); $http.MaxResponseContentBufferSize=2097152
    foreach ($name in $classes) {
        if ([DateTime]::UtcNow -ge $deadline) { throw 'Node probe total deadline exceeded' }
        $text=$http.GetStringAsync("http://127.0.0.1:$port/object_info/$name").GetAwaiter().GetResult()
        $schema=$text | ConvertFrom-Json
        if ($null -eq $schema.PSObject.Properties[$name]) { throw "Required Wrapper node missing: $name" }
        [IO.File]::WriteAllText("$probeRoot/$name.json",$text,$utf8)
    }
    $result.passed=$true
} catch {
    $result.error=$_.Exception.Message
} finally {
    if ($null -ne $http) { $http.Dispose() }
    try {
        if ($null -ne $owned) {
            if (-not $owned.HasExited) { $owned.Kill() }
            $result.exited=$owned.WaitForExit(10000)
            if ($result.exited) { $result.exit_code=$owned.ExitCode }
        }
    } catch { $result.cleanup_error=$_.Exception.Message } finally {
        if ($null -ne $job) { $job.Dispose() }
        foreach ($name in $priorEnv.Keys) { [Environment]::SetEnvironmentVariable($name,$priorEnv[$name],'Process') }
    }
    $result.port_closed=@(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).Count -eq 0
    [IO.File]::WriteAllText("$probeRoot/result.json",($result | ConvertTo-Json -Depth 8),$utf8)
}
if (-not $result.passed -or -not $result.exited -or -not $result.port_closed) { throw 'Probe failed or cleanup not established; inspect preserved result/logs, do not retry automatically' }
$result | ConvertTo-Json -Depth 8
