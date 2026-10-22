"""Reconstruct revision dependencies and invalidation from admitted originals."""
from copy import deepcopy
from pathlib import Path

from ..planning.production_scenes import canonical_digest
from ..planning.scene_revision import plan_scene_revision,identity_from_options
from .manifest import thaw
from .production_state import ProductionRefused


def import_dependencies(domain,key,plan,existing):
    wanted=[]
    if domain!='common':wanted.append('common:all')
    if domain not in ('common','plan'):wanted.append('plan:all')
    if domain=='choice':wanted.append('image:'+key)
    if domain=='image':
        scene=next((s for s in plan['scenes'] if s['scene_id']==key),None)
        if scene is None:raise ProductionRefused('unknown image dependency node')
        wanted.extend('choice:'+r['source_scene_id'] for r in scene['reference_bindings'])
        if scene['reference_bindings']:wanted.append('reference_settings:all')
    if domain=='image_group':wanted.extend('choice:'+s['scene_id'] for s in plan['scenes'])
    if domain=='clip':
        clip=next((c for c in plan['clips'] if c['clip_id']==key),None)
        if clip is None:raise ProductionRefused('unknown clip dependency node')
        wanted.append('choice:'+clip['scene_id'])
        if clip['parent_clip_id']:wanted.append('clip:'+clip['parent_clip_id'])
    if domain=='upscale':wanted.append('clip:'+key.split(':')[0])
    if any(i not in existing for i in wanted):raise ProductionRefused('reusable node lacks imported content ancestor')
    return list(dict.fromkeys(wanted))


def verify_invalidation(frozen,origin,proof,originals):
    from ._scene_revision_origins import require_origin_node,source_clip_record
    from ._scene_revision_reference import source_reference_context
    from .scene_revision_records import _json
    request=_json(proof['commit']['request']['path'],root=Path(frozen.options['scene_revision']['path']).parent)
    if canonical_digest(request)!=proof['invalidation']['request_sha256']:
        raise ProductionRefused('revision request differs from invalidation')
    plan_value=require_origin_node(origin,'plan','all');plan=plan_value['scene_plan']
    choices={s['key']:originals[iid] for iid,(s,_) in proof['imports'].items() if s['domain']=='choice'}
    if request['kind']=='reselect_images':
        for sid in request['scene_ids']:
            if sid not in choices:choices[sid]=require_origin_node(origin,'choice',sid)
    clips=[];frames=[]
    for budget in plan['clips']:
        cid=budget['clip_id'];value=originals.get('clip:'+cid)
        accepted=source_clip_record(origin,cid)['accepted'] if value is not None else None
        clips.append(dict(clip_id=cid,record=value,acceptance=accepted,status='accepted' if value is not None else 'pending'))
        for index in range(budget['retained_frames']):
            fid=cid+f':frame_{index+1:06d}';frame=originals.get('upscale:'+fid)
            frames.append(dict(frame_id=fid,record=frame,status='ready' if frame is not None else 'pending'))
    options=deepcopy(thaw(origin.options));reference=source_reference_context(origin)
    options['_scene_revision_planning']=dict(
        identity=identity_from_options(origin.options,reference_settings_sha256=reference['digest'] if reference else None),
        completed_image_ids=[s['key'] for s,_ in proof['imports'].values() if s['domain']=='image'],
        image_group_accepted='image_group:all' in proof['imports'],target_config=thaw(frozen.config.raw))
    snapshot=dict(source_options=options,bible=plan_value['bible'],scene_plan=plan,
        image_choices=[choices[s['scene_id']] for s in plan['scenes'] if s['scene_id'] in choices],
        clip_nodes=clips,upscale_nodes=frames,pending_effects=[])
    rebuilt=plan_scene_revision(snapshot,request,proof['commit']['target_identity'])
    if canonical_digest(rebuilt)!=canonical_digest(proof['invalidation']):
        raise ProductionRefused('revision invalidation differs from verified source/request/target')
