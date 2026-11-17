"""Guard integration: each return is a fresh boundary, never a send-wide cache."""
from copy import deepcopy
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from video_ai.runtime import manifest, verification
from video_ai.runtime.scene_clip_records import SceneClipStore
from video_ai.runtime.scene_media_records import SceneMediaStore
from video_ai.runtime.production_state import RunLock


@pytest.mark.parametrize('kind', ['clip', 'media'])
@pytest.mark.parametrize('experiment', [False, True])
def test_guard_owns_one_pass_and_preserves_semantic_checks(runtime_run, monkeypatch, kind, experiment):
    from video_ai.runtime import _protected_continuity_inputs as protected
    from video_ai.runtime.scene_validation_pass import candidate_scene_validation
    run, _, paths = runtime_run
    frozen = SimpleNamespace(options={'model_stamps': {}}, config=SimpleNamespace(raw={}))
    source = run/'shared.bin'; source.write_bytes(b'shared input')
    cid = 'scene_0001_clip_0001'
    with RunLock(run) as held:
        cls = SceneClipStore if kind == 'clip' else SceneMediaStore
        store = cls(frozen, run, paths=paths, lock=held, clip_ids=[cid])
        value = store.artifact(source); store.guard_paths[str(source)] = deepcopy(value)
        request = dict(clip_id=cid, parent=None, source=value) if kind == 'clip' else dict(frame_id=cid+':frame_000001', source=value)
        folder = store.clip_dir(cid) if kind == 'clip' else store.frame_dir(request['frame_id'])
        graph = {'node': 'original'}
        store.write('inputs.json', {})
        for name, content in [('input.json', {}), ('request.json', request), ('graph.json', graph)]:
            store.write(folder/name, content)
        guard = store.capture_guard(request, graph)
        calls = []; passes = []; owns = []
        original = store._validate_artifact_uncached; owned = store.assert_owned
        def strict(value):
            calls.append(value['path']); passes.append(protected._current_read_pass())
            return original(value)
        def assert_owned():
            owns.append(1); return owned()
        monkeypatch.setattr(store, '_validate_artifact_uncached', strict)
        monkeypatch.setattr(store, 'assert_owned', assert_owned)
        with verification.whole_input_protection(), candidate_scene_validation() if experiment else nullcontext():
            manifest.hash_file(source)
            guard(); guard()
        assert all((p is not None) == experiment for p in passes)
        if experiment: assert passes[0] is not passes[-1]
        assert calls.count(str(source)) == (4 if kind == 'clip' and not experiment else 2)
        assert len(owns) == 2
        # Changing the saved request after the first send still prevents the next.
        (folder/'request.json').write_text('{}')
        with pytest.raises(ValueError): guard()


def test_clip_global_inventory_reused_only_with_exit_recheck(runtime_run, monkeypatch):
    from video_ai.runtime.scene_validation_pass import scene_validation_pass
    from video_ai.runtime import _continuity_byte_guard as byte
    run, _, paths = runtime_run
    frozen = SimpleNamespace(options={'model_stamps': {}}, config=SimpleNamespace(raw={}))
    directory = run/'evidence'; directory.mkdir()
    scans = []; scan = byte._scan
    def counted(spec, deadline):
        if spec.path == str(directory): scans.append(spec)
        return scan(spec, deadline)
    monkeypatch.setattr(byte, '_scan', counted)
    with RunLock(run) as held:
        store = SceneClipStore(frozen, run, paths=paths, lock=held)
        store.guard_directories[str(directory)] = set()
        with verification.whole_input_protection(), scene_validation_pass():
            store.verify_global(); store.verify_global()
            assert len(scans) == 1
        assert len(scans) == 2


def test_composition_capture_flushes_its_own_scope(runtime_run, monkeypatch):
    from video_ai.runtime import production_scene_composition as composition
    from video_ai.runtime import _protected_continuity_inputs as protected
    from video_ai.runtime.scene_validation_pass import verify_inventory_once
    from video_ai.runtime.scene_validation_pass import candidate_scene_validation
    run, _, _ = runtime_run
    directory = run/'inventory'; directory.mkdir()
    frozen = SimpleNamespace(options={}, config=SimpleNamespace(raw={}))
    store = SimpleNamespace(lock=None, frozen=frozen, revision_context=None)
    base = SimpleNamespace(**vars(store))
    class Stop(Exception): pass
    def check():
        assert protected._current_read_pass() is not None
        verify_inventory_once(directory, set(), recursive=True, strict_check=lambda: None)
        (directory/'new.json').write_text('{}')
        raise Stop()
    store.verify_captured_bytes = check
    with verification.whole_input_protection(), candidate_scene_validation(), pytest.raises(ValueError, match='inventory'):
        composition._capture_composition_guard(dict(store=base, composition_store=store), {})
