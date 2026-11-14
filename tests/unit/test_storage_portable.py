from pathlib import Path

from video_ai.runtime.storage import VideoStorage, managed_location, managed_output


def test_bundle_revision_and_delivery_layout(tmp_path):
    storage = VideoStorage(tmp_path/'runtime with spaces')
    video = storage.create('portable')
    run = storage.allocate_revision(video)
    assert storage.video_dir(video) == storage.runtime_root/'work/0001-portable'
    assert storage.output_dir(video) == storage.runtime_root/'output/0001-portable'
    assert storage.index_root == storage.runtime_root/'shared/config/storage/videos'
    assert managed_location(run) == (storage.runtime_root, storage.video_dir(video))
    assert managed_output(run) == storage.output_dir(video)/'v001/video.mp4'
    assert storage.current_run(video) == run
