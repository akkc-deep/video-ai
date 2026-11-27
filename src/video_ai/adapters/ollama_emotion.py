"""One full-script Ollama request with explicit, durable narrative fallback."""
import json
from uuid import uuid4

from .common import AdapterError
from .ollama import ollama_body, parse_completed_response
from ..planning.emotion import BASE_STYLE, emotion_prompt, emotion_schema, make_plan


class EmotionDirector:
    def __init__(self, http, *, base_style=BASE_STYLE, cpu_only=False):
        if not isinstance(base_style, str) or not base_style.strip() or len(base_style) > 260:
            raise ValueError('base_style must contain 1–260 characters')
        if type(cpu_only) is not bool:
            raise ValueError('cpu_only must be boolean')
        self.http, self.base_style, self.cpu_only = http, base_style, cpu_only

    def plan(self, text):
        if not isinstance(text, str) or not text.strip():
            raise ValueError('emotion planning requires nonempty source text')
        schema = emotion_schema(len(text))
        body = ollama_body(emotion_prompt(text), schema, cpu_only=self.cpu_only)
        body['options']['num_predict'] = 16384
        required = (len(body['prompt'].encode('utf-8'))
                    +len(json.dumps(body['format'], ensure_ascii=False).encode('utf-8'))
                    +2048+body['options']['num_predict'])
        context = 32768
        while context < required and context < 131072:
            context *= 2
        body['options']['num_ctx'] = context
        token = uuid4().hex
        prefix = f'tts-emotion/{token}'
        logger = self.http.logger
        evidence = [str(logger.save_json(f'{prefix}/intent.json', dict(body=body, schema=schema)))]
        failure = None
        if required > context:
            failure = dict(kind='capacity', message=f'complete emotion request requires at most {required} tokens; '
                           f'exceeds context capacity {context}; source retained without truncation',
                           evidence_paths=list(evidence))
        else:
            try:
                response = self.http.request('POST', '/api/generate', json_body=body,
                                             stage='tts-emotion', unit_id=token)
                evidence.append(str(response.evidence_path))
                outer = self.http.parse_json(response, method='POST', stage='tts-emotion', unit_id=token)
            except AdapterError as error:
                evidence.extend(str(p) for p in error.evidence_paths if str(p) not in evidence)
                failure = dict(kind=error.kind.value, message=str(error), evidence_paths=list(evidence))
            else:
                try:
                    # An escaped unpaired surrogate is legal to the JSON decoder
                    # but is invalid model text for our UTF-8 evidence. Keep the
                    # raw HTTP body and fall back; actual disk errors still escape.
                    evidence.append(str(logger.save_json(f'{prefix}/outer.json', outer)))
                except UnicodeEncodeError as error:
                    failure = dict(kind='invalid_result', message=str(error), evidence_paths=list(evidence))
                if failure is None:
                    failure, plan = self._parse_plan(text, outer, schema, evidence)
        if failure is not None:
            plan = make_plan(text, [], self.base_style, fallback=failure)
        # Record the final path within the record itself; save_json is exclusive.
        plan['evidence_paths'] = [*evidence, logger.path(f'{prefix}/emotion-plan.json').as_posix()]
        logger.save_json(f'{prefix}/emotion-plan.json', plan)
        logger.event('tts-emotion', token, 'emotion_plan', dict(status=plan['status'],
            spans=len(plan['spans']), fallback=failure, plan_path=plan['evidence_paths'][-1]))
        return plan

    def _parse_plan(self, text, outer, schema, evidence):
        try:
            if isinstance(outer, dict) and outer.get('done_reason') == 'length':
                raise ValueError('Ollama emotion response truncated at output token limit')
            content = parse_completed_response(outer, schema=schema,
                request_id='initial', evidence_paths=evidence)
            return None, make_plan(text, content['spans'], self.base_style)
        except (AdapterError, ValueError) as error:
            return dict(kind=getattr(getattr(error, 'kind', None), 'value', 'invalid_result'),
                        message=str(error), evidence_paths=list(evidence)), None
