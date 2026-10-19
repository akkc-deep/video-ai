"""Reference-stage coordination uses actual records and offline boundaries."""
import json
from pathlib import Path

import pytest

from image_selection_helpers import setup_selection, candidate_manifest, save, notification_receipt
from unit.test_reference_config import capability, storage_settings, write_json


def prepared_baseline(runtime_run, tmp_path, *, accept=True, original_format='png', proposal=None):
    from video_ai.runtime import image_selection_records as records
    from video_ai.runtime.production_image_selection import consume_image_selection
    from video_ai.runtime.logging import RunLogger
    from video_ai.planning.production_scenes import canonical_digest
    s = setup_selection(runtime_run, tmp_path, proposal=proposal)
    s['logger'] = RunLogger(s['run'], production=True)
    manifests = [candidate_manifest(s, sid) for sid in s['plan']['batches'][0]]
    if original_format == 'jpeg':
        import hashlib
        import subprocess
        first = next(manifests[0].parent.rglob('*.original'))
        jpeg = s['run']/'baseline.jpeg'
        subprocess.run([str(s['frozen'].config.tools['ffmpeg']), '-nostdin', '-v', 'error', '-i', str(first),
                        '-frames:v', '1', '-q:v', '2', str(jpeg)], check=True, capture_output=True)
        raw = jpeg.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
        for manifest_path in manifests:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            for row in manifest['candidates']:
                path = Path(row['path']); path.write_bytes(raw)
                row.update(bytes=len(raw), sha256=digest, format='mjpeg')
                save(path.with_suffix('.json'), row)
                receipt = json.loads(path.with_suffix('.download.json').read_text(encoding='utf-8'))
                receipt.update(bytes=len(raw), sha256=digest); save(path.with_suffix('.download.json'), receipt)
            for result_path in manifest_path.parent.glob('*/result.json'):
                result = json.loads(result_path.read_text(encoding='utf-8'))
                result['candidates'] = [row for row in manifest['candidates'] if row['request_id'] == result_path.parent.name]
                save(result_path, result)
            save(manifest_path, manifest)
    batch = records.build_batch(s['frozen'], s['units'], s['timeline'], manifests, batch_index=1)
    folder = s['run']/'production/image-selection'/batch['batch_id']
    save(folder/'batch.json', batch)
    template = records.selection_template(batch)
    save(folder/'selection-template.json', template)
    save(folder.parent/'active-batch.json', dict(schema_version=2, run_id=s['run'].name,
         batch_id=batch['batch_id'], batch_sha256=canonical_digest(batch)))
    notification_receipt(s, batch)
    if accept:
        value = dict(template, intent='accept', selections=[dict(scene_id=row['scene_id'],
                     candidate_id=row['candidates'][0]['candidate_id'], sha256=row['candidates'][0]['sha256'])
                     for row in batch['scenes']])
        result = consume_image_selection(s['frozen'], s['units'], s['timeline'],
            save(s['run']/'first-selection.json', value), paths=s['paths'], logger=s['logger'])
        assert result.status == 'image_batch_accepted', result.error
    cap_path = write_json(tmp_path/'reference-capability.json', capability())
    s['reference_settings_path'] = write_json(tmp_path/'reference-settings.json', dict(reference_generation=None,
        reference_capabilities={'jimeng_t2i_v40': str(cap_path)}, reference_storage=storage_settings()))
    return s


def produce(s, **kwargs):
    from video_ai.runtime.production_reference_images import produce_reference_batch
    return produce_reference_batch(s['frozen'], s['units'], s['timeline'], batch_index=2,
                                   paths=s['paths'], logger=s['logger'], **kwargs)


def test_missing_configuration_wait_preserves_baseline_and_releases_lock(runtime_run, tmp_path):
    s = prepared_baseline(runtime_run, tmp_path)
    original = next((s['run']/'production/image-selection').glob('image_batch_*/accepted.json')).read_bytes()
    result = produce(s)
    assert result.status == 'awaiting_image_model_configuration' and result.exit_code == 3
    assert result.wan_inputs is None and result.selection_result is None
    assert set(result.to_dict()) == set('schema_version production_strategy run_id run_dir status active_stage batch_id selection_result wan_inputs log_dir error'.split())
    assert not (s['run']/'.make-video.lock').exists()
    assert next((s['run']/'production/image-selection').glob('image_batch_*/accepted.json')).read_bytes() == original
    assert not (s['run']/'production/reference-images/settings.json').exists()


