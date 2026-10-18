from dataclasses import replace

import pytest


@pytest.mark.parametrize('role,node,key,value',[
    ('sdxl','12','steps',1),('sdxl','12','cfg',20),('sdxl','13','batch_size',2),
    ('wan','129:128','value',1),('wan','129:131','value',True),('wan','129:89','text','different'),
    ('wan','129:86','sampler_name','heun'),('wan','129:104','shift',2),
    ('upscale','2','model_name','other.pth'),('upscale','3','image',['1',1]),
    ('upscale','4','width',1280),('upscale','4','upscale_method','nearest-exact'),
])
def test_fixed_sampling_is_checked_independently_of_mapping_hash(runtime_run,role,node,key,value):
    from video_ai.runtime.production_visual_templates import validate_fixed_visual_template
    from video_ai.runtime.workflows import WorkflowTemplate
    run,config,paths=runtime_run
    template=WorkflowTemplate.load(config.workflows[role],config.workflows.get(role+'_mapping',config.workflows[role].with_suffix('.mapping.json')),config.models)
    validate_fixed_visual_template(template,role)
    template.graph[node]['inputs'][key]=value
    with pytest.raises(ValueError):validate_fixed_visual_template(template,role)


def test_frozen_model_path_must_be_the_file_loaded_by_comfy_root(runtime_run):
    from video_ai.runtime.production_visual_templates import validate_production_model_paths
    run,config,paths=runtime_run
    validate_production_model_paths(config)
    changed=replace(config,models=dict(config.models,sdxl=config.runtime_root/'models/alternate'/config.models['sdxl'].name))
    with pytest.raises(ValueError):validate_production_model_paths(changed)
