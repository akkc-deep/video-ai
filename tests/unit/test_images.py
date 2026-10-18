from dataclasses import replace
from pathlib import Path
import pytest
from image_helpers import write_png


@pytest.fixture
def media_context(runtime_run):
    from video_ai.config import load_config
    from video_ai.runtime.logging import RunLogger
    run,config,paths=runtime_run
    actual=load_config(Path('D:/VideoSi/projects/video-ai/config/production.json'))
    config=replace(config,tools=dict(config.tools,ffmpeg=actual.tools['ffmpeg'],ffprobe=actual.tools['ffprobe']))
    return run,dict(config=config,paths=paths,logger=RunLogger(run),unit_id='shot_0001')


@pytest.mark.parametrize('width,height',[(80,40),(40,80)])
def test_real_contain_retains_source_and_produces_one_rgb_png(media_context,width,height):
    from video_ai.media.images import adapt_image,validate_start_png,_command
    run,kwargs=media_context;source=write_png(run/'input.png',width,height);before=source.read_bytes()
    target=run/'start.png';info,evidence=adapt_image(source,target,width=1280,height=720,**kwargs)
    assert info['width']==1280 and info['height']==720 and info['pixel_format']=='rgb24'
    assert source.read_bytes()==before and len(evidence)>=3
    assert validate_start_png(target,width=1280,height=720,**kwargs)[0]['format']=='png'
    pixels=_command((kwargs['config'].tools['ffmpeg'],'-nostdin','-v','error','-i',target,'-pix_fmt','rgb24','-f','rawvideo','-'),**kwargs).stdout_path.read_bytes()
    assert len(pixels)==1280*720*3
    assert pixels[:3]==b'\0\0\0'
    center=(360*1280+640)*3
    assert pixels[center:center+3]==bytes((120,150,200))
    with pytest.raises(FileExistsError):adapt_image(source,target,width=1280,height=720,**kwargs)


def test_bad_and_multiframe_images_refused(media_context):
    from video_ai.media.images import inspect_image
    run,kwargs=media_context;bad=run/'bad.png';bad.write_bytes(b'not an image')
    with pytest.raises((RuntimeError,ValueError)):inspect_image(bad,**kwargs)
    # Two-frame GIF made without a third-party library.
    gif=run/'animated.gif'
    frame=b'\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00'
    delay=b'\x21\xf9\x04\x00\x0a\x00\x00\x00'
    gif.write_bytes(b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff'+delay+frame+delay+frame+b'\x3b')
    with pytest.raises(ValueError,match='single'):inspect_image(gif,**kwargs)


def test_upscale_image_stage_keeps_original_unit_and_decreasing_deadline(media_context,monkeypatch):
    import json
    from video_ai.media import images
    run,kwargs=media_context;kwargs=dict(kwargs,unit_id='shot_0001:frame_000001')
    source=write_png(run/'frame.png',1280,720)
    clock=[100.0];original=images.run_logged
    def command(*args,**kw):
        result=original(*args,**kw);clock[0]+=2;return result
    monkeypatch.setattr(images,'run_logged',command)
    monkeypatch.setattr(images,'monotonic',lambda:clock[0],raising=False)
    info,evidence=images.validate_start_png(source,width=1280,height=720,stage='upscale',timeout=10,**kwargs)
    assert info['format']=='png' and evidence[0].parent==run/'logs/upscale'
    assert ':' not in evidence[0].name
    events=[json.loads(l) for l in (run/'logs/events.jsonl').read_text().splitlines()]
    starts=[e for e in events if e['event']=='command_started']
    assert [e['details']['timeout'] for e in starts]==[10,8]
    assert all(e['stage']=='upscale' and e['unit_id']==kwargs['unit_id'] for e in events)


def test_expired_image_budget_stops_before_decode(media_context,monkeypatch):
    from video_ai.media import images
    run,kwargs=media_context;source=write_png(run/'frame.png',1280,720)
    clock=[100.];original=images.run_logged
    def command(*args,**kw):
        result=original(*args,**kw);clock[0]+=11;return result
    monkeypatch.setattr(images,'run_logged',command)
    monkeypatch.setattr(images,'monotonic',lambda:clock[0],raising=False)
    with pytest.raises(TimeoutError):images.inspect_image(source,stage='upscale',timeout=10,**kwargs)


@pytest.mark.parametrize('timeout',[True,0,-1,float('nan'),float('inf')])
def test_image_rejects_invalid_budget_before_commands(media_context,timeout):
    from video_ai.media.images import inspect_image
    run,kwargs=media_context;source=write_png(run/'frame.png',1280,720)
    with pytest.raises(ValueError):inspect_image(source,timeout=timeout,**kwargs)
