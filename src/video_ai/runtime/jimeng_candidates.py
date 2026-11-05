"""Version-2 official image candidates, with durable one-submission recovery."""
import hashlib
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from uuid import uuid4

from ..adapters.common import AdapterError, FailureKind
from ..adapters.jimeng import JimengClient, encode_body, redact
from ..config import read_json
from ..jimeng_config import STRATEGY
from .manifest import hash_file, now, thaw, validate_run_dir
from .production_inputs import load_frozen_inputs, _same_json
from .execution_limits import execution_deadline
from .production_state import ProductionRefused, RunLock, run_path, object_fields, write_exclusive
from .scene_revision_records import (revision_checkpoint_transaction, revision_checkpoints_active,
                                     revision_read_checkpoint, revision_read_matches, revision_validation)
from .verification import protect_scene_inputs


def boundary(point, identity):
    """Durable transaction boundary for orchestration/fault injection."""


def _digest(value):
    return hashlib.sha256(encode_body(value)).hexdigest()


class _Records:
    def __init__(self, run, lock):
        self.run, self.lock = run, lock
        self.revision_guard = None

    def lock_owned(self):
        if self.lock.run_dir != self.run or read_json(self.lock.path) != self.lock.owner:
            raise ProductionRefused('candidate generation lost held run lock')

    def owned(self):
        self.lock_owned()
        if self.revision_guard is not None and not revision_checkpoints_active():
            self.revision_guard.verify_captured_bytes()

    def save(self, path, value):
        self.owned(); path = run_path(self.run, path)
        if path.exists():
            if not _same_json(read_json(path), value): raise ProductionRefused('immutable image record differs')
            return
        temporary = run_path(self.run, path.with_name(path.name+'.'+uuid4().hex+'.tmp'))
        write_exclusive(temporary, value)
        self.owned(); os.rename(temporary, path)

    def image(self, path, raw):
        self.owned(); path = run_path(self.run, path)
        temporary = run_path(self.run, path.with_name(path.name+'.'+uuid4().hex+'.tmp'))
        with temporary.open('xb') as file:
            file.write(raw); file.flush(); os.fsync(file.fileno())
        self.owned(); os.rename(temporary, path)


def _read_bound(path, fields, identity):
    value = read_json(path)
    object_fields(value, fields, 'Jimeng record')
    if type(value['schema_version']) is not int or value['schema_version'] != 2 or value['identity'] != identity:
        raise ProductionRefused('Jimeng record schema or identity differs')
    return value


def record_output_layout(store, folder, identity, task_id, urls):
    """Keep initial ordering; one accepted output can move between CDN origins."""
    layout = dict(schema_version=2, identity=identity,
        sources=[_digest(urlsplit(url)._replace(query='', fragment='').geturl()) for url in urls])
    path = folder/'outputs.json'
    if not path.exists():
        store.save(path, layout)
        return
    original = _read_bound(path, ('schema_version', 'identity', 'sources'), identity)
    if _same_json(original, layout):
        return
    old_sources = original['sources']
    if (type(old_sources) is not list or len(old_sources) != 1 or len(layout['sources']) != 1
            or type(old_sources[0]) is not str or not re.fullmatch('[0-9a-f]{64}', old_sources[0])):
        raise ProductionRefused('official image output origins/order changed; cannot map multiple outputs')
    # Both responses belong to the same accepted task. A single output has no
    # ordering ambiguity; never change its task, candidate ID or original bytes.
    refresh = dict(schema_version=2, identity=identity, task_id=task_id,
        algorithm='single_output_origin_refresh_v1', original_outputs_sha256=_digest(original),
        sources=layout['sources'])
    store.save(folder/('outputs-refresh-'+_digest(refresh)+'.json'), refresh)


