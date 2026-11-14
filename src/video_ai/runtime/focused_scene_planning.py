"""Recoverable small visual requests with program-owned source bindings."""
from contextlib import ExitStack
import hashlib

from ..adapters.common import strict_json
from ..adapters.ollama import OllamaFormatError, ollama_body, parse_completed_response
from ..config import parse_scene_planner_model, read_json
from ..planning.focused_scenes import source_slices, focus_request, merge_focus, partition_request
from ..planning.production_scenes import canonical_digest, paragraphs_from_script
from ..planning.storyboard import _schema_check
from .production_state import ProductionRefused
from .production_support import recover_http
from .scene_environment_repair import repair_planner


def boundary(point):
    """Durable boundaries for recovery tests."""


def use_focused_transport(folder, script, transport=None):
    if (folder/'focused-v1').exists(): return True
    # Never supersede an existing submission, including a completed proposal.
    if any(folder.rglob('*.intent.json')) or (folder.parent/'scene-plan-commit.json').exists(): return False
    return transport=='focused_v1' or len([line for line in script.text.splitlines() if line.strip()]) >= 8


def _request_batch(*, prompt, wire, context, batch, prefix, model, frozen, logger, store, get_client, normalize):
    last_error=None
    def make_body(current):
        return ollama_body(current,wire,cpu_only=frozen.options['cpu_planner'],
            scene_planning=True,model=model,scene_local_repair=True,
            scene_output_limit=16384 if prefix.startswith(('scene_plan_focused_visual3_','scene_plan_focused_visual4_')) else None)
    for suffix in ('initial','correction'):
        current=prompt if suffix=='initial' else prompt+'\nCORRECTION\n'+last_error
        uid=prefix+'_'+suffix
        body=make_body(current)
        intent=dict(request_id=uid,body=body,context=context)
        path=batch/(suffix+'.intent.json')
        if path.exists():
            if read_json(path)!=intent:raise ProductionRefused('focused scene original intent differs')
        else:
            store.save(path,intent);boundary('intent');store.owned()
            def on_intent(path,actual):
                store.owned()
                if actual!=body:raise ProductionRefused('focused planner changed original request')
            try:get_client().generate(current,schema=wire,request_id=uid,on_intent=on_intent)
            except OllamaFormatError:pass
        raw,_,evidence=recover_http(logger,uid=uid,
            url=frozen.config.services['ollama'].rstrip('/')+'/api/generate',payload=body)
        response_sha=hashlib.sha256(raw).hexdigest()
        store.save(batch/(suffix+'.response.json'),dict(request_id=uid,response_sha256=response_sha,evidence_paths=evidence))
        boundary('response');store.owned()
        outer=strict_json(raw)
        if not isinstance(outer,dict) or outer.get('done') is not True or outer.get('done_reason')=='length':
            raise ProductionRefused('focused scene original response incomplete; no POST retry')
        correction=batch/'correction.intent.json'
        if suffix=='initial' and correction.exists():
            # Prefer an already submitted correction even when a lossless
            # decoder fix would now admit the earlier response. Preserve its
            # exact saved feedback; the next loop verifies the complete body.
            saved=read_json(correction)['body']['prompt']
            sentinel='__VIDEO_AI_SAVED_CORRECTION_REASON__'
            template=make_body(prompt+'\nCORRECTION\n'+sentinel)['prompt']
            if template.count(sentinel)!=1:raise ProductionRefused('ambiguous correction feedback template')
            head,tail=template.split(sentinel)
            if not saved.startswith(head) or tail and not saved.endswith(tail):
                raise ProductionRefused('focused scene correction source prompt differs')
            last_error=saved[len(head):len(saved)-len(tail) if tail else None]
            continue
        try:
            content=parse_completed_response(outer,schema=wire,request_id=uid,evidence_paths=evidence,expected_model=model)
            updated=normalize(content)
        except (OllamaFormatError,ValueError) as exc:
            last_error=str(exc)
            if suffix=='correction':raise ProductionRefused('focused scene correction failed: '+last_error) from exc
            continue
        store.save(batch/'accepted.json',dict(context_sha256=canonical_digest(context),request_id=uid,
            response_sha256=response_sha,content=content,proposal_sha256=canonical_digest(updated)))
        boundary('accepted')
        return updated


