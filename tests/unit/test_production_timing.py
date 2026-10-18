"""Automatic estimated cuts preserve every real PCM sample."""
from dataclasses import replace

import pytest

from video_ai.config import TimelineSettings
from video_ai.media.timing import EnvelopeEstimate
from video_ai.planning.segments import SegmentedScript, segment_text
from video_ai.runtime.production_state import ArtifactStamp


def timeline(samples, text='甲，乙。'):
    from video_ai.planning.production_timeline import ProductionAudioInfo, build_production_timeline
    script = SegmentedScript(text, False, segment_text(text))
    infos = {s.unit_id:ProductionAudioInfo(ArtifactStamp('D:/pcm.wav', n*2+44, 123),48000,1,2,n) for s,n in zip(script.spans,samples)}
    return build_production_timeline(script, infos, settings=TimelineSettings(0,0,0,0))


def estimate(n, start=0, end=None, uncertainty=0, silences=()):
    end = n if end is None else end
    return EnvelopeEstimate(1, 'pcm_envelope_v1', n, 200, (1,2,4,8), ((start,end),)*4, 240, start, end, uncertainty, silences)


@pytest.mark.parametrize('uncertainty,frame,basis,error', [(2100,2,'pcm_envelope',48000), (2101,1,'pcm_start',48016)])
def test_threshold_and_pcm_start_fallback(uncertainty, frame, basis, error):
    from video_ai.planning.production_timing import build_automatic_slots, validate_automatic_slots
    t = timeline([3000, 9000])
    estimates = {'speech_0001':estimate(3000), 'speech_0002':estimate(9000,2100,uncertainty=uncertainty)}
    p = build_automatic_slots(t, estimates)
    assert [(s.start_frame,s.end_frame) for s in p.slots] == [(0,frame), (frame,4)]
    assert p.cuts[0].as_dict() == {'from_unit_id':'speech_0001', 'to_unit_id':'speech_0002', 'cue_sample':5100, 'frame':frame, 'uncertainty_samples':uncertainty, 'error_numerator':error, 'basis':basis, 'alignment_claim':'estimated'}
    validate_automatic_slots(t, p, estimates)


def test_quantization_edge_keeps_complete_foreign_pcm_and_silence():
    from video_ai.planning.production_timing import build_automatic_slots
    t = timeline([4500, 7500])
    p = build_automatic_slots(t, {'speech_0001':estimate(4500), 'speech_0002':estimate(7500,1500)})
    assert [(s.start_frame,s.end_frame,s.primary_unit_id) for s in p.slots] == [(0,2,'speech_0001'),(2,4,'speech_0002')]
    assert [(b.unit_id,b.start_sample,b.end_sample,b.quantization_edge,b.silence_only,b.spoken_overlap_samples) for b in p.slots[0].bindings] == [('speech_0001',0,4500,False,False,4500), ('speech_0002',4500,6000,False,True,0)]
    assert [(b.unit_id,b.start_sample,b.end_sample) for b in p.slots[1].bindings] == [('speech_0002',6000,12000)]


def test_non_silent_quantization_edge_within_one_frame():
    from video_ai.planning.production_timing import build_automatic_slots
    t = timeline([4500,7500])
    p = build_automatic_slots(t, {'speech_0001':estimate(4500), 'speech_0002':estimate(7500)})
    edge = p.slots[0].bindings[1]
    assert (edge.start_sample,edge.end_sample,edge.quantization_edge,edge.spoken_overlap_samples) == (4500,6000,True,1500)


def test_long_slot_subdivision_literal_edges_and_full_pcm():
    from video_ai.planning.production_timing import AutomaticSlotPlan, build_automatic_slots
    t = timeline([624001], '长句。')
    p = build_automatic_slots(t, {'speech_0001':estimate(624001)})
    assert [(s.shot_id,s.start_frame,s.end_frame) for s in p.slots] == [('shot_0001',0,69),('shot_0002',69,139),('shot_0003',139,209)]
    assert [(s.bindings[0].start_sample,s.bindings[0].end_sample) for s in p.slots] == [(0,207000),(207000,417000),(417000,624001)]
    assert all(s.primary_unit_id == 'speech_0001' for s in p.slots)
    assert p.cuts == ()
    assert AutomaticSlotPlan.from_dict(p.as_dict()) == p


