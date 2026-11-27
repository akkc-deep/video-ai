from dataclasses import FrozenInstanceError
import hashlib

import pytest

from video_ai.planning.emotion import BASE_STYLE, make_plan


def profile(runtime_run):
    from test_tts_backends import vox_config
    from video_ai.planning.speech import freeze_voice
    return freeze_voice(vox_config(runtime_run[1]))


def plan_for(text):
    return make_plan(text, [], BASE_STYLE, fallback={'kind': 'test'})


def assert_coverage(plan, text):
    ranges = sorted([*plan['units'], *plan['skips']], key=lambda x:x['start'])
    assert ''.join(x['original_text'] for x in ranges) == text
    position = 0
    for row in ranges:
        assert row['start'] == position
        assert row['original_text'] == text[row['start']:row['end']]
        position = row['end']
    assert position == len(text)


def test_frozen_voice_and_repeatable_long_script(runtime_run):
    from video_ai.planning.speech import plan_speech
    voice = profile(runtime_run)
    with pytest.raises(TypeError): voice.parameters['seed'] = 999
    with pytest.raises(FrozenInstanceError): voice.reference_sha256 = 'other'
    text = (' 旅行者 2 号，NASA 距离 3.14 光年🙂。\r\n再看繁星！\n' * 150)
    result = plan_speech(plan_for(text), voice)
    assert result == plan_speech(plan_for(text), voice)
    assert result['voice'] == voice.as_dict()
    assert result['source_sha256'] == hashlib.sha256(text.encode()).hexdigest()
    assert_coverage(result, text)
    assert all(len(u['synthesis_text']) <= 250 for u in result['units'])
    assert all(u['voice_id'] == voice.voice_id and u['seed'] == 42 for u in result['units'])


def test_sentence_and_paragraph_pauses_without_whitespace_requests(runtime_run):
    from video_ai.planning.speech import plan_speech
    text = '  第一小句，含有 3.14 和 NASA。\r\n第二句！第三句。  '
    result = plan_speech(plan_for(text), profile(runtime_run))
    assert_coverage(result, text)
    assert len(result['units']) == 3
    assert [u['pause_after_ms'] for u in result['units']] == [450, 220, 0]
    assert result['units'][0]['synthesis_text'].count('3.14') == 1


def test_tiny_same_style_emotion_spans_merge_but_style_changes_split(runtime_run):
    from video_ai.planning.segments import segment_text
    from video_ai.planning.speech import plan_speech
    text = '旅行者 2 号，NASA 仍在前行。多么壮丽，星海无边！'
    rows = [dict(start=s.start, end=s.end, emotion='narrative' if s.start < text.index('多') else 'awe',
                 emotion_intensity=.3, tone='沉稳', pause_after_ms=150) for s in segment_text(text)]
    plan = make_plan(text, rows, BASE_STYLE)
    result = plan_speech(plan, profile(runtime_run))
    assert len(result['units']) == 2
    assert [u['emotion'] for u in result['units']] == ['narrative', 'awe']
    assert len(result['units'][0]['emotion_span_ids']) > 1
    assert_coverage(result, text)


@pytest.mark.parametrize('text', ['星'*1800, '星，'*1000, '始。'+' '*1200+'终。', '\r\n'*200+'正文。', '。。。。正文。！！！'])
def test_hard_limit_and_skip_coverage(runtime_run, text):
    from video_ai.planning.speech import plan_speech
    from video_ai.planning.segments import speakable
    result = plan_speech(plan_for(text), profile(runtime_run))
    assert_coverage(result, text)
    assert all(0 < len(u['synthesis_text']) <= 250 and speakable(u['synthesis_text']) for u in result['units'])


@pytest.mark.parametrize('damage', ['gap', 'source', 'rewrite', 'emotion', 'pause', 'tone'])
def test_invalid_plan_rejected(runtime_run, damage):
    from video_ai.planning.speech import plan_speech
    plan = plan_for('原文。')
    if damage == 'gap': plan['spans'][0]['start'] = 1
    if damage == 'source': plan['source_sha256'] = 'bad'
    if damage == 'rewrite': plan['spans'][0]['synthesis_text'] = '改写'
    if damage == 'emotion': plan['spans'][0]['emotion'] = 'bad'
    if damage == 'pause': plan['spans'][0]['pause_after_ms'] = 999
    if damage == 'tone': plan['spans'][0]['tone'] = 'bad'
    with pytest.raises(ValueError): plan_speech(plan, profile(runtime_run))


@pytest.mark.parametrize('limits', [(0,250), (180,251), (251,250), (True,250)])
def test_invalid_limits_rejected(runtime_run, limits):
    from video_ai.planning.speech import plan_speech
    with pytest.raises(ValueError):
        plan_speech(plan_for('正文。'), profile(runtime_run), target_chars=limits[0], max_chars=limits[1])


@pytest.mark.parametrize('text, pauses', [('\r\nOne. Two.', [220,0]),
    ('a'*249+'.\r\nTwo. Three.', [450,220,0])])
def test_newline_pause_belongs_to_boundary_between_spoken_text(runtime_run, text, pauses):
    from video_ai.planning.speech import plan_speech
    result = plan_speech(plan_for(text), profile(runtime_run))
    assert_coverage(result, text)
    assert [u['pause_after_ms'] for u in result['units']] == pauses


@pytest.mark.parametrize('text', [
    'NASA released the U.S. results at science.nasa.gov. Then we left.',
    'Dr. Smith measured 3.14 km. NASA confirmed it.',
    '这里使用 e.g. examples 和 science.nasa.gov 查询。下一句。',
])
def test_english_internal_periods_do_not_insert_sentence_pauses(runtime_run, text):
    from video_ai.planning.speech import plan_speech
    result = plan_speech(plan_for(text), profile(runtime_run))
    assert_coverage(result, text)
    assert len(result['units']) == 2


def test_pause_hint_before_attached_whitespace_is_retained(runtime_run):
    from video_ai.planning.segments import segment_text
    from video_ai.planning.speech import plan_speech
    text = 'One.\r\nTwo.'
    rows = [dict(start=s.start, end=s.end, emotion='narrative', emotion_intensity=.3,
                 tone='沉稳', pause_after_ms=610 if s.start == 0 else 0) for s in segment_text(text)]
    result = plan_speech(make_plan(text, rows, BASE_STYLE), profile(runtime_run))
    assert result['units'][0]['pause_after_ms'] == 610


def test_tiny_emotion_lead_in_joins_dominant_same_sentence_style(runtime_run):
    from video_ai.planning.speech import plan_speech
    text = '看啊，星云在黑暗中绽放，宇宙竟然如此壮丽！'
    rows = [dict(start=0,end=3,emotion='narrative',emotion_intensity=.3,tone='沉稳',pause_after_ms=150),
            dict(start=3,end=len(text),emotion='awe',emotion_intensity=.6,tone='沉稳',pause_after_ms=0)]
    result = plan_speech(make_plan(text, rows, BASE_STYLE), profile(runtime_run))
    assert len(result['units']) == 1
    assert result['units'][0]['emotion'] == 'awe'
    assert len(result['units'][0]['emotion_span_ids']) == 2
    assert_coverage(result, text)


def test_unpunctuated_long_text_does_not_leave_one_character_tail(runtime_run):
    from video_ai.planning.speech import plan_speech
    result = plan_speech(plan_for('星'*251), profile(runtime_run))
    assert [len(u['synthesis_text']) for u in result['units']] == [180,71]
