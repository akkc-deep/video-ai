"""Offline, real-PNG reference input and HTTP fixtures."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from image_selection_helpers import setup_selection, save
from unit.test_image_selection_records import batch, accept_batch
from unit.test_reference_config import capability, storage_settings


class ReferenceStorageFixture:
    def __init__(self, settings):
        self.settings = settings
        self.presigns = 0
        self.offset = 0

    def presign_get(self, record, *, expires_seconds):
        self.presigns += 1
        issued = datetime.now(timezone.utc)+timedelta(seconds=self.offset)
        return dict(url='https://'+record['bucket']+'.tos-'+record['region']+'.volces.com/'+record['key']+'?signature=private',
                    issued_at=issued.isoformat(), expires_at=(issued+timedelta(seconds=expires_seconds)).isoformat())


def reference_setup(runtime_run, tmp_path, monkeypatch, *, capability_changes=None):
    from video_ai.adapters.jimeng import JimengClient
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.runtime.jimeng_candidates import _Records
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.reference_settings import bind_reference_settings
    from video_ai.runtime.reference_image_records import resolve_reference_bindings
    s = setup_selection(runtime_run, tmp_path)
    accepted = accept_batch(s, batch(s), accepted=[])
    cap_path = save(tmp_path/'reference-cap.json', capability(**(capability_changes or {})))
    source = save(tmp_path/'reference-settings.json', dict(reference_generation=None,
        reference_capabilities={'jimeng_t2i_v40': str(cap_path)}, reference_storage=storage_settings()))
    with RunLock(s['run']) as held:
        settings = bind_reference_settings(s['frozen'], store=_Records(s['run'], held), reference_settings_path=source)
    scene = s['plan']['scenes'][1]
    resolved = resolve_reference_bindings(s['frozen'], s['bible'], s['plan'], scene, [accepted])
    references = []
    for original, uses in resolved:
        obj = dict(bucket='test-bucket', region='cn-beijing', endpoint='https://tos-cn-beijing.volces.com',
            key='video-ai-references/'+s['run'].name+'/'+original['sha256']+'.original',
            bytes=original['bytes'], sha256=original['sha256'], content_type='image/png', etag='fixture-etag')
        intent = dict(schema_version=2, run_id=s['run'].name, object={k:v for k,v in obj.items() if k != 'etag'},
            source={k:original[k] for k in ('path', 'bytes', 'sha256')}, created_at=datetime.now(timezone.utc).isoformat())
        folder = s['run']/'production/reference-storage'/original['sha256']
        save(folder/'intent.json', intent)
        save(folder/'object.json', dict(schema_version=2, run_id=s['run'].name,
            intent_sha256=canonical_digest(intent), object=obj, verified_at=datetime.now(timezone.utc).isoformat()))
        references.append(dict({k:original[k] for k in ('scene_id','candidate_id','sha256','bytes','width','height','format')},
                               uses=uses, object=obj))
    state = dict(submits=[], queries=[], downloads=0, failure=None)
    png = Path(resolved[0][0]['path']).read_bytes()
    class Http:
        def request(self, method, url, **kw):
            if method == 'GET':
                state['downloads'] += 1
                if state['failure'] == 'download': raise TimeoutError('fixture download timeout')
                return SimpleNamespace(body=png)
            from urllib.parse import parse_qs, urlsplit
            payload = json.loads(kw['body']); action = parse_qs(urlsplit(url).query)['Action'][0]
            if action == 'CVSync2AsyncSubmitTask':
                state['submits'].append(payload)
                if state['failure'] == 'submit': raise TimeoutError('fixture submit response lost')
                reply = dict(code=10000, data={'task_id': 'task_'+str(len(state['submits']))}, request_id='official_submit')
            else:
                state['queries'].append(payload['task_id'])
                if state['failure'] == 'query': raise TimeoutError('fixture query timeout')
                reply = dict(code=10000, data=dict(status='done', image_urls=['https://cdn.example/output?signature=private']), request_id='official_query')
            return SimpleNamespace(body=json.dumps(reply).encode())
    monkeypatch.setenv('TEST_VOLC_AK', 'fixture-ak'); monkeypatch.setenv('TEST_VOLC_SK', 'fixture-sk')
    s.update(settings=settings, references=references, scene=scene, accepted=[accepted], state=state,
             storage=ReferenceStorageFixture(settings['storage']), client=JimengClient(s['frozen'].config.image_generation, http=Http()))
    return s


def generate_reference(s, **kw):
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.jimeng_reference_candidates import generate_reference_candidates
    with RunLock(s['run']) as held:
        return generate_reference_candidates(s['frozen'], s['scene'], s['bible'], s['references'],
            settings=s['settings'], capability=s['settings']['capability'], client=s['client'],
            paths=s['paths'], logger=None, lock=held, storage=s['storage'], **kw)
