"""Read-only exact extraction, PNG preparation and technical frame reconstruction."""
from copy import deepcopy
import os
from pathlib import Path
import re
from .production_state import ProductionRefused,object_fields,timestamp,run_path
from .scene_clip_records import equal,_decode_video
from ..planning.production_scenes import canonical_digest
from ..media.scene_upscale import verify_scene_frame_pixels,verify_png
from ..jimeng_config import STRATEGY


def clip_rows(context,clip_id): return [r for r in context['rows'] if r['clip_id']==clip_id]


def mapping(row): return {k:deepcopy(v) for k,v in row.items() if k!='source'}


def extraction_recipe(context,clip):
    p=context['frozen'].config.media.profile
    return dict(algorithm='scene_retained_rgb24_v1',parameters=dict(expected_frames=clip['budget']['retained_frames'],
        width=p.width,height=p.height,filter='format=rgb24',start_number=1,fps_mode='passthrough'))


def validate_extraction(context,clip,*,promote=False,media=True):
    if not media and promote:raise ProductionRefused('declared extraction cannot be promoted')
    store=context['store']; folder=store.clip_dir(clip['clip_id']); ready=store.read(folder/'extraction-ready.json')
    value=store.read(folder/'extraction.json')
    if ready is None:
        if value is not None or (folder/'input-frames').exists(): raise ProductionRefused('extraction lacks preparation proof')
        return None
    object_fields(ready,'schema_version run_id clip_id source staging_directory target_directory staging_frames target_frames recipe evidence created_at'.split(),'extraction ready')
    timestamp(ready['created_at']); rows=clip_rows(context,clip['clip_id']); recipe=extraction_recipe(context,clip)
    equal({k:ready[k] for k in ('schema_version','run_id','clip_id','source','recipe')},
        dict(schema_version=2,run_id=store.run_dir.name,clip_id=clip['clip_id'],source=clip['source'],recipe=recipe),'extraction identity')
    from ._scene_revision_origin_clips import declared_artifact
    check=store.validate_artifact if media else lambda value:declared_artifact(store,value)
    check(clip['source'])
    stage=run_path(store.run_dir,ready['staging_directory']); target=run_path(store.run_dir,ready['target_directory'])
    if target!=folder/'input-frames' or stage.parent!=folder or not stage.name.startswith('extraction-'):
        raise ProductionRefused('extraction directory ownership differs')
    if len(ready['staging_frames'])!=len(rows) or len(ready['target_frames'])!=len(rows): raise ProductionRefused('extraction count differs')
    def frames(directory,actual):
        expected=[]
        for row,item in zip(rows,actual):
            object_fields(item,'retained_frame_index generated_frame_index output_frame_index image'.split(),'extraction frame')
            image=dict(item['image'],path=str(directory/f'frame_{row["retained_frame_index"]+1:06d}.png'))
            expected.append(dict(**{k:row[k] for k in ('retained_frame_index','generated_frame_index','output_frame_index')},image=image))
        equal(actual,expected,'extraction indexed sequence')
        return expected
    frames(stage,ready['staging_frames']); frames(target,ready['target_frames'])
    for a,b in zip(ready['staging_frames'],ready['target_frames']):
        equal({k:a['image'][k] for k in ('bytes','sha256')},{k:b['image'][k] for k in ('bytes','sha256')},'extraction staging bytes')
    for directory,items in ((stage,ready['staging_frames']),(target,ready['target_frames'])):
        if media and directory.exists():
            if {str(p) for p in directory.iterdir()}!={r['image']['path'] for r in items}: raise ProductionRefused('extraction extra or missing file')
            for row in items: store.validate_artifact(row['image'])
    if media and not stage.exists() and not target.exists(): raise ProductionRefused('prepared extraction bytes missing')
    if media and not target.exists():
        if value is not None: raise ProductionRefused('committed extraction target missing')
        if promote:
            store.verify_global(); os.rename(stage,target); store.assert_owned()
    p=context['frozen'].config.media.profile
    if media:_decode_video(store,clip['source'],frames=len(rows),width=p.width,height=p.height)
    active=ready['target_frames'] if target.exists() else ready['staging_frames']
    key=('scene-native',canonical_digest(clip['source']),canonical_digest(active))
    if media and key not in store.media_cache:
        verify_scene_frame_pixels(clip['source']['path'],[r['image']['path'] for r in active],
            expected_frames=len(rows),width=p.width,height=p.height,config=context['frozen'].config)
        store.media_cache.add(key)
    for artifact in ready['evidence']: store.validate_artifact(artifact)
    expected=dict(schema_version=2,run_id=store.run_dir.name,clip_id=clip['clip_id'],source=clip['source'],
        frames=ready['target_frames'],recipe=recipe,evidence=ready['evidence'],created_at=ready['created_at'])
    if value is not None: equal(value,expected,'extraction final')
    elif promote: store.write(folder/'extraction.json',expected)
    else: return None  # Valid prepared prefix, not an accepted extraction gate.
    return expected