def test_unselected_baseline_stops_before_settings_and_network(runtime_run, tmp_path):
    s = prepared_baseline(runtime_run, tmp_path, accept=False)
    result = produce(s, reference_settings_path=s['reference_settings_path'])
    assert result.status == 'blocked' and result.exit_code == 2
    assert not (s['run']/'production/reference-images/settings.json').exists()
    assert not list((s['run']/'production/jimeng').glob('scene_0002/*/intent.json'))


def test_external_lock_retained_for_configuration_wait(runtime_run, tmp_path):
    from video_ai.runtime.production_state import RunLock
    s = prepared_baseline(runtime_run, tmp_path)
    with RunLock(s['run']) as held:
        assert produce(s, lock=held).status == 'awaiting_image_model_configuration'
        assert held.path.exists()
    assert not held.path.exists()


def test_reference_result_exit_codes_and_exact_schema():
    from video_ai.runtime.production_reference_images import ReferencePreparationResult
    for status, code in [('awaiting_image_model_configuration', 3), ('blocked', 2), ('failed', 1), ('interrupted', 130)]:
        assert ReferencePreparationResult(status=status).exit_code == code
    with pytest.raises(ValueError): ReferencePreparationResult(status='completed')
    with pytest.raises(ValueError): ReferencePreparationResult(schema_version=True)
    with pytest.raises(ValueError): ReferencePreparationResult(wan_inputs=Path('D:/unverified.json'))


class OfflineCloud:
    """HTTP-level doubles retain actual controlled request bodies in memory only."""
    def __init__(self, s):
        self.s = s; self.objects = {}; self.storage_calls = []; self.submits = []; self.queries = []; self.downloads = []
        self.unknown = False
        self.raw = next((s['run']/'production/jimeng/scene_0001').rglob('*.original')).read_bytes()

    def storage_request(self, method, url, **kwargs):
        from video_ai.adapters.external_https import ExternalResponse
        kwargs['ownership_check']()
        self.storage_calls.append(method)
        if method == 'HEAD':
            if url not in self.objects: return ExternalResponse(404, b'')
            raw, headers = self.objects[url]
            return ExternalResponse(200, b'', headers)
        if method == 'PUT':
            raw = kwargs['body']
            headers = {'Content-Length': str(len(raw)), 'Content-Type': kwargs['headers']['content-type'],
                       'x-tos-meta-sha256': kwargs['headers']['x-tos-meta-sha256'], 'ETag': 'offline-etag'}
            self.objects[url] = raw, headers
            return ExternalResponse(200, b'')
        assert method == 'GET'
        return ExternalResponse(200, self.objects[url][0])

    def official_request(self, method, url, **kwargs):
        from video_ai.adapters.external_https import ExternalResponse
        from video_ai.adapters.common import AdapterError, FailureKind
        from video_ai.adapters.jimeng import encode_body
        if method == 'GET':
            self.downloads.append(url)
            return ExternalResponse(200, self.raw)
        payload = json.loads(kwargs['body'])
        if 'CVSync2AsyncSubmitTask' in url:
            self.submits.append(payload)
            if self.unknown: raise AdapterError(FailureKind.ambiguous, 'offline ambiguous submit')
            data = dict(task_id='ref-task-'+str(len(self.submits)))
        else:
            self.queries.append(payload['task_id'])
            data = dict(status='done', image_urls=['https://cdn.example.test/'+payload['task_id']+'.png'])
        return ExternalResponse(200, encode_body(dict(code=10000, request_id='offline-request', data=data)))


def configured_cloud(s, monkeypatch):
    from types import SimpleNamespace
    from video_ai.adapters.jimeng import JimengClient
    from video_ai.adapters.reference_storage import ReferenceStorage
    from video_ai.reference_config import parse_reference_storage
    from integration.test_image_selection_flow import SMTP
    for name in ('TEST_TOS_AK', 'TEST_TOS_SK', 'TEST_VOLC_AK', 'TEST_VOLC_SK', 'VIDEO_AI_SMTP_AUTH_CODE'):
        monkeypatch.setenv(name, 'offline-secret-'+name)
    cloud = OfflineCloud(s); smtp = SMTP()
    storage = ReferenceStorage(parse_reference_storage(storage_settings()),
                               http=SimpleNamespace(request=cloud.storage_request))
    kwargs = dict(reference_settings_path=s['reference_settings_path'], storage=storage,
        client_factory=lambda model: JimengClient(model, http=SimpleNamespace(request=cloud.official_request)),
        smtp_factory=smtp.factory)
    return cloud, smtp, kwargs


