"""Real HTTP unit planning: bounded correction and durable zero-submit recovery."""
import json
import threading

import pytest

from test_production_inputs import production_config
from test_production_speech import make_prefix
from production_helpers import (model_server, config_for_server, install_owned_services,
                                proposal_for)


def response(content, *, done=True):
    inner = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return 200, 'application/json', json.dumps(dict(model='qwen3:8b', done=done,
                                                   response=inner)).encode()


def run_units(frozen, state, manifest, paths, logger):
    from video_ai.runtime.production_storyboard import produce_units
    return produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)


def checkpoint(run, request_id):
    return json.loads((run/f'logs/production/checkpoints/units/{request_id}.json').read_text())


def test_completed_invalid_format_corrected_once_with_completed_transport(production_config, runtime_run, monkeypatch):
    run, _, paths = runtime_run
    def handler(path, body, count):
        assert path == '/api/generate'
        return response('not JSON' if count == 1 else proposal_for(body))
    with model_server(handler) as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, '湖水。')
        install_owned_services(monkeypatch)
        result = run_units(frozen, state, manifest, paths, logger)
        assert len(posts) == 2
        assert json.loads(posts[0][1]['prompt'].split('\nINPUT_JSON\n')[1]) == (
            dict(decoded_text='湖水。', candidates=[dict(start=0, end=3, text='湖水。', kind='speech',
                boundary='sentence', unit_id='speech_0001')], known_spans=[]))
        assert '\nCORRECTION\n' in posts[1][1]['prompt']
        first = checkpoint(run, 'units_batch_0001_initial')
        assert first['status'] == 'completed' and first['request']['state'] == 'completed'
        assert first['payload']['format_valid'] is False and first['payload']['proposal'] is None
        assert state.snapshot()['units']['units']['units_batch_0001_initial']['status'] == 'completed'
        assert result['planner']['batches'][0]['request_ids'] == ['units_batch_0001_initial', 'units_batch_0001_correction']
        assert run_units(frozen, state, manifest, paths, logger) == result
        assert len(posts) == 2


def test_second_completed_invalid_format_is_terminal_without_third_post(production_config, runtime_run, monkeypatch):
    run, _, paths = runtime_run
    with model_server(lambda path, body, count: response('broken JSON')) as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, '湖水。')
        install_owned_services(monkeypatch)
        with pytest.raises(RuntimeError): run_units(frozen, state, manifest, paths, logger)
        assert len(posts) == 2
        assert checkpoint(run, 'units_batch_0001_correction')['payload']['format_valid'] is False
        with pytest.raises(RuntimeError): run_units(frozen, state, manifest, paths, logger)
        assert len(posts) == 2


@pytest.mark.parametrize('legacy_transport', [False, True])
def test_seventeenth_batch_terminal_coverage_and_zero_post_resume(production_config, runtime_run, monkeypatch, legacy_transport):
    """Optional array tails would make the simulated model omit the final words."""
    run, _, paths = runtime_run
    sentence = '它只是阳光里一个极其微弱的浅蓝色光点。'
    text = '湖。' * 128 + sentence
    if legacy_transport:
        import video_ai.adapters.ollama as ollama
        original_body = ollama.ollama_body
        monkeypatch.setattr(ollama, 'ollama_body', lambda *args, **kwargs: original_body(*args, **dict(kwargs, units_coverage=False)))
    def handler(path, body, count):
        canonical = proposal_for(body)
        if all(value['type'] == 'object' for value in body['format']['properties'].values()):
            return response({key: dict(leading_parts=rows[:-1], final_part=rows[-1]) for key, rows in canonical.items()})
        if count >= 17:
            canonical['speech_0129'][0]['text_end'] = 262  # only 它只是阳光里
        return response(canonical)
    with model_server(handler) as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, text)
        install_owned_services(monkeypatch)
        if legacy_transport:
            with pytest.raises(RuntimeError, match='proposal omits original candidate tail'):
                run_units(frozen, state, manifest, paths, logger)
            assert len(posts) == 18
            return
        result = run_units(frozen, state, manifest, paths, logger)
        assert len(posts) == 17
        assert ''.join(row['text'] for row in result['spans']) == text
        assert result['spans'][-1]['text'] == sentence and result['spans'][-1]['end'] == 275
        assert run_units(frozen, state, manifest, paths, logger) == result
        assert len(posts) == 17


