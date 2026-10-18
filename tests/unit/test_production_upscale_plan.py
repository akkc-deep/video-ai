from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from video_ai.runtime.production_state import ArtifactStamp


def source_payload(counts=(53,54,93)):
    from video_ai.planning.production_visual_plan import ProductionSourceClipPlan,production_frame_mapping
    from video_ai.planning.timeline import ShotBudget
    clips=[]; mappings=[]; cursor=0
    for i,n in enumerate(counts,1):
        sid=f'shot_{i:04d}';wan=((n-1+3)//4)*4+1
        budget=vars(ShotBudget(sid,cursor,cursor+n,cursor,cursor+n,0,0,('speech_0001',),n,n,wan,wan-n))
        stamp=ArtifactStamp(f'D:/source-{i}.mp4',100,123).to_dict()
        plan=ProductionSourceClipPlan(sid,'speech_0001',budget,{},ArtifactStamp.from_dict(stamp))
        clips.append(dict(shot_id=sid,primary_unit_id='speech_0001',budget=dict(budget,associated_unit_ids=['speech_0001']),
                          parameters=dict(width=768,height=432),start_image=stamp,generated=stamp,source=stamp,
                          native_fps=16,generated_frames=wan,source_frames=n,submission={}))
        mappings.append(production_frame_mapping(plan,generated_frames=wan));cursor+=n
    return dict(clips=clips,frame_mappings=mappings)


def test_production_plans_keep_53_54_93_and_freeze_without_sha():
    from video_ai.planning.production_visual_plan import plan_production_upscale,production_upscale_frame_mapping
    from video_ai.planning.upscale import PARAMETERS
    payload=source_payload();plans=plan_production_upscale(payload)
    assert [p.source_frames for p in plans]==[53,54,93]
    assert all(dict(p.parameters)==PARAMETERS for p in plans)
    for plan,mapping in zip(plans,payload['frame_mappings']):
        assert plan.source_stamp.to_dict()==payload['clips'][int(plan.shot_id[5:])-1]['source']
        assert 'sha256' not in plan.source_stamp.to_dict()
        with pytest.raises(TypeError):plan.budget['associated_unit_ids'][0]='changed'
        with pytest.raises(FrozenInstanceError):plan.source_frames=1
        mapped=production_upscale_frame_mapping(mapping,upscaled_frames=plan.source_frames)
        assert mapped['source_to_upscaled']==mapped['output_to_upscaled']==list(range(plan.source_frames))
        assert set(mapped)==set('shot_id coverage_start_frame coverage_end_frame core_start_frame core_end_frame native_fps output_fps source_frames upscaled_frames source_to_upscaled output_to_upscaled'.split())


@pytest.mark.parametrize('change',['order','count','gap','bool','mapping_bool','overlap','sha','unknown','profile'])
def test_production_plan_rejects_changed_source_contract(change):
    from video_ai.planning.production_visual_plan import plan_production_upscale
    p=source_payload()
    if change=='order':p['clips'].reverse()
    elif change=='count':p['clips'][0]['source_frames']-=1
    elif change=='gap':p['frame_mappings'][1]['coverage_start_frame']+=1
    elif change=='bool':p['clips'][0]['native_fps']=True
    elif change=='mapping_bool':p['frame_mappings'][0]['output_to_source'][0]=False
    elif change=='overlap':p['clips'][0]['budget']['incoming_overlap_frames']=1
    elif change=='sha':p['clips'][0]['source']['sha256']='a'*64
    elif change=='unknown':p['clips'][0]['extra']=1
    else:p['clips'][0]['parameters']['width']=320
    with pytest.raises(ValueError):plan_production_upscale(p)


@pytest.mark.parametrize('count',[True,0,-1,52,54])
def test_mapping_requires_exact_integer_count(count):
    from video_ai.planning.production_visual_plan import production_upscale_frame_mapping
    with pytest.raises(ValueError):production_upscale_frame_mapping(source_payload()['frame_mappings'][0],upscaled_frames=count)


def test_mapping_rejects_invalid_shot_identity():
    from video_ai.planning.production_visual_plan import production_upscale_frame_mapping
    mapping=source_payload()['frame_mappings'][0];mapping['shot_id']='foreign'
    with pytest.raises(ValueError):production_upscale_frame_mapping(mapping,upscaled_frames=53)


def test_windows_frame_checkpoint_path_uses_underscore_and_preserves_unit_id(runtime_run):
    from video_ai.runtime.production_support import checkpoint_path
    run,_,_=runtime_run;uid='shot_0001:frame_000001'
    path=checkpoint_path(SimpleNamespace(run_dir=run),'upscale',uid)
    assert path==run/'logs/production/checkpoints/upscale/shot_0001_frame_000001.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(uid,encoding='utf-8')
    assert path.read_text(encoding='utf-8')==uid
