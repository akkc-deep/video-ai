"""Fixed visual batches, frozen global style and original-response reconciliation."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from uuid import uuid4

from ..adapters.common import AdapterError, HttpClient, strict_json
from ..adapters.ollama import (OllamaPlanner,OllamaFormatError,parse_completed_response,ollama_schema,
                              _GROUNDING_NOTE,_has_shared_grounding)
from ..config import read_json
from ..planning.storyboard import (GROUNDED_POLICY,UnsupportedSemanticTimingError,make_model_schema,
    validate_model_content,primary_model_slots,expand_boundary_requirements,depiction_anchor,CAMERA_PATHS)
from ..planning.production_visual_plan import build_production_budgets
from .manifest import thaw
from .production_state import ProductionRefused,object_fields
from .production_inputs import check_stage_space
from .production_support import (read_report,recover_checkpoint,recover_http,commit_checkpoint,stamps,
                                 mark_request_error,sync_manifest_stage)
from .service_specs import build_service_specs
from .services import ServiceConflictError
from .owned_cleanup import stop_owned_preserving_exception


def _batch_sources(batch,primary,facts):
    """Include the batch and the complete chain of its explicit source references."""
    needed={slot.primary_unit_id for slot in batch};pending=list(needed)
    while pending:
        uid=pending.pop()
        for source in facts[uid]['context_sources']:
            other=source['unit_id']
            if other not in needed:needed.add(other);pending.append(other)
    selected={slot.shot_id for slot in batch};covered={slot.primary_unit_id for slot in batch}
    for slot in primary:
        if slot.primary_unit_id in needed-covered:
            selected.add(slot.shot_id);covered.add(slot.primary_unit_id)
    if covered!=needed:raise ProductionRefused('visual batch has unavailable original context sources')
    sources=tuple(slot for slot in primary if slot.shot_id in selected)
    return sources,{uid:value for uid,value in facts.items() if uid in needed}


def _concise_schema(schema):
    """Bound generated prose, keeping all fixed facts and original quotes intact."""
    schema=deepcopy(schema)
    for shot in schema['properties']['shots']['prefixItems']:
        props=shot['properties'];fields=props['visual_requirements']['prefixItems'][0]['properties']
        prefix=depiction_anchor({key:field['const'] for key,field in fields.items() if 'const' in field},
                               source_quote=fields['source_quote']['const'])
        for name in ('composition','action_start','action_end','image_prompt','video_prompt'):
            suffix=max(len(' Camera path: '+camera+'.') for camera in CAMERA_PATHS) if name=='video_prompt' else 0
            props[name]['maxLength']=len(prefix)+160+suffix
        for requirement in props['visual_requirements']['prefixItems']:
            fields=requirement['properties']
            anchor=depiction_anchor({key:field['const'] for key,field in fields.items() if 'const' in field},
                                   source_quote=fields['source_quote']['const'])
            fields['visual_expression']['maxLength']=len(anchor)+160
    global_props=schema['properties']['global_visual']['properties']
    for name in ('style','color_palette','lighting'):global_props[name]['maxLength']=80
    global_props['entities']['items']['properties']['description']['maxLength']=160

    def compact(node):
        if isinstance(node,list):return [compact(item) for item in node]
        if not isinstance(node,dict):return node
        # A fixed value already carries the entire constraint. Repeating the
        # full source catalog under its array items only inflates the grammar.
        if 'const' in node:return {key:deepcopy(node[key]) for key in ('type','const') if key in node}
        return {key:compact(value) for key,value in node.items()}
    return compact(schema)


def _global_sources(primary,facts):
    result=[];seen=set()
    for slot in primary:
        fact=facts[slot.primary_unit_id]
        if not any(fact[key] is not None for key in ('subject','action_or_state','setting','quantity','negation','relation_or_order')):continue
        subject=fact['subject'] or depiction_anchor(fact)
        if subject in seen:continue
        seen.add(subject)
        result.append(dict(subject=subject,source_quote=slot.bindings[0].text))
    return result


def _visual_request(frozen,batch,primary,slots,facts,global_visual,shots,*,concise,constrain_entities=True,model_visual=False):
    if concise:
        sources,batch_facts=_batch_sources(batch,primary,facts)
        schema=_concise_schema(make_model_schema(batch,semantic_specs=batch_facts,depiction_policy=GROUNDED_POLICY,source_slots=sources))
        data=dict(visual_mode='concise_v1',facts=batch_facts,slots=thaw(batch),
            context_sources=[dict(unit_id=slot.primary_unit_id,text=slot.bindings[0].text) for slot in sources if slot.shot_id not in {s.shot_id for s in batch}],
            batch_shot_ids=[s.shot_id for s in batch],global_visual=global_visual,
            global_sources=_global_sources(primary,facts) if global_visual is None else [],
            prior_shots=[{key:shots[-1][key] for key in ('shot_id','entity_ids','action_end')}] if shots else [])
        instructions=('Plan only the fixed shots in this batch. Before image/video generation, distill each source into '
            'one concise visible subject, setting and main action. Keep quantities, negations and event order accurate. '
            'Narration and subtitles use the complete original script separately; NEVER summarize or rewrite their text. '
            'Only simplify generated visual presentations: aim for 50-100 characters and never exceed 160 characters per field. '
            'Describe each idea once; no loops, repeated subject lists or unnecessary detail. '
            'Source facts are automated interpretations; no human review has been performed. '
            'Do not alter source quotes, facts, bindings or frame ranges. Use the exact grounded transport format. '
            'Choose a coherent natural visual style. Use global_sources to establish entities for the entire video; '
            'later batches repeat global_visual unchanged. Use context_sources only for explicit references. '
            'No invented events; needs_finer_audio must honestly report incompatible meaning.')
    else:
        # Replay old runs using their original request contract and evidence.
        schema=make_model_schema(batch,semantic_specs=facts,depiction_policy=GROUNDED_POLICY,source_slots=slots)
        instructions=('Plan only the fixed shots in this batch. Source facts are automated interpretations of the original text. '
            'No human review has been performed. Do not alter text, bindings, ranges or facts. '
            'Use the exact grounded transport format supplied by the schema. Choose a coherent natural visual style. '
            'The first global_visual must cover entities needed by ALL fixed shots; later batches repeat it unchanged. '
            'No invented events; needs_finer_audio must honestly report incompatible meaning.')
        data=dict(decoded_text=frozen.script.text,facts=facts,slots=thaw(slots),batch_shot_ids=[s.shot_id for s in batch],
            global_visual=global_visual,prior_shots=shots)
    if constrain_entities:
        data['entity_ids_policy']='frozen_v1'
        instructions+=(' entity_ids only reference IDs declared in global_visual.entities. '
            'Keep other original subjects in source facts and visual descriptions; use [] when no registered entity applies. '
            'Never invent entity IDs or replace a subject with a different registered entity.')
        if global_visual is not None:
            entity_ids=[entity['entity_id'] for entity in global_visual['entities']]
            for shot in schema['properties']['shots']['prefixItems']:
                field=shot['properties']['entity_ids']
                # The legacy schema shares string nodes with global fields.
                if entity_ids:field['items']=dict(field['items'],enum=entity_ids)
                else:field.update(const=[],maxItems=0)
    if model_visual:
        from ..planning.model_visual_prompts import VISUAL_MODE,MODEL_VISUAL_INSTRUCTIONS
        schema['description']=VISUAL_MODE
        if global_visual is None:
            global_props=schema['properties']['global_visual']['properties']
            global_props['style']['enum']=['cinematic photorealistic reconstruction','natural documentary photography','realistic cinematic illustration']
            global_props['entities']['items']['properties']['source_quotes']['items']['enum']=list(dict.fromkeys(s.bindings[0].text for s in primary))
        data['visual_mode']=VISUAL_MODE
        selected={s.shot_id for s in batch};indices={i for i,s in enumerate(primary) if s.shot_id in selected}
        nearby={j for i in indices for j in range(max(0,i-3),min(len(primary),i+3))}
        data['original_source_catalog']=[dict(unit_id=s.primary_unit_id,text=s.bindings[0].text)
            for i,s in enumerate(primary) if i in nearby]
        data={key:data[key] for key in ('visual_mode','original_source_catalog','global_visual','entity_ids_policy') if key in data}
        data['shots']=[dict(shot_id=s.shot_id,source_quote=s.bindings[0].text,
            source_facts=facts[s.primary_unit_id]) for s in batch]
        if global_visual is None:data['global_subject_sources']=_global_sources(primary,facts)
        if shots:
            from ..planning.model_visual_prompts import presentation
            previous=dict(shots[-1],primary_unit_id=shots[-1]['visual_requirements'][0]['unit_id'])
            data['previous_scene']=dict(shot_id=previous['shot_id'],image_prompt=presentation(previous,'image_prompt'))
        if frozen is not None:data['topic_context']=frozen.script.text[:300]
        instructions=('Generate the fixed shots in the JSON schema, once each. Narration and subtitles remain the original source. '
            'Descriptions are for image and video models. Source facts are evidence, not output text. '
            'Keep source_quotes in entity definitions as exact original quotes from original_source_catalog. '
            'Use global_subject_sources to register recurring physical subjects across the video, and previous_scene for continuity. '
            'Use global_visual unchanged when supplied. ')+MODEL_VISUAL_INSTRUCTIONS
        instructions+=(' TRANSPORT: generate only the English scene fields in the supplied format. '
            'Do NOT emit source facts, source anchors or Camera path clauses in generated descriptions. '
            'The application restores facts from the immutable input and appends camera_motion itself. '
            'In every image_prompt name the actual scene/location; in video_prompt describe a small compatible motion. '
            'An abstract sentence continues the preceding concrete scene without invented events.')
    if global_visual is not None:schema['properties']['global_visual']['const']=deepcopy(global_visual)
    return schema,instructions+'\nVISUAL_INPUT_JSON\n'+json.dumps(data,ensure_ascii=False)


def _concise_run(logger):
    initial=logger.path('storyboard/storyboard_batch_0001_initial.intent.json')
    if not initial.exists():return True
    value=read_json(initial)
    try:data=json.loads(value['prompt'].split('\nVISUAL_INPUT_JSON\n',1)[1])
    except (KeyError,IndexError,ValueError) as exc:raise ProductionRefused('unknown saved visual request format') from exc
    return data.get('visual_mode') in ('concise_v1','model_visual_v2')


def model_visual_run(logger):
    initial=logger.path('storyboard/storyboard_batch_0001_initial.intent.json')
    if not initial.exists():return True
    value=read_json(initial)
    try:data=json.loads(value['prompt'].split('\nVISUAL_INPUT_JSON\n',1)[1])
    except (KeyError,IndexError,ValueError) as exc:raise ProductionRefused('unknown saved visual request format') from exc
    return data.get('visual_mode')=='model_visual_v2'


def _entity_constraints(logger,uid):
    """Saved requests retain their exact contract; new requests constrain IDs."""
    path=logger.path(f'storyboard/{uid}.intent.json')
    if not path.exists():return True
    value=read_json(path)
    try:data=json.loads(value['prompt'].split('\nVISUAL_INPUT_JSON\n',1)[1].split('\nCORRECTION\n')[0].split('\nENTITY_REPAIR\n')[0])
    except (KeyError,IndexError,ValueError) as exc:raise ProductionRefused('unknown saved visual request format') from exc
    policy=data.get('entity_ids_policy')
    if policy not in (None,'frozen_v1'):raise ProductionRefused('unknown saved entity ID policy')
    return policy=='frozen_v1'


def _intent(path, uid, prompt, schema, context, frozen):
    value=read_json(Path(path));object_fields(value,('request_id','body','schema','prompt','context'),'visual intent')
    actual=value['context'];object_fields(actual,(*context,'client_id'),'visual context')
    if (value['request_id']!=uid or value['schema']!=schema or value['prompt']!=prompt or
        {k:v for k,v in actual.items() if k!='client_id'}!=context): raise ProductionRefused('visual intent differs from fixed batch')
    expected=dict(model='qwen3:8b',prompt=prompt+(_GROUNDING_NOTE if _has_shared_grounding(schema) else ''),
                  stream=False,format=ollama_schema(schema),keep_alive=0,think=False,options=dict(temperature=0,num_predict=8192))
    if frozen.options['cpu_planner']: expected['options']['num_gpu']=0
    if json.dumps(value['body'],sort_keys=True,allow_nan=False)!=json.dumps(expected,sort_keys=True,allow_nan=False):
        raise ProductionRefused('original visual request body changed')
    return value


def produce(frozen,units,timeline,slot_plan,*,state,manifest,paths,logger,manager_factory,port_probe):
    report=read_report(state,'storyboard');complete=state.snapshot()['stages']['storyboard']['status']=='completed'
    if complete and report is None: raise ProductionRefused('completed storyboard has no report')
    if not complete: state.start_stage('storyboard');check_stage_space(frozen.config,frames=timeline.total_frames)
    slots=slot_plan.slots;primary=primary_model_slots(slots)
    facts={uid:spec['facts'] for uid,spec in units['semantic_specs'].items()}
    budgets=build_production_budgets(timeline,slots)
    inputs=stamps({'options':state.run_dir/'production/options.json','units':state.run_dir/'production/units.json',
                  'timeline':state.run_dir/'production/timeline.json','slots':state.run_dir/'logs/production/checkpoints/timeline/automatic-slots.json'})
    planner=OllamaPlanner(HttpClient(frozen.config.services['ollama'],frozen.options['execution_policy']['ollama_request_seconds'],logger),cpu_only=frozen.options['cpu_planner'])
    manager=manager_factory(paths,manifest,logger);handle=None;global_visual=None;shots=[]
    concise=_concise_run(logger)
    model_visual=concise and _entity_constraints(logger,'storyboard_batch_0001_initial') and model_visual_run(logger)
    try:
        for index,start in enumerate(range(0,len(primary),8),1):
            batch=primary[start:start+8];bid=f'storyboard_batch_{index:04d}'
            constrained=_entity_constraints(logger,bid+'_initial')
            schema,prompt=_visual_request(frozen,batch,primary,slots,facts,global_visual,shots,concise=concise,
                                         constrain_entities=constrained,model_visual=model_visual)
            context=dict(script_identity=frozen.options['execution_policy']['input_identities']['script'],
                         shot_ranges=[dict(shot_id=s.shot_id,start_frame=s.start_frame,end_frame=s.end_frame,primary_unit_id=s.primary_unit_id) for s in batch],
                         units_stamp=inputs['units'],slots_stamp=inputs['slots'],global_visual=global_visual)
            last_error=None
            for suffix in ('initial','correction','entityrepair'):
                uid=bid+'_'+suffix
                if suffix=='entityrepair':
                    # Only the exhausted legacy unknown-ID failure reaches here.
                    # Original requests/checkpoints remain immutable; this has a
                    # distinct ID, durable intent and one bounded model request.
                    schema,prompt=_visual_request(frozen,batch,primary,slots,facts,global_visual,shots,concise=concise,
                                                 constrain_entities=True,model_visual=model_visual)
                    current_prompt=prompt+'\nENTITY_REPAIR\n'+last_error
                else:current_prompt=prompt if suffix=='initial' else prompt+'\nCORRECTION\n'+last_error
                cp=recover_checkpoint(state,'storyboard',uid)
                record=state.snapshot()['units'].get('storyboard',{}).get(uid)
                intent_path=logger.path(f'storyboard/{uid}.intent.json')
                if cp or record and record['request'] or intent_path.exists():
                    intent=_intent(intent_path,uid,current_prompt,schema,context,frozen)
                    req=dict(state='intent',intent_path=str(intent_path),client_id=intent['context']['client_id'],prompt_id=None,response_paths=[])
                    if record is None:state.record_unit('storyboard',uid,status='running',request=req)
                    else:
                        req=record['request']
                        if req is None or req['client_id']!=intent['context']['client_id'] or req['intent_path']!=str(intent_path):raise ProductionRefused('visual request identity differs')
                else:
                    if complete:raise ProductionRefused('completed storyboard lacks original batch checkpoint')
                    if handle is None:
                        if port_probe(frozen.config.services['ollama'],3): raise ProductionRefused('external Ollama service at '+frozen.config.services['ollama'])
                        try:handle=manager.ensure(build_service_specs(frozen.config,state.run_dir,production=True,frozen=frozen,store=manifest)['ollama'])
                        except ServiceConflictError as exc:raise ProductionRefused(str(exc)) from exc
                        if not handle.owned:raise ProductionRefused('external Ollama service at '+handle.url)
                    client=uuid4().hex
                    def on_intent(path,body):
                        state.record_unit('storyboard',uid,status='running',request=dict(state='intent',intent_path=str(path),client_id=client,prompt_id=None,response_paths=[]))
                    print(f'[make-video] storyboard {bid} {suffix}: Ollama',file=sys.stderr,flush=True)
                    try:planner.generate(current_prompt,schema=schema,request_id=uid,intent_context=dict(context,client_id=client),on_intent=on_intent)
                    except OllamaFormatError:pass # Reparse the complete original response below.
                    except AdapterError as exc:mark_request_error(state,'storyboard',uid,exc)
                    intent=_intent(intent_path,uid,current_prompt,schema,context,frozen)
                    req=state.snapshot()['units']['storyboard'][uid]['request']
                try:
                    raw,_,evidence=recover_http(logger,uid=uid,url=frozen.config.services['ollama']+'/api/generate',payload=intent['body'])
                except AdapterError as exc:mark_request_error(state,'storyboard',uid,exc)
                error=None;content=None
                try:outer=strict_json(raw)
                except ValueError as exc:raise ProductionRefused('unknown original Ollama outer response; no correction POST') from exc
                try:
                    content=parse_completed_response(outer,schema=schema,request_id=uid,evidence_paths=evidence)
                    validate_model_content(content,batch,semantic_specs=facts,depiction_policy=GROUNDED_POLICY,source_slots=slots)
                    if model_visual:
                        from ..planning.model_visual_prompts import validate_english_content
                        validate_english_content(content)
                    if global_visual is not None and content['global_visual']!=global_visual:raise ValueError('global_visual differs from frozen first batch')
                except UnsupportedSemanticTimingError as exc:
                    state.record_unit('storyboard',uid,status='failed',request=dict(req,state='failed',response_paths=evidence),
                                      error=dict(kind='UnsupportedSemanticTimingError',message=str(exc),evidence_paths=evidence))
                    raise RuntimeError(str(exc)) from exc
                except (OllamaFormatError,ValueError) as exc:error=str(exc);content=None
                except AdapterError as exc:mark_request_error(state,'storyboard',uid,exc)
                payload=dict(batch_id=bid,shot_ids=[s.shot_id for s in batch],format_valid=error is None,content=content,error=error)
                if cp:
                    if cp['payload']!=payload:raise ProductionRefused('visual checkpoint differs from original response')
                else:
                    evidence=list(dict.fromkeys([str(intent_path),*evidence,*[str(p) for p in logger.path('storyboard').glob(uid+'.*.json')]]))
                    commit_checkpoint(state,'storyboard',uid,request=dict(req,response_paths=evidence),
                                      outputs=stamps({f'evidence_{i}':p for i,p in enumerate(evidence)}),payload=payload)
                if error is None:break
                last_error=error
                if suffix=='correction':
                    if (not constrained and global_visual is not None and error=='unknown entity identity'
                        and _entity_constraints(logger,bid+'_entityrepair')):continue
                    raise RuntimeError(f'{bid}: second completed response invalid: {error}')
                if suffix=='entityrepair':raise RuntimeError(f'{bid}: entity repair response invalid: {error}')
            if global_visual is None:global_visual=deepcopy(content['global_visual'])
            shots.extend(content['shots'])
        expanded,_=expand_boundary_requirements(dict(schema_version=1,global_visual=global_visual,shots=shots),slots,
                                                semantic_specs=facts,depiction_policy=GROUNDED_POLICY)
        rows=[]
        for slot,visual,budget in zip(slots,expanded['shots'],budgets.shots):
            row=dict(thaw(slot),**{k:v for k,v in visual.items() if k!='shot_id'},budget=thaw(budget))
            for i,r in enumerate(row['visual_requirements'],1):r['requirement_id']=f'{slot.shot_id}:req_{i:04d}'
            rows.append(row)
        media=frozen.config.media;profile=thaw(media.profile)
        payload=dict(global_visual=global_visual,effective_media=dict(fps=16,native_fps=16,profile=profile,image_aspect_ratio='16:9',
            default_image_width=1280 if model_visual else profile['width'],default_image_height=720 if model_visual else profile['height'],transition='cut',transition_seconds=media.transition_seconds),shots=rows,transitions=[])
        if report and (report['payload']!=payload or report['input_records']!=inputs):raise ProductionRefused('immutable storyboard report differs from checkpoints')
        if not report:state.write_report('storyboard',payload,input_records=inputs)
        if not complete:state.complete_stage('storyboard')
        sync_manifest_stage(manifest,'storyboard',state.run_dir/'production/storyboard.json')
        return payload
    finally:stop_owned_preserving_exception(manager,handle,logger,'storyboard')
