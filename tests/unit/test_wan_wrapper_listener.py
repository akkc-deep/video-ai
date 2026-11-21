"""Native netstat headers use an OEM code page even under Python -X utf8."""
from types import SimpleNamespace

import pytest

from video_ai.experiments import whole_scene_runner as runner
from tests.unit.test_wan_wrapper_host_budget import controller_module


def entry(name):
    return runner._listener_owned if name=='client' else controller_module().owned_listener


@pytest.mark.parametrize('name',['client','controller'])
def test_localized_netstat_header_does_not_erase_valid_owned_listener(monkeypatch,name):
    payload='活动连接\r\n'.encode('gbk')+b'  TCP    127.0.0.1:8297   0.0.0.0:0   LISTENING   12804\r\n'
    def native(argv,**kwargs):
        assert argv==['netstat','-ano','-p','tcp']
        # A failed subprocess reader thread leaves stdout=None in the observed bug.
        return SimpleNamespace(returncode=0,stdout=None if kwargs.get('text') else payload)
    monkeypatch.setattr(runner.subprocess,'run',native)
    entry(name)(8297,12804)


@pytest.mark.parametrize('name',['client','controller'])
@pytest.mark.parametrize('payload,code',[
    (b'TCP 127.0.0.1:8297 0.0.0.0:0 LISTENING 999\r\n',0),
    (b'TCP 0.0.0.0:8297 0.0.0.0:0 LISTENING 12804\r\n',0),
    (b'TCP 127.0.0.1:9000 0.0.0.0:0 LISTENING 12804\r\n',0),
    (b'TCP 127.0.0.1:8297 0.0.0.0:0 LISTENING 12804\r\n'*2,0),
    (b'TCP 127.0.0.1:8297 LISTENING\r\n',0),
    (b'TCP 127.0.0.1:8297 0.0.0.0:0 LISTENING 12804\r\n',1),
    (None,0),
])
def test_unproved_listener_still_fails_closed(monkeypatch,name,payload,code):
    monkeypatch.setattr(runner.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=code,stdout=payload))
    with pytest.raises((RuntimeError,ValueError)):entry(name)(8297,12804)
