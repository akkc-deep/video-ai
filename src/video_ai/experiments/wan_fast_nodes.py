"""Strict native Comfy admission, registered only in an LVA-04 owned worker."""
from functools import wraps
import json
import math
from pathlib import Path

from .wan_fast_profiles import verify_profile


def assert_sigmas(values):
    expected = (1, 15/16, 5/6, 5/8, 0)
    if len(values) != 5 or any(not math.isfinite(float(x)) or abs(float(x)-y) > 1e-6
                               for x, y in zip(values, expected)):
        raise ValueError('native sigma differs from frozen 1022 recipe')


def finite_images(images):
    if not bool(images.isfinite().all()):
        raise ValueError('nonfinite VAE IMAGE before uint8 conversion')
    return images


def admit_pair(high, low, loader):
    """Validate both experts before returning either; never mutate base patchers."""
    prepared, counts = [], {}
    for role, original in (('high', high), ('low', low)):
        tensors, patches = loader(role, original)
        if not patches:
            raise ValueError('incompatible_lora: empty '+role+' patches')
        consumed = set()
        state = original.model_state_dict()
        for key, patch in patches.items():
            if not isinstance(key, str) or key not in state or getattr(patch, 'name', None) != 'lora':
                raise ValueError('incompatible_lora: unsupported patch kind/key')
            weights = patch.weights
            if len(weights) != 6 or any(x is not None for x in weights[3:]):
                raise ValueError('incompatible_lora: only ordinary 2D LoRA supported')
            up, down = weights[:2]
            if (len(up.shape) != 2 or len(down.shape) != 2 or up.shape[1] != 64
                    or down.shape[0] != 64 or tuple(state[key].shape) != (up.shape[0], down.shape[1])):
                raise ValueError('incompatible_lora: rank64/target shape mismatch')
            consumed.update(patch.loaded_keys)
        if set(tensors) != consumed:
            raise ValueError('incompatible_lora: lora key not loaded')
        clone = original.clone()
        if set(clone.add_patches(patches, 1.0)) != set(patches):
            raise ValueError('incompatible_lora: patch not applied')
        prepared.append(clone)
        counts[role] = len(patches)
    return tuple(prepared), counts


def check_model_path(folder_paths, category, name, allowed):
    resolved = Path(folder_paths.get_full_path_or_raise(category, name)).resolve(strict=True)
    if not any(name == Path(a.path).name and resolved == Path(a.path) for a in allowed):
        raise ValueError('native model path differs from frozen profile: '+name)


