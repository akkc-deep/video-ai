"""TEST ONLY prompt revisions retain exact native meaning and fresh author gates."""
import copy
import json
import pytest
from storyboard_helpers import mock_generation,review_for,write_review


def revised(storyboard_run,monkeypatch):
    from video_ai.runtime import storyboard_checks as sc,speech_checks
    from video_ai.runtime.pipeline_import import derive_completed_stages
    from video_ai.runtime.pipeline_evidence import save_record
    from video_ai.runtime.manifest import hash_file,thaw,now
    parent,config,store,timing,path=storyboard_run
    mock_generation(monkeypatch)
    assert sc.plan_storyboard(config,run_dir=parent,timing_review_path=path).status=='review_required'
    assert sc.finalize_storyboard(config,run_dir=parent,review_path=write_review(parent,review_for(parent))).passed
    original=store.snapshot()
    base=save_record(parent,'manifest',original)
    changes=dict(schema_version=1,base_run_id=parent.name,base_manifest_snapshot_identity=thaw(base),
        created_at=now(),reason='TEST ONLY motion refinement',script_identity=None,unit_review_identity=None,
        config_identity=thaw(hash_file(config.config_file)),shot_changes=[dict(shot_id='shot_0002',
            image_prompt=None,video_prompt='visible motion with slow camera pan',reason='TEST ONLY refine camera')])
    change_path=parent/'logs/pipeline/test-changes.json'
    change_path.write_text(json.dumps(changes),encoding='utf-8')
    real=speech_checks.load_committed_speech
    # This fixture isolates prompt authoring; production acceptance is never written.
    monkeypatch.setattr(speech_checks,'load_committed_speech',lambda run:dict(real(run),accepted=True))
    child=derive_completed_stages(config,parent_run_dir=parent,stages=('speech','storyboard'),
        reason='TEST ONLY revision',changes_identity=hash_file(change_path),changes=changes)
    return sc,parent,child,config,store,original


def test_prompt_revision_requires_new_bound_review_and_preserves_parent(storyboard_run,monkeypatch):
    from video_ai.runtime.manifest import ManifestStore
    from video_ai.runtime.pipeline_stages import validate_checkpoint
    sc,parent,child,config,store,original=revised(storyboard_run,monkeypatch)
    draft=json.loads((child/'storyboard-draft.json').read_text(encoding='utf-8'))
    assert draft['shots'][1]['video_prompt']=='visible motion with slow camera pan'
    assert not (child/'storyboard.json').exists()
    snapshot=ManifestStore.open(child).snapshot()
    assert snapshot['stages']['storyboard']['status']=='running'
    assert validate_checkpoint('storyboard',config,child,snapshot)['draft_complete']
    with pytest.raises(ValueError):sc.load_committed_storyboard(child)
    review=write_review(child,review_for(child))
    assert sc.finalize_storyboard(config,run_dir=child,review_path=review).passed
    report=sc.load_committed_storyboard(child)
    origin=sc.load_committed_storyboard(parent)
    for a,b in zip(report['shots'],origin['shots']):
        for key in a:
            if key!='video_prompt':assert a[key]==b[key]
    assert store.snapshot()==original


def test_revision_cannot_modify_bound_requirements(storyboard_run,monkeypatch):
    from video_ai.runtime._pipeline_storyboard_revision import validate_revision
    sc,parent,child,config,store,original=revised(storyboard_run,monkeypatch)
    draft=json.loads((child/'storyboard-draft.json').read_text(encoding='utf-8'))
    bad=copy.deepcopy(draft);bad['shots'][1]['visual_requirements'][0]['source_quote']='changed text'
    with pytest.raises(ValueError,match='revision|origin|differs'):validate_revision(config,child,bad)
