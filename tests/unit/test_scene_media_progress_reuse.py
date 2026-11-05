"""Read-only progress does one complete retained-frame reconstruction."""
from types import SimpleNamespace

from video_ai.runtime import scene_media_records as media, _scene_upscale_records as upscales
from video_ai.runtime.production_state import write_exclusive
from video_ai.config import read_json


def test_completed_progress_reconstructs_each_frame_only_once(runtime_run, monkeypatch):
    run, _, _ = runtime_run
    root = run/'production/scene-upscale'
    frames = [{'frame_id': 'one'}, {'frame_id': 'two'}]
    store = SimpleNamespace(run_dir=run, root=root,
        read=lambda name: read_json(root/name) if (root/name).exists() else None,
        verify_tools=lambda: None)
    context = dict(frozen=SimpleNamespace(options={'run_id': run.name}), store=store,
        inputs={}, scene_clips={'clips': []}, rows=[{}, {}],
        timeline=SimpleNamespace(as_dict=lambda: {'frames': 2}))
    write_exclusive(root/'inputs.json', {})
    write_exclusive(root/'complete.json', upscales.complete_value(context, frames))
    calls = []

    def reconstruct(*a, **kw):
        calls.append(True)
        return frames

    monkeypatch.setattr(upscales, 'validate_upscale_frames', reconstruct)
    result = media._load_scene_media_progress(context)
    assert result['upscale']['status'] == 'ready'
    assert result['upscale']['completed_items'] == 2
    assert len(calls) == 1
