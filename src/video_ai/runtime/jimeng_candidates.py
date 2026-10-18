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
from .production_state import ProductionRefused, RunLock, run_path, object_fields, write_exclusive


def boundary(point, identity):
    """Durable transaction boundary for orchestration/fault injection."""


def _digest(value):
    return hashlib.sha256(encode_body(value)).hexdigest()


class _Records:
    def __init__(self, run, lock):
        self.run, self.lock = run, lock

    def owned(self):
        if self.lock.run_dir != self.run or read_json(self.lock.path) != self.lock.owner:
            raise ProductionRefused('candidate generation lost held run lock')

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


def _request_candidates(store, folder, request, client, inspect, settings, sleep):
    identity = _digest(request)
    store.save(folder/'request.json', request)
    accepted_path = folder/'accepted.json'
    intent_path = folder/'intent.json'
    if accepted_path.exists():
        accepted = _read_bound(accepted_path, ('schema_version', 'identity', 'task_id', 'request_id', 'diagnostic'), identity)
    else:
        if intent_path.exists():
            raise ProductionRefused('submit_unknown: image submission intent has no durable task_id; verify original request manually, no automatic resubmission')
        # Missing credentials is a local precondition and must not create a submission intent.
        if isinstance(client, JimengClient): client.check_credentials()
        store.save(intent_path, dict(schema_version=2, identity=identity, created_at=now(), state='intent'))
        store.owned()
        try:
            response = client.submit(request['prompt'])
        except AdapterError as exc:
            store.save(folder/('submission-error-'+uuid4().hex+'.json'), dict(schema_version=2, identity=identity,
                kind=exc.kind.value, diagnostic=getattr(exc, 'diagnostic', {})))
            raise
        accepted = dict(schema_version=2, identity=identity, task_id=response['task_id'],
                        request_id=response['request_id'], diagnostic=response['diagnostic'])
        store.save(accepted_path, accepted)
        boundary('accepted', identity)
    if not intent_path.exists(): raise ProductionRefused('accepted task has no submission intent')
    _read_bound(intent_path, ('schema_version', 'identity', 'created_at', 'state'), identity)
    task_id = accepted['task_id']
    if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,256}', task_id):
        raise ProductionRefused('invalid persisted official task ID')
    result_path = folder/'result.json'
    if result_path.exists():
        result = _read_bound(result_path, ('schema_version', 'identity', 'task_id', 'candidates'), identity)
        if result['task_id'] != task_id or not isinstance(result['candidates'], list) or not result['candidates']:
            raise ProductionRefused('invalid image task result identity')
        for index, candidate in enumerate(result['candidates'], 1):
            _verify_candidate(candidate, request, task_id, index, folder, inspect, settings)
        return result['candidates']
    terminal_path = folder/'terminal.json'
    if terminal_path.exists():
        terminal = _read_bound(terminal_path, ('schema_version', 'identity', 'status'), identity)
        raise ProductionRefused('official task '+str(terminal['status'])+'; no automatic resubmission')
    end = time.monotonic()+settings.task_timeout_seconds
    delay = settings.poll_interval_seconds
    def remaining():
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
    layout = dict(schema_version=2, identity=identity, sources=[_digest(urlsplit(url)._replace(query='', fragment='').geturl()) for url in urls])
    store.save(folder/'outputs.json', layout)
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
    fresh = load_frozen_inputs(run)
    if not _same_json(fresh, frozen): raise ProductionRefused('candidate frozen input/model identity differs')
    if frozen.config.production_strategy != STRATEGY: raise ProductionRefused('candidate API requires paragraph_jimeng_v1')
    settings = frozen.config.image_generation
    if client is not None and not _same_json(client.settings, settings): raise ProductionRefused('candidate client model differs')
    client = client or JimengClient(settings)
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
    for request in requests:
        directory = run_path(run, folder/request['request_id']); directory.mkdir(exist_ok=True)
        candidates.extend(_request_candidates(store, directory, request, client, inspect, settings, sleep))
    result = dict(schema_version=2, run_id=run.name, scene_id=scene_id, identity=identity, candidates=candidates)
    store.save(manifest_path, result)
    return result
