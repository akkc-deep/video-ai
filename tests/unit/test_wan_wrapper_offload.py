import sys
import types

import pytest


class Tensor:
    def __init__(self,value,device='cpu',storage=None):
        self.value=value;self.device=types.SimpleNamespace(type=device);self.storage=storage or object()
    def detach(self):return Tensor(self.value,self.device.type,self.storage)
    def moved(self,device):return Tensor(self.value,device)


class Parameter:
    def __init__(self,value,requires_grad=False):self._data=value;self.requires_grad=requires_grad
    @property
    def data(self):return self._data
    @data.setter
    def data(self,value):
        if self._data.device.type=='meta' and value.device.type!='meta':raise TypeError('incompatible tensor type')
        self._data=value
    @property
    def device(self):return self.data.device
    def detach(self):return self.data.detach()


class Block:
    def __init__(self):
        self._parameters={'weight':Parameter(Tensor(3))}
        self._buffers={'_step':Tensor(0),'lora_diff_0_0':Tensor(5),'_lora_strength_0':Tensor(1)}
    def modules(self):return [self]
    def parameters(self):return iter(self._parameters.values())
    def to(self,device,**kwargs):
        device=getattr(device,'type',device)
        for value in self._parameters.values():
            if device=='cpu' and value.device.type!='cpu':raise MemoryError('large native CPU copy exceeds Job commit')
            if value.device.type!=device:value.data=value.data.moved(device)
        for name,value in self._buffers.items():
            if device=='cpu' and name.startswith('lora_diff_') and value.device.type!='cpu':raise MemoryError('large LoRA CPU copy')
            if value.device.type!=device:self._buffers[name]=value.moved(device)
        return self


def setup(monkeypatch):
    events=[];mm=types.SimpleNamespace(soft_empty_cache=lambda:events.append('trim'))
    monkeypatch.setitem(sys.modules,'comfy',types.SimpleNamespace(model_management=mm))
    monkeypatch.setitem(sys.modules,'comfy.model_management',mm)
    block=Block();return block,types.SimpleNamespace(blocks=[block]),events


def test_offload_restores_cpu_sources_without_copy_and_preserves_mutable_buffers(monkeypatch):
    from video_ai.experiments.wan_wrapper_offload import block_offload_scope
    block,model,events=setup(monkeypatch)
    original_weight=block._parameters['weight'].data;diff=block._buffers['lora_diff_0_0']
    with block_offload_scope(model):
        block.to('cuda');block._buffers['_step'].value=7;block._buffers['_lora_strength_0'].value=.5
        assert block._parameters['weight'].device.type=='cuda'
        block.to('cpu',non_blocking=False)
        assert block._parameters['weight'].data.storage is original_weight.storage
        assert block._buffers['lora_diff_0_0'].storage is diff.storage
        assert block._buffers['_step'].value==7 and block._buffers['_lora_strength_0'].value==.5
        block.to('cuda');block.to('cpu')
        assert original_weight.value==3 and diff.value==5
    assert 'to' not in vars(block) and events


def test_capture_is_after_native_reload_and_exception_restores_owned_method(monkeypatch):
    from video_ai.experiments.wan_wrapper_offload import block_offload_scope
    block,model,_=setup(monkeypatch);original=lambda *a,**kw:Block.to(block,*a,**kw);block.to=original
    overlay=Tensor(42)
    with pytest.raises(RuntimeError,match='kernel error'):
        with block_offload_scope(model):
            block._parameters['weight']=Parameter(overlay)
            block.to('cuda');block._buffers['_step'].value=9
            raise RuntimeError('kernel error')
    assert block.to is original and block._parameters['weight'].data.storage is overlay.storage
    assert block._buffers['_step'].value==9 and block._buffers['_step'].device.type=='cpu'


def test_training_and_foreign_gpu_state_are_rejected(monkeypatch):
    from video_ai.experiments.wan_wrapper_offload import block_offload_scope
    block,model,_=setup(monkeypatch);block._parameters['weight'].requires_grad=True
    with block_offload_scope(model):
        with pytest.raises(ValueError,match='frozen'):block.to('cuda')
    block._parameters['weight']=Parameter(Tensor(3,'cuda'))
    with block_offload_scope(model):
        with pytest.raises(ValueError,match='CPU source'):block.to('cpu')
    assert block._parameters['weight'].device.type=='cuda' and 'to' not in vars(block)


def test_native_meta_replacement_does_not_mask_kernel_failure(monkeypatch):
    from video_ai.experiments.wan_wrapper_offload import block_offload_scope
    block,model,_=setup(monkeypatch);original=block._parameters['weight'];source=original.data
    with pytest.raises(RuntimeError,match='kernel failure'):
        with block_offload_scope(model):
            block.to('cuda');block._buffers['_step'].value=11
            # Pinned native sampler finally replaces parameters by meta and removes LoRA buffers.
            block._parameters['weight']=Parameter(Tensor(0,'meta'))
            del block._buffers['lora_diff_0_0']
            raise RuntimeError('kernel failure')
    assert block._parameters['weight'] is original and original.data.storage is source.storage
    assert block._buffers['_step'].value==11 and block._buffers['_step'].device.type=='cpu'
    assert 'to' not in vars(block)


def test_cleanup_continues_other_blocks_and_preserves_primary_failure(monkeypatch):
    from video_ai.experiments.wan_wrapper_offload import block_offload_scope
    first,model,_=setup(monkeypatch);second=Block();model.blocks.append(second)
    def failing_return(device,**kw):
        if device=='cpu':raise RuntimeError('secondary cleanup failure')
        return Block.to(first,device,**kw)
    first.to=failing_return
    with pytest.raises(KeyError,match='original failure') as error:
        with block_offload_scope(model):
            first.to('cuda');second.to('cuda');second._buffers['_step'].value=13
            raise KeyError('original failure')
    assert any('secondary cleanup failure' in note for note in error.value.__notes__)
    assert second._parameters['weight'].device.type=='cpu' and second._buffers['_step'].device.type=='cpu'
    assert second._buffers['_step'].value==13 and first.to is failing_return and 'to' not in vars(second)


def test_source_less_cuda_lora_buffer_rejected(monkeypatch):
    from video_ai.experiments.wan_wrapper_offload import block_offload_scope
    block,model,_=setup(monkeypatch);block._buffers['lora_diff_0_0']=Tensor(5,'cuda')
    with block_offload_scope(model):
        with pytest.raises(ValueError,match='CPU source'):block.to('cpu')
