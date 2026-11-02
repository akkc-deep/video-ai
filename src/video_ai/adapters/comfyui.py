"""Once-only Comfy submissions, durable intent, and read-only same-ID tracking."""
from copy import deepcopy
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import time
from uuid import UUID, uuid4

from .common import AdapterError, FailureKind, JSON_LIMIT, positive_timeout
from ..runtime.manifest import hash_file, now, pending_record, thaw, validate_unit, STAGES
from ..runtime.paths import PathPolicy
from ..runtime.workflows import safe_comfy_path


@dataclass(frozen=True)
class Submission:
    attempt_id: str
    prompt_id: str
    stage: str
    kind: str
    unit_id: str
    output_node: str
    collection: str


@dataclass(frozen=True)
class HistoryResult:
    prompt_id: str
    outputs: tuple[dict, ...]
    evidence_path: Path


class ComfyClient:
    def __init__(self, http, manifest, logger):
        self.http, self.manifest, self.logger = http, manifest, logger
        self._templates = []

    def validate_template(self, template):
        info = self.http.get_json('/object_info', max_bytes=JSON_LIMIT)
        template.validate_remote(info)
        self._templates.append(template)

    def _mapping(self, workflow):
        if not isinstance(workflow, dict):
            raise ValueError('workflow must be object')
        signature = {k:v.get('class_type') for k,v in workflow.items() if isinstance(v,dict)}
        matches = [t for t in self._templates if signature == t.mapping['nodes']]
        if len(matches) != 1:
            raise ValueError('workflow must match one remotely validated versioned template')
        template = matches[0]
        for group in ('inputs', 'models'):
            for name, ref in template.mapping[group].items():
                value = workflow[ref['node_id']].get('inputs', {}).get(ref['input'])
                if group == 'models' and value != template.graph[ref['node_id']]['inputs'][ref['input']]:
                    raise ValueError(f'model changed: {name}')
                if ref['input'] == 'image' or name == 'output_prefix':
                    if not isinstance(value, str) or '<' in value or '__' in value:
                        raise ValueError(f'{name}: unresolved placeholder')
                    safe_comfy_path(value)
        return template.mapping

    def _submission_state(self, submission, state, *, response_path=None, prompt_id=None, number=None, error=None):
        def mutate(data):
            record = data['units'][submission.kind][submission.unit_id]
            sub = record['submission']
            if sub['attempt_id'] != submission.attempt_id:
                raise ValueError('attempt mismatch')
            sub['state'], sub['last_seen_at'] = state, now()
            if response_path is not None:
                sub['response_path'] = str(response_path)
            if prompt_id is not None:
                sub['prompt_id'], sub['number'] = prompt_id, number
            if error is not None:
                record['error'] = error
            data['events'].append(dict(time=now(), stage=submission.stage, unit_id=submission.unit_id,
                                       action='submission_'+state,
                                       evidence_paths=[str(response_path)] if response_path else []))
        self.manifest.update(mutate)

    def _snapshots(self, stage, unit_id, prompt_id=None):
        evidence = []
        for path in ('/queue', '/history/'+prompt_id if prompt_id else '/history'):
            try:
                response = self.http.request('GET',path,max_bytes=JSON_LIMIT,timeout=min(2,self.http.timeout),stage=stage,unit_id=unit_id)
                evidence.append(response.evidence_path)
            except AdapterError as exc:
                evidence.extend(exc.evidence_paths)
        return evidence

    def submit_once(self, workflow, *, stage, kind, unit_id, on_intent=None):
        if on_intent is not None and not callable(on_intent): raise ValueError('on_intent must be callable')
        if stage not in STAGES:
            raise ValueError('unknown stage')
        validate_unit(kind, unit_id)
        if kind == 'image' and stage != 'start_images':
            raise ValueError('image submission requires start_images stage')
        if kind == 'shot_attempt' and stage != 'source_clips':
            raise ValueError('shot attempt submission requires source_clips stage')
        mapping = self._mapping(workflow)
        attempt, client_id = str(uuid4()), str(uuid4())
        directory = PathPolicy().validate_write(self.manifest.run_dir / 'workflows', 'run')
        directory.mkdir(exist_ok=True)
        request_path = PathPolicy().validate_write(directory / f'{attempt}.json', 'run')
        raw = json.dumps(workflow, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')
        with request_path.open('xb') as file:
            file.write(raw)
            file.flush(); os.fsync(file.fileno())
        identity = hash_file(request_path)
        submission = Submission(attempt, '', stage, kind, unit_id, mapping['output']['node_id'], mapping['output']['collection'])
        def intent(data):
            record = data['units'].setdefault(kind, {}).setdefault(unit_id, pending_record(unit=True))
            if record['submission'] is not None or record['status'] not in ('pending','running'):
                raise AdapterError(FailureKind.ambiguous, 'unit already has a submission; follow saved evidence, no re-POST')
            record.update(status='running', started_at=record['started_at'] or now())
            record['submission'] = dict(attempt_id=attempt, client_id=client_id, state='intent',
                                        request_path=str(request_path), response_path=None, prompt_id=None,
                                        number=None, submitted_at=now(), last_seen_at=None)
            data['workflows'][attempt] = thaw(identity)
            data['events'].append(dict(time=now(), stage=stage, unit_id=unit_id, action='submission_intent', evidence_paths=[str(request_path)]))
        self.manifest.update(intent)
        if on_intent is not None:
            on_intent(request_path,deepcopy(self.manifest.snapshot()['units'][kind][unit_id]['submission']))
        response = None
        try:
            response = self.http.request('POST','/prompt',json_body={'prompt':workflow,'client_id':client_id},
                                         max_bytes=JSON_LIMIT,stage=stage,unit_id=unit_id)
            data = self.http.parse_json(response, method='POST', stage=stage, unit_id=unit_id)
            prompt_id, number = data.get('prompt_id'), data.get('number')
            if (not isinstance(prompt_id,str) or str(UUID(prompt_id)) != prompt_id or
                    type(number) not in (int,float) or not math.isfinite(number) or not isinstance(data.get('node_errors'),dict)):
                raise ValueError('invalid prompt_id/number/node_errors acceptance')
            self._submission_state(submission, 'accepted', response_path=response.evidence_path, prompt_id=prompt_id, number=number)
            return Submission(attempt,prompt_id,stage,kind,unit_id,submission.output_node,submission.collection)
        except Exception as exc:
            kind_error = exc.kind if isinstance(exc,AdapterError) else FailureKind.ambiguous
            state = 'rejected' if kind_error == FailureKind.explicit else 'ambiguous'
            evidence = list(exc.evidence_paths) if isinstance(exc,AdapterError) else []
            if response:
                evidence.append(response.evidence_path)
            trace = self.logger.exception(stage,unit_id,exc)
            evidence.append(trace)
            if state == 'ambiguous':
                evidence.extend(self._snapshots(stage,unit_id))
            error = dict(kind=kind_error.value, message=str(exc), traceback_path=str(trace), evidence_paths=[str(p) for p in evidence])
            try:
                self._submission_state(submission,state,response_path=response.evidence_path if response else None,error=error)
            except Exception as write_error:
                evidence.append(self.logger.exception(stage,unit_id,write_error))
            raise AdapterError(kind_error, str(exc), evidence) from exc

    def wait_for(self, submission, *, deadline_seconds, poll_seconds=2.0):
        from ..runtime.execution_limits import execution_deadline
        end = execution_deadline(deadline_seconds,time.monotonic())
        poll_seconds = positive_timeout(poll_seconds)
        saved = self.manifest.snapshot()['units'][submission.kind][submission.unit_id]['submission']
        if saved['attempt_id'] != submission.attempt_id or saved['prompt_id'] != submission.prompt_id or saved['state'] not in ('accepted','ambiguous'):
            raise AdapterError(FailureKind.ambiguous,'tracking requires matching saved accepted prompt_id')
        evidence = []
        while end is None or time.monotonic() < end:
            try:
                remaining = self.http.timeout if end is None else end-time.monotonic()
                if remaining <= 0:
                    break
                response = self.http.request('GET','/history/'+submission.prompt_id,max_bytes=JSON_LIMIT,
                                             timeout=remaining,stage=submission.stage,unit_id=submission.unit_id)
                evidence.append(response.evidence_path)
                history = self.http.parse_json(response,stage=submission.stage,unit_id=submission.unit_id)
            except AdapterError as exc:
                evidence.extend(exc.evidence_paths)
                history = {}
            item = history.get(submission.prompt_id) if isinstance(history,dict) else None
            if item is not None and not isinstance(item,dict):
                self._tracking_failure(submission,FailureKind.invalid_result,'history entry must be object',evidence)
            if isinstance(item,dict):
                status = item.get('status',{})
                if not isinstance(status,dict):
                    self._tracking_failure(submission,FailureKind.invalid_result,'history status must be object',evidence)
                messages = status.get('messages',[])
                if not isinstance(messages,list):
                    self._tracking_failure(submission,FailureKind.invalid_result,'history status messages must be list',evidence)
                failed = status.get('status_str') == 'error' or any(isinstance(m,list) and m and m[0] == 'execution_error' for m in messages)
                if failed:
                    self._tracking_failure(submission,FailureKind.explicit,'Comfy execution failed',evidence)
                if status.get('completed') is True and status.get('status_str') == 'success':
                    try:
                        outputs = item['outputs'][submission.output_node][submission.collection]
                        if not isinstance(outputs,list) or not outputs:
                            raise ValueError('successful history has no mapped output')
                        for output in outputs:
                            if not isinstance(output,dict) or not {'filename','subfolder','type'} <= set(output):
                                raise ValueError('invalid output file metadata')
                            safe_comfy_path(output['filename'])
                            if Path(output['filename']).name != output['filename']:
                                raise ValueError('output filename must be basename')
                            safe_comfy_path(output['subfolder'],allow_empty=True)
                            if output['type'] != 'output':
                                raise ValueError('mapped output must have output type')
                    except (KeyError,TypeError,ValueError) as exc:
                        self._tracking_failure(submission,FailureKind.invalid_result,str(exc),evidence)
                    self._submission_state(submission,'completed',response_path=response.evidence_path)
                    return HistoryResult(submission.prompt_id,tuple(deepcopy(outputs)),response.evidence_path)
            remaining = self.http.timeout if end is None else end-time.monotonic()
            if remaining > 0:
                try:
                    queue = self.http.request('GET','/queue',max_bytes=JSON_LIMIT,timeout=remaining,
                                              stage=submission.stage,unit_id=submission.unit_id)
                    evidence.append(queue.evidence_path)
                except AdapterError as exc:
                    evidence.extend(exc.evidence_paths)
            if end is None or end > time.monotonic():
                time.sleep(poll_seconds if end is None else min(poll_seconds,end-time.monotonic()))
        self._tracking_failure(submission,FailureKind.ambiguous,'tracking deadline exceeded; task remains unknown',evidence)

    def _tracking_failure(self, submission, kind, message, evidence):
        error = dict(kind=kind.value, message=message, traceback_path=None, evidence_paths=[str(p) for p in evidence])
        self._submission_state(submission,'ambiguous' if kind == FailureKind.ambiguous else 'failed',error=error)
        raise AdapterError(kind,message,evidence)
