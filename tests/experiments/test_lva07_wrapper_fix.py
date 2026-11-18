"""Opt-in real-source CPU repair tests; no Comfy registration or GPU calls."""
import ast
import copy
import importlib
import importlib.machinery
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


SOURCE = os.environ.get('LVA07_FIX_SOURCE')


@unittest.skipUnless(SOURCE, 'Set LVA07_FIX_SOURCE to an isolated audited source copy')
class WrapperFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.dont_write_bytecode = True
        os.environ['CUDA_VISIBLE_DEVICES'] = ''
        import torch
        assert str(torch.__version__) == '2.14.1+cpu' and torch.version.cuda is None
        cls.torch = torch
        cls.root = Path(SOURCE)
        for name, path in [('lva07_test', cls.root), ('lva07_test.gguf', cls.root/'gguf')]:
            module = types.ModuleType(name)
            module.__path__ = [str(path)]
            module.__package__ = name
            module.__spec__ = importlib.machinery.ModuleSpec(name, loader=None, is_package=True)
            module.__spec__.submodule_search_locations = module.__path__
            sys.modules[name] = module
        cls.custom = importlib.import_module('lva07_test.custom_linear')

    def api(self):
        self.assertTrue((self.root/'lva07_mixed_delta.py').is_file(), 'Private pair application API is missing')
        return importlib.import_module('lva07_test.lva07_mixed_delta')

    def model(self, dtype=None):
        t = self.torch
        dtype = dtype or t.float64
        root = t.nn.Module()
        block = t.nn.Module()
        block.modulation = t.nn.Parameter(t.ones((1, 6, 2), dtype=dtype))
        block.norm = t.nn.LayerNorm(2, eps=0., dtype=dtype)
        block.cross_attn = t.nn.Module()
        block.cross_attn.k = self.custom.CustomLinear(2, 2, bias=True, compute_dtype=dtype,
                                                       device=t.device('cpu')).to(dtype=dtype)
        with t.no_grad():
            block.cross_attn.k.weight.copy_(t.eye(2, dtype=dtype))
            block.cross_attn.k.bias.copy_(t.tensor([.5, -.5], dtype=dtype))
        root.blocks = t.nn.ModuleList([block])
        root.head = t.nn.Module()
        root.head.modulation = t.nn.Parameter(t.ones((1, 2, 2), dtype=dtype))
        root.head.proj = t.nn.Linear(2, 2, dtype=dtype)
        root.register_buffer('counter', t.tensor(7))
        root.source_patches = {'old': [t.tensor([3.], dtype=dtype)]}
        return root

    def delta(self, shape, value=.25):
        return self.torch.full(shape, value, dtype=self.torch.float64)

    def diff(self, value, strength=.5):
        return [(strength, ('diff', (value,)), 1., None, None)]

    def patches(self):
        return {
            'diffusion_model.blocks.0.modulation': self.diff(self.delta((1, 6, 2))),
            'diffusion_model.head.modulation': self.diff(self.delta((1, 2, 2))),
            'diffusion_model.blocks.0.norm.weight': self.diff(self.delta((2,))),
            'diffusion_model.blocks.0.cross_attn.k.bias': self.diff(self.torch.tensor([.25, -.75], dtype=self.torch.float64)),
            'diffusion_model.blocks.0.cross_attn.k.weight': self.diff(self.delta((2, 2))),
        }

    def unchanged(self, model, before):
        self.assertEqual(set(model.state_dict()), set(before))
        for key, value in model.state_dict().items():
            self.torch.testing.assert_close(value, before[key], atol=0, rtol=0)

    def test_original_three_numeric_failures_and_weight_control_are_repaired(self):
        api = self.api(); t = self.torch
        for dtype in (t.float32, t.float64):
            with self.subTest(dtype=dtype):
                high, low = self.model(dtype), self.model(dtype)
                before_h, before_l = copy.deepcopy(high.state_dict()), copy.deepcopy(low.state_dict())
                hp = self.patches(); lp = self.patches()
                pair = api.prepare_lora_pair(high, low, hp, lp)
                for model in (pair.high, pair.low):
                    t.testing.assert_close(model.blocks[0].modulation, t.full((1, 6, 2), 1.125, dtype=dtype))
                    t.testing.assert_close(model.head.modulation, t.full((1, 2, 2), 1.125, dtype=dtype))
                    t.testing.assert_close(model.blocks[0].norm(t.tensor([[1., 3.]], dtype=dtype)), t.tensor([[-1.125, 1.125]], dtype=dtype))
                    # Weight and bias updates coexist: original bias-only expected + 0.375 weight contribution.
                    t.testing.assert_close(model.blocks[0].cross_attn.k(t.tensor([[1., 2.]], dtype=dtype)), t.tensor([[2., 1.5]], dtype=dtype))
                self.unchanged(high, before_h); self.unchanged(low, before_l)
                self.assertEqual(len(pair.manifest), 10)
                self.assertTrue(all(x['applied'] for x in pair.manifest))

    def test_original_bias_only_literal(self):
        api = self.api(); t = self.torch
        ps = {'diffusion_model.blocks.0.cross_attn.k.bias': self.diff(t.tensor([.25, -.75], dtype=t.float64))}
        pair = api.prepare_lora_pair(self.model(), self.model(), ps, {})
        t.testing.assert_close(pair.high.blocks[0].cross_attn.k(t.tensor([[1., 2.]], dtype=t.float64)), t.tensor([[1.625, 1.125]], dtype=t.float64))

    def test_weight_diff_only_literal(self):
        api = self.api(); t = self.torch
        ps = {'diffusion_model.blocks.0.cross_attn.k.weight': self.diff(self.delta((2, 2)))}
        pair = api.prepare_lora_pair(self.model(), self.model(), {}, ps)
        t.testing.assert_close(pair.low.blocks[0].cross_attn.k(t.tensor([[1., 2.]], dtype=t.float64)), t.tensor([[1.875, 1.875]], dtype=t.float64))

    def test_ordinary_lora_alpha_rank_uses_real_custom_linear(self):
        api = self.api(); t = self.torch
        payload = types.SimpleNamespace(name='lora', weights=(t.tensor([[2.], [3.]], dtype=t.float64), t.tensor([[1., 2.]], dtype=t.float64), 2., None, None, None))
        ps = {'diffusion_model.blocks.0.cross_attn.k.weight': [(.25, payload, 1., None, None)]}
        pair = api.prepare_lora_pair(self.model(), self.model(), ps, {})
        t.testing.assert_close(pair.high.blocks[0].cross_attn.k(t.tensor([[1., 2.]], dtype=t.float64)), t.tensor([[6.5, 9.]], dtype=t.float64))

    def test_global_strength_scales_once(self):
        api = self.api(); t = self.torch
        ps = {'diffusion_model.blocks.0.modulation': self.diff(self.delta((1, 6, 2)))}
        pair = api.prepare_lora_pair(self.model(), self.model(), ps, {}, strengths=(2., 1.))
        t.testing.assert_close(pair.high.blocks[0].modulation, t.full((1, 6, 2), 1.25, dtype=t.float64))

    def test_duplicate_application_is_rejected_and_removal_restores_independent_bases(self):
        api = self.api(); t = self.torch
        high, low = self.model(), self.model()
        bh, bl = copy.deepcopy(high.state_dict()), copy.deepcopy(low.state_dict())
        pair = api.prepare_lora_pair(high, low, self.patches(), self.patches())
        with self.assertRaises(api.UnsupportedPatch):
            api.prepare_lora_pair(pair.high, pair.low, self.patches(), self.patches())
        with t.no_grad(): pair.high.blocks[0].modulation.add_(100)
        rh, rl = api.remove_lora_pair(pair)
        self.unchanged(rh, bh); self.unchanged(rl, bl)
        self.assertNotEqual(rh.blocks[0].modulation.data_ptr(), high.blocks[0].modulation.data_ptr())
        again = api.prepare_lora_pair(rh, rl, self.patches(), {})
        t.testing.assert_close(again.high.head.modulation, t.full((1, 2, 2), 1.125, dtype=t.float64))

    def test_invalid_patch_inputs_reject_pair_without_original_mutation(self):
        api = self.api(); t = self.torch
        key = 'diffusion_model.blocks.0.cross_attn.k.bias'
        variants = [
            {'unknown.weight': self.diff(self.delta((2,)))},
            {key: self.diff(self.delta((3,)))},
            {key: self.diff(t.tensor([float('nan'), 1.]))},
            {key: self.diff(t.tensor([float('inf'), 1.]))},
            {key: self.diff(t.tensor([1, 2], dtype=t.int64))},
            {key: self.diff(self.delta((2,)), strength=[.5, .5])},
            {key: [(.5, ('set', (self.delta((2,)),)), 1., None, None)]},
            {key: [(.5, ('diff', (self.delta((2,)),)), .9, None, None)]},
            {key: [(.5, ('diff', (self.delta((2,)),)), 1., (0, 0, 1), None)]},
            {key: [(.5, ('diff', (self.delta((2,)),)), 1., None, lambda x: x)]},
            {key: []},
        ]
        for ps in variants:
            with self.subTest(patch=repr(ps)[:120]):
                h, l = self.model(), self.model(); bh, bl = copy.deepcopy(h.state_dict()), copy.deepcopy(l.state_dict())
                with self.assertRaises(api.UnsupportedPatch): api.prepare_lora_pair(h, l, {}, ps)
                self.unchanged(h, bh); self.unchanged(l, bl)

    def test_unknown_adapter_extensions_and_zero_alpha_are_rejected(self):
        api = self.api(); t = self.torch
        key = 'diffusion_model.blocks.0.cross_attn.k.weight'
        for alpha, mid, dora, reshape in [(0., None, None, None), (1., t.ones(1), None, None), (1., None, t.ones(1), None), (1., None, None, (2, 2))]:
            with self.subTest(alpha=alpha, mid=mid, dora=dora, reshape=reshape):
                data = types.SimpleNamespace(name='lora', weights=(t.ones((2, 1)), t.ones((1, 2)), alpha, mid, dora, reshape))
                with self.assertRaises(api.UnsupportedPatch):
                    api.prepare_lora_pair(self.model(), self.model(), {key: [(.5, data, 1., None, None)]}, {})

    def test_aliases_and_shared_expert_storage_are_rejected(self):
        api = self.api()
        h, l = self.model(), self.model(); h.alias = h.blocks[0].cross_attn.k
        with self.assertRaises(api.UnsupportedPatch): api.prepare_lora_pair(h, l, self.patches(), {})
        h = self.model()
        with self.assertRaises(api.UnsupportedPatch): api.prepare_lora_pair(h, h, {}, {})
        l = self.model(); l.head.modulation = h.head.modulation
        with self.assertRaises(api.UnsupportedPatch): api.prepare_lora_pair(h, l, {}, {})

    def test_low_apply_exception_never_changes_either_original(self):
        api = self.api()
        h, l = self.model(), self.model(); bh, bl = copy.deepcopy(h.state_dict()), copy.deepcopy(l.state_dict())
        actual_apply = api.apply_static_deltas; calls = []
        def injected(model, plan):
            actual_apply(model, plan); calls.append(model)
            if len(calls) == 2: raise RuntimeError('injected low failure after real mutation')
        with patch.object(api, 'apply_static_deltas', side_effect=injected):
            with self.assertRaisesRegex(RuntimeError, 'injected low failure'):
                api.prepare_lora_pair(h, l, self.patches(), self.patches())
        self.unchanged(h, bh); self.unchanged(l, bl)
        self.assertIsNot(calls[0], h); self.assertIsNot(calls[1], l)

    def test_legacy_single_expert_entry_rejects_static_payloads(self):
        api = self.api()
        with self.assertRaises(api.UnsupportedPatch): api.require_dynamic_only(self.model(), self.patches())

    def test_scalar_scale_applies_before_delta_for_both_forward_branches(self):
        t = self.torch
        model = self.model(); linear = model.blocks[0].cross_attn.k
        linear.scale_weight = t.tensor(.25, dtype=t.float64)
        ps = {'diffusion_model.blocks.0.cross_attn.k.weight': self.diff(self.delta((2, 2)))}
        self.custom.set_lora_params(model, ps)
        for n in (1, 3):
            with self.subTest(batch=n):
                actual = linear(t.tensor([[1., 2.]]*n, dtype=t.float64))
                t.testing.assert_close(actual, t.tensor([[1.125, .375]]*n, dtype=t.float64), atol=1e-12, rtol=0)

    def test_fp8_scaled_dynamic_weight_and_static_bias(self):
        api = self.api(); t = self.torch
        h, l = self.model(), self.model(); linear = h.blocks[0].cross_attn.k
        linear.weight = t.nn.Parameter(t.eye(2).to(t.float8_e4m3fn), requires_grad=False)
        linear.scale_weight = t.tensor(.25, dtype=t.float64)
        ps = {'diffusion_model.blocks.0.cross_attn.k.weight': self.diff(self.delta((2, 2))),
              'diffusion_model.blocks.0.cross_attn.k.bias': self.diff(t.tensor([.25, -.75], dtype=t.float64))}
        pair = api.prepare_lora_pair(h, l, ps, {})
        t.testing.assert_close(pair.high.blocks[0].cross_attn.k(t.tensor([[1., 2.]], dtype=t.float64)), t.tensor([[1.25, 0.]], dtype=t.float64))

    def test_unsupported_quantized_static_and_scale_reject(self):
        api = self.api(); t = self.torch
        h, l = self.model(), self.model()
        h.head.modulation = t.nn.Parameter(t.ones((1, 2, 2)).to(t.float8_e4m3fn), requires_grad=False)
        with self.assertRaises(api.UnsupportedPatch): api.prepare_lora_pair(h, l, self.patches(), {})
        for scale in (t.tensor([1., 2.]), t.tensor(float('nan')), t.tensor(0.)):
            with self.subTest(scale=scale):
                h = self.model(); h.blocks[0].cross_attn.k.scale_weight = scale
                with self.assertRaises(api.UnsupportedPatch): api.prepare_lora_pair(h, l, self.patches(), {})

    def test_normalization_collision_is_rejected_before_overwrite(self):
        source = (self.root/'nodes_model_loading.py').read_text(encoding='utf-8')
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name=='standardize_lora_key_format')
        namespace = {}; exec(compile(ast.Module(body=[node], type_ignores=[]), str(self.root/'nodes_model_loading.py'), 'exec'), namespace)
        standardize = namespace['standardize_lora_key_format']
        with self.assertRaises(ValueError):
            standardize({'blocks.0.diff_m': 1, 'diffusion_model.blocks.0.modulation.diff': 2})
        self.assertEqual(standardize({'blocks.0.diff_m': 1}), {'diffusion_model.blocks.0.modulation.diff': 1})

    def test_dynamic_overflow_is_rejected_before_pair_publication(self):
        api = self.api()
        h, l = self.model(), self.model(); before = copy.deepcopy(h.state_dict())
        ps = {'diffusion_model.blocks.0.cross_attn.k.weight': self.diff(self.delta((2, 2), 1e308), strength=1e308)}
        with self.assertRaises(api.UnsupportedPatch): api.prepare_lora_pair(h, l, ps, {})
        self.unchanged(h, before)

    def test_non_independent_deepcopy_is_rejected_before_any_application(self):
        api = self.api()
        h, l = self.model(), self.model(); before = copy.deepcopy(h.state_dict())
        h.__deepcopy__ = lambda memo: h
        with self.assertRaises(api.UnsupportedPatch): api.prepare_lora_pair(h, l, self.patches(), {})
        self.unchanged(h, before)

    def test_legacy_guard_allows_meta_linear_weights_without_cpu_model_loading(self):
        api = self.api(); t = self.torch
        h = t.nn.Module(); h.proj = t.nn.Linear(2, 2, device='meta')
        api.require_dynamic_only(h, {'diffusion_model.proj.weight': self.diff(self.delta((2, 2)))})

    def test_rank_two_alpha_scaling(self):
        api = self.api(); t = self.torch
        payload = types.SimpleNamespace(name='lora', weights=(t.eye(2, dtype=t.float64), t.eye(2, dtype=t.float64), 4., None, None, None))
        ps = {'diffusion_model.blocks.0.cross_attn.k.weight': [(.25, payload, 1., None, None)]}
        pair = api.prepare_lora_pair(self.model(), self.model(), ps, {})
        t.testing.assert_close(pair.high.blocks[0].cross_attn.k(t.tensor([[1., 2.]], dtype=t.float64)), t.tensor([[2., 2.5]], dtype=t.float64))

    def test_legacy_scheduled_mixed_rejection_preserves_real_transformer_state(self):
        # Execute the complete real entry function. Unavailable Comfy I/O/parser
        # boundaries carry a decoded synthetic diff; no patch math is simulated.
        api = self.api(); model = self.model(); model.lora_scheduling_enabled = False
        source = (self.root/'nodes_model_loading.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name in {'standardize_lora_key_format', 'add_lora_weights'}]
        delta = self.delta((2,))
        namespace = {'__name__':'lva07_test.nodes_model_loading',
                     'log': importlib.import_module('logging').getLogger('lva07-test'),
                     'load_torch_file':lambda *a, **kw: {'diffusion_model.blocks.0.cross_attn.k.diff_b':delta},
                     'model_lora_keys_unet':lambda *a, **kw: {},
                     'comfy':types.SimpleNamespace(lora=types.SimpleNamespace(load_lora=lambda *a: {'diffusion_model.blocks.0.cross_attn.k.bias':('diff',(delta,))})),
                     'require_dynamic_only':api.require_dynamic_only,
                     'preflight_legacy_lora_inputs':getattr(api, 'preflight_legacy_lora_inputs', None)}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(self.root/'nodes_model_loading.py'), 'exec'), namespace)
        patcher = types.SimpleNamespace(model=types.SimpleNamespace(diffusion_model=model))
        with self.assertRaises(api.UnsupportedPatch):
            namespace['add_lora_weights'](patcher, [{'name':'mixed','path':'synthetic','strength':[.5,.5],'blocks':False}], self.torch.float64, merge_loras=False)
        self.assertFalse(model.lora_scheduling_enabled, 'Guard rejected after original transformer state had changed')

    def test_all_legacy_inputs_are_checked_before_any_application(self):
        api = self.api(); self.assertTrue(callable(getattr(api, 'preflight_legacy_lora_inputs', None)))
        source = (self.root/'nodes_model_loading.py').read_text(encoding='utf-8')
        node = next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='standardize_lora_key_format')
        ns = {}; exec(compile(ast.Module(body=[node],type_ignores=[]),'<real-normalizer>','exec'),ns)
        model = self.model(); before=copy.deepcopy(model.state_dict())
        states = {'first':{'blocks.0.cross_attn.k.diff':self.delta((2,2))},
                  'last':{'blocks.0.cross_attn.k.diff_b':self.delta((2,))}}
        items = [{'path':'first','strength':.5},{'path':'last','strength':.5}]
        with self.assertRaises(api.UnsupportedPatch):
            api.preflight_legacy_lora_inputs(model, items, lambda p:states[p], ns['standardize_lora_key_format'])
        self.unchanged(model,before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
