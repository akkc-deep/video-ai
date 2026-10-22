"""Real local HTTP evidence, transaction interruption and conservative replay."""
from copy import deepcopy
from dataclasses import replace
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

import pytest

from unit.test_jimeng_config import configured
from unit.test_production_inputs import production_config


def proposal():
    def scene(ids):
        return dict(paragraph_id='paragraph_0001', unit_ids=ids, summary='湖边白鸟',
                    image_prompt='湖边白鸟停在石头上，横向自然摄影', motion_prompt='湖面缓慢泛起涟漪',
                    entity_ids=[], variant_ids=[], scene_group_id='lake', change_sources=[])
    return dict(global_style=dict(description='自然摄影', source_facts=[], creative_choices=[]),
                entities=[], appearance_variants=[], scene_groups=[dict(key='lake', label='湖边',
                environment='湖边石头', time='白天', lighting='自然光', spatial_relations=[],
                source_facts=[], creative_choices=[], change_sources=[])],
                scenes=[scene(['speech_0001', 'speech_0002']), scene(['speech_0003'])])


@pytest.fixture
def scene_setup(production_config, runtime_run, tmp_path, request):
    from video_ai.adapters.common import HttpClient
    from video_ai.adapters.ollama import OllamaPlanner
    from video_ai.config import load_config
    from video_ai.planning.production_timeline import ProductionAudioInfo, build_production_timeline
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.manifest import thaw
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.production_state import ArtifactStamp
    parameter = getattr(request, 'param', 'qwen3:8b')
    model = parameter.get('model', 'qwen3:8b') if isinstance(parameter, dict) else parameter
    text = parameter.get('text', '湖面很静。白鸟停在石上。它望向远处。') if isinstance(parameter, dict) else '湖面很静。白鸟停在石上。它望向远处。'
    received = []; replies = []; controls = {}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            item = replies.pop(0) if replies else proposal()
            outer = dict(model=model, done=True, done_reason='stop', response=json.dumps(item, ensure_ascii=False))
            outer.update(controls.get('outer', {}))
            raw = json.dumps(outer, ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length', str(len(raw))); self.end_headers()
            self.wfile.write(raw)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        config = configured(production_config, tmp_path, **({'scene_planner_model': model} if model != 'qwen3:8b' else {}))
        data = thaw(config.raw); data['services']['ollama'] = f'http://127.0.0.1:{server.server_port}'
        config.config_file.write_text(json.dumps(data), encoding='utf-8')
        config = load_config(config.config_file)
        run = runtime_run[0]
        frozen = freeze_inputs(config, run, text=text)
        script = frozen.script
        audio = {s.unit_id: ProductionAudioInfo(ArtifactStamp('D:/pcm.wav', 96046, 123),
                 48000, 1, 2, 48001) for s in script.spans if s.kind == 'speech'}
        timeline = build_production_timeline(script, audio, settings=config.media.timeline)
        units = dict(decoded_text=script.text, has_bom=script.has_bom, spans=thaw(script.spans),
                     semantic_specs={s.unit_id: dict(facts={}) for s in script.spans if s.kind == 'speech'})
        logger = RunLogger(run, production=True)
        planner = OllamaPlanner(HttpClient(config.services['ollama'], 5, logger), model=model)
        controls.update(frozen=frozen, timeline=timeline, units=units, logger=logger,
                        planner=planner, paths=RuntimePaths.from_config(config), run=run,
                        received=received, replies=replies)
        yield controls
    finally:
        server.shutdown(); server.server_close(); thread.join(3)


def produce(s, **kwargs):
    from video_ai.runtime.production_scene_plan import produce_scene_plan
    return produce_scene_plan(s['frozen'], s['units'], s['timeline'], paths=s['paths'],
                              logger=s['logger'], planner=s['planner'], **kwargs)


@pytest.mark.parametrize('scene_setup', [dict(model='qwen3:14b', text='白鹭'+'在湖边'*50+'。')], indirect=True)
def test_compact_scene_response_replays_when_legacy_citation_body_exceeds_capacity(scene_setup):
    from unit.test_scene_environment_transport import environment_wire
    from video_ai.adapters.ollama import ollama_body
    from video_ai.config import parse_scene_planning
    from video_ai.planning.production_scenes import make_scene_schema
    from video_ai.runtime.production_scene_plan import _prompt
    s = scene_setup
    s['units']['planner'] = {'original_evidence': 'x'*5000}
    settings = parse_scene_planning(s['frozen'].config.raw.get('scene_planning'))
    schema = make_scene_schema(s['frozen'].script, s['units'], s['timeline'], settings)
    prompt = _prompt(s['frozen'].script, s['units'], s['timeline'], settings)
    with pytest.raises(ValueError, match='full-input capacity'):
        ollama_body(prompt, schema, scene_planning=True, scene_environment_constraints=False)
    ollama_body(prompt, schema, scene_planning=True)
    wire = environment_wire()
    del wire['scenes']['scene_0002'], wire['scenes']['scene_0003']
    s['replies'].append(wire)
    bible, plan = produce(s)
    assert len(plan['scenes']) == 1 and len(bible['scene_groups']) == 1
    assert plan['scenes'][0]['unit_ids'] == ['speech_0001']
    assert plan['total_frames'] == s['timeline'].total_frames
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in s['run'].rglob('*') if p.is_file()}
    assert produce(s) == (bible, plan)
    assert len(s['received']) == 1
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == value for p, value in before.items())


