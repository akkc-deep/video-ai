import pytest


def test_only_approved_paths_and_cg_type_can_be_exempted():
    from video_ai.runtime.gpu_desktop import approved_desktop
    assert approved_desktop('C:/Windows/explorer.exe','C+G')
    assert approved_desktop('D:/Program Files/JetBrains/PyCharm 2025.3.3/bin/pycharm64.exe','C+G')
    assert not approved_desktop('D:/unknown/explorer.exe','C+G')
    assert not approved_desktop('C:/Windows/explorer.exe','C')
    assert not approved_desktop('D:/AI/runtime/python.exe','C+G')


@pytest.mark.parametrize('path',[
    'E:/Program Files/Tencent/QQLive/QQLive.exe',
    'E:/Program Files/Tencent/QQLive/11.189.7537.0/QQLiveService.exe',
    'E:/Program Files/Oray/AweSun/agent/AweSun.exe',
    'E:/Program Files/Oray/AweSun/flutter/AweSun.exe',
    'E:/Program Files/ShareX/ShareX.exe',
    'E:/Program Files/JetBrains/PyCharm 2026.3/plugins/jcef-plugin/jcef/cef_server.exe',
    'E:/Program Files (x86)/Tencent/QQMusic/QQMusic.exe',
    'C:/Users/qzw19/AppData/Roaming/Tencent/QQMusic/wmpf/2.2.3.465/runtime/WeChatAppEx.exe',
    'C:/Program Files/WindowsApps/AdvancedMicroDevicesInc-2.AMDRadeonSoftware_10.25.10376.0_x64__0a9344xs7nr4m/radeonsoftware/RadeonSoftware.exe',
    'C:/Program Files/WindowsApps/AdvancedMicroDevicesInc-2.AMDRadeonSoftware_10.25.10376.0_x64__0a9344xs7nr4m/radeonsoftware/AMDRSSrcExt.exe',
    'C:/Program Files/WindowsApps/9426MICRO-STARINTERNATION.MSICenter_2.0.75.0_x64__kzh8wxbdkxb8p/DCv2/DCv2.exe',
])
def test_observed_desktop_programs_are_not_external_inference(path):
    from video_ai.runtime.gpu_desktop import approved_desktop
    assert approved_desktop(path,'C+G')
    assert not approved_desktop(path,'C')


def test_protected_driver_host_is_only_allowed_as_desktop(runtime_run,monkeypatch):
    import video_ai.runtime.gpu_desktop as module
    def denied(pid):raise PermissionError('protected driver host')
    monkeypatch.setattr(module,'process_image',denied)
    monkeypatch.setattr(module,'process_names',lambda:{42:'wudfhost.exe',43:'wudfhost.exe'})
    monkeypatch.setattr(module,'process_types',lambda run:{42:'C+G',43:'C'})
    sample={'status':'verified','external_pids':[42,43],'gpu_total_mib':24455,'gpu_used_mib':3000}
    assert module.desktop_policy(runtime_run[0],sample)['external_pids']==[43]


def test_desktop_filter_preserves_unknown_external_processes(runtime_run,monkeypatch):
    import video_ai.runtime.gpu_desktop as module
    monkeypatch.setattr(module,'process_image',lambda pid:'C:/Windows/explorer.exe' if pid==42 else 'D:/AI/python.exe')
    monkeypatch.setattr(module,'process_types',lambda run:{42:'C+G',43:'C+G'})
    sample={'status':'verified','external_pids':[42,43],'gpu_total_mib':24455,'gpu_used_mib':3000}
    result=module.desktop_policy(runtime_run[0],sample)
    assert result['external_pids']==[43]
    assert result['approved_desktop_pids']==[42]
    assert result['gpu_free_mib']==21455


def test_failed_desktop_query_never_assumes_idle(runtime_run,monkeypatch):
    import video_ai.runtime.gpu_desktop as module
    def failure(run): raise OSError('permission denied')
    monkeypatch.setattr(module,'process_types',failure)
    sample={'status':'verified','external_pids':[42],'gpu_total_mib':24455,'gpu_used_mib':3000}
    result=module.desktop_policy(runtime_run[0],sample)
    assert result['status']=='unverified' and result['external_pids']==[42]


