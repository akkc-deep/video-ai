"""One structured generation POST with durable intent and conservative errors."""
from copy import deepcopy
import json
import os
import re
from ..config import parse_scene_planner_model
from .common import AdapterError, FailureKind, HttpClient, JSON_LIMIT, strict_json
from .ollama_units import project_units_schema, restore_units_content, UNITS_COVERAGE_NOTE
from .ollama_visuals import is_model_visual,project as project_visuals,restore as restore_visuals
from .ollama_scenes import is_environment_transport, project_scene_environment, restore_scene_content


class SceneCapacityError(ValueError):
    """The complete scene request cannot fit the fixed context budget."""


def _tuple_keys(schema):
    keys=[]
    for index,item in enumerate(schema['prefixItems']):
        properties=item.get('properties',{})
        key=next((properties[name]['const'] for name in ('shot_id','unit_id') if name in properties and isinstance(properties[name].get('const'),str)),f'item_{index:04d}')
        if key in keys:raise ValueError('duplicate tuple transport key')
        keys.append(key)
    return keys


def _grounded_pattern_parts(pattern):
    """Recognize only the application's complete literal anchor language."""
    marker=r'[^ \t\r\n].*'
    if not isinstance(pattern,str) or not pattern.startswith('^') or not pattern.endswith('$'):
        return None
    parts=pattern[1:-1].split(marker)
    if len(parts)!=2:return None
    prefix,suffix=parts
    if suffix:
        from ..planning.storyboard import CAMERA_PATHS
        if suffix!=' Camera path: ('+'|'.join(CAMERA_PATHS)+r')\.':return None
    decoded=[];index=0
    operators=r'\.^$|?*+(){}[]'
    while index<len(prefix):
        char=prefix[index];index+=1
        if char=='\\':
            if index==len(prefix):return None
            char=prefix[index];index+=1
            if char in 'nrt':char={'n':'\n','r':'\r','t':'\t'}[char]
            elif char not in operators:return None
        elif char in operators:return None
        decoded.append(char)
    decoded=''.join(decoded)
    if not decoded.endswith('. '):return None
    return decoded,suffix


def _presentation_pattern(video=False, max_length=None):
    # The installed converter matches serialized JSON characters/escapes.
    escape=r'\\(["\\/bfnrt]|u[0-9a-fA-F]{4})'
    first=r'([^"\\\x00-\x20]|'+escape+')'
    budget=min(160,max_length) if video and max_length is not None else 160 if video else max_length
    rest=r'([^"\\\x00-\x1f]|'+escape+')'+('{0,'+str(budget-1)+'}' if budget is not None else '*')
    return '^'+first+rest+'$'


def _json_payload_pattern(pattern, max_length=None):
    """Preserve full anchors/camera outside the bounded video presentation."""
    parts=_grounded_pattern_parts(pattern)
    if parts is None:return None
    decoded,suffix=parts
    operators=r'\.^$|?*+(){}[]'
    payload=json.dumps(decoded,ensure_ascii=False)[1:-1]
    literal=''.join('\\'+c if c in operators else c for c in payload)
    budget=_presentation_budget(dict(maxLength=max_length),decoded,bool(suffix)) if max_length is not None else None
    return '^'+literal+_presentation_pattern(bool(suffix),budget)[1:-1]+suffix+'$'


def _presentation_budget(field,prefix,video=False):
    if 'maxLength' not in field:return None
    from ..planning.storyboard import CAMERA_PATHS
    suffix=max(len(' Camera path: '+camera+'.') for camera in CAMERA_PATHS) if video else 0
    return field['maxLength']-len(prefix)-suffix


