"""Prepared reference-image batches; selected originals remain immutable."""
from dataclasses import dataclass
from pathlib import Path
import json

from ..adapters.jimeng import JimengClient, redact
from ..config import read_json
from ..jimeng_config import STRATEGY, parse_image_generation
from ..planning.production_scenes import canonical_digest
from ..reference_config import ReferenceConfigurationRequired
from . import image_selection_records as selection_records
from .manifest import hash_file, now, thaw, validate_run_dir
from .production_inputs import _same_json, load_frozen_inputs
from .production_image_selection import _Records as SelectionRecords, prepare_image_batch
from .production_state import ProductionRefused, RunLock, integer, object_fields, run_path, timestamp
from .reference_settings import bind_reference_settings


def boundary(point):
    """Durable fault-injection boundary; never a service or media operation."""


@dataclass(frozen=True)
class ReferencePreparationResult:
    schema_version: int = 2
    production_strategy: str = STRATEGY
    run_id: str | None = None
    run_dir: Path | None = None
    status: str = 'blocked'
    active_stage: str = 'start_images'
    batch_id: str | None = None
    selection_result: dict | None = None
    wan_inputs: Path | None = None
    log_dir: Path | None = None
    error: dict | None = None

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 2 or self.production_strategy != STRATEGY:
            raise ValueError('invalid reference result schema')
        if self.status not in ('awaiting_image_model_configuration', 'awaiting_image_selection', 'email_delivery_unknown',
                               'image_batch_accepted', 'images_ready', 'blocked', 'failed', 'interrupted'):
            raise ValueError('invalid reference result status')
        if self.active_stage != 'start_images': raise ValueError('invalid reference result stage')
        if self.run_dir is not None:
            run = validate_run_dir(Path(self.run_dir)); object.__setattr__(self, 'run_dir', run)
            if self.run_id != run.name: raise ValueError('reference result run identity differs')
            for key in ('wan_inputs', 'log_dir'):
                value = getattr(self, key)
                if value is not None: object.__setattr__(self, key, run_path(run, value))
        elif any(value is not None for value in (self.run_id, self.log_dir, self.wan_inputs, self.selection_result)):
            raise ValueError('reference result requires verified run identity')
        if self.status == 'images_ready':
            if self.wan_inputs is None or not self.wan_inputs.is_file(): raise ValueError('images_ready requires verified Wan inputs')
        elif self.wan_inputs is not None: raise ValueError('Wan inputs require images_ready')
        if self.selection_result is not None:
            from .production_image_selection import ImageSelectionResult
            # Validate both exact keys and the run/stage identity of the nested result.
            object_fields(self.selection_result, ImageSelectionResult.__dataclass_fields__, 'reference selection result')
            nested = ImageSelectionResult(**self.selection_result)
            if nested.run_id != self.run_id or nested.run_dir != self.run_dir:
                raise ValueError('nested selection run differs')
        if self.error is not None: object_fields(self.error, ('kind', 'message', 'evidence_paths'), 'reference result error')
        json.dumps(self.to_dict(), allow_nan=False)

    def to_dict(self): return thaw(self)

    @property
    def exit_code(self):
        return dict(awaiting_image_model_configuration=3, awaiting_image_selection=3, email_delivery_unknown=3,
                    image_batch_accepted=0, images_ready=0, blocked=2, failed=1, interrupted=130)[self.status]


class _Records(SelectionRecords):
    # Settings binding also accepts the smaller candidate store's image interface.
    def image(self, path, raw): return self.bytes(path, raw)


def _result(run, status, *, batch_id=None, selection=None, wan=None, error=None):
    return ReferencePreparationResult(run_id=run.name if run else None, run_dir=run, status=status,
        batch_id=batch_id, selection_result=selection.to_dict() if selection else None,
        wan_inputs=wan, log_dir=run/'logs/production' if run else None, error=error)


def _original_unchanged(store, original):
    store.owned()
    fresh = hash_file(run_path(store.run, original['path']))
    if (fresh.bytes, fresh.sha256) != (original['bytes'], original['sha256']):
        raise ProductionRefused('reference original changed before storage or submission')


def _storage_format(value):
    return {'mjpeg': 'jpeg', 'jpg': 'jpeg'}.get(value, value)


