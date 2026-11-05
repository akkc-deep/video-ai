param(
    [ValidateSet('Export', 'Restore', 'Generate')]
    [string] $Mode = 'Export',
    [string] $PackagePath = '',
    [string] $Config = '',
    [string] $Script = '',
    [string] $Text = '',
    [string] $Video = '',
    [string] $Title = '',
    [switch] $IncludeHistory,
    [switch] $WithoutSecrets,
    [switch] $AllowExisting,
    [switch] $NoLaunch
)

$ErrorActionPreference = 'Stop'
$MigrationScriptPath = $PSCommandPath
$MigrationSourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$MigrationRuntimeRoot = 'D:\VideoSi'
$MigrationInstallRoot = 'D:\code\py\video-ai'
$MigrationUtf8 = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $MigrationUtf8
$OutputEncoding = $MigrationUtf8

function Write-MigrationText([string] $Path, [string] $Value) {
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Path)) | Out-Null
    [IO.File]::WriteAllText($Path, $Value, $MigrationUtf8)
}

function Assert-MigrationTarget([string] $Path, [bool] $MayExist) {
    if ((Test-Path -LiteralPath $Path) -and -not $MayExist) {
        if (@(Get-ChildItem -LiteralPath $Path -Force | Select-Object -First 1).Count) {
            throw "Target already contains files: $Path. Use -AllowExisting only to merge intentionally."
        }
    }
    # Refuse redirected destination ancestors before copying any files.
    $cursor = [IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Redirected target is not supported: $cursor"
            }
        }
        $parent = Split-Path -Parent $cursor
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
}

function Copy-MigrationTree([string] $Source, [string] $Destination, [string[]] $ExcludeDirectories = @(), [string[]] $ExcludeFiles = @()) {
    $sourcePath = [IO.Path]::GetFullPath($Source).TrimEnd('\')
    $destinationPath = [IO.Path]::GetFullPath($Destination).TrimEnd('\')
    if ($sourcePath -eq $destinationPath -or
        $destinationPath.StartsWith($sourcePath + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $sourcePath.StartsWith($destinationPath + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Copy source and destination must be separate trees: $sourcePath -> $destinationPath"
    }
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Container)) { throw "Missing source: $sourcePath" }
    Assert-MigrationTarget $destinationPath $true
    Write-Host "Copy: $sourcePath -> $destinationPath"
    # No /MIR or /PURGE: never delete destination files. Preserve file timestamps
    # because the application's artifact identities include mtime_ns.
    $copyArgs = @($sourcePath, $destinationPath, '/E', '/COPY:DAT', '/DCOPY:DAT', '/XJ', '/R:2', '/W:2', '/MT:8', '/NP', '/NFL', '/NDL')
    $copyArgs += @('/XD', '__pycache__') + $ExcludeDirectories
    if ($ExcludeFiles.Count) { $copyArgs += @('/XF') + $ExcludeFiles }
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & robocopy.exe @copyArgs | Out-Host
        $copyExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    # Robocopy codes 0..7 are successful copy/skip/difference results.
    if ($copyExit -ge 8) { throw "Robocopy failed ($copyExit): $sourcePath -> $destinationPath" }
}

function Update-MigrationVenv([string] $VenvRoot, [string] $BaseRoot) {
    $path = Join-Path $VenvRoot 'pyvenv.cfg'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing virtual environment configuration: $path" }
    $lines = @(Get-Content -LiteralPath $path -Encoding UTF8 | Where-Object { $_ -notmatch '^(home|executable|command)\s*=' })
    $lines += @("home = $BaseRoot", "executable = $(Join-Path $BaseRoot 'python.exe')")
    Write-MigrationText $path (($lines -join "`r`n") + "`r`n")
}

function Test-MigrationOrchestrator([string] $Python) {
    # Windows PowerShell's native argument marshaler strips embedded double
    # quotes; Python string literals here must use single quotes instead.
    & $Python -B -c 'import sys, struct, video_ai; assert sys.version_info[:2] == (3, 12) and struct.calcsize(''P'') == 8; print(''Python 3.12 and video-ai: ready'')'
    if ($LASTEXITCODE -ne 0) { throw 'Restored Python cannot start. Check Windows x64 and the Microsoft Visual C++ 2015-2022 x64 runtime.' }
}

function Save-MigrationNarration([string] $Value, [string] $InputRoot) {
    if (-not $Value.Trim()) { throw 'Narration cannot be empty.' }
    $path = Join-Path $InputRoot ('narration-' + [guid]::NewGuid().ToString('N') + '.txt')
    Write-MigrationText $path $Value
    return $path
}

function Get-MigrationRuntimeInstaller([string] $Directory) {
    $installer = Join-Path $Directory 'VC_redist.x64.exe'
    [IO.Directory]::CreateDirectory($Directory) | Out-Null
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
        Write-Host 'Downloading Microsoft Visual C++ x64 runtime for the destination PC...'
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile $installer -TimeoutSec 180
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
        throw "Microsoft runtime installer signature is invalid. Remove $installer and retry the export."
    }
}

function Install-MigrationRuntime([string] $Directory) {
    $installer = Join-Path $Directory 'VC_redist.x64.exe'
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw 'Missing bundled Microsoft Visual C++ x64 runtime installer.' }
    $runtime = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64' -ErrorAction SilentlyContinue
    $bundledVersion = [regex]::Match((Get-Item -LiteralPath $installer).VersionInfo.ProductVersion, '\d+\.\d+\.\d+(?:\.\d+)?').Value
    if ($runtime -and $runtime.Installed -eq 1 -and $bundledVersion -and
        $runtime.Version -match '^v?(\d+\.\d+\.\d+(?:\.\d+)?)$') {
        if ([version]$Matches[1] -ge [version]$bundledVersion) { return }
    }
    Write-Host 'Installing Microsoft Visual C++ x64 runtime. Windows may ask for administrator approval.'
    $options = @{
        FilePath = $installer; ArgumentList = @('/install', '/quiet', '/norestart')
        Wait = $true; PassThru = $true; WindowStyle = 'Hidden'
    }
    $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { $options.Verb = 'RunAs' }
    $process = Start-Process @options
    if ($process.ExitCode -eq 3010) { throw 'Microsoft runtime installed and Windows requires a restart. Restart this PC, then run restore.cmd again.' }
    if ($process.ExitCode -notin @(0, 1638)) { throw "Microsoft runtime installation failed: $($process.ExitCode)" }
}

