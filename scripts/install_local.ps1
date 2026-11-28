param([string] $HfEndpoint = 'https://hf-mirror.com', [string] $VoiceAssets = '')

$ErrorActionPreference = 'Stop'

# Load the existing installer without launching its entrypoint.
. (Join-Path $PSScriptRoot 'install_online.ps1') -NoLaunch -HfEndpoint $HfEndpoint -VoiceAssets $VoiceAssets

# This checkout already contains the source. Keep it and install dependencies.
$originalArchiveInstaller = ${function:Install-OnlineArchive}
function Install-OnlineArchive {
    param([string] $Url, [string] $Name, [string] $Target, [string] $Marker)
    if ([IO.Path]::GetFullPath($Target) -eq $OnlineSourceRoot) {
        Write-Host 'Using current source checkout.'
        return
    }
    & $originalArchiveInstaller $Url $Name $Target $Marker
}

try {
    Install-VideoAiOnline
} catch {
    [Console]::Error.WriteLine($_.ToString())
    exit 1
}
