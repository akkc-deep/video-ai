"""Native subprocess entry and durable one-sample transaction.

Importing this module in the stdlib parent does not import Torch or codecs.
The numeric provider is loaded only inside the owned embedded interpreter.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = 'video_ai.runtime'

from ..adapters.common import strict_json
from ..planning.production_scenes import canonical_digest
from ..planning.scene_temporal import temporal_frame_mapping, validate_temporal_clip
from .manifest import now
from .production_state import ProductionRefused, json_bytes, object_fields
from .temporal_scene_admission import _refused, _write_exact

QUALIFIED_TEXT_ROOT = Path('D:/VideoSi/projects/video-ai/vco08-preflight/20261102-native16-qualification/allocator-async-candidate-v1/trial-001')
TEXT_CACHE_ROOT = Path('D:/VideoSi/cache/video-ai/temporal-text')


class MissingNativeTextCache(ProductionRefused):
    """A different, validated prompt pair needs its own explicit cache operation."""


def import_native_torch(*, importer=importlib.import_module):
    # Set both supported names before any package can transitively import Torch.
    os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'backend:cudaMallocAsync'
    os.environ['PYTORCH_ALLOC_CONF'] = 'backend:cudaMallocAsync'
    return importer('torch')


def artifact(path):
    path = Path(path)
    with path.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest)


def checked_artifact(item):
    object_fields(item, ('path', 'bytes', 'sha256'), 'native artifact')
    path = Path(item['path'])
    if not path.is_absolute() or artifact(path) != item:
        raise ProductionRefused('native consumed artifact drift')
    return path


def write_record(path, value):
    _write_exact(path, json_bytes(value))
    return artifact(path)


def _commit_array(path, frames):
    import numpy as np
    path = Path(path)
    if path.exists():
        actual = np.load(path, mmap_mode='r', allow_pickle=False)
        if actual.dtype != frames.dtype or actual.shape != frames.shape or not np.array_equal(actual, frames):
            raise ProductionRefused('native committed RGB pixels differ')
        return artifact(path)
    temp = path.with_name(path.name+'.'+uuid4().hex+'.pending')
    with temp.open('xb') as stream:
        np.save(stream, frames, allow_pickle=False); stream.flush(); os.fsync(stream.fileno())
    if path.exists(): raise ProductionRefused('native RGB destination appeared during commit')
    os.rename(temp, path)
    return artifact(path)


def _rgb(path, shape):
    import numpy as np
    frames = np.load(path, mmap_mode='r', allow_pickle=False)
    if frames.dtype != np.uint8 or frames.shape != shape:
        raise ProductionRefused('native raw RGB shape/dtype differs')
    return frames


@_refused
def prepare_native_input(store, row, selected, parent=None):
    """Copy actual original bytes or exactly parent raw pixels [80,93)."""
    import numpy as np
    store.assert_owned()
    budget = validate_temporal_clip(row['budget'])
    folder = store.clip_dir(budget['clip_id']); folder.mkdir(parents=True, exist_ok=True)
    selected = {key: selected[key] for key in ('path', 'bytes', 'sha256')}
    record = dict(schema_version=1, algorithm='temporal_native_input_v1', clip_id=budget['clip_id'],
        kind=budget['input_kind'], source=None, snapshot=None, source_frame_range=None,
        parent_result_sha256=None, condition_pixel_sha256=None)
    if budget['ordinal'] == 1:
        if parent is not None: raise ProductionRefused('first window has a parent')
        path = checked_artifact(selected)
        snapshot = folder/'input.original'
        _write_exact(snapshot, path.read_bytes())
        record.update(source=selected, snapshot=artifact(snapshot))
    else:
        if parent is None or parent['budget']['clip_id'] != budget['parent_clip_id']:
            raise ProductionRefused('native raw13 requires matching parent')
        source = parent['raw_frames']
        frames = _rgb(checked_artifact(source), (93, 432, 768, 3))
        history = np.ascontiguousarray(frames[80:93])
        record.update(source=source, snapshot=_commit_array(folder/'condition13.npy', history),
            source_frame_range=[80, 93], parent_result_sha256=parent['result']['sha256'],
            condition_pixel_sha256=hashlib.sha256(memoryview(history).cast('B')).hexdigest())
    previous = store.read(folder/'input.json')
    if previous is not None and canonical_digest(previous) != canonical_digest(record):
        raise ProductionRefused('native prepared input identity differs')
    store.write(folder/'input.json', record)
    return record


def _condition(request):
    import numpy as np
    item, parent = request['input'], request['parent']
    source, snapshot = checked_artifact(item['source']), checked_artifact(item['snapshot'])
    if request['budget']['ordinal'] == 1:
        if (parent is not None or item['source']!=request['selected_image'] or item['source']['sha256'] != item['snapshot']['sha256']
                or item['source_frame_range'] is not None or item['condition_pixel_sha256'] is not None):
            raise ProductionRefused('first native condition differs')
        return snapshot
    if (parent is None or item['source'] != parent['raw_frames'] or item['source_frame_range'] != [80, 93]
            or item['parent_result_sha256'] != parent['result']['sha256']):
        raise ProductionRefused('native raw13 parent identity differs')
    for role in ('result', 'generator', 'static_acceptance'): checked_artifact(parent[role])
    static = strict_json(Path(parent['static_acceptance']['path']).read_bytes())
    if (static.get('verdict') != 'acceptable' or static.get('allow_next_window') is not True
            or static.get('result_sha256') != parent['result']['sha256']):
        raise ProductionRefused('native parent is not statically accepted')
    raw, history = _rgb(source, (93, 432, 768, 3)), _rgb(snapshot, (13, 432, 768, 3))
    if not np.array_equal(raw[80:93], history): raise ProductionRefused('snapshot is not actual parent raw13')
    pixels = np.ascontiguousarray(history)
    if hashlib.sha256(memoryview(pixels).cast('B')).hexdigest() != item['condition_pixel_sha256']:
        raise ProductionRefused('native consumed raw13 pixel SHA differs')
    return pixels


def _request(request, output):
    from .temporal_scene_records import temporal_workflow
    object_fields(request, ('schema_version algorithm production_strategy run_id scene_id clip_id protocol inputs_sha256 '
        'execution_budget admission budget parameters workflow_sha256 input parent text_identity text_cache_key '
        'selected_image comparison_images narration_bindings visual_bible_sha256').split(), 'native worker request')
    if type(request['schema_version']) is not int or request['schema_version'] != 1 or request['algorithm'] != 'longcat_native16_request_v1':
        raise ProductionRefused('native worker request schema differs')
    budget = validate_temporal_clip(request['budget'])
    if (request['protocol']!='longcat_native16_v1' or request['production_strategy']!='paragraph_jimeng_v1'
            or request['run_id']!=output.parents[2].name or request['scene_id']!=budget['scene_id'] or request['clip_id']!=budget['clip_id']):
        raise ProductionRefused('native worker request header differs from frozen run/budget')
    from .temporal_scene_records import INPUT_FIELDS
    object_fields(request['input'],INPUT_FIELDS,'native worker condition input')
    condition=request['input']
    if (type(condition['schema_version']) is not int or condition['schema_version']!=1 or condition['algorithm']!='temporal_native_input_v1'
            or condition['clip_id']!=budget['clip_id'] or condition['kind']!=budget['input_kind']):
        raise ProductionRefused('native worker condition header differs')
    if output.name != budget['clip_id'] or strict_json((output/'request.json').read_bytes()) != request:
        raise ProductionRefused('native worker frozen request/output differs')
    workflow = strict_json((output/'workflow.json').read_bytes())
    expected = temporal_workflow(dict(evidence=dict(value=workflow)), dict(budget=budget, parameters=request['parameters']))
    if canonical_digest(workflow) != request['workflow_sha256'] or canonical_digest(workflow) != canonical_digest(expected):
        raise ProductionRefused('native worker frozen workflow differs')
    if request['text_cache_key'] != canonical_digest(request['text_identity']):
        raise ProductionRefused('native text identity differs')
    text_identity=dict(algorithm='official-umt5-eager-bfloat16-layer-staging-v1',model_manifest_sha256=workflow['model_manifest']['sha256'],
        positive_sha256=hashlib.sha256(request['parameters']['positive'].encode()).hexdigest(),
        negative_sha256=hashlib.sha256(request['parameters']['negative'].encode()).hexdigest())
    if canonical_digest(text_identity)!=canonical_digest(request['text_identity']):raise ProductionRefused('native prompt/model cache identity differs')
    checked_artifact(request['admission']); checked_artifact(request['execution_budget']);checked_artifact(request['selected_image'])
    return workflow


def _sample_record(request, output):
    from .temporal_scene_records import _sample
    # Use the same exact sample validator as the parent without loading its GPU stack.
    class Store:
        run_dir = output.parents[2]
        def artifact(self, path): return artifact(path)
        def read(self, path): return strict_json(Path(path).read_bytes())
        def validate_artifact(self, item): return checked_artifact(item)
    return _sample(dict(store=Store()), output, request, artifact(output/'intent.json'))


def validate_native_tokens(tokenizer, texts):
    counts = []
    for text in texts:
        tokens = tokenizer(text, truncation=False, add_special_tokens=True)['input_ids']
        if not 0 < len(tokens) <= 512: raise ProductionRefused('native prompt would be truncated by fixed 512-token encoder')
        counts.append(len(tokens))
    return counts


@_refused
def existing_native_text_context(request, *, cache_root=TEXT_CACHE_ROOT):
    """Resolve immutable cache identity; this function cannot encode text."""
    identity = request['text_identity']; parameters = request['parameters']
    if (request['text_cache_key'] != canonical_digest(identity)
            or identity['positive_sha256'] != hashlib.sha256(parameters['positive'].encode()).hexdigest()
            or identity['negative_sha256'] != hashlib.sha256(parameters['negative'].encode()).hexdigest()):
        raise ProductionRefused('native exact text identity differs')
    folder = Path(cache_root)/request['text_cache_key']
    binding_path = folder/'binding.json'
    if binding_path.exists():
        binding = strict_json(binding_path.read_bytes())
        cache = binding['cache']
        checked_artifact(cache)
        if binding['identity'] != identity or binding['cache_sha256'] != cache['sha256']:
            raise ProductionRefused('existing native text cache binding drift')
        return dict(cache=cache, binding=artifact(binding_path))
    case_path = QUALIFIED_TEXT_ROOT/'case.json'
    case = strict_json(case_path.read_bytes())
    if (parameters['positive'] != case['positive'] or parameters['negative'] != case['negative']
            or identity['model_manifest_sha256'] != case['model_manifest_sha256']):
        raise MissingNativeTextCache('exact native cache missing: explicit prepare-cache operation required')
    old_binding = strict_json((QUALIFIED_TEXT_ROOT/'text-context.json').read_bytes())
    cache = artifact(QUALIFIED_TEXT_ROOT/'text-context.safetensors')
    if (old_binding['sha256'] != cache['sha256'] or old_binding['identity'] != dict(case_sha256=artifact(case_path)['sha256'],
            model_manifest_sha256=identity['model_manifest_sha256'], algorithm=identity['algorithm'])):
        raise ProductionRefused('qualified cached text source changed')
    write_record(binding_path, dict(schema_version=1, identity=identity, cache=cache,
        cache_sha256=cache['sha256'], new_text_encoding_calls=0,
        reused_from=artifact(QUALIFIED_TEXT_ROOT/'text-context.json')))
    return dict(cache=cache, binding=artifact(binding_path))


class NativeGuard:
    """Actual free-capacity reserves, with no elapsed-time or allocation cap."""
    def __init__(self, output, torch, memory):
        import threading
        import time
        from .temporal_native_process import STARTUP, _reserve
        self.stage_dir = Path(output); self.torch = torch; self.memory = memory
        self.phase = 'preparing'; self.last_check = self.last_emit = 0.; self.start = time.monotonic()
        self.snapshots = []; self.trigger = None
        self.startup = self.snapshot()
        if _reserve(self.startup, STARTUP): raise ProductionRefused('native startup reserve below required free capacity')
        self.minima = dict(self.startup)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._monitor, daemon=True); self._thread.start()

    def snapshot(self):
        import shutil
        mem = self.memory()
        return dict(physical=mem['available_physical'], commit=mem['available_pagefile'],
            gpu=self.torch.cuda.mem_get_info()[0], disk=shutil.disk_usage(self.stage_dir).free)

    def _monitor(self):
        while not self._stop.wait(.01):
            mem = self.memory()
            for name, key in (('physical', 'available_physical'), ('commit', 'available_pagefile')):
                self.minima[name] = min(self.minima[name], mem[key])

    def check(self, *, force=False):
        import time
        from .temporal_native_process import RUNNING, _reserve
        current = time.monotonic()
        if not force and current-self.last_check < 2: return
        self.last_check = current
        sample = self.snapshot()
        for name, value in sample.items(): self.minima[name] = min(self.minima[name], value)
        reason = _reserve(sample, RUNNING) or _reserve(self.minima, RUNNING)
        if reason:
            self.trigger = dict(phase=self.phase, reason=reason, snapshot=sample, minima=dict(self.minima), thresholds=RUNNING)
            write_record(self.stage_dir/('resource-stop-'+uuid4().hex+'.json'), self.trigger)
            raise ProductionRefused('native running '+reason)
        record = dict(at=now(), phase=self.phase, elapsed_seconds=current-self.start, available=sample,
            gpu_allocated=self.torch.cuda.memory_allocated(), gpu_reserved=self.torch.cuda.memory_reserved(),
            peak_gpu_allocated=self.torch.cuda.max_memory_allocated(), peak_gpu_reserved=self.torch.cuda.max_memory_reserved())
        self.snapshots.append(record)
        if current-self.last_emit >= 15:
            self.last_emit = current
            print(json.dumps(record), flush=True)
            temporary = self.stage_dir/('progress-'+uuid4().hex+'.pending')
            temporary.write_bytes(json_bytes(record))
            try: os.replace(temporary, self.stage_dir/'progress.json')
            except PermissionError as exc:
                if getattr(exc, 'winerror', None) not in (5, 32, 33): raise
                temporary.unlink(missing_ok=True)
                print(json.dumps(dict(status='progress_snapshot_deferred', winerror=exc.winerror)), flush=True)

    def close(self):
        self._stop.set(); self._thread.join(timeout=2)


class NativeProvider:
    """Fixed qualified numerical core; production input and transaction are independent."""
    def __init__(self, runtime, output, *, setup=False):
        import importlib.metadata
        from .temporal_scene_admission import BUNDLE_TOOLS_ROOT, MODEL_ROOT, _current_worker_sources
        self.output = Path(output); self.runtime = runtime; self.model = MODEL_ROOT
        self.sources = [artifact(path) for path in _current_worker_sources()]
        if checked_artifact(runtime['production_worker']) != Path(__file__).resolve():
            raise ProductionRefused('current native worker identity differs')
        bundle_path = checked_artifact(runtime['runtime_bundle']); bundle = strict_json(bundle_path.read_bytes())
        self.bundle_root = bundle_path.parent
        if self.bundle_root.parent != BUNDLE_TOOLS_ROOT or self.bundle_root.name != canonical_digest(bundle):
            raise ProductionRefused('native numeric bundle path differs')
        if bundle['package_versions'] != runtime['package_versions'] or len(bundle['core_files']) != 27:
            raise ProductionRefused('native numeric bundle/runtime differs')
        for item in bundle['core_files'] + bundle['auxiliary_files']:
            relative = Path(item['path'])
            if relative.is_absolute() or '..' in relative.parts: raise ProductionRefused('numeric bundle source escapes root')
            checked_artifact(dict(item, path=str(self.bundle_root/relative)))
        if artifact(self.bundle_root/'model-manifest.json')['sha256'] != runtime['model_manifest']['sha256']:
            raise ProductionRefused('native selected model manifest differs')
        sys.path[:0] = [str(self.bundle_root), str(self.bundle_root/'working'),
            'D:/VideoSi/projects/video-ai/vco08-preflight/20261101-1238/python-deps']
        for name, version in runtime['package_versions'].items():
            if importlib.metadata.version(name) != version: raise ProductionRefused('native dependency changed: '+name)
        self.torch = import_native_torch()
        self.torch.set_grad_enabled(False)
        if self.torch.cuda.memory.get_allocator_backend() != 'cudaMallocAsync':
            raise ProductionRefused('native allocator backend differs')
        # Include the actual worker's numeric, tokenizer and codec import footprint.
        import numpy
        import av
        import PIL.Image
        import transformers
        import safetensors.torch
        importlib.import_module('video_ai.runtime.temporal_scene_records')
        importlib.import_module('video_ai.runtime.temporal_scene_origins')
        self.core = importlib.import_module('runtime_support')
        self.pipeline = importlib.import_module('native16_pipeline').Native16Pipeline
        self.media_core = importlib.import_module('trial_media')
        self.core.check_download()  # Existing file receipts/stat only; no full weight rehash/copy/download.
        self.guard = NativeGuard(output, self.torch, importlib.import_module('resource_probe').memory)
        self.vae = self.pipe = None

    def text_context(self, request):
        value = existing_native_text_context(request)
        from safetensors.torch import load_file
        self.cache = load_file(value['cache']['path'], device='cpu')
        if set(self.cache) != {'positive', 'positive_mask', 'negative', 'negative_mask'}:
            raise ProductionRefused('native cached text tensor inventory differs')
        for name in ('positive', 'negative'):
            if tuple(self.cache[name].shape) != (1, 1, 512, 4096): raise ProductionRefused('native cached text shape differs')
            if tuple(self.cache[name+'_mask'].shape) != (1, 512): raise ProductionRefused('native text mask shape differs')
        return value

    def prepare_cache(self, request):
        try: return self.text_context(request)
        except MissingNativeTextCache:
            # Never replace an existing binding or re-encode the qualified prompt.
            if (TEXT_CACHE_ROOT/request['text_cache_key']/'binding.json').exists(): raise
            case = strict_json((QUALIFIED_TEXT_ROOT/'case.json').read_bytes())
            if all(request['parameters'][key] == case[key] for key in ('positive', 'negative')): raise
            if (TEXT_CACHE_ROOT/request['text_cache_key']/'context.safetensors').exists():
                raise ProductionRefused('unknown partial native cache: never silently re-encode')
            if (request['text_identity']['algorithm']!='official-umt5-eager-bfloat16-layer-staging-v1'
                    or request['text_identity']['model_manifest_sha256']!=self.runtime['model_manifest']['sha256']):
                raise ProductionRefused('native cache encoding/model identity differs')
        import gc
        from transformers import AutoTokenizer
        from longcat_video.pipeline_longcat_video import prompt_clean
        from safetensors.torch import save_file
        tokenizer = AutoTokenizer.from_pretrained(str(self.model/'tokenizer'), local_files_only=True)
        texts = [request['parameters'][key] for key in ('positive', 'negative')]
        counts = validate_native_tokens(tokenizer, [prompt_clean(value) for value in texts])
        self.guard.phase = 'text_encoding'; self.guard.check(force=True)
        encoder = self.core.load_text_encoder(self.guard)
        pipe = self.pipeline(tokenizer, encoder, None, None, None)
        with self.torch.autocast('cuda', dtype=self.torch.bfloat16):
            tensors = pipe.encode_prompt(prompt=texts[0], negative_prompt=texts[1], device='cuda', dtype=self.torch.bfloat16)
        folder = TEXT_CACHE_ROOT/request['text_cache_key']; folder.mkdir(parents=True, exist_ok=True)
        target = folder/'context.safetensors'
        temporary = folder/('context-'+uuid4().hex+'.pending')
        save_file({name: value.cpu().contiguous() for name, value in zip(
            ('positive', 'positive_mask', 'negative', 'negative_mask'), tensors)}, str(temporary))
        if target.exists(): raise ProductionRefused('native cache destination already exists')
        os.rename(temporary, target)
        cache = artifact(target)
        write_record(folder/'binding.json', dict(schema_version=1, identity=request['text_identity'], cache=cache,
            cache_sha256=cache['sha256'], new_text_encoding_calls=2, token_counts=counts))
        del pipe, encoder, tensors; gc.collect(); self.torch.cuda.empty_cache()
        return self.text_context(request)

    def _vae(self):
        if self.vae is None: self.vae = self.core.load_vae()
        return self.vae

    def _kv_receipt(self, dit):
        bank = dit.model._vco08_disk_kv
        rows = []
        if set(bank.entries) != set(range(48)): raise ProductionRefused('actual native KV layers differ')
        total = 0
        for layer in range(48):
            for item in bank.entries[layer]:
                if item['dtype'] != 'BF16' or item['shape'] != [1, 32, 5184, 128]:
                    raise ProductionRefused('actual native KV shape/dtype differs')
                checked_artifact({key: item[key] for key in ('path', 'bytes', 'sha256')})
                total += item['bytes']
            rows.append(dict(layer=layer, manifest=artifact(bank.folder/f'layer-{layer:03d}.json'), pair=bank.entries[layer]))
        if total != 4076863488: raise ProductionRefused('actual native KV size differs')
        manifest = write_record(self.output/'kv-manifest.json', dict(layers=rows, bytes=total))
        return dict(layers=48, bytes=total, manifest=manifest)

    def sample(self, request, *, condition, generator, output, **condition_options):
        import gc
        import types
        from PIL import Image
        from safetensors.torch import load_file, save_file
        from longcat_video.modules.scheduling_flow_match_euler_discrete import FlowMatchEulerDiscreteScheduler
        from native_adapter import install_attention
        torch = self.torch
        self.guard.phase = 'loading_dit'; self.guard.check(force=True)
        dit = self.core.load_dit(self.guard); vae = self._vae()
        scheduler = FlowMatchEulerDiscreteScheduler.from_config(strict_json((self.model/'scheduler/scheduler_config.json').read_bytes()))
        pipe = self.pipeline(None, types.SimpleNamespace(config=types.SimpleNamespace(d_model=4096)), vae, scheduler, dit)
        def cached_prompt(pipe_self, *, prompt, negative_prompt, device, dtype, **kwargs):
            if prompt != request['parameters']['positive'] or negative_prompt != request['parameters']['negative']:
                raise ProductionRefused('native pipeline prompt differs from exact cache')
            return tuple(self.cache[key].to(device=device, dtype=dtype if 'mask' not in key else None)
                for key in ('positive', 'positive_mask', 'negative', 'negative_mask'))
        pipe.encode_prompt = types.MethodType(cached_prompt, pipe)
        rng = torch.Generator(device='cuda').manual_seed(request['parameters']['seed'])
        if generator is not None:
            checked_artifact(generator)
            state = load_file(generator['path'], device='cpu')
            if set(state) != {'generator_state'}: raise ProductionRefused('native parent RNG tensor differs')
            rng.set_state(state['generator_state'])
        install_attention(); self.guard.phase = 'diffusion_sampling'; self.guard.check(force=True)
        kwargs = dict(prompt=request['parameters']['positive'], negative_prompt=request['parameters']['negative'],
            resolution='432p-native16', num_frames=93, num_inference_steps=50, use_distill=False,
            guidance_scale=4., generator=rng, output_type='latent')
        with torch.autocast('cuda', dtype=torch.bfloat16):
            if generator is None:
                with Image.open(condition) as image: latent = pipe.generate_i2v(image=image.convert('RGB'), **kwargs)
            else:
                latent = pipe.generate_vc(video=[Image.fromarray(frame) for frame in condition], **condition_options, **kwargs)
        if tuple(latent.shape) != (1, 16, 24, 54, 96) or not torch.isfinite(latent).all():
            raise ProductionRefused('native sampled latent is invalid')
        sample_path, rng_path = output/'sample.safetensors', output/'generator.safetensors'
        for path, tensors in ((sample_path, {'latents': latent.detach().cpu().contiguous()}),
                              (rng_path, {'generator_state': rng.get_state().cpu().contiguous()})):
            temporary = path.with_name(path.name+'.'+uuid4().hex+'.pending')
            save_file(tensors, str(temporary))
            if path.exists(): raise ProductionRefused('native sample destination exists')
            os.rename(temporary, path)
        kv = self._kv_receipt(dit) if generator is not None else dict(layers=0, bytes=0, manifest=None)
        pipe._clear_cache(); pipe.dit = None
        del dit, pipe, latent; gc.collect(); torch.cuda.empty_cache()
        return dict(sample=artifact(sample_path), generator=artifact(rng_path), latent_shape=[1, 16, 24, 54, 96], kv=kv)

    def decode(self, sample):
        import numpy as np
        from safetensors.torch import load_file
        torch = self.torch
        self.guard.phase = 'vae_decode'; self.guard.check(force=True)
        checked_artifact(sample['sample'])
        saved = load_file(sample['sample']['path'], device='cpu')
        if set(saved) != {'latents'}: raise ProductionRefused('native latent tensor inventory differs')
        latent = saved['latents'].cuda()
        if tuple(latent.shape) != (1, 16, 24, 54, 96) or not torch.isfinite(latent).all():
            raise ProductionRefused('native committed latent invalid')
        pipe = self.pipeline(None, None, self._vae(), None, None)
        with torch.autocast('cuda', dtype=torch.bfloat16):
            raw = pipe.vae.decode(pipe.denormalize_latents(latent.to(pipe.vae.dtype)), return_dict=False)[0]
            data = pipe.video_processor.postprocess_video(raw, output_type='np')
        frames = np.clip(np.asarray(data)[0]*255, 0, 255).astype(np.uint8)
        self.guard.check(force=True)
        return frames

    def media(self, output, frames, budget, condition):
        import numpy as np
        from PIL import Image
        self.guard.phase = 'media_commit'; self.guard.check(force=True)
        paths = dict(raw_movie=output/'raw.mp4', viewing_movie=output/'viewing.mp4', source_movie=output/'source.mp4',
            last_frame=output/'last-frame.png', contact_sheet=output/'contact-sheet.png')
        retained = frames[budget['retained_source_start']:budget['retained_source_end']]
        self.media_core.commit_movie(paths['raw_movie'], frames, lossless=True)
        self.media_core.commit_movie(paths['viewing_movie'], frames, lossless=False)
        self.media_core.commit_movie(paths['source_movie'], retained, lossless=True)
        image = Image.fromarray(retained[-1]); target = paths['last_frame']
        if target.exists():
            with Image.open(target) as saved:
                if saved.convert('RGB').tobytes() != image.tobytes(): raise ProductionRefused('native last retained frame differs')
        else:
            temporary = target.with_name('last-frame-'+uuid4().hex+'.png'); image.save(temporary); os.rename(temporary, target)
        if isinstance(condition, Path):
            with Image.open(condition) as source: reference = np.asarray(source.convert('RGB'))
            previous = None
        else: reference, previous = condition[0], condition
        with Image.open(checked_artifact(self.request['selected_image'])) as selected:
            reference = np.asarray(selected.convert('RGB'))
        self.media_core.contact_sheet(paths['contact_sheet'], frames, reference=reference, previous=previous)
        write_record(output/'diagnostics.json', self.media_core.diagnostics(frames, previous=previous))
        self.guard.check(force=True)
        return {name: artifact(path) for name, path in paths.items()}

    def resource_preflight(self, request):
        """Five real pretrained forwards; zero scheduler steps or generated videos."""
        import gc
        import numpy as np
        from safetensors.torch import load_file
        from native_adapter import install_attention
        from ..planning.scene_temporal import CLOCK_POLICY
        from .temporal_scene_admission import _current_worker_sources
        torch = self.torch; guard = self.guard
        report = dict(schema_version=1, algorithm='temporal_native_resource_v1', complete=False,
            production_worker=self.runtime['production_worker'], production_sources=self.sources,
            runtime_bundle=self.runtime['runtime_bundle'], model_manifest_sha256=self.runtime['model_manifest']['sha256'],
            package_versions=self.runtime['package_versions'], allocator_backend='cudaMallocAsync',
            output_clock_policy=CLOCK_POLICY, deployed_output_fps=16, time_limit_seconds=None,
            max_gpu_allocated_bytes=None, native_diffusion_calls=0, new_text_encoding_calls=0,
            scheduler_steps=0, video_outputs=0, worker_import_footprint_included=True,
            startup_available=guard.startup, completed_shapes=[])
        torch.manual_seed(42608)
        try:
            self.text_context(request)
            install_attention()
            guard.phase = 'loading_dit'; dit = self.core.load_dit(guard); vae = self._vae()
            positive, negative = self.cache['positive'].cuda(), self.cache['negative'].cuda()
            text = torch.cat([negative, positive])
            mask = torch.cat([self.cache['negative_mask'], self.cache['positive_mask']]).cuda()
            preparation = self.pipeline(None, None, vae, None, None)
            rng = torch.Generator(device='cuda').manual_seed(42608)
            guard.phase = 'prepare_first_condition'
            pixels = torch.zeros(1, 3, 432, 768, device='cuda', dtype=torch.bfloat16)
            with torch.autocast('cuda', dtype=torch.bfloat16):
                prepared = preparation.prepare_latents(image=pixels, batch_size=1, num_channels_latents=16,
                    height=432, width=768, num_frames=93, num_cond_frames=1, dtype=torch.float32, device='cuda', generator=rng)
            if tuple(prepared.shape) != (1, 16, 24, 54, 96) or prepared.dtype != torch.float32:
                raise ProductionRefused('actual first preparation differs')
            report['prepared_latent_shape'] = list(prepared.shape)
            x = torch.cat([prepared]*2).to(torch.bfloat16)
            previous_prediction = torch.zeros_like(x, dtype=torch.float32)
            previous_guidance = torch.zeros_like(prepared, dtype=torch.float32)
            timestep = torch.full((2, 24), 500., device='cuda', dtype=torch.bfloat16); timestep[:, :1] = 0
            guard.phase = 'first_window_full_forward'; guard.check(force=True)
            with torch.autocast('cuda', dtype=torch.bfloat16): output = dit(x, timestep, text, mask, num_cond_latents=1)
            if output.shape != x.shape or not torch.isfinite(output).all(): raise ProductionRefused('actual first forward invalid')
            report['completed_shapes'].append('first')
            del x, timestep, output, prepared, pixels, previous_prediction, previous_guidance
            torch.cuda.empty_cache(); guard.check(force=True)
            guard.phase = 'prepare_history_condition'
            pixels = torch.zeros(1, 3, 13, 432, 768, device='cuda', dtype=torch.bfloat16)
            with torch.autocast('cuda', dtype=torch.bfloat16):
                prepared = preparation.prepare_latents(video=pixels, batch_size=1, num_channels_latents=16,
                    height=432, width=768, num_frames=93, num_cond_frames=13, dtype=torch.float32, device='cuda', generator=rng)
            history = prepared[:, :, :4].to(torch.bfloat16)
            guard.phase = 'clean_history_full_forward'
            with torch.autocast('cuda', dtype=torch.bfloat16):
                _, kv = dit(history, torch.zeros(1, 4, device='cuda'), text[:1], mask[:1],
                    return_kv=True, skip_crs_attn=True, offload_kv_cache=True)
            shapes = {tuple(t.shape) for pair in kv.values() for t in pair}
            if len(kv) != 48 or shapes != {(1, 32, 5184, 128)}: raise ProductionRefused('actual preflight clean KV differs')
            report['clean_kv_shape'] = [1, 32, 5184, 128]
            report['kv_bytes'] = sum(t.numel()*t.element_size() for pair in kv.values() for t in pair)
            report['completed_shapes'].append('clean_history'); torch.cuda.empty_cache()
            guard.phase = 'continuation_full_forward'
            x = torch.cat([prepared[:, :, 4:]]*2).to(torch.bfloat16)
            previous_prediction = torch.zeros_like(x, dtype=torch.float32)
            previous_guidance = torch.zeros_like(prepared[:, :, 4:], dtype=torch.float32)
            with torch.autocast('cuda', dtype=torch.bfloat16):
                output = dit(x, torch.full((2, 20), 500., device='cuda'), text, mask, num_cond_latents=4, kv_cache_dict=kv)
            if output.shape != x.shape or not torch.isfinite(output).all(): raise ProductionRefused('actual continuation forward invalid')
            report['completed_shapes'].append('continuation')
            report['kv'] = self._kv_receipt(dit)
            del x, output, kv, history, prepared, pixels, previous_prediction, previous_guidance, preparation
            gc.collect(); torch.cuda.empty_cache(); guard.check(force=True)
            guard.phase = 'vae_encode_13'
            pixels = torch.rand(1, 3, 13, 432, 768, device='cuda', dtype=torch.bfloat16)*2-1
            with torch.autocast('cuda', dtype=torch.bfloat16): encoded = vae.encode(pixels).latent_dist.mode()
            if tuple(encoded.shape) != (1, 16, 4, 54, 96) or not torch.isfinite(encoded).all():
                raise ProductionRefused('actual VAE encode invalid')
            report['vae_encode_shape'] = list(encoded.shape); guard.check(force=True)
            report['completed_shapes'].append('vae_encode_13')
            del pixels, encoded, dit; gc.collect(); torch.cuda.empty_cache()
            guard.phase = 'vae_decode_93'
            pipe = self.pipeline(None, None, vae, None, None)
            latent = torch.randn(1, 16, 24, 54, 96, device='cuda', dtype=torch.bfloat16)
            with torch.autocast('cuda', dtype=torch.bfloat16):
                raw = vae.decode(pipe.denormalize_latents(latent.to(vae.dtype)), return_dict=False)[0]
                if tuple(raw.shape) != (1, 3, 93, 432, 768): raise ProductionRefused('actual VAE decode shape differs')
                for part in raw.split(4, dim=2):
                    if not torch.isfinite(part).all(): raise ProductionRefused('actual VAE decode invalid')
                data = pipe.video_processor.postprocess_video(raw, output_type='np')
            frames = np.clip(np.asarray(data)[0]*255, 0, 255).astype(np.uint8)
            if frames.shape != (93, 432, 768, 3): raise ProductionRefused('actual RGB decode shape differs')
            report['vae_decode_frames_shape'] = list(frames.shape)
            guard.check(force=True); report['completed_shapes'].append('vae_decode_93')
            if self.sources != [artifact(path) for path in _current_worker_sources()]: raise ProductionRefused('production source changed during preflight')
            report['complete'] = True
        except BaseException as exc:
            report.update(error=type(exc).__name__, detail=str(exc))
            raise
        finally:
            guard.close()
            report.update(minima=guard.minima, snapshots=guard.snapshots, resource_stop=guard.trigger,
                peak_gpu_allocated=torch.cuda.max_memory_allocated(), peak_gpu_reserved=torch.cuda.max_memory_reserved())
            write_record(self.output/'production-resource.json', report)
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation', choices=('resource-preflight', 'prepare-cache', 'one-window', 'decode-only'), required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--owner-file', type=Path)
    parser.add_argument('--owner-token')
    args = parser.parse_args(argv)
    provider = None
    try:
        from .paths import PathPolicy
        if not args.request.is_absolute() or not args.output.is_absolute(): raise ProductionRefused('absolute native CLI paths required')
        video_operation=args.operation in ('one-window','decode-only')
        if video_operation:PathPolicy().validate_write(args.output,'run')
        else:
            try:PathPolicy().validate_write(args.output,'input')
            except ValueError:PathPolicy().validate_write(args.output,'run')
        request = strict_json(args.request.read_bytes())
        args.output.mkdir(parents=True,exist_ok=True)
        if video_operation or args.owner_file is not None:
            import time
            from .production_state import process_started_at
            if args.owner_file is None or args.owner_token is None: raise ProductionRefused('owned native launch required')
            if args.owner_file.parent != args.output: raise ProductionRefused('native owner path differs')
            for attempt in range(100):
                if args.owner_file.exists(): break
                time.sleep(.1)  # bounded publication handshake, independent of inference wait
            owner = strict_json(args.owner_file.read_bytes())
            if (owner.get('token') != args.owner_token or owner.get('pid') != os.getpid()
                    or owner.get('process_started_at') != process_started_at(os.getpid())
                    or owner.get('request_sha256') != canonical_digest(request)):
                raise ProductionRefused('native live process owner differs')
            runtime = _request(request, args.output) if video_operation else request
        else: runtime = request
        provider = NativeProvider(runtime, args.output, setup=args.operation in ('resource-preflight', 'prepare-cache'))
        result = execute_native_operation(request, operation=args.operation, output=args.output, provider=provider)
        print(json.dumps(dict(status=result.get('status', 'complete'), operation=args.operation)), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps(dict(status='failed', error=type(exc).__name__, detail=str(exc))), file=sys.stderr, flush=True)
        return 2
    finally:
        if provider is not None: provider.guard.close()


@_refused
def execute_native_operation(request, *, operation, output, provider=None) -> dict:
    output = Path(output)
    if not output.is_absolute(): raise ProductionRefused('absolute native output required')
    output.mkdir(parents=True, exist_ok=True)
    if operation not in ('one-window', 'decode-only', 'prepare-cache', 'resource-preflight'):
        raise ProductionRefused('unknown native worker operation')
    if operation in ('prepare-cache', 'resource-preflight'):
        provider = provider or NativeProvider(request, output, setup=True)
        return provider.prepare_cache(request) if operation == 'prepare-cache' else provider.resource_preflight(request)
    workflow = _request(request, output)
    digest = canonical_digest(request)
    result_path = output/'native-result.json'
    condition = _condition(request)
    if result_path.exists():
        result = strict_json(result_path.read_bytes())
        sample, sample_id = _sample_record(request, output)
        if result['request_sha256'] != digest or result['sample_complete'] != sample_id:
            raise ProductionRefused('native existing result differs')
        for item in result['artifacts'].values(): checked_artifact(item)
        return result
    intent_path, sample_path = output/'intent.json', output/'sample-complete.json'
    if intent_path.exists() and not sample_path.exists():
        raise ProductionRefused('native unknown/failed intent: never resample')
    if sample_path.exists() and not intent_path.exists(): raise ProductionRefused('orphan native sample')
    if operation == 'decode-only' and not sample_path.exists(): raise ProductionRefused('decode-only needs committed latent')
    provider = provider or NativeProvider(workflow, output)
    if isinstance(provider,NativeProvider):provider.request=request
    if sample_path.exists():
        sample, sample_id = _sample_record(request, output)
        intent = strict_json(intent_path.read_bytes())
        if intent['request_sha256'] != digest or intent['workflow_sha256'] != request['workflow_sha256']:
            raise ProductionRefused('native original intent differs')
    else:
        text = provider.text_context(request)
        checked_artifact(text['cache']); checked_artifact(text['binding'])
        binding = strict_json(Path(text['binding']['path']).read_bytes())
        if binding['identity'] != request['text_identity'] or binding['cache_sha256'] != text['cache']['sha256']:
            raise ProductionRefused('native consumed cache binding differs')
        write_record(output/'consumed-condition.json', dict(schema_version=1, request_sha256=digest,
            input_snapshot=request['input']['snapshot'], source_frame_range=request['input']['source_frame_range'],
            condition_pixel_sha256=request['input']['condition_pixel_sha256']))
        intent = dict(schema_version=1, request_sha256=digest, workflow_sha256=request['workflow_sha256'],
            native_diffusion_attempt=1, automatic_retry=False, input_snapshot=request['input']['snapshot'],
            parent=request['parent'], text_cache_key=request['text_cache_key'], started_at=now())
        intent_id = write_record(intent_path, intent)
        sampled = provider.sample(request, condition=condition,
            generator=None if request['parent'] is None else request['parent']['generator'], output=output,
            num_cond_frames=request['parameters']['num_cond_frames'], use_kv_cache=True, offload_kv_cache=True, enhance_hf=False)
        for key in ('sample', 'generator'): checked_artifact(sampled[key])
        if sampled['latent_shape'] != [1, 16, 24, 54, 96]: raise ProductionRefused('actual native latent shape differs')
        if request['parent'] is not None:
            kv = sampled['kv']
            if kv['layers'] != 48 or kv['bytes'] != 4076863488: raise ProductionRefused('actual clean history KV differs')
            checked_artifact(kv['manifest'])
            write_record(output/'consumed-kv.json', dict(request_sha256=digest, **kv))
        sample = dict(schema_version=1, algorithm='temporal_native_sample_v1', request_sha256=digest,
            workflow_sha256=request['workflow_sha256'], intent_sha256=intent_id['sha256'],
            sample=sampled['sample'], generator=sampled['generator'], native_diffusion_completed=True,
            text_cache_key=request['text_cache_key'], text_cache=text['cache'], text_binding=text['binding'],
            latent_shape=sampled['latent_shape'], created_at=now())
        sample_id = write_record(sample_path, sample)
    frames = provider.decode(sample)
    import numpy as np
    if frames.dtype != np.uint8 or frames.shape != (93, 432, 768, 3):
        raise ProductionRefused('decoded native raw RGB differs')
    frames_id = _commit_array(output/'frames.npy', frames)
    media = provider.media(output, frames, request['budget'], condition)
    object_fields(media, ('raw_movie', 'viewing_movie', 'source_movie', 'last_frame', 'contact_sheet'), 'native committed media')
    for item in media.values(): checked_artifact(item)
    head = request['budget']['discard_head_frames']
    result = dict(schema_version=1, algorithm='temporal_native_window_v1', status='complete',
        request_sha256=digest, workflow_sha256=request['workflow_sha256'], intent_sha256=artifact(intent_path)['sha256'],
        sample_complete=sample_id, native_diffusion_calls=1, budget=request['budget'],
        frame_mapping=temporal_frame_mapping(request['budget'], actual_generated_frames=93),
        artifacts=dict(sample=sample['sample'], generator=sample['generator'], frames=frames_id, **media), created_at=now(),
        technical=dict(raw=dict(frames=93, fps='16/1', width=768, height=432, pixel_exact=True),
            source=dict(frames=request['budget']['retained_frames'], fps='16/1', width=768, height=432, pixel_exact=True),
            history=dict(pixels=13 if head else 1, latents=4 if head else 1, kv_layers=48 if head else 0,
                kv_bytes=4076863488 if head else 0, source_frame_range=request['input']['source_frame_range'],
                condition_pixel_sha256=request['input']['condition_pixel_sha256'])))
    write_record(result_path, result)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
