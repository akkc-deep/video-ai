"""Explicit recovery of an owned MP4 after loss of original server history.

This proves local provenance only. Native decoding and authored visual review
remain the ordinary producer's responsibility.
"""
from datetime import datetime
from pathlib import Path

from ..adapters.common import JSON_LIMIT, positive_timeout, strict_json
from ..planning.production_scenes import canonical_digest
from . import scene_comfy_transactions as tx
from .manifest import now, thaw
from .production_comfy import _same_history_graph, matches, metadata
from .production_state import ProductionRefused, object_fields, run_path, timestamp
from .workflows import safe_comfy_path


_SUBMISSION='schema_version run_id clip_id intent_sha256 accepted_sha256 prompt_id local_recovery_evidence output'.split()
_RECEIPT=('schema_version run_id clip_id algorithm request_sha256 intent_sha256 accepted_sha256 '
          'graph_sha256 input_sha256 client_id prompt_id number output_prefix authorization '
          'input_record input_target queue_evidence absence_evidence output metadata_evidence started_at created_at').split()
_COMMAND='schema_version run_id clip_id source command stdout stderr'.split()
_RESULT='args cwd returncode timed_out stdout_path stderr_path started_at finished_at'.split()


def _refuse(message):
    raise ProductionRefused('local output recovery: '+message)


def _time(value):
    timestamp(value)
    return datetime.fromisoformat(value)


def _bindings(request, intent, accepted):
    return dict(request_sha256=canonical_digest(request),intent_sha256=canonical_digest(intent),
        accepted_sha256=canonical_digest(accepted),graph_sha256=request['graph_sha256'],input_sha256=request['input_sha256'],
        client_id=intent['client_id'],prompt_id=accepted['prompt_id'],number=accepted['number'],output_prefix=intent['output_prefix'])


def _input(store, request, *, media):
    path=store.clip_dir(request['clip_id'])/'input.json'
    value=store.read(path)
    if not isinstance(value,dict) or canonical_digest(value)!=request['input_sha256']:
        _refuse('input record digest differs from original request')
    if (type(value.get('schema_version')) is not int or value['schema_version']!=2
            or value.get('run_id')!=request['run_id'] or value.get('clip_id')!=request['clip_id']):
        _refuse('input record identity differs')
    target=value.get('target')
    expected=store.run_dir/'comfy/input'/request['run_id']/'scene_clips'/request['clip_id']/'start.png'
    if run_path(store.run_dir,expected)!=expected: _refuse('input image target is redirected')
    from ._scene_revision_origin_clips import declared_artifact
    if declared_artifact(store,target)!=expected: _refuse('input image target differs')
    if media: store.validate_artifact(target)
    return store.artifact(path),target


def _original(store, request, graph, loaded):
    directory,intent,accepted,rows=loaded
    if intent is None or accepted is None: _refuse('accepted original request is required')
    if any(tx._post_rejected(row) for row in rows): _refuse('original POST was rejected')
    _,candidate,_=tx._history_candidates(rows,intent,accepted,graph)
    if candidate and candidate.get('execution_failed'): _refuse('original execution failed')
    saved=tx._saved(intent,accepted)
    queues=[]
    for row in rows:
        value=tx._parse(row)
        if not isinstance(value,dict) or row['request']['method']!='GET': continue
        if row['request']['route']=='/queue':
            if any(matches(metadata(item),saved,graph) for key in ('queue_running','queue_pending') for item in value[key]):
                queues.append(row)
        elif accepted['prompt_id'] in value:
            entry=value[accepted['prompt_id']]
            status=entry.get('status',{}) if isinstance(entry,dict) else {}
            if status.get('completed') is True and status.get('status_str')=='success':
                _refuse('complete original history is available; use normal history recovery')
    if not queues: _refuse('retained full original queue identity is required')
    return directory,intent,accepted,rows,queues


def _output_path(store, intent):
    try: prefix=Path(safe_comfy_path(intent['output_prefix']))
    except ValueError as exc: raise ProductionRefused('unsafe original output prefix') from exc
    folder=store.run_dir/'comfy/output'/prefix.parent
    if run_path(store.run_dir,folder)!=folder: _refuse('output directory is redirected')
    return folder,prefix.name


def _owned_output(store, intent):
    folder,prefix=_output_path(store,intent)
    outputs=[]
    for path in folder.glob(prefix+'_*'):
        if path.is_file() and path.suffix.lower()=='.mp4':
            if run_path(store.run_dir,path)!=path: _refuse('matching output is redirected')
            outputs.append(path)
    if len(outputs)!=1: _refuse('exactly one matching owned MP4 is required')
    return outputs[0]