def accept_reference_batch(s, result, *, observation=False):
    from video_ai.runtime.production_image_selection import consume_image_selection
    nested = result.selection_result
    path = Path(nested['selection_template'])
    value = json.loads(path.read_text(encoding='utf-8'))
    batch = json.loads((path.parent/'batch.json').read_text(encoding='utf-8'))
    value.update(intent='accept', selections=[dict(scene_id=row['scene_id'], candidate_id=row['candidates'][0]['candidate_id'],
                  sha256=row['candidates'][0]['sha256']) for row in batch['scenes']])
    if observation:
        choices = []
        for accepted in sorted((s['run']/'production/image-selection').glob('image_batch_*/accepted.json')):
            choices.extend({key: row[key] for key in ('scene_id', 'candidate_id', 'sha256')}
                           for row in json.loads(accepted.read_text(encoding='utf-8'))['selections'])
        by_scene = {row['scene_id']: row for row in choices+value['selections']}
        value['observation'] = dict(scope='all_selected_images', review_method='human_image', reviewer='offline fixture',
            viewed_images=list(by_scene.values()), subject_consistency='passed', style_consistency='passed',
            verdict='passed', issues=[], reason='Synthetic observation fixture; no real model quality assertion.')
    return consume_image_selection(s['frozen'], s['units'], s['timeline'],
        save(s['run']/'reference-selection.json', value), paths=s['paths'], logger=s['logger'])


def test_actual_reference_requests_fixed_baseline_and_complete_wan_images(runtime_run, tmp_path, monkeypatch):
    from video_ai.runtime.reference_image_records import require_reference_image_acceptance
    s = prepared_baseline(runtime_run, tmp_path)
    cloud, smtp, kwargs = configured_cloud(s, monkeypatch)
    result = produce(s, **kwargs)
    assert result.status == 'awaiting_image_selection', result.error
    assert len(cloud.submits) == 4 and len(smtp.messages) == 1
    baseline = json.loads((s['run']/'production/image-selection/image_batch_0001/accepted.json').read_text())['selections'][0]
    for payload in cloud.submits:
        assert payload['req_key'] == s['frozen'].config.image_generation.req_key
        assert len(payload['image_urls']) == 1
        assert baseline['sha256']+'.original?' in payload['image_urls'][0]
        assert '\nVISUAL_BIBLE_JSON\n' in payload['prompt']
        assert '写实自然光' in payload['prompt']
    for sid in ('scene_0002', 'scene_0003'):
        provenance = json.loads((s['run']/f'production/reference-images/{sid}/provenance.json').read_text(encoding='utf-8'))
        reference = provenance['references'][0]
        assert reference['scene_id'] == 'scene_0001' and reference['candidate_id'] == baseline['candidate_id']
        assert reference['sha256'] == baseline['sha256']
        assert reference['uses'] == [dict(kind='entity', id='entity_0001'), dict(kind='scene_group', id='group_0001')]
    assert not (s['run']/'production/reference-images/wan-inputs.json').exists()
    assert accept_reference_batch(s, result).status == 'awaiting_image_selection'
    assert not (s['run']/'production/reference-images/wan-inputs.json').exists()
    assert accept_reference_batch(s, result, observation=True).all_images_accepted
    assert produce(s, **kwargs).status == 'images_ready'
    manifest = require_reference_image_acceptance(s['frozen'], s['units'], s['timeline'])
    assert [row['scene_id'] for row in manifest['scenes']] == ['scene_0001', 'scene_0002', 'scene_0003']
    assert manifest['scenes'][0]['reference_provenance_sha256'] is None
    assert all(row['reference_provenance_sha256'] for row in manifest['scenes'][1:])
    assert len(cloud.submits) == 4 and len(smtp.messages) == 1
    for path in (s['run']/'production').rglob('*.json'):
        raw = path.read_text(encoding='utf-8')
        assert 'X-Tos-Signature=' not in raw and 'offline-secret-' not in raw and 'Authorization' not in raw
    selected = Path(manifest['scenes'][0]['path']); original = selected.read_bytes()
    selected.write_bytes(original+b'changed')
    with pytest.raises(ValueError): require_reference_image_acceptance(s['frozen'], s['units'], s['timeline'])
    selected.write_bytes(original)
    provenance_path = s['run']/'production/reference-images/scene_0002/provenance.json'
    provenance_raw = provenance_path.read_bytes(); provenance = json.loads(provenance_raw)
    provenance['prompt_sha256'] = 'f'*64; save(provenance_path, provenance)
    with pytest.raises(ValueError): require_reference_image_acceptance(s['frozen'], s['units'], s['timeline'])
    provenance_path.write_bytes(provenance_raw)
    assert not (s['run']/'.make-video.lock').exists()


