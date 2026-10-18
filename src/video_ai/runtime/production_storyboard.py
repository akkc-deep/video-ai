"""Automatic lossless units and fixed-slot visual authoring."""
from dataclasses import asdict
import json
from pathlib import Path
from uuid import uuid4

from ..adapters.common import AdapterError, HttpClient, strict_json
from ..adapters.ollama import OllamaFormatError, OllamaPlanner, ollama_schema, ollama_body, parse_completed_response
from ..config import read_json
from ..planning.composition import CompositionSettings
from ..media.font_metrics import PrivateFont
from ..planning.production_units import (apply_units_proposal, make_units_schema,
                                         validate_production_units)
from .manifest import thaw
from .owned_cleanup import stop_owned_preserving_exception
from .production_inputs import check_stage_space
from .production_state import ArtifactStamp, ProductionRefused, object_fields, run_path
from .production_support import (commit_checkpoint, mark_request_error, read_report, recover_checkpoint,
                                 recover_http, stamps)
from .service_specs import build_service_specs
from .services import ServiceConflictError, ServiceManager, port_listening


def _prompt(frozen, candidates, known):
    return ('你是原文无损分段规划器。一般每个候选句只需一个单元，只有多个独立先后画面或两行字幕过长才进一步细分。'
            'context_sources不是本单元原文的出处，它只能用于补全省略或指代，引用此前已经完成的其他speech单元。'
            '明确写出的主体/动作/地点直接填facts即可，不需要context_sources；无指代时context_sources和resolved_references均为[]。'
            '严禁在context_sources引用当前单元自身、当前候选的尚未完成部分或未来单元。'
            'text_end为全文绝对字符位置，每候选的数组必须严格递增，末项等于候选end；不生成新的text字段。'
            '例如无指代单句只有一项，其facts可为'
            '{"subject":null,"action_or_state":null,"setting":null,"quantity":null,"negation":null,'
            '"relation_or_order":null,"context_sources":[],"resolved_references":[]}；有明确原文信息时填对应字符串。\n'
            'Split each candidate losslessly into original ranges with one visual meaning. '
            'Return ONLY the fixed-key JSON schema. Do not rewrite text, join candidates or invent events. '
            'text_end is an absolute Python Unicode character offset; final end must equal candidate.end. '
            'Use null for unspecified facts; context sources can only be complete prior finalized speech units. '
            'Keep each piece short enough for two subtitle lines. No human review has been performed.\nINPUT_JSON\n' +
            json.dumps(dict(decoded_text=frozen.script.text, candidates=thaw(candidates),
                            known_spans=thaw(known)), ensure_ascii=False))


def _check_intent(path, *, frozen, uid, schema, prompt, candidates):
    data = read_json(Path(path))
    object_fields(data, ('request_id', 'body', 'schema', 'prompt', 'context'), 'Ollama intent')
    context = data['context']
    object_fields(context,('client_id','script_identity','candidate_ranges'),'Ollama intent context')
    if (data['request_id'] != uid or data['schema'] != schema or data['prompt'] != prompt or
        context['script_identity'] != frozen.options['execution_policy']['input_identities']['script'] or
        context['candidate_ranges'] != [dict(unit_id=s.unit_id,start=s.start,end=s.end) for s in candidates]):
        raise ProductionRefused(f'{uid}: frozen Ollama intent differs')
    expected=[ollama_body(prompt,schema,cpu_only=frozen.options['cpu_planner'],units_coverage=mode)
              for mode in (False,True)]
    if json.dumps(data['body'],sort_keys=True,allow_nan=False) not in [json.dumps(body,sort_keys=True,allow_nan=False) for body in expected]:
        raise ProductionRefused(f'{uid}: original Ollama body differs from frozen request')
    return data


def produce_units(frozen, *, state, manifest, paths, logger):
    settings = CompositionSettings()
    with PrivateFont(frozen.config.media.font_file, settings.font_name, settings.font_size) as font:
        return _produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger,
                              settings=settings, measure=font.measure)


