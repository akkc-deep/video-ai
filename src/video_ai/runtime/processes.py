"""Subprocess execution with live evidence and explicit production wait policy."""
from dataclasses import dataclass
from pathlib import Path
import subprocess
from uuid import uuid4

from .environment import CACHE_LOCATIONS
from .manifest import now
from .paths import PathPolicy, _validate_spelling
from .execution_limits import command_timeout


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    cwd: Path
    returncode: int | None
    timed_out: bool
    stdout_path: Path
    stderr_path: Path
    started_at: str
    finished_at: str


def validate_command(args, cwd, env):
    if not args or not all(isinstance(a,str) for a in args):
        raise ValueError('args must be nonempty strings')
    if not Path(_validate_spelling(args[0])).is_absolute():
        raise ValueError('executable must be absolute')
    # A -c body is code, not a file; positional script/file paths stay absolute.
    skip_code = False
    for arg in args[1:]:
        if skip_code:
            skip_code = False
            continue
        if arg == '-c':
            skip_code = True
        elif arg.lower().endswith(('.py', '.exe', '.ps1', '.json', '.yaml', '.yml')) and not Path(_validate_spelling(arg)).is_absolute():
            raise ValueError('file arguments must be absolute')
    policy = PathPolicy()
    good_cwd = None
    for category in ('run', 'cache', 'tool-env', 'input'):
        try:
            good_cwd = policy.validate_write(cwd,category)
            break
        except ValueError:
            pass
    if good_cwd is None or not good_cwd.is_dir():
        raise ValueError('cwd must be an existing absolute D:/VideoSi directory')
    for key in CACHE_LOCATIONS:
        if key not in env:
            raise ValueError(f'missing child cache location {key}')
        policy.validate_write(env[key],'cache')
    if 'OLLAMA_MODELS' not in env:
        raise ValueError('missing child Ollama model location')
    policy.validate_write(env['OLLAMA_MODELS'],'model')
    return tuple(args), good_cwd


def stop_process(process):
    """The caller must own this live Popen object. Never reconstruct it from PID."""
    if process.poll() is not None:
        return process.returncode
    process.terminate()
    try:
        return process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait(timeout=2)


def run_logged(args, *, cwd, env, timeout, logger, stage, unit_id=None):
    timeout = command_timeout(timeout)
    args, cwd = validate_command(args,cwd,env)
    token = uuid4().hex
    stdout_path, stdout = logger.open_exclusive(f'processes/{token}.stdout')
    stderr_path, stderr = logger.open_exclusive(f'processes/{token}.stderr')
    started_at = now()
    process, timed_out, interrupted = None, False, False
    logger.event(stage,unit_id,'command_started',dict(args=args,cwd=cwd,timeout=timeout,
                                                     stdout_path=stdout_path,stderr_path=stderr_path))
    try:
        process = subprocess.Popen(args,cwd=cwd,env=dict(env),stdout=stdout,stderr=stderr,shell=False)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stop_process(process)
            logger.exception(stage,unit_id,exc)
        except KeyboardInterrupt as exc:
            interrupted = True
            stop_process(process)
            logger.exception(stage,unit_id,exc)
            raise
    except Exception as exc:
        if process is not None:
            stop_process(process)
        logger.exception(stage,unit_id,exc)
        raise
    finally:
        stdout.close()
        stderr.close()
        finished_at = now()
        logger.event(stage,unit_id,'command_finished',dict(args=args,cwd=cwd,timeout=timeout,
                     returncode=process.returncode if process else None,timed_out=timed_out,
                     interrupted=interrupted,stdout_path=stdout_path,stderr_path=stderr_path,
                     started_at=started_at,finished_at=finished_at))
    return CommandResult(args,cwd,process.returncode,timed_out,stdout_path,stderr_path,started_at,finished_at)
