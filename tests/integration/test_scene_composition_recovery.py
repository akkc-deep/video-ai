"""Candidate evidence recovery must preserve original attempts and media bytes."""
from pathlib import Path
import json
import pytest

from video_ai.runtime.production_scene_composition import produce_scene_composition
from video_ai.runtime.production_state import ProductionRefused
from video_ai.runtime.scene_media_records import require_scene_composition


def _compose(setup):
    return produce_scene_composition(setup['frozen'],setup['units'],setup['timeline'],
        paths=setup['paths'],logger=setup['logger'])


def test_exact_evidence_recovers_missing_outer_record_without_reencoding(runtime_run,tmp_path,monkeypatch):
    from scene_media_helpers import prepared_upscaled
    import video_ai.runtime.production_scene_composition as module
    setup = prepared_upscaled(runtime_run,tmp_path,monkeypatch)
    original_runner=module.run_logged; calls=[]; intents={}
    root=setup['run']/'production/scene-composition'
    def interrupt_materialized(point):
        if point=='materialized': raise KeyboardInterrupt('accepted materialization before encode')
    monkeypatch.setattr(module,'boundary',interrupt_materialized)
    stopped=_compose(setup)
    assert stopped.status=='interrupted',('materialized',stopped.error)
    materialized_ready=(root/'materialized-ready.json').read_bytes()
    assert (root/'materialized.json').read_bytes()==materialized_ready
    assert not list((root/'commands').glob('*.intent.json'))
    monkeypatch.setattr(module,'boundary',lambda point:None)
    # One real run crosses both interruption boundaries in order: encode, then probe.
    for operation in ('encode','probe'):
        def crash_after_command(*args,**kwargs):
            assert ':'+operation+':' in kwargs['unit_id'],('completed command repeated',kwargs['unit_id'])
            result=original_runner(*args,**kwargs); calls.append(kwargs['unit_id'])
            raise KeyboardInterrupt('after original '+operation+' completion')
        monkeypatch.setattr(module,'run_logged',crash_after_command)
        interrupted=_compose(setup)
        assert interrupted.status=='interrupted',(operation,interrupted.error)
        paths=list((root/'commands').glob(operation+'-*.intent.json'))
        assert len(paths)==1,operation
        intents[paths[0]]=paths[0].read_bytes()
    assert len(calls)==2 and ':encode:' in calls[0] and ':probe:' in calls[1]
    monkeypatch.setattr(module,'run_logged',lambda *a,**k:pytest.fail('completed encode/probe must never run again'))
    # Candidate preparation, rename and commit are separate durable boundaries.
    candidate_ready=None
    for expected in ('candidate_ready','candidate_promoted','candidate_commit'):
        def stop_candidate(point):
            if point==expected: raise KeyboardInterrupt('after '+point)
        monkeypatch.setattr(module,'boundary',stop_candidate)
        stopped=_compose(setup)
        assert stopped.status=='interrupted',(expected,stopped.error)
        ready_bytes=(root/'media-ready/candidate.json').read_bytes()
        if candidate_ready is None: candidate_ready=ready_bytes
        assert ready_bytes==candidate_ready,expected
        assert (root/'candidate.mp4').exists()==(expected!='candidate_ready'),expected
    monkeypatch.setattr(module,'boundary',lambda point:None)
    first=_compose(setup)
    assert first.status=='awaiting_final_review',first.error
    assert (root/'materialized-ready.json').read_bytes()==materialized_ready
    assert len(list((root/'materialized-attempts').iterdir()))==1
    for path,raw in intents.items(): assert path.read_bytes()==raw,('original command intent changed',path)
    commit=json.loads((root/'candidate-commit.json').read_text(encoding='utf-8'))
    monkeypatch.setattr(module,'run_logged',lambda *a,**k:pytest.fail('accepted encode/probe must never run again'))
    for missing in ('materialized.json','candidate-commit.json','encode-success','probe-success'):
        if missing.endswith('-success'):
            path=next((root/'commands').glob(missing.replace('-success','')+'-*.success.json'))
        else: path=root/missing
        original=path.read_bytes(); path.unlink()
        with pytest.raises(ProductionRefused):
            require_scene_composition(setup['frozen'],setup['units'],setup['timeline'])
        second=_compose(setup)
        assert second.status=='awaiting_final_review',(missing,second.error)
        assert path.read_bytes()==original,missing
        assert json.loads((root/'candidate-commit.json').read_text(encoding='utf-8'))==commit,missing
    _assert_missing_original_evidence(setup)
    _assert_media_tamper(setup)
    for path,raw in intents.items(): assert path.read_bytes()==raw,('original command intent changed',path)


