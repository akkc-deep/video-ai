"""Small, source-bound model decisions for missing environment references."""
from contextlib import contextmanager,ExitStack
from copy import deepcopy
import json

from ..adapters.common import HttpClient,strict_json
from ..adapters.ollama import OllamaPlanner, OllamaFormatError, ollama_body, parse_completed_response
from ..config import read_json,parse_scene_planner_model
from ..planning.production_scenes import canonical_digest
from .manifest import ManifestStore
from .owned_cleanup import stop_owned_preserving_exception
from .production_state import ProductionRefused
from .production_support import recover_http
from .service_specs import build_service_specs
from .services import ServiceManager, port_listening


def evidence_end(value):
    if isinstance(value,list):return max((evidence_end(v) for v in value),default=0)
    if not isinstance(value,dict):return 0
    return max([value.get('text_end',0),*(evidence_end(v) for v in value.values())])


def expand_sources(value,catalog,latest):
    if isinstance(value,list):return [expand_sources(v,catalog,latest) for v in value]
    if not isinstance(value,dict):return value
    result={}
    for key,item in value.items():
        if key in ('sources','change_sources'):
            if not isinstance(item,list) or any(not isinstance(uid,str) or uid not in catalog for uid in item):
                raise ValueError('environment repair has unknown source')
            if any(catalog[uid]['text_end']>latest for uid in item):raise ValueError('environment repair has future source')
            result[key]=[deepcopy(catalog[uid]) for uid in item]
        else:result[key]=expand_sources(item,catalog,latest)
    return result


def apply_decisions(proposal,decisions,indices,catalog):
    result=deepcopy(proposal)
    groups={g['key']:g for g in result['scene_groups']}
    expected={f'scene_{i+1:04d}' for i in indices}
    if set(decisions)!=expected:raise ValueError('environment repair lacks exact scene decisions')
    for index in indices:
        scene=result['scenes'][index]
        latest=catalog[scene['unit_ids'][-1]]['text_end']
        decision=decisions[f'scene_{index+1:04d}']
        if set(decision)=={'reuse','change_sources'}:
            key=decision['reuse']
            if key not in groups:raise ValueError('environment repair has unknown environment')
            if evidence_end(groups[key])>latest:raise ValueError('environment repair has future environment evidence')
            added=expand_sources({'change_sources':decision['change_sources']},catalog,latest)['change_sources']
            for source in added:
                if source not in scene['change_sources']:scene['change_sources'].append(source)
        elif set(decision)=={'new'}:
            key=f'environment_repair_{index+1:04d}'
            if key in groups:raise ValueError('environment repair key already exists')
            group=dict(expand_sources(decision['new'],catalog,latest),key=key)
            result['scene_groups'].append(group);groups[key]=group
        else:raise ValueError('environment repair decision shape differs')
        previous=result['scenes'][index-1]['scene_group_id'] if index else None
        if previous in groups and previous!=key:
            physical=('environment','time','lighting','spatial_relations')
            if ((any(groups[previous].get(k)!=groups[key].get(k) for k in physical)
                    or groups[previous].get('creative_choices')!=groups[key].get('creative_choices'))
                    and not scene['change_sources'] and not groups[key]['change_sources']):
                raise ValueError('environment repair changes physical state without source evidence')
        scene['scene_group_id']=key
    return result


def decision_schema(proposal,indices,catalog,group_schema):
    def citations(value,eligible):
        if isinstance(value,list):return [citations(v,eligible) for v in value]
        if not isinstance(value,dict):return value
        if value.get('type')=='object' and set(value.get('properties',{}))=={'unit_id','text_start','text_end','quote'}:
            return dict(type='string',enum=eligible)
        return {k:citations(v,eligible) for k,v in value.items()}
    slots={}
    for index in indices:
        latest=catalog[proposal['scenes'][index]['unit_ids'][-1]]['text_end']
        eligible=[uid for uid,row in catalog.items() if row['text_end']<=latest]
        keys=[g['key'] for g in proposal['scene_groups'] if evidence_end(g)<=latest]
        new=citations(deepcopy(group_schema),eligible)
        del new['properties']['key'];new['required'].remove('key')
        if index:new['properties']['change_sources']['minItems']=1
        variants=[dict(type='object',properties=dict(new=new),required=['new'],additionalProperties=False)]
        if keys:
            variants.insert(0,dict(type='object',properties=dict(reuse=dict(type='string',enum=keys),
                change_sources=dict(type='array',items=dict(type='string',enum=eligible),uniqueItems=True)),
                required=['reuse','change_sources'],additionalProperties=False))
        slots[f'scene_{index+1:04d}']=dict(anyOf=variants)
    return dict(type='object',properties=slots,required=list(slots),additionalProperties=False)