def test_http_complete_script_and_exact_commit_replayed_without_writes(scene_setup):
    s = scene_setup
    bible, plan = produce(s)
    assert len(s['received']) == 1
    prompt = s['received'][0]['prompt']
    assert s['frozen'].script.text in prompt and 'paragraph_0001' in prompt
    assert all(c.unit_id in prompt for c in s['timeline'].clips)
    assert s['received'][0]['model'] == 'qwen3:8b'
    assert len(plan['scenes']) == 2 and plan['scenes'][0]['unit_ids'] == ['speech_0001','speech_0002']
    assert plan['scenes'][0]['start_frame'] == 0
    assert plan['scenes'][-1]['end_frame'] == s['timeline'].total_frames
    folder = s['run']/'production'
    commit = json.loads((folder/'scene-plan-commit.json').read_text(encoding='utf-8'))
    assert set(commit) == set('schema_version run_id source_sha256 units_sha256 timeline_sha256 settings visual_bible_sha256 scene_plan_sha256'.split())
    assert commit['source_sha256'] == hashlib.sha256((folder/'script.txt').read_bytes()).hexdigest()
    before = {p: p.stat().st_mtime_ns for p in s['run'].rglob('*') if p.is_file()}
    assert produce(s) == (bible, plan)
    assert all(p.stat().st_mtime_ns == stamp for p, stamp in before.items())
    assert len(s['received']) == 1
    assert not (s['run']/'.make-video.lock').exists()


@pytest.mark.parametrize('scene_setup', ['qwen3:14b'], indirect=True)
@pytest.mark.parametrize('correction', [False, True])
def test_explicit_14b_scene_model_is_frozen_and_replays_without_http(scene_setup, correction):
    from video_ai.runtime.production_inputs import load_frozen_inputs
    s = scene_setup
    if correction:
        s['replies'].append({'wrong': 'format'})
    result = produce(s)
    assert len(s['received']) == (2 if correction else 1)
    assert all(row['model'] == 'qwen3:14b' for row in s['received'])
    config = s['frozen'].config
    raw = json.loads(config.config_file.read_text(encoding='utf-8'))
    raw['scene_planner_model'] = 'qwen3:8b'
    config.config_file.write_text(json.dumps(raw), encoding='utf-8')
    assert load_frozen_inputs(s['run']).config.raw['scene_planner_model'] == 'qwen3:14b'
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in s['run'].rglob('*') if p.is_file()}
    assert produce(s) == result
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == value for p, value in before.items())
    assert len(s['received']) == (2 if correction else 1)


