"""Explicit local-file choices retain image identities without claiming mail delivery."""
import json
from pathlib import Path

import pytest

from integration.test_image_selection_flow import (
    selection_setup, scene_setup, production_config, stub_production_config, prepare, consume)


def local_choice(setup):
    folder = setup['run']/'production/image-selection/image_batch_0001'
    value = json.loads((folder/'selection-template.json').read_text(encoding='utf-8'))
    batch = json.loads((folder/'batch.json').read_text(encoding='utf-8'))
    choices = [dict(scene_id=s['scene_id'], candidate_id=s['candidates'][0]['candidate_id'],
                    sha256=s['candidates'][0]['sha256']) for s in batch['scenes']]
    value.update(intent='accept', selections=choices,
        local_review=dict(schema_version=1, method='local_files', reviewer='synthetic-protocol-fixture',
            statement='Synthetic local-file choice; not a real human review.', viewed_images=[dict(c) for c in choices]))
    path = setup['run']/'local-choice.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    return path, value


def test_local_file_acceptance_without_smtp_survives_disk_reentry_and_resume(selection_setup, monkeypatch):
    from video_ai.runtime.image_selection_records import load_accepted_batches
    setup = selection_setup
    monkeypatch.delenv('VIDEO_AI_SMTP_AUTH_CODE')
    assert prepare(setup).status == 'blocked'
    path, value = local_choice(setup)
    result = consume(setup, path)
    assert result.status == 'image_batch_accepted', result.error
    assert not result.all_images_accepted
    folder = Path(result.selection_template).parent
    accepted = load_accepted_batches(setup['frozen'], setup['units'], setup['timeline'])
    assert accepted[0]['selections'][0]['candidate_id'] == 'request_01_image_01'
    submission = folder/'submissions'/(accepted[0]['source_submission_sha256']+'.json')
    assert json.loads(submission.read_text(encoding='utf-8'))['local_review'] == value['local_review']
    assert consume(setup, path).status == 'image_batch_accepted'
    assert prepare(setup).status == 'image_batch_accepted'
    assert not setup['smtp'].messages
    assert not list((folder/'mail').rglob('receipt.json'))
    assert not (folder.parent/'complete-acceptance.json').exists()


@pytest.mark.parametrize('change', ['sha', 'scene', 'candidate', 'coverage', 'statement', 'reviewer', 'method', 'schema', 'extra', 'draft'])
def test_local_evidence_must_match_the_exact_user_choice(selection_setup, monkeypatch, change):
    setup = selection_setup
    monkeypatch.delenv('VIDEO_AI_SMTP_AUTH_CODE')
    assert prepare(setup).status == 'blocked'
    path, value = local_choice(setup)
    local = value['local_review']
    if change == 'sha': local['viewed_images'][0]['sha256'] = 'f'*64
    elif change == 'scene': local['viewed_images'][0]['scene_id'] = 'scene_9999'
    elif change == 'candidate': local['viewed_images'][0]['candidate_id'] = 'request_99_image_01'
    elif change == 'coverage': local['viewed_images'] = []
    elif change == 'statement': local['statement'] = ' '
    elif change == 'reviewer': local['reviewer'] = ''
    elif change == 'method': local['method'] = 'smtp'
    elif change == 'schema': local['schema_version'] = True
    elif change == 'extra': local['smtp_code'] = 250
    else: value['intent'] = 'draft'
    path.write_text(json.dumps(value), encoding='utf-8')
    result = consume(setup, path)
    assert result.status == 'blocked', result.error
    assert not list((setup['run']/'production/image-selection').rglob('accepted.json'))


def test_legacy_choice_still_requires_smtp_receipts(selection_setup, monkeypatch):
    setup = selection_setup
    monkeypatch.delenv('VIDEO_AI_SMTP_AUTH_CODE')
    assert prepare(setup).status == 'blocked'
    path, value = local_choice(setup)
    del value['local_review']
    path.write_text(json.dumps(value), encoding='utf-8')
    result = consume(setup, path)
    assert result.status == 'blocked'
    assert 'SMTP acceptance receipts' in result.error['message']
