from types import SimpleNamespace

import pytest

from video_ai.runtime import _scene_revision_copy as copies
from video_ai.runtime import scene_revision_records as records


@pytest.mark.parametrize('mutate',[False,True])
def test_structure_reuses_admitted_proof_and_rechecks_bytes(tmp_path,monkeypatch,mutate):
    import os
    path=tmp_path/'source.json';path.write_bytes(b'original')
    frozen=SimpleNamespace(options=dict(script_path=str(tmp_path/'production/script.txt'),scene_revision={}))
    guard=records.RevisionGuard(frozen);guard.capture(path,root=tmp_path)
    checks=[];verify=records.verify_artifact
    def counted(*args,**kwargs):
        checks.append(1);return verify(*args,**kwargs)
    monkeypatch.setattr(records,'verify_artifact',counted)
    proof=dict(guard=guard,commit={},imports={})
    def read():
        with records.revision_read_transaction():
            for _ in range(10):
                assert records.validate_revision_structure(frozen.options,tmp_path) is proof
            if mutate:
                stamp=path.stat();path.write_bytes(b'modified')
                os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    with records.revision_scope():
        records._context.get()['validated'][str(tmp_path)]=proof
        if mutate:
            with pytest.raises(ValueError,match='captured bytes changed'):read()
        else:read()
    assert len(checks)==2


def test_structure_reuse_rejects_changed_typed_options(tmp_path):
    frozen=SimpleNamespace(options=dict(script_path=str(tmp_path/'production/script.txt'),scene_revision={},flag=1))
    guard=records.RevisionGuard(frozen)
    with records.revision_scope():
        records._context.get()['validated'][str(tmp_path)]=dict(guard=guard)
        with pytest.raises(ValueError,match='frozen options changed'):
            records.validate_revision_structure(dict(frozen.options,flag=True),tmp_path)


@pytest.mark.parametrize('mutate',[False,True])
def test_reference_context_batches_checks_and_detects_changes(tmp_path,monkeypatch,mutate):
    from video_ai.runtime import _scene_revision_reference as references
    path=tmp_path/'source.json';path.write_bytes(b'original')
    frozen=SimpleNamespace(options=dict(script_path=str(tmp_path/'production/script.txt'),scene_revision={}))
    guard=records.RevisionGuard(frozen);guard.capture(path,root=tmp_path)
    checks=[];verify=records.verify_artifact
    def counted(*args,**kwargs):
        checks.append(1);return verify(*args,**kwargs)
    monkeypatch.setattr(records,'verify_artifact',counted)
    def proof(value):
        for _ in range(12):guard.verify_captured_bytes()
        if mutate:path.write_bytes(b'modified')
        return dict(imports={})
    monkeypatch.setattr(references,'require_scene_revision',proof)
    if mutate:
        with pytest.raises(ValueError,match='captured bytes changed'):
            references.source_reference_context(frozen)
    else:assert references.source_reference_context(frozen) is None
    assert len(checks)==2


@pytest.mark.parametrize('mutate',[False,True])
def test_final_revision_admission_groups_read_checks_before_ready(tmp_path,monkeypatch,mutate):
    from video_ai.runtime import production_scene_revision as revisions
    path=tmp_path/'source.json';path.write_bytes(b'original')
    frozen=SimpleNamespace(options=dict(script_path=str(tmp_path/'production/script.txt')))
    guard=records.RevisionGuard(frozen);guard.capture(path,root=tmp_path)
    checks=[];verify=records.verify_artifact
    def counted(*args,**kwargs):
        checks.append(1);return verify(*args,**kwargs)
    monkeypatch.setattr(records,'verify_artifact',counted)
    def structure(options,target):
        for _ in range(10):guard.verify_captured_bytes()
    def proof(value):
        for _ in range(10):guard.verify_captured_bytes()
        if mutate:path.write_bytes(b'modified')
    monkeypatch.setattr(revisions,'validate_revision_structure',structure)
    monkeypatch.setattr(revisions,'require_scene_revision',proof)
    if mutate:
        with pytest.raises(ValueError,match='captured bytes changed'):
            revisions._admit_created_revision(frozen,tmp_path)
    else:revisions._admit_created_revision(frozen,tmp_path)
    assert len(checks)==2


