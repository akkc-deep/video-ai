"""Windows paths: resolve once, then enforce category roots before writes."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath
import re
import os
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from ..config import ProjectConfig

RUNTIME_ROOT = Path(os.environ.get('VIDEO_AI_RUNTIME_ROOT', 'E:/VideoAI')).absolute()
SOURCE_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = RUNTIME_ROOT / 'shared'
OUTPUT_ROOT = RUNTIME_ROOT / 'output'
CACHE_ROOT = RUNTIME_ROOT / 'scratch'
PRODUCTION_ROOT = RUNTIME_ROOT / 'work'
DISPOSABLE_ROOT = RUNTIME_ROOT / 'scratch'
_LOCAL_TIME = timezone(timedelta(hours=8), 'Asia/Shanghai')
_RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I)


def _validate_spelling(value: str | Path) -> str:
    text = str(value)
    if not text.strip() or any(ord(character) < 32 for character in text):
        raise ValueError('empty or invalid path')
    win = PureWindowsPath(text)
    if win.drive.startswith('\\\\') or text.replace('\\', '/').startswith('//'):
        raise ValueError('UNC and device paths are forbidden')
    if win.drive and not win.root:
        raise ValueError('drive-relative paths are forbidden')
    # A rooted path without a drive depends on the current drive.
    if win.root and not win.drive:
        raise ValueError('root-relative paths are forbidden')
    for part in win.parts[1:] if win.anchor else win.parts:
        if part in ('.', '..'):
            continue
        if ':' in part or any(c in part for c in '<>"|?*'):
            raise ValueError('ADS or invalid Windows path component')
        if part.endswith(('.', ' ')) or PureWindowsPath(part).is_reserved() or _RESERVED.match(part):
            raise ValueError('Windows path alias is forbidden')
    return text


def _resolve(value: str | Path, base: Path) -> Path:
    path = Path(_validate_spelling(value))
    return (path if path.is_absolute() else base / path).resolve(strict=False)


def resolve_config_path(value: str, config_file: Path) -> Path:
    return _resolve(value, config_file.resolve().parent)


def resolve_cli_path(value: str, invocation_cwd: Path) -> Path:
    return _resolve(value, invocation_cwd.resolve())


@dataclass(frozen=True)
class PathPolicy:
    runtime_root: Path = RUNTIME_ROOT
    source_root: Path = SOURCE_ROOT

    def __post_init__(self):
        # Equal lexical roots would resolve identically. Supplied aliases still
        # require fresh resolution; validate_write also resolves every candidate.
        root = Path(_validate_spelling(self.runtime_root))
        if not root.is_absolute():
            raise ValueError('runtime_root must be absolute')
        object.__setattr__(self, 'runtime_root', Path(os.path.abspath(root)))
        if Path(self.source_root).resolve() != SOURCE_ROOT:
            raise ValueError('source_root must identify this checkout')

    def validate_write(self, path: str | Path, category: str) -> Path:
        candidate = Path(_validate_spelling(path))
        if not candidate.is_absolute():
            raise ValueError('writes require an absolute local path')
        candidate = candidate.resolve(strict=False)
        root = Path(self.runtime_root)
        roots = {
            'config': (root/'shared/config',),
            'input': (root/'work', root/'shared/assets'),
            'run': (root/'work',), 'output': (root/'output',),
            'cache': (root/'scratch',root/'work'),
            'log': (root/'scratch',root/'work'),
            'tool-env': (root/'shared/tools',root/'shared/envs'),
            'model': (root/'shared/models',),
        }
        if category not in roots:
            raise ValueError(f'unknown write category: {category}')
        # Test-only in-process scope; never populated from a production CLI flag or environment.
        from .storage import _test_runtimes
        for sandbox in tuple(_test_runtimes):
            extra = {
                'config': (sandbox/'projects/video-ai/config',),
                'input': (sandbox/'projects/video-ai/inputs',),
                'run': (sandbox/'projects/video-ai/runs',sandbox/'projects/video-ai/productions'),
                'output': (sandbox/'output/video-ai',),
                'cache': (sandbox/'cache/video-ai',sandbox/'disposable/video-ai'),
                'log': (sandbox/'cache/video-ai',sandbox/'projects/video-ai/runs',sandbox/'projects/video-ai/productions',sandbox/'disposable/video-ai'),
                'tool-env': (sandbox/'tools',sandbox/'envs'), 'model': (sandbox/'models',),
            }
            roots[category] += extra[category]
            roots[category] += {
                'config': (sandbox/'shared/config',), 'input': (sandbox/'work',sandbox/'shared/assets'),
                'run': (sandbox/'work',), 'output': (sandbox/'output',),
                'cache': (sandbox/'scratch',sandbox/'work'), 'log': (sandbox/'scratch',sandbox/'work'),
                'tool-env': (sandbox/'shared/tools',sandbox/'shared/envs'), 'model': (sandbox/'shared/models',),
            }[category]
        # Do not resolve trusted roots: a redirected root must fail closed too.
        if not any(candidate.is_relative_to(root) for root in roots[category]):
            raise ValueError(f'{category}: path outside allowed runtime subtree: {candidate}')
        return candidate


@dataclass(frozen=True)
class RuntimePaths:
    runtime_root: Path
    project_root: Path
    config_root: Path
    input_root: Path
    runs_root: Path
    output_root: Path
    cache_root: Path
    env_root: Path

    @classmethod
    def from_config(cls, config: 'ProjectConfig') -> 'RuntimePaths':
        from .storage import _sandbox
        sandbox = _sandbox.get()
        if sandbox is not None:
            project = sandbox/'shared'
            return cls(sandbox,project,project/'config',sandbox/'work',sandbox/'work',
                       sandbox/'output',sandbox/'scratch/cache',project/'envs/video-ai')
        return cls(config.runtime_root, config.project_root, config.project_root / 'config',
                   config.runtime_root / 'work', config.runtime_root / 'work',
                   config.output_root, config.cache_root, config.runtime_root / 'shared/envs/video-ai')

    @property
    def policy(self) -> PathPolicy:
        return PathPolicy(self.runtime_root)

    @property
    def comfy_directories(self) -> dict[str, Path]:
        """Planned service paths; a concrete run supplies output/temp/user later."""
        return {'models': self.runtime_root / 'shared/models/comfyui', 'input': self.input_root,
                'output': self.runs_root, 'temp': self.cache_root / 'comfy/temp',
                'user': self.cache_root / 'comfy/user'}

    def validate(self) -> None:
        for field, category in [('config_root', 'config'), ('input_root', 'input'),
                                ('runs_root', 'run'), ('output_root', 'output'),
                                ('cache_root', 'cache'), ('env_root', 'tool-env')]:
            self.policy.validate_write(getattr(self, field), category)


def new_run_id(now: datetime | None = None) -> str:
    now = now or datetime.now(_LOCAL_TIME)
    if now.tzinfo is not None:
        now = now.astimezone(_LOCAL_TIME)
    return f'{now:%Y%m%d-%H%M%S}-{uuid4().hex[:12]}'


def create_run(paths: RuntimePaths) -> Path:
    from .storage import allocated_run
    managed = allocated_run()
    if managed is not None:
        return paths.policy.validate_write(managed, 'run')
    paths.validate()
    for _ in range(3):
        run = paths.policy.validate_write(paths.runs_root / new_run_id(), 'run')
        try:
            run.mkdir(parents=True, exist_ok=False)
            return run
        except FileExistsError:
            pass
    raise FileExistsError('run ID collided three times; no existing run was overwritten')


def validate_shot_id(shot_id: str) -> None:
    if not re.fullmatch(r'shot_[0-9]{4,}', shot_id) or int(shot_id[5:]) == 0:
        raise ValueError('shot_id must be shot_ followed by at least four ASCII digits and a positive integer')


def shot_dir(run_dir: Path, shot_id: str) -> Path:
    validate_shot_id(shot_id)
    return PathPolicy().validate_write(run_dir / 'shots' / shot_id, 'run')


def validate_output_pair(mp4_path: Path) -> tuple[Path, Path]:
    movie = PathPolicy().validate_write(mp4_path, 'output')
    if movie.suffix.lower() != '.mp4':
        raise ValueError('output must have .mp4 extension')
    subtitle = PathPolicy().validate_write(movie.with_suffix('.srt'), 'output')
    for path in (movie, subtitle):
        if path.exists() or path.is_symlink():
            raise FileExistsError(f'output already exists: {path}')
    return movie, subtitle