_VISUAL_FIELDS=('composition','action_start','action_end','image_prompt','video_prompt')
_GROUNDING_NOTE=('\n\nStructured transport protocol: For shot objects whose format contains _grounded_visual, '
      'this representation overrides the base instructions to emit complete strings ONLY for '
      'composition, action_start, action_end, image_prompt and video_prompt. Emit the complete exact '
      'depiction_anchor once as _grounded_visual.fact_prefix. Emit each concise visible presentation '
      'in _grounded_visual.presentations under its original field name, without repeating the anchor. '
      'Emit camera_motion using its required enum. In the video_prompt presentation emit only the '
      'visible start/process/end, at most 160 characters, without the Camera path clause. The declared '
      'decoder joins the emitted fact_prefix with each emitted presentation and appends " Camera path: " '
      '+ the emitted camera_motion + "." to video_prompt. All source meaning and other requirements '
      'remain in force. Unfactored visual_expression must still contain its complete exact anchor '
      'and visible presentation. This protocol applies to both initial and correction requests.')


def _shared_grounding(schema):
    """Conservatively recognize required controlled shots; never drop constraints."""
    if not isinstance(schema,dict) or set(schema)!={'type','properties','required','additionalProperties'}:
        return None
    if schema['type']!='object' or schema['additionalProperties'] is not False:return None
    props=schema['properties'];required=schema['required']
    if not isinstance(props,dict) or not isinstance(required,list) or not all(isinstance(k,str) for k in required):return None
    if len(required)!=len(props) or set(required)!=set(props) or '_grounded_visual' in props:return None
    shot=props.get('shot_id',{});camera=props.get('camera_motion',{})
    if not isinstance(shot,dict) or set(shot)!={'type','const'} or shot['type']!='string':return None
    if not isinstance(shot['const'],str) or re.fullmatch(r'shot_[0-9]{4}',shot['const']) is None:return None
    if not isinstance(camera,dict) or set(camera)!={'type','enum'} or camera['type']!='string':return None
    from ..planning.storyboard import CAMERA_PATHS
    choices=camera['enum']
    if not isinstance(choices,(list,tuple)) or not choices or not all(isinstance(c,str) and c in CAMERA_PATHS for c in choices):return None
    if len(set(choices))!=len(choices):return None
    prefix=None
    bounded=['maxLength' in props.get(name,{}) for name in _VISUAL_FIELDS]
    if any(bounded) and not all(bounded):return None
    for name in _VISUAL_FIELDS:
        field=props.get(name,{})
        if (not isinstance(field,dict) or not {'type','pattern','minLength'}<=set(field)
            or set(field)-{'type','pattern','minLength','maxLength'} or field['type']!='string'
            or type(field['minLength']) is not int or field['minLength']!=1):return None
        parts=_grounded_pattern_parts(field['pattern'])
        if parts is None or bool(parts[1])!=(name=='video_prompt'):return None
        if prefix is not None and parts[0]!=prefix:return None
        prefix=parts[0]
        if 'maxLength' in field and (type(field['maxLength']) is not int or _presentation_budget(field,prefix,name=='video_prompt')<1):return None
    return prefix


def _shared_context(schema,allowed):
    # A constraint/union/reference or opaque literal cannot acquire a new
    # representation underneath it: the decoder does not interpret branches.
    return allowed and not any(key in schema for key in
        ('anyOf','oneOf','allOf','not','if','then','else','$ref','$dynamicRef','const','enum'))


def _restoration_schemas(schema):
    """Only schema locations actually visited by lossless restoration."""
    if 'prefixItems' in schema:return schema['prefixItems']
    if schema.get('type')=='object':return schema.get('properties',{}).values()
    if schema.get('type')=='array':return [schema.get('items',{})]
    return []


def _has_shared_grounding(schema,allowed=True,*,bounded=False):
    if is_model_visual(schema):return False
    if isinstance(schema,(list,tuple)):return any(_has_shared_grounding(item,allowed,bounded=bounded) for item in schema)
    if not isinstance(schema,dict):return False
    allowed=_shared_context(schema,allowed)
    if not allowed:return False
    if _shared_grounding(schema) is not None and (not bounded or all('maxLength' in schema['properties'][name] for name in _VISUAL_FIELDS)):return True
    return any(_has_shared_grounding(child,allowed,bounded=bounded) for child in _restoration_schemas(schema))


