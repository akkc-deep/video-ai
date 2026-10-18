"""TEST ONLY: prompt revisions consume the original attributed source contract."""
import json

import pytest

from storyboard_helpers import review_for, write_review
from unit.test_storyboard_contract import setup_contract, grounded_model


@pytest.mark.parametrize('version', [1, 2])
def test_prompt_revision_retains_bound_source_contract_and_new_review_gate(
        storyboard_run, monkeypatch, version):
    from video_ai.planning.storyboard import (
        GROUNDED_POLICY, expand_boundary_requirements, primary_model_slots,
    )
    from video_ai.runtime import storyboard_checks as sc, speech_checks
    from video_ai.runtime.manifest import ManifestStore, hash_file, now, thaw
    from video_ai.runtime.pipeline_evidence import save_record
    from video_ai.runtime.pipeline_import import derive_completed_stages

    parent, config, store, timing, timing_path = storyboard_run
    slots, specs, model, contract, contract_path = setup_contract(storyboard_run)
    if version == 2:
        contract.update(schema_version=2, depiction_policy=GROUNDED_POLICY)
        contract_path.write_text(json.dumps(contract), encoding='utf-8')
        model = grounded_model(model, primary_model_slots(slots), specs)

    # Only the external model call is replaced. Contract, import, revision,
    # canonical validation, author binding and committed readers remain real.
    def generate(config, run, store, logger, slots, **kwargs):
        return expand_boundary_requirements(model, slots)[0], {}

    monkeypatch.setattr(sc, '_generate_owned', generate)
    assert sc.plan_storyboard(config, run_dir=parent,
                              timing_review_path=timing_path).status == 'review_required'
    assert sc.finalize_storyboard(config, run_dir=parent,
                                 review_path=write_review(parent, review_for(parent))).passed
    original = sc.load_committed_storyboard(parent)
    parent_manifest = store.snapshot()
    original_contract = hash_file(contract_path)
    snapshot = save_record(parent, 'manifest', parent_manifest)
    revised_prompt = original['shots'][1]['image_prompt'] + ' Clear exterior framing.'
    changes = dict(
        schema_version=1, base_run_id=parent.name,
        base_manifest_snapshot_identity=thaw(snapshot), created_at=now(),
        reason='TEST ONLY source-preserving static prompt revision',
        script_identity=None, unit_review_identity=None,
        config_identity=thaw(hash_file(config.config_file)),
        shot_changes=[dict(shot_id='shot_0002', image_prompt=revised_prompt,
                           video_prompt=None, reason='TEST ONLY framing refinement')],
    )
    changes_path = parent / 'logs/pipeline/test-source-contract-changes.json'
    changes_path.write_text(json.dumps(changes), encoding='utf-8')
    committed_speech = speech_checks.load_committed_speech
    # The pre-existing unit fixture has no real human listening receipt.
    monkeypatch.setattr(speech_checks, 'load_committed_speech',
                        lambda run: dict(committed_speech(run), accepted=True))
    child = derive_completed_stages(
        config, parent_run_dir=parent, stages=('speech', 'storyboard'),
        reason='TEST ONLY contracted prompt revision', changes=changes,
        changes_identity=hash_file(changes_path),
    )
    draft = json.loads((child / 'storyboard-draft.json').read_text(encoding='utf-8'))
    assert draft['shots'][1]['image_prompt'] == revised_prompt
    assert draft['provenance']['inputs']['visual_contract'] == original['provenance']['inputs']['visual_contract']
    assert not (child / 'logs/storyboard/visual-contract.json').exists()
    assert not (child / 'storyboard.json').exists()
    assert ManifestStore.open(child).snapshot()['stages']['storyboard']['status'] == 'running'
    with pytest.raises(ValueError):
        sc.load_committed_storyboard(child)

    assert sc.finalize_storyboard(config, run_dir=child,
                                 review_path=write_review(child, review_for(child))).passed
    report = sc.load_committed_storyboard(child)
    for current, previous in zip(report['shots'], original['shots']):
        expected = dict(previous)
        if previous['shot_id'] == 'shot_0002':
            expected['image_prompt'] = revised_prompt
        assert current == expected
    assert report['global_visual'] == original['global_visual']
    assert store.snapshot() == parent_manifest
    assert hash_file(contract_path).sha256 == original_contract.sha256

    # A later prompt-only revision (for example explicit image normalization)
    # must keep following the original author's contract and timing, rather
    # than treating the intermediate child's run_id as their author.
    child_store = ManifestStore.open(child)
    child_manifest = child_store.snapshot()
    next_changes = dict(changes, base_run_id=child.name,
                        base_manifest_snapshot_identity=thaw(save_record(child, 'manifest', child_manifest)))
    next_path = child / 'logs/pipeline/test-nested-contract-changes.json'
    next_path.write_text(json.dumps(next_changes), encoding='utf-8')
    descendant = derive_completed_stages(
        config, parent_run_dir=child, stages=('speech', 'storyboard'),
        reason='TEST ONLY nested contracted prompt revision', changes=next_changes,
        changes_identity=hash_file(next_path),
    )
    assert sc.finalize_storyboard(config, run_dir=descendant,
                                 review_path=write_review(descendant, review_for(descendant))).passed
    assert sc.load_committed_storyboard(descendant)['shots'] == report['shots']
    assert child_store.snapshot() == child_manifest

    # A formerly accepted child must stop consuming a changed original author
    # contract; changing a presentation does not grant new source authority.
    contract['reason'] = 'TEST ONLY later source-author mutation'
    contract_path.write_text(json.dumps(contract), encoding='utf-8')
    with pytest.raises((ValueError, OSError)):
        sc.load_committed_storyboard(child)
    with pytest.raises((ValueError, OSError)):
        sc.load_committed_storyboard(descendant)
