import importlib.util
from pathlib import Path
import pytest
from integration.test_upscale_pipeline_recovery import fixture


def test_observer_refuses_profile_and_asset_drift_before_start(tmp_path):
    path=Path(__file__).parents[2]/'scripts/observe_upscale_comfy.py'
    spec=importlib.util.spec_from_file_location('upscale_observer_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    from video_ai.experiments.upscale_experiment import baseline_api
    root,manifest,profile=fixture(tmp_path,n=1)
    baseline_api().write_once(root/'experiment.json',dict(port=8189,profile_sha256=profile))
    baseline_api().write_once(root/'frozen/service-launch.json',dict(port=8189,profile_sha256=profile))
    assert module.validate_launch(root,profile,8189)['factor']=='pipeline'
    with pytest.raises(ValueError):module.validate_launch(root,'f'*64,8189)
    Path(manifest['artifacts']['model']['path']).write_bytes(b'changed')
    with pytest.raises(ValueError):module.validate_launch(root,profile,8189)


def test_supervisor_job_closes_cpu_child_on_handle_close():
    import subprocess
    import sys
    path=Path(__file__).parents[2]/'scripts/observe_upscale_comfy.py'
    spec=importlib.util.spec_from_file_location('upscale_job_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        job=module.KillOnCloseJob(child)
        job.close()
        assert child.wait(timeout=5) is not None
    finally:
        if child.poll() is None:child.terminate();child.wait(timeout=5)


def test_frozen_configuration_string_loads_as_path():
    path=Path(__file__).parents[2]/'scripts/observe_upscale_comfy.py'
    spec=importlib.util.spec_from_file_location('upscale_config_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    config_path=Path(__file__).parents[2]/'config/production.example.json'
    config=module.launch_configuration({'artifacts':{'configuration':{'path':str(config_path.resolve())}}})
    assert config.config_file==config_path.resolve()
