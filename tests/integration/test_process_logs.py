from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time
import pytest


def test_output_is_visible_while_real_process_is_still_running(runtime_run):
    from video_ai.runtime.processes import run_logged
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.environment import build_child_env
    run, _, paths = runtime_run
    script = run/'stream.py'
    script.write_text('import sys,time\nprint("first stdout",flush=True)\nprint("first stderr",file=sys.stderr,flush=True)\ntime.sleep(1)\nprint("last stdout",flush=True)\n',encoding='utf-8')
    log = RunLogger(run)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run_logged,[sys.executable,'-u',str(script)],cwd=run,env=build_child_env(paths),timeout=5,logger=log,stage='validation')
        deadline = time.monotonic()+3
        found = False
        while time.monotonic()<deadline:
            out = list((run/'logs/processes').glob('*.stdout')) if (run/'logs/processes').exists() else []
            err = list((run/'logs/processes').glob('*.stderr')) if (run/'logs/processes').exists() else []
            if out and err and b'first stdout' in out[0].read_bytes() and b'first stderr' in err[0].read_bytes():
                found = True
                break
            time.sleep(.01)
        assert found and not future.done()
        result = future.result()
    assert result.returncode == 0 and not result.timed_out
    assert b'last stdout' in result.stdout_path.read_bytes()


@pytest.mark.parametrize('timeout,code,expected', [(3,'import sys; print("failure",file=sys.stderr,flush=True); sys.exit(7)',7),(.15,'import time; print("before timeout",flush=True); time.sleep(20)',None)])
def test_real_failure_and_timeout_keep_logs(runtime_run,timeout,code,expected):
    from video_ai.runtime.processes import run_logged
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.environment import build_child_env
    run,_,paths = runtime_run
    result = run_logged([sys.executable,'-u','-c',code],cwd=run,env=build_child_env(paths),timeout=timeout,logger=RunLogger(run),stage='validation')
    if expected is not None:
        assert result.returncode == expected and not result.timed_out
        assert b'failure' in result.stderr_path.read_bytes()
    else:
        assert result.timed_out and result.returncode != 0
        assert b'before timeout' in result.stdout_path.read_bytes()


def test_interruption_records_and_only_terminates_held_process(runtime_run,monkeypatch):
    import video_ai.runtime.processes as module
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.environment import build_child_env
    run,_,paths = runtime_run
    class Process:
        pid=123
        returncode=None
        terminated=False
        def poll(self): return self.returncode
        def wait(self,timeout=None):
            if not self.terminated: raise KeyboardInterrupt()
            self.returncode=-15
            return -15
        def terminate(self): self.terminated=True
    process=Process()
    monkeypatch.setattr(module.subprocess,'Popen',lambda *a,**k:process)
    with pytest.raises(KeyboardInterrupt):
        module.run_logged([sys.executable,'-c','pass'],cwd=run,env=build_child_env(paths),timeout=1,logger=RunLogger(run),stage='speech')
    assert process.terminated
    records=[json.loads(line) for line in (run/'logs/events.jsonl').read_text().splitlines()]
    assert any(r['event']=='command_finished' and r['details']['interrupted'] for r in records)


def test_process_refuses_relative_executable_and_unsafe_env(runtime_run):
    from video_ai.runtime.processes import run_logged
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.environment import build_child_env
    run,_,paths=runtime_run
    env=build_child_env(paths)
    with pytest.raises(ValueError):
        run_logged(['python','-c','pass'],cwd=run,env=env,timeout=1,logger=RunLogger(run),stage='speech')
    env['TEMP']='C:/temp'
    with pytest.raises(ValueError):
        run_logged([sys.executable,'-c','pass'],cwd=run,env=env,timeout=1,logger=RunLogger(run),stage='speech')


def test_log_disk_failure_cannot_prevent_timeout_cleanup(runtime_run,monkeypatch):
    import subprocess
    import video_ai.runtime.processes as module
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.environment import build_child_env
    run,_,paths=runtime_run
    class Process:
        pid=123
        returncode=None
        terminated=False
        def poll(self):return self.returncode
        def wait(self,timeout=None):
            if not self.terminated:raise subprocess.TimeoutExpired(['test'],timeout)
            self.returncode=-15
            return -15
        def terminate(self):self.terminated=True
    process=Process()
    monkeypatch.setattr(module.subprocess,'Popen',lambda *a,**k:process)
    logger=RunLogger(run)
    def disk_full(*a,**k):raise OSError('log disk full')
    monkeypatch.setattr(logger,'exception',disk_full)
    with pytest.raises(OSError):module.run_logged([sys.executable,'-c','pass'],cwd=run,env=build_child_env(paths),timeout=.1,logger=logger,stage='validation')
    assert process.terminated
