from copy import deepcopy
from uuid import uuid4
import pytest
from natural_study_helpers import save
from video_ai.runtime.manifest import now


def review_fixture(tmp_path):
    source=save(tmp_path/'source.json',dict(source=1));candidate=save(tmp_path/'master.json',dict(candidate=1))
    playback=save(tmp_path/'playback.json',dict(playback=1));report=save(tmp_path/'report.json',dict(report=1))
    expected=dict(source=source,candidate=candidate,playback=playback,before_report=report,after_report=report,
        frames=49,created_at='2026-10-28T00:00:00+00:00',risks=[])
    from video_ai.runtime.natural_candidate_records import VISUAL_CHECKS
    row=dict(schema_version=1,kind='natural_repair_visual_review_v1',candidate_id=str(uuid4()),
        **{k:expected[k] for k in ('source','candidate','playback','before_report','after_report')},
        review_method='human_video',reviewer='fixture only',viewed_at=now(),
        playback_ranges=[dict(media=m,start_frame=0,end_frame=49,fps='16/1') for m in (source,playback)],
        start_observation='fixture start',process_observation='fixture process',end_observation='fixture end',
        quality_observation='fixture only; not real natural evidence',checks={k:'passed' for k in VISUAL_CHECKS},responses=[],issues=[],verdict='passed')
    return row,expected


def test_full_visual_review_binds_source_candidate_playback_and_all_checks(tmp_path):
    from video_ai.runtime.natural_candidate_records import validate_visual_review
    row,expected=review_fixture(tmp_path)
    assert validate_visual_review(row,expected,identity=row['candidate_id'])=='passed'


@pytest.mark.parametrize('problem',['range','failure','unknown','future','wrong_media','missing_check','issue'])
def test_partial_unknown_or_failed_review_cannot_claim_improvement(tmp_path,problem):
    from video_ai.runtime.natural_candidate_records import validate_visual_review
    row,expected=review_fixture(tmp_path)
    if problem=='range': row['playback_ranges'][0]['end_frame']=48
    elif problem=='failure': row['checks']['motion_process']='failed'
    elif problem=='unknown': row['checks']['color_improvement']='unverified'
    elif problem=='future': row['viewed_at']='2999-01-01T00:00:00+00:00'
    elif problem=='wrong_media': row['playback']=row['source']
    elif problem=='missing_check': row['checks'].pop('material_preservation')
    else: row['issues']=[dict(check='motion_process',media=row['source'],frames=[0,1],description='fixture problem')]
    with pytest.raises(ValueError): validate_visual_review(row,expected,identity=row['candidate_id'])


def test_failed_visual_review_is_retained_and_unknown_is_not_passed(tmp_path):
    from video_ai.runtime.natural_candidate_records import validate_visual_review
    row,expected=review_fixture(tmp_path)
    row['checks']['color_improvement']='unverified';row['verdict']='unverified'
    assert validate_visual_review(row,expected,identity=row['candidate_id'])=='unverified'
    row['checks']['motion_process']='failed';row['verdict']='failed'
    row['issues']=[dict(check='motion_process',media=row['source'],frames=[0,49],description='fixture motion issue')]
    assert validate_visual_review(row,expected,identity=row['candidate_id'])=='failed'


def test_reordered_duplicate_risk_cannot_hide_an_unanswered_after_concern(tmp_path):
    from video_ai.runtime.natural_candidate_records import validate_visual_review
    row,expected=review_fixture(tmp_path)
    first=dict(phase='before',detector_id='local_color',concern_id='first')
    second=dict(phase='after',detector_id='motion_reset',concern_id='second')
    expected['risks']=[first,second]
    row['responses']=[dict(risk=risk,disposition='not_observed_in_full_playback',reason='fixture response',references=[])
        for risk in (first,dict(reversed(list(first.items()))))]
    with pytest.raises(ValueError): validate_visual_review(row,expected,identity=row['candidate_id'])


@pytest.fixture
def precheck_fixture(tmp_path,monkeypatch):
    from video_ai.runtime import natural_candidate_records as r
    from video_ai.runtime import scene_continuity_records as ordinary
    source=save(tmp_path/'source.json',dict(fixture=True));obs=save(tmp_path/'author.json',dict(fixture=True))
    manifest=save(tmp_path/'manifest.json',dict(fixture=True));report=save(tmp_path/'report.json',dict(fixture=True))
    assessment=save(tmp_path/'assessment.json',dict(report=report,created_at='2026-10-28T00:00:00+00:00'))
    req=dict(run_id='fixture',material=source,epoch=source,assessment=assessment,pair_manifest=manifest,operation='exposure',operator_basis='known fixture axis')
    context=dict(commit=source,source=source,frames=[source]*49,assessment=assessment)
    author=dict(natural_label='mild_color_bias',operation='exposure',correction_direction='negative',target_reference_confirmed=True,
        subject_structure_intact=True,motion_intact=True,intentional_lighting_change=False,unresolved=False,hard_noncolor_failure=False)
    monkeypatch.setattr(r,'registered_history',lambda *a,**kw:(dict(case_id='fixture',observations=[obs]),{}))
    monkeypatch.setattr(r,'read_author_observations',lambda *a,**kw:author)
    concerns=[dict(detector_id='local_color',concern_id='first'),dict(detector_id='motion_reset',concern_id='second')]
    monkeypatch.setattr(ordinary,'derive_concerns',lambda *a:concerns)
    risks=[dict(kind='observation',artifact=obs)]+[dict(kind='ordinary',concern=c) for c in concerns]
    value=dict(schema_version=1,source_kind='research_wan_material_v1',**req,source=source,observations=[obs],
        review_method='human_video',reviewer='software fixture only',viewed_at=now(),
        playback_ranges=[dict(media=source,start_frame=0,end_frame=49,fps='16/1')],color_issue='fixture known slight bias',correction_direction='negative',
        target_reference_confirmed=True,subject_structure_intact=True,motion_intact=True,intentional_lighting_change=False,
        responses=[dict(risk=risk,disposition='not_observed_in_full_playback',reason='fixture complete response',references=[]) for risk in risks])
    return r,value,req,context


def test_complete_precheck_accepts_each_distinct_registered_risk_once(precheck_fixture):
    from video_ai.runtime.natural_study_records import StudyReader
    r,value,req,context=precheck_fixture
    assert r.validate_precheck(value,req,context,StudyReader())['correction_direction']=='negative'


def test_precheck_reordered_duplicate_cannot_omit_noncolor_risk(precheck_fixture):
    from video_ai.runtime.natural_study_records import StudyReader
    r,value,req,context=precheck_fixture
    duplicate=deepcopy(value['responses'][1]);duplicate['risk']=dict(reversed(list(duplicate['risk'].items())))
    value['responses'][2]=duplicate
    with pytest.raises(ValueError): r.validate_precheck(value,req,context,StudyReader())
