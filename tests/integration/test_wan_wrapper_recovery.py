import json
from uuid import uuid4

import pytest

from video_ai.experiments import wan_wrapper_backend as b
from tests.unit.test_wan_wrapper_backend import fixture, profiles


def experiment(tmp_path,transport):
    ps=profiles();f=fixture();b.freeze_comparison(tmp_path,ps,f)
    return b.WrapperExperimentClient(tmp_path,profile_digest=ps['control'].digest(),port=8297,http=transport),b.build_graph(ps['control'],f)


def test_lost_response_resumes_unique_original_without_second_post(tmp_path):
    calls=[];pid=str(uuid4())
    def transport(method,route,payload=None):
        calls.append(method)
        if method=='POST':raise TimeoutError('response lost')
        intent=b.read(tmp_path/'trials/control_1/intent.json')
        return {pid:{'prompt':[0,pid,graph,{'client_id':intent['client_id']}]}} if route=='/history' else {}
    c,graph=experiment(tmp_path,transport)
    with pytest.raises(TimeoutError):c.submit('control_1',graph)
    assert c.recover('control_1',graph)==pid
    assert calls.count('POST')==1


def test_unknown_never_reposts(tmp_path):
    calls=[]
    def transport(method,*a):
        calls.append(method)
        if method=='POST':raise TimeoutError()
        return {}
    c,g=experiment(tmp_path,transport)
    with pytest.raises(TimeoutError):c.submit('control_1',g)
    for _ in range(2):
        with pytest.raises(Exception,match='unknown'):c.recover('control_1',g)
    assert calls.count('POST')==1


@pytest.mark.parametrize('pid',[None,'not-uuid',str(uuid4()).upper()])
def test_invalid_recovered_uuid_refused(tmp_path,pid):
    c,g=experiment(tmp_path,lambda *a:{})
    c.bind('control_1',g)
    folder=tmp_path/'trials/control_1'
    b.write_once(folder/'intent.json',dict(client_id=str(uuid4()),graph=g,graph_sha256=b.digest(g)))
    b.write_once(folder/'accepted.json',dict(prompt_id=pid,recovered=True))
    with pytest.raises(ValueError):c.recover('control_1',g)


def test_conflicting_post_and_accepted_refused(tmp_path):
    c,g=experiment(tmp_path,lambda *a:pytest.fail('no HTTP'))
    c.bind('control_1',g);folder=tmp_path/'trials/control_1'
    b.write_once(folder/'intent.json',dict(client_id=str(uuid4()),graph=g,graph_sha256=b.digest(g)))
    b.write_once(folder/'accepted.json',dict(prompt_id=str(uuid4()),recovered=False))
    b.write_once(folder/'post.response.json',dict(prompt_id=str(uuid4()),node_errors={}))
    with pytest.raises(ValueError,match='conflict'):c.submit('control_1',g)


def test_fast_requires_current_pair_and_exact_control_review(tmp_path):
    ps=profiles();f=fixture();marker=b.freeze_comparison(tmp_path,ps,f)
    c=b.WrapperExperimentClient(tmp_path,profile_digest=ps['fast'].digest(),port=8297,http=lambda *a:pytest.fail('no HTTP'))
    with pytest.raises((ValueError,FileNotFoundError)):c.submit('fast_1',b.build_graph(ps['fast'],f))