def graph_for(context,row):
    path=context['store'].run_dir.name+'/scene_upscale/'+row['clip_id']+f'/frame_{row["retained_frame_index"]+1:06d}.png'
    prefix=context['store'].run_dir.name+'/scene_upscale/'+row['clip_id']+f'/frame_{row["retained_frame_index"]+1:06d}/attempt_0001'
    return context['template'].instantiate(dict(image=path),output_prefix=prefix)


def expected_request(context,row,input_image,input_copy):
    clip=next(c for c in context['scene_clips']['clips'] if c['clip_id']==row['clip_id'])
    return dict(schema_version=2,production_strategy=STRATEGY,run_id=context['store'].run_dir.name,
        **{k:row[k] for k in ('frame_id','clip_id','scene_id')},inputs_sha256=canonical_digest(context['inputs']),
        clip_sha256=clip['clip_sha256'],observation_acceptance_sha256=clip['observation_acceptance_sha256'],
        mapping=mapping(row),source=row['source'],input=input_image,input_copy=input_copy,
        parameters=deepcopy(context['inputs']['parameters']),graph_sha256=canonical_digest(graph_for(context,row)))


def validate_png(store,artifact,*,width,height):
    store.verify_tools()
    path=store.validate_artifact(artifact); key=('png',canonical_digest(artifact),width,height)
    if key not in store.media_cache:
        verify_png(path,width=width,height=height,config=store.frozen.config)
        store.validate_artifact(artifact); store.media_cache.add(key)
    store.verify_tools()


def validate_png_receipt(context,row,operation,*,source=None,promote=False,media=True):
    if not media and promote:raise ProductionRefused('declared PNG cannot be promoted')
    store=context['store']; folder=store.frame_dir(row['frame_id']); value=store.read(folder/'media-ready'/(operation+'.json'))
    if value is None: return None
    object_fields(value,'schema_version run_id frame_id operation source staging target recipe evidence created_at'.split(),'PNG media ready')
    timestamp(value['created_at'])
    equal({k:value[k] for k in ('schema_version','run_id','frame_id','operation','recipe')},dict(schema_version=2,
        run_id=store.run_dir.name,frame_id=row['frame_id'],operation=operation,
        recipe=dict(algorithm='identity_png_copy_v1',parameters={})),'PNG copy recipe')
    if operation not in ('input_copy','output'): raise ProductionRefused('unknown PNG operation')
    if source is not None: equal(value['source'],source,'PNG source')
    from ._scene_revision_origin_clips import declared_artifact
    check=store.validate_artifact if media else lambda value:declared_artifact(store,value)
    check(value['source'])
    stage=run_path(store.run_dir,value['staging']['path']); target=run_path(store.run_dir,value['target']['path'])
    expected=store.run_dir/'comfy/input'/store.run_dir.name/'scene_upscale'/row['clip_id']/f'frame_{row["retained_frame_index"]+1:06d}.png' if operation=='input_copy' else folder/'output.png'
    if target!=expected or stage.parent!=folder/'staging': raise ProductionRefused('PNG copy target/staging differs')
    for artifact in (value['staging'],value['target']):
        if not media:check(artifact)
        equal({k:artifact[k] for k in ('bytes','sha256')},{k:value['source'][k] for k in ('bytes','sha256')},'identity PNG copy bytes')
    if media:
        if stage.exists():store.validate_artifact(value['staging'])
        if target.exists(): store.validate_artifact(value['target'])
        elif promote and stage.exists():
            store.verify_global(); target.parent.mkdir(parents=True,exist_ok=True); os.rename(stage,target); store.assert_owned()
        elif not stage.exists(): raise ProductionRefused('prepared PNG promotion missing')
    for artifact in value['evidence']: store.validate_artifact(artifact)
    p=context['frozen'].config.media.profile
    if media:validate_png(store,value['target'] if target.exists() else value['staging'],width=p.width if operation=='input_copy' else 1920,height=p.height if operation=='input_copy' else 1080)
    return value


