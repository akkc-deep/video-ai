from copy import deepcopy
import json

import pytest

from production_helpers import model_server, config_for_server, install_owned_services, proposal_for, wav_bytes
from unit.test_production_inputs import production_config
from unit.test_production_speech import make_prefix


def wire_value(schema):
    if 'const' in schema: return deepcopy(schema['const'])
    if 'enum' in schema: return schema['enum'][0]
    if 'anyOf' in schema: return wire_value(schema['anyOf'][0])
    kind=schema['type']
    if isinstance(kind,list): return None if 'null' in kind else wire_value(dict(schema,type=kind[0]))
    if kind=='object': return {k:wire_value(v) for k,v in schema['properties'].items()}
    if kind=='array': return [wire_value(schema['items']) for _ in range(schema.get('minItems',0))]
    if kind=='boolean': return False
    if kind=='integer': return schema.get('minimum',0)
    from video_ai.adapters.ollama import _grounded_pattern_parts
    parts=_grounded_pattern_parts(schema.get('pattern'))
    if parts is None and r'\. ' in schema.get('pattern',''):
        import re
        prefix=schema['pattern'].split(r'\. ',1)[0][1:]
        parts=(re.sub(r'\\(.)',r'\1',prefix)+'. ','')
    return (parts[0] if parts else '')+'Visible lake scene'


def visual_handler(path,body,count):
    if path=='/tts': return 200,'audio/wav',wav_bytes()
    if '\nINPUT_JSON\n' in body['prompt']:
        proposal=proposal_for(body)
        data=json.loads(body['prompt'].split('\nINPUT_JSON\n')[1].split('\nCORRECTION\n')[0])
        for candidate in data['candidates']: proposal[candidate['unit_id']][0]['facts']['subject']=candidate['text']
        wire=proposal
    else: wire=wire_value(body['format'])
    return 200,'application/json',json.dumps(dict(model='qwen3:8b',done=True,response=json.dumps(wire,ensure_ascii=False))).encode()


def visual_prefix(config,run,paths,url,monkeypatch,text='湖水。白鸟。'):
    from video_ai.runtime.production_storyboard import produce_units
    from video_ai.runtime.production_speech import produce_speech
    from video_ai.runtime.production_timeline import produce_timeline
    frozen,state,manifest,logger=make_prefix(config_for_server(config,url,run),run,text)
    install_owned_services(monkeypatch)
    units=produce_units(frozen,state=state,manifest=manifest,paths=paths,logger=logger)
    audio=produce_speech(frozen,units,state=state,manifest=manifest,paths=paths,logger=logger)
    timeline,plan=produce_timeline(frozen,units,audio,state=state,manifest=manifest,paths=paths,logger=logger)
    return frozen,state,manifest,logger,units,timeline,plan


def test_full_catalog_allows_cross_batch_sources_and_entity_quote():
    from video_ai.planning.storyboard import make_model_schema,validate_model_content,primary_model_slots
    from video_ai.planning.production_timing import build_automatic_slots
    from test_production_timing import timeline,estimate
    t=timeline([6000,6000]);slots=build_automatic_slots(t,{'speech_0001':estimate(6000),'speech_0002':estimate(6000)}).slots
    projected=primary_model_slots(slots)
    facts={s.primary_unit_id:dict(subject=s.bindings[0].text,action_or_state=None,setting=None,quantity=None,
                                negation=None,relation_or_order=None,context_sources=[],resolved_references=[]) for s in projected}
    b=slots[0].bindings[0]
    facts['speech_0002']['context_sources']=[dict(unit_id=b.unit_id,text_start=b.text_start,text_end=b.text_end,source_quote=b.text)]
    schema=make_model_schema(projected[1:],semantic_specs=facts,source_slots=slots)
    from storyboard_helpers import content_for
    content=content_for(projected[1:]);content['shots'][0]['visual_requirements'][0].update(facts['speech_0002'])
    content['global_visual']['entities']=[dict(entity_id='lake',description='lake',source_quotes=[b.text])]
    validate_model_content(content,projected[1:],semantic_specs=facts,source_slots=slots)
    with pytest.raises(ValueError): make_model_schema(projected[1:],semantic_specs=facts)


