"""Native schema4 contributes the full timeline and cannot relabel an old index."""
from copy import deepcopy
from types import SimpleNamespace
import pytest


def index(count=334):
    from video_ai.planning.scene_temporal import derive_temporal_clips,temporal_frame_mapping
    clips=derive_temporal_clips(dict(total_frames=count,scenes=[dict(scene_id='scene_0001',start_frame=0,end_frame=count)]),dict(total_frames=count))
    def artifact(name):return dict(path='D:/VideoSi/source/'+name,bytes=123,sha256='a'*64)
    accepted=artifact('chain/accepted.json')
    return dict(schema_version=4,production_strategy='paragraph_jimeng_v1',run_id='20261103-000000-abcdef123456',
        protocol='longcat_native16_v1',inputs_sha256='a'*64,scene_plan_sha256='b'*64,visual_bible_sha256='c'*64,
        wan_inputs_sha256='d'*64,timeline_sha256='e'*64,execution_budget=artifact('execution.json'),total_frames=count,scenes=[],
        temporal_chains=[dict(scene_id='scene_0001',result=artifact('chain/result.json'),acceptance=accepted,frame_range=[0,count])],
        clips=[dict(clip_id=b['clip_id'],scene_id=b['scene_id'],budget=b,narration_bindings=[],generated=artifact(b['clip_id']+'/raw.mp4'),
            source=artifact(b['clip_id']+'/source.mp4'),frame_mapping=temporal_frame_mapping(b,actual_generated_frames=93),
            last_frame=artifact(b['clip_id']+'/last-frame.png'),clip_sha256='f'*64,observation_acceptance_sha256=accepted['sha256'],
            temporal_chain=dict(acceptance=accepted,source_frame_range=[b['start_frame'],b['end_frame']])) for b in clips])


def test_native_mapping_preserves_full_pcm_subtitle_frame_contributions():
    from video_ai.planning.scene_media import plan_scene_upscale,plan_scene_contributions
    value=index();rows=plan_scene_upscale(value)
    assert len(rows)==334 and [r['output_frame_index'] for r in rows]==list(range(334))
    assert rows[93]['generated_frame_index']==13 and rows[333]['generated_frame_index']==13
    upscaled=dict(total_frames=334,frames=[dict(frame_id=r['frame_id'],mapping={k:v for k,v in r.items() if k!='source'},
        output=dict(path=f'D:/VideoSi/upscale/{i}.png',bytes=123,sha256='b'*64)) for i,r in enumerate(rows)])
    timeline=SimpleNamespace(total_frames=334,total_samples=1000200,subtitle_end_sample=1000200)
    contributions=plan_scene_contributions(value,upscaled,timeline)
    assert len(contributions)==334 and contributions[-1]['output_frame_index']==333
    assert timeline.total_samples==timeline.subtitle_end_sample==1000200


@pytest.mark.parametrize('fault',['old_schema','protocol','chain_review','range','scope','unknown'])
def test_temporal_index_is_strict_and_cannot_downgrade_to_schema3(fault):
    from video_ai.planning.scene_media import plan_scene_upscale
    value=index()
    if fault=='old_schema':
        value['schema_version']=3;value.pop('protocol');value.pop('temporal_chains')
        for clip in value['clips']:clip.pop('temporal_chain')
    elif fault=='protocol':value['protocol']='foreign'
    elif fault=='chain_review':value['clips'][0]['temporal_chain']['acceptance']['sha256']='0'*64
    elif fault=='range':value['clips'][-1]['temporal_chain']['source_frame_range']=[0,1]
    elif fault=='scope':value['temporal_chains'][0]['frame_range']=[0,320]
    else:value['temporal_chains'][0]['future_human_acceptance']=True
    with pytest.raises(ValueError):plan_scene_upscale(value)
