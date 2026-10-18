from dataclasses import replace
import os
import pytest


def test_new_service_specs_bind_run_directories_and_ollama_host(runtime_run):
    from video_ai.runtime.service_specs import build_service_specs
    run,config,_=runtime_run
    config=replace(config,services={**config.services,'ollama':'http://127.0.0.1:11435'})
    specs=build_service_specs(config,run)
    comfy=specs['comfyui']
    assert '-B' in comfy.args
    assert '-B' in specs['tts'].args
    for name in ('input','output','temp','user'):
        assert str(run/'comfy'/name) in comfy.args
    database=comfy.args[comfy.args.index('--database-url')+1]
    assert database=='sqlite:///'+(run/'comfy/user/comfyui.db').as_posix()
    assert comfy.cwd==config.tools['comfy_root']
    assert specs['ollama'].env_overrides=={'OLLAMA_HOST':'127.0.0.1:11435'}
    assert str(config.project_root/'config/tts-api.yaml') in specs['tts'].args


@pytest.mark.parametrize('overrides',[
    {'TEMP':'C:/temp'}, {'OLLAMA_HOST':'0.0.0.0:11435'},
    {'OLLAMA_HOST':'127.0.0.1:11434'}, {'OLLAMA_HOST':'http://127.0.0.1:11435'},
])
def test_service_env_rejects_unapproved_overrides(runtime_run,overrides):
    from video_ai.runtime.services import ServiceSpec, service_environment
    run,_,paths=runtime_run
    spec=ServiceSpec('ollama','http://127.0.0.1:11435',('D:/VideoSi/tools/ollama/ollama.exe','serve'),run,30,overrides)
    with pytest.raises(ValueError): service_environment(paths,spec)


def test_service_environment_leaves_parent_untouched(runtime_run,monkeypatch):
    from video_ai.runtime.services import ServiceSpec, service_environment
    run,_,paths=runtime_run
    monkeypatch.setenv('OLLAMA_HOST','parent-value')
    spec=ServiceSpec('ollama','http://127.0.0.1:11435',('D:/VideoSi/tools/ollama/ollama.exe','serve'),run,30,{'OLLAMA_HOST':'127.0.0.1:11435'})
    result=service_environment(paths,spec)
    assert result['OLLAMA_HOST']=='127.0.0.1:11435'
    assert os.environ['OLLAMA_HOST']=='parent-value'


def test_specs_refuse_old_tool_location(runtime_run):
    from pathlib import Path
    from video_ai.runtime.service_specs import build_service_specs
    run,config,_=runtime_run
    config=replace(config,tools={**config.tools,'comfy_root':Path('D:/AI/tools/ComfyUI')})
    with pytest.raises(ValueError): build_service_specs(config,run)
