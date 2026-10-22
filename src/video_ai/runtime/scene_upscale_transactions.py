"""Immutable schema-2 scene submissions and GET-only original-task recovery."""
import hashlib
import math
from datetime import datetime
from pathlib import Path
import time
from threading import Event
from uuid import UUID, uuid4

from ..adapters.common import AdapterError, JSON_LIMIT, positive_timeout, strict_json
from ..adapters.scene_comfy import prompt_payload
from ..planning.production_scenes import canonical_digest
from .manifest import now
from .production_comfy import metadata, matches, output_from_history
from .production_state import ProductionRefused, object_fields, run_path, timestamp


class SceneSubmitUnknown(RuntimeError):
    """Durable intent exists; only the original task may be queried again."""


class SceneFrameTerminal(ProductionRefused):
    """A definitive original verdict proved by retained protocol bytes, with or without its index."""
    def __init__(self,terminal):
        self.terminal=terminal
        super().__init__('original scene submission terminal: '+terminal['status']+': '+terminal['reason'])


_INTENT='schema_version run_id frame_id request_sha256 graph_sha256 input_sha256 attempt_id client_id output_prefix created_at'.split()
_ACCEPTED='schema_version run_id frame_id intent_sha256 prompt_id number acceptance_evidence'.split()
_SUBMISSION='schema_version run_id frame_id intent_sha256 accepted_sha256 prompt_id history_evidence output'.split()
_HTTP_REQUEST='schema_version run_id frame_id intent_sha256 method route body_sha256 started_at'.split()
_HTTP_RESPONSE='schema_version run_id frame_id request_sha256 status headers body finished_at error'.split()
_REQUEST='schema_version production_strategy run_id frame_id clip_id scene_id inputs_sha256 clip_sha256 observation_acceptance_sha256 mapping source input input_copy parameters graph_sha256'.split()
_TERMINAL='schema_version run_id frame_id intent_sha256 status evidence reason'.split()


def _uuid(value):
    try: valid=isinstance(value,str) and str(UUID(value))==value
    except ValueError: valid=False
    if not valid: raise ProductionRefused('expected canonical UUID')


def _identity(value, fields, request, label):
    object_fields(value,fields,label)
    if type(value['schema_version']) is not int or value['schema_version']!=2 or value['run_id']!=request['run_id'] or value['frame_id']!=request['frame_id']:
        raise ProductionRefused(label+' identity differs')


def _digest_equal(a,b,label):
    if canonical_digest(a)!=canonical_digest(b): raise ProductionRefused(label+' differs')


def _prefix(request): return request['run_id']+'/scene_upscale/'+request['clip_id']+'/'+request['frame_id'].split(':')[1]+'/attempt_0001'


def _body_artifact(store,path):
    """Raw HTTP alone may be empty; media Artifacts remain strictly positive."""
    path=run_path(store.run_dir,path); raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def _parse(row):
    response=row['response']
    if response['error'] is not None or response['status']!=200: return None
    media=next((v for k,v in response['headers'].items() if k.lower()=='content-type'),'').split(';')[0].strip().lower()
    if media!='application/json' and not media.endswith('+json'): return None
    try: return strict_json(row['raw'])
    except (ValueError,UnicodeError): return None


