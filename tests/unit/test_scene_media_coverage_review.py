"""Fresh-review regressions: callback changes and actual ancestor/cache bindings."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from test_scene_media_check_coverage import coverage_case


@pytest.mark.parametrize('operation',['global','send'])
@pytest.mark.parametrize('change',['budget','callback','missing_callback'])
def test_changed_execution_binding_inside_source_callback_refuses_global_and_send(coverage_case,monkeypatch,operation,change):
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime._continuity_byte_guard import ByteGuard
    c=coverage_case();s=c['store'];original=ByteGuard.verify;changed=[]
    with RunLock(c['run']) as lock:
        s.lock=lock;s._media_check_coverage=c['module'].capture_media_check_coverage(s,c['source'])
        request=dict(frame_id='scene_0001_clip_0001:frame_000001');graph={'node':1}
        s.write('inputs.json',{});s.write(s.frame_dir(request['frame_id'])/'request.json',request)
        s.write(s.frame_dir(request['frame_id'])/'graph.json',graph)
        send=s.capture_guard(request,graph)
        def verify(proof):
            result=original(proof)
            if proof is c['proof'] and not changed:
                changed.append(True)
                if change=='budget':c['check'].budget_artifact['sha256']='f'*64
                elif change=='missing_callback':s.execution_guard=None
                else:
                    def refuse():raise ValueError('replacement execution refuses')
                    s.execution_guard=refuse
            return result
        monkeypatch.setattr(ByteGuard,'verify',verify)
        with pytest.raises((ValueError,OSError)):(s.verify_global if operation=='global' else send)()
        assert changed


@pytest.mark.parametrize('change',['file','inventory','child_guard','override'])
def test_different_whole_ancestor_reader_is_not_certified_and_remains_live(coverage_case,change):
    from video_ai.runtime._whole_scene_admission import EvidenceReader
    from video_ai.runtime.scene_revision_records import RevisionGuard
    from video_ai.runtime.production_state import RunLock
    c=coverage_case();s=c['store']
    frozen=SimpleNamespace(options=dict(deepcopy(s.frozen.options),ancestor=True),config=s.frozen.config)
    ancestor=RevisionGuard(frozen);reader=EvidenceReader();reader.capture(c['evidence'])
    c['cache'][id(frozen)]=reader;ancestor.verify_frozen(frozen)
    c['revision'].ancestors.append(ancestor)
    coverage=c['module'].capture_media_check_coverage(s,c['source'])
    assert coverage is None
    path=c['run']/'ancestor-new.json';path.write_text('{}')
    if change=='file':reader.capture(path);path.write_text('{"changed":true}')
    elif change=='inventory':
        folder=c['run']/'ancestor-folder';folder.mkdir();reader.inventory(folder,'*.json')
        (folder/'new.json').write_text('{}')
    elif change=='child_guard':
        child=EvidenceReader();child.capture(path);reader.guards.append(child);path.write_text('{"changed":true}')
    else:
        def refuse():raise ValueError('custom ancestor validation refuses')
        reader.verify=refuse
    with RunLock(c['run']) as lock:
        s.lock=lock;s._media_check_coverage=coverage
        with pytest.raises((ValueError,OSError)):s.verify_global()


def test_admission_cache_rebinding_invalidates_existing_certificate(coverage_case):
    from video_ai.runtime._whole_scene_admission import EvidenceReader
    from video_ai.runtime.production_state import RunLock
    c=coverage_case();s=c['store'];coverage=c['module'].capture_media_check_coverage(s,c['source'])
    assert coverage is not None
    reader=EvidenceReader();reader.capture(c['evidence'])
    c['cache'][id(s.frozen)]=reader
    assert not coverage.applies(s)
    path=c['run']/'rebound-new.json';path.write_text('{}');reader.capture(path);path.write_text('{"changed":true}')
    with RunLock(c['run']) as lock:
        s.lock=lock;s._media_check_coverage=coverage
        with pytest.raises((ValueError,OSError)):s.verify_global()


def test_same_actual_whole_reader_can_cover_another_revision_guard(coverage_case):
    from video_ai.runtime.scene_revision_records import RevisionGuard
    c=coverage_case();ancestor=RevisionGuard(c['store'].frozen)
    ancestor.verify_frozen(ancestor.frozen);c['revision'].ancestors.append(ancestor)
    coverage=c['module'].capture_media_check_coverage(c['store'],c['source'])
    assert coverage is not None and coverage.applies(c['store'])


@pytest.mark.parametrize('writer',[False,True])
def test_existing_admission_cache_accessor_uses_original_key_without_validation(monkeypatch,writer):
    import video_ai.runtime.scene_execution_records as execution
    from video_ai.planning.production_scenes import canonical_digest
    frozen=SimpleNamespace(options={'role':'fixture'},config=SimpleNamespace(raw={'fixture':True}))
    cache={};token=execution._writer_admissions.set(cache if writer else None)
    monkeypatch.setattr(execution,'validation_memo',lambda name:cache)
    monkeypatch.setattr(execution,'rendering_mode',lambda f:'whole_scene_v1')
    def forbidden(*a,**kw):raise AssertionError('cache binding read must not rerun admission')
    monkeypatch.setattr(execution,'verify_whole_scene_frozen',forbidden)
    try:
        key=canonical_digest(dict(options=frozen.options,raw=frozen.config.raw))
        first=object();cache[key]={'guard':first}
        assert execution.cached_whole_scene_admission_guard(frozen) is first
        second=object();cache[key]={'guard':second}
        assert execution.cached_whole_scene_admission_guard(frozen) is second
        frozen.config.raw['changed']=True
        assert execution.cached_whole_scene_admission_guard(frozen) is None
    finally:execution._writer_admissions.reset(token)
