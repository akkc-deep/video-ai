from dataclasses import replace
import pytest
from test_timeline import make

TEXT = '夜色渐渐安静下来，微风轻轻吹过树梢。\r\n远处的灯光映在水面上，随着细小的波纹轻轻摇动。\n我们沿着安静的小路慢慢前行，听见脚步声，也听见夜风穿过枝叶。\n'


def real_timeline(fps=16):
    return make(TEXT, [106560,39360,141120,156480,164160,81600,133440], fps)


def timing_for(t, start=1200, end_margin=1200, uncertainty=200):
    from video_ai.planning.storyboard import SpeechTimingEvidence, UnitTiming, SemanticCue
    units=tuple(UnitTiming(c.unit_id,start,c.samples-end_margin,uncertainty,(), 'passed','passed') for c in t.clips)
    cues=tuple(SemanticCue(f'cue_{i:04d}',a.unit_id,b.unit_id,b.start_sample+start,'passed')
               for i,(a,b) in enumerate(zip(t.clips,t.clips[1:]),1))
    return SpeechTimingEvidence(units,cues)


def test_pcm_candidate_cells_are_not_verified_cues():
    from video_ai.planning.storyboard import plan_slots, validate_slots
    t=real_timeline(); slots=plan_slots(t)
    assert [(s.start_frame,s.end_frame) for s in slots]==[(0,68),(68,113),(113,160),(160,244),(244,299),(299,326),(326,419)]
    validate_slots(t,slots)
    assert all(b.spoken_overlap_samples is None and not b.silence_only for s in slots for b in s.bindings)
    for c in t.clips:
        intervals=[(b.start_sample,b.end_sample) for s in slots for b in s.bindings if b.unit_id==c.unit_id]
        assert intervals[0][0]==c.start_sample and intervals[-1][1]==c.end_sample
        assert all(a[1]==b[0] for a,b in zip(intervals,intervals[1:]))
    assert sum(b.end_sample-b.start_sample for s in slots for b in s.bindings)==822720


def test_verified_onset_moves_cut_without_changing_timeline():
    from video_ai.planning.storyboard import plan_slots
    t=real_timeline(); before=t.as_dict(); timing=timing_for(t,start=3000)
    slots=plan_slots(t,timing=timing)
    assert slots[0].end_frame==69 and slots[1].end_frame==114
    assert t.as_dict()==before
    assert any(b.quantization_edge for s in slots for b in s.bindings)


def test_silence_plus_subframe_voice_retains_binding():
    from video_ai.planning.storyboard import plan_slots
    t=make('甲，乙。',[48000,48000]); timing=timing_for(t,start=11000)
    slots=plan_slots(t,timing=timing)
    other=next(b for b in slots[0].bindings if b.unit_id=='speech_0002')
    assert other.end_sample-other.start_sample>3000
    assert other.quantization_edge and 0<other.spoken_overlap_samples<=3000
    silent=plan_slots(t,timing=timing_for(t,start=10000))[0].bindings[-1]
    assert silent.silence_only and silent.spoken_overlap_samples==0


@pytest.mark.parametrize('fps',[16,24])
def test_uncertainty_and_quantization_share_one_frame(fps):
    from video_ai.planning.storyboard import plan_slots
    t=real_timeline(fps); timing=timing_for(t,start=3000,end_margin=3000,uncertainty=2500)
    with pytest.raises(ValueError,match='one frame'): plan_slots(t,timing=timing)


@pytest.mark.parametrize('bad',['missing','cue','order','bool','verdict','semantic','silence','uncertainty'])
def test_invalid_timing_rejected(bad):
    from video_ai.planning.storyboard import plan_slots
    t=real_timeline(); timing=timing_for(t)
    u=timing.units[0]
    if bad=='missing': timing=replace(timing,units=timing.units[1:])
    if bad=='cue': timing=replace(timing,cues=timing.cues[1:])
    if bad=='order': timing=replace(timing,units=tuple(reversed(timing.units)))
    if bad=='bool': u=replace(u,spoken_start_sample=True)
    if bad=='verdict': u=replace(u,verdict='unverified')
    if bad=='semantic': u=replace(u,semantic_unit_verdict='failed')
    if bad=='silence': u=replace(u,verified_internal_silences=((1300,2000),(1800,2100)))
    if bad=='uncertainty': u=replace(u,boundary_uncertainty_samples=1300)
    if bad not in ('missing','cue','order'):timing=replace(timing,units=(u,*timing.units[1:]))
    with pytest.raises(ValueError):plan_slots(t,timing=timing)