def _http_rows(store,request,intent):
    rows=[]; folder=store.frame_dir(request['frame_id'])/'http'; digest=canonical_digest(intent); posts=0
    requests={path.name.removesuffix('.request.json') for path in folder.glob('*.request.json')}
    for suffix in ('.response.json','.body'):
        for path in folder.glob('*'+suffix):
            token=path.name.removesuffix(suffix); _uuid(token)
            if token not in requests: raise ProductionRefused('orphan original HTTP response/body lacks request proof')
    for rp in sorted(folder.glob('*.request.json')):
        token=rp.name.removesuffix('.request.json'); _uuid(token)
        value=store.read(rp); _identity(value,_HTTP_REQUEST,request,'HTTP request'); timestamp(value['started_at'])
        if value['intent_sha256']!=digest: raise ProductionRefused('HTTP intent differs')
        method,route=value['method'],value['route']
        if method=='POST':
            posts+=1
            if posts>1: raise ProductionRefused('multiple POST records for one original intent')
            expected=hashlib.sha256(prompt_payload(store.read(store.frame_dir(request['frame_id'])/'graph.json'),intent['client_id'])).hexdigest()
            if route!='/prompt' or value['body_sha256']!=expected: raise ProductionRefused('original POST payload differs')
        elif method=='GET':
            if value['body_sha256'] is not None or route not in ('/queue','/history','/history/'+(store.read(store.frame_dir(request['frame_id'])/'accepted.json') or {}).get('prompt_id','')):
                # Original known-ID history is also valid before accepted.json is restored.
                if not (value['body_sha256'] is None and isinstance(route,str) and route.startswith('/history/') and _valid_uuid(route[9:])):
                    raise ProductionRefused('invalid scene GET route')
        else: raise ProductionRefused('invalid scene HTTP method')
        mp=rp.with_name(token+'.response.json'); response=store.read(mp)
        if response is None: continue
        _identity(response,_HTTP_RESPONSE,request,'HTTP response'); timestamp(response['finished_at'])
        if response['request_sha256']!=canonical_digest(value): raise ProductionRefused('HTTP request digest differs')
        if response['status'] is not None and (type(response['status']) is not int or not 100<=response['status']<=599): raise ProductionRefused('invalid HTTP status')
        if not isinstance(response['headers'],dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in response['headers'].items()): raise ProductionRefused('invalid HTTP headers')
        if response['error'] is not None:
            object_fields(response['error'],('kind','message'),'HTTP error')
            if any(not isinstance(v,str) or not v for v in response['error'].values()): raise ProductionRefused('invalid HTTP error')
        object_fields(response['body'],('path','bytes','sha256'),'HTTP body Artifact')
        bp=run_path(store.run_dir,response['body']['path'])
        if type(response['body']['bytes']) is not int or response['body']['bytes']<0 or _body_artifact(store,bp)!=response['body']: raise ProductionRefused('HTTP body Artifact differs')
        if Path(bp)!=rp.with_name(token+'.body'): raise ProductionRefused('HTTP body path differs')
        raw=Path(bp).read_bytes()
        if len(raw)>JSON_LIMIT: raise ProductionRefused('HTTP response exceeds 32MiB')
        rows.append(dict(request=value,response=response,raw=raw,evidence=store.artifact(mp)))
    return sorted(rows,key=lambda row:datetime.fromisoformat(row['request']['started_at']))


def _valid_uuid(value):
    try: _uuid(value); return True
    except ProductionRefused: return False


def _load(store,request,graph,*,allow_terminal=False):
    object_fields(request,_REQUEST,'scene request')
    if type(request['schema_version']) is not int or request['schema_version']!=2 or request['production_strategy']!='paragraph_jimeng_v1': raise ProductionRefused('invalid scene request identity')
    if canonical_digest(graph)!=request['graph_sha256']: raise ProductionRefused('scene graph digest differs')
    directory=store.frame_dir(request['frame_id']); saved=store.read(directory/'request.json'); saved_graph=store.read(directory/'graph.json')
    if saved is not None: _digest_equal(saved,request,'saved request')
    if saved_graph is not None: _digest_equal(saved_graph,graph,'saved graph')
    intent=store.read(directory/'intent.json')
    if intent is None:
        if any(store.read(directory/name) is not None for name in ('accepted.json','submission.json','terminal.json')) or any((directory/'http').glob('*')):
            raise ProductionRefused('submission evidence has no original intent')
        return directory,None,None,[]
    if saved is None or saved_graph is None: raise ProductionRefused('intent has no original request/graph')
    _identity(intent,_INTENT,request,'intent'); timestamp(intent['created_at']); _uuid(intent['attempt_id']); _uuid(intent['client_id'])
    expected=dict(request_sha256=canonical_digest(request),graph_sha256=request['graph_sha256'],input_sha256=request['input_copy']['sha256'],
        output_prefix=_prefix(request))
    if any(intent[k]!=v for k,v in expected.items()): raise ProductionRefused('intent binding differs')
    terminal=store.read(directory/'terminal.json')
    if terminal is not None:
        _identity(terminal,_TERMINAL,request,'terminal')
        if terminal['intent_sha256']!=canonical_digest(intent) or terminal['status'] not in ('rejected','execution_failed','identity_conflict','invalid_media') or not isinstance(terminal['evidence'],list) or not isinstance(terminal['reason'],str) or not terminal['reason']: raise ProductionRefused('invalid terminal record')
        for artifact in terminal['evidence']: store.validate_artifact(artifact)
    rows=_http_rows(store,request,intent); accepted=store.read(directory/'accepted.json')
    if accepted is not None:
        _identity(accepted,_ACCEPTED,request,'accepted'); _uuid(accepted['prompt_id'])
        if accepted['intent_sha256']!=canonical_digest(intent) or type(accepted['number']) not in (int,float) or not math.isfinite(accepted['number']): raise ProductionRefused('invalid accepted identity')
        store.validate_artifact(accepted['acceptance_evidence'])
        selected=[row for row in rows if row['evidence']==accepted['acceptance_evidence']]
        if len(selected)!=1 or not _acceptance_matches(selected[0],intent,graph,accepted['prompt_id'],accepted['number']): raise ProductionRefused('accepted response does not prove original identity')
    if terminal is not None and not allow_terminal:
        raise SceneFrameTerminal(validate_scene_terminal(store,request,graph))
    return directory,intent,accepted,rows


