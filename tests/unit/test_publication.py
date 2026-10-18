"""TEST ONLY publication gates and same-byte durable transaction evidence."""
import json
from pathlib import Path
import pytest


@pytest.fixture
def publication_fixture(runtime_run,monkeypatch):
    from publication_helpers import make_publication_fixture,cleanup_output
    values=make_publication_fixture(runtime_run,monkeypatch)
    try:yield values
    finally:cleanup_output(values[1],values[0])


def test_missing_review_and_acceptance_preserves_pending_and_writes_diagnostic(run_store):
    from video_ai.runtime.publication import publish_candidate, PublicationRefusal
    from video_ai.config import load_config
    from video_ai.runtime.manifest import thaw
    run=run_store.run_dir
    config=load_config(Path(run_store.snapshot()['config_snapshot']['path']))
    before=run_store.snapshot()
    with pytest.raises(PublicationRefusal) as caught:
        publish_candidate(config,run_dir=run,review_path=run/'logs/validation/missing-review.json',acceptance_path=run/'logs/validation/missing-acceptance.json')
    assert run_store.snapshot()==before
    assert set(caught.value.missing_checks)>={'final_review','full_film_acceptance'}
    diagnostic=json.loads(caught.value.diagnostic_path.read_text(encoding='utf-8'))
    assert diagnostic['status']=='refused'
    assert diagnostic['missing_checks']==caught.value.missing_checks
    assert not (config.output_root/(run.name+'.mp4')).exists()


def test_foreign_run_lock_is_retained(run_store):
    from video_ai.runtime.publication import publish_candidate,PublicationRefusal
    from video_ai.config import load_config
    run=run_store.run_dir; lock=run/'.publish.lock'; lock.write_bytes(b'foreign lock')
    config=load_config(Path(run_store.snapshot()['config_snapshot']['path']))
    with pytest.raises(PublicationRefusal):
        publish_candidate(config,run_dir=run,review_path=run/'logs/validation/review.json',acceptance_path=run/'logs/validation/acceptance.json')
    assert lock.read_bytes()==b'foreign lock'
    assert run_store.snapshot()['stages']['publish']['status']=='pending'


def test_uncommitted_publication_cannot_be_consumed(run_store):
    from video_ai.runtime.publication import load_committed_publication
    with pytest.raises(ValueError,match='completed'):
        load_committed_publication(run_store.run_dir)


def test_success_preserves_bytes_and_committed_consumer(publication_fixture):
    from video_ai.runtime.publication import publish_candidate,load_committed_publication
    run,config,store,review,acceptance=publication_fixture
    result=publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance)
    assert result.published and result.passed and not result.staging_only
    report=load_committed_publication(run)
    assert result.output_video_path.read_bytes()==Path(report['accepted_candidate_identity']['path']).read_bytes()
    assert result.output_subtitle_path.read_bytes()==Path(report['accepted_subtitle_identity']['path']).read_bytes()
    assert store.snapshot()['stages']['publish']['status']=='completed'
    assert set(store.snapshot()['workflows'])>={'publication_report','final_review','full_film_acceptance'}


def test_new_process_reconstructs_committed_fixture(publication_fixture):
    import subprocess
    import sys
    run,config,store,review,acceptance=publication_fixture
    from video_ai.runtime.publication import publish_candidate
    result=publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance)
    assert result.published
    code="""import sys
from pathlib import Path
sys.path.insert(0,sys.argv[2])
from publication_helpers import fixture_upstream
from video_ai.runtime import candidate_checks
candidate_checks.load_committed_composition=fixture_upstream
from video_ai.runtime.publication import load_committed_publication
report=load_committed_publication(Path(sys.argv[1]))
assert report['published'] is True
assert report['validation']['full_film_acceptance']=='passed'
print('TEST ONLY committed publication reconstructed in fresh process')
"""
    process=subprocess.run([sys.executable,'-B','-c',code,str(run),str(Path(__file__).resolve().parents[1])],cwd=run,capture_output=True,text=True,timeout=300)
    assert process.returncode==0,process.stderr
    assert 'TEST ONLY committed publication reconstructed' in process.stdout


@pytest.mark.parametrize('extension',['.mp4','.srt','.publication.json','lock'])
def test_existing_output_or_foreign_lock_refuses_without_copy(publication_fixture,extension):
    from video_ai.runtime.publication import publish_candidate,PublicationRefusal
    run,config,store,review,acceptance=publication_fixture
    path=config.output_root/('.'+run.name+'.publish.lock' if extension=='lock' else run.name+extension)
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'foreign bytes')
    before=store.snapshot()
    with pytest.raises(PublicationRefusal):publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance)
    assert path.read_bytes()==b'foreign bytes'
    assert store.snapshot()==before


