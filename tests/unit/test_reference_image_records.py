"""Reference request identity, ordered baselines and strict Wan admission."""
import json

import pytest

from image_selection_helpers import setup_selection
from unit.test_image_selection_records import batch, accept_batch


def test_prompt_contains_only_referenced_stable_bible_rows(runtime_run, tmp_path):
    from video_ai.runtime.reference_image_records import build_reference_prompt
    s = setup_selection(runtime_run, tmp_path)
    scene = s['plan']['scenes'][1]
    prompt = build_reference_prompt(scene, s['bible'])
    prefix, raw = prompt.split('\nVISUAL_BIBLE_JSON\n')
    assert prefix == scene['image_prompt']
    context = json.loads(raw)
    assert context == {key: s['bible'][key] for key in
                       ('global_style', 'entities', 'appearance_variants', 'scene_groups')}
    assert raw == json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def test_reference_bindings_deduplicate_one_original_preserving_all_uses(runtime_run, tmp_path):
    from video_ai.runtime.reference_image_records import resolve_reference_bindings
    s = setup_selection(runtime_run, tmp_path)
    a = accept_batch(s, batch(s), accepted=[])
    rows = resolve_reference_bindings(s['frozen'], s['bible'], s['plan'], s['plan']['scenes'][1], [a])
    assert len(rows) == 1
    original, uses = rows[0]
    assert original['sha256'] == a['selections'][0]['sha256']
    assert uses == [dict(kind='entity', id='entity_0001'), dict(kind='scene_group', id='group_0001')]
    with pytest.raises(ValueError):
        resolve_reference_bindings(s['frozen'], s['bible'], s['plan'], s['plan']['scenes'][1], [])


def test_wan_builder_rejects_legacy_text_only_related_candidates(runtime_run, tmp_path):
    from video_ai.runtime.reference_image_records import build_reference_image_acceptance
    s = setup_selection(runtime_run, tmp_path)
    with pytest.raises(ValueError):
        build_reference_image_acceptance(s['frozen'], s['units'], s['timeline'])


def test_submit_uses_explicit_reference_urls_and_rejects_parameter_bypass(monkeypatch):
    from video_ai.adapters.jimeng import JimengClient
    from video_ai.jimeng_config import parse_image_generation
    from unit.test_jimeng_config import image_settings
    settings = parse_image_generation(image_settings(), 'fixture')
    client = JimengClient(settings)
    seen = []
    def request(action, payload, timeout):
        seen.append(payload)
        return {'task_id': 'reference_task'}, 'official', {}
    monkeypatch.setattr(client, '_request', request)
    client.submit('bird', image_urls=['https://test-bucket.tos-cn-beijing.volces.com/original?signature=secret'])
    assert seen[0]['image_urls'] == ['https://test-bucket.tos-cn-beijing.volces.com/original?signature=secret']
    assert 'image_urls' not in settings.model_parameters


@pytest.mark.parametrize('change', ['source', 'schema', 'extra'])
def test_reference_resolution_rejects_tampered_commit(runtime_run, tmp_path, change):
    from image_selection_helpers import save
    from video_ai.config import read_json
    from video_ai.runtime.reference_image_records import resolve_reference_bindings
    s = setup_selection(runtime_run, tmp_path)
    a = accept_batch(s, batch(s), accepted=[])
    path = s['run']/'production/scene-plan-commit.json'; commit = read_json(path)
    commit[{'source': 'source_sha256', 'schema': 'schema_version', 'extra': 'extra'}[change]] = (
        'f'*64 if change == 'source' else True)
    save(path, commit)
    with pytest.raises(ValueError):
        resolve_reference_bindings(s['frozen'], s['bible'], s['plan'], s['plan']['scenes'][1], [a])