@pytest.mark.parametrize('mutate',[False,True])
def test_origin_capture_batch_reuses_read_checks_and_detects_changes(tmp_path,monkeypatch,mutate):
    from video_ai.runtime import production_scene_revision as revisions
    path=tmp_path/'source.json';path.write_bytes(b'original')
    guard=records.RevisionGuard(SimpleNamespace(options=dict(script_path=str(tmp_path/'production/script.txt'))))
    guard.capture(path,root=tmp_path)
    checks=[];verify=records.verify_artifact
    def counted(*args,**kwargs):
        checks.append(1)
        return verify(*args,**kwargs)
    monkeypatch.setattr(records,'verify_artifact',counted)
    calls=[]
    def capture(source,domain,key):
        calls.append((domain,key))
        for _ in range(12):guard.verify_captured_bytes()
        if mutate and key=='second':path.write_bytes(b'modified')
        return dict(guard=guard,value=key)
    from video_ai.runtime import _scene_revision_origins as origins
    monkeypatch.setattr(origins,'capture_origin',capture)
    nodes=[('image','first'),('image','second')]
    if mutate:
        with pytest.raises(ValueError,match='captured bytes changed'):
            revisions._capture_origins(None,nodes)
    else:
        result=revisions._capture_origins(None,nodes)
        assert list(result)==nodes
    assert calls==nodes
    assert len(checks)==2


@pytest.mark.parametrize('mutate',[False,True])
def test_copy_batch_checks_full_origin_at_boundaries(tmp_path,monkeypatch,mutate):
    path=tmp_path/'source.wav';path.write_bytes(b'original')
    frozen=SimpleNamespace(options=dict(script_path=str(tmp_path/'production/script.txt')))
    guard=records.RevisionGuard(frozen)
    source=guard.capture(path,root=tmp_path)
    checks=[];verify=records.verify_artifact
    def counted(*args,**kwargs):
        checks.append(1)
        return verify(*args,**kwargs)
    monkeypatch.setattr(records,'verify_artifact',counted)
    def copy(*args,**kwargs):
        for _ in range(4):guard.verify_captured_bytes()
        if mutate:path.write_bytes(b'modified')
        return source
    monkeypatch.setattr(copies,'copy_identity',copy)
    if mutate:
        with pytest.raises(ValueError,match='captured bytes changed'):
            copies.copy_media(None,'common:all','common','all',[('pcm_000001',source),('pcm_000002',source)],guard=guard)
    else:
        result=copies.copy_media(None,'common:all','common','all',[('pcm_000001',source),('pcm_000002',source)],guard=guard)
        assert len(result)==2
    assert len(checks)==2


@pytest.mark.parametrize('mutate',[False,True])
def test_revision_snapshot_reuses_checks_but_detects_source_changes(tmp_path,monkeypatch,mutate):
    from video_ai.runtime import production_scene_revision as revisions
    path=tmp_path/'source.json';path.write_bytes(b'original')
    guard=records.RevisionGuard(SimpleNamespace(options=dict(script_path=str(tmp_path/'production/script.txt'))))
    guard.capture(path,root=tmp_path)
    checks=[];verify=records.verify_artifact
    def counted(*args,**kwargs):
        checks.append(1);return verify(*args,**kwargs)
    monkeypatch.setattr(records,'verify_artifact',counted)
    def snapshot(*args,**kwargs):
        for _ in range(20):guard.verify_captured_bytes()
        if mutate:path.write_bytes(b'modified')
        return 'snapshot'
    monkeypatch.setattr(revisions,'_snapshot_contents',snapshot,raising=False)
    if mutate:
        with pytest.raises(ValueError,match='captured bytes changed'):revisions._snapshot(None)
    else:assert revisions._snapshot(None)=='snapshot'
    assert len(checks)==2
