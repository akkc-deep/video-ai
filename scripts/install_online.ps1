param(
    [string] $HfEndpoint = 'https://hf-mirror.com',
    [string] $SourceRef = '242f8a05f2ac69bb3ec3aa6d79c9a3257f1760b3',
    [string] $ReferenceAudioUrl = '',
    [string] $ReferenceText = '',
    [string] $Script = '',
    [switch] $NoLaunch
)

# Standalone: no files, models or environment from the old PC are needed.
$ErrorActionPreference = 'Stop'
$OnlineRuntimeRoot = 'D:\VideoSi'
$OnlineSourceRoot = 'D:\code\py\video-ai'
$OnlineDownloads = 'D:\VideoSi\disposable\video-ai\downloads\online-install'
$OnlineUtf8 = [Text.UTF8Encoding]::new($false)
$OnlineSevenZip = Join-Path $OnlineRuntimeRoot 'tools\7zip\7za.exe'
$OnlinePython = Join-Path $OnlineRuntimeRoot 'tools\python312\python.exe'

function Write-OnlineText([string] $Path, [string] $Value) {
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Path)) | Out-Null
    [IO.File]::WriteAllText($Path, $Value, $OnlineUtf8)
}

function Invoke-OnlineNative([string] $Executable, [string[]] $Arguments, [int[]] $SuccessCodes = @(0)) {
    Get-Command $Executable -ErrorAction Stop | Out-Null
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Executable @Arguments 2>&1 | ForEach-Object { [Console]::WriteLine($_.ToString()) }; $code = $LASTEXITCODE }
    finally { $ErrorActionPreference = $saved }
    if ($code -notin $SuccessCodes) { throw "Command failed with exit ${code}: $Executable" }
}

function Get-OnlineHfUrl([string] $Repository, [string] $Revision, [string] $File, [string] $Endpoint = $HfEndpoint) {
    $uri = [uri]$Endpoint
    if ($uri.Scheme -ne 'https' -or $uri.UserInfo -or $uri.Query -or $uri.Fragment) { throw 'HfEndpoint must be an HTTPS origin.' }
    $encoded = (($File.Split('/') | ForEach-Object { [uri]::EscapeDataString($_) }) -join '/')
    return $Endpoint.TrimEnd('/') + '/' + $Repository + '/resolve/' + [uri]::EscapeDataString($Revision) + '/' + $encoded
}

function Get-OnlineDownload([string] $Url, [string] $Destination) {
    if (([uri]$Url).Scheme -ne 'https') { throw 'Downloads require HTTPS.' }
    $receipt = $Destination + '.download.json'
    $pending = $Destination + '.download.pending.json'
    $partial = $Destination + '.part'
    if ((Test-Path -LiteralPath $pending) -and -not (Test-Path -LiteralPath $receipt)) {
        $commit = Get-Content -LiteralPath $pending -Raw -Encoding UTF8 | ConvertFrom-Json
        $finished = if (Test-Path -LiteralPath $Destination) { $Destination } else { $partial }
        if ($commit.url -eq $Url -and (Test-Path -LiteralPath $finished) -and $commit.bytes -eq (Get-Item -LiteralPath $finished).Length) {
            if ($finished -eq $partial) { [IO.File]::Move($partial, $Destination) }
            [IO.File]::Move($pending, $receipt)
            return $Destination
        }
    }
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        if (Test-Path -LiteralPath $receipt -PathType Leaf) {
            $previous = Get-Content -LiteralPath $receipt -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($previous.url -eq $Url -and $previous.bytes -eq (Get-Item -LiteralPath $Destination).Length) { return $Destination }
        }
        throw "Existing unmanaged or changed download: $Destination. Installation will not overwrite it."
    }
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Destination)) | Out-Null
    $origin = $partial + '.url'
    if (Test-Path -LiteralPath $partial) {
        if (-not (Test-Path -LiteralPath $origin) -or (Get-Content -LiteralPath $origin -Raw -Encoding UTF8) -ne $Url) {
            throw "Partial download belongs to another URL: $partial"
        }
    }
    Write-OnlineText $origin $Url
    Write-Host ('Download: ' + [IO.Path]::GetFileName($Destination))
    Invoke-OnlineNative 'curl.exe' @('--fail', '--location', '--retry', '3', '--retry-delay', '3', '--connect-timeout', '30', '--continue-at', '-', '--output', $partial, $Url)
    if (-not (Test-Path -LiteralPath $partial) -or (Get-Item -LiteralPath $partial).Length -eq 0) { throw "Empty download: $Destination" }
    Write-OnlineText $pending (@{ url = $Url; bytes = (Get-Item -LiteralPath $partial).Length } | ConvertTo-Json)
    [IO.File]::Move($partial, $Destination)
    [IO.File]::Move($pending, $receipt)
    return $Destination
}

