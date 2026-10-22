"""Held-lock exact retained-frame RealESRGAN production and original-task recovery."""
from copy import deepcopy
import os
from pathlib import Path
import sys
from uuid import uuid4
from .manifest import now
from .production_state import ProductionRefused,RunLock,run_path
from .scene_media_records import SceneMediaResult,scene_media_context
from .scene_clip_records import equal
from .production_scene_clips import _GuardedLogger,_OwnedService,_error
from ._scene_upscale_records import (clip_rows,extraction_recipe,validate_extraction,validate_upscale_frames,
    validate_frame,validate_png_receipt,validate_png,graph_for,expected_request,complete_value)
from ..planning.production_scenes import canonical_digest


def boundary(point):
    """Durable caller-thread interruption boundary."""


def _evidence(store,paths):
    return [store.artifact(p) for p in paths if Path(p).is_file() and Path(p).stat().st_size]


def _result(context,status,error=None):
    store=context['store'] if context else None; run=store.run_dir if store else None
    return SceneMediaResult(run_id=run.name if run else None,run_dir=run,status=status,active_stage='upscale',
        upscaled_clips=store.root/'complete.json' if status=='upscale_ready' else None,
        log_dir=run/'logs/production' if run else None,error=error)


def _extract(context,clip,logger):
    from ..media.scene_upscale import extract_scene_frames
    store=context['store']; old=validate_extraction(context,clip,promote=True)
    if old is not None: return old
    folder=store.clip_dir(clip['clip_id']); stage=folder/('extraction-'+uuid4().hex); target=folder/'input-frames'
    p=context['frozen'].config.media.profile; store.verify_global()
    images,evidence=extract_scene_frames(clip['source']['path'],stage,expected_frames=clip['budget']['retained_frames'],
        width=p.width,height=p.height,config=context['frozen'].config,paths=store.paths,logger=logger,unit_id=clip['clip_id'])
    store.verify_global(); stage_frames=[]; target_frames=[]
    for row,image in zip(clip_rows(context,clip['clip_id']),images):
        indexed={k:row[k] for k in ('retained_frame_index','generated_frame_index','output_frame_index')}
        stage_frames.append(dict(**indexed,image=image))
        target_frames.append(dict(**indexed,image=dict(image,path=str(target/Path(image['path']).name))))
    store.write(folder/'extraction-ready.json',dict(schema_version=2,run_id=store.run_dir.name,clip_id=clip['clip_id'],
        source=clip['source'],staging_directory=str(stage),target_directory=str(target),staging_frames=stage_frames,
        target_frames=target_frames,recipe=extraction_recipe(context,clip),evidence=_evidence(store,evidence),created_at=now()))
    boundary('extraction-ready')
    value=validate_extraction(context,clip,promote=True); boundary('extraction'); return value


def _copy(context,row,operation,source):
    store=context['store']; old=validate_png_receipt(context,row,operation,source=source,promote=True)
    if old is not None: return old
    folder=store.frame_dir(row['frame_id']); stage=folder/'staging'/(operation+'-'+uuid4().hex+'.png')
    target=store.run_dir/'comfy/input'/store.run_dir.name/'scene_upscale'/row['clip_id']/f'frame_{row["retained_frame_index"]+1:06d}.png' if operation=='input_copy' else folder/'output.png'
    if target.exists(): raise ProductionRefused('unregistered PNG target already exists')
    store.verify_global(); store.validate_artifact(source)
    stage.parent.mkdir(parents=True,exist_ok=True)
    with Path(source['path']).open('rb') as src,stage.open('xb') as dst:
        while chunk:=src.read(1024*1024): dst.write(chunk)
        dst.flush(); os.fsync(dst.fileno())
    store.verify_global(); store.validate_artifact(source); artifact=store.artifact(stage)
    equal({k:artifact[k] for k in ('bytes','sha256')},{k:source[k] for k in ('bytes','sha256')},'copied PNG bytes')
    p=context['frozen'].config.media.profile
    validate_png(store,artifact,width=p.width if operation=='input_copy' else 1920,height=p.height if operation=='input_copy' else 1080)
    value=dict(schema_version=2,run_id=store.run_dir.name,frame_id=row['frame_id'],operation=operation,source=source,
        staging=artifact,target=dict(artifact,path=str(target)),recipe=dict(algorithm='identity_png_copy_v1',parameters={}),evidence=[],created_at=now())
    store.write(folder/'media-ready'/(operation+'.json'),value); boundary(operation+'-ready')
    result=validate_png_receipt(context,row,operation,source=source,promote=True); boundary(operation); return result