def _retire_invalid_catalog_visuals(folder,*,frozen,logger,store):
    legacy=sorted(folder.glob('batch_*'))
    if not legacy:return
    if len(legacy)!=1 or legacy[0].name!='batch_0001' or (legacy[0]/'accepted.json').exists():
        raise ProductionRefused('prior catalog visual transport must be recovered in its original version')
    path=legacy[0]/'correction.intent.json'
    if not path.exists():raise ProductionRefused('prior visual correction outcome must be resolved first')
    intent=read_json(path)
    if intent['context']['prior_proposal_sha256']!=canonical_digest(None):
        raise ProductionRefused('prior visual transport has accepted upstream content')
    raw,_,evidence=recover_http(logger,uid=intent['request_id'],
        url=frozen.config.services['ollama'].rstrip('/')+'/api/generate',payload=intent['body'])
    outer=strict_json(raw)
    if not isinstance(outer,dict) or outer.get('done') is not True or outer.get('done_reason')=='length':
        raise ProductionRefused('prior visual correction outcome is incomplete')
    content=parse_completed_response(outer,schema=intent['body']['format'],request_id=intent['request_id'],
        evidence_paths=evidence,expected_model=intent['body']['model'])
    known={row['key'] for row in content['scene_groups']}
    invalid={key:row['scene_group_id'] for key,row in content['scenes'].items() if row['scene_group_id'] not in known}
    if not invalid:raise ProductionRefused('prior visual correction is not a confirmed invalid environment result')
    store.save(folder/'catalog-visuals-retired.json',dict(schema_version=1,
        reason='completed correction references undeclared environments; use inline environment transport',
        request_id=intent['request_id'],body_sha256=canonical_digest(intent['body']),
        response_sha256=hashlib.sha256(raw).hexdigest(),invalid_environments=invalid,evidence_paths=evidence))


def require_retired_visual_v2(folder,*,frozen,logger):
    old=folder/'visual-v2'
    if not old.exists():return
    marker=old/'retired.json'
    if not marker.is_file() or (old/'proposal.json').exists():
        raise ProductionRefused('prior visual-v2 requires explicit terminal local-failure retirement')
    record=read_json(marker)
    pending=[batch for batch in sorted(old.glob('batch_*')) if not (batch/'accepted.json').exists()]
    if len(pending)!=1:raise ProductionRefused('prior visual-v2 unresolved batch coverage differs')
    path=pending[0]/('correction.intent.json' if (pending[0]/'correction.intent.json').exists() else 'initial.intent.json')
    intent=read_json(path)
    if (record.get('request_id')!=intent['request_id'] or record.get('body_sha256')!=canonical_digest(intent['body'])
            or not isinstance(record.get('reason'),str) or not record['reason'].strip()):
        raise ProductionRefused('prior visual-v2 retirement differs from original intent')
    matches=[]
    url=frozen.config.services['ollama'].rstrip('/')+'/api/generate'
    for path in logger.path('http').glob('*.request.json'):
        req=read_json(path)
        if req.get('unit_id')==intent['request_id'] and req.get('method')=='POST':
            if req.get('url')!=url or req.get('json_body')!=intent['body']:
                raise ProductionRefused('prior visual-v2 HTTP request identity differs')
            matches.append(path)
    if len(matches)!=1:raise ProductionRefused('prior visual-v2 original HTTP evidence missing or duplicated')
    path=matches[0];stem=path.name.removesuffix('.request.json')
    meta=read_json(path.with_name(stem+'.response.json'));raw=path.with_name(stem+'.body').read_bytes()
    expected=dict(method='POST',url=url,unit_id=intent['request_id'],status=500,bytes=len(raw),truncated=False,error=None)
    if any(meta.get(key)!=value for key,value in expected.items()):
        raise ProductionRefused('prior visual-v2 original request is not a complete local failure')
    error=strict_json(raw).get('error')
    if (not isinstance(error,str) or not error.startswith('ConnectionResetError:')
            or record.get('response_sha256')!=hashlib.sha256(raw).hexdigest()):
        raise ProductionRefused('prior visual-v2 local termination evidence differs')