def _assert_media_tamper(setup):
    root=setup['run']/'production/scene-composition'
    materialized=json.loads((root/'materialized.json').read_text(encoding='utf-8'))
    path=Path(materialized['narration']['audio']['path'])
    original=path.read_bytes()
    with path.open('r+b') as stream:
        stream.seek(44); value=stream.read(1); stream.seek(44); stream.write(bytes([value[0]^1]))
    result=_compose(setup)
    assert result.status=='blocked',('narration byte tamper',result.error)
    path.write_bytes(original)


def _assert_missing_original_evidence(setup):
    root=setup['run']/'production/scene-composition'
    for lost in ('command-completion','materialized-evidence'):
        restore={}
        if lost=='command-completion':
            success=next((root/'commands').glob('encode-*.success.json'))
            restore[success]=success.read_bytes(); success.unlink()
            events=setup['logger'].path('events.jsonl'); restore[events]=events.read_bytes()
            rows=[line for line in events.read_text(encoding='utf-8').splitlines()
                  if not (json.loads(line).get('stage')=='scene_composition'
                          and ':encode:' in (json.loads(line).get('unit_id') or ''))]
            events.write_text('\n'.join(rows)+'\n',encoding='utf-8')
        else:
            for path in (root/'materialized.json',root/'materialized-ready.json'):
                restore[path]=path.read_bytes(); path.unlink()
        before={p for p in root.rglob('*')}
        result=_compose(setup)
        assert result.status=='blocked',(lost,result.error)
        assert {p for p in root.rglob('*')}==before,lost
        for path,raw in restore.items(): path.write_bytes(raw)


@pytest.mark.parametrize('staging_present',[True,False],ids=['extant-staging-mutation','promoted-staging-reappearance'])
def test_candidate_ready_handoff_preserves_real_file_staging_guards(runtime_run,staging_present):
    """Exercise the admitted-record handoff only; no fake complete enters a public gate."""
    from types import SimpleNamespace
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_scene_composition import _capture_composition_guard
    run=runtime_run[0]
    with RunLock(run) as lock:
        base=SceneMediaStore(SimpleNamespace(options={'model_stamps':{}}),run,lock=lock)
        store=base.for_root('production/scene-composition')
        source=store.path('encodes/original/candidate.mp4'); source.parent.mkdir(parents=True)
        source.write_bytes(b'original file bytes for narrow staging ownership test')
        target=store.path('candidate.mp4'); target.write_bytes(source.read_bytes())
        staging=store.path('staging/original.mp4'); staging.parent.mkdir()
        if staging_present: staging.write_bytes(source.read_bytes())
        target_artifact=store.artifact(target)
        receipt=dict(schema_version=2,run_id=run.name,operation='candidate',source=store.artifact(source),
            staging=dict(target_artifact,path=str(staging)),target=target_artifact,
            recipe=dict(algorithm='identity_mp4_copy_v1',parameters={}),evidence=[],created_at='2026-10-19T00:00:00+00:00')
        store.write('media-ready/candidate.json',receipt)
        for name in ('inputs.json','contributions.json','materialized-ready.json','materialized.json','candidate-commit.json'):
            store.write(name,{})
        context=dict(store=base,composition_store=store,materialized={})
        _capture_composition_guard(context,dict(candidate=target_artifact))
        base.verify_global()
        staging.write_bytes(b'late changed staging' if staging_present else source.read_bytes())
        with pytest.raises(ProductionRefused): base.verify_global()


