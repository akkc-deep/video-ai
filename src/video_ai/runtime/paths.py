"""Windows paths: resolve once, then enforce category roots before writes."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath
import re
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from ..config import ProjectConfig

RUNTIME_ROOT = Path('D:/VideoSi')
SOURCE_ROOT = Path('D:/code/py/video-ai')
PROJECT_ROOT = RUNTIME_ROOT / 'projects/video-ai'
OUTPUT_ROOT = RUNTIME_ROOT / 'output/video-ai'
CACHE_ROOT = RUNTIME_ROOT / 'cache/video-ai'
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
        runtime_root = Path(self.runtime_root)
        if runtime_root != RUNTIME_ROOT and runtime_root.resolve() != RUNTIME_ROOT.resolve():
            raise ValueError('runtime_root must be D:/VideoSi')
        source_root = Path(self.source_root)
        if source_root != SOURCE_ROOT and source_root.resolve() != SOURCE_ROOT.resolve():
            raise ValueError('source_root must be D:/code/py/video-ai')

    def validate_write(self, path: str | Path, category: str) -> Path:
        candidate = Path(_validate_spelling(path))
        if not candidate.is_absolute() or candidate.drive.casefold() != 'd:':
            raise ValueError('writes require an absolute local D: path')
        candidate = candidate.resolve(strict=False)
        roots = {
            'config': (PROJECT_ROOT / 'config',),
            'input': (PROJECT_ROOT / 'inputs',),
            'run': (PROJECT_ROOT / 'runs',),
            'output': (OUTPUT_ROOT,),
            'cache': (CACHE_ROOT,),
            'log': (CACHE_ROOT / 'logs', PROJECT_ROOT / 'runs'),
            'tool-env': (RUNTIME_ROOT / 'tools', RUNTIME_ROOT / 'envs/video-ai'),
            'model': (RUNTIME_ROOT / 'models',),
        }
        if category not in roots:
            raise ValueError(f'unknown write category: {category}')
        # Do not resolve trusted roots: a redirected root must fail closed too.
        if candidate.is_relative_to(SOURCE_ROOT) or not any(candidate.is_relative_to(root) for root in roots[category]):
            raise ValueError(f'{category}: path outside allowed D:/VideoSi subtree: {candidate}')
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
        return cls(config.runtime_root, config.project_root, config.project_root / 'config',
                   config.project_root / 'inputs', config.project_root / 'runs',
                   config.output_root, config.cache_root, config.runtime_root / 'envs/video-ai')

    @property
    def policy(self) -> PathPolicy:
        return PathPolicy(self.runtime_root)

    @property
    def comfy_directories(self) -> dict[str, Path]:
        """Planned service paths; a concrete run supplies output/temp/user later."""
        return {'models': self.runtime_root / 'models/comfyui', 'input': self.input_root,
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
    paths.validate()
    for _ in range(3):
        run = paths.policy.validate_write(paths.runs_root / new_run_id(), 'run')
        try:
            run.mkdir(parents=True, exist_ok=False)
            return run
        except FileExistsError:
            pass
    raise FileExistsError('run ID collided three times; no existing run was overwritten')


def shot_dir(run_dir: Path, shot_id: str) -> Path:
    if not re.fullmatch(r'shot_[0-9]{4,}', shot_id) or int(shot_id[5:]) == 0:
        raise ValueError('shot_id must be shot_ followed by at least four ASCII digits and a positive integer')
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
