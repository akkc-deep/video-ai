"""Real CPU candidate transaction; source and natural authority are isolated fixtures."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import pytest
from test_natural_repair_media import natural_media


@pytest.fixture
def ready_candidate(natural_media,monkeypatch):
    from video_ai.runtime import production_natural_repair as p
    from video_ai.runtime.natural_study_records import put_json
    from video_ai.runtime._scene_continuity_io import artifact
    from video_ai.runtime.manifest import now,thaw,hash_file
    run,config,paths,manifest,report,_,video,report_path=natural_media
    material=put_json(run/'research/material/fixture-commit.json',dict(fixture_only=True))
    epoch=put_json(run/'fixture-epoch.json',dict(fixture_only=True))
    mref=put_json(run/'fixture-manifest.json',manifest)
    assessment=put_json(run/'fixture-assessment.json',dict(manifest=mref,report=artifact(report_path),created_at=now()))
    cp=artifact(Path('D:/VideoSi/projects/video-ai/continuity-benchmark/AI-repair-calibration-20261027-r2/experimental-repair-profile.json'))
    precheck=put_json(run/'fixture-precheck.json',dict(fixture_only=True))
    profile=put_json(run/'fixture-natural-profile.json',dict(fixture_only=True))
    context=dict(commit=material,epoch=epoch,assessment=assessment,source=artifact(video),frames=[f['record'] for f in manifest['clips'][0]['frames']])
    request=dict(schema_version=1,run_id=run.name,candidate_id=str(uuid4()),policy='research_candidate_natural_v1',
        material=material,epoch=epoch,assessment=assessment,pair_manifest=mref,conditional_profile=cp,natural_profile=profile,
        precheck=precheck,operation='exposure',operator_basis='software fixture only',revision_of=None,requested_at=now(),reason='CPU software test, not real natural acceptance')
    monkeypatch.setattr(p,'_prepare',lambda req:(run,context,manifest,report,config,paths))
    monkeypatch.setattr(p,'validate_precheck',lambda *a,**kw:dict(correction_direction='negative'))
    monkeypatch.setattr(p,'load_natural_repair_profile',lambda *a,**kw:dict(conditional_profile=cp))
    # Legacy closure replay is covered separately; avoid rehashing the multi-GB
    # historical experiment on each status/review in this media transaction test.
    import json
    from video_ai.runtime import _scene_color_repair_profile as legacy
    conditional=json.loads(Path(cp['path']).read_bytes())
    monkeypatch.setattr(legacy,'verified_profile',lambda *a,**kw:(conditional,[cp]))
    monkeypatch.setattr(p,'direction_thresholds',lambda *a,**kw:dict(noop_bias_ceiling=.001,minimum_bias_improvement=.001,
        maximum_frame_bias_regression=.001,maximum_off_axis_residual=.001,maximum_temporal_bias_increase=.001))
    return p,run,request


def test_real_cpu_candidate_review_failure_is_permanent_and_status_readonly(ready_candidate):
    from video_ai.runtime.natural_study_records import put_json,StudyReader
    from video_ai.runtime.manifest import now
    from video_ai.runtime.natural_candidate_records import VISUAL_CHECKS
    p,run,request=ready_candidate
    ref=put_json(run/'candidate-request.json',request);result=p.propose(ref)
    assert result['status']=='awaiting_review',result
    reader=StudyReader();folder=run/'research/natural-color-repair'/request['candidate_id']
    terminal=reader.any(result['terminal']);media=reader.any(terminal['media'])
    review=dict(schema_version=1,kind='natural_repair_visual_review_v1',candidate_id=request['candidate_id'],
        **{k:media[k] for k in ('source','candidate','playback','before_report','after_report')},
        review_method='human_video',reviewer='software fixture declaration only',viewed_at=now(),
        playback_ranges=[dict(media=m,start_frame=0,end_frame=4,fps='16/1') for m in (media['source'],media['playback'])],
        start_observation='fixture start',process_observation='fixture process',end_observation='fixture end',quality_observation='software test, not actual human acceptance',
        checks={k:'passed' for k in VISUAL_CHECKS},responses=[dict(risk=r,disposition='not_observed_in_full_playback',reason='constructed test response',references=[]) for r in media['risks']],issues=[],verdict='passed')
    passed=put_json(run/'review-passed.json',review)
    assert p.review(run,request['candidate_id'],passed)['status']=='research_candidate_reviewed'
    before={str(f):(f.read_bytes(),f.stat().st_mtime_ns) for f in folder.rglob('*') if f.is_file()}
    p.status(run,request['candidate_id'])
    assert before=={str(f):(f.read_bytes(),f.stat().st_mtime_ns) for f in folder.rglob('*') if f.is_file()}
    failed=deepcopy(review);failed['checks']['color_improvement']='failed';failed['verdict']='failed'
    failed['responses']=[dict(risk=r,disposition='confirmed_issue',reason='fixture failed observation',references=[]) for r in media['risks']]
    failed['issues']=[dict(check='color_improvement',media=media['playback'],frames=[0,4],description='fixture improvement rejected')]
    failure=put_json(run/'review-failed.json',failed)
    assert p.review(run,request['candidate_id'],failure)['status']=='review_failed'
    with pytest.raises(ValueError,match='cannot be overwritten'): p.review(run,request['candidate_id'],passed)


def test_real_media_interruption_keeps_all_outputs_and_does_not_rerender(ready_candidate,monkeypatch):
    from video_ai.runtime.natural_study_records import put_json
    p,run,request=ready_candidate
    def interrupt(point):
        if point=='media': raise KeyboardInterrupt()
    monkeypatch.setattr(p,'boundary',interrupt)
    ref=put_json(run/'candidate-request.json',request)
    with pytest.raises(KeyboardInterrupt): p.propose(ref)
    folder=run/'research/natural-color-repair'/request['candidate_id']
    master=folder/'media/master.mp4';before=(master.read_bytes(),master.stat().st_mtime_ns)
    assert p.propose(ref)['status']=='interrupted'
    assert before==(master.read_bytes(),master.stat().st_mtime_ns)
