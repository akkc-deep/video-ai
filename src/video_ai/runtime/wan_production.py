"""Production Wan recipes and request-local backend selection. No tensor imports."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
import json

from ..experiments.wan_fast_profiles import digest
from ..experiments.wan_wrapper_backend import MODEL_PINS, recipe, contract, SETTINGS
from .workflows import WorkflowTemplate, safe_comfy_path

SOURCE = Path(__file__).resolve().parents[3]
from .paths import RUNTIME_ROOT
ENVIRONMENT_RELATIVE = Path('scratch/benchmarks/LVA-07-04-environment')
ENVIRONMENT = RUNTIME_ROOT/ENVIRONMENT_RELATIVE
PROTOCOL = 'production_wan_wrapper_v1'
MODES = ('fast','control','native')
_mode = ContextVar('production_wan_mode', default='native')


def current_mode(): return _mode.get()


def environment_for(config):return config.runtime_root/ENVIRONMENT_RELATIVE


def require_environment(config):
    environment=environment_for(config)
    for relative in ('python_embeded/python.exe','ComfyUI/main.py','sources.json'):
        if not (environment/relative).is_file():
            raise ValueError(f'Wrapper runtime unavailable at {environment}; migrate the repaired runtime or use --wan-mode native')
    return environment


@contextmanager
def mode_scope(mode):
    if mode not in MODES: raise ValueError('wan_mode must be fast, control or native')
    token=_mode.set(mode)
    try: yield
    finally: _mode.reset(token)


def production_mode(function):
    @wraps(function)
    def call(*args,**kwargs):
        with mode_scope(kwargs.get('wan_mode','fast')):
            return function(*args,**kwargs)
    return call


def select_mode(saved_graph):
    """An existing request always wins over the invocation's new-work default."""
    if saved_graph is None: return current_mode()
    prepares=[v for v in saved_graph.values() if v.get('class_type')=='VideoAIWanPrepare']
    if not prepares: return 'native'
    if len(prepares)!=1 or prepares[0]['inputs'].get('protocol')!=PROTOCOL:
        raise ValueError('invalid production Wrapper protocol')
    mode=prepares[0]['inputs'].get('mode')
    if mode not in ('fast','control'): raise ValueError('invalid production Wrapper mode')
    return mode


def parameter_mode(p):
    if p.get('scheduler')=='euler': return 'fast' if p.get('lora_enabled') is True else 'control'
    return 'native'


def effective_parameters(parameters,mode):
    p=deepcopy(parameters)
    if mode=='native': return p
    if mode not in ('fast','control'): raise ValueError('unknown Wrapper mode')
    if ((p['width'],p['height'],p['fps'])!=(768,432,16) or type(p['length']) is not int
            or not 1<=p['length']<=93 or (p['length']-1)%4):
        raise ValueError('Wrapper fast/control requires 768x432, native16, 4n+1 frames <=93; use --wan-mode native for this profile')
    r=recipe(mode)
    p.update(steps=r['steps'],cfg=r['cfg'],sampler='euler',scheduler='euler',split_step=r['split'],
             shift_high=5.,shift_low=5.,lora_enabled=r['lora_enabled'])
    return p


@dataclass(frozen=True)
class ProductionProfile:
    mode:str
    def identity_dict(self):
        return dict(schema_version=2,kind='production',backend='wan_wrapper',protocol=PROTOCOL,
            mode=self.mode,recipe=recipe(self.mode),settings={k:v for k,v in SETTINGS.items() if k!='num_frames'},
            memory_limits=contract()['future_full_model_limits'])
    def digest(self): return digest(self.identity_dict())


def production_profile(mode):
    if mode not in ('fast','control'): raise ValueError('production Wrapper mode required')
    return ProductionProfile(mode)


