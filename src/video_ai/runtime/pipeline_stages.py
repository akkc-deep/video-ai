"""Fixed stage registry. All generation and review remain in their runtime owners."""
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from ..config import read_json
from .manifest import STAGES, ManifestStore, hash_file, thaw
from .timeline_checks import _local, _fresh, _again


@dataclass(frozen=True)
class StageAdapter:
    name: str
    module: str | None
    producer: str | None
    consumer: str | None
    finalizer: str | None = None
    review_role: str | None = None
    draft: str | None = None


REGISTRY = (
    StageAdapter('preflight', None, None, None),
    StageAdapter('speech', 'speech_checks', 'synthesize_script', 'load_committed_speech'),
    StageAdapter('timeline', 'timeline_checks', 'plan_timeline', 'load_committed_timeline'),
    StageAdapter('storyboard', 'storyboard_checks', 'plan_storyboard', 'load_committed_storyboard', 'finalize_storyboard', 'storyboard', 'storyboard-draft.json'),
    StageAdapter('start_images', 'start_image_checks', 'prepare_start_images', 'load_committed_start_images', 'finalize_start_images', 'start_images', 'images-draft.json'),
    StageAdapter('source_clips', 'source_clip_checks', 'prepare_source_clips', 'load_committed_source_clips', 'finalize_source_clips', 'source_clips', 'source-clips-draft.json'),
    StageAdapter('upscale', 'upscale_checks', 'prepare_upscaled_clips', 'load_committed_upscaled_clips', 'finalize_upscaled_clips', 'upscale', 'upscaled-clips-draft.json'),
    StageAdapter('composition', 'composition_checks', 'compose_clips', 'load_committed_composition'),
    StageAdapter('validation', 'candidate_checks', 'validate_candidate', 'load_committed_candidate'),
    StageAdapter('publish', 'publication', 'publish_candidate', 'load_committed_publication'),
)
assert tuple(row.name for row in REGISTRY) == STAGES
BY_NAME = {row.name: row for row in REGISTRY}
REVIEW_PATHS = {
    'voice_acceptance': 'logs/pipeline/voice-acceptance.json',
    'timing': 'logs/storyboard/timing-review.json',
    'visual_contract': 'logs/storyboard/visual-contract.json',
    'storyboard': 'logs/storyboard/semantic-review.json',
    'start_images': 'logs/start-images/semantic-review.json',
    'source_clips': 'logs/source-clips/semantic-review.json',
    'upscale': 'logs/upscale/semantic-review.json',
    'final_review': 'logs/validation/final-review.json',
    'full_film_acceptance': 'logs/validation/full-film-acceptance.json',
}


def _module(name):
    return import_module('.'+BY_NAME[name].module, __package__)


def consume(name, config, run):
    if name == 'preflight':
        store = ManifestStore.open(run); stage = store.snapshot()['stages'][name]
        if stage['status'] != 'completed' or len(stage['artifacts']) != 1:
            raise ValueError('registered completed preflight required')
        identity = _fresh(stage['artifacts'][0], run=run)
        report = read_json(Path(identity.path))
        if report.get('passed') is not True:
            raise ValueError('preflight report is not passed')
        return report
    value = getattr(_module(name), BY_NAME[name].consumer)(run)
    if name == 'timeline':
        from .timeline_checks import _inputs
        from ..planning.timeline import build_timeline
        snapshot = ManifestStore.open(run).snapshot()
        script, audio, ids, accepted, listening = _inputs(config, run, snapshot)
        expected = build_timeline(script, audio, settings=config.media.timeline, fps=config.media.fps)
        if expected.as_dict() != value.as_dict():
            raise ValueError('timeline no longer matches config and PCM')
        _again(ids)
    return value


