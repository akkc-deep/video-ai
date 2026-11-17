"""Experimental CPU buffers cannot submit, commit, or inherit caller proofs."""
from contextvars import ContextVar
from dataclasses import replace
import hashlib
import os
from pathlib import Path
from threading import Event, get_ident
from time import monotonic, sleep

import pytest


def artifact(path):
    return dict(path=str(path.resolve()), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def job_at(tmp_path, **changes):
    from video_ai.experiments.upscale_pipeline import UpscaleFrameJob
    path = tmp_path/'input.png'
    if not path.exists(): path.write_bytes(b'original-source')
    values = dict(frame_id=1, source=artifact(path), graph_bytes=b'{"graph":1}',
                  parameters_sha256='a'*64, profile_sha256='b'*64)
    values.update(changes)
    return UpscaleFrameJob(**values)


def ready(call):
    end = monotonic()+3
    while monotonic()<end:
        result = call()
        if result is not None: return result
        sleep(.002)
    raise AssertionError('CPU slot did not finish')


def test_single_write_slot_backpressure_and_completed_replay(tmp_path):
    from video_ai.experiments.upscale_pipeline import PipelineConfig, UpscalePipeline
    job = job_at(tmp_path); output=tmp_path/'output.png'; output.write_bytes(b'captured-png')
    stage=tmp_path/'private'/'frame.part'
    pool=UpscalePipeline(PipelineConfig(writeback=True))
    try:
        assert pool.stage_output(job,artifact(output),stage)
        # Even an already finished copy retains its slot until coordinator drain.
        assert not pool.stage_output(replace(job,frame_id=2),artifact(output),tmp_path/'other.part')
        result=ready(lambda:pool.finish_output(job))
        assert result.job_key==job.key and result.artifact['sha256']==hashlib.sha256(b'captured-png').hexdigest()
        assert stage.read_bytes()==b'captured-png'
        assert not (tmp_path/'frame.json').exists()
        assert pool.finish_output(job) is None
        assert pool.report()['peak_writeback_jobs']==1
    finally: pool.close()


def test_prefetch_single_slot_and_complete_key(tmp_path):
    from video_ai.experiments.upscale_pipeline import PipelineConfig, UpscalePipeline
    job=job_at(tmp_path);pool=UpscalePipeline(PipelineConfig(prefetch=True))
    try:
        assert pool.prepare(job) and not pool.prepare(replace(job,frame_id=2))
        value=ready(lambda:pool.consume(job))
        assert value.job_key==job.key and value.source_bytes==b'original-source'
        assert value.graph_bytes==b'{"graph":1}'
        assert pool.prepare(job)
        assert pool.consume(replace(job,profile_sha256='c'*64)) is None
    finally:pool.close()


def test_same_size_mtime_rollback_and_write_source_drift(tmp_path):
    from video_ai.experiments.upscale_pipeline import PipelineConfig, UpscalePipeline
    job=job_at(tmp_path);path=Path(job.source['path']);stamp=path.stat()
    path.write_bytes(b'X'*job.source['bytes']);os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    pool=UpscalePipeline(PipelineConfig(prefetch=True,writeback=True))
    try:
        assert pool.prepare(job)
        assert ready(lambda:pool.consume(job)).error=='source_changed'
        assert pool.stage_output(job,dict(job.source),tmp_path/'private.part')
        result=ready(lambda:pool.finish_output(job))
        assert result.error is not None
    finally:pool.close()


def test_payload_budget_and_serial_defaults(tmp_path):
    from video_ai.experiments.upscale_pipeline import PipelineConfig, UpscalePipeline
    job=job_at(tmp_path)
    pool=UpscalePipeline(PipelineConfig())
    assert not pool.prepare(job) and not pool.stage_output(job,dict(job.source),tmp_path/'unused')
    pool.close()
    with pytest.raises(ValueError):PipelineConfig(max_prefetch_bytes=64*1024**2+1)
    with pytest.raises(ValueError):PipelineConfig(max_writeback_bytes=32*1024**2+1)
    pool=UpscalePipeline(PipelineConfig(prefetch=True,writeback=True,max_prefetch_bytes=20,max_writeback_bytes=10))
    try:
        assert not pool.prepare(job)  # source + graph exceeds 20, independently of RSS.
        assert not pool.stage_output(job,dict(job.source),tmp_path/'oversize')
        assert pool.report()['peak_payload_bytes']<=30
    finally:pool.close()


def test_workers_have_empty_context_and_no_coordinator_handles(tmp_path,monkeypatch):
    from video_ai.experiments.upscale_pipeline import PipelineConfig, UpscalePipeline
    sentinel=ContextVar('owner_proof',default=None);token=sentinel.set('private')
    owner=get_ident();seen=[];original=Path.open;job=job_at(tmp_path)
    def opened(path,*args,**kwargs):
        if get_ident()!=owner:seen.append((sentinel.get(),args[0]))
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',opened)
    pool=UpscalePipeline(PipelineConfig(prefetch=True,writeback=True))
    try:
        assert pool.prepare(job);ready(lambda:pool.consume(job))
        assert pool.stage_output(job,dict(job.source),tmp_path/'private.part')
        assert ready(lambda:pool.finish_output(job)).error is None
        assert seen and all(context is None and mode in ('rb','xb') for context,mode in seen)
        assert set(job.source)=={'path','bytes','sha256'}
    finally:pool.close();sentinel.reset(token)


def test_close_drops_late_staging_and_never_promotes(tmp_path,monkeypatch):
    import video_ai.experiments.upscale_pipeline as pipeline
    job=job_at(tmp_path);entered=Event();release=Event();original=pipeline._copy_output
    def delayed(*args):
        entered.set();release.wait(5);return original(*args)
    monkeypatch.setattr(pipeline,'_copy_output',delayed)
    pool=pipeline.UpscalePipeline(pipeline.PipelineConfig(writeback=True))
    assert pool.stage_output(job,dict(job.source),tmp_path/'private.part') and entered.wait(1)
    started=monotonic();pool.close()
    assert monotonic()-started<2.3 and pool.report()['unfinished_worker']
    release.set()
    assert pool.finish_output(job) is None
    assert not (tmp_path/'accepted.json').exists()
    assert not pool.stage_output(job,dict(job.source),tmp_path/'second.part')


def test_writeback_growth_reads_at_most_declared_plus_one(tmp_path,monkeypatch):
    import video_ai.experiments.upscale_pipeline as pipeline
    import io
    job=job_at(tmp_path);source=Path(job.source['path']);original=Path.open;counts=[];grew=[]
    class Raw(io.RawIOBase):
        def __init__(self):self.stream=original(source,'rb',buffering=0)
        def fileno(self):return self.stream.fileno()
        def read(self,n=-1):
            if not grew:
                with original(source,'ab') as stream:stream.write(b'X'*10000)
                grew.append(True)
            data=self.stream.read(n);counts.append(len(data));return data
        def close(self):self.stream.close();super().close()
    def opened(path,*args,**kwargs):
        return Raw() if path==source and args==('rb',) else original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',opened)
    pool=pipeline.UpscalePipeline(pipeline.PipelineConfig(writeback=True))
    try:
        assert pool.stage_output(job,dict(job.source),tmp_path/'private.part')
        assert ready(lambda:pool.finish_output(job)).error
        assert sum(counts)<=job.source['bytes']+1
    finally:pool.close()
