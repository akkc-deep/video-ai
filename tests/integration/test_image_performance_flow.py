"""Offline image orchestration performance flow invariants."""
from reference_helpers import reference_setup, generate_reference
import pytest


def test_both_reference_tasks_are_accepted_before_first_poll(runtime_run, tmp_path, monkeypatch):
    s = reference_setup(runtime_run, tmp_path, monkeypatch)
    events = []
    submit, query = s['client'].submit, s['client'].query
    def submitting(*a, **kw):
        value = submit(*a, **kw)
        events.append(('submit', value['task_id']))
        return value
    def querying(task_id, **kw):
        events.append(('query', task_id))
        return query(task_id, **kw)
    monkeypatch.setattr(s['client'], 'submit', submitting)
    monkeypatch.setattr(s['client'], 'query', querying)
    result = generate_reference(s)
    assert [kind for kind, _ in events] == ['submit', 'submit', 'query', 'query']
    assert len(result['candidates']) == 2
    before = list(events)
    assert generate_reference(s) == result
    assert events == before


@pytest.mark.parametrize('evidence', ['intent', 'terminal'])
def test_later_unknown_or_terminal_request_blocks_all_new_paid_work(runtime_run, tmp_path, monkeypatch, evidence):
    from image_selection_helpers import save
    from video_ai.runtime.reference_image_records import validate_reference_inputs, reference_requests, validate_reference_intent
    from video_ai.planning.production_scenes import canonical_digest
    from video_ai.runtime.manifest import now
    s = reference_setup(runtime_run, tmp_path, monkeypatch)
    model, prompt = validate_reference_inputs(s['frozen'], s['scene'], s['bible'], s['plan'], s['references'], s['settings'])
    request = reference_requests(s['frozen'], s['scene'], prompt, s['references'], model)[1]
    folder = s['run']/'production/jimeng'/s['scene']['scene_id']/'request_02'
    save(folder/'request.json', request)
    if evidence == 'terminal':
        value = dict(schema_version=2, identity=canonical_digest(request), status='failed')
    else:
        # An incomplete intent still refuses; it must never authorize a fresh
        # first paid submission while later evidence requires reconciliation.
        value = {'schema_version': 2}
    save(folder/(evidence+'.json'), value)
    with pytest.raises(ValueError): generate_reference(s)
    assert not s['state']['submits']


def test_completed_reference_batch_replays_under_input_protection(runtime_run, tmp_path, monkeypatch):
    from integration.test_jimeng_reference_flow import prepared_baseline, configured_cloud, produce, accept_reference_batch
    s = prepared_baseline(runtime_run, tmp_path)
    _, _, kwargs = configured_cloud(s, monkeypatch)
    pending = produce(s, **kwargs)
    assert pending.status == 'awaiting_image_selection', pending.error
    accepted = accept_reference_batch(s, pending, observation=True)
    assert accepted.all_images_accepted, accepted.error
    ready = produce(s, **kwargs)
    assert ready.status == 'images_ready', ready.error


def test_active_batch_replay_admits_activation_once(runtime_run, tmp_path, monkeypatch):
    from integration.test_jimeng_reference_flow import prepared_baseline, configured_cloud, produce
    from video_ai.runtime import production_image_selection as selection
    s = prepared_baseline(runtime_run, tmp_path)
    _, _, kwargs = configured_cloud(s, monkeypatch)
    pending = produce(s, **kwargs)
    assert pending.status == 'awaiting_image_selection', pending.error
    calls = []
    original = selection._activation_value
    def counted(*a, **kw): calls.append(True); return original(*a, **kw)
    monkeypatch.setattr(selection, '_activation_value', counted)
    replay = produce(s, **kwargs)
    assert replay.status == 'awaiting_image_selection', replay.error
    assert len(calls) == 1


def test_unknown_second_submit_still_recovers_known_first_task(runtime_run, tmp_path, monkeypatch):
    s = reference_setup(runtime_run, tmp_path, monkeypatch)
    s['state']['failure'] = 'query'
    with pytest.raises(TimeoutError): generate_reference(s)
    folder = s['run']/'production/jimeng'/s['scene']['scene_id']
    # Reproduce response loss for the second task: a durable intent exists but
    # only the first task ID is known locally.
    (folder/'request_02/accepted.json').unlink()
    s['state']['failure'] = None
    with pytest.raises(ValueError, match='submit_unknown'): generate_reference(s)
    assert (folder/'request_01/result.json').is_file()
    assert not (folder/'request_02/accepted.json').exists()
    assert len(s['state']['submits']) == 2


def test_terminal_evidence_is_not_ignored_when_result_also_exists(runtime_run, tmp_path, monkeypatch):
    from image_selection_helpers import save
    from video_ai.config import read_json
    s = reference_setup(runtime_run, tmp_path, monkeypatch)
    generate_reference(s)
    folder = s['run']/'production/jimeng'/s['scene']['scene_id']/'request_02'
    result = read_json(folder/'result.json')
    save(folder/'terminal.json', dict(schema_version=2, identity=result['identity'], status='failed'))
    with pytest.raises(ValueError, match='failed'): generate_reference(s)
    assert len(s['state']['submits']) == 2
