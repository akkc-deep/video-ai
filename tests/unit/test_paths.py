from datetime import datetime
import hashlib
import importlib
import os
from pathlib import Path
import re
import subprocess
import uuid

import pytest


def paths():
    return importlib.import_module('video_ai.runtime.paths')


def create_junction(junction, destination):
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                             '$ErrorActionPreference="Stop"; New-Item -ItemType Junction -Path $env:VAI_TEST_JUNCTION -Target $env:VAI_TEST_TARGET | Out-Null'],
                            env={**os.environ, 'VAI_TEST_JUNCTION': str(junction),
                                 'VAI_TEST_TARGET': str(destination)}, capture_output=True, text=True)
    if result.returncode:
        pytest.skip('junction creation unavailable: ' + result.stderr)


def test_relative_paths_use_their_owner_and_leave_cwd(tmp_path):
    p = paths()
    before = Path.cwd()
    owner = tmp_path / '中文 目录' / 'config.json'
    assert p.resolve_config_path('../声音/a.wav', owner) == tmp_path / '声音/a.wav'
    assert p.resolve_cli_path('中文/a.txt', tmp_path) == tmp_path / '中文/a.txt'
    assert Path.cwd() == before


@pytest.mark.parametrize('value', [
    'C:/Windows/out.mp4', 'D:/code/py/video-ai/out.mp4',
    'D:/VideoSi-other/output/video-ai/out.mp4',
    'D:/VideoSi/output/video-ai/../../../escaped.mp4',
    '//server/share/out.mp4', '//?/D:/VideoSi/output/video-ai/a.mp4',
    'D:relative.mp4', 'D:/VideoSi/output/video-ai/a.mp4:stream',
    'D:/VideoSi/output/video-ai/NUL.mp4',
    'D:/VideoSi/output/video-ai/CON .mp4',
    'D:/VideoSi/output/video-ai/COM¹.mp4',
    'D:/VideoSi/output/video-ai/LPT².mp4',
    'D:/VideoSi/output/video-ai/control\x01.mp4',
    'D:/VideoSi/output/video-ai/foo./out.mp4',
])
def test_write_policy_rejects_escape_and_windows_aliases(value):
    with pytest.raises(ValueError):
        paths().PathPolicy().validate_write(value, 'output')


def test_category_and_case_are_checked_by_components():
    policy = paths().PathPolicy()
    assert policy.validate_write('d:/videosi/output/video-ai/movie.mp4', 'output').is_absolute()
    with pytest.raises(ValueError):
        policy.validate_write('D:/VideoSi/cache/video-ai/movie.mp4', 'output')


@pytest.mark.parametrize('field,root', [
    ('runtime_root', 'D:/VideoSi'), ('source_root', 'D:/code/py/video-ai'),
])
def test_policy_supplied_roots_preserve_resolution_checks(field, root):
    p = paths()
    canonical = Path(root)
    for supplied in (Path(root.lower()), canonical / '..' / canonical.name):
        policy = p.PathPolicy(**{field: supplied})
        assert getattr(policy, field) == supplied
        assert policy.validate_write(p.OUTPUT_ROOT / 'root-check.mp4', 'output') == p.OUTPUT_ROOT / 'root-check.mp4'
    with pytest.raises(ValueError, match=field):
        p.PathPolicy(**{field: canonical / 'different-root'})


@pytest.mark.parametrize('field,target', [
    ('runtime_root', 'D:/VideoSi'), ('source_root', 'D:/code/py/video-ai'),
])
def test_policy_noncanonical_junction_root_uses_its_current_target(tmp_path, field, target):
    junction = tmp_path / 'root-alias'
    create_junction(junction, target)
    try:
        assert getattr(paths().PathPolicy(**{field: junction}), field) == junction
        junction.rmdir()
        create_junction(junction, tmp_path)
        with pytest.raises(ValueError, match=field):
            paths().PathPolicy(**{field: junction})
    finally:
        if junction.is_junction():
            junction.rmdir()