def test_compact_batch_preserves_transitive_references_quantities_and_negations():
    from video_ai.runtime.production_visual_storyboard import _visual_request
    from video_ai.planning.storyboard import primary_model_slots,validate_model_content
    from video_ai.planning.production_timing import build_automatic_slots
    from video_ai.adapters.ollama import ollama_schema,parse_completed_response
    from test_production_timing import timeline,estimate
    t=timeline([6000]*10,text='甲。'*10)
    slots=build_automatic_slots(t,{f'speech_{i:04d}':estimate(6000) for i in range(1,11)}).slots
    primary=primary_model_slots(slots)
    facts={s.primary_unit_id:dict(subject=s.bindings[0].text,action_or_state=None,setting=None,quantity=None,
        negation=None,relation_or_order=None,context_sources=[],resolved_references=[]) for s in primary}
    for index,source_index in ((9,8),(8,0)):
        binding=primary[source_index].bindings[0]
        facts[primary[index].primary_unit_id]['context_sources']=[dict(unit_id=binding.unit_id,
            text_start=binding.text_start,text_end=binding.text_end,source_quote=binding.text)]
    facts['speech_0010'].update(quantity='3',negation='does not vanish')
    facts['speech_0008'].update(subject=None)  # An unrelated future source may have no explicit facts.
    schema,prompt=_visual_request(None,primary[9:],primary,slots,facts,None,[],concise=True)
    payload=json.loads(prompt.split('\nVISUAL_INPUT_JSON\n')[1])
    assert set(payload['facts'])=={'speech_0001','speech_0009','speech_0010'}
    wire=wire_value(ollama_schema(schema))
    content=parse_completed_response(dict(model='qwen3:8b',done=True,response=json.dumps(wire)),
        schema=schema,request_id='storyboard_batch_0002_initial',evidence_paths=[])
    requirement=content['shots'][0]['visual_requirements'][0]
    assert requirement['quantity']=='3' and requirement['negation']=='does not vanish'
    assert requirement['context_sources'][0]['unit_id']=='speech_0009'
    assert requirement['source_quote']==primary[9].bindings[0].text
    validate_model_content(content,primary[9:],semantic_specs=facts,depiction_policy='grounded_prompts_v1',source_slots=slots)


@pytest.mark.parametrize('empty_facts',[False,True])
def test_nine_shots_freeze_global_and_resume_original_http(production_config,runtime_run,monkeypatch,empty_facts):
    from video_ai.runtime.production_storyboard import produce_storyboard
    run,_,paths=runtime_run
    def handler(path,body,count):
        status,media,response=visual_handler(path,body,count)
        if empty_facts and '\nINPUT_JSON\n' in body.get('prompt',''):
            outer=json.loads(response);proposal=json.loads(outer['response'])
            for key in ('speech_0008','speech_0009'):
                if key in proposal:proposal[key][0]['facts']['subject']=None
            outer['response']=json.dumps(proposal,ensure_ascii=False)
            response=json.dumps(outer,ensure_ascii=False).encode()
        return status,media,response
    with model_server(handler) as (url,posts):
        f,s,m,l,u,t,p=visual_prefix(production_config,run,paths,url,monkeypatch,text=''.join(f'湖{i}。' for i in range(9)))
        base=len(posts)
        result=produce_storyboard(f,u,t,p,state=s,manifest=m,paths=paths,logger=l)
        requests=posts[base:]
        assert len(result['shots'])==9 and len(requests)==2
        assert len(requests[0][1]['format']['properties']['shots']['properties'])==8
        assert requests[1][1]['format']['properties']['global_visual']['const']==result['global_visual']
        assert [r['start_frame'] for r in result['shots']]==[slot.start_frame for slot in p.slots]
        assert result['shots'][-1]['end_frame']==t.total_frames and result['transitions']==[]
        assert s.snapshot()['active_stage']=='start_images'
        if empty_facts:
            for shot,quote in zip(result['shots'][-2:],('湖7。','湖8。')):
                assert shot['image_prompt'].startswith(quote+'. ')
                assert shot['visual_requirements'][0]['subject'] is None
            assert u['semantic_specs']['speech_0009']['facts']['subject'] is None
        assert produce_storyboard(f,u,t,p,state=s,manifest=m,paths=paths,logger=l)==result
        assert len(posts)==base+2


