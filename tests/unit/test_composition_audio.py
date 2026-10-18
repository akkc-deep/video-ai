from array import array
from dataclasses import replace
from pathlib import Path
import wave
import pytest
from composition_helpers import inputs
from video_ai.planning.composition import CompositionSettings
from video_ai.runtime.manifest import hash_file

def module():
    from video_ai.media import composition_audio
    return composition_audio

def wav(path,samples):
    with wave.open(str(path),'wb') as f:f.setparams((1,2,48000,0,'NONE',''));f.writeframes(array('h',samples).tobytes())
    return path

def fixture(tmp_path):
    t,*_=inputs()
    clips=[]
    for i,c in enumerate(t.clips,1):
        path=wav(tmp_path/(c.unit_id+'.wav'),[i*1000,0,-i*1000]*16000)
        ident=hash_file(path)
        clips.append(replace(c,pcm=replace(c.pcm,path=path,sha256=ident.sha256,bytes=ident.bytes)))
    return replace(t,clips=tuple(clips))

def test_narration_preserves_every_payload_byte(tmp_path):
    t=fixture(tmp_path);target=tmp_path/'narration.wav'
    record=module().write_narration(t,target)
    assert record['samples']==144000 and record['speech_samples']==144000
    with wave.open(str(target),'rb') as f:data=f.readframes(f.getnframes())
    assert data==b''.join(wave.open(str(c.pcm.path),'rb').readframes(c.samples) for c in t.clips)
    assert module().validate_narration(t,target)==record
    with pytest.raises(FileExistsError):module().write_narration(t,target)

def test_added_silence_and_padding_are_exact(tmp_path):
    from video_ai.config import TimelineSettings
    from video_ai.planning.timeline import build_timeline
    from video_ai.planning.segments import SegmentedScript
    t=fixture(tmp_path)
    audio={c.unit_id:replace(c.pcm,samples=47999) for c in t.clips}
    for info in audio.values():wav(info.path,[100]*47999)
    audio={k:replace(a,bytes=hash_file(a.path).bytes,sha256=hash_file(a.path).sha256) for k,a in audio.items()}
    t=build_timeline(SegmentedScript(t.original_text,t.has_bom,t.source_spans),audio,settings=TimelineSettings(0.1,0.2,0.1,0.1),fps=16)
    p=tmp_path/'narration.wav';module().write_narration(t,p)
    with wave.open(str(p),'rb') as f:
        raw=array('h',f.readframes(f.getnframes()))
    assert len(raw)==165000
    for c in t.clips:assert list(raw[c.start_sample:c.end_sample])==[100]*47999
    for s in t.silences:assert not any(raw[s.start_sample:s.end_sample])
    assert not any(raw[t.total_samples:])

def test_narration_rejects_changed_pcm_and_nonzero_external_silence(tmp_path):
    t=fixture(tmp_path);target=tmp_path/'n.wav';module().write_narration(t,target)
    wav(t.clips[0].pcm.path,[0]*48000)
    with pytest.raises((ValueError,OSError)):module().validate_narration(t,target)

@pytest.mark.parametrize('samples',[1,5,1200,10000])
def test_music_loop_and_peak_keep_narration_duration(tmp_path,samples):
    n=wav(tmp_path/'n.wav',[32767,-32767,0]*1000)
    music=tmp_path/'music.f32';music.write_bytes(array('f',[0.8,-0.8]*samples).tobytes())
    target=tmp_path/'mixed.wav';record=module().mix_music(n,music,target,settings=CompositionSettings(music_fade_seconds=0.01,music_loop_crossfade_seconds=0.00005))
    with wave.open(str(target),'rb') as f:
        assert (f.getnframes(),f.getnchannels(),f.getframerate())==(3000,2,48000)
        values=array('h',f.readframes(3000))
    assert max(abs(v) for v in values)<=31130
    assert record['narration_gain']<1 and record['music_gain']<=0.12
    assert record['crossfade_samples']==min(2,(samples-1)//2)
    assert module().validate_mix(n,music,target,settings=CompositionSettings(music_fade_seconds=0.01,music_loop_crossfade_seconds=0.00005))==record

def test_zero_music_has_zero_gain_and_stereo_narration(tmp_path):
    n=wav(tmp_path/'n.wav',[1000,-1000]*10);m=tmp_path/'m.f32';m.write_bytes(array('f',[0,0]).tobytes())
    record=module().mix_music(n,m,tmp_path/'mix.wav',settings=CompositionSettings())
    assert record['music_gain']==0 and record['narration_gain']==1 and record['hard_seam'] is True

def test_first_music_crossfade_begins_before_original_tail(tmp_path):
    n=wav(tmp_path/'n.wav',[0]*10);m=tmp_path/'m.f32'
    m.write_bytes(array('f',[x for v in [.1,.2,.3,.4,.5] for x in (v,v)]).tobytes())
    target=tmp_path/'mix.wav'
    module().mix_music(n,m,target,settings=CompositionSettings(music_gain=.1,music_fade_seconds=0,music_loop_crossfade_seconds=2/48000))
    with wave.open(str(target),'rb') as f:actual=array('h',f.readframes(10))[::2]
    assert list(actual)==[328,655,983,1311,655,983,1311,655,983,1311]

def test_music_that_covers_target_is_cropped_without_looping(tmp_path):
    n=wav(tmp_path/'n.wav',[0]*5);m=tmp_path/'m.f32'
    m.write_bytes(array('f',[x for v in [.1,.2,.3,.4,.5] for x in (v,v)]).tobytes())
    target=tmp_path/'mix.wav'
    result=module().mix_music(n,m,target,settings=CompositionSettings(music_gain=.1,music_fade_seconds=0,music_loop_crossfade_seconds=2/48000))
    with wave.open(str(target),'rb') as f:actual=array('h',f.readframes(5))[::2]
    assert list(actual)==[328,655,983,1311,1638] and result['loop_count']==1

def test_final_music_copy_tail_is_not_overlapped_without_another_copy(tmp_path):
    n=wav(tmp_path/'n.wav',[0]*8);m=tmp_path/'m.f32'
    m.write_bytes(array('f',[x for v in [.1,.2,.3,.4,.5] for x in (v,v)]).tobytes())
    target=tmp_path/'mix.wav'
    result=module().mix_music(n,m,target,settings=CompositionSettings(music_gain=.1,music_fade_seconds=0,music_loop_crossfade_seconds=2/48000))
    with wave.open(str(target),'rb') as f:actual=array('h',f.readframes(8))[::2]
    assert list(actual)==[328,655,983,1311,655,983,1311,1638] and result['loop_count']==2

@pytest.mark.parametrize('values',[[],[float('nan'),0],[1]])
def test_invalid_music_is_refused(tmp_path,values):
    n=wav(tmp_path/'n.wav',[100]*10);m=tmp_path/'m.f32';m.write_bytes(array('f',values).tobytes())
    with pytest.raises(ValueError):module().mix_music(n,m,tmp_path/'mix.wav',settings=CompositionSettings())
