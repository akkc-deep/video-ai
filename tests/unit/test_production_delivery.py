from pathlib import Path
import pytest
from delivery_helpers import delivery_case


def test_actual_bytes_published_once_and_completed_transaction_frozen(runtime_run,monkeypatch):
    from video_ai.runtime.production_delivery import OutputLock, publish_delivery
    from video_ai.runtime.production_state import ArtifactStamp
    run,frozen,_,p=delivery_case(runtime_run)
    with OutputLock(run,frozen.options['output_paths']['movie']) as lock:
        receipt=publish_delivery(frozen,run,lock)
    assert Path(receipt['movie']['path']).read_bytes()==Path(p['candidate']['path']).read_bytes()
    assert Path(receipt['subtitle']['path']).read_bytes()==Path(p['subtitle']['path']).read_bytes()
    assert Path(receipt['movie']['path']).stat().st_ino!=Path(p['candidate']['path']).stat().st_ino
    before=ArtifactStamp.read(run/'production/delivery.json')
    import video_ai.runtime.production_delivery as module
    monkeypatch.setattr(module,'copy_media',lambda *args:pytest.fail('completed copy repeated'))
    with OutputLock(run,frozen.options['output_paths']['movie']) as lock:
        assert publish_delivery(frozen,run,lock)==receipt
    assert ArtifactStamp.read(run/'production/delivery.json')==before


@pytest.mark.parametrize('role',['movie','subtitle','receipt','marker'])
def test_foreign_target_preserved_without_copy(runtime_run,role,monkeypatch):
    import video_ai.runtime.production_delivery as module
    run,frozen,_,_=delivery_case(runtime_run)
    path=Path(frozen.options['output_paths']['movie']).with_suffix('.publication.json') if role=='marker' else Path(frozen.options['output_paths'][role])
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'foreign')
    monkeypatch.setattr(module,'copy_media',lambda *args:pytest.fail('foreign target copied'))
    with module.OutputLock(run,frozen.options['output_paths']['movie']) as lock:
        with pytest.raises(ValueError):module.publish_delivery(frozen,run,lock)
    assert path.read_bytes()==b'foreign'


def test_progress_goes_to_stderr_and_records_frame_total_elapsed(runtime_run,capsys):
    from video_ai.runtime.logging import RunLogger
    run,_,_=runtime_run
    logger=RunLogger(run,production=True)
    logger.progress('upscale','shot_0001',frame=2,total=4)
    captured=capsys.readouterr()
    assert captured.out=='' and '2/4' in captured.err and 'elapsed=' in captured.err
    from video_ai.config import read_json
    import json
    event=json.loads(logger.path('events.jsonl').read_text(encoding='utf-8').splitlines()[-1])
    assert event['details']['frame']==2 and event['details']['total']==4 and event['details']['elapsed_seconds']>=0


@pytest.mark.parametrize('mode',['live','reused','missing_intent','foreign_run','foreign_token','guard'])
def test_output_lock_refuses_unproven_owner_and_preserves_file(runtime_run,monkeypatch,mode):
    import video_ai.runtime.production_delivery as module
    from video_ai.runtime.production_state import write_exclusive
    from video_ai.config import read_json
    run,frozen,_,_=delivery_case(runtime_run)
    lock=module.OutputLock(run,frozen.options['output_paths']['movie'])
    lock.path.parent.mkdir(parents=True,exist_ok=True)
    owner=dict(lock.owner)
    if mode=='foreign_run':owner['run_id']='foreign'
    if mode=='foreign_token':owner['token']='0'*32
    write_exclusive(lock.path,owner)
    if mode!='missing_intent':write_exclusive(lock.intent_path,dict(owner=lock.owner,lock_path=str(lock.path),created_at=__import__('video_ai.runtime.manifest',fromlist=['now']).now()))
    if mode=='reused':monkeypatch.setattr(module,'process_started_at',lambda pid:'123')
    if mode=='guard':write_exclusive(lock.path.with_name('.'+lock.movie.stem+'.make-video-reclaim.lock'),{'foreign':True})
    before=lock.path.read_bytes()
    with pytest.raises(ValueError):
        with module.OutputLock(run,lock.movie):pytest.fail('unproven lock acquired')
    assert lock.path.read_bytes()==before


def test_proven_dead_output_lock_reclaimed_with_original_intent(runtime_run,monkeypatch):
    import video_ai.runtime.production_delivery as module
    from video_ai.runtime.production_state import write_exclusive
    from video_ai.runtime.manifest import now
    run,frozen,_,_=delivery_case(runtime_run)
    lock=module.OutputLock(run,frozen.options['output_paths']['movie']);owner=dict(lock.owner,pid=987654321)
    write_exclusive(lock.intent_path,dict(owner=owner,lock_path=str(lock.path),created_at=now()))
    write_exclusive(lock.path,owner)
    real=module.process_started_at
    monkeypatch.setattr(module,'process_started_at',lambda pid:None if pid==987654321 else real(pid))
    with module.OutputLock(run,lock.movie) as fresh:assert fresh.owner['token']!=owner['token']
    assert list((run/'logs/production/delivery/reclaims').glob('*.json'))


@pytest.mark.parametrize('cause',['copy','fsync','space'])
def test_delivery_io_failure_preserves_original_sources(runtime_run,monkeypatch,cause):
    import video_ai.runtime.production_delivery as module
    from video_ai.runtime.production_state import ArtifactStamp
    run,frozen,_,p=delivery_case(runtime_run)
    before=ArtifactStamp.read(p['candidate']['path'])
    with module.OutputLock(run,frozen.options['output_paths']['movie']) as lock:
        def fail(*args):raise OSError('injected I/O')
        if cause=='copy':monkeypatch.setattr(module,'copy_media',fail)
        elif cause=='fsync':monkeypatch.setattr(module.os,'fsync',fail)
        else:
            from types import SimpleNamespace
            monkeypatch.setattr(module.shutil,'disk_usage',lambda *args:SimpleNamespace(free=0))
        with pytest.raises(OSError):module.publish_delivery(frozen,run,lock)
        monkeypatch.undo()
    assert ArtifactStamp.read(p['candidate']['path'])==before
    assert not Path(frozen.options['output_paths']['receipt']).exists()


def test_lock_cleanup_preserves_original_interrupt(runtime_run):
    import video_ai.runtime.production_delivery as module
    run,frozen,_,_=delivery_case(runtime_run)
    with pytest.raises(KeyboardInterrupt,match='original'):
        with module.OutputLock(run,frozen.options['output_paths']['movie']) as lock:
            lock.path.write_bytes(b'foreign replacement');raise KeyboardInterrupt('original')
    assert lock.path.read_bytes()==b'foreign replacement'


@pytest.mark.parametrize('mode',['deleted','token'])
def test_delivery_detects_lost_held_run_lock(runtime_run,mode):
    from video_ai.runtime.production_state import RunLock,write_exclusive
    import video_ai.runtime.production_delivery as module
    run,frozen,_,_=delivery_case(runtime_run)
    with RunLock(run) as owner:
        with module.OutputLock(run,frozen.options['output_paths']['movie']) as lock:
            original=owner.path.read_bytes()
            if mode=='deleted':owner.path.unlink()
            else:
                import json
                owner.path.write_text(json.dumps(dict(owner.owner,token='0'*32)),encoding='utf-8')
            try:
                with pytest.raises(ValueError):lock.check()
            finally:owner.path.write_bytes(original)