@pytest.mark.parametrize('concise',[False,True])
def test_empty_facts_use_exact_source_quote_through_boundary_expansion(concise):
    from types import SimpleNamespace
    from video_ai.runtime.production_visual_storyboard import _visual_request
    from video_ai.planning.storyboard import primary_model_slots,expand_boundary_requirements,validate_model_content
    from video_ai.planning.production_timing import build_automatic_slots
    from video_ai.adapters.ollama import ollama_schema,parse_completed_response
    from test_production_timing import timeline,estimate
    t=timeline([4500,7500],text='甲，乙。')
    slots=build_automatic_slots(t,{'speech_0001':estimate(4500),'speech_0002':estimate(7500)}).slots
    primary=primary_model_slots(slots)
    facts={s.primary_unit_id:dict(subject=None,action_or_state=None,setting=None,quantity=None,
        negation=None,relation_or_order=None,context_sources=[],resolved_references=[]) for s in primary}
    before=deepcopy(facts)
    schema,_=_visual_request(SimpleNamespace(script=SimpleNamespace(text='甲，乙。')),primary,primary,slots,facts,None,[],concise=concise)
    content=parse_completed_response(dict(model='qwen3:8b',done=True,response=json.dumps(wire_value(ollama_schema(schema)))),
        schema=schema,request_id='storyboard_batch_0001_initial',evidence_paths=[])
    expanded,_=expand_boundary_requirements(content,slots,semantic_specs=facts,depiction_policy='grounded_prompts_v1')
    assert expanded['shots'][0]['image_prompt']=='甲，. Visible lake scene'
    assert expanded['shots'][0]['visual_requirements'][1]['visual_expression']=='乙。. Visible lake scene'
    assert facts==before
    bad=deepcopy(expanded);bad['shots'][0]['image_prompt']='Invented subject. Visible lake scene'
    with pytest.raises(ValueError):
        validate_model_content(bad,slots,semantic_specs=facts,depiction_policy='grounded_prompts_v1')


def test_resume_legacy_visual_request_uses_original_contract(production_config,runtime_run,monkeypatch):
    from video_ai.runtime.production_storyboard import produce_storyboard
    from video_ai.runtime import production_visual_storyboard
    run,_,paths=runtime_run
    with model_server(visual_handler) as (url,posts):
        f,s,m,l,u,t,p=visual_prefix(production_config,run,paths,url,monkeypatch)
        with monkeypatch.context() as legacy:
            legacy.setattr(production_visual_storyboard,'_concise_run',lambda logger:False)
            result=produce_storyboard(f,u,t,p,state=s,manifest=m,paths=paths,logger=l)
        base=len(posts)
        assert produce_storyboard(f,u,t,p,state=s,manifest=m,paths=paths,logger=l)==result
        assert len(posts)==base


def test_visual_batches_keep_original_audio_and_send_only_relevant_sources(production_config,runtime_run,monkeypatch):
    from video_ai.runtime.production_storyboard import produce_storyboard
    from video_ai.media.subtitles import plan_subtitle_events
    from video_ai.planning.composition import CompositionSettings
    run,_,paths=runtime_run
    text=''.join(f'湖{i}。' for i in range(10))
    with model_server(visual_handler) as (url,posts):
        f,s,m,l,u,t,p=visual_prefix(production_config,run,paths,url,monkeypatch,text=text)
        base=len(posts)
        speech_before=(run/'production/speech.json').read_bytes()
        timeline_before=(run/'production/timeline.json').read_bytes()
        result=produce_storyboard(f,u,t,p,state=s,manifest=m,paths=paths,logger=l)
        first,second=[body for _,body in posts[base:]]
        payload=json.loads(first['prompt'].split('\nVISUAL_INPUT_JSON\n')[1].split('\n\nStructured transport')[0])
        assert 'decoded_text' not in payload
        assert [slot['shot_id'] for slot in payload['shots']]==[f'shot_{i:04d}' for i in range(1,9)]
        assert len(payload['shots'])==8
        next_payload=json.loads(second['prompt'].split('\nVISUAL_INPUT_JSON\n')[1].split('\n\nStructured transport')[0])
        assert [s['shot_id'] for s in next_payload['shots']]==['shot_0009','shot_0010']
        assert all('source_facts' in s for s in next_payload['shots'])
        assert (run/'production/script.txt').read_text(encoding='utf-8')==text
        assert (run/'production/speech.json').read_bytes()==speech_before
        assert (run/'production/timeline.json').read_bytes()==timeline_before
        assert [row['text'] for row in json.loads(speech_before)['payload']['spans'] if row['kind']=='speech']==[f'湖{i}。' for i in range(10)]
        assert [row['end_frame'] for row in result['shots']]==[slot.end_frame for slot in p.slots]
        events=plan_subtitle_events(t.subtitles,settings=CompositionSettings(),measure=lambda value:len(value)*20)
        assert ''.join(''.join(event['layout']['lines']) for event in events)==text


