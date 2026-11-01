"""Regression for alias creation after the first batch ownership check."""
from pathlib import Path
import os
import pytest
from unit.test_frames import media_context, make_video


@pytest.mark.parametrize('when',['last_png','evidence_guard'])
def test_late_external_hardlink_never_returns_an_accepted_batch(media_context,monkeypatch,when):
    import video_ai.media.scene_native_batch as batch
    run,kwargs=media_context;source=make_video(media_context,frames=3)
    original_verify=batch.verify_png;logger=kwargs['logger']
    def alias(path):os.link(path,run/'external-alias.png')
    def verify(path,**kw):
        pixels=original_verify(path,**kw)
        if when=='last_png' and Path(path).name=='frame_000003.png':
            alias(Path(path).parent/'frame_000001.png')
        return pixels
    class Logger:
        def __getattr__(self,name):return getattr(logger,name)
        def save_json(self,name,value):
            if when=='evidence_guard' and value.get('algorithm')=='scene_native_png_batch_v1':
                alias(Path(value['frames'][0]['image']['path']))
            return logger.save_json(name,value)
    monkeypatch.setattr(batch,'verify_png',verify)
    with pytest.raises(ValueError,match='non-aliased'):
        batch.extract_native_scene_batch(source,run/'batch',expected_frames=3,width=128,height=72,
            **dict(kwargs,logger=Logger()))


def test_preexisting_external_hardlink_is_refused(media_context):
    from video_ai.media.scene_native_batch import extract_native_scene_batch
    run,kwargs=media_context;source=make_video(media_context,frames=3)
    images,_=extract_native_scene_batch(source,run/'batch',expected_frames=3,width=128,height=72,**kwargs)
    os.link(images[-1]['path'],run/'external-alias.png')
    with pytest.raises(ValueError,match='non-aliased'):
        extract_native_scene_batch(source,run/'batch',expected_frames=3,width=128,height=72,
            reuse_existing=True,**kwargs)
