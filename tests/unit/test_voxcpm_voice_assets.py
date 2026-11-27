import hashlib
import json
from dataclasses import replace
from pathlib import Path
import socket

import pytest

from test_speech_plan import profile
from test_tts_backends import vox_config


def asset_at(root):
    folder = root/'shared/assets/voices/male-sleep-01'
    folder.mkdir(parents=True)
    audio = folder/'reference.wav'; audio.write_bytes(b'new-male-reference')
    value = dict(schema_version=1, voice_id='male-sleep-01', reference_audio='reference.wav',
                 reference_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
                 base_style='成年男声，温润中低音，纪录片旁白，语速舒缓，情绪克制')
    path = folder/'voice.json'; path.write_text(json.dumps(value), encoding='utf-8')
    return path, audio, value


def test_explicit_asset_freezes_new_voice_without_mutating_gpt(runtime_run, tmp_path):
    from video_ai.planning.speech import freeze_voice
    config = replace(vox_config(runtime_run[1]), runtime_root=tmp_path/'runtime')
    path, audio, value = asset_at(config.runtime_root)
    new = freeze_voice(config, voice_profile=path)
    assert new.voice_id == 'male-sleep-01'
    assert new.reference_sha256 == value['reference_sha256']
    assert new.base_style == value['base_style']
    assert new.parameters['voice_id'] == new.voice_id
    assert new.parameters['seed'] == 42
    assert new.reference_sha256 != config.voice.reference_sha256
    assert freeze_voice(config) == profile(runtime_run)


def test_explicit_service_assets_ignore_legacy_config_and_copy_reference_once(tmp_path):
    from video_ai.voxcpm.engine import load_assets
    root = tmp_path/'runtime'
    path, audio, value = asset_at(root)
    binding, factory = load_assets(root, root/'scratch/state', voice_profile=path)
    assert binding['voice_id'] == value['voice_id']
    assert binding['reference_sha256'] == value['reference_sha256']
    assert (root/'scratch/state/inputs'/(value['reference_sha256']+'.wav')).read_bytes() == audio.read_bytes()
    assert callable(factory)


def test_legacy_service_assets_keep_original_binding(tmp_path):
    from video_ai.voxcpm.engine import load_assets
    root = tmp_path/'runtime'
    path, audio, value = asset_at(root)
    legacy = root/'shared/config'; legacy.mkdir(parents=True)
    voice = legacy/'voice.json'
    voice.write_text(json.dumps(dict(reference_audio=str(audio),reference_sha256=value['reference_sha256'])),encoding='utf-8')
    (legacy/'production.json').write_text(json.dumps(dict(voice_config=str(voice))),encoding='utf-8')
    binding, _ = load_assets(root, root/'scratch/state')
    assert binding['voice_id'] == 'existing-reference'


@pytest.mark.parametrize('damage', ['outside_profile','outside_reference','traversal','absolute_reference','digest','identity','style','version'])
def test_invalid_voice_asset_rejected_without_inference(tmp_path, damage):
    from video_ai.voxcpm.voices import load_voice_asset
    from video_ai.voxcpm.engine import load_assets
    root = tmp_path/'runtime'
    path, _, value = asset_at(root)
    if damage == 'outside_profile':
        outside = tmp_path/'voice.json'; outside.write_text(path.read_text(encoding='utf-8'),encoding='utf-8'); path=outside
    if damage == 'outside_reference': value['reference_audio'] = str(tmp_path/'outside.wav')
    if damage == 'traversal': value['reference_audio'] = '../reference.wav'
    if damage == 'absolute_reference': value['reference_audio'] = str(root/'other.wav')
    if damage == 'digest': value['reference_sha256'] = 'a'*64
    if damage == 'identity': value['voice_id'] = '../bad'
    if damage == 'style': value['base_style'] = ' '
    if damage == 'version': value['schema_version'] = 99
    path.write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ValueError):
        if damage == 'digest': load_assets(root, root/'scratch/state', voice_profile=path)
        else: load_voice_asset(path, root)
    assert not (root/'scratch/state/inputs').exists()


def test_owner_passes_explicit_asset_to_child(tmp_path, monkeypatch):
    from video_ai.voxcpm.process import VoxServiceProcess
    root = tmp_path/'runtime'
    path, _, _ = asset_at(root)
    captured = {}
    def launch(command, **kwargs):
        captured['command'] = command
        raise FileNotFoundError('stop before launching')
    monkeypatch.setattr('video_ai.voxcpm.process.subprocess.Popen', launch)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0)); port = probe.getsockname()[1]
    controller = VoxServiceProcess(root, root/'scratch/state', port=port, voice_profile=path)
    with pytest.raises(FileNotFoundError): controller.start()
    command = captured['command']
    assert command[command.index('--voice-profile')+1] == str(path)


def test_saved_runtime_relative_profile_roundtrips(runtime_run, tmp_path):
    from video_ai.voxcpm.voices import load_voice_asset
    from video_ai.voxcpm.process import VoxServiceProcess
    from video_ai.planning.speech import freeze_voice
    root = tmp_path/'runtime'
    path, _, value = asset_at(root)
    relative = str(path.relative_to(root))
    assert load_voice_asset(relative, root).voice_id == value['voice_id']
    config = replace(vox_config(runtime_run[1]), runtime_root=root)
    assert freeze_voice(config, voice_profile=relative).reference_sha256 == value['reference_sha256']
    assert VoxServiceProcess(root, root/'scratch/state', voice_profile=relative).voice_profile == path