def _verify_candidate(value, request, task_id, index, folder, inspect, settings):
    fields = ('candidate_id', 'request_id', 'task_id', 'req_key', 'path', 'bytes', 'sha256', 'width', 'height', 'format')
    object_fields(value, fields, 'Jimeng candidate')
    cid = f'{request["request_id"]}_image_{index:02d}'
    if (value['candidate_id'] != cid or value['request_id'] != request['request_id'] or value['task_id'] != task_id
            or value['req_key'] != settings.req_key or value['path'] != str(folder/(cid+'.original'))):
        raise ProductionRefused('candidate model/task/path identity differs')
    path = run_path(folder.parents[3], value['path'])
    fresh = hash_file(path)
    if type(value['bytes']) is not int or (fresh.bytes, fresh.sha256) != (value['bytes'], value['sha256']):
        raise ProductionRefused('candidate image SHA256 differs')
    _verify_download(folder/(cid+'.download.json'), _digest(request), cid, fresh)
    if (type(value['width']) is not int or type(value['height']) is not int
            or (value['width'], value['height']) != (settings.output_width, settings.output_height)):
        raise ProductionRefused('candidate dimensions differ from model configuration')
    if not isinstance(value['format'], str) or not value['format']: raise ProductionRefused('invalid candidate image format')


def _verify_download(receipt_path, identity, candidate_id, fresh):
    receipt = _read_bound(receipt_path, ('schema_version', 'identity', 'candidate_id', 'bytes', 'sha256'), identity)
    if (receipt['candidate_id'] != candidate_id or type(receipt['bytes']) is not int
            or (receipt['bytes'], receipt['sha256']) != (fresh.bytes, fresh.sha256)):
        raise ProductionRefused('downloaded original SHA256 differs from download receipt')


def _inspect_original(path, inspect, settings):
    info = inspect(path)
    if (type(info.get('width')) is not int or type(info.get('height')) is not int
            or (info['width'], info['height']) != (settings.output_width, settings.output_height)):
        raise ProductionRefused('official image dimensions differ from configured model dimensions; original retained')
    if not isinstance(info.get('format'), str) or not info['format']: raise ProductionRefused('invalid image format')
    return info