def test_capacity_refusal_leaves_no_media(publication_fixture,monkeypatch):
    from video_ai.runtime import publication
    from collections import namedtuple
    run,config,store,review,acceptance=publication_fixture
    monkeypatch.setattr(publication.shutil,'disk_usage',lambda path:namedtuple('Usage','total used free')(1,1,0))
    with pytest.raises(publication.PublicationRefusal,match='capacity'):
        publication.publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance)
    assert store.snapshot()['stages']['publish']['status']=='pending'
    assert not (config.output_root/(run.name+'.mp4')).exists()


@pytest.mark.parametrize('file',['candidate.mp4','subtitle.srt','review','acceptance','pcm','config','marker','report'])
def test_committed_consumer_rejects_every_bound_file_drift(publication_fixture,file):
    from video_ai.runtime.publication import publish_candidate,load_committed_publication
    from video_ai.config import read_json
    run,config,store,review,acceptance=publication_fixture
    result=publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance)
    assert result.published
    candidate=read_json(run/'candidate-validation.json')
    paths={'candidate.mp4':run/'staging/composition/candidate.mp4','subtitle.srt':run/'staging/composition/subtitle.srt',
           'review':review,'acceptance':acceptance,'pcm':Path(next(v['path'] for k,v in candidate['input_identities'].items() if k.startswith('pcm/'))),
           'config':config.config_file,'marker':result.output_video_path.with_suffix('.publication.json'),'report':run/'publication.json'}
    with paths[file].open('ab') as stream:stream.write(b'\nTEST ONLY drift')
    with pytest.raises((ValueError,OSError)):load_committed_publication(run)


@pytest.mark.parametrize('kind',['write','interrupt','source_drift','review_drift','pcm_drift','nested_drift','frame_drift'])
def test_copy_failure_and_commit_drift_preserve_partial_files(publication_fixture,monkeypatch,kind):
    from video_ai.runtime import publication
    from video_ai.config import read_json
    run,config,store,review,acceptance=publication_fixture
    real_copy=publication.copy_bytes;real_json=publication.atomic_json
    video=config.output_root/(run.name+'.mp4')
    if kind in ('write','interrupt','source_drift','review_drift'):
        def copy(run_dir,record,target):
            if target.suffix=='.mp4':
                if kind in ('write','interrupt'):
                    with target.open('xb') as stream:stream.write(b'TEST ONLY partial')
                    if kind=='interrupt':raise KeyboardInterrupt()
                    raise OSError('TEST ONLY disk write failure')
                value=real_copy(run_dir,record,target)
                path=Path(record['path']) if kind=='source_drift' else review
                with path.open('ab') as stream:stream.write(b'TEST ONLY mutation after copy')
                return value
            return real_copy(run_dir,record,target)
        monkeypatch.setattr(publication,'copy_bytes',copy)
    else:
        def json_write(path,data,**kw):
            value=real_json(path,data,**kw)
            if path==run/'publication.json':
                candidate=read_json(run/'candidate-validation.json')
                if kind=='frame_drift':pcm=Path(read_json(run/'composition.json')['frame_mappings'][0]['contributors'][0]['frame_identity']['path'])
                elif kind=='nested_drift':pcm=Path(candidate['requirement_bindings'][0]['actual_artifact']['path'])
                else:pcm=Path(next(v['path'] for k,v in candidate['input_identities'].items() if k.startswith('pcm/')))
                with pcm.open('ab') as stream:stream.write(b'TEST ONLY late PCM drift')
            return value
        monkeypatch.setattr(publication,'atomic_json',json_write)
    if kind=='interrupt':
        with pytest.raises(KeyboardInterrupt):publication.publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance)
    else:
        result=publication.publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance)
        assert not result.published and result.status=='failed'
    assert video.exists()
    assert store.snapshot()['stages']['publish']['status']==('interrupted' if kind=='interrupt' else 'failed')
    with pytest.raises(ValueError,match='completed'):publication.load_committed_publication(run)
    retained=video.read_bytes()
    with pytest.raises(publication.PublicationRefusal):publication.publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance)
    assert video.read_bytes()==retained