def wrapper_template(mode):
    production_profile(mode)
    name=lambda role:Path(MODEL_PINS[role][0]).name
    graph={
        '10':dict(class_type='VideoAIWanPrepare',inputs=dict(start_image='__IMAGE__',positive_prompt='',negative_prompt='',
            width=768,height=432,num_frames=93,seed_high=0,seed_low=0,mode=mode,protocol=PROTOCOL,
            recipe_sha256=production_profile(mode).digest(),trial_token='__PREFIX__')),
        '30':dict(class_type='VideoAIWanSampler',inputs=dict(role='high',mode=mode,model_name=name('base_high'),
            image_embeds=['10',0],text_embeds=['10',1],seed=0,trial_token='__PREFIX__')),
        '40':dict(class_type='VideoAIWanSampler',inputs=dict(role='low',mode=mode,model_name=name('base_low'),
            image_embeds=['10',0],text_embeds=['10',1],seed=0,samples=['30',0],trial_token='__PREFIX__')),
        '50':dict(class_type='WanVideoDecode',inputs=dict(vae=['10',2],samples=['40',0],enable_vae_tiling=False,
            tile_x=272,tile_y=272,tile_stride_x=144,tile_stride_y=128,normalization='default')),
        '108':dict(class_type='VideoAIWanSave',inputs=dict(images=['50',0],fps=16,filename_prefix='__PREFIX__'))}
    references={'positive_prompt':('10','positive_prompt'),'negative_prompt':('10','negative_prompt'),
        'start_image':('10','start_image'),'width':('10','width'),'height':('10','height'),'length':('10','num_frames'),
        'fps':('108','fps'),'seed_high':('30','seed'),'seed_low':('40','seed'),'output_prefix':('108','filename_prefix')}
    mapping=dict(schema_version=1,nodes={k:v['class_type'] for k,v in graph.items()},
        inputs={k:dict(node_id=v[0],input=v[1]) for k,v in references.items()},models={},output=dict(node_id='108',collection='images'))
    return WorkflowTemplate(graph,mapping)


def request_graph(template,p,image,prefix):
    safe_comfy_path(image);safe_comfy_path(prefix)
    values=dict(positive_prompt=p['positive'],start_image=image,width=p['width'],height=p['height'],
        length=p['length'],fps=p['fps'],seed_high=p['seed_high'],seed_low=p['seed_low'])
    wrapper=select_mode(template.graph)!='native'
    if wrapper: values['negative_prompt']=p['negative']
    graph=template.instantiate(values,output_prefix=prefix)
    if wrapper:
        graph['10']['inputs'].update(seed_high=p['seed_high'],seed_low=p['seed_low'],trial_token=prefix)
        for node in ('30','40'): graph[node]['inputs']['trial_token']=prefix
    return graph


def scene_template(context,row):
    mode=parameter_mode(row['parameters'])
    return context['template'] if mode=='native' else wrapper_template(mode)


def route_scene_rows(frozen,store,rows):
    from ._scene_revision_readers import inherited_clip_record
    for row in rows:
        cid=row['budget']['clip_id'];saved=store.read(store.clip_dir(cid)/'graph.json')
        inherited=inherited_clip_record(frozen,cid,context=store.revision_context) if store.revision_context is not None else None
        mode=parameter_mode(inherited['request']['parameters']) if inherited is not None else select_mode(saved)
        row['parameters']=effective_parameters(row['parameters'],mode)


def service_spec(config,run,native_spec):
    """Replace only the source-stage Comfy process, retaining its URL/ownership."""
    from dataclasses import replace
    from urllib.parse import urlsplit
    parts=urlsplit(native_spec.url)
    environment=require_environment(config)
    launch=prepare_launch(config,run)
    args=(str(environment/'python_embeded/python.exe'),'-I','-B','-X','utf8',str(SOURCE/'scripts/serve_wan_production.py'),
        '--run',str(run),'--launch',str(launch),'--port',str(parts.port))
    return replace(native_spec,args=args,cwd=environment/'ComfyUI')


def prepare_launch(config,run):
    from .manifest import hash_file,thaw
    from ..experiments.wan_fast_profiles import write_once
    from uuid import uuid4
    epoch=uuid4().hex
    root=Path(run)/'comfy/wan-production'/epoch
    source_files=[SOURCE/'scripts/serve_wan_production.py',SOURCE/'scripts/observe_wan_wrapper_comfy.py',
                  Path(__file__),Path(__file__).with_name('wan_production_worker.py')]
    source_files+=sorted((SOURCE/'src/video_ai/experiments').glob('wan_wrapper_*.py'))
    source_files+=[SOURCE/'src/video_ai/experiments/wan_fast_profiles.py',SOURCE/'src/video_ai/experiments/wan_fast_experiment.py',
                  SOURCE/'docs/task-designs/LVA-07-04-contract.json']
    from .production_state import process_started_at
    from ..config import read_json
    import os
    lock=Path(run)/'.make-video.lock'
    launch=dict(schema_version=1,protocol=PROTOCOL,epoch=epoch,run=str(Path(run).resolve()),
        owner_pid=os.getpid(),owner_started_at=process_started_at(os.getpid()),
        run_lock=read_json(lock) if lock.exists() else None,source_root=str(SOURCE),runtime_root=str(config.runtime_root),
        environment=str(environment_for(config)),
        tools={k:str(config.tools[k]) for k in ('ffmpeg','ffprobe')},
        models={role:dict(path=str(config.runtime_root/'shared/models/comfyui'/pin[0]),bytes=pin[1],sha256=pin[2]) for role,pin in MODEL_PINS.items()},
        source_artifacts=[thaw(hash_file(p)) for p in source_files])
    path=root/'launch.json';write_once(path,launch)
    return path