def test_write_policy_resolves_again_after_junction_is_redirected(tmp_path):
    policy = paths().PathPolicy()
    allowed = tmp_path / 'allowed'
    allowed.mkdir()
    junction = tmp_path / 'write-alias'
    create_junction(junction, allowed)
    candidate = junction / 'candidate.log'
    try:
        assert policy.validate_write(candidate, 'cache') == allowed / 'candidate.log'
        junction.rmdir()
        create_junction(junction, 'D:/code/py/video-ai')
        with pytest.raises(ValueError):
            policy.validate_write(candidate, 'cache')
    finally:
        if junction.is_junction():
            junction.rmdir()
    assert not (allowed / 'candidate.log').exists()


def test_junction_to_source_is_rejected(tmp_path):
    junction = tmp_path / 'junction'
    # PowerShell creates a junction without changing or deleting its target.
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                             '$ErrorActionPreference="Stop"; New-Item -ItemType Junction -Path $env:VAI_TEST_JUNCTION -Target $env:VAI_TEST_TARGET | Out-Null'],
                            env={**os.environ, 'VAI_TEST_JUNCTION': str(junction),
                                 'VAI_TEST_TARGET': 'D:/code/py/video-ai'}, capture_output=True, text=True)
    if result.returncode:
        pytest.skip('junction creation unavailable: ' + result.stderr)
    try:
        with pytest.raises(ValueError):
            paths().PathPolicy().validate_write(junction / 'bad.log', 'cache')
    finally:
        junction.unlink() if junction.is_symlink() else junction.rmdir()


def test_run_ids_have_local_timestamp_and_unique_random_part():
    ids = {paths().new_run_id(datetime(2026, 10, 3, 12, 34, 56)) for _ in range(100)}
    assert len(ids) == 100
    assert all(re.fullmatch(r'20261003-123456-[0-9a-f]{12}', value) for value in ids)


def test_run_creation_does_not_overwrite_existing(monkeypatch):
    p = paths()
    from video_ai.config import load_config
    rp = p.RuntimePaths.from_config(load_config(Path('config/production.example.json').resolve()))
    unique = 'test-' + uuid.uuid4().hex
    monkeypatch.setattr(p, 'new_run_id', lambda: unique)
    run = p.create_run(rp)
    sentinel = run / 'sentinel'
    sentinel.write_bytes(b'keep')
    with pytest.raises(FileExistsError):
        p.create_run(rp)
    assert sentinel.read_bytes() == b'keep'
    assert p.shot_dir(run, 'shot_0001') == run / 'shots/shot_0001'


@pytest.mark.parametrize('shot', ['shot_0000', 'shot_0', 'shot_1', '../shot_0001', 'shot_0001/a', 'shot_０００１'])
def test_shot_name_rejects_invalid_or_injected_id(shot):
    with pytest.raises(ValueError):
        paths().shot_dir(Path('D:/VideoSi/projects/video-ai/runs/test'), shot)


@pytest.mark.parametrize('existing', ['.mp4', '.srt'])
def test_output_pair_refuses_either_existing_file_without_modification(existing):
    folder = Path('D:/VideoSi/output/video-ai/tests') / uuid.uuid4().hex
    folder.mkdir(parents=True)
    movie = folder / '中文 movie.mp4'
    occupied = movie.with_suffix(existing)
    occupied.write_bytes(b'existing artifact')
    before = hashlib.sha256(occupied.read_bytes()).hexdigest()
    try:
        with pytest.raises(FileExistsError):
            paths().validate_output_pair(movie)
        assert hashlib.sha256(occupied.read_bytes()).hexdigest() == before
    finally:
        if occupied.parent != folder or folder.resolve(strict=True) != folder:
            raise ValueError('test output cleanup redirected')
        if occupied.read_bytes() != b'existing artifact':
            raise ValueError('test output cleanup file changed')
        occupied.unlink()
        folder.rmdir()


def test_output_pair_calculates_srt_and_rejects_wrong_extension():
    movie = Path('D:/VideoSi/output/video-ai') / (uuid.uuid4().hex + '.mp4')
    assert paths().validate_output_pair(movie) == (movie, movie.with_suffix('.srt'))
    with pytest.raises(ValueError):
        paths().validate_output_pair(movie.with_suffix('.avi'))