def _acceptance_matches(row,intent,graph,pid,number):
    value=_parse(row)
    if not isinstance(value,dict): return False
    if row['request']['method']=='POST':
        return value.get('prompt_id')==pid and type(value.get('number')) in (int,float) and value['number']==number and value.get('node_errors')=={}
    saved=dict(client_id=intent['client_id'],prompt_id=pid,number=number)
    if row['request']['route']=='/queue': return any(matches(metadata(r),saved,graph) for k in ('queue_running','queue_pending') for r in value.get(k,[]))
    entry=value.get(pid)
    return isinstance(entry,dict) and matches(metadata(entry.get('prompt')),saved,graph)


def _post_rejected(row):
    if row['request']['method']!='POST' or row['response']['error'] is not None: return False
    try: value=strict_json(row['raw'])
    except (ValueError,UnicodeError): return False
    return isinstance(value,dict) and (400<=row['response']['status']<500 or bool(value.get('node_errors')))


def _saved(intent,accepted):
    return dict(client_id=intent['client_id'],prompt_id=accepted['prompt_id'] if accepted else None,number=accepted['number'] if accepted else None)


def _terminal(store,request,intent,status,reason,evidence):
    store.assert_owned()
    terminal=dict(schema_version=2,run_id=request['run_id'],frame_id=request['frame_id'],
        intent_sha256=canonical_digest(intent),status=status,evidence=evidence,reason=reason)
    store.write(store.frame_dir(request['frame_id'])/'terminal.json',terminal)
    raise SceneFrameTerminal(terminal)


def _accept(store,request,intent,pid,number,evidence):
    _uuid(pid)
    if type(number) not in (int,float) or not math.isfinite(number): raise ProductionRefused('invalid acceptance number')
    accepted=dict(schema_version=2,run_id=request['run_id'],frame_id=request['frame_id'],intent_sha256=canonical_digest(intent),
        prompt_id=pid,number=number,acceptance_evidence=evidence)
    store.assert_owned(); store.write(store.frame_dir(request['frame_id'])/'accepted.json',accepted)
    return accepted