@pytest.mark.parametrize('scene_setup', ['qwen3:14b'], indirect=True)
def test_wrong_scene_response_model_never_authorizes_correction(scene_setup):
    s = scene_setup
    s['outer'] = {'model': 'qwen3:8b'}
    for _ in range(2):
        with pytest.raises(Exception, match='model|completion'):
            produce(s)
    assert len(s['received']) == 1
    assert not (s['run'] / 'production/scene-planning/correction.intent.json').exists()


@pytest.mark.parametrize('scene_setup', ['qwen3:14b'], indirect=True)
def test_injected_scene_model_mismatch_refused_before_submission(scene_setup):
    from video_ai.adapters.ollama import OllamaPlanner
    s = scene_setup
    s['planner'] = OllamaPlanner(s['planner'].http, model='qwen3:8b')
    with pytest.raises(ValueError, match='binding'):
        produce(s)
    assert not s['received']
    assert not (s['run'] / 'production/scene-planning/initial.intent.json').exists()


@pytest.mark.parametrize('scene_setup', ['qwen3:14b'], indirect=True)
@pytest.mark.parametrize('target', ['intent', 'frozen'])
def test_scene_model_change_cannot_rebind_completed_evidence(scene_setup, target):
    s = scene_setup
    produce(s)
    if target == 'intent':
        path = s['run'] / 'production/scene-planning/initial.intent.json'
        value = json.loads(path.read_bytes())
        value['body']['model'] = 'qwen3:8b'
        path.write_text(json.dumps(value), encoding='utf-8')
    else:
        config = s['frozen'].config
        s['frozen'] = replace(s['frozen'], config=replace(config, raw=dict(config.raw, scene_planner_model='qwen3:8b')))
    with pytest.raises(ValueError):
        produce(s)
    assert len(s['received']) == 1


@pytest.mark.parametrize('point', ['proposal', 'visual-bible', 'scene-plan'])
def test_interrupted_durable_proposal_or_commit_resumes_without_http(scene_setup, monkeypatch, point):
    import video_ai.runtime.production_scene_plan as module
    def interrupt(where):
        if where == point: raise KeyboardInterrupt()
    monkeypatch.setattr(module, 'boundary', interrupt)
    with pytest.raises(KeyboardInterrupt): produce(scene_setup)
    assert not (scene_setup['run']/'.make-video.lock').exists()
    monkeypatch.setattr(module, 'boundary', lambda *args: None)
    assert len(produce(scene_setup)[1]['scenes']) == 2
    assert len(scene_setup['received']) == 1


def test_response_saved_before_proposal_recovers_original_http(scene_setup, monkeypatch):
    import video_ai.runtime.production_scene_plan as module
    monkeypatch.setattr(module, 'boundary', lambda where: (_ for _ in ()).throw(KeyboardInterrupt()) if where=='response' else None)
    with pytest.raises(KeyboardInterrupt): produce(scene_setup)
    monkeypatch.setattr(module, 'boundary', lambda *args: None)
    assert len(produce(scene_setup)[1]['scenes']) == 2
    assert len(scene_setup['received']) == 1


@pytest.mark.parametrize('point', ['completed', 'response'])
@pytest.mark.parametrize('grounded,reasoning', [(False, False), (True, False), (True, True)])
@pytest.mark.parametrize('scene_setup', ['qwen3:8b', 'qwen3:14b'], indirect=True)
def test_legacy_scene_wire_replays_original_body_without_new_http(scene_setup, monkeypatch, point, grounded, reasoning):
    import video_ai.adapters.ollama as adapter
    import video_ai.runtime.production_scene_plan as module
    body = adapter.ollama_body
    def legacy(*args, **kwargs):
        result = body(*args, **dict(kwargs, scene_source_constraints=grounded,scene_reasoning=reasoning,scene_key_constraints=False))
        return result
    with monkeypatch.context() as patch:
        patch.setattr(adapter, 'ollama_body', legacy)
        patch.setattr(module, 'ollama_body', legacy)
        if point == 'response':
            patch.setattr(module, 'boundary', lambda where: (_ for _ in ()).throw(KeyboardInterrupt()) if where == 'response' else None)
            with pytest.raises(KeyboardInterrupt):
                produce(scene_setup)
        else:
            produce(scene_setup)
    intent = scene_setup['run'] / 'production/scene-planning/initial.intent.json'
    original = intent.read_bytes()
    assert len(produce(scene_setup)[1]['scenes']) == 2
    assert len(scene_setup['received']) == 1
    assert intent.read_bytes() == original


