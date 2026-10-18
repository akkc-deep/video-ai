"""Fresh review regressions: saved summaries must reproduce original transport."""
import json

import pytest

from test_production_inputs import production_config
from test_production_speech import make_prefix
from production_helpers import config_for_server, install_owned_services, model_server, proposal_for


def test_checkpoint_proposal_cannot_replace_confirmed_original_response(
        production_config, runtime_run, monkeypatch):
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.production_storyboard import produce_units
    run, _, paths = runtime_run
    with model_server() as (url, posts):
        frozen, state, manifest, logger = make_prefix(
            config_for_server(production_config, url, run), run, '湖水。')
        install_owned_services(monkeypatch)
        original_write = state.write_report
        def interrupted_report(stage, *args, **kwargs):
            if stage == 'units': raise OSError('report persistence interrupted')
            return original_write(stage, *args, **kwargs)
        monkeypatch.setattr(state, 'write_report', interrupted_report)
        with pytest.raises(OSError, match='report persistence interrupted'):
            produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)
        assert len(posts) == 1
        checkpoint = run/'logs/production/checkpoints/units/units_batch_0001_initial.json'
        data = json.loads(checkpoint.read_text(encoding='utf-8'))
        data['payload']['proposal']['speech_0001'][0]['semantic_reason'] = 'different persisted interpretation'
        checkpoint.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        monkeypatch.setattr(state, 'write_report', original_write)
        with pytest.raises(ProductionRefused, match='checkpoint|response'):
            produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)
        assert len(posts) == 1
        assert not (run/'production/units.json').exists()


@pytest.mark.parametrize('inner', ['', ' \r\n\t'])
def test_confirmed_empty_inner_response_gets_one_format_correction(
        production_config, runtime_run, monkeypatch, inner):
    from video_ai.runtime.production_storyboard import produce_units
    run, _, paths = runtime_run
    def handler(path, body, count):
        response = inner if count == 1 else json.dumps(proposal_for(body), ensure_ascii=False)
        return 200, 'application/json', json.dumps(dict(model='qwen3:8b', done=True, response=response)).encode()
    with model_server(handler) as (url, posts):
        frozen, state, manifest, logger = make_prefix(
            config_for_server(production_config, url, run), run, '湖水。')
        install_owned_services(monkeypatch)
        produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)
        assert len(posts) == 2
        first = json.loads((run/'logs/production/checkpoints/units/units_batch_0001_initial.json').read_text(encoding='utf-8'))
        assert first['payload']['format_valid'] is False
        assert first['request']['state'] == first['status'] == 'completed'
        produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)
        assert len(posts) == 2


def test_frozen_ollama_intent_body_must_match_declared_prompt_and_schema(
        production_config, runtime_run, monkeypatch):
    from video_ai.planning.production_units import make_units_schema
    from video_ai.runtime.production_state import ProductionRefused
    from video_ai.runtime.production_storyboard import _check_intent, _prompt, produce_units
    run, _, paths = runtime_run
    with model_server() as (url, posts):
        frozen, state, manifest, logger = make_prefix(
            config_for_server(production_config, url, run), run, '湖水。')
        install_owned_services(monkeypatch)
        produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)
        uid = 'units_batch_0001_initial'
        intent_path = logger.path(f'storyboard/{uid}.intent.json')
        data = json.loads(intent_path.read_text(encoding='utf-8'))
        data['body']['prompt'] = 'replacement prompt'
        intent_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        candidates = tuple(s for s in frozen.script.spans if s.kind == 'speech')
        with pytest.raises(ProductionRefused, match='intent|body'):
            _check_intent(intent_path, frozen=frozen, uid=uid,
                schema=make_units_schema(candidates, ()), prompt=_prompt(frozen, candidates, []),
                candidates=candidates)
        assert len(posts) == 1
