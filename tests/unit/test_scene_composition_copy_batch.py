"""Every copied frame keeps its own byte proof, without repeating whole history."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from video_ai.runtime import _scene_composition_materialized as media
from video_ai.runtime.scene_revision_records import RevisionGuard, artifact, verify_artifact
from video_ai.runtime.production_state import RunLock
from video_ai.config import read_json


def test_frame_copy_batch_checks_history_only_at_boundaries(runtime_run):
    run, _, _ = runtime_run
    source = run/'sources'
    source.mkdir()
    output = run/'materialized'
    (output/'frames').mkdir(parents=True)
    rows = []
    guard = RevisionGuard(SimpleNamespace(options={'script_path': str(run/'production/script.txt')}))
    for i in range(8):
        path = source/f'{i}.png'
        path.write_bytes(f'original pixels {i}'.encode())
        bound = guard.capture(path, root=run)
        rows.append({'image': bound})
    checks = []
    writes = []
    with RunLock(run) as held:
        def global_check():
            checks.append(True)
            guard.verify_captured_bytes()

        def write_check():
            writes.append(True)
            assert read_json(held.path) == held.owner

        store = SimpleNamespace(run_dir=run, verify_global=global_check, assert_write=write_check,
            validate_artifact=lambda value: verify_artifact(value, root=run),
            artifact=lambda path: artifact(path, root=run))
        result = media.copy_frame_sequence(store, rows, output)
        assert len(checks) == 2
        assert len(writes) >= 16
        assert [Path(value['path']).read_bytes() for value in result] == [f'original pixels {i}'.encode() for i in range(8)]
        assert [value['sha256'] for value in result] == [row['image']['sha256'] for row in rows]


def test_frame_batch_final_source_check_is_not_skipped(runtime_run):
    run, _, _ = runtime_run
    path = run/'source.png'
    path.write_bytes(b'original pixels')
    output = run/'materialized'
    (output/'frames').mkdir(parents=True)
    guard = RevisionGuard(SimpleNamespace(options={'script_path': str(run/'production/script.txt')}))
    bound = guard.capture(path, root=run)
    calls = []

    def global_check():
        calls.append(True)
        if len(calls) == 2:
            path.write_bytes(b'changed! pixels')
        guard.verify_captured_bytes()

    store = SimpleNamespace(run_dir=run, verify_global=global_check, assert_write=lambda: None,
        validate_artifact=lambda value: verify_artifact(value, root=run), artifact=lambda target: artifact(target, root=run))
    with pytest.raises(ValueError, match='captured bytes changed'):
        media.copy_frame_sequence(store, [{'image': bound}], output)
