"""Strict read-only admission of exact candidate, selection and observation identities."""
from copy import deepcopy
import hashlib
import json

import pytest

from image_selection_helpers import candidate_manifest, notification_receipt, save, setup_selection


@pytest.fixture
def selection_setup(runtime_run, tmp_path):
    return setup_selection(runtime_run, tmp_path)


def batch(s, index=1):
    from video_ai.runtime.image_selection_records import build_batch
    manifests = [candidate_manifest(s, sid) for sid in s['plan']['batches'][index-1]]
    return build_batch(s['frozen'], s['units'], s['timeline'], manifests, batch_index=index)


def validate(s, b, value, accepted=()):
    from video_ai.runtime.image_selection_records import validate_selection
    return validate_selection(s['frozen'], s['bible'], s['plan'], b, value, accepted_batches=list(accepted))


def submitted(b, intent='accept'):
    from video_ai.runtime.image_selection_records import selection_template
    result = selection_template(b); result['intent'] = intent
    result['selections'] = [dict(scene_id=row['scene_id'], candidate_id=row['candidates'][0]['candidate_id'],
                                 sha256=row['candidates'][0]['sha256']) for row in b['scenes']]
    return result


def test_committed_batch_is_bound_to_original_text_and_read_only(selection_setup):
    from video_ai.runtime.image_selection_records import load_committed_plan, validate_batch
    s = selection_setup; b = batch(s)
    before = {p: p.stat().st_mtime_ns for p in s['run'].rglob('*') if p.is_file()}
    assert load_committed_plan(s['frozen'], s['units'], s['timeline']) == (s['bible'], s['plan'])
    assert b['scenes'][0]['original_text'] == s['frozen'].script.text[:s['plan']['scenes'][0]['text_end']]
    assert b['baseline_bindings'] == []
    validate_batch(s['frozen'], s['units'], s['timeline'], s['bible'], s['plan'], b)
    assert {p: p.stat().st_mtime_ns for p in s['run'].rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('change', ['commit', 'bible', 'units', 'bool'])
def test_committed_plan_rejects_changed_binding(selection_setup, change):
    from video_ai.runtime.image_selection_records import load_committed_plan
    s = selection_setup
    if change == 'units': s['units']['semantic_specs']['speech_0001']['facts']['subject'] = 'changed'
    else:
        path = s['run']/'production'/('visual-bible.json' if change == 'bible' else 'scene-plan-commit.json')
        value = json.loads(path.read_text(encoding='utf-8'))
        value['schema_version' if change == 'bool' else 'source_sha256'] = True if change == 'bool' else 'f'*64
        save(path, value)
    with pytest.raises(ValueError): load_committed_plan(s['frozen'], s['units'], s['timeline'])


@pytest.mark.parametrize('change', ['manifest', 'request', 'result', 'download', 'original', 'dimensions'])
def test_batch_checks_backing_candidate_records(selection_setup, change):
    from video_ai.runtime.image_selection_records import build_batch
    s = selection_setup; manifest = candidate_manifest(s, 'scene_0001')
    folder = manifest.parent/'request_01'
    if change == 'original': (folder/'request_01_image_01.original').write_bytes(b'bad image')
    else:
        path = {'manifest': manifest, 'request': folder/'request.json', 'result': folder/'result.json',
                'download': folder/'request_01_image_01.download.json', 'dimensions': folder/'request_01_image_01.json'}[change]
        value = json.loads(path.read_text(encoding='utf-8'))
        if change == 'dimensions': value['width'] = True
        elif change == 'result': value['candidates'][0]['task_id'] = 'foreign'
        elif change == 'manifest': value['run_id'] = 'foreign'
        elif change == 'request': value['prompt'] += 'changed'
        else: value['sha256'] = 'f'*64
        save(path, value)
    with pytest.raises(ValueError): build_batch(s['frozen'], s['units'], s['timeline'], [manifest], batch_index=1)


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'foreign_scene', 'foreign_candidate', 'sha', 'bool', 'extra', 'baseline'])
def test_selection_rejects_incomplete_or_foreign_identity(selection_setup, change):
    s = selection_setup; b = batch(s); value = submitted(b)
    if change == 'missing': value['selections'] = []
    elif change == 'duplicate': value['selections'] *= 2
    elif change == 'foreign_scene': value['selections'][0]['scene_id'] = 'scene_9999'
    elif change == 'foreign_candidate': value['selections'][0]['candidate_id'] = 'unknown'
    elif change == 'sha': value['selections'][0]['sha256'] = 'A'*64
    elif change == 'bool': value['schema_version'] = True
    elif change == 'extra': value['passed'] = True
    else: value['baseline_bindings'] = [dict(kind='entity', id='entity_0001', scene_id='scene_0001', candidate_id='fake', sha256='a'*64)]
    with pytest.raises(ValueError): validate(s, b, value)