function Find-OnlineArchiveRoot([string] $Stage, [string] $Marker) {
    $candidates = @($Stage) + @(Get-ChildItem -LiteralPath $Stage -Directory | ForEach-Object FullName)
    $found = @($candidates | Where-Object { Test-Path -LiteralPath (Join-Path $_ $Marker) -PathType Leaf })
    if ($found.Count -ne 1) { throw "Unexpected archive structure: $Stage (expected $Marker)" }
    return $found[0]
}

function Install-OnlineArchive([string] $Url, [string] $Name, [string] $Target, [string] $Marker) {
    $receipt = Join-Path $Target '.online-install.json'
    if (Test-Path -LiteralPath $Target) {
        if ((Test-Path -LiteralPath $receipt) -and (Test-Path -LiteralPath (Join-Path $Target $Marker))) {
            $installed = Get-Content -LiteralPath $receipt -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($installed.url -eq $Url) { return }
        }
        throw "Existing installation is not owned by this installer/version: $Target"
    }
    $archive = Get-OnlineDownload $Url (Join-Path $OnlineDownloads $Name)
    $stage = Join-Path $OnlineDownloads ('extract-' + [IO.Path]::GetFileNameWithoutExtension($Name))
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    Invoke-OnlineNative $OnlineSevenZip @('x', $archive, ('-o' + $stage), '-y')
    $root = Find-OnlineArchiveRoot $stage $Marker
    $absolute = [IO.Path]::GetFullPath($Target)
    # Verify the absolute destination before moving the staged directory.
    if (-not ($absolute.StartsWith($OnlineRuntimeRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or $absolute -eq $OnlineSourceRoot)) {
        throw "Installation target escapes the configured roots: $absolute"
    }
    [IO.Directory]::CreateDirectory((Split-Path -Parent $absolute)) | Out-Null
    # Move ownership metadata with the directory so a retry recognizes it.
    Write-OnlineText (Join-Path $root '.online-install.json') (@{ url = $Url } | ConvertTo-Json)
    [IO.Directory]::Move($root, $absolute)
}

function Install-OnlinePrerequisites {
    $vc = Get-OnlineDownload 'https://aka.ms/vs/17/release/vc_redist.x64.exe' (Join-Path $OnlineDownloads 'VC_redist.x64.exe')
    $signature = Get-AuthenticodeSignature -LiteralPath $vc
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { throw 'Microsoft runtime installer signature is invalid.' }
    $options = @{ FilePath=$vc; ArgumentList=@('/install','/quiet','/norestart'); Wait=$true; PassThru=$true; WindowStyle='Hidden' }
    $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { $options.Verb='RunAs' }
    $process = Start-Process @options
    if ($process.ExitCode -eq 3010) { throw 'Windows requires a restart after installing its runtime. Restart and run this installer again.' }
    if ($process.ExitCode -notin @(0,1638)) { throw "Microsoft runtime installation failed: $($process.ExitCode)" }
    if (-not (Test-Path -LiteralPath $OnlinePython)) {
        $installer = Get-OnlineDownload 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' (Join-Path $OnlineDownloads 'python-3.12.10-amd64.exe')
        Invoke-OnlineNative $installer @('/quiet', 'InstallAllUsers=0', ('TargetDir=' + (Split-Path -Parent $OnlinePython)), 'Include_pip=1', 'Include_launcher=0', 'Include_test=0', 'PrependPath=0', '/log', (Join-Path $OnlineDownloads 'python-install.log'))
    }
    Invoke-OnlineNative $OnlinePython @('-B','-c','import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize(''P'') == 8')
    if (-not (Test-Path -LiteralPath $OnlineSevenZip)) {
        $seven = Get-OnlineDownload 'https://github.com/ip7z/7zip/releases/download/26.05/7zr.exe' (Join-Path $OnlineDownloads '7zr-26.05.exe')
        $extra = Get-OnlineDownload 'https://github.com/ip7z/7zip/releases/download/26.05/7z2605-extra.7z' (Join-Path $OnlineDownloads '7z2605-extra.7z')
        Invoke-OnlineNative $seven @('x',$extra,('-o' + (Split-Path -Parent $OnlineSevenZip)),'-y')
    }
}

function Get-OnlineChineseFont {
    $font = Join-Path $env:WINDIR 'Fonts\msyh.ttc'
    if (Test-Path -LiteralPath $font) { return $font }
    Write-Host 'Downloading the Windows Simplified Chinese font component (administrator approval may appear)...'
    $process = Start-Process powershell.exe -ArgumentList @('-NoProfile','-Command', 'Add-WindowsCapability -Online -Name Language.Fonts.Hans~~~und-HANS~0.0.1.0 -ErrorAction Stop | Out-Null') -Verb RunAs -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $font)) { throw 'Windows could not install Microsoft YaHei. Enable Windows Update and rerun the installer.' }
    return $font
}

