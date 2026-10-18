"""Fixed numeric/connectivity contract and the actual Comfy model root."""
from pathlib import Path

from ..config import read_json
from .paths import SOURCE_ROOT,RUNTIME_ROOT
from .production_state import ProductionRefused
from .production_comfy import same


def validate_production_model_paths(config):
    folders=dict(sdxl='checkpoints',wan_high='diffusion_models',wan_low='diffusion_models',
                 text_encoder='text_encoders',vae='vae',upscale='upscale_models')
    for role,folder in folders.items():
        if role == 'sdxl' and config.production_strategy == 'paragraph_jimeng_v1': continue
        path=config.models[role]
        expected=(RUNTIME_ROOT/'models/comfyui'/folder/path.name).resolve()
        if path.resolve()!=expected:
            raise ProductionRefused(f'models.{role}: actual Comfy loading requires {expected}; configured {path}')


def validate_fixed_visual_template(template,role):
    filename={'sdxl':'sdxl_api.json','wan':'wan22_i2v_14b_api.json','upscale':'upscale_api.json'}[role]
    baseline=read_json(SOURCE_ROOT/'workflows'/filename)
    mapping=read_json((SOURCE_ROOT/'workflows'/filename).with_suffix('.mapping.json'))
    for key in ('inputs','models','output','nodes'):
        if not same(template.mapping[key],mapping[key]):raise ProductionRefused(f'{role}: fixed graph mapping/connectivity differs')
    variable={(ref['node_id'],ref['input']) for name,ref in mapping['inputs'].items()
              if role!='wan' or name!='negative_prompt'}
    if set(template.graph)!=set(baseline):
        raise ProductionRefused(f'{role}: fixed graph node set differs')
    # Only the declared parameter slots vary. All sampling nodes, constants,
    # switches, negatives, bit depth, codec and links stay the tested graph.
    for node,expected in baseline.items():
        actual=template.graph.get(node)
        if not isinstance(actual,dict) or actual.get('class_type')!=expected['class_type'] or set(actual.get('inputs',{}))!=set(expected['inputs']):
            raise ProductionRefused(f'{role}: fixed graph node/input set differs: {node}')
        for key,value in expected['inputs'].items():
            if (node,key) not in variable and not same(actual['inputs'][key],value):
                raise ProductionRefused(f'{role}: fixed sampling/connection differs: {node}.{key}')