def test_draft_does_not_invent_observation_or_selections(selection_setup):
    from video_ai.runtime.image_selection_records import selection_template
    s = selection_setup; b = batch(s)
    assert validate(s, b, selection_template(b)) == dict(selections=[], observation=None)


def test_baseline_dependencies_need_prior_accepted_and_preserve_each_use(selection_setup):
    from video_ai.runtime.image_selection_records import build_accepted, load_accepted_batches
    s = selection_setup; b = batch(s)
    with pytest.raises(ValueError): batch(s, 2)
    value = submitted(b); raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
    sha = hashlib.sha256(raw).hexdigest()
    accepted = build_accepted(b, validate(s, b, value), source_submission_sha256=sha,
                                                  bible=s['bible'], accepted_batches=[])
    save(s['run']/'production/image-selection/image_batch_0001/batch.json', b)
    save(s['run']/'production/image-selection/image_batch_0001/accepted.json', accepted)
    save(s['run']/'production/image-selection/image_batch_0001/submissions'/(sha+'.json'), value)
    notification_receipt(s,b)
    b2 = batch(s, 2)
    assert [r['kind'] for r in b2['baseline_bindings']] == ['entity', 'scene_group']
    assert len(load_accepted_batches(s['frozen'], s['units'], s['timeline'])) == 1


@pytest.mark.parametrize('change', ['coverage', 'passed_issue', 'failed_empty', 'method', 'reviewer'])
def test_observation_is_explicit_exact_and_consistent(selection_setup, change):
    s = selection_setup; b = batch(s); value = submitted(b)
    obs = dict(scope='current_batch', review_method='human_image', reviewer='reviewer',
               viewed_images=deepcopy(value['selections']), subject_consistency='passed',
               style_consistency='passed', verdict='passed', issues=[], reason='Viewed exact originals together')
    if change == 'coverage': obs['viewed_images'] = []
    elif change == 'passed_issue': obs['issues'] = ['visible mismatch']
    elif change == 'failed_empty': obs['verdict'] = 'failed'
    elif change == 'method': obs['review_method'] = 'hash'
    else: obs['reviewer'] = ' '
    value['observation'] = obs
    with pytest.raises(ValueError): validate(s, b, value)


def test_complete_requires_explicit_whole_set_observation_and_durable_receipt(selection_setup):
    from video_ai.runtime.image_selection_records import require_complete_image_acceptance
    s = selection_setup
    with pytest.raises(ValueError): require_complete_image_acceptance(s['frozen'], s['units'], s['timeline'])


def accept_batch(s, b, *, accepted):
    from video_ai.runtime.image_selection_records import build_accepted
    value = submitted(b)
    sha = hashlib.sha256(json.dumps(value, ensure_ascii=False).encode('utf-8')).hexdigest()
    receipt = build_accepted(b, validate(s, b, value, accepted), source_submission_sha256=sha,
                             bible=s['bible'], accepted_batches=accepted)
    folder = s['run']/'production/image-selection'/b['batch_id']
    save(folder/'batch.json', b); save(folder/'accepted.json', receipt)
    save(folder/'submissions'/(sha+'.json'), value)
    notification_receipt(s,b)
    return receipt


def test_complete_revalidates_all_originals_and_explicit_observation_submission(selection_setup):
    from video_ai.runtime.image_selection_records import build_complete_acceptance, require_complete_image_acceptance
    s = selection_setup; b1 = batch(s); a1 = accept_batch(s, b1, accepted=[])
    b2 = batch(s, 2); a2 = accept_batch(s, b2, accepted=[a1]); accepted = [a1,a2]
    value = submitted(b2)
    value['observation'] = dict(scope='all_selected_images', review_method='human_image', reviewer='reviewer',
        viewed_images=[{k:r[k] for k in ('scene_id','candidate_id','sha256')} for a in accepted for r in a['selections']],
        subject_consistency='passed', style_consistency='passed', verdict='passed', issues=[], reason='Viewed all originals')
    normalized = validate(s, b2, value, accepted)
    sha = hashlib.sha256(json.dumps(value, ensure_ascii=False).encode('utf-8')).hexdigest()
    save(s['run']/'production/image-selection'/b2['batch_id']/'submissions'/(sha+'.json'), value)
    complete = build_complete_acceptance(s['frozen'], s['bible'], s['plan'], accepted,
        normalized['observation'], observation_submission_sha256=sha)
    save(s['run']/'production/image-selection/complete-acceptance.json', complete)
    assert require_complete_image_acceptance(s['frozen'], s['units'], s['timeline']) == complete
    receipt = s['run']/'production/image-selection'/b1['batch_id']/'mail/part_0001/attempt_0001/receipt.json'
    saved = receipt.read_bytes(); receipt.unlink()
    with pytest.raises(ValueError): require_complete_image_acceptance(s['frozen'],s['units'],s['timeline'])
    receipt.write_bytes(saved)
    from pathlib import Path
    Path(a1['selections'][0]['path']).write_bytes(b'changed original')
    with pytest.raises(ValueError): require_complete_image_acceptance(s['frozen'], s['units'], s['timeline'])