def _history_candidates(rows,intent,accepted,graph):
    saved=_saved(intent,accepted); candidates={}; observed={}; evidence=[]; active=set(); queue_started=None; completed_outputs={}
    for row in rows:
        value=_parse(row)
        if not isinstance(value,dict) or row['request']['method']!='GET': continue
        route=row['request']['route']; evidence.append(row['evidence'])
        if route=='/queue':
            values=[]
            for k in ('queue_running','queue_pending'):
                if not isinstance(value.get(k),list): raise ProductionRefused('invalid queue rows')
                values.extend(value[k])
            active={r[1] for r in values if isinstance(r,list) and len(r)>1 and isinstance(r[1],str)}
            queue_started=datetime.fromisoformat(row['request']['started_at'])
            entries=[(r[1] if isinstance(r,list) and len(r)>1 else None,r,None) for r in values]
        else: entries=[(pid,entry.get('prompt') if isinstance(entry,dict) else None,entry) for pid,entry in value.items()]
        for pid,prompt,entry in entries:
            if isinstance(pid,str): observed.setdefault(pid,[]).append(metadata(prompt))
            meta=metadata(prompt)
            if matches(meta,saved,graph):
                if pid!=meta[0]: raise ProductionRefused('history key differs from original prompt')
                _uuid(pid); candidate=candidates.setdefault(pid,dict(meta=meta,evidence=row['evidence']))
                if entry is not None:
                    status=entry.get('status',{})
                    if not isinstance(status,dict) or not isinstance(status.get('messages',[]),list): raise ProductionRefused('original history status malformed; conflict')
                    if status.get('status_str')=='error' or any(isinstance(m,list) and m and m[0]=='execution_error' for m in status.get('messages',[])):
                        candidate['execution_failed']=True
                    if status.get('completed') is True and status.get('status_str')=='success':
                        digest=canonical_digest(entry.get('outputs'))
                        if pid in completed_outputs and completed_outputs[pid]!=digest: raise ProductionRefused('original completed outputs conflict')
                        completed_outputs[pid]=digest
                    candidate.update(entry=entry,history=row['evidence'],history_finished=datetime.fromisoformat(row['response']['finished_at']))
    if accepted and any(not matches(meta,saved,graph) for meta in observed.get(accepted['prompt_id'],[])):
        raise ProductionRefused('same prompt queue/history identity conflict')
    if len(candidates)>1: raise ProductionRefused('multiple original task identity matches; conflict')
    if candidates:
        pid,candidate=next(iter(candidates.items())); reference=candidate['meta']
        candidate['queue_needs_refresh']=pid in active and (queue_started is None or queue_started<candidate.get('history_finished',queue_started))
        candidate['queued']=pid in active and not candidate['queue_needs_refresh']
        if any(not matches(meta,dict(saved,prompt_id=pid,number=reference[3]),graph) for meta in observed[pid]): raise ProductionRefused('same prompt queue/history identity conflict')
        return pid,candidate,evidence
    return None,None,evidence


def _output(store,request,graph,intent,accepted,entry,template):
    return output_from_history(entry,_saved(intent,accepted),graph,template,store.run_dir,intent['output_prefix'],'.png')


def validate_scene_terminal(store,request,graph):
    """Read a terminal only after validating its complete original evidence chain."""
    directory,intent,accepted,rows=_load(store,request,graph,allow_terminal=True)
    terminal=store.read(directory/'terminal.json')
    if terminal is None: return None
    if terminal['status']=='rejected' and not any(_post_rejected(row) for row in rows):
        raise ProductionRefused('terminal rejection lacks original rejected POST evidence')
    if terminal['status']=='identity_conflict':
        conflict=False
        try:
            pid,candidate,_=_history_candidates(rows,intent,accepted,graph)
            if accepted is not None:
                for row in rows:
                    value=_parse(row)
                    if (row['request']['method']=='POST' and isinstance(value,dict) and _valid_uuid(value.get('prompt_id'))
                        and type(value.get('number')) in (int,float) and value.get('node_errors')=={}
                        and (value['prompt_id']!=accepted['prompt_id'] or value['number']!=accepted['number'])):
                        conflict=True
            if candidate and candidate.get('entry') is not None:
                from types import SimpleNamespace
                template=SimpleNamespace(mapping={'output':{'node_id':'5','collection':'images'}})
                effective=accepted or dict(prompt_id=pid,number=candidate['meta'][3])
                target=_output(store,request,graph,intent,effective,candidate['entry'],template)
                conflict=conflict or (target is not None and candidate.get('queued',False))
        except ProductionRefused: conflict=True
        except AdapterError: pass
        if not conflict: raise ProductionRefused('terminal identity conflict lacks original conflicting evidence')
    if terminal['status']=='execution_failed':
        if accepted is None: raise ProductionRefused('execution failure has no accepted original task')
        failed=False
        for row in rows:
            value=_parse(row)
            if not isinstance(value,dict) or not row['request']['route'].startswith('/history'): continue
            entry=value.get(accepted['prompt_id'])
            if not isinstance(entry,dict): continue
            if matches(metadata(entry.get('prompt')),_saved(intent,accepted),graph):
                status=entry.get('status',{})
                failed=failed or status.get('status_str')=='error' or any(isinstance(m,list) and m and m[0]=='execution_error' for m in status.get('messages',[]))
        if not failed: raise ProductionRefused('terminal execution failure lacks original failure evidence')
    if terminal['status']=='invalid_media':
        from types import SimpleNamespace
        from ..media.scene_upscale import verify_png,InvalidScenePng
        pid,candidate,_=_history_candidates(rows,intent,accepted,graph)
        if accepted is None or candidate is None or candidate.get('entry') is None:
            raise ProductionRefused('invalid media terminal lacks original accepted output')
        target=_output(store,request,graph,intent,accepted,candidate['entry'],SimpleNamespace(mapping={'output':{'node_id':'5','collection':'images'}}))
        if target is None or terminal['evidence']!=[store.artifact(target)]: raise ProductionRefused('invalid media terminal output differs')
        invalid=False
        try: verify_png(target,width=1920,height=1080,config=store.frozen.config)
        except InvalidScenePng: invalid=True
        if not invalid: raise ProductionRefused('invalid media terminal lacks actual PNG defect')
    return terminal