@pytest.mark.parametrize('path',['D:/code/py/video-ai/not-allowed.mp4','C:/not-allowed.mp4','D:/VideoSi/output/video-ai/name:stream.mp4','//server/share/output.mp4','D:/VideoSi/output/video-ai/bad. /candidate.mp4'])
def test_output_path_policy_refuses_without_stage_start(publication_fixture,path):
    from video_ai.runtime.publication import publish_candidate,PublicationRefusal
    run,config,store,review,acceptance=publication_fixture
    with pytest.raises(PublicationRefusal):publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance,output_path=Path(path))
    assert store.snapshot()['stages']['publish']['status']=='pending'


def test_external_author_path_is_not_read(run_store,tmp_path):
    from video_ai.runtime.publication import publish_candidate,PublicationRefusal
    from video_ai.config import load_config
    run=run_store.run_dir;config=load_config(Path(run_store.snapshot()['config_snapshot']['path']))
    author=tmp_path/'external.json';author.write_bytes(b'invalid JSON must not be read')
    with pytest.raises(PublicationRefusal):
        publish_candidate(config,run_dir=run,review_path=author,acceptance_path=run/'logs/validation/acceptance.json')


@pytest.mark.parametrize('phase',['marker','report','manifest'])
def test_commit_failure_never_advertises_completed(publication_fixture,monkeypatch,phase):
    from video_ai.runtime import publication
    run,config,store,review,acceptance=publication_fixture
    real_json=publication.atomic_json;real_update=publication.ManifestStore.update
    def write(path,data,**kw):
        if (phase=='marker' and path.suffixes[-2:]==['.publication','.json']) or (phase=='report' and path==run/'publication.json'):raise OSError('TEST ONLY commit write failure')
        return real_json(path,data,**kw)
    def update(self,fn):
        if phase=='manifest' and fn.__name__=='commit':raise OSError('TEST ONLY manifest completion failure')
        return real_update(self,fn)
    monkeypatch.setattr(publication,'atomic_json',write);monkeypatch.setattr(publication.ManifestStore,'update',update)
    result=publication.publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance)
    assert not result.published and result.status=='failed'
    assert result.output_video_path.exists() and result.output_subtitle_path.exists()
    assert store.snapshot()['stages']['publish']['status']=='failed'
    with pytest.raises(ValueError):publication.load_committed_publication(run)


def test_same_stem_concurrency_and_case_alias_keep_second_run_pending(publication_fixture,runtime_run,monkeypatch):
    from threading import Event,Thread
    from publication_helpers import make_publication_fixture,cleanup_output
    from video_ai.runtime import publication
    from video_ai.runtime.paths import create_run,RuntimePaths
    run,config,store,review,acceptance=publication_fixture
    paths=RuntimePaths.from_config(config)
    second=make_publication_fixture((create_run(paths),runtime_run[1],paths),monkeypatch)
    other,other_config,other_store,other_review,other_acceptance=second
    entered=Event();release=Event();results=[];errors=[];real_copy=publication.copy_bytes
    def copy(run_dir,record,target):
        if run_dir==run and target.suffix=='.mp4':
            entered.set()
            if not release.wait(30):raise OSError('TEST ONLY concurrency coordination timeout')
        return real_copy(run_dir,record,target)
    monkeypatch.setattr(publication,'copy_bytes',copy)
    def first():
        try:results.append(publication.publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance))
        except BaseException as exc:errors.append(exc)
    thread=Thread(target=first);thread.start()
    try:
        assert entered.wait(30)
        # Windows spelling differs only in stem case; the same output lock is held.
        alias=config.output_root/(run.name.upper()+'.mp4')
        with pytest.raises(publication.PublicationRefusal,match='lock'):
            publication.publish_candidate(other_config,run_dir=other,review_path=other_review,acceptance_path=other_acceptance,output_path=alias)
        assert other_store.snapshot()['stages']['publish']['status']=='pending'
    finally:
        release.set();thread.join(30);cleanup_output(other_config,other)
    assert not thread.is_alive() and not errors
    assert results[0].published
    assert publication.load_committed_publication(run)['published'] is True


def test_marker_missing_blocks_completed_consumer(publication_fixture):
    from video_ai.runtime.publication import publish_candidate,load_committed_publication
    run,config,store,review,acceptance=publication_fixture
    result=publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance)
    result.output_video_path.with_suffix('.publication.json').unlink()
    with pytest.raises((ValueError,OSError)):load_committed_publication(run)


def test_stale_acceptance_collection_refuses_without_output(publication_fixture):
    from video_ai.runtime.publication import publish_candidate,PublicationRefusal
    from video_ai.config import read_json
    from candidate_helpers import write
    run,config,store,review,acceptance=publication_fixture
    data=read_json(acceptance);data['review_collection_identities'].pop(next(k for k in data['review_collection_identities'] if 'observations' in k))
    write(acceptance,data)
    with pytest.raises(PublicationRefusal):publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance)
    assert store.snapshot()['stages']['publish']['status']=='pending'
    assert not (config.output_root/(run.name+'.mp4')).exists()


