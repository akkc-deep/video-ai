"""Only byte-for-byte covered execution/revision obligations can be deduplicated."""
from copy import copy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import pytest


@pytest.fixture
def coverage_case(runtime_run,monkeypatch):
    return lambda: _build_coverage_case(runtime_run,monkeypatch)


def _build_coverage_case(runtime_run,monkeypatch):
    import video_ai.runtime._scene_media_check_coverage as module
    from video_ai.runtime._continuity_byte_guard import capture_reads
    from video_ai.runtime._whole_scene_admission import EvidenceReader
    from video_ai.runtime.scene_revision_records import RevisionGuard
    from video_ai.runtime.manifest import hash_file,thaw
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.runtime.scene_media_records import SceneMediaStore
    import video_ai.runtime.scene_execution_records as execution
    run=runtime_run[0]
    # Coverage remains a strict-store mechanism. Whole media now deliberately
    # omits repeated audits; exercise the historical strict branch here.
    frozen=SimpleNamespace(options=dict(script_path=str(run/'inputs/script.txt'),model_stamps={},
        config_snapshot=dict(raw=dict(scene_rendering=dict(mode='segmented_v1')))),
        config=SimpleNamespace(raw=dict(scene_rendering=dict(mode='segmented_v1'))))
    budget=run/'budget.json';budget.write_text('{"budget":1}',encoding='utf-8')
    evidence=run/'evidence.json';evidence.write_text('{"evidence":1}',encoding='utf-8')
    folder=run/'revision';folder.mkdir();revision_file=folder/'view.json';revision_file.write_text('{}')
    reader=EvidenceReader();reader.capture(evidence);reader.inventory(folder,'*.json')
    calls=[];clock=[0.0];cache={}
    def admitted(f):
        calls.append('execution');clock[0]+=1.812
        current=cache.setdefault(id(f),reader);current.verify();return {'guard':current}
    monkeypatch.setattr(execution,'verify_whole_scene_frozen',admitted)
    monkeypatch.setattr(execution,'cached_whole_scene_admission_guard',lambda f:cache.get(id(f)),raising=False)
    def artifact(path):
        identity=thaw(hash_file(Path(path)));return {k:identity[k] for k in ('path','bytes','sha256')}
    store=SceneMediaStore(frozen,run,clip_ids=('scene_0001_clip_0001',))
    check=module.WholeExecutionCheck(store,frozen,artifact(budget))
    store.execution_guard=check
    revision=RevisionGuard(frozen);revision.capture(revision_file,root=run)
    revision.capture_directory(folder,root=run);revision.capture_absent(run/'absent.json',root=run)
    store.revision_context={'guard':revision}
    with capture_reads() as capture:
        check();revision.verify_captured_bytes()
    proof=capture.finish();baseline=canonical_digest(frozen.options)
    def source():
        calls.append('source');clock[0]+=4.406
        if canonical_digest(frozen.options)!=baseline:raise ValueError('source arguments changed')
        proof.verify()
    module._tag_ready_continuity_guard(source,proof)
    store.continuity_check=source;store.continuity_read_guard=source
    return dict(module=module,store=store,proof=proof,source=source,revision=revision,
        check=check,calls=calls,clock=clock,run=run,budget=budget,evidence=evidence,cache=cache,reader=reader)


def test_real_exact_coverage_and_changed_revision_contract(coverage_case):
    c=coverage_case()
    coverage=c['module'].capture_media_check_coverage(c['store'],c['source'])
    assert coverage is not None and coverage.applies(c['store'])
    path=c['run']/'new.json';path.write_text('{}')
    c['revision'].capture(path,root=c['run'])
    assert not coverage.applies(c['store'])