def test_ambiguous_submit_resumes_without_second_paid_request(runtime_run, tmp_path, monkeypatch):
    s = prepared_baseline(runtime_run, tmp_path)
    cloud, smtp, kwargs = configured_cloud(s, monkeypatch); cloud.unknown = True
    assert produce(s, **kwargs).status in ('failed', 'blocked')
    assert len(cloud.submits) == 1 and not smtp.messages
    cloud.unknown = False
    result = produce(s, **kwargs)
    assert result.status == 'blocked' and 'submit_unknown' in result.error['message']
    assert len(cloud.submits) == 1


def test_notification_failure_resumes_only_mail(runtime_run, tmp_path, monkeypatch):
    s = prepared_baseline(runtime_run, tmp_path)
    cloud, smtp, kwargs = configured_cloud(s, monkeypatch); smtp.fail = 'auth'
    result = produce(s, **kwargs)
    assert result.status == 'blocked', result.error
    assert len(cloud.submits) == 4
    smtp.fail = None
    assert produce(s, **kwargs).status == 'awaiting_image_selection'
    assert len(cloud.submits) == 4 and len(smtp.messages) == 1


@pytest.mark.parametrize('point', ['reference-settings', 'storage-intent', 'storage-object', 'reference-candidates'])
def test_durable_boundaries_release_lock_and_resume(runtime_run, tmp_path, monkeypatch, point):
    import video_ai.runtime.production_reference_images as module
    s = prepared_baseline(runtime_run, tmp_path)
    cloud, smtp, kwargs = configured_cloud(s, monkeypatch)
    fired = []
    def interrupt(observed):
        if observed == point and not fired:
            fired.append(observed); raise KeyboardInterrupt()
    monkeypatch.setattr(module, 'boundary', interrupt)
    result = produce(s, **kwargs)
    assert fired and result.status == 'interrupted', result.error
    assert not (s['run']/'.make-video.lock').exists()
    monkeypatch.setattr(module, 'boundary', lambda observed: None)
    assert produce(s, **kwargs).status == 'awaiting_image_selection'
    assert len(cloud.submits) == 4


@pytest.mark.parametrize('change', ['bytes', 'dimensions', 'format', 'prompt', 'ttl'])
def test_batch_limits_stop_before_any_cloud_request(runtime_run, tmp_path, monkeypatch, change):
    s = prepared_baseline(runtime_run, tmp_path)
    cloud, smtp, kwargs = configured_cloud(s, monkeypatch)
    value = json.loads(s['reference_settings_path'].read_text(encoding='utf-8'))
    cap_path = Path(value['reference_capabilities']['jimeng_t2i_v40'])
    cap = json.loads(cap_path.read_text(encoding='utf-8'))
    if change == 'bytes': cap['max_image_bytes'] = 1
    elif change == 'dimensions': cap['min_width'] = 4096
    elif change == 'format': cap['formats'] = ['jpeg']
    elif change == 'prompt': cap['max_prompt_bytes'] = 10
    else: value['reference_storage']['url_ttl_seconds'] = 100
    write_json(cap_path, cap); write_json(s['reference_settings_path'], value)
    result = produce(s, **kwargs)
    assert result.status == 'awaiting_image_model_configuration', result.error
    assert not cloud.storage_calls and not cloud.submits and not smtp.messages


def test_own_lock_release_error_uses_reference_result_schema(runtime_run, tmp_path, monkeypatch):
    from video_ai.runtime.production_state import RunLock
    s = prepared_baseline(runtime_run, tmp_path)
    original = RunLock.__exit__
    def release(self, *args):
        original(self, *args)
        raise OSError('private failure details')
    monkeypatch.setattr(RunLock, '__exit__', release)
    result = produce(s)
    assert result.status == 'failed' and result.schema_version == 2
    assert result.error['kind'] == 'OSError' and 'private failure' not in result.error['message']
    assert not (s['run']/'.make-video.lock').exists()


