"""CPU-only mixed-delta preparation for the audited Wrapper fork.

Accepts parsed Comfy patch tuples, not raw LoRA files or ModelPatchers.
Original CustomLinear implements all dynamic weight LoRA arithmetic.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import math
from numbers import Real

import torch

from . import custom_linear


class UnsupportedPatch(ValueError):
    """The entire expert pair must be rejected before it becomes usable."""


_FLOATS = {torch.float16, torch.bfloat16, torch.float32, torch.float64}
_MAX_MODEL_BYTES = 256 * 1024 * 1024  # CPU proof only, never two full 14B models.


@dataclass(frozen=True)
class _Plan:
    key: str
    target: str
    route: str
    entries: tuple


@dataclass(frozen=True)
class PreparedLoraPair:
    high: torch.nn.Module
    low: torch.nn.Module
    manifest: tuple
    _base_high: torch.nn.Module
    _base_low: torch.nn.Module


def _scalar(value, label):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise UnsupportedPatch(f'{label}: finite constant scalar required; schedules unsupported')
    return float(value)


def _tensor(value, label):
    if (not isinstance(value, torch.Tensor) or value.device.type != 'cpu'
            or value.layout != torch.strided or value.dtype not in _FLOATS):
        raise UnsupportedPatch(f'{label}: dense floating CPU tensor required')
    if not torch.isfinite(value).all().item():
        raise UnsupportedPatch(f'{label}: non-finite tensor')
    return value


def _model_info(model):
    if not isinstance(model, torch.nn.Module) or hasattr(model, 'diffusion_model'):
        raise UnsupportedPatch('Supply bare transformer modules, not ModelPatchers or wrappers')
    if getattr(model, '_lva07_prepared', False):
        raise UnsupportedPatch('Already applied: restore independent original bases first')
    parameters = dict(model.named_parameters(remove_duplicate=False))
    buffers = dict(model.named_buffers(remove_duplicate=False))
    all_tensors = {**parameters, **buffers}
    seen = set()
    size = 0
    for name, tensor in all_tensors.items():
        if tensor.device.type != 'cpu' or tensor.layout != torch.strided:
            raise UnsupportedPatch(f'{name}: CPU dense model required')
        size += tensor.numel() * tensor.element_size()
        if tensor.numel():
            storage = tensor.untyped_storage().data_ptr()
            if storage in seen:
                raise UnsupportedPatch(f'{name}: shared/aliased model storage unsupported')
            seen.add(storage)
    if size > _MAX_MODEL_BYTES:
        raise UnsupportedPatch('CPU proof memory budget exceeded; full-model preparation not enabled')
    for module in model.modules():
        if getattr(module, 'fp8_matmul_enabled', False) or getattr(module, 'fp8_fast', False):
            raise UnsupportedPatch('Fast FP8 kernels are not validated in this CPU path')
        if isinstance(module, custom_linear.CustomLinear) and (
                module.lora_diffs or hasattr(module, 'lora_diff_0_0')):
            raise UnsupportedPatch('Pre-existing dynamic patches require original-base restoration')
    return parameters, seen


def _check_scale(module):
    scale = getattr(module, 'scale_weight', None)
    if scale is not None:
        _tensor(scale, 'scale_weight')
        if scale.numel() != 1 or scale.ndim > 2 or scale.item() <= 0:
            raise UnsupportedPatch('Only finite positive scalar weight scale is supported')
    return scale


def _preflight(model, patches, outer_strength, parameters=None):
    if parameters is None:
        parameters, _ = _model_info(model)
    if not isinstance(patches, dict):
        raise UnsupportedPatch('Parsed patch dictionary required')
    outer_strength = _scalar(outer_strength, 'expert strength')
    seen = set()
    plans = []
    for key, entries in patches.items():
        if not isinstance(key, str):
            raise UnsupportedPatch('Offset/tuple target keys unsupported')
        target = key.removeprefix('diffusion_model.')
        if target in seen:
            raise UnsupportedPatch(f'{key}: target normalization collision')
        seen.add(target)
        if target not in parameters:
            raise UnsupportedPatch(f'{key}: no exact target parameter')
        weight = parameters[target]
        module_path, _, attribute = target.rpartition('.')
        module = model.get_submodule(module_path)
        if getattr(module, 'is_gguf', False):
            raise UnsupportedPatch(f'{key}: GGUF not verified')
        dynamic = isinstance(module, custom_linear.CustomLinear) and attribute == 'weight'
        route = 'dynamic_weight' if dynamic else 'static_parameter'
        if dynamic and 'head' in target:
            raise UnsupportedPatch(f'{key}: upstream explicitly skips dynamic head LoRA')
        if weight.dtype not in _FLOATS:
            if not (dynamic and weight.dtype == torch.float8_e4m3fn and _check_scale(module) is not None):
                raise UnsupportedPatch(f'{key}: unsupported target quantization/dtype')
        if not torch.isfinite(weight.detach().to(torch.float64)).all().item():
            raise UnsupportedPatch(f'{key}: non-finite base parameter')
        if dynamic:
            _check_scale(module)
            if module.compute_dtype not in _FLOATS:
                raise UnsupportedPatch(f'{key}: unsupported compute dtype')
        if not isinstance(entries, (tuple, list)) or not entries:
            raise UnsupportedPatch(f'{key}: empty/malformed patch list')
        prepared = []
        for entry in entries:
            if not isinstance(entry, (tuple, list)) or len(entry) != 5:
                raise UnsupportedPatch(f'{key}: five-field patch tuple required')
            strength, payload, model_strength, offset, function = entry
            strength = _scalar(strength, key) * outer_strength
            if not math.isfinite(strength) or _scalar(model_strength, key) != 1. or offset is not None or function is not None:
                raise UnsupportedPatch(f'{key}: model scaling, offsets or callbacks unsupported')
            if isinstance(payload, tuple) and len(payload) == 2 and payload[0] == 'diff':
                if not isinstance(payload[1], (tuple, list)) or len(payload[1]) != 1:
                    raise UnsupportedPatch(f'{key}: padding/extended diff semantics unsupported')
                delta = _tensor(payload[1][0], key)
                if delta.shape != weight.shape:
                    raise UnsupportedPatch(f'{key}: exact delta shape required')
            elif dynamic and getattr(payload, 'name', None) == 'lora' and hasattr(payload, 'weights'):
                weights = payload.weights
                if not isinstance(weights, (tuple, list)) or len(weights) != 6:
                    raise UnsupportedPatch(f'{key}: expected six-field ordinary LoRA adapter')
                up, down, alpha, mid, dora, reshape = weights
                up, down = _tensor(up, key), _tensor(down, key)
                if (up.ndim != 2 or down.ndim != 2 or down.shape[0] <= 0
                        or up.shape[1] != down.shape[0]
                        or tuple(weight.shape) != (up.shape[0], down.shape[1])):
                    raise UnsupportedPatch(f'{key}: rank/matrix shape mismatch')
                if any(x is not None for x in (mid, dora, reshape)):
                    raise UnsupportedPatch(f'{key}: mid/DoRA/reshape extensions unsupported')
                if alpha is not None and _scalar(alpha, key) == 0:
                    raise UnsupportedPatch(f'{key}: upstream zero-alpha semantics not supported')
            else:
                raise UnsupportedPatch(f'{key}: unsupported payload/target combination')
            prepared.append((strength, copy.deepcopy(payload), 1., None, None))
        plans.append(_Plan('diffusion_model.' + target, target, route, tuple(prepared)))
    return tuple(plans)


def apply_static_deltas(private_model, static_plan):
    """Apply preflighted additive deltas once, only on a private model owner."""
    with torch.no_grad():
        for plan in static_plan:
            parameter = private_model.get_parameter(plan.target)
            dtype = torch.float64 if parameter.dtype == torch.float64 else torch.float32
            result = parameter.detach().to(dtype=dtype, copy=True)
            for strength, payload, _, _, _ in plan.entries:
                result.add_(payload[1][0].to(dtype=dtype), alpha=strength)
            converted = result.to(dtype=parameter.dtype)
            if not torch.isfinite(converted).all().item():
                raise UnsupportedPatch(f'{plan.key}: update overflow')
            parameter.copy_(converted)


def _apply_private(model, plans):
    apply_static_deltas(model, tuple(p for p in plans if p.route == 'static_parameter'))
    dynamic = {p.key: list(p.entries) for p in plans if p.route == 'dynamic_weight'}
    custom_linear.set_lora_params(model, dynamic)
    for plan in plans:
        if plan.route == 'dynamic_weight':
            module = model.get_submodule(plan.target.rpartition('.')[0])
            if len(module.lora_diffs) != len(plan.entries):
                raise UnsupportedPatch(f'{plan.key}: incomplete dynamic application')
            # One preparation-boundary check using the real upstream math.
            # No full scan or recalculation is added to sampling steps.
            with torch.no_grad():
                base = module.weight.to(dtype=module.compute_dtype)
                if module.scale_weight is not None:
                    base = base * module.scale_weight
                effective = module._get_weight_with_lora(base)
                if not torch.isfinite(effective).all().item():
                    raise UnsupportedPatch(f'{plan.key}: dynamic update overflow')
    model._lva07_prepared = True


def _assert_isolated(owners):
    seen_objects, seen_storage = set(), set()
    for model in owners:
        if id(model) in seen_objects:
            raise UnsupportedPatch('Deepcopy did not create an independent model owner')
        seen_objects.add(id(model))
        tensors = list(model.parameters()) + list(model.buffers())
        tensors += [m.scale_weight for m in model.modules()
                    if isinstance(getattr(m, 'scale_weight', None), torch.Tensor)]
        own_storage = {t.untyped_storage().data_ptr() for t in tensors if t.numel()}
        if seen_storage.intersection(own_storage):
            raise UnsupportedPatch('Deepcopy retained source parameter/buffer storage')
        seen_storage.update(own_storage)


def prepare_lora_pair(high, low, high_patches, low_patches, strengths=(1., 1.)):
    """Publish both private models only after both expert applications succeed."""
    if not isinstance(strengths, (tuple, list)) or len(strengths) != 2:
        raise UnsupportedPatch('Two constant expert strengths required')
    hp, hs = _model_info(high)
    lp, ls = _model_info(low)
    if high is low or hs.intersection(ls):
        raise UnsupportedPatch('Experts share model storage')
    high_plan = _preflight(high, high_patches, strengths[0], hp)
    low_plan = _preflight(low, low_patches, strengths[1], lp)
    base_high, base_low = copy.deepcopy(high), copy.deepcopy(low)
    private_high, private_low = copy.deepcopy(base_high), copy.deepcopy(base_low)
    _assert_isolated((high, low, base_high, base_low, private_high, private_low))
    _apply_private(private_high, high_plan)
    _apply_private(private_low, low_plan)
    manifest = tuple({'expert': expert, 'target': p.target, 'key': p.key,
                      'route': p.route, 'patch_count': len(p.entries), 'consumed': True, 'applied': True}
                     for expert, plans in [('high', high_plan), ('low', low_plan)] for p in plans)
    return PreparedLoraPair(private_high, private_low, manifest, base_high, base_low)


def remove_lora_pair(prepared):
    """Restore independent originals without subtracting or re-quantizing updates."""
    if not isinstance(prepared, PreparedLoraPair):
        raise UnsupportedPatch('Expected a prepared pair')
    return copy.deepcopy(prepared._base_high), copy.deepcopy(prepared._base_low)


def require_dynamic_only(model, patches):
    """Structural legacy guard; meta/device model loading is not CPU proof."""
    if not isinstance(patches, dict) or not patches:
        raise UnsupportedPatch('No recognized parsed patches; refuse silent acceptance')
    parameters = dict(model.named_parameters())
    for key in patches:
        if not isinstance(key, str):
            raise UnsupportedPatch('Offset target keys unsupported on legacy entry')
        target = key.removeprefix('diffusion_model.')
        path, _, attribute = target.rpartition('.')
        if target not in parameters:
            raise UnsupportedPatch(f'{key}: no exact legacy target')
        module = model.get_submodule(path)
        if attribute != 'weight' or not isinstance(module, torch.nn.Linear) or 'head' in target:
            raise UnsupportedPatch('Mixed static deltas require prepare_lora_pair; legacy single-expert path rejected')


def preflight_legacy_lora_inputs(model, inputs, load_state, normalize, parse=None):
    """Read and check the entire legacy list before flags, clones or application.

    Callers provide the real file reader, normalizer and (when available) Comfy
    parser. Cached normalized states avoid a second file read during execution.
    """
    if not isinstance(inputs, (list, tuple)):
        raise UnsupportedPatch('Legacy LoRA list required')
    parameters = dict(model.named_parameters())
    states = []
    for item in inputs:
        if not isinstance(item, dict):
            raise UnsupportedPatch('LoRA descriptor required')
        strength = _scalar(item.get('strength'), 'legacy strength')
        if item.get('blocks') or item.get('layer_filter'):
            raise UnsupportedPatch('Filtered legacy application is not full consumption')
        if strength == 0:
            states.append(None)
            continue
        raw = load_state(item['path'])
        if any(k.startswith('base_model.model.') for k in raw):
            raise UnsupportedPatch('Legacy rs-LoRA compensation requires separate validation')
        state = normalize(raw)
        targets = {}
        pairs = {}
        functional = False
        for key in state:
            target = None
            for suffix, side in [('.lora_A.weight','down'), ('.lora_B.weight','up'),
                                 ('.lora_down.weight','down'), ('.lora_up.weight','up')]:
                if key.endswith(suffix):
                    target = key[:-len(suffix)] + '.weight'
                    pairs.setdefault(target, set()).add(side)
                    functional = True
                    break
            if target is None:
                if key.endswith('.diff_b') or key.endswith('.b_norm'):
                    raise UnsupportedPatch('Static bias requires the private pair API')
                if key.endswith('.diff'):
                    stem = key[:-5]
                    target = stem if stem.removeprefix('diffusion_model.') in parameters else stem+'.weight'
                    functional = True
                elif key.endswith('.w_norm'):
                    target = key[:-7]+'.weight'
                    functional = True
                elif key.endswith('.alpha'):
                    target = key[:-6]+'.weight'
                else:
                    raise UnsupportedPatch(f'{key}: unsupported legacy source tensor')
            targets[target] = None
        if not functional or any(sides != {'up', 'down'} for sides in pairs.values()):
            raise UnsupportedPatch('No complete ordinary/diff legacy weights')
        require_dynamic_only(model, targets)
        if parse is not None:
            parsed = parse(state)
            require_dynamic_only(model, {k:[(strength,v,1.,None,None)] for k,v in parsed.items()})
        states.append(state)
    return tuple(states)