def _produce_units(frozen, *, state, manifest, paths, logger, settings, measure):
    report = read_report(state, 'units')
    complete = state.snapshot()['stages']['units']['status'] == 'completed'
    if report and complete:
        validate_production_units(report['payload'], measure=measure, composition_settings=settings)
        if report['payload']['decoded_text']!=frozen.script.text or report['payload']['has_bom']!=frozen.script.has_bom:
            raise ProductionRefused('completed units differ from frozen source text')
    if complete and report is None: raise ProductionRefused('units cursor has no report')
    if not complete: state.start_stage('units'); check_stage_space(frozen.config)
    speech = [s for s in frozen.script.spans if s.kind == 'speech']
    known = []; specs = {}; batches = []; request_paths = []
    manager = ServiceManager(paths, manifest, logger); handle = None
    planner = OllamaPlanner(HttpClient(frozen.config.services['ollama'],
        frozen.options['execution_policy']['ollama_request_seconds'],logger),cpu_only=frozen.options['cpu_planner'])
    try:
        for index, start in enumerate(range(0, len(speech), 8), 1):
            candidates = tuple(speech[start:start+8]); bid = f'units_batch_{index:04d}'
            schema = make_units_schema(candidates, tuple(known)); prompt = _prompt(frozen,candidates,known)
            request_ids = []; last_error = None; batch_result = None
            for suffix in ('initial', 'correction'):
                uid = bid+'_'+suffix; request_ids.append(uid)
                current_prompt = prompt if suffix == 'initial' else prompt+'\nCORRECTION\n'+str(last_error)+(
                    '\n重新输出完整的固定键对象，仅修正上述格式/结构错误。不要为修正来源而新增不必要的细分。'
                    '若context_sources引用本单元自身或无可用前序来源，改为[]；无指代resolved_references也为[]。')
                cp = recover_checkpoint(state,'units',uid)
                if cp:
                    intent = _check_intent(cp['request']['intent_path'],frozen=frozen,uid=uid,schema=schema,
                                           prompt=current_prompt,candidates=candidates)
                    if intent['context']['client_id'] != cp['request']['client_id']: raise ProductionRefused('Ollama client identity differs')
                    raw,_,original_evidence=recover_http(logger,uid=uid,
                        url=frozen.config.services['ollama']+'/api/generate',payload=intent['body'])
                    original_error=None;original_content=None
                    try:
                        original_content=parse_completed_response(strict_json(raw),schema=schema,request_id=uid,evidence_paths=original_evidence)
                        original_result=apply_units_proposal(frozen.script,candidates,original_content,known_spans=tuple(known),
                                                            measure=measure,composition_settings=settings)
                    except (OllamaFormatError,ValueError) as exc: original_error=str(exc)
                    payload=cp['payload']
                    if (payload['format_valid'] != (original_error is None) or
                        original_error is not None and payload['error']!=original_error or
                        original_error is None and payload['proposal']!=original_content):
                        raise ProductionRefused('unit checkpoint differs from original completed model response')
                    request_paths.extend(cp['request']['response_paths'])
                    payload = cp['payload']
                    if not payload['format_valid']:
                        last_error = payload['error']
                        if suffix == 'correction': raise RuntimeError(last_error)
                        continue
                    try:
                        batch_result = apply_units_proposal(frozen.script,candidates,payload['proposal'],known_spans=tuple(known),
                                                            measure=measure,composition_settings=settings)
                    except ValueError as exc: raise ProductionRefused('saved unit proposal differs from valid checkpoint') from exc
                    break
                if complete: raise ProductionRefused('completed units lack original request checkpoints')
                record = state.snapshot()['units'].get('units',{}).get(uid)
                intent_path = logger.path(f'storyboard/{uid}.intent.json')
                content = None; format_error = None
                if record and record['request'] or intent_path.exists():
                    intent = _check_intent(intent_path,frozen=frozen,uid=uid,schema=schema,prompt=current_prompt,candidates=candidates)
                    req = dict(state='intent',intent_path=str(intent_path),client_id=intent['context']['client_id'],prompt_id=None,response_paths=[])
                    if record is None: state.record_unit('units',uid,status='running',request=req)
                    else:
                        req = record['request']
                        if req is None or req['client_id'] != intent['context']['client_id'] or req['intent_path'] != str(intent_path):
                            raise ProductionRefused('Ollama intent/state association differs')
                    try: raw, meta, evidence = recover_http(logger,uid=uid,url=frozen.config.services['ollama']+'/api/generate',payload=intent['body'])
                    except AdapterError as exc: mark_request_error(state,'units',uid,exc)
                    media = next((v for k,v in meta['headers'].items() if k.lower()=='content-type'),'').split(';')[0]
                    if media != 'application/json' and not media.endswith('+json'): raise ProductionRefused('unknown Ollama JSON response')
                    try: outer = strict_json(raw)
                    except ValueError as exc: raise ProductionRefused('unknown Ollama outer response') from exc
                    try: content = parse_completed_response(outer,schema=schema,request_id=uid,evidence_paths=evidence)
                    except OllamaFormatError as exc: format_error = exc
                    except AdapterError as exc: mark_request_error(state,'units',uid,exc)
                else:
                    if handle is None:
                        try: occupied=port_listening(frozen.config.services['ollama'],3)
                        except ServiceConflictError as exc: raise ProductionRefused(str(exc)) from exc
                        if occupied: raise ProductionRefused(f'external service listening at {frozen.config.services["ollama"]}')
                        try: handle = manager.ensure(build_service_specs(frozen.config,state.run_dir,production=True,frozen=frozen,store=manifest)['ollama'])
                        except ServiceConflictError as exc: raise ProductionRefused(str(exc)) from exc
                        if not handle.owned: raise ProductionRefused(f'external Ollama service: {handle.url}')
                    client_id = uuid4().hex
                    context = dict(client_id=client_id,script_identity=frozen.options['execution_policy']['input_identities']['script'],
                                   candidate_ranges=[dict(unit_id=s.unit_id,start=s.start,end=s.end) for s in candidates])
                    def on_intent(path, body):
                        state.record_unit('units',uid,status='running',request=dict(state='intent',intent_path=str(path),
                            client_id=client_id,prompt_id=None,response_paths=[]))
                    try:
                        import sys
                        print(f'[make-video] units {bid} {suffix}: Ollama',file=sys.stderr,flush=True)
                        content = planner.generate(current_prompt,schema=schema,request_id=uid,intent_context=context,on_intent=on_intent)
                    except OllamaFormatError as exc: format_error = exc
                    except AdapterError as exc: mark_request_error(state,'units',uid,exc)
                    req = state.snapshot()['units']['units'][uid]['request']
                    intent = read_json(intent_path)
                    _, _, evidence = recover_http(logger,uid=uid,url=frozen.config.services['ollama']+'/api/generate',payload=intent['body'])
                evidence = list(dict.fromkeys([str(intent_path),*evidence,*[str(p) for p in logger.path('storyboard').glob(uid+'.*.json')]]))
                if format_error is None:
                    try:
                        batch_result = apply_units_proposal(frozen.script,candidates,content,known_spans=tuple(known),
                                                            measure=measure,composition_settings=settings)
                    except ValueError as exc: format_error = exc
                if format_error is not None:
                    last_error = str(format_error)
                    payload = dict(format_valid=False,proposal=None,error=last_error)
                else: payload = dict(format_valid=True,proposal=content,error=None)
                req = dict(req,response_paths=evidence)
                commit_checkpoint(state,'units',uid,request=req,outputs=stamps({f'evidence_{i}':p for i,p in enumerate(evidence)}),payload=payload)
                request_paths.extend(evidence)
                if format_error is None: break
                if suffix == 'correction': raise RuntimeError(f'{bid}: second completed response invalid: {last_error}')
            batch_spans,batch_specs = batch_result
            known.extend(s for s in batch_spans if s.kind == 'speech'); specs.update(batch_specs)
            batches.append(dict(batch_id=bid,candidate_ids=[s.unit_id for s in candidates],request_ids=request_ids))
        spans = sorted([s for s in frozen.script.spans if s.kind=='skip']+known,key=lambda s:s.start)
        payload = dict(decoded_text=frozen.script.text,has_bom=frozen.script.has_bom,spans=thaw(spans),semantic_specs=specs,
                       planner=dict(model='qwen3:8b',request_paths=list(dict.fromkeys(request_paths)),batches=batches))
        validate_production_units(payload,measure=measure,composition_settings=settings)
        if report and report['payload'] != payload: raise ProductionRefused('immutable units report differs from original checkpoints')
        if not report: state.write_report('units',payload,input_records=stamps({'script':frozen.options['script_path']}))
        if not complete: state.complete_stage('units')
        logger.event('units',None,'completed',dict(speech_units=len(known),batches=len(batches)))
        return payload
    finally: stop_owned_preserving_exception(manager,handle,logger,'units')


def produce_storyboard(frozen, units, timeline, slot_plan, *, state, manifest, paths, logger):
    # Keep units service dependencies shared; the visual batching implementation
    # has its own report/schema recovery boundary.
    from .production_visual_storyboard import produce
    return produce(frozen,units,timeline,slot_plan,state=state,manifest=manifest,paths=paths,logger=logger,
                   manager_factory=ServiceManager,port_probe=port_listening)
