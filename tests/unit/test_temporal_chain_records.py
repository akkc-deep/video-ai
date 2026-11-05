"""A complete native index requires one genuine-scope chain review per scene."""
from pathlib import Path

import pytest

from unit.test_temporal_scene_records import completed_fixture, put
from unit.test_temporal_scene_observations import author, NOW


def chain_fixture(runtime_run, monkeypatch):
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.runtime.temporal_scene_observations import build_temporal_observation_template
    records, context, row, folder, result = completed_fixture(runtime_run, monkeypatch)
    window = records.validate_temporal_window(context, row)
    template = build_temporal_observation_template(context, window, scope='temporal_window_static')
    observation = put(folder/'observations/static.json', author(template))
    put(folder/'static-accepted.json', dict(schema_version=1, algorithm='temporal_window_static_acceptance_v1',
        result_sha256=window['result']['sha256'], request_sha256=canonical_digest(window['request']),
        template_sha256=canonical_digest(template), observation=observation, verdict='acceptable',
        allow_next_window=False, accepted_at=NOW.isoformat()))
    window = records.validate_temporal_window(context, row)
    assert window['status'] == 'static_ready'
    monkeypatch.setattr(records, '_verify_native_chain_media', lambda *a, **k: None, raising=False)
    return records, context, row, window


def write_chain(context, window):
    from video_ai.planning.production_scenes import canonical_digest
    folder = context['store'].root/'chains/scene_0001'
    sources = [dict(clip_id=window['budget']['clip_id'], result=window['result'], raw_frames=window['raw_frames'],
                    source_frame_range=[0, 93], chain_frame_range=[0, 93])]
    mapping = dict(schema_version=1, protocol='longcat_native16_v1', fps='16/1', frame_range=[0, 93],
                   windows=sources, history_output_once=True, blend_interpolate_repeat_or_retime=False)
    artifacts = {key: put(folder/name, ('fixture_only '+key).encode()) for key, name in dict(
        frames='frames.npy', raw_movie='raw.mp4', viewing_movie='viewing.mp4', diagnostics='diagnostics.json').items()}
    artifacts['mapping'] = put(folder/'mapping.json', mapping)
    result = dict(schema_version=1, algorithm='longcat_native_scene_chain_v1', scene_id='scene_0001',
        inputs_sha256=canonical_digest(context['inputs']), frames=93, fps='16/1', frame_range=[0, 93],
        boundary_frames=[], windows=sources, artifacts=artifacts, history_output_once=True,
        blend_interpolate_repeat_or_retime=False, new_model_calls=0, created_at='2026-11-03T00:00:00+00:00',
        technical=dict(raw=dict(frames=93, fps='16/1', width=768, height=432, pixel_exact=True),
                       viewing=dict(frames=93, fps='16/1', width=768, height=432, pixel_exact=False)))
    result_id = put(folder/'result.json', result)
    return folder, result, result_id


def test_static_ready_alone_cannot_create_complete_native_index(runtime_run, monkeypatch):
    from video_ai.runtime.production_state import ProductionRefused
    records, context, row, window = chain_fixture(runtime_run, monkeypatch)
    progress = records.collect_temporal_progress(context)
    assert progress['status'] == 'awaiting_chain_assembly' and progress['source_clips_ready'] is False
    with pytest.raises(ProductionRefused): records.complete_temporal_value(context, progress['records'])


def test_assembled_chain_still_requires_full_dynamic_feedback(runtime_run, monkeypatch):
    from video_ai.runtime.production_state import ProductionRefused
    records, context, row, window = chain_fixture(runtime_run, monkeypatch)
    write_chain(context, window)
    progress = records.collect_temporal_progress(context)
    assert progress['status'] == 'awaiting_chain_review' and progress['source_clips_ready'] is False
    with pytest.raises(ProductionRefused): records.complete_temporal_value(context, progress['records'])


def test_schema4_index_references_the_actual_single_chain_event(runtime_run, monkeypatch):
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.runtime.temporal_scene_observations import build_temporal_observation_template
    records, context, row, window = chain_fixture(runtime_run, monkeypatch)
    folder, result, result_id = write_chain(context, window)
    chain = dict(scene_id='scene_0001', result=result_id, selected_image=window['selected_image'],
                 viewing=result['artifacts']['viewing_movie'], windows=[window], created_at=result['created_at'])
    template = build_temporal_observation_template(context, chain, scope='scene_temporal_chain_process')
    observation = put(folder/'observations/full.json', author(template))
    accepted = put(folder/'accepted.json', dict(schema_version=1, algorithm='temporal_chain_acceptance_v1',
        result_sha256=result_id['sha256'], template_sha256=canonical_digest(template), observation=observation,
        verdict='passed', accepted_at=NOW.isoformat()))
    progress = records.collect_temporal_progress(context)
    assert progress['status'] == 'source_clips_ready' and progress['source_clips_ready'] is True
    value = records.complete_temporal_value(context, progress['records'])
    assert value['schema_version'] == 4 and value['protocol'] == 'longcat_native16_v1'
    assert value['total_frames'] == 93 and len(value['temporal_chains']) == 1
    assert value['clips'][0]['observation_acceptance_sha256'] == accepted['sha256']
    assert value['clips'][0]['temporal_chain'] == dict(acceptance=accepted, source_frame_range=[0, 93])
    assert value['temporal_chains'][0]['acceptance'] == accepted


def test_chain_receipt_cannot_upgrade_static_review_to_video(runtime_run, monkeypatch):
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.temporal_scene_observations import build_temporal_observation_template
    records, context, row, window = chain_fixture(runtime_run, monkeypatch)
    folder, result, result_id = write_chain(context, window)
    chain = dict(scene_id='scene_0001', result=result_id, selected_image=window['selected_image'],
                 viewing=result['artifacts']['viewing_movie'], windows=[window], created_at=result['created_at'])
    template = build_temporal_observation_template(context, chain, scope='scene_temporal_chain_process')
    observed = author(template); observed['review_method'] = 'agent_image'
    observation = put(folder/'observations/false-video.json', observed)
    put(folder/'accepted.json', dict(schema_version=1, algorithm='temporal_chain_acceptance_v1',
        result_sha256=result_id['sha256'], template_sha256=canonical_digest(template), observation=observation,
        verdict='passed', accepted_at=NOW.isoformat()))
    with pytest.raises(ProductionRefused): records.collect_temporal_progress(context)
