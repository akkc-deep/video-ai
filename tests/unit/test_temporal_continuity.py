"""VCO-04 consumes genuine native-chain playback, retaining its original risk responses."""
from pathlib import Path
from uuid import UUID

from unit.test_temporal_scene_records import put
from unit.test_temporal_chain_records import chain_fixture,write_chain
from unit.test_temporal_scene_observations import author,NOW


def test_native_continuity_binding_names_real_result_not_comfy_record(runtime_run,monkeypatch):
    from video_ai.runtime.temporal_scene_records import temporal_progress_view
    from video_ai.runtime.scene_continuity_records import _binding
    records,context,row,window=chain_fixture(runtime_run,monkeypatch)
    context['execution']=dict(mode='temporal_extension_v1')
    write_chain(context,window)
    progress,view=temporal_progress_view(context)
    bound=_binding(context,view,window['budget']['clip_id'])
    assert Path(bound['clips'][0]['clip_record']['path']).name=='native-result.json'
    assert bound['clips'][0]['source_frames']==[0,93]
    assert view[window['budget']['clip_id']]['template']['scope']=='scene_temporal_chain_process'


def test_one_native_full_chain_playback_is_valid_prefix_for_vco04(runtime_run,monkeypatch):
    from video_ai.runtime.temporal_scene_observations import build_temporal_observation_template
    from video_ai.runtime.scene_continuity_records import validate_continuity_review
    records,context,row,window=chain_fixture(runtime_run,monkeypatch)
    folder,raw,result_id=write_chain(context,window)
    chain=records.validate_temporal_chain(context,'scene_0001',[window])
    template=build_temporal_observation_template(context,chain,scope='scene_temporal_chain_process')
    observation=put(folder/'actual-full.json',author(template))
    aid=str(UUID(int=123))
    assessment=dict(assessment_id=aid,created_at='2026-11-03T00:00:00+00:00',concerns=[])
    assessment_id=put(folder/'assessment.json',assessment)
    review=dict(schema_version=1,run_id=context['store'].run_dir.name,assessment_id=aid,assessment=assessment_id,
        video_observation=observation,prefix_observation=observation,reviewer=author(template)['reviewer'],reviewed_at=NOW.isoformat(),responses=[])
    expected=dict(run=context['store'].run_dir,assessment=assessment,assessment_artifact=assessment_id,
        binding=dict(clips=[dict(clip_id=f'fixture_{i}') for i in range(4)]),video_expected=dict(template=template,created_at=raw['created_at']))
    assert validate_continuity_review(review,expected,now=NOW)==review


def test_source_snapshot_validator_reads_native_record_without_comfy(runtime_run,monkeypatch):
    from video_ai.runtime.scene_clip_records import validate_clip
    records,context,row,window=chain_fixture(runtime_run,monkeypatch)
    context['execution']=dict(mode='temporal_extension_v1')
    write_chain(context,window)
    value=validate_clip(context,row)
    assert value['clip']['schema_version']==4 and value['clip']['native_result']==window['result']
    assert value['native_window']['raw_frames']==window['raw_frames']
    assert value['request']['selected_image']==window['selected_image']


def test_native_playback_keeps_every_risk_response_and_author_gate(runtime_run,monkeypatch):
    from copy import deepcopy
    import pytest
    from video_ai.runtime.temporal_scene_observations import build_temporal_observation_template
    from video_ai.runtime.scene_continuity_records import validate_continuity_review,_review_state,Reader
    from video_ai.runtime.production_state import ProductionRefused
    records,context,row,window=chain_fixture(runtime_run,monkeypatch)
    folder,raw,_=write_chain(context,window)
    chain=records.validate_temporal_chain(context,'scene_0001',[window])
    template=build_temporal_observation_template(context,chain,scope='scene_temporal_chain_process')
    observation=put(folder/'fixture-risk-full.json',author(template))
    aid=str(UUID(int=124))
    concerns=[dict(concern_id='fixture-risk-1'),dict(concern_id='fixture-risk-2')]
    assessment=dict(assessment_id=aid,created_at=raw['created_at'],concerns=concerns)
    assessment_id=put(folder/'fixture-risk-assessment.json',assessment)
    review=dict(schema_version=1,run_id=context['store'].run_dir.name,assessment_id=aid,assessment=assessment_id,
        video_observation=observation,prefix_observation=observation,reviewer=author(template)['reviewer'],
        reviewed_at=NOW.isoformat(),responses=[dict(concern_id=c['concern_id'],disposition='not_observed_in_full_playback',
            reason='fixture_only full playback declaration',references=[]) for c in concerns])
    expected=dict(run=context['store'].run_dir,assessment=assessment,assessment_artifact=assessment_id,
        binding=dict(clips=[dict(clip_id=row['budget']['clip_id'])]),video_expected=dict(template=template,created_at=raw['created_at']))
    assert validate_continuity_review(review,expected,now=NOW)==review
    for defect in ('missing','duplicate','author','different_prefix'):
        changed=deepcopy(review)
        if defect=='missing':changed['responses'].pop()
        elif defect=='duplicate':changed['responses'][1]=deepcopy(changed['responses'][0])
        elif defect=='author':changed['reviewer']='different fixture author'
        else:changed['prefix_observation']=assessment_id
        with pytest.raises(ProductionRefused):validate_continuity_review(changed,expected,now=NOW)
    for disposition,state in (('confirmed_issue','blocked'),('unverified','awaiting_review')):
        changed=deepcopy(review);changed['responses'][0]['disposition']=disposition
        assert validate_continuity_review(changed,expected,now=NOW)==changed
        assert _review_state(changed,Reader())==state
    assert assessment['concerns']==concerns

