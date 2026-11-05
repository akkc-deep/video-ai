"""Small installer fixtures; no tool/model downloads or inference."""
import json
import os
from pathlib import Path
import subprocess


SOURCE = Path(__file__).resolve().parents[2]
INSTALLER = SOURCE / 'scripts/install_online.ps1'


def run_ps(tmp_path, body):
    harness = tmp_path / 'online fixture.ps1'
    harness.write_text("$ErrorActionPreference='Stop'\n. $env:VAI_ONLINE_SCRIPT\n" + body, encoding='utf-8-sig')
    return subprocess.run(
        ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(harness)],
        env={**os.environ, 'VAI_ONLINE_SCRIPT': str(INSTALLER), 'VAI_FIXTURE': str(tmp_path)},
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=35,
    )


def test_hf_urls_are_pinned_and_encode_filenames(tmp_path):
    result = run_ps(tmp_path, """
[Console]::WriteLine((Get-OnlineHfUrl 'org/model' 'abc123' 'folder/weight=12.ckpt' 'https://hf-mirror.com'))
""")
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'https://hf-mirror.com/org/model/resolve/abc123/folder/weight%3D12.ckpt' in result.stdout


def test_archive_layout_and_native_failure(tmp_path):
    nested = tmp_path / 'archive space' / 'release'
    (nested / 'bin').mkdir(parents=True)
    (nested / 'bin/ffmpeg.exe').write_bytes(b'fixture')
    result = run_ps(tmp_path, """
$root = Find-OnlineArchiveRoot (Join-Path $env:VAI_FIXTURE 'archive space') 'bin/ffmpeg.exe'
if ($root -ne (Join-Path $env:VAI_FIXTURE 'archive space/release')) { throw 'wrong archive root' }
try { Invoke-OnlineNative 'C:/Windows/System32/cmd.exe' @('/c', 'exit', '7') }
catch { if ($_.ToString().Contains('exit 7')) { exit 7 }; throw }
exit 0
""")
    assert result.returncode == 7, result.stdout + result.stderr


def test_fresh_configuration_and_launcher_need_no_migration_bundle(tmp_path):
    (tmp_path / 'voice.wav').write_bytes(b'audio fixture')
    result = run_ps(tmp_path, """
$OnlineRuntimeRoot = Join-Path $env:VAI_FIXTURE 'runtime'
$OnlineSourceRoot = Join-Path $env:VAI_FIXTURE 'source'
[IO.Directory]::CreateDirectory((Join-Path $OnlineSourceRoot 'config')) | Out-Null
Copy-Item -LiteralPath (Join-Path $env:VAI_SOURCE 'config/production.example.json') -Destination (Join-Path $OnlineSourceRoot 'config/production.example.json')
Copy-Item -LiteralPath (Join-Path $env:VAI_SOURCE 'config/voice.example.json') -Destination (Join-Path $OnlineSourceRoot 'config/voice.example.json')
New-OnlineConfiguration (Join-Path $env:VAI_FIXTURE 'voice.wav') 'public sample transcript' 'C:/Windows/Fonts/msyh.ttc'
""".replace('$env:VAI_SOURCE', "'" + str(SOURCE).replace("'", "''") + "'"))
    assert result.returncode == 0, result.stdout + result.stderr
    config_root = tmp_path / 'runtime/projects/video-ai/config'
    config = json.loads((config_root / 'production.json').read_text(encoding='utf-8-sig'))
    voice = json.loads((config_root / 'voice.json').read_text(encoding='utf-8-sig'))
    assert config['services']['ollama'] == 'http://127.0.0.1:11435'
    assert config['workflows']['sdxl'].replace('\\', '/').endswith('/source/workflows/sdxl_api.json')
    assert voice['reference_text'] == 'public sample transcript'
    assert voice['reference_sha256'] and voice['device'] == 'cpu' and voice['is_half'] is False
    assert 'custom:' in (config_root / 'tts-api.yaml').read_text(encoding='utf-8-sig')
    launcher = (tmp_path / 'runtime/projects/video-ai/generate_online.ps1').read_text(encoding='utf-8-sig')
    assert 'start_windows.ps1' in launcher
    assert 'migrate_windows.ps1' not in launcher


def test_missing_executable_does_not_inherit_previous_success(tmp_path):
    result = run_ps(tmp_path, """
Invoke-OnlineNative 'C:/Windows/System32/cmd.exe' @('/c','exit','0')
try { Invoke-OnlineNative 'definitely-missing-video-ai-tool.exe' @() }
catch { exit 7 }
exit 0
""")
    assert result.returncode == 7, result.stdout + result.stderr


def test_download_keeps_partial_then_resumes_without_repeating_completed_file(tmp_path):
    result = run_ps(tmp_path, """
$target=Join-Path $env:VAI_FIXTURE 'weights.bin'
function curl.exe {
    $out=$args[[Array]::IndexOf($args,'--output') + 1]
    [IO.File]::WriteAllText($out,'partial')
    $global:LASTEXITCODE=22
}
try { Get-OnlineDownload 'https://example.com/weight' $target | Out-Null; throw 'expected failure' }
catch { if ($_.ToString() -notmatch 'exit 22') { throw } }
if ((Test-Path -LiteralPath $target) -or -not (Test-Path -LiteralPath ($target+'.part'))) { throw 'bad partial state' }
function curl.exe {
    $out=$args[[Array]::IndexOf($args,'--output') + 1]
    [IO.File]::WriteAllText($out,'complete fixture')
    $global:LASTEXITCODE=0
}
Get-OnlineDownload 'https://example.com/weight' $target | Out-Null
function curl.exe { throw 'completed download must be reused' }
Get-OnlineDownload 'https://example.com/weight' $target | Out-Null
""")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / 'weights.bin').read_text() == 'complete fixture'


def test_download_recovers_interruption_after_final_file_move(tmp_path):
    target = tmp_path / 'completed.bin'
    target.write_bytes(b'complete')
    (tmp_path / 'completed.bin.download.pending.json').write_text(
        json.dumps({'url': 'https://example.com/model', 'bytes': 8}))
    result = run_ps(tmp_path, """
function curl.exe { throw 'completed download must not run again' }
Get-OnlineDownload 'https://example.com/model' (Join-Path $env:VAI_FIXTURE 'completed.bin') | Out-Null
""")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / 'completed.bin.download.json').is_file()
