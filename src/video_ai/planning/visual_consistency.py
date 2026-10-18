"""Fixed first-use reference baselines and stable scene dependency batches."""
import json


KINDS = (('entity', 'entities', 'entity_id', 'entity_ids'),
         ('appearance_variant', 'appearance_variants', 'variant_id', 'variant_ids'),
         ('scene_group', 'scene_groups', 'group_id', 'scene_group_id'))


def _keys(row, fields):
    if type(row) is not dict or set(row) != set(fields.split()):
        raise ValueError('invalid reference graph fields')


def _string(value):
    if type(value) is not str or not value.strip():
        raise ValueError('nonempty graph ID required')


def _ids(value):
    if type(value) is not list:
        raise ValueError('reference ID array required')
    for item in value: _string(item)
    if len(set(value)) != len(value):
        raise ValueError('duplicate reference ID')
    return value


def derive_reference_graph(scenes, bible):
    """Derive baselines, bindings and batches without accepting claimed edges."""
    if type(scenes) is not list or not scenes or type(bible) is not dict:
        raise ValueError('nonempty scenes and visual bible required')
    scene_ids = []
    for index, scene in enumerate(scenes, 1):
        if type(scene) is not dict or scene.get('scene_id') != f'scene_{index:04d}':
            raise ValueError('sequential scene IDs required')
        scene_ids.append(scene['scene_id'])
    catalogs = {}
    for kind, name, id_field, _ in KINDS:
        rows = bible.get(name)
        if type(rows) is not list:
            raise ValueError('visual bible catalog array required')
        catalog = {}
        prefix = {'entity':'entity','appearance_variant':'variant','scene_group':'group'}[kind]
        for index, row in enumerate(rows, 1):
            if type(row) is not dict or row.get(id_field) != f'{prefix}_{index:04d}':
                raise ValueError('sequential unique visual IDs required')
            catalog[row[id_field]] = row
        catalogs[kind] = catalog
    for variant in catalogs['appearance_variant'].values():
        if variant.get('entity_id') not in catalogs['entity']:
            raise ValueError('unknown variant entity')
    first = {}
    scene_uses = []
    for scene in scenes:
        entities, variants = _ids(scene.get('entity_ids')), _ids(scene.get('variant_ids'))
        group = scene.get('scene_group_id'); _string(group)
        if any(catalogs['appearance_variant'].get(v, {}).get('entity_id') not in entities for v in variants):
            raise ValueError('variant owner missing from scene')
        uses = []
        for kind, _, _, field in KINDS:
            ids = [group] if kind == 'scene_group' else scene[field]
            for item in ids:
                if item not in catalogs[kind]:
                    raise ValueError('unknown scene reference')
                first.setdefault((kind,item),scene['scene_id'])
                uses.append(dict(kind=kind,id=item))
        scene_uses.append(uses)
    baselines = []
    for kind, _, _, _ in KINDS:
        for item in catalogs[kind]:
            if (kind,item) not in first:
                raise ValueError('unused visual bible entry')
            baselines.append(dict(kind=kind,id=item,scene_id=first[kind,item]))
    bindings, dependencies = [], []
    for scene, uses in zip(scenes,scene_uses):
        sources = {}
        for use in uses:
            origin = first[use['kind'],use['id']]
            if origin != scene['scene_id']:
                sources.setdefault(origin,[]).append(use)
        ordered = sorted(sources,key=scene_ids.index)
        bindings.append([dict(source_scene_id=source,uses=sources[source]) for source in ordered])
        dependencies.append(ordered)
    remaining = dict(zip(scene_ids,map(set,dependencies)))
    batches = []
    while remaining:
        batch = sorted(key for key, edges in remaining.items() if not edges)
        if not batch:
            raise ValueError('cyclic scene dependencies')
        batches.append(batch)
        for key in batch: del remaining[key]
        for edges in remaining.values(): edges.difference_update(batch)
    return baselines, bindings, dependencies, batches


def validate_reference_graph(scenes, bible) -> list[list[str]]:
    """Reject missing uses, substituted baselines and forged dependency edges."""
    try:
        baselines, bindings, dependencies, batches = derive_reference_graph(scenes,bible)
        if type(bible.get('baselines')) is not list:
            raise ValueError('baseline array required')
        for baseline in bible['baselines']: _keys(baseline,'kind id scene_id')
        for scene in scenes:
            if type(scene.get('reference_bindings')) is not list:
                raise ValueError('reference bindings array required')
            _ids(scene.get('dependencies'))
            for binding in scene['reference_bindings']:
                _keys(binding,'source_scene_id uses')
                _string(binding['source_scene_id'])
                if type(binding['uses']) is not list: raise ValueError('uses array required')
                for use in binding['uses']: _keys(use,'kind id')
        actual = [bible['baselines'],[s['reference_bindings'] for s in scenes],[s['dependencies'] for s in scenes]]
        expected = [baselines,bindings,dependencies]
        if json.dumps(actual,sort_keys=True,allow_nan=False) != json.dumps(expected,sort_keys=True,allow_nan=False):
            raise ValueError('reference graph differs from fixed first-use baselines')
        return batches
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError('invalid reference graph structure') from exc