@pytest.mark.parametrize('reasoning', [False, 'high'])
def test_tampered_reasoning_cannot_rebind_the_original_http_evidence(scene_setup, reasoning):
    s = scene_setup
    produce(s)
    path = s['run'] / 'production/scene-planning/initial.intent.json'
    value = json.loads(path.read_bytes())
    value['body']['think'] = reasoning
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(ValueError):
        produce(s)
    assert len(s['received']) == 1


def test_null_saved_scene_body_is_rejected_before_http_recovery(scene_setup, monkeypatch):
    import video_ai.runtime.production_scene_plan as module
    s = scene_setup
    produce(s)
    path = s['run'] / 'production/scene-planning/initial.intent.json'
    value = json.loads(path.read_bytes())
    value['body'] = None
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    def unexpected_recovery(*args, **kwargs):
        raise AssertionError('unmatched intent reached HTTP recovery')
    monkeypatch.setattr(module, 'recover_http', unexpected_recovery)
    with pytest.raises(ValueError, match='original scene planning intent'):
        produce(s)
    assert len(s['received']) == 1


def test_future_source_correction_receives_exact_rejected_and_eligible_sources(scene_setup):
    s = scene_setup
    bad = proposal()
    rejected = dict(unit_id='speech_0003', text_start=12, text_end=18, quote='它望向远处。')
    bad['scene_groups'][0]['source_facts'] = [dict(name='environment', value='湖边环境', sources=[rejected])]
    s['replies'].extend([bad, proposal()])
    assert len(produce(s)[1]['scenes']) == 2
    correction = s['received'][1]['prompt']
    assert 'SOURCE_REPAIR_JSON\n' in correction
    repair, _ = json.JSONDecoder().raw_decode(correction.split('SOURCE_REPAIR_JSON\n', 1)[1])
    assert repair['rejected_source'] == rejected
    assert repair['latest_allowed_end'] == 12
    assert repair['eligible_sources'] == [
        dict(unit_id='speech_0001', text_start=0, text_end=5, quote='湖面很静。'),
        dict(unit_id='speech_0002', text_start=5, text_end=12, quote='白鸟停在石上。'),
    ]
    assert len(s['received']) == 2


@pytest.mark.parametrize('historical', [False, True])
def test_unknown_scene_key_feedback_identifies_scene_and_declared_keys(scene_setup, monkeypatch, historical):
    import video_ai.runtime.production_scene_plan as module
    s = scene_setup
    bad = proposal()
    bad['scenes'][1]['scene_group_id'] = 'lake_00意图'
    s['replies'].extend([bad, proposal()])
    original_build = module.build_scene_plan
    def old_build(*args, **kwargs):
        try:
            return original_build(*args, **kwargs)
        except ValueError as exc:
            raise ValueError(str(exc)) from None
    with monkeypatch.context() as patch:
        if historical:
            patch.setattr(module, 'build_scene_plan', old_build)
        assert len(produce(s)[1]['scenes']) == 2
    prompt = s['received'][1]['prompt']
    assert ('SCENE_LINK_REPAIR_JSON\n' in prompt) is (not historical)
    if not historical:
        diagnostic, _ = json.JSONDecoder().raw_decode(prompt.split('SCENE_LINK_REPAIR_JSON\n', 1)[1])
        assert diagnostic['scene_index'] == 2
        assert diagnostic['rejected_references']['scene_group_id'] == 'lake_00意图'
        assert diagnostic['available_keys'] == dict(entity_ids=[], variant_ids=[], scene_group_ids=['lake'])
    before = {p: p.read_bytes() for p in s['run'].rglob('*') if p.is_file()}
    produce(s)
    assert len(s['received']) == 2
    assert all(p.read_bytes() == value for p, value in before.items())


