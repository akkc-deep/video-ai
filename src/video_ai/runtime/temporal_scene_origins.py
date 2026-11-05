"""Explicit native revision views; original observations remain original events."""
from copy import deepcopy
from pathlib import Path

from ..planning.production_scenes import canonical_digest
from .production_state import ProductionRefused
from .temporal_scene_admission import _refused


def remap_temporal_window(window,mappings):
    from ._scene_revision_origins import remap_media
    result=remap_media({key:value for key,value in window.items() if not key.startswith('origin_')},mappings)
    # A copied artifact gets a local address; its original intent and author
    # events keep the exact original meaning and SHA-bound paths.
    for key in ('request','static_observation'):
        if key in window:result[key]=deepcopy(window[key])
    return result


def remap_temporal_chain(chain,mappings):
    from ._scene_revision_origins import remap_media
    result=remap_media(chain,mappings)
    for key in ('observation','origin_template'):
        if key in chain:result[key]=deepcopy(chain[key])
    if 'windows' in chain:result['windows']=[remap_temporal_window(window,mappings) for window in chain['windows']]
    return result


def _guards(root):
    from .scene_revision_records import RevisionGuard
    stack=[root];seen=set()
    while stack:
        guard=stack.pop()
        if type(guard) is not RevisionGuard:raise ProductionRefused('unknown native revision origin guard')
        if id(guard) in seen:continue
        seen.add(id(guard));yield guard;stack.extend(guard.ancestors)


@_refused
def bound_temporal_artifact(store,path,expected=None):
    """Allow an original JSON only when the revision captured its actual identity."""
    from .paths import PROJECT_ROOT
    from .scene_revision_records import verify_artifact,path_identity
    if getattr(store,'execution_mode',None)!='temporal_extension_v1' or store.revision_context is None:return None
    path=Path(path)
    if path.is_relative_to(store.run_dir):return None
    for guard in _guards(store.revision_context['guard']):
        entry=guard.files.get(str(path))
        if entry is None:continue
        value,root,empty,identity=entry;root=Path(root)
        if not root.is_relative_to(PROJECT_ROOT/'runs') or not path.is_relative_to(root):continue
        if empty or value['bytes']<=0 or expected is not None and value!=expected:
            raise ProductionRefused('native revision Artifact differs from captured original')
        verify_artifact(value,root=root)
        if path_identity(path)!=identity:raise ProductionRefused('native original file ownership changed')
        return deepcopy(value)
    return None


@_refused
def inherited_temporal_window(context,row,parent=None):
    from ._scene_revision_readers import proof_for
    from .scene_revision_records import require_revision_import
    from .production_inputs import load_frozen_inputs
    from ._scene_revision_origins import source_clip_record,remap_media
    store=context['store'];key=row['budget']['clip_id']
    proof=proof_for(context['frozen'],'clip',key,context=store.revision_context)
    if proof is None:return None
    folder=store.clip_dir(key)
    if folder.exists() and any(folder.iterdir()):raise ProductionRefused('owned native window competes with imported content')
    source=load_frozen_inputs(proof['source_run']);record=source_clip_record(source,key)
    if 'native_window' not in record or record['accepted'] is None or record['rejected'] is not None:
        raise ProductionRefused('native import lacks original complete chain acceptance')
    window=record['native_window'];request=record['request']
    if (canonical_digest(window['budget'])!=canonical_digest(row['budget'])
            or canonical_digest(request['parameters'])!=canonical_digest(row['parameters'])
            or canonical_digest(request['narration_bindings'])!=canonical_digest(row['narration_bindings'])):
        raise ProductionRefused('native imported parameters/narration/mapping differ')
    selected=next(image for image in context['wan']['scenes'] if image['scene_id']==row['budget']['scene_id'])
    selected={key:selected[key] for key in ('path','bytes','sha256')}
    if any(selected[key]!=window['selected_image'][key] for key in ('bytes','sha256')):
        raise ProductionRefused('native imported selected original differs')
    if parent is not None and request['parent']['clip_id']!=parent['budget']['clip_id']:
        raise ProductionRefused('native imported parent differs')
    mappings=[item for sidecar,_ in proof['imports'].values() for item in sidecar['local_artifacts']]
    origin={key:deepcopy(value) for key,value in record['native_chain'].items() if key not in ('windows','origin_template')}
    origin=remap_temporal_chain(origin,mappings)
    result=remap_temporal_window(window,mappings)
    result.update(selected_image=selected,origin_chain=origin,origin_template=deepcopy(record['template']),
        origin_clip_view=require_revision_import(context['frozen'],'clip',key,context=proof))
    proof['guard'].verify_captured_bytes()
    return result


@_refused
def inherited_temporal_chain(context,scene_id,windows):
    if not windows or any('origin_chain' not in window for window in windows):return None
    first=windows[0]['origin_chain']
    if any(window['origin_chain']['result']!=first['result'] or window['origin_chain']['acceptance']!=first['acceptance'] for window in windows):
        raise ProductionRefused('native imported windows do not share one original chain event')
    if first['frame_range']!=[windows[0]['budget']['start_frame'],windows[-1]['budget']['end_frame']]:
        raise ProductionRefused('native original complete playback scope differs')
    template=windows[0]['origin_template']
    wanted=[window['budget']['clip_id'] for window in windows]
    if [row['clip_id'] for row in template['binding']['windows']]!=wanted:raise ProductionRefused('native imported chain coverage differs')
    store=context['store'];folder=store.path(Path('chains')/scene_id)
    if folder.exists() and any(folder.iterdir()):raise ProductionRefused('owned chain competes with inherited complete viewing')
    for key in ('result','acceptance'):
        if bound_temporal_artifact(store,first[key]['path'],first[key]) is None:raise ProductionRefused('native original chain metadata is outside captured origin')
    store.validate_artifact(first['viewing'])
    return dict(deepcopy(first),scene_id=scene_id,status='accepted',windows=windows,origin_template=deepcopy(template))