@pytest.mark.parametrize('mode',['overlong','repeat','truncated'])
def test_concise_visual_errors_get_one_correction_and_resume_without_repost(production_config,runtime_run,monkeypatch,mode):
    from video_ai.runtime.production_storyboard import produce_storyboard
    run,_,paths=runtime_run
    def handler(path,body,count):
        if path=='/api/generate' and '\nVISUAL_INPUT_JSON\n' in body['prompt'] and '\nCORRECTION\n' not in body['prompt']:
            wire=wire_value(body['format'])
            shot=next(iter(wire['shots'].values()))
            target=shot['_grounded_visual']['presentations'] if '_grounded_visual' in shot else shot
            target['composition']=('Visible craft. '*30 if mode=='overlong' else 'Voyager craft; '*8)
            return 200,'application/json',json.dumps(dict(model='qwen3:8b',done=True,
                done_reason='length' if mode=='truncated' else 'stop',eval_count=8192,
                response=json.dumps(wire,ensure_ascii=False))).encode()
        return visual_handler(path,body,count)
    with model_server(handler) as (url,posts):
        f,s,m,l,u,t,p=visual_prefix(production_config,run,paths,url,monkeypatch)
        base=len(posts)
        result=produce_storyboard(f,u,t,p,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==base+2
        correction=posts[-1][1]['prompt'].split('\nCORRECTION\n')[1]
        assert ('truncated' if mode=='truncated' else 'repeated' if mode=='repeat' else 'length') in correction
        assert produce_storyboard(f,u,t,p,state=s,manifest=m,paths=paths,logger=l)==result
        assert len(posts)==base+2


@pytest.mark.parametrize('mode',['format','unknown','bad_outer','needs_finer'])
def test_completed_format_only_one_correction_and_unknown_no_repost(production_config,runtime_run,monkeypatch,mode):
    from video_ai.runtime.production_storyboard import produce_storyboard
    from video_ai.runtime.production_state import ProductionRefused
    run,_,paths=runtime_run
    def handler(path,body,count):
        if path=='/api/generate' and '\nINPUT_JSON\n' not in body['prompt']:
            if mode=='unknown':return 503,'text/plain',b'unknown'
            if mode=='bad_outer':return 200,'application/json',b'{not JSON'
            wire=wire_value(body['format'])
            if mode=='needs_finer':
                for shot in wire['shots'].values():
                    if 'visual_requirements' in shot:
                        for req in shot['visual_requirements'].values(): req['needs_finer_audio']=True
                    else:shot['needs_finer_audio']=True
                return 200,'application/json',json.dumps(dict(model='qwen3:8b',done=True,response=json.dumps(wire))).encode()
            return 200,'application/json',json.dumps(dict(model='qwen3:8b',done=True,response='')).encode()
        return visual_handler(path,body,count)
    with model_server(handler) as (url,posts):
        f,s,m,l,u,t,p=visual_prefix(production_config,run,paths,url,monkeypatch)
        base=len(posts)
        for _ in range(2):
            with pytest.raises(ProductionRefused if mode in ('unknown','bad_outer') else RuntimeError):
                produce_storyboard(f,u,t,p,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)-base==(2 if mode=='format' else 1)


@pytest.mark.parametrize('entities', [[], [dict(entity_id='lake',description='lake',source_quotes=['甲。'])]])
@pytest.mark.parametrize('concise',[True,False])
def test_frozen_entities_are_enforced_in_visual_transport(entities,concise):
    from video_ai.runtime.production_visual_storyboard import _visual_request
    from video_ai.planning.storyboard import primary_model_slots
    from video_ai.planning.production_timing import build_automatic_slots
    from video_ai.adapters.ollama import ollama_schema,parse_completed_response,OllamaFormatError
    from test_production_timing import timeline,estimate
    t=timeline([6000],text='甲。')
    slots=build_automatic_slots(t,{'speech_0001':estimate(6000)}).slots
    primary=primary_model_slots(slots)
    facts={'speech_0001':dict(subject='甲',action_or_state=None,setting=None,quantity=None,
        negation=None,relation_or_order=None,context_sources=[],resolved_references=[])}
    global_visual=dict(style='natural',color_palette='blue',lighting='soft',entities=entities)
    from types import SimpleNamespace
    frozen=SimpleNamespace(script=SimpleNamespace(text='甲。'))
    schema,prompt=_visual_request(frozen,primary,primary,slots,facts,global_visual,[],concise=concise)
    wire=wire_value(ollama_schema(schema))
    next(iter(wire['shots'].values()))['entity_ids']=['earth']
    with pytest.raises(OllamaFormatError):
        parse_completed_response(dict(model='qwen3:8b',done=True,response=json.dumps(wire)),
            schema=schema,request_id='storyboard_batch_0002_initial',evidence_paths=[])
    for shot in wire['shots'].values():shot['entity_ids']=['lake'] if entities else []
    parse_completed_response(dict(model='qwen3:8b',done=True,response=json.dumps(wire)),
        schema=schema,request_id='storyboard_batch_0002_initial',evidence_paths=[])
    assert 'entity_ids' in prompt and '[]' in prompt


@pytest.mark.parametrize('repair_mode',['valid','invalid','unknown','interrupted'])
def test_legacy_unknown_entities_have_one_durable_repair(production_config,runtime_run,monkeypatch,repair_mode):
    from video_ai.runtime.production_storyboard import produce_storyboard
    from video_ai.runtime import production_visual_storyboard as module
    from video_ai.runtime.production_state import ProductionStateStore,ProductionRefused
    run,_,paths=runtime_run
    def handler(path,body,count):
        if path=='/api/generate' and '\nVISUAL_INPUT_JSON\n' in body['prompt']:
            wire=wire_value(body['format'])
            if 'const' not in body['format']['properties']['global_visual']:
                wire['global_visual']['entities']=[dict(entity_id='lake',description='lake',source_quotes=['湖0。'])]
            elif '\nENTITY_REPAIR\n' not in body['prompt'] or repair_mode=='invalid':
                for shot in wire['shots'].values():shot['entity_ids']=['earth']
            if '\nENTITY_REPAIR\n' in body['prompt'] and repair_mode=='unknown':return 503,'text/plain',b'unknown'
            return 200,'application/json',json.dumps(dict(model='qwen3:8b',done=True,response=json.dumps(wire))).encode()
        return visual_handler(path,body,count)
    with model_server(handler) as (url,posts):
        f,s,m,l,u,t,p=visual_prefix(production_config,run,paths,url,monkeypatch,text=''.join(f'湖{i}。' for i in range(9)))
        base=len(posts)
        with monkeypatch.context() as legacy:
            legacy.setattr(module,'_entity_constraints',lambda *args:False,raising=False)
            with pytest.raises(RuntimeError,match='unknown entity identity'):
                produce_storyboard(f,u,t,p,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==base+3
        original={str(path):(path.read_bytes(),path.stat().st_mtime_ns) for folder in
            ('production/audio','logs/production/storyboard','logs/production/checkpoints/storyboard')
            for path in (run/folder).rglob('*') if path.is_file()}
        original.update({str(run/name):((run/name).read_bytes(),(run/name).stat().st_mtime_ns)
            for name in ('production/speech.json','production/timeline.json')})
        if repair_mode=='interrupted':
            commit=module.commit_checkpoint
            def interrupt_commit(state,stage,uid,**kwargs):
                if uid=='storyboard_batch_0002_entityrepair':raise KeyboardInterrupt('complete response before checkpoint')
                return commit(state,stage,uid,**kwargs)
            with monkeypatch.context() as interrupted:
                interrupted.setattr(module,'commit_checkpoint',interrupt_commit)
                with pytest.raises(KeyboardInterrupt):
                    produce_storyboard(f,u,t,p,state=s,manifest=m,paths=paths,logger=l)
            assert len(posts)==base+4
        if repair_mode in ('valid','interrupted'):
            result=produce_storyboard(f,u,t,p,state=s,manifest=m,paths=paths,logger=l)
            assert len(result['shots'])==9 and result['shots'][-1]['entity_ids']==[]
            reopened=ProductionStateStore.open(run)
            assert produce_storyboard(f,u,t,p,state=reopened,manifest=m,paths=paths,logger=l)==result
            assert 'storyboard_batch_0002_entityrepair' in reopened.snapshot()['units']['storyboard']
        else:
            for _ in range(2):
                with pytest.raises(ProductionRefused if repair_mode=='unknown' else RuntimeError):
                    produce_storyboard(f,u,t,p,state=s,manifest=m,paths=paths,logger=l)
        assert len(posts)==base+4
        assert '\nENTITY_REPAIR\n' in posts[-1][1]['prompt']
        for name,(data,mtime) in original.items():
            from pathlib import Path
            path=Path(name)
            assert (path.read_bytes(),path.stat().st_mtime_ns)==(data,mtime)
