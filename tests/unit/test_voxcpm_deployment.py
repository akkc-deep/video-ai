"""Deployment transactions operate on shared defaults, never historical runs."""
import hashlib
import json
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2]


@pytest.fixture
def installation(tmp_path):
    root = tmp_path/'runtime space'
    source = tmp_path/'source'
    (source/'config').mkdir(parents=True)
    recipe = json.loads((SOURCE/'config/approved-narration.json').read_text(encoding='utf-8'))
    recipe['reference_sha256'] = hashlib.sha256(b'reference').hexdigest()
    (source/'config/approved-narration.json').write_text(json.dumps(recipe), encoding='utf-8')
    assets = tmp_path/'approved assets'
    assets.mkdir()
    (assets/'reference.wav').write_bytes(b'reference')
    (assets/'approved-production-20261128.wav').write_bytes(b'approved production')
    (assets/'voice.json').write_text(json.dumps(dict(schema_version=1,voice_id=recipe['voice_id'],
        reference_audio='reference.wav',reference_sha256=recipe['reference_sha256'],base_style='approved')),encoding='utf-8')
    return root, source, assets, recipe


def test_asset_install_is_idempotent_and_preserves_conflicts(installation):
    from video_ai.voxcpm.deployment import provision_voice
    root, source, assets, recipe = installation
    provision_voice(root, source, assets)
    target = root/Path(recipe['voice_profile'])
    assert target.is_file()
    default = root/'shared/config/tts/default-narration.json'
    before = default.stat().st_mtime_ns
    provision_voice(root, source, assets)
    assert default.stat().st_mtime_ns == before
    target.with_name('reference.wav').write_bytes(b'conflict')
    with pytest.raises(ValueError, match='identity|conflict'):
        provision_voice(root, source, assets)
    assert target.with_name('reference.wav').read_bytes() == b'conflict'


def test_missing_assets_fail_before_creating_default(installation):
    from video_ai.voxcpm.deployment import provision_voice
    root, source, assets, _ = installation
    (assets/'approved-production-20261128.wav').unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        provision_voice(root, source, assets)
    assert not (root/'shared/config/tts/default-narration.json').exists()


def test_upgrade_850ms_default_keeps_backup(installation):
    from video_ai.voxcpm.deployment import provision_voice
    root, source, assets, recipe = installation
    target=root/'shared/config/tts/default-narration.json'
    target.parent.mkdir(parents=True)
    old=dict(recipe, paragraph_pause_ms=850);old.pop('onset_guard')
    original=json.dumps(old).encode();target.write_bytes(original)
    provision_voice(root, source, assets)
    assert json.loads(target.read_text())['paragraph_pause_ms']==500
    assert any(p.read_bytes()==original for p in target.parent.glob('default-narration.before-vox10-*.json'))


def test_switch_idempotence_and_exact_rollback(installation, monkeypatch):
    import video_ai.voxcpm.deployment as deploy
    root, source, assets, recipe = installation
    deploy.provision_voice(root, source, assets)
    config=root/'shared/config/production.json'
    original=b'{"services":{"tts":"http://127.0.0.1:9880"},"tts":{"engine":"gpt-sovits"},"keep":true}\r\n'
    config.write_bytes(original)
    validated=[]
    monkeypatch.setattr(deploy,'validate_configuration',lambda path,raw:validated.append(raw))
    monkeypatch.setattr(deploy,'verify_installation',lambda *args,**kwargs:None)
    backup=deploy.activate(config,root,source)
    assert backup.read_bytes()==original
    current=json.loads(config.read_text())
    assert current['tts']['narration']['onset_guard']['text']=='下面继续讲述。'
    assert current['tts']['narration']['paragraph_pause_ms']==500
    assert current['keep'] is True and len(validated)==1
    assert deploy.activate(config,root,source) is None
    deploy.restore_backup(config,backup)
    assert config.read_bytes()==original
    with pytest.raises(ValueError):deploy.restore_backup(config,source/'unrelated.json')


def test_modified_default_cannot_silently_change_approved_voice(installation, monkeypatch):
    import video_ai.voxcpm.deployment as deploy
    root, source, assets, recipe = installation
    deploy.provision_voice(root, source, assets)
    default=root/'shared/config/tts/default-narration.json'
    recipe['prompt_text']='擅自替换';default.write_text(json.dumps(recipe),encoding='utf-8')
    config=root/'shared/config/production.json';config.write_text('{}')
    with pytest.raises(ValueError,match='approved'):
        deploy.activate(config,root,source)
    assert config.read_text()=='{}'


