"""Advance original scene stages once, stopping at every explicit review gate."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from ..config import read_json
from ..planning.production_scenes import canonical_digest
from .manifest import now
from .production_state import ProductionRefused,object_fields
from .scene_pipeline_records import (ScenePipelineResult,common_inputs,record_common,pipeline_inputs,
    validate_common_record,error,run_of,load_scene_pipeline_progress)
from .scene_revision_records import revision_validation,artifact,stable_bytes,require_scene_revision
from ._scene_revision_copy import RevisionStore

DEPENDENCIES = ('planner image_client_factory reference_storage reference_client_factory smtp_factory '
                'wan_client_factory wan_service_factory upscale_client_factory upscale_service_factory').split()


def boundary(point):
    """Durable caller-thread coordination boundary for fault injection."""


def _dependencies(value):
    if value is None:return SimpleNamespace(**dict.fromkeys(DEPENDENCIES))
    fields = value if isinstance(value,dict) else vars(value)
    if set(fields)-set(DEPENDENCIES):raise ProductionRefused('unknown scene dependency injection field')
    return SimpleNamespace(**{name:fields.get(name) for name in DEPENDENCIES})


def _common(frozen,*,paths,logger,lock):
    run=run_of(frozen)
    proof=require_scene_revision(frozen) if 'scene_revision' in frozen.options else None
    inherited=proof is not None and 'common:all' in proof['imports']
    automatic=(run/'production/production-state.json').exists()
    if proof is not None and 'all' in proof['invalidation']['dirty']['common']:
        from .production_state import ProductionStateStore
        from .manifest import create_manifest
        if not automatic:
            if any((run/f'production/{s}.json').exists() for s in ('units','speech','timeline','scene-plan')):
                raise ProductionRefused('new automatic revision has an unowned partial common prefix')
            RevisionStore(run,lock).owned();ProductionStateStore.create(run);automatic=True
        if not (run/'manifest.json').exists():
            state=ProductionStateStore.open(run).snapshot()
            if any(s['status']!='pending' for s in state['stages'].values()):
                raise ProductionRefused('automatic revision manifest missing after work began')
            RevisionStore(run,lock).owned()
            create_manifest(run,frozen.config,inputs=frozen.options['execution_policy']['input_identities'],models={},workflows={},verify_integrity=False)
    if not inherited and automatic:
        from .production_state import ProductionStateStore
        from .manifest import ManifestStore
        from ..production import _finish_prefix
        from .production_storyboard import produce_units
        from .production_speech import produce_speech
        from .production_timeline import produce_timeline
        state=ProductionStateStore.open(run);state._run_lock_owner=dict(lock.owner)
        manifest=ManifestStore.open(run,verify_integrity=False)
        def step(stage,operation,*args,**kwargs):
            try:return operation(*args,**kwargs)
            except (Exception,KeyboardInterrupt) as exc:
                exc._scene_pipeline_stage=stage
                raise
        step('preflight',_finish_prefix,frozen,state,manifest)
        units=step('units',produce_units,frozen,state=state,manifest=manifest,paths=paths,logger=logger)
        audio=step('speech',produce_speech,frozen,units,state=state,manifest=manifest,paths=paths,logger=logger)
        timeline,_=step('timeline',produce_timeline,frozen,units,audio,state=state,manifest=manifest,paths=paths,logger=logger)
        mode='automatic'
    else:
        units,timeline,mode=common_inputs(frozen)
    inputs=record_common(frozen,units,timeline,mode,lock=lock)
    return units,timeline,inputs


def _preflight_later(frozen,units,timeline):
    """Any extant later proof is checked before a new earlier external effect."""
    run=run_of(frozen)
    media_exists=any((run/('production/'+name)).exists() for name in ('scene-upscale','scene-composition','scene-delivery'))
    if media_exists:
        from .scene_completed import validate_scene_completed_prefix,load_validated_prefix_details
        from .scene_media_records import SceneMediaResult
        progress=validate_scene_completed_prefix(frozen,units,timeline)
        waiting=_continuity_wait(frozen,units,timeline)
        if waiting is not None:return waiting
        if progress['composition']['status']=='ready':
            details=load_validated_prefix_details(frozen);candidate=details['candidate']
            template=run/'production/scene-composition/final-observation-template.json'
            if not template.is_file():return None  # Only the original writer may restore this marker.
            final=progress['final_review'];status={'ready':'final_review_ready','final_review_failed':'final_review_failed'}.get(final['status'],'awaiting_final_review')
            return SceneMediaResult(run_id=run.name,run_dir=run,status=status,active_stage='composition',
                upscaled_clips=Path(progress['upscale']['record']),candidate=Path(candidate['candidate']['path']),
                final_observation_template=template,log_dir=run/'logs/production',error=final['error'])
    elif (run/'production/scene-clips').exists():
        from .scene_clip_records import scene_context,collect_progress
        collect_progress(scene_context(frozen,units,timeline))


def _continuity_wait(frozen,units,timeline):
    from .scene_continuity_records import require_scene_continuity_acceptance,SceneContinuityPending
    try:require_scene_continuity_acceptance(frozen,units,timeline)
    except SceneContinuityPending as exc:
        from .production_scene_clips import _result,_error
        return _result(run_of(frozen),'awaiting_continuity_review',error=_error(exc))


def _restore_missing_aggregates(frozen,units,timeline,*,paths,logger,lock,deps):
    """Original writers may restore exact indexes after all their leaves pass."""
    run=run_of(frozen);stage='source_clips'
    media=any((run/('production/'+name)).exists() for name in ('scene-upscale','scene-composition','scene-delivery'))
    try:
        if media and not (run/'production/scene-clips/complete.json').exists():
            from .scene_clip_records import scene_context,collect_progress,complete_value
            context=scene_context(frozen,units,timeline,paths=paths,lock=lock)
            _,records=collect_progress(context);expected=complete_value(context,records)
            later=run/'production/scene-upscale/inputs.json'
            if later.is_file() and read_json(later)['scene_clips_sha256']!=canonical_digest(expected):
                raise ProductionRefused('later upscale disagrees with missing source aggregate')
            waiting=_continuity_wait(frozen,units,timeline)
            if waiting is not None:return waiting
            from .production_scene_clips import produce_scene_clips
            result=produce_scene_clips(frozen,units,timeline,paths=paths,logger=logger,lock=lock,
                client_factory=deps.wan_client_factory,service_factory=deps.wan_service_factory)
            if result.status!='source_clips_ready':return result
        stage='upscale'
        if (run/'production/scene-composition').exists() and not (run/'production/scene-upscale/complete.json').exists():
            from .scene_media_records import _scene_media_base_context
            from ._scene_upscale_records import validate_upscale_frames,complete_value
            context=_scene_media_base_context(frozen,units,timeline,paths=paths,lock=lock)
            expected=complete_value(context,validate_upscale_frames(context))
            later=run/'production/scene-composition/inputs.json'
            if later.is_file() and read_json(later)['upscale_sha256']!=canonical_digest(expected):
                raise ProductionRefused('later composition disagrees with missing upscale aggregate')
            waiting=_continuity_wait(frozen,units,timeline)
            if waiting is not None:return waiting
            from .production_scene_upscale import produce_scene_upscaled_clips
            result=produce_scene_upscaled_clips(frozen,units,timeline,paths=paths,logger=logger,lock=lock,
                client_factory=deps.upscale_client_factory,service_factory=deps.upscale_service_factory)
            if result.status!='upscale_ready':return result
    except (Exception,KeyboardInterrupt) as exc:
        exc._scene_pipeline_stage=stage
        raise


@revision_validation
def produce_scene_pipeline(frozen,*,paths,logger,lock,reference_settings_path=None,email_settings=None,dependencies=None):
    deps=_dependencies(dependencies);run=run_of(frozen);stage='preflight'
    store=RevisionStore(run,lock);store.owned()
    try:
        units,timeline,inputs=_common(frozen,paths=paths,logger=logger,lock=lock)
        stage='scene_plan'
        from .image_selection_records import load_committed_plan,load_accepted_batches,_candidates,require_complete_image_acceptance
        from .production_scene_plan import produce_scene_plan
        if not (run/'production/scene-plan-commit.json').exists() and not ('scene_revision' in frozen.options and 'plan:all' in require_scene_revision(frozen)['imports']):
            produce_scene_plan(frozen,units,timeline,paths=paths,logger=logger,lock=lock,planner=deps.planner)
        bible,plan=load_committed_plan(frozen,units,timeline)
        if frozen.config.raw.get('scene_rendering',{}).get('mode') is not None:
            from .scene_execution_records import ensure_scene_execution
            # Validate the complete scene batch before image or video requests;
            # revisions without common imports reach this after regeneration.
            ensure_scene_execution(frozen,plan,timeline,lock=lock)
        recovered=_restore_missing_aggregates(frozen,units,timeline,paths=paths,logger=logger,lock=lock,deps=deps)
        if recovered is not None:return recovered
        prefix_result=_preflight_later(frozen,units,timeline)
        if prefix_result is not None:return prefix_result
        stage='start_images'
        from .production_image_selection import prepare_image_batch,ImageSelectionResult
        from .production_reference_images import produce_reference_batch
        from .jimeng_candidates import generate_candidates
        from ._scene_revision_origins import inherited
        accepted=load_accepted_batches(frozen,units,timeline,bible,plan)
        for index,ids in enumerate(plan['batches'],1):
            if any(b['batch_id']==f'image_batch_{index:04d}' for b in accepted):continue
            scenes=[s for s in plan['scenes'] if s['scene_id'] in ids]
            reference=[bool(s['reference_bindings']) for s in scenes]
            if any(reference) and not all(reference):raise ProductionRefused('mixed baseline/reference image batch')
            if all(reference):
                result=produce_reference_batch(frozen,units,timeline,batch_index=index,paths=paths,logger=logger,lock=lock,
                    reference_settings_path=reference_settings_path,storage=deps.reference_storage,
                    client_factory=deps.reference_client_factory,smtp_factory=deps.smtp_factory,email_settings=email_settings)
            else:
                manifests=[]
                for scene in scenes:
                    store.owned();sid=scene['scene_id']
                    if inherited(frozen,'image',sid) is not None:
                        _candidates(frozen,scene,run/'production/jimeng'/sid/'candidates.json')
                        manifests.append(run/'production/jimeng'/sid/'candidates.json');continue
                    client=deps.image_client_factory(frozen.config.image_generation) if deps.image_client_factory else None
                    value=generate_candidates(frozen,sid,scene['image_prompt'],client=client,lock=lock)
                    manifests.append(value if isinstance(value,(Path,str)) else run/'production/jimeng'/sid/'candidates.json')
                result=prepare_image_batch(frozen,units,timeline,manifests,batch_index=index,paths=paths,logger=logger,
                    lock=lock,email_settings=email_settings,smtp_factory=deps.smtp_factory)
            if result.status not in ('image_batch_accepted','images_ready'):return result
            boundary('image-accepted')
            accepted=load_accepted_batches(frozen,units,timeline,bible,plan)
        require_complete_image_acceptance(frozen,units,timeline)
        from .reference_image_records import build_reference_image_acceptance,require_reference_image_acceptance
        wan=run/'production/reference-images/wan-inputs.json'
        if not wan.exists():
            expected=build_reference_image_acceptance(frozen,units,timeline)
            store.owned();store.save(wan,expected)
        require_reference_image_acceptance(frozen,units,timeline);boundary('wan-inputs')
        stage='source_clips'
        from .production_scene_clips import produce_scene_clips
        from .scene_clip_records import require_scene_clip_acceptance
        result=produce_scene_clips(frozen,units,timeline,paths=paths,logger=logger,lock=lock,
            client_factory=deps.wan_client_factory,service_factory=deps.wan_service_factory)
        if result.status!='source_clips_ready':return result
        require_scene_clip_acceptance(frozen,units,timeline);boundary('clip-accepted')
        stage='upscale'
        from .production_scene_upscale import produce_scene_upscaled_clips
        result=produce_scene_upscaled_clips(frozen,units,timeline,paths=paths,logger=logger,lock=lock,
            client_factory=deps.upscale_client_factory,service_factory=deps.upscale_service_factory)
        if result.status!='upscale_ready':return result
        boundary('upscale-ready');stage='composition'
        from .production_scene_composition import produce_scene_composition
        result=produce_scene_composition(frozen,units,timeline,paths=paths,logger=logger,lock=lock)
        if result.status in ('awaiting_final_review','final_review_ready','final_review_failed'):boundary('candidate-ready')
        return result
    except (Exception,KeyboardInterrupt) as exc:
        stage=getattr(exc,'_scene_pipeline_stage',stage)
        status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'blocked' if isinstance(exc,ValueError) or 'Unknown' in type(exc).__name__ else 'failed'
        kwargs=dict(run_id=run.name,run_dir=run,status=status,log_dir=run/'logs/production',error=error(exc))
        if stage=='start_images':
            from .production_image_selection import ImageSelectionResult
            return ImageSelectionResult(**kwargs)
        if stage=='source_clips':
            from .production_scene_clips import SceneClipResult
            return SceneClipResult(**kwargs)
        if stage in ('upscale','composition'):
            from .scene_media_records import SceneMediaResult
            return SceneMediaResult(**kwargs,active_stage=stage)
        return ScenePipelineResult(**kwargs,active_stage=stage)


def record_invocation(frozen,action,result,submissions,*,lock):
    run=run_of(frozen);root=run/'production/scene-pipeline'
    store=RevisionStore(run,lock);store.owned()
    if 'scene_revision' in frozen.options:require_scene_revision(frozen)['guard'].verify_captured_bytes()
    inputs=read_json(root/'inputs.json') if (root/'inputs.json').exists() else None
    value=dict(schema_version=2,run_id=run.name,action=action,inputs_sha256=canonical_digest(inputs) if inputs else None,
        submissions=submissions,result=result.to_dict(),created_at=now())
    store.save(run/'logs/production/scene-invocations'/(str(uuid4())+'.json'),value)
    boundary('invocation-written')


def submit_file(frozen,path,*,lock):
    path=Path(path);raw=stable_bytes(path,root=path.parent)
    import hashlib
    digest=hashlib.sha256(raw).hexdigest()
    store=RevisionStore(run_of(frozen),lock)
    target=store.run/'production/scene-pipeline/submissions'/(digest+'.json')
    store.image(target,raw)
    return target,artifact(target,root=store.run)
