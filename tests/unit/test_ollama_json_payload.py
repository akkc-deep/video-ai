"""Grounded wire strings must keep their anchor inside a safe JSON payload."""
from copy import deepcopy
import json
import re

import pytest

from video_ai.adapters.ollama import ollama_schema
from video_ai.planning.storyboard import _anchored_string


def schema_for(subject, *, video=False):
    facts=dict(subject=subject,action_or_state=None,setting=None,quantity=None,negation=None,relation_or_order=None)
    return _anchored_string(facts,video=video)


@pytest.mark.parametrize('subject',[
    'TEST ONLY spacecraft',
    'TEST ONLY 银白 (probe) [x]+? # with "windows" and C:\\bay',
    'TEST ONLY first\nsecond\rthird\tfourth\x00',
])
@pytest.mark.parametrize('video',[False,True])
def test_wire_enforces_full_anchor_and_camera_on_serialized_json(subject,video):
    schema=schema_for(subject,video=video); before=deepcopy(schema)
    wire=ollama_schema(schema)
    pattern=wire.get('pattern')
    assert pattern is not None, 'grounded wire constraint must not be dropped'
    value=subject+'. Visible "probe" at C:\\bay.\n银白'+(' Camera path: slow right pan.' if video else '')
    payload=json.dumps(value,ensure_ascii=False)[1:-1]
    assert re.fullmatch(pattern,payload)
    assert not re.fullmatch(pattern,json.dumps('Unrelated presentation.')[1:-1])
    if video:
        assert not re.fullmatch(pattern,json.dumps(subject+'. Visible probe. Camera path: invalid orbit.')[1:-1])
    assert schema == before


@pytest.mark.parametrize('invalid_tail',[
    'Visible " + "concatenation',
    'Visible\nraw newline',
    'Visible\x00raw control',
    r'Visible\qbad escape',
    'Visible\\',
    '',
    ' begins with a space',
])
def test_wire_rejects_observed_concat_and_invalid_json_payload(invalid_tail):
    pattern=ollama_schema(schema_for('TEST ONLY source')).get('pattern')
    assert pattern is not None, 'grounded wire constraint must not be dropped'
    assert not re.fullmatch(pattern,'TEST ONLY source. '+invalid_tail)


@pytest.mark.parametrize('pattern',['^.*$','^A.*$','^A[^ \\t\\r\\n].* unexpected$','^A|B[^ \\t\\r\\n].*$'])
def test_unrecognized_patterns_use_normal_json_string_rule(pattern):
    assert 'pattern' not in ollama_schema(dict(type='string',pattern=pattern))


def test_video_wire_rejects_observed_unbounded_repetition():
    schema=schema_for('TEST ONLY source',video=True)
    value='TEST ONLY source. Camera path: static camera. '+('The probe continues forward. '*100)+' Camera path: static camera.'
    # Canonical remains unchanged: this is a generation budget, not a source
    # fact limit or a repair of the returned string.
    assert re.fullmatch(schema['pattern'],value)
    assert not re.fullmatch(ollama_schema(schema)['pattern'],json.dumps(value)[1:-1])


@pytest.mark.parametrize('subject',[
    'TEST ONLY source',
    'TEST ONLY '+('long source fact '*40)+'银白 (probe) [x]+? "windows" C:\\bay',
])
@pytest.mark.parametrize('presentation',[
    'V'+('x'*159),
    'V'+('"\\\t银'*39)+'end',
])
def test_video_budget_preserves_full_long_anchor_and_json_escapes(subject,presentation):
    schema=schema_for(subject,video=True);before=deepcopy(schema)
    pattern=ollama_schema(schema)['pattern']
    value=subject+'. '+presentation+' Camera path: slow left pan.'
    assert re.fullmatch(pattern,json.dumps(value,ensure_ascii=False)[1:-1])
    assert re.fullmatch(schema['pattern'],value)
    assert schema==before
    overlong=subject+'. '+('V'*161)+' Camera path: slow left pan.'
    assert not re.fullmatch(pattern,json.dumps(overlong,ensure_ascii=False)[1:-1])


def test_video_budget_does_not_limit_nonvideo_grounded_fields():
    value='TEST ONLY source. '+('Visible probe. '*100)
    assert re.fullmatch(ollama_schema(schema_for('TEST ONLY source'))['pattern'],json.dumps(value)[1:-1])
