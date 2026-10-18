"""Lossless scene grouping and provenance using actual PCM timelines."""
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json

import pytest

from video_ai.config import TimelineSettings
from video_ai.planning.production_timeline import ProductionAudioInfo, build_production_timeline
from video_ai.planning.segments import SegmentedScript, segment_text
from video_ai.runtime.production_state import ArtifactStamp


def scene_inputs(text='湖面很静。白鸟停在石上。它望向远处。\r\n\r\n它飞走了。', samples=None, pauses=True):
    script = SegmentedScript(text, True, segment_text(text))
    speech = [s for s in script.spans if s.kind == 'speech']
    samples = samples or [4501, 7502, 9901, 6103][:len(speech)]
    audio = {s.unit_id: ProductionAudioInfo(ArtifactStamp('D:/pcm.wav', n*2+44, 123), 48000, 1, 2, n)
             for s, n in zip(speech, samples)}
    timeline = build_production_timeline(script, audio, settings=TimelineSettings(0.02, 0.04, 0.03, 0.01) if pauses else TimelineSettings(0, 0, 0, 0))
    units = dict(decoded_text=text, has_bom=True, spans=[asdict(s) for s in script.spans],
                 semantic_specs={s.unit_id: dict(semantic_reason='source', facts={}, interpretation_method='automated_source') for s in speech}, planner={})
    return script, units, timeline


def scene_proposal():
    group = dict(key='lake', label='湖畔', environment='湖和石头', time='清晨', lighting='柔光', spatial_relations=[], source_facts=[], creative_choices=[], change_sources=[])
    entity = dict(key='bird', label='白鸟', fixed_attributes=['白色羽毛'], source_facts=[], creative_choices=[])
    def scene(paragraph, ids):
        return dict(paragraph_id=paragraph, unit_ids=ids, summary='白鸟在湖边', image_prompt='白鸟立于湖边石上', motion_prompt='白鸟轻轻转头', entity_ids=['bird'], variant_ids=[], scene_group_id='lake', change_sources=[])
    return dict(global_style=dict(description='写实自然光', source_facts=[], creative_choices=[]), entities=[entity], appearance_variants=[], scene_groups=[group], scenes=[scene('paragraph_0001', ['speech_0001','speech_0002']),scene('paragraph_0001',['speech_0003']),scene('paragraph_0003',['speech_0004'])])


def build(script=None, units=None, timeline=None, proposal=None, settings=None):
    from video_ai.config import ScenePlanningSettings
    from video_ai.planning.production_scenes import build_scene_plan
    if script is None: script, units, timeline = scene_inputs()
    return build_scene_plan(script, units, timeline, proposal or scene_proposal(), settings=settings or ScenePlanningSettings())


def test_multisentence_semantics_cover_original_pcm_and_baseline_uses():
    script, units, timeline = scene_inputs()
    bible, plan = build(script, units, timeline)
    assert plan['paragraphs'] == [dict(paragraph_id='paragraph_0001', text_start=0,text_end=20,unit_ids=['speech_0001','speech_0002','speech_0003']), dict(paragraph_id='paragraph_0002',text_start=20,text_end=22,unit_ids=[]),dict(paragraph_id='paragraph_0003',text_start=22,text_end=27,unit_ids=['speech_0004'])]
    assert plan['scenes'][0]['unit_ids'] == ['speech_0001','speech_0002']
    assert len(plan['scenes']) == 3
    assert plan['scenes'][0]['start_frame'] == 0
    assert plan['scenes'][-1]['end_frame'] == timeline.total_frames
    assert [s['end_frame'] for s in plan['scenes'][:-1]] == [s['start_frame'] for s in plan['scenes'][1:]]
    assert plan['batches'] == [['scene_0001'], ['scene_0002','scene_0003']]
    assert bible['baselines'] == [dict(kind='entity',id='entity_0001',scene_id='scene_0001'),dict(kind='scene_group',id='group_0001',scene_id='scene_0001')]
    assert plan['scenes'][1]['reference_bindings'] == [dict(source_scene_id='scene_0001',uses=[dict(kind='entity',id='entity_0001'),dict(kind='scene_group',id='group_0001')])]
    for clip in timeline.clips:
        bindings = [b for s in plan['scenes'] for b in s['bindings'] if b['unit_id']==clip.unit_id]
        assert bindings[0]['start_sample'] == clip.start_sample
        assert bindings[-1]['end_sample'] == clip.end_sample
        assert sum(b['end_sample']-b['start_sample'] for b in bindings) == clip.samples
        assert all(b['text']==clip.text for b in bindings)
    assert script.text == timeline.original_text == units['decoded_text']


def test_one_scene_for_three_sentences_and_mixed_newline_paragraphs():
    from video_ai.planning.production_scenes import paragraphs_from_script
    script = SegmentedScript('甲。\r\n\r乙。\n丙。',False,segment_text('甲。\r\n\r乙。\n丙。'))
    assert [(p['text_start'],p['text_end']) for p in paragraphs_from_script(script)] == [(0,4),(4,5),(5,8),(8,10)]
    proposal = scene_proposal()
    proposal['scenes'][0]['unit_ids'].append('speech_0003')
    del proposal['scenes'][1]
    assert len(build(proposal=proposal)[1]['scenes']) == 2


