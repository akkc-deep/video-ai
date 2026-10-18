# No named parameters: preserve arbitrary CLI flags and the invocation cwd.
$cliArguments = @($args)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'bootstrap.ps1')
$exitCode = 1
try {
    Initialize-VideoAiEnvironment 'start'
    Assert-VideoAiRuntimePath $VideoAiEnvRoot | Out-Null
    Assert-VideoAiRuntimePath $VideoAiPython | Out-Null
    if (-not (Test-Path -LiteralPath $VideoAiPython -PathType Leaf)) {
        throw "Missing orchestration environment. Run $VideoAiSourceRoot\scripts\install_windows.ps1."
    }
    Invoke-VideoAiNative $VideoAiPython (@('-B', '-m', 'video_ai') + $cliArguments)
    $exitCode = $script:VideoAiExitCode
} catch {
    if ($script:VideoAiLog) { Write-VideoAiLog ($_ | Out-String) }
    [Console]::Error.WriteLine($_.ToString())
} finally {
    if ($script:VideoAiLog) { Write-VideoAiLog "script_exit=$exitCode" }
}
exit $exitCode