def _produce(context,logger,client_factory,service_factory):
    from ..adapters.scene_comfy import SceneComfyClient
    from .scene_upscale_transactions import recover_or_submit_scene_frame,SceneSubmitUnknown,SceneFrameTerminal
    from .production_inputs import check_stage_space
    from ..media.scene_upscale import InvalidScenePng
    store=context['store']; store.assert_write(); logger=_GuardedLogger(logger,store.assert_write)
    check_stage_space(context['frozen'].config,frames=len(context['rows']))
    # Full batch read-only scan precedes even local extraction or any service start.
    for row in context['rows']: graph_for(context,row)
    validate_upscale_frames(context,promote=True)
    store.write('inputs.json',context['inputs']); boundary('inputs')
    if store.read('complete.json') is not None:
        equal(store.read('complete.json'),complete_value(context,validate_upscale_frames(context)),'complete replay')
        return _result(context,'upscale_ready')
    service=None
    def ensure():
        nonlocal service
        store.verify_global()
        if service is None: service=(service_factory or _OwnedService)(context['frozen'],store.paths,logger,store.lock)
        service.ensure(); store.verify_global()
    try:
        for clip in context['scene_clips']['clips']:
            from ._scene_revision_readers import inherited_frame
            needed = [r for r in clip_rows(context,clip['clip_id']) if inherited_frame(context,r) is None]
            if not needed: continue
            extraction=_extract(context,clip,logger)
            for row in clip_rows(context,clip['clip_id']):
                old=validate_frame(context,row,extraction,promote=True)
                if old is not None: continue
                image=extraction['frames'][row['retained_frame_index']]['image']
                copy=_copy(context,row,'input_copy',image); graph=graph_for(context,row)
                request=expected_request(context,row,image,copy['target']); folder=store.frame_dir(row['frame_id'])
                store.write(folder/'request.json',request); store.write(folder/'graph.json',graph); boundary('request')
                client=(client_factory or SceneComfyClient)(context['frozen'].config.services['comfyui'],
                    request_timeout=context['frozen'].config.timeouts['comfy_request'],ownership_check=store.capture_guard(request,graph))
                submission=recover_or_submit_scene_frame(store,request,graph,client=client,template=context['template'],
                    ensure_service=ensure,logger=logger,timeout=context['frozen'].config.timeouts['upscale_frame'])
                try: validate_png(store,submission['output'],width=1920,height=1080)
                except InvalidScenePng as exc:
                    # Only definitive media validation is terminal; missing tools/OSError remains recoverable.
                    intent=store.read(folder/'intent.json')
                    terminal=dict(schema_version=2,run_id=store.run_dir.name,frame_id=row['frame_id'],
                        intent_sha256=canonical_digest(intent),status='invalid_media',evidence=[submission['output']],reason=str(exc))
                    store.write(folder/'terminal.json',terminal)
                    raise SceneFrameTerminal(terminal) from exc
                _copy(context,row,'output',submission['output'])
                validate_frame(context,row,extraction,promote=True); boundary('frame')
        frames=validate_upscale_frames(context); store.verify_global()
        store.write('complete.json',complete_value(context,frames)); boundary('complete')
        return _result(context,'upscale_ready')
    finally:
        original=sys.exception()
        if service is not None:
            try: service.close()
            except Exception as cleanup:
                if original is not None: original.add_note('service cleanup failed: '+str(cleanup))
                else: raise


from .scene_revision_records import revision_validation


@revision_validation
def produce_scene_upscaled_clips(frozen,units,timeline,*,paths,logger,client_factory=None,service_factory=None,lock=None):
    from .image_selection_records import _run
    from .scene_upscale_transactions import SceneSubmitUnknown,SceneFrameTerminal
    run=None; acquired=None; context=None; result=None
    try:
        prepared=Path(frozen.options['script_path']).parent.parent
        if not prepared.is_dir() or not run_path(prepared,prepared/'production/options.json').is_file():
            raise ProductionRefused('unknown prepared scene media run')
        try: candidate=_run(frozen)
        except (OSError,ValueError) as exc: raise ProductionRefused('unprepared scene media run: '+str(exc)) from exc
        if not candidate.is_dir() or not (candidate/'production/options.json').is_file(): raise ProductionRefused('unknown prepared scene media run')
        if logger.run_dir!=candidate or not logger.production: raise ProductionRefused('scene media requires matching production logger')
        run=candidate
        if lock is None: acquired=RunLock(run); acquired.__enter__(); lock=acquired
        context=scene_media_context(frozen,units,timeline,paths=paths,lock=lock)
        context['store'].assert_owned()
        result=_produce(context,logger,client_factory,service_factory)
    except KeyboardInterrupt as exc: result=_result(context,'interrupted',_error(exc))
    except (ProductionRefused,SceneSubmitUnknown) as exc:
        status='blocked'; evidence=[]
        if isinstance(exc,SceneFrameTerminal):
            terminal=exc.terminal
            status='blocked' if terminal['status']=='identity_conflict' else 'failed'
            evidence=[v['path'] for v in terminal['evidence']]
        result=_result(context,status,_error(exc,evidence))
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,AttributeError) as exc: result=_result(context,'failed',_error(exc))
    finally:
        if acquired is not None:
            try: acquired.__exit__(None,None,None)
            except Exception as exc:
                error=_error(exc)
                if result and result.error: error['message']=result.error['message']+'; cleanup: '+error['message']
                result=_result(context,'failed',error)
    return result