def test_group_change_feedback_distinguishes_actions_from_environment(scene_setup):
    s = scene_setup
    bad = proposal()
    bad['scene_groups'].append(dict(deepcopy(bad['scene_groups'][0]), key='lake_next'))
    bad['scenes'][1]['scene_group_id'] = 'lake_next'
    s['replies'].extend([bad, proposal()])
    assert len(produce(s)[1]['scenes']) == 2
    prompt = s['received'][1]['prompt']
    assert 'SCENE_GROUP_REPAIR_JSON\n' in prompt
    diagnostic, _ = json.JSONDecoder().raw_decode(prompt.split('SCENE_GROUP_REPAIR_JSON\n', 1)[1])
    assert diagnostic['scene_index'] == 2
    assert diagnostic['previous_group'] == 'lake'
    assert diagnostic['proposed_group'] == 'lake_next'
    assert diagnostic['reuse_latest_end'] == 12
    assert diagnostic['eligible_reuse_source_ids'] == ['speech_0001', 'speech_0002']
    assert diagnostic['current_unit_ids'] == ['speech_0003']
    assert 'action change alone' in diagnostic['instruction']
    assert 'change_sources' in diagnostic['instruction']
    before = {p: p.read_bytes() for p in s['run'].rglob('*') if p.is_file()}
    produce(s)
    assert len(s['received']) == 2
    assert all(p.read_bytes() == value for p, value in before.items())


def test_historical_generic_group_feedback_replays_without_http(scene_setup, monkeypatch):
    import video_ai.runtime.production_scene_plan as module
    s = scene_setup
    bad = proposal()
    bad['scene_groups'].append(dict(deepcopy(bad['scene_groups'][0]), key='lake_next'))
    bad['scenes'][1]['scene_group_id'] = 'lake_next'
    s['replies'].extend([bad, proposal()])
    original_build = module.build_scene_plan
    def old_build(*args, **kwargs):
        try:
            return original_build(*args, **kwargs)
        except ValueError as exc:
            raise ValueError(str(exc)) from None
    with monkeypatch.context() as patch:
        patch.setattr(module, 'build_scene_plan', old_build)
        result = produce(s)
    assert 'CORRECTION\nscene group change requires source evidence' in s['received'][1]['prompt']
    assert 'SCENE_GROUP_REPAIR_JSON' not in s['received'][1]['prompt']
    before = {p: p.read_bytes() for p in s['run'].rglob('*') if p.is_file()}
    assert produce(s) == result
    assert len(s['received']) == 2
    assert all(p.read_bytes() == value for p, value in before.items())


@pytest.mark.parametrize('historical', [False, True])
@pytest.mark.parametrize('point', ['completed', 'response'])
@pytest.mark.parametrize('reasoning,keys', [(False, False), (True, False), (True, True)])
def test_source_correction_replays_exact_detailed_or_historical_feedback(scene_setup, monkeypatch, historical, point, reasoning, keys):
    import video_ai.adapters.ollama as adapter
    import video_ai.planning.production_scenes as scenes
    import video_ai.runtime.production_scene_plan as module
    s = scene_setup
    bad = proposal()
    bad['scene_groups'][0]['source_facts'] = [dict(name='environment', value='湖边环境', sources=[
        dict(unit_id='speech_0003', text_start=12, text_end=18, quote='它望向远处。')])]
    s['replies'].extend([bad, proposal()])
    original_source = scenes._source
    original_body = adapter.ollama_body
    def prior_body(*args, **kwargs):
        return original_body(*args, **dict(kwargs, scene_reasoning=reasoning,scene_key_constraints=keys))
    def without_notes(*args, **kwargs):
        try:
            return original_source(*args, **kwargs)
        except ValueError as exc:
            raise ValueError(str(exc)) from None
    def interrupt(where):
        if where == 'response' and len(s['received']) == 2:
            raise KeyboardInterrupt()
    with monkeypatch.context() as patch:
        patch.setattr(adapter, 'ollama_body', prior_body)
        patch.setattr(module, 'ollama_body', prior_body)
        if historical:
            patch.setattr(scenes, '_source', without_notes)
        if point == 'response':
            patch.setattr(module, 'boundary', interrupt)
            with pytest.raises(KeyboardInterrupt):
                produce(s)
        else:
            produce(s)
    intent = s['run'] / 'production/scene-planning/correction.intent.json'
    original = intent.read_bytes()
    assert json.loads(original)['body']['think'] is reasoning
    prompt = json.loads(original)['prompt']
    assert ('SOURCE_REPAIR_JSON\n' in prompt) is (not historical)
    before = {p: p.read_bytes() for p in s['run'].rglob('*') if p.is_file()}
    assert len(produce(s)[1]['scenes']) == 2
    assert len(s['received']) == 2
    assert intent.read_bytes() == original
    assert all(p.read_bytes() == value for p, value in before.items())