def validate_scene_frame_submission(store,request,graph,*,template=None,media=True):
    """Reconstruct a complete submission from raw evidence without writing or GET."""
    directory,intent,accepted,rows=_load(store,request,graph)
    submission=store.read(directory/'submission.json')
    if submission is None:
        if intent is not None: _adjudicate_pending(store,request,graph,intent,accepted,rows,template)
        return None
    if intent is None or accepted is None: raise ProductionRefused('submission lacks accepted intent')
    _identity(submission,_SUBMISSION,request,'submission')
    if submission['intent_sha256']!=canonical_digest(intent) or submission['accepted_sha256']!=canonical_digest(accepted) or submission['prompt_id']!=accepted['prompt_id']: raise ProductionRefused('submission binding differs')
    store.validate_artifact(submission['history_evidence'])
    if media:store.validate_artifact(submission['output'])
    else:
        from ._scene_revision_origin_clips import declared_artifact
        declared_artifact(store,submission['output'])
    selected=[row for row in rows if row['evidence']==submission['history_evidence'] and row['request']['method']=='GET' and row['request']['route'].startswith('/history')]
    if len(selected)!=1: raise ProductionRefused('submission history evidence differs')
    pid,candidate,_=_history_candidates(rows,intent,accepted,graph)
    if pid!=accepted['prompt_id'] or candidate is None: raise ProductionRefused('submission lacks original history')
    if candidate.get('queued'): raise ProductionRefused('completed history conflicts with active queue')
    if candidate.get('queue_needs_refresh'): raise ProductionRefused('completed history requires fresh queue evidence')
    if candidate.get('execution_failed'): raise ProductionRefused('retained original Comfy execution failed')
    value=_parse(selected[0]); entry=value.get(pid) if isinstance(value,dict) else None
    if not isinstance(entry,dict): raise ProductionRefused('missing original history entry')
    from types import SimpleNamespace
    template=template or SimpleNamespace(mapping={'output':{'node_id':'5','collection':'images'}})
    target=_output(store,request,graph,intent,accepted,entry,template)
    if target is None or (store.artifact(target)!=submission['output'] if media else str(target)!=submission['output']['path']): raise ProductionRefused('submission output differs')
    return submission


