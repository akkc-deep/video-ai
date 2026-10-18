import json
from pathlib import Path
import pytest

SOURCE = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('settings', [None, {}, {'sentence_pause_seconds':0,'closing_seconds':0}])
def test_timeline_compatible_defaults(tmp_path,settings):
    from video_ai.config import load_config
    path=fixture_config(tmp_path,change=lambda d: d['media'].pop('timeline',None) if settings is None else d['media'].update(timeline=settings))
    t=load_config(path).media.timeline
    assert t.paragraph_pause_seconds==2 and t.opening_seconds==2
    assert t.sentence_pause_seconds==(0 if settings and 'sentence_pause_seconds' in settings else .8)


@pytest.mark.parametrize('value',[None,True,-1,'1',float('inf'),{'extra':1},{'opening_seconds':None},{'opening_seconds':True},{'closing_seconds':-1}])
def test_timeline_config_invalid(tmp_path,value):
    from video_ai.config import load_config,ConfigError
    path=fixture_config(tmp_path,change=lambda d:d['media'].update(timeline=value))
    with pytest.raises(ConfigError):load_config(path)


def fixture_config(tmp_path, change=None, voice_change=None):
    data = json.loads((SOURCE / 'config/production.example.json').read_text(encoding='utf-8'))
    voice = json.loads((SOURCE / 'config/voice.example.json').read_text(encoding='utf-8'))
    if change:
        change(data)
    if voice_change:
        voice_change(voice)
    (tmp_path / '声音 目录').mkdir(exist_ok=True)
    voice_path = tmp_path / '声音 目录/voice.json'
    voice_path.write_text(json.dumps(voice, ensure_ascii=False), encoding='utf-8-sig')
    data['voice_config'] = './声音 目录/voice.json'
    path = tmp_path / 'project.json'
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8-sig')
    return path


def test_config_load_resolves_nested_owner_and_preserves_input(tmp_path):
    from video_ai.config import load_config
    path = fixture_config(tmp_path, voice_change=lambda d: d.update(reference_audio='../参考.wav'))
    before = set(tmp_path.rglob('*'))
    config = load_config(path)
    assert config.voice.reference_audio == tmp_path / '参考.wav'
    assert config.voice.raw['reference_audio'] == '../参考.wav'
    assert config.media.fps == 16
    assert config.media.frame_rate_conversion is False
    assert config.media.profile.width == 768
    assert config.media.profile.native_fps == 16
    assert set(tmp_path.rglob('*')) == before


@pytest.mark.parametrize('field,value', [
    ('schema_version', True), ('schema_version', 2), ('runtime_root', None),
    ('runtime_root', 'C:/VideoSi'), ('cache_root', 'D:/code/py/video-ai/cache'),
    ('voice_config', ''), ('unexpected', 1),
])
def test_invalid_top_level_field_has_actionable_location(tmp_path, field, value):
    from video_ai.config import load_config, ConfigError
    path = fixture_config(tmp_path, change=lambda d: d.update({field: value}))
    if field == 'voice_config':
        d = json.loads(path.read_text(encoding='utf-8-sig'))
        d[field] = value
        path.write_text(json.dumps(d), encoding='utf-8')
    with pytest.raises(ConfigError, match=field):
        load_config(path)


@pytest.mark.parametrize('section,field,value', [
    ('media', 'fps', True), ('media', 'fps', 30), ('media', 'final_width', True),
    ('media', 'profile', 'unknown'), ('media', 'burn_subtitles', False),
    ('media', 'transition_seconds', float('nan')), ('timeouts', 'wan', 0),
    ('services', 'tts', 'https://127.0.0.1:9880'),
    ('services', 'tts', 'http://remote.example:9880'),
    ('services', 'tts', 'http://user@localhost:9880'),
    ('services', 'tts', 'http://localhost:9880?secret=1'),
    ('services', 'tts', 'http://@localhost:9880'),
    ('services', 'tts', 'http://loca\tlhost:9880'),
    ('services', 'tts', ' http://localhost:9880'),
    ('media', 'transition_seconds', 10**1000),
])
def test_invalid_nested_fields_rejected(tmp_path, section, field, value):
    from video_ai.config import load_config, ConfigError
    path = fixture_config(tmp_path, change=lambda d: d[section].update({field: value}))
    with pytest.raises(ConfigError):
        load_config(path)


@pytest.mark.parametrize('field,value', [
    ('reference_sha256', 'not-a-hash'), ('reference_text', ''),
    ('speed_factor', -1), ('is_half', True), ('device', 'cuda:-1'),
])
def test_voice_invalid_fields_rejected(tmp_path, field, value):
    from video_ai.config import load_config, ConfigError
    path = fixture_config(tmp_path, voice_change=lambda d: d.update({field: value}))
    with pytest.raises(ConfigError, match=field):
        load_config(path)


def test_24fps_explicitly_records_conversion(tmp_path):
    from video_ai.config import load_config
    path = fixture_config(tmp_path, change=lambda d: d['media'].update(fps=24))
    assert load_config(path).media.frame_rate_conversion is True


def test_duplicate_keys_and_null_rejected_without_directory_creation(tmp_path):
    from video_ai.config import load_config, ConfigError
    path = tmp_path / 'duplicate.json'
    path.write_text('{"schema_version":1,"schema_version":1}', encoding='utf-8')
    with pytest.raises(ConfigError, match='schema_version'):
        load_config(path)
    path.write_text('null', encoding='utf-8')
    with pytest.raises(ConfigError):
        load_config(path)
