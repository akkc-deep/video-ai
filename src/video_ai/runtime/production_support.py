"""Durable production prefix reconciliation and original HTTP response recovery."""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
import os
from pathlib import Path
from threading import get_ident

from ..config import read_json
from ..adapters.common import AdapterError, FailureKind, strict_json
from .manifest import hash_file
from .production_state import (ArtifactStamp, ProductionRefused, REPORT_NAMES, run_path,
                               sync_file, validate_checkpoint, validate_report)


class MissingHttpEvidence(ProductionRefused):
    """An original response is unavailable, without a conflicting request identity."""


_http_recovery = ContextVar('production_http_recovery', default=None)


class _RequestDirectoryWatch:
    """Windows name-change notification cannot be hidden by restoring mtime."""
    def __init__(self,root):
        import ctypes
        from ctypes import wintypes
        self.api=ctypes.WinDLL('kernel32',use_last_error=True)
        self.api.FindFirstChangeNotificationW.argtypes=[wintypes.LPCWSTR,wintypes.BOOL,wintypes.DWORD]
        self.api.FindFirstChangeNotificationW.restype=wintypes.HANDLE
        self.api.FindNextChangeNotification.argtypes=[wintypes.HANDLE]
        self.api.FindNextChangeNotification.restype=wintypes.BOOL
        self.api.FindCloseChangeNotification.argtypes=[wintypes.HANDLE]
        self.api.FindCloseChangeNotification.restype=wintypes.BOOL
        self.api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        self.api.WaitForSingleObject.restype=wintypes.DWORD
        self.handle=self.api.FindFirstChangeNotificationW(str(root),False,3)
        if self.handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())

    def changed(self):
        import ctypes
        result=self.api.WaitForSingleObject(self.handle,0)
        if result==258:return False
        if result!=0 or not self.api.FindNextChangeNotification(self.handle):
            raise ctypes.WinError(ctypes.get_last_error())
        return True

    def close(self):
        if self.handle is not None:
            handle,self.handle=self.handle,None
            if not self.api.FindCloseChangeNotification(handle):
                import ctypes
                raise ctypes.WinError(ctypes.get_last_error())


class _HttpRequestIndex:
    """Index immutable request identities while Windows denies writes/deletes."""
    def __init__(self, root):
        self.root,self.entries,self.durable=root,{},set()
        self.watch=None;self.inventory=None;self.by_unit={};self.watch_failed=False;self.directory_identity=None;self.failed=False

    def _directory_changed(self):
        """Refresh on native notification; unsupported/error paths always scan."""
        try:
            stat=self.root.stat();identity=(stat.st_dev,stat.st_ino)
            if self.directory_identity is not None and identity!=self.directory_identity:
                self.watch_failed=True
            self.directory_identity=identity
            if self.watch_failed:
                if self.watch is not None:self.watch.close();self.watch=None
                return True
            if self.watch is None:self.watch=_RequestDirectoryWatch(self.root)
            return self.watch.changed()
        except OSError:
            self.watch_failed=True
            if self.watch is not None:self.watch.close();self.watch=None
            return True

    def paths(self, uid, durable):
        if self.failed:raise ProductionRefused('HTTP request protection could not be restored')
        changed=self._directory_changed()
        if self.inventory is None or changed:
            # Notifications are rearmed before enumeration. A second check
            # covers names created while glob was in progress.
            while True:
                self.inventory=set(self.root.glob('*.request.json'))
                if self.watch is None or not self._directory_changed():break
            paths=self.inventory
            if set(self.entries)-paths:raise ProductionRefused('original HTTP request evidence disappeared')
            for path in paths-self.entries.keys():
                if durable:sync_file(path)
                self.entries[path]=_pin_http_request(path)
                _,_,value,_=self.entries[path]
                if value.get('method')=='POST' and isinstance(value.get('unit_id'),str):
                    self.by_unit.setdefault(value['unit_id'],[]).append(path)
                if durable:self.durable.add(path)
        selected=[]
        for path in self.by_unit.get(uid,()):
            if durable:self.flush(path)
            lease,_,_,_=self.entries[path]
            lease.verify(path);selected.append(path)
        return selected

    def flush(self,path):
        if path in self.durable:return
        with _http_evidence_flush((path,)):sync_file(path)
        self.durable.add(path)

    def close(self):
        error=None
        for path,(lease,_,_,_) in self.entries.items():
            try:lease.verify(path)
            except BaseException as exc:
                if error is None:error=exc
            finally:
                try:lease.close()
                except BaseException as exc:
                    if error is None:error=exc
        if self.watch is not None:
            try:self.watch.close()
            except BaseException as exc:
                if error is None:error=exc
        if error is not None:raise error


