"""Production submission truth and GET-only original identity recovery."""
from copy import deepcopy
import json
import math
from pathlib import Path
from urllib.parse import quote

from ..adapters.common import AdapterError,FailureKind,JSON_LIMIT,strict_json
from ..adapters.comfyui import Submission,HistoryResult
from ..config import read_json
from .manifest import now
from .production_state import ProductionRefused,run_path
from .production_support import recover_http,MissingHttpEvidence
from .workflows import safe_comfy_path


def same(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)


def _same_history_graph(a,b):
    # Comfy validates FLOAT inputs in place: an original fps=16 is returned as
    # 16.0. Compare exact numeric values, preserving all keys and connections;
    # bools and lossy float conversions of integer seeds never match.
    if type(a) in (int,float) and type(b) in (int,float):
        return (type(a) is int or math.isfinite(a)) and (type(b) is int or math.isfinite(b)) and a==b
    if type(a) is not type(b):return False
    if isinstance(a,dict):return a.keys()==b.keys() and all(_same_history_graph(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(_same_history_graph(x,y) for x,y in zip(a,b))
    return a==b


def metadata(row):
    if (not isinstance(row,(list,tuple)) or len(row)<4 or type(row[0]) not in (int,float)
        or not math.isfinite(row[0]) or not isinstance(row[1],str) or not row[1]
        or not isinstance(row[2],dict) or not isinstance(row[3],dict)):return None
    return row[1],row[2],row[3].get('client_id'),row[0]


def matches(meta,saved,graph):
    return meta is not None and meta[2]==saved['client_id'] and _same_history_graph(meta[1],graph) and (
        saved['prompt_id'] is None or saved['prompt_id']==meta[0]) and (saved['number'] is None or saved['number']==meta[3])


def output_from_history(entry,saved,graph,template,run,prefix,extension):
    meta=metadata(entry.get('prompt'))
    if not matches(meta,saved,graph):raise ProductionRefused('history graph/client/prompt identity differs')
    if len(entry['prompt'])<5 or entry['prompt'][4]!=[template.mapping['output']['node_id']]:raise ProductionRefused('history output nodes differ')
    status=entry.get('status',{})
    if status.get('status_str')=='error' or any(isinstance(m,list) and m and m[0]=='execution_error' for m in status.get('messages',[])):
        raise AdapterError(FailureKind.explicit,'original Comfy execution failed')
    if status.get('completed') is not True or status.get('status_str')!='success':return None
    node=template.mapping['output']['node_id'];collection=template.mapping['output']['collection']
    outputs=entry.get('outputs',{})
    if set(outputs)!={node} or not isinstance(outputs[node],dict):raise ProductionRefused('history outputs differ from mapped node')
    values=outputs[node].get(collection)
    if not isinstance(values,list) or len(values)!=1:raise ProductionRefused('one mapped model output required')
    value=values[0]
    if not isinstance(value,dict) or not {'filename','subfolder','type'}<=set(value) or value['type']!='output':raise ProductionRefused('invalid owned output metadata')
    name=safe_comfy_path(value['filename']);folder=safe_comfy_path(value['subfolder'],allow_empty=True)
    if Path(name).name!=name:raise ProductionRefused('output filename must be basename')
    path=run_path(run,run/'comfy/output'/folder/name)
    expected=run/'comfy/output'/Path(prefix).parent
    if path.parent!=expected or not path.name.startswith(Path(prefix).name+'_') or path.suffix.lower()!=extension:
        raise ProductionRefused('output does not belong to original run/shot/prefix')
    return path


def evidence(logger,unit_id):
    result=[]
    for path in logger.path('http').glob('*.request.json'):
        if read_json(path).get('unit_id')!=unit_id:continue
        result.append(str(path))
        for suffix in ('.response.json','.body'):
            other=path.with_name(path.name.removesuffix('.request.json')+suffix)
            if other.is_file():result.append(str(other))
    return result


def request(saved,paths):
    states={'intent':'intent','accepted':'accepted','ambiguous':'ambiguous','completed':'completed','rejected':'failed','failed':'failed'}
    return dict(state=states[saved['state']],intent_path=saved['request_path'],client_id=saved['client_id'],prompt_id=saved['prompt_id'],response_paths=paths)


def _local_histories(logger,unit_id,evidence_paths=None,*,route='/history'):
    paths=logger.path('http').glob('*.request.json') if evidence_paths is None else (Path(p) for p in evidence_paths if str(p).endswith('.request.json'))
    for path in paths:
        r=read_json(path)
        if r.get('unit_id')!=unit_id or r.get('method')!='GET' or route not in r.get('url',''):continue
        base=path.name.removesuffix('.request.json');mp=path.with_name(base+'.response.json');bp=path.with_name(base+'.body')
        if not mp.is_file() or not bp.is_file():continue
        m=read_json(mp)
        if m.get('status')!=200 or m.get('truncated') is not False or m.get('error') is not None or m.get('bytes')!=bp.stat().st_size:continue
        if m.get('url')!=r['url'] or m.get('unit_id')!=unit_id or m.get('method')!='GET':raise ProductionRefused('history HTTP metadata differs')
        try:value=strict_json(bp.read_bytes())
        except ValueError:continue
        if isinstance(value,dict):yield value,mp


def _check_identity_views(saved,graph,pid,reference,observed,*,state,logger,unit_id,evidence_paths):
    if any(not matches(metadata(r),saved,graph) or metadata(r)[3]!=reference[3] for r in observed):
        relative=f'logs/production/recovery-conflicts/{saved["attempt_id"]}.json'
        state.save_exclusive(relative,dict(schema_version=1,attempt_id=saved['attempt_id'],
            client_id=saved['client_id'],prompt_id=pid,
            reason='same prompt has conflicting queue/history identity',
            evidence_paths=list(evidence_paths) if evidence_paths is not None else evidence(logger,unit_id)))
        raise ProductionRefused('same prompt has conflicting queue/history identity; no re-POST')


def reconcile(client,template,graph,*,stage,kind,unit_id,state,production_uid,logger,prefix,extension,allow_get,evidence_paths=None):
    manifest=client.manifest;record=manifest.snapshot()['units'].get(kind,{}).get(unit_id)
    if record is None or record['submission'] is None:return None
    saved=record['submission'];path=run_path(state.run_dir,saved['request_path'])
    if not same(read_json(path),graph):raise ProductionRefused('original persisted graph differs from fixed request')
    identity=manifest.snapshot()['workflows'][saved['attempt_id']]
    from .production_inputs import _verify_identity
    if identity['path']!=str(path):raise ProductionRefused('original graph path differs')
    _verify_identity(identity,state.run_dir)
    conflict_path=run_path(state.run_dir,state.run_dir/'logs/production/recovery-conflicts'/f'{saved["attempt_id"]}.json')
    if conflict_path.exists():
        raise ProductionRefused('original queue/history identity conflict is retained; no re-POST')
    local=state.snapshot()['units'].get(stage,{}).get(production_uid)
    req=request(saved,list(evidence_paths) if evidence_paths is not None else evidence(logger,unit_id))
    if local and local['request'] is not None:
        old=local['request']
        if (old['intent_path']!=req['intent_path'] or old['client_id']!=req['client_id'] or
            old['prompt_id'] is not None and old['prompt_id']!=req['prompt_id']):raise ProductionRefused('manifest and production request disagree')
    elif state.snapshot()['stages'][stage]['status']=='running':
        state.record_unit(stage,production_uid,status='running',request=dict(req,state='intent',prompt_id=None))
    if saved['state'] in ('failed','rejected'):raise RuntimeError('original Comfy submission failed; no automatic retry')
    # Original acceptance may be durable while the manifest cursor is still intent.
    try:
        raw,_,_=recover_http(logger,uid=unit_id,url=client.http.base_url+'/prompt',payload=dict(prompt=graph,client_id=saved['client_id']),evidence_paths=evidence_paths)
    except MissingHttpEvidence:pass
    else:
        try:acceptance=strict_json(raw)
        except (ValueError,UnicodeError):acceptance={}
        if not isinstance(acceptance,dict):acceptance={}
        from uuid import UUID
        pid=acceptance.get('prompt_id');number=acceptance.get('number')
        try:valid=isinstance(pid,str) and str(UUID(pid))==pid and type(number) in (int,float) and math.isfinite(number) and isinstance(acceptance.get('node_errors'),dict)
        except ValueError:valid=False
        if valid:
            if saved['prompt_id'] is not None and (saved['prompt_id']!=pid or saved['number']!=number):raise ProductionRefused('original acceptance differs')
            if saved['prompt_id'] is None:
                _accept(client,saved,stage,kind,unit_id,template,pid,number)
                saved=manifest.snapshot()['units'][kind][unit_id]['submission']
    completed=[]
    for history,ep in _local_histories(logger,unit_id,evidence_paths):
        for pid,entry in history.items():
            if isinstance(entry,dict) and matches(metadata(entry.get('prompt')),saved,graph):
                if pid!=entry['prompt'][1]:raise ProductionRefused('local history key differs from original prompt ID')
                target=output_from_history(entry,saved,graph,template,state.run_dir,prefix,extension)
                if target is not None:completed.append((pid,entry,ep,target))
    ids={row[0] for row in completed}
    if len(ids)>1:raise ProductionRefused('multiple original history identity matches')
    if completed:
        pid,entry,ep,target=completed[-1]
        observed=[]
        for queue,_ in _local_histories(logger,unit_id,evidence_paths,route='/queue'):
            for key in ('queue_running','queue_pending'):
                rows=queue.get(key,[])
                if not isinstance(rows,list):raise ProductionRefused('original queue rows must be list')
                observed.extend(r for r in rows if isinstance(r,(list,tuple)) and len(r)>1 and r[1]==pid)
        _check_identity_views(saved,graph,pid,metadata(entry['prompt']),observed,
            state=state,logger=logger,unit_id=unit_id,evidence_paths=evidence_paths)
        if saved['prompt_id'] is None:
            _accept(client,saved,stage,kind,unit_id,template,pid,entry['prompt'][0]);saved=manifest.snapshot()['units'][kind][unit_id]['submission']
        sub=_submission(saved,stage,kind,unit_id,template)
        if saved['state']!='completed':client._submission_state(sub,'completed',response_path=ep)
        return target,manifest.snapshot()['units'][kind][unit_id]['submission']
    if not allow_get:return 'needs_get'
    # A unique full match from both interfaces is required for unknown IDs.
    queue=client.http.get_json('/queue',max_bytes=JSON_LIMIT,stage=stage,unit_id=unit_id)
    history=client.http.get_json('/history'+('/'+quote(saved['prompt_id'],safe='') if saved['prompt_id'] else ''),max_bytes=JSON_LIMIT,stage=stage,unit_id=unit_id)
    if not isinstance(queue,dict) or not isinstance(history,dict):raise ProductionRefused('invalid queue/history response')
    candidates={};queue_rows=[]
    for key in ('queue_running','queue_pending'):
        rows=queue.get(key,[])
        if not isinstance(rows,list):raise ProductionRefused('queue rows must be list')
        for row in rows:
            queue_rows.append(row)
            meta=metadata(row)
            if matches(meta,saved,graph):candidates.setdefault(meta[0],{})['queue']=row
            elif saved['prompt_id'] is not None and meta is not None and meta[0]==saved['prompt_id']:raise ProductionRefused('same prompt has conflicting queue identity')
    for pid,entry in history.items():
        meta=metadata(entry.get('prompt')) if isinstance(entry,dict) else None
        if matches(meta,saved,graph):
            if pid!=meta[0]:raise ProductionRefused('history key differs from original prompt')
            candidates.setdefault(pid,{})['history']=entry
        elif saved['prompt_id'] is not None and pid==saved['prompt_id']:raise ProductionRefused('same prompt has conflicting history identity')
    if len(candidates)!=1:raise ProductionRefused('no unique client_id and complete graph match; no re-POST')
    pid,candidate=next(iter(candidates.items()))
    entry=candidate.get('history');row=entry['prompt'] if entry else candidate['queue']
    reference=metadata(row)
    # Unknown IDs must agree across interfaces, including rows which failed
    # the initial full-match filter. Keep a refusal durable: cached successful
    # history on a later invocation cannot erase contradictory original truth.
    observed=[r for r in queue_rows if isinstance(r,(list,tuple)) and len(r)>1 and r[1]==pid]
    if pid in history:observed.append(history[pid].get('prompt') if isinstance(history[pid],dict) else None)
    _check_identity_views(saved,graph,pid,reference,observed,
        state=state,logger=logger,unit_id=unit_id,evidence_paths=evidence_paths)
    if saved['prompt_id'] is None:
        _accept(client,saved,stage,kind,unit_id,template,pid,row[0]);saved=manifest.snapshot()['units'][kind][unit_id]['submission']
    if entry and output_from_history(entry,saved,graph,template,state.run_dir,prefix,extension) is not None:
        if 'queue' in candidate:raise ProductionRefused('completed history conflicts with active queue')
        return reconcile(client,template,graph,stage=stage,kind=kind,unit_id=unit_id,state=state,production_uid=production_uid,logger=logger,prefix=prefix,extension=extension,allow_get=False,evidence_paths=evidence_paths)
    sub=_submission(saved,stage,kind,unit_id,template)
    client.wait_for(sub,deadline_seconds=client._production_deadline)
    return reconcile(client,template,graph,stage=stage,kind=kind,unit_id=unit_id,state=state,production_uid=production_uid,logger=logger,prefix=prefix,extension=extension,allow_get=False,evidence_paths=evidence_paths)


def _submission(saved,stage,kind,unit_id,template):
    return Submission(saved['attempt_id'],saved['prompt_id'],stage,kind,unit_id,template.mapping['output']['node_id'],template.mapping['output']['collection'])


def _accept(client,saved,stage,kind,unit_id,template,pid,number):
    client._submission_state(_submission(saved,stage,kind,unit_id,template),'accepted',prompt_id=pid,number=number)


def submission_payload(saved,logger,unit_id,evidence_paths=None):
    return dict(attempt_id=saved['attempt_id'],client_id=saved['client_id'],prompt_id=saved['prompt_id'],
                intent_path=saved['request_path'],response_paths=list(evidence_paths) if evidence_paths is not None else evidence(logger,unit_id))


class HttpEvidenceIndex:
    """Index durable HTTP once, then observe each new HTTP evidence write."""
    def __init__(self,logger):
        self.logger=logger;self.units={};self.requests={}
        for path in logger.path('http').glob('*.request.json'):
            uid=read_json(path).get('unit_id');self.requests[path.name.removesuffix('.request.json')]=uid
            self.add(uid,path)
            for suffix in ('.response.json','.body'):
                other=path.with_name(path.name.removesuffix('.request.json')+suffix)
                if other.is_file():self.add(uid,other)

    def add(self,uid,path):
        paths=self.units.setdefault(uid,[]);value=str(path)
        if value not in paths:paths.append(value);paths.sort()

    def paths(self,uid):return self.units.setdefault(uid,[])

    def __getattr__(self,key):return getattr(self.logger,key)

    def save_json(self,name,data):
        path=self.logger.save_json(name,data)
        if name.startswith('http/'):
            if name.endswith('.request.json'):
                token=Path(name).name.removesuffix('.request.json');self.requests[token]=data.get('unit_id')
                self.add(data.get('unit_id'),path)
            elif name.endswith('.response.json'):
                token=Path(name).name.removesuffix('.response.json');self.add(self.requests[token],path)
        return path

    def save_bytes(self,name,data):
        path=self.logger.save_bytes(name,data)
        if name.startswith('http/') and name.endswith('.body'):
            self.add(self.requests[Path(name).name.removesuffix('.body')],path)
        return path