def _adjudicate_pending(store,request,graph,intent,accepted,rows,template):
    """Reject retained definitive failures before any new frame POST; never repair."""
    def verdict(status,reason):
        raise SceneFrameTerminal(dict(schema_version=2,run_id=request['run_id'],frame_id=request['frame_id'],
            intent_sha256=canonical_digest(intent),status=status,reason=reason,evidence=[row['evidence'] for row in rows]))
    reference=accepted
    for row in rows:
        if _post_rejected(row): verdict('rejected','retained original Comfy POST rejected')
        value=_parse(row)
        if (row['request']['method']=='POST' and isinstance(value,dict) and _valid_uuid(value.get('prompt_id'))
                and type(value.get('number')) in (int,float) and math.isfinite(value['number']) and value.get('node_errors')=={}):
            if reference is not None and (reference['prompt_id']!=value['prompt_id'] or reference['number']!=value['number']):
                verdict('identity_conflict','retained original POST identity conflict')
            reference=dict(prompt_id=value['prompt_id'],number=value['number'])
    try:
        pid,candidate,_=_history_candidates(rows,intent,reference,graph)
        if candidate is None: return
        if candidate.get('execution_failed'): verdict('execution_failed','retained original Comfy execution failed')
        if candidate.get('entry') is not None:
            from types import SimpleNamespace
            template=template or SimpleNamespace(mapping={'output':{'node_id':'5','collection':'images'}})
            effective=reference or dict(prompt_id=pid,number=candidate['meta'][3])
            target=_output(store,request,graph,intent,effective,candidate['entry'],template)
            if target is not None:
                if candidate.get('queued') and not candidate.get('queue_needs_refresh'):
                    verdict('identity_conflict','retained completed history conflicts with active queue')
                return store.artifact(target)
    except SceneFrameTerminal: raise
    except AdapterError as exc: verdict('execution_failed',str(exc))
    except ProductionRefused as exc: verdict('identity_conflict',str(exc))


def _pending_scene_frame_output(store,request,graph,*,template=None):
    """Read-only owned success output, even when interruption omitted submission.json."""
    directory,intent,accepted,rows=_load(store,request,graph)
    if intent is None: return None
    return _adjudicate_pending(store,request,graph,intent,accepted,rows,template)


def _record_http(store,request,intent,method,route,call,timeout,graph):
    store.assert_owned(); directory=store.frame_dir(request['frame_id'])/'http'; token=str(uuid4())
    payload=prompt_payload(graph,intent['client_id']) if method=='POST' else None
    req=dict(schema_version=2,run_id=request['run_id'],frame_id=request['frame_id'],intent_sha256=canonical_digest(intent),method=method,route=route,
        body_sha256=hashlib.sha256(payload).hexdigest() if payload is not None else None,started_at=now())
    store.write(directory/(token+'.request.json'),req); response=None; error=None; interrupted=None
    try:
        response=call(timeout)
        if (not isinstance(response,dict) or set(response)!={'status','headers','body'} or type(response['status']) is not int
            or not 100<=response['status']<=599 or not isinstance(response['headers'],dict)
            or any(not isinstance(k,str) or not isinstance(v,str) for k,v in response['headers'].items())
            or not isinstance(response['body'],bytes) or len(response['body'])>JSON_LIMIT):
            response=None; raise ValueError('invalid memory HTTP response')
    except BaseException as exc:
        error=dict(kind=type(exc).__name__,message=str(exc) or type(exc).__name__)
        interrupted=exc
    # No callback can write after lock loss. Evidence is caller-thread only.
    store.assert_owned()
    bp=store.write_bytes(directory/(token+'.body'),response['body'] if response else b'')
    meta=dict(schema_version=2,run_id=request['run_id'],frame_id=request['frame_id'],request_sha256=canonical_digest(req),
        status=response['status'] if response else None,headers=response['headers'] if response else {},body=_body_artifact(store,bp),finished_at=now(),error=error)
    mp=store.write(directory/(token+'.response.json'),meta)
    row=dict(request=req,response=meta,raw=response['body'] if response else b'',evidence=store.artifact(mp))
    if interrupted is not None:
        if isinstance(interrupted,KeyboardInterrupt): raise interrupted
        raise SceneSubmitUnknown('original scene request outcome unknown: '+str(interrupted)) from interrupted
    return row


