"""A numerical improvement or stale receipt cannot stand in for video review."""
from copy import deepcopy
import importlib
import importlib.util
from uuid import uuid4

import pytest

from scene_continuity_helpers import save,artifact


def validator():
    assert importlib.util.find_spec('video_ai.runtime._scene_color_repair_validation'), 'candidate playback validator missing'
    return importlib.import_module('video_ai.runtime._scene_color_repair_validation').validate_candidate_review


def review_fixture(run):
    from video_ai.runtime.manifest import now
    names=('terminal','source','candidate','playback','before_report','after_report','fit')
    refs={n:artifact(save(run/(n+'.json'),{'fixture_only':n})) for n in names}
    cid=str(uuid4());ranges=[dict(media=refs['source'],start_frame=0,end_frame=2),dict(media=refs['playback'],start_frame=0,end_frame=2)]
    expected=dict(run_id=run.name,candidate_id=cid,**refs,parent_chain=[],playback_ranges=ranges,created_at=now(),
        before_concerns=[dict(concern_id='color',detector_id='color_drift')],after_concerns=[],confirmed_colors={'color'})
    value=dict(schema_version=1,**{k:expected[k] for k in ('run_id','candidate_id','terminal','source','candidate','playback','parent_chain','before_report','after_report')},
        review_method='agent_video',reviewer='fixture_only synthetic software test',viewed_at=now(),playback_ranges=ranges,
        start_observation='fixture_only start',process_observation='fixture_only full process',end_observation='fixture_only end',
        quality_observation='fixture_only before color difference resolved; no actual playback claim',
        checks={k:'passed' for k in 'subject_identity appearance_structure color_improvement material_preservation motion_process camera_path parent_join no_new_flicker native_timing'.split()},
        responses=[dict(assessment=refs['before_report'],concern_id='color',disposition='resolved_in_candidate',
            reason='fixture_only candidate difference',references=[refs['after_report'],refs['fit']])],verdict='passed',issues=[])
    return value,expected


def test_full_review_boundaries_and_resolved_color_require_actual_ranges(runtime_run):
    from video_ai.runtime._scene_continuity_io import Reader
    value,expected=review_fixture(runtime_run[0]);validate=validator()
    assert validate(value,expected,reader=Reader())==value
    for key,bad in [('review_method','still_images'),('reviewer',''),('playback_ranges',[]),('responses',[]),('viewed_at','2999-01-01T00:00:00+00:00')]:
        invalid=deepcopy(value);invalid[key]=bad
        with pytest.raises(ValueError):validate(invalid,expected,reader=Reader())


@pytest.mark.parametrize('fault',['flicker','unverified','non_color_resolved','missing_fit','fake_pass','after_issue'])
def test_review_cannot_hide_failed_unverified_or_unresolved_risk(runtime_run,fault):
    from video_ai.runtime._scene_continuity_io import Reader
    value,expected=review_fixture(runtime_run[0])
    if fault=='flicker':value['checks']['no_new_flicker']='failed'
    elif fault=='unverified':value['checks']['material_preservation']='unverified'
    elif fault=='non_color_resolved':expected['before_concerns'][0]['detector_id']='motion_reset'
    elif fault=='missing_fit':value['responses'][0]['references']=[]
    elif fault=='fake_pass':value['responses'][0]['disposition']='confirmed_issue'
    else:
        expected['after_concerns']=[dict(concern_id='after',detector_id='local_color')]
        value['responses'].append(dict(assessment=expected['after_report'],concern_id='after',disposition='unverified',reason='fixture_only uncertain',references=[]))
    with pytest.raises(ValueError):validator()(value,expected,reader=Reader())


def test_confirmed_before_color_cannot_be_denied_by_a_passed_candidate_review(runtime_run):
    from video_ai.runtime._scene_continuity_io import Reader
    value,expected=review_fixture(runtime_run[0])
    value['responses'][0].update(disposition='not_observed_in_full_playback',references=[])
    with pytest.raises(ValueError):validator()(value,expected,reader=Reader())
