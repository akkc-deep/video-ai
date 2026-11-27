param(
    [Parameter(Mandatory=$true)][string] $StateDirectory,
    [int] $Port = 9881
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'bootstrap.ps1')
Initialize-VideoAiEnvironment 'voxcpm2-service'
$voxPython = Join-Path $VideoAiRuntimeRoot 'shared\envs\voxcpm2\Scripts\python.exe'
$env:PYTHONPATH = (Join-Path $VideoAiSourceRoot 'src')
& $voxPython -B -u -m video_ai.voxcpm.server --state-dir $StateDirectory --port $Port
exit $LASTEXITCODE
