import array
from dataclasses import replace
from pathlib import Path
import wave
import pytest


def write_pcm(path, samples):
    with wave.open(str(path),'wb') as file:
        file.setparams((1,2,48000,0,'NONE',''))
        file.writeframes(array.array('h',samples).tobytes())


def test_signal_envelope_preserves_pcm_and_includes_detection_guard(tmp_path):
    from video_ai.media.timing import measure_envelope
    path=tmp_path/'signal.wav';write_pcm(path,[0]*480+[100]*4800+[0]*960)
    before=path.read_bytes();result=measure_envelope(path)
    assert result.spoken_start_sample==480 and result.spoken_end_sample==5280
    assert result.boundary_uncertainty_samples==240
    assert result.threshold_boundaries==((480,5280),)*4
    assert result.samples==6240 and result.peak==100
    assert path.read_bytes()==before


def test_signal_uncertainty_reflects_threshold_variation(tmp_path):
    from video_ai.media.timing import measure_envelope
    path=tmp_path/'signal.wav';write_pcm(path,[0]*10+[1]*600+[100]*4800+[1]*1000+[0]*1000)
    result=measure_envelope(path)
    assert result.spoken_start_sample==310 and result.spoken_end_sample==5910
    assert result.boundary_uncertainty_samples==740
    assert result.threshold_boundaries[0]==(10,6410)
    assert result.threshold_boundaries[3]==(610,5410)


@pytest.mark.parametrize('value',[0,1,7])
def test_missing_signal_is_not_accepted_as_speech(tmp_path,value):
    from video_ai.media.timing import measure_envelope
    path=tmp_path/'silent.wav';write_pcm(path,[value]*4800)
    with pytest.raises(ValueError):measure_envelope(path)


def test_automatic_uncertainty_clips_to_pcm_but_human_rules_preserved():
    from test_timeline import make
    from video_ai.planning.storyboard import SpeechTimingEvidence,UnitTiming,SemanticCue,plan_slots
    t=make('甲，乙。',[4800,4800]);u=tuple(UnitTiming(c.unit_id,100,4000,300,(),'passed','passed') for c in t.clips)
    cues=(SemanticCue('cue_0001',u[0].unit_id,u[1].unit_id,t.clips[1].start_sample+100,'passed'),)
    timing=SpeechTimingEvidence(u,cues,review_method='automated_audio')
    assert len(plan_slots(t,timing=timing))==2
    with pytest.raises(ValueError):plan_slots(t,timing=replace(timing,review_method='human_audio'))


def test_digital_internal_silence_never_becomes_word_timing(tmp_path):
    from video_ai.media.timing import measure_envelope
    path=tmp_path/'signal.wav';write_pcm(path,[0]*500+[100]*1000+[0]*600+[100]*1000+[0]*500)
    result=measure_envelope(path)
    assert result.verified_internal_silences==((1500,2100),)
    assert result.spoken_start_sample==500 and result.spoken_end_sample==3100
