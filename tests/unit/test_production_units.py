"""Automatic units preserve source text and reject unsupported source identities."""
from copy import deepcopy
from dataclasses import asdict

import pytest

from video_ai.planning.composition import CompositionSettings
from video_ai.planning.segments import SegmentedScript, TextSpan, segment_text


SETTINGS = CompositionSettings()


def facts(**changes):
    value = dict(subject='白鸽', action_or_state=None, setting=None, quantity=None,
                 negation=None, relation_or_order=None, context_sources=[], resolved_references=[])
    value.update(changes)
    return value


def item(end, **changes):
    return dict(text_end=end, semantic_reason='一个连续画面', facts=facts(**changes))


def apply(script, candidates, proposal, known=(), measure=len):
    from video_ai.planning.production_units import apply_units_proposal
    return apply_units_proposal(script, candidates, proposal, known_spans=known,
                                measure=measure, composition_settings=SETTINGS)


def test_bom_crlf_subdivision_resolves_exact_prior_final_source(tmp_path):
    path = tmp_path / 'script.txt'
    path.write_bytes(b'\xef\xbb\xbf' + '白鸽飞翔。\r\n它缓缓落下。'.encode())
    script = SegmentedScript.read(path)
    candidates = [s for s in script.spans if s.kind == 'speech']
    proposal = {'speech_0001': [item(2), item(5)], 'speech_0002': [item(13,
        context_sources=[dict(text_start=0, text_end=2, source_quote='白鸽')],
        resolved_references=[dict(reference_quote='它', resolved_subject='白鸽', context_source_indices=[0])])]}
    spans, specs = apply(script, candidates, proposal)
    assert [(s.start, s.end, s.text, s.boundary, s.unit_id) for s in spans] == [
        (0, 2, '白鸽', 'phrase', 'speech_0001'), (2, 5, '飞翔。', 'sentence', 'speech_0002'),
        (5, 7, '\r\n', 'newline', None), (7, 13, '它缓缓落下。', 'sentence', 'speech_0003')]
    assert ''.join(s.text for s in spans) == script.text
    assert specs['speech_0003']['facts']['context_sources'] == [dict(
        unit_id='speech_0001', text_start=0, text_end=2, source_quote='白鸽')]
    assert specs['speech_0003']['interpretation_method'] == 'automated_source'
    assert script.has_bom


@pytest.mark.parametrize('mutation', ['bool_end', 'decreasing', 'incomplete', 'outside', 'unknown',
    'blank_reason', 'missing_fact', 'blank_fact', 'bool_source', 'bad_quote', 'partial_source',
    'future_source', 'duplicate_source', 'bool_index', 'duplicate_index', 'negative_index',
    'missing_index', 'outside_reference', 'empty_indices', 'unknown_source_key'])
def test_invalid_wire_units_and_references_rejected(mutation):
    script = SegmentedScript('白鸽。它飞。', False, segment_text('白鸽。它飞。'))
    proposal = {'speech_0001': [item(3)], 'speech_0002': [item(6,
        context_sources=[dict(text_start=0, text_end=3, source_quote='白鸽。')],
        resolved_references=[dict(reference_quote='它', resolved_subject='白鸽', context_source_indices=[0])])]}
    first = proposal['speech_0001'][0]
    last = proposal['speech_0002'][0]
    source = last['facts']['context_sources'][0]
    reference = last['facts']['resolved_references'][0]
    if mutation == 'bool_end': first['text_end'] = True
    if mutation == 'decreasing': proposal['speech_0001'] = [item(2), item(1), item(3)]
    if mutation == 'incomplete': first['text_end'] = 2
    if mutation == 'outside': first['text_end'] = 4
    if mutation == 'unknown': first['text'] = '改写'
    if mutation == 'blank_reason': first['semantic_reason'] = ' '
    if mutation == 'missing_fact': del first['facts']['subject']
    if mutation == 'blank_fact': first['facts']['subject'] = ''
    if mutation == 'bool_source': source['text_start'] = False
    if mutation == 'bad_quote': source['source_quote'] = '另一只鸽子'
    if mutation == 'partial_source': source.update(text_end=2, source_quote='白鸽')
    if mutation == 'future_source': first['facts']['context_sources'] = [dict(text_start=3, text_end=6, source_quote='它飞。')]
    if mutation == 'duplicate_source': last['facts']['context_sources'].append(deepcopy(source))
    if mutation == 'bool_index': reference['context_source_indices'] = [False]
    if mutation == 'duplicate_index': reference['context_source_indices'] = [0, 0]
    if mutation == 'negative_index': reference['context_source_indices'] = [-1]
    if mutation == 'missing_index': reference['context_source_indices'] = [1]
    if mutation == 'outside_reference': reference['reference_quote'] = '他'
    if mutation == 'empty_indices': reference['context_source_indices'] = []
    if mutation == 'unknown_source_key': source['unit_id'] = 'speech_0001'
    with pytest.raises(ValueError):
        apply(script, script.spans, proposal)


