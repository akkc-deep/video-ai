"""Exact experiment-only head full-delta installation; fixed upstream is untouched."""
from contextlib import contextmanager

HEAD_KEY = 'diffusion_model.head.head.weight'


def preflight_head(owner, parsed, parameters):
    """Certify the fixed full additive head payload before any static write."""
    if HEAD_KEY not in parsed:
        return {}
    import torch
    repair = owner.components.repair
    module = owner.transformer.get_submodule('head.head')
    weight = parameters.get('head.head.weight')
    if (not isinstance(module, owner.components.custom.CustomLinear)
            or getattr(module, 'is_gguf', False)
            or weight is not module.weight or weight.dtype != torch.float8_e4m3fn
            or module.compute_dtype != torch.float16):
        raise ValueError('unsupported actual head full-delta target')
    if repair._check_scale(module) is None or not torch.isfinite(weight.float()).all().item():
        raise ValueError('head requires finite scaled FP8 base')
    entries = parsed[HEAD_KEY]
    if not isinstance(entries, (list, tuple)) or len(entries) != 1:
        raise ValueError('exactly one fixed head full delta required')
    entry = entries[0]
    if not isinstance(entry, (list, tuple)) or len(entry) != 5:
        raise ValueError('head five-field entry required')
    strength, payload, model_strength, offset, function = entry
    if (repair._scalar(strength, HEAD_KEY) != 1.
            or repair._scalar(model_strength, HEAD_KEY) != 1.
            or offset is not None or function is not None):
        raise ValueError('fixed head strengths and no offset/callback required')
    if (not isinstance(payload, tuple) or len(payload) != 2 or payload[0] != 'diff'
            or not isinstance(payload[1], (list, tuple)) or len(payload[1]) != 1):
        raise ValueError('head supports only the pinned full additive diff')
    delta = repair._tensor(payload[1][0], HEAD_KEY)
    if delta.dtype != torch.bfloat16 or delta.shape != weight.shape:
        raise ValueError('head full delta shape/dtype differs')
    return {HEAD_KEY: entries}


def install_head(owner, patches):
    """Install already-certified entries after the original setter skips head."""
    entries = patches.get(HEAD_KEY)
    if entries is None:
        return
    module = owner.transformer.get_submodule('head.head')
    module.set_lora_diffs([entry[1][1] for entry in entries], device=module.weight.device)
    module.set_lora_strengths([entry[0] for entry in entries], device=module.weight.device)
    module._step.zero_()
    if len(module.lora_diffs) != len(entries) or not hasattr(module, 'lora_diff_0_0'):
        raise ValueError('head full-delta installation incomplete')
    module._lva07_head_installations = getattr(module, '_lva07_head_installations', 0) + 1


@contextmanager
def head_reload_scope(owner, sampler_module):
    """Restore head after each actual sampler installation, never per forward."""
    if HEAD_KEY not in owner.patcher.patches:
        yield
        return
    original = sampler_module.set_lora_params
    def install(module, patches, *args, **kwargs):
        if module is not owner.transformer or patches is not owner.patcher.patches:
            raise ValueError('head reload owner/patch identity differs')
        result = original(module, patches, *args, **kwargs)
        install_head(owner, patches)
        return result
    sampler_module.set_lora_params = install
    try:
        yield
    finally:
        sampler_module.set_lora_params = original
