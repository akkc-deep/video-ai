"""User prompt corrections reach real candidate records without changing their origin."""
import json

import pytest

from integration.test_scene_revision_flow import revision_source, revision_request, tree_identity


def prepare(setup, *, overrides=None, source=None):
    from datetime import datetime, timezone
    import hashlib
    from uuid import uuid4
    from video_ai.runtime.production_scene_revision import create_scene_revision
    path, value = revision_request(setup, kind='regenerate_images')
    value.update(choices=[], reason='Earth must remain behind the departing probe')
    if source is not None:
        value.update(source_run_id=source.name,
                     source_options_sha256=hashlib.sha256((source/'production/options.json').read_bytes()).hexdigest(),
                     revision_id=str(uuid4()), requested_at=datetime.now(timezone.utc).isoformat())
    if overrides is not None:
        value['image_prompt_overrides'] = overrides
        value['scene_ids'] = list(overrides)
    path.write_text(json.dumps(value), encoding='utf-8')
    return create_scene_revision(source or setup['run'], path), path


def test_corrected_prompt_is_submitted_verified_and_replayed_without_new_tasks(revision_source, monkeypatch):
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.production_scene_pipeline import produce_scene_pipeline
    from video_ai.runtime.production_state import RunLock
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.runtime.logging import RunLogger
    from integration.test_image_selection_flow import SMTP, png
    setup = revision_source
    before = tree_identity(setup['run'])
    result, _ = prepare(setup, overrides={'scene_0001': 'Earth behind the probe; depart into deep space.'})
    assert result.status == 'revision_ready', result.error
    frozen = load_frozen_inputs(result.run_dir)
    submitted = []

    class Images:
        settings = frozen.config.image_generation

        def submit(self, prompt):
            submitted.append(prompt)
            return dict(task_id='corrected_'+str(len(submitted)), request_id='test_submit', diagnostic={})

        def query(self, task_id, **kwargs):
            return dict(status='done', request_id='test_query', diagnostic={}, image_urls=['https://cdn.example/image'])

        def download(self, url, **kwargs):
            return png(1280, 720)

    smtp = SMTP()
    monkeypatch.setenv('VIDEO_AI_SMTP_AUTH_CODE', 'synthetic-test-only')
    def resume():
        with RunLock(result.run_dir) as lock:
            return produce_scene_pipeline(frozen, paths=RuntimePaths.from_config(frozen.config),
                logger=RunLogger(result.run_dir, production=True), lock=lock,
                dependencies=dict(image_client_factory=lambda settings: Images(), smtp_factory=smtp.factory))
    first = resume()
    assert first.status == 'awaiting_image_selection', first.error
    assert submitted == ['Earth behind the probe; depart into deep space.'] * 2
    assert len(smtp.messages) == 1
    assert resume().status == 'awaiting_image_selection'
    assert len(submitted) == 2 and len(smtp.messages) == 1
    assert tree_identity(setup['run']) == before


def test_later_regeneration_preserves_prior_prompt_correction(revision_source):
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.scene_image_prompts import effective_image_prompt
    first, _ = prepare(revision_source, overrides={'scene_0001': 'Earth behind; deep space ahead.'})
    assert first.status == 'revision_ready', first.error
    second, _ = prepare(revision_source, source=first.run_dir)
    assert second.status == 'revision_ready', second.error
    scene = revision_source['plan']['scenes'][0]
    assert effective_image_prompt(load_frozen_inputs(second.run_dir), scene) == 'Earth behind; deep space ahead.'


def test_reference_prompt_contains_correction_and_preserves_visual_context(revision_source):
    from video_ai.runtime.production_inputs import load_frozen_inputs
    from video_ai.runtime.reference_image_records import resolve_reference_prompt
    from video_ai.runtime.reference_settings import load_reference_settings
    from video_ai.runtime.scene_revision_records import load_scene_common_prefix
    from video_ai.runtime.image_selection_records import load_committed_plan
    result, _ = prepare(revision_source, overrides={'scene_0002': 'Earth behind the probe, never approaching it.'})
    assert result.status == 'revision_ready', result.error
    frozen = load_frozen_inputs(result.run_dir)
    units, timeline = load_scene_common_prefix(frozen)
    bible, plan = load_committed_plan(frozen, units, timeline)
    scene = plan['scenes'][1]
    prompt = resolve_reference_prompt(frozen, scene, bible, load_reference_settings(frozen)['capability'])
    assert prompt.startswith('Earth behind the probe, never approaching it.\nVISUAL_')
    assert '白鸟' in prompt
    assert scene['image_prompt'] == revision_source['plan']['scenes'][1]['image_prompt']


def test_changed_correction_cannot_reuse_existing_revision_binding(revision_source):
    from video_ai.runtime.production_inputs import load_frozen_inputs
    result, _ = prepare(revision_source, overrides={'scene_0001': 'Earth behind, deep space ahead.'})
    assert result.status == 'revision_ready', result.error
    path = result.run_dir/'production/scene-revision/request.json'
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
        value['image_prompt_overrides']['scene_0001'] = 'Changed after freezing'
        path.write_text(json.dumps(value), encoding='utf-8')
        with pytest.raises(ValueError):
            load_frozen_inputs(result.run_dir)
    finally:
        path.write_bytes(raw)


@pytest.mark.parametrize('overrides', [None, {}, {'scene_0002': 'Wrong target'}, {'scene_0001': ''},
    {'scene_0001': 'https://example.com'}, {'scene_0001': 7}])
def test_invalid_prompt_overrides_are_rejected_before_target_allocation(revision_source, overrides):
    path, value = revision_request(revision_source, kind='regenerate_images')
    value.update(choices=[], image_prompt_overrides=overrides)
    path.write_text(json.dumps(value), encoding='utf-8')
    from video_ai.runtime.production_scene_revision import create_scene_revision
    result = create_scene_revision(revision_source['run'], path)
    assert result.status == 'blocked' and result.run_dir is None, result.error