def ollama_schema(schema, *, units_coverage=False):
    """Transport fixed tuples as required keyed objects for llama.cpp.

    The installed converter ignores prefixItems and cannot convert items=False.
    Keyed objects enforce each slot/binding's own constraints during generation.
    The external storyboard representation remains a strictly validated array.
    """
    if is_model_visual(schema):return project_visuals(schema)
    if units_coverage:
        wire=project_units_schema(schema)
        if wire is not None:return wire
    return _project_schema(schema,True)


def _scene_source_constraints(prompt, schema, *, key_constraints=True):
    """Constrain scene citations to real complete units without rewriting input."""
    marker='\nSCENE_INPUT_JSON\n'
    if marker not in prompt:return prompt,schema
    payload,_=json.JSONDecoder().raw_decode(prompt.split(marker,1)[1])
    text=payload['decoded_text']
    sources=[]
    for span in payload['finalized_units']['spans']:
        if span['kind']!='speech':continue
        start,end=span['start'],span['end']
        if (type(start) is not int or type(end) is not int or not 0<=start<end<=len(text)
                or span['text']!=text[start:end]):
            raise ValueError('scene source catalog differs from complete original text')
        sources.append(dict(unit_id=span['unit_id'],text_start=start,text_end=end,quote=span['text']))
    if not sources:raise ValueError('scene source catalog has no speech units')
    fields={'unit_id','text_start','text_end','quote'}
    def constrain(node):
        if isinstance(node,list):return [constrain(item) for item in node]
        if not isinstance(node,dict):return node
        if node.get('type')=='object' and set(node.get('properties',{}))==fields:
            return dict(deepcopy(node),enum=deepcopy(sources))
        result={key:constrain(value) for key,value in node.items()}
        if key_constraints and result.get('type')=='object':
            props=result.get('properties',{})
            for key in ('key','entity_key','scene_group_id'):
                if props.get(key,{}).get('type')=='string':
                    props[key].update(pattern='^[A-Za-z][A-Za-z0-9_]{0,63}$',maxLength=64)
            for key in ('entity_ids','variant_ids'):
                item=props.get(key,{}).get('items',{})
                if item.get('type')=='string':
                    item.update(pattern='^[A-Za-z][A-Za-z0-9_]{0,63}$',maxLength=64)
        return result
    note=('\nSOURCE_CITATION_RULES\nChoose complete original-unit citations from the grammar; '
          'offsets are absolute. Shared fixed appearance and environment facts must already '
          'be supported at their FIRST scene of use; cite that scene or earlier units. '
          'Later actions belong to their scene, not to shared fixed attributes.\n')
    if key_constraints:
        note+=('Use short ASCII identifiers for keys and references. Each entity/variant/group '
               'reference must exactly match a declared key; explanations belong in description fields.\n')
    return prompt+note,constrain(schema)


