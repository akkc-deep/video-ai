param(
    [string] $Python = '',
    [string] $Wheelhouse = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'bootstrap.ps1')
$exitCode = 1
try {
    Initialize-VideoAiEnvironment 'install'
    if (-not $Python) {
        $Python = (Get-Command python.exe -ErrorAction Stop).Source
    }
    $Python = [IO.Path]::GetFullPath($Python)
    Assert-VideoAiPython $Python
    if (-not (Test-Path -LiteralPath $VideoAiPython -PathType Leaf)) {
        $target = Assert-VideoAiRuntimePath $VideoAiEnvRoot
        Invoke-VideoAiNative $Python @('-B', '-m', 'venv', $target)
        if ($script:VideoAiExitCode -ne 0) { exit $script:VideoAiExitCode }
    }
    Assert-VideoAiPython $VideoAiPython
    $pipArgs = @('-B', '-m', 'pip', 'install', '--disable-pip-version-check', '--retries', '0', '--timeout', '20')
    if ($Wheelhouse) {
        $wheelPath = [IO.Path]::GetFullPath($Wheelhouse)
        $pipArgs += @('--no-index', '--find-links', $wheelPath)
    }
    $pipArgs += @('--editable', "$VideoAiSourceRoot[dev]")
    Invoke-VideoAiNative $VideoAiPython $pipArgs
    $exitCode = $script:VideoAiExitCode
} catch {
    if ($script:VideoAiLog) { Write-VideoAiLog ($_ | Out-String) }
    [Console]::Error.WriteLine($_.ToString())
} finally {
    if ($script:VideoAiLog) { Write-VideoAiLog "script_exit=$exitCode" }
}
exit $exitCode
