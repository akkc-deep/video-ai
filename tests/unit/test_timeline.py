from dataclasses import replace
from pathlib import Path
import pytest
from video_ai.media.audio import AudioInfo
from video_ai.planning.segments import SegmentedScript, segment_text


def make(text='甲，乙。\r\n丙。', samples=None, fps=16, settings=None):
    from video_ai.config import TimelineSettings
    from video_ai.planning.timeline import build_timeline
    script = SegmentedScript(text, True, segment_text(text))
    speech = [s for s in script.spans if s.kind == 'speech']
    sizes = samples or [48000] * len(speech)
    audio = {s.unit_id: AudioInfo(Path('D:/VideoSi/fixture')/s.unit_id, 'a'*64,
             n*2+44,48000,1,2,n) for s,n in zip(speech,sizes)}
    return build_timeline(script,audio,settings=settings or TimelineSettings(),fps=fps)


@pytest.mark.parametrize('fps,frames,padding', [(16,419,2280),(24,628,1280)])
def test_real_seven_pcm_sample_positions(fps,frames,padding):
    text='夜色渐渐安静下来，微风轻轻吹过树梢。\r\n远处的灯光映在水面上，随着细小的波纹轻轻摇动。\n我们沿着安静的小路慢慢前行，听见脚步声，也听见夜风穿过枝叶。\n'
    t=make(text,[106560,39360,141120,156480,164160,81600,133440],fps)
    assert len(text)==75 and len(t.source_spans)==10
    assert [c.start_sample for c in t.clips]==[96000,202560,337920,479040,731520,895680,977280]
    assert [c.end_sample for c in t.clips]==[202560,241920,479040,635520,895680,977280,1110720]
    assert [c.pause_samples for c in t.clips]==[0,96000,0,96000,0,0,0]
    assert (t.total_speech_samples,t.total_silence_samples,t.total_samples)==(822720,432000,1254720)
    assert (t.total_frames,t.video_padding_samples)==(frames,padding)
    assert t.native_fps==16 and t.frame_rate_conversion==(fps==24)
    assert [s.text for s in t.subtitles]==[c.text for c in t.clips]
    if fps==16: assert [(s.start_frame,s.end_frame) for s in t.subtitles]==[(32,68),(68,81),(113,160),(160,212),(244,299),(299,326),(326,370)]


@pytest.mark.parametrize('text,kinds', [('甲。乙。',['sentence','none']),('甲，乙。',['none','none']),
    (' \r\n甲。\n\n\n乙。\r\n',['paragraph','none']),('甲。\r\n乙。',['paragraph','none']),
    ('值3.14，乙。',['none','none']),('甲！？”乙。',['sentence','none']),('甲 ， 。 乙',['sentence','none'])])
def test_canonical_pause_priority(text,kinds):
    t=make(text)
    assert [c.pause_kind for c in t.clips]==kinds
    assert sum(c.pause_samples for c in t.clips)==sum({'none':0,'sentence':38400,'paragraph':96000}[k] for k in kinds)


def test_zero_micro_projection_and_sample_association():
    from video_ai.config import TimelineSettings
    from video_ai.planning.timeline import associate_units
    t=make('树梢，水面倒影。',[1,3000],settings=TimelineSettings(0,0,0,0))
    assert t.clips[0].start_frame==t.clips[0].end_frame==0
    assert t.total_frames==2 and t.video_padding_samples==2999 and not t.silences
    assert associate_units(t,0,1)==('speech_0001','speech_0002')
    assert associate_units(t,1,2)==('speech_0002',)
    t=make('长句。',[480000],settings=TimelineSettings(0,0,0,0))
    assert associate_units(t,0,80)==associate_units(t,80,160)==('speech_0001',)


def test_half_up_and_absolute_mapping():
    from video_ai.planning.timeline import seconds_to_samples, sample_to_frame
    assert seconds_to_samples(.000010416666666667)==1
    assert sample_to_frame(1500,16)==1
    t=make('甲，乙，丙。',[1600,1600,1600])
    assert [c.end_frame for c in t.clips]==[33,33,34]


@pytest.mark.parametrize('value', [True,-1,None,float('nan'),float('inf'),'2',10**400])
def test_invalid_seconds(value):
    from video_ai.planning.timeline import seconds_to_samples
    with pytest.raises(ValueError): seconds_to_samples(value)


