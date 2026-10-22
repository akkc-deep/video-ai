"""Immutable coordinator inputs/common prefix and strictly read-only diagnostics."""
from dataclasses import dataclass
from pathlib import Path

from ..adapters.jimeng import redact
from ..config import read_json
from ..jimeng_config import STRATEGY
from ..planning.production_scenes import canonical_digest
from .manifest import now,thaw,validate_run_dir
from .production_state import ProductionRefused,object_fields,run_path,timestamp
from .scene_revision_records import artifact,require_scene_revision,load_scene_common_prefix,revision_validation
from ._scene_revision_origins import owned_common
from ._scene_revision_copy import RevisionStore

INPUT_FIELDS = ('schema_version production_strategy run_id algorithm frozen_options_sha256 source_mode revision_commit_sha256').split()
COMMON_FIELDS = ('schema_version run_id inputs_sha256 source_mode units timeline speech pcm created_at').split()


@dataclass(frozen=True)
class ScenePipelineResult:
    schema_version:int=2
    production_strategy:str=STRATEGY
    run_id:str|None=None
    run_dir:Path|None=None
    status:str='blocked'
    active_stage:str='preflight'
    log_dir:Path|None=None
    error:dict|None=None

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version!=2 or self.production_strategy!=STRATEGY:
            raise ValueError('invalid pipeline result schema')
        if self.status not in ('blocked','failed','interrupted') or self.active_stage not in ('preflight','units','speech','timeline','scene_plan'):
            raise ValueError('invalid early pipeline state')
        if self.run_dir is None:
            if self.run_id is not None or self.log_dir is not None: raise ValueError('pipeline has no verified run')
        else:
            run=validate_run_dir(self.run_dir);object.__setattr__(self,'run_dir',run)
            if run.name!=self.run_id:raise ValueError('pipeline run identity differs')
            if self.log_dir is not None:run_path(run,self.log_dir)
        if self.error is not None:object_fields(self.error,('kind','message','evidence_paths'),'pipeline error')

    def to_dict(self):return thaw(self)

    @property
    def exit_code(self):return dict(blocked=2,failed=1,interrupted=130)[self.status]


def error(exc):
    return dict(kind=type(exc).__name__,message=redact('; '.join([str(exc) or type(exc).__name__,*getattr(exc,'__notes__',())])),evidence_paths=[])


def run_of(frozen):return Path(frozen.options['script_path']).parent.parent


def common_inputs(frozen):
    """Admit original reports/PCM or an explicitly frozen inherited prefix."""
    run=run_of(frozen)
    if 'scene_revision' in frozen.options:
        proof=require_scene_revision(frozen)
        if 'common:all' in proof['imports']:
            if any((run/f'production/{s}.json').exists() for s in ('units','timeline','speech')):
                raise ProductionRefused('owned common prefix competes with import')
            return (*load_scene_common_prefix(frozen),'inherited')
    value=owned_common(frozen)
    from ..planning.production_timeline import ProductionTimeline
    mode='automatic' if (run/'production/production-state.json').exists() else 'prepared'
    if mode=='prepared':
        from .image_selection_records import load_committed_plan
        load_committed_plan(frozen,value['units'],ProductionTimeline.from_dict(value['timeline']))
    return value['units'],ProductionTimeline.from_dict(value['timeline']),mode


def pipeline_inputs(frozen,mode):
    return dict(schema_version=2,production_strategy=STRATEGY,run_id=frozen.options['run_id'],algorithm='scene_pipeline_v1',
        frozen_options_sha256=canonical_digest(frozen.options),source_mode=mode,
        revision_commit_sha256=frozen.options.get('scene_revision',{}).get('sha256'))


def common_value(frozen,units,timeline,mode,inputs,*,created_at):
    run=run_of(frozen)
    if mode=='inherited':
        bound=require_scene_revision(frozen)['imports']['common:all'][0]['view_artifact']
        units_artifact=timeline_artifact=bound
    else:
        units_artifact=artifact(run/'production/units.json',root=run)
        timeline_artifact=artifact(run/'production/timeline.json',root=run)
    return dict(schema_version=2,run_id=run.name,inputs_sha256=canonical_digest(inputs),source_mode=mode,
        units=units_artifact,timeline=timeline_artifact,
        speech=artifact(run/'production/speech.json',root=run) if mode=='automatic' else None,
        pcm=[dict(unit_id=c.unit_id,audio=artifact(c.pcm.path,root=run),samples=c.samples) for c in timeline.clips],created_at=created_at)


def validate_common_record(frozen,units,timeline,mode):
    root=run_of(frozen)/'production/scene-pipeline'
    inputs=pipeline_inputs(frozen,mode)
    if (root/'inputs.json').exists():
        saved=read_json(root/'inputs.json');object_fields(saved,INPUT_FIELDS,'scene pipeline inputs')
        if type(saved['schema_version']) is not int or saved!=inputs:raise ProductionRefused('scene pipeline frozen inputs differ')
    if (root/'common-inputs-ready.json').exists():
        saved=read_json(root/'common-inputs-ready.json');object_fields(saved,COMMON_FIELDS,'scene common ready')
        if type(saved['schema_version']) is not int:raise ProductionRefused('scene common ready schema differs')
        timestamp(saved['created_at'])
        expected=common_value(frozen,units,timeline,mode,inputs,created_at=saved['created_at'])
        if saved!=expected:raise ProductionRefused('scene common bytes or PCM differ')
    return inputs


