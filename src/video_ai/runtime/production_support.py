"""Durable production prefix reconciliation and original HTTP response recovery."""
from pathlib import Path

from ..config import read_json
from ..adapters.common import AdapterError, FailureKind, strict_json
from .manifest import hash_file
from .production_state import (ArtifactStamp, ProductionRefused, REPORT_NAMES, run_path,
                               sync_file, validate_checkpoint, validate_report)


class MissingHttpEvidence(ProductionRefused):
    """An original response is unavailable, without a conflicting request identity."""


def stamps(paths):
    return {role: ArtifactStamp.read(path).to_dict() for role, path in paths.items()}


def read_report(state, stage):
    path = run_path(state.run_dir, state.run_dir/f'production/{REPORT_NAMES[stage]}.json')
    if not path.exists(): return None
    data = read_json(path); validate_report(data, state.run_dir, stage)
    for stamp in data['input_records'].values(): ArtifactStamp.from_dict(stamp).verify()
    return data


def checkpoint_path(state, stage, uid):
    return run_path(state.run_dir, state.run_dir/f'logs/production/checkpoints/{stage}/{uid.replace(":", "_")}.json')


def recover_checkpoint(state, stage, uid):
    path = checkpoint_path(state, stage, uid)
    record = state.snapshot()['units'].get(stage, {}).get(uid)
    if record and record['status'] == 'failed': raise RuntimeError(f'{stage}/{uid}: original request or result failed; automatic retry is disabled')
    if not path.exists():
        if record and record['status'] == 'completed': raise ProductionRefused('completed cursor has no checkpoint')
        return None
    data = read_json(path); validate_checkpoint(data, state.run_dir, stage, uid)
    if record and record['status'] == 'completed': return data
    if record is None:
        request = dict(data['request'], state='intent') if data['request'] else None
        state.record_unit(stage, uid, status='running', request=request)
    state.record_unit(stage, uid, status='completed', checkpoint_path=path,
                      request=data['request'], outputs=data['outputs'])
    return data


def commit_checkpoint(state, stage, uid, *, request=None, outputs=None, payload=None):
    request = dict(request, state='completed') if request else None
    path = state.write_checkpoint(stage, uid, request=request, outputs=outputs or {}, payload=payload)
    state.record_unit(stage, uid, status='completed', checkpoint_path=path, request=request, outputs=outputs or {})
    return read_json(path)


def mark_request_error(state, stage, uid, exc):
    record = state.snapshot()['units'].get(stage,{}).get(uid)
    if record is None or record['request'] is None:
        # An intent write or callback may fail before the state cursor exists.
        raise exc
    request = dict(record['request'])
    paths = [str(run_path(state.run_dir, p)) for p in getattr(exc, 'evidence_paths', ()) if Path(p).exists()]
    request['response_paths'] = paths
    unknown = getattr(exc, 'kind', None) in (FailureKind.ambiguous, FailureKind.unavailable)
    request['state'] = 'ambiguous' if unknown else 'failed'
    state.record_unit(stage, uid, status='running' if unknown else 'failed', request=request,
                      error=dict(kind=type(exc).__name__, message=str(exc), evidence_paths=paths))
    if unknown: raise ProductionRefused(f'{stage}/{uid}: unknown original submission; no automatic POST retry; {exc}') from exc
    raise exc


def recover_http(logger, *, uid, url, payload, evidence_paths=None, durable=True):
    """Match original POST+body, complete metadata and body; never perform a network call."""
    matches = []
    paths = logger.path('http').glob('*.request.json') if evidence_paths is None else (Path(p) for p in evidence_paths if str(p).endswith('.request.json'))
    for path in paths:
        request = read_json(path)
        if request.get('unit_id') != uid or request.get('method') != 'POST': continue
        if request.get('url') != url or request.get('json_body') != payload:
            raise ProductionRefused(f'{uid}: original HTTP request identity differs')
        matches.append(path)
    if not matches: raise MissingHttpEvidence(f'{uid}: original submission has no complete response; no POST retry')
    if len(matches) != 1: raise ProductionRefused(f'{uid}: duplicate original submission records; no POST retry')
    req_path = matches[0]
    token = req_path.name.removesuffix('.request.json')
    meta_path = req_path.with_name(token+'.response.json'); body_path = req_path.with_name(token+'.body')
    if not meta_path.is_file() or not body_path.is_file(): raise MissingHttpEvidence(f'{uid}: original response missing; no POST retry')
    meta = read_json(meta_path)
    if any(meta.get(k) != v for k, v in dict(method='POST', url=url, unit_id=uid, truncated=False, error=None).items()):
        if any(meta.get(k)!=v for k,v in dict(method='POST',url=url,unit_id=uid).items()):
            raise ProductionRefused(f'{uid}: original response identity differs')
        raise MissingHttpEvidence(f'{uid}: original response is incomplete; no POST retry')
    status = meta.get('status')
    if type(status) is not int or not 200 <= status < 300:
        if type(status) is int and 400<=status<500:
            try: strict_json(body_path.read_bytes())
            except ValueError: pass
            else: raise AdapterError(FailureKind.explicit,f'{uid}: original HTTP {status}',(req_path,meta_path,body_path))
        raise MissingHttpEvidence(f'{uid}: original response acceptance unknown; no POST retry')
    raw = body_path.read_bytes()
    if type(meta.get('bytes')) is not int or meta['bytes'] != len(raw): raise ProductionRefused(f'{uid}: response byte count differs')
    if durable:
        for path in (req_path, meta_path, body_path): sync_file(path)
    return raw, meta, [str(req_path), str(meta_path), str(body_path)]


def sync_manifest_stage(manifest, stage, report_path):
    """Only small reports are SHA identities; production media stays stamp-based."""
    status = manifest.snapshot()['stages'][stage]['status']
    if status == 'pending': manifest.record_stage(stage, 'running'); status = 'running'
    if status == 'running':
        identity = hash_file(report_path)
        manifest.record_stage(stage, 'completed', artifacts=[dict(path=str(report_path), category='run',
            bytes=identity.bytes, sha256=identity.sha256, verified_at=identity.verified_at)])
    elif status != 'completed': raise ProductionRefused(f'manifest {stage} has incompatible status')
