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
    $pytestCache = New-VideoAiDirectory (Join-Path $VideoAiCacheRoot "pytest\$script:VideoAiCommandId")
    $tempParent = New-VideoAiDirectory (Join-Path $VideoAiCacheRoot 'pytest-tmp')
    $pytestTemp = Assert-VideoAiRuntimePath (Join-Path $tempParent $script:VideoAiCommandId)
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