def test_legacy_frozen_units_body_still_resumes_without_post(production_config, runtime_run, monkeypatch):
    import video_ai.adapters.ollama as ollama
    original_body = ollama.ollama_body
    run, _, paths = runtime_run
    with model_server() as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, '湖水。')
        install_owned_services(monkeypatch)
        monkeypatch.setattr(ollama, 'ollama_body', lambda *args, **kwargs: original_body(*args, **dict(kwargs, units_coverage=False)))
        result = run_units(frozen, state, manifest, paths, logger)
        old_body = posts[0][1]
        assert old_body['format']['properties']['speech_0001']['type'] == 'array'
        intent = logger.path('storyboard/units_batch_0001_initial.intent.json')
        recorded = intent.read_bytes()
        monkeypatch.setattr(ollama, 'ollama_body', original_body)
        assert run_units(frozen, state, manifest, paths, logger) == result
        assert len(posts) == 1 and intent.read_bytes() == recorded


@pytest.mark.parametrize('kind', ['incomplete_done', 'wrong_model', 'timeout'])
def test_unknown_completion_refuses_resume_without_post(production_config, runtime_run, monkeypatch, kind):
    from video_ai.config import load_config
    from video_ai.runtime.manifest import thaw
    from video_ai.runtime.production_state import ProductionRefused
    run, _, paths = runtime_run
    def handler(path, body, count):
        if kind == 'timeout': threading.Event().wait(0.5)
        if kind == 'wrong_model':
            outer = dict(model='other-model', done=True, response=json.dumps(proposal_for(body)))
            return 200, 'application/json', json.dumps(outer).encode()
        return response(proposal_for(body), done=kind != 'incomplete_done')
    with model_server(handler) as (url, posts):
        config = config_for_server(production_config, url, run)
        if kind == 'timeout':
            data = thaw(config.raw)
            data['timeouts']['ollama_request'] = 0.1
            config.config_file.write_text(json.dumps(data), encoding='utf-8')
            config = load_config(config.config_file)
        frozen, state, manifest, logger = make_prefix(config, run, '湖水。')
        install_owned_services(monkeypatch)
        with pytest.raises(ProductionRefused): run_units(frozen, state, manifest, paths, logger)
        assert len(posts) == 1
        intent = json.loads(logger.path('storyboard/units_batch_0001_initial.intent.json').read_text())
        assert intent['body'] == posts[0][1]
        assert intent['context']['candidate_ranges'] == [dict(unit_id='speech_0001', start=0, end=3)]
        with pytest.raises(ProductionRefused): run_units(frozen, state, manifest, paths, logger)
        assert len(posts) == 1


def test_more_than_eight_candidates_uses_prior_final_context_across_http_batches(production_config, runtime_run, monkeypatch):
    run, _, paths = runtime_run
    text = '白鸽。' + '湖面。'*7 + '它飞。'
    def handler(path, body, count):
        proposal = proposal_for(body)
        if count == 2:
            proposal['speech_0009'][0]['facts'].update(
                context_sources=[dict(text_start=0, text_end=3, source_quote='白鸽。')],
                resolved_references=[dict(reference_quote='它', resolved_subject='白鸽', context_source_indices=[0])])
        return response(proposal)
    with model_server(handler) as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, text)
        install_owned_services(monkeypatch)
        result = run_units(frozen, state, manifest, paths, logger)
        assert len(posts) == 2
        inputs = [json.loads(body['prompt'].split('\nINPUT_JSON\n')[1]) for path, body in posts]
        assert [len(data['candidates']) for data in inputs] == [8, 1]
        assert all(data['decoded_text'] == text for data in inputs)
        assert [s['unit_id'] for s in inputs[1]['known_spans']] == [f'speech_{i:04d}' for i in range(1, 9)]
        assert result['semantic_specs']['speech_0009']['facts']['context_sources'] == [
            dict(unit_id='speech_0001', text_start=0, text_end=3, source_quote='白鸽。')]
        assert ''.join(s['text'] for s in result['spans']) == text


