from copy import deepcopy

import pytest

from video_ai.runtime.scene_environment_repair import apply_decisions


def test_explicit_model_decision_preserves_scene_and_cites_original_source():
    group=dict(key='space',environment='space',time='night',lighting='stars',spatial_relations=[],
               source_facts=[],creative_choices=[],change_sources=[])
    proposal=dict(scene_groups=[group],scenes=[dict(unit_ids=['speech_0001'],scene_group_id='missing',
        image_prompt='original image',motion_prompt='original motion',summary='original',change_sources=[])])
    before=deepcopy(proposal)
    catalog={'speech_0001':dict(unit_id='speech_0001',text_start=0,text_end=3,quote='sky')}
    fixed=apply_decisions(proposal,{'scene_0001':dict(reuse='space',change_sources=[])},[0],catalog)
    assert fixed['scenes'][0]['scene_group_id']=='space'
    assert fixed['scenes'][0]['image_prompt']=='original image'
    assert proposal==before
    with_evidence=deepcopy(proposal)
    with_evidence['scenes'][0]['change_sources']=[catalog['speech_0001']]
    preserved=apply_decisions(with_evidence,{'scene_0001':dict(reuse='space',change_sources=[])},[0],catalog)
    assert preserved['scenes'][0]['change_sources']==[catalog['speech_0001']]
    with pytest.raises(ValueError,match='unknown environment'):
        apply_decisions(proposal,{'scene_0001':dict(reuse='invented',change_sources=[])},[0],catalog)


def test_future_change_source_is_rejected():
    proposal=dict(scene_groups=[dict(key='space',source_facts=[],change_sources=[])],
                  scenes=[dict(unit_ids=['speech_0001'],scene_group_id='missing',change_sources=[])])
    catalog={f'speech_{i:04d}':dict(unit_id=f'speech_{i:04d}',text_start=i,text_end=i+1,quote='x') for i in (1,2)}
    with pytest.raises(ValueError,match='future source'):
        apply_decisions(proposal,{'scene_0001':dict(reuse='space',change_sources=['speech_0002'])},[0],catalog)
