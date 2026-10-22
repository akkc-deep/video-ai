"""Fixed byte budgets must admit visual facts without rewriting old requests."""
import json

import pytest

from integration.test_jimeng_reference_flow import (prepared_baseline, configured_cloud,
    produce, accept_reference_batch)


def limited_setup(runtime_run, tmp_path, monkeypatch, limit=800, style=None):
    from unit.test_production_scenes import scene_proposal
    proposal = scene_proposal()
    if style is not None:
        proposal['global_style']['description'] = style
    proposal['entities'][0]['source_facts'] = [dict(name=f'appearance_evidence_{i}', value='白色羽毛',
        sources=[dict(unit_id='speech_0002', text_start=5, text_end=12, quote='白鸟停在石上。')]) for i in range(3)]
    s = prepared_baseline(runtime_run, tmp_path, proposal=proposal)
    path = tmp_path/'reference-capability.json'
    value = json.loads(path.read_bytes())
    value['max_prompt_bytes'] = limit
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return s, *configured_cloud(s, monkeypatch)


def test_visual_fields_fit_without_changing_frozen_budget_and_replay_to_wan(runtime_run, tmp_path, monkeypatch):
    from video_ai.runtime.reference_image_records import build_reference_prompt, require_reference_image_acceptance
    s, cloud, smtp, kwargs = limited_setup(runtime_run, tmp_path, monkeypatch)
    assert len(build_reference_prompt(s['plan']['scenes'][1], s['bible']).encode()) > 800
    result = produce(s, **kwargs)
    assert result.status == 'awaiting_image_selection', result.error
    assert len(cloud.submits) == 4 and len(smtp.messages) == 1
    for body in cloud.submits:
        assert len(body['prompt'].encode('utf-8')) <= 800
        for text in ('写实自然光', '白鸟', '白色羽毛', '湖和石头', '清晨', '柔光'):
            assert text in body['prompt']
    assert accept_reference_batch(s, result, observation=True).all_images_accepted
    assert produce(s, **kwargs).status == 'images_ready'
    assert len(require_reference_image_acceptance(s['frozen'], s['units'], s['timeline'])['scenes']) == 3
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (s['run']/'production').rglob('*') if p.is_file()}
    assert produce(s, **kwargs).status == 'images_ready'
    assert not [str(p.relative_to(s['run'])) for p, value in before.items()
                if (p.read_bytes(), p.stat().st_mtime_ns) != value]
    assert len(cloud.submits) == 4 and len(smtp.messages) == 1


def test_still_oversized_visual_fields_stop_before_storage_or_paid_submission(runtime_run, tmp_path, monkeypatch):
    s, cloud, smtp, kwargs = limited_setup(runtime_run, tmp_path, monkeypatch, limit=1)
    result = produce(s, **kwargs)
    assert result.status == 'awaiting_image_model_configuration'
    assert not cloud.storage_calls and not cloud.submits and not smtp.messages


@pytest.mark.parametrize('point', ['accepted', 'downloaded', 'provenance'])
def test_compact_original_response_recovers_across_durable_boundaries(runtime_run, tmp_path, monkeypatch, point):
    import video_ai.runtime.jimeng_reference_candidates as module
    s, cloud, smtp, kwargs = limited_setup(runtime_run, tmp_path, monkeypatch)
    stopped = []
    def interrupt(where, identity):
        if where == point and not stopped:
            stopped.append(where)
            raise KeyboardInterrupt()
    with monkeypatch.context() as patch:
        patch.setattr(module, 'boundary', interrupt)
        result = produce(s, **kwargs)
    assert result.status == 'interrupted', result.error
    assert stopped == [point]
    assert produce(s, **kwargs).status == 'awaiting_image_selection'
    assert len(cloud.submits) == 4 and len(smtp.messages) == 1


def test_compact_unknown_submit_never_posts_again(runtime_run, tmp_path, monkeypatch):
    s, cloud, smtp, kwargs = limited_setup(runtime_run, tmp_path, monkeypatch)
    cloud.unknown = True
    assert produce(s, **kwargs).status in ('failed', 'blocked')
    assert len(cloud.submits) == 1
    cloud.unknown = False
    result = produce(s, **kwargs)
    assert result.status == 'blocked' and 'submit_unknown' in result.error['message']
    assert len(cloud.submits) == 1 and not smtp.messages


@pytest.mark.parametrize('change', ['mixed_prompts', 'missing_request', 'missing_folder', 'unknown_prompt'])
def test_saved_compact_identity_cannot_switch_or_rebuild_orphan_evidence(runtime_run, tmp_path, monkeypatch, change):
    from video_ai.runtime.reference_image_records import build_reference_prompt
    s, cloud, smtp, kwargs = limited_setup(runtime_run, tmp_path, monkeypatch)
    assert produce(s, **kwargs).status == 'awaiting_image_selection'
    request = s['run']/'production/jimeng/scene_0002/request_02/request.json'
    if change == 'missing_request':
        request.unlink()
    elif change == 'missing_folder':
        preserved = request.parent.with_name('preserved_request_02')
        assert request.parent.resolve().is_relative_to(s['run'].resolve())
        assert preserved.resolve().is_relative_to(s['run'].resolve())
        request.parent.rename(preserved)
    else:
        value = json.loads(request.read_bytes())
        value['prompt'] = build_reference_prompt(s['plan']['scenes'][1], s['bible']) if change == 'mixed_prompts' else 'unbound prompt'
        request.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    before = (len(cloud.submits), len(cloud.storage_calls), len(smtp.messages))
    assert produce(s, **kwargs).status == 'blocked'
    assert (len(cloud.submits), len(cloud.storage_calls), len(smtp.messages)) == before