@pytest.mark.parametrize('text,end', [('a\u0301b。', 1), ('👩\u200d💻好。', 1), ('👩\u200d💻好。', 2),
    ('✈\ufe0f飞。', 1), ('👍🏽好。', 1), ('🇨🇳好。', 1), ('क\u093f好。', 1)])
def test_split_inside_grapheme_is_rejected(text, end):
    script = SegmentedScript(text, False, segment_text(text))
    with pytest.raises(ValueError):
        apply(script, script.spans, {'speech_0001': [item(end), item(len(text))]})


def test_layout_rejects_three_lines_but_accepts_lossless_refinement():
    script = SegmentedScript('甲乙丙丁戊。', False, segment_text('甲乙丙丁戊。'))
    with pytest.raises(ValueError, match='two lines'):
        apply(script, script.spans, {'speech_0001': [item(6)]}, measure=lambda s: len(s)*800)
    spans, _ = apply(script, script.spans, {'speech_0001': [item(3), item(6)]}, measure=lambda s: len(s)*800)
    assert [s.text for s in spans] == ['甲乙丙', '丁戊。']


def test_cross_batch_final_ids_and_references():
    script = SegmentedScript('白鸽。' * 9 + '它飞。', False, segment_text('白鸽。' * 9 + '它飞。'))
    first, _ = apply(script, script.spans[:8], {s.unit_id: [item(s.end)] for s in script.spans[:8]})
    spans, specs = apply(script, script.spans[8:], {'speech_0009': [item(27)], 'speech_0010': [item(30,
        context_sources=[dict(text_start=0, text_end=3, source_quote='白鸽。')],
        resolved_references=[dict(reference_quote='它', resolved_subject='白鸽', context_source_indices=[0])])]}, known=first)
    assert [s.unit_id for s in spans] == ['speech_0009', 'speech_0010']
    assert specs['speech_0010']['facts']['context_sources'][0]['unit_id'] == 'speech_0001'


def test_schema_fixed_candidates_and_strict_wire_types():
    from video_ai.planning.production_units import make_units_schema
    from video_ai.planning.storyboard import _schema_check
    script = SegmentedScript('甲。乙。', False, segment_text('甲。乙。'))
    schema = make_units_schema(script.spans, ())
    _schema_check({'speech_0001': [item(2)], 'speech_0002': [item(4)]}, schema)
    for invalid in ({'speech_0001': [item(2)]}, {'speech_0001': [item(True)], 'speech_0002': [item(4)]}):
        with pytest.raises(ValueError):
            _schema_check(invalid, schema)
    with pytest.raises(ValueError):
        make_units_schema(segment_text('甲。'*9), ())


def test_punctuation_only_subdivision_is_rejected_before_tts():
    script = SegmentedScript('甲。', False, segment_text('甲。'))
    with pytest.raises(ValueError):
        apply(script, script.spans, {'speech_0001': [item(1), item(2)]})


def test_ambiguous_known_context_identity_is_rejected():
    script = SegmentedScript('白鸽。它飞。', False, segment_text('白鸽。它飞。'))
    known = (script.spans[0], script.spans[0])
    with pytest.raises(ValueError):
        apply(script, script.spans[1:], {'speech_0002': [item(6)]}, known=known)


