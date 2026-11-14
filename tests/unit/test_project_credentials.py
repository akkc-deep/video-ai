import json

import pytest

from video_ai import credentials


def test_local_credentials_and_environment_priority(tmp_path,monkeypatch):
    path=tmp_path/'secrets.local.json'
    path.write_text(json.dumps({'AK':'local-ak','SK':'local-sk'}),encoding='utf-8')
    monkeypatch.setattr(credentials,'PROJECT_CREDENTIALS_FILE',path)
    monkeypatch.delenv('AK',raising=False);monkeypatch.delenv('SK',raising=False)
    assert credentials.read_credentials('AK','SK')==('local-ak','local-sk')
    monkeypatch.setenv('AK','env-ak')
    assert credentials.read_credentials('AK','SK')==('env-ak','local-sk')
    path.write_text('{private-invalid-secret',encoding='utf-8')
    with pytest.raises(ValueError) as error:credentials.read_credentials('AK','SK')
    assert 'private-invalid-secret' not in str(error.value)
    monkeypatch.setenv('SK','env-sk')
    assert credentials.read_credentials('AK','SK')==('env-ak','env-sk')


def test_missing_file_or_empty_values_return_no_credentials(tmp_path,monkeypatch):
    path=tmp_path/'secrets.local.json'
    monkeypatch.setattr(credentials,'PROJECT_CREDENTIALS_FILE',path)
    monkeypatch.delenv('AK',raising=False);monkeypatch.delenv('SK',raising=False)
    assert credentials.read_credentials('AK','SK')==(None,None)
    path.write_text('{"AK":"  ","SK":""}',encoding='utf-8')
    assert credentials.read_credentials('AK','SK')==(None,None)


def test_jimeng_reads_project_file_without_environment_variables(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from video_ai.adapters.jimeng import JimengClient
    path=tmp_path/'secrets.local.json'
    path.write_text('{"PROJECT_AK":"file-ak","PROJECT_SK":"file-sk"}',encoding='utf-8')
    monkeypatch.setattr(credentials,'PROJECT_CREDENTIALS_FILE',path)
    monkeypatch.delenv('PROJECT_AK',raising=False);monkeypatch.delenv('PROJECT_SK',raising=False)
    client=JimengClient(SimpleNamespace(access_key_env='PROJECT_AK',secret_key_env='PROJECT_SK'))
    assert client.check_credentials()==('file-ak','file-sk')
