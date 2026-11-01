"""Immutable identities for a single native twenty-second Wan experiment."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import traceback
from uuid import uuid4

from ..adapters.common import strict_json


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return strict_json(Path(path).read_bytes().removeprefix(b'\xef\xbb\xbf'))


def write_bytes(path, raw):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return path


def write_json(path, value):
    return write_bytes(path, (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n').encode())


def identity(path):
    path = Path(path).resolve(strict=True)
    before = path.stat()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('identity changed during read: '+str(path))
    return dict(path=str(path), bytes=after.st_size, sha256=digest, mtime_ns=after.st_mtime_ns)


def verify_identity(value):
    if identity(value['path']) != value:
        raise ValueError('identity changed: '+value['path'])


def tree_identity(root):
    return [identity(p) for p in sorted(Path(root).rglob('*')) if p.is_file()]


class Evidence:
    """HttpClient-compatible durable evidence, outside any production run."""
    def __init__(self, root): self.root = Path(root)
    def save_bytes(self, name, raw):
        path = (self.root/name).resolve()
        if not path.is_relative_to(self.root.resolve()): raise ValueError('evidence path escape')
        return write_bytes(path, raw)
    def save_json(self, name, value):
        return self.save_bytes(name, (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n').encode())
    def exception(self, stage, unit_id, exc):
        return self.save_bytes('errors/'+uuid4().hex+'.txt', ''.join(traceback.format_exception(exc)).encode())
    def event(self, stage, unit_id, event, details):
        return self.save_json('events/'+uuid4().hex+'.json',
            dict(time=now(),stage=stage,unit_id=unit_id,event=event,details=details))


def native_budget():
    return dict(requested_frames=321, retained_frames=320, source_start=0,
                source_end=320, fps=16, duration_seconds=20)


def validate_graph(graph):
    """Only named input slots can vary; sampling/connectivity stay versioned."""
    from ..runtime.paths import SOURCE_ROOT
    from ..runtime.workflows import WorkflowTemplate
    from ..runtime.production_visual_templates import validate_fixed_visual_template
    baseline = read_json(SOURCE_ROOT/'workflows/wan22_i2v_14b_api.json')
    mapping = read_json(SOURCE_ROOT/'workflows/wan22_i2v_14b_api.mapping.json')
    template = WorkflowTemplate(graph, mapping)
    validate_fixed_visual_template(template, 'wan')
    required = {'width': 768, 'height': 432, 'length': 321, 'fps': 16}
    for name, expected in required.items():
        ref = mapping['inputs'][name]
        actual = graph[ref['node_id']]['inputs'][ref['input']]
        if type(actual) not in (int, float) or isinstance(actual, bool) or actual != expected:
            raise ValueError('fixed native budget differs: '+name)
    for name, ref in mapping['models'].items():
        node, key = ref['node_id'], ref['input']
        if graph[node]['inputs'][key] != baseline[node]['inputs'][key]:
            raise ValueError('fixed model differs: '+name)
    for name in ('start_image', 'output_prefix'):
        from ..runtime.workflows import safe_comfy_path
        ref = mapping['inputs'][name]
        safe_comfy_path(graph[ref['node_id']]['inputs'][ref['input']])


def freeze_case(root, *, source_run, graph, dependencies, runtime):
    root, source = Path(root).resolve(), Path(source_run).resolve(strict=True)
    if root.is_relative_to(source) or source.is_relative_to(root):
        raise ValueError('experiment overlaps source run')
    validate_graph(graph)
    root.mkdir(parents=True, exist_ok=False)
    write_json(root/'graph.json', graph)
    write_json(root/'source-inventory.json', tree_identity(source))
    case = dict(schema_version=1, algorithm='wan22_whole_scene_experiment_v1',
                created_at=now(), source_run=str(source), budget=native_budget(),
                graph=identity(root/'graph.json'), source_inventory=identity(root/'source-inventory.json'),
                dependencies={k: identity(v) for k, v in dependencies.items()}, runtime=deepcopy(runtime))
    write_json(root/'case.json', case)
    return case


def verify_case(root):
    root = Path(root).resolve(strict=True); case = read_json(root/'case.json')
    if (case['schema_version'] != 1 or case['algorithm'] != 'wan22_whole_scene_experiment_v1'
            or case['budget'] != native_budget()): raise ValueError('unknown experiment contract')
    if root.is_relative_to(Path(case['source_run'])): raise ValueError('source overlap')
    for value in [case['graph'], case['source_inventory'], *case['dependencies'].values()]:
        verify_identity(value)
    validate_graph(read_json(root/'graph.json'))
    if read_json(root/'source-inventory.json') != tree_identity(case['source_run']):
        raise ValueError('source run identity changed')
    return case


def validate_model_loading(models, model_root, comfy_root):
    """Bind Comfy's actual search order, excluding alternate path injection."""
    model_root=Path(model_root).resolve();comfy_root=Path(comfy_root).resolve()
    if (comfy_root/'extra_model_paths.yaml').exists():
        raise ValueError('unfrozen extra model paths configuration')
    folders={'wan_high':'diffusion_models','wan_low':'diffusion_models',
             'text_encoder':'text_encoders','vae':'vae'}
    for role,folder in folders.items():
        path=Path(models[role]).resolve(strict=True)
        if path != (model_root/folder/path.name).resolve(strict=True):
            raise ValueError('actual model loading path differs: '+role)
        alternate='unet' if role in ('wan_high','wan_low') else 'clip' if role=='text_encoder' else None
        if alternate and (model_root/alternate/path.name).exists():
            raise ValueError('alternate model search path shadows frozen model: '+role)


