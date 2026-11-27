param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('prepare', 'baseline', 'voxcpm', 'package')]
    [string] $Phase,
    [string] $OutputDirectory,
    [string] $LongText,
    [double] $LongSeconds = 1800
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\bootstrap.ps1')
Initialize-VideoAiEnvironment 'voxcpm2-quality'
$voxPython = Join-Path $VideoAiRuntimeRoot 'shared\envs\voxcpm2\Scripts\python.exe'
$voxArguments = @('-B', '-u', (Join-Path $PSScriptRoot 'voxcpm2_quality.py'), $Phase)
if ($OutputDirectory) { $voxArguments += @('--output', $OutputDirectory) }
if ($LongText) { $voxArguments += @('--long-text', $LongText) }
$voxArguments += @('--long-seconds', $LongSeconds.ToString([Globalization.CultureInfo]::InvariantCulture))
& $voxPython @voxArguments
exit $LASTEXITCODE
