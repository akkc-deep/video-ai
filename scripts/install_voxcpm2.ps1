param(
    [string] $VoiceAssets = '',
    [string] $Config = '',
    [string] $PublishTo = '',
    [string] $HfEndpoint = 'https://hf-mirror.com',
    [switch] $Offline,
    [switch] $VerifyOnly,
    [switch] $NoActivate
)
$ErrorActionPreference = 'Stop'
$VoxSourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$VoxRuntimeRoot = if ($env:VIDEO_AI_RUNTIME_ROOT) { [IO.Path]::GetFullPath($env:VIDEO_AI_RUNTIME_ROOT) } else { 'E:\VideoAI' }
if (-not $Config) { $Config = Join-Path $VoxRuntimeRoot 'shared/config/production.json' }
# Reuse the existing downloader and native exit handling, without its entrypoint.
. (Join-Path $PSScriptRoot 'install_online.ps1') -NoLaunch -HfEndpoint $HfEndpoint -VoiceAssets $VoiceAssets
$env:PYTHONPATH = Join-Path $VoxSourceRoot 'src'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$VoxBase = Join-Path $VoxRuntimeRoot 'shared/tools/python312/python.exe'
$VoxPython = Join-Path $VoxRuntimeRoot 'shared/envs/voxcpm2/Scripts/python.exe'
$VoxOrchestrator = Join-Path $VoxRuntimeRoot 'shared/envs/video-ai/Scripts/python.exe'
$VoxDeployment = @('-B','-m','video_ai.voxcpm.deployment')
$VoxCommon = @('--runtime-root',$VoxRuntimeRoot,'--source-root',$VoxSourceRoot,'--config',$Config)

function Test-VoxEnvironment {
    if (-not (Test-Path -LiteralPath $VoxPython)) { return $false }
    $probe = 'import sys; from pathlib import Path; from importlib.metadata import version; rows=Path(sys.argv[1]).read_text().splitlines(); pins=[r.split(''=='',1) for r in rows if r.strip() and not r.startswith(''#'')]; pins += [(''torch'',''2.9.1+cu128''),(''torchaudio'',''2.9.1+cu128''),(''voxcpm'',''2.0.3.post46+g300e4260b'')]; assert all(version(n)==v for n,v in pins)'
    $saved=$ErrorActionPreference; $ErrorActionPreference='Continue'
    try { & $VoxPython -B -c $probe (Join-Path $VoxSourceRoot 'config/voxcpm2-environment.lock.txt') *> $null; return $LASTEXITCODE -eq 0 }
    finally { $ErrorActionPreference=$saved }
}

