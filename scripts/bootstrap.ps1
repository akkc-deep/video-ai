# Dot-source before executing any Python. These settings apply only to this process.
$VideoAiSourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$VideoAiRuntimeRoot = if ($env:VIDEO_AI_RUNTIME_ROOT) { [IO.Path]::GetFullPath($env:VIDEO_AI_RUNTIME_ROOT) } else { 'E:\VideoAI' }
$VideoAiCacheRoot = Join-Path $VideoAiRuntimeRoot 'scratch'
$VideoAiDisposableRoot = Join-Path $VideoAiRuntimeRoot 'scratch'
$VideoAiEnvRoot = Join-Path $VideoAiRuntimeRoot 'shared\envs\video-ai'
$VideoAiPython = Join-Path $VideoAiEnvRoot 'Scripts\python.exe'

function Enter-VideoAiStorageLease {
    $lockPath = New-VideoAiDirectory (Join-Path $VideoAiRuntimeRoot 'shared\config\storage')
    $lockPath = Join-Path $lockPath 'lifecycle.lock'
    $stream = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
    try { $stream.Lock(0, 1); return $stream }
    catch { $stream.Dispose(); throw 'Video storage is occupied. Retry installation after the current operation finishes.' }
}

function Exit-VideoAiStorageLease($Lease) {
    if ($Lease) { try { $Lease.Unlock(0, 1) } finally { $Lease.Dispose() } }
}

function Assert-VideoAiRuntimePath([string] $Path) {
    $absolute = [IO.Path]::GetFullPath($Path)
    if (-not $absolute.StartsWith(($VideoAiRuntimeRoot.TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase)) {
        throw "Runtime path is outside ${VideoAiRuntimeRoot}: $absolute"
    }
    $cursor = $absolute
    while ($cursor -and $cursor -ne [IO.Path]::GetPathRoot($absolute)) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Refusing redirected runtime directory: $cursor"
            }
        }
        $cursor = Split-Path -Parent $cursor
    }
    return $absolute
}

function New-VideoAiDirectory([string] $Path) {
    $absolute = Assert-VideoAiRuntimePath $Path
    [IO.Directory]::CreateDirectory($absolute) | Out-Null
    return $absolute
}

function Initialize-VideoAiEnvironment([string] $CommandName) {
    # Python emits UTF-8; Windows PowerShell decodes native output using the
    # console encoding and uses OutputEncoding for native pipeline input.
    $utf8 = [Text.UTF8Encoding]::new($false)
    $script:OutputEncoding = $utf8
    [Console]::OutputEncoding = $utf8
    $locations = @{
        TEMP='tmp'; TMP='tmp'; TMPDIR='tmp'; PYTHONPYCACHEPREFIX='cache\pycache'
        PIP_CACHE_DIR='cache\pip'; UV_CACHE_DIR='cache\uv'; XDG_CACHE_HOME='cache\xdg'
        CUDA_CACHE_PATH='cache\cuda'; TORCHINDUCTOR_CACHE_DIR='cache\torchinductor'
        TRITON_CACHE_DIR='cache\triton'; MPLCONFIGDIR='cache\matplotlib'; NUMBA_CACHE_DIR='cache\numba'
    }
    foreach ($entry in $locations.GetEnumerator()) {
        $directory = New-VideoAiDirectory (Join-Path $VideoAiDisposableRoot $entry.Value)
        [Environment]::SetEnvironmentVariable($entry.Key, $directory, 'Process')
    }
    # Legacy caches can contain actual weights/base Python. Keep them until explicitly migrated.
    $dependencies = @{
        HF_HOME=@('huggingface','shared\models\huggingface')
        HF_HUB_CACHE=@('huggingface\hub','shared\models\huggingface\hub')
        TRANSFORMERS_CACHE=@('huggingface\transformers','shared\models\huggingface\transformers')
        TORCH_HOME=@('torch','shared\models\torch')
        NLTK_DATA=@('nltk','shared\models\nltk')
        UV_PYTHON_INSTALL_DIR=@('uv-python','shared\envs\python')
    }
    foreach ($entry in $dependencies.GetEnumerator()) {
        $legacy = Join-Path $VideoAiCacheRoot $entry.Value[0]
        $target = Join-Path $VideoAiRuntimeRoot $entry.Value[1]
        [Environment]::SetEnvironmentVariable($entry.Key, (New-VideoAiDirectory $target), 'Process')
    }
    $env:OLLAMA_MODELS = New-VideoAiDirectory (Join-Path $VideoAiRuntimeRoot 'shared\models\ollama')
    $env:PYTHONUTF8 = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    $env:PYTHONPATH = Join-Path $VideoAiSourceRoot 'src'
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
    $env:PYTEST_ADDOPTS = ''
    $env:PYTEST_PLUGINS = ''
    $script:VideoAiCommandId = [guid]::NewGuid().ToString('N')
    $logs = New-VideoAiDirectory (Join-Path $VideoAiDisposableRoot 'logs')
    $script:VideoAiLog = Join-Path $logs "$CommandName-$script:VideoAiCommandId.log"
    $env:VIDEO_AI_ACTIVE_LOG = $script:VideoAiLog
    [IO.File]::WriteAllText($script:VideoAiLog, "command=$CommandName cwd=$((Get-Location).Path)`r`n", [Text.UTF8Encoding]::new($false))
    [Console]::Error.WriteLine("Log: $script:VideoAiLog")
}

function Write-VideoAiLog([string] $Message) {
    [IO.File]::AppendAllText($script:VideoAiLog, "$Message`r`n", [Text.UTF8Encoding]::new($false))
}

function Invoke-VideoAiNative([string] $Executable, [string[]] $Arguments) {
    Write-VideoAiLog "executable=$Executable arguments=$($Arguments -join ' ')"
    # Windows PowerShell represents native stderr as ErrorRecord. It must not
    # turn successful native commands into terminating PowerShell exceptions.
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Executable @Arguments 2>&1 | ForEach-Object {
            $line = $_.ToString()
            Write-VideoAiLog $line
            if ($_ -is [Management.Automation.ErrorRecord]) {
                [Console]::Error.WriteLine($line)
            } else {
                Write-Output $line
            }
        }
        $script:VideoAiExitCode = $LASTEXITCODE
        Write-VideoAiLog "exit_code=$script:VideoAiExitCode"
    } finally {
        $ErrorActionPreference = $savedPreference
    }
}

function Assert-VideoAiPython([string] $Executable) {
    if ($Executable -eq $VideoAiPython) {
        Assert-VideoAiRuntimePath $VideoAiEnvRoot | Out-Null
        Assert-VideoAiRuntimePath $Executable | Out-Null
    }
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw "Missing Python: $Executable. Run scripts/install_windows.ps1."
    }
    Invoke-VideoAiNative $Executable @('-B', '-c', 'import struct,sys; print(sys.version); sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize(''P'') == 8 else 2)')
    if ($script:VideoAiExitCode -ne 0) {
        throw 'The orchestration interpreter must be Python 3.12, 64-bit.'
    }
}