@pytest.mark.parametrize('bad', ['format', 'semantics'])
def test_one_correction_always_sees_full_source(scene_setup, bad):
    s = scene_setup
    item = proposal()
    if bad == 'format': item = {'wrong':'format'}
    else: item['scenes'][0]['unit_ids'] = ['speech_0001']
    s['replies'].append(item)
    assert len(produce(s)[1]['scenes']) == 2
    assert len(s['received']) == 2
    assert all(s['frozen'].script.text in p['prompt'] for p in s['received'])


def test_two_invalid_responses_stop_and_replay_never_posts(scene_setup):
    s = scene_setup; s['replies'] += [{'wrong':'first'}, {'wrong':'second'}]
    with pytest.raises(ValueError): produce(s)
    with pytest.raises(ValueError): produce(s)
    assert len(s['received']) == 2
    assert not (s['run']/'production/scene-plan-commit.json').exists()


def test_intent_without_response_stops_no_post_on_resume(scene_setup, monkeypatch):
    import video_ai.runtime.production_scene_plan as module
    monkeypatch.setattr(module, 'boundary', lambda where: (_ for _ in ()).throw(KeyboardInterrupt()) if where=='intent' else None)
    with pytest.raises(KeyboardInterrupt): produce(scene_setup)
    monkeypatch.setattr(module, 'boundary', lambda *args: None)
    with pytest.raises(ValueError, match='response|submission|POST'): produce(scene_setup)
    assert len(scene_setup['received']) == 0


@pytest.mark.parametrize('change', ['units','timeline','commit','bible','prompt','settings','run'])
def test_changed_identity_and_records_refused_without_http(scene_setup, change):
    s = scene_setup; produce(s)
    if change == 'units': s['units']['semantic_specs']['speech_0001']['facts']['subject']='changed'
    elif change == 'timeline': s['timeline'] = replace(s['timeline'], total_frames=s['timeline'].total_frames+1)
    elif change == 'settings':
        s['frozen'] = replace(s['frozen'], config=replace(s['frozen'].config,
                      raw=dict(s['frozen'].config.raw, scene_planning=dict(max_clip_seconds=3))))
    elif change == 'run': s['frozen'] = replace(s['frozen'], options=dict(s['frozen'].options, run_id='foreign'))
    else:
        path = {'commit': s['run']/'production/scene-plan-commit.json',
                'bible': s['run']/'production/visual-bible.json',
                'prompt': s['run']/'production/scene-planning/initial.intent.json'}[change]
        value = json.loads(path.read_text(encoding='utf-8'))
        if change == 'prompt': value['prompt'] += ' changed'
        else: value['source_sha256'] = '0'*64
        path.write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(ValueError): produce(s)
    assert len(s['received']) == 1


def test_caller_lock_consumed_and_not_released(scene_setup):
    from video_ai.runtime.production_state import RunLock
    s = scene_setup
    with RunLock(s['run']) as held:
        produce(s, lock=held)
        assert held.path.exists()
    assert not held.path.exists()