@pytest.mark.parametrize('fault',['file','sha','mtime','ownership','inventory','kind','pattern','absence'])
def test_coverage_is_exact_for_all_original_obligations(coverage_case,fault):
    from video_ai.runtime._continuity_byte_guard import ByteGuard
    c=coverage_case();proof=c['proof'];files=proof.files;inventories=proof.inventories;absences=proof.absences
    if fault=='file':files=files[:-1]
    elif fault in ('sha','mtime','ownership'):
        row=files[0]
        changes={'sha':dict(sha256='f'*64),'mtime':dict(mtime_ns=row.mtime_ns+1),
                 'ownership':dict(ownership=(*row.ownership[:-1],'changed'))}[fault]
        files=(replace(row,**changes),*files[1:])
    elif fault=='absence':absences=()
    else:
        row=inventories[0]
        changes={'inventory':dict(expected=()),'kind':dict(kind='json_direct'),
                 'pattern':dict(pattern='*.different')}[fault]
        inventories=(replace(row,**changes),*inventories[1:])
    partial=ByteGuard(files,inventories,absences)
    assert not c['module']._proof_covers(partial,proof)
    assert c['module']._proof_covers(proof,proof)


def test_missing_dependency_never_installs_partial_certificate(coverage_case):
    from video_ai.runtime._continuity_byte_guard import ByteGuard
    c=coverage_case();p=c['proof'];partial=ByteGuard(p.files[:-1],p.inventories,p.absences)
    c['module']._tag_ready_continuity_guard(c['source'],partial)
    assert c['module'].capture_media_check_coverage(c['store'],c['source']) is None


@pytest.mark.parametrize('fault',['untagged','unknown_execution','missing_execution','unknown_revision',
                                'execution_override','reader_override','revision_override','capture_overflow'])
def test_unknown_or_unbounded_cases_retain_full_validation(coverage_case,fault):
    c=coverage_case();source=c['source'];kwargs={}
    if fault=='untagged':source=lambda:None
    elif fault=='unknown_execution':c['store'].execution_guard=lambda:None
    elif fault=='missing_execution':del c['store'].execution_guard
    elif fault=='unknown_revision':c['store'].revision_context={'guard':SimpleNamespace(verify_captured_bytes=lambda:None)}
    elif fault=='execution_override':c['check'].contract=lambda:{}
    elif fault=='reader_override':c['check'].admission_guard.verify=lambda:None
    elif fault=='revision_override':c['revision'].verify_captured_bytes=lambda:None
    else:kwargs['maximum_files']=0
    assert c['module'].capture_media_check_coverage(c['store'],source,**kwargs) is None


@pytest.mark.parametrize('fault',['callback','budget_binding','frozen','view','ancestor','reader_binding'])
def test_changed_live_validator_contract_falls_back(coverage_case,fault):
    c=coverage_case();coverage=c['module'].capture_media_check_coverage(c['store'],c['source'])
    assert coverage is not None
    if fault=='callback':c['store'].continuity_check=lambda:None
    elif fault=='budget_binding':c['check'].budget_artifact['sha256']='f'*64
    elif fault=='frozen':c['store'].frozen=copy(c['store'].frozen)
    elif fault=='view':c['revision'].views['new']='import'
    elif fault=='ancestor':c['revision'].ancestors.append(c['revision'])
    else:c['check'].admission_guard.artifacts[str(c['evidence'])]['sha256']='e'*64
    assert not coverage.applies(c['store'])


def test_qualified_clone_rechecks_its_own_callbacks(coverage_case):
    c=coverage_case();coverage=c['module'].capture_media_check_coverage(c['store'],c['source'])
    c['store']._media_check_coverage=coverage
    clone=c['store'].for_root('production/scene-composition')
    assert clone._media_check_coverage is coverage and coverage.applies(clone)
    clone.continuity_read_guard=lambda:None
    assert not coverage.applies(clone)


@pytest.mark.parametrize('operation',['write','global','send'])
def test_qualified_writes_and_sends_still_reject_actual_input_drift(coverage_case,operation):
    from video_ai.runtime.production_state import RunLock
    c=coverage_case();s=c['store']
    with RunLock(c['run']) as lock:
        s.lock=lock;s._media_check_coverage=c['module'].capture_media_check_coverage(s,c['source'])
        request=dict(frame_id='scene_0001_clip_0001:frame_000001');graph={'node':1}
        s.write('inputs.json',{});s.write(s.frame_dir(request['frame_id'])/'request.json',request)
        s.write(s.frame_dir(request['frame_id'])/'graph.json',graph)
        send=s.capture_guard(request,graph)
        c['budget'].write_text('{"budget":2}')
        action={'write':lambda:s.write('new.json',{}),'global':s.verify_global,'send':send}[operation]
        with pytest.raises((ValueError,OSError)):action()
        assert not s.path('new.json').exists()