def test_verified_internal_silence_excluded_from_spoken_overlap_only():
    from video_ai.planning.production_timing import build_automatic_slots
    t = timeline([12000], '长句。')
    p = build_automatic_slots(t, {'speech_0001':estimate(12000,silences=((3000,6000),))})
    assert (p.slots[0].bindings[0].start_sample,p.slots[0].bindings[0].end_sample,p.slots[0].bindings[0].spoken_overlap_samples) == (0,12000,9000)


@pytest.mark.parametrize('change', ['missing', 'extra', 'samples', 'onset_bool', 'range', 'silence_order'])
def test_malformed_estimate_coverage_and_values_rejected(change):
    from video_ai.planning.production_timing import build_automatic_slots
    t = timeline([6000,6000])
    estimates = {'speech_0001':estimate(6000), 'speech_0002':estimate(6000)}
    if change == 'missing': del estimates['speech_0002']
    elif change == 'extra': estimates['other'] = estimate(6000)
    elif change == 'samples': estimates['speech_0002'] = estimate(9000)
    elif change == 'onset_bool': estimates['speech_0002'] = replace(estimate(6000),spoken_start_sample=True)
    elif change == 'range': estimates['speech_0002'] = replace(estimate(6000),spoken_end_sample=6001)
    else: estimates['speech_0002'] = estimate(6000,silences=((3000,4000),(2000,2500)))
    with pytest.raises(ValueError): build_automatic_slots(t, estimates)


def test_nonpositive_cell_and_nonpositive_fallback_rejected():
    from video_ai.planning.production_timing import build_automatic_slots
    t = timeline([1,6000])
    with pytest.raises(ValueError): build_automatic_slots(t, {'speech_0001':estimate(1), 'speech_0002':estimate(6000)})
    t = timeline([100,12000])
    with pytest.raises(ValueError): build_automatic_slots(t, {'speech_0001':estimate(100), 'speech_0002':estimate(12000,6000,uncertainty=6000)})


@pytest.mark.parametrize('change', ['cut_frame','alignment','binding_bool','gap','unknown'])
def test_tampered_plan_rejected(change):
    from video_ai.planning.production_timing import AutomaticSlotPlan, build_automatic_slots, validate_automatic_slots
    t = timeline([6000,6000])
    estimates = {'speech_0001':estimate(6000),'speech_0002':estimate(6000)}
    data = build_automatic_slots(t,estimates).as_dict()
    if change == 'cut_frame': data['cuts'][0]['frame'] = 3
    elif change == 'alignment': data['cuts'][0]['alignment_claim'] = 'passed'
    elif change == 'binding_bool': data['slots'][0]['bindings'][0]['start_sample'] = False
    elif change == 'gap': data['slots'][1]['start_frame'] = 3
    else: data['slots'][0]['unexpected'] = 0
    with pytest.raises(ValueError):
        p = AutomaticSlotPlan.from_dict(data)
        validate_automatic_slots(t,p,estimates)


@pytest.mark.parametrize('target,field,value', [
    ('slot','start_frame',False), ('binding','spoken_overlap_samples',float('nan')),
    ('binding','silence_only',0), ('cut','frame',True), ('cut','alignment_claim','passed'),
    ('cut','basis','human_audio'),
])
def test_plan_parser_rejects_non_json_types_and_invalid_claims(target, field, value):
    from video_ai.planning.production_timing import AutomaticSlotPlan, build_automatic_slots
    t = timeline([6000,6000])
    data = build_automatic_slots(t, {'speech_0001':estimate(6000),'speech_0002':estimate(6000)}).as_dict()
    item = {'slot':data['slots'][0], 'binding':data['slots'][0]['bindings'][0], 'cut':data['cuts'][0]}[target]
    item[field] = value
    with pytest.raises(ValueError): AutomaticSlotPlan.from_dict(data)
