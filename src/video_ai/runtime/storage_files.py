"""Metadata-only storage operations; never decode media or hash model files."""
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4


def read_record(path):
    with Path(path).open(encoding='utf-8-sig') as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f'invalid storage record: {path}')
    return value


def write_record(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.'+path.name+'.'+uuid4().hex+'.tmp')
    try:
        with temp.open('x', encoding='utf-8', newline='\n') as file:
            json.dump(value, file, ensure_ascii=False, allow_nan=False, indent=2)
            file.write('\n'); file.flush(); os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def safe_path(path, root):
    """Check the lexical absolute boundary and every existing reparse component."""
    from .paths import _validate_spelling
    path, root = Path(path), Path(root)
    _validate_spelling(path)
    if not path.is_absolute() or '..' in path.parts or not path.is_relative_to(root):
        raise ValueError(f'storage path outside managed root: {path}')
    for item in (path, *path.parents):
        if item.is_symlink() or item.is_junction():
            raise ValueError(f'redirected storage path: {item}')
    if path.resolve(strict=False) != path:
        raise ValueError(f'storage path changed: {path}')
    return path


def inventory(path):
    """Return logical sizes and JSON filenames, refusing links rather than following."""
    path = Path(path)
    total = files = directories = 0
    records = []
    if not path.exists():
        return dict(logical_bytes=0, files=0, directories=0, json_paths=[])
    safe_path(path,path)
    if path.is_file():
        return dict(logical_bytes=path.stat().st_size,files=1,directories=0,
                    json_paths=[path] if path.suffix=='.json' else [])
    pending = [path]
    while pending:
        folder = safe_path(pending.pop(), path)
        with os.scandir(folder) as entries:
            for entry in entries:
                if entry.is_symlink() or (hasattr(entry, 'is_junction') and entry.is_junction()):
                    raise ValueError(f'reparse point in storage tree: {entry.path}')
                if entry.is_dir(follow_symlinks=False):
                    directories += 1; pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    files += 1; total += entry.stat(follow_symlinks=False).st_size
                    if entry.name.endswith('.json'):
                        records.append(Path(entry.path))
    return dict(logical_bytes=total, files=files, directories=directories, json_paths=records)


def remove_tree(path, root):
    path = safe_path(path, root)
    if path == Path(root):
        raise ValueError('cannot remove the disposable root')
    inventory(path)  # Includes every child before recursive deletion; no media reads.
    if path.exists():
        if path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)


def materialize_immutable(source, target):
    """Link a closed, immutable local asset; fall back to an exclusive ordinary copy."""
    source,target = Path(source),Path(target)
    try:
        os.link(source,target)
        return
    except FileExistsError:
        raise
    except OSError:
        pass  # Cross-volume/filesystem limitations are ordinary copy cases.
    with source.open('rb') as incoming,target.open('xb') as outgoing:
        shutil.copyfileobj(incoming,outgoing,1024*1024)
        outgoing.flush(); os.fsync(outgoing.fileno())