def validate_frame(context,row,extraction,*,promote=False,media=True):
    if not media and promote:raise ProductionRefused('declared frame cannot be promoted')
    from ._scene_revision_readers import inherited_frame
    imported = inherited_frame(context,row)
    if imported is not None:return imported
    from .scene_upscale_transactions import validate_scene_frame_submission,_pending_scene_frame_output
    store=context['store']; folder=store.frame_dir(row['frame_id']); value=store.read(folder/'frame.json')
    request=store.read(folder/'request.json'); graph=graph_for(context,row)
    input_target=store.run_dir/'comfy/input'/store.run_dir.name/'scene_upscale'/row['clip_id']/f'frame_{row["retained_frame_index"]+1:06d}.png'
    store._lexical(input_target)
    if input_target.exists() and store.read(folder/'media-ready/input_copy.json') is None:
        raise ProductionRefused('unregistered input PNG copy exists')
    if (folder/'output.png').exists() and store.read(folder/'media-ready/output.json') is None:
        raise ProductionRefused('unregistered output PNG exists')
    if request is None:
        if value is not None or any((folder/name).exists() for name in ('graph.json','intent.json','submission.json','accepted.json','terminal.json','output.png')) or list((folder/'http').glob('*')):
            raise ProductionRefused('frame evidence lacks request')
        if extraction is not None:
            image=extraction['frames'][row['retained_frame_index']]['image']
            copy=validate_png_receipt(context,row,'input_copy',source=image,promote=promote)
            target=store.run_dir/'comfy/input'/store.run_dir.name/'scene_upscale'/row['clip_id']/f'frame_{row["retained_frame_index"]+1:06d}.png'
            if copy is None and target.exists(): raise ProductionRefused('unregistered input PNG copy exists')
        elif (folder/'media-ready').exists(): raise ProductionRefused('frame copy lacks extraction')
        if (folder/'media-ready/output.json').exists(): raise ProductionRefused('output preparation lacks request/submission')
        return None
    if extraction is None: raise ProductionRefused('frame request lacks extraction')
    image=extraction['frames'][row['retained_frame_index']]['image']
    copy=validate_png_receipt(context,row,'input_copy',source=image,promote=promote,media=media)
    if copy is None: raise ProductionRefused('request lacks PNG copy preparation')
    if media and not Path(copy['target']['path']).exists():
        if value is not None: raise ProductionRefused('technical frame input copy missing')
        return None
    equal(request,expected_request(context,row,image,copy['target']),'frame request')
    equal(store.read(folder/'graph.json'),graph,'frame graph')
    submission=validate_scene_frame_submission(store,request,graph,template=context['template'],media=media)
    if submission is None:
        owned=_pending_scene_frame_output(store,request,graph,template=context['template'])
        if owned is not None: validate_png(store,owned,width=1920,height=1080)
        if value is not None or (folder/'output.png').exists() or (folder/'media-ready/output.json').exists(): raise ProductionRefused('technical frame/output lacks submission')
        return None
    # Batch preflight must reject a known bad later model result before any
    # earlier new POST, including the prefix preceding output preparation.
    if media:validate_png(store,submission['output'],width=1920,height=1080)
    output=validate_png_receipt(context,row,'output',source=submission['output'],promote=promote,media=media)
    if output is None:
        if value is not None: raise ProductionRefused('technical frame lacks output preparation')
        return None
    if media and not Path(output['target']['path']).exists():
        if value is not None: raise ProductionRefused('technical frame output missing')
        return None
    expected=dict(schema_version=2,production_strategy=STRATEGY,run_id=store.run_dir.name,frame_id=row['frame_id'],
        request_sha256=canonical_digest(request),submission_sha256=canonical_digest(submission),mapping=mapping(row),
        input=image,input_copy=copy['target'],model_output=submission['output'],output=output['target'],
        evidence=output['evidence'],created_at=output['created_at'])
    if value is not None: equal(value,expected,'technical frame')
    elif promote: store.write(folder/'frame.json',expected)
    else: return None  # Accepted output preparation may precede its outer frame commit.
    return expected


