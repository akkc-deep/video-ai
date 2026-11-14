from types import SimpleNamespace
from video_ai.runtime import reference_image_records as refs, scene_revision_records as records
from video_ai.runtime import _scene_revision_origins as origins, _scene_revision_readers as readers, production_inputs
from unit.test_review_admission_optimization import admission_fixture

def test_inherited_provenance_reuses_typed_timeline(monkeypatch):
    source=object(); target=object(); scene={'scene_id':'s'}; timeline={'test':1}; calls=[]
    monkeypatch.setattr(readers,'proof_for',lambda f,*a: {'source_run':'source','source_frozen':source,'guard':SimpleNamespace(verify_captured_bytes=lambda:None)} if f is target else None)
    monkeypatch.setattr(production_inputs,'load_frozen_inputs',lambda p:source)
    monkeypatch.setattr(origins,'common',lambda f:{'units':{},'timeline':timeline})
    monkeypatch.setattr(origins.ProductionTimeline,'from_dict',lambda v:calls.append(v) or object())
    monkeypatch.setattr(refs.images,'load_committed_plan',lambda *a:({}, {'scenes':[scene]}))
    monkeypatch.setattr(refs,'_committed',lambda *a: (_ for _ in ()).throw(LookupError('origin reached')))
    with records.revision_artifact_batch():
        for _ in range(2):
            try:refs.verify_reference_provenance(target,scene,{}, {})
            except LookupError:pass
    assert len(calls)==1

def test_batch_reviews_build_context_once(monkeypatch,admission_fixture):
    from video_ai.runtime import production_scene_clips as clips
    calls=[]
    monkeypatch.setattr(clips,'_entry',lambda *a,operation,**kw:operation(admission_fixture.context))
    monkeypatch.setattr(clips,'_consume',lambda ctx,path:calls.append(path) or SimpleNamespace(status='awaiting_continuity_review'))
    result=clips.consume_scene_clip_observations(None,None,None,['a','b'],paths=None,logger=None)
    assert calls==['a','b']
    assert result.status=='awaiting_continuity_review'

def test_batch_stops_on_failed_review(monkeypatch,admission_fixture):
    from video_ai.runtime import production_scene_clips as clips
    calls=[]
    monkeypatch.setattr(clips,'_entry',lambda *a,operation,**kw:operation(admission_fixture.context))
    monkeypatch.setattr(clips,'_consume',lambda ctx,path:calls.append(path) or SimpleNamespace(status='blocked'))
    result=clips.consume_scene_clip_observations(None,None,None,['a','b'],paths=None,logger=None)
    assert calls==['a']
    assert result.status=='blocked'


def test_inherited_provenance_reuses_source_plan(monkeypatch):
    source=object(); target=object(); scene={'scene_id':'s'}; calls=[]
    guard=SimpleNamespace(verify_captured_bytes=lambda:None)
    monkeypatch.setattr(readers,'proof_for',lambda f,*a: {'source_run':'source','source_frozen':source,'guard':guard} if f is target else None)
    monkeypatch.setattr(origins,'common',lambda f:{'units':{},'timeline':{}})
    monkeypatch.setattr(origins,'origin_timeline',lambda v:None)
    monkeypatch.setattr(refs.images,'load_committed_plan',lambda *a:calls.append(1) or ({},{'scenes':[scene]}))
    monkeypatch.setattr(refs,'_committed',lambda *a: (_ for _ in ()).throw(LookupError()))
    with records.revision_artifact_batch():
        for _ in range(2):
            try:refs.verify_reference_provenance(target,scene,{}, {})
            except LookupError:pass
    assert len(calls)==1

def test_cached_source_plan_still_checks_source_changes(monkeypatch):
    import pytest
    source=object(); target=object(); scene={'scene_id':'s'}; changed=[False]
    def verify():
        if changed[0]:raise ValueError('source changed')
    monkeypatch.setattr(readers,'proof_for',lambda f,*a: {'source_run':'source','source_frozen':source,'guard':SimpleNamespace(verify_captured_bytes=verify)} if f is target else None)
    monkeypatch.setattr(origins,'common',lambda f:{'units':{},'timeline':{}})
    monkeypatch.setattr(origins,'origin_timeline',lambda v:None)
    monkeypatch.setattr(refs.images,'load_committed_plan',lambda *a:({},{'scenes':[scene]}))
    monkeypatch.setattr(refs,'_committed',lambda *a: (_ for _ in ()).throw(LookupError()))
    with records.revision_artifact_batch():
        with pytest.raises(LookupError):refs.verify_reference_provenance(target,scene,{}, {})
        changed[0]=True
        with pytest.raises(ValueError,match='source changed'):refs.verify_reference_provenance(target,scene,{}, {})

def test_prior_batches_reused_and_changes_rejected(tmp_path, monkeypatch):
    import pytest
    from video_ai.runtime.manifest import hash_file
    path=tmp_path/'accepted.json';path.write_bytes(b'original');calls=[]
    def load(*a,**kw):
        calls.append(1);hash_file(path);return [{'accepted':True}]
    monkeypatch.setattr(refs.images,'_load_accepted',load)
    frozen=SimpleNamespace(options={});plan={'batches':[['s']]};scene={'scene_id':'s'}
    with pytest.raises(ValueError,match='byte proof'):
        with records.revision_artifact_batch():
            assert refs._prior(frozen,{},plan,scene)==refs._prior(frozen,{},plan,scene)
            assert len(calls)==1
            path.write_bytes(b'changed')

def test_read_boundary_shares_fresh_artifact_reads(tmp_path, monkeypatch):
    from video_ai.runtime import manifest
    path=tmp_path/'shared.json';path.write_bytes(b'original')
    frozen=SimpleNamespace(options={'script_path':str(tmp_path/'production/script.txt')})
    guards=[records.RevisionGuard(frozen) for _ in range(4)]
    for guard in guards:guard.capture(path,root=tmp_path)
    calls=[];original=manifest._hash_open_file
    def counted(*a):calls.append(1);return original(*a)
    monkeypatch.setattr(manifest,'_hash_open_file',counted)
    records._verify_read_boundary({'inputs':{},'checked':dict.fromkeys(guards)})
    assert len(calls)<=2  # first fresh read plus batch exit, not once per overlapping guard

def test_repeated_guard_inside_same_capture_is_shared(tmp_path, monkeypatch):
    from video_ai.runtime._continuity_byte_guard import capture_reads
    from video_ai.runtime import manifest
    path=tmp_path/'source.json';path.write_bytes(b'original')
    frozen=SimpleNamespace(options={'script_path':str(tmp_path/'production/script.txt')})
    guard=records.RevisionGuard(frozen);guard.capture(path,root=tmp_path)
    calls=[];original=manifest._hash_open_file
    def counted(*a):calls.append(1);return original(*a)
    monkeypatch.setattr(manifest,'_hash_open_file',counted)
    with records.revision_read_transaction():
        with capture_reads() as capture:
            guard.verify_captured_bytes();guard.verify_captured_bytes()
            assert len(calls)==1
        assert capture.finish().file_count==1