def test_chinese_visual_fields_are_checked_as_bytes_before_upload(runtime_run, tmp_path, monkeypatch):
    from video_ai.runtime.reference_visual_prompt import compact_reference_prompt
    s, cloud, smtp, kwargs = limited_setup(runtime_run, tmp_path, monkeypatch, style='湖'*200)
    prompt = compact_reference_prompt(s['plan']['scenes'][1], s['bible'])
    assert len(prompt) < 800 < len(prompt.encode('utf-8'))
    assert produce(s, **kwargs).status == 'awaiting_image_model_configuration'
    assert not cloud.storage_calls and not cloud.submits and not smtp.messages


def test_provenance_without_one_whole_request_never_repeats_paid_submission(runtime_run, tmp_path, monkeypatch):
    import video_ai.runtime.jimeng_reference_candidates as module
    s, cloud, smtp, kwargs = limited_setup(runtime_run, tmp_path, monkeypatch)
    def interrupt(where, identity):
        if where == 'provenance':
            raise KeyboardInterrupt()
    with monkeypatch.context() as patch:
        patch.setattr(module, 'boundary', interrupt)
        assert produce(s, **kwargs).status == 'interrupted'
    assert len(cloud.submits) == 2
    source = s['run']/'production/jimeng/scene_0002/request_02'
    preserved = source.with_name('preserved_request_02')
    assert source.resolve().is_relative_to(s['run'].resolve())
    assert preserved.resolve().is_relative_to(s['run'].resolve())
    source.rename(preserved)
    before = (len(cloud.submits), len(cloud.storage_calls), len(smtp.messages))
    assert produce(s, **kwargs).status == 'blocked'
    assert (len(cloud.submits), len(cloud.storage_calls), len(smtp.messages)) == before


def test_existing_full_reference_requests_keep_exact_original_prompt(runtime_run, tmp_path, monkeypatch):
    from video_ai.runtime.reference_image_records import build_reference_prompt
    s, cloud, smtp, kwargs = limited_setup(runtime_run, tmp_path, monkeypatch, limit=100_000)
    assert produce(s, **kwargs).status == 'awaiting_image_selection'
    prompts = [build_reference_prompt(scene, s['bible']) for scene in s['plan']['scenes'][1:]]
    assert [body['prompt'] for body in cloud.submits] == [p for p in prompts for _ in range(2)]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (s['run']/'production').rglob('*') if p.is_file()}
    assert produce(s, **kwargs).status == 'awaiting_image_selection'
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == value for p, value in before.items())
    assert len(cloud.submits) == 4 and len(smtp.messages) == 1


@pytest.mark.parametrize('missing', ['submission_pair', 'intent', 'submit-evidence', 'accepted'])
def test_completed_provenance_requires_original_submission_evidence_before_cloud(runtime_run, tmp_path, monkeypatch, missing):
    import video_ai.runtime.jimeng_reference_candidates as module
    s, cloud, smtp, kwargs = limited_setup(runtime_run, tmp_path, monkeypatch)
    def interrupt(where, identity):
        if where == 'provenance':
            raise KeyboardInterrupt()
    with monkeypatch.context() as patch:
        patch.setattr(module, 'boundary', interrupt)
        assert produce(s, **kwargs).status == 'interrupted'
    folder = s['run']/'production/jimeng/scene_0002/request_02'
    for name in (('intent', 'accepted') if missing == 'submission_pair' else (missing,)):
        (folder/(name+'.json')).unlink()
    assert (folder/'request.json').exists()
    before = (len(cloud.submits), len(cloud.storage_calls), len(smtp.messages))
    assert produce(s, **kwargs).status == 'blocked'
    assert (len(cloud.submits), len(cloud.storage_calls), len(smtp.messages)) == before


def test_compact_missing_result_recovers_original_task_after_input_url_expired(runtime_run, tmp_path, monkeypatch):
    from datetime import datetime, timedelta
    import video_ai.runtime.jimeng_reference_candidates as module
    s, cloud, smtp, kwargs = limited_setup(runtime_run, tmp_path, monkeypatch)
    assert produce(s, **kwargs).status == 'awaiting_image_selection'
    folder = s['run']/'production/jimeng/scene_0002/request_01'
    task_id = json.loads((folder/'accepted.json').read_bytes())['task_id']
    (folder/'result.json').unlink()
    (folder.parent/'candidates.json').unlink()
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz)+timedelta(seconds=4000)
    monkeypatch.setattr(module, 'datetime', Clock)
    before = (len(cloud.submits), len(cloud.storage_calls), len(smtp.messages))
    assert produce(s, **kwargs).status == 'awaiting_image_selection'
    assert cloud.queries[-1] == task_id
    assert (len(cloud.submits), len(cloud.storage_calls), len(smtp.messages)) == before
