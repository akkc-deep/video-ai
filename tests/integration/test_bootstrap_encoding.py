"""UTF-8 runtime receipts must not depend on the launching console code page."""
from pathlib import Path
import os
import subprocess
import sys


ROOT=Path(__file__).resolve().parents[2]


def run_gbk_console(script,env):
    # An owned, hidden subprocess forces the non-UTF-8 launch condition.
    # Capture bytes; strict decoding below tests the actual public boundary.
    return subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],
        env={**os.environ,**env},capture_output=True,timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW)


def test_native_utf8_text_and_log_remain_correct_from_gbk_console(tmp_path):
    helper=tmp_path/'utf8.py'
    helper.write_text("import sys\nprint('out中文',flush=True)\nprint('err中文',file=sys.stderr,flush=True)\nsys.exit(7)\n",encoding='utf-8')
    harness=tmp_path/'gbk-native.ps1'
    harness.write_text("[Console]::OutputEncoding=[Text.Encoding]::GetEncoding(936)\n"
        ". 'D:/code/py/video-ai/scripts/bootstrap.ps1'\n"
        "Initialize-VideoAiEnvironment 'test-gbk-native'\n"
        "Invoke-VideoAiNative $env:VAI_ENCODING_PYTHON @('-B',$env:VAI_ENCODING_HELPER)\n"
        "[Console]::Error.WriteLine('probe-log='+$script:VideoAiLog)\n"
        "exit $script:VideoAiExitCode\n",encoding='utf-8-sig')
    result=run_gbk_console(harness,dict(VAI_ENCODING_PYTHON=sys.executable,VAI_ENCODING_HELPER=str(helper)))
    assert result.returncode==7
    out,err=result.stdout.decode('utf-8'),result.stderr.decode('utf-8')
    assert 'out中文' in out and 'err中文' in err
    log=Path(next(line.split('=',1)[1] for line in err.splitlines() if line.startswith('probe-log=')))
    text=log.read_text(encoding='utf-8')
    assert 'out中文' in text and 'err中文' in text and 'exit_code=7' in text


def test_wrong_interpreter_diagnostic_is_utf8_from_gbk_console(tmp_path):
    harness=tmp_path/'gbk-install.ps1'
    harness.write_text("[Console]::OutputEncoding=[Text.Encoding]::GetEncoding(936)\n"
        "& 'D:/code/py/video-ai/scripts/install_windows.ps1' -Python 'C:/Windows/System32/whoami.exe'\n"
        "exit $LASTEXITCODE\n",encoding='utf-8-sig')
    result=run_gbk_console(harness,{})
    assert result.returncode==1
    assert 'Python 3.12' in result.stderr.decode('utf-8')
