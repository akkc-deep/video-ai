"""Approved exact-set policy tests; opt-in CPU/meta schema fixtures only."""
import copy
import importlib
from importlib.machinery import ModuleSpec
import json
import os
from pathlib import Path
import sys
import unittest
import tempfile
import hashlib
import struct
import importlib.util


@unittest.skipUnless(os.environ.get('LVA07_FIX_SOURCE'), 'opt-in independent CPU source required')
class ApplicabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        assert str(torch.__version__)=='2.14.1+cpu' and torch.version.cuda is None
        cls.torch=torch; cls.root=Path(os.environ['LVA07_FIX_SOURCE'])
        cls.policy=json.loads((Path(__file__).resolve().parents[2]/'patches/wanvideo-wrapper/lva07_img_policy.json').read_text(encoding='utf-8'))

    def api(self):
        self.assertTrue((self.root/'lva07_applicability.py').is_file(), 'Exact applicability API is missing')
        # Reuse package resolution from the actual Wrapper test module.
        if 'lva07_test' not in sys.modules:
            import types
            pkg=types.ModuleType('lva07_test');pkg.__path__=[str(self.root)];pkg.__spec__=ModuleSpec('lva07_test',None,is_package=True);sys.modules['lva07_test']=pkg
        return importlib.import_module('lva07_test.lva07_applicability')

    def data(self,role):
        p=self.policy['profiles'][role];t=self.torch;model=t.nn.Module()
        dtypes={'F16':t.float16,'BF16':t.bfloat16,'F32':t.float32,'F64':t.float64,'F8_E4M3':t.float8_e4m3fn}
        for row in p['tensors']:
            if row['excluded']:continue
            parts=row['target'].split('.');m=model
            for name in parts[:-1]:
                if name not in m._modules:m.add_module(name,t.nn.Module())
                m=m._modules[name]
            if parts[-1] not in m._parameters:
                m.register_parameter(parts[-1],t.nn.Parameter(t.empty(row['target_shape'],dtype=dtypes[row['target_dtype']],device='meta'),requires_grad=False))
        headers={r['source']:{'shape':r['shape'][:],'dtype':r['dtype']} for r in p['tensors']}
        ids={'lora':copy.deepcopy(p['lora_identity']),'base':copy.deepcopy(p['base_identity'])}
        return headers,model,ids

    def test_exact_original_headers_classify_290_without_applied_claim(self):
        api=self.api()
        for role,want,excluded in [('high',1500,0),('low',1459,290)]:
            with self.subTest(role=role):
                h,m,i=self.data(role);plan=api.plan_lora_applicability(role,h,m,i)
                self.assertEqual(len(plan.applicable),want);self.assertEqual(len(plan.excluded),excluded)
                self.assertTrue(all(r['runtime_applied'] is None for r in plan.manifest))
                self.assertTrue(all(r['classification']=='declared_not_applicable' for r in plan.excluded))
                self.assertEqual(set(h),{r['source_key'] for r in plan.manifest})

    def test_additional_or_missing_img_source_is_not_generically_filtered(self):
        api=self.api()
        for change in ['extra','missing']:
            h,m,i=self.data('low')
            if change=='extra':h['diffusion_model.blocks.0.cross_attn.k_img_unreviewed.diff']={'shape':[5120],'dtype':'F16'}
            else:h.pop(self.policy['profiles']['low']['tensors'][0]['source'])
            with self.assertRaises(api.ApplicabilityError):api.plan_lora_applicability('low',h,m,i)

    def test_changed_role_identity_or_source_schema_rejects(self):
        api=self.api()
        for change in ['role','sha','bytes','shape','dtype','base_header']:
            with self.subTest(change=change):
                h,m,i=self.data('low');role='low';key=next(iter(h))
                if change=='role':role='other'
                elif change=='sha':i['lora']['sha256']='0'*64
                elif change=='bytes':i['base']['bytes']+=1
                elif change=='base_header':i['base']['header_sha256']='0'*64
                elif change=='shape':h[key]['shape']=[1]
                elif change=='dtype':h[key]['dtype']='F64'
                with self.assertRaises(api.ApplicabilityError):api.plan_lora_applicability(role,h,m,i)

    def test_actual_model_img_presence_or_missing_target_rejects(self):
        api=self.api();t=self.torch
        for change in ['img','missing','shape']:
            with self.subTest(change=change):
                h,m,i=self.data('low');row=next(r for r in self.policy['profiles']['low']['tensors'] if not r['excluded'])
                parent,_,name=row['target'].rpartition('.');owner=m.get_submodule(parent)
                if change=='img':m.register_buffer('unexpected_img_branch',t.zeros(1))
                elif change=='missing':delattr(owner,name)
                else:setattr(owner,name,t.nn.Parameter(t.zeros(1),requires_grad=False))
                with self.assertRaises(api.ApplicabilityError):api.plan_lora_applicability('low',h,m,i)

    def test_selection_maps_source_keys_but_is_not_runtime_ownership(self):
        api=self.api();h,m,i=self.data('low');p=api.plan_lora_applicability('low',h,m,i)
        self.assertEqual(len({r['normalized_key'] for r in p.manifest}),1749)
        self.assertFalse(p.full_model_verified)
        self.assertTrue(all('img' not in k for k in p.applicable))
        with self.assertRaises(TypeError):p.applicable['bad']='bad'

    def test_incompatible_target_storage_dtype_rejects(self):
        api=self.api()
        for dtype in [self.torch.int32,self.torch.float64]:
            h,m,i=self.data('low')
            row=next(r for r in self.policy['profiles']['low']['tensors'] if not r['excluded'])
            parent,_,name=row['target'].rpartition('.')
            setattr(m.get_submodule(parent),name,self.torch.nn.Parameter(self.torch.empty(row['target_shape'],device='meta',dtype=dtype),requires_grad=False))
            with self.assertRaisesRegex(api.ApplicabilityError,'dtype'):
                api.plan_lora_applicability('low',h,m,i)


