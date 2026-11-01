"""A send audits each unchanged global Artifact once, retaining original captures."""
from test_scene_media_check_coverage import coverage_case
import pytest


def prepare(c):
    from video_ai.runtime.production_state import RunLock
    s=c['store'];lock=RunLock(c['run']);lock.__enter__();s.lock=lock
    s._media_check_coverage=c['module'].capture_media_check_coverage(s,c['source'])
    s.bind_artifact(s.artifact(c['budget']))
    request=dict(frame_id='scene_0001_clip_0001:frame_000001');graph={'node':1}
    s.write('inputs.json',{});s.write(s.frame_dir(request['frame_id'])/'request.json',request)
    s.write(s.frame_dir(request['frame_id'])/'graph.json',graph)
    return s,lock,s.capture_guard(request,graph)


def test_same_global_artifact_is_not_rehashed_again_after_full_global_guard(coverage_case,monkeypatch):
    c=coverage_case();s,lock,guard=prepare(c);calls=[];original=s.validate_artifact
    def validate(value):calls.append(value['path']);return original(value)
    monkeypatch.setattr(s,'validate_artifact',validate)
    try:
        guard()
        assert calls.count(str(c['budget']))==1
    finally:lock.__exit__(None,None,None)


@pytest.mark.parametrize('change',['removed','rebound'])
def test_send_still_checks_original_snapshot_when_current_binding_changes(coverage_case,monkeypatch,change):
    c=coverage_case();s,lock,guard=prepare(c);original=s.verify_global
    def changed():
        original();c['budget'].write_text('{"changed":true}')
        if change=='removed':s.guard_paths.pop(str(c['budget']))
        else:s.guard_paths[str(c['budget'])]=s.artifact(c['budget'])
    monkeypatch.setattr(s,'verify_global',changed)
    try:
        with pytest.raises((ValueError,OSError)):guard()
    finally:lock.__exit__(None,None,None)


def test_non_global_request_and_graph_are_still_physically_checked(coverage_case,monkeypatch):
    c=coverage_case();s,lock,guard=prepare(c);original=s.verify_global
    path=s.frame_dir('scene_0001_clip_0001:frame_000001')/'graph.json'
    def changed():original();path.write_text('{"different":true}')
    monkeypatch.setattr(s,'verify_global',changed)
    try:
        with pytest.raises((ValueError,OSError)):guard()
    finally:lock.__exit__(None,None,None)


def test_captured_artifacts_are_independent_of_in_place_binding_updates(coverage_case):
    c=coverage_case();s,lock,_=prepare(c)
    path=c['run']/'supplement.bin';path.write_bytes(b'a');s.bind_artifact(s.artifact(path))
    request=dict(frame_id='scene_0001_clip_0001:frame_000001');graph={'node':1}
    guard=s.capture_guard(request,graph)
    try:
        path.write_bytes(b'b');s.guard_paths[str(path)].update(s.artifact(path))
        with pytest.raises((ValueError,OSError)):guard()
    finally:lock.__exit__(None,None,None)
