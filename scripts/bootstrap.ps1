# Dot-source before executing any Python. These settings apply only to this process.
$VideoAiSourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$VideoAiRuntimeRoot = 'D:\VideoSi'
$VideoAiCacheRoot = 'D:\VideoSi\cache\video-ai'
$VideoAiEnvRoot = 'D:\VideoSi\envs\video-ai'
$VideoAiPython = Join-Path $VideoAiEnvRoot 'Scripts\python.exe'

function Assert-VideoAiRuntimePath([string] $Path) {
    $absolute = [IO.Path]::GetFullPath($Path)
    if (-not $absolute.StartsWith('D:\VideoSi\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Runtime path is outside D:\VideoSi: $absolute"
    }
    $cursor = $absolute
    while ($cursor -and $cursor -ne 'D:\') {
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
        TEMP='temp'; TMP='temp'; TMPDIR='temp'; PYTHONPYCACHEPREFIX='pycache'
        HF_HOME='huggingface'; HF_HUB_CACHE='huggingface\hub'
        TRANSFORMERS_CACHE='huggingface\transformers'; TORCH_HOME='torch'
        PIP_CACHE_DIR='pip'; UV_CACHE_DIR='uv'; UV_PYTHON_INSTALL_DIR='uv-python'
        XDG_CACHE_HOME='xdg'
    }
    foreach ($entry in $locations.GetEnumerator()) {
        $directory = New-VideoAiDirectory (Join-Path $VideoAiCacheRoot $entry.Value)
        [Environment]::SetEnvironmentVariable($entry.Key, $directory, 'Process')
    }
    $env:OLLAMA_MODELS = New-VideoAiDirectory (Join-Path $VideoAiRuntimeRoot 'models\ollama')
    $env:PYTHONUTF8 = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    $env:PYTHONPATH = Join-Path $VideoAiSourceRoot 'src'
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
    $env:PYTEST_ADDOPTS = ''
    $env:PYTEST_PLUGINS = ''
    $script:VideoAiCommandId = [guid]::NewGuid().ToString('N')
    $logs = New-VideoAiDirectory (Join-Path $VideoAiCacheRoot 'logs')
    $script:VideoAiLog = Join-Path $logs "$CommandName-$script:VideoAiCommandId.log"
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