def test_relocate_only_shared_paths_and_vox_venv(installation):
    from video_ai.voxcpm.deployment import relocate
    root, source, _, _ = installation
    old='D:/old runtime'
    config=root/'shared/config/production.json';config.parent.mkdir(parents=True)
    config.write_text(json.dumps(dict(runtime_root=old,project_root=old+'/shared',
        output_root=old+'/output',voice_config=old+'/shared/config/voice.json',
        tools=dict(tts_python=old+'/shared/tools/GPT-SoVITS/runtime/python.exe'),
        workflows=dict(wan='D:/old source/workflows/wan.json'),
        tts=dict(narration=dict(voice_profile=old+'/shared/assets/voices/id/voice.json',
            prompt_text='D:/old runtime 是正文的一部分')))),encoding='utf-8')
    history=root/'work/old/production/inputs/config.json';history.parent.mkdir(parents=True)
    history.write_bytes(config.read_bytes());original=history.read_bytes()
    venv=root/'shared/envs/voxcpm2/pyvenv.cfg';venv.parent.mkdir(parents=True)
    venv.write_text('home = D:/old python\nversion = 3.12.10\nexecutable = D:/old python/python.exe\ncommand = D:/old python/python.exe -m venv old\n')
    relocate(root,source,config)
    raw=json.loads(config.read_text())
    assert raw['runtime_root']==str(root)
    assert raw['voice_config']==str(root/'shared/config/voice.json')
    assert raw['workflows']['wan']==str(source/'workflows/wan.json')
    assert raw['tts']['narration']['prompt_text']=='D:/old runtime 是正文的一部分'
    assert history.read_bytes()==original
    assert 'old python' not in venv.read_text()
    assert str(root/'shared/tools/python312') in venv.read_text()


def test_relocate_ignores_unrelated_configuration_records(installation):
    from video_ai.voxcpm.deployment import relocate
    root, source, _, _ = installation
    config=root/'shared/config/production.json';config.parent.mkdir(parents=True)
    config.write_text(json.dumps(dict(runtime_root='D:/old',voice_config='D:/old/shared/config/voice.json')))
    unrelated=config.parent/'third-party.json';unrelated.write_text('[1,2,3]')
    relocate(root,source,config)
    assert unrelated.read_text()=='[1,2,3]'


def test_missing_backend_prevents_default_switch(installation, monkeypatch):
    import video_ai.voxcpm.deployment as deploy
    root, source, assets, _=installation
    deploy.provision_voice(root,source,assets)
    config=root/'shared/config/production.json';config.write_text('{"services":{"tts":"http://127.0.0.1:9880"}}')
    original=config.read_bytes()
    monkeypatch.setattr(deploy,'validate_configuration',lambda *args:None)
    def missing(*args,**kwargs):raise ValueError('missing Vox backend')
    monkeypatch.setattr(deploy,'verify_installation',missing)
    with pytest.raises(ValueError,match='missing Vox'):deploy.activate(config,root,source)
    assert config.read_bytes()==original


def test_source_identity_requires_detached_checkout_without_git(tmp_path):
    from video_ai.voxcpm.source_identity import source_revision
    folder=tmp_path/'.git';folder.mkdir()
    revision='a'*40
    (folder/'HEAD').write_text(revision+'\n',encoding='ascii')
    assert source_revision(tmp_path)==revision
    (folder/'HEAD').write_text('ref: refs/heads/main\n',encoding='ascii')
    with pytest.raises(ValueError,match='detached'):source_revision(tmp_path)


def test_publish_keeps_original_until_verified_candidate_is_ready(installation,monkeypatch):
    import video_ai.voxcpm.deployment as deploy
    root,source,assets,recipe=installation;deploy.provision_voice(root,source,assets)
    config=root/'shared/config/production.json';config.write_bytes(b'{"old":true}\r\n')
    original=config.read_bytes()
    candidate=config.with_name('production.pending-vox10.json')
    candidate.write_text(json.dumps(dict(tts=dict(engine='gpt-sovits'))))
    with pytest.raises(ValueError,match='approved'):deploy.publish_configuration(candidate,config,root,source)
    assert config.read_bytes()==original
    raw=dict(tts=dict(engine='voxcpm2',model_revision=recipe['model_revision'],narration=recipe))
    candidate.write_text(json.dumps(raw),encoding='utf-8')
    monkeypatch.setattr(deploy,'validate_configuration',lambda *args:None)
    backup=deploy.publish_configuration(candidate,config,root,source)
    assert backup.read_bytes()==original
    assert json.loads(config.read_text(encoding='utf-8'))==raw


def test_interrupted_relocation_keeps_old_root_until_dependencies_are_written(installation,monkeypatch):
    import video_ai.voxcpm.deployment as deploy
    root,source,_,_=installation
    config=root/'shared/config/production.json';config.parent.mkdir(parents=True)
    config.write_text(json.dumps(dict(runtime_root='D:/old',voice_config='D:/old/shared/config/voice.json')))
    voice=config.with_name('voice.json');voice.write_text('{"reference_audio":"D:/old/shared/assets/voice.wav"}')
    write=deploy.write_record
    def interrupt(path,raw):
        if Path(path)==config:raise RuntimeError('interrupted before root commit')
        return write(path,raw)
    monkeypatch.setattr(deploy,'write_record',interrupt)
    with pytest.raises(RuntimeError):deploy.relocate(root,source,config)
    assert json.loads(config.read_text())['runtime_root']=='D:/old'
    assert json.loads(voice.read_text(encoding='utf-8'))['reference_audio']==str(root/'shared/assets/voice.wav')
    monkeypatch.setattr(deploy,'write_record',write)
    deploy.relocate(root,source,config)
    assert json.loads(config.read_text())['runtime_root']==str(root)
