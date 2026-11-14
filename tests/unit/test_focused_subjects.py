from copy import deepcopy

import pytest

from video_ai.planning.focused_subjects import restore_subjects


def test_whole_previous_subjects_preserve_appearance_and_cross_batch_active_state():
    entity=dict(label='probe',fixed_attributes=[],source_facts=[],creative_choices=[])
    appearance=dict(attributes=['extended antenna'],source_facts=[],creative_choices=[],change_sources=[])
    slices=[dict(scene_key=f'scene_{i:04d}') for i in (1,2)]
    raw=dict(scenes={'scene_0001':dict(subjects=[dict(new=entity,appearance=dict(new=appearance))]),
                     'scene_0002':dict(subjects=dict(reuse_previous=True))})
    restore_subjects(raw,None,slices)
    owner=raw['entities'][0]['key'];variant=raw['appearance_variants'][0]['key']
    assert raw['appearance_variants'][0]['entity_key']==owner
    assert raw['scenes']['scene_0001']==raw['scenes']['scene_0002']==dict(entity_ids=[owner],variant_ids=[variant])
    prior=dict(entities=raw['entities'],appearance_variants=raw['appearance_variants'],scenes=list(raw['scenes'].values()))
    next_batch=dict(scenes={'scene_0003':dict(subjects=[dict(reuse=owner,appearance=dict(unchanged=True))])})
    restore_subjects(next_batch,prior,[dict(scene_key='scene_0003')])
    assert next_batch['scenes']['scene_0003']['variant_ids']==[variant]
    assert next_batch['entities']==next_batch['appearance_variants']==[]


def test_appearance_cannot_be_attached_to_a_different_subject():
    prior=dict(entities=[dict(key='a'),dict(key='b')],appearance_variants=[dict(key='v',entity_key='a')],
               scenes=[dict(entity_ids=['a','b'],variant_ids=['v'])])
    raw=dict(scenes={'scene_0002':dict(subjects=[dict(reuse='b',appearance=dict(reuse='v'))])})
    with pytest.raises(ValueError,match='another subject'):
        restore_subjects(raw,prior,[dict(scene_key='scene_0002')])


def test_first_scene_must_declare_subject_instead_of_inventing_an_id():
    from unit.test_focused_scenes import inputs
    from video_ai.planning.focused_scenes import source_slices,focus_request
    from video_ai.planning.storyboard import _schema_check
    script,units,schema,settings=inputs()
    _,wire=focus_request(script,units,schema,source_slices(script,settings)[:1],None)
    assert set(wire['properties'])=={'global_style','scenes'}
    row=wire['properties']['scenes']['properties']['scene_0001']
    assert 'entity_ids' not in row['properties'] and 'variant_ids' not in row['properties']
    subjects=row['properties']['subjects']
    with pytest.raises(ValueError):
        _schema_check([dict(reuse='invented',appearance=dict(unchanged=True))],subjects)


def test_identical_repeated_subject_choice_is_idempotent_but_conflicts_are_rejected():
    prior=dict(entities=[dict(key='a')],appearance_variants=[],scenes=[dict(entity_ids=['a'],variant_ids=[])])
    choice=dict(reuse='a',appearance=dict(unchanged=True))
    raw=dict(scenes={'scene_0002':dict(subjects=[deepcopy(choice),deepcopy(choice)])})
    restore_subjects(raw,prior,[dict(scene_key='scene_0002')])
    assert raw['scenes']['scene_0002']==dict(entity_ids=['a'],variant_ids=[])
    raw=dict(scenes={'scene_0002':dict(subjects=[choice,dict(reuse='a',appearance=dict(reuse='different'))])})
    with pytest.raises(ValueError):restore_subjects(raw,prior,[dict(scene_key='scene_0002')])
