import json
from types import SimpleNamespace

import pytest

from video_ai.runtime.production_scene_plan import use_grouped_compact, use_partition_compact, direct_attempt
from video_ai.planning.production_scenes import canonical_digest


@pytest.mark.parametrize('status,retired,expected', [(500, True, True), (500, False, False), (200, True, None), (None, True, False)])
def test_explicit_retirement_of_failed_correction(tmp_path, status, retired, expected):
    prior = tmp_path / 'compact-v1'
    prior.mkdir()
    http = tmp_path / 'http'
    http.mkdir()
    def save(path, value):
        path.write_text(json.dumps(value), encoding='utf-8')
    intent = dict(request_id='scene_plan_compact_correction', body={'prompt': 'entire source'})
    save(prior / 'initial.intent.json', {})
    save(prior / 'initial.response.json', {})
    save(prior / 'correction.intent.json', intent)
    save(http / 'request.request.json', dict(unit_id=intent['request_id'], method='POST', json_body=intent['body']))
    raw = http / 'request.body'
    raw.write_bytes(b'{}')
    if status is not None:
        save(http / 'request.response.json', dict(status=status, error=None, truncated=False, bytes=2,
             method='POST',unit_id=intent['request_id']))
    if retired:
        save(prior / 'retired.json', dict(request_id=intent['request_id'],
             body_sha256=canonical_digest(intent['body']), reason='Owned runaway model stopped; preserve original evidence'))
    logger = SimpleNamespace(path=lambda _: http)
    if expected is None:
        with pytest.raises(ValueError, match='completed original HTTP'):
            use_grouped_compact(tmp_path, logger)
    else:
        assert use_grouped_compact(tmp_path, logger) is expected


@pytest.mark.parametrize('mode',['compact-v2','compact-v3','compact-v4'])
def test_partition_cannot_bypass_historical_intent(tmp_path,mode):
    prior=tmp_path/mode
    prior.mkdir()
    (prior/'initial.intent.json').write_text('{}',encoding='utf-8')
    assert use_partition_compact(tmp_path,SimpleNamespace(path=lambda _:tmp_path)) is False


@pytest.mark.parametrize('valid',[False,True])
def test_explicit_retirement_rechecks_completed_invalid_response(tmp_path,valid):
    import hashlib
    folder=tmp_path/'partition-v1';folder.mkdir()
    http=tmp_path/'http';http.mkdir()
    schema=dict(type='object',properties=dict(x=dict(type='integer')),required=['x'],additionalProperties=False)
    body=dict(model='qwen3:8b',format=schema)
    intent=dict(request_id='scene_plan_partition_correction',body=body,schema=schema,prompt='original source')
    def save(path,value):path.write_text(json.dumps(value),encoding='utf-8')
    save(folder/'correction.intent.json',intent)
    save(folder/'correction.response.json',{})
    raw=json.dumps(dict(model='qwen3:8b',done=True,done_reason='stop',response=json.dumps(dict(x=1 if valid else 'bad')))).encode()
    (http/'a.body').write_bytes(raw)
    save(http/'a.request.json',dict(unit_id=intent['request_id'],method='POST',json_body=body))
    save(http/'a.response.json',dict(status=200,error=None,truncated=False,bytes=len(raw)))
    save(folder/'retired.json',dict(request_id=intent['request_id'],body_sha256=canonical_digest(body),
         reason='Explicit repair of confirmed invalid proposal',rejected_response_sha256=hashlib.sha256(raw).hexdigest()))
    logger=SimpleNamespace(path=lambda _:http)
    if valid:
        with pytest.raises(ValueError,match='completed original HTTP'):
            direct_attempt(folder,logger,request_prefix='scene_plan_partition_')
    else:
        attempt,prefix=direct_attempt(folder,logger,request_prefix='scene_plan_partition_')
        assert attempt==folder/'attempt_0001' and prefix=='scene_plan_partition_attempt_0001_'
