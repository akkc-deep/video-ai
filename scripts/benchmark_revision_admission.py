"""Offline revision admission measurements; writes only the requested report."""
import argparse
from collections import Counter
import json
import hashlib
from pathlib import Path
import socket
import sys
import os
from time import perf_counter
from unittest.mock import patch
from video_ai.runtime import manifest, scene_revision_records as records, verification
from video_ai.runtime.production_inputs import load_frozen_inputs

parser = argparse.ArgumentParser()
parser.add_argument('--run', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
run = args.run.resolve(strict=True)
output = args.output.resolve()
if output.is_relative_to(run):
    parser.error('report must be outside production run')
source_root = Path(__file__).resolve().parents[1]/'src'
report = {'run': str(run), 'stages': {}, 'network_requests': 0,
          'source_sha256': {str(p.relative_to(source_root)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(source_root.rglob('*.py'))}}
report['metric_notes'] = 'hash_read_bytes counts actual Python read/readinto bytes during SHA256; hashed_bytes is summed input size; neither measures physical disk I/O. directory_traversals counts rglob invocations.'
counts = Counter()
paths = Counter()


def read_only_audit(event, values):
    if event == 'open':
        path, mode, flags = values
        writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        targets = (path,) if writing else ()
    elif event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.rename', 'os.replace', 'os.chmod', 'os.utime'):
        targets = values[:2] if event in ('os.rename', 'os.replace') else values[:1]
    else:
        return
    for value in targets:
        if isinstance(value, (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(value)).absolute()
            if path.is_relative_to(run) or path.is_relative_to(Path('E:/VideoAI/work')):
                raise RuntimeError('offline benchmark forbids production writes: '+event)


sys.addaudithook(read_only_audit)
report['production_write_guard'] = 'audit hook denies write opens and filesystem mutations under production work'
report['status'] = 'running'
original_hash = manifest._hash_open_file
original_rglob = Path.rglob


def scanned(path, pattern, *args, **kwargs):
    counts['directory_traversals'] += 1
    return original_rglob(path, pattern, *args, **kwargs)

def hashed(file, path):
    counts['hash_calls'] += 1
    counts['hashed_bytes'] += path.stat().st_size
    paths[str(path)] += 1
    class CountedReader:
        def __getattr__(self, name):
            return getattr(file, name)
        def readinto(self, buffer):
            size = file.readinto(buffer)
            counts['hash_read_bytes'] += size or 0
            return size
        def read(self, *args):
            value = file.read(*args)
            counts['hash_read_bytes'] += len(value)
            return value
    return original_hash(CountedReader(), path)

def denied(*a, **kw):
    raise RuntimeError('offline benchmark forbids network')

def measure(name, function):
    counts.clear()
    paths.clear()
    start = perf_counter()
    try:
        return function()
    finally:
        value = dict(hash_calls=0, hashed_bytes=0, hash_read_bytes=0, directory_traversals=0)
        value.update(counts)
        value.update(seconds=perf_counter()-start, unique_hashed_paths=len(paths),
                     max_hashes_per_path=max(paths.values(), default=0))
        report['stages'][name] = value
        output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({name: value}), flush=True)

with patch.object(socket.socket, 'connect', denied), patch.object(socket, 'create_connection', denied), patch.object(manifest, '_hash_open_file', hashed), patch.object(Path, 'rglob', scanned), verification.whole_input_protection(), records.revision_scope():
    frozen = measure('initial_load', lambda: load_frozen_inputs(run))
    proof = measure('initial_revision_admission', lambda: records.require_scene_revision(frozen))
    measure('warm_source_check', proof['guard'].verify_captured_bytes)
    measure('warm_config_load', lambda: load_frozen_inputs(run))
    def repeated():
        with records.revision_read_transaction():
            for _ in range(3):
                records.require_scene_revision(frozen)
    measure('three_reads_one_transaction', repeated)
    def checkpoint():
        with records.revision_checkpoint_transaction():
            records.require_scene_revision(frozen)
            records.revision_read_checkpoint()
    measure('read_checkpoint_and_exit', checkpoint)
report['status'] = 'completed'
report['source_unchanged_during_benchmark'] = all(
    hashlib.sha256((source_root/name).read_bytes()).hexdigest() == digest
    for name, digest in report['source_sha256'].items())
output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
