"""Terminal source coverage must be mandatory in the model wire grammar."""
from copy import deepcopy
import json

import pytest

from video_ai.adapters.ollama import OllamaFormatError, ollama_schema, parse_completed_response
from video_ai.planning.production_units import make_units_schema
from video_ai.planning.segments import TextSpan


TEXT = '它只是阳光里一个极其微弱的浅蓝色光点。'


def schema():
    return make_units_schema((TextSpan(1659, 1678, TEXT, 'speech', 'sentence', 'speech_0136'),), ())


def piece(end):
    return dict(text_end=end, semantic_reason=TEXT, facts=dict(subject=None, action_or_state=None,
        setting=None, quantity=None, negation=None, relation_or_order=None,
        context_sources=[], resolved_references=[]))


def parsed(value):
    return parse_completed_response(dict(model='qwen3:8b', done=True, response=json.dumps(value, ensure_ascii=False)),
        schema=schema(), request_id='units_batch_0017_initial', evidence_paths=[])


def test_required_terminal_part_restores_exact_original_end():
    assert parsed({'speech_0136': dict(leading_parts=[], final_part=piece(1678))}) == {'speech_0136': [piece(1678)]}


def test_internal_subdivision_preserves_both_pieces_and_terminal():
    value = {'speech_0136': dict(leading_parts=[piece(1665)], final_part=piece(1678))}
    assert parsed(value) == {'speech_0136': [piece(1665), piece(1678)]}


@pytest.mark.parametrize('change', ['wrong_end', 'missing_final', 'bool_end', 'leading_at_end', 'unknown'])
def test_new_terminal_wire_refuses_partial_or_malformed_coverage(change):
    value = {'speech_0136': dict(leading_parts=[], final_part=piece(1678))}
    item = value['speech_0136']
    if change == 'wrong_end': item['final_part']['text_end'] = 1665
    elif change == 'missing_final': del item['final_part']
    elif change == 'bool_end': item['final_part']['text_end'] = True
    elif change == 'leading_at_end': item['leading_parts'] = [piece(1678)]
    elif change == 'unknown': item['unexpected'] = 1
    with pytest.raises(OllamaFormatError): parsed(value)


def test_actual_failure_offset_cannot_satisfy_new_generation_grammar():
    from video_ai.adapters.ollama import _response_schema_check
    wire = ollama_schema(schema(), units_coverage=True)
    with pytest.raises(ValueError):
        _response_schema_check({'speech_0136': dict(leading_parts=[], final_part=piece(1665))}, wire)
    _response_schema_check({'speech_0136': dict(leading_parts=[], final_part=piece(1678))}, wire)


def test_legacy_saved_response_restores_without_rewriting_its_offsets():
    # Legacy invalid completion remains invalid to the caller; never extend it.
    assert parsed({'speech_0136': [piece(1665)]}) == {'speech_0136': [piece(1665)]}
    assert parsed({'speech_0136': [piece(1678)]}) == {'speech_0136': [piece(1678)]}


def test_single_character_has_no_leading_piece_and_required_terminal():
    from video_ai.adapters.ollama import _response_schema_check
    one = make_units_schema((TextSpan(0, 1, '甲', 'speech', 'none', 'speech_0001'),), ())
    wire = ollama_schema(one, units_coverage=True)
    value = {'speech_0001': dict(leading_parts=[], final_part=piece(1))}
    _response_schema_check(value, wire)
    bad = deepcopy(value)
    bad['speech_0001']['leading_parts'] = [piece(1)]
    with pytest.raises(ValueError): _response_schema_check(bad, wire)


def test_unrelated_planner_schema_keeps_original_transport():
    unrelated = dict(type='object', properties=dict(x=dict(type='integer')), required=['x'], additionalProperties=False)
    assert ollama_schema(unrelated, units_coverage=True) == unrelated


def test_five_digit_candidate_keeps_mandatory_terminal_coverage():
    from video_ai.adapters.ollama import _response_schema_check
    source = make_units_schema((TextSpan(0, 2, '甲。', 'speech', 'sentence', 'speech_10000'),), ())
    wire = ollama_schema(source, units_coverage=True)
    _response_schema_check({'speech_10000': dict(leading_parts=[], final_part=piece(2))}, wire)
    with pytest.raises(ValueError):
        _response_schema_check({'speech_10000': dict(leading_parts=[], final_part=piece(1))}, wire)
