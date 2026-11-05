"""English-only scene transport; source facts are restored from fixed schemas."""
from copy import deepcopy

MODE='model_visual_v2'
FIELDS=('composition','action_start','action_end','image_prompt','video_prompt')


def is_model_visual(schema):
    return isinstance(schema,dict) and schema.get('description') in (MODE,'model_visual_v3')


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
        if schema.get('description')=='model_visual_v3':
            requirement=p['visual_requirements']['prefixItems'][0]['properties']
            subject=requirement.get('subject',{}).get('const')
            names={'木星':'Jupiter','土星':'Saturn','天王星':'Uranus','海王星':'Neptune','木卫一':'Io','地球':'Earth'}
            quote=requirement.get('source_quote',{}).get('const','')
            explicit=[name for name in names if quote.startswith(name) or any(
                verb+name in quote for verb in ('抵达','靠近','接近','飞掠','飞过','掠过'))]
            if len(explicit)==1:subject=explicit[0]
            if subject in names:
                name=names[subject]
                name_pattern='['+name[0].upper()+name[0].lower()+']'+name[1:]
                for key in ('image_prompt','video_prompt'):
                    props[key]['pattern']="^[A-Za-z0-9 ,.;:!?()'-]{0,72}"+name_pattern+"[A-Za-z0-9 ,.;:!?()'-]{0,71}[.]$"
        props['needs_finer_audio']=dict(type='boolean')
        shots[sid]=obj(props)
    global_visual=deepcopy(schema['properties']['global_visual'])
    if 'const' not in global_visual:
        for key in ('style','color_palette','lighting'):global_visual['properties'][key]['pattern']=pattern
        global_visual['properties']['entities']['items']['properties']['description']['pattern']=pattern
    properties=dict(schema_version=dict(type='integer',const=1))
    if schema.get('description')!='model_visual_v3' or 'const' not in global_visual:
        properties['global_visual']=global_visual
    properties['shots']=obj(shots)
    return obj(properties)


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
    global_visual=(value['global_visual'] if 'global_visual' in wire['properties'] else
                   schema['properties']['global_visual']['const'])
    return dict(schema_version=1,global_visual=deepcopy(global_visual),shots=rows)