def ollama_body(prompt,schema,*,cpu_only=False,units_coverage=False,scene_planning=False,scene_source_constraints=True,scene_reasoning=True,model='qwen3:8b',scene_key_constraints=True,scene_environment_constraints=True):
    model=parse_scene_planner_model(model)
    if not scene_planning and model!='qwen3:8b':
        raise ValueError('alternate planner model requires scene planning')
    note=UNITS_COVERAGE_NOTE if units_coverage and project_units_schema(schema) is not None else ''
    if note:
        marker='\nINPUT_JSON\n'
        if marker in prompt:
            prefix,payload=prompt.split(marker,1);prompt=prefix+note+marker+payload
        else:prompt=note+'\n'+prompt
    body=dict(model=model,prompt=prompt+(_GROUNDING_NOTE if _has_shared_grounding(schema) else ''),
        stream=False,format=ollama_schema(schema,units_coverage=units_coverage),keep_alive=0,
        think=False,options=dict(temperature=0,num_predict=8192))
    if cpu_only:body['options']['num_gpu']=0
    if scene_planning:
        body['think']=scene_reasoning
        if scene_source_constraints:
            body['prompt'],body['format']=_scene_source_constraints(body['prompt'],body['format'],key_constraints=scene_key_constraints)
        if scene_environment_constraints:
            body['prompt'],body['format']=project_scene_environment(body['prompt'],body['format'])
        # qwen3 byte-level tokenization cannot exceed one token per UTF-8
        # byte. Count schema bytes too, even though grammar need not enter
        # the prompt, and reserve template/system plus the entire output.
        # This intentionally rejects large inputs rather than allowing
        # Ollama's implicit truncation of the beginning of the original.
        body['options']['num_ctx']=32768
        upper=(len(body['prompt'].encode('utf-8'))+
               len(json.dumps(body['format'],ensure_ascii=False,allow_nan=False).encode('utf-8'))+2048)
        if upper+body['options']['num_predict']>body['options']['num_ctx']:
            raise SceneCapacityError('scene planning context exceeds full-input capacity; no truncation or automatic retry')
    return body


def _project_schema(schema,allowed):
    if isinstance(schema,list):return [_project_schema(item,allowed) for item in schema]
    if not isinstance(schema,dict):return schema
    allowed=_shared_context(schema,allowed)
    # Never send decoded-string wildcards directly to the payload grammar.
    result={key:deepcopy(value) if key in ('const','enum') else
            {name:_project_schema(child,allowed and schema.get('type')=='object') for name,child in value.items()} if key=='properties' else
            _project_schema(value,allowed and key=='items' and schema.get('type')=='array')
            for key,value in schema.items()
            if key!='prefixItems' and not (key=='pattern' and schema.get('type')=='string')}
    if schema.get('type')=='string' and 'pattern' in schema:
        pattern=_json_payload_pattern(schema['pattern'],schema.get('maxLength'))
        if pattern is not None:result['pattern']=pattern
    if 'prefixItems' in schema:
        keys=_tuple_keys(schema)
        result=dict(type='object',properties=dict(zip(keys,_project_schema(schema['prefixItems'],allowed))),required=keys,additionalProperties=False)
    prefix=_shared_grounding(schema) if allowed else None
    if prefix is not None:
        for name in _VISUAL_FIELDS:del result['properties'][name]
        presentations={name:dict(type='string',minLength=1,pattern=_presentation_pattern(name=='video_prompt',
            _presentation_budget(schema['properties'][name],prefix,name=='video_prompt'))) for name in _VISUAL_FIELDS}
        result['properties']['_grounded_visual']=dict(type='object',properties=dict(
            fact_prefix=dict(type='string',const=prefix),presentations=dict(type='object',properties=presentations,
            required=list(_VISUAL_FIELDS),additionalProperties=False)),required=['fact_prefix','presentations'],additionalProperties=False)
        result['required']=[name for name in schema['required'] if name not in _VISUAL_FIELDS]+['_grounded_visual']
    return result


def ollama_content(value,schema):
    """Lossless restoration in frozen source order, refusing missing/extra keys."""
    if is_model_visual(schema):return restore_visuals(value,schema,_response_schema_check)
    units=restore_units_content(value,schema,_response_schema_check)
    return units if units is not None else _restore_content(value,schema,True)


