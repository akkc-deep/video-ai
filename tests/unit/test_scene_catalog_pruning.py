"""Unreferenced visual declarations are explicit dead data, never source edits."""
from copy import deepcopy

import pytest

from unit.test_scene_environment_transport import environment_input,environment_wire
from video_ai.adapters.ollama_scenes import restore_scene_content
from video_ai.config import ScenePlanningSettings
from video_ai.planning.production_scenes import build_scene_plan


def test_unused_rows_are_pruned_without_changing_scenes_or_used_facts():
    from video_ai.planning.production_scenes import prune_unused_visual_entries
    prompt,_,script,units,timeline=environment_input()
    proposal=restore_scene_content(environment_wire(),prompt)
    proposal['entities']=[dict(key='earth',label='Earth',fixed_attributes=[],source_facts=[],creative_choices=[])]
    before=deepcopy(proposal)
    with pytest.raises(ValueError,match='unused proposal'):build_scene_plan(script,units,timeline,proposal,settings=ScenePlanningSettings(1,6))
    normalized,removed=prune_unused_visual_entries(proposal)
    assert proposal==before and normalized['scenes']==proposal['scenes']
    assert normalized['scene_groups']==proposal['scene_groups'] and normalized['entities']==[]
    assert removed==[dict(category='entities',key='earth')]
    assert len(build_scene_plan(script,units,timeline,normalized,settings=ScenePlanningSettings(1,6))[1]['scenes'])==3


def test_unknown_references_are_not_repaired_by_catalog_pruning():
    from video_ai.planning.production_scenes import prune_unused_visual_entries
    prompt,*_=environment_input();proposal=restore_scene_content(environment_wire(),prompt)
    proposal['scenes'][0]['entity_ids']=['undefined']
    normalized,removed=prune_unused_visual_entries(proposal)
    assert normalized==proposal and removed==[]
