"""Reviewable environment preparation commands; default action only inspects the plan.

This is not the LVA-07-04 worker or model admission implementation.
Run mutating stages only after authorization of the accompanying preparation plan.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import urllib.request

REPO = Path('E:/code/py/video-ai')
EVIDENCE = Path('E:/VideoAI/scratch/benchmarks/LVA-07-03-planning')
DEST = Path('E:/VideoAI/scratch/benchmarks/LVA-07-04-environment')
WRAPPER_SHA = 'a7439db30bed0c5b5fa437d77ae8a7bb220dfd00'
COMFY_SHA = '2c75dc1b379a59e0880619d029607af5169a62ef'
RESERVE = 8 * 1024**3
INPUTS = {
    EVIDENCE/'metadata.json': 'bb4e85921e8dc5e589209444dd5906a246b72375804fe518926118cc7bdf2cdf',
    EVIDENCE/'archive-binary-metadata.json': '13a4ec3c41b29147887db28785f53859f886941e71610934e682a99c0d5dc690',
    EVIDENCE/'additional-wheels.lock': '9ad1a5b5aba663af6d3a80c35f47b7ea657ad1411848472d697d791582cf82a4',
    REPO/'docs/task-designs/LVA-07-wrapper-tree.json': '6f981a6b15b4e57154902c8007e80791c0b4000badddfb220152bc959ba05dd2',
}


def sha(path, algorithm='sha256'):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def read_inputs():
    for path, expected in INPUTS.items():
        if sha(path) != expected:
            raise RuntimeError(f'Planning input changed: {path}')
    m = json.loads((EVIDENCE/'metadata.json').read_text(encoding='utf-8'))
    a = json.loads((EVIDENCE/'archive-binary-metadata.json').read_text(encoding='utf-8'))
    tree = json.loads((REPO/'docs/task-designs/LVA-07-wrapper-tree.json').read_text(encoding='utf-8'))
    return m, a, tree


def run(argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, check=True, capture_output=True, text=True,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def new_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(content)


def marker(stage, data):
    new_file(DEST/f'{stage}.json', (json.dumps(data, indent=2)+'\n').encode())


def require_stage(stage):
    if not (DEST/f'{stage}.json').is_file():
        raise RuntimeError(f'Required stage missing: {stage}')


def download(url, count, algorithm, expected, prefix=b''):
    with urllib.request.urlopen(url, timeout=40) as response:
        data = response.read(count+1)
    if len(data) != count or hashlib.new(algorithm, prefix+data).hexdigest() != expected:
        raise RuntimeError(f'Download identity/size mismatch: {url}')
    return data


def sources(m, tree):
    if DEST.exists():
        raise RuntimeError('Destination must be new; never overwrite or automatically retry partial preparation')
    patch_dir = REPO/'patches/wanvideo-wrapper'
    patch_manifest = json.loads((patch_dir/'manifest.json').read_text())
    for name, expected in patch_manifest['artifacts'].items():
        if sha(patch_dir/name) != expected:
            raise RuntimeError('Repair artifact drift')
    if tree['truncated'] or any(r['type'] not in ('tree', 'blob') or r['mode'] not in ('040000','100644') for r in tree['tree']):
        raise RuntimeError('Unsupported source manifest')
    DEST.mkdir()
    archive = DEST/'comfy.tar'
    # Export the pinned committed tree, never a mutable production working tree.
    run(['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', '-C', 'E:/VideoAI/shared/tools/ComfyUI_windows_portable/ComfyUI',
         'archive', '--format=tar', f'--output={archive}', COMFY_SHA])
    if archive.stat().st_size > 64*1024**2:
        raise RuntimeError('Comfy archive exceeds approved 64 MiB bound')
    comfy = DEST/'ComfyUI'
    expected = {r['path']: r for r in m['comfy']['files']}
    seen = set()
    with tarfile.open(archive, 'r:') as tar:
        for item in tar:
            if item.isdir():
                continue
            path = PurePosixPath(item.name)
            if not item.isfile() or path.is_absolute() or '..' in path.parts or str(path) not in expected:
                raise RuntimeError('Unexpected Comfy archive member')
            row = expected[str(path)]
            if str(path) in seen or item.size != row['bytes']:
                raise RuntimeError('Comfy archive size/duplicate mismatch')
            data = tar.extractfile(item).read(item.size+1)
            blob = b'blob '+str(len(data)).encode()+b'\0'+data
            if hashlib.sha1(blob).hexdigest() != row['git_sha1']:
                raise RuntimeError('Comfy committed blob mismatch')
            new_file(comfy/str(path), data)
            seen.add(str(path))
    if seen != set(expected):
        raise RuntimeError('Incomplete Comfy source')
    wrapper = comfy/'custom_nodes/ComfyUI-WanVideoWrapper-LVA07'
    for row in tree['tree']:
        if row['type'] != 'blob':
            continue
        path = PurePosixPath(row['path'])
        if path.is_absolute() or '..' in path.parts:
            raise RuntimeError('Unsafe Wrapper path')
        data = download(f'https://raw.githubusercontent.com/kijai/ComfyUI-WanVideoWrapper/{WRAPPER_SHA}/{row["path"]}',
                        row['size'], 'sha1', row['sha'], b'blob '+str(row['size']).encode()+b'\0')
        new_file(wrapper/row['path'], data)
    for row in patch_manifest['baseline_files']:
        if sha(wrapper/row['path']) != row['sha256']:
            raise RuntimeError('Audited baseline mismatch')
    run(['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', 'apply', '--check', str(patch_dir/'mixed-delta.patch')], cwd=wrapper)
    run(['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', 'apply', str(patch_dir/'mixed-delta.patch')], cwd=wrapper)
    for name in ('lva07_mixed_delta.py','lva07_applicability.py','lva07_img_policy.json'):
        new_file(wrapper/name, (patch_dir/name).read_bytes())
    for name, expected_hash in patch_manifest['patched_files'].items():
        if sha(wrapper/name) != expected_hash:
            raise RuntimeError('Patched source mismatch')
    files = [{'path': str(p.relative_to(wrapper)).replace('\\','/'), 'bytes': p.stat().st_size, 'sha256': sha(p)}
             for p in sorted(wrapper.rglob('*')) if p.is_file()]
    marker('sources', dict(comfy_commit=COMFY_SHA, wrapper_upstream=WRAPPER_SHA,
        kind='complete pinned source snapshot, not a git checkout', wrapper_files=files,
        full_node_import=False, gpu=False))


def runtime(m, a):
    require_stage('sources')
    target = DEST/'python_embeded'
    if target.exists():
        raise RuntimeError('Runtime target already exists')
    original = Path(m['runtime']['path'])
    target.mkdir()
    for row in m['runtime']['files']:
        src = original/row['path']
        stat = src.stat()
        if src.is_symlink() or (stat.st_size, stat.st_mtime_ns, stat.st_ino) != (row['bytes'], row['mtime_ns'], row['file_id']):
            raise RuntimeError('Runtime source drift; refresh proposal, do not improvise')
        dst = target/row['path']; dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        after = src.stat()
        if (after.st_size, after.st_mtime_ns, after.st_ino) != (stat.st_size, stat.st_mtime_ns, stat.st_ino):
            raise RuntimeError('Runtime changed during copy')
    for binary in a['runtime_binaries']:
        if sha(target/binary['path']) != binary['sha256']:
            raise RuntimeError('Independent binary copy mismatch')
    # Every entry resolves within the independent portable root.
    (target/'python313._pth').write_text('python313.zip\n.\nLib/site-packages\n../ComfyUI\nimport site\n', encoding='utf-8')
    marker('runtime', dict(files=len(m['runtime']['files']), copied_bytes=m['runtime']['bytes'],
        verified_binaries=len(a['runtime_binaries']), production_mutated=False))


def wheels(m):
    require_stage('runtime')
    target = DEST/'wheelhouse'
    if target.exists():
        raise RuntimeError('Wheelhouse already exists')
    target.mkdir()
    for pkg in m['new_packages']:
        data = download(pkg['url'], pkg['bytes'], 'sha256', pkg['sha256'])
        new_file(target/pkg['filename'], data)
    lock = '\n'.join(f"{p['name']}=={p['version']} --hash=sha256:{p['sha256']}" for p in m['new_packages'])+'\n'
    new_file(DEST/'additional-wheels.lock', lock.encode())
    marker('wheels', dict(count=len(m['new_packages']), bytes=m['wheel_download_bytes']))


def install(m):
    require_stage('wheels')
    if (DEST/'install.json').exists():
        raise RuntimeError('Install already completed')
    python = DEST/'python_embeded/python.exe'
    flags = ['--disable-pip-version-check','--no-cache-dir']
    proc = run([str(python), '-I', '-m', 'pip', *flags, 'install', '--no-index', '--no-deps',
        '--no-compile', '--require-hashes', '--find-links', str(DEST/'wheelhouse'),
        '-r', str(DEST/'additional-wheels.lock')], cwd=DEST)
    new_file(DEST/'pip-install.log', proc.stdout.encode())
    checked = run([str(python), '-I', '-m', 'pip', 'check'], cwd=DEST)
    actual = {re.sub(r'[-_.]+', '-', d.metadata['Name']).lower():d.version for d in
        importlib.metadata.distributions(path=[str(DEST/'python_embeded/Lib/site-packages')])}
    expected = {n:p['version'] for n,p in m['installed'].items()}
    expected.update({p['name']:p['version'] for p in m['new_packages']})
    if actual != expected:
        raise RuntimeError('Installed versions differ from immutable baseline plus additional wheels')
    marker('install', dict(pip_check=checked.stdout, versions=actual, node_import=False,
                          model_admission=False, service_start=False, gpu=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('inspect','sources','runtime','wheels','install'), default='inspect')
    args = parser.parse_args()
    m,a,tree = read_inputs()
    if args.stage == 'inspect':
        print(json.dumps(dict(destination=str(DEST), source_bytes=47250651,
            wheel_download_bytes=m['wheel_download_bytes'], runtime_copy_bytes=m['runtime']['bytes'],
            wheel_uncompressed_bytes=a['wheel_uncompressed_bytes'], disk_reserve_bytes=RESERVE,
            executed_mutations=0, task04_ready=False)))
        return
    if not DEST.resolve().is_relative_to(Path('E:/VideoAI/scratch/benchmarks').resolve()):
        raise RuntimeError('Destination escaped the explicitly named scratch directory')
    if shutil.disk_usage(DEST.parent).free < RESERVE:
        raise RuntimeError('8 GiB free-space prerequisite failed')
    if args.stage == 'sources':
        sources(m,tree)
    elif args.stage == 'runtime':
        runtime(m,a)
    elif args.stage == 'wheels':
        wheels(m)
    else:
        install(m)


if __name__ == '__main__':
    main()
