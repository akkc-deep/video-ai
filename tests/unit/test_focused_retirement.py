import hashlib
import json
from types import SimpleNamespace

import pytest

from video_ai.planning.production_scenes import canonical_digest


def test_new_visual_transport_requires_explicit_body_bound_terminal_failure(tmp_path):
    from video_ai.runtime.focused_scene_planning import require_retired_visual_v2
    folder=tmp_path/'focused-v1';old=folder/'visual-v2';batch=old/'batch_0002';batch.mkdir(parents=True)
    http=tmp_path/'http';http.mkdir()
    uid='scene_plan_focused_visual2_0002_initial';url='http://127.0.0.1:11435/api/generate';body={'prompt':'original'}
    def save(path,value):path.write_text(json.dumps(value),encoding='utf-8')
    save(batch/'initial.intent.json',dict(request_id=uid,body=body))
    req=http/'request.request.json';save(req,dict(method='POST',url=url,unit_id=uid,json_body=body))
    raw=json.dumps({'error':'ConnectionResetError: backend stopped'}).encode()
    (http/'request.body').write_bytes(raw)
    meta=dict(method='POST',url=url,unit_id=uid,status=500,bytes=len(raw),truncated=False,error=None)
    save(http/'request.response.json',meta)
    logger=SimpleNamespace(path=lambda name:http)
    frozen=SimpleNamespace(config=SimpleNamespace(services={'ollama':'http://127.0.0.1:11435'}))
    with pytest.raises(ValueError):require_retired_visual_v2(folder,frozen=frozen,logger=logger)
    save(old/'retired.json',dict(request_id=uid,body_sha256=canonical_digest(body),
        response_sha256=hashlib.sha256(raw).hexdigest(),reason='Operator stopped unbounded local inference'))
    require_retired_visual_v2(folder,frozen=frozen,logger=logger)
    meta['status']=200;save(http/'request.response.json',meta)
    with pytest.raises(ValueError):require_retired_visual_v2(folder,frozen=frozen,logger=logger)