def _request_candidates(store, folder, request, client, inspect, settings, sleep, *, phase='collect'):
    identity = _digest(request)
    store.save(folder/'request.json', request)
    accepted_path = folder/'accepted.json'
    intent_path = folder/'intent.json'
    if accepted_path.exists():
        accepted = _read_bound(accepted_path, ('schema_version', 'identity', 'task_id', 'request_id', 'diagnostic'), identity)
    else:
        if (folder/'terminal.json').exists() or (folder/'result.json').exists():
            raise ProductionRefused('image result/terminal lacks durable task_id; no automatic resubmission')
        if intent_path.exists():
            raise ProductionRefused('submit_unknown: image submission intent has no durable task_id; verify original request manually, no automatic resubmission')
        if phase == 'check': return None
        # Missing credentials is a local precondition and must not create a submission intent.
        if isinstance(client, JimengClient): client.check_credentials()
        store.save(intent_path, dict(schema_version=2, identity=identity, created_at=now(), state='intent'))
        store.owned()
        if revision_checkpoints_active(): revision_read_checkpoint()
        if isinstance(client, JimengClient):
            snapshots = [(path, hash_file(path)) for path in (folder/'request.json', intent_path)]
            def before_send():
                store.lock_owned()
                for path, expected in snapshots:
                    fresh = hash_file(path)
                    if (fresh.bytes, fresh.sha256) != (expected.bytes, expected.sha256):
                        raise ProductionRefused('image request/intent changed before actual HTTP send')
                store.lock_owned()
            client.ownership_check = before_send
        try:
            response = client.submit(request['prompt'])
        except AdapterError as exc:
            store.save(folder/('submission-error-'+uuid4().hex+'.json'), dict(schema_version=2, identity=identity,
                kind=exc.kind.value, diagnostic=getattr(exc, 'diagnostic', {})))
            raise
        finally:
            if isinstance(client, JimengClient): client.ownership_check = store.lock_owned
        accepted = dict(schema_version=2, identity=identity, task_id=response['task_id'],
                        request_id=response['request_id'], diagnostic=response['diagnostic'])
        store.save(accepted_path, accepted)
        boundary('accepted', identity)
    if not intent_path.exists(): raise ProductionRefused('accepted task has no submission intent')
    _read_bound(intent_path, ('schema_version', 'identity', 'created_at', 'state'), identity)
    task_id = accepted['task_id']
    if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,256}', task_id):
        raise ProductionRefused('invalid persisted official task ID')
    terminal_path = folder/'terminal.json'
    if terminal_path.exists():
        terminal = _read_bound(terminal_path, ('schema_version', 'identity', 'status'), identity)
        raise ProductionRefused('official task '+str(terminal['status'])+'; no automatic resubmission')
    result_path = folder/'result.json'
    if result_path.exists():
        result = _read_bound(result_path, ('schema_version', 'identity', 'task_id', 'candidates'), identity)
        if result['task_id'] != task_id or not isinstance(result['candidates'], list) or not result['candidates']:
            raise ProductionRefused('invalid image task result identity')
        for index, candidate in enumerate(result['candidates'], 1):
            _verify_candidate(candidate, request, task_id, index, folder, inspect, settings)
        return result['candidates']
    if phase in ('check', 'submit'): return None
    end = execution_deadline(settings.task_timeout_seconds,time.monotonic())
    delay = settings.poll_interval_seconds
    def remaining():
        if end is None:return settings.request_timeout_seconds
        value = end-time.monotonic()
        if value <= 0: raise TimeoutError('Jimeng image polling/download budget expired; resume original task')
        return value
    while True:
        store.owned()
        response = client.query(task_id, timeout=remaining())
        store.save(folder/('query-'+uuid4().hex+'.json'), dict(schema_version=2, identity=identity,
            task_id=task_id, status=response['status'], request_id=response['request_id'], diagnostic=response['diagnostic']))
        if response['status'] == 'done': break
        if response['status'] in ('expired', 'not_found', 'failed'):
            store.save(terminal_path, dict(schema_version=2, identity=identity, status=response['status']))
            raise ProductionRefused('official task '+response['status']+'; no automatic resubmission')
        sleep(min(delay, remaining())); delay = min(delay*2, 15)
    urls = response['image_urls']
    # Persist output ordering without persisting the expiring signed URLs.
    record_output_layout(store, folder, identity, task_id, urls)
    candidates = []
    for index, url in enumerate(urls, 1):
        cid = f'{request["request_id"]}_image_{index:02d}'
        path = folder/(cid+'.original'); metadata = folder/(cid+'.json')
        if metadata.exists():
            record = read_json(metadata)
            _verify_candidate(record, request, task_id, index, folder, inspect, settings)
        else:
            receipt_path = folder/(cid+'.download.json')
            if not path.exists():
                store.owned(); raw = client.download(url, timeout=remaining())
                if revision_checkpoints_active(): revision_read_checkpoint()
                # Bind downloaded bytes before exposing a reusable original. An
                # interruption before decoding must not allow replacement adoption.
                store.save(receipt_path, dict(schema_version=2, identity=identity, candidate_id=cid,
                    bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
                store.image(path, raw)
                boundary('downloaded', cid)
            if not receipt_path.exists(): raise ProductionRefused('original has no SHA256 download receipt')
            _verify_download(receipt_path, identity, cid, hash_file(path))
            info = _inspect_original(path, inspect, settings)
            fresh = hash_file(path)
            record = dict(candidate_id=cid, request_id=request['request_id'], task_id=task_id, req_key=settings.req_key,
                path=str(path), bytes=fresh.bytes, sha256=fresh.sha256, width=info['width'], height=info['height'], format=info['format'])
            store.save(metadata, record)
        candidates.append(record)
    store.save(result_path, dict(schema_version=2, identity=identity, task_id=task_id, candidates=candidates))
    return candidates


@protect_scene_inputs
@revision_validation
@revision_checkpoint_transaction()
def generate_candidates(frozen, scene_id, prompt, *, client=None, inspect=None, sleep=time.sleep, lock=None):
    """Generate/recover original candidates; acquire a run lock unless supplied by coordinator.

    Returns a schema-2 candidate manifest. This API never accepts selections,
    sends email, or submits a downstream video task.
    """
    if not isinstance(scene_id, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,99}', scene_id):
        raise ProductionRefused('safe scene_id required')
    if not isinstance(prompt, str) or not prompt.strip() or '://' in prompt:
        raise ProductionRefused('nonempty image prompt without URLs required')
    run = validate_run_dir(Path(frozen.options['script_path']).parent.parent)
    if lock is None:
        with RunLock(run) as held:
            return generate_candidates(frozen, scene_id, prompt, client=client, inspect=inspect, sleep=sleep, lock=held)
    store = _Records(run, lock); store.owned()
    if store.revision_guard is not None: store.revision_guard.verify_captured_bytes()
    if not revision_read_matches(('frozen-inputs', str(run)), frozen, lambda: load_frozen_inputs(run)):
        raise ProductionRefused('candidate frozen input/model identity differs')
    if 'scene_revision' in frozen.options:
        from .scene_revision_records import require_scene_revision
        proof=require_scene_revision(frozen);store.revision_guard=proof['guard']
        if 'image:'+scene_id in proof['imports']:raise ProductionRefused('imported image must be read through its registered view')
    if frozen.config.production_strategy != STRATEGY: raise ProductionRefused('candidate API requires paragraph_jimeng_v1')
    settings = frozen.config.image_generation
    if client is not None and not _same_json(client.settings, settings): raise ProductionRefused('candidate client model differs')
    client = client or JimengClient(settings)
    if isinstance(client,JimengClient):
        client.ownership_check=store.lock_owned
        # GET has no paid side effect. Full source checks bracket downloading
        # and every durable save; per-chunk checks only need the active lease.
        client.download_ownership_check=store.lock_owned
    if inspect is None:
        from ..media.images import inspect_image
        from .logging import RunLogger
        from .paths import RuntimePaths
        logger = RunLogger(run, production=True)
        def inspect(path):
            info, _ = inspect_image(path, config=frozen.config, paths=RuntimePaths.from_config(frozen.config),
                logger=logger, unit_id=scene_id, stage='start_images', production=True)
            return info
    folder = run_path(run, run/'production/jimeng'/scene_id)
    folder.mkdir(parents=True, exist_ok=True)
    requests = [dict(schema_version=2, run_id=run.name, scene_id=scene_id, request_id=f'request_{i:02d}',
        prompt=prompt, image_generation=thaw(settings)) for i in range(1, settings.candidates_per_scene+1)]
    identity = _digest(requests)
    manifest_path = folder/'candidates.json'
    candidates = []
    # An existing manifest is a commit marker: validate all backing records before returning.
    manifest = read_json(manifest_path) if manifest_path.exists() else None
    if manifest is not None:
        object_fields(manifest, ('schema_version', 'run_id', 'scene_id', 'identity', 'candidates'), 'candidate manifest')
        if (type(manifest['schema_version']) is not int or manifest['schema_version'] != 2
                or manifest['run_id'] != run.name or manifest['scene_id'] != scene_id or manifest['identity'] != identity):
            raise ProductionRefused('candidate manifest schema/run/scene/input identity differs')
        for request in requests:
            if not (folder/request['request_id']/'result.json').exists(): raise ProductionRefused('committed candidates lack request result')
    work = []
    try:
        for request in requests:
            directory = run_path(run, folder/request['request_id']); directory.mkdir(exist_ok=True)
            completed = _request_candidates(store, directory, request, client, inspect, settings, sleep, phase='check')
            work.append((request, directory, completed))
        for request, directory, completed in work:
            if completed is None:
                _request_candidates(store, directory, request, client, None, settings, sleep, phase='submit')
    except (ProductionRefused, AdapterError, TimeoutError):
        for request in requests:
            directory = run_path(run, folder/request['request_id'])
            if (directory/'accepted.json').exists() and not (directory/'result.json').exists():
                try:
                    _request_candidates(store, directory, request, client, inspect, settings, sleep)
                except Exception:
                    pass
        raise
    for request, directory, completed in work:
        candidates.extend(completed if completed is not None else
            _request_candidates(store, directory, request, client, inspect, settings, sleep))
    result = dict(schema_version=2, run_id=run.name, scene_id=scene_id, identity=identity, candidates=candidates)
    if not manifest_path.exists(): revision_read_checkpoint()
    store.save(manifest_path, result)
    return result
