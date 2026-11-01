"""Continuity admission uses explicit evidence; fixtures never claim real playback."""
from types import SimpleNamespace
import pytest


def test_accepted_video_does_not_admit_missing_current_diagnostic(runtime_run, tmp_path, monkeypatch):
    from scene_pipeline_helpers import prepared_pipeline
    from video_ai.runtime import scene_continuity_records as records
    from video_ai.runtime.production_state import ProductionRefused
    from dataclasses import replace
    from video_ai.runtime.manifest import thaw
    setup = prepared_pipeline(runtime_run, tmp_path, monkeypatch)
    raw = thaw(setup['frozen'].config.raw)
    raw['scene_continuity'] = {'schema_version': 1, 'policy': 'advisory_v1'}
    frozen = replace(setup['frozen'], config=replace(setup['frozen'].config, raw=raw))
    # The old video observation validator is deliberately outside overlay admission.
    submissions = []
    monkeypatch.setattr('video_ai.adapters.scene_comfy.SceneComfyClient.submit',
                        lambda *args, **kwargs: submissions.append(args))
    with pytest.raises(ProductionRefused):
        records.require_scene_continuity_acceptance(frozen, setup['units'], setup['timeline'],
                                                   clip_id=setup['plan']['clips'][0]['clip_id'])
    assert submissions == []


def test_legacy_progress_does_not_import_numerics_or_touch_directory(runtime_run):
    from video_ai.runtime.scene_continuity_records import load_scene_continuity_progress
    run, config, _ = runtime_run
    frozen = SimpleNamespace(config=config, options={'run_id': run.name, 'script_path': str(run/'production/script.txt')})
    before = set(run.rglob('*'))
    assert load_scene_continuity_progress(frozen, {}, None) == dict(
        schema_version=1, run_id=run.name, policy=None, current_epoch=None, clips=[], ready=None)
    assert set(run.rglob('*')) == before


@pytest.fixture
def epoch_setup(runtime_run, monkeypatch):
    from dataclasses import replace
    from video_ai.runtime.manifest import thaw, hash_file
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.runtime._scene_continuity_io import artifact
    from image_selection_helpers import save
    run, config, paths = runtime_run
    raw=thaw(config.raw);raw['scene_continuity']=dict(schema_version=1,policy='advisory_v1')
    policy=save(run/'production/scene-continuity/policy.json',raw['scene_continuity'])
    options=dict(run_id=run.name,script_path=str(run/'production/script.txt'),
        execution_policy={'input_identities':{'scene_continuity_policy':thaw(hash_file(policy))}})
    frozen=SimpleNamespace(config=replace(config,raw=raw),options=options)
    source=save(run/'fixture-only-engine.json',dict(note='Synthetic engine inventory for transaction tests'))
    source_id=thaw(hash_file(source));versions=dict(python='fixture_only',numpy='fixture_only',opencv='fixture_only')
    from video_ai.media._continuity_schema import stable
    engine=dict(algorithm='continuity_cv_v1',parameters_sha256='a'*64,implementation=[artifact(source)],
        dependency_fingerprint=canonical_digest(dict(**versions,build_information='fixture_only\n',package_files=stable([source_id]))))
    capture=dict(engine=engine,versions=versions,build_information='fixture_only\n',files=[source_id])
    monkeypatch.setattr('video_ai.media.continuity_report.capture_engine_sources',lambda:capture)
    monkeypatch.setattr('video_ai.media.continuity_report.capture_continuity_engine',lambda:engine)
    store=SimpleNamespace(run_dir=run)
    context=dict(store=store,rows=[{'budget':{'clip_id':'clip_a'}}],plan={'clips':[{'clip_id':'clip_a'}]},frozen=frozen)
    monkeypatch.setattr('video_ai.runtime.scene_clip_records.scene_context',lambda *a,**kw:context)
    monkeypatch.setattr('video_ai.runtime.scene_clip_records.collect_progress',lambda *a:({},{}))
    return dict(run=run,frozen=frozen,paths=paths,capture=capture,context=context)


