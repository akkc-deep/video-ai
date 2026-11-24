import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from unit.test_scene_comfy_transactions import transaction


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return path


def completed_clip(run, cid='scene_0001_clip_0001', verdict=None):
    folder = run/'production/scene-clips'/cid
    folder.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for name in ('generated.mp4', 'source.mp4', 'frame_000001.png'):
        path = folder/name
        path.write_bytes(b'already produced; must never decode or hash')
        artifacts[name] = dict(path=str(path), bytes=1, sha256='old-saved-identity')
    clip = dict(clip_id=cid, generated=artifacts['generated.mp4'], source=artifacts['source.mp4'])
    save(folder/'clip.json', clip)
    save(folder/'request.json', dict(clip_id=cid, parameters=dict(scheduler='euler', lora_enabled=True)))
    save(folder/'mapping.json', dict(saved_mapping=True))
    save(folder/'last-frame.json', dict(image=artifacts['frame_000001.png']))
    save(folder/'observation-template.json', dict(saved_template=True))
    if verdict:
        save(folder/('observation-accepted.json' if verdict == 'passed' else 'observation-rejected.json'),
             dict(saved_receipt=True, observation=dict(path=str(folder/'observations/review.json'))))
    return folder, clip


def revision(run, source, imports):
    root = run/'production/scene-revision'
    bounds = []
    for iid, view, mappings in imports:
        domain, key = iid.split(':', 1)
        bounds.append(dict(path=str(save(root/'imports'/(domain+'-'+key+'.json'),
            dict(domain=domain, key=key, view=view, local_artifacts=mappings)))))
    save(root/'imports.json', dict(imports=bounds))
    save(root/'invalidation.json', dict(dirty=dict(common=[])))
    save(root/'commit.json', dict(source_run_dir=str(source),
        imports=dict(path=str(root/'imports.json')), invalidation=dict(path=str(root/'invalidation.json'))))
    return dict(run_id=run.name, script_path=str(run/'production/script.txt'),
                scene_revision=dict(path=str(root/'commit.json')))


def test_resume_scope_is_local_and_only_enabled_for_existing_work(tmp_path):
    from video_ai.runtime.resume_materials import resume_existing_materials, trusting_materials

    @resume_existing_materials
    def invoke(**kwargs):
        return trusting_materials()

    assert not invoke(text='new movie')
    assert invoke(run_dir=tmp_path)
    assert invoke(run_dir=tmp_path, clip_observation='review.json')
    assert not invoke(run_dir=tmp_path, revision='revision.json')
    assert not invoke(run_dir=tmp_path, publish=True)
    assert not trusting_materials()


@pytest.mark.parametrize('mode', ['whole_scene_v1', 'temporal_extension_v1'])
def test_specialized_renderers_keep_their_original_recovery_protocol(tmp_path, mode):
    from video_ai.runtime.resume_materials import resume_existing_materials, trusting_materials
    save(tmp_path/'production/options.json', dict(config_snapshot=dict(raw=dict(scene_rendering=dict(mode=mode)))))
    @resume_existing_materials
    def invoke(**kwargs):
        return trusting_materials()
    assert not invoke(run_dir=tmp_path)


def test_revision_reads_committed_views_without_loading_any_ancestor(tmp_path, monkeypatch):
    from video_ai.runtime.resume_materials import trust_existing_materials
    from video_ai.runtime.scene_revision_records import require_scene_revision, validate_revision_structure
    run = tmp_path/'10'
    options = revision(run, tmp_path/'ancestor-is-not-opened', [('plan:all', dict(saved_plan=True), [])])
    frozen = SimpleNamespace(options=options)
    def forbidden(*args, **kwargs):
        pytest.fail('resume rebuilt/validated ancestor materials')
    monkeypatch.setattr('video_ai.runtime.production_inputs.load_frozen_inputs', forbidden)
    monkeypatch.setattr('video_ai.runtime.scene_revision_records._scan_revision_structure', forbidden)
    with trust_existing_materials(run):
        proof = require_scene_revision(frozen)
        assert proof['imports']['plan:all'][0]['view'] == dict(saved_plan=True)
        proof['guard'].capture_absent(run/'production/reference-images/wan-inputs.json', root=run)
        assert validate_revision_structure(options, run) is proof


def test_completed_clip_reuses_saved_metadata_and_current_review_receipts(tmp_path):
    from video_ai.runtime.resume_materials import trust_existing_materials, saved_clip
    folder, clip = completed_clip(tmp_path)
    with trust_existing_materials(tmp_path):
        record = saved_clip(tmp_path, clip['clip_id'])
        assert record['clip'] == clip
        assert record['accepted'] is None and record['rejected'] is None
        save(folder/'observation-rejected.json', dict(explicit_failure=True))
        assert saved_clip(tmp_path, clip['clip_id'])['rejected'] == dict(explicit_failure=True)


