import json
from pathlib import Path

import pytest
from unit.test_production_inputs import production_config


def recipe():
    return json.loads((Path(__file__).parents[2]/'config/approved-narration.json').read_text(encoding='utf-8'))


def approved_config(config, narration=None):
    from video_ai.config import load_config
    from video_ai.runtime.manifest import thaw
    raw = thaw(config.raw)
    import hashlib
    r = dict(narration) if narration is not None else recipe()
    if narration is None:
        # Historical 07 fixtures exercise their original frozen 850ms path.
        r.pop('onset_guard', None); r['paragraph_pause_ms'] = 850
    profile = config.config_file.parent/'source-voice/voice.json'
    profile.parent.mkdir(parents=True,exist_ok=True)
    reference=profile.parent/'reference.wav'; reference.write_bytes(config.voice.reference_audio.read_bytes())
    r.update(voice_profile=str(profile),reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest())
    profile.write_text(json.dumps(dict(schema_version=1,voice_id=r['voice_id'],reference_audio='reference.wav',
        reference_sha256=r['reference_sha256'],base_style='approved')),encoding='utf-8')
    raw['tts'] = dict(engine='voxcpm2', model_revision=r['model_revision'], narration=r)
    config.config_file.write_text(json.dumps(raw), encoding='utf-8')
    return load_config(config.config_file)


def test_recipe_freezes_exact_reference_prompt():
    from video_ai.tts_config import parse_tts_settings
    from video_ai.voxcpm.contracts import freeze_request
    r = recipe()
    settings = parse_tts_settings(dict(tts=dict(engine='voxcpm2', model_revision=r['model_revision'], narration=r)))
    bound = freeze_request(dict(settings.parameters, request_id='test', text='湖水。'), dict(voice_id=r['voice_id']))
    assert bound['synthesis_text'] == '湖水。'
    assert bound['prompt_text'] == r['prompt_text']
    assert bound['conditioning_mode'] == 'reference-prompt'
    assert bound['inference_timesteps'] == 20
    assert settings.narration['speech_rate'] == .95


def test_production_accepts_only_explicit_recipe(production_config):
    from video_ai.runtime.production_inputs import validate_supported
    validate_supported(approved_config(production_config))


def test_frozen_recipe_assets_survive_global_change(production_config, runtime_run):
    from video_ai.runtime.production_inputs import freeze_inputs, load_frozen_inputs
    from video_ai.runtime.manifest import thaw
    import hashlib
    run = runtime_run[0]
    config = approved_config(production_config)
    profile = run/'source-voice/voice.json'
    profile.parent.mkdir(parents=True, exist_ok=True)
    reference = profile.parent/'reference.wav'
    reference.write_bytes(config.voice.reference_audio.read_bytes())
    r = recipe(); r['reference_sha256'] = hashlib.sha256(reference.read_bytes()).hexdigest()
    r['voice_profile'] = str(profile)
    raw = thaw(config.raw); raw['tts']['narration'] = r
    profile.write_text(json.dumps(dict(schema_version=1, voice_id=r['voice_id'], reference_audio='reference.wav',
        reference_sha256=r['reference_sha256'], base_style='approved')), encoding='utf-8')
    config.config_file.write_text(json.dumps(raw), encoding='utf-8')
    from video_ai.config import load_config
    frozen = freeze_inputs(load_config(config.config_file), run, text='湖水。')
    reference.write_bytes(b'changed'); profile.write_text('{}')
    loaded = load_frozen_inputs(run)
    assert loaded.config.tts.narration == frozen.config.tts.narration
    assert (run/'production/inputs/vox/reference.wav').read_bytes() != b'changed'


def test_paragraph_plan_preserves_skips_and_limits_long_text():
    from video_ai.runtime.production_vox_speech import paragraph_plan
    from video_ai.planning.segments import segment_text
    text = '湖水。白鸟。\n，。\n'+'星'*520+'。'
    plan = paragraph_plan(text, [vars(s) for s in segment_text(text)])
    assert all(len(p['text']) <= 250 for p in plan)
    assert plan[0]['text'] == '湖水。白鸟。'
    assert plan[0]['pause_after_ms'] == 850
    assert ''.join(text[p['start']:p['end']] for p in plan).replace('湖水。白鸟。','') == '星'*520+'。'


def test_measured_alignment_cuts_without_character_interpolation():
    from video_ai.media.speech_alignment import measured_cuts
    spans = [dict(start=0,end=3,text='湖水。'),dict(start=3,end=6,text='白鸟。')]
    aligned = dict(tokens=['湖','水','白','鸟'], timestamp=[[0,50],[50,90],[130,160],[160,200]])
    assert measured_cuts('湖水。白鸟。', spans, aligned, 12000) == [0,5280,12000]
    with pytest.raises(ValueError): measured_cuts('湖水。白鸟。',spans,dict(aligned,tokens=['错']),12000)