def _args(store, output):
    return [str(store.frozen.config.tools['ffprobe']),'-v','error','-show_format','-of','json',str(output)]


def _row(rows, artifact, method, route):
    selected=[row for row in rows if row['evidence']==artifact and row['request']['method']==method and row['request']['route']==route]
    if len(selected)!=1: _refuse('referenced HTTP evidence differs')
    return selected[0]


def _absence(queue, history, accepted):
    q,h=tx._parse(queue),tx._parse(history); pid=accepted['prompt_id']
    if (not isinstance(q,dict) or not all(isinstance(q.get(k),list) for k in ('queue_running','queue_pending'))
            or not isinstance(h,dict)):
        _refuse('fresh queue/history responses must be successful JSON views')
    active={item[1] for key in ('queue_running','queue_pending') for item in q[key]
            if isinstance(item,list) and len(item)>1 and isinstance(item[1],str)}
    if pid in active: _refuse('original task is still active in fresh queue')
    if pid in h: _refuse('original history is available; use normal history recovery')


def _metadata(store, request, graph, evidence, output, *, started_at):
    path=store.validate_artifact(evidence)
    expected=store.clip_dir(request['clip_id'])/'local-output-metadata.json'
    if path!=expected: _refuse('metadata command receipt path differs')
    value=store.read(path); tx._identity(value,_COMMAND,request,'local metadata command')
    if value['source']!=output: _refuse('metadata command source differs')
    command=value['command']; object_fields(command,_RESULT,'local metadata command result')
    if (command['args']!=_args(store,output['path']) or command['cwd']!=str(store.run_dir)
            or type(command['returncode']) is not int or command['returncode']!=0 or command['timed_out'] is not False):
        _refuse('metadata command did not successfully probe original output')
    if not _time(started_at)<=_time(command['started_at'])<=_time(command['finished_at']): _refuse('metadata command timing differs')
    for key in ('stdout','stderr'):
        artifact=value[key]; object_fields(artifact,('path','bytes','sha256'),'local metadata stream')
        if type(artifact['bytes']) is not int or artifact['bytes']<0: _refuse('metadata stream size must be a nonnegative integer')
        stream=run_path(store.run_dir,artifact['path'])
        if command[key+'_path']!=str(stream) or tx._body_artifact(store,stream)!=artifact:
            _refuse('raw metadata command evidence differs')
        if not stream.is_relative_to(store.run_dir/'logs'): _refuse('metadata stream must remain in run logs')
    raw=Path(value['stdout']['path']).read_bytes()
    if len(raw)>JSON_LIMIT: _refuse('metadata exceeds JSON limit')
    try:
        metadata_json=strict_json(raw)
        prompt=metadata_json['format']['tags']['prompt']
        embedded=strict_json(prompt.encode('utf-8')) if isinstance(prompt,str) else None
    except (KeyError,TypeError,ValueError,UnicodeError) as exc:
        raise ProductionRefused('local output recovery: missing valid embedded MP4 prompt') from exc
    # Comfy's IsChangedCache appends LoadImage.IS_CHANGED to its live prompt.
    # Accept only the exact fingerprint of this owned input, never arbitrary
    # runtime fields or changes to the submitted graph.
    if isinstance(embedded,dict):
        target=store.read(store.clip_dir(request['clip_id'])/'input.json')['target']
        image=f"{request['run_id']}/scene_clips/{request['clip_id']}/start.png"
        for key,node in list(embedded.items()):
            original=graph.get(key)
            if (isinstance(node,dict) and isinstance(original,dict) and 'is_changed' not in original
                    and original.get('class_type')=='LoadImage' and original.get('inputs',{}).get('image')==image
                    and node.get('is_changed')==[target['sha256']]):
                embedded[key]={k:v for k,v in node.items() if k!='is_changed'}
    if not isinstance(embedded,dict) or not _same_history_graph(embedded,graph):
        _refuse('embedded MP4 graph differs from original graph')
    return value