@pytest.mark.parametrize('sample,fps', [(True,16),(-1,16),(1,True),(1,30),(1.0,16)])
def test_invalid_frame_parameters(sample,fps):
    from video_ai.planning.timeline import sample_to_frame
    with pytest.raises(ValueError): sample_to_frame(sample,fps)


def test_bad_script_audio_and_modified_timeline_rejected():
    from video_ai.config import TimelineSettings
    from video_ai.planning.timeline import build_timeline,validate_timeline
    t=make()
    for changed in [replace(t,total_samples=t.total_samples+1), replace(t,subtitles=()),
                    replace(t,clips=(replace(t.clips[0],start_sample=True),*t.clips[1:]))]:
        with pytest.raises(ValueError): validate_timeline(changed)
    script=SegmentedScript('甲。',False,segment_text('甲。'))
    for audio in [{},{'reference_replay':AudioInfo(Path('D:/x'),'a'*64,44,48000,1,2,1)},
                  {'speech_0001':AudioInfo(Path('D:/x'),'a'*64,44,44100,1,2,1)}]:
        with pytest.raises(ValueError): build_timeline(script,audio,settings=TimelineSettings(),fps=16)
    wrong=replace(script,spans=(replace(script.spans[0],boundary='phrase'),))
    with pytest.raises(ValueError): build_timeline(wrong,{},settings=TimelineSettings(),fps=16)
    with pytest.raises(ValueError): make(' ,!?\n')


@pytest.mark.parametrize('fps,end,mid,outputs,overlap',[(16,160,80,84,8),(24,240,120,126,12)])
def test_fade_and_cut_budgets(fps,end,mid,outputs,overlap):
    from video_ai.config import TimelineSettings
    from video_ai.planning.timeline import SlotRange,budget_slots
    t=make('甲。',[480000],fps,TimelineSettings(0,0,0,0))
    slots=[SlotRange('shot_0001',0,mid),SlotRange('shot_0002',mid,end)]
    b=budget_slots(t,slots,transition='fade',transition_seconds=.5)
    assert [s.required_output_frames for s in b.shots]==[outputs,outputs]
    assert [s.required_native_frames for s in b.shots]==[84,84]
    assert [s.wan_frames for s in b.shots]==[85,85]
    assert b.transitions[0].actual_frames==overlap
    assert (b.transitions[0].start_frame,b.transitions[0].end_frame)==(mid-overlap//2,mid+overlap//2)
    cut=budget_slots(t,slots,transition='cut',transition_seconds=0)
    assert [s.required_output_frames for s in cut.shots]==[mid,mid]


def test_odd_limited_three_slot_budget():
    from video_ai.config import TimelineSettings
    from video_ai.planning.timeline import SlotRange,budget_slots
    t=make('甲。',[48000],settings=TimelineSettings(0,0,0,0))
    b=budget_slots(t,[SlotRange('shot_0001',0,2),SlotRange('shot_0002',2,5),SlotRange('shot_0003',5,16)],transition='fade',transition_seconds=1)
    assert [x.actual_frames for x in b.transitions]==[2,3]
    assert [(x.start_frame,x.end_frame) for x in b.transitions]==[(1,3),(4,7)]
    assert all(x.limited_reason=='short_adjacent_slot' for x in b.transitions)
    assert sum(x.required_output_frames for x in b.shots)-5==16


@pytest.mark.parametrize('ranges,transition,seconds', [
    ([(0,7),(8,16)],'cut',0), ([(0,9),(8,16)],'cut',0), ([(0,8),(8,16)],'fade',.001),
    ([(0,8),(8,16)],'cut',1), ([(0,8),(8,15)],'cut',0), ([(0,True)],'cut',0)])
def test_invalid_slot_budget(ranges,transition,seconds):
    from video_ai.config import TimelineSettings
    from video_ai.planning.timeline import SlotRange,budget_slots
    t=make('甲。',[48000],settings=TimelineSettings(0,0,0,0))
    with pytest.raises(ValueError): budget_slots(t,[SlotRange(f'shot_{i:04d}',a,b) for i,(a,b) in enumerate(ranges,1)],transition=transition,transition_seconds=seconds)
