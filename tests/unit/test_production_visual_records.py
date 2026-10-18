from copy import deepcopy

import pytest

from video_ai.runtime.manifest import now
from video_ai.runtime.production_state import validate_report,validate_checkpoint,ArtifactStamp


def image_row(run):
    from video_ai.planning.start_images import image_parameters
    shot=dict(shot_id='shot_0001',image_prompt='Lake',entity_ids=[])
    g=dict(style='natural',lighting='morning',color_palette='blue',entities=[])
    return dict(shot_id='shot_0001',primary_unit_id='speech_0001',parameters=image_parameters(shot,g,768,432),
                image=ArtifactStamp(str(run/'start.png'),100,123).to_dict(),
                submission=dict(attempt_id='00000000-0000-0000-0000-000000000001',client_id='client',
                                prompt_id='00000000-0000-0000-0000-000000000002',intent_path=str(run/'workflow.json'),response_paths=[str(run/'response.json')]))


def report(run,stage,payload):
    return dict(schema_version=1,execution_mode='automatic',run_id=run.name,stage=stage,created_at=now(),status='completed',input_records={},payload=payload)


@pytest.mark.parametrize('change',['extra','params_extra','width_bool','seed_bool','stamp_bool','submission_extra','prompt_missing','order'])
def test_strict_image_payload_rejects_nested_drift(runtime_run,change):
    run,_,_=runtime_run;row=image_row(run)
    validate_report(report(run,'start_images',dict(images=[row])),run,'start_images')
    if change=='extra':row['extra']=1
    elif change=='params_extra':row['parameters']['extra']=1
    elif change=='width_bool':row['parameters']['width']=True
    elif change=='seed_bool':row['parameters']['seed']=True
    elif change=='stamp_bool':row['image']['mtime_ns']=True
    elif change=='submission_extra':row['submission']['extra']=1
    elif change=='prompt_missing':row['submission']['prompt_id']=None
    else:row['shot_id']='shot_0002'
    with pytest.raises(ValueError):validate_report(report(run,'start_images',dict(images=[row])),run,'start_images')


def test_comfy_callback_failure_is_before_post_and_preserves_manifest_intent(run_store,runtime_run):
    from integration.test_comfy_tracking import setup_client,post_count
    from http_helpers import Response
    client,transport,graph=setup_client(run_store,runtime_run,lambda r,t:Response({}))
    def reject(path,saved):
        assert path.is_file() and saved['state']=='intent'
        assert run_store.snapshot()['units']['image']['shot_0001']['submission']==saved
        saved['client_id']='callback mutation'
        raise KeyboardInterrupt('stop before POST')
    with pytest.raises(KeyboardInterrupt):client.submit_once(graph,stage='start_images',kind='image',unit_id='shot_0001',on_intent=reject)
    assert post_count(transport)==0
    assert run_store.snapshot()['units']['image']['shot_0001']['submission']['state']=='intent'
    assert run_store.snapshot()['units']['image']['shot_0001']['submission']['client_id']!='callback mutation'