def _remote_validate(store,client,template,logger,timeout):
    """Service capability evidence precedes the once-only model intent."""
    from .logging import RunLogger
    logger=logger or RunLogger(store.run_dir,production=True)
    token=str(uuid4()); name='scene-upscale/service/'+token
    store.assert_owned()
    logger.save_json(name+'.request.json',dict(method='GET',route='/object_info',started_at=now()))
    response=None; failure=None
    try:
        response=client.object_info(timeout=timeout)
        if (not isinstance(response,dict) or set(response)!={'status','headers','body'} or type(response['status']) is not int
            or not isinstance(response['headers'],dict) or not isinstance(response['body'],bytes) or len(response['body'])>JSON_LIMIT):
            response=None; raise ValueError('invalid object_info memory response')
    except BaseException as exc: failure=exc
    store.assert_owned()
    body=logger.save_bytes(name+'.body',response['body'] if response is not None else b'')
    store.assert_owned()
    logger.save_json(name+'.response.json',dict(status=response['status'] if response else None,headers=response['headers'] if response else {},
        body=_body_artifact(store,body),finished_at=now(),error=dict(kind=type(failure).__name__,message=str(failure)) if failure else None))
    if failure is not None:
        if isinstance(failure,KeyboardInterrupt): raise failure
        raise SceneSubmitUnknown('remote object_info unavailable before intent: '+str(failure)) from failure
    value=_parse(dict(response=dict(response,error=None),raw=response['body']))
    if not isinstance(value,dict): raise ProductionRefused('remote object_info must be successful JSON object')
    try: template.validate_remote(value)
    except ValueError as exc: raise ProductionRefused('remote Wan template invalid: '+str(exc)) from exc


