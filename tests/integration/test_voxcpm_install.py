"""Exercise real PowerShell control flow with native deployment calls intercepted."""
import os
from pathlib import Path
import subprocess

SOURCE=Path(__file__).resolve().parents[2]


def run_ps(tmp_path, body):
    harness=tmp_path/'vox fixture.ps1'
    harness.write_text("$ErrorActionPreference='Stop'\n. $env:VOX_INSTALL -VerifyOnly\n"+body,encoding='utf-8-sig')
    return subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(harness)],
        env={**os.environ,'VOX_INSTALL':str(SOURCE/'scripts/install_voxcpm2.ps1'),
             'VIDEO_AI_RUNTIME_ROOT':str(tmp_path/'runtime space')},capture_output=True,text=True,
        encoding='utf-8',errors='replace',timeout=30)


def test_verify_only_never_provisions_or_activates(tmp_path):
    result=run_ps(tmp_path,"""
function Invoke-OnlineNative([string] $Executable,[string[]] $Arguments) {
    if ($Arguments -contains 'provision' -or $Arguments -contains 'activate' -or $Arguments -contains 'relocate') { throw 'verification mutated installation' }
    if ($Arguments -notcontains 'verify') { throw 'expected verification' }
}
Install-VideoAiVox
""")
    assert result.returncode==0,result.stdout+result.stderr


def test_offline_checks_before_activation_and_stops_on_failure(tmp_path):
    result=run_ps(tmp_path,"""
$VerifyOnly=$false; $Offline=$true; $NoActivate=$false
$script:actions=@()
function Install-VoxDependencies { throw 'offline installation attempted a download' }
function Invoke-OnlineNative([string] $Executable,[string[]] $Arguments) {
    $action=$Arguments[3];$script:actions+=@($action)
    if ($action -eq 'verify') { throw 'fixture missing model' }
}
try { Install-VideoAiVox; throw 'expected failure' }
catch { if ($_.ToString() -notmatch 'fixture missing model') { throw } }
if (($script:actions -join ',') -ne 'provision,relocate,verify') { throw ($script:actions -join ',') }
""")
    assert result.returncode==0,result.stdout+result.stderr


def test_owned_partial_environment_resumes_dependency_install(tmp_path):
    root=tmp_path/'runtime space'
    official=root/'shared/tools/VoxCPM';official.mkdir(parents=True)
    envroot=root/'shared/envs/voxcpm2';(envroot/'Scripts').mkdir(parents=True)
    (envroot/'Scripts/python.exe').write_bytes(b'partial environment fixture')
    import json
    spec=json.loads((SOURCE/'config/voxcpm2-deployment.json').read_text())
    (envroot/'.vox-install.json').write_text(json.dumps(dict(source_revision=spec['source_revision'],state='installing')))
    for name in spec['model_files']:
        path=root/'shared/models/VoxCPM2'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture')
    alignment=json.loads((SOURCE/'config/voxcpm2-alignment.json').read_text())
    for name in alignment['files']:
        path=root/'shared/models/funasr/timestamp'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture')
    result=run_ps(tmp_path,"""
function git.exe { $global:LASTEXITCODE=0; return '300e4260b509066151d623dc9c0aa922cf82232b' }
function Test-VoxEnvironment { return $false }
$script:pipCount=0
function Invoke-OnlineNative([string] $Executable,[string[]] $Arguments) {
    if ($Executable -eq $VoxPython -and $Arguments -contains 'pip') { $script:pipCount++ }
}
Install-VoxDependencies
if ($script:pipCount -lt 3) { throw 'partial environment dependencies were skipped' }
""")
    assert result.returncode==0,result.stdout+result.stderr
