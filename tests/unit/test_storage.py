"""Storage lifecycle tests use only synthetic files in pytest's isolated runtime."""
import json
from pathlib import Path

import pytest

from video_ai.runtime.storage import VideoStorage, allocation_scope
from video_ai.runtime.paths import RuntimePaths, create_run


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


@pytest.fixture
def storage(tmp_path):
    return VideoStorage(tmp_path/'runtime')


def delivered(storage, video):
    """A synthetic published package, never an assertion about real media."""
    run = storage.allocate_revision(video)
    folder = storage.output_dir(video)/'v001'
    folder.mkdir(parents=True)
    for name in ('video.mp4', 'video.srt', 'script.txt'):
        (folder/name).write_bytes(b'synthetic fixture')
    put(folder/'delivery.json', dict(schema_version=1, video=video['number'],
        files={n:dict(bytes=(folder/n).stat().st_size) for n in ('video.mp4','video.srt','script.txt')}))
    storage.record_delivery(video, run, folder)
    return run, folder


def test_allocate_one_visible_number_and_short_revisions(storage):
    one = storage.create('旅行者一号')
    two = storage.create('第二个视频')
    assert one['number'] == '0001'
    assert storage.video_dir(one).name == '0001-旅行者一号'
    assert two['number'] == '0002'
    assert storage.find('1')['number'] == '0001'
    assert storage.find('旅行者一号')['number'] == '0001'
    assert storage.allocate_revision(one).name == '01'
    assert storage.allocate_revision(one).name == '02'
    assert storage.current_run(one).name == '02'


def test_reserving_a_revision_does_not_commit_current_progress(storage):
    video=storage.create('修订准备')
    first=storage.allocate_revision(video)
    reserved=storage.allocate_revision(video,revision_key='explicit-request')
    assert reserved.name == '02'
    assert storage.current_run(video) == first
    assert storage.allocate_revision(video,revision_key='explicit-request') == reserved


def test_legacy_generation_also_blocks_shared_cleanup(storage):
    from video_ai.runtime.storage import managed_lease, test_runtime_scope as sandbox
    legacy=storage.project_root/'runs/20261105-000000-123456789abc'
    legacy.mkdir(parents=True)
    cache=storage.disposable_root/'cache/pip/fixture.whl'
    cache.parent.mkdir(parents=True); cache.write_bytes(b'active fixture')
    with sandbox(storage.runtime_root),managed_lease(legacy):
        result=storage.clean()
    assert cache.exists()
    assert result['skipped']


def test_close_and_targeted_clean_keep_independent_delivery(storage):
    one = storage.create('旅行者一号')
    run, output = delivered(storage, one)
    (run/'large-process-file.bin').write_bytes(b'process data')
    two = storage.create('另一个')
    other = storage.allocate_revision(two)
    assert storage.close('0001', dry_run=True)['status'] == 'close_ready'
    assert run.exists()
    assert storage.close('0001')['status'] == 'closed'
    assert not run.exists()
    assert storage.find('0001')['state'] == 'closed'
    assert storage.clean('0001', dry_run=True)['status'] == 'clean_ready'
    assert storage.clean('0001')['status'] == 'cleaned'
    assert (output/'video.mp4').read_bytes() == b'synthetic fixture'
    assert (output/'delivery.json').is_file()
    assert other.exists()
    assert storage.find('0001')['state'] == 'cleaned'
    with pytest.raises(ValueError, match='closed|cleaned|结束|清理'):
        storage.current_run('0001')


def test_unpublished_and_unknown_effects_cannot_close(storage):
    video = storage.create('尚未发布')
    with pytest.raises(ValueError, match='deliver|publish|交付|发布'):
        storage.close('0001')
    run, _ = delivered(storage, video)
    put(run/'production/jimeng/scene_001/request_01/intent.json',
        dict(status='submitted', request_id='original-paid-request'))
    with pytest.raises(ValueError, match='unknown|unresolved|未决|请求'):
        storage.close('0001')
    assert run.exists()