def _restore_content(value,schema,allowed):
    allowed=_shared_context(schema,allowed)
    prefix=_shared_grounding(schema) if allowed else None
    if prefix is not None:
        expected=(set(schema['properties'])-set(_VISUAL_FIELDS))|{'_grounded_visual'}
        if not isinstance(value,dict) or set(value)!=expected:raise ValueError('missing/unknown grounded shot transport keys')
        group=value['_grounded_visual']
        if not isinstance(group,dict) or set(group)!={'fact_prefix','presentations'}:raise ValueError('missing/unknown grounding keys')
        actual=group['fact_prefix']
        if not isinstance(actual,str) or actual!=prefix:raise ValueError('missing/wrong emitted fact prefix')
        presentations=group['presentations']
        if not isinstance(presentations,dict) or set(presentations)!=set(_VISUAL_FIELDS):raise ValueError('missing/unknown presentation keys')
        camera=value['camera_motion']
        if not isinstance(camera,str) or camera not in schema['properties']['camera_motion']['enum']:raise ValueError('missing/wrong emitted camera')
        for name,text in presentations.items():
            if not isinstance(text,str) or not text.strip() or re.fullmatch(_presentation_pattern(name=='video_prompt',
                    _presentation_budget(schema['properties'][name],prefix,name=='video_prompt')),json.dumps(text,ensure_ascii=False)[1:-1]) is None:
                raise ValueError('invalid emitted grounded presentation length/format')
        result={name:_restore_content(item,schema['properties'][name],allowed) for name,item in value.items() if name!='_grounded_visual'}
        for name in _VISUAL_FIELDS:result[name]=actual+presentations[name]+(' Camera path: '+camera+'.' if name=='video_prompt' else '')
        _response_schema_check(result,schema)
        return result
    if 'prefixItems' in schema:
        keys=_tuple_keys(schema)
        if not isinstance(value,dict) or set(value)!=set(keys):raise ValueError('missing/unknown fixed tuple transport keys')
        return [_restore_content(value[key],item,allowed) for key,item in zip(keys,schema['prefixItems'])]
    if isinstance(value,dict) and schema.get('type')=='object':
        return {key:_restore_content(item,schema.get('properties',{}).get(key,{}),allowed) for key,item in value.items()}
    if isinstance(value,list) and schema.get('type')=='array':return [_restore_content(item,schema.get('items',{}),allowed) for item in value]
    return value


class OllamaFormatError(AdapterError):
    """Only a confirmed done response with invalid inner JSON may be corrected."""
    def __init__(self,message,evidence_paths=()):
        super().__init__(FailureKind.invalid_result,message,evidence_paths)


def _validate_request_id(request_id):
    if (not isinstance(request_id,str) or request_id not in ('initial','correction')
            and re.fullmatch(r'(units|storyboard)_batch_[0-9]{4}_(initial|correction)',request_id) is None
            and re.fullmatch(r'storyboard_batch_[0-9]{4}_entityrepair',request_id) is None
            and request_id not in ('scene_plan_initial','scene_plan_correction')):
        raise ValueError('invalid structured generation request ID')


def _completed_wire(outer, evidence_paths, *, production=False,reject_truncated=False,expected_model='qwen3:8b'):
    if (not isinstance(outer,dict) or outer.get('done') is not True or outer.get('model')!=expected_model
            or not isinstance(outer.get('response'),str) or not production and not outer['response'].strip()):
        raise AdapterError(FailureKind.ambiguous,'unconfirmed Ollama completion/model/response',evidence_paths)
    if reject_truncated and outer.get('done_reason')=='length':
        raise OllamaFormatError(f'Ollama response truncated at output token limit (eval_count={outer.get("eval_count")}); return shorter visual descriptions',evidence_paths)
    try:
        content=strict_json(outer['response'].encode('utf-8'))
        if not isinstance(content,dict): raise ValueError('inner response must be an object')
        return content
    except (ValueError,UnicodeError) as exc:
        raise OllamaFormatError(str(exc),evidence_paths) from exc


def _completed_content(content, schema, evidence_paths, *, scene_prompt=None, wire_schema=None):
    try:
        if scene_prompt is not None:
            _response_schema_check(content,wire_schema)
            content=restore_scene_content(content,scene_prompt)
        content=ollama_content(content,schema)
        _response_schema_check(content,schema)
        if _has_shared_grounding(schema,bounded=True) or is_model_visual(schema):_reject_repeated_visuals(content,schema)
        return content
    except (ValueError,UnicodeError) as exc:
        raise OllamaFormatError(str(exc),evidence_paths) from exc


