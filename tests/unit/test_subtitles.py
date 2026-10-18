from dataclasses import replace
from pathlib import Path
import pytest
from composition_helpers import inputs
from video_ai.planning.composition import CompositionSettings

def module():
    from video_ai.media import subtitles
    return subtitles

def test_absolute_quantization_uses_half_up():
    s=module()
    assert [s.quantize(x,1000) for x in (0,23,24,25,47999,48000)]==[0,0,1,1,1000,1000]
    assert [s.quantize(x,100) for x in (239,240,241,48000)]==[0,1,1,100]

def test_layout_preserves_every_character_and_limits_two_lines():
    s=module();layout=s.layout_text('树梢，水面倒影。',measure=lambda text:len(text)*10,width=50)
    assert layout['lines']==['树梢，水面','倒影。']
    assert ''.join(layout['lines'])=='树梢，水面倒影。'
    assert layout['line_ranges']==[dict(start=0,end=5),dict(start=5,end=8)]
    with pytest.raises(ValueError):s.layout_text('长'*11,measure=lambda text:len(text)*10,width=50)

def test_layout_does_not_split_combining_character():
    result=module().layout_text('a\u0301bc',measure=lambda text:len(text)*10,width=25)
    assert result['lines']==['a\u0301','bc']

def test_original_text_and_shared_subtitle_boundaries_are_preserved():
    t,*_=inputs();s=module();p=s.plan_subtitles(t,CompositionSettings(),measure=lambda text:len(text)*54)
    assert p[0]['end_ms']==p[1]['start_ms']==1000
    assert p[0]['end_cs']==p[1]['start_cs']==100
    raw=s.srt_text(p)
    assert raw.startswith('1\n00:00:00,000 --> 00:00:01,000\n夜色渐深，\n')
    assert '\r' not in raw and '\ufeff' not in raw
    assert 'Microsoft YaHei' in s.ass_text(p,CompositionSettings())

def test_literal_characters_are_separate_from_ass_tags():
    s=module();text="中文 空格 ' : \\N {\\pos(0,0)} <>&"
    escaped=s.ass_literal(text)
    assert '{\\pos(0,0)}' not in escaped
    assert '\\{}' not in escaped  # libass renders these inserted braces visibly.
    assert s.decode_ass_literal(escaped)==text

def test_quantization_collapse_and_overlap_fail():
    t,*_=inputs();s=module()
    for events in [(replace(t.subtitles[0],end_sample=1),), (t.subtitles[0],replace(t.subtitles[1],start_sample=47999))]:
        with pytest.raises(ValueError):s.plan_subtitles(replace(t,subtitles=events),CompositionSettings(),measure=lambda text:len(text))

def test_real_private_font_metrics_and_missing_glyph_refusal():
    from video_ai.media.font_metrics import PrivateFont
    font=Path('D:/VideoSi/projects/video-ai/inputs/fonts/msyh.ttc')
    with PrivateFont(font,'Microsoft YaHei',54) as m:
        assert m.face=='Microsoft YaHei'
        assert 90<m.measure('中文')<130
        assert m.measure('中文 空格')>m.measure('中文')
        with pytest.raises(ValueError):m.measure('\U0010ffff')
    assert m.closed

def test_font_file_must_contain_selected_face():
    from video_ai.media.font_metrics import PrivateFont
    with pytest.raises(ValueError):
        with PrivateFont(Path('D:/VideoSi/projects/video-ai/inputs/fonts/msyh.ttc'),'Arial',54):pass
