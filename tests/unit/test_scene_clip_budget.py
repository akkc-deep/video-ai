from copy import deepcopy
import math
from types import MappingProxyType

import pytest

from video_ai.planning import production_visual_plan


def scene_plan(frames):
    return {'scenes': [{'scene_id': 'scene_0001', 'start_frame': 0, 'end_frame': frames}],
            'total_frames': frames}


def test_two_hundred_frame_scene_exact_clip_budget_and_no_mutation():
    source = scene_plan(200)
    before = deepcopy(source)
    actual = production_visual_plan.plan_scene_clips(source, max_clip_seconds=6)
    expected = []
    for index, (start, end, retained, generated, head, tail) in enumerate(
            [(0, 93, 93, 93, 0, 0), (93, 185, 92, 93, 1, 0), (185, 200, 15, 17, 1, 1)], 1):
        expected.append(dict(clip_id=f'scene_0001_clip_{index:04d}', scene_id='scene_0001',
                             ordinal=index, parent_clip_id=None if index == 1 else f'scene_0001_clip_{index-1:04d}',
                             input_kind='selected_scene_image' if index == 1 else 'parent_retained_last_frame',
                             start_frame=start, end_frame=end, retained_frames=retained,
                             generated_frames=generated, discard_head_frames=head, trim_tail_frames=tail,
                             retained_source_start=head, retained_source_end=head+retained))
    assert actual == expected
    assert source == before


@pytest.mark.parametrize('frames,retained,generated', [
    (1, [1], [1]), (93, [93], [93]), (94, [93, 1], [93, 5]), (185, [93, 92], [93, 93])])
def test_default_duration_clip_boundaries(frames, retained, generated):
    clips = production_visual_plan.plan_scene_clips(scene_plan(frames), max_clip_seconds=6)
    assert [c['retained_frames'] for c in clips] == retained
    assert [c['generated_frames'] for c in clips] == generated


@pytest.mark.parametrize('seconds', [.3125, .562499999999, .5625, 5.99999999999, 6, 6.0625])
def test_short_and_float_duration_caps_preserve_all_frames(seconds):
    plan = scene_plan(200)
    clips = production_visual_plan.plan_scene_clips(plan, max_clip_seconds=seconds)
    assert sum(c['retained_frames'] for c in clips) == 200
    assert clips[0]['start_frame'] == 0 and clips[-1]['end_frame'] == 200
    assert all(a['end_frame'] == b['start_frame'] for a, b in zip(clips, clips[1:]))
    assert all(c['generated_frames'] <= math.floor(seconds*16) and c['generated_frames'] % 4 == 1 for c in clips)
    assert all(c['generated_frames'] == c['discard_head_frames'] + c['retained_frames'] + c['trim_tail_frames'] for c in clips)


def test_multiple_scenes_reset_parent_and_accept_frozen_plan():
    plan = MappingProxyType({'scenes': (
        MappingProxyType({'scene_id': 'scene_0001', 'start_frame': 0, 'end_frame': 94}),
        MappingProxyType({'scene_id': 'scene_0002', 'start_frame': 94, 'end_frame': 95}))})
    clips = production_visual_plan.plan_scene_clips(plan, max_clip_seconds=6)
    assert clips[-1]['parent_clip_id'] is None
    assert clips[-1]['ordinal'] == 1
    assert clips[-1]['start_frame'] == 94
    assert clips[-1]['clip_id'] == 'scene_0002_clip_0001'
    assert len(plan['scenes']) == 2


@pytest.mark.parametrize('seconds', [True, 0, -1, .312499999999, float('nan'), float('inf'), '6'])
def test_invalid_clip_cap_rejected(seconds):
    with pytest.raises(ValueError, match='max_clip_seconds'):
        production_visual_plan.plan_scene_clips(scene_plan(1), max_clip_seconds=seconds)


@pytest.mark.parametrize('change', [
    {'start_frame': True}, {'end_frame': 0}, {'end_frame': 1.0}, {'scene_id': ''}, {'start_frame': 1}])
def test_invalid_scene_ranges_rejected(change):
    plan = scene_plan(1)
    plan['scenes'][0].update(change)
    with pytest.raises(ValueError):
        production_visual_plan.plan_scene_clips(plan, max_clip_seconds=6)