def _reject_repeated_visuals(value,schema):
    """Check generated descriptions; quoted source facts are never shortened."""
    if 'const' in schema:return
    if isinstance(value,str) and 'maxLength' in schema:
        parts=_grounded_pattern_parts(schema.get('pattern'))
        text=value[len(parts[0]):] if parts else value
        for repeated in re.finditer(r'(.{4,80}?)\1{3,}',text):
            phrase=repeated.group(1)
            # Repeated labels and numeric identifiers can be literal facts;
            # a loop repeats complete narrative clauses, including punctuation.
            if any(c in '.;。；!?！？' for c in phrase) and any(c.isalpha() for c in phrase):
                raise ValueError('repeated visual presentation; describe one subject, setting and main action once')
    elif isinstance(value,dict):
        for key,item in value.items():_reject_repeated_visuals(item,schema['properties'][key])
    elif isinstance(value,list):
        prefix=schema.get('prefixItems',[])
        for index,item in enumerate(value):_reject_repeated_visuals(item,prefix[index] if index<len(prefix) else schema['items'])


def _response_schema_check(value,schema):
    """Validate the emitted subset while accepting legacy unconstrained schemas."""
    if schema is True: return
    if schema is False: raise ValueError('unexpected schema value')
    for key in ('anyOf','oneOf'):
        if key in schema:
            matches=0
            for alternative in schema[key]:
                try: _response_schema_check(value,alternative)
                except ValueError: pass
                else: matches+=1
            if not matches or key=='oneOf' and matches!=1: raise ValueError('invalid schema alternative')
    for alternative in schema.get('allOf',[]): _response_schema_check(value,alternative)
    actual=('null' if value is None else 'boolean' if type(value) is bool else 'integer' if type(value) is int
            else 'number' if type(value) is float else 'string' if isinstance(value,str)
            else 'array' if isinstance(value,list) else 'object' if isinstance(value,dict) else 'unknown')
    types=schema.get('type'); types=[types] if isinstance(types,str) else types
    if types is not None and actual not in types and not (actual=='integer' and 'number' in types):
        raise ValueError('invalid schema type')
    if 'const' in schema and (value!=schema['const'] or type(value) is bool and type(schema['const']) is not bool):
        raise ValueError('wrong schema const')
    if 'enum' in schema and value not in schema['enum']: raise ValueError('value outside schema enum')
    if actual in ('integer','number'):
        if value<schema.get('minimum',value) or value>schema.get('maximum',value): raise ValueError('value outside schema range')
    if actual=='string':
        if len(value)<schema.get('minLength',0) or len(value)>schema.get('maxLength',len(value)): raise ValueError('invalid string length')
        if 'pattern' in schema and re.search(schema['pattern'],value) is None: raise ValueError('invalid string pattern')
    if actual=='object':
        properties=schema.get('properties',{})
        if not set(schema.get('required',[]))<=set(value): raise ValueError('missing schema property')
        if schema.get('additionalProperties') is False and set(value)-set(properties): raise ValueError('unknown schema property')
        for key,item in value.items():
            _response_schema_check(item,properties.get(key,schema.get('additionalProperties',True)))
    if actual=='array':
        if not schema.get('minItems',0)<=len(value)<=schema.get('maxItems',len(value)): raise ValueError('invalid array count')
        if schema.get('uniqueItems') and len({json.dumps(v,sort_keys=True) for v in value})!=len(value): raise ValueError('duplicate array item')
        prefix=schema.get('prefixItems',[])
        for i,item in enumerate(value): _response_schema_check(item,prefix[i] if i<len(prefix) else schema.get('items',True))