def test_real_font_width_rejects_initial_then_accepts_lossless_correction(production_config, runtime_run, monkeypatch):
    run, _, paths = runtime_run
    text = '湖'*100 + '。'
    def handler(path, body, count):
        proposal = proposal_for(body)
        if count == 2:
            row = proposal['speech_0001'][0]
            proposal['speech_0001'] = [dict(row, text_end=50), row]
        return response(proposal)
    with model_server(handler) as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, text)
        install_owned_services(monkeypatch)
        result = run_units(frozen, state, manifest, paths, logger)
        assert len(posts) == 2
        assert [s['text'] for s in result['spans']] == ['湖'*50, '湖'*50+'。']
        assert checkpoint(run, 'units_batch_0001_initial')['payload']['format_valid'] is False
        assert 'two lines' in posts[1][1]['prompt']


@pytest.mark.parametrize('lag', ['checkpoint_file', 'unit_cursor', 'report_cursor'])
def test_durable_checkpoint_or_report_reconciles_without_new_http(production_config, runtime_run, monkeypatch, lag):
    run, _, paths = runtime_run
    with model_server() as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, '湖水。')
        install_owned_services(monkeypatch)
        if lag == 'checkpoint_file':
            original = state.write_checkpoint
            def crash(stage, uid, **kwargs):
                if stage == 'units': raise OSError('simulated checkpoint file crash')
                return original(stage, uid, **kwargs)
            monkeypatch.setattr(state, 'write_checkpoint', crash)
        elif lag == 'unit_cursor':
            original = state.record_unit
            def crash(stage, uid, **kwargs):
                if stage == 'units' and kwargs['status'] == 'completed': raise OSError('simulated cursor crash')
                return original(stage, uid, **kwargs)
            monkeypatch.setattr(state, 'record_unit', crash)
        else:
            original = state.complete_stage
            def crash(stage):
                if stage == 'units': raise OSError('simulated report cursor crash')
                return original(stage)
            monkeypatch.setattr(state, 'complete_stage', crash)
        with pytest.raises(OSError, match='simulated'): run_units(frozen, state, manifest, paths, logger)
        assert len(posts) == 1
        if lag == 'checkpoint_file':
            assert not (run/'logs/production/checkpoints/units/units_batch_0001_initial.json').exists()
            first = None
            monkeypatch.setattr(state, 'write_checkpoint', original)
        else:
            first = checkpoint(run, 'units_batch_0001_initial')
            assert first['payload']['format_valid'] is True
        if lag == 'unit_cursor':
            assert state.snapshot()['units']['units']['units_batch_0001_initial']['status'] == 'running'
            monkeypatch.setattr(state, 'record_unit', original)
        elif lag == 'report_cursor':
            assert (run/'production/units.json').exists()
            saved_report = (run/'production/units.json').read_bytes()
            monkeypatch.setattr(state, 'complete_stage', original)
        result = run_units(frozen, state, manifest, paths, logger)
        assert result['spans'][0]['text'] == '湖水。'
        assert len(posts) == 1
        final_checkpoint = checkpoint(run, 'units_batch_0001_initial')
        assert final_checkpoint['payload']['format_valid'] is True
        if first: assert final_checkpoint == first
        assert state.snapshot()['active_stage'] == 'speech'
        if lag == 'report_cursor': assert (run/'production/units.json').read_bytes() == saved_report


def test_healthy_external_service_is_refused_before_model_post(production_config, runtime_run, monkeypatch):
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.services import ServiceHandle
    run, _, paths = runtime_run
    with model_server() as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, '湖水。')
        manager = install_owned_services(monkeypatch)
        monkeypatch.setattr(manager, 'ensure', lambda self, spec: ServiceHandle(spec.name, spec.url, False, None, None, None))
        with pytest.raises(ProductionRefused, match='external'): run_units(frozen, state, manifest, paths, logger)
        assert posts == []
        # A TCP connection proves refusing this service left its listener running.
        import socket
        from urllib.parse import urlsplit
        address = urlsplit(url)
        with socket.create_connection((address.hostname, address.port), timeout=1): pass
