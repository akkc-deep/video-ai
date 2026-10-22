"""Reference-image asynchronous transactions with a durable single-submit intent."""
from datetime import datetime, timezone
import hashlib
import re
import time
from urllib.parse import urlsplit
from uuid import uuid4

from ..adapters.common import AdapterError
from ..adapters.external_https import validate_https_url
from ..adapters.jimeng import JimengClient, encode_body, redact
from ..jimeng_config import STRATEGY
from ..planning.production_scenes import canonical_digest
from ..reference_config import require_url_budget
from .manifest import hash_file, now, thaw
from .production_inputs import _same_json
from .production_state import ProductionRefused, RunLock, object_fields, run_path
from .jimeng_candidates import (_Records, _read_bound, _verify_candidate, _verify_download,
                                _inspect_original)
from . import image_selection_records as images
from .reference_image_records import (reference_requests, reference_candidates,
                                     validate_reference_inputs, validate_reference_intent,
                                     submit_evidence, validate_submit_evidence)


def boundary(point, identity):
    """Durable transaction boundary for local orchestration/fault injection."""


def _live_urls(storage, references, settings, model):
    if storage is None: raise ProductionRefused('reference storage is required before submission')
    if not _same_json(storage.settings, settings['storage']):
        raise ProductionRefused('reference storage settings differ from immutable binding')
    urls = []; evidence = []
    for reference in references:
        signed = storage.presign_get(reference['object'], expires_seconds=settings['storage']['url_ttl_seconds'])
        object_fields(signed, 'url issued_at expires_at'.split(), 'presigned reference')
        validate_https_url(signed['url'])
        parts = urlsplit(signed['url'])
        obj = reference['object']
        if (parts.netloc != obj['bucket']+'.tos-'+obj['region']+'.volces.com'
                or parts.path != '/'+obj['key'] or parts.fragment):
            raise ProductionRefused('presigned reference URL object differs')
        urls.append(signed['url'])
        evidence.append(dict(sha256=hashlib.sha256(signed['url'].encode('utf-8')).hexdigest(),
                             issued_at=signed['issued_at'], expires_at=signed['expires_at']))
    _remaining_lifetime(evidence, model, settings)
    return urls, evidence


def _remaining_lifetime(evidence, model, settings):
    needed = require_url_budget(model, settings['storage'])
    current = datetime.now(timezone.utc)
    for row in evidence:
        images.timestamp(row['issued_at']); images.timestamp(row['expires_at'])
        issued, expires = (datetime.fromisoformat(row[k]) for k in ('issued_at','expires_at'))
        if issued > current or (expires-current).total_seconds() < needed:
            raise ProductionRefused('reference URL remaining TTL cannot cover task budget')


def _submission_guard(store, request, evidence, model, settings):
    """Capture immutable local identities; the network worker only reads them.

    A connection can spend time in DNS/TLS after caller-side validation. Its
    final send guard must still cover URL lifetime and original/object identity.
    """
    snapshots = []
    for reference in request['reference_inputs']:
        folder = store.run/'production/reference-storage'/reference['sha256']
        intent = images._read(folder/'intent.json')
        source = intent['source']
        if any(source[k]!=reference[k] for k in ('bytes','sha256')):
            raise ProductionRefused('reference storage source differs from selected original')
        snapshots.append((run_path(store.run, source['path']), source['bytes'], source['sha256']))
        for path in (folder/'intent.json', folder/'object.json'):
            stamp = hash_file(path); snapshots.append((path, stamp.bytes, stamp.sha256))
    root = store.run/'production/reference-images'
    request_folder = store.run/'production/jimeng'/request['scene_id']/request['request_id']
    for path in (root/'settings.json', root/'capability.json', root/'config-source.json',
                 store.run/'production/reference-capabilities'/(model.req_key+'.json'),
                 request_folder/'intent.json', request_folder/'submit-evidence.json', request_folder/'request.json'):
        if path.exists():
            stamp = hash_file(path); snapshots.append((path, stamp.bytes, stamp.sha256))
    def guard():
        store.owned(); _remaining_lifetime(evidence, model, settings)
        for path, size, sha in snapshots:
            fresh = hash_file(path)
            if (fresh.bytes, fresh.sha256) != (size, sha):
                raise ProductionRefused('reference source/object/settings changed before actual HTTP send')
        store.owned(); _remaining_lifetime(evidence, model, settings)
    return guard