def test_real_jpeg_baseline_can_be_used_for_reference_generation(runtime_run, tmp_path, monkeypatch):
    s = prepared_baseline(runtime_run, tmp_path, original_format='jpeg')
    cloud, smtp, kwargs = configured_cloud(s, monkeypatch)
    result = produce(s, **kwargs)
    assert result.status == 'awaiting_image_selection', result.error
    assert len(cloud.submits) == 4 and len(smtp.messages) == 1
    assert all(headers['Content-Type'] == 'image/jpeg' for raw, headers in cloud.objects.values())


def test_distinct_baselines_with_identical_bytes_share_object_preserving_uses(runtime_run, tmp_path, monkeypatch):
    from unit.test_production_scenes import scene_proposal
    proposal = scene_proposal()
    proposal['entities'].append(dict(proposal['entities'][0], key='second-bird', label='另一只白鸟'))
    proposal['scene_groups'].append(dict(proposal['scene_groups'][0], key='second-lake', label='另一处湖畔'))
    proposal['scenes'][1].update(entity_ids=['second-bird'], scene_group_id='second-lake')
    proposal['scenes'][2]['entity_ids'].append('second-bird')
    from video_ai.planning.segments import segment_text
    spans = segment_text('湖面很静。白鸟停在石上。它望向远处。\r\n\r\n它飞走了。')
    for index, unit in ((1, 'speech_0003'), (2, 'speech_0004')):
        span = next(row for row in spans if row.unit_id == unit)
        proposal['scenes'][index]['change_sources'] = [dict(unit_id=unit, text_start=span.start, text_end=span.end, quote=span.text)]
    s = prepared_baseline(runtime_run, tmp_path, proposal=proposal)
    assert s['plan']['batches'] == [['scene_0001', 'scene_0002'], ['scene_0003']]
    source = json.loads(s['reference_settings_path'].read_text(encoding='utf-8'))
    cap_path = Path(source['reference_capabilities']['jimeng_t2i_v40'])
    write_json(cap_path, capability(max_images=2))
    cloud, smtp, kwargs = configured_cloud(s, monkeypatch)
    result = produce(s, **kwargs)
    assert result.status == 'awaiting_image_selection', result.error
    assert cloud.storage_calls.count('PUT') == 1 and len(cloud.submits) == 2
    assert all(len(payload['image_urls']) == 2 for payload in cloud.submits)
    provenance = json.loads((s['run']/'production/reference-images/scene_0003/provenance.json').read_text(encoding='utf-8'))
    assert [row['scene_id'] for row in provenance['references']] == ['scene_0001', 'scene_0002']
    assert provenance['references'][0]['object'] == provenance['references'][1]['object']


def test_complete_text_only_selections_cannot_pass_reference_admission(runtime_run, tmp_path):
    from types import SimpleNamespace
    from video_ai.runtime import image_selection_records as records
    from video_ai.runtime.reference_image_records import build_reference_image_acceptance
    from video_ai.planning.production_scenes import canonical_digest
    s = prepared_baseline(runtime_run, tmp_path)
    manifests = [candidate_manifest(s, sid) for sid in s['plan']['batches'][1]]
    batch = records.build_batch(s['frozen'], s['units'], s['timeline'], manifests, batch_index=2)
    folder = s['run']/'production/image-selection'/batch['batch_id']
    save(folder/'batch.json', batch); template = save(folder/'selection-template.json', records.selection_template(batch))
    save(folder.parent/'active-batch.json', dict(schema_version=2, run_id=s['run'].name,
        batch_id=batch['batch_id'], batch_sha256=canonical_digest(batch)))
    notification_receipt(s, batch)
    result = SimpleNamespace(selection_result=dict(selection_template=str(template)))
    assert accept_reference_batch(s, result, observation=True).all_images_accepted
    assert records.require_complete_image_acceptance(s['frozen'], s['units'], s['timeline'])
    with pytest.raises(ValueError): build_reference_image_acceptance(s['frozen'], s['units'], s['timeline'])
    assert not (s['run']/'production/reference-images/wan-inputs.json').exists()