def recover_or_submit_scene_frame(store,request,graph,*,client,template,ensure_service,logger,timeout):
    budget=positive_timeout(timeout); end=time.monotonic()+budget
    store.assert_owned(); directory,intent,accepted,rows=_load(store,request,graph)
    completed=validate_scene_frame_submission(store,request,graph,template=template) if store.read(directory/'submission.json') is not None else None
    if completed is not None: return completed
    if intent is None:
        prompt_payload(graph,str(uuid4()))
        store.write(directory/'request.json',request); store.write(directory/'graph.json',graph)
    verify=store.capture_guard(request,graph); cancelled=Event()
    def guard():
        if cancelled.is_set() or time.monotonic()>=end: raise SceneSubmitUnknown('original frame tracking deadline exceeded')
        verify()
        if cancelled.is_set() or time.monotonic()>=end: raise SceneSubmitUnknown('original frame tracking deadline exceeded')
    guard()
    def remaining():
        guard(); result=end-time.monotonic()
        if result<=0: raise SceneSubmitUnknown('original scene tracking deadline exceeded')
        return result
    old_guard=getattr(client,'ownership_check',None)
    if old_guard is not None: client.ownership_check=guard
    service_ready=False
    try:
        if intent is None:
            cid=str(uuid4()); prompt_payload(graph,cid)  # Size rejection precedes intent.
            guard(); ensure_service(); guard()
            service_ready=True
            _remote_validate(store,client,template,logger,remaining()); guard()
            store.write(directory/'request.json',request); store.write(directory/'graph.json',graph)
            intent=dict(schema_version=2,run_id=request['run_id'],frame_id=request['frame_id'],request_sha256=canonical_digest(request),graph_sha256=request['graph_sha256'],
                input_sha256=request['input_copy']['sha256'],
                attempt_id=str(uuid4()),client_id=cid,output_prefix=_prefix(request),created_at=now())
            store.write(directory/'intent.json',intent); guard()
            row=_record_http(store,request,intent,'POST','/prompt',lambda t:client.submit(graph,client_id=cid,timeout=t),remaining(),graph)
            rows.append(row); value=_parse(row)
            if _post_rejected(row):
                _terminal(store,request,intent,'rejected','original Comfy POST rejected',[row['evidence']])
            if isinstance(value,dict) and _valid_uuid(value.get('prompt_id')) and type(value.get('number')) in (int,float) and math.isfinite(value['number']) and value.get('node_errors')=={}:
                accepted=_accept(store,request,intent,value['prompt_id'],value['number'],row['evidence'])
        else:
            # Durable raw POST acceptance precedes its derived accepted index.
            for row in rows:
                if _post_rejected(row): _terminal(store,request,intent,'rejected','original Comfy POST rejected',[row['evidence']])
                value=_parse(row)
                if row['request']['method']=='POST' and isinstance(value,dict) and _valid_uuid(value.get('prompt_id')) and type(value.get('number')) in (int,float) and math.isfinite(value['number']) and value.get('node_errors')=={}:
                    if accepted is not None and (accepted['prompt_id']!=value['prompt_id'] or accepted['number']!=value['number']):
                        _terminal(store,request,intent,'identity_conflict','POST acceptance identity conflict',[row['evidence']])
                    if accepted is None: accepted=_accept(store,request,intent,value['prompt_id'],value['number'],row['evidence'])
        fetched=False; network_failed=False
        while True:
            try: pid,candidate,evidence=_history_candidates(rows,intent,accepted,graph)
            except ProductionRefused as exc: _terminal(store,request,intent,'identity_conflict',str(exc),[row['evidence'] for row in rows])
            except AdapterError as exc: _terminal(store,request,intent,'execution_failed',str(exc),[row['evidence'] for row in rows])
            if candidate:
                if accepted is None: accepted=_accept(store,request,intent,pid,candidate['meta'][3],candidate['evidence'])
                if candidate.get('execution_failed'): _terminal(store,request,intent,'execution_failed','original Comfy execution failed',evidence)
                entry=candidate.get('entry')
                if entry is not None:
                    try: target=_output(store,request,graph,intent,accepted,entry,template)
                    except AdapterError as exc: _terminal(store,request,intent,'execution_failed',str(exc),evidence)
                    except ProductionRefused as exc: _terminal(store,request,intent,'identity_conflict',str(exc),evidence)
                    if target is not None:
                        if candidate.get('queue_needs_refresh'):
                            if not service_ready:
                                guard(); ensure_service(); guard(); service_ready=True
                            if network_failed: time.sleep(min(2,remaining()))
                            try:
                                row=_record_http(store,request,intent,'GET','/queue',lambda t:client.queue(timeout=t),remaining(),graph); rows.append(row)
                                if not isinstance(_parse(row),dict): raise SceneSubmitUnknown('queue temporarily unavailable')
                                network_failed=False
                            except SceneSubmitUnknown:
                                remaining(); network_failed=True
                            continue
                        if candidate.get('queued'): _terminal(store,request,intent,'identity_conflict','completed history conflicts with active queue',evidence)
                        try: output=store.artifact(target)
                        except (ValueError,OSError) as exc: raise SceneSubmitUnknown('original owned output unavailable') from exc
                        result=dict(schema_version=2,run_id=request['run_id'],frame_id=request['frame_id'],intent_sha256=canonical_digest(intent),accepted_sha256=canonical_digest(accepted),
                            prompt_id=accepted['prompt_id'],history_evidence=candidate['history'],output=output)
                        store.assert_owned(); store.write(directory/'submission.json',result)
                        return validate_scene_frame_submission(store,request,graph)
            if fetched:
                if candidate is None and not network_failed: raise SceneSubmitUnknown('no unique original graph/client identity; no re-POST')
                time.sleep(min(2,remaining()))
            else:
                if not service_ready:
                    guard(); ensure_service(); guard(); service_ready=True
                fetched=True
            # Every view is retained. A later success cannot erase a contradiction.
            network_failed=False
            try:
                row=_record_http(store,request,intent,'GET','/queue',lambda t:client.queue(timeout=t),remaining(),graph); rows.append(row)
                if not isinstance(_parse(row),dict): raise SceneSubmitUnknown('queue temporarily unavailable')
                route='/history'+('/'+accepted['prompt_id'] if accepted else '')
                row=_record_http(store,request,intent,'GET',route,lambda t:client.history(accepted['prompt_id'] if accepted else None,timeout=t),remaining(),graph); rows.append(row)
                if not isinstance(_parse(row),dict): raise SceneSubmitUnknown('history temporarily unavailable')
            except SceneSubmitUnknown:
                remaining(); network_failed=True
    finally:
        # Keep the cancelled guard installed: a late transport must never regain a
        # deadline-free send guard after this caller has returned.
        cancelled.set()