def parse_completed_response(outer, *, schema, request_id, evidence_paths, expected_model='qwen3:8b', scene_prompt=None, wire_schema=None):
    """Parse confirmed durable evidence without issuing a model request."""
    _validate_request_id(request_id)
    expected_model=parse_scene_planner_model(expected_model)
    if not request_id.startswith('scene_plan_') and expected_model!='qwen3:8b':
        raise ValueError('alternate planner model requires scene planning')
    if not isinstance(schema,dict): raise ValueError('schema must be an object')
    return _completed_content(_completed_wire(outer,evidence_paths,production=request_id.startswith(('units_batch_','storyboard_batch_','scene_plan_')),
        reject_truncated=_has_shared_grounding(schema,bounded=True) or is_model_visual(schema),expected_model=expected_model),schema,evidence_paths,
        scene_prompt=scene_prompt,wire_schema=wire_schema)


class OllamaPlanner:
    def __init__(self,http: HttpClient, *, cpu_only=False, model='qwen3:8b'):
        if type(cpu_only) is not bool:raise ValueError('cpu_only must be boolean')
        self.http=http;self.cpu_only=cpu_only
        self.model=parse_scene_planner_model(model)

    def _save(self,name,data):
        path=self.http.logger.save_json(name,data)
        with path.open('r+b') as file: file.flush(); os.fsync(file.fileno())
        return path

    def generate(self,prompt: str, *, schema: dict, request_id: str, intent_context=None, on_intent=None) -> dict:
        _validate_request_id(request_id)
        if not isinstance(prompt,str) or not prompt.strip() or not isinstance(schema,dict):
            raise ValueError('invalid structured generation request')
        context_fields=({'client_id','scene_identity'} if request_id.startswith('scene_plan_') else
                        {'client_id','script_identity','shot_ranges','units_stamp','slots_stamp','global_visual'}
                        if request_id.startswith('storyboard_batch_') else {'client_id','script_identity','candidate_ranges'})
        if intent_context is not None and (not isinstance(intent_context,dict) or set(intent_context)!=context_fields):
            raise ValueError('intent context must contain exact production identity fields')
        if on_intent is not None and not callable(on_intent): raise ValueError('on_intent must be callable')
        evidence=[]
        body=ollama_body(prompt,schema,cpu_only=self.cpu_only,
            units_coverage=intent_context is not None and request_id.startswith('units_batch_'),
            scene_planning=request_id.startswith('scene_plan_'),model=self.model)
        try:
            intent=dict(request_id=request_id,body=body)
            if intent_context is not None:
                intent.update(schema=schema,prompt=prompt,context=intent_context)
            evidence.append(self._save(f'storyboard/{request_id}.intent.json',intent))
            if on_intent is not None: on_intent(evidence[-1],deepcopy(body))
            response=self.http.request('POST','/api/generate',json_body=body,max_bytes=JSON_LIMIT,stage='storyboard',unit_id=request_id)
            evidence.append(response.evidence_path)
            outer=self.http.parse_json(response,method='POST',stage='storyboard',unit_id=request_id)
            evidence.append(self._save(f'storyboard/{request_id}.outer.json',outer))
            try:
                content=_completed_wire(outer,evidence,production=intent_context is not None,reject_truncated=_has_shared_grounding(schema,bounded=True) or is_model_visual(schema),expected_model=self.model)
            except OllamaFormatError as exc:
                evidence.append(self._save(f'storyboard/{request_id}.format-error.json',dict(message=str(exc))))
                raise OllamaFormatError(str(exc),evidence) from exc
            evidence.append(self._save(f'storyboard/{request_id}.wire-content.json',content))
            try:content=_completed_content(content,schema,evidence,
                scene_prompt=prompt if is_environment_transport(body) else None,wire_schema=body['format'])
            except OllamaFormatError as exc:
                evidence.append(self._save(f'storyboard/{request_id}.format-error.json',dict(message=str(exc))))
                raise OllamaFormatError(str(exc),evidence) from exc
            evidence.append(self._save(f'storyboard/{request_id}.content.json',content))
            return content
        except AdapterError:
            raise
        except Exception as exc:
            # A service may have accepted the request even if evidence storage failed.
            raise AdapterError(FailureKind.ambiguous,str(exc),evidence) from exc
