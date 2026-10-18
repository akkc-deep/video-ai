"""English-only scene transport; source facts are restored from fixed schemas."""
from copy import deepcopy

MODE='model_visual_v2'
FIELDS=('composition','action_start','action_end','image_prompt','video_prompt')


def is_model_visual(schema):
    return isinstance(schema,dict) and schema.get('description')==MODE


def obj(properties):
    return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)


def project(schema):
    # llama.cpp matches JSON payload characters, so quotes/backslashes must
    # not be admitted as raw characters in generated English strings.
    pattern=r"^[A-Za-z0-9 ,.;:!?()'-]{1,160}$"
    english=dict(type='string',minLength=1,maxLength=160,pattern=pattern)
    shots={}
    for shot in schema['properties']['shots']['prefixItems']:
        p=shot['properties'];sid=p['shot_id']['const']
        props={k:deepcopy(p[k]) for k in ('shot_id','entity_ids','camera_motion')}
        props.update({k:deepcopy(english) for k in FIELDS})
        props['needs_finer_audio']=dict(type='boolean')
        shots[sid]=obj(props)
    global_visual=deepcopy(schema['properties']['global_visual'])
    if 'const' not in global_visual:
        for key in ('style','color_palette','lighting'):global_visual['properties'][key]['pattern']=pattern
        global_visual['properties']['entities']['items']['properties']['description']['pattern']=pattern
    return obj(dict(schema_version=dict(type='integer',const=1),global_visual=global_visual,shots=obj(shots)))


def restore(value,schema,check):
    wire=project(schema);check(value,wire)
    rows=[]
    from ..planning.storyboard import depiction_anchor
    for spec in schema['properties']['shots']['prefixItems']:
        p=spec['properties'];sid=p['shot_id']['const'];row=deepcopy(value['shots'][sid])
        requirements=[]
        for item in p['visual_requirements']['prefixItems']:
            fields=item['properties']
            req={k:deepcopy(v['const']) for k,v in fields.items() if 'const' in v}
            req['needs_finer_audio']=row['needs_finer_audio']
            req['visual_expression']=depiction_anchor(req,source_quote=req['source_quote'])+row['composition']
            requirements.append(req)
        del row['needs_finer_audio']
        anchor=depiction_anchor(requirements[0],source_quote=requirements[0]['source_quote'])
        for key in FIELDS:row[key]=anchor+row[key]
        row['video_prompt']+=' Camera path: '+row['camera_motion']+'.'
        row['visual_requirements']=requirements;rows.append(row)
    return dict(schema_version=1,global_visual=deepcopy(value['global_visual']),shots=rows)
