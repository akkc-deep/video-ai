import json
from pathlib import Path

import pytest
from unit.test_production_inputs import production_config
from production_helpers import model_server, config_for_server, install_owned_services, wav_bytes


def make_prefix(config, run, text):
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.production_state import ProductionStateStore
    from video_ai.runtime.manifest import create_manifest
    from video_ai.runtime.logging import RunLogger
    frozen = freeze_inputs(config, run, text=text)
    state = ProductionStateStore.create(run)
    manifest = create_manifest(run, frozen.config, inputs=frozen.options['execution_policy']['input_identities'],
                               models={}, workflows={}, verify_integrity=False)
    state.start_stage('preflight')
    state.write_report('preflight', {'checks': [dict(name='fixture', passed=True, details='local only')]})
    state.complete_stage('preflight')
    return frozen, state, manifest, RunLogger(run, production=True)


def test_real_http_original_text_once_and_complete_resume(production_config, runtime_run, monkeypatch):
    from video_ai.runtime.production_storyboard import produce_units
    from video_ai.runtime.production_speech import produce_speech
    run, _, paths = runtime_run
    with model_server() as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config, url, run), run, ' 湖水。\r\n白鸟。')
        install_owned_services(monkeypatch)
        units = produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)
        audio = produce_speech(frozen, units, state=state, manifest=manifest, paths=paths, logger=logger)
        assert [b['text'] for p,b in posts if p == '/tts'] == ['湖水。', '白鸟。']
        assert len(posts) == 3
        assert [a.samples for a in audio.values()] == [4800, 4800]
        assert state.snapshot()['active_stage'] == 'timeline'
        count = len(posts)
        assert produce_speech(frozen, units, state=state, manifest=manifest, paths=paths, logger=logger) == audio
        assert len(posts) == count
        assert json.loads(Path(frozen.options['tts_yaml_path']).read_text())['custom']['version'] == 'v2'


def test_coordinator_finishes_timing_slots_and_resumes_without_posts(production_config, runtime_run, monkeypatch):
    import video_ai.production as production
    from video_ai.runtime.production_state import ProductionRefused
    import video_ai.runtime.production_storyboard as storyboard
    def stop_at_storyboard(*args,**kwargs):raise ProductionRefused('MAKE-02 prefix fixture')
    monkeypatch.setattr(storyboard,'produce_storyboard',stop_at_storyboard)
    run, _, paths = runtime_run
    with model_server() as (url, posts):
        frozen,state,manifest,logger = make_prefix(config_for_server(production_config,url,run),run,'湖水。白鸟。')
        install_owned_services(monkeypatch)
        with pytest.raises(ProductionRefused,match='MAKE-02'):
            production._run_generation(frozen,state,manifest)
        assert len(posts) == 3
        assert state.snapshot()['active_stage'] == 'storyboard'
        assert all(state.snapshot()['stages'][s]['status']=='completed' for s in ('units','speech','timeline'))
        timeline=json.loads((run/'production/timeline.json').read_text())['payload']
        assert timeline['total_speech_samples']==9600
        plan=json.loads((run/'logs/production/checkpoints/timeline/automatic-slots.json').read_text())['payload']
        assert plan['slots'][0]['start_frame']==0
        assert plan['slots'][-1]['end_frame']==timeline['total_frames']
        with pytest.raises(ProductionRefused,match='MAKE-02'):
            production._run_generation(frozen,state,manifest)
        assert len(posts)==3


def test_unknown_tts_intent_resume_does_not_post(production_config, runtime_run, monkeypatch):
    from video_ai.runtime.production_storyboard import produce_units
    from video_ai.runtime.production_speech import produce_speech
    from video_ai.runtime.production_state import ProductionRefused
    run, _, paths = runtime_run
    def handler(path, body, count):
        from production_helpers import proposal_for
        if path == '/tts': return 503, 'text/plain', b'unknown result'
        return 200, 'application/json', json.dumps(dict(model='qwen3:8b', done=True,response=json.dumps(proposal_for(body)))).encode()
    with model_server(handler) as (url, posts):
        frozen, state, manifest, logger = make_prefix(config_for_server(production_config,url,run),run,'湖水。')
        install_owned_services(monkeypatch)
        units = produce_units(frozen,state=state,manifest=manifest,paths=paths,logger=logger)
        with pytest.raises(ProductionRefused): produce_speech(frozen,units,state=state,manifest=manifest,paths=paths,logger=logger)
        assert len(posts) == 2
        with pytest.raises(ProductionRefused): produce_speech(frozen,units,state=state,manifest=manifest,paths=paths,logger=logger)
        assert len(posts) == 2


@pytest.mark.parametrize('kind', ['silence', 'truncated'])
def test_confirmed_bad_wav_fails_once(production_config, runtime_run, monkeypatch, kind):
    from video_ai.runtime.production_storyboard import produce_units
    from video_ai.runtime.production_speech import produce_speech
    run, _, paths = runtime_run
    def handler(path, body, count):
        from production_helpers import proposal_for
        if path == '/tts':
            raw = wav_bytes(silent=kind == 'silence')
            return 200,'audio/wav',raw[:-10] if kind == 'truncated' else raw
        return 200,'application/json',json.dumps(dict(model='qwen3:8b',done=True,response=json.dumps(proposal_for(body)))).encode()
    with model_server(handler) as (url, posts):
        frozen,state,manifest,logger = make_prefix(config_for_server(production_config,url,run),run,'湖水。')
        install_owned_services(monkeypatch)
        units = produce_units(frozen,state=state,manifest=manifest,paths=paths,logger=logger)
        with pytest.raises(RuntimeError): produce_speech(frozen,units,state=state,manifest=manifest,paths=paths,logger=logger)
        assert len(posts) == 2
        with pytest.raises(RuntimeError): produce_speech(frozen,units,state=state,manifest=manifest,paths=paths,logger=logger)
        assert len(posts) == 2
