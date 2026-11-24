"""Public resumes reuse finished reference preparation without model calls."""
import pytest

from integration.test_scene_revision_flow import revision_source


def test_public_resume_skips_completed_reference_preparation(revision_source, monkeypatch):
    import video_ai.runtime.image_selection_records as images
    import video_ai.runtime.reference_image_records as reference
    import video_ai.runtime.production_scene_clips as clips
    from video_ai.production import make_video
    from video_ai.runtime.resume_materials import trusting_materials
    from video_ai.runtime.scene_clip_records import scene_context, collect_progress

    setup = revision_source
    calls = []
    def forbidden(*args, **kwargs):
        pytest.fail('resume revalidated a completed reference-image batch')
    monkeypatch.setattr(images, 'load_accepted_batches', forbidden)
    monkeypatch.setattr(images, 'require_complete_image_acceptance', forbidden)
    monkeypatch.setattr(reference, 'verify_reference_provenance', forbidden)
    def next_stage(frozen, units, timeline, *, paths, logger, lock, **kwargs):
        assert trusting_materials()
        context = scene_context(frozen, units, timeline, paths=paths, lock=lock)
        progress, records = collect_progress(context)
        context['store'].assert_owned()
        calls.append(len(progress['scenes']))
        return clips._result(setup['run'], 'awaiting_continuity_review', scenes=progress['scenes'])
    monkeypatch.setattr(clips, 'produce_scene_clips', next_stage)
    result = make_video(run_dir=setup['run'], wan_mode='native')
    assert result.status == 'awaiting_continuity_review', result.error
    assert calls == [len(setup['plan']['scenes'])]
    assert not trusting_materials()