def test_protected_observed_desktop_uses_fresh_os_name(runtime_run,monkeypatch):
    import video_ai.runtime.gpu_desktop as module
    def denied(pid):raise PermissionError('protected process')
    monkeypatch.setattr(module,'process_image',denied)
    monkeypatch.setattr(module,'process_names',lambda:{42:'dwm.exe',43:'python.exe'})
    monkeypatch.setattr(module,'process_types',lambda run:{42:'C+G',43:'C+G'})
    sample={'status':'verified','external_pids':[42,43],'gpu_total_mib':24455,'gpu_used_mib':3000}
    result=module.desktop_policy(runtime_run[0],sample)
    assert result['approved_desktop_pids']==[42]
    assert result['external_pids']==[43]


def test_explicit_desktop_approval_is_scoped_and_preserves_compute_blocks(runtime_run,monkeypatch):
    import json
    import video_ai.runtime.gpu_desktop as module
    scope=getattr(module,'desktop_approval_scope',None)
    assert callable(scope),'explicit invocation-scoped desktop approval is missing'
    app='D:/Program Files/Oray/AweSun/flutter/AweSun.exe'
    monkeypatch.setattr(module,'process_image',lambda pid:app if pid in (42,43) else 'D:/AI/python.exe')
    monkeypatch.setattr(module,'process_types',lambda run:{42:'C+G',43:'C',44:'C+G'})
    sample={'status':'verified','external_pids':[42,43,44],'gpu_total_mib':24455,'gpu_used_mib':2000}
    run=runtime_run[0]
    assert module.desktop_policy(run,sample)['external_pids']==[42,43,44]
    with scope(run,[app],'User: keep this observed desktop application running'):
        result=module.desktop_policy(run,sample)
        assert result['external_pids']==[43,44]
        assert result['approved_desktop_pids']==[42]
        records=[json.loads(p.read_text(encoding='utf-8')) for p in (run/'logs/resources').glob('desktop-policy-*.json')]
        assert any(r.get('additional_approval',{}).get('authorization')=='User: keep this observed desktop application running' for r in records)
        assert module.desktop_policy(run.with_name('20261030-000000-000000000000'),sample)['external_pids']==[42,43,44]
    assert module.desktop_policy(run,sample)['external_pids']==[42,43,44]


def test_explicit_approval_cannot_replace_unknown_process_identity(runtime_run,monkeypatch):
    import video_ai.runtime.gpu_desktop as module
    scope=getattr(module,'desktop_approval_scope',None)
    assert callable(scope),'explicit invocation-scoped desktop approval is missing'
    def denied(pid):raise PermissionError('protected identity')
    monkeypatch.setattr(module,'process_image',denied)
    monkeypatch.setattr(module,'process_names',lambda:{42:'awesun.exe'})
    monkeypatch.setattr(module,'process_types',lambda run:{42:'C+G'})
    sample={'status':'verified','external_pids':[42],'gpu_total_mib':24455,'gpu_used_mib':2000}
    with scope(runtime_run[0],['D:/Program Files/Oray/AweSun/flutter/AweSun.exe'],'User: keep AweSun'):
        assert module.desktop_policy(runtime_run[0],sample)['external_pids']==[42]


@pytest.mark.parametrize('paths,authorization',[
    (['AweSun.exe'],'User approval'),
    (['D:/Apps/*/AweSun.exe'],'User approval'),
    (['D:/Apps/../AweSun.exe'],'User approval'),
    (['D:/Apps/AweSun.exe'],''),
])
def test_explicit_approval_requires_exact_paths_and_authorization(runtime_run,paths,authorization):
    import video_ai.runtime.gpu_desktop as module
    scope=getattr(module,'desktop_approval_scope',None)
    assert callable(scope),'explicit invocation-scoped desktop approval is missing'
    with pytest.raises(ValueError):
        with scope(runtime_run[0],paths,authorization):
            pytest.fail('invalid desktop approval entered')
