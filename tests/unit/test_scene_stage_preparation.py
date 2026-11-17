"""Read-only preparation never carries admission proofs or starts services."""
from contextvars import ContextVar
from dataclasses import FrozenInstanceError, replace
import hashlib
import io
import json
import os
from pathlib import Path
from threading import Event, get_ident
from time import monotonic, sleep
from types import SimpleNamespace

import pytest


def job_at(tmp_path, **changes):
    from video_ai.runtime.scene_stage_preparation import PreparationJob
    path = tmp_path/'source.png'
    if not path.exists(): path.write_bytes(b'fixture-source')
    values = dict(clip_id='scene_0002_clip_0001',
                  source=dict(path=str(path), bytes=path.stat().st_size,
                              sha256=hashlib.sha256(path.read_bytes()).hexdigest()),
                  parameters_sha256='a'*64, workflow_sha256='b'*64,
                  graph_bytes=b'{"node":{"inputs":{"seed":1}}}', parent_required=False)
    values.update(changes)
    return PreparationJob(**values)


def take_ready(pool, job):
    until = monotonic()+2
    while monotonic() < until:
        result = pool.take(job)
        if result is not None: return result
        sleep(.005)
    raise AssertionError('preparation did not finish')


def test_disabled_and_single_slot_and_immutable_result(tmp_path):
    from video_ai.runtime.scene_stage_preparation import ScenePreparationPool
    job = job_at(tmp_path)
    disabled = ScenePreparationPool()
    assert disabled.submit(job) is False
    disabled.close()
    pool = ScenePreparationPool(enabled=True)
    try:
        assert pool.submit(job)
        assert not pool.submit(job)
        value = take_ready(pool, job)
        assert value.job_key == job.key
        assert value.source_bytes == b'fixture-source'
        assert value.actual_sha256 == job.source['sha256']
        assert value.graph_bytes == job.graph_bytes
        with pytest.raises(FrozenInstanceError): value.graph_bytes = b'changed'
        with pytest.raises(TypeError): job.source['bytes'] = 4
        assert pool.report()['peak_jobs'] == 1
    finally: pool.close()


@pytest.mark.parametrize('change', [dict(parent_required=True),
    dict(clip_id='scene_0002_clip_0002'), dict(source_limit=3), dict(graph_limit=3)])
def test_parent_nonfirst_and_resource_budget_refused(tmp_path, change):
    from video_ai.runtime.scene_stage_preparation import ScenePreparationPool
    source_limit, graph_limit = change.pop('source_limit', 64*1024*1024), change.pop('graph_limit',32*1024*1024)
    pool = ScenePreparationPool(enabled=True,max_source_bytes=source_limit,max_graph_bytes=graph_limit)
    try: assert pool.submit(job_at(tmp_path, **change)) is False
    finally: pool.close()


def test_same_size_mtime_rollback_cannot_defeat_sha(tmp_path):
    from video_ai.runtime.scene_stage_preparation import ScenePreparationPool
    job = job_at(tmp_path); path = Path(job.source['path']); before = path.stat()
    path.write_bytes(b'X'*job.source['bytes']); os.utime(path, ns=(before.st_atime_ns,before.st_mtime_ns))
    pool = ScenePreparationPool(enabled=True)
    try:
        assert pool.submit(job)
        assert take_ready(pool,job).error == 'source_changed'
        assert pool.report()['failure_reasons']['source_changed']==1
    finally: pool.close()


def test_windows_creation_and_handle_change_times_may_differ(tmp_path):
    from video_ai.runtime.scene_stage_preparation import ScenePreparationPool
    job=job_at(tmp_path);path=Path(job.source['path']);stamp=path.stat()
    os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns-60_000_000_000))
    pool=ScenePreparationPool(enabled=True)
    try:
        assert pool.submit(job)
        result=take_ready(pool,job)
        assert result.error is None
        assert result.source_bytes==b'fixture-source'
    finally:pool.close()