def test_initial_epoch_is_locked_idempotent_and_query_never_writes(epoch_setup):
    from video_ai.runtime.production_scene_continuity import ensure_initial_epoch
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    from video_ai.runtime.scene_continuity_records import load_scene_continuity_progress
    s=epoch_setup
    with pytest.raises(ProductionRefused):
        ensure_initial_epoch(s['frozen'],{},None,paths=s['paths'],logger=None,lock=None)
    with RunLock(s['run']) as held:
        first=ensure_initial_epoch(s['frozen'],{},None,paths=s['paths'],logger=None,lock=held)
        second=ensure_initial_epoch(s['frozen'],{},None,paths=s['paths'],logger=None,lock=held)
    assert first==second
    before={str(p):p.read_bytes() for p in s['run'].rglob('*') if p.is_file()}
    progress=load_scene_continuity_progress(s['frozen'],{},None)
    assert progress['current_epoch']==first
    assert progress['clips'][0]['state']=='awaiting_analysis'
    assert progress['ready'] is False
    assert before=={str(p):p.read_bytes() for p in s['run'].rglob('*') if p.is_file()}


def test_initial_epoch_budget_starts_after_source_admission(epoch_setup,monkeypatch):
    from pathlib import Path
    from video_ai.runtime import production_scene_continuity as writer
    from video_ai.runtime import _scene_continuity_io as continuity_io
    from video_ai.runtime.production_state import RunLock
    import json
    s=epoch_setup;clock=[0.]
    monkeypatch.setattr(continuity_io,'monotonic',lambda:clock[0])
    original_context=writer._context
    def admitted_context(*args,**kwargs):
        result=original_context(*args,**kwargs)
        clock[0]+=301  # A valid whole-scene admission can exceed the epoch IO budget.
        return result
    monkeypatch.setattr(writer,'_context',admitted_context)
    with RunLock(s['run']) as held:
        result=writer.ensure_initial_epoch(s['frozen'],{},None,paths=s['paths'],logger=None,lock=held)
    commit=json.loads(Path(result['path']).read_text(encoding='utf-8'))
    intent=json.loads(Path(commit['intent']['path']).read_text(encoding='utf-8'))
    assert intent['clip_ids']==['clip_a']
    assert intent['engine']==s['capture']['engine']


def test_initial_epoch_keeps_shared_300_second_budget(epoch_setup,monkeypatch):
    from video_ai.runtime import production_scene_continuity as writer
    from video_ai.runtime import _scene_continuity_io as continuity_io
    from video_ai.runtime.production_state import RunLock
    import video_ai.media.continuity_report as report
    s=epoch_setup;clock=[0.]
    monkeypatch.setattr(continuity_io,'monotonic',lambda:clock[0])
    original_capture=report.capture_engine_sources
    def slow_capture():
        clock[0]+=301
        return original_capture()
    monkeypatch.setattr(report,'capture_engine_sources',slow_capture)
    with RunLock(s['run']) as held,pytest.raises(TimeoutError,match='continuity deadline expired'):
        writer.ensure_initial_epoch(s['frozen'],{},None,paths=s['paths'],logger=None,lock=held)
    assert not list((s['run']/'production/scene-continuity/epochs').glob('*/commit.json'))


@pytest.mark.parametrize('point',['epoch-intent','epoch-commit'])
def test_initial_epoch_boundary_recovers_same_intent_without_network(epoch_setup,monkeypatch,point):
    from video_ai.runtime import production_scene_continuity as writer
    from video_ai.runtime.production_state import RunLock
    s=epoch_setup
    def interrupt(name):
        if name==point:raise KeyboardInterrupt(name)
    monkeypatch.setattr(writer,'boundary',interrupt)
    with RunLock(s['run']) as held:
        with pytest.raises(KeyboardInterrupt): writer.ensure_initial_epoch(s['frozen'],{},None,paths=s['paths'],logger=None,lock=held)
    intents=list((s['run']/'production/scene-continuity/epochs').glob('*/intent.json'))
    assert len(intents)==1
    original=intents[0].read_bytes()
    monkeypatch.setattr(writer,'boundary',lambda _:None)
    with RunLock(s['run']) as held:
        result=writer.ensure_initial_epoch(s['frozen'],{},None,paths=s['paths'],logger=None,lock=held)
    assert intents[0].read_bytes()==original
    assert result['path'].endswith('commit.json')