def test_source_configuration_is_loaded_lazily_for_inherited_prompts(tmp_path, monkeypatch):
    from video_ai.runtime.resume_materials import trust_existing_materials, saved_revision
    source = tmp_path/'01'
    run = tmp_path/'10'
    options = revision(run, source, [])
    calls = []
    frozen = SimpleNamespace(options=dict(saved_source=True))
    monkeypatch.setattr('video_ai.runtime.production_inputs.load_frozen_inputs',
                        lambda path: calls.append(path) or frozen)
    with trust_existing_materials(run):
        proof = saved_revision(options, run)
        assert calls == []
        assert proof['source_frozen'] is frozen
        assert proof['source_frozen'] is frozen
        assert calls == [source]


def test_unreceipted_failure_is_preserved(tmp_path):
    from video_ai.runtime.resume_materials import trust_existing_materials, saved_clip
    folder, clip = completed_clip(tmp_path)
    save(folder/'observations/review.json', dict(verdict='failed', reason='observed broken geometry'))
    with trust_existing_materials(tmp_path):
        result = saved_clip(tmp_path, clip['clip_id'])
        assert result['accepted'] is None and result['rejected']['_raw_only']
        assert set(result['rejected']['observation']) == {'path', 'bytes', 'sha256'}
        from video_ai.runtime.production_scene_clips import _check_observation_replacement
        _check_observation_replacement(result, dict(verdict='failed', reason='observed broken geometry'))


def test_missing_completed_media_is_not_treated_as_an_unsent_clip(tmp_path):
    from video_ai.runtime.resume_materials import trust_existing_materials, saved_clip
    folder, clip = completed_clip(tmp_path)
    (folder/'source.mp4').unlink()
    with trust_existing_materials(tmp_path), pytest.raises(ValueError, match='missing'):
        saved_clip(tmp_path, clip['clip_id'])


def test_inherited_clip_uses_saved_sidecars_and_remaps_media_without_context_rebuild(tmp_path, monkeypatch):
    from video_ai.runtime.resume_materials import trust_existing_materials, saved_clip
    source, target = tmp_path/'01', tmp_path/'10'
    _, clip = completed_clip(source, verdict='passed')
    mappings = []
    target_clip = json.loads(json.dumps(clip))
    for role in ('generated', 'source'):
        original = clip[role]
        path = target/'production/scene-revision/media'/Path(original['path']).name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'previously copied')
        target_clip[role] = dict(original, path=str(path))
        mappings.append(dict(role=role, source=original, target=target_clip[role]))
    revision(target, source, [('clip:'+clip['clip_id'], target_clip, mappings)])
    monkeypatch.setattr('video_ai.runtime._scene_revision_origins.source_clip_record',
                        lambda *args, **kwargs: pytest.fail('source scene context rebuilt'))
    with trust_existing_materials(target):
        record = saved_clip(target, clip['clip_id'])
        assert record['clip'] == target_clip
        assert record['accepted'] and record['last_frame']


def test_new_clip_in_same_invocation_still_uses_original_validation(tmp_path, monkeypatch):
    from video_ai.runtime.resume_materials import trust_existing_materials
    from video_ai.runtime.scene_clip_records import validate_clip
    cid = 'scene_0001_clip_0001'
    context = dict(frozen=SimpleNamespace(options={}), store=SimpleNamespace(run_dir=tmp_path,
        revision_context=None, clip_dir=lambda cid: tmp_path/'production/scene-clips'/cid))
    row = dict(budget=dict(clip_id=cid))
    def strict(*args, **kwargs):
        raise RuntimeError('new material technical checks reached')
    monkeypatch.setattr('video_ai.runtime.scene_clip_records._validate_input', strict)
    with trust_existing_materials(tmp_path):
        completed_clip(tmp_path)
        with pytest.raises(RuntimeError, match='new material technical checks reached'):
            validate_clip(context, row)


def test_existing_clip_bypasses_hash_decode_and_request_reconstruction(tmp_path, monkeypatch):
    from video_ai.runtime.resume_materials import trust_existing_materials
    from video_ai.runtime.scene_clip_records import validate_clip
    _, clip = completed_clip(tmp_path, verdict='passed')
    def forbidden(*args, **kwargs):
        pytest.fail('completed material was revalidated')
    monkeypatch.setattr('video_ai.runtime.scene_clip_records._validate_input', forbidden)
    monkeypatch.setattr('video_ai.runtime.scene_clip_records._decode_video', forbidden)
    context = dict(frozen=SimpleNamespace(options={}), store=SimpleNamespace(run_dir=tmp_path, revision_context=None))
    with trust_existing_materials(tmp_path):
        result = validate_clip(context, dict(budget=dict(clip_id=clip['clip_id'])))
        assert result['clip'] == clip and result['accepted']