def register_nodes(nodes, root, profile_digest):
    """Called after native init_extra_nodes, after main configures the device."""
    import comfy.lora as lora
    import comfy.lora_convert as convert
    import comfy.samplers as samplers
    import comfy.utils as utils
    import folder_paths
    profile = verify_profile(root, profile_digest)
    assets = dict(profile.assets)
    # Native search roots may include models/unet or extra_model_paths.yaml.
    # Check the same lookup the real loaders use, then check again on loading.
    loader_specs = (('UNETLoader', 'diffusion_models', 'unet_name', ('wan_high', 'wan_low')),
                    ('CLIPLoader', 'text_encoders', 'clip_name', ('text_encoder',)),
                    ('VAELoader', 'vae', 'vae_name', ('vae',)))
    for cls_name, category, field, roles in loader_specs:
        allowed = tuple(assets[r] for r in roles)
        for a in allowed:
            check_model_path(folder_paths, category, Path(a.path).name, allowed)
        loader_cls = nodes.NODE_CLASS_MAPPINGS[cls_name]
        original_loader = getattr(loader_cls, loader_cls.FUNCTION)

        def guard_loader(original, category, field, allowed):
            import inspect
            @wraps(original)
            def guarded(*args, **kwargs):
                bound = inspect.signature(original).bind(*args, **kwargs)
                check_model_path(folder_paths, category, bound.arguments[field], allowed)
                return original(*args, **kwargs)
            return guarded
        setattr(loader_cls, loader_cls.FUNCTION, guard_loader(original_loader, category, field, allowed))

    def record(kind, **value):
        from comfy_execution.utils import get_executing_context
        context = get_executing_context()
        with (Path(root)/'fast-node-evidence.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(kind=kind, profile_sha256=profile_digest,
                prompt_id=getattr(context, 'prompt_id', None), **value), allow_nan=False)+'\n')

    class LVA04LoraPair:
        @classmethod
        def INPUT_TYPES(cls):
            return {'required': {'high': ('MODEL',), 'low': ('MODEL',),
                'lora_high_name': ('STRING',), 'lora_low_name': ('STRING',),
                'strength_high': ('FLOAT', {'default': 1.0}), 'strength_low': ('FLOAT', {'default': 1.0})}}

        RETURN_TYPES = ('MODEL', 'MODEL')
        FUNCTION = 'load'
        CATEGORY = 'LVA04/experiment'

        def load(self, high, low, lora_high_name, lora_low_name, strength_high, strength_low):
            verify_profile(root, profile_digest)
            if profile.mode != 'fast_experimental' or (strength_high, strength_low) != (1, 1):
                raise ValueError('incompatible_lora: frozen pair required')

            def loader(role, model):
                name = lora_high_name if role == 'high' else lora_low_name
                path = Path(folder_paths.get_full_path_or_raise('loras', name)).resolve(strict=True)
                if path != Path(assets['lora_'+role].path):
                    raise ValueError('incompatible_lora: role/path differs')
                tensors = convert.convert_lora(utils.load_torch_file(str(path), safe_load=True))
                keys = lora.model_lora_keys_unet(model.model, {})
                # load_lora also logs unmapped keys; consumed-key equality is an
                # independent hard failure, never merely a warning.
                patches = lora.load_lora(tensors, keys)
                return tensors, patches

            try:
                result, counts = admit_pair(high, low, loader)
            except Exception as exc:
                record('incompatible_lora', error_type=type(exc).__name__)
                raise
            record('lora_pair_admitted', patches=counts, strengths=[1, 1])
            return result

    if 'LVA04LoraPair' in nodes.NODE_CLASS_MAPPINGS:
        raise ValueError('LVA04 node registration collision')
    nodes.NODE_CLASS_MAPPINGS['LVA04LoraPair'] = LVA04LoraPair
    sampler_class = nodes.NODE_CLASS_MAPPINGS['KSamplerAdvanced']
    sample_name = sampler_class.FUNCTION
    original_sample = getattr(sampler_class, sample_name)

    @wraps(original_sample)
    def sample(*args, **kwargs):
        import inspect
        bound = inspect.signature(original_sample).bind(*args, **kwargs)
        bound.apply_defaults()
        params = bound.arguments
        model, steps = params['model'], params['steps']
        if (steps != profile.steps or params['cfg'] != profile.cfg or params['sampler_name'] != 'euler'
                or params['scheduler'] != 'simple'):
            raise ValueError('sampler differs from frozen profile')
        values = samplers.calculate_sigmas(model.get_model_object('model_sampling'), 'simple', steps).tolist()
        if profile.mode == 'fast_experimental':
            assert_sigmas(values)
        record('actual_sigma', values=values, steps=steps, cfg=params['cfg'])
        return original_sample(*args, **kwargs)

    setattr(sampler_class, sample_name, sample)
    vae_class = nodes.NODE_CLASS_MAPPINGS['VAEDecode']
    original_decode = getattr(vae_class, vae_class.FUNCTION)

    @wraps(original_decode)
    def decode(*args, **kwargs):
        result = original_decode(*args, **kwargs)
        finite_images(result[0])
        record('finite_image', passed=True)
        return result

    setattr(vae_class, vae_class.FUNCTION, decode)
