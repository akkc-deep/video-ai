param(
    [string] $Text,
    [string] $Instruction,
    [string] $ReferenceAudio
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\bootstrap.ps1')
Initialize-VideoAiEnvironment 'voxcpm2-smoke'
$voxPython = Join-Path $VideoAiRuntimeRoot 'shared\envs\voxcpm2\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $voxPython)) {
    throw 'VoxCPM2 environment is missing. See docs/voxcpm2-deployment.md.'
}
$voxArguments = @('-B', '-u', (Join-Path $PSScriptRoot 'voxcpm2_smoke.py'))
if ($PSBoundParameters.ContainsKey('Text')) { $voxArguments += @('--text', $Text) }
if ($PSBoundParameters.ContainsKey('Instruction')) { $voxArguments += @('--instruction', $Instruction) }
if ($ReferenceAudio) { $voxArguments += @('--reference-audio', $ReferenceAudio) }
& $voxPython @voxArguments
exit $LASTEXITCODE
