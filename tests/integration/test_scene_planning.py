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
def scene_setup(production_config, runtime_run, tmp_path):
    from video_ai.adapters.common import HttpClient
    from video_ai.adapters.ollama import OllamaPlanner
    from video_ai.config import load_config
    from video_ai.planning.production_timeline import ProductionAudioInfo, build_production_timeline
    from video_ai.runtime.logging import RunLogger
    from video_ai.runtime.manifest import thaw
    from video_ai.runtime.paths import RuntimePaths
    from video_ai.runtime.production_inputs import freeze_inputs
    from video_ai.runtime.production_state import ArtifactStamp
    received = []; replies = []; controls = {}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            item = replies.pop(0) if replies else proposal()
            outer = dict(model='qwen3:8b', done=True, done_reason='stop', response=json.dumps(item, ensure_ascii=False))
            outer.update(controls.get('outer', {}))
            raw = json.dumps(outer, ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length', str(len(raw))); self.end_headers()
            self.wfile.write(raw)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        config = configured(production_config, tmp_path)
        data = thaw(config.raw); data['services']['ollama'] = f'http://127.0.0.1:{server.server_port}'
        config.config_file.write_text(json.dumps(data), encoding='utf-8')
        config = load_config(config.config_file)
        run = runtime_run[0]
        frozen = freeze_inputs(config, run, text='湖面很静。白鸟停在石上。它望向远处。')
        script = frozen.script
        audio = {s.unit_id: ProductionAudioInfo(ArtifactStamp('D:/pcm.wav', 96046, 123),
                 48000, 1, 2, 48001) for s in script.spans if s.kind == 'speech'}
        timeline = build_production_timeline(script, audio, settings=config.media.timeline)
        units = dict(decoded_text=script.text, has_bom=script.has_bom, spans=thaw(script.spans),
                     semantic_specs={s.unit_id: dict(facts={}) for s in script.spans if s.kind == 'speech'})
        logger = RunLogger(run, production=True)
        planner = OllamaPlanner(HttpClient(config.services['ollama'], 5, logger))
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
