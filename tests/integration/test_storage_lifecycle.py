"""Exercise the managed CLI lifecycle with a synthetic production engine."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from unit.test_production_inputs import production_config

from video_ai.runtime.storage import VideoStorage, test_runtime_scope as runtime_scope


@pytest.fixture
def managed(tmp_path):
    from video_ai import managed_production
    storage = VideoStorage(tmp_path/'runtime')
    with runtime_scope(storage.runtime_root):
        yield storage, managed_production


class Result(SimpleNamespace):
    exit_code = 3
    def to_dict(self):
        return {k:str(v) if isinstance(v,Path) else v for k,v in vars(self).items()}


def fake_engine(config=None, *, script=None, text=None, run_dir=None, publish=False, **kwargs):
    from video_ai.config import load_config
    from video_ai.runtime.paths import create_run, RuntimePaths
    from video_ai.runtime.manifest import validate_run_dir
    from video_ai.runtime.production_inputs import output_paths
    from video_ai.runtime.storage_files import write_record
    if run_dir is None:
        config = load_config(Path('config/production.example.json'))
        run = create_run(RuntimePaths.from_config(config))
        targets = output_paths(config,run)
        (run/'production').mkdir()
        (run/'production/script.txt').write_bytes(Path(script).read_bytes())
        write_record(run/'production/options.json',dict(output_paths=targets))
    else:
        run = validate_run_dir(run_dir)
    if publish:
        from video_ai.runtime.storage_files import read_record
        targets = read_record(run/'production/options.json')['output_paths']
        for role,path in targets.items():
            path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(b'synthetic '+role.encode())
        return Result(status='delivered',run_dir=run,run_id=run.name,
            movie=Path(targets['movie']),subtitle=Path(targets['subtitle']),receipt_path=Path(targets['receipt']),error=None)
    return Result(status='awaiting_image_selection',run_dir=run,run_id=run.name,error=None)


def test_new_resume_publish_close_clean_end_to_end(managed,monkeypatch):
    storage,module = managed
    monkeypatch.setattr('video_ai.production.make_video',fake_engine)
    first = module.make_managed_video(text='原文：旅行者一号。',title='旅行者一号',storage=storage)
    assert first.video_number == '0001'
    assert first.run_dir.name == '01'
    assert first.run_dir.is_relative_to(storage.production_root/'0001-旅行者一号')
    assert first.to_dict()['video_number'] == '0001'
    resumed = module.make_managed_video(video='0001',storage=storage)
    assert resumed.run_dir == first.run_dir
    published = module.make_managed_video(video='0001',publish=True,storage=storage)
    assert published.status == 'delivered'
    package = storage.output_dir(storage.find('0001'))/'v001'
    assert (package/'script.txt').read_text(encoding='utf-8') == '原文：旅行者一号。'
    assert (package/'delivery.json').exists()
    assert storage.close('0001')['status'] == 'closed'
    assert storage.clean('0001')['status'] == 'cleaned'
    assert (package/'video.mp4').exists()
    with pytest.raises(ValueError,match='closed|cleaned'):
        module.make_managed_video(video='0001',storage=storage)


def test_unknown_video_never_creates_new_task(managed,monkeypatch):
    storage,module = managed
    def forbidden(*a,**k): raise AssertionError('must not call model engine')
    monkeypatch.setattr('video_ai.production.make_video',forbidden)
    with pytest.raises(ValueError):
        module.make_managed_video(video='9999',storage=storage)
    assert storage.videos() == []


def test_blocked_run_stays_resumable_without_allocating_another_revision(managed,monkeypatch):
    storage,module = managed
    monkeypatch.setattr('video_ai.production.make_video',fake_engine)
    first = module.make_managed_video(text='完整文案',title='续作',storage=storage)
    for _ in range(3):
        assert module.make_managed_video(video='1',storage=storage).run_dir == first.run_dir
    assert len(list(first.run_dir.parent.iterdir())) == 1
    assert storage.find('1')['state'] == 'active'


def test_allocation_scope_preserves_old_unmanaged_paths(managed):
    storage,_ = managed
    from video_ai.config import load_config
    from video_ai.runtime.paths import create_run,RuntimePaths
    from video_ai.runtime.manifest import validate_run_dir
    run = create_run(RuntimePaths.from_config(load_config(Path('config/production.example.json'))))
    assert run.parent == storage.project_root/'runs'
    assert validate_run_dir(run) == run


def test_storage_cli_uses_number_and_dry_run(managed,monkeypatch,capsys):
    storage,_ = managed
    from video_ai import cli
    monkeypatch.setattr('video_ai.runtime.storage.VideoStorage',lambda: storage)
    storage.create('目录查询')
    assert cli.main(['storage','report','--video','0001','--json']) == 0
    assert '0001' in capsys.readouterr().out
    assert cli.main(['storage','clean','--video','0001','--dry-run','--json']) == 2
    assert storage.video_dir('0001').exists()


def test_cli_make_video_accepts_video_selector_instead_of_run_id(managed,monkeypatch,capsys):
    storage,module = managed
    from video_ai import cli
    monkeypatch.setattr('video_ai.production.make_video',fake_engine)
    first = module.make_managed_video(text='文案',title='只认编号',storage=storage)
    original = module.make_managed_video
    monkeypatch.setattr(module,'make_managed_video',lambda *a,**k: original(*a,storage=storage,**k))
    assert cli.main(['make-video','--video','0001']) == 3
    output = capsys.readouterr().out
    assert '--video 0001' in output
    assert '--run-dir' not in output
    assert first.run_dir.exists()


def test_real_revision_records_stay_in_one_video_bundle(managed,tmp_path,monkeypatch):
    storage,_ = managed
    from video_ai.config import load_config
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.runtime.production_scene_revision import create_scene_revision
    from scene_pipeline_helpers import prepared_pipeline
    from integration.test_scene_revision_flow import revision_request
    config = load_config(Path('config/production.example.json'))
    video = storage.create('实际修订协议')
    source = storage.allocate_revision(video)
    setup = prepared_pipeline((source,config,RuntimePaths.from_config(config)),tmp_path,monkeypatch)
    import video_ai.runtime.production_inputs as input_module
    real_loader=input_module.load_frozen_inputs
    def guarded_loader(*args,**kwargs):
        assert storage._activities.get(video['number'],0)>0, 'direct revision read escaped lifecycle lease'
        return real_loader(*args,**kwargs)
    monkeypatch.setattr(input_module,'load_frozen_inputs',guarded_loader)
    request,_ = revision_request(setup)
    result = create_scene_revision(source,request)
    assert result.status == 'revision_ready',result.error
    assert result.run_dir == source.parent/'02'
    assert storage.current_run(video) == result.run_dir
    assert create_scene_revision(source,request).run_dir == result.run_dir
    assert source.exists()
    # Failed preparation through the low-level API must not change the current revision.
    import json
    bad,value=revision_request(setup)
    value['choices'][0]['candidate_id']='request_99_image_99'
    bad.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    blocked=create_scene_revision(source,bad)
    assert blocked.status == 'blocked'
    assert storage.current_run(video) == result.run_dir


def test_managed_remote_namespace_is_unique_but_legacy_keys_stay_unchanged(managed):
    storage,_ = managed
    from video_ai.runtime.storage import remote_namespace
    one = storage.allocate_revision(storage.create('一'))
    two = storage.allocate_revision(storage.create('二'))
    assert one.name == two.name == '01'
    assert remote_namespace(one) != remote_namespace(two)
    legacy = storage.project_root/'runs/20261105-000000-123456789abc'
    assert remote_namespace(legacy) == legacy.name


def test_full_engine_with_synthetic_models_delivers_then_cleans_one_managed_video(
        managed,production_config,runtime_run,monkeypatch,capsys):
    """Use the real engine/codec path with local protocol doubles, never real inference."""
    storage,module=managed
    video=storage.create('旅行者一号')
    run=storage.allocate_revision(video)
    monkeypatch.setattr(storage,'create',lambda title:storage.find(video['number']))
    monkeypatch.setattr(module,'VideoStorage',lambda:storage)
    from integration.test_make_video_cli import test_cli_text_to_candidate_then_same_run_zero_model_or_media as exercise
    exercise(production_config,(run,runtime_run[1],runtime_run[2]),monkeypatch,capsys,'text',None)
    package=storage.output_dir(video)/'v001'
    assert (package/'delivery.json').is_file()
    # The reused legacy exercise deliberately ends by replacing its own lock
    # with this known synthetic corruption to verify foreign-owner refusal.
    lock=run/'.make-video.lock'
    assert lock.read_text(encoding='utf-8') == 'foreign replacement'
    lock.unlink()  # Restore only that test-created corruption before lifecycle cleanup.
    storage.close('0001')
    storage.clean('0001')
    assert not storage.video_dir(video).exists()
    assert (package/'video.mp4').is_file() and (package/'video.srt').is_file()