def test_missing_acceptance_after_candidate_completed_preserves_validation(publication_fixture):
    from video_ai.runtime.publication import publish_candidate,PublicationRefusal
    run,config,store,review,acceptance=publication_fixture
    acceptance.unlink();before=store.snapshot()
    with pytest.raises(PublicationRefusal) as caught:publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance)
    assert caught.value.missing_checks==['full_film_acceptance']
    assert store.snapshot()==before
    assert before['stages']['validation']['status']=='completed'


def test_redirected_output_parent_refuses_without_external_copy(publication_fixture,tmp_path):
    import subprocess
    from video_ai.runtime.publication import publish_candidate,PublicationRefusal
    run,config,store,review,acceptance=publication_fixture
    junction=config.output_root/('TEST-ONLY-redirect-'+run.name)
    target=tmp_path/'redirect-target';target.mkdir()
    quote=lambda path:"'"+str(path).replace("'","''")+"'"
    command=['powershell.exe','-NoProfile','-Command',f"New-Item -ItemType Junction -Path {quote(junction)} -Target {quote(target)} | Out-Null"]
    # Windows native junctions do not require elevated symlink privilege.
    process=subprocess.run(command,capture_output=True,text=True,timeout=30)
    assert process.returncode==0,process.stderr
    try:
        with pytest.raises(PublicationRefusal):publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance,output_path=junction/'candidate.mp4')
        assert not list(target.iterdir())
        assert store.snapshot()['stages']['publish']['status']=='pending'
    finally:
        # Remove only this explicitly test-created link, without recursion.
        junction.unlink() if junction.is_symlink() else junction.rmdir()


@pytest.mark.parametrize('kind',['copy','gate','alias'])
def test_refreshed_receipts_cannot_hide_forged_transaction_evidence(publication_fixture,kind):
    from video_ai.runtime.publication import publish_candidate,load_committed_publication
    from video_ai.runtime.manifest import hash_file,thaw
    from video_ai.config import read_json
    from candidate_helpers import write
    run,config,store,review,acceptance=publication_fixture
    assert publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance).published
    report=read_json(run/'publication.json')
    if kind in ('copy','gate'):
        name=next(k for k in report['request_evidence'] if k.startswith('logs/publication/'+kind+'-'))
        data=read_json(run/name)
        if kind=='copy':data['copied_bytes']+=1
        else:data['validation']['actual_final_video_sync']='unverified'
        write(run/name,data);report['request_evidence'][name]=thaw(hash_file(run/name))
    else:
        name=next(k for k in report['request_evidence'] if k.startswith('logs/publication/copy-'))
        report['request_evidence'][name.replace('logs/publication/','logs/publication//')]=report['request_evidence'].pop(name)
    write(run/'publication.json',report)
    identity=thaw(hash_file(run/'publication.json'))
    # An attacker edits disk directly: the legitimate ManifestStore correctly
    # refuses replacing a terminal artifact, so do not bypass it with an API.
    data=store.snapshot();data['workflows']['publication_report']=identity
    artifact=dict(identity);artifact.pop('mtime_ns');artifact['category']='run'
    data['stages']['publish']['artifacts'][2]=artifact
    write(run/'manifest.json',data)
    with pytest.raises((ValueError,OSError)):load_committed_publication(run)


@pytest.mark.parametrize('kind',['run','output'])
def test_replaced_lock_owner_refuses_commit_and_retains_foreign_lock(publication_fixture,monkeypatch,kind):
    from video_ai.runtime import publication
    run,config,store,review,acceptance=publication_fixture
    lock=run/'.publish.lock' if kind=='run' else config.output_root/('.'+run.name+'.publish.lock')
    real_copy=publication.copy_bytes
    def copy(run_dir,record,target):
        value=real_copy(run_dir,record,target)
        if target.suffix=='.mp4':lock.write_bytes(b'TEST ONLY foreign replacement lock')
        return value
    monkeypatch.setattr(publication,'copy_bytes',copy)
    result=publication.publish_candidate(config,run_dir=run,review_path=review,acceptance_path=acceptance)
    assert not result.published
    assert lock.read_bytes()==b'TEST ONLY foreign replacement lock'
    assert store.snapshot()['stages']['publish']['status']=='failed'
    assert result.output_video_path.exists()
