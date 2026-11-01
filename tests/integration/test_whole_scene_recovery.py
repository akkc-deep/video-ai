"""Fixture-only recovery keeps original whole requests and readonly budgets."""
import json
from pathlib import Path

import pytest

from integration.test_scene_revision_flow import revision_source, tree_identity
from integration.test_whole_scene_flow import whole_setup, offline_whole_backend,whole_revision


def test_whole_reconfigure_defers_budget_when_common_must_be_rebuilt(revision_source,tmp_path,monkeypatch):
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_revision_records import require_scene_revision
    font=tmp_path/'fixture-only-font.ttf';font.write_bytes(b'fixture_only new font identity; no rendering claimed')
    result,_=whole_revision(revision_source,tmp_path,monkeypatch,font_file=font)
    assert result.status=='revision_ready',result.error
    frozen=load_frozen_inputs(result.run_dir)
    proof=require_scene_revision(frozen)
    assert proof['invalidation']['dirty']['common']==['all']
    assert 'common:all' not in proof['imports'] and 'plan:all' not in proof['imports']
    assert not (result.run_dir/'production/scene-rendering/execution-budget.json').exists()


def test_whole_rejected_request_stops_following_scenes(revision_source,tmp_path,monkeypatch):
    from scene_clip_helpers import generate
    setup=whole_setup(revision_source,tmp_path,monkeypatch)
    backend=offline_whole_backend(setup); backend.mode='rejected'
    result=generate(setup,backend)
    assert result.status in ('failed','blocked'),result.error
    assert len(backend.posts)==1
    before=len(backend.posts)
    assert generate(setup,backend).status in ('failed','blocked')
    assert len(backend.posts)==before


def test_whole_lost_response_and_missing_budget_never_submit_twice(revision_source,tmp_path,monkeypatch):
    from collections import Counter
    from copy import deepcopy
    from scene_clip_helpers import generate
    from video_ai.runtime import scene_execution_records
    from video_ai.runtime.scene_execution_records import load_scene_execution
    setup=whole_setup(revision_source,tmp_path,monkeypatch)
    evidence=scene_execution_records.verify_whole_scene_frozen(setup['frozen'])
    # The records tests and whole observation-gate case cover admission drift.
    # Use the flow test's fixture seam here to isolate request/budget recovery.
    monkeypatch.setattr(scene_execution_records,'verify_whole_scene_frozen',lambda *a,**k:evidence)
    execution=load_scene_execution(setup['frozen'],setup['plan'],setup['timeline'])
    expected_clips={row['clip_id'] for row in execution['clips']}
    backend=offline_whole_backend(setup); backend.mode='lost_response'
    first=generate(setup,backend)
    assert first.status in ('awaiting_continuity_review','blocked'),first.error
    original_posts=deepcopy(backend.posts)
    assert original_posts
    def posts_by_clip():
        return Counter(Path(row['prompt']['108']['inputs']['filename_prefix']).parent.name for row in backend.posts)
    initial_counts=posts_by_clip()
    assert set(initial_counts)<=expected_clips
    assert all(count==1 for count in initial_counts.values())
    backend.mode='normal'
    recovered=generate(setup,backend)
    assert recovered.status=='awaiting_continuity_review',recovered.error
    # Resolving the original task permits each previously unstarted scene once.
    # Count per clip: a larger total alone does not imply a repeated submission.
    assert backend.posts[:len(original_posts)]==original_posts
    assert posts_by_clip()=={clip_id:1 for clip_id in expected_clips}
    posts=len(backend.posts)
    root=setup['run']/'production/scene-rendering/execution-budget.json'
    raw=root.read_bytes();root.unlink()
    before=tree_identity(setup['run'])
    try:
        with pytest.raises(ValueError,match='budget.*missing'):
            load_scene_execution(setup['frozen'],setup['plan'],setup['timeline'])
        assert tree_identity(setup['run'])==before
        result=generate(setup,backend)
        assert result.status=='blocked',result.error
        assert not root.exists() and len(backend.posts)==posts
    finally: root.write_bytes(raw)