def _request(store, folder, request, client, inspect, model, settings, presign, verify):
    identity = canonical_digest(request)
    store.save(folder/'request.json', request)
    accepted_path, intent_path = folder/'accepted.json', folder/'intent.json'
    if accepted_path.exists():
        accepted = _read_bound(accepted_path, 'schema_version identity task_id request_id diagnostic'.split(), identity)
    else:
        if intent_path.exists():
            validate_reference_intent(images._read(intent_path), request, settings)
            raise ProductionRefused('submit_unknown: reference intent has no durable task_id; no automatic resubmission')
        if hasattr(client, 'check_credentials'): client.check_credentials()
        urls, evidence = presign()
        payload = dict(thaw(model.model_parameters), req_key=model.req_key, prompt=request['prompt'], image_urls=urls)
        intent = dict(schema_version=2, run_id=request['run_id'], scene_id=request['scene_id'],
            request_id=request['request_id'], logical_request_sha256=identity,
            submit_body_sha256=hashlib.sha256(encode_body(payload)).hexdigest(), reference_urls=evidence, created_at=now())
        validate_reference_intent(intent, request, settings)
        _remaining_lifetime(evidence, model, settings)
        store.save(intent_path, intent)
        store.save(folder/'submit-evidence.json', submit_evidence(request, intent))
        boundary('intent', identity)
        store.owned()
        verify()
        store.owned()
        _remaining_lifetime(evidence, model, settings)
        if isinstance(client, JimengClient):
            client.ownership_check = _submission_guard(store, request, evidence, model, settings)
        try:
            response = client.submit(request['prompt'], image_urls=urls)
        except AdapterError as exc:
            store.save(folder/('submission-error-'+uuid4().hex+'.json'), dict(schema_version=2, identity=identity,
                kind=exc.kind.value, diagnostic=redact(getattr(exc, 'diagnostic', {}))))
            raise
        finally:
            # Accepted-task query/download recovery uses the original task even
            # after its reference input URLs expire. In-flight HTTPS requests
            # retain their captured submission guard after this reset.
            if isinstance(client, JimengClient): client.ownership_check = store.owned
        accepted = dict(schema_version=2, identity=identity, task_id=response['task_id'],
                        request_id=response['request_id'], diagnostic=redact(response['diagnostic']))
        store.save(accepted_path, accepted)
        boundary('accepted', identity)
    if not intent_path.exists(): raise ProductionRefused('reference task lacks durable submission intent')
    intent = images._read(intent_path)
    validate_reference_intent(intent, request, settings)
    validate_submit_evidence(folder, request, intent)
    task_id = accepted['task_id']
    if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,256}', task_id):
        raise ProductionRefused('invalid persisted reference task ID')
    result_path = folder/'result.json'
    if result_path.exists():
        result = _read_bound(result_path, 'schema_version identity task_id candidates'.split(), identity)
        if result['task_id'] != task_id or not isinstance(result['candidates'], list) or not result['candidates']:
            raise ProductionRefused('invalid reference task result')
        for index, candidate in enumerate(result['candidates'], 1):
            _verify_candidate(candidate, request, task_id, index, folder, inspect, model)
        return result['candidates']
    terminal_path = folder/'terminal.json'
    if terminal_path.exists():
        terminal = _read_bound(terminal_path, 'schema_version identity status'.split(), identity)
        raise ProductionRefused('official task '+str(terminal['status'])+'; no automatic resubmission')
    end = time.monotonic()+model.task_timeout_seconds
    def remaining():
        seconds = end-time.monotonic()
        if seconds <= 0: raise TimeoutError('reference task budget expired; resume original task')
        return seconds
    delay = model.poll_interval_seconds
    while True:
        store.owned(); response = client.query(task_id, timeout=remaining())
        store.save(folder/('query-'+uuid4().hex+'.json'), dict(schema_version=2, identity=identity,
            task_id=task_id, status=response['status'], request_id=response['request_id'], diagnostic=redact(response['diagnostic'])))
        if response['status'] == 'done': break
        if response['status'] in ('expired', 'not_found', 'failed'):
            store.save(terminal_path, dict(schema_version=2, identity=identity, status=response['status']))
            raise ProductionRefused('official task '+response['status']+'; no automatic resubmission')
        time.sleep(min(delay, remaining())); delay = min(delay*2, 15)
    urls = response['image_urls']
    store.save(folder/'outputs.json', dict(schema_version=2, identity=identity,
        sources=[canonical_digest(urlsplit(url)._replace(query='', fragment='').geturl()) for url in urls]))
    candidates = []
    for index, url in enumerate(urls, 1):
        cid = f'{request["request_id"]}_image_{index:02d}'
        path, metadata = folder/(cid+'.original'), folder/(cid+'.json')
        if metadata.exists():
            record = images._read(metadata)
            _verify_candidate(record, request, task_id, index, folder, inspect, model)
        else:
            receipt_path = folder/(cid+'.download.json')
            if not path.exists():
                store.owned(); raw = client.download(url, timeout=remaining())
                store.save(receipt_path, dict(schema_version=2, identity=identity, candidate_id=cid,
                    bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
                store.image(path, raw); boundary('downloaded', cid)
            if not receipt_path.exists(): raise ProductionRefused('reference original lacks download receipt')
            _verify_download(receipt_path, identity, cid, hash_file(path))
            info = _inspect_original(path, inspect, model); fresh = hash_file(path)
            record = dict(candidate_id=cid, request_id=request['request_id'], task_id=task_id, req_key=model.req_key,
                path=str(path), bytes=fresh.bytes, sha256=fresh.sha256, width=info['width'], height=info['height'], format=info['format'])
            store.save(metadata, record)
        candidates.append(record)
    store.save(result_path, dict(schema_version=2, identity=identity, task_id=task_id, candidates=candidates))
    return candidates


def generate_reference_candidates(frozen, scene, bible, references, *, settings, capability, client,
                                  paths, logger, lock, storage=None):
    """Generate/recover reference candidates; supplied lock belongs to the caller."""
    run = images._run(frozen)
    if lock is None:
        with RunLock(run) as held:
            return generate_reference_candidates(frozen, scene, bible, references, settings=settings,
                capability=capability, client=client, paths=paths, logger=logger, lock=held, storage=storage)
    store = _Records(run, lock); store.owned()
    from ._scene_revision_origins import inherited
    imported=inherited(frozen,'plan','all')
    plan=imported['scene_plan'] if imported is not None else images._read(run/'production/scene-plan.json')
    if 'scene_revision' in frozen.options:
        from .scene_revision_records import require_scene_revision
        store.revision_guard=require_scene_revision(frozen)['guard']
    model, prompt = validate_reference_inputs(frozen, scene, bible, plan, references, settings)
    images._equal(capability, settings['capability'], 'supplied reference capability')
    if client is None: client = JimengClient(model)
    if not _same_json(client.settings, model): raise ProductionRefused('reference client model differs')
    if isinstance(client, JimengClient): client.ownership_check = store.owned
    requests = reference_requests(frozen, scene, prompt, references, model)
    provenance = dict(schema_version=2, production_strategy=STRATEGY, run_id=run.name, scene_id=scene['scene_id'],
        scene_plan_sha256=canonical_digest(plan), visual_bible_sha256=canonical_digest(bible), model_settings=thaw(model),
        capability_sha256=settings['capability_sha256'], prompt_sha256=hashlib.sha256(prompt.encode('utf-8')).hexdigest(),
        references=references, requests=[dict(request_id=r['request_id'], logical_request_sha256=canonical_digest(r)) for r in requests])
    provenance_path = run_path(run, run/'production/reference-images'/scene['scene_id']/'provenance.json')
    if provenance_path.exists(): images._equal(images._read(provenance_path), provenance, 'immutable reference provenance')
    folder = run_path(run, run/'production/jimeng'/scene['scene_id']); folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder/'candidates.json'
    if manifest_path.exists():
        manifest = images._read(manifest_path)
        images._equal(manifest['identity'], canonical_digest(requests), 'reference manifest requests')
        for request in requests:
            if not (folder/request['request_id']/'result.json').exists():
                raise ProductionRefused('committed reference candidates lack result')
    def presign():
        store.owned()
        validate_reference_inputs(frozen, scene, bible, plan, references, settings)
        store.owned()
        return _live_urls(storage, references, settings, model)
    candidates = []
    def verify():
        validate_reference_inputs(frozen, scene, bible, plan, references, settings)
    for request in requests:
        directory = run_path(run, folder/request['request_id']); directory.mkdir(exist_ok=True)
        candidates.extend(_request(store, directory, request, client,
            lambda path: images._inspect_original(frozen, path), model, settings, presign, verify))
    result = dict(schema_version=2, run_id=run.name, scene_id=scene['scene_id'],
                  identity=canonical_digest(requests), candidates=candidates)
    provenance_path.parent.mkdir(parents=True, exist_ok=True)
    store.save(provenance_path, provenance); boundary('provenance', provenance['scene_id'])
    store.save(manifest_path, result)
    reference_candidates(frozen, scene, manifest_path)
    return result
