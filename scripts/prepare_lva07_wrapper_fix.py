"""Rebuild the isolated audited Wrapper repair from local snapshots only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess


def prepare(source: Path, destination: Path, artifacts: Path) -> dict:
    manifest = json.loads((artifacts/'manifest.json').read_text(encoding='utf-8'))
    if destination.exists():
        raise ValueError('Destination already exists; refusing to overwrite it')
    content = {}
    source = source.resolve(strict=True)
    for item in manifest['baseline_files']:
        relative = PurePosixPath(item['path'])
        if relative.is_absolute() or '..' in relative.parts or ':' in str(relative):
            raise ValueError('Unsafe source manifest path')
        path = (source/str(relative)).resolve(strict=True)
        path.relative_to(source)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError(f'Source identity mismatch: {relative}')
        content[str(relative)] = raw
    for name, expected in manifest['artifacts'].items():
        if hashlib.sha256((artifacts/name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Repair artifact identity mismatch: {name}')
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    for relative, raw in content.items():
        target = destination/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    def git(*args):
        return subprocess.run(['git', '-C', str(destination), *args],
                              check=True, capture_output=True, text=True).stdout.strip()
    git('init', '-b', 'lva07/mixed-delta-fix')
    git('config', 'core.autocrlf', 'false')
    git('add', '.')
    git('-c', 'user.name=Codex', '-c', 'user.email=codex@local',
        'commit', '-m', 'audit: frozen partial Wrapper snapshot a7439db')
    baseline_commit = git('rev-parse', 'HEAD')
    repair = str((artifacts/'mixed-delta.patch').resolve())
    git('apply', '--check', repair)
    git('apply', repair)
    additions=[]
    for name in manifest['artifacts']:
        if name=='mixed-delta.patch':
            continue
        if PurePosixPath(name).name != name or ':' in name:
            raise ValueError('Unsafe repair artifact filename')
        (destination/name).write_bytes((artifacts/name).read_bytes())
        additions.append(name)
    identities = [{'path': relative, 'sha256': hashlib.sha256((destination/relative).read_bytes()).hexdigest()}
                  for relative in [*content, *additions]]
    result = {'upstream_reference': manifest['upstream_reference'],
              'partial_audited_snapshot': True, 'local_baseline_commit': baseline_commit,
              'files': identities, 'patch_sha256': manifest['artifacts']['mixed-delta.patch']}
    (destination/'.lva07-manifest.json').write_bytes((json.dumps(result, indent=2)+'\n').encode('utf-8'))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    artifacts = Path(__file__).resolve().parents[1]/'patches/wanvideo-wrapper'
    try:
        result = prepare(args.source_root, args.destination, artifacts)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(json.dumps({'destination': str(args.destination), 'files': len(result['files']),
                      'local_baseline_commit': result['local_baseline_commit'],
                      'partial_audited_snapshot': True}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
