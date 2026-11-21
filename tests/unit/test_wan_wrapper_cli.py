import importlib.util
from pathlib import Path
import pytest


def cli():
    path=Path(__file__).resolve().parents[2]/'scripts/benchmark_wan_wrapper.py'
    spec=importlib.util.spec_from_file_location('wrapper_cli',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


@pytest.mark.parametrize('command',['run','admit-pair'])
def test_gpu_actions_without_authorization_never_touch_transport(tmp_path,command,monkeypatch):
    module=cli()
    monkeypatch.setattr(module,'WrapperExperimentClient',lambda *a,**kw:pytest.fail('no transport without auth'))
    with pytest.raises(ValueError,match='authorization'):module.main([command,'--root',str(tmp_path)])
    assert list(tmp_path.iterdir())==[]


def test_recover_missing_intent_never_creates_generation(tmp_path):
    from tests.unit.test_wan_wrapper_backend import profiles,fixture
    from video_ai.experiments.wan_wrapper_backend import freeze_comparison
    freeze_comparison(tmp_path,profiles(),fixture())
    with pytest.raises(ValueError,match='intent'):cli().main(['recover','--root',str(tmp_path)])
    assert not (tmp_path/'trials/control_1/intent.json').exists()


def test_graph_offline_fixture_has_no_network(tmp_path):
    from tests.unit.test_wan_wrapper_backend import profiles,fixture
    from video_ai.experiments.wan_wrapper_backend import freeze_comparison,read,digest
    freeze_comparison(tmp_path,profiles(),fixture())
    assert cli().main(['graph','--root',str(tmp_path),'--mode','fast'])==0
    assert read(tmp_path/'graphs/fast.json')==read(tmp_path/'frozen/graphs/fast.json')


def test_admission_response_loss_gets_original_only(tmp_path):
    from video_ai.experiments import wan_wrapper_backend as b
    from tests.unit.test_wan_wrapper_backend import profiles,fixture
    ps=profiles();b.freeze_comparison(tmp_path,ps,fixture());calls=[]
    def http(method,route,payload=None):
        calls.append((method,route))
        if method=='POST':raise TimeoutError()
        return {'status':'unknown'}
    c=b.WrapperExperimentClient(tmp_path,profile_digest=ps['fast'].digest(),port=8297,http=http)
    with pytest.raises(TimeoutError):c.admit_pair()
    assert c.admit_pair()=={'status':'unknown'}
    assert [v[0] for v in calls]==['POST','GET']
    assert calls[1][1].startswith('/lva07/admission/')
