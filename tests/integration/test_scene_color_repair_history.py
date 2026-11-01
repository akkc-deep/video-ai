"""Real ordinary reports preserve color-only exceptions and non-color failures."""
import json
from pathlib import Path
from uuid import uuid4

import pytest

from scene_continuity_helpers import analysis_request,review_request,save,snapshot
from scene_color_repair_helpers import repair_request
from test_scene_color_repair_flow import complete_setup,propose


@pytest.mark.parametrize('confirm_motion',[False,True])
def test_original_continuity_history_survives_new_epoch_and_fresh_precheck(runtime_run,monkeypatch,confirm_motion):
    from video_ai.runtime.production_scene_continuity import consume_scene_continuity_review,reassess_scene_continuity,analyze_scene_continuity
    from video_ai.runtime.manifest import now
    setup,old_request=complete_setup(runtime_run,monkeypatch)
    assessment=json.loads(setup['assessment'].read_text(encoding='utf-8'))
    review=review_request(setup,setup['assessment']);value=json.loads(review.read_text(encoding='utf-8'))
    concerns={row['concern_id']:row for row in assessment['concerns']}
    assert any(row['detector_id'] not in ('seam_color','local_color','color_drift','cumulative_color') for row in concerns.values())
    for response in value['responses']:
        color=concerns[response['concern_id']]['detector_id'] in ('seam_color','local_color','color_drift','cumulative_color')
        response['disposition']='confirmed_issue' if color or confirm_motion else 'not_observed_in_full_playback'
    save(review,value)
    consume_scene_continuity_review(setup['frozen'],[],setup['timeline'],review,paths=setup['paths'],logger=setup['logger'])
    epoch_request=save(setup['run']/'fixture_only-fresh-repair-epoch.json',dict(schema_version=1,run_id=setup['run'].name,
        epoch_id=str(uuid4()),previous_commit=assessment['epoch'],requested_at=now(),reason='fixture_only actual history check'))
    new_epoch=reassess_scene_continuity(setup['frozen'],[],setup['timeline'],epoch_request,paths=setup['paths'],logger=setup['logger'])
    assert new_epoch.status=='awaiting_analysis',new_epoch.error
    frozen_manifest=json.loads(Path(assessment['manifest']['path']).read_text(encoding='utf-8'))
    request=analysis_request(setup,new_epoch.epoch,count=2,manifest=frozen_manifest)
    analyzed=analyze_scene_continuity(setup['frozen'],[],setup['timeline'],request,paths=setup['paths'],logger=setup['logger'])
    assert analyzed.status=='awaiting_review',analyzed.error
    aid=json.loads(request.read_text(encoding='utf-8'))['assessment_id']
    new_assessment=setup['run']/f'production/scene-continuity/jobs/{aid}/assessment.json'
    profile=Path(json.loads(old_request.read_text(encoding='utf-8'))['profile']['path'])
    fresh=repair_request(setup,new_assessment,profile=profile)
    original=snapshot(setup['run']/'production/scene-clips')
    result=propose(setup,fresh)
    if confirm_motion:
        assert result.status=='blocked' and 'non-color' in result.error['message'],result.error
        assert result.intent is None and result.terminal is None
    else:assert result.status=='noop',result.error
    assert snapshot(setup['run']/'production/scene-clips')==original