def record_common(frozen,units,timeline,mode,*,lock):
    inputs=validate_common_record(frozen,units,timeline,mode)
    run=run_of(frozen);store=RevisionStore(run,lock);root=run/'production/scene-pipeline'
    store.save(root/'inputs.json',inputs)
    from .production_scene_pipeline import boundary
    boundary('pipeline-inputs')
    old=read_json(root/'common-inputs-ready.json') if (root/'common-inputs-ready.json').exists() else None
    store.save(root/'common-inputs-ready.json',common_value(frozen,units,timeline,mode,inputs,created_at=old['created_at'] if old else now()))
    boundary('common-ready')
    return inputs


@revision_validation
def load_scene_pipeline_progress(frozen):
    from .image_selection_records import _run,load_committed_plan,load_accepted_batches
    run=_run(frozen);root=run/'production/scene-pipeline'
    result=dict(schema_version=2,production_strategy=STRATEGY,run_id=run.name,
        common=dict(status='pending',record=None,source_mode=None,error=None),plan=dict(status='pending',record=None,error=None),
        images=dict(status='pending',accepted_batch_ids=[],next_batch_id=None,selection_template=None,wan_inputs=None,error=None),clips=None,media=None)
    inherited='scene_revision' in frozen.options
    if not inherited and not any((run/f'production/{s}.json').exists() for s in ('units','timeline')):
        if (root/'inputs.json').exists():
            value=read_json(root/'inputs.json');object_fields(value,INPUT_FIELDS,'scene pipeline inputs')
            if value!=pipeline_inputs(frozen,value['source_mode']):raise ProductionRefused('pipeline inputs differ')
            result['common'].update(status='running',source_mode=value['source_mode'])
        return result
    try:
        units,timeline,mode=common_inputs(frozen)
        validate_common_record(frozen,units,timeline,mode)
        result['common'].update(status='ready',source_mode=mode,record=str(root/'common-inputs-ready.json') if (root/'common-inputs-ready.json').exists()
            else str(require_scene_revision(frozen)['imports']['common:all'][0]['view_artifact']['path']) if mode=='inherited' else str(run/'production/timeline.json'))
    except (ValueError,OSError,KeyError,TypeError) as exc:
        result['common'].update(status='blocked',error=error(exc));return result
    try:
        if not (run/'production/scene-plan-commit.json').exists() and not (inherited and 'plan:all' in require_scene_revision(frozen)['imports']):return result
        bible,plan=load_committed_plan(frozen,units,timeline)
        result['plan'].update(status='ready',record=str(run/'production/scene-plan-commit.json') if (run/'production/scene-plan-commit.json').exists()
            else require_scene_revision(frozen)['imports']['plan:all'][0]['view_artifact']['path'])
    except (ValueError,OSError,KeyError,TypeError) as exc:
        result['plan'].update(status='blocked',error=error(exc));return result
    try:
        accepted=load_accepted_batches(frozen,units,timeline,bible,plan)
        result['images']['accepted_batch_ids']=[b['batch_id'] for b in accepted]
        next_index=len(accepted)+1
        if next_index<=len(plan['batches']):
            batch=f'image_batch_{next_index:04d}';folder=run/'production/image-selection'/batch
            result['images']['next_batch_id']=batch
            if (folder/'selection-template.json').exists():
                result['images'].update(status='awaiting_image_selection',selection_template=str(folder/'selection-template.json'))
                if (folder/'batch.json').exists():
                    from .production_image_selection import notification_delivery_state
                    if notification_delivery_state(run,read_json(folder/'batch.json'))=='unknown':result['images']['status']='email_delivery_unknown'
            elif any(s['reference_bindings'] for s in plan['scenes'] if s['scene_id'] in plan['batches'][next_index-1]):
                if not (run/'production/reference-images/settings.json').exists() and not inherited:
                    result['images']['status']='awaiting_image_model_configuration'
        if (run/'production/reference-images/wan-inputs.json').exists():
            from .reference_image_records import require_reference_image_acceptance
            require_reference_image_acceptance(frozen,units,timeline)
            result['images'].update(status='images_ready',wan_inputs=str(run/'production/reference-images/wan-inputs.json'))
        elif next_index>len(plan['batches']):result['images']['status']='awaiting_image_selection'
    except (ValueError,OSError,KeyError,TypeError) as exc:
        result['images'].update(status='blocked',error=error(exc));return result
    if result['images']['status']=='images_ready' and (run/'production/scene-clips/inputs.json').exists():
        from .scene_clip_records import load_scene_clip_progress
        result['clips']=load_scene_clip_progress(frozen,units,timeline)
    if (run/'production/scene-clips/complete.json').exists():
        from .scene_media_records import load_scene_media_progress
        result['media']=load_scene_media_progress(frozen,units,timeline)
    return result