@unittest.skipUnless(os.environ.get('LVA07_FIX_SOURCE'), 'opt-in independent CPU source required')
class PayloadEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('lva07_payload_tests',cls.repo/'scripts/validate_lva07_applicable_payloads.py')
        cls.worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.worker)

    def test_real_parser_overwritten_reads_are_rejected(self):
        import torch
        w=self.worker
        self.assertTrue(hasattr(w,'verify_retained_inputs'),'Parser retention check missing')
        ns,_=w.components(Path('E:/VideoAI/shared/tools/ComfyUI_windows_portable/ComfyUI'),self.repo/'docs/task-designs/LVA-07-environment-review.json')
        values={'p.lora_up.weight':torch.ones(2,1),'p.lora_down.weight':torch.ones(1,2),'p.diff':torch.ones(2,2)}
        mapping={k:k for k in values};metadata={k:{'shape':list(v.shape),'dtype':'F32'} for k,v in values.items()}
        trace=w.ReadTrace(mapping,values.__getitem__,metadata)
        parsed=ns['load_lora'](trace,{'p':'diffusion_model.p.weight'},log_missing=False)
        self.assertEqual(trace.read,set(mapping))
        rows={k:{'target':'p.weight'} for k in values}
        with self.assertRaisesRegex(RuntimeError,'retained'):
            w.verify_retained_inputs(trace,parsed,rows)
        for selected in [list(values)[:2],['p.diff']]:
            trace=w.ReadTrace({k:k for k in selected},values.__getitem__,metadata)
            parsed=ns['load_lora'](trace,{'p':'diffusion_model.p.weight'},log_missing=False)
            w.verify_retained_inputs(trace,parsed,rows)
        with self.assertRaises(RuntimeError):w.verify_retained_inputs(trace,parsed|{'unexpected':parsed['diffusion_model.p.weight']},rows)

    def test_current_header_identity_and_length_are_checked(self):
        w=self.worker
        self.assertTrue(hasattr(w,'read_header'),'Bounded header admission missing')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture.safetensors';raw=json.dumps({'p.weight':{'shape':[2,2],'dtype':'F16','data_offsets':[0,8]}}).encode()
            p.write_bytes(struct.pack('<Q',len(raw))+raw+b'\0'*8)
            identity={'bytes':p.stat().st_size,'header_sha256':hashlib.sha256(raw).hexdigest()}
            header,evidence=w.read_header(p,identity)
            model=w.schema_model(header)
            import torch
            self.assertEqual(model.get_parameter('p.weight').dtype,torch.float16)
            self.assertEqual(evidence['header_sha256'],identity['header_sha256'])
            with self.assertRaises(RuntimeError):w.read_header(p,identity|{'header_sha256':'0'*64})
            p.write_bytes(struct.pack('<Q',2**63))
            with self.assertRaisesRegex(RuntimeError,'length'):w.read_header(p,{'bytes':8})

    def test_source_drift_rejected_before_execution(self):
        w=self.worker
        self.assertTrue(hasattr(w,'verify_source'),'Source admission missing')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=b'raise AssertionError("must never execute")\n';(root/'bad.py').write_bytes(raw)
            manifest={'upstream_reference':'fixture','patch_sha256':'patch','files':[{'path':'bad.py','sha256':hashlib.sha256(raw).hexdigest()}]}
            (root/'.lva07-manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            trusted={'upstream_reference':'fixture','artifacts':{'mixed-delta.patch':'patch'},'baseline_files':copy.deepcopy(manifest['files']),'patched_files':{}}
            w.verify_source(root,trusted)
            (root/'bad.py').write_bytes(raw+b'# drift\n')
            with self.assertRaisesRegex(RuntimeError,'identity'):w.verify_source(root,trusted)
            manifest['files'][0]['sha256']=hashlib.sha256((root/'bad.py').read_bytes()).hexdigest()
            (root/'.lva07-manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            with self.assertRaises(RuntimeError):w.verify_source(root,trusted)


if __name__=='__main__':unittest.main(verbosity=2)
