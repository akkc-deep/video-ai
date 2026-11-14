from copy import deepcopy
import json

import pytest

from unit.test_production_scenes import scene_inputs
from video_ai.adapters.ollama import ollama_body, parse_completed_response, _response_schema_check
from video_ai.config import ScenePlanningSettings
from video_ai.planning.production_scenes import make_scene_schema
from video_ai.runtime.production_scene_plan import _prompt


def test_partition_wire_preserves_multiscene_coverage_and_source_order():
    from video_ai.adapters.scene_partition import project, restore
    script, units, timeline = scene_inputs('湖面很静。白鸟停在石上。\n它望向远处。', samples=[48000]*3)
    settings = ScenePlanningSettings(target_scenes_per_paragraph=3)
    schema = make_scene_schema(script, units, timeline, settings)
    prompt = _prompt(script, units, timeline, settings)
    _, wire_schema = project(prompt, schema)
    source_schema=wire_schema['properties']['scene_groups']['items']['properties']['source_facts']['items']['properties']['sources']['items']
    assert source_schema['type']=='string'
    assert source_schema['enum']==['speech_0001','speech_0002','speech_0003']
    with pytest.raises(ValueError,match='outside schema enum'):
        _response_schema_check('speech_0299',source_schema)
    variants = wire_schema['properties']['scenes']['properties']['paragraph_0001']['anyOf']
    assert len(variants) == 2
    assert variants[1]['properties']['scene_0002']['properties']['end_unit']['const'] == 'speech_0002'
    scene = dict(summary='湖畔', image_prompt='湖畔白鸟', motion_prompt='水面起伏',
                 entity_ids=[], variant_ids=[], scene_group_id='lake', change_sources=[])
    proposal = dict(global_style=dict(description='自然摄影',source_facts=[],creative_choices=[]),
        entities=[],appearance_variants=[],scene_groups=[dict(key='lake',label='湖畔',environment='湖畔',time='清晨',
        lighting='日光',spatial_relations=[],source_facts=[],creative_choices=[],change_sources=[])],scenes={
        'paragraph_0001': dict(scene_0001=dict(scene, end_unit='speech_0001'), scene_0002=dict(scene, end_unit='speech_0002')),
        'paragraph_0002': dict(scene_0001=dict(scene, end_unit='speech_0003'))})
    restored = restore(proposal, prompt)
    assert [s['unit_ids'] for s in restored['scenes']] == [['speech_0001'], ['speech_0002'], ['speech_0003']]
    bad = deepcopy(proposal)
    bad['scenes']['paragraph_0001']['scene_0002']['end_unit'] = 'speech_0001'
    with pytest.raises(ValueError, match='increase'):
        restore(bad, prompt)
    cited=deepcopy(proposal)
    cited['scenes']['paragraph_0001']['scene_0001']['change_sources']=['speech_0001']
    assert restore(cited,prompt)['scenes'][0]['change_sources'][0]['quote']=='湖面很静。'
    cited['scenes']['paragraph_0001']['scene_0001']['change_sources']=['speech_9999']
    with pytest.raises(ValueError,match='unknown source'):
        restore(cited,prompt)
    missing_tail=deepcopy(proposal)
    missing_tail['scenes']['paragraph_0001'].pop('scene_0002')
    with pytest.raises(ValueError,match='cover paragraph tail'):
        restore(missing_tail,prompt)
    foreign=deepcopy(proposal)
    foreign['scenes']['paragraph_0001']['scene_0002']['end_unit']='speech_0003'
    with pytest.raises(ValueError,match='foreign boundary'):
        restore(foreign,prompt)
    body = ollama_body(prompt, schema, scene_planning=True, scene_partition=True, scene_compact=True)
    assert body['format']['$comment'] == 'video_ai_scene_partition_v3'
    assert 'num_ctx' not in body['options']
    for exact,boundaries in ((False,False),(True,False),(True,True)):
        candidate=ollama_body(prompt,schema,scene_planning=True,scene_partition=True,scene_compact=True,
                             scene_partition_exact_sources=exact,scene_partition_exact_boundaries=boundaries)
        parsed=parse_completed_response(dict(model='qwen3:8b',done=True,done_reason='stop',response=json.dumps(proposal)),
            schema=schema,request_id='scene_plan_partition_initial',scene_prompt=prompt,wire_schema=candidate['format'],evidence_paths=())
        assert parsed==restored
    compact, _ = json.JSONDecoder().raw_decode(body['prompt'].split('\nSCENE_COMPACT_INPUT_JSON\n')[1])
    assert compact['decoded_text'] == script.text


def test_grammar_only_allows_increasing_boundaries():
    from video_ai.adapters.scene_partition import project
    script,units,timeline=scene_inputs('湖面很静。白鸟停在石上。它望向远处。',samples=[48000]*3)
    settings=ScenePlanningSettings(target_scenes_per_paragraph=3)
    _,wire=project(_prompt(script,units,timeline,settings),make_scene_schema(script,units,timeline,settings))
    alternatives=wire['properties']['scenes']['properties']['paragraph_0001']['anyOf']
    boundaries=[]
    for alternative in alternatives:
        ends=[row['properties']['end_unit']['const'] for row in alternative['properties'].values()]
        assert ends==sorted(set(ends)) and ends[-1]=='speech_0003'
        boundaries.append(ends)
    assert len(boundaries)==4