def _pin_http_request(path,expected=None):
    """Keep only a duplicated native handle; release the temporary CRT reader."""
    from .verification import _locked_reader,file_stamp,check_path,_NativeInput
    lease=None
    try:
        with _locked_reader(path) as stream:
            stamp=file_stamp(stream)
            value=read_json(path) if expected is None else expected[1]
            digest=sha256(stream.read()).hexdigest()
            check_path(path,stream,stamp if expected is None else expected[0])
            if expected is not None and digest!=expected[2]:
                raise ProductionRefused('HTTP request changed while making evidence durable')
            lease=_NativeInput(path,stream,stamp,digest)
    except BaseException:
        if lease is not None:lease.close()
        raise
    return lease,stamp,value,digest


@contextmanager
def http_recovery_scope():
    """Reuse request discovery only in this live caller-thread stage invocation."""
    current=_http_recovery.get()
    if current is not None and current['active'] and current['thread']==get_ident():
        yield;return
    current=dict(active=True,thread=get_ident(),indexes={})
    token=_http_recovery.set(current)
    try:yield
    finally:
        current['active']=False;_http_recovery.reset(token)
        error=None
        for index in current['indexes'].values():
            try:index.close()
            except BaseException as exc:
                if error is None:error=exc
        if error is not None:raise error


def _http_request_paths(logger, uid, durable):
    root=logger.path('http')
    scope=_http_recovery.get()
    if os.name!='nt' or scope is None or not scope['active'] or scope['thread']!=get_ident():
        return root.glob('*.request.json')
    index=scope['indexes'].setdefault(root,_HttpRequestIndex(root))
    return index.paths(uid,durable)


@contextmanager
def _http_evidence_flush(paths):
    """Permit existing fsync writers, then reauthenticate the unchanged request."""
    scope=_http_recovery.get();suspended=[]
    try:
        if scope is not None and scope['active'] and scope['thread']==get_ident():
            for path in set(Path(p) for p in paths):
                index=scope['indexes'].get(path.parent)
                if index is None or path not in index.entries:continue
                lease,stamp,value,digest=index.entries[path]
                lease.verify(path);lease.close()
                del index.entries[path]
                suspended.append((index,path,stamp,value,digest))
        yield
    finally:
        error=None
        for index,path,stamp,value,digest in suspended:
            try:index.entries[path]=_pin_http_request(path,(stamp,value,digest))
            except BaseException as exc:
                index.failed=True
                if error is None:error=exc
        if error is not None:raise error


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
    with _http_evidence_flush(output['path'] for output in data['outputs'].values()):
        state.record_unit(stage, uid, status='completed', checkpoint_path=path,
                          request=data['request'], outputs=data['outputs'])
    return data


def commit_checkpoint(state, stage, uid, *, request=None, outputs=None, payload=None):
    request = dict(request, state='completed') if request else None
    path = state.write_checkpoint(stage, uid, request=request, outputs=outputs or {}, payload=payload)
    with _http_evidence_flush(output['path'] for output in (outputs or {}).values()):
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
    paths = _http_request_paths(logger,uid,durable) if evidence_paths is None else (Path(p) for p in evidence_paths if str(p).endswith('.request.json'))
    scope=_http_recovery.get()
    if (evidence_paths is not None and logger is not None and scope is not None
            and scope['active'] and scope['thread']==get_ident()):
        # Checkpoint associations narrow response reads, but cannot conceal a
        # second submission that appeared since the checkpoint was committed.
        discovered=[]
        for path in _http_request_paths(logger,uid,durable):
            request=read_json(path)
            if request.get('unit_id')==uid and request.get('method')=='POST':discovered.append(path)
        if len(discovered)>1:raise ProductionRefused(f'{uid}: duplicate original submission records; no POST retry')
        selected=list(paths)
        if set(discovered)!=set(selected):raise ProductionRefused(f'{uid}: checkpoint HTTP request association differs')
        paths=selected
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
        indexed=(scope['indexes'].get(req_path.parent) if scope is not None and scope['active']
                 and scope['thread']==get_ident() else None)
        if indexed is None or req_path not in indexed.durable:sync_file(req_path)
        for path in (meta_path, body_path): sync_file(path)
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
