"""Common-prefix admission coalesces pure reads before any persistence."""
from types import SimpleNamespace

from video_ai.runtime import production_scene_pipeline as pipeline, scene_revision_records as records


def test_common_prefix_reuses_one_pure_read_admission(runtime_run, monkeypatch):
    run, _, _ = runtime_run
    source = run/'history.json'
    source.write_bytes(b'{}')
    frozen = SimpleNamespace(options={'script_path': str(run/'production/script.txt'), 'scene_revision': {}})
    guard = records.RevisionGuard(frozen)
    guard.capture(source, root=run)
    proof = dict(imports={'common:all': {}}, invalidation={'dirty': {'common': []}})
    calls = []
    original = records.verify_artifact

    def counted(*a, **kw):
        calls.append(True)
        return original(*a, **kw)

    def revision(value):
        guard.verify_captured_bytes()
        return proof

    timeline = object()

    def common(value):
        for _ in range(3):
            guard.verify_captured_bytes()
        return {'units': 'original'}, timeline, 'inherited'

    monkeypatch.setattr(records, 'verify_artifact', counted)
    monkeypatch.setattr(pipeline, 'require_scene_revision', revision)
    monkeypatch.setattr(pipeline, 'common_inputs', common)
    monkeypatch.setattr(pipeline, 'record_common', lambda *a, **kw: {'ready': True})
    result = pipeline._common(frozen, paths=None, logger=None, lock=None)
    assert result == ({'units': 'original'}, timeline, {'ready': True})
    assert len(calls) == 2