def test_growth_reads_no_more_than_declared_length_plus_one(tmp_path,monkeypatch):
    from video_ai.runtime.scene_stage_preparation import ScenePreparationPool
    job=job_at(tmp_path);path=Path(job.source['path']);original=Path.open;read_bytes=[];grew=[]
    class Raw(io.RawIOBase):
        def __init__(self):self.file=original(path,'rb',buffering=0)
        def readable(self):return True
        def fileno(self):return self.file.fileno()
        def readinto(self,buffer):
            if not grew:
                with original(path,'ab') as writer:writer.write(b'X'*10000)
                grew.append(True)
            count=self.file.readinto(buffer);read_bytes.append(count);return count
        def close(self):self.file.close();super().close()
    def opened(target,*args,**kwargs):
        if target==path and args==('rb',):
            raw=Raw()
            return raw if kwargs.get('buffering')==0 else io.BufferedReader(raw)
        return original(target,*args,**kwargs)
    monkeypatch.setattr(Path,'open',opened)
    pool=ScenePreparationPool(enabled=True)
    try:
        assert pool.submit(job)
        assert take_ready(pool,job).error=='source_changed'
        assert sum(read_bytes)<=job.source['bytes']+1
    finally:pool.close()


@pytest.mark.parametrize('field', ['parameters_sha256','workflow_sha256','graph_bytes','source'])
def test_mismatched_job_invalidates_result(tmp_path,field):
    from video_ai.runtime.scene_stage_preparation import ScenePreparationPool
    job = job_at(tmp_path)
    value = dict(job.source,sha256='c'*64) if field=='source' else b'{}' if field=='graph_bytes' else 'c'*64
    pool = ScenePreparationPool(enabled=True)
    try:
        assert pool.submit(job)
        assert pool.take(replace(job,**{field:value})) is None
        assert pool.report()['discarded'] == 1
    finally: pool.close()


def test_worker_context_empty_and_read_only(tmp_path,monkeypatch):
    from video_ai.runtime.scene_stage_preparation import ScenePreparationPool
    sentinel = ContextVar('caller_admission',default=None); sentinel.set('private-proof')
    job = job_at(tmp_path); owner = get_ident(); seen = []; original = Path.open
    def opened(path,*args,**kwargs):
        if get_ident()!=owner:
            seen.append((sentinel.get(),args[0] if args else kwargs.get('mode')))
            assert args == ('rb',)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',opened)
    pool = ScenePreparationPool(enabled=True)
    try:
        assert pool.submit(job)
        assert take_ready(pool,job).error is None
        assert seen == [(None,'rb')]
    finally: pool.close()


def test_close_cancels_late_read_and_releases_slot(tmp_path,monkeypatch):
    from video_ai.runtime.scene_stage_preparation import ScenePreparationPool
    job = job_at(tmp_path); entered = Event(); release = Event(); original = Path.open
    def opened(path,*args,**kwargs):
        entered.set(); release.wait(5)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',opened)
    pool = ScenePreparationPool(enabled=True)
    assert pool.submit(job) and entered.wait(1)
    started = monotonic(); pool.close()
    assert monotonic()-started < 2.3
    assert pool.report()['unfinished_worker'] is True
    assert pool.take(job) is None and not pool.submit(job)
    release.set()
    pool._thread.join(1)
    assert pool.take(job) is None
    assert pool.report()['retained_bytes'] == 0


def test_worker_start_resource_failure_falls_back_without_masking_exit(tmp_path,monkeypatch):
    import video_ai.runtime.scene_stage_preparation as preparation
    pool=preparation.ScenePreparationPool(enabled=True)
    def unavailable(*args):raise RuntimeError('cannot start new thread')
    monkeypatch.setattr(preparation.Thread,'start',unavailable)
    assert pool.submit(job_at(tmp_path)) is False
    pool.close()
    assert pool.report()['retained_bytes']==0


def test_phase_diagnostic_failure_keeps_original_phase_error(tmp_path,monkeypatch):
    import video_ai.runtime.production_scene_clips as clips
    def broken(*args,**kwargs):raise ValueError('original phase failure')
    monkeypatch.setattr(clips,'_produce_phase',broken)
    class Logger:
        def save_json(self,*args):raise OSError('diagnostic unavailable')
    context={'store':SimpleNamespace(assert_owned=lambda:None)}
    with pytest.raises(ValueError,match='original phase failure') as caught:
        clips._produce(context,paths=None,logger=Logger(),client_factory=None,service_factory=None)
    assert any('phase diagnostic failed' in note for note in caught.value.__notes__)