def validate_local_scene_submission(store, request, graph, submission, *, media=True, loaded=None):
    """Reconstruct a local provenance receipt without network, writes or FFprobe."""
    loaded=tx._load(store,request,graph) if loaded is None else loaded
    directory,intent,accepted,rows,queues=_original(store,request,graph,loaded)
    tx._identity(submission,_SUBMISSION,request,'local submission')
    if (submission['intent_sha256']!=canonical_digest(intent) or submission['accepted_sha256']!=canonical_digest(accepted)
            or submission['prompt_id']!=accepted['prompt_id']): _refuse('submission bindings differ')
    receipt_path=store.validate_artifact(submission['local_recovery_evidence'])
    if receipt_path!=directory/'local-output-recovery.json': _refuse('recovery receipt path differs')
    receipt=store.read(receipt_path); tx._identity(receipt,_RECEIPT,request,'local recovery receipt')
    if receipt['algorithm']!='owned_output_metadata_v1': _refuse('unsupported recovery algorithm')
    bindings=_bindings(request,intent,accepted)
    if any(not _same_history_graph(receipt[k],v) for k,v in bindings.items()): _refuse('receipt original bindings differ')
    if not isinstance(receipt['authorization'],str) or not receipt['authorization'].strip(): _refuse('explicit authorization is required')
    if _time(receipt['created_at'])<_time(receipt['started_at']): _refuse('receipt timing differs')
    input_record,input_target=_input(store,request,media=media)
    if receipt['input_record']!=input_record or receipt['input_target']!=input_target: _refuse('receipt input differs')
    if not any(row['evidence']==receipt['queue_evidence'] for row in queues): _refuse('original queue evidence differs')
    original=_row(rows,receipt['queue_evidence'],'GET','/queue')
    if _time(original['response']['finished_at'])>_time(receipt['started_at']): _refuse('queue identity was not retained before recovery')
    pairs=receipt['absence_evidence']
    if not isinstance(pairs,list) or len(pairs)!=2: _refuse('two fresh absence pairs are required')
    previous=_time(receipt['started_at']); tokens=[]
    for pair in pairs:
        object_fields(pair,('queue','history'),'local absence pair')
        queue=_row(rows,pair['queue'],'GET','/queue'); history=_row(rows,pair['history'],'GET','/history/'+accepted['prompt_id'])
        for row in (queue,history):
            if not previous<=_time(row['request']['started_at'])<=_time(row['response']['finished_at'])<=_time(receipt['created_at']):
                _refuse('absence observations are not fresh sequential views')
            previous=_time(row['response']['finished_at']); tokens.append(row['evidence']['path'])
        _absence(queue,history,accepted)
    if len(set(tokens))!=4: _refuse('absence evidence must contain four distinct GETs')
    output=receipt['output']
    if submission['output']!=output: _refuse('submission output differs from receipt')
    from ._scene_revision_origin_clips import declared_artifact
    target=declared_artifact(store,output); folder,prefix=_output_path(store,intent)
    if target.parent!=folder or not target.name.startswith(prefix+'_') or target.suffix.lower()!='.mp4':
        _refuse('receipt output does not belong to original prefix')
    if media:
        if _owned_output(store,intent)!=target: _refuse('owned output differs')
        store.validate_artifact(output)
    command=_metadata(store,request,graph,receipt['metadata_evidence'],output,started_at=receipt['started_at'])
    if _time(command['command']['started_at'])<previous or _time(command['command']['finished_at'])>_time(receipt['created_at']):
        _refuse('metadata command was not after absence evidence')
    # A later observation cannot silently reclassify a live original task.
    _,candidate,_=tx._history_candidates(rows,intent,accepted,graph)
    if candidate and candidate.get('queued'): _refuse('original task is active in retained latest queue')
    return submission


