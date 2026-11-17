import importlib.util
from pathlib import Path
import wave
import os
import pytest


def api():
    spec=importlib.util.spec_from_file_location('gpu_postprocess',Path(__file__).parents[2]/'scripts/postprocess_local_gpu.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_narration_slice_keeps_original_samples_and_canonical_silence(tmp_path):
    module=api()
    source=tmp_path/'source.wav'
    with wave.open(str(source),'wb') as audio:
        audio.setparams((1,2,48000,0,'NONE',''));audio.writeframes(b'\x01\x02'*3000)
    stamp=dict(path=str(source),bytes=source.stat().st_size,mtime_ns=source.stat().st_mtime_ns)
    timeline=dict(clips=[dict(unit_id='speech_1',start_sample=1000,end_sample=4000,samples=3000,
        pcm=dict(stamp=stamp))],subtitles=[])
    target=tmp_path/'slice.wav'
    result=module.slice_narration(timeline,start_frame=0,frames=2,target=target)
    with wave.open(str(target),'rb') as audio:
        assert audio.getnframes()==6000
        assert audio.readframes(6000)==bytes(2000)+b'\x01\x02'*3000+bytes(4000)
    assert result['samples']==6000
    assert result['speech_samples']==3000
    with source.open('r+b') as stream:
        stream.seek(-2,2);stream.write(b'xx')
    os.utime(source,ns=(source.stat().st_atime_ns,stamp['mtime_ns']+10000000))
    with pytest.raises(ValueError):
        module.slice_narration(timeline,start_frame=0,frames=2,target=tmp_path/'changed.wav')
