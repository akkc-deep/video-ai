from array import array
from copy import deepcopy
import json
from pathlib import Path

import pytest
from unit.test_production_inputs import production_config


GUARD = dict(schema_version=1, text='下面继续讲述。', search_start_ms=1000,
             search_end_ms=2600, min_silence_ms=150, retained_silence_ms=50,
             silence_peak=32, boundary='longest-quiet-run', zero_quiet_edges=True)


def current_recipe():
    value = json.loads((Path(__file__).parents[2]/'config/approved-narration.json').read_text(encoding='utf-8'))
    value.update(paragraph_pause_ms=500, onset_guard=deepcopy(GUARD))
    return value


def test_repository_default_is_the_approved_full_narration_version():
    value = json.loads((Path(__file__).parents[2]/'config/approved-narration.json').read_text(encoding='utf-8'))
    assert value['paragraph_pause_ms'] == 500
    assert value['onset_guard'] == GUARD
    assert value['approval']['user_instruction'] == '后面的视频都按这一版来'


def test_new_recipe_preserves_voice_and_accepts_approved_500ms_guard():
    from video_ai.tts_config import parse_tts_settings
    r = current_recipe()
    settings = parse_tts_settings(dict(tts=dict(engine='voxcpm2', model_revision=r['model_revision'], narration=r)))
    assert settings.narration['paragraph_pause_ms'] == 500
    assert settings.parameters['seed'] == 42
    assert settings.parameters['prompt_text'] == r['prompt_text']


def test_legacy_frozen_recipe_remains_accepted_but_unguarded_500ms_is_refused():
    from video_ai.tts_config import parse_tts_settings
    from video_ai.config import ConfigError
    r = current_recipe(); r.pop('onset_guard'); r['paragraph_pause_ms'] = 850
    parse_tts_settings(dict(tts=dict(engine='voxcpm2', model_revision=r['model_revision'], narration=r)))
    r['paragraph_pause_ms'] = 500
    with pytest.raises(ConfigError):
        parse_tts_settings(dict(tts=dict(engine='voxcpm2', model_revision=r['model_revision'], narration=r)))


def test_guard_removal_uses_acoustic_separator_and_preserves_original_body():
    from video_ai.media.narration_guard import remove_spoken_guard
    # A voiced guide/residual, the guide/body separator, then original speech.
    pcm = array('h', [14000]*62400 + [0]*40800 + [15000]*24000 + [0]*4800)
    body, metadata = remove_spoken_guard(pcm.tobytes(), GUARD)
    assert metadata['cut_samples'] == 100800  # 2.15s quiet end minus 50ms
    assert body == pcm[100800:].tobytes()
    assert array('h', body)[:2400] == array('h', [0]*2400)


def test_missing_separator_fails_without_discarding_arbitrary_speech():
    from video_ai.media.narration_guard import remove_spoken_guard
    with pytest.raises(ValueError, match='separator'):
        remove_spoken_guard(array('h', [12000]*144000).tobytes(), GUARD)


def test_longer_pause_inside_body_is_refused_instead_of_deleting_first_phrase():
    from video_ai.media.narration_guard import remove_spoken_guard
    pcm = array('h', [14000]*62400 + [0]*9600 + [15000]*14400
                + [0]*28800 + [15000]*14400)
    with pytest.raises(ValueError, match='ambiguous.*separator'):
        remove_spoken_guard(pcm.tobytes(), GUARD)


def test_too_short_guide_gap_is_not_hidden_by_later_body_pause():
    from video_ai.media.narration_guard import remove_spoken_guard
    pcm = array('h', [14000]*62400 + [0]*4800 + [15000]*19200
                + [0]*28800 + [15000]*14400)
    with pytest.raises(ValueError, match='ambiguous.*separator'):
        remove_spoken_guard(pcm.tobytes(), GUARD)


def test_tiny_quiet_blip_next_to_approved_separator_keeps_original_cut():
    from video_ai.media.narration_guard import remove_spoken_guard
    pcm = array('h', [14000]*65280 + [0]*480 + [14000]*960 + [0]*42240 + [15000]*12000)
    body, metadata = remove_spoken_guard(pcm.tobytes(), GUARD)
    assert metadata['silent_separator_ms'] == [1390,2270]
    assert body == pcm[106560:].tobytes()


def test_guarded_planning_reserves_request_capacity_and_uses_500ms():
    from video_ai.runtime.production_vox_speech import paragraph_plan
    from video_ai.planning.segments import segment_text
    text = '星'*520+'。\n木星。'
    plan = paragraph_plan(text, [vars(s) for s in segment_text(text)], narration=current_recipe())
    assert all(len(GUARD['text']+p['text']) <= 250 for p in plan)
    assert plan[-2]['pause_after_ms'] == 500
    assert plan[-1]['pause_after_ms'] == 0
    assert ''.join(p['text'] for p in plan) == text.replace('\n', '')


