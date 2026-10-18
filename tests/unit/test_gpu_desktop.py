import pytest


def test_only_approved_paths_and_cg_type_can_be_exempted():
    from video_ai.runtime.gpu_desktop import approved_desktop
    assert approved_desktop('C:/Windows/explorer.exe','C+G')
    assert approved_desktop('D:/Program Files/JetBrains/PyCharm 2025.3.3/bin/pycharm64.exe','C+G')
    assert not approved_desktop('D:/unknown/explorer.exe','C+G')
    assert not approved_desktop('C:/Windows/explorer.exe','C')
    assert not approved_desktop('D:/AI/runtime/python.exe','C+G')


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