def _storage_object(store, original, settings, storage, *, verify_remote):
    _original_unchanged(store, original)
    image_format = _storage_format(original['format'])
    mime = {'png': 'image/png', 'jpeg': 'image/jpeg', 'webp': 'image/webp'}[image_format]
    expected = {key: settings[key] for key in ('bucket', 'region', 'endpoint')}
    expected.update(key=settings['key_prefix']+'/'+store.run.name+'/'+original['sha256']+'.original',
                    bytes=original['bytes'], sha256=original['sha256'], content_type=mime)
    source = {key: original[key] for key in ('path', 'bytes', 'sha256')}
    folder = run_path(store.run, store.run/'production/reference-storage'/original['sha256'])
    intent_path = folder/'intent.json'; receipt_path = folder/'object.json'
    intent = None
    if intent_path.exists():
        intent = read_json(intent_path)
        object_fields(intent, ('schema_version', 'run_id', 'object', 'source', 'created_at'), 'reference storage intent')
        timestamp(intent['created_at'])
        # One content-addressed object may serve different accepted paths with identical bytes.
        # Keep its initial upload source as immutable evidence and validate that source independently.
        recorded_source = intent['source']
        object_fields(recorded_source, ('path', 'bytes', 'sha256'), 'reference storage source')
        if any(recorded_source[key] != source[key] for key in ('bytes', 'sha256')):
            raise ProductionRefused('reference storage source content differs')
        _original_unchanged(store, recorded_source)
        proposed = dict(schema_version=2, run_id=store.run.name, object=expected, source=recorded_source, created_at=intent['created_at'])
        if not _same_json(intent, proposed): raise ProductionRefused('reference storage intent identity differs')

    def before_put():
        nonlocal intent
        _original_unchanged(store, original)
        if intent is None:
            intent = dict(schema_version=2, run_id=store.run.name, object=expected, source=source, created_at=now())
        store.save(intent_path, intent); boundary('storage-intent')

    def existing_receipt():
        if intent is None or not receipt_path.exists(): raise ProductionRefused('reference object lacks verified storage receipt')
        value = read_json(receipt_path)
        object_fields(value, ('schema_version', 'run_id', 'intent_sha256', 'object', 'verified_at'), 'reference storage receipt')
        timestamp(value['verified_at'])
        obj = value['object']; object_fields(obj, tuple(expected)+('etag',), 'reference object')
        if (type(value['schema_version']) is not int or value['schema_version'] != 2 or value['run_id'] != store.run.name
                or value['intent_sha256'] != canonical_digest(intent) or not _same_json({k: obj[k] for k in expected}, expected)
                or not isinstance(obj['etag'], str) or not obj['etag']):
            raise ProductionRefused('reference storage receipt identity differs')
        return obj

    old = existing_receipt() if receipt_path.exists() else None
    if not verify_remote: return existing_receipt()
    obj = storage.ensure_original(dict(original, format=image_format), run_id=store.run.name, before_put=before_put)
    _original_unchanged(store, original)
    object_fields(obj, tuple(expected)+('etag',), 'verified reference object')
    if not _same_json({key: obj[key] for key in expected}, expected) or not isinstance(obj['etag'], str) or not obj['etag']:
        raise ProductionRefused('verified reference object identity differs')
    if intent is None: raise ProductionRefused('storage adapter did not authorize logical intent')
    if old is not None:
        if not _same_json(old, obj): raise ProductionRefused('immutable reference storage object changed')
    else:
        store.save(receipt_path, dict(schema_version=2, run_id=store.run.name, intent_sha256=canonical_digest(intent),
                                     object=obj, verified_at=now()))
        boundary('storage-object')
    return obj