function Import-MigrationSecrets([string] $Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
    $values = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($property in $values.PSObject.Properties) {
        if ($property.Name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$' -or $property.Value -isnot [string]) {
            throw 'Invalid local credential mapping; expected environment variable names and string values.'
        }
        # Process only; never log values or change the user's global environment.
        [Environment]::SetEnvironmentVariable($property.Name, $property.Value, 'Process')
    }
}

function Get-MigrationSecretNames($Value) {
    if ($null -eq $Value -or $Value -is [string]) { return }
    if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [pscustomobject]) {
        foreach ($entry in $Value) { Get-MigrationSecretNames $entry }
        return
    }
    foreach ($property in $Value.PSObject.Properties) {
        if ($property.Name -match '_env$' -and $property.Value -is [string]) { $property.Value }
        elseif ($property.Value -is [pscustomobject] -or $property.Value -is [array]) { Get-MigrationSecretNames $property.Value }
    }
}

function Export-MigrationSecrets([string] $ConfigRoot, [string] $Destination) {
    $names = @('VIDEO_AI_VOLC_ACCESS_KEY', 'VIDEO_AI_VOLC_SECRET_KEY', 'VIDEO_AI_SMTP_AUTH_CODE')
    foreach ($file in Get-ChildItem -LiteralPath $ConfigRoot -Filter '*.json') {
        $value = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        $names += @(Get-MigrationSecretNames $value)
    }
    $local = @{}
    foreach ($localName in @('jimeng.credentials.local.json', 'migration-secrets.local.json')) {
        $localPath = Join-Path $ConfigRoot $localName
        if (Test-Path -LiteralPath $localPath) {
            $values = Get-Content -LiteralPath $localPath -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($property in $values.PSObject.Properties) {
                $local[$property.Name] = $property.Value
                $names += $property.Name
            }
        }
    }
    $result = @{}
    foreach ($name in ($names | Sort-Object -Unique)) {
        if ($name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { throw 'Invalid credential environment variable name in configuration.' }
        $value = [Environment]::GetEnvironmentVariable($name, 'Process')
        if (-not $value -and $local.ContainsKey($name)) { $value = $local[$name] }
        if ($value) { $result[$name] = [string]$value }
    }
    Write-MigrationText $Destination ($result | ConvertTo-Json)
    Write-Host 'The migration package contains private configuration and credentials. Keep it private.' -ForegroundColor Yellow
}

function Get-MigrationStrings($Value) {
    if ($Value -is [string]) { $Value; return }
    if ($Value -is [pscustomobject]) {
        foreach ($property in $Value.PSObject.Properties) { Get-MigrationStrings $property.Value }
    } elseif ($Value -is [array]) {
        foreach ($item in $Value) { Get-MigrationStrings $item }
    }
}

function Get-MigrationEvidenceDirectories([string] $RuntimeRoot) {
    # These historical records are runtime dependencies, not disposable logs.
    # Discover the whole component/source runs and log trees they reference,
    # without loading models or verifying large-file hashes.
    $acceptance = Join-Path $RuntimeRoot 'projects\video-ai\runs\20261004-040653-a0fcd961cc58\task4-acceptance.json'
    $pinned = Join-Path $RuntimeRoot 'cache\video-ai\logs\vco05-20261027-native321'
    $roots = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    if (Test-Path -LiteralPath $pinned -PathType Container) { [void]$roots.Add($pinned) }
    if (Test-Path -LiteralPath $acceptance -PathType Leaf) { [void]$roots.Add((Split-Path -Parent $acceptance)) }
    foreach ($seed in @($acceptance, (Join-Path $pinned 'case.json'))) {
        if (-not (Test-Path -LiteralPath $seed -PathType Leaf)) { continue }
        $data = Get-Content -LiteralPath $seed -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($value in (Get-MigrationStrings $data)) {
            if (-not [IO.Path]::IsPathRooted($value)) { continue }
            $absolute = [IO.Path]::GetFullPath($value)
            foreach ($relative in @('projects\video-ai\runs', 'cache\video-ai\logs')) {
                $prefix = (Join-Path $RuntimeRoot $relative).TrimEnd('\') + '\'
                if ($absolute.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
                    $first = $absolute.Substring($prefix.Length).Split('\')[0]
                    $tree = Join-Path $prefix $first
                    if (Test-Path -LiteralPath $tree -PathType Container) { [void]$roots.Add($tree) }
                }
            }
        }
    }
    $roots | Sort-Object
}

function Export-VideoAiMigration {
    if (-not $PackagePath) { $PackagePath = 'D:\VideoAiMigration-' + (Get-Date -Format 'yyyyMMdd-HHmmss') }
    $PackagePath = [IO.Path]::GetFullPath($PackagePath)
    # Keep bundles outside both source trees, including for interrupted exports.
    foreach ($root in @($MigrationRuntimeRoot, $MigrationSourceRoot)) {
        if ($PackagePath -eq $root -or $PackagePath.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Choose a package directory outside D:\VideoSi and the source checkout.'
        }
    }
    Assert-MigrationTarget $PackagePath ([bool]$AllowExisting)
    if ($WithoutSecrets -and (Test-Path -LiteralPath $PackagePath) -and
        @(Get-ChildItem -LiteralPath $PackagePath -Force | Select-Object -First 1).Count) {
        throw 'Use a new empty package directory with -WithoutSecrets so no old credentials remain in the package.'
    }
    $configRoot = Join-Path $MigrationRuntimeRoot 'projects\video-ai\config'
    if (-not $Config) { $Config = Join-Path $configRoot 'production.json' }
    $Config = [IO.Path]::GetFullPath($Config)
    if (-not $Config.StartsWith($configRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $Config -PathType Leaf)) {
        throw "Choose an existing production configuration under $configRoot."
    }
    $orchestrator = Join-Path $MigrationRuntimeRoot 'envs\video-ai\Scripts\python.exe'
    $baseRoot = & $orchestrator -B -c 'import sys; print(sys.base_prefix)'
    if ($LASTEXITCODE -ne 0 -or -not $baseRoot) { throw 'Cannot locate the working Python 3.12 base interpreter.' }
    $baseRoot = ([string]$baseRoot).Trim()
    $payload = Join-Path $PackagePath 'payload'
    [IO.Directory]::CreateDirectory($PackagePath) | Out-Null
    # Invalidate an old completion marker before resuming an interrupted export.
    $manifestPath = Join-Path $PackagePath 'migration.json'
    if (Test-Path -LiteralPath $manifestPath) { Remove-Item -LiteralPath $manifestPath }
    Get-MigrationRuntimeInstaller (Join-Path $PackagePath 'prerequisites')
    Write-Host 'Exporting the installed stack. Model copies can take a long time; no inference tests will run.'
    Copy-MigrationTree $MigrationSourceRoot (Join-Path $payload 'source') @('.git', '.idea', '.venv', '.pytest_cache', '.aws', '.codex', '.agents') @('.env', '.env.*', '*.log')
    $toolExclusions = @()
    if (-not $IncludeHistory) {
        $toolExclusions = @(
            (Join-Path $MigrationRuntimeRoot 'tools\ComfyUI_windows_portable\ComfyUI\output'),
            (Join-Path $MigrationRuntimeRoot 'tools\ComfyUI_windows_portable\ComfyUI\temp'),
            (Join-Path $MigrationRuntimeRoot 'tools\GPT-SoVITS\TEMP')
        )
    }
    Copy-MigrationTree (Join-Path $MigrationRuntimeRoot 'tools') (Join-Path $payload 'runtime\tools') $toolExclusions
    Copy-MigrationTree (Join-Path $MigrationRuntimeRoot 'models') (Join-Path $payload 'runtime\models')
    Copy-MigrationTree (Join-Path $MigrationRuntimeRoot 'envs\video-ai') (Join-Path $payload 'runtime\envs\video-ai')
    $projectRoot = Join-Path $MigrationRuntimeRoot 'projects\video-ai'
    $projectExclusions = @()
    if (-not $IncludeHistory) { $projectExclusions = @((Join-Path $projectRoot 'runs'), (Join-Path $projectRoot 'productions')) }
    $projectExcludedFiles = @()
    if ($WithoutSecrets) { $projectExcludedFiles = @('*.credentials.local.json', 'migration-secrets.local.json') }
    Copy-MigrationTree $projectRoot (Join-Path $payload 'runtime\projects\video-ai') $projectExclusions $projectExcludedFiles
    foreach ($evidence in (Get-MigrationEvidenceDirectories $MigrationRuntimeRoot)) {
        if ($IncludeHistory -and $evidence.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { continue }
        $relative = $evidence.Substring($MigrationRuntimeRoot.Length + 1)
        Copy-MigrationTree $evidence (Join-Path $payload ('runtime\' + $relative))
    }
    # A Windows venv alone is not portable: include its real base installation.
    Copy-MigrationTree $baseRoot (Join-Path $payload 'runtime\tools\video-ai-python312')
    if ($IncludeHistory -and (Test-Path -LiteralPath (Join-Path $MigrationRuntimeRoot 'output\video-ai'))) {
        Copy-MigrationTree (Join-Path $MigrationRuntimeRoot 'output\video-ai') (Join-Path $payload 'runtime\output\video-ai')
    }
    $secretTarget = Join-Path $payload 'runtime\projects\video-ai\config\migration-secrets.local.json'
    if (-not $WithoutSecrets) { Export-MigrationSecrets $configRoot $secretTarget }
    Copy-Item -LiteralPath $MigrationScriptPath -Destination (Join-Path $PackagePath 'migrate_windows.ps1') -Force
    $restoreLauncher = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0migrate_windows.ps1" -Mode Restore -PackagePath "%~dp0." %*
set "migration_exit=%errorlevel%"
pause
exit /b %migration_exit%
'@
    Write-MigrationText (Join-Path $PackagePath 'restore.cmd') $restoreLauncher
    $manifest = [ordered]@{
        schema_version = 1
        exported_at = (Get-Date).ToUniversalTime().ToString('o')
        config = $Config
        include_history = [bool]$IncludeHistory
        includes_secrets = -not [bool]$WithoutSecrets
    }
    Write-MigrationText $manifestPath ($manifest | ConvertTo-Json)
    Write-Host "Export complete: $PackagePath" -ForegroundColor Green
    Write-Host 'Copy the WHOLE directory to the other PC, then double-click restore.cmd.'
}

function Restore-VideoAiMigration {
    if (-not $PackagePath) { $PackagePath = $PSScriptRoot }
    $PackagePath = [IO.Path]::GetFullPath($PackagePath)
    $manifestPath = Join-Path $PackagePath 'migration.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'Incomplete package: migration.json is missing. Finish exporting on the source PC first.' }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.schema_version -ne 1) { throw 'Unsupported migration package version.' }
    $payload = Join-Path $PackagePath 'payload'
    foreach ($required in @('source\scripts\start_windows.ps1', 'runtime\tools\video-ai-python312\python.exe', 'runtime\envs\video-ai\pyvenv.cfg')) {
        if (-not (Test-Path -LiteralPath (Join-Path $payload $required) -PathType Leaf)) { throw "Incomplete package: $required" }
    }
    $receipt = Join-Path $MigrationRuntimeRoot 'migration-install.json'
    $sameInstall = $false
    if (Test-Path -LiteralPath $receipt) {
        $previous = Get-Content -LiteralPath $receipt -Raw -Encoding UTF8 | ConvertFrom-Json
        $sameInstall = $previous.exported_at -eq $manifest.exported_at
    }
    $mayExist = [bool]$AllowExisting -or $sameInstall
    # Guard both destinations before any installation writes.
    Assert-MigrationTarget $MigrationRuntimeRoot $mayExist
    Assert-MigrationTarget $MigrationInstallRoot $mayExist
    foreach ($destination in @($MigrationRuntimeRoot, $MigrationInstallRoot)) {
        if ($PackagePath -eq $destination -or $PackagePath.StartsWith($destination + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Place the migration package outside the installation directories before restoring.'
        }
    }
    # A pending receipt permits retry after interruption; it is not readiness proof.
    Write-MigrationText $receipt (@{ exported_at = $manifest.exported_at; state = 'restoring' } | ConvertTo-Json)
    Copy-MigrationTree (Join-Path $payload 'runtime') $MigrationRuntimeRoot
    Copy-MigrationTree (Join-Path $payload 'source') $MigrationInstallRoot
    Update-MigrationVenv (Join-Path $MigrationRuntimeRoot 'envs\video-ai') (Join-Path $MigrationRuntimeRoot 'tools\video-ai-python312')
    if (-not $Config) { $Config = $manifest.config }
    Write-MigrationText (Join-Path $MigrationRuntimeRoot 'projects\video-ai\config\migration-default.local.json') (@{ config = $Config } | ConvertTo-Json)
    Install-MigrationRuntime (Join-Path $PackagePath 'prerequisites')
    $python = Join-Path $MigrationRuntimeRoot 'envs\video-ai\Scripts\python.exe'
    $env:PYTHONPATH = Join-Path $MigrationInstallRoot 'src'
    $env:PYTHONUTF8 = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    Test-MigrationOrchestrator $python
    # Only lightweight startup/import checks; do not load models or run inference.
    & (Join-Path $MigrationRuntimeRoot 'tools\ComfyUI_windows_portable\python_embeded\python.exe') -B -c 'import torch; ready = torch.cuda.is_available(); print(''torch='' + torch.__version__ + '', CUDA='' + str(ready)); raise SystemExit(0 if ready else 2)'
    if ($LASTEXITCODE -ne 0) { throw 'ComfyUI CUDA startup failed. Install a compatible NVIDIA driver and the Microsoft Visual C++ x64 runtime.' }
    # The project's configured GPT-SoVITS voice runs on CPU.
    & (Join-Path $MigrationRuntimeRoot 'tools\GPT-SoVITS\runtime\python.exe') -B -c 'import torch; print(''TTS torch='' + torch.__version__)'
    if ($LASTEXITCODE -ne 0) { throw 'GPT-SoVITS Python startup failed. Check the Microsoft Visual C++ x64 runtime.' }
    Write-MigrationText $receipt (@{ exported_at = $manifest.exported_at; state = 'ready'; inference_verified = $false } | ConvertTo-Json)
    Write-Host 'Restore complete. Generation entry: D:\code\py\video-ai\generate_video.cmd' -ForegroundColor Green
    if (-not $NoLaunch) {
        $entry = Join-Path $MigrationInstallRoot 'scripts\migrate_windows.ps1'
        $launchArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $entry, '-Mode', 'Generate', '-Config', $Config)
        if ($Text) {
            if ($Script) { throw 'Use either -Script or -Text, not both.' }
            $Script = Save-MigrationNarration $Text (Join-Path $MigrationRuntimeRoot 'disposable\video-ai\tmp\narration')
        }
        if ($Script) { $launchArgs += @('-Script', $Script) }
        & powershell.exe @launchArgs
        $script:MigrationExitCode = $LASTEXITCODE
    }
}

function Start-MigratedVideo {
    $configRoot = Join-Path $MigrationRuntimeRoot 'projects\video-ai\config'
    $defaults = Join-Path $configRoot 'migration-default.local.json'
    if (-not $Config -and (Test-Path -LiteralPath $defaults)) {
        $Config = (Get-Content -LiteralPath $defaults -Raw -Encoding UTF8 | ConvertFrom-Json).config
    }
    if (-not $Config) { $Config = Join-Path $configRoot 'production.json' }
    Import-MigrationSecrets (Join-Path $configRoot 'jimeng.credentials.local.json')
    Import-MigrationSecrets (Join-Path $configRoot 'migration-secrets.local.json')
    if ($Video) {
        if ($Script -or $Text -or $Title) { throw 'Use -Video to continue, or -Script/-Text and -Title for a new video.' }
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $MigrationSourceRoot 'scripts\start_windows.ps1') make-video --video $Video
        $script:MigrationExitCode = $LASTEXITCODE
        return
    }
    if (-not $Script -and -not $Text) {
        Write-Host "Default configuration: $Config"
        $choice = Read-Host 'Configuration path (Enter to keep default)'
        if ($choice) { $Config = $choice.Trim('"') }
        $inputValue = Read-Host 'Paste narration text, or enter the path to a UTF-8 text file'
        if (-not $inputValue.Trim()) { throw 'Narration cannot be empty.' }
        $possibleFile = $inputValue.Trim('"')
        if (Test-Path -LiteralPath $possibleFile -PathType Leaf) { $Script = [IO.Path]::GetFullPath($possibleFile) }
        elseif ($possibleFile -match '^[A-Za-z]:[\\/]|\.txt$') { throw "Narration file not found: $possibleFile" }
        else { $Text = $inputValue }
    }
    if ($Script -and $Text) { throw 'Use either -Script or -Text, not both.' }
    # Put original text in a UTF-8 file before crossing another process boundary.
    # Quotes, Chinese text and line breaks then reach make-video unchanged.
    if ($Text) { $Script = Save-MigrationNarration $Text (Join-Path $MigrationRuntimeRoot 'disposable\video-ai\tmp\narration') }
    $cliArgs = @('make-video', '--config', $Config)
    if ($Title) { $cliArgs += @('--title', $Title) }
    if ($Script) { $cliArgs += @('--script', [IO.Path]::GetFullPath($Script)) }
    # A child process preserves the existing entry point's exit codes and logs.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $MigrationSourceRoot 'scripts\start_windows.ps1') @cliArgs
    $script:MigrationExitCode = $LASTEXITCODE
    if ($script:MigrationExitCode -eq 3) {
        Write-Host 'Generation is waiting for image selection or review. Continue using the video number reported above: generate_video.cmd -Video 0001' -ForegroundColor Yellow
    }
}

# Dot-sourcing loads helpers for small fixture tests without exporting anything.
if ($MyInvocation.InvocationName -ne '.') {
    $script:MigrationExitCode = 0
    try {
        if (-not [Environment]::Is64BitOperatingSystem -or -not (Test-Path -LiteralPath 'D:\')) { throw 'This project requires Windows x64 and a local D: drive.' }
        switch ($Mode) {
            'Export' { Export-VideoAiMigration }
            'Restore' { Restore-VideoAiMigration }
            'Generate' { Start-MigratedVideo }
        }
    } catch {
        [Console]::Error.WriteLine($_.ToString())
        $script:MigrationExitCode = 1
    }
    exit $script:MigrationExitCode
}