def test_unsupported_alignment_characters_refused_before_generation():
    from video_ai.media.speech_alignment import alignment_words
    assert alignment_words('温度20℃，AI正在运行。') == ['温','度','2','0','AI','正','在','运','行']
    with pytest.raises(ValueError,match='unsupported.*α'):
        alignment_words('α粒子进入大气层。')


def test_graceful_shutdown_preserves_accepted_running_request(tmp_path):
    import threading
    import wave
    from video_ai.voxcpm.store import JobStore
    from video_ai.voxcpm.service import JobService
    from unit.test_voxcpm_service import BINDING, BODY, wait_for
    started=threading.Event(); release=threading.Event()
    class Backend:
        def generate(self,request,temporary):
            started.set(); assert release.wait(3)
            temporary.parent.mkdir(parents=True,exist_ok=True)
            with wave.open(str(temporary),'wb') as f:
                f.setparams((1,2,48000,0,'NONE',''));f.writeframes(b'\x40\x01'*480)
            return dict(generation_time_ms=1)
    root=tmp_path/'runtime'
    with JobStore(root/'scratch/tts',root) as store:
        service=JobService(store,BINDING,Backend);service.start()
        wait_for(service.health,lambda v:v['status']=='ready')
        service.submit(BODY); assert started.wait(2)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(1) as pool:
            done=pool.submit(service.close,finish_pending=True)
            release.set()
            try: done.result(timeout=3)
            finally: service.close()
        assert store.get(BODY['request_id'])['status']=='completed'


def test_production_reuses_raw_after_interrupted_alignment(production_config, runtime_run, monkeypatch):
    import shutil
    from types import SimpleNamespace
    from production_helpers import model_server,config_for_server,install_owned_services,wav_bytes
    from unit.test_production_speech import make_prefix
    from video_ai.runtime.production_storyboard import produce_units
    from video_ai.runtime.production_speech import produce_speech
    from video_ai.runtime.production_timeline import produce_timeline
    import video_ai.runtime.production_vox_speech as vox
    from video_ai.config import read_json
    run,_,paths=runtime_run
    shutil.copyfile('C:/Windows/Fonts/msyh.ttc',production_config.media.font_file)
    generated=[]; stopped=[]
    class Process:
        def __init__(self,*args,**kwargs): pass
        def start(self,**kwargs): pass
        def stop(self,**kwargs): stopped.append(True);return 0
    def synthesize(self,text,*,unit_id):
        generated.append(text)
        return SimpleNamespace(body=wav_bytes(samples=12000))
    monkeypatch.setattr(vox,'VoxServiceProcess',Process)
    monkeypatch.setattr(vox.VoxTtsClient,'synthesize',synthesize)
    def command(args,**kwargs):
        if '-af' in args:
            shutil.copyfile(args[args.index('-i')+1],args[-1]); return
        raise RuntimeError('interrupted alignment')
    monkeypatch.setattr(vox,'audio_command',command)
    with model_server() as (url,posts):
        config=approved_config(config_for_server(production_config,url,run))
        frozen,state,manifest,logger=make_prefix(config,run,'湖水。白鸟。\n星光。')
        install_owned_services(monkeypatch)
        units=produce_units(frozen,state=state,manifest=manifest,paths=paths,logger=logger)
        with pytest.raises(RuntimeError,match='interrupted'):
            produce_speech(frozen,units,state=state,manifest=manifest,paths=paths,logger=logger)
        assert generated==['湖水。白鸟。','星光。'] and stopped==[True]
        def completed_command(args,**kwargs):
            rows=read_json(Path(args[args.index('--request')+1]))['paragraphs']
            measured=[dict(unit_id=r['unit_id'],tokens=list('湖水白鸟') if i==0 else list('星光'),
                timestamp=[[i*40,(i+1)*40] for i in range(4 if i==0 else 2)]) for i,r in enumerate(rows)]
            Path(args[args.index('--output')+1]).write_text(json.dumps(dict(paragraphs=measured)),encoding='utf-8')
        monkeypatch.setattr(vox,'audio_command',completed_command)
        audio=produce_speech(frozen,units,state=state,manifest=manifest,paths=paths,logger=logger)
        timeline,_=produce_timeline(frozen,units,audio,state=state,manifest=manifest,paths=paths,logger=logger)
        assert len(generated)==2 and len(stopped)==1
        assert timeline.total_silence_samples==240000  # only opening and closing, no duplicate pauses
        assert sum(v.samples for v in audio.values())==64800
        assert produce_speech(frozen,units,state=state,manifest=manifest,paths=paths,logger=logger)==audio
        import wave
        def pcm(path):
            with wave.open(str(path),'rb') as f:return f.readframes(f.getnframes())
        narration=read_json(run/'production/vox/narration.json')['metadata']['audio_path']
        assert b''.join(pcm(i.path) for i in audio.values())==pcm(narration)
