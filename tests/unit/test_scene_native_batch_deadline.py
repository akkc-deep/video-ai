"""The unchanged PNG checker can consume one caller's remaining batch budget."""
import json
from types import SimpleNamespace
import pytest
from image_helpers import write_png


@pytest.mark.parametrize('probe_elapsed',[250,450])
def test_png_decode_uses_fresh_remaining_budget_after_probe(runtime_run,monkeypatch,probe_elapsed):
    import video_ai.media.scene_upscale as checker
    from video_ai.media.images import _remaining
    path=runtime_run[0]/'frame.png';write_png(path,2,2)
    clock=[0.0];seen=[]
    def probe(*a,**kw):
        seen.append(('probe',kw['timeout']));clock[0]=probe_elapsed
        return SimpleNamespace(returncode=0,stdout=json.dumps(dict(streams=[dict(
            codec_name='png',width=2,height=2,pix_fmt='rgb24')])).encode())
    def decode(*a,**kw):seen.append(('decode',kw['timeout']));return bytes(12)
    monkeypatch.setattr(checker.subprocess,'run',probe)
    monkeypatch.setattr(checker,'_decode',decode)
    config=SimpleNamespace(tools={'ffprobe':'fixture-only'})
    call=lambda:checker.verify_png(path,width=2,height=2,config=config,
        remaining_timeout=lambda:_remaining(400,clock[0]))
    if probe_elapsed==450:
        with pytest.raises(TimeoutError,match='media budget expired'):call()
        assert seen==[('probe',300)]
    else:
        assert call()==bytes(12)
        assert seen==[('probe',300),('decode',150)]
