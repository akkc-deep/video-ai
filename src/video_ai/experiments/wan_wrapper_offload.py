"""Return frozen Wan blocks to their existing CPU storages, without D2H copies."""
from contextlib import contextmanager
import sys


@contextmanager
def block_offload_scope(transformer):
    import comfy.model_management as mm
    states=[]
    def restore_sources(state):
        for module,name,buffer,parameter,source in state['sources']:
            if buffer:module._buffers[name]=source
            else:
                parameter.data=source
                module._parameters[name]=parameter
    def install(block):
        state=dict(block=block,original=block.to,owned='to' in vars(block),value=vars(block).get('to'),sources=None)
        states.append(state)
        def move(*args,**kwargs):
            device=kwargs.get('device',args[0] if args else None)
            kind=device.split(':',1)[0] if isinstance(device,str) else getattr(device,'type',None)
            if kind=='cuda' and state['sources'] is None:
                if len(args)>1 or kwargs.get('dtype') is not None:raise ValueError('device-only block transfer required')
                sources=[]
                for module in block.modules():
                    for name,value in module._parameters.items():
                        if value is None:continue
                        if value.requires_grad:raise ValueError('frozen block parameters required')
                        if value.device.type!='cpu':raise ValueError('original CPU source required before block transfer')
                        sources.append((module,name,False,value,value.detach()))
                    for name,value in module._buffers.items():
                        if value is not None and name.startswith('lora_diff_'):
                            if value.device.type!='cpu':raise ValueError('original CPU source required for LoRA buffer')
                            sources.append((module,name,True,None,value.detach()))
                state['sources']=sources
            if kind=='cpu':
                if state['sources'] is not None:
                    restore_sources(state)
                    mm.soft_empty_cache()
                elif (any(p.device.type!='cpu' for p in block.parameters())
                        or any(value is not None and name.startswith('lora_diff_') and value.device.type!='cpu'
                            for module in block.modules() for name,value in module._buffers.items())):
                    raise ValueError('original CPU source missing for block offload')
            result=state['original'](*args,**kwargs)
            if kind=='cpu':state['sources']=None
            return result
        block.to=move
    try:
        for block in transformer.blocks:install(block)
        yield
    finally:
        primary=sys.exc_info()[1];errors=[]
        for state in states:
            if state['sources'] is not None:
                try:
                    restore_sources(state);mm.soft_empty_cache();state['original']('cpu')
                except BaseException as exc:errors.append(exc)
        for state in reversed(states):
            try:
                if state['owned']:state['block'].to=state['value']
                else:delattr(state['block'],'to')
            except BaseException as exc:errors.append(exc)
        if errors:
            target=primary if primary is not None else errors[0]
            for error in errors:target.add_note('block offload cleanup: '+type(error).__name__+': '+str(error))
            if primary is None:raise target
