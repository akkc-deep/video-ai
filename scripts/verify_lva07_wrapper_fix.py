"""Run opt-in CPU repair tests and record exact source and result identities."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['LVA07_FIX_SOURCE'] = str(args.source_root.resolve())
    if any('comfyui_windows_portable' in p.lower() for p in sys.path):
        raise RuntimeError('Production import path in CPU proof environment')
    manifest = json.loads((args.source_root/'.lva07-manifest.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        actual = hashlib.sha256((args.source_root/item['path']).read_bytes()).hexdigest()
        if actual != item['sha256']:
            raise RuntimeError(f'Tested source identity mismatch: {item["path"]}')
    tests = Path(__file__).resolve().parents[1]/'tests/experiments'
    suite = unittest.defaultTestLoader.discover(str(tests),pattern='test_lva07*.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    import torch
    commit = subprocess.check_output(['git', '-C', str(args.source_root), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(args.source_root), 'status', '--porcelain'], text=True)
    report = {'fixture_tests_passed': result.wasSuccessful(), 'full_model_compatibility_verified': False,
              'tests_run': result.testsRun,
              'failures': [{'test': t.id(), 'traceback': trace} for t, trace in result.failures],
              'errors': [{'test': t.id(), 'traceback': trace} for t, trace in result.errors],
              'source_root': str(args.source_root.resolve()), 'local_git_commit': commit,
              'local_git_dirty': bool(dirty), 'source_manifest': manifest,
              'python': sys.version, 'executable': sys.executable, 'sys_path': sys.path,
              'torch': str(torch.__version__), 'torch_cuda': torch.version.cuda,
              'comfy_imported': any(k == 'comfy' or k.startswith('comfy.') for k in sys.modules),
              'node_module_evidence': 'complete standardize_lora_key_format function via AST; full node imports not executed',
              'test_file_sha256': {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(tests.glob('test_lva07*.py'))},
              'limitations': ['parsed synthetic patch inputs; no original LoRA payload consumption',
                              'CPU-bounded pair cloning only; no full 14B loading',
                              'scalar-scale float8_e4m3fn CPU fixture only, no fast FP8/GPU',
                              'no merged, complete node registration, video or quality acceptance']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
