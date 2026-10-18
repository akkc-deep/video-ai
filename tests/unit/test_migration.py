import hashlib
from pathlib import Path
import shutil
from uuid import uuid4
import pytest


@pytest.fixture
def copies(tmp_path, runtime_run):
    from video_ai.runtime.migration import CopyEntry
    from video_ai.runtime.logging import RunLogger
    source = tmp_path / 'source.bin'
    source.write_bytes(b'actual source content')
    target = Path('D:/VideoSi/tools/tests') / uuid4().hex / 'copy.bin'
    return CopyEntry(source, target, 'tool-env', source.stat().st_size, None), RunLogger(runtime_run[0])


def test_copy_verified_identity_and_idempotence(copies):
    from video_ai.runtime.migration import copy_verified
    entry, logger = copies
    result = copy_verified(entry, logger=logger)
    assert result.sha256 == hashlib.sha256(entry.source.read_bytes()).hexdigest()
    assert entry.target.read_bytes() == entry.source.read_bytes()
    old_mtime = entry.target.stat().st_mtime_ns
    assert copy_verified(entry, logger=logger).sha256 == result.sha256
    assert entry.target.stat().st_mtime_ns == old_mtime


def test_conflict_never_overwrites_target(copies):
    from video_ai.runtime.migration import copy_verified
    entry, logger = copies
    entry.target.parent.mkdir(parents=True)
    entry.target.write_bytes(b'keep user file')
    with pytest.raises(FileExistsError):
        copy_verified(entry, logger=logger)
    assert entry.target.read_bytes() == b'keep user file'


def test_copy_rejects_source_drift(copies):
    from video_ai.runtime.migration import copy_verified
    entry, logger = copies
    entry.source.write_bytes(b'changed size')
    with pytest.raises(OSError, match='changed'):
        copy_verified(entry, logger=logger)
    assert not entry.target.exists()


def test_copy_rejects_inventory_digest_drift(copies):
    from dataclasses import replace
    from video_ai.runtime.migration import copy_verified
    entry, logger = copies
    with pytest.raises(OSError, match='SHA256'):
        copy_verified(replace(entry, source_sha256='0'*64), logger=logger)
    assert not entry.target.exists()


def test_target_category_enforced(copies):
    from dataclasses import replace
    from video_ai.runtime.migration import copy_verified
    entry, logger = copies
    with pytest.raises(ValueError):
        copy_verified(replace(entry,target=entry.source),logger=logger)


def test_capacity_rejects_insufficient_space(copies, monkeypatch):
    import video_ai.runtime.migration as module
    entry, _ = copies
    monkeypatch.setattr(module.shutil,'disk_usage',lambda p:shutil._ntuple_diskusage(100,99,1))
    report = module.check_capacity((entry,),reserve_bytes=20*1024**3)
    assert not report['passed']
    assert report['copy_bytes'] == entry.bytes
    assert report['temporary_peak_bytes'] == entry.bytes
    assert report['required_bytes'] > 20*1024**3


def test_migration_report_preserves_completed_on_later_conflict(copies):
    from dataclasses import replace
    from video_ai.runtime.migration import migrate
    entry, logger = copies
    conflict=replace(entry,target=entry.target.with_name('z.bin'))
    conflict.target.parent.mkdir(parents=True)
    conflict.target.write_bytes(b'conflict')
    result=migrate((entry,conflict),logger=logger,report_path=logger.run_dir/'migration.json')
    assert result['passed'] is False
    assert result['counts']['verified'] == 1 and result['counts']['conflict'] == 1
    assert entry.target.read_bytes()==entry.source.read_bytes()


def test_interrupt_keeps_verified_copy_and_propagates(copies,monkeypatch):
    import video_ai.runtime.migration as module
    entry,logger=copies
    def interrupted(*a,**k): raise KeyboardInterrupt
    monkeypatch.setattr(module,'copy_verified',interrupted)
    with pytest.raises(KeyboardInterrupt):
        module.migrate((entry,),logger=logger,report_path=logger.run_dir/'migration.json')


def test_atomic_report_retries_windows_reader_sharing_violation(copies,monkeypatch):
    import json
    import video_ai.runtime.migration as module
    _,logger=copies
    original=module.os.replace
    attempts=[]
    def held_once(source,target):
        attempts.append(1)
        if len(attempts)==1:
            failure=PermissionError('temporary Windows reader sharing violation')
            failure.winerror=32
            raise failure
        return original(source,target)
    monkeypatch.setattr(module.os,'replace',held_once)
    report=logger.run_dir/'sharing.json'
    module.atomic_report(report,{'passed':True})
    assert json.loads(report.read_text())['passed'] is True
    assert len(attempts)==2


def test_directory_enumeration_failure_is_not_silently_skipped(copies,monkeypatch):
    import video_ai.runtime.migration as module
    entry,_=copies
    def unreadable(root,**kwargs):
        kwargs['onerror'](PermissionError('source subtree unreadable'))
        yield str(root),[],[]
    monkeypatch.setattr(module.os,'walk',unreadable)
    with pytest.raises(PermissionError,match='unreadable'):
        list(module.scan_files(entry.source.parent))