@pytest.mark.parametrize('change', ['baseline','text','bool','delivery'])
def test_selection_direct_validation_rejects_tampered_batch(selection_setup, change):
    s = selection_setup; b = batch(s)
    if change == 'baseline': b['baseline_bindings'] = [dict(kind='entity',id='entity_0001',scene_id='scene_0001',candidate_id='fake',sha256='a'*64)]
    elif change == 'text': b['scenes'][0]['original_text'] = 'summary instead of original'
    elif change == 'bool': b['batch_index'] = True
    else: b['delivery']['max_mime_bytes'] = True
    with pytest.raises(ValueError): validate(s, b, submitted(b))


def test_decode_rejects_forged_image_even_when_hash_receipts_match(selection_setup):
    from video_ai.runtime.image_selection_records import build_batch
    from pathlib import Path
    s = selection_setup; manifest = candidate_manifest(s, 'scene_0001')
    records = json.loads(manifest.read_text(encoding='utf-8'))
    row = records['candidates'][0]; path = Path(row['path']); path.write_bytes(b'not an image')
    sha = hashlib.sha256(path.read_bytes()).hexdigest(); row.update(bytes=path.stat().st_size, sha256=sha)
    save(manifest, records); save(path.with_suffix('.json'), row)
    result = json.loads((path.parent/'result.json').read_text(encoding='utf-8')); result['candidates'][0] = row
    save(path.parent/'result.json', result)
    receipt = json.loads(path.with_suffix('.download.json').read_text(encoding='utf-8')); receipt.update(bytes=row['bytes'],sha256=sha)
    save(path.with_suffix('.download.json'), receipt)
    with pytest.raises(ValueError, match='decode|image'): build_batch(s['frozen'],s['units'],s['timeline'],[manifest],batch_index=1)


def test_selection_rechecks_accepted_baseline_originals(selection_setup):
    from pathlib import Path
    s = selection_setup; b1 = batch(s); a1 = accept_batch(s,b1,accepted=[])
    b2 = batch(s,2)
    Path(a1['selections'][0]['path']).write_bytes(b'changed baseline original')
    with pytest.raises(ValueError): validate(s,b2,submitted(b2),[a1])


@pytest.mark.parametrize('value', [None, [], {'schema_version': 2}])
def test_malformed_selection_is_a_validation_error(selection_setup, value):
    s = selection_setup; b = batch(s)
    with pytest.raises(ValueError): validate(s,b,value)


@pytest.mark.parametrize('observation', [[], '', True, 2])
def test_non_object_observation_is_rejected_cleanly(selection_setup, observation):
    s = selection_setup; b = batch(s); value = submitted(b); value['observation'] = observation
    with pytest.raises(ValueError): validate(s,b,value)


def test_current_batch_only_binds_baseline_uses_it_actually_references(runtime_run,tmp_path):
    from unit.test_production_scenes import scene_inputs, scene_proposal, source
    proposal = scene_proposal(); script = scene_inputs()[0]
    proposal['scene_groups'].append(dict(proposal['scene_groups'][0],key='new_lake',
                                         change_sources=[source(script,'speech_0003')]))
    proposal['scenes'][1]['scene_group_id'] = 'new_lake'
    proposal['scenes'][2]['scene_group_id'] = 'new_lake'
    s = setup_selection(runtime_run,tmp_path,proposal=proposal)
    b1 = batch(s); accept_batch(s,b1,accepted=[])
    b2 = batch(s,2)
    assert [(r['kind'],r['id']) for r in b2['baseline_bindings']] == [('entity','entity_0001')]