def test_external_video_dependency_blocks_close(storage):
    one = storage.create('被引用')
    source, _ = delivered(storage, one)
    two = storage.create('依赖方')
    target = storage.allocate_revision(two)
    put(target/'production/scene-revision/commit.json', dict(source_run_dir=str(source)))
    with pytest.raises(ValueError, match='depend|引用|依赖'):
        storage.close('0001')
    assert source.exists()


def test_ascii_escaped_chinese_dependency_paths_also_block_close(storage):
    one=storage.create('中文源视频')
    source,_=delivered(storage,one)
    target=storage.allocate_revision(storage.create('另一个'))
    path=target/'production/inherited.json'; path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(source_run_dir=str(source))),encoding='utf-8')
    assert '\\u' in path.read_text(encoding='utf-8')
    with pytest.raises(ValueError,match='depend|引用|依赖'):
        storage.close('0001')


def test_clean_does_not_accept_arbitrary_paths_or_active_video(storage):
    video = storage.create('制作中')
    storage.allocate_revision(video)
    with pytest.raises(ValueError):
        storage.clean(str(storage.runtime_root))
    with pytest.raises(ValueError, match='close|closed|结束|制作'):
        storage.clean('0001')
    assert storage.video_dir(video).exists()


def test_unknown_title_does_not_allocate_or_reuse_number(storage):
    with pytest.raises(ValueError):
        storage.find('不存在')
    one = storage.create('重复标题')
    storage.create('重复标题')
    with pytest.raises(ValueError, match='ambiguous|多个|编号'):
        storage.find('重复标题')
    delivered(storage, one)
    storage.close('0001')
    storage.clean('0001')
    assert storage.create('新视频')['number'] == '0003'


def test_recover_close_after_move_before_index_commit(storage, monkeypatch):
    video = storage.create('中断')
    run, output = delivered(storage, video)
    original = storage._write_video
    def interrupted(value):
        if value['state'] == 'closed':
            raise OSError('synthetic interruption')
        return original(value)
    monkeypatch.setattr(storage, '_write_video', interrupted)
    with pytest.raises(OSError):
        storage.close('0001')
    monkeypatch.setattr(storage, '_write_video', original)
    assert storage.close('0001')['status'] == 'closed'
    assert not run.exists()
    assert (output/'video.mp4').exists()


def test_forged_index_cannot_point_cleanup_at_public_models(storage):
    video = storage.create('伪造')
    delivered(storage, video)
    index = storage.index_root/'0001.json'
    value = json.loads(index.read_text(encoding='utf-8'))
    value.update(state='closed', directory='../../../../models')
    put(index, value)
    with pytest.raises(ValueError):
        storage.clean('0001')


def test_report_reads_metadata_without_media_hash_or_decoding(storage):
    video = storage.create('占用')
    run = storage.allocate_revision(video)
    (run/'asset.bin').write_bytes(b'12345')
    report = storage.report('0001')
    assert report['videos'][0]['logical_bytes'] >= 5
    assert report['videos'][0]['number'] == '0001'


def test_managed_activity_blocks_close(storage):
    video = storage.create('运行中')
    run, _ = delivered(storage, video)
    with storage.activity(video):
        with pytest.raises(ValueError, match='active|occupied|运行|占用'):
            storage.close('0001')
    assert run.exists()


def test_unknown_tts_and_mail_requests_survive_close_attempt(storage):
    video = storage.create('未决外部请求')
    run,_ = delivered(storage,video)
    put(run/'production/production-state.json',dict(units=dict(speech=dict(speech_0001=dict(
        status='failed',request=dict(state='ambiguous',intent_path=str(run/'logs/tts.intent.json')))))))
    with pytest.raises(ValueError,match='unresolved|请求|未决'):
        storage.close('0001')
    (run/'production/production-state.json').unlink()
    put(run/'production/image-selection/image_batch_0001/mail/part_0001/attempt_0001/intent.json',
        dict(message_id='<synthetic-unknown@video-ai.local>'))
    with pytest.raises(ValueError,match='unresolved|请求|未决'):
        storage.close('0001')
    assert run.exists()


