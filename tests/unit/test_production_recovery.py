"""Real HTTP evidence must remain bound to frozen text and original PCM on resume."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from test_production_inputs import production_config
from test_production_speech import make_prefix
from production_helpers import (
    config_for_server, install_owned_services, model_server, proposal_for, wav_bytes,
)


def _write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding='utf-8')


@pytest.mark.parametrize('change', ['frozen_text', 'checkpoint_semantics'])
def test_completed_units_report_must_match_frozen_text_and_original_checkpoints(
        production_config, runtime_run, monkeypatch, change):
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.production_storyboard import produce_units
    run, _, paths = runtime_run
    with model_server() as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, '湖水。')
        install_owned_services(monkeypatch)
        original = produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)
        assert len(posts) == 1
        report_path = run/'production/units.json'
        report = json.loads(report_path.read_text(encoding='utf-8'))
        if change == 'frozen_text':
            report['payload']['decoded_text'] = '海水。'
            report['payload']['spans'][0]['text'] = '海水。'
        else:
            report['payload']['semantic_specs']['speech_0001']['semantic_reason'] = '替换后的解释'
        _write_json(report_path, report)
        with pytest.raises(ProductionRefused):
            produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)
        assert len(posts) == 1
        assert frozen.script.text == original['decoded_text'] == '湖水。'


def test_completed_speech_report_cannot_replace_original_checkpoint_pcm(
        production_config, runtime_run, monkeypatch):
    from video_ai.runtime.production_state import ArtifactStamp, ProductionRefused
    from video_ai.runtime.production_storyboard import produce_units
    from video_ai.runtime.production_speech import produce_speech
    run, _, paths = runtime_run
    with model_server() as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, '湖水。')
        install_owned_services(monkeypatch)
        units = produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)
        original = produce_speech(frozen, units, state=state, manifest=manifest, paths=paths, logger=logger)
        replacement = run/'production/audio/unrelated-pcm.wav'
        replacement.write_bytes(wav_bytes(silent=True))
        report_path = run/'production/speech.json'
        report = json.loads(report_path.read_text(encoding='utf-8'))
        report['payload']['spans'][0]['pcm'] = ArtifactStamp.read(replacement).to_dict()
        _write_json(report_path, report)
        with pytest.raises(ProductionRefused):
            produce_speech(frozen, units, state=state, manifest=manifest, paths=paths, logger=logger)
        assert len(posts) == 2
        assert original['speech_0001'].path != replacement


@pytest.mark.parametrize('field,value', [
    ('samples', True), ('sample_rate', 44100), ('sample_rate', True),
    ('channels', 2), ('sample_width', 1),
])
def test_speech_payload_parser_rejects_invalid_pcm_numeric_metadata(
        production_config, runtime_run, monkeypatch, field, value):
    from video_ai.runtime.production_storyboard import produce_units
    from video_ai.runtime.production_speech import produce_speech, validate_speech_payload
    run, _, paths = runtime_run
    with model_server() as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, '湖水。')
        install_owned_services(monkeypatch)
        units = produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)
        produce_speech(frozen, units, state=state, manifest=manifest, paths=paths, logger=logger)
        payload = json.loads((run/'production/speech.json').read_text(encoding='utf-8'))['payload']
        payload['spans'][0][field] = value
        if field == 'samples': payload['total_speech_samples'] = 1
        with pytest.raises(ValueError): validate_speech_payload(payload, run=run, units=units)
        assert len(posts) == 2


def test_retained_complete_tts_response_without_checkpoint_reconverts_without_post(
        production_config, runtime_run, monkeypatch):
    import video_ai.runtime.production_speech as speech
    from video_ai.runtime.production_storyboard import produce_units
    run, _, paths = runtime_run
    with model_server() as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, '湖水。')
        install_owned_services(monkeypatch)
        units = produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)
        original_converter = speech.standardize_production_wav
        def disk_failure(*args, **kwargs): raise OSError('conversion attempt disk write interrupted')
        monkeypatch.setattr(speech, 'standardize_production_wav', disk_failure)
        with pytest.raises(OSError, match='disk write interrupted'):
            speech.produce_speech(frozen, units, state=state, manifest=manifest, paths=paths, logger=logger)
        original_request = deepcopy(state.snapshot()['units']['speech']['speech_0001']['request'])
        assert len(posts) == 2
        assert [b['text'] for p, b in posts if p == '/tts'] == ['湖水。']
        assert not (run/'logs/production/checkpoints/speech/speech_0001.json').exists()
        retained = list((run/'production/audio/speech_0001').glob('*/raw.wav'))
        assert len(retained) == 1 and retained[0].read_bytes() == wav_bytes()
        monkeypatch.setattr(speech, 'standardize_production_wav', original_converter)
        audio = speech.produce_speech(frozen, units, state=state, manifest=manifest, paths=paths, logger=logger)
        completed = state.snapshot()['units']['speech']['speech_0001']
        assert completed['status'] == completed['request']['state'] == 'completed'
        assert completed['request']['client_id'] == original_request['client_id']
        assert completed['request']['intent_path'] == original_request['intent_path']
        assert audio['speech_0001'].samples == 4800
        assert retained[0].read_bytes() == wav_bytes()
        assert len(posts) == 2


def test_speech_checkpoint_written_before_cursor_is_reconciled_without_new_pcm_or_post(
        production_config, runtime_run, monkeypatch):
    from video_ai.runtime.production_storyboard import produce_units
    from video_ai.runtime.production_speech import produce_speech
    run, _, paths = runtime_run
    with model_server() as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, '湖水。')
        install_owned_services(monkeypatch)
        units = produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)
        original_record = state.record_unit
        def cursor_failure(stage, uid, **kwargs):
            if stage == 'speech' and kwargs['status'] == 'completed':
                raise OSError('completed unit cursor write interrupted')
            return original_record(stage, uid, **kwargs)
        monkeypatch.setattr(state, 'record_unit', cursor_failure)
        with pytest.raises(OSError, match='cursor write interrupted'):
            produce_speech(frozen, units, state=state, manifest=manifest, paths=paths, logger=logger)
        checkpoint_path = run/'logs/production/checkpoints/speech/speech_0001.json'
        checkpoint_bytes = checkpoint_path.read_bytes()
        checkpoint = json.loads(checkpoint_bytes)
        assert state.snapshot()['units']['speech']['speech_0001']['status'] == 'running'
        pcm_paths = list((run/'production/audio/speech_0001').glob('*/pcm-48000.wav'))
        assert len(pcm_paths) == 1
        monkeypatch.setattr(state, 'record_unit', original_record)
        audio = produce_speech(frozen, units, state=state, manifest=manifest, paths=paths, logger=logger)
        assert audio['speech_0001'].stamp.to_dict() == checkpoint['outputs']['pcm']
        assert checkpoint_path.read_bytes() == checkpoint_bytes
        assert list((run/'production/audio/speech_0001').glob('*/pcm-48000.wav')) == pcm_paths
        assert state.snapshot()['stages']['speech']['status'] == 'completed'
        assert len(posts) == 2


def test_keyboard_interrupt_remains_primary_when_owned_service_stop_fails(
        production_config, runtime_run, monkeypatch):
    import video_ai.runtime.production_speech as speech
    from video_ai.runtime.production_storyboard import produce_units
    run, _, paths = runtime_run
    with model_server() as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, '湖水。')
        owned = install_owned_services(monkeypatch)
        units = produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)
        def interrupt(*args, **kwargs): raise KeyboardInterrupt('interrupted original conversion')
        def stop_failure(self, handle): raise OSError('owned shutdown failed')
        monkeypatch.setattr(speech, 'standardize_production_wav', interrupt)
        monkeypatch.setattr(owned, 'stop', stop_failure)
        with pytest.raises(KeyboardInterrupt, match='original conversion'):
            speech.produce_speech(frozen, units, state=state, manifest=manifest, paths=paths, logger=logger)
        assert len(posts) == 2
        record = state.snapshot()['units']['speech']['speech_0001']
        assert record['status'] == 'running' and record['request']['state'] == 'intent'
        diagnostics = [p.read_text(encoding='utf-8') for p in logger.path('errors').glob('*.txt')]
        assert any('owned shutdown failed' in text for text in diagnostics)


def test_complete_http_400_before_failure_cursor_recovers_terminal_failure_without_post(
        production_config, runtime_run, monkeypatch):
    import video_ai.runtime.production_speech as speech
    from video_ai.runtime.production_storyboard import produce_units
    run, _, paths = runtime_run
    def handler(path, body, count):
        if path == '/tts': return 400, 'application/json', b'{"error":"explicit original rejection"}'
        return 200, 'application/json', json.dumps(dict(model='qwen3:8b', done=True, response=json.dumps(proposal_for(body)))).encode()
    with model_server(handler) as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, '湖水。')
        install_owned_services(monkeypatch)
        units = produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)
        original_mark = speech.mark_request_error
        def failed_cursor(*args, **kwargs): raise OSError('failure cursor interrupted after original response')
        monkeypatch.setattr(speech, 'mark_request_error', failed_cursor)
        with pytest.raises(OSError, match='failure cursor interrupted'):
            speech.produce_speech(frozen, units, state=state, manifest=manifest, paths=paths, logger=logger)
        request = deepcopy(state.snapshot()['units']['speech']['speech_0001']['request'])
        assert request['state'] == 'intent'
        assert len(posts) == 2
        monkeypatch.setattr(speech, 'mark_request_error', original_mark)
        with pytest.raises(RuntimeError):
            speech.produce_speech(frozen, units, state=state, manifest=manifest, paths=paths, logger=logger)
        record = state.snapshot()['units']['speech']['speech_0001']
        assert record['status'] == record['request']['state'] == 'failed'
        assert record['request']['client_id'] == request['client_id']
        assert record['request']['intent_path'] == request['intent_path']
        assert len(posts) == 2
