$pytestArguments = @($args)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'bootstrap.ps1')
$exitCode = 1
$invocationDirectory = Get-Location
try {
    Initialize-VideoAiEnvironment 'test'
    foreach ($argument in $pytestArguments) {
        # pytest deletes basetemp before using it. Both basetemp and cache_dir
        # must remain script-owned, including aliases, env/config overrides.
        if ($argument -match '^(--basetemp|--override-ini|--config-file|--junit-?xml|--log-file|--debug)(=|$)' -or
            $argument -match '^(-o|-c)' -or $argument -eq '--' -or $argument -match 'cache_dir=') {
            $exitCode = 2
            throw 'Test cache/temp and file-output paths are controlled by this script; overriding them is forbidden.'
        }
    }
    Assert-VideoAiPython $VideoAiPython
    $testRoot = New-VideoAiDirectory (Join-Path $VideoAiDisposableRoot 'tests')
    $testSession = New-VideoAiDirectory (Join-Path $testRoot $script:VideoAiCommandId)
    $pytestCache = New-VideoAiDirectory (Join-Path $testSession 'cache')
    $pytestTemp = Assert-VideoAiRuntimePath (Join-Path $testSession 'temp')
    @{pid=$PID; process_started_at='launcher'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $testSession 'owner.json') -Encoding UTF8
    Set-Location -LiteralPath $VideoAiSourceRoot
    $nativeArgs = @('-B', '-m', 'pytest') + $pytestArguments + @('-o', "cache_dir=$pytestCache", "--basetemp=$pytestTemp")
    Invoke-VideoAiNative $VideoAiPython $nativeArgs
    $exitCode = $script:VideoAiExitCode
} catch {
    if ($script:VideoAiLog) { Write-VideoAiLog ($_ | Out-String) }
    [Console]::Error.WriteLine($_.ToString())
} finally {
    Set-Location -LiteralPath $invocationDirectory.Path
    if ($script:VideoAiLog) { Write-VideoAiLog "script_exit=$exitCode" }
}
exit $exitCode
