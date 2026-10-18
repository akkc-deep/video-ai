from pathlib import Path
import pytest
from delivery_helpers import delivery_case


@pytest.mark.parametrize('role,point',[(r,p) for r in ('movie','subtitle','receipt') for p in ('pending','created','copied','renamed','published')]+[('receipt','completed')])
def test_every_publish_boundary_resumes_without_overwrite(runtime_run,monkeypatch,role,point):
    import video_ai.runtime.production_delivery as module
    from video_ai.runtime.production_state import ArtifactStamp
    run,frozen,_,p=delivery_case(runtime_run)
    fired=[]
    def interrupt(event,current):
        if not fired and (event,current)==(point,role):
            fired.append(True);raise KeyboardInterrupt('delivery boundary')
    monkeypatch.setattr(module,'boundary',interrupt)
    with module.OutputLock(run,frozen.options['output_paths']['movie']) as lock:
        with pytest.raises(KeyboardInterrupt):module.publish_delivery(frozen,run,lock)
    before={key:ArtifactStamp.read(value) for key,value in frozen.options['output_paths'].items() if Path(value).exists()}
    monkeypatch.setattr(module,'boundary',lambda *args:None)
    with module.OutputLock(run,frozen.options['output_paths']['movie']) as lock:
        receipt=module.publish_delivery(frozen,run,lock)
    assert fired and receipt['human_review']=='unverified'
    for key,stamp in before.items():assert ArtifactStamp.read(frozen.options['output_paths'][key])==stamp
    assert Path(receipt['movie']['path']).read_bytes()==Path(p['candidate']['path']).read_bytes()


def test_unregistered_temporary_is_retained_and_refused(runtime_run,monkeypatch):
    import video_ai.runtime.production_delivery as module
    from video_ai.config import read_json
    run,frozen,_,_=delivery_case(runtime_run)
    with module.OutputLock(run,frozen.options['output_paths']['movie']) as lock:
        tx=module.new_transaction(frozen,run,lock);module.save_transaction(run,tx,lock,initial=True)
        unknown=Path(tx['operations']['movie']['temp_path']);unknown.write_bytes(b'unknown partial')
        with pytest.raises(ValueError):module.publish_delivery(frozen,run,lock)
    assert unknown.read_bytes()==b'unknown partial'


def test_archive_rename_before_cursor_resumes_from_original_file_id(runtime_run,monkeypatch):
    import video_ai.runtime.production_delivery as module
    run,frozen,_,_=delivery_case(runtime_run)
    def interrupt(point,role):
        if (point,role)==('created','movie'):raise KeyboardInterrupt('created')
    monkeypatch.setattr(module,'boundary',interrupt)
    with module.OutputLock(run,frozen.options['output_paths']['movie']) as lock:
        with pytest.raises(KeyboardInterrupt):module.publish_delivery(frozen,run,lock)
    def archive_interrupt(point,role):
        if point=='archived':raise KeyboardInterrupt('archived')
    monkeypatch.setattr(module,'boundary',archive_interrupt)
    with module.OutputLock(run,frozen.options['output_paths']['movie']) as lock:
        with pytest.raises(KeyboardInterrupt):module.publish_delivery(frozen,run,lock)
    monkeypatch.setattr(module,'boundary',lambda *args:None)
    with module.OutputLock(run,frozen.options['output_paths']['movie']) as lock:module.publish_delivery(frozen,run,lock)
    from video_ai.config import read_json
    tx=read_json(run/'production/delivery.json')
    assert len(tx['operations']['movie']['archives'])==1


@pytest.mark.parametrize('change',['source','published_stamp','same_bytes_foreign_inode'])
def test_recorded_source_or_official_file_changes_refuse_without_recopy(runtime_run,monkeypatch,change):
    import os
    import video_ai.runtime.production_delivery as module
    run,frozen,_,p=delivery_case(runtime_run)
    with module.OutputLock(run,frozen.options['output_paths']['movie']) as lock:module.publish_delivery(frozen,run,lock)
    target=Path(p['candidate']['path'] if change=='source' else frozen.options['output_paths']['movie'])
    before=target.stat();raw=target.read_bytes()
    if change=='same_bytes_foreign_inode':
        target.rename(target.with_suffix('.preserved'))
        target.write_bytes(raw);os.utime(target,ns=(before.st_atime_ns,before.st_mtime_ns))
    else:target.write_bytes(raw+b'changed')
    monkeypatch.setattr(module,'copy_media',lambda *args:pytest.fail('completed file recopied'))
    with module.OutputLock(run,frozen.options['output_paths']['movie']) as lock:
        with pytest.raises(ValueError):module.publish_delivery(frozen,run,lock)
