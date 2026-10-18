from dataclasses import replace

import pytest

from test_production_timing import timeline, estimate
from video_ai.planning.production_timing import build_automatic_slots
from video_ai.runtime.production_state import ArtifactStamp


def fixed_slots():
    t = timeline([600000], '湖。')
    p = build_automatic_slots(t, {'speech_0001': estimate(600000)})
    slots = tuple(replace(s, start_frame=a, end_frame=b) for s, (a,b) in
                  zip(p.slots, [(0,53),(53,107),(107,200)]))
    return t, slots


def test_native_budget_and_mapping_cover_200_frames_without_sha():
    from video_ai.planning.production_visual_plan import build_production_budgets, ProductionSourceClipPlan, production_frame_mapping
    t, slots = fixed_slots()
    budgets = build_production_budgets(t, slots)
    assert budgets.total_frames == 200 and budgets.transitions == ()
    assert [b.required_native_frames for b in budgets.shots] == [53,54,93]
    assert [b.wan_frames for b in budgets.shots] == [53,57,93]
    assert [b.native_trim_frames for b in budgets.shots] == [0,3,0]
    assert all(b.incoming_overlap_frames == b.outgoing_overlap_frames == 0 for b in budgets.shots)
    stamp = ArtifactStamp('D:/image.png', 100, 123)
    mappings=[]
    for b in budgets.shots:
        plan=ProductionSourceClipPlan(b.shot_id,'speech_0001',vars(b),{'length':b.wan_frames},stamp)
        mappings.append(production_frame_mapping(plan,generated_frames=b.wan_frames))
        with pytest.raises(TypeError): plan.parameters['length']=1
    assert mappings[1]['generated_to_source'] == list(range(54))+[None,None,None]
    assert sum(len(m['output_to_source']) for m in mappings) == 200
    assert all('sha256' not in str(m) for m in mappings)
    for n in (True, -1, 53):
        with pytest.raises(ValueError): production_frame_mapping(plan,generated_frames=n)


@pytest.mark.parametrize('bad',['gap','overlap','bool','order','rate'])
def test_invalid_fixed_budget_input_rejected(bad):
    from video_ai.planning.production_visual_plan import build_production_budgets
    t,slots=fixed_slots()
    if bad=='rate': t=replace(t,output_fps=24)
    elif bad=='bool': slots=(replace(slots[0],start_frame=False),*slots[1:])
    elif bad=='order': slots=(replace(slots[0],shot_id='shot_9999'),*slots[1:])
    else: slots=(slots[0],replace(slots[1],start_frame=54 if bad=='gap' else 52),slots[2])
    with pytest.raises(ValueError): build_production_budgets(t,slots)


def test_associated_unit_ids_keep_binding_order():
    from video_ai.planning.production_visual_plan import build_production_budgets
    t=timeline([4500,7500])
    p=build_automatic_slots(t,{'speech_0001':estimate(4500),'speech_0002':estimate(7500)})
    b=build_production_budgets(t,p.slots)
    assert b.shots[0].associated_unit_ids==('speech_0001','speech_0002')
    assert b.shots[1].associated_unit_ids==('speech_0002',)
