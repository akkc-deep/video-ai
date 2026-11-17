from pathlib import Path
from types import SimpleNamespace
import subprocess
import pytest


def test_stop_timeout_terminates_verified_child_before_supervisor(tmp_path,monkeypatch):
    import video_ai.experiments.upscale_manifest as lifecycle
    api=lifecycle.baseline_api();root=tmp_path/'phase';root.mkdir();calls=[]
    owner=dict(pid=123,process_started_at='original',profile_sha256='a'*64)
    api.write_once(root/'service-owner.json',owner)
    api.write_once(root/'frozen/service-binding.json',owner)
    monkeypatch.setattr(lifecycle,'_process_identity',lambda pid:'original')
    waits=iter([False,True]);monkeypatch.setattr(lifecycle,'_wait_owner_exit',lambda *a,**k:next(waits))
    monkeypatch.setattr(lifecycle,'_terminate_owner',lambda value:calls.append(('child',value['pid'])))
    class Supervisor:
        def wait(self,timeout):calls.append(('wait_supervisor',timeout));return 0
        def poll(self):return None
        def terminate(self):calls.append(('terminate_supervisor',))
    lifecycle.stop_owner(root,'a'*64,Supervisor())
    assert calls[0]==('child',123)
    assert not any(c[0]=='terminate_supervisor' for c in calls)


@pytest.mark.parametrize('pixel,status',[('a','awaiting_human_review'),('b','rejected_pixel_contract')])
def test_existing_phase_recovery_stops_owner_and_writes_results(tmp_path,monkeypatch,pixel,status):
    import video_ai.experiments.upscale_manifest as lifecycle
    from integration.test_upscale_pipeline_recovery import fixture
    from video_ai.experiments.upscale_experiment import freeze_manifest
    runtime=tmp_path/'runtime';container=runtime/'scratch/benchmarks/phase';container.mkdir(parents=True)
    root,m,old=fixture(container,n=1)
    (root/'frozen/manifest.json').unlink();m.update(root=str(root),source_binding=[{'expected_rgb_sha256':['a'*64]}])
    profile=freeze_manifest(root,m)
    plan=dict(task_id='LVA-05',max_upscale_requests=1,phases=[dict(phase='low-serial',root=str(root),
        manifest=m,profile_sha256=profile,requires_single_factor_acceptance=False)])
    path=tmp_path/'plan.json';lifecycle.baseline_api().write_once(path,plan)
    calls=[]
    monkeypatch.setattr(lifecycle,'RUNTIME_ROOT',runtime)
    monkeypatch.setattr(lifecycle,'run_frames',lambda *a,**k:dict(frame_rgb_sha256=[pixel*64]))
    monkeypatch.setattr(lifecycle,'stop_owner',lambda *a,**k:calls.append('stopped'))
    def no_launch(*a,**k):raise AssertionError('recovery must not launch a replacement')
    monkeypatch.setattr(lifecycle.subprocess,'Popen',no_launch)
    result=lifecycle.run_phase(path,'low-serial')
    assert calls==['stopped'] and (root/'phase-results.json').is_file()
    assert result['accepted_baseline_pixels_equal']==(pixel=='a')
    assert result['status']==status


def test_effective_tools_are_taken_from_pinned_artifacts(tmp_path):
    from video_ai.experiments.upscale_manifest import pinned_tools
    root=tmp_path/'ComfyUI';root.mkdir();python=tmp_path/'python.exe';python.write_bytes(b'python')
    main=root/'main.py';main.write_bytes(b'entry')
    from video_ai.experiments.wan_fast_profiles import artifact
    manifest=dict(artifacts={'comfy_python':artifact(python).identity_dict(),'comfy_main.py':artifact(main).identity_dict()})
    tools=pinned_tools(manifest)
    assert tools['comfy_python']==python and tools['comfy_root']==root


def test_owner_file_before_listener_is_not_startup_failure(tmp_path,monkeypatch):
    import video_ai.experiments.upscale_manifest as lifecycle
    import video_ai.experiments.upscale_experiment as experiment
    root=tmp_path/'phase';root.mkdir();(root/'service-owner.json').write_text('{}')
    calls=[]
    class Client:
        def __init__(self,*a,**kw):self.delegate=self
        def verify(self):calls.append('verify')
        def assert_owned_service(self):calls.append('assert_listener')
    monkeypatch.setattr(experiment,'PipelineExperimentClient',Client)
    readiness=iter([False,True]);monkeypatch.setattr(lifecycle,'_port_open',lambda port:next(readiness))
    assert lifecycle.owned_service_ready(root,'a'*64,8189) is False
    assert lifecycle.owned_service_ready(root,'a'*64,8189) is True
    assert calls==['verify','verify','assert_listener']
