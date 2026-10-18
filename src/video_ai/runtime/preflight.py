"""Local resource/capability checks. No HTTP, model loading or run creation."""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4

from ..config import ProjectConfig
from ..jimeng_config import STRATEGY, active_models, active_workflows
from .environment import build_child_env
from .paths import RuntimePaths, validate_output_pair
from .workflows import validate_workflow


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    passed: bool
    details: str


@dataclass(frozen=True)
class PreflightReport:
    checks: tuple[PreflightCheck, ...]
    log_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    def as_dict(self) -> dict:
        return {'schema_version': 1, 'checks': [asdict(c) for c in self.checks],
                'passed': self.passed, 'log_dir': str(self.log_dir) if self.log_dir else None,
                'full_run_space_checked': False, 'inference_verified': False,
                'fast_profile_verified': False}


def parse_capabilities(text: str, kind: str) -> set[str]:
    if kind not in ('filters', 'encoders'):
        raise ValueError('expected filters or encoders')
    flags = r'[TSC\.]{2,3}' if kind == 'filters' else r'[VAS\.][A-Z\.]{5}'
    pattern = re.compile(r'^\s*' + flags + r'\s+([a-zA-Z0-9_]+)\s+')
    return {match.group(1) for line in text.splitlines() if (match := pattern.match(line))}