def _retire_invalid_subject_catalog(folder,*,frozen,logger,store):
    old=folder/'visual-v3'
    if not old.exists():return
    batches=sorted(old.glob('batch_*'))
    if len(batches)!=1 or (batches[0]/'accepted.json').exists() or (old/'proposal.json').exists():
        raise ProductionRefused('prior subject catalog transport must be recovered in its original version')
    intent=read_json(batches[0]/'correction.intent.json')
    if intent['context']['prior_proposal_sha256']!=canonical_digest(None):
        raise ProductionRefused('prior subject catalog has accepted upstream content')
    raw,_,evidence=recover_http(logger,uid=intent['request_id'],
        url=frozen.config.services['ollama'].rstrip('/')+'/api/generate',payload=intent['body'])
    outer=strict_json(raw)
    if not isinstance(outer,dict) or outer.get('done') is not True or outer.get('done_reason')=='length':
        raise ProductionRefused('prior subject correction response incomplete')
    content=parse_completed_response(outer,schema=intent['body']['format'],request_id=intent['request_id'],
        evidence_paths=evidence,expected_model=intent['body']['model'])
    entities={row['key'] for row in content['entities']};variants={row['key'] for row in content['appearance_variants']}
    invalid={key:dict(entities=sorted(set(row['entity_ids'])-entities),variants=sorted(set(row['variant_ids'])-variants))
        for key,row in content['scenes'].items() if set(row['entity_ids'])-entities or set(row['variant_ids'])-variants}
    if not invalid:raise ProductionRefused('prior subject catalog is not a confirmed invalid result')
    store.save(old/'retired.json',dict(schema_version=1,request_id=intent['request_id'],
        reason='completed correction references undeclared subjects; use inline subject declarations',
        body_sha256=canonical_digest(intent['body']),response_sha256=hashlib.sha256(raw).hexdigest(),
        invalid_subjects=invalid,evidence_paths=evidence))


def produce_focused_proposal(*, frozen, script, units, schema, settings, folder, identity, paths, logger, store, planner=None):
    model=parse_scene_planner_model(frozen.config.raw.get('scene_planner_model','qwen3:8b'))
    with ExitStack() as stack:
        client=planner
        def get_client():
            nonlocal client
            if client is None:
                if not (store.run/'manifest.json').exists():
                    from .manifest import create_manifest,hash_file
                    from pathlib import Path
                    create_manifest(store.run,frozen.config,inputs={'script':hash_file(Path(frozen.options['script_path']))},
                        models={},workflows={},verify_integrity=False)
                client=stack.enter_context(repair_planner(frozen,store.run,paths,logger,None))
            return client
        paragraphs=[p for p in paragraphs_from_script(script) if p['unit_ids']]
        partitions={}
        for number,start in enumerate(range(0,len(paragraphs),6),1):
            selected=paragraphs[start:start+6]
            prompt,wire=partition_request(script,settings,selected)
            context=dict(identity=identity,paragraphs=selected,model=model)
            print(f'[scene-plan] source boundaries {number}/{(len(paragraphs)+5)//6}',flush=True)
            def normalize(content):
                _schema_check(content,wire)
                return {key:row['end_units'] for key,row in content.items()}
            partitions.update(_request_batch(prompt=prompt,wire=wire,context=context,
                batch=folder/'partition'/f'batch_{number:04d}',prefix=f'scene_plan_focused_partition_{number:04d}',
                model=model,frozen=frozen,logger=logger,store=store,get_client=get_client,normalize=normalize))
        slices=source_slices(script,settings,partitions)
        _retire_invalid_catalog_visuals(folder,frozen=frozen,logger=logger,store=store)
        require_retired_visual_v2(folder,frozen=frozen,logger=logger)
        _retire_invalid_subject_catalog(folder,frozen=frozen,logger=logger,store=store)
        return _describe_slices(frozen=frozen,script=script,units=units,schema=schema,slices=slices,
            folder=folder/'visual-v4',identity=identity,logger=logger,store=store,model=model,get_client=get_client)


def _describe_slices(*,frozen,script,units,schema,slices,folder,identity,logger,store,model,get_client):
    # Keep complete paragraphs together, up to three per request.
    batches = []
    current = []
    paragraphs = []
    for source in slices:
        pid = source['paragraph_id']
        if pid not in paragraphs:
            if len(paragraphs) == 3:
                batches.append(current); current = []; paragraphs = []
            paragraphs.append(pid)
        current.append(source)
    if current: batches.append(current)
    result = None
    for number, selected in enumerate(batches, 1):
        prompt,wire=focus_request(script,units,schema,selected,result)
        context=dict(identity=identity,prior_proposal_sha256=canonical_digest(result),fixed_scenes=selected,model=model)
        print(f'[scene-plan] source-bound batch {number}/{len(batches)} ({len(selected)} scenes)',flush=True)
        result=_request_batch(prompt=prompt,wire=wire,context=context,batch=folder/f'batch_{number:04d}',
            prefix=f'scene_plan_focused_visual4_{number:04d}',model=model,frozen=frozen,logger=logger,store=store,
            get_client=get_client,normalize=lambda content:merge_focus(result,content,selected,wire,script,units))
    store.save(folder/'proposal.json', dict(identity=identity, proposal=result))
    return result
