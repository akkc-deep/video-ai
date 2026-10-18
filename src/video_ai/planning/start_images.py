"""Deterministic start-image parameters and exact source-to-image associations."""
from pathlib import Path

from ..runtime.paths import _validate_spelling

NEGATIVE = 'lowres, blurry, out of focus, deformed, bad anatomy, extra limbs, mutated, watermark, text, logo, signature'


def keys(data, names, label):
    if not isinstance(data, dict) or set(data) != set(names.split()):
        raise ValueError(f'{label}: missing/unknown fields')


def validate_dimensions(width, height):
    if any(type(v) is not int or v < 64 or v % 8 for v in (width, height)) or width*9 != height*16:
        raise ValueError('image dimensions must be integers >=64, multiples of 8, and exactly 16:9')
    return width, height


def contain_filter(width, height):
    validate_dimensions(width, height)
    return (f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,'
            f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=rgb24')


def validate_input_map(data, storyboard):
    keys(data, 'schema_version run_id shots entities', 'image input map')
    if type(data['schema_version']) is not int or data['schema_version'] != 1 or data['run_id'] != storyboard['run_id']:
        raise ValueError('image input schema/run mismatch')
    allowed = dict(shots={s['shot_id'] for s in storyboard['shots']},
                   entities={e['entity_id'] for e in storyboard['global_visual']['entities']})
    for kind in allowed:
        if not isinstance(data[kind],dict) or set(data[kind])-allowed[kind]:
            raise ValueError(f'unknown {kind} IDs')
        for value in data[kind].values():
            if not isinstance(value,str) or not value.strip() or not Path(_validate_spelling(value)).is_absolute():
                raise ValueError('explicit absolute source image path required')
    return data


def validate_directions(data, storyboard):
    keys(data, 'schema_version run_id storyboard_identity review_basis_identity shots', 'visual directions')
    if type(data['schema_version']) is not int or data['schema_version'] != 1 or data['run_id'] != storyboard['run_id']:
        raise ValueError('visual directions schema/run mismatch')
    shots = {s['shot_id']: s for s in storyboard['shots']}
    if not isinstance(data['shots'], dict) or not data['shots'] or set(data['shots']) - set(shots):
        raise ValueError('visual directions require known shots')
    for uid, direction in data['shots'].items():
        keys(direction, 'positive negative reason requirement_ids', 'static direction')
        if any(not isinstance(direction[k], str) or not direction[k].strip() for k in ('positive', 'reason')) or not isinstance(direction['negative'], str):
            raise ValueError('static direction text/reason required')
        expected = [r['requirement_id'] for r in shots[uid]['visual_requirements'] if r['unit_id'] == shots[uid]['primary_unit_id']]
        if direction['requirement_ids'] != expected or not expected:
            raise ValueError('static directions must bind exact primary scene requirements')
    return data['shots']


def image_parameters(shot, global_visual, width, height, *, direction=None, model_visual=False):
    validate_dimensions(width,height)
    seed=812045847300606+int(shot['shot_id'].split('_')[1])-1
    if not 0 <= seed < 2**64: raise ValueError('SDXL seed out of uint64 range')
    descriptions={e['entity_id']:e['description'] for e in global_visual['entities']}
    prompt=shot['image_prompt']+'\n'+'\n'.join(f'{key}: {global_visual[key]}' for key in ('style','color_palette','lighting'))
    for eid in shot['entity_ids']: prompt+=f'\nentity {eid}: {descriptions[eid]}'
    if model_visual:
        from .model_visual_prompts import render_model_prompt
        prompt=render_model_prompt(shot,global_visual,'image')
    negative=NEGATIVE
    if model_visual:
        from .model_visual_prompts import MODEL_NEGATIVE_SUFFIX,VOYAGER_NEGATIVE_SUFFIX,VOYAGER_APPEARANCE
        negative+=MODEL_NEGATIVE_SUFFIX
        if VOYAGER_APPEARANCE in prompt:negative+=VOYAGER_NEGATIVE_SUFFIX
        # SDXL is trained around one megapixel. Wan fast size is independent;
        # its I2V node resizes this high-quality still to the native clip size.
        width,height=1280,720
    if direction is not None:
        prompt=direction['positive']+'\nOriginal storyboard image prompt and descriptions:\n'+prompt
        if direction['negative'].strip():negative+=', '+direction['negative'].strip()
    return dict(positive=prompt,negative=negative,seed=seed,width=width,height=height,steps=25,
                cfg=7,sampler='dpmpp_2m',scheduler='karras',denoise=1,batch=1)


def requirement_images(storyboard, identities):
    result=[];shots=storyboard['shots']
    for shot in shots:
        for index,req in enumerate(shot['visual_requirements']):
            target=shot;role='primary'
            if req['unit_id'] != shot['primary_unit_id']:
                if not any(b['unit_id']==req['unit_id'] and b.get('quantization_edge') is True for b in shot['bindings']):
                    raise ValueError('foreign image requirement is not a quantization edge')
                matches=[(i,s) for i,s in enumerate(shots) if s['primary_unit_id']==req['unit_id']]
                if not matches: raise ValueError('edge has no primary image scene')
                _,target=min(matches,key=lambda pair:(abs(pair[1]['start_frame']-shot['start_frame']),pair[0]))
                role='quantization_edge_preview'
            result.append(dict(shot_id=shot['shot_id'],requirement_id=req['requirement_id'],requirement_index=index,
                unit_id=req['unit_id'],source_quote=req['source_quote'],image_shot_id=target['shot_id'],
                role=role,image_identity=identities[target['shot_id']]))
    return result