function Install-OnlineModels {
    $models = Join-Path $OnlineRuntimeRoot 'models'
    $wanRevision = 'ee6f4a40737a995bf5818954cfce6d59443b0f04'
    foreach ($file in @(
        'diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors',
        'diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors',
        'text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors',
        'vae/wan_2.1_vae.safetensors'
    )) {
        $url = Get-OnlineHfUrl 'Comfy-Org/Wan_2.2_ComfyUI_Repackaged' $wanRevision ('split_files/' + $file)
        Get-OnlineDownload $url (Join-Path $models ('comfyui/' + $file)) | Out-Null
    }
    $url = Get-OnlineHfUrl 'stabilityai/stable-diffusion-xl-base-1.0' '462165984030d82259a11f4367a4eed129e94a7b' 'sd_xl_base_1.0.safetensors'
    Get-OnlineDownload $url (Join-Path $models 'comfyui/checkpoints/sd_xl_base_1.0.safetensors') | Out-Null
    Get-OnlineDownload 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth' (Join-Path $models 'comfyui/upscale_models/RealESRGAN_x4plus.pth') | Out-Null
    $revision = '8f8857563c040d542de108a2c18b0425abd6c9c5'
    $treeUrl = $HfEndpoint.TrimEnd('/') + '/api/models/lj1995/GPT-SoVITS/tree/' + $revision + '?recursive=true&limit=1000'
    $treeFile = Get-OnlineDownload $treeUrl (Join-Path $OnlineDownloads 'tts-model-tree.json')
    $tree = Get-Content -LiteralPath $treeFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $selected = @($tree | Where-Object {
        $_.type -eq 'file' -and ($_.path.StartsWith('chinese-hubert-base/') -or
        $_.path.StartsWith('chinese-roberta-wwm-ext-large/') -or
        $_.path -in @('gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt','gsv-v2final-pretrained/s2G2333k.pth'))
    })
    if ($selected.Count -lt 7) { throw 'Incomplete GPT-SoVITS model listing.' }
    foreach ($entry in $selected) {
        # Reject unexpected repository paths before using remote metadata locally.
        if ($entry.path -match '(^|/)\.\.(/|$)|[\\:]') { throw 'Invalid model repository path.' }
        Get-OnlineDownload (Get-OnlineHfUrl 'lj1995/GPT-SoVITS' $revision $entry.path) (Join-Path $models ('tts/' + $entry.path)) | Out-Null
    }
}

