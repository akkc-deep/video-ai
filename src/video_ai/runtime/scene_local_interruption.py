"""Explicit operator evidence of a rebooted local job, never server completion.

This receipt only releases a revision's pending local effect. It cannot provide
media, technical acceptance, playback review, or permission to re-POST an intent.
The caller archives operator evidence in the run and holds its ordinary run lock.
"""
from datetime import datetime
import re
from urllib.parse import urlsplit

from ..adapters.common import strict_json
from ..planning.production_scenes import canonical_digest
from . import scene_comfy_transactions as tx
from .manifest import now
from .production_comfy import metadata, matches
from .production_state import ProductionRefused, object_fields, run_path, timestamp


_RECEIPT = ('schema_version run_id clip_id classification request_sha256 graph_sha256 '
    'intent_sha256 accepted_sha256 prompt_id authorization service_event service_stderr '
    'reboot boot_observation absence_pairs recorded_at').split()
_ARTIFACT = ('path', 'bytes', 'sha256')


def _refuse(message):
    raise ProductionRefused('local interruption: '+message)


def _time(value):
    timestamp(value)
    return datetime.fromisoformat(value)


def _artifact(store, artifact):
    object_fields(artifact, _ARTIFACT, 'local interruption Artifact')
    path = run_path(store.run_dir, artifact['path'])
    store.validate_artifact(artifact)
    return path


def _json_artifact(store, artifact):
    value = strict_json(_artifact(store, artifact).read_bytes())
    if not isinstance(value, dict): _refuse('operator evidence must be a JSON object')
    return value


def _bindings(request, intent, accepted):
    return dict(request_sha256=canonical_digest(request), graph_sha256=request['graph_sha256'],
        intent_sha256=canonical_digest(intent), accepted_sha256=canonical_digest(accepted),
        prompt_id=accepted['prompt_id'])


def _absent(row, pid, saved, graph):
    value = tx._parse(row)
    if not isinstance(value, dict): _refuse('absence needs successful raw JSON HTTP views')
    route = row['request']['route']
    if route=='/queue':
        for key in ('queue_running', 'queue_pending'):
            if not isinstance(value.get(key), list): _refuse('malformed queue view')
            for item in value[key]:
                meta = metadata(item)
                if meta is None: _refuse('malformed queue task')
                if meta[0]==pid or matches(meta, dict(saved, prompt_id=None, number=None), graph):
                    _refuse('original task is still queued')
    else:
        if pid in value: _refuse('original history exists; recover it instead')
        for entry in value.values():
            if not isinstance(entry, dict) or metadata(entry.get('prompt')) is None:
                _refuse('malformed history task')
            if matches(metadata(entry['prompt']), dict(saved, prompt_id=None, number=None), graph):
                _refuse('original history identity conflicts')