def _operate(frozen, units, timeline, store, *, batch_index, paths, logger, reference_settings_path,
             storage, client_factory, smtp_factory, email_settings):
    bible, plan = selection_records.load_committed_plan(frozen, units, timeline)
    integer(batch_index, 'reference batch index', 1)
    if batch_index > len(plan['batches']): raise ProductionRefused('reference batch outside committed plan')
    accepted = selection_records.load_accepted_batches(frozen, units, timeline, bible, plan)
    accepted_ids = {row['batch_id'] for row in accepted}
    for index in range(1, batch_index):
        if f'image_batch_{index:04d}' not in accepted_ids:
            raise ProductionRefused('reference batch requires accepted earlier baseline batch')
    batch_id = f'image_batch_{batch_index:04d}'
    scenes = [scene for scene in plan['scenes'] if scene['scene_id'] in plan['batches'][batch_index-1]]
    if not scenes or any(not scene['reference_bindings'] for scene in scenes):
        raise ProductionRefused('reference entry requires associated scenes; prepare baseline with existing image API')
    # A missing baseline must not bind settings or make any external request.
    choices = {row['scene_id'] for batch in accepted for row in batch['selections']}
    if any(binding['source_scene_id'] not in choices for scene in scenes for binding in scene['reference_bindings']):
        raise ProductionRefused('required reference baseline is not accepted')
    marker = bind_reference_settings(frozen, store=store, reference_settings_path=reference_settings_path)
    boundary('reference-settings')
    from .reference_image_records import (resolve_reference_bindings, build_reference_prompt,
                                          build_reference_image_acceptance, require_reference_image_acceptance)
    from .jimeng_reference_candidates import generate_reference_candidates
    from ..adapters.reference_storage import ReferenceStorage
    model = parse_image_generation(marker['model_settings'], 'bound reference model')
    cap = marker['capability']; storage_settings = marker['storage']
    resolved = []
    # Validate the entire batch before the first upload or paid submission.
    for scene in scenes:
        sources = resolve_reference_bindings(frozen, bible, plan, scene, accepted)
        prompt = build_reference_prompt(scene, bible)
        if not sources or len(sources) > cap['max_images']:
            raise ReferenceConfigurationRequired('reference image count exceeds verified model capability')
        if len(prompt.encode('utf-8')) > cap['max_prompt_bytes']:
            raise ReferenceConfigurationRequired('reference prompt exceeds verified model capability')
        for original, uses in sources:
            if (original['bytes'] > cap['max_image_bytes'] or _storage_format(original['format']) not in cap['formats']
                    or not cap['min_width'] <= original['width'] <= cap['max_width']
                    or not cap['min_height'] <= original['height'] <= cap['max_height']):
                raise ReferenceConfigurationRequired('reference original exceeds verified model capability')
            _original_unchanged(store, original)
        resolved.append((scene, sources))
    storage = storage or ReferenceStorage(storage_settings, ownership_check=store.owned)
    if not _same_json(thaw(storage.settings), storage_settings): raise ProductionRefused('reference storage settings differ')
    # Injected test transports are trusted boundaries; production credentials remain environment-only.
    if isinstance(storage, ReferenceStorage):
        storage.ownership_check = store.owned
        storage.check_credentials()
    client = client_factory(model) if client_factory else JimengClient(model)
    if not _same_json(client.settings, model): raise ProductionRefused('reference client model differs')
    if isinstance(client, JimengClient): client.check_credentials()
    manifests = []
    for scene, sources in resolved:
        store.owned(); sid = scene['scene_id']; refs = []
        request_root = store.run/'production/jimeng'/sid
        needs_submit = any(not (request_root/f'request_{i:02d}'/'intent.json').exists()
                           for i in range(1, model.candidates_per_scene+1))
        for original, uses in sources:
            obj = _storage_object(store, original, storage_settings, storage, verify_remote=needs_submit)
            refs.append(dict(scene_id=original['scene_id'],
                **{key: original[key] for key in ('candidate_id', 'sha256', 'bytes', 'width', 'height', 'format')},
                uses=uses, object=obj))
        generate_reference_candidates(frozen, scene, bible, refs, settings=marker, capability=cap, client=client,
                                      paths=paths, logger=logger, lock=store.lock, storage=storage)
        boundary('reference-candidates')
        manifests.append(request_root/'candidates.json')
    selection = prepare_image_batch(frozen, units, timeline, manifests, batch_index=batch_index, paths=paths,
        logger=logger, email_settings=email_settings, smtp_factory=smtp_factory, lock=store.lock)
    store.owned()
    if selection.status in ('failed', 'blocked', 'interrupted', 'email_delivery_unknown'):
        return _result(store.run, selection.status, batch_id=batch_id, selection=selection, error=selection.error)
    if selection.all_images_accepted:
        value = build_reference_image_acceptance(frozen, units, timeline)
        path = run_path(store.run, store.run/'production/reference-images/wan-inputs.json')
        store.save(path, value); boundary('wan-inputs')
        require_reference_image_acceptance(frozen, units, timeline)
        return _result(store.run, 'images_ready', batch_id=batch_id, selection=selection, wan=path)
    return _result(store.run, selection.status, batch_id=batch_id, selection=selection)


def produce_reference_batch(frozen, units, timeline, *, batch_index, paths, logger, reference_settings_path=None,
                            storage=None, client_factory=None, smtp_factory=None, email_settings=None, lock=None):
    run = None
    try:
        candidate_run = validate_run_dir(Path(frozen.options['script_path']).parent.parent)
        if frozen.config.production_strategy != STRATEGY or not _same_json(load_frozen_inputs(candidate_run), frozen):
            raise ProductionRefused('reference frozen inputs or strategy differ')
        run = candidate_run
        if logger.run_dir != run or not logger.production: raise ProductionRefused('matching production logger required')
        if lock is None:
            with RunLock(run) as held:
                return produce_reference_batch(frozen, units, timeline, batch_index=batch_index, paths=paths, logger=logger,
                    reference_settings_path=reference_settings_path, storage=storage, client_factory=client_factory,
                    smtp_factory=smtp_factory, email_settings=email_settings, lock=held)
        store = _Records(run, lock); store.owned()
        return _operate(frozen, units, timeline, store, batch_index=batch_index, paths=paths, logger=logger,
            reference_settings_path=reference_settings_path, storage=storage, client_factory=client_factory,
            smtp_factory=smtp_factory, email_settings=email_settings)
    except (Exception, KeyboardInterrupt) as exc:
        status = ('awaiting_image_model_configuration' if isinstance(exc, ReferenceConfigurationRequired) else
                  'interrupted' if isinstance(exc, KeyboardInterrupt) else 'blocked' if isinstance(exc, ValueError) else 'failed')
        message = (redact(str(exc)) if isinstance(exc, (ProductionRefused, ReferenceConfigurationRequired))
                   else 'Reference image preparation '+status+' ('+type(exc).__name__+').')
        return _result(run, status, error=dict(kind=type(exc).__name__, message=message or status, evidence_paths=[]))