@pytest.mark.parametrize('accepted',[False,True])
def test_real_jimeng_intent_shape_is_not_mistaken_for_a_resolved_local_record(storage,accepted):
    video=storage.create('真实协议未决请求')
    run,_=delivered(storage,video)
    put(run/'production/jimeng/scene_0001/request_01/intent.json',
        dict(schema_version=2,identity='a'*64,created_at='2026-11-05T00:00:00Z',state='intent'))
    if accepted:
        put(run/'production/jimeng/scene_0001/request_01/accepted.json',dict(task_id='original-paid-task'))
    with pytest.raises(ValueError,match='unresolved|请求|未决'):
        storage.close('0001')
    assert run.exists()


def test_process_lock_excludes_other_threads(storage):
    from concurrent.futures import ThreadPoolExecutor
    def contender():
        with storage._lock():
            return 'entered'
    with storage._lock(),ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(ValueError,match='occupied'):
            pool.submit(contender).result(timeout=5)


def test_clean_all_clears_only_disposable_shared_data_and_closed_bundles(storage):
    video = storage.create('已完成')
    _,output = delivered(storage,video)
    storage.close('0001')
    cache = storage.disposable_root/'cache/pip/package.whl'
    cache.parent.mkdir(parents=True); cache.write_bytes(b'redownloadable')
    model = storage.runtime_root/'models/public-weight.bin'
    model.parent.mkdir(parents=True); model.write_bytes(b'keep')
    active = storage.allocate_revision(storage.create('活动任务'))
    storage.clean(dry_run=True)
    assert cache.exists()
    storage.clean()
    assert not cache.exists()
    assert model.exists() and active.exists() and (output/'video.mp4').exists()


def test_test_session_owner_protects_it_from_shared_cleanup(storage):
    import os
    from video_ai.runtime.production_state import process_started_at
    folder = storage.disposable_root/'tests/session-live'
    put(folder/'owner.json',dict(pid=os.getpid(),process_started_at=process_started_at(os.getpid())))
    asset = folder/'fixture.bin'; asset.write_bytes(b'active fixture')
    report = storage.clean()
    assert asset.exists()
    assert report['skipped']


def test_managed_composition_links_immutable_frames_without_second_disk_copy(storage):
    import hashlib
    import os
    from types import SimpleNamespace
    from video_ai.runtime._scene_composition_materialized import copy_frame_sequence
    video = storage.create('省空间')
    run = storage.allocate_revision(video)
    source = run/'master.png'; source.write_bytes(b'synthetic immutable frame bytes')
    folder = run/'materialized'; (folder/'frames').mkdir(parents=True)
    def artifact(path):
        path=Path(path)
        return dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    store = SimpleNamespace(run_dir=run,verify_global=lambda:None,assert_write=lambda:None,
        validate_artifact=lambda value:Path(value['path']),artifact=artifact)
    from video_ai.runtime.storage import test_runtime_scope as sandbox
    with sandbox(storage.runtime_root):
        rows=copy_frame_sequence(store,[dict(image=artifact(source))],folder)
    target=Path(rows[0]['path'])
    assert os.path.samefile(source,target)
    target.unlink()
    assert source.read_bytes() == b'synthetic immutable frame bytes'


def test_shared_clean_preserves_log_of_the_running_launcher(storage,monkeypatch):
    active=storage.disposable_root/'logs/active.log'
    active.parent.mkdir(parents=True); active.write_text('current launcher',encoding='utf-8')
    old=active.with_name('old.log'); old.write_text('old log',encoding='utf-8')
    monkeypatch.setenv('VIDEO_AI_ACTIVE_LOG',str(active))
    storage.clean()
    assert active.read_text(encoding='utf-8') == 'current launcher'
    assert not old.exists()


def test_cleanup_rejects_a_junction_without_touching_public_files(storage):
    from unit.test_paths import create_junction
    video=storage.create('链接边界')
    delivered(storage,video)
    storage.close('0001')
    public=storage.runtime_root/'models/public'
    public.mkdir(parents=True)
    sentinel=public/'weight.bin'; sentinel.write_bytes(b'keep public resource')
    junction=storage._completed(storage.find('0001'))/'redirected-models'
    create_junction(junction,public)
    try:
        with pytest.raises(ValueError,match='reparse|redirect'):
            storage.clean('0001')
        assert sentinel.read_bytes() == b'keep public resource'
    finally:
        junction.rmdir()  # Remove only the synthetic junction, never traverse its target.