def preflight(config: ProjectConfig, *, script: Path | None = None, output: Path | None = None,
              disk_usage=shutil.disk_usage, runner=subprocess.run, log_dir: Path | None = None,
              automatic: bool = False) -> PreflightReport:
    checks = []
    paths = RuntimePaths.from_config(config)
    policy = paths.policy
    try:
        paths.validate()
        for path in config.tools.values():
            policy.validate_write(path, 'tool-env')
        for path in active_models(config).values():
            policy.validate_write(path, 'model')
        for field in ('gpt_weights', 'sovits_weights', 'bert_root', 'hubert_root'):
            policy.validate_write(getattr(config.voice, field), 'model')
        if output is not None:
            validate_output_pair(output)
    except (ValueError, OSError) as exc:
        return PreflightReport((PreflightCheck('paths', False, str(exc)),))
    checks.append(PreflightCheck('paths', True, 'all planned writable paths are inside category roots; no outputs overwritten'))

    def record(name, action):
        try:
            details = action()
            checks.append(PreflightCheck(name, True, str(details)))
            return True
        except (OSError, ValueError, TypeError, KeyError) as exc:
            checks.append(PreflightCheck(name, False, str(exc)))
            return False

    def readable(path, directory=False):
        if directory:
            if not path.is_dir():
                raise ValueError(f'missing directory: {path}')
            next(path.iterdir(), None)
        else:
            with path.open('rb') as file:
                if not file.read(1):
                    raise ValueError(f'empty file: {path}')
        return f'readable: {path}'

    def text_script():
        if not script.read_text(encoding='utf-8-sig').strip():
            raise ValueError(f'empty UTF-8 script: {script}')
        return f'UTF-8 script readable: {script}'

    if script is not None:
        record('script', text_script)
    record('voice.reference_text', lambda: 'explicit nonempty transcription recorded' if config.voice.reference_text.strip()
           else (_ for _ in ()).throw(ValueError('empty reference transcription')))
    reference_ok = record('voice.reference_audio', lambda: readable(config.voice.reference_audio))
    if reference_ok:
        def reference_hash():
            with config.voice.reference_audio.open('rb') as file:
                actual = hashlib.file_digest(file, 'sha256').hexdigest()
            if actual != config.voice.reference_sha256:
                raise ValueError(f'reference SHA256 mismatch: {config.voice.reference_audio}')
            return f'SHA256 matches: {config.voice.reference_audio}'
        record('voice.reference_sha256', reference_hash)
    record('font_file', lambda: readable(config.media.font_file))
    if config.media.music is not None:
        record('music', lambda: readable(config.media.music))
    tool_readable = {}
    for name, path in config.tools.items():
        tool_readable[name] = record('tools.' + name, lambda p=path, n=name: readable(p, n.endswith('_root')))
    for name, path in active_models(config).items():
        record('models.' + name, lambda p=path: readable(p))
    for field in ('gpt_weights', 'sovits_weights', 'bert_root', 'hubert_root'):
        record('voice.' + field, lambda n=field: readable(getattr(config.voice, n), n.endswith('_root')))
    for name, path in active_workflows(config).items():
        record('workflows.' + name, lambda p=path: readable(p))

    requested_log_dir = log_dir
    log_dir = None
    commands = []
    try:
        env = build_child_env(paths)
        log_dir = (policy.validate_write(requested_log_dir, 'run') if requested_log_dir is not None
                   else policy.validate_write(paths.cache_root / 'doctor' / uuid4().hex, 'cache'))
        log_dir.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError) as exc:
        checks.append(PreflightCheck('environment', False, str(exc)))
    else:
        checks.append(PreflightCheck('environment', True, f'child cache/log redirection: {log_dir}'))

        def query(tool, flag, label, capability_kind=None, expected=()):
            args = [str(config.tools[tool]), '-hide_banner', flag]
            stdout_path, stderr_path = log_dir / (label + '.stdout.txt'), log_dir / (label + '.stderr.txt')
            command = {'args': args, 'cwd': str(log_dir), 'timeout_seconds': 30,
                       'stdout': str(stdout_path), 'stderr': str(stderr_path),
                       'returncode': None, 'timed_out': False, 'error': None}
            try:
                with stdout_path.open('w', encoding='utf-8') as stdout, stderr_path.open('w', encoding='utf-8') as stderr:
                    result = runner(args, cwd=str(log_dir), env=env, timeout=30, stdout=stdout,
                                    stderr=stderr, text=True, encoding='utf-8', errors='replace')
                command['returncode'] = result.returncode
                if result.returncode != 0:
                    raise ValueError(f'{label}: exit {result.returncode}; stderr: {stderr_path}')
                text = stdout_path.read_text(encoding='utf-8')
                if not text.strip():
                    raise ValueError(f'{label}: empty command response; log: {stdout_path}')
                if capability_kind:
                    available = parse_capabilities(text, capability_kind)
                    missing = sorted(set(expected) - available)
                    if missing:
                        raise ValueError(f'{label}: missing capabilities {", ".join(missing)}; log: {stdout_path}')
                checks.append(PreflightCheck(label, True, f'query exit 0; raw stdout/stderr: {log_dir}'))
            except subprocess.TimeoutExpired as exc:
                command['timed_out'] = True
                command['error'] = str(exc)
                checks.append(PreflightCheck(label, False, f'{label}: timeout after 30s; logs: {log_dir}'))
            except (OSError, ValueError) as exc:
                command['error'] = str(exc)
                checks.append(PreflightCheck(label, False, str(exc)))
            finally:
                commands.append(command)
                (log_dir / 'commands.json').write_text(json.dumps(commands, ensure_ascii=False, indent=2), encoding='utf-8')

        if tool_readable['ffmpeg']:
            query('ffmpeg', '-version', 'ffmpeg-version')
            query('ffmpeg', '-encoders', 'ffmpeg-encoders', 'encoders',
                  ('libx264', 'aac') if automatic else ('h264_nvenc', 'libx264', 'aac'))
            query('ffmpeg', '-filters', 'ffmpeg-filters', 'filters',
                  ('subtitles',) if automatic else ('subtitles', 'scale', 'loudnorm', 'amix', 'xfade'))
        if tool_readable['ffprobe']:
            query('ffprobe', '-version', 'ffprobe-version')

    def disk():
        usage = disk_usage(config.runtime_root)
        if usage.total <= 0 or usage.free <= 0:
            raise ValueError(f'D: no available disk space: free={usage.free}, total={usage.total}')
        return f'free={usage.free}, total={usage.total}; full_run_space_checked=false'
    record('disk', disk)
    for kind in (('wan', 'upscale') if config.production_strategy == STRATEGY else ('sdxl', 'wan', 'upscale')):
        workflow = config.workflows[kind]
        mapping = config.workflows['wan_mapping'] if kind == 'wan' else workflow.with_suffix('.mapping.json')
        def check_workflow(w=workflow, m=mapping):
            validate_workflow(w, m, config.models)
            return f'nodes/inputs/output/model filenames/template SHA256 match: {w}'
        record('workflow.' + kind, check_workflow)
    report = PreflightReport(tuple(checks), log_dir)
    if log_dir is not None:
        (log_dir / 'report.json').write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
    return report