def test_nonapproved_guard_values_are_rejected():
    from video_ai.tts_config import parse_tts_settings
    from video_ai.config import ConfigError
    r = current_recipe(); r['onset_guard']['text'] = '换个声音。'
    with pytest.raises(ConfigError):
        parse_tts_settings(dict(tts=dict(engine='voxcpm2', model_revision=r['model_revision'], narration=r)))


def test_guarded_production_aligns_only_body_and_resumes_without_new_tts(production_config, runtime_run, monkeypatch):
    from io import BytesIO
    import shutil
    from types import SimpleNamespace
    import wave
    from production_helpers import model_server, config_for_server, install_owned_services
    from unit.test_approved_voice_production import approved_config
    from unit.test_production_speech import make_prefix
    from video_ai.runtime.production_storyboard import produce_units
    from video_ai.runtime.production_speech import produce_speech
    from video_ai.runtime.production_timeline import produce_timeline
    from video_ai.config import read_json
    import video_ai.runtime.production_vox_speech as vox

    run, _, paths = runtime_run
    shutil.copyfile('C:/Windows/Fonts/msyh.ttc', production_config.media.font_file)
    buffer = BytesIO()
    with wave.open(buffer, 'wb') as f:
        f.setparams((1,2,48000,0,'NONE',''))
        f.writeframes(array('h', [14000]*62400+[0]*40800+[1200]*12000+[0]*4800).tobytes())
    generated, stopped = [], []
    class Process:
        def __init__(self, *args, **kwargs): pass
        def start(self, **kwargs): pass
        def stop(self, **kwargs): stopped.append(True); return 0
    monkeypatch.setattr(vox, 'VoxServiceProcess', Process)
    def synthesize(self, text, *, unit_id):
        generated.append(text); return SimpleNamespace(body=buffer.getvalue())
    monkeypatch.setattr(vox.VoxTtsClient, 'synthesize', synthesize)
    def interrupted(args, **kwargs):
        if '-af' in args:
            assert args[args.index('-af')+1] == 'atempo=0.95'
            shutil.copyfile(args[args.index('-i')+1], args[-1]); return
        raise RuntimeError('interrupted body alignment')
    monkeypatch.setattr(vox, 'audio_command', interrupted)
    with model_server() as (url, posts):
        config = approved_config(config_for_server(production_config,url,run), narration=current_recipe())
        frozen, state, manifest, logger = make_prefix(config, run, '湖水。白鸟。\n星光。')
        install_owned_services(monkeypatch)
        units = produce_units(frozen, state=state, manifest=manifest, paths=paths, logger=logger)
        with pytest.raises(RuntimeError, match='interrupted body alignment'):
            produce_speech(frozen, units, state=state, manifest=manifest, paths=paths, logger=logger)
        assert generated == [GUARD['text']+'湖水。白鸟。', GUARD['text']+'星光。']
        def aligned(args, **kwargs):
            rows = read_json(Path(args[args.index('--request')+1]))['paragraphs']
            assert [r['text'] for r in rows] == ['湖水。白鸟。', '星光。']
            for row in rows:
                assert Path(row['audio_path']).name == 'body.wav'
                with wave.open(row['audio_path'], 'rb') as f: assert f.readframes(2400) == bytes(4800)
            result = [dict(unit_id=r['unit_id'], tokens=list('湖水白鸟') if i == 0 else list('星光'),
                           timestamp=[[60+j*40,100+j*40] for j in range(4 if i == 0 else 2)])
                      for i,r in enumerate(rows)]
            Path(args[args.index('--output')+1]).write_text(json.dumps(dict(paragraphs=result)), encoding='utf-8')
        monkeypatch.setattr(vox, 'audio_command', aligned)
        audio = produce_speech(frozen, units, state=state, manifest=manifest, paths=paths, logger=logger)
        timeline, _ = produce_timeline(frozen, units, audio, state=state, manifest=manifest, paths=paths, logger=logger)
        assert len(generated) == 2 and len(stopped) == 1
        assert timeline.total_silence_samples == 240000
        assert timeline.total_speech_samples == 55200
        assert produce_speech(frozen, units, state=state, manifest=manifest, paths=paths, logger=logger) == audio
        metadata = read_json(run/'production/vox/narration.json')['metadata']
        assert metadata['voice']['paragraph_pause_ms'] == 500
        with wave.open(metadata['audio_path'],'rb') as f: full = f.readframes(f.getnframes())
        clips = metadata['clips']
        a = clips[0]['end_sample']-clips[0]['trailing_silence_samples']
        b = clips[1]['start_sample']+clips[1]['leading_silence_samples']
        assert b-a == 24000 and full[a*2:b*2] == bytes(48000)