def test_owned_handle_start_binding_cannot_change(monkeypatch):
    from video_ai.runtime.production_scene_clips import _OwnedService
    import video_ai.runtime.production_state as state
    monkeypatch.setattr(state,'process_started_at',lambda pid:'same-process')
    process=SimpleNamespace(poll=lambda:None)
    service=object.__new__(_OwnedService);service.process_identity='same-process'
    service.handle=SimpleNamespace(owned=True,pid=1,process=process,started_at='changed',url='url')
    service._handle_binding=(1,'original','url',id(process))
    with pytest.raises(state.ProductionRefused,match='identity changed'):service.ensure()


@pytest.mark.parametrize('poll,identity', [(1,'start'),(None,'reused'),(None,None)])
def test_owned_ensure_rejects_exit_pid_reuse_or_missing_identity(monkeypatch,poll,identity):
    from video_ai.runtime.production_scene_clips import _OwnedService
    import video_ai.runtime.production_state as state
    monkeypatch.setattr(state,'process_started_at',lambda pid:identity)
    service = object.__new__(_OwnedService)
    service.process_identity = 'start'
    service.handle = SimpleNamespace(owned=True,process=SimpleNamespace(poll=lambda:poll),
                                     pid=123,started_at='stamp',url='http://127.0.0.1')
    from video_ai.runtime.production_state import ProductionRefused
    with pytest.raises(ProductionRefused,match='identity changed'): service.ensure()


def test_owned_ensure_rechecks_live_handle(monkeypatch):
    from video_ai.runtime.production_scene_clips import _OwnedService
    service = object.__new__(_OwnedService); service.handle=object(); seen=[]
    monkeypatch.setattr(service,'capability_identity',lambda:seen.append('checked'))
    service.ensure(); service.ensure()
    assert seen == ['checked','checked']


def test_phase_events_are_bounded_and_numeric_without_private_data():
    from video_ai.runtime.scene_stage_preparation import ScenePhaseMetrics
    metrics = ScenePhaseMetrics()
    metrics.event('phase_enter')
    metrics.event('ensure_request',clip_id='scene_0001_clip_0001',service_identity=(123,456,'stamp','url'))
    metrics.event('phase_exit',seconds=.1)
    result = metrics.report()
    assert result['counts']['ensure_request'] == 1
    assert 'url' not in json.dumps(result)
    assert result['events'][-1]['seconds'] == .1


def test_coordinator_consumes_graph_copy_and_rechecks_source(tmp_path):
    from video_ai.runtime.production_scene_clips import _preparation_job, _prepared_graph
    from video_ai.runtime.scene_stage_preparation import ScenePreparationPool, ScenePhaseMetrics
    from video_ai.runtime.production_state import ProductionRefused
    job = job_at(tmp_path); checked=[]
    class Store:
        def assert_owned(self): checked.append('lock')
        def validate_artifact(self,value):
            checked.append(value['path'])
            if hashlib.sha256(Path(value['path']).read_bytes()).hexdigest()!=value['sha256']:
                raise ProductionRefused('source drift')
    context = dict(store=Store(),wan=dict(scenes=[dict(scene_id='scene_0002',**dict(job.source))]),
                   inputs=dict(workflow=dict(job.source),mapping=dict(job.source)))
    row=dict(budget=dict(clip_id=job.clip_id,scene_id='scene_0002',parent_clip_id=None),parameters=dict(seed=1))
    graph = json.loads(job.graph_bytes)
    actual = _preparation_job(context,row,graph)
    pool = ScenePreparationPool(enabled=True)
    metrics = ScenePhaseMetrics()
    try:
        assert pool.submit(actual)
        until=monotonic()+2
        while pool.report()['retained_bytes']==0 and monotonic()<until:sleep(.005)
        copied = _prepared_graph(context,row,graph,pool,metrics)
        copied['node']['inputs']['seed']=2
        assert graph['node']['inputs']['seed']==1
        assert metrics.report()['counts']['prepare_consumed']==1
        assert pool.submit(actual)
        Path(job.source['path']).write_bytes(b'X'*job.source['bytes'])
        with pytest.raises(ProductionRefused,match='source drift'):
            _prepared_graph(context,row,graph,pool,metrics)
    finally:pool.close()