def prepare(name, config, run, *, options, reviews, store):
    spec = BY_NAME[name]
    kwargs = dict(run_dir=run)
    if name in ('source_clips','upscale'):
        from ._pipeline_model_paths import prepare_or_consume_model_binding
        prepare_or_consume_model_binding(config,run,'wan' if name=='source_clips' else 'upscale',create=True)
    if name in ('speech','start_images','source_clips','upscale') and 'pipeline_import' in store.snapshot()['workflows']:
        from .pipeline_import import load_pipeline_import,make_reuse_context,fresh
        receipt=load_pipeline_import(run)
        retry_speech=(name=='speech' and any(row['id']=='speech' and row['source_record']['status']!='completed'
            and bool(row['imported_record'].get('retry_failed_units')) for row in receipt['stages']))
        if any(row['imported_record'].get('stage')==name for row in receipt['units']) or retry_speech:
            if name=='speech':
                report=read_json(run/'segments.json')
                unit_ids=('reference_replay',)+tuple(s['unit_id'] for s in report['spans'] if s['kind']=='speech')
                identities={k:fresh(v) for k,v in store.snapshot()['inputs'].items()}
            elif name=='start_images':
                board,identities=_module(name)._input_files(config,run)
                unit_ids=tuple(s['shot_id'] for s in board['shots'])
            elif name=='source_clips':
                from ._source_clip_inputs import inputs
                context=inputs(config,run);identities=context['identities']
                unit_ids=tuple(p.shot_id for p in context['plans'])
            else:
                from ._upscale_inputs import inputs
                context=inputs(config,run);identities=context['identities']
                unit_ids=tuple(f'{p.shot_id}:frame_{i:06d}' for p in context['plans'] for i in range(1,p.source_frames+1))
            reuse=make_reuse_context(run,stage=name,unit_ids=unit_ids,current_input_identities=identities)
            facade={'speech':'resume_speech','start_images':'resume_start_images','source_clips':'resume_source_clips','upscale':'resume_upscale_generation'}[name]
            kwargs['reuse_context']=reuse
            if name=='speech':kwargs['store']=store
            return getattr(_module(name),facade)(config,**kwargs)
    if name == 'speech':
        kwargs.update(store=store, segmentation_path=options['unit_review_path'])
        return getattr(_module(name), spec.producer)(config, Path(options['script']), **kwargs)
    if name == 'storyboard':
        kwargs.update(timing_review_path=reviews['timing'], cpu_planner=options.get('cpu_planner', False))
    elif name == 'start_images':
        kwargs['image_inputs_path'] = options.get('image_inputs_path')
    elif name == 'composition':
        kwargs['settings_path'] = options.get('settings_path')
    elif name == 'upscale':
        kwargs['execution_policy'] = 'pipeline'
    elif name == 'publish':
        kwargs.update(review_path=reviews.get('final_review', run/REVIEW_PATHS['final_review']),
            acceptance_path=reviews.get('full_film_acceptance', run/REVIEW_PATHS['full_film_acceptance']),
            output_path=options.get('output_path'))
    return getattr(_module(name), spec.producer)(config, **kwargs)


def finalize(name, config, run, review_path):
    return getattr(_module(name), BY_NAME[name].finalizer)(config, run_dir=run, review_path=review_path)


def validate_checkpoint(name, config, run, snapshot):
    """A running report never counts as a checkpoint until its owner replays it."""
    spec = BY_NAME[name]
    if spec.draft is None:
        raise ValueError('stage has no review draft')
    path = _local(run, run/spec.draft)
    artifacts = [a for a in snapshot['stages'][name]['artifacts'] if Path(a['path']) == path]
    if len(artifacts) != 1:
        raise ValueError('running draft is not registered')
    identity = _fresh(artifacts[0], run=run, expected=path)
    draft = read_json(path)
    if name=='storyboard' and 'storyboard_revision' in snapshot['workflows']:
        from ._pipeline_storyboard_revision import validate_revision
        ids=validate_revision(config,run,draft)
    elif draft.get('schema_version') in (2, 3):
        from .pipeline_import import validate_pipeline_checkpoint
        ids = validate_pipeline_checkpoint(name, config, run, snapshot)['identities']
    elif name == 'storyboard':
        owner = _module(name)
        timeline, ids = owner._verified_inputs(config, run, snapshot)
        timing, more = owner._timing(run, Path(draft['timing_review_identity']['path']), timeline)
        ids.update(more)
        owner._validate_draft(config, run, draft, timeline, timing, ids)
    elif name == 'start_images':
        owner = _module(name)
        board, ids = owner._input_files(config, run)
        ids.update(owner._validate_draft(config, run, draft, board, snapshot))
    elif name == 'source_clips':
        from ._source_clip_inputs import inputs
        from ._source_clip_evidence import validate
        context = inputs(config, run)
        ids = dict(context['identities'], **validate(config, run, draft, context, snapshot))
    elif name == 'upscale':
        from ._upscale_inputs import inputs
        from ._upscale_evidence import validate
        context = inputs(config, run)
        ids = dict(context['identities'], **validate(config, run, draft, context, snapshot))
    else:
        raise ValueError('unknown checkpoint owner')
    ids['draft'] = identity
    _again(ids)
    return dict(draft_complete=True, draft_identity=thaw(identity), input_identities=thaw(ids), report=draft)
