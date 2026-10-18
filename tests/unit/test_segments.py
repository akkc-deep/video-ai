from dataclasses import replace
import pytest


@pytest.mark.parametrize('text,parts', [
    ('夜色安静，风吹树梢。\r\n\r\n听见脚步。', ['夜色安静，', '风吹树梢。', '\r\n\r\n', '听见脚步。']),
    ('“你好？！”  数字3.14，🙂123尾巴', ['“你好？！”', '  ', '数字3.14，', '🙂123尾巴']),
    ('他说：「可以。」\n末尾', ['他说：', '「可以。」', '\n', '末尾']),
    ('无分界' * 1000, ['无分界' * 1000]),
    ('，。 \t\n', ['，。', ' \t\n']),
    ('', []),
])
def test_exact_unicode_coverage(text, parts):
    from video_ai.planning.segments import segment_text, validate_segments
    spans = segment_text(text)
    assert [s.text for s in spans] == parts
    validate_segments(text, spans)
    assert ''.join(s.text for s in spans) == text
    speech = [s for s in spans if s.kind == 'speech']
    assert [s.unit_id for s in speech] == [f'speech_{i:04d}' for i in range(1, len(speech)+1)]


def test_bom_crlf_no_normalization(tmp_path):
    from video_ai.planning.segments import SegmentedScript
    path = tmp_path / 'script.txt'
    path.write_bytes(b'\xef\xbb\xbf' + '你好。\r\n🙂'.encode())
    result = SegmentedScript.read(path)
    assert result.has_bom and result.text == '你好。\r\n🙂'
    assert result.spans[-1].start == 5
    path.write_bytes(b'\xff')
    with pytest.raises(UnicodeError):
        SegmentedScript.read(path)


@pytest.mark.parametrize('mutation', ['gap', 'overlap', 'rewrite', 'id', 'skip', 'bool', 'reverse', 'missing'])
def test_invalid_coverage_rejected(mutation):
    from video_ai.planning.segments import segment_text, validate_segments
    text = '甲，乙。\n'
    spans = list(segment_text(text))
    if mutation == 'gap': spans[1] = replace(spans[1], start=3)
    if mutation == 'overlap': spans[1] = replace(spans[1], start=1)
    if mutation == 'rewrite': spans[0] = replace(spans[0], text='错，')
    if mutation == 'id': spans[1] = replace(spans[1], unit_id=spans[0].unit_id)
    if mutation == 'skip': spans[0] = replace(spans[0], kind='skip', unit_id=None)
    if mutation == 'bool': spans[0] = replace(spans[0], start=False)
    if mutation == 'reverse': spans.reverse()
    if mutation == 'missing': spans.pop()
    with pytest.raises(ValueError): validate_segments(text, spans)


def test_boundaries_and_symbols():
    from video_ai.planning.segments import segment_text
    spans = segment_text('甲，乙！\r\n  。🙂$')
    assert [s.boundary for s in spans] == ['phrase', 'sentence', 'newline', 'sentence', 'end']
    assert [s.kind for s in spans] == ['speech', 'speech', 'skip', 'skip', 'speech']