def _validate(store, request, graph, receipt):
    tx._identity(receipt, _RECEIPT, request, 'local interruption receipt')
    directory, intent, accepted, rows = tx._load(store, request, graph, allow_terminal=True)
    if intent is None or accepted is None: _refuse('accepted original request required')
    if receipt['classification']!='owned_service_rebooted_before_output': _refuse('classification differs')
    if any(receipt[key]!=value for key,value in _bindings(request,intent,accepted).items()):
        _refuse('original request binding differs')
    if not isinstance(receipt['authorization'],str) or not receipt['authorization'].strip():
        _refuse('explicit operator authorization required')
    recorded = _time(receipt['recorded_at'])
    # A local interruption cannot replace an existing output or server terminal.
    for name in ('terminal.json','submission.json','clip.json','generated.mp4','source.mp4'):
        if (directory/name).exists(): _refuse('original completion or terminal exists')
    prefix = run_path(store.run_dir, store.run_dir/'comfy/output'/intent['output_prefix'])
    if any(prefix.parent.glob(prefix.name+'*')): _refuse('original output prefix exists')

    event = _json_artifact(store, receipt['service_event'])
    object_fields(event, ('time','stage','unit_id','event','details'), 'original service event')
    details = event['details']
    if not isinstance(details,dict) or event['event']!='service_starting' or details.get('owned') is not True:
        _refuse('original service must be locally owned')
    pid = details.get('pid')
    if type(pid) is not int or pid<=0: _refuse('invalid original service PID')
    try: url = urlsplit(details.get('url',''))
    except (ValueError,TypeError): _refuse('invalid original service URL')
    if (url.scheme!='http' or url.hostname!='127.0.0.1' or url.username is not None
            or url.password is not None or url.path not in ('','/') or url.query or url.fragment):
        _refuse('original service must use local loopback HTTP')
    args = details.get('args')
    if not isinstance(args,list) or args.count('--output-directory')!=1:
        _refuse('original service lacks owned run output directory')
    index = args.index('--output-directory')+1
    if index>=len(args) or run_path(store.run_dir,args[index])!=store.run_dir/'comfy/output':
        _refuse('original service output directory differs')
    stderr = _artifact(store, receipt['service_stderr'])
    if str(stderr)!=details.get('stderr_path'): _refuse('original service stderr path differs')
    lines = [line.strip() for line in stderr.read_text(encoding='utf-8',errors='replace').splitlines() if line.strip()]
    progress = re.search(r'(\d+)%\|.*?\|\s*(\d+)\s*/\s*(\d+)\b',lines[-1]) if lines else None
    if progress is None: _refuse('original stderr must end with incomplete sampling progress')
    percent, done, total = map(int,progress.groups())
    if not (0<=percent<100 and total>0 and 0<=done<total):
        _refuse('original sampling is complete or invalid')

    reboot = _json_artifact(store, receipt['reboot'])
    previous = reboot.get('previous_service'); clip = reboot.get('interrupted_clip')
    if (reboot.get('run_id')!=request['run_id'] or not isinstance(previous,dict)
            or type(previous.get('pid')) is not int or previous['pid']!=pid
            or previous.get('process_absent') is not True or not isinstance(clip,dict)
            or clip.get('clip_id')!=request['clip_id'] or clip.get('prompt_id')!=accepted['prompt_id']):
        _refuse('reboot identity differs from original local job')
    boot = _time(reboot.get('os_boot_time_local'))
    if not _time(event['time'])<=_time(intent['created_at'])<boot<=recorded:
        _refuse('service/intent/reboot chronology differs')
    acceptance = [r for r in rows if r['evidence']==accepted['acceptance_evidence']]
    if len(acceptance)!=1 or not _time(acceptance[0]['response']['finished_at'])<boot:
        _refuse('original acceptance must precede reboot')
    observation = _json_artifact(store, receipt['boot_observation'])
    object_fields(observation, ('boot_time','observed_at','provenance'), 'operator boot observation')
    if (not isinstance(observation['provenance'],str) or not observation['provenance'].strip()
            or not boot<=_time(observation['boot_time'])<=_time(observation['observed_at'])<=recorded):
        _refuse('operator current boot observation differs')

    pairs = receipt['absence_pairs']
    if not isinstance(pairs,list) or len(pairs)<2: _refuse('two distinct queue/history pairs required')
    used = set(); previous_finish = boot; saved = tx._saved(intent,accepted)
    for pair in pairs:
        object_fields(pair, ('queue','history'), 'absence pair')
        for kind in ('queue','history'):
            artifact = pair[kind]; _artifact(store, artifact)
            key = canonical_digest(artifact)
            if key in used: _refuse('duplicate absence response')
            used.add(key)
            selected = [row for row in rows if row['evidence']==artifact]
            if len(selected)!=1: _refuse('bound original HTTP response missing')
            row = selected[0]; route = row['request']['route']
            valid_route = route=='/queue' if kind=='queue' else route in ('/history','/history/'+accepted['prompt_id'])
            if row['request']['method']!='GET' or not valid_route: _refuse('absence HTTP route differs')
            start, finish = _time(row['request']['started_at']), _time(row['response']['finished_at'])
            if not previous_finish<=start<=finish<=recorded: _refuse('postboot absence chronology differs')
            _absent(row,accepted['prompt_id'],saved,graph)
            previous_finish = finish
    # Retained history always wins. Preboot queue membership is expected; any
    # postboot membership contradicts interruption. Unbound unsuccessful or
    # malformed views never serve as absence proof or replace the bound pairs.
    for row in rows:
        value = tx._parse(row)
        if row['request']['method']!='GET' or not isinstance(value,dict): continue
        route = row['request']['route']
        if route.startswith('/history'):
            if accepted['prompt_id'] in value: _refuse('original history exists; recover it instead')
            items = [entry.get('prompt') for entry in value.values() if isinstance(entry,dict)]
        elif _time(row['request']['started_at'])>=boot:
            items = [item for key in ('queue_running','queue_pending')
                for item in (value.get(key) if isinstance(value.get(key),list) else [])]
        else: continue
        for item in items:
            meta = metadata(item)
            # Even an otherwise malformed queue row with the original UUID is
            # a contradictory observation, never usable as proof of absence.
            if ((isinstance(item,list) and len(item)>1 and item[1]==accepted['prompt_id'])
                    or matches(meta,dict(saved,prompt_id=None,number=None),graph)):
                _refuse('retained original queue/history identity conflicts')
    return receipt


def validate_local_interruption(store, request, graph):
    """Read-only receipt validation; None leaves the original pending/unknown."""
    receipt = store.read(store.clip_dir(request['clip_id'])/'local-interruption.json')
    return None if receipt is None else _validate(store,request,graph,receipt)


def record_local_interruption(store, request, graph, *, authorization, service_event,
        service_stderr, reboot, boot_observation, absence_pairs):
    """Record an explicitly authorized interruption using archived run Artifacts.

    service_event is one original service_starting JSON event. service_stderr is
    the immutable original stderr named by that event. reboot preserves the
    operator's run_id/previous_service/os_boot_time_local/interrupted_clip proof.
    boot_observation has exact boot_time/observed_at/provenance fields. Each
    absence_pairs item binds exact queue/history response Artifacts (at least 2).
    An interrupted candidate write can be retried with identical arguments.
    """
    store.assert_owned()
    directory,intent,accepted,_ = tx._load(store,request,graph,allow_terminal=True)
    if intent is None or accepted is None: _refuse('accepted original request required')
    path = directory/'local-interruption.json'; candidate_path = directory/'local-interruption-candidate.json'
    existing = store.read(path); candidate = store.read(candidate_path)
    for old in (existing,candidate):
        if old is not None: tx._identity(old,_RECEIPT,request,'local interruption candidate/receipt')
    prior = existing if existing is not None else candidate
    receipt = dict(schema_version=2,run_id=request['run_id'],clip_id=request['clip_id'],
        classification='owned_service_rebooted_before_output',**_bindings(request,intent,accepted),
        authorization=authorization,service_event=service_event,service_stderr=service_stderr,
        reboot=reboot,boot_observation=boot_observation,absence_pairs=absence_pairs,
        recorded_at=prior['recorded_at'] if prior is not None else now())
    if any(old is not None and old!=receipt for old in (existing,candidate)):
        _refuse('immutable authorization or evidence differs')
    _validate(store,request,graph,receipt)
    store.assert_owned(); store.write(candidate_path,receipt)
    # Validate the persisted candidate before publishing the authoritative name.
    _validate(store,request,graph,store.read(candidate_path))
    store.assert_owned(); store.write(path,receipt)
    return receipt