def test_reassess_only_changes_diagnostic_epoch_and_stale_head_rejected(epoch_setup):
    from uuid import uuid4
    from image_selection_helpers import save
    from video_ai.runtime import production_scene_continuity as writer
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.manifest import now
    s=epoch_setup
    original=save(s['run']/'production/retained-video-identity.json',dict(no_generation='fixture_only'))
    original_bytes=original.read_bytes()
    with RunLock(s['run']) as held:
        previous=writer.ensure_initial_epoch(s['frozen'],{},None,paths=s['paths'],logger=None,lock=held)
        request=save(s['run']/'reassess.json',dict(schema_version=1,run_id=s['run'].name,epoch_id=str(uuid4()),
            previous_commit=previous,reason='Explicit local reassessment',requested_at=now()))
        result=writer.reassess_scene_continuity(s['frozen'],{},None,request,paths=s['paths'],logger=None,lock=held)
        assert result.status=='awaiting_analysis' and result.exit_code==3
        replay=writer.reassess_scene_continuity(s['frozen'],{},None,request,paths=s['paths'],logger=None,lock=held)
        assert replay.epoch==result.epoch
        stale=save(s['run']/'stale-reassess.json',dict(__import__('json').loads(request.read_text()),epoch_id=str(uuid4())))
        assert writer.reassess_scene_continuity(s['frozen'],{},None,stale,paths=s['paths'],logger=None,lock=held).status=='blocked'
    assert original.read_bytes()==original_bytes


def test_changed_engine_requires_reassessment_and_archive_damage_rejects(epoch_setup,monkeypatch):
    from video_ai.runtime import production_scene_continuity as writer
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    from video_ai.runtime.scene_continuity_records import load_scene_continuity_progress
    s=epoch_setup
    with RunLock(s['run']) as held:writer.ensure_initial_epoch(s['frozen'],{},None,paths=s['paths'],logger=None,lock=held)
    changed=dict(s['capture']['engine'],parameters_sha256='b'*64)
    monkeypatch.setattr('video_ai.media.continuity_report.capture_continuity_engine',lambda:changed)
    assert load_scene_continuity_progress(s['frozen'],{},None)['clips'][0]['state']=='blocked'
    archived=next((s['run']/'production/scene-continuity/epochs').glob('*/engine/files/*'))
    archived.write_bytes(b'broken archive')
    with pytest.raises(ProductionRefused):load_scene_continuity_progress(s['frozen'],{},None)


def test_new_record_schema_rejects_boolean_version_and_unknown_fields():
    from video_ai.runtime.scene_continuity_records import _schema
    for value in ({'schema_version':True}, {'schema_version':1,'extra':None}, {'schema_version':2}):
        with pytest.raises(ValueError):_schema(value,'schema_version')


def test_artifact_rejects_same_stat_byte_drift_and_hardlink(runtime_run):
    import os
    from video_ai.runtime._scene_continuity_io import artifact,verify
    run=runtime_run[0];path=run/'bound-source.bin';path.write_bytes(b'abcd')
    identity=artifact(path);stamp=path.stat();path.write_bytes(b'abce')
    os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    with pytest.raises(ValueError):verify(identity)
    os.link(path,run/'alias.bin')
    with pytest.raises(ValueError):artifact(path)


def test_json_single_file_limit_is_fail_closed_before_parsing(runtime_run):
    from video_ai.runtime._scene_continuity_io import Reader
    path=runtime_run[0]/'oversize.json';path.write_bytes(b' '*16777217)
    with pytest.raises(ValueError,match='resource_limit'):Reader().read(path)


