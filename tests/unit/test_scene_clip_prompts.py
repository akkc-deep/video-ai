"""Clip conditioning inherits only from byte-guarded, compatible revision plans."""
import json
from types import SimpleNamespace

import pytest

from video_ai.runtime.production_state import ProductionRefused


@pytest.fixture
def chain(tmp_path, monkeypatch):
    from video_ai.runtime import scene_revision_records as records
    from unit.test_scene_revision import revision_fixture
    proofs = {}
    def make(name, origin=None, changes=None, *, imports=True, rendering=None, workflow='a'):
        run = tmp_path/name
        folder = run/'production/scene-revision'
        folder.mkdir(parents=True)
        raw = {} if rendering is None else {'scene_rendering': rendering}
        options = dict(script_path=str(run/'production/script.txt'),
            config_snapshot={'raw': raw}, workflow_snapshots={
                'wan': {'source_identity': {'bytes': 1, 'sha256': workflow*64}}})
        frozen = SimpleNamespace(options=options, config=SimpleNamespace(raw=raw))
        if origin is None and changes is None:
            return frozen
        options['scene_revision'] = {'sha256': name}
        _, request, _ = revision_fixture('regenerate_clips')
        request.update(scene_ids=[], choices=[], clip_ids=['scene_0001_clip_0001', 'scene_0002_clip_0001'])
        if changes is not None:
            request['clip_prompt_overrides'] = changes
        path = folder/'request.json'
        path.write_text(json.dumps(request), encoding='utf-8')
        guard = records.RevisionGuard(frozen)
        bound = guard.capture(path, root=run)
        proofs[id(frozen)] = dict(commit={'request': bound}, guard=guard, source_frozen=origin,
            imports={'plan:all': {}} if imports else {},
            invalidation={'dirty': {'clips': request['clip_ids']}})
        return frozen
    monkeypatch.setattr(records, 'require_scene_revision', lambda frozen: proofs[id(frozen)])
    return make, proofs


def test_legacy_without_revision_has_no_override(chain):
    from video_ai.runtime.scene_clip_prompts import effective_clip_prompt_overrides
    make, _ = chain
    assert effective_clip_prompt_overrides(make('base')) == {}


def test_nearest_override_wins_and_later_regeneration_keeps_prior_correction(chain):
    from video_ai.runtime.scene_clip_prompts import effective_clip_prompt_overrides
    make, _ = chain
    base = make('base')
    first = make('first', base, {'scene_0001_clip_0001': 'Rigid old.', 'scene_0002_clip_0001': 'Drift.'})
    second = make('second', first, {'scene_0001_clip_0001': 'Rigid new.'})
    third = make('third', second)
    assert effective_clip_prompt_overrides(third) == {
        'scene_0001_clip_0001': 'Rigid new.', 'scene_0002_clip_0001': 'Drift.'}


@pytest.mark.parametrize('boundary', ['plan', 'contract', 'workflow'])
def test_override_does_not_cross_plan_or_renderer_authority_boundary(chain, boundary):
    from video_ai.runtime.scene_clip_prompts import effective_clip_prompt_overrides
    make, _ = chain
    first = make('first', make('base'), {'scene_0001_clip_0001': 'Rigid.'})
    second = make('second', first, imports=boundary != 'plan',
        rendering={'prompt_policy': 'visual_v2'} if boundary == 'contract' else None,
        workflow='b' if boundary == 'workflow' else 'a')
    assert effective_clip_prompt_overrides(second) == {}


def test_override_requires_dirty_clip_and_legacy_mode(chain):
    from video_ai.runtime.scene_clip_prompts import effective_clip_prompt_overrides
    make, proofs = chain
    changed = make('changed', make('base'), {'scene_0001_clip_0001': 'Rigid.'})
    proofs[id(changed)]['invalidation']['dirty']['clips'] = []
    with pytest.raises(ProductionRefused, match='invalidation'):
        effective_clip_prompt_overrides(changed)
    unsupported = make('unsupported', make('otherbase'), {'scene_0001_clip_0001': 'Rigid.'},
        rendering={'mode': 'temporal_extension_v1'})
    with pytest.raises(ProductionRefused, match='legacy'):
        effective_clip_prompt_overrides(unsupported)


def test_changed_request_bytes_cannot_supply_a_new_override(chain):
    from video_ai.runtime.scene_clip_prompts import effective_clip_prompt_overrides
    make, proofs = chain
    changed = make('changed', make('base'), {'scene_0001_clip_0001': 'Rigid.'})
    path = proofs[id(changed)]['commit']['request']['path']
    from pathlib import Path
    request = json.loads(Path(path).read_text(encoding='utf-8'))
    request['clip_prompt_overrides']['scene_0001_clip_0001'] = 'Tampered.'
    Path(path).write_text(json.dumps(request), encoding='utf-8')
    with pytest.raises(ProductionRefused, match='changed'):
        effective_clip_prompt_overrides(changed)
