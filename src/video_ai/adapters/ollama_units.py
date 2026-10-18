"""Lossless production-unit wire codec with mandatory terminal coverage."""
from copy import deepcopy
import re


UNITS_COVERAGE_NOTE = (
    '\n\nUnit coverage transport v1 overrides the instruction to emit candidate arrays: '
    'for EACH fixed candidate key emit an object with leading_parts and final_part. '
    'leading_parts is [] unless the candidate needs subdivision; its text_end values '
    'are strictly increasing absolute offsets BEFORE candidate.end. final_part is '
    'mandatory and describes ALL remaining original text after those leading parts. '
    'Its text_end is the exact candidate.end fixed by the format const. Emit '
    'semantic_reason and facts for every part, including final_part. The decoder '
    'concatenates leading_parts + [final_part] into the canonical proposal array. '
    'Do not omit the terminal part, repeat an endpoint, rewrite text or invent facts.'
)


def project_units_schema(schema):
    """Recognize only the exact production-unit schema, never arbitrary arrays."""
    if (not isinstance(schema, dict) or set(schema) != {'type', 'properties', 'required', 'additionalProperties'}
            or schema['type'] != 'object' or schema['additionalProperties'] is not False):
        return None
    props = schema['properties']
    if (not isinstance(props, dict) or not 1 <= len(props) <= 8
            or schema['required'] != list(props)
            or any(not isinstance(key, str) or re.fullmatch(r'speech_(?:[0-9]{4}|[1-9][0-9]{4,})', key) is None for key in props)):
        return None
    from ..planning.production_units import _facts_schema
    result = deepcopy(schema)
    for key, array in props.items():
        if (not isinstance(array, dict) or set(array) != {'type', 'items', 'minItems'}
                or array['type'] != 'array' or type(array['minItems']) is not int or array['minItems'] != 1):
            return None
        item = array['items']
        if (not isinstance(item, dict) or set(item) != {'type', 'properties', 'required', 'additionalProperties'}
                or item['type'] != 'object' or item['additionalProperties'] is not False
                or item['required'] != ['text_end', 'semantic_reason', 'facts']
                or set(item['properties']) != {'text_end', 'semantic_reason', 'facts'}):
            return None
        fields = item['properties']
        end = fields['text_end']
        if (not isinstance(end, dict) or set(end) != {'type', 'minimum', 'maximum'}
                or end['type'] != 'integer' or type(end['minimum']) is not int or type(end['maximum']) is not int
                or not 1 <= end['minimum'] <= end['maximum']
                or fields['semantic_reason'] != dict(type='string', minLength=1)
                or fields['facts'] != _facts_schema()):
            return None
        leading, final = deepcopy(item), deepcopy(item)
        if end['maximum'] > end['minimum']:
            leading['properties']['text_end']['maximum'] = end['maximum'] - 1
        final['properties']['text_end'] = dict(type='integer', const=end['maximum'])
        result['properties'][key] = dict(type='object', properties=dict(
            leading_parts=dict(type='array', items=leading, minItems=0,
                               maxItems=end['maximum'] - end['minimum']),
            final_part=final), required=['leading_parts', 'final_part'], additionalProperties=False)
    return result


def restore_units_content(value, schema, validate):
    wire = project_units_schema(schema)
    if wire is None:
        return None
    if not isinstance(value, dict) or set(value) != set(schema['properties']):
        raise ValueError('missing/unknown unit coverage candidate keys')
    # Original frozen responses retain their exact original arrays and offsets.
    if all(isinstance(item, list) for item in value.values()):
        return deepcopy(value)
    if not all(isinstance(item, dict) for item in value.values()):
        raise ValueError('mixed legacy and terminal unit coverage transport')
    validate(value, wire)
    return {key: deepcopy(value[key]['leading_parts'] + [value[key]['final_part']])
            for key in schema['properties']}