def prepare_case(source_run, scene_id, contract_path, root):
    """Consume the real admitted image and a fully reviewed VCO-01 contract."""
    from ..planning.production_scenes import canonical_digest
    from ..planning.scene_video_prompts import validate_scene_video_prompt_contract, render_scene_video_prompt
    from ..runtime.production_inputs import load_frozen_inputs
    from ..runtime.scene_revision_records import load_scene_common_prefix
    from ..runtime.image_selection_records import load_committed_plan
    from ..runtime.reference_image_records import require_reference_image_acceptance
    from ..runtime.paths import PathPolicy

    source = Path(source_run).resolve(strict=True); root = Path(root).resolve()
    PathPolicy().validate_write(root, 'cache')
    frozen = load_frozen_inputs(source)
    units, timeline = load_scene_common_prefix(frozen)
    bible, plan = load_committed_plan(frozen, units, timeline)
    wan = require_reference_image_acceptance(frozen, units, timeline)
    contract = validate_scene_video_prompt_contract(read_json(contract_path),
        bible=bible, plan=plan, wan_inputs=wan, script=frozen.script)
    scene = next(s for s in plan['scenes'] if s['scene_id'] == scene_id)
    clip = next(c for c in plan['clips'] if c['scene_id'] == scene_id and c['parent_clip_id'] is None)
    folder = source/'production/scene-clips'/clip['clip_id']
    original = read_json(folder/'request.json'); adapted = read_json(folder/'input.json')
    selected = next(s for s in wan['scenes'] if s['scene_id'] == scene_id)
    for item in (selected, adapted['source'], adapted['target']):
        current = identity(item['path'])
        if any(current[k] != item[k] for k in ('bytes', 'sha256')):
            raise ValueError('admitted input identity changed')
    if (canonical_digest(adapted) != original['input_sha256']
            or adapted['source']['sha256'] != selected['sha256'] or original['selected_image'] != selected
            or adapted['width'] != 768 or adapted['height'] != 432):
        raise ValueError('original first-clip input differs from admission')
    graph = read_json(folder/'graph.json')
    if canonical_digest(graph) != original['graph_sha256']:
        raise ValueError('original graph binding changed')
    if (graph['129:86']['inputs']['noise_seed'] != original['parameters']['seed_high']
            or graph['129:85']['inputs']['noise_seed'] != original['parameters']['seed_low']):
        raise ValueError('original seed declaration differs from graph')
    graph['129:98']['inputs']['length'] = 321
    graph['129:93']['inputs']['text'] = render_scene_video_prompt(contract, bible, scene, clip['clip_id'])
    graph['97']['inputs']['image'] = 'start.png'
    graph['108']['inputs']['filename_prefix'] = 'candidate'
    cfg = frozen.config
    from ..runtime.production_visual_templates import validate_production_model_paths
    validate_production_model_paths(cfg)
    validate_model_loading(cfg.models,'D:/VideoSi/models/comfyui',cfg.tools['comfy_root'])
    runtime = dict(scene_id=scene_id, clip_id=clip['clip_id'],
        wan_seconds=cfg.timeouts['wan'], service_start_seconds=cfg.timeouts['service_start'],
        tools={k: str(cfg.tools[k]) for k in ('comfy_root','comfy_python','ffmpeg','ffprobe')},
        model_root='D:/VideoSi/models/comfyui', seed_high=original['parameters']['seed_high'],
        seed_low=original['parameters']['seed_low'], prompt_policy='visual_v2',
        noise_note='Changing length changes noise tensor; matching seed is not elementwise identical noise.')
    for key in ('wan_seconds', 'service_start_seconds'):
        if not isinstance(runtime[key], (int,float)) or not math.isfinite(runtime[key]) or runtime[key] <= 0:
            raise ValueError('finite frozen deadline required')
    dependencies = {'start': Path(adapted['target']['path']), 'selected': Path(selected['path']),
                    'prompt_contract': Path(contract_path)}
    for role in ('wan_high','wan_low','text_encoder','vae'):
        dependencies['model/'+role] = cfg.models[role]
    for role in ('comfy_python','ffmpeg','ffprobe'):
        dependencies['tool/'+role] = cfg.tools[role]
    # Archive exact executable source, including built-in Comfy nodes. No package installation.
    from ..runtime.paths import SOURCE_ROOT
    for base, prefix in ((SOURCE_ROOT/'src/video_ai', 'video_ai'), (cfg.tools['comfy_root'], 'comfy')):
        for path in base.rglob('*.py'):
            if '.git' not in path.parts and '__pycache__' not in path.parts:
                dependencies['code/'+prefix+'/'+path.relative_to(base).as_posix()] = path
    case = freeze_case(root, source_run=source, graph=graph, dependencies=dependencies, runtime=runtime)
    write_bytes(root/'input/start.png', Path(adapted['target']['path']).read_bytes())
    write_bytes(root/'prompt-contract.json', Path(contract_path).read_bytes())
    for name, path in dependencies.items():
        if name.startswith('code/'):
            write_bytes(root/'software'/name.removeprefix('code/'), Path(path).read_bytes())
    write_json(root/'prepared.json', dict(case_sha256=identity(root/'case.json')['sha256'],
        start=identity(root/'input/start.png'), prompt=identity(root/'prompt-contract.json'),
        software=tree_identity(root/'software')))
    return case