def test_future_epoch_commit_and_extra_epoch_without_intent_rejected(epoch_setup):
    import json
    from video_ai.runtime import production_scene_continuity as writer
    from video_ai.runtime.scene_continuity_records import load_scene_continuity_progress
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    s=epoch_setup
    with RunLock(s['run']) as held:
        commit=writer.ensure_initial_epoch(s['frozen'],{},None,paths=s['paths'],logger=None,lock=held)
    path=__import__('pathlib').Path(commit['path']);original=path.read_bytes()
    value=json.loads(original);value['created_at']='2999-01-01T00:00:00+00:00'
    path.write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ProductionRefused):load_scene_continuity_progress(s['frozen'],{},None)
    path.write_bytes(original)
    (path.parent.parent/str(__import__('uuid').uuid4())).mkdir()
    with pytest.raises(ProductionRefused):load_scene_continuity_progress(s['frozen'],{},None)


def test_engine_archive_budget_failure_retains_intent_without_commit(epoch_setup,monkeypatch):
    from copy import deepcopy
    from video_ai.runtime import production_scene_continuity as writer
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    capture=deepcopy(epoch_setup['capture']);capture['files'][0]['bytes']=536870913
    monkeypatch.setattr('video_ai.media.continuity_report.capture_engine_sources',lambda:capture)
    s=epoch_setup
    with RunLock(s['run']) as held,pytest.raises(ProductionRefused,match='512MiB'):
        writer.ensure_initial_epoch(s['frozen'],{},None,paths=s['paths'],logger=None,lock=held)
    assert len(list((s['run']/'production/scene-continuity/epochs').glob('*/intent.json')))==1
    assert not list((s['run']/'production/scene-continuity/epochs').glob('*/commit.json'))


def test_missing_optional_engine_is_blocked_before_any_epoch_commit(epoch_setup,monkeypatch):
    from video_ai.runtime import production_scene_continuity as writer
    from video_ai.runtime.production_state import RunLock,ProductionRefused
    def unavailable():raise RuntimeError('Install video-ai[continuity] for CPU continuity diagnostics')
    monkeypatch.setattr('video_ai.media.continuity_report.capture_engine_sources',unavailable)
    s=epoch_setup
    with RunLock(s['run']) as held,pytest.raises(ProductionRefused):
        writer.ensure_initial_epoch(s['frozen'],{},None,paths=s['paths'],logger=None,lock=held)
    assert not list((s['run']/'production/scene-continuity/epochs').glob('*/commit.json'))


def test_complete_engine_archive_survives_interrupt_before_commit(epoch_setup,monkeypatch):
    from copy import deepcopy
    from datetime import datetime,timezone
    from pathlib import Path
    from video_ai.runtime import production_scene_continuity as writer
    from video_ai.runtime._scene_continuity_io import ContinuityStore
    from video_ai.runtime.production_state import RunLock
    s=epoch_setup
    def capture():
        result=deepcopy(s['capture'])
        result['files'][0]['verified_at']=datetime.now(timezone.utc).isoformat()
        return result
    monkeypatch.setattr('video_ai.media.continuity_report.capture_engine_sources',capture)
    original=ContinuityStore.write
    def before_commit(self,relative,value):
        if Path(relative).name=='commit.json':raise KeyboardInterrupt('after complete archive before commit')
        return original(self,relative,value)
    monkeypatch.setattr(ContinuityStore,'write',before_commit)
    with RunLock(s['run']) as held,pytest.raises(KeyboardInterrupt):
        writer.ensure_initial_epoch(s['frozen'],{},None,paths=s['paths'],logger=None,lock=held)
    archive=next((s['run']/'production/scene-continuity/epochs').glob('*/engine/manifest.json'))
    raw=archive.read_bytes()
    monkeypatch.setattr(ContinuityStore,'write',original)
    with RunLock(s['run']) as held:
        commit=writer.ensure_initial_epoch(s['frozen'],{},None,paths=s['paths'],logger=None,lock=held)
    assert archive.read_bytes()==raw
    assert Path(commit['path']).is_file()