def test_identity_uses_bom_and_canonical_payload_excluding_api_wrapper():
    script, units, timeline = scene_inputs()
    bible, _ = build(script, units, timeline)
    assert bible['source_sha256'] == hashlib.sha256(b'\xef\xbb\xbf'+script.text.encode()).hexdigest()
    assert bible['units_sha256'] == hashlib.sha256(json.dumps(units,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    units.update(run_id='frozen-run',source_sha256='a'*64)
    identified, plan = build(script,units,timeline)
    assert identified['units_sha256'] == bible['units_sha256']
    assert identified['run_id'] == plan['run_id'] == 'frozen-run'
    assert identified['source_sha256'] == 'a'*64


@pytest.mark.parametrize('change',['missing','duplicate','reverse','cross_paragraph','unknown','unused','duplicate_key','extra','empty_prompt','too_many'])
def test_rejects_invalid_semantic_partition_and_proposal(change):
    proposal = scene_proposal()
    if change=='missing': proposal['scenes'][0]['unit_ids'].pop()
    elif change=='duplicate': proposal['scenes'][1]['unit_ids']=['speech_0002','speech_0003']
    elif change=='reverse': proposal['scenes'][0]['unit_ids'].reverse()
    elif change=='cross_paragraph': proposal['scenes'][1]['unit_ids'].append('speech_0004'); proposal['scenes'].pop()
    elif change=='unknown': proposal['scenes'][0]['entity_ids']=['missing']
    elif change=='unused': proposal['entities'].append(dict(proposal['entities'][0],key='unused'))
    elif change=='duplicate_key': proposal['entities'].append(deepcopy(proposal['entities'][0]))
    elif change=='extra': proposal['scenes'][0]['start_frame']=0
    elif change=='empty_prompt': proposal['scenes'][0]['motion_prompt']=' '
    else:
        from video_ai.config import ScenePlanningSettings
        with pytest.raises(ValueError,match='config|target|scene'): build(proposal=proposal,settings=ScenePlanningSettings(target_scenes_per_paragraph=1))
        return
    with pytest.raises(ValueError): build(proposal=proposal)


def source(script, unit):
    span = next(s for s in script.spans if s.unit_id==unit)
    return dict(unit_id=unit,text_start=span.start,text_end=span.end,quote=span.text)


@pytest.mark.parametrize('change',['quote','future_variant','future_group','missing_change','orphan_variant','fake_selection'])
def test_source_validation_and_change_evidence(change):
    script,units,timeline = scene_inputs()
    proposal=scene_proposal()
    variant=dict(key='coat',entity_key='bird',attributes=['红衣'],source_facts=[],creative_choices=[],change_sources=[source(script,'speech_0003')])
    proposal['appearance_variants']=[variant]
    proposal['scenes'][1]['variant_ids']=['coat']
    if change=='quote': proposal['entities'][0]['source_facts']=[dict(name='羽毛',value='白',sources=[dict(source(script,'speech_0002'),quote='wrong')])]
    elif change=='future_variant': variant['change_sources']=[source(script,'speech_0004')]
    elif change=='future_group':
        group=dict(proposal['scene_groups'][0],key='new',change_sources=[source(script,'speech_0004')]); proposal['scene_groups'].append(group);proposal['scenes'][1]['scene_group_id']='new'
    elif change=='missing_change':
        proposal['appearance_variants'].insert(0,dict(variant,key='plain',change_sources=[]));proposal['scenes'][0]['variant_ids']=['plain'];variant['change_sources']=[]
    elif change=='orphan_variant': proposal['scenes'][1]['entity_ids']=[]
    else: proposal['global_style']['creative_choices']=[dict(name='风格',value='写实',reason='用户已选此风格')]
    with pytest.raises(ValueError): build(script,units,timeline,proposal)


def test_valid_appearance_change_and_first_use_id_order():
    script,units,timeline=scene_inputs()
    proposal=scene_proposal()
    proposal['appearance_variants']=[dict(key='new',entity_key='bird',attributes=['展开羽翼'],source_facts=[],creative_choices=[],change_sources=[source(script,'speech_0003')]),dict(key='old',entity_key='bird',attributes=[],source_facts=[],creative_choices=[],change_sources=[])]
    proposal['scenes'][0]['variant_ids']=['old']
    proposal['scenes'][1]['variant_ids']=['new']
    bible,plan=build(script,units,timeline,proposal)
    assert [v['attributes'] for v in bible['appearance_variants']] == [[],['展开羽翼']]
    assert plan['scenes'][1]['variant_ids']==['variant_0002']


@pytest.mark.parametrize('kind',['variant','group'])
def test_first_use_cannot_display_future_clothing_or_location_fact(kind):
    script,units,timeline=scene_inputs('他穿白衣。忽然下雨。他换上红衣。',[9000,9000,9000],False)
    proposal=scene_proposal();proposal['scenes']=proposal['scenes'][:2]
    proposal['scenes'][0]['unit_ids']=['speech_0001']
    proposal['scenes'][1]['unit_ids']=['speech_0002','speech_0003']
    fact=dict(name='外观或地点',value='红衣或新地点',sources=[source(script,'speech_0003')])
    if kind=='variant':
        proposal['appearance_variants']=[dict(key='red',entity_key='bird',attributes=['红衣'],
                        source_facts=[fact],creative_choices=[],change_sources=[])]
        for row in proposal['scenes']: row['variant_ids']=['red']
    else: proposal['scene_groups'][0]['source_facts']=[fact]
    with pytest.raises(ValueError,match='future|source'): build(script,units,timeline,proposal)


def test_multiple_referenced_appearances_keep_each_fixed_baseline_use():
    proposal=scene_proposal()
    proposal['appearance_variants']=[dict(key=key,entity_key='bird',attributes=[],source_facts=[],creative_choices=[],change_sources=[]) for key in ('left','right')]
    for scene in proposal['scenes']: scene['variant_ids']=['left','right']
    bible,plan=build(proposal=proposal)
    assert len(bible['appearance_variants'])==2
    assert plan['scenes'][1]['reference_bindings'][0]['uses']==[dict(kind='entity',id='entity_0001'),dict(kind='appearance_variant',id='variant_0001'),dict(kind='appearance_variant',id='variant_0002'),dict(kind='scene_group',id='group_0001')]


@pytest.mark.parametrize('field,value',[('run_id',None),('source_sha256',None),('source_sha256','x'),('source_sha256',True)])
def test_supplied_identity_wrapper_is_strict(field,value):
    script,units,timeline=scene_inputs()
    units[field]=value
    with pytest.raises(ValueError): build(script,units,timeline)


@pytest.mark.parametrize('change',['bool','gap','text','batch','baseline','clip','digest','extra','binding_flag'])
def test_validator_rederives_all_fields_and_rejects_forgery(change):
    from video_ai.config import ScenePlanningSettings
    from video_ai.planning.production_scenes import validate_scene_plan
    script,units,timeline=scene_inputs(); bible,plan=build(script,units,timeline)
    if change=='bool': plan['scenes'][0]['start_frame']=False
    elif change=='gap': plan['scenes'][1]['bindings'][0]['start_sample']+=1
    elif change=='text': plan['scenes'][0]['bindings'][0]['text']='summary'
    elif change=='batch': plan['batches']=[['scene_0001','scene_0002','scene_0003']]
    elif change=='baseline': bible['baselines'][0]['scene_id']='scene_0002'
    elif change=='clip': plan['clips'][0]['retained_frames']+=1
    elif change=='digest': plan['units_sha256']='b'*64
    elif change=='extra': plan['passed']=True
    else: plan['scenes'][0]['bindings'][0]['semantic_member']=1
    with pytest.raises(ValueError): validate_scene_plan(script,units,timeline,bible,plan,settings=ScenePlanningSettings())


def test_invalid_timeline_and_units_do_not_get_planned():
    script,units,timeline=scene_inputs()
    with pytest.raises(ValueError): build(script,units,replace(timeline,total_samples=timeline.total_samples+1))
    units['spans'][0]['text']='rewritten'
    with pytest.raises(ValueError): build(script,units,timeline)


def test_collapsed_frame_cut_requires_merge_and_quantization_keeps_neighbor_pcm():
    proposal=scene_proposal();proposal['scenes']=proposal['scenes'][:2]
    proposal['scenes'][0]['unit_ids']=['speech_0001'];proposal['scenes'][1]['unit_ids']=['speech_0002']
    script,units,timeline=scene_inputs('甲。乙。',[1,9000],False)
    with pytest.raises(ValueError,match='merge|合并|positive|frame'): build(script,units,timeline,proposal)
    script,units,timeline=scene_inputs('甲。乙。',[4501,7502],False)
    _,plan=build(script,units,timeline,proposal)
    assert [(s['start_frame'],s['end_frame']) for s in plan['scenes']]==[(0,2),(2,5)]
    assert plan['scenes'][0]['bindings'][1] == dict(unit_id='speech_0002',text_start=2,text_end=4,text='乙。',semantic_member=False,start_sample=4501,end_sample=6000)


def test_schema_carries_strict_keys_and_scene_count_limits():
    from video_ai.config import ScenePlanningSettings
    from video_ai.planning.production_scenes import make_scene_schema
    script,units,timeline=scene_inputs()
    schema=make_scene_schema(script,units,timeline,ScenePlanningSettings())
    assert set(schema['properties'])=={'global_style','entities','appearance_variants','scene_groups','scenes'}
    assert schema['additionalProperties'] is False
    assert 'start_frame' not in schema['properties']['scenes']['items']['properties']