from test_scene_upscale_transactions import transaction,Client


@pytest.mark.parametrize('qualified',[False,True])
def test_actual_media_store_protocol_with_measured_costs_and_original_180s(coverage_case,transaction,monkeypatch,qualified):
    """Fixture-only clock model; all writes use the real media store implementation."""
    from video_ai.runtime import scene_upscale_transactions as protocol
    from video_ai.runtime.production_state import RunLock
    c=coverage_case();s=c['store'];_,request,graph,template=transaction
    with RunLock(c['run']) as lock:
        s.lock=lock
        if qualified:s._media_check_coverage=c['module'].capture_media_check_coverage(s,c['source'])
        s.write('inputs.json',{});s.write(s.frame_dir(request['frame_id'])/'request.json',request)
        s.write(s.frame_dir(request['frame_id'])/'graph.json',graph)
        client=Client(s,request,graph);client.ownership_check=lambda:None;network=[]
        for name in ('object_info','submit','queue','history'):
            original=getattr(client,name)
            def guarded(*a,_name=name,_original=original,**kw):
                client.ownership_check();network.append((_name,c['clock'][0]))
                return _original(*a,**kw)
            monkeypatch.setattr(client,name,guarded)
        c['clock'][0]=0;c['calls'].clear()
        monkeypatch.setattr(protocol.time,'monotonic',lambda:c['clock'][0])
        def ensure():s.verify_global();c['clock'][0]+=30;s.verify_global()
        call=lambda:protocol.recover_or_submit_scene_frame(s,request,graph,client=client,
            template=template,ensure_service=ensure,logger=None,timeout=180)
        if qualified:
            result=call();assert result['prompt_id']==client.pid and client.posts==1
            assert c['clock'][0]<180
            assert c['calls'].count('execution')==0
        else:
            with pytest.raises(protocol.SceneSubmitUnknown):call()
            assert client.posts<=1
        assert all(at<180 for _,at in network)
        print(dict(fixture_only=True,qualified=qualified,elapsed=c['clock'][0],posts=client.posts,
            source_checks=c['calls'].count('source'),execution_checks=c['calls'].count('execution'),network=network))


def test_noncovered_revision_addition_is_checked_before_next_write(coverage_case):
    from video_ai.runtime.production_state import RunLock
    c=coverage_case();s=c['store']
    with RunLock(c['run']) as lock:
        s.lock=lock;s._media_check_coverage=c['module'].capture_media_check_coverage(s,c['source'])
        new=c['run']/'new.json';new.write_text('{}');c['revision'].capture(new,root=c['run'])
        new.write_text('{"changed":true}')
        with pytest.raises((ValueError,OSError)):s.write('new.json',{})
        assert not s.path('new.json').exists()


def test_revision_contract_changed_inside_full_callback_is_checked_before_write(coverage_case,monkeypatch):
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime._continuity_byte_guard import ByteGuard
    c=coverage_case();s=c['store'];original=ByteGuard.verify;changed=[]
    with RunLock(c['run']) as lock:
        s.lock=lock;s._media_check_coverage=c['module'].capture_media_check_coverage(s,c['source'])
        def verify(proof):
            result=original(proof)
            if proof is c['proof'] and not changed:
                changed.append(True);path=c['run']/'new-input.json';path.write_text('{}')
                c['revision'].capture(path,root=c['run']);path.write_text('{"later":true}')
            return result
        monkeypatch.setattr(ByteGuard,'verify',verify)
        with pytest.raises((ValueError,OSError)):s.write('not-accepted.json',{})
        assert changed and not s.path('not-accepted.json').exists()


def test_new_media_artifact_on_clone_remains_a_live_guard(coverage_case):
    from video_ai.runtime.production_state import RunLock
    c=coverage_case();s=c['store']
    with RunLock(c['run']) as lock:
        s.lock=lock;s._media_check_coverage=c['module'].capture_media_check_coverage(s,c['source'])
        clone=s.for_root('production/scene-composition')
        path=c['run']/'new-media.json';path.write_text('{}')
        clone.bind_artifact(clone.artifact(path));path.write_text('{"later":true}')
        with pytest.raises((ValueError,OSError)):clone.verify_global()
