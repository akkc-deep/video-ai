"""Pure validation of author supplied, lossless single visual speech spans."""
from datetime import datetime, timezone

from .segments import TextSpan, segment_text, validate_segments
from .storyboard import _schema_check, _object, _array, _source_references


def reviewed_timestamp(value):
    if not isinstance(value, str): raise ValueError('review timestamp required')
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp > datetime.now(timezone.utc):
        raise ValueError('review timestamp must be timezone aware and not future')


def _keys(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError('missing/unknown author review fields')


def _text(value):
    if not isinstance(value, str) or not value.strip(): raise ValueError('nonempty author text required')


def validate_reviewed_spans(text, review) -> tuple[TextSpan, ...]:
    """Allow refinements of existing spans; never merge, rewrite or omit text."""
    _keys(review,'schema_version script_identity review_method reviewer reviewed_at verdict reason spans')
    if type(review['schema_version']) is not int or review['schema_version'] != 1:
        raise ValueError('unsupported unit review schema')
    if type(review['review_method']) is not str or review['review_method'] not in {'human_text','agent_source'} or review['verdict'] != 'passed':
        raise ValueError('passed human/source text review required')
    reviewed_timestamp(review['reviewed_at']); _text(review['reviewer']); _text(review['reason'])
    if not isinstance(review['spans'], list): raise ValueError('reviewed span list required')
    canonical = segment_text(text); spans=[]
    for item in review['spans']:
        _keys(item,'unit_id kind text_start text_end text single_visual_semantics verdict reason context_sources resolved_references')
        if type(item['text_start']) is not int or type(item['text_end']) is not int:
            raise ValueError('integer original text bounds required')
        containers=[s for s in canonical if s.start <= item['text_start'] < item['text_end'] <= s.end]
        if len(containers)!=1: raise ValueError('review cannot merge original boundaries')
        base=containers[0]
        if base.kind=='skip' and (item['text_start'],item['text_end'])!=(base.start,base.end):
            raise ValueError('original skipped boundary must be preserved')
        if item['verdict']!='passed': raise ValueError('every original span needs passed review')
        if item['kind']=='speech':
            if item['single_visual_semantics'] is not True: raise ValueError('single visual semantics must be explicitly true')
        elif item['kind']=='skip':
            if item['single_visual_semantics'] is not None or item['unit_id'] is not None:
                raise ValueError('skip semantics/ID must be null')
        else: raise ValueError('unsupported span kind')
        _text(item['reason'])
        spans.append(TextSpan(item['text_start'],item['text_end'],item['text'],item['kind'],
            base.boundary if item['text_end']==base.end else 'phrase',item['unit_id']))
    result=tuple(spans); validate_segments(text,result)
    if not any(s.kind=='speech' for s in result): raise ValueError('review has no speech')
    catalog={s.unit_id:dict(unit_id=s.unit_id,text_start=s.start,text_end=s.end,text=s.text) for s in result if s.kind=='speech'}
    string=dict(type='string',minLength=1)
    support=_object(dict(unit_id=string,text_start=dict(type='integer'),text_end=dict(type='integer'),source_quote=string))
    reference=_object(dict(reference_quote=string,resolved_subject=string,
        context_source_indices=_array(dict(type='integer',minimum=0),minItems=1,uniqueItems=True)))
    for item in review['spans']:
        _schema_check(item['context_sources'],_array(support),'context_sources')
        _schema_check(item['resolved_references'],_array(reference),'resolved_references')
        if any(s['unit_id'] not in catalog for s in item['context_sources']): raise ValueError('unknown context source')
        _source_references(item,item['text'],catalog)
    return result
