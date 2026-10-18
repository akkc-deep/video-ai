from copy import deepcopy
from datetime import datetime, timezone
import pytest


def review_for(text, spans=None):
    from video_ai.planning.segments import segment_text
    from video_ai.runtime.manifest import now
    spans = segment_text(text) if spans is None else spans
    return dict(schema_version=1, script_identity={}, review_method='agent_source', reviewer='TEST ONLY',
        reviewed_at=now(), verdict='passed', reason='Original visual semantics checked',
        spans=[dict(unit_id=s.unit_id, kind=s.kind, text_start=s.start, text_end=s.end, text=s.text,
            single_visual_semantics=True if s.kind=='speech' else None, verdict='passed', reason='One visual meaning',
            context_sources=[], resolved_references=[]) for s in spans])


def test_review_allows_explicit_finer_phrase_boundary():
    from video_ai.planning import speech_semantics as s
    from video_ai.planning.segments import TextSpan
    text='红鸟飞过蓝湖。\n'
    spans=(TextSpan(0,4,text[:4],'speech','phrase','speech_0001'),
        TextSpan(4,7,text[4:7],'speech','sentence','speech_0002'),TextSpan(7,8,'\n','skip','newline',None))
    assert s.validate_reviewed_spans(text,review_for(text,spans)) == spans


@pytest.mark.parametrize('bad',['missing_semantics','false_semantics','merge','rewrite','skip_body','unit_id','unknown','future','context','reference'])
def test_review_refuses_forged_or_inexact_spans(bad):
    from video_ai.planning import speech_semantics as s
    text='一只鸟，另一只鸟。'
    r=review_for(text)
    if bad=='missing_semantics':r['spans'][0].pop('single_visual_semantics')
    if bad=='false_semantics':r['spans'][0]['single_visual_semantics']=1
    if bad=='merge':r['spans']=[dict(r['spans'][0],text=text,text_end=len(text))]
    if bad=='rewrite':r['spans'][0]['text']='两只鸟，'
    if bad=='skip_body':r['spans'][0].update(kind='skip',unit_id=None,single_visual_semantics=None)
    if bad=='unit_id':r['spans'][0]['unit_id']='speech_0002'
    if bad=='unknown':r['extra']=False
    if bad=='future':r['reviewed_at']='2999-01-01T00:00:00+00:00'
    if bad=='context':r['spans'][1]['context_sources']=[dict(unit_id='speech_0001',text_start=0,text_end=4,source_quote='假话')]
    if bad=='reference':r['spans'][1]['resolved_references']=[dict(reference_quote='它',resolved_subject='bird',context_source_indices=[0])]
    with pytest.raises(ValueError):s.validate_reviewed_spans(text,r)


def test_original_context_reference_objects_are_validated():
    from video_ai.planning import speech_semantics as s
    text='红鸟，它飞走。'
    r=review_for(text)
    r['spans'][1]['context_sources']=[dict(unit_id='speech_0001',text_start=0,text_end=2,source_quote='红鸟')]
    r['spans'][1]['resolved_references']=[dict(reference_quote='它',resolved_subject='红鸟',context_source_indices=[0])]
    assert len(s.validate_reviewed_spans(text,r))==2
