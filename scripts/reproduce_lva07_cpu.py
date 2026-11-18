"""Opt-in fixed-source CPU characterization. Expected RED is NOT a fix/pass.

Run only with the separately authorized CPU interpreter; no Comfy/node imports.
Inputs are synthetic parsed-diff tuples, not the full LightX2V payloads.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.machinery
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import types
import unittest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--source-evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['HF_HUB_DISABLE_XET'] = '1'
    if any('comfyui_windows_portable' in p.lower() for p in sys.path):
        raise RuntimeError('Production package path in sys.path')

    import torch

    if str(torch.__version__) != '2.14.1+cpu' or torch.version.cuda is not None:
        raise RuntimeError('Requires the authorized CPU-only torch 2.14.1')
    torch.set_num_threads(1)

    previous = json.loads(args.source_evidence.read_text(encoding='utf-8'))
    expected_hashes = {f['path']: f['sha256'] for f in previous['wrapper_files']}
    files = []
    for relative in ['custom_linear.py', 'gguf/gguf_utils.py']:
        path = args.source_root / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected_hashes[relative]:
            raise RuntimeError(f'Frozen source mismatch: {relative}')
        files.append({'path': str(path.resolve()), 'sha256': actual})

    # Namespace resolution only: actual complete modules and dependencies execute.
    # Do not execute the Wrapper node-registration __init__.py.
    for name, path in [('lva07_frozen', args.source_root),
                       ('lva07_frozen.gguf', args.source_root / 'gguf')]:
        namespace = types.ModuleType(name)
        namespace.__path__ = [str(path.resolve())]
        namespace.__package__ = name
        namespace.__spec__ = importlib.machinery.ModuleSpec(name, loader=None, is_package=True)
        namespace.__spec__.submodule_search_locations = namespace.__path__
        sys.modules[name] = namespace
    custom = importlib.import_module('lva07_frozen.custom_linear')
    records = []
    dtype = torch.float64

    class MixedDeltaCPU(unittest.TestCase):
        def model(self):
            root = torch.nn.Module()
            block = torch.nn.Module()
            block.modulation = torch.nn.Parameter(torch.ones((1, 6, 2), dtype=dtype))
            block.cross_attn = torch.nn.Module()
            block.cross_attn.k = custom.CustomLinear(
                2, 2, bias=True, compute_dtype=dtype, device=torch.device('cpu'),
                allow_compile=False).to(dtype=dtype)
            with torch.no_grad():
                block.cross_attn.k.weight.copy_(torch.eye(2, dtype=dtype))
                block.cross_attn.k.bias.copy_(torch.tensor([0.5, -0.5], dtype=dtype))
            root.blocks = torch.nn.ModuleList([block])
            root.head = torch.nn.Module()
            root.head.modulation = torch.nn.Parameter(torch.ones((1, 2, 2), dtype=dtype))
            root.head.proj = torch.nn.Linear(2, 2, dtype=dtype)
            return root

        def compare(self, *, source_key, target, kind, actual, expected):
            self.assertEqual(actual.device.type, 'cpu')
            self.assertEqual(expected.device.type, 'cpu')
            error = (actual.detach() - expected).abs().max().item()
            records.append({
                'test': self.id().split('.')[-1], 'source_key_example': source_key,
                'target': target, 'patch_kind': kind,
                'input_origin': 'synthetic parsed diff tuple; no LoRA payload loaded',
                'dtype': str(actual.dtype), 'parameter_storage_dtype': 'torch.float64',
                'device': actual.device.type,
                'expected': expected.tolist(), 'actual': actual.detach().tolist(),
                'max_abs_error': error, 'atol': 1e-12, 'rtol': 0,
                'outcome': 'matches_reference' if error <= 1e-12 else 'RED_missing_application',
            })
            torch.testing.assert_close(actual.detach(), expected, atol=1e-12, rtol=0)

        def test_weight_diff_control(self):
            root = self.model()
            delta = torch.full((2, 2), 0.25, dtype=dtype)
            key = 'diffusion_model.blocks.0.cross_attn.k.weight'
            custom.set_lora_params(root, {key: [(0.5, ('diff', (delta,)), 1.0, None, None)]})
            actual = root.blocks[0].cross_attn.k(torch.tensor([[1., 2.]], dtype=dtype))
            # (I + 0.5 * 0.25 * ones) @ [1,2] + [0.5,-0.5].
            self.compare(source_key='diffusion_model.blocks.0.cross_attn.k.diff',
                         target=key, kind='diff', actual=actual,
                         expected=torch.tensor([[1.875, 1.875]], dtype=dtype))

        def test_high_block_modulation_is_applied(self):
            root = self.model()
            key = 'diffusion_model.blocks.0.modulation'
            delta = torch.full((1, 6, 2), 0.25, dtype=dtype)
            custom.set_lora_params(root, {key: [(0.5, ('diff', (delta,)), 1.0, None, None)]})
            self.compare(source_key='diffusion_model.blocks.0.diff_m', target=key,
                         kind='diff_m_normalized_to_modulation_diff',
                         actual=root.blocks[0].modulation,
                         expected=torch.full((1, 6, 2), 1.125, dtype=dtype))

        def test_high_head_modulation_is_applied(self):
            root = self.model()
            key = 'diffusion_model.head.modulation'
            delta = torch.full((1, 2, 2), 0.25, dtype=dtype)
            custom.set_lora_params(root, {key: [(0.5, ('diff', (delta,)), 1.0, None, None)]})
            self.compare(source_key='diffusion_model.head.diff_m', target=key,
                         kind='diff_m_normalized_to_modulation_diff',
                         actual=root.head.modulation,
                         expected=torch.full((1, 2, 2), 1.125, dtype=dtype))

        def test_low_bias_delta_changes_forward(self):
            root = self.model()
            key = 'diffusion_model.blocks.0.cross_attn.k.bias'
            delta = torch.tensor([0.25, -0.75], dtype=dtype)
            custom.set_lora_params(root, {key: [(0.5, ('diff', (delta,)), 1.0, None, None)]})
            actual = root.blocks[0].cross_attn.k(torch.tensor([[1., 2.]], dtype=dtype))
            # I @ [1,2] + [0.5,-0.5] + 0.5 * [0.25,-0.75].
            self.compare(source_key='diffusion_model.blocks.0.cross_attn.k.diff_b',
                         target=key, kind='diff_b', actual=actual,
                         expected=torch.tensor([[1.625, 1.125]], dtype=dtype))

    suite = unittest.TestSuite(MixedDeltaCPU(name) for name in [
        'test_weight_diff_control', 'test_high_block_modulation_is_applied',
        'test_high_head_modulation_is_applied', 'test_low_bias_delta_changes_forward'])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    evidence = {
        'baseline_wrapper_commit': 'a7439db30bed0c5b5fa437d77ae8a7bb220dfd00',
        'python': sys.version, 'executable': sys.executable, 'sys_path': sys.path,
        'torch': str(torch.__version__), 'torch_cuda': torch.version.cuda,
        'installed': {n: importlib.metadata.version(n) for n in ['torch', 'accelerate', 'gguf', 'numpy']},
        'imported_sources': files, 'namespace_shim': 'package path resolution only; complete real modules',
        'custom_op_path': True, 'compile_requested': False,
        'comfy_imported': any(n == 'comfy' or n.startswith('comfy.') for n in sys.modules),
        'cases': records, 'tests_run': result.testsRun,
        'failures': [{'test': t.id(), 'traceback': trace} for t, trace in result.failures],
        'errors': [{'test': t.id(), 'traceback': trace} for t, trace in result.errors],
        'fixture_tests_passed': result.wasSuccessful(),
        'full_compatibility_verified': False,
        'stop_condition': 'missing application; no expansion or GPU' if result.failures else None,
        'limitations': ['Synthetic parsed-diff fixtures only; no full LoRA payload consumption',
                        'No full nodes_model_loading/utils module imports',
                        'No merged/FP8/full-model/pair atomicity validation'],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