@pytest.mark.parametrize('change',['remove','change'],ids=['removed-completion-row','changed-completion-row'])
def test_original_command_completion_proof_is_preserved_in_downstream_guard(runtime_run,change):
    """Real event bytes and lock, with authored command protocol data; no media claim."""
    from types import SimpleNamespace
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.scene_media_records import SceneMediaStore
    from video_ai.runtime.production_scene_composition import _capture_composition_guard
    from video_ai.runtime._scene_composition_commands import _completion
    run,config,_=runtime_run; token='11111111-1111-4111-8111-111111111111'
    with RunLock(run) as lock:
        base=SceneMediaStore(SimpleNamespace(options={'model_stamps':{}}),run,lock=lock)
        store=base.for_root('production/scene-composition')
        media=store.path('candidate.mp4'); media.parent.mkdir(parents=True); media.write_bytes(b'owned handoff file')
        artifact=store.artifact(media); staging=store.path('staging/original.mp4')
        ready=dict(source=artifact,staging=dict(artifact,path=str(staging)),target=artifact,operation='candidate',
            recipe=dict(algorithm='identity_mp4_copy_v1',parameters={}))
        store.write('media-ready/candidate.json',ready)
        for name in ('inputs.json','contributions.json','materialized-ready.json','materialized.json','candidate-commit.json'):
            store.write(name,{})
        logs=run/'logs/production'; logs.mkdir(parents=True,exist_ok=True)
        stdout=logs/'original.stdout'; stdout.write_bytes(b'')
        stderr=logs/'original.stderr'; stderr.write_bytes(b'')
        intent=dict(operation='encode',args=[str(config.tools['ffmpeg']),'-v','error'],cwd=str(run))
        command=dict(args=intent['args'],cwd=str(run),returncode=0,timed_out=False,
            stdout_path=str(stdout),stderr_path=str(stderr),started_at='2026-10-19T00:00:00+00:00',finished_at='2026-10-19T00:00:01+00:00')
        event=dict(stage='scene_composition',unit_id='scene_composition:encode:'+token,event='command_finished',
            details=dict(command,timeout=300,interrupted=False))
        events=logs/'events.jsonl'; events.write_text(json.dumps(event)+'\n',encoding='utf-8')
        context=dict(store=base,composition_store=store,materialized={},composition_command_events=store.artifact(events))
        assert _completion(context,intent,token)==command
        _capture_composition_guard(context,dict(candidate=artifact)); base.verify_global()
        event['details']['returncode']=1
        events.write_text('' if change=='remove' else json.dumps(event)+'\n',encoding='utf-8')
        assert _completion(context,intent,token) is None
        with pytest.raises(ProductionRefused): base.verify_global()


@pytest.fixture
def composition_capture_fixture(runtime_run):
    """Real guard files for narrow handoff/admission orchestration, without a media claim."""
    from types import SimpleNamespace
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.scene_media_records import SceneMediaStore
    run=runtime_run[0]
    with RunLock(run) as lock:
        base=SceneMediaStore(SimpleNamespace(options={'model_stamps':{}}),run,lock=lock)
        store=base.for_root('production/scene-composition')
        media=store.path('candidate.mp4'); media.parent.mkdir(parents=True); media.write_bytes(b'original narrow handoff bytes')
        artifact=store.artifact(media)
        store.write('media-ready/candidate.json',dict(source=artifact,target=artifact,
            staging=dict(artifact,path=str(store.path('staging/original.mp4'))),operation='candidate',
            recipe=dict(algorithm='identity_mp4_copy_v1',parameters={})))
        for name in ('inputs.json','contributions.json','materialized-ready.json','materialized.json','candidate-commit.json'):
            store.write(name,{})
        store.write('commands/encode-11111111-1111-4111-8111-111111111111.intent.json',{'operation':'encode'})
        yield dict(store=base,composition_store=store,materialized={}),dict(candidate=artifact)


@pytest.mark.parametrize('victim',['candidate-commit.json','commands/encode-11111111-1111-4111-8111-111111111111.intent.json'])
def test_composition_capture_cannot_replace_previously_admitted_json_bytes(composition_capture_fixture,monkeypatch,victim):
    import video_ai.runtime.production_scene_composition as module
    context,candidate=composition_capture_fixture; store=context['composition_store']; path=store.path(victim)
    original=store.artifact(path); store.bind_artifact(original)
    capture=module._capture; mutated=[]
    def change_after_initial_audit(target,value):
        if not mutated:
            path.write_text('{"changed_after_initial_audit":true}\n',encoding='utf-8'); mutated.append(True)
        return capture(target,value)
    monkeypatch.setattr(module,'_capture',change_after_initial_audit)
    with pytest.raises(ProductionRefused): module._capture_composition_guard(context,candidate)
    assert mutated and store.guard_paths[str(path)]==original


def test_readonly_composition_admission_rejects_command_added_after_semantic_scan(composition_capture_fixture,monkeypatch):
    import video_ai.runtime.production_scene_composition as module
    context,candidate=composition_capture_fixture; store=context['composition_store']
    new_command=store.path('commands/probe-22222222-2222-4222-8222-222222222222.intent.json')
    monkeypatch.setattr(module,'_prepare',lambda value:value)
    def completed_semantic_scan(value,*,write):
        assert write is False
        assert store.read('candidate-commit.json')=={}
        new_command.write_text('{"operation":"probe"}\n',encoding='utf-8')
        return candidate
    monkeypatch.setattr(module,'_commit',completed_semantic_scan)
    with pytest.raises(ProductionRefused): module.require_scene_composition_record(context)
    assert new_command.is_file(),'the unexpected record must remain as conflict evidence'