function Install-VoxDependencies {
    Get-Command git.exe -ErrorAction Stop | Out-Null
    $spec = Get-Content -LiteralPath (Join-Path $VoxSourceRoot 'config/voxcpm2-deployment.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $official = Join-Path $VoxRuntimeRoot 'shared/tools/VoxCPM'
    $sourceReceipt = Join-Path $official '.vox-source-install.json'
    if (-not (Test-Path -LiteralPath $official)) {
        [IO.Directory]::CreateDirectory($official) | Out-Null
        Write-OnlineText $sourceReceipt (@{source_revision=$spec.source_revision;state='installing'} | ConvertTo-Json)
    }
    if (Test-Path -LiteralPath $sourceReceipt) {
        $owned=Get-Content -LiteralPath $sourceReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($owned.source_revision -ne $spec.source_revision) { throw 'Vox source installer version conflicts.' }
        if ($owned.state -eq 'installing') {
            if (-not (Test-Path -LiteralPath (Join-Path $official '.git'))) { Invoke-OnlineNative 'git.exe' @('init',$official) }
            # setuptools_scm needs the original tags/history to reproduce the locked package version.
            Invoke-OnlineNative 'git.exe' @('-C',$official,'fetch','--tags',$spec.source_url,$spec.source_revision)
            Invoke-OnlineNative 'git.exe' @('-C',$official,'checkout','--detach',$spec.source_revision)
            Write-OnlineText $sourceReceipt (@{source_revision=$spec.source_revision;state='installed'} | ConvertTo-Json)
        }
    }
    $revision = & git.exe -C $official rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $revision -ne $spec.source_revision) { throw 'Existing VoxCPM source differs from the locked revision; refusing to overwrite it.' }
    $envRoot = Split-Path -Parent (Split-Path -Parent $VoxPython)
    $envReceipt = Join-Path $envRoot '.vox-install.json'
    if (-not (Test-VoxEnvironment)) {
        if ((Test-Path -LiteralPath $envRoot) -and -not (Test-Path -LiteralPath $envReceipt)) { throw 'Existing unmanaged Vox environment differs; keep it and deploy to a separate runtime root.' }
        if (Test-Path -LiteralPath $envReceipt) {
            $owned=Get-Content -LiteralPath $envReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($owned.source_revision -ne $spec.source_revision) { throw 'Vox environment installer version conflicts.' }
        }
        Write-OnlineText $envReceipt (@{source_revision=$spec.source_revision;state='installing'} | ConvertTo-Json)
        # venv may have copied python.exe before ensurepip was interrupted.
        # Re-running without --clear repairs that owned partial environment.
        Invoke-OnlineNative $VoxBase @('-B','-m','venv',$envRoot)
        Invoke-OnlineNative $VoxPython @('-B','-m','pip','install','--no-deps','-r',(Join-Path $VoxSourceRoot 'config/voxcpm2-environment.lock.txt'))
        Invoke-OnlineNative $VoxPython @('-B','-m','pip','install','--no-deps','torch==2.9.1','torchaudio==2.9.1','--index-url','https://download.pytorch.org/whl/cu128')
        Invoke-OnlineNative $VoxPython @('-B','-m','pip','install','--no-deps','--no-build-isolation',$official)
        Write-OnlineText $envReceipt (@{source_revision=$spec.source_revision;state='installed'} | ConvertTo-Json)
    }
    foreach ($property in $spec.model_files.PSObject.Properties) {
        $target = Join-Path $VoxRuntimeRoot ('shared/models/VoxCPM2/' + $property.Name)
        if (-not (Test-Path -LiteralPath $target)) {
            Get-OnlineDownload (Get-OnlineHfUrl $spec.model_id $spec.model_revision $property.Name) $target | Out-Null
        }
    }
    $alignment = Get-Content -LiteralPath (Join-Path $VoxSourceRoot 'config/voxcpm2-alignment.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($property in $alignment.files.PSObject.Properties) {
        $target = Join-Path $VoxRuntimeRoot ('shared/models/funasr/timestamp/' + $property.Name)
        if (-not (Test-Path -LiteralPath $target)) {
            $url = 'https://modelscope.cn/models/' + $alignment.model_id + '/resolve/' + $alignment.revision + '/' + $property.Name
            Get-OnlineDownload $url $target | Out-Null
        }
    }
    $alignPython = Join-Path $VoxRuntimeRoot 'shared/tools/GPT-SoVITS/runtime/python.exe'
    Invoke-OnlineNative $alignPython @('-B','-m','pip','install','funasr==1.0.27')
}

function Install-VideoAiVox {
    if (-not $VerifyOnly) {
        $assetArgs = @(); if ($VoiceAssets) { $assetArgs = @('--voice-assets',[IO.Path]::GetFullPath($VoiceAssets)) }
        Invoke-OnlineNative $VoxOrchestrator ($VoxDeployment + @('provision') + $VoxCommon + $assetArgs)
        if (-not $Offline) { Install-VoxDependencies }
        Invoke-OnlineNative $VoxOrchestrator ($VoxDeployment + @('relocate') + $VoxCommon)
    }
    $checkArgs = @(); if (-not $VerifyOnly) { $checkArgs = @('--hash-models') }
    if (-not $VerifyOnly -and -not $NoActivate) {
        $checkArgs += @('--activate')
        if ($PublishTo) { $checkArgs += @('--publish-to',$PublishTo) }
    }
    Invoke-OnlineNative $VoxOrchestrator ($VoxDeployment + @('verify') + $VoxCommon + $checkArgs)
    Write-Host 'VoxCPM2 installation verified. Historical video runs retain their frozen backend.'
}

if ($MyInvocation.InvocationName -ne '.') {
    try { Install-VideoAiVox; exit 0 }
    catch { [Console]::Error.WriteLine($_.ToString()); exit 1 }
}