def validate_upscale_frames(context,*,promote=False,terminal_errors=None):
    results=[]; store=context['store']
    store.verify_tools()
    if store.root.exists():
        allowed={'inputs.json','complete.json',*(c['clip_id'] for c in context['scene_clips']['clips'])}
        if any(p.name not in allowed and not _store_temporary(store,p) for p in store.root.iterdir()): raise ProductionRefused('unknown upscale root evidence')
    for clip in context['scene_clips']['clips']:
        folder=store.clip_dir(clip['clip_id'])
        known={f'frame_{r["retained_frame_index"]+1:06d}' for r in clip_rows(context,clip['clip_id'])}
        if folder.exists():
            for path in folder.iterdir():
                if path.name not in known|{'extraction.json','extraction-ready.json','input-frames'} and not path.name.startswith('extraction-') and not _store_temporary(store,path):
                    raise ProductionRefused('unknown upscale clip evidence')
        for name in known:
            frame_folder=folder/name
            if frame_folder.exists():
                allowed={'request.json','graph.json','intent.json','accepted.json','submission.json','terminal.json','frame.json','output.png','staging','media-ready','http'}
                if any(p.name not in allowed and not _store_temporary(store,p) for p in frame_folder.iterdir()): raise ProductionRefused('unknown frame transaction evidence')
                ready=frame_folder/'media-ready'
                if ready.exists() and any(p.name not in ('input_copy.json','output.json') and not _store_temporary(store,p) for p in ready.iterdir()):
                    raise ProductionRefused('unknown PNG preparation evidence')
    for clip in context['scene_clips']['clips']:
        extraction=validate_extraction(context,clip,promote=promote)
        for row in clip_rows(context,clip['clip_id']):
            folder=store.frame_dir(row['frame_id'])
            if terminal_errors is not None and store.read(folder/'terminal.json') is not None:
                from .scene_upscale_transactions import validate_scene_terminal
                request=store.read(folder/'request.json')
                if request is None: raise ProductionRefused('terminal lacks original frame request')
                terminal=validate_scene_terminal(store,request,graph_for(context,row))
                terminal_errors.append(terminal)
                continue
            from .scene_upscale_transactions import SceneFrameTerminal
            try: frame=validate_frame(context,row,extraction,promote=promote)
            except SceneFrameTerminal as exc:
                if terminal_errors is None: raise
                terminal_errors.append(exc.terminal)
                continue
            if frame is not None: results.append(frame)
    store.verify_tools()
    return results


def _store_temporary(store,path):
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.json\.[0-9a-f]{32}\.tmp',path.name): return False
    store.path(path)
    if not path.is_file(): raise ProductionRefused('atomic JSON temporary must be regular file')
    return True


def complete_value(context,frames):
    if len(frames)!=len(context['rows']): raise ProductionRefused('all retained upscale frames required')
    return dict(schema_version=2,production_strategy=STRATEGY,run_id=context['store'].run_dir.name,
        inputs_sha256=canonical_digest(context['inputs']),scene_clips_sha256=canonical_digest(context['scene_clips']),
        timeline_sha256=canonical_digest(context['timeline'].as_dict()),total_frames=len(frames),width=1920,height=1080,fps=16,frames=frames)


def require_upscale_record(context):
    store=context['store']
    store.verify_tools()
    if store.read('inputs.json') is None: raise ProductionRefused('upscale inputs missing')
    value=store.read('complete.json')
    if value is None: raise ProductionRefused('upscale complete acceptance missing')
    equal(value,complete_value(context,validate_upscale_frames(context)),'upscale complete')
    store.verify_tools()
    return value
