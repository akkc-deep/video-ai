"""Opt-in, small real pinned-function CPU fixtures, never model payloads."""
import gc
import os
from pathlib import Path
import tempfile
import types
import unittest


@unittest.skipUnless(os.environ.get('LVA07_RUNTIME_FIXTURE'),'explicit independent CPU runtime required')
class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from verify_lva07_wrapper_runtime import load_components
        cls.c=load_components(Path(os.environ['LVA07_WRAPPER']),Path(os.environ['LVA07_COMFY']))
        import torch
        cls.t=torch
        from video_ai.experiments import wan_wrapper_lora
        cls.api=wan_wrapper_lora

    def model(self):
        t=self.t;m=t.nn.Module();m.blocks=t.nn.ModuleList([t.nn.Module()])
        m.blocks[0].modulation=t.nn.Parameter(t.ones((1,6,2),dtype=t.float16),requires_grad=False)
        m.blocks[0].norm=t.nn.LayerNorm(2,dtype=t.float16)
        m.blocks[0].q=self.c.custom.CustomLinear(2,2,bias=True,compute_dtype=t.float16,scale_weight=t.tensor(.5,dtype=t.float16))
        m.blocks[0].q.weight=t.nn.Parameter(t.full((2,2),2,dtype=t.float8_e4m3fn),requires_grad=False)
        m.blocks[0].q.bias=t.nn.Parameter(t.zeros(2,dtype=t.float16),requires_grad=False)
        m.head=t.nn.Module();m.head.modulation=t.nn.Parameter(t.ones((1,2,2),dtype=t.float16),requires_grad=False)
        m.patch_embedding=t.nn.Linear(2,2,dtype=t.float32)
        return m

    def owner(self):
        m=self.model();sd={k:v.detach() for k,v in m.named_parameters()}
        sd['patch_embedding.weight']=sd['patch_embedding.weight'].to(self.t.float16)
        sd['patch_embedding.bias']=sd['patch_embedding.bias'].to(self.t.float16)
        sd['blocks.0.q.scale_weight']=self.t.tensor(.5,dtype=self.t.float16)
        p=types.SimpleNamespace(model={'sd':sd},patches={},model_options={'transformer_options':{}})
        o=self.api.ExpertOwner(p,m,sd,self.c,role='high')
        self.c.load(o)
        return o

    def patches(self):
        t=self.t
        out={}
        for k,shape in [('blocks.0.modulation',(1,6,2)),('blocks.0.norm.weight',(2,)),('head.modulation',(1,2,2)),
                        ('blocks.0.q.bias',(2,)),('patch_embedding.weight',(2,2)),('patch_embedding.bias',(2,))]:
            out['diffusion_model.'+k]=[(1.,('diff',(t.full(shape,.25,dtype=t.bfloat16),)),1.,None,None)]
        payload=types.SimpleNamespace(name='lora',weights=(t.full((2,64),.125,dtype=t.bfloat16),t.full((64,2),.25,dtype=t.bfloat16),32.,None,None,None))
        out['diffusion_model.blocks.0.q.weight']=[(1.,payload,1.,None,None)]
        return out

    def head_owner(self):
        o=self.owner();t=self.t
        o.transformer.head.head=self.c.custom.CustomLinear(2,2,bias=True,compute_dtype=t.float16,
            scale_weight=t.tensor(.5,dtype=t.float16))
        m=o.transformer.head.head
        m.weight=t.nn.Parameter(t.full((2,2),2.,dtype=t.float8_e4m3fn),requires_grad=False)
        m.bias=t.nn.Parameter(t.zeros(2,dtype=t.float16),requires_grad=False)
        o.original_sd.update({'head.head.weight':m.weight.detach(),'head.head.bias':m.bias.detach(),
            'head.head.scale_weight':m.scale_weight})
        self.c.load(o)
        return o

    def head_patches(self):
        p=self.patches();t=self.t
        p['diffusion_model.head.head.weight']=[(1.,('diff',(t.full((2,2),.25,dtype=t.bfloat16),)),1.,None,None)]
        p['diffusion_model.head.head.bias']=[(1.,('diff',(t.full((2,),.125,dtype=t.bfloat16),)),1.,None,None)]
        return p

    def test_head_full_delta_real_forward_scale_once_and_source_unchanged(self):
        t=self.t;o=self.head_owner();before={k:v.clone() for k,v in o.original_sd.items()}
        cert=self.api.prepare_private(o,self.head_patches())
        self.assertIn('diffusion_model.head.head.weight',cert.dynamic)
        self.assertNotIn('head.head.weight',cert.static)
        # (FP8base2 * scale.5 + delta.25) * input[1,2] + bias.125
        t.testing.assert_close(o.transformer.head.head(t.tensor([[1.,2.]],dtype=t.float16)),
            t.tensor([[3.875,3.875]],dtype=t.float16),rtol=0,atol=0)
        probe=next(p for p in cert.witness['dynamic_probes'] if p['target']=='diffusion_model.head.head.weight')
        self.assertEqual(probe['observed'],[1.25]*4)
        for k,v in before.items():t.testing.assert_close(o.original_sd[k].float(),v.float(),rtol=0,atol=0)
        self.assertEqual(o.transformer.head.head.weight.dtype,t.float8_e4m3fn)
        self.assertEqual(float(o.transformer.head.head.scale_weight),.5)

    def test_head_reload_scope_restores_after_original_skip_and_parameter_meta(self):
        from video_ai.experiments.wan_wrapper_head import head_reload_scope
        t=self.t;o=self.head_owner();self.api.prepare_private(o,self.head_patches())
        sampler=types.SimpleNamespace(set_lora_params=self.c.custom.set_lora_params)
        original=sampler.set_lora_params
        original(o.transformer,o.patcher.patches)
        self.assertEqual(len(o.transformer.head.head.lora_diffs),0)  # actual pinned omission
        with head_reload_scope(o,sampler):
            for iteration in range(3):
                if iteration==2:
                    for name,param in list(o.transformer.named_parameters()):
                        self.api._set_parameter(o.transformer,name,t.empty_like(param,device='meta'))
                self.c.load(o)
                sampler.set_lora_params(o.transformer,o.patcher.patches)
                t.testing.assert_close(o.transformer.head.head(t.tensor([[1.,2.]],dtype=t.float16)),
                    t.tensor([[3.875,3.875]],dtype=t.float16),rtol=0,atol=0)
        self.assertIs(sampler.set_lora_params,original)
        with self.assertRaisesRegex(RuntimeError,'sampling failed'):
            with head_reload_scope(o,sampler):raise RuntimeError('sampling failed')
        self.assertIs(sampler.set_lora_params,original)
        clean=self.owner();without_setter=types.SimpleNamespace()
        with head_reload_scope(clean,without_setter):pass
        self.assertFalse(hasattr(without_setter,'set_lora_params'))
        with self.assertRaisesRegex(ValueError,'owner'):
            with head_reload_scope(o,sampler):sampler.set_lora_params(self.head_owner().transformer,o.patcher.patches)
        self.assertIs(sampler.set_lora_params,original)

    def test_invalid_head_rejects_before_static_write(self):
        t=self.t
        variants=[(1.,('diff',(t.ones(3,2,dtype=t.bfloat16),)),1.,None,None),
            (1.,('diff',(t.full((2,2),float('nan'),dtype=t.bfloat16),)),1.,None,None),
            ([1.],('diff',(t.ones(2,2,dtype=t.bfloat16),)),1.,None,None),
            (1.,('diff',(t.ones(2,2,dtype=t.bfloat16),)),.5,None,None),
            (1.,('other',(t.ones(2,2,dtype=t.bfloat16),)),1.,None,None)]
        for entry in variants:
            o=self.head_owner();before=o.transformer.head.modulation.clone();p=self.head_patches()
            p['diffusion_model.head.head.weight']=[entry]
            with self.assertRaises(ValueError):self.api.prepare_private(o,p)
            t.testing.assert_close(o.transformer.head.modulation,before,rtol=0,atol=0)

    def test_static_private_overlay_two_reload_and_meta_restore(self):
        t=self.t;o=self.owner();before={k:v.clone() for k,v in o.original_sd.items()}
        parsed=self.patches();cert=self.api.prepare_private(o,parsed)
        self.assertEqual(len(cert.static),6)
        self.assertEqual(set(o.patcher.patches),{'diffusion_model.blocks.0.q.weight'})
        for _ in range(2):
            self.c.load(o)
            t.testing.assert_close(o.transformer.head.modulation,t.full((1,2,2),1.25,dtype=t.float16),rtol=0,atol=0)
        o.transformer.to('meta');self.c.load(o)
        t.testing.assert_close(o.transformer.blocks[0].modulation,t.full((1,6,2),1.25,dtype=t.float16),rtol=0,atol=0)
        for k,v in o.original_sd.items():t.testing.assert_close(v.to(t.float32),before[k].to(t.float32),rtol=0,atol=0)
        self.assertEqual(o.transformer.patch_embedding.weight.dtype,t.float32)
        for k,v in cert.static.items():self.assertNotEqual(v.data_ptr(),o.patcher.model['sd'][k].data_ptr())

    def test_pinned_patch_embedding_module_aliases_keep_private_overlay(self):
        o=self.owner();original=o.original_sd['patch_embedding.weight'].clone()
        o.transformer.original_patch_embedding=o.transformer.patch_embedding
        o.transformer.expanded_patch_embedding=o.transformer.patch_embedding
        cert=self.api.prepare_private(o,self.patches())
        self.assertIn('patch_embedding.weight',cert.static)
        self.assertIs(o.transformer.original_patch_embedding,o.transformer.patch_embedding)
        self.assertIs(o.transformer.expanded_patch_embedding,o.transformer.patch_embedding)
        self.t.testing.assert_close(o.original_sd['patch_embedding.weight'],original)

    def test_unknown_or_distinct_parameter_alias_still_rejected(self):
        for kind in ('unknown','distinct'):
            o=self.owner()
            if kind=='unknown':o.transformer.unexpected=o.transformer.patch_embedding
            else:
                o.transformer.original_patch_embedding=self.t.nn.Linear(2,2,dtype=self.t.float32)
                o.transformer.original_patch_embedding.weight=o.transformer.patch_embedding.weight
            with self.assertRaisesRegex(ValueError,'alias'):
                self.api.prepare_private(o,self.patches())

    def test_true_dynamic_forward_scale_rank_alpha_and_reset(self):
        o=self.owner();cert=self.api.prepare_private(o,self.patches())
        q=o.transformer.blocks[0].q
        # base2*.5 + sum64(.125*.25)*(alpha32/rank64) =2; bias .25
        self.t.testing.assert_close(q(self.t.tensor([[1.,2.]],dtype=self.t.float16)),self.t.tensor([[6.25,6.25]],dtype=self.t.float16))
        self.assertEqual(cert.witness['dynamic_probes'][0]['coordinates'],[[0,0],[0,1],[1,0],[1,1]])
        q._step.zero_()

    def test_production_preparation_skips_cpu_probes_but_keeps_actual_lora_math(self):
        from unittest.mock import patch
        o=self.head_owner()
        with patch.object(self.api,'probe_dynamic',side_effect=AssertionError('production CPU probe')):
            cert=self.api.prepare_private(o,self.head_patches(),verify_dynamic=False)
        self.assertEqual(cert.witness['dynamic_probes'],[])
        self.assertFalse(cert.witness['dynamic_forward_verified'])
        self.assertIn('diffusion_model.head.head.weight',cert.dynamic)
        self.t.testing.assert_close(o.transformer.blocks[0].q(self.t.tensor([[1.,2.]],dtype=self.t.float16)),
            self.t.tensor([[6.25,6.25]],dtype=self.t.float16))
        self.t.testing.assert_close(o.transformer.head.head(self.t.tensor([[1.,2.]],dtype=self.t.float16)),
            self.t.tensor([[3.875,3.875]],dtype=self.t.float16),rtol=0,atol=0)

    def test_nan_unknown_shape_and_colliding_targets_reject_before_write(self):
        t=self.t
        variants=[{'unknown':[(1.,('diff',(t.ones(2),)),1.,None,None)]},
            {'diffusion_model.head.modulation':[(1.,('diff',(t.ones(3),)),1.,None,None)]},
            {'diffusion_model.head.modulation':[(1.,('diff',(t.full((1,2,2),float('nan')),)),1.,None,None)]}]
        for ps in variants:
            o=self.owner();before=o.transformer.head.modulation.clone()
            with self.assertRaises(ValueError):self.api.prepare_private(o,ps)
            t.testing.assert_close(o.transformer.head.modulation,before)

    def test_repeated_prepare_rejects_and_fresh_control_unchanged(self):
        o=self.owner();self.api.prepare_private(o,self.patches())
        with self.assertRaises(ValueError):self.api.prepare_private(o,self.patches())
        clean=self.owner();self.api.assert_clean(clean)
        self.t.testing.assert_close(clean.transformer.head.modulation,self.t.ones((1,2,2),dtype=self.t.float16))
        clean.patcher.patches={'unexpected':[]}
        with self.assertRaises(ValueError):self.api.assert_clean(clean)

    def test_readonly_mapping_is_never_written(self):
        import numpy as np
        import warnings
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'readonly.bin';p.write_bytes(np.ones((1,2,2),dtype=np.float16).tobytes())
            o=self.owner();mapped=np.memmap(p,dtype=np.float16,mode='r',shape=(1,2,2))
            with warnings.catch_warnings():
                warnings.simplefilter('ignore');v=self.t.from_numpy(mapped)
            o.original_sd['head.modulation']=v;o.patcher.model['sd']=o.original_sd
            self.c.load(o);self.api.prepare_private(o,self.patches())
            self.assertEqual(p.read_bytes(),np.ones((1,2,2),dtype=np.float16).tobytes())
            self.t.testing.assert_close(v,self.t.ones((1,2,2),dtype=self.t.float16))
            self.api.release_expert(o);del v;gc.collect();mapped._mmap.close()

    def test_real_normalizer_mapper_parser_retains_exact_payload_objects(self):
        from video_ai.experiments.wan_wrapper_runtime_support import TraceInputs,verify_retained
        t=self.t;o=self.owner();ns=self.c.ns
        wrapper=t.nn.Module();wrapper.diffusion_model=o.transformer;wrapper.model_config=types.SimpleNamespace(unet_config={})
        raw={'diffusion_model.blocks.0.q.lora_down.weight':t.ones((64,2),dtype=t.bfloat16),
             'diffusion_model.blocks.0.q.lora_up.weight':t.ones((2,64),dtype=t.bfloat16),
             'diffusion_model.head.modulation.diff':t.ones((1,2,2),dtype=t.bfloat16)}
        mapping=ns['standardize_lora_key_format']({k:k for k in raw})
        header={k:{'shape':list(v.shape),'dtype':'BF16'} for k,v in raw.items()}
        data=TraceInputs(mapping,raw.__getitem__,header)
        parsed=ns['load_lora'](data,ns['model_lora_keys_unet'](wrapper,{}),log_missing=False)
        manifest=[dict(normalized_key=k,target='blocks.0.q.weight' if 'lora_' in k else 'head.modulation',
                       classification='applicable_pending_execution') for k in mapping]
        verify_retained(data,parsed,manifest)
        self.assertEqual(len(data.read),3)
        parsed['diffusion_model.head.modulation']=('diff',(raw['diffusion_model.head.modulation.diff'].clone(),))
        with self.assertRaisesRegex(ValueError,'retained'):verify_retained(data,parsed,manifest)

    def test_sequential_pair_low_failure_never_publishes(self):
        outer=self
        class Factory:
            epoch='fixture-epoch';comparison_sha256='a'*64;full_model=False
            def __init__(self):self.active=False;self.events=[]
            def build_unpatched(self,role):
                self.events.append(role);o=outer.owner();o.role=role;return o
            def parse(self,o):
                if o.role=='low':raise ValueError('low malformed')
                return outer.patches(),{'applicable':7,'excluded':0}
            def materialize(self,o):outer.c.load(o)
            def release(self,o):pass
        f=Factory()
        with tempfile.TemporaryDirectory() as td:
            f.root=Path(td)
            with self.assertRaisesRegex(ValueError,'low malformed'):self.api.admit_pair(f,'fixture-profile',None)
            self.assertFalse((Path(td)/'admission/pair.json').exists())
            self.assertEqual(f.events,['high','low'])

    def test_owner_leak_blocks_next_build(self):
        guard=self.api.OwnerGuard();o=self.owner();guard.acquire(o)
        guard.release(o)
        with self.assertRaisesRegex(ValueError,'live'):guard.check()
        del o;gc.collect();guard.check()

    def test_actual_missing_targets_or_img_exception_drift_rejected(self):
        o=self.owner();rows=[dict(target='head.modulation',classification='applicable_pending_execution')]
        self.api.validate_runtime_targets(o,rows)
        del o.transformer.head.modulation
        with self.assertRaises(ValueError):self.api.validate_runtime_targets(o,rows)
        o=self.owner();o.transformer.img_emb=self.t.nn.Linear(2,2)
        with self.assertRaises(ValueError):self.api.validate_runtime_targets(o,rows)

    def test_successful_pair_receipt_binds_full_witness_trace_and_original_id(self):
        import hashlib,json
        outer=self
        class Factory:
            epoch='fixture';comparison_sha256='a'*64;full_model=False;admission_id='fixture-original'
            def build_unpatched(self,role):o=outer.owner();o.role=role;return o
            def parse(self,o):return outer.patches(),{'applicable':7,'excluded':0,'unique_trace':'bound-'+o.role}
            def materialize(self,o):outer.c.load(o)
            def release(self,o):pass
        with tempfile.TemporaryDirectory() as td:
            f=Factory();f.root=Path(td);pair=self.api.admit_pair(f,'fixture-profile',None)
            self.assertEqual(pair.receipt['admission_id'],'fixture-original')
            for role in ('high','low'):
                raw=(Path(td)/f'admission/{role}-witness.json').read_bytes()
                self.assertEqual(pair.receipt[role+'_witness_sha256'],hashlib.sha256(raw).hexdigest())
                self.assertEqual(json.loads(raw)['trace']['unique_trace'],'bound-'+role)

    def test_production_pair_does_not_claim_full_forward_verification(self):
        from unittest.mock import patch
        outer=self
        class Factory:
            epoch='production';comparison_sha256='a'*64;full_model=True
            def build_unpatched(self,role):o=outer.owner();o.role=role;return o
            def parse(self,o):return outer.patches(),{'applicable':7,'excluded':0}
            def materialize(self,o):outer.c.load(o)
            def release(self,o):pass
        with tempfile.TemporaryDirectory() as td:
            factory=Factory();factory.root=Path(td)
            leases=types.SimpleNamespace(verify=lambda:None)
            with patch.object(self.api,'probe_dynamic',side_effect=AssertionError('production CPU probe')):
                pair=self.api.admit_pair(factory,'production-profile',leases,verify_dynamic=False)
            self.assertFalse(pair.receipt['full_model_verified'])
            self.assertFalse(pair.receipt['dynamic_forward_verified'])
            for cert in (pair.high,pair.low):
                self.assertFalse(cert.witness['full_model_verified'])
                self.assertEqual(cert.witness['dynamic_probes'],[])
                self.assertEqual(len(cert.static),6)
                self.assertEqual(set(cert.dynamic),{'diffusion_model.blocks.0.q.weight'})


if __name__=='__main__':unittest.main()