def test_original_punctuation_skip_is_preserved_between_candidates():
    script = SegmentedScript('甲。 。\r\n乙。', False, segment_text('甲。 。\r\n乙。'))
    candidates = [s for s in script.spans if s.kind == 'speech']
    spans, _ = apply(script, candidates, {'speech_0001': [item(2)], 'speech_0002': [item(8)]})
    assert [asdict(s) for s in spans if s.kind == 'skip'] == [
        dict(start=2, end=3, text=' ', kind='skip', boundary='none', unit_id=None),
        dict(start=3, end=4, text='。', kind='skip', boundary='sentence', unit_id=None),
        dict(start=4, end=6, text='\r\n', kind='skip', boundary='newline', unit_id=None)]


def payload_fixture():
    text = '白鸽。\r\n它飞。'
    script = SegmentedScript(text, True, segment_text(text))
    spans, specs = apply(script, [s for s in script.spans if s.kind == 'speech'],
        {'speech_0001': [item(3)], 'speech_0002': [item(8)]})
    return dict(decoded_text=text, has_bom=True, spans=[asdict(s) for s in spans], semantic_specs=specs,
        planner=dict(model='qwen3:8b', request_paths=['D:/VideoSi/run/units_batch_0001_initial.json'],
        batches=[dict(batch_id='units_batch_0001', candidate_ids=['speech_0001', 'speech_0002'],
                      request_ids=['units_batch_0001_initial'])]))


def test_completed_payload_reconstructs_script():
    from video_ai.planning.production_units import validate_production_units
    script = validate_production_units(payload_fixture(), measure=len, composition_settings=SETTINGS)
    assert script.has_bom is True and script.text == '白鸽。\r\n它飞。'
    assert script.spans[1] == TextSpan(3, 5, '\r\n', 'skip', 'newline', None)


@pytest.mark.parametrize('mutation', ['unknown_payload', 'bool_bom', 'bool_start', 'unknown_span',
    'split_skip', 'boundary', 'merge_original', 'semantic_id', 'review_method', 'unknown_spec',
    'wrong_model', 'missing_candidate', 'unknown_planner', 'relative_path', 'duplicate_request', 'wrong_request',
    'array_boundary', 'array_kind'])
def test_completed_payload_rejects_tampering(mutation):
    from video_ai.planning.production_units import validate_production_units
    payload = payload_fixture()
    if mutation == 'unknown_payload': payload['review'] = 'passed'
    if mutation == 'bool_bom': payload['has_bom'] = 1
    if mutation == 'bool_start': payload['spans'][0]['start'] = False
    if mutation == 'unknown_span': payload['spans'][0]['sha256'] = 'fake'
    if mutation == 'split_skip': payload['spans'][1:2] = [dict(start=3, end=4, text='\r', kind='skip', boundary='newline', unit_id=None), dict(start=4, end=5, text='\n', kind='skip', boundary='newline', unit_id=None)]
    if mutation == 'boundary': payload['spans'][0]['boundary'] = 'phrase'
    if mutation == 'merge_original': payload['spans'] = [dict(start=0, end=8, text=payload['decoded_text'], kind='speech', boundary='sentence', unit_id='speech_0001')]
    if mutation == 'semantic_id': del payload['semantic_specs']['speech_0002']
    if mutation == 'review_method': payload['semantic_specs']['speech_0001']['interpretation_method'] = 'human_text'
    if mutation == 'unknown_spec': payload['semantic_specs']['speech_0001']['verdict'] = 'passed'
    if mutation == 'wrong_model': payload['planner']['model'] = 'other'
    if mutation == 'missing_candidate': payload['planner']['batches'][0]['candidate_ids'].pop()
    if mutation == 'unknown_planner': payload['planner']['human_review'] = 'passed'
    if mutation == 'relative_path': payload['planner']['request_paths'] = ['logs/request.json']
    if mutation == 'duplicate_request': payload['planner']['batches'][0]['request_ids'] *= 2
    if mutation == 'wrong_request': payload['planner']['batches'][0]['request_ids'] = ['units_batch_0002_initial']
    if mutation == 'array_boundary': payload['spans'][0]['boundary'] = []
    if mutation == 'array_kind': payload['spans'][0]['kind'] = []
    with pytest.raises(ValueError):
        validate_production_units(payload, measure=len, composition_settings=SETTINGS)
