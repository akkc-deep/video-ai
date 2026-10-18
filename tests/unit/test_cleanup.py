import json
import pytest
from video_ai.runtime.manifest import hash_file, thaw


def test_cleanup_only_registered_ephemeral_unreferenced_files(runtime_run):
    from video_ai.runtime.cleanup import create_owned_temporary, cleanup_owned_temporaries
    run, _, _ = runtime_run
    temporary = run/'ephemeral.tmp'; own=create_owned_temporary(run,temporary,b'ours')
    retained = run/'retained.tmp'; keep=create_owned_temporary(run,retained,b'review input')
    foreign = run/'foreign.tmp'; foreign.write_bytes(b'foreign')
    registrations = [own,keep]
    removed = cleanup_owned_temporaries(run, registrations, referenced=(hash_file(retained),))
    assert tuple(removed) == (temporary,)
    assert retained.read_bytes() == b'review input' and foreign.read_bytes() == b'foreign'


def test_cleanup_drift_and_permanent_reports_are_preserved(runtime_run):
    from video_ai.runtime.cleanup import create_owned_temporary, cleanup_owned_temporaries
    run, _, _ = runtime_run
    path = run/'ephemeral.tmp'; registration=create_owned_temporary(run,path,b'before')
    path.write_bytes(b'after')
    with pytest.raises((ValueError, OSError)): cleanup_owned_temporaries(run, [registration])
    assert path.read_bytes() == b'after'
    path = run/'segments.json'; registration=create_owned_temporary(run,path,b'permanent')
    with pytest.raises(ValueError): cleanup_owned_temporaries(run, [registration])
    assert path.read_bytes() == b'permanent'


def test_lock_owner_replacement_is_retained(runtime_run):
    from video_ai.runtime.pipeline_evidence import exclusive, check_lock
    run, _, _ = runtime_run
    with exclusive(run) as owner:
        (run/'.pipeline.lock').write_text(json.dumps(dict(pid=1, token='foreign')), encoding='utf-8')
        with pytest.raises(ValueError): check_lock(run, owner)
    assert json.loads((run/'.pipeline.lock').read_text(encoding='utf-8'))['token'] == 'foreign'


def test_preexisting_foreign_file_and_directory_cannot_be_claimed(runtime_run):
    from video_ai.runtime.cleanup import OwnedTemporary,cleanup_owned_temporaries
    run,_,_=runtime_run
    foreign=run/'foreign.tmp';foreign.write_bytes(b'foreign')
    directory=run/'foreign-empty';directory.mkdir()
    with pytest.raises(ValueError):cleanup_owned_temporaries(run,[OwnedTemporary(hash_file(foreign),True)])
    with pytest.raises(ValueError):cleanup_owned_temporaries(run,[],created_directories=[directory])
    assert foreign.read_bytes()==b'foreign' and directory.is_dir()


def test_implicit_manifest_reference_protects_owned_new_file(run_store):
    from video_ai.runtime.cleanup import create_owned_temporary,cleanup_owned_temporaries
    store=run_store;run=store.run_dir
    owned=create_owned_temporary(run,run/'owned.tmp',b'author evidence')
    report=run/'author.json';report.write_text(json.dumps({'evidence_identity':thaw(owned.identity)}),encoding='utf-8')
    store.update(lambda data:data['workflows'].update(author=thaw(hash_file(report))))
    assert cleanup_owned_temporaries(run,[owned])==()
    assert (run/'owned.tmp').read_bytes()==b'author evidence'


@pytest.mark.parametrize('place',['source','parent','model','c_drive','unc','ads'])
def test_cleanup_refuses_other_roots_and_stream_paths(runtime_run,place):
    from pathlib import Path
    from video_ai.runtime.cleanup import OwnedTemporary,cleanup_owned_temporaries
    from video_ai.runtime.manifest import FileIdentity
    run,config,paths=runtime_run
    if place=='source':path=Path(__file__).resolve()
    elif place=='parent':path=run.parent/'outside.tmp'
    elif place=='model':path=config.models['upscale']
    elif place=='c_drive':path=Path('C:/Windows/System32/cmd.exe')
    elif place=='unc':path=Path('//server/share/file.tmp')
    else:path=Path(str(run/'ephemeral.tmp')+':foreign')
    before=path.read_bytes() if place not in ('unc','ads') and path.is_file() else None
    identity=hash_file(path) if before is not None else FileIdentity(str(path),1,1,'a'*64,'2026-01-01T00:00:00+00:00')
    with pytest.raises((ValueError,OSError)):cleanup_owned_temporaries(run,[OwnedTemporary(identity,True)])
    if before is not None:assert path.read_bytes()==before