def test_interruption_after_clip_marker_rebuilds_missing_review_template(tmp_path, monkeypatch):
    from video_ai.runtime.resume_materials import trust_existing_materials
    from video_ai.runtime.scene_clip_records import validate_clip
    folder, clip = completed_clip(tmp_path)
    (folder/'observation-template.json').unlink()
    expected = dict(recovered_template=True)
    monkeypatch.setattr('video_ai.runtime.scene_clip_observations.build_observation_template',
                        lambda *args: expected)
    context = dict(frozen=SimpleNamespace(options={}), store=SimpleNamespace(run_dir=tmp_path, revision_context=None))
    with trust_existing_materials(tmp_path):
        assert validate_clip(context, dict(budget=dict(clip_id=clip['clip_id'])))['template'] == expected


def test_producer_restore_does_not_replay_completed_media_receipts(tmp_path, monkeypatch):
    from video_ai.runtime.resume_materials import trust_existing_materials
    from video_ai.runtime.production_scene_clips import _restore_outer
    _, clip = completed_clip(tmp_path, verdict='passed')
    def forbidden(*args, **kwargs):
        pytest.fail('producer replayed completed material receipts')
    monkeypatch.setattr('video_ai.runtime.production_scene_clips.validate_media_receipt', forbidden)
    store = SimpleNamespace(run_dir=tmp_path, revision_context=None,
                            clip_dir=lambda cid: tmp_path/'production/scene-clips'/cid, read=forbidden)
    context = dict(frozen=SimpleNamespace(options={}), store=store,
                   rows=[dict(budget=dict(clip_id=clip['clip_id'], scene_id='scene_0001', parent_clip_id=None))])
    with trust_existing_materials(tmp_path):
        _restore_outer(context, paths=None, logger=None)


def test_public_resume_activates_policy_before_frozen_inputs(runtime_run, monkeypatch):
    import video_ai.production as production
    from video_ai.runtime.resume_materials import trusting_materials
    run, _, _ = runtime_run
    save(run/'production/options.json', {})
    frozen = SimpleNamespace(config=SimpleNamespace(production_strategy='paragraph_jimeng_v1'),
                             options={'scene_revision': {}})
    result = object()
    def load(*args, **kwargs):
        assert trusting_materials()
        return frozen
    def advance(*args, **kwargs):
        assert trusting_materials()
        return result
    monkeypatch.setattr(production, 'load_frozen_inputs', load)
    monkeypatch.setattr(production, '_scene_completed_fast', lambda *args: None)
    monkeypatch.setattr(production, '_make_scene_video', advance)
    assert production.make_video(run_dir=run) is result
    assert not trusting_materials()


def test_saved_reference_images_do_not_replay_acceptance_or_provenance(tmp_path, monkeypatch):
    from video_ai.runtime.resume_materials import trust_existing_materials
    from video_ai.runtime.reference_image_records import require_reference_image_acceptance
    image = tmp_path/'selected.png'
    image.write_bytes(b'previously generated image')
    value = dict(scenes=[dict(path=str(image), bytes=1, sha256='previously recorded')])
    save(tmp_path/'production/reference-images/wan-inputs.json', value)
    frozen = SimpleNamespace(options=dict(script_path=str(tmp_path/'production/script.txt')))
    monkeypatch.setattr('video_ai.runtime.reference_image_records.build_reference_image_acceptance',
                        lambda *args: pytest.fail('old images were re-admitted'))
    with trust_existing_materials(tmp_path):
        assert require_reference_image_acceptance(frozen, None, None) == value


def test_old_artifacts_reuse_identity_but_new_files_are_still_verified(runtime_run):
    from video_ai.runtime.resume_materials import trust_existing_materials, remember
    from video_ai.runtime.scene_clip_records import SceneClipStore
    run, _, paths = runtime_run
    store = SceneClipStore(SimpleNamespace(options={}), run, paths=paths)
    old = run/'completed.mp4'
    old.write_bytes(b'do not decode or hash this old material')
    declared = dict(path=str(old), bytes=1, sha256='saved identity is trusted')
    with trust_existing_materials(run):
        remember(declared)
        assert store.artifact(old) == declared
        assert store.validate_artifact(declared) == old
        new = run/'new.mp4'
        new.write_bytes(b'new output')
        actual = store.artifact(new)
        assert actual['bytes'] == len(b'new output')
        with pytest.raises(ValueError):
            store.validate_artifact(dict(actual, sha256='a'*64))


def test_unknown_original_submission_is_recovered_without_reposting(transaction):
    from unit.test_scene_comfy_transactions import Client
    from video_ai.runtime.resume_materials import trust_existing_materials
    from video_ai.runtime.scene_comfy_transactions import recover_or_submit_scene_clip, SceneSubmitUnknown
    store, request, graph, template = transaction
    client = Client(store, request, graph, lose_response=True)
    arguments = dict(client=client, template=template, ensure_service=lambda: None, logger=None, timeout=1)
    with pytest.raises(SceneSubmitUnknown):
        recover_or_submit_scene_clip(store, request, graph, **arguments)
    with trust_existing_materials(store.run_dir):
        result = recover_or_submit_scene_clip(store, request, graph, **arguments)
    assert result['prompt_id'] == client.pid
    assert client.posts == 1
