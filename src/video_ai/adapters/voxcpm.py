"""Finite async-to-WAV adaptation of the persistent local VoxCPM2 protocol."""
import hashlib
import json
import time

from .common import AdapterError, FailureKind
from .tts import require_wav
from ..planning.segments import speakable
from ..runtime.manifest import validate_unit
from ..voxcpm.contracts import freeze_request


class VoxTtsClient:
    def __init__(self, http, settings, *, reference_sha256, request_scope):
        if not isinstance(request_scope, str) or not request_scope.strip():
            raise ValueError('VoxCPM2 requires a persistent revision/attempt request_scope')
        self.http, self.settings, self.scope = http, settings, request_scope
        self.binding = dict(voice_id=settings.parameters['voice_id'],
                            model_revision=settings.model_revision, reference_sha256=reference_sha256)
        self._ready = False

    def request_id(self, unit_id):
        validate_unit('speech', unit_id)
        identity = json.dumps([self.scope, unit_id], ensure_ascii=False, separators=(',', ':'))
        return 'vox_' + hashlib.sha256(identity.encode('utf-8')).hexdigest()

    def payload(self, text):
        if not isinstance(text, str) or not speakable(text) or len(text) > 250:
            raise ValueError('VoxCPM2 requires original speech text of at most 250 characters')
        return dict(self.settings.parameters, text=text)

    def synthesize(self, text, *, unit_id):
        body = dict(self.payload(text), request_id=self.request_id(unit_id))
        expected = freeze_request(body, self.binding)
        deadline = time.monotonic() + self.http.timeout
        evidence = []
        submitted = False

        def fail(kind, message):
            raise AdapterError(kind, message, evidence)

        def request(method, path, **kwargs):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                fail(FailureKind.ambiguous if submitted else FailureKind.unavailable,
                     'VoxCPM2 deadline exceeded; query original request_id ' + body['request_id'])
            response = self.http.request(method, path, timeout=remaining, stage='speech', unit_id=unit_id, **kwargs)
            evidence.append(response.evidence_path)
            return response

        def read_json(response, method='GET'):
            return self.http.parse_json(response, method=method, stage='speech', unit_id=unit_id)

        def query():
            try:
                response = request('GET', path, allow_not_found=True)
                if response.status == 404:
                    return None
                return read_json(response)
            except AdapterError as error:
                # A reconstructed client cannot infer whether this ID was submitted earlier.
                raise AdapterError(FailureKind.ambiguous,
                                   'VoxCPM2 original task query unknown: ' + body['request_id'],
                                   error.evidence_paths) from error

        def validate(task):
            if not isinstance(task, dict) or task.get('request_id') != body['request_id'] or task.get('engine') != 'voxcpm2':
                fail(FailureKind.invalid_result, 'VoxCPM2 task identity differs')
            frozen = task.get('request')
            if not isinstance(frozen, dict) or any(frozen.get(k) != v for k,v in expected.items() if k != 'binding'):
                fail(FailureKind.explicit, 'VoxCPM2 frozen request differs; use a new revision/attempt scope')
            binding = frozen.get('binding')
            if not isinstance(binding, dict) or any(binding.get(k) != v for k,v in self.binding.items()):
                fail(FailureKind.explicit, 'VoxCPM2 frozen model/reference binding differs')
            return task.get('status')

        path = '/tts/tasks/' + body['request_id']
        try:
            if not self._ready:
                health = read_json(request('GET', '/health'))
                voices = read_json(request('GET', '/voices'))
                if (not isinstance(health, dict) or health.get('service') != 'video-ai-voxcpm2'
                        or health.get('status') != 'ready' or health.get('model_revision') != self.settings.model_revision
                        or not isinstance(voices, dict) or not isinstance(voices.get('voices'), list)
                        or not any(isinstance(v, dict) and v.get('voice_id') == self.binding['voice_id']
                            and v.get('reference_sha256') == self.binding['reference_sha256'] for v in voices['voices'])):
                    fail(FailureKind.explicit, 'VoxCPM2 service model/reference binding differs')
                self._ready = True
            task = query()
            if task is None:
                submitted = True  # A lost response may already have committed the intent.
                try:
                    task = read_json(request('POST', '/tts/generate', json_body=body), 'POST')
                except AdapterError as error:
                    evidence.extend(error.evidence_paths)
                    if error.kind not in (FailureKind.ambiguous, FailureKind.unavailable):
                        raise
                    task = query()
                    if task is None:
                        fail(FailureKind.ambiguous, 'VoxCPM2 submission unknown; query original request_id ' + body['request_id'])
            submitted = True
            while True:
                status = validate(task)
                if status == 'completed':
                    return require_wav(request('GET', path + '/audio', max_bytes=64*1024*1024))
                if status in ('failed', 'cancelled', 'cancel_requested'):
                    fail(FailureKind.explicit, f'VoxCPM2 {status}: {task.get("error")}')
                if status not in ('queued', 'running'):
                    fail(FailureKind.invalid_result, 'unknown VoxCPM2 task status')
                time.sleep(min(.2, max(0, deadline - time.monotonic())))
                task = query()
                if task is None:
                    fail(FailureKind.ambiguous, 'VoxCPM2 original task disappeared; no resubmission')
        except AdapterError as error:
            kind = FailureKind.ambiguous if submitted and error.kind == FailureKind.unavailable else error.kind
            raise AdapterError(kind, str(error), tuple(dict.fromkeys([*evidence, *error.evidence_paths]))) from error