function New-OnlineConfiguration([string] $Reference, [string] $Transcript, [string] $Font) {
    $project = Join-Path $OnlineRuntimeRoot 'projects\video-ai'
    $configRoot = Join-Path $project 'config'
    $configPath = Join-Path $configRoot 'production.json'
    $owner = Join-Path $configRoot '.online-config.json'
    foreach ($name in @('production.json','voice.json','tts-api.yaml')) {
        if ((Test-Path -LiteralPath (Join-Path $configRoot $name)) -and -not (Test-Path -LiteralPath $owner)) {
            throw "Existing configuration is not owned by this installer: $name"
        }
    }
    $config = Get-Content -LiteralPath (Join-Path $OnlineSourceRoot 'config/production.example.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $voice = Get-Content -LiteralPath (Join-Path $OnlineSourceRoot 'config/voice.example.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $config.runtime_root = $OnlineRuntimeRoot
    $config.project_root = $project
    $config.output_root = Join-Path $OnlineRuntimeRoot 'output/video-ai'
    $config.cache_root = Join-Path $OnlineRuntimeRoot 'cache/video-ai'
    $config.voice_config = Join-Path $configRoot 'voice.json'
    $config.services.ollama = 'http://127.0.0.1:11435'
    $config.media.font_file = $Font
    foreach ($property in $config.tools.PSObject.Properties) { $property.Value = $property.Value.Replace('D:/VideoSi', $OnlineRuntimeRoot.Replace('\','/')) }
    foreach ($property in $config.models.PSObject.Properties) { $property.Value = $property.Value.Replace('D:/VideoSi', $OnlineRuntimeRoot.Replace('\','/')) }
    foreach ($property in $config.workflows.PSObject.Properties) { $property.Value = Join-Path $OnlineSourceRoot ('workflows/' + [IO.Path]::GetFileName($property.Value)) }
    foreach ($field in @('gpt_weights','sovits_weights','bert_root','hubert_root')) { $voice.$field = $voice.$field.Replace('D:/VideoSi', $OnlineRuntimeRoot.Replace('\','/')) }
    $voice.reference_audio = $Reference
    $voice.reference_sha256 = (Get-FileHash -LiteralPath $Reference -Algorithm SHA256).Hash.ToLowerInvariant()
    $voice.reference_text = $Transcript
    $voice.device = 'cpu'; $voice.is_half = $false
    $yaml = "custom:`n  device: cpu`n  is_half: false`n  version: v2`n  t2s_weights_path: '$($voice.gpt_weights)'`n  vits_weights_path: '$($voice.sovits_weights)'`n  bert_base_path: '$($voice.bert_root)'`n  cnhuhbert_base_path: '$($voice.hubert_root)'`n"
    Write-OnlineText $owner (@{ schema_version=1; source_ref=$SourceRef; state='configuring' } | ConvertTo-Json)
    Write-OnlineText (Join-Path $configRoot 'tts-api.yaml') $yaml
    Write-OnlineText (Join-Path $configRoot 'voice.json') ($voice | ConvertTo-Json -Depth 20)
    Write-OnlineText $configPath ($config | ConvertTo-Json -Depth 20)
    Write-OnlineText $owner (@{ schema_version=1; source_ref=$SourceRef; state='configured' } | ConvertTo-Json)
    $launcher = @'
param([string] $Script = '', [string] $Text = '', [string] $Video = '', [string] $Title = '')
$ErrorActionPreference = 'Stop'
try {
    if ($Video) {
        if ($Script -or $Text -or $Title) { throw 'Use -Video to continue an existing video.' }
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '__SOURCE__/scripts/start_windows.ps1' make-video --video $Video
        exit $LASTEXITCODE
    }
    if ($Script -and $Text) { throw 'Use -Script or -Text, not both.' }
    if (-not $Script -and -not $Text) {
        $inputValue = Read-Host 'Enter narration text or a UTF-8 text file path'
        $path = $inputValue.Trim('"')
        if (Test-Path -LiteralPath $path -PathType Leaf) { $Script = $path }
        elseif ($path -match '^[A-Za-z]:[\\/]|\.txt$') { throw ('File not found: ' + $path) }
        else { $Text = $inputValue }
    }
    if ($Text) {
        $folder = '__RUNTIME__/disposable/video-ai/tmp/narration'
        [IO.Directory]::CreateDirectory($folder) | Out-Null
        $Script = Join-Path $folder ('narration-' + [guid]::NewGuid().ToString('N') + '.txt')
        [IO.File]::WriteAllText($Script,$Text,[Text.UTF8Encoding]::new($false))
    }
    if (-not $Script) { throw 'Narration cannot be empty.' }
    $cliArgs = @('make-video','--config','__PROJECT__/config/production.json','--script',([IO.Path]::GetFullPath($Script)))
    if ($Title) { $cliArgs += @('--title',$Title) }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File '__SOURCE__/scripts/start_windows.ps1' @cliArgs
    exit $LASTEXITCODE
} catch { [Console]::Error.WriteLine($_.ToString()); exit 1 }
'@
    $launcher = $launcher.Replace('__SOURCE__', $OnlineSourceRoot.Replace('\','/')).Replace('__PROJECT__', $project.Replace('\','/')).Replace('__RUNTIME__', $OnlineRuntimeRoot.Replace('\','/'))
    Write-OnlineText (Join-Path $project 'generate_online.ps1') $launcher
    $cmd = "@echo off`r`nchcp 65001 >nul`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$project\generate_online.ps1`" %*`r`nset `"video_exit=%errorlevel%`"`r`npause`r`nexit /b %video_exit%`r`n"
    Write-OnlineText (Join-Path $project 'generate_video.cmd') $cmd
}

function Install-OnlinePlanner {
    $executable = Join-Path $OnlineRuntimeRoot 'tools/ollama/ollama.exe'
    $env:OLLAMA_MODELS = Join-Path $OnlineRuntimeRoot 'models/ollama'
    $env:OLLAMA_HOST = '127.0.0.1:11435'
    $probe = [Net.Sockets.TcpClient]::new()
    try { $probe.Connect('127.0.0.1',11435); throw 'Port 11435 is already in use. Stop that Ollama server before installation.' }
    catch [Net.Sockets.SocketException] { } finally { $probe.Dispose() }
    $server = Start-Process -FilePath $executable -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $OnlineDownloads 'ollama.stdout.log') -RedirectStandardError (Join-Path $OnlineDownloads 'ollama.stderr.log')
    try {
        $ready = $false
        for ($attempt=0; $attempt -lt 60; $attempt++) {
            if ($server.HasExited) { throw 'Installer-owned Ollama server exited. See ollama.stderr.log.' }
            try { Invoke-RestMethod 'http://127.0.0.1:11435/api/version' -TimeoutSec 2 | Out-Null; $ready=$true; break } catch { Start-Sleep -Seconds 1 }
        }
        if (-not $ready) { throw 'Ollama startup timed out. See ollama.stderr.log.' }
        Invoke-OnlineNative $executable @('pull','qwen3:8b')
    } finally { if (-not $server.HasExited) { $server.Kill(); $server.WaitForExit() }; $server.Dispose() }
}

function Install-VideoAiOnline {
    if (-not [Environment]::Is64BitOperatingSystem -or -not (Test-Path -LiteralPath 'D:\')) { throw 'Windows x64 and a local D: drive are required.' }
    $leaseRoot = Join-Path $OnlineRuntimeRoot 'projects/video-ai/storage'
    [IO.Directory]::CreateDirectory($leaseRoot) | Out-Null
    $storageLease = [IO.File]::Open((Join-Path $leaseRoot 'lifecycle.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
    try { $storageLease.Lock(0, 1) }
    catch { $storageLease.Dispose(); throw 'Video storage is occupied. Retry installation after the current operation finishes.' }
    try {
    Get-Command curl.exe -ErrorAction Stop | Out-Null
    $gpuTool = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
    if (-not $gpuTool) { throw 'Install the NVIDIA driver for this PC first; nvidia-smi.exe is unavailable.' }
    Invoke-OnlineNative $gpuTool.Source @('--query-gpu=name,memory.total','--format=csv,noheader')
    [IO.Directory]::CreateDirectory($OnlineDownloads) | Out-Null
    [Console]::OutputEncoding = $OnlineUtf8; $script:OutputEncoding = $OnlineUtf8
    $env:PYTHONUTF8='1'; $env:PYTHONDONTWRITEBYTECODE='1'
    $env:TEMP=Join-Path $OnlineDownloads 'temp'; $env:TMP=$env:TEMP
    [IO.Directory]::CreateDirectory($env:TEMP) | Out-Null
    $env:PIP_CACHE_DIR=Join-Path $OnlineDownloads 'pip'
    $env:HF_HOME=Join-Path $OnlineRuntimeRoot 'cache/video-ai/huggingface'
    $env:TORCH_HOME=Join-Path $OnlineRuntimeRoot 'cache/video-ai/torch'
    if ($ReferenceAudioUrl -and -not $ReferenceText) { throw 'A custom ReferenceAudioUrl requires its exact ReferenceText.' }
    if (-not $ReferenceAudioUrl) {
        $ReferenceAudioUrl='https://raw.githubusercontent.com/QwenAudio/CosyVoice/074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc/asset/zero_shot_prompt.wav'
        $ReferenceText=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('5biM5pyb5L2g5Lul5ZCO6IO95aSf5YGa55qE5q+U5oiR6L+Y5aW95ZGm44CC'))
    }
    Install-OnlinePrerequisites
    Install-OnlineArchive ('https://codeload.github.com/akkc-deep/video-ai/zip/' + [uri]::EscapeDataString($SourceRef)) ('video-ai-' + $SourceRef + '.zip') $OnlineSourceRoot 'pyproject.toml'
    Install-OnlineArchive 'https://github.com/Comfy-Org/ComfyUI/releases/download/v0.44.0/ComfyUI_windows_portable_nvidia.7z' 'comfyui-v0.44.0-nvidia.7z' (Join-Path $OnlineRuntimeRoot 'tools/ComfyUI_windows_portable') 'ComfyUI/main.py'
    $ttsUrl = Get-OnlineHfUrl 'lj1995/GPT-SoVITS-windows-package' 'c8b61d4f627d1f02e74c1ba158a4844051d2289f' 'GPT-SoVITS-v2pro-20250604-nvidia50.7z'
    Install-OnlineArchive $ttsUrl 'GPT-SoVITS-v2pro-20250604-nvidia50.7z' (Join-Path $OnlineRuntimeRoot 'tools/GPT-SoVITS') 'api_v2.py'
    Install-OnlineArchive 'https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip' 'ffmpeg-9.0.2.zip' (Join-Path $OnlineRuntimeRoot 'tools/ffmpeg') 'bin/ffmpeg.exe'
    Install-OnlineArchive 'https://github.com/ollama/ollama/releases/download/v0.40.14/ollama-windows-amd64.zip' 'ollama-v0.40.14.zip' (Join-Path $OnlineRuntimeRoot 'tools/ollama') 'ollama.exe'
    Install-OnlineModels
    $reference = Get-OnlineDownload $ReferenceAudioUrl (Join-Path $OnlineRuntimeRoot 'projects/video-ai/inputs/online-reference.wav')
    $font = Get-OnlineChineseFont
    New-OnlineConfiguration $reference $ReferenceText $font
    $envRoot=Join-Path $OnlineRuntimeRoot 'envs/video-ai'
    $python=Join-Path $envRoot 'Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $python)) { Invoke-OnlineNative $OnlinePython @('-B','-m','venv',$envRoot) }
    Invoke-OnlineNative $python @('-B','-m','pip','install','--disable-pip-version-check','--editable',($OnlineSourceRoot + '[continuity]'))
    Invoke-OnlineNative (Join-Path $OnlineRuntimeRoot 'tools/ComfyUI_windows_portable/python_embeded/python.exe') @('-B','-c','import torch; assert torch.cuda.is_available(), ''CUDA unavailable: install a compatible NVIDIA driver''; print(''CUDA runtime: ready'')')
    Invoke-OnlineNative (Join-Path $OnlineRuntimeRoot 'tools/GPT-SoVITS/runtime/python.exe') @('-B','-c','import torch, yaml, transformers; print(''TTS runtime: ready'')')
    Install-OnlinePlanner
    $env:PYTHONPATH=Join-Path $OnlineSourceRoot 'src'
    $config=Join-Path $OnlineRuntimeRoot 'projects/video-ai/config/production.json'
    Invoke-OnlineNative $python @('-B','-c','import sys; from video_ai.config import load_config; load_config(__import__(''pathlib'').Path(sys.argv[1])); print(''Configuration: ready'')',$config)
    Write-OnlineText (Join-Path $OnlineRuntimeRoot 'online-install.json') (@{schema_version=1; source_ref=$SourceRef; state='ready'; inference_verified=$false} | ConvertTo-Json)
    Write-Host 'Online installation complete. Start: D:\VideoSi\projects\video-ai\generate_video.cmd' -ForegroundColor Green
    } finally { try { $storageLease.Unlock(0, 1) } finally { $storageLease.Dispose() } }
    if (-not $NoLaunch) {
        $launchArgs=@('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $OnlineRuntimeRoot 'projects/video-ai/generate_online.ps1'))
        if ($Script) { $launchArgs+=@('-Script',[IO.Path]::GetFullPath($Script)) }
        & powershell.exe @launchArgs
        $script:OnlineExitCode=$LASTEXITCODE
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    $script:OnlineExitCode=0
    try { Install-VideoAiOnline }
    catch { [Console]::Error.WriteLine($_.ToString()); $script:OnlineExitCode=1 }
    exit $script:OnlineExitCode
}
