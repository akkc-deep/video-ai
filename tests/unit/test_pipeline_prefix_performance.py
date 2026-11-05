"""Offline prefix optimizations preserve exact evidence and historical requests."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from unit.test_production_inputs import production_config


def saved(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return path


def http_evidence(root, uid, token=None):
    token = token or uid
    request = saved(root / f'{token}.request.json',
                    dict(method='POST', unit_id=uid, url='http://local/tts', json_body={'text': uid}))
    meta = saved(root / f'{token}.response.json', dict(method='POST', unit_id=uid,
                 url='http://local/tts', status=200, truncated=False, error=None, bytes=4))
    body = root / f'{token}.body'
    body.write_bytes(b'WAVE')
    return [str(request), str(meta), str(body)]


def recover(module, logger, uid, **kwargs):
    return module.recover_http(logger, uid=uid, url='http://local/tts',
                               payload={'text': uid}, durable=False, **kwargs)


@pytest.mark.skipif(os.name != 'nt', reason='Mandatory request locks are Windows-specific')
def test_stage_recovery_indexes_requests_once_and_observes_new_duplicates(tmp_path, monkeypatch):
    import video_ai.runtime.production_support as support
    root = tmp_path / 'http'
    for index in range(24):
        http_evidence(root, f'unit_{index}')
    logger = SimpleNamespace(path=lambda name: tmp_path / name)
    calls = []
    scans=[]
    original_glob=Path.glob
    def counted_glob(path,pattern):
        if path==root and pattern=='*.request.json':scans.append(path)
        return original_glob(path,pattern)
    monkeypatch.setattr(Path,'glob',counted_glob)
    original = support.read_json
    def counted(path):
        if str(path).endswith('.request.json'): calls.append(Path(path))
        return original(path)
    monkeypatch.setattr(support, 'read_json', counted)
    with support.http_recovery_scope():
        for index in range(24):
            assert recover(support, logger, f'unit_{index}')[0] == b'WAVE'
        assert len(calls) <= 48
        assert len(scans)==1
        http_evidence(root, 'unit_0', 'duplicate')
        with pytest.raises(support.ProductionRefused, match='duplicate'):
            recover(support, logger, 'unit_0')
        assert 2 <= len(scans) <= 4  # Windows can deliver the three file creations separately.
    # Scope release must allow the immutable request to be replaced afterward.
    (root / 'unit_0.request.json').write_text('{}', encoding='utf-8')


@pytest.mark.skipif(os.name != 'nt', reason='Mandatory request locks are Windows-specific')
def test_index_cannot_hide_same_size_restored_mtime_request_mutation(tmp_path):
    import video_ai.runtime.production_support as support
    root = tmp_path / 'http'
    paths = http_evidence(root, 'unit_0')
    logger = SimpleNamespace(path=lambda name: tmp_path / name)
    request = Path(paths[0])
    before = request.stat()
    with support.http_recovery_scope():
        recover(support, logger, 'unit_0')
        with pytest.raises(OSError):
            with request.open('r+b') as stream:
                stream.write(request.read_bytes().replace(b'unit_0', b'unit_1'))
                os.utime(request, ns=(before.st_atime_ns, before.st_mtime_ns))


def test_precise_checkpoint_recovery_never_scans_unrelated_requests(tmp_path, monkeypatch):
    import video_ai.runtime.production_support as support
    evidence = http_evidence(tmp_path / 'http', 'unit_0')
    logger = SimpleNamespace(path=lambda name: pytest.fail('checkpoint recovery scanned HTTP directory'))
    assert recover(support, logger, 'unit_0', evidence_paths=evidence)[0] == b'WAVE'
    request = Path(evidence[0])
    value = json.loads(request.read_text())
    value['json_body']['text'] = 'changed'
    saved(request, value)
    with pytest.raises(support.ProductionRefused, match='identity differs'):
        recover(support, logger, 'unit_0', evidence_paths=evidence)


def test_scoped_checkpoint_paths_still_reject_new_duplicate_submission(tmp_path):
    import video_ai.runtime.production_support as support
    root=tmp_path/'http'
    evidence=http_evidence(root,'unit_0')
    logger=SimpleNamespace(path=lambda name:tmp_path/name)
    with support.http_recovery_scope():
        assert recover(support,logger,'unit_0',evidence_paths=evidence)[0]==b'WAVE'
        http_evidence(root,'unit_0','duplicate')
        with pytest.raises(support.ProductionRefused,match='duplicate'):
            recover(support,logger,'unit_0',evidence_paths=evidence)


def test_existing_common_ready_hashes_each_pcm_only_once(runtime_run, monkeypatch):
    import video_ai.runtime.scene_pipeline_records as records
    from video_ai.runtime.production_state import RunLock
    run, _, _ = runtime_run
    production = run / 'production'
    saved(production / 'units.json', {'text': 'original'})
    saved(production / 'timeline.json', {'samples': 4})
    pcm = production / 'original.wav'
    pcm.write_bytes(b'original PCM bytes')
    frozen = SimpleNamespace(options={'script_path': str(production / 'script.txt'), 'run_id': run.name})
    timeline = SimpleNamespace(clips=[SimpleNamespace(unit_id='unit_0', pcm=SimpleNamespace(path=pcm), samples=4)])
    calls = []
    original = records.artifact
    def counted(path, **kwargs):
        if Path(path) == pcm: calls.append(path)
        return original(path, **kwargs)
    monkeypatch.setattr(records, 'artifact', counted)
    with RunLock(run) as held:
        records.record_common(frozen, {}, timeline, 'prepared', lock=held)
        calls.clear()
        records.record_common(frozen, {}, timeline, 'prepared', lock=held)
    assert len(calls) == 1


def test_common_ready_cannot_commit_unobserved_pcm_change_at_write_boundary(runtime_run, monkeypatch):
    import video_ai.runtime.scene_pipeline_records as records
    import video_ai.runtime.production_scene_pipeline as pipeline
    from video_ai.runtime.production_state import RunLock
    run, _, _ = runtime_run
    production=run/'production'
    saved(production/'units.json', {})
    saved(production/'timeline.json', {})
    pcm=production/'original.wav';pcm.write_bytes(b'original')
    frozen=SimpleNamespace(options={'script_path':str(production/'script.txt'),'run_id':run.name})
    timeline=SimpleNamespace(clips=[SimpleNamespace(unit_id='u',pcm=SimpleNamespace(path=pcm),samples=4)])
    with RunLock(run) as held:
        records.record_common(frozen,{},timeline,'prepared',lock=held)
        def mutate(point):
            if point=='pipeline-inputs':pcm.write_bytes(b'modified')
        monkeypatch.setattr(pipeline,'boundary',mutate)
        with pytest.raises((OSError, ValueError)):
            records.record_common(frozen,{},timeline,'prepared',lock=held)


def test_new_planner_intent_records_versioned_residency_without_changing_inference(runtime_run):
    from http_helpers import ScriptedTransport, Response
    from video_ai.adapters.common import HttpClient
    from video_ai.adapters.ollama import OllamaPlanner
    from video_ai.runtime.logging import RunLogger
    run,_,_=runtime_run
    transport=ScriptedTransport(lambda request, timeout:Response(dict(model='qwen3:8b',done=True,response='{}')))
    logger=RunLogger(run,production=True)
    planner=OllamaPlanner(HttpClient('http://127.0.0.1:11435',1,logger,transport=transport))
    context=dict(client_id='c',script_identity={},candidate_ranges=[],model_session='owned_stage_v1')
    assert planner.generate('original',schema={'type':'object'},request_id='units_batch_0001_initial',intent_context=context)=={}
    body=json.loads(transport.calls[0][2])
    assert body['keep_alive']=='5m'
    assert body['options']==dict(temperature=0,num_predict=8192)
    assert len(transport.calls)==1
    intent=json.loads(logger.path('storyboard/units_batch_0001_initial.intent.json').read_text())
    assert intent['context']['model_session']=='owned_stage_v1'
    assert intent['body']==body


def test_owned_model_session_changes_only_residency_and_retains_legacy_default():
    from video_ai.adapters.ollama import ollama_body
    schema = {'type': 'object', 'properties': {}}
    historical = ollama_body('original prompt', schema)
    resident = ollama_body('original prompt', schema, model_session='owned_stage_v1')
    assert historical['keep_alive'] == 0
    assert resident['keep_alive'] == '5m'
    assert dict(resident, keep_alive=0) == historical
    with pytest.raises(ValueError, match='model session'):
        ollama_body('original prompt', schema, model_session='unversioned')


@pytest.mark.parametrize('session', [None, 'owned_stage_v1'])
def test_units_intent_recovery_accepts_original_runtime_contract(tmp_path, session):
    from video_ai.adapters.ollama import ollama_body
    from video_ai.runtime.production_storyboard import _check_intent
    frozen = SimpleNamespace(options={'cpu_planner': False,
          'execution_policy': {'input_identities': {'script': {'sha256': 'original'}}}})
    context = dict(client_id='client', script_identity={'sha256': 'original'}, candidate_ranges=[])
    kwargs = {}
    if session:
        context['model_session'] = session
        kwargs['model_session'] = session
    schema = {'type': 'object', 'properties': {}}
    value = dict(request_id='units_batch_0001_initial', body=ollama_body('original', schema, **kwargs),
                 schema=schema, prompt='original', context=context)
    path = saved(tmp_path / 'intent.json', value)
    assert _check_intent(path, frozen=frozen, uid=value['request_id'], schema=schema,
                         prompt='original', candidates=[]) == value
    value['body']['options']['temperature'] = 0.5
    saved(path, value)
    with pytest.raises(ValueError, match='body differs'):
        _check_intent(path, frozen=frozen, uid=value['request_id'], schema=schema,
                      prompt='original', candidates=[])


@pytest.mark.parametrize('session',[None,'owned_stage_v1'])
def test_visual_intent_recovery_keeps_old_and_new_body_contracts(tmp_path,session):
    from video_ai.runtime.production_visual_storyboard import _intent
    context=dict(script_identity={},shot_ranges=[],units_stamp={},slots_stamp={},global_visual=None)
    stored=dict(context,client_id='c')
    if session:stored['model_session']=session
    schema={'type':'object'}
    body=dict(model='qwen3:8b',prompt='original',stream=False,format=schema,
              keep_alive='5m' if session else 0,think=False,options=dict(temperature=0,num_predict=8192))
    value=dict(request_id='storyboard_batch_0001_initial',body=body,schema=schema,prompt='original',context=stored)
    path=saved(tmp_path/'intent.json',value)
    frozen=SimpleNamespace(options={'cpu_planner':False})
    assert _intent(path,value['request_id'],'original',schema,context,frozen)==value
    body['keep_alive']=0 if session else '5m'
    saved(path,value)
    with pytest.raises(ValueError,match='body changed'):
        _intent(path,value['request_id'],'original',schema,context,frozen)


def test_owned_units_batches_and_complete_resume_use_recorded_resident_requests(production_config,runtime_run,monkeypatch):
    import video_ai.runtime.production_storyboard as units_runtime
    from video_ai.adapters.common import HttpClient
    from http_helpers import ScriptedTransport,Response
    from production_helpers import install_owned_services,proposal_for
    from unit.test_production_speech import make_prefix
    run,_,paths=runtime_run
    def respond(request,timeout):
        body=json.loads(request.data)
        return Response(dict(model='qwen3:8b',done=True,response=json.dumps(proposal_for(body))))
    transport=ScriptedTransport(respond)
    monkeypatch.setattr(units_runtime,'HttpClient',lambda *args,**kwargs:HttpClient(*args,**kwargs,transport=transport))
    manager=install_owned_services(monkeypatch)
    frozen,state,manifest,logger=make_prefix(production_config,run,'湖水。'*9)
    result=units_runtime.produce_units(frozen,state=state,manifest=manifest,paths=paths,logger=logger)
    assert ''.join(span['text'] for span in result['spans'])=='湖水。'*9
    assert len(transport.calls)==2
    assert [json.loads(call[2])['keep_alive'] for call in transport.calls]==['5m','5m']
    assert manager.stopped==['ollama']
    assert units_runtime.produce_units(frozen,state=state,manifest=manifest,paths=paths,logger=logger)==result
    assert len(transport.calls)==2


def test_read_only_index_can_become_durable_without_losing_protection(tmp_path):
    import video_ai.runtime.production_support as support
    evidence=http_evidence(tmp_path/'http','unit_0')
    logger=SimpleNamespace(path=lambda name:tmp_path/name)
    with support.http_recovery_scope():
        recover(support,logger,'unit_0')
        assert support.recover_http(logger,uid='unit_0',url='http://local/tts',payload={'text':'unit_0'})[0]==b'WAVE'
        with pytest.raises(OSError):Path(evidence[0]).write_text('{}')


def test_durability_window_rejects_request_byte_change_even_after_mtime_restore(tmp_path,monkeypatch):
    import video_ai.runtime.production_support as support
    evidence=http_evidence(tmp_path/'http','unit_0')
    path=Path(evidence[0]);stamp=path.stat()
    logger=SimpleNamespace(path=lambda name:tmp_path/name)
    original=support.sync_file
    def mutate(target):
        if Path(target)==path:
            path.write_bytes(path.read_bytes().replace(b'unit_0',b'unit_1'))
            os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        else:original(target)
    with pytest.raises((OSError,ValueError)):
        with support.http_recovery_scope():
            recover(support,logger,'unit_0')
            monkeypatch.setattr(support,'sync_file',mutate)
            support.recover_http(logger,uid='unit_0',url='http://local/tts',payload={'text':'unit_0'})


def test_notification_failure_falls_back_to_strict_request_discovery(tmp_path,monkeypatch):
    import video_ai.runtime.production_support as support
    root=tmp_path/'http';http_evidence(root,'unit_0')
    logger=SimpleNamespace(path=lambda name:tmp_path/name)
    def unavailable(root):raise OSError('notifications unavailable')
    monkeypatch.setattr(support,'_RequestDirectoryWatch',unavailable)
    with support.http_recovery_scope():
        recover(support,logger,'unit_0')
        http_evidence(root,'unit_0','duplicate')
        with pytest.raises(support.ProductionRefused,match='duplicate'):recover(support,logger,'unit_0')


@pytest.mark.skipif(os.name!='nt',reason='Windows native notification race')
def test_new_duplicate_during_enumeration_is_not_lost(tmp_path,monkeypatch):
    import video_ai.runtime.production_support as support
    root=tmp_path/'http';http_evidence(root,'unit_0')
    logger=SimpleNamespace(path=lambda name:tmp_path/name)
    original=Path.glob;created=[]
    def racing_glob(path,pattern):
        paths=list(original(path,pattern))
        if path==root and pattern=='*.request.json' and not created:
            created.append(True);stamp=root.stat()
            http_evidence(root,'unit_0','duplicate')
            os.utime(root,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        return iter(paths)
    monkeypatch.setattr(Path,'glob',racing_glob)
    with support.http_recovery_scope():
        with pytest.raises(support.ProductionRefused,match='duplicate'):recover(support,logger,'unit_0')


def test_closed_copied_recovery_context_cannot_reuse_stale_discovery(tmp_path):
    from contextvars import copy_context
    import video_ai.runtime.production_support as support
    root=tmp_path/'http';http_evidence(root,'unit_0')
    logger=SimpleNamespace(path=lambda name:tmp_path/name)
    with support.http_recovery_scope():
        recover(support,logger,'unit_0');copied=copy_context()
    http_evidence(root,'unit_0','duplicate')
    with pytest.raises(support.ProductionRefused,match='duplicate'):
        copied.run(recover,support,logger,'unit_0')


def native_handle_count():
    import ctypes
    from ctypes import wintypes
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.GetCurrentProcess.restype=wintypes.HANDLE
    api.GetProcessHandleCount.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    api.GetProcessHandleCount.restype=wintypes.BOOL
    count=wintypes.DWORD()
    if not api.GetProcessHandleCount(api.GetCurrentProcess(),ctypes.byref(count)):
        raise ctypes.WinError(ctypes.get_last_error())
    return count.value


@pytest.mark.skipif(os.name!='nt',reason='Windows CRT descriptor limit and native handles')
def test_request_index_above_512_requests_releases_all_native_leases(tmp_path,monkeypatch):
    import weakref
    import video_ai.runtime.production_support as support
    import video_ai.runtime.verification as verification
    root=tmp_path/'http';http_evidence(root,'unit_0')
    for index in range(1,641):
        saved(root/f'unit_{index}.request.json',dict(method='POST',unit_id=f'unit_{index}',
              url='http://local/tts',json_body={'text':f'unit_{index}'}))
    logger=SimpleNamespace(path=lambda name:tmp_path/name)
    readers=[];original=verification._locked_reader
    def observed_reader(path):
        stream=original(path);readers.append(weakref.ref(stream));return stream
    monkeypatch.setattr(verification,'_locked_reader',observed_reader)
    before=native_handle_count()
    with support.http_recovery_scope():
        assert recover(support,logger,'unit_0')[0]==b'WAVE'
        assert sum(reader() is not None and not reader().closed for reader in readers)<=1
        # Every indexed request remains protected, including one beyond CRT's default limit.
        with pytest.raises(OSError):(root/'unit_640.request.json').write_text('{}')
    assert native_handle_count()<=before+4
    (root/'unit_640.request.json').write_text('{}')


@pytest.mark.skipif(os.name!='nt',reason='Windows protected HTTP leases')
def test_fsync_relock_failure_still_restores_remaining_leases_and_closes_handles(tmp_path,monkeypatch):
    import video_ai.runtime.production_support as support
    import video_ai.runtime.verification as verification
    root=tmp_path/'http'
    paths=[Path(http_evidence(root,f'unit_{index}')[0]) for index in range(3)]
    logger=SimpleNamespace(path=lambda name:tmp_path/name)
    before=native_handle_count()
    with support.http_recovery_scope():
        recover(support,logger,'unit_0')
        original=verification._locked_reader;attempts=[]
        def relock(path):
            attempts.append(path)
            if len(attempts)==1:raise OSError('injected first relock failure')
            return original(path)
        monkeypatch.setattr(verification,'_locked_reader',relock)
        with pytest.raises(OSError,match='injected first relock failure'):
            with support._http_evidence_flush(paths):pass
        assert set(attempts)==set(paths)
    assert native_handle_count()<=before+4
    for path in paths:path.write_text('{}')


@pytest.mark.skipif(os.name!='nt',reason='Windows source native leases')
def test_common_source_protection_above_512_clips_does_not_retain_crt_files(runtime_run,monkeypatch):
    import weakref
    import video_ai.runtime.scene_pipeline_records as records
    import video_ai.runtime.verification as verification
    run,_,_=runtime_run
    production=run/'production'
    saved(production/'units.json',{});saved(production/'timeline.json',{})
    clips=[]
    for index in range(600):
        pcm=production/f'pcm_{index}.wav';pcm.write_bytes(b'original')
        clips.append(SimpleNamespace(pcm=SimpleNamespace(path=pcm)))
    frozen=SimpleNamespace(options={'script_path':str(production/'script.txt')})
    readers=[];original=verification._locked_reader
    def observed_reader(path):
        stream=original(path);readers.append(weakref.ref(stream));return stream
    monkeypatch.setattr(verification,'_locked_reader',observed_reader)
    before=native_handle_count()
    with records._common_sources(frozen,SimpleNamespace(clips=clips),'prepared'):
        assert sum(reader() is not None and not reader().closed for reader in readers)<=1
        with pytest.raises(OSError):clips[-1].pcm.path.write_bytes(b'modified')
    assert native_handle_count()<=before+4
    clips[-1].pcm.path.write_bytes(b'modified')
