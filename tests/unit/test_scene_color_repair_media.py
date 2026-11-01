"""Reject contradictory saved media before any probe or pixel work."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from scene_continuity_helpers import save,artifact


def media_fixture(run):
    from video_ai.runtime._scene_color_repair_media import RECIPE
    cid=str(uuid4());folder=run/'production/scene-color-repair/candidates'/cid
    folder.mkdir(parents=True)
    source=artifact(save(run/'source.mp4',{'fixture_only':'not a real media input; invalid metadata must reject first'}))
    master=artifact(save(folder/'master.mp4',{'fixture_only':'not decoded'}))
    mapping=artifact(save(run/'mapping.json',dict(retained_frames=2,retained_to_generated=[0,1],start_frame=0)))
    rows=[dict(candidate_frame=i,source_frame=i,generated_frame=i,output_frame=i,source_pts=i*1024,source_time_base='1/16384',
        candidate_pts=i*1024,candidate_time_base='1/16384',rgb_sha256='0'*64) for i in range(2)]
    fm=artifact(save(folder/'frame-map.json',dict(schema_version=1,candidate_id=cid,source=source,candidate=master,frames=rows)))
    media=dict(schema_version=1,candidate_id=cid,source=source,candidate=master,frames=2,width=64,height=36,fps='16/1',
        time_base='1/16384',pts=[0,1024],frame_map=fm,encoding=dict(algorithm='fixed_srgb_yuv444_crf0_v1',parameters=RECIPE,command_receipts=[]),
        last_frame=artifact(save(folder/'last-frame.png',{'fixture_only':'not decoded'})),evidence=[])
    intent=dict(candidate_id=cid,request=artifact(save(folder/'request.json',{'fixture_only':True})),binding=dict(source=source,mapping=mapping))
    return media,intent,folder


@pytest.mark.parametrize('fault',['width_bool','height_zero','frames_bool','shortened','raw_alias'])
def test_saved_media_cannot_change_dimensions_frame_count_or_candidate_role(runtime_run,fault):
    from video_ai.runtime._scene_color_repair_media import validate_media
    from video_ai.runtime._scene_continuity_io import Reader
    import json
    run,config,_=runtime_run;media,intent,folder=media_fixture(run)
    if fault=='width_bool':media['width']=True
    elif fault=='height_zero':media['height']=0
    elif fault=='frames_bool':media['frames']=True
    else:
        fm=json.loads(Path(media['frame_map']['path']).read_text(encoding='utf-8'))
        if fault=='shortened':media.update(frames=1,pts=[0]);fm['frames']=fm['frames'][:1]
        else:media['candidate']=media['source'];fm['candidate']=media['source']
        media['frame_map']=artifact(save(folder/'frame-map.json',fm))
    with pytest.raises(ValueError):validate_media(media,intent,config=config,reader=Reader())