def test_long_unit_splits_without_repeating_audio_and_micro_cell_refused():
    from video_ai.config import TimelineSettings
    from video_ai.planning.storyboard import plan_slots, UnsupportedSemanticTimingError, validate_slots
    t=make('长句。',[480000],settings=TimelineSettings(0,0,0,0)); slots=plan_slots(t)
    assert [(s.start_frame,s.end_frame) for s in slots]==[(0,80),(80,160)]
    validate_slots(t,slots)
    with pytest.raises(UnsupportedSemanticTimingError):plan_slots(make('甲，乙。',[1,3000],settings=TimelineSettings(0,0,0,0)))
    with pytest.raises(ValueError):validate_slots(t,(replace(slots[0],start_frame=True),slots[1]))


from storyboard_helpers import content_for


def test_schema_cannot_change_binding_identity():
    from video_ai.planning.storyboard import plan_slots,make_model_schema,validate_model_content
    slots=plan_slots(real_timeline()); good=content_for(slots)
    validate_model_content(good,slots)
    schema=make_model_schema(slots)
    assert schema['additionalProperties'] is False
    for mutate in [lambda c:c['shots'][0].update(text='changed'),lambda c:c['shots'][0].update(shot_id='shot_0002'),
                   lambda c:c['shots'].pop(),lambda c:c.update(schema_version=True)]:
        import copy
        bad=copy.deepcopy(good); mutate(bad)
        with pytest.raises(ValueError):validate_model_content(bad,slots)


def test_context_reference_to_previous_reflection():
    from video_ai.planning.storyboard import plan_slots,validate_model_content
    slots=plan_slots(real_timeline()); content=content_for(slots)
    r=next(r for r in content['shots'][3]['visual_requirements'] if r['unit_id']=='speech_0004')
    r['subject']='灯光倒影'; r['context_sources']=[dict(unit_id='speech_0003',text_start=20,text_end=31,source_quote='远处的灯光映在水面上，')]
    # Independent original character offsets are 20..31.
    assert TEXT[20:31]=='远处的灯光映在水面上，'
    r['resolved_references']=[dict(reference_quote='摇动',resolved_subject='灯光倒影',context_source_indices=[0])]
    validate_model_content(content,slots)
    r['context_sources'][0]['text_start']=21
    with pytest.raises(ValueError):validate_model_content(content,slots)


def test_requirements_fix_binding_order_and_full_original_quotes():
    from video_ai.planning.storyboard import plan_slots,make_model_schema
    slots=plan_slots(real_timeline());schema=make_model_schema(slots)
    for shot,slot in zip(schema['properties']['shots']['prefixItems'],slots):
        requirements=shot['properties']['visual_requirements']
        expected=[b for b in slot.bindings if not b.silence_only]
        assert requirements['minItems']==requirements['maxItems']==len(expected)
        for item,binding in zip(requirements['prefixItems'],expected):
            assert item['properties']['unit_id']['const']==binding.unit_id
            assert item['properties']['source_quote']['const']==binding.text


@pytest.mark.parametrize('bad',['bool_index','duplicate_index','no_binding','quantity','negation','finer','quote','entity'])
def test_quantity_negation_and_finer_audio_contract(bad):
    from video_ai.planning.storyboard import plan_slots,validate_model_content,UnsupportedSemanticTimingError
    slots=plan_slots(real_timeline()); c=content_for(slots); r=c['shots'][0]['visual_requirements'][0]
    if bad=='no_binding':c['shots'][0]['visual_requirements']=[]
    if bad=='quantity':r['quantity']=2
    if bad=='negation':r['negation']=''
    if bad=='finer':r['needs_finer_audio']=True
    if bad=='quote':r['source_quote']='飞船'
    if bad=='entity':c['shots'][0]['entity_ids']=['invented']
    if bad in ('bool_index','duplicate_index'):
        r['context_sources']=[dict(unit_id='speech_0001',text_start=0,text_end=9,source_quote='夜色渐渐安静下来，')]
        r['resolved_references']=[dict(reference_quote='夜色',resolved_subject='夜色',context_source_indices=[True] if bad=='bool_index' else [0,0])]
    with pytest.raises(UnsupportedSemanticTimingError if bad=='finer' else ValueError,match='context_source_indices' if bad in ('bool_index','duplicate_index') else None):validate_model_content(c,slots)
