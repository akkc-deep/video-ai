from video_ai.cli import main


def test_migrate_requires_exactly_one_mode(capsys):
    assert main(['migrate','--inventory','D:/VideoSi/docs/video-ai/VAI-01-inventory'])==2
    assert main(['migrate','--inventory','D:/VideoSi/docs/video-ai/VAI-01-inventory','--execute','--dry-run'])==2


def test_migration_dry_run_saves_plan_without_copy(runtime_run,monkeypatch,capsys):
    from pathlib import Path
    import json
    import video_ai.runtime.migration as module
    from video_ai.runtime.migration import CopyEntry
    source=runtime_run[0]/'test-source.bin'
    source.write_bytes(b'dry-run only')
    target=Path('D:/VideoSi/tools/tests')/runtime_run[0].name/'dry.bin'
    monkeypatch.setattr(module,'build_copy_plan',lambda p:(CopyEntry(source,target,'tool-env',12,None),))
    assert main(['migrate','--inventory','D:/VideoSi/docs/video-ai/VAI-01-inventory','--dry-run'])==0
    assert not target.exists()
    report=json.loads(capsys.readouterr().out)
    assert report['capacity']['passed']
    assert Path(report['run_dir'],'manifest.json').exists()


def test_verify_component_command_selects_component(runtime_run,monkeypatch,capsys):
    import video_ai.runtime.component_checks as module
    called=[]
    def verify(config,*,run_dir,only):
        called.append((config,run_dir,only))
        return {'passed':False,'run_dir':str(run_dir),'reason':'injected resource failure'}
    monkeypatch.setattr(module,'verify_components',verify)
    assert main(['verify-components','--config',str(runtime_run[1].config_file),'--only','wan'])==1
    assert called[0][2]=='wan'


def test_migration_io_failure_records_terminal_manifest(monkeypatch,capsys):
    import json
    from pathlib import Path
    import video_ai.runtime.migration as module
    def failure(inventory):raise PermissionError('unreadable source subtree')
    monkeypatch.setattr(module,'build_copy_plan',failure)
    assert main(['migrate','--inventory','D:/VideoSi/docs/video-ai/VAI-01-inventory','--execute'])==1
    result=json.loads(capsys.readouterr().out)
    manifest=json.loads((Path(result['run_dir'])/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['stages']['preflight']['status']=='failed'
    assert 'unreadable' in manifest['stages']['preflight']['error']['message']
