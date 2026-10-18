from copy import deepcopy

import pytest

from video_ai.runtime.manifest import now
from video_ai.runtime.production_state import ArtifactStamp, validate_report, validate_checkpoint
from test_production_composition_records import stamp, command


def frame_payload(run):
    from video_ai.planning.upscale import PARAMETERS
    return dict(shot_id='shot_0001',frame_index=1,source_frame_index=0,source=stamp(run,'source.mp4'),
        parameters=deepcopy(PARAMETERS),input=stamp(run,'input/frame_000001.png'),input_copy=stamp(run,'copied.png'),
        output=stamp(run,'output/frame_000001.png'),model_output=stamp(run,'model.png'),
        submission=dict(attempt_id='00000000-0000-0000-0000-000000000001',client_id='client',
            prompt_id='00000000-0000-0000-0000-000000000002',intent_path=str(run/'intent.json'),
            response_paths=[str(run/'response.json')]),media_evidence_paths=[str(run/'validation.json')])


@pytest.mark.parametrize('change',['unknown','index_bool','source_index','parameters_bool','parameters_unknown','submission_unknown','foreign','empty_evidence'])
def test_upscale_frame_rejects_nested_drift(runtime_run,change):
    from video_ai.runtime.production_upscale_records import validate_upscale_checkpoint
    run,_,_=runtime_run;p=frame_payload(run)
    validate_upscale_checkpoint('shot_0001:frame_000001',p,run)
    if change=='unknown':p['unknown']=1
    elif change=='index_bool':p['frame_index']=True
    elif change=='source_index':p['source_frame_index']=1
    elif change=='parameters_bool':p['parameters']['batch']=True
    elif change=='parameters_unknown':p['parameters']['unknown']=1
    elif change=='submission_unknown':p['submission']['unknown']=1
    elif change=='foreign':p['output']['path']=str(run.parent/'foreign.png')
    else:p['media_evidence_paths']=[]
    with pytest.raises(ValueError):validate_upscale_checkpoint('shot_0001:frame_000001',p,run)


def test_frame_checkpoint_rejects_replaced_request_and_missing_outputs(runtime_run):
    run,_,_=runtime_run;p=frame_payload(run)
    request=dict(state='completed',intent_path=p['submission']['intent_path'],client_id='replacement',
        prompt_id=p['submission']['prompt_id'],response_paths=p['submission']['response_paths'])
    cp=dict(schema_version=1,execution_mode='automatic',run_id=run.name,stage='upscale',
        unit_id='shot_0001:frame_000001',created_at=now(),status='completed',request=request,
        outputs={k:p[k] for k in ('input','input_copy','output','model_output')},payload=p)
    with pytest.raises(ValueError):validate_checkpoint(cp,run,'upscale',cp['unit_id'])


def test_frame_checkpoint_and_report_bind_actual_completed_record(runtime_run):
    from video_ai.runtime.production_state import ProductionStateStore
    run,_,_=runtime_run;p=frame_payload(run)
    evidence=stamp(run,'validation.json');response=stamp(run,'response.json')
    req=dict(state='completed',**{key:p['submission'][key] for key in ('intent_path','client_id','prompt_id','response_paths')})
    outputs={key:p[key] for key in ('input','input_copy','output','model_output')}
    outputs.update(evidence=evidence,response=response)
    store=ProductionStateStore(run)
    uid='shot_0001:frame_000001'
    cp=store.write_checkpoint('upscale',uid,payload=p,outputs=outputs,request=req)
    assert cp.name=='shot_0001_frame_000001.json'
    row={key:p[key] for key in ('frame_index','source_frame_index','input','input_copy','output','submission')}
    row['checkpoint_path']=str(cp)
    mapping=dict(shot_id='shot_0001',coverage_start_frame=0,coverage_end_frame=1,core_start_frame=0,core_end_frame=1,
        native_fps=16,output_fps=16,source_frames=1,upscaled_frames=1,source_to_upscaled=[0],output_to_upscaled=[0])
    report=dict(schema_version=1,execution_mode='automatic',run_id=run.name,stage='upscale',created_at=now(),
        status='completed',input_records={},payload=dict(clips=[dict(shot_id='shot_0001',source=p['source'],upscaled_frames=1,frames=[row])],frame_mappings=[mapping]))
    validate_report(report,run,'upscale')
    row['output']=stamp(run,'replacement.png')
    with pytest.raises(ValueError):validate_report(report,run,'upscale')


@pytest.mark.parametrize('change',['frame_order','source_index_bool','count_bool','short_mapping','unknown_mapping','mapping_bool'])
def test_upscale_report_rejects_wrong_mapping_or_frames(runtime_run,change):
    run,_,_=runtime_run;p=frame_payload(run)
    row={k:p[k] for k in ('frame_index','source_frame_index','input','input_copy','output','submission')}
    row['checkpoint_path']=str(run/'logs/production/checkpoints/upscale/shot_0001_frame_000001.json')
    mapping=dict(shot_id='shot_0001',coverage_start_frame=0,coverage_end_frame=1,core_start_frame=0,core_end_frame=1,
        native_fps=16,output_fps=16,source_frames=1,upscaled_frames=1,source_to_upscaled=[0],output_to_upscaled=[0])
    payload=dict(clips=[dict(shot_id='shot_0001',source=p['source'],upscaled_frames=1,frames=[row])],frame_mappings=[mapping])
    if change=='frame_order':row['frame_index']=2
    elif change=='source_index_bool':row['source_frame_index']=False
    elif change=='count_bool':payload['clips'][0]['upscaled_frames']=True
    elif change=='short_mapping':mapping['output_to_upscaled']=[]
    elif change=='unknown_mapping':mapping['unknown']=1
    else:mapping['source_to_upscaled']=[False]
    report=dict(schema_version=1,execution_mode='automatic',run_id=run.name,stage='upscale',created_at=now(),
        status='completed',input_records={},payload=payload)
    with pytest.raises(ValueError):validate_report(report,run,'upscale')


def test_extract_rejects_unknown_command_and_wrong_input_index(runtime_run):
    from video_ai.runtime.production_upscale_records import validate_upscale_checkpoint
    run,_,_=runtime_run
    p=dict(shot_id='shot_0001',source=stamp(run,'source.mp4'),source_frames=1,width=768,height=432,
        frames=[dict(frame_index=1,source_frame_index=0,input=stamp(run,'input/frame_000001.png'))],command=command(run))
    validate_upscale_checkpoint('shot_0001_extract',p,run)
    for changed in ('index','command'):
        bad=deepcopy(p)
        if changed=='index':bad['frames'][0]['source_frame_index']=False
        else:bad['command']['unknown']=1
        with pytest.raises(ValueError):validate_upscale_checkpoint('shot_0001_extract',bad,run)
