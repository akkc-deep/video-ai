from collections import Counter
from copy import deepcopy

from video_ai.planning.production_visual_plan import plan_scene_clips
from video_ai.planning.scene_clip_continuation import scene_clip_frame_mapping
import pytest


def retained_scene_fixture(frames=200):
    plan = {'scenes': [{'scene_id': 'scene_0001', 'start_frame': 0, 'end_frame': frames}],
            'total_frames': frames}
    plan['clips'] = plan_scene_clips(plan, max_clip_seconds=6)
    return {'total_frames': frames, 'clips': [dict(
        clip_id=c['clip_id'], scene_id=c['scene_id'], budget=c,
        frame_mapping=scene_clip_frame_mapping(c, actual_generated_frames=c['generated_frames']),
        source={'path': f'D:/VideoSi/run/{c["clip_id"]}.mp4', 'bytes': 100, 'sha256': 'a'*64})
        for c in plan['clips']]}


def test_200_retained_frames_upscale_once_without_second_head_drop():
    from video_ai.planning.scene_media import plan_scene_upscale
    scene_clips = retained_scene_fixture()
    before = deepcopy(scene_clips)
    rows = plan_scene_upscale(scene_clips)
    assert len(rows) == 200
    assert list(Counter(row['clip_id'] for row in rows).values()) == [93, 92, 15]
    assert [r['generated_frame_index'] for r in rows[-15:]] == list(range(1, 16))
    assert [r['output_frame_index'] for r in rows] == list(range(200))
    assert rows[93]['retained_frame_index'] == 0
    assert rows[93]['generated_frame_index'] == 1
    assert len({r['frame_id'] for r in rows}) == 200
    assert scene_clips == before


@pytest.mark.parametrize('fault',['bool','extra','head','gap','duplicate','artifact_extra'])
def test_native_mapping_and_artifacts_are_exact(fault):
    from video_ai.planning.scene_media import plan_scene_upscale
    clips=retained_scene_fixture()
    if fault=='bool': clips['clips'][0]['budget']['retained_frames']=True
    elif fault=='extra': clips['clips'][0]['frame_mapping']['extra']=1
    elif fault=='head': clips['clips'][1]['frame_mapping']['retained_to_generated'][0]=0
    elif fault=='gap': clips['total_frames']=201
    elif fault=='duplicate': clips['clips'].append(clips['clips'][0])
    else: clips['clips'][0]['source']['extra']=1
    with pytest.raises(ValueError): plan_scene_upscale(clips)


@pytest.mark.parametrize('count',[1,93,94,200])
def test_contribution_sequence_rebuilds_every_exact_technical_frame(count):
    from types import SimpleNamespace
    from video_ai.planning.scene_media import plan_scene_upscale,plan_scene_contributions
    from video_ai.planning.production_scenes import canonical_digest
    clips=retained_scene_fixture(count); rows=plan_scene_upscale(clips)
    frames=[dict(frame_id=r['frame_id'],mapping={k:v for k,v in r.items() if k!='source'},
        output=dict(path=f'D:/VideoSi/run/frame_{i}.png',bytes=100,sha256='b'*64)) for i,r in enumerate(rows)]
    upscaled=dict(total_frames=count,frames=frames)
    result=plan_scene_contributions(clips,upscaled,SimpleNamespace(total_frames=count))
    assert [r['output_frame_index'] for r in result]==list(range(count))
    assert [r['image'] for r in result]==[f['output'] for f in frames]
    assert [r['upscale_frame_sha256'] for r in result]==[canonical_digest(f) for f in frames]
    frames[-1]['mapping']['output_frame_index']=True
    with pytest.raises(ValueError): plan_scene_contributions(clips,upscaled,SimpleNamespace(total_frames=count))