@contextmanager
def repair_planner(frozen,run,paths,logger,planner):
    if planner is not None:
        yield planner
        return
    manifest=ManifestStore.open(run,verify_integrity=False)
    manager=ServiceManager(paths,manifest,logger);handle=None
    try:
        if port_listening(frozen.config.services['ollama'],3):raise ProductionRefused('external scene repair service')
        handle=manager.ensure(build_service_specs(frozen.config,run,production=True,frozen=frozen,
            store=manifest,planner_transport='llama_direct')['ollama'])
        if not handle.owned:raise ProductionRefused('external scene repair service')
        yield OllamaPlanner(HttpClient(frozen.config.services['ollama'],
            frozen.options['execution_policy']['ollama_request_seconds'],logger),
            cpu_only=frozen.options['cpu_planner'],model=frozen.config.raw.get('scene_planner_model','qwen3:8b'))
    finally:stop_owned_preserving_exception(manager,handle,logger,'scene_environment_repair')


def repair_environment_links(proposal,*,frozen,units,schema,store,folder,logger,paths,planner):
    known={g['key'] for g in proposal['scene_groups']}
    indices=[i for i,s in enumerate(proposal['scenes']) if s['scene_group_id'] not in known]
    if not indices:return proposal
    catalog={s['unit_id']:dict(unit_id=s['unit_id'],text_start=s['start'],text_end=s['end'],quote=s['text'])
             for s in units['spans'] if s['kind']=='speech'}
    result=deepcopy(proposal);identity=canonical_digest(proposal)
    count=(len(indices)+15)//16
    model=parse_scene_planner_model(frozen.config.raw.get('scene_planner_model','qwen3:8b'))
    with ExitStack() as service_stack:
        client=planner
        for number,start in enumerate(range(0,len(indices),16),1):
            selected=indices[start:start+16]
            batch_schema=decision_schema(result,selected,catalog,schema['properties']['scene_groups']['items'])
            context=dict(original_proposal_sha256=identity,current_proposal_sha256=canonical_digest(result),
                source_sha256=frozen.options['execution_policy']['input_identities']['script']['sha256'],
                full_original_text=frozen.script.text,source_units=list(catalog.values()),
                declared_environments=result['scene_groups'],
                scenes={f'scene_{i+1:04d}':result['scenes'][i] for i in selected})
            prompt=('Repair ONLY missing environment references. Preserve all scene descriptions and narration. '
                'Use the ENTIRE original text for meaning. Explicitly choose a declared physical environment if it fits, '
                'or define a new physical environment with current/prior original-source evidence. '
                'Do not assume a missing key means the only existing setting. Source citations are original unit IDs. '
                'Changing the physical environment requires change_sources. New factual claims require source_facts; '
                'creative visual choices must be labelled creative_choices. Return only the required scene decisions.\n'
                +json.dumps(context,ensure_ascii=False,separators=(',',':')))
            batch=folder/f'batch_{number:04d}';last_error=None
            print(f'[scene-plan] environment repair {number}/{count}',flush=True)
            for suffix in ('initial','correction'):
                current=prompt if suffix=='initial' else prompt+'\nCORRECTION\n'+last_error
                uid=f'scene_plan_environment_repair_{identity[:12]}_{number:04d}_{suffix}'
                intent_path=batch/(suffix+'.intent.json')
                body=ollama_body(current,batch_schema,cpu_only=frozen.options['cpu_planner'],scene_planning=True,
                    model=model,scene_local_repair=True)
                if intent_path.exists():
                    intent=read_json(intent_path)
                    if intent.get('body')!=body or intent.get('context')!=context or intent.get('request_id')!=uid:
                        raise ProductionRefused('environment repair original intent differs')
                else:
                    intent=dict(request_id=uid,body=body,context=context)
                    store.save(intent_path,intent);store.owned()
                    if client is None:client=service_stack.enter_context(repair_planner(frozen,store.run,paths,logger,None))
                    try:client.generate(current,schema=batch_schema,request_id=uid)
                    except OllamaFormatError:pass
                raw,_,evidence=recover_http(logger,uid=uid,url=frozen.config.services['ollama'].rstrip('/')+'/api/generate',payload=body)
                try:
                    decisions=parse_completed_response(strict_json(raw),schema=batch_schema,request_id=uid,
                        evidence_paths=evidence,expected_model=model)
                    updated=apply_decisions(result,decisions,selected,catalog)
                except (OllamaFormatError,ValueError) as exc:
                    last_error=str(exc)
                    if suffix=='correction':raise ProductionRefused('environment repair failed: '+last_error) from exc
                    continue
                store.save(batch/'accepted.json',dict(request_id=uid,context_sha256=canonical_digest(context),
                    decisions=decisions,evidence_paths=evidence,proposal_sha256=canonical_digest(updated)))
                result=updated
                break
    return result
