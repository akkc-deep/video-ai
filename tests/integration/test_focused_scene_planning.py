import pytest

from integration.test_scene_planning import scene_setup
from unit.test_production_inputs import production_config
from unit.test_focused_scenes import wire_value


@pytest.mark.parametrize('scene_setup', [dict(text='木星。\n土星。')], indirect=True)
def test_focused_http_recovery_keeps_source_binding_without_resubmission(scene_setup, monkeypatch):
    from video_ai.config import ScenePlanningSettings
    from video_ai.planning.production_scenes import make_scene_schema
    from video_ai.runtime.production_scene_plan import _Records
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime import focused_scene_planning as focused
    s=scene_setup
    s['replies'].append({'paragraph_0001':dict(source_text='木星。\n',end_units=['speech_0001']),
                         'paragraph_0002':dict(source_text='土星。',end_units=['speech_0002'])})
    style=dict(description='科学纪录片',source_facts=[],creative_choices=[])
    group=dict(key='space',label='太空',environment='太空',time='白天',lighting='阳光',
               spatial_relations=[],source_facts=[],creative_choices=[],change_sources=[])
    def scene(text):
        return dict(source_text=text,summary=text,image_prompt=text+'写实全景',motion_prompt='镜头缓慢推进',
                    entity_ids=[],variant_ids=[],scene_group_id='space',change_sources=[])
    s['replies'].append(wire_value(dict(global_style=style,entities=[],appearance_variants=[],scene_groups=[group],
                            scenes={'scene_0001':scene('木星。'),'scene_0002':scene('土星。')})))
    settings=ScenePlanningSettings()
    schema=make_scene_schema(s['frozen'].script,s['units'],s['timeline'],settings)
    kwargs=dict(frozen=s['frozen'],script=s['frozen'].script,units=s['units'],schema=schema,settings=settings,
                folder=s['run']/'production/scene-planning/focused-v1',identity={'source':'same'},
                paths=s['paths'],logger=s['logger'],planner=s['planner'])
    def interrupt(point):
        if point=='response':raise KeyboardInterrupt()
    monkeypatch.setattr(focused,'boundary',interrupt)
    with RunLock(s['run']) as lock:
        with pytest.raises(KeyboardInterrupt):focused.produce_focused_proposal(store=_Records(s['run'],lock),**kwargs)
    assert len(s['received'])==1
    monkeypatch.setattr(focused,'boundary',lambda point:None)
    with RunLock(s['run']) as lock:
        result=focused.produce_focused_proposal(store=_Records(s['run'],lock),**kwargs)
    assert len(s['received'])==2
    assert [row['summary'] for row in result['scenes']]==['木星。','土星。']
    assert [row['unit_ids'] for row in result['scenes']]==[['speech_0001'],['speech_0002']]
    assert 'source_text' in s['received'][1]['format']['properties']['scenes']['properties']['scene_0001']['properties']


@pytest.mark.parametrize('scene_setup',[dict(text='甲乙。\n乙。\n丙。\n丁。\n戊。\n己。\n庚。\n辛。')],indirect=True)
def test_fresh_long_plan_uses_finalized_unit_ids_and_replays_committed_plan(scene_setup):
    from copy import deepcopy
    from dataclasses import replace
    from integration.test_scene_planning import produce
    from video_ai.planning.segments import TextSpan,SegmentedScript
    from video_ai.planning.production_timeline import ProductionAudioInfo,build_production_timeline
    from video_ai.runtime.production_state import ArtifactStamp
    s=scene_setup
    units=deepcopy(s['units'])
    first=units['spans'].pop(0)
    units['spans'][:0]=[dict(first,end=1,text='甲',boundary='phrase'),dict(first,start=1,text='乙。')]
    number=0
    for row in units['spans']:
        if row['kind']=='speech':number+=1;row['unit_id']=f'speech_{number:04d}'
    units['semantic_specs']={row['unit_id']:dict(facts={}) for row in units['spans'] if row['kind']=='speech'}
    s['units']=units
    script=SegmentedScript(s['frozen'].script.text,s['frozen'].script.has_bom,tuple(TextSpan(**row) for row in units['spans']))
    audio={row.unit_id:ProductionAudioInfo(ArtifactStamp('D:/pcm.wav',96046,123),48000,1,2,48001)
           for row in script.spans if row.kind=='speech'}
    s['timeline']=build_production_timeline(script,audio,settings=s['frozen'].config.media.timeline)
    paragraphs=s['frozen'].script.text.splitlines(keepends=True)
    for start in (0,6):
        s['replies'].append({f'paragraph_{i+1:04d}':dict(source_text=paragraphs[i],end_units=[f'speech_{i+2:04d}'])
                            for i in range(start,min(start+6,8))})
    style=dict(description='纪录片',source_facts=[],creative_choices=[])
    group=dict(key='space',label='太空',environment='太空',time='白天',lighting='阳光',
               spatial_relations=[],source_facts=[],creative_choices=[],change_sources=[])
    for start in (0,3,6):
        scenes={}
        for i in range(start,min(start+3,8)):
            text=paragraphs[i].strip()
            scenes[f'scene_{i+1:04d}']=dict(source_text=text,summary=text,image_prompt=text+'写实场景',
                motion_prompt='平缓推进',entity_ids=[],variant_ids=[],scene_group_id='space',change_sources=[])
        s['replies'].append(wire_value(dict(global_style=style,entities=[],appearance_variants=[],
                                scene_groups=[group] if start==0 else [],scenes=scenes)))
    bible,plan=produce(s)
    assert len(s['received'])==5
    assert [row['summary'] for row in plan['scenes']]==[text.strip() for text in paragraphs]
    assert [row['unit_ids'] for row in plan['scenes']]==[['speech_0001','speech_0002']]+[[f'speech_{i+2:04d}'] for i in range(1,8)]
    assert plan['total_frames']==s['timeline'].total_frames
    assert produce(s)==(bible,plan)
    assert len(s['received'])==5


def test_recovery_prefers_existing_correction_after_validator_becomes_more_permissive(scene_setup):
    from video_ai.runtime.focused_scene_planning import _request_batch
    from video_ai.runtime.production_scene_plan import _Records
    from video_ai.runtime.production_state import RunLock
    s=scene_setup
    wire=dict(type='object',properties=dict(status=dict(type='string')),required=['status'],additionalProperties=False)
    s['replies'].extend([dict(status='initial'),dict(status='correction')])
    strict=True
    def normalize(value):
        if strict and value['status']=='initial':raise ValueError('duplicate focused subject')
        return value
    kwargs=dict(prompt='Original fixed source',wire=wire,context={'original':'source'},
        batch=s['run']/'production/focused-test',prefix='scene_plan_focused_visual4_0001',model='qwen3:8b',
        frozen=s['frozen'],logger=s['logger'],get_client=lambda:s['planner'],normalize=normalize)
    with RunLock(s['run']) as lock:
        assert _request_batch(store=_Records(s['run'],lock),**kwargs)==dict(status='correction')
    strict=False
    with RunLock(s['run']) as lock:
        assert _request_batch(store=_Records(s['run'],lock),**kwargs)==dict(status='correction')
    assert len(s['received'])==2