def test_lost_lock_before_request_stops_and_preserves_foreign_owner(scene_setup, monkeypatch):
    import video_ai.runtime.production_scene_plan as module
    s = scene_setup
    def steal(where):
        if where == 'intent':
            path=s['run']/'.make-video.lock'; owner=json.loads(path.read_text(encoding='utf-8'))
            owner['token']='f'*32; path.write_text(json.dumps(owner), encoding='utf-8')
    monkeypatch.setattr(module, 'boundary', steal)
    with pytest.raises(ValueError, match='lock'): produce(s)
    assert not s['received']
    assert (s['run']/'.make-video.lock').exists()


@pytest.mark.parametrize('outer', [dict(done=False), dict(done_reason='length'), dict(model='another:model')])
def test_incomplete_truncated_or_wrong_model_response_never_commits_or_corrects(scene_setup, outer):
    s=scene_setup; s['outer']=outer
    with pytest.raises(Exception): produce(s)
    with pytest.raises(Exception): produce(s)
    assert len(s['received']) == 1
    assert not (s['run']/'production/scene-plan-commit.json').exists()


@pytest.mark.parametrize('invalid', [False, True])
@pytest.mark.parametrize('scene_setup', ['qwen3:8b', 'qwen3:14b'], indirect=True)
def test_default_planner_stops_only_owned_service_and_releases_lock(scene_setup, monkeypatch, invalid):
    import video_ai.runtime.production_scene_plan as module
    from video_ai.runtime.services import ServiceHandle
    s=scene_setup; stopped=[]; ensured=[]
    class Manager:
        def __init__(self, paths, manifest, logger):
            assert manifest.snapshot()['run_id'] == s['run'].name
        def ensure(self, spec):
            ensured.append(spec)
            return ServiceHandle('ollama',spec.url,True,123,None,'now')
        def stop(self, handle): stopped.append(handle)
    monkeypatch.setattr(module,'ServiceManager',Manager)
    monkeypatch.setattr(module,'port_listening',lambda *args:False)
    if invalid: s['replies'] += [{'bad':1},{'bad':2}]
    def call():
        return module.produce_scene_plan(s['frozen'],s['units'],s['timeline'],paths=s['paths'],logger=s['logger'])
    if invalid:
        with pytest.raises(ValueError): call()
    else:
        assert len(call()[1]['scenes'])==2
        call() # Committed recovery starts no service.
    assert len(ensured)==len(stopped)==1
    assert ensured[0].args[-1]=='serve'
    assert not (s['run']/'.make-video.lock').exists()


def test_recovery_uses_persisted_effective_defaults(scene_setup, monkeypatch):
    import video_ai.config as config
    import video_ai.runtime.production_scene_plan as module
    s=scene_setup; result=produce(s)
    original=config.parse_scene_planning
    def changed_defaults(value):
        return config.ScenePlanningSettings(1,3) if value is None else original(value)
    monkeypatch.setattr(config,'parse_scene_planning',changed_defaults)
    monkeypatch.setattr(module,'parse_scene_planning',changed_defaults)
    assert produce(s)==result
    assert len(s['received'])==1


def test_changed_original_http_body_conflicts_with_saved_response(scene_setup):
    s=scene_setup; produce(s)
    path=next((s['run']/'logs/production/http').glob('*.body'))
    raw=path.read_bytes(); path.write_bytes(raw.replace('湖'.encode(),'河'.encode()))
    with pytest.raises(ValueError): produce(s)
    assert len(s['received'])==1


def test_model_context_explicitly_reserves_room_for_full_prompt_and_output(scene_setup):
    s=scene_setup; produce(s)
    body=s['received'][0]
    prompt_bytes=len(body['prompt'].encode('utf-8'))
    schema_bytes=len(json.dumps(body['format'],ensure_ascii=False).encode('utf-8'))
    assert body['options']['num_ctx'] >= prompt_bytes+schema_bytes+body['options']['num_predict']+2048


def test_oversized_full_context_refuses_before_intent_and_http(scene_setup):
    s=scene_setup
    s['units']['planner']=dict(original_evidence='全文不能截断'*10000)
    with pytest.raises(ValueError,match='context|上下文'): produce(s)
    assert s['received']==[]
    assert not (s['run']/'production/scene-planning/initial.intent.json').exists()
    assert not (s['run']/'production/scene-plan-commit.json').exists()
