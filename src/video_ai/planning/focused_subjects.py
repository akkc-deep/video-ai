"""Inline subject declarations; references can only name existing identities."""
from copy import deepcopy


def _object(properties):
    return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)


def subject_schema(entity,variant,prior,*,previous_possible):
    entity=deepcopy(entity);variant=deepcopy(variant)
    for key in ('key',):entity['properties'].pop(key);entity['required'].remove(key)
    for key in ('key','entity_key'):variant['properties'].pop(key);variant['required'].remove(key)
    appearance=[_object(dict(unchanged=dict(type='boolean',const=True))),_object(dict(new=variant))]
    if prior and prior['appearance_variants']:
        appearance.append(_object(dict(reuse=dict(type='string',enum=[v['key'] for v in prior['appearance_variants']]))))
    presentation=dict(anyOf=appearance)
    subjects=[_object(dict(new=entity,appearance=presentation))]
    if prior and prior['entities']:
        subjects.insert(0,_object(dict(reuse=dict(type='string',enum=[e['key'] for e in prior['entities']]),appearance=presentation)))
    choices=[dict(type='array',items=dict(anyOf=subjects),minItems=0,maxItems=4)]
    if previous_possible:choices.insert(0,_object(dict(reuse_previous=dict(type='boolean',const=True))))
    return dict(anyOf=choices)


def restore_subjects(restored,prior,slices):
    restored['entities']=[];restored['appearance_variants']=[]
    previous=prior['scenes'][-1] if prior and prior['scenes'] else None
    active={}
    variants={v['key']:v for v in prior['appearance_variants']} if prior else {}
    if prior:
        for scene in prior['scenes']:
            owners={variants[key]['entity_key'] for key in scene['variant_ids']}
            for owner in owners:active[owner]=[key for key in scene['variant_ids'] if variants[key]['entity_key']==owner]
    for source in slices:
        scene=restored['scenes'][source['scene_key']]
        subjects=scene.pop('subjects')
        if isinstance(subjects,dict):
            if previous is None:raise ValueError('no previous focused subjects')
            scene['entity_ids']=deepcopy(previous['entity_ids']);scene['variant_ids']=deepcopy(previous['variant_ids'])
        else:
            scene['entity_ids']=[];scene['variant_ids']=[]
            seen={}
            for index,subject in enumerate(subjects,1):
                if 'new' in subject:
                    key=f'focus_subject_{source["scene_key"]}_{index:02d}'
                    restored['entities'].append(dict(subject['new'],key=key))
                else:key=subject['reuse']
                if key in seen:
                    if seen[key]==subject:continue
                    raise ValueError('conflicting duplicate focused subject')
                seen[key]=deepcopy(subject)
                scene['entity_ids'].append(key)
                appearance=subject['appearance']
                if 'new' in appearance:
                    vid=f'focus_variant_{source["scene_key"]}_{index:02d}'
                    row=dict(appearance['new'],key=vid,entity_key=key)
                    restored['appearance_variants'].append(row);variants[vid]=row
                    active[key]=[vid]
                elif 'reuse' in appearance:
                    vid=appearance['reuse']
                    if vid not in variants or variants[vid]['entity_key']!=key:
                        raise ValueError('focused appearance belongs to another subject')
                    active[key]=[vid]
                scene['variant_ids'].extend(active.get(key,[]))
        previous=scene