def recover_local_scene_output(store, request, graph, *, client, logger, authorization, request_timeout_seconds=60):
    """Write one explicit local provenance receipt under the existing run lock.

    ``authorization`` is the user's nonempty approval text/reference. Replays
    return the original validated submission without GETs or a new probe.
    """
    store.assert_owned()
    loaded=tx._load(store,request,graph)
    existing=tx.validate_scene_submission(store,request,graph)
    if existing is not None: return existing
    if not isinstance(authorization,str) or not authorization.strip(): _refuse('explicit authorization is required')
    timeout=positive_timeout(request_timeout_seconds)
    directory,intent,accepted,rows,queues=_original(store,request,graph,loaded)
    input_record,input_target=_input(store,request,media=True)
    guard=store.capture_guard(request,graph); guard(); started=now()
    # Permit replay after a crash between immutable receipt and submission writes.
    prior=store.read(directory/'local-output-recovery.json')
    if prior is not None:
        result=dict(schema_version=2,run_id=request['run_id'],clip_id=request['clip_id'],intent_sha256=canonical_digest(intent),
            accepted_sha256=canonical_digest(accepted),prompt_id=accepted['prompt_id'],
            local_recovery_evidence=store.artifact(directory/'local-output-recovery.json'),output=prior['output'])
        validate_local_scene_submission(store,request,graph,result,loaded=loaded)
        guard(); store.write(directory/'submission.json',result)
        return result
    queue_evidence=queues[-1]['evidence']; pairs=[]
    old_guard=getattr(client,'ownership_check',None)
    if old_guard is not None: client.ownership_check=guard
    try:
        metadata_path=directory/'local-output-metadata.json'
        prior_metadata=store.read(metadata_path)
        if prior_metadata is not None:
            # An interruption after the immutable probe receipt must reuse its
            # original observations, rather than overwrite it with a new probe.
            probe_start=_time(prior_metadata['command']['started_at'])
            earlier=[row for row in rows if _time(row['response']['finished_at'])<=probe_start]
            selected=earlier[-4:]
            routes=['/queue','/history/'+accepted['prompt_id']]*2
            if len(selected)!=4 or any(row['request']['method']!='GET' or row['request']['route']!=route
                    for row,route in zip(selected,routes)):
                _refuse('interrupted metadata lacks its original absence observations')
            started=selected[0]['request']['started_at']
            pairs=[dict(queue=selected[i]['evidence'],history=selected[i+1]['evidence']) for i in (0,2)]
            original_queues=[row for row in queues if _time(row['response']['finished_at'])<=_time(started)]
            if not original_queues: _refuse('interrupted metadata lacks earlier original queue identity')
            queue_evidence=original_queues[-1]['evidence']
            output=store.artifact(_owned_output(store,intent))
            evidence=store.artifact(metadata_path)
        for _ in range(0 if prior_metadata is not None else 2):
            queue=tx._record_http(store,request,intent,'GET','/queue',lambda t:client.queue(timeout=t),timeout,graph); rows.append(queue)
            # Both fresh views precede all local media inspection.
            history=tx._record_http(store,request,intent,'GET','/history/'+accepted['prompt_id'],
                lambda t:client.history(accepted['prompt_id'],timeout=t),timeout,graph); rows.append(history)
            _absence(queue,history,accepted)
            _original(store,request,graph,(directory,intent,accepted,rows))
            pairs.append(dict(queue=queue['evidence'],history=history['evidence']))
        if prior_metadata is None:
            guard(); output=store.artifact(_owned_output(store,intent))
            from .logging import RunLogger
            from .processes import run_logged
            from .environment import build_child_env
            logger=logger or RunLogger(store.run_dir,production=True)
            guard()
            result=run_logged(_args(store,output['path']),cwd=store.run_dir,env=build_child_env(store.paths,logger.run_dir),
                timeout=timeout,logger=logger,stage='scene_local_output_recovery',unit_id=request['clip_id'])
            guard(); store.validate_artifact(output)
            command=dict(schema_version=2,run_id=request['run_id'],clip_id=request['clip_id'],source=output,command=thaw(result),
                stdout=tx._body_artifact(store,result.stdout_path),stderr=tx._body_artifact(store,result.stderr_path))
            evidence=store.artifact(store.write(metadata_path,command))
        _metadata(store,request,graph,evidence,output,started_at=started)
        receipt=dict(schema_version=2,run_id=request['run_id'],clip_id=request['clip_id'],algorithm='owned_output_metadata_v1',
            **_bindings(request,intent,accepted),authorization=authorization,input_record=input_record,input_target=input_target,
            queue_evidence=queue_evidence,absence_evidence=pairs,output=output,metadata_evidence=evidence,started_at=started,created_at=now())
        guard(); store.validate_artifact(output)
        receipt_path=store.write(directory/'local-output-recovery.json',receipt)
        submission=dict(schema_version=2,run_id=request['run_id'],clip_id=request['clip_id'],intent_sha256=canonical_digest(intent),
            accepted_sha256=canonical_digest(accepted),prompt_id=accepted['prompt_id'],local_recovery_evidence=store.artifact(receipt_path),output=output)
        validate_local_scene_submission(store,request,graph,submission,loaded=(directory,intent,accepted,rows))
        guard(); store.write(directory/'submission.json',submission)
        return submission
    finally:
        if old_guard is not None: client.ownership_check=old_guard
